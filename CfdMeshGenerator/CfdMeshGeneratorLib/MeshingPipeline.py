"""The meshing pipeline of the CFD Mesh Generator module, with nothing of Slicer in it.

This is VMTK's vmtkmeshgenerator script as a class. The script itself cannot be run here: it
drives the pipeline through the `vmtk` Python package, which the Slicer extension does not
install - only the wrapped C++ classes are available. The pipeline below is the same one, built
out of those classes directly, and every parameter the script exposes is exposed here under the
same name, meaning and default.

It lives apart from the module so that it can be run in a process of its own: the module hands a
surface and the parameters to MeshingWorker, which builds a MeshingPipeline in a plain PythonSlicer
and runs it there. Nothing here may therefore need the application - no qt, no slicer.app, no
scene - and everything it says is said through logging and the step callback.
"""

import dataclasses
import enum
import logging
import time

import vtk

from CfdMeshGeneratorLib import FTetWild, Netgen

try:
    from slicer.i18n import tr as _
except ImportError:
    # Outside Slicer's Python there is nothing to translate with.
    def _(text):
        return text


# What vmtkmeshgenerator uses for an edge length that is not to be limited. It is not infinity
# because the remesher compares areas against it; it only has to be past any real mesh. The module
# offers 0 in its place, which reads better in a spin box (see meshLengthLimit).
UNLIMITED_EDGE_LENGTH = 1e16

# Fewest substeps the boundary layer may be swept in. The generator spends the first hundredth of
# them on an initial warp, so below a hundred it spends none: it then reads the points that warp
# was to have written, which it never allocated, and what it finds there is whatever the process
# had at that address (vtkvmtkBoundaryLayerGenerator's IncrementalWarpVectors).
MINIMUM_SUBSTEPS = 100

# Point data arrays saying which vessel end each boundary point belongs to, under the names VMTK's
# own filters read and write by default (vtkvmtkBoundaryLabels::GetDefaultBoundaryLabelsArrayName),
# which are the names Clip Vessel writes them with. A boundary that carries them is named by the
# end it closes rather than by the order the extractor happened to find it in, which is what lets a
# cap be given the same id every run - and the same id Clip Vessel gives it. The label is that id:
# boundary labels and face ids are one numbering, so the end labelled 2 in the point data is the
# face numbered 2 in the cell data, here and in Clip Vessel. Every filter here that rebuilds the
# mesh carries them across, the surface projection putting them back on what the remesher hands
# over, so they are still there when the inner surface is capped. They can be changed so that a
# surface already carrying arrays under these names, meaning something else, is not mistaken for a
# labeled one.
DEFAULT_BOUNDARY_LABELS_ARRAY_NAME = "BoundaryLabels"
DEFAULT_BOUNDARY_POINT_ORDER_ARRAY_NAME = "BoundaryPointOrder"

# Cell data array saying which cells are caps: 1 or more on a cap, anything less on the wall.
# Where a surface carries it, it is what tells the caps from the wall, and the face ids are free
# to number the wall in as many pieces as they like; where it does not, the wall is
# wallCellEntityId and every face above it is a cap. The name SimVascular's models come with.
DEFAULT_CAP_IDS_ARRAY_NAME = "CapID"

# What to install when fTetWild is asked for; see FTetWild for where it is installed to.
FTETWILD_REQUIREMENT = FTetWild.REQUIREMENT

# What to install when Netgen is asked for, which is always into this Python; see Netgen.
NETGEN_REQUIREMENT = Netgen.REQUIREMENT


class ElementSizeMode(enum.Enum):
    """Where the target size of a surface element comes from (vmtkmeshgenerator's elementsizemode).

    The remesher works in areas throughout; both modes give it the edge length of the equilateral
    triangle of that area, either as one number for the whole surface or as a value per point
    carried on the surface itself.
    """

    EDGE_LENGTH = "edgelength"
    EDGE_LENGTH_ARRAY = "edgelengtharray"

    def label(self):
        return {
            ElementSizeMode.EDGE_LENGTH: _("Constant edge length"),
            ElementSizeMode.EDGE_LENGTH_ARRAY: _("Edge length from array"),
        }[self]


class CappingMethod(enum.Enum):
    """Shape of the mesh that closes an open boundary of the input surface.

    "Simple" fills each boundary with a fan of triangles, which is what the clipped end of a
    vessel lumen wants. The two annular methods close the gap between an inner and an outer
    boundary instead, which is the shape the end of a vessel wall of finite thickness has;
    "concave annular" allows that ring to be non-convex.
    """

    SIMPLE = "simple"
    ANNULAR = "annular"
    CONCAVE_ANNULAR = "concaveannular"

    def label(self):
        return {
            CappingMethod.SIMPLE: _("Simple"),
            CappingMethod.ANNULAR: _("Annular"),
            CappingMethod.CONCAVE_ANNULAR: _("Concave annular"),
        }[self]


class Mesher(enum.Enum):
    """Which mesher fills the surface with tetrahedra.

    They answer differently shaped questions. TetGen is handed the surface as a boundary it may
    not touch, and returns the same triangles it was given with tetrahedra behind them; the mesh
    meets the surface exactly, and a surface it cannot fill is one it fails on - loudly at best.
    fTetWild is handed the surface as a shape to stay within a tolerance of, and meshes what it
    makes of it; the boundary comes back retriangulated and slightly moved, and almost nothing
    makes it fail.

    Netgen is asked TetGen's question and brings fTetWild's strength to it: it keeps the surface
    it is given, triangle for triangle, and fills the inside of it, sizing the tetrahedra by
    position where a size per point is given. A surface it cannot fill it gives up on, quietly,
    with no tetrahedra behind it.

    Neither of the last two is built into the extension: fTetWild arrives as the pytetwild
    package and Netgen as netgen-mesher, each downloaded from PyPI the first time it is asked
    for.
    """

    TETGEN = "tetgen"
    FTETWILD = "ftetwild"
    NETGEN = "netgen"

    def label(self):
        return {
            Mesher.TETGEN: _("TetGen"),
            Mesher.FTETWILD: _("fTetWild"),
            Mesher.NETGEN: _("Netgen"),
        }[self]

    @property
    def keepsTheSurface(self):
        """Whether the mesher hands back the triangles it was given, over the same points, with
        the tetrahedra behind them - or a boundary of its own making within a tolerance of them.
        Which of the two decides how a boundary layer is put together with the tetrahedra; see
        MeshingPipeline.meshWithBoundaryLayer."""
        return self != Mesher.FTETWILD

    @property
    def sizesByPosition(self):
        """Whether the mesher reads a target edge length per point of the volume, so that the
        tetrahedra can be graded the way the surface is."""
        return self != Mesher.TETGEN


@dataclasses.dataclass
class VolumeMeshing:
    """What the mesher needs to know to fill a surface, whichever mesher it is.

    Gathered into one object so that the steps between the surface and the volume - which differ
    by whether there is a boundary layer, not by which mesher is running - can carry it through
    without naming the parameters of either.
    """

    mesher: str = Mesher.TETGEN.value

    # The edge length the tetrahedra aim for: the size the surface was meshed at, scaled.
    edgeLength: float = 0.8

    # A target edge length per point of a background mesh, as (points, tetrahedra, lengths).
    # fTetWild interpolates it over the tetrahedra; Netgen reads the points and the lengths
    # alone, lowering its own size field at each. None asks for one size throughout. TetGen
    # ignores it: the switch that reads a size per point takes it from a background mesh of its
    # own making and answers differently each run (see runTetGen).
    sizingField: object = None

    # How far the boundary of the mesh may sit from the surface it was made for, in mm. Only
    # fTetWild has such a thing; 0 asks for its default, a thousandth of the bounding box.
    surfaceTolerance: float = 0.0

    # fTetWild stops improving the mesh once its worst element scores below this. The score is a
    # conformal AMIPS energy, which is 3 for a regular tetrahedron and grows without bound as one
    # flattens.
    stopEnergy: float = 10.0
    maxOptimizationPasses: int = 80

    # Make the mesh as coarse as the tolerance allows, rather than as fine as asked for.
    coarsen: bool = False

    # How fast Netgen lets the element size change from one element to the next, 0 to 1: at 1
    # the tetrahedra grow away from the surface as fast as they can, and near 0 the whole volume
    # is meshed at the size of the finest part of the surface.
    netgenGrading: float = 0.3

    # Passes Netgen spends improving the mesh once it has filled the surface.
    netgenOptimizationSteps: int = 3



class MeshingPipeline:
    """The meshing pipeline, one step per vmtk script that vmtkmeshgenerator drives.

    generateMesh() runs the whole of it; the steps are methods of their own so that a caller can
    run one alone - cap a surface, remesh it - which is what the tests do.
    """

    # Entity id given to the cells that came from the input surface. The caps are numbered upwards
    # from it, so a wall cell can always be told from a cap cell - which is what makes the id array
    # usable as a boundary condition map, and what lets the remesher be pointed at the caps alone.
    # It is also what the boundary labels of a surface are numbered above, so that a label is the
    # id of the cap that closes it (see DEFAULT_BOUNDARY_LABELS_ARRAY_NAME); a surface labeled for
    # some other wall would have its ends capped over the faces of this one.
    wallCellEntityId = 1

    # Id parked on the sidewall cells of a boundary layer that was not grown over the caps, until
    # each of them is handed the id of the cap it ran into (see nameSidewallsAfterTheirCap). Any
    # value no cap can take would do; this is the one vmtkmeshgenerator uses.
    placeholderCellEntityId = 9999


    # The names the boundary labels are read under when a caller gives none of its own; see
    # DEFAULT_BOUNDARY_LABELS_ARRAY_NAME for what they hold and why they travel with the mesh.
    boundaryLabelsArrayName = DEFAULT_BOUNDARY_LABELS_ARRAY_NAME
    boundaryPointOrderArrayName = DEFAULT_BOUNDARY_POINT_ORDER_ARRAY_NAME

    # Smallest angle, in radians, that an edge may subtend before the remesher collapses it. This
    # is vmtksurfaceremeshing's own default rather than the filter's, which is more than twice as
    # large; vmtkmeshgenerator does not offer it (see remeshSurface).
    collapseAngleThreshold = 0.2

    def __init__(self) -> None:
        # Whether the last run ended with the mesher refusing to fill the surface it was given.
        # The mesh is handed back anyway - what there is of it is the thing to look at to see why
        # - so this is what says the result is not a finished mesh (see process).
        self.lastTetrahedralizationFailed = False
        # The step log() is currently announcing, and when it started, so that the next call - or
        # the end of the run - can say how long it took. None between runs and once the last step
        # of one has been reported.
        self._stepName = None
        self._stepStartTime = None
        # Called with the name of each step as it starts, for whoever is showing progress. None
        # leaves the step to the log alone.
        self.stepCallback = None
        # The Python interpreter fTetWild is run in, or None to run it in this process. It is a
        # separate one where this process's Python cannot host pytetwild; see FTetWild.
        self.fTetWildPython = None
        # Which face ids are caps for the run in progress; see isCapId().
        self._capFaceIds = None
        self._largestInputFaceId = None

    #
    # Which meshers this installation can offer.
    #

    @staticmethod
    def isTetGenAvailable():
        """Whether VMTK was built with TetGen. Its licence makes that a decision, so a build
        that was made without it has no wrapper class at all rather than one that refuses."""
        import vtkvmtkMiscPython as vtkvmtkMisc

        return hasattr(vtkvmtkMisc, "vtkvmtkTetGenWrapper")

    def isFTetWildAvailable(self):
        """Whether fTetWild can be used right now, in the interpreter it would be run in. It is
        imported rather than looked for: a package that is installed but cannot be imported is
        not one to offer."""
        return FTetWild.isAvailable(self.fTetWildPython)

    def requireFTetWild(self):
        """Raise RuntimeError, saying how to get it, if fTetWild cannot be run."""
        if self.isFTetWildAvailable():
            return
        raise RuntimeError(_(
            "fTetWild is not installed. It comes as the Python package {requirement}, which "
            "the module offers to download when fTetWild is chosen and Apply is pressed."
        ).format(requirement=FTetWild.REQUIREMENT))

    @staticmethod
    def isNetgenAvailable():
        """Whether Netgen can be used right now, in this process, which is the only place it is
        run. Imported rather than looked for, as fTetWild is."""
        return Netgen.isAvailable()

    def requireNetgen(self):
        """Raise RuntimeError, saying how to get it, if Netgen cannot be run."""
        if self.isNetgenAvailable():
            return
        raise RuntimeError(_(
            "Netgen is not installed. It comes as the Python package {requirement}, which the "
            "module offers to download when Netgen is chosen and Apply is pressed."
        ).format(requirement=Netgen.REQUIREMENT))

    def availableMeshers(self):
        """The meshers this installation can offer, in the order they are presented."""
        return [mesher for mesher in Mesher
                if mesher != Mesher.TETGEN or self.isTetGenAvailable()]

    @staticmethod
    def splitArrayNames(names):
        """The names in a comma-separated list, with the whitespace around each taken off and
        empty entries dropped: what a text field holding several array names comes to."""
        return [name.strip() for name in names.split(",") if name.strip()]

    @classmethod
    def chooseCellEntityIdsArrayName(cls, surface, names):
        """The name the face ids are read from and written under, out of the names offered.

        The first of them the surface carries, so that a surface labelled by any of the names
        in use - VMTK's CellEntityIds, SimVascular's ModelFaceID - is read as labelled without
        the name having to be typed in. Where it carries none of them the first name is used,
        which is then the name the faces are written under after being numbered afresh.

        :param names: the names as a list, or as one comma-separated string.
        """
        if isinstance(names, str):
            names = cls.splitArrayNames(names)
        if not names:
            raise ValueError(_("No face ids array name was given"))
        cellData = surface.GetCellData() if surface is not None else None
        for name in names:
            if cellData is not None and cellData.GetArray(name) is not None:
                return name
        return names[0]

    def generateMesh(self, surface, *,
                     targetEdgeLength=1.0,
                     targetEdgeLengthArrayName="",
                     targetEdgeLengthFactor=1.0,
                     triangleSplitFactor=5.0,
                     endcapsEdgeLengthFactor=1.0,
                     maxEdgeLength=0.0,
                     minEdgeLength=0.0,
                     cellEntityIdsArrayName="CellEntityIds",
                     capIdsArrayName=DEFAULT_CAP_IDS_ARRAY_NAME,
                     boundaryLabelsArrayName=None,
                     boundaryPointOrderArrayName=None,
                     elementSizeMode="edgelength",
                     cappingMethod="simple",
                     skipCapping=False,
                     skipRemeshing=False,
                     remeshCapsOnly=False,
                     mesher=Mesher.TETGEN.value,
                     volumeElementScaleFactor=0.8,
                     surfaceTolerance=0.0,
                     stopEnergy=10.0,
                     maxOptimizationPasses=80,
                     coarsen=False,
                     netgenGrading=0.3,
                     netgenOptimizationSteps=3,
                     boundaryLayer=False,
                     boundaryLayerOnCaps=False,
                     numberOfSubLayers=2,
                     subLayerRatio=0.5,
                     boundaryLayerThicknessFactor=0.25,
                     numberOfSubsteps=2000,
                     relaxation=0.01,
                     localCorrectionFactor=0.45,
                     tetrahedralize=False,
                     carriedCellArrays=()):
        """Fill the surface with tetrahedra, the way VMTK's vmtkmeshgenerator does.

        The surface is capped, remeshed into near equilateral triangles, optionally lined on the
        inside with a prismatic boundary layer, and whatever space is left over is filled by the
        mesher asked for. Every cell of the result carries an entity id in cellEntityIdsArrayName:
        wallCellEntityId for the wall, one id per cap above it, and 0 for the volume elements.

        :param surface: the surface to mesh, as vtkPolyData. It is not modified.
        :param targetEdgeLength: edge length the surface triangles aim for, in mm.
        :param targetEdgeLengthArrayName: point data array holding a target edge length per point,
          read when elementSizeMode is "edgelengtharray". It also gives the boundary layer its
          thickness, which is then a fraction of the local edge length rather than a constant.
        :param targetEdgeLengthFactor: what the values of that array are multiplied by.
        :param triangleSplitFactor: how much larger than the target a triangle has to be before
          the remesher splits it about its centre rather than subdividing an edge.
        :param endcapsEdgeLengthFactor: multiplies the target edge length for the caps, which are
          remeshed on their own only when a boundary layer stops short of them.
        :param maxEdgeLength: upper limit on the edge length, 0 for none. It also limits the
          thickness of the boundary layer.
        :param minEdgeLength: lower limit on the edge length.
        :param cellEntityIdsArrayName: name of the cell array the face ids are written into.
        :param capIdsArrayName: cell data array of the input surface saying which cells are caps,
          1 or more on a cap. Where the surface carries it, a face is a cap if its cells say so,
          and the wall may be numbered in any number of faces; where it does not, the wall is
          wallCellEntityId and every face above it is a cap. None or an empty name asks for the
          latter outright. See isCapId().
        :param boundaryLabelsArrayName: point data array saying which vessel end each boundary
          point belongs to, which is what lets a cap be given the same id every run - and the
          same id Clip Vessel, which writes the array, gives it. None uses the logic default.
        :param boundaryPointOrderArrayName: point data array holding each boundary point's index
          within its own boundary, which travels with the labels. None uses the logic default.
        :param elementSizeMode: "edgelength" for one length over the whole surface, or
          "edgelengtharray" to read it per point from targetEdgeLengthArrayName.
        :param cappingMethod: "simple", "annular" or "concaveannular"; see CappingMethod.
        :param skipCapping: take the surface as already closed, and do not cap it.
        :param skipRemeshing: fill the surface as it is, without remeshing it first.
        :param remeshCapsOnly: remesh the caps and leave the wall as it is.
        :param mesher: which mesher fills the surface, "tetgen", "ftetwild" or "netgen"; see
          Mesher.
        :param volumeElementScaleFactor: size of the tetrahedra relative to the target edge
          length of the surface.
        :param surfaceTolerance: how far the boundary of the mesh may sit from the surface it
          was made for, in mm, 0 for the mesher's own default. fTetWild only: TetGen keeps the
          surface it is given exactly.
        :param stopEnergy: how good the worst element has to be before fTetWild stops improving
          the mesh. 3 is a regular tetrahedron and there is no upper bound.
        :param maxOptimizationPasses: how many passes fTetWild may spend improving the mesh.
        :param coarsen: make the mesh as coarse as the tolerance allows rather than as fine as
          asked for (fTetWild only).
        :param netgenGrading: how fast Netgen lets the element size change from one element to
          the next, 0 to 1 (Netgen only).
        :param netgenOptimizationSteps: passes Netgen spends improving the mesh once it has
          filled the surface (Netgen only).
        :param boundaryLayer: line the wall on the inside with layers of prisms, which is what
          resolves the velocity gradient at the wall.
        :param boundaryLayerOnCaps: grow the boundary layer over the caps as well as the wall.
          Off keeps each cap one flat face with the flow meeting it directly, which is what an
          inlet or outlet condition wants; the caps are then made after the layer, on the inner
          surface. A surface that arrived already capped has its caps taken off first and their
          ids put back on the ones made in their place, so that the setting means the same thing
          whether the ends were closed before the surface got here or not.
        :param numberOfSubLayers: number of prism layers.
        :param subLayerRatio: thickness of each layer over the thickness of the next one out.
        :param boundaryLayerThicknessFactor: total thickness of the boundary layer, as a fraction
          of the target edge length.
        :param numberOfSubsteps: steps the inner surface is marched inwards in. More of them let
          it get around a tight corner without folding over itself. Raised to MINIMUM_SUBSTEPS
          when it is asked for below that.
        :param relaxation: how far the inner surface moves per substep.
        :param localCorrectionFactor: how strongly a warp vector is pulled back towards its
          neighbours where the layer starts to tangle.
        :param tetrahedralize: split every prism of the boundary layer into tetrahedra, for a
          solver that takes nothing else.
        :param carriedCellArrays: names of cell data arrays of the input surface to carry onto
          the faces of the output, face by face; see carryCellArrays().
        :return: (mesh, remeshedSurface), a vtkUnstructuredGrid and the vtkPolyData it was built
          on. The surface is the capped input when remeshing was skipped.
        """
        import vtkvmtkMiscPython as vtkvmtkMisc

        if surface is None or surface.GetNumberOfCells() == 0:
            raise ValueError(_("The input surface is empty"))

        # Asked and answered before anything is meshed, so that a mesher that cannot run says so
        # now rather than after the minutes the surface takes to prepare.
        try:
            mesher = Mesher(mesher).value
        except ValueError:
            raise ValueError(_("There is no mesher called \"{mesher}\". The ones there are: "
                               "{available}.").format(
                mesher=mesher,
                available=", ".join(choice.value for choice in Mesher))) from None
        if mesher == Mesher.TETGEN.value and not self.isTetGenAvailable():
            raise RuntimeError(_("This installation was built without TetGen, which its licence "
                                 "makes a decision rather than a default. Choose fTetWild or "
                                 "Netgen."))
        if mesher == Mesher.FTETWILD.value:
            self.requireFTetWild()
        if mesher == Mesher.NETGEN.value:
            self.requireNetgen()

        boundaryLabelsArrayName = boundaryLabelsArrayName or self.boundaryLabelsArrayName
        boundaryPointOrderArrayName = (boundaryPointOrderArrayName
                                       or self.boundaryPointOrderArrayName)

        self._capFaceIds, self._largestInputFaceId = self.capFaceIdsOf(
            surface, cellEntityIdsArrayName, capIdsArrayName)

        self.lastTetrahedralizationFailed = False
        # A run that was interrupted by an earlier exception can leave a step open; start clean.
        self._stepName = None
        self._stepStartTime = None

        cellData = surface.GetCellData()
        if cellData.GetArray(cellEntityIdsArrayName) is None and cellData.GetNumberOfArrays() > 0:
            # Worth saying out loud: the ids are what hold one face against another while the
            # surface is remeshed, so a surface whose labels are not read comes back not merely
            # unlabelled but with the boundaries between its faces smoothed away.
            logging.warning(
                "The input surface carries no %s array, so its faces are numbered afresh and no "
                "boundary it already had is held while it is remeshed. It does carry: %s.",
                cellEntityIdsArrayName,
                ", ".join(cellData.GetArrayName(index) or "(unnamed)"
                          for index in range(cellData.GetNumberOfArrays())))

        maxEdgeLength = self.meshLengthLimit(maxEdgeLength)
        # Not a preference but a floor: fewer than this and the sweep reads memory it never wrote.
        numberOfSubsteps = max(numberOfSubsteps, MINIMUM_SUBSTEPS)

        # A boundary layer that is not to be grown over the caps needs the surface still open while
        # the layer is swept; it gets its caps afterwards, on the inner surface. Only then, though:
        # with no layer to keep off them, leaving the surface open would just hand TetGen a
        # surface with holes in it.
        layerOffTheCaps = boundaryLayer and not boundaryLayerOnCaps
        capsTakenOff = {}
        if skipCapping or layerOffTheCaps:
            self.note(_("Not capping surface"))
            cappedSurface = self.withCellEntityIds(surface, cellEntityIdsArrayName)
            if layerOffTheCaps:
                # A surface that arrived capped - one from Clip Vessel has been closed already -
                # is opened again here. Not capping it is not enough to keep the layer off its
                # caps when the caps are already part of it: the sweep would run straight over
                # them, whatever the setting says.
                cappedSurface, capsTakenOff = self.openCappedEnds(
                    cappedSurface, cellEntityIdsArrayName,
                    boundaryLabelsArrayName=boundaryLabelsArrayName)
                if not capsTakenOff and self.numberOfOpenBoundaries(cappedSurface) == 0:
                    # Still closed: its caps could not be told from its wall, or it has none
                    # numbered as caps at all. The layer is going over them, then, and the rest
                    # of the run has to know that - or the faces of the closed surface would be
                    # taken for the wall of an open one and renumbered as such, losing every
                    # id it arrived with.
                    if self._capFaceIds is None:
                        logging.warning(
                            "The boundary layer is grown over the caps of this surface, which "
                            "arrived closed and whose caps could not be told apart from its "
                            "wall by the %s array - the wall is face %d and each cap is a face "
                            "numbered above it - and which carries no %s array to tell them "
                            "apart by.", cellEntityIdsArrayName, self.wallCellEntityId,
                            capIdsArrayName or DEFAULT_CAP_IDS_ARRAY_NAME)
                    else:
                        logging.warning(
                            "The boundary layer is grown over the caps of this surface, which "
                            "arrived closed and whose caps could not be told apart from its "
                            "wall: the faces its %s array marks as caps are not faces of its "
                            "%s array that come off whole.", capIdsArrayName,
                            cellEntityIdsArrayName)
                    boundaryLayerOnCaps = True
        else:
            self.log(_("Capping surface"))
            cappedSurface = self.capSurface(
                surface, cellEntityIdsArrayName, cappingMethod,
                boundaryLabelsArrayName=boundaryLabelsArrayName,
                boundaryPointOrderArrayName=boundaryPointOrderArrayName)

        if skipRemeshing:
            # Triangles all the same: a cap is one polygon as the capper leaves it, the sizing
            # function has nothing to say about a cell that is not a triangle, and TetGen is left
            # with a face it was given no sizes for. Remeshing would have triangulated the surface
            # on its way past; with it skipped, this is where that happens.
            remeshedSurface = self.triangulate(self.cleanSurface(cappedSurface))
        else:
            self.log(_("Remeshing surface"))
            remeshedSurface = self.remeshSurface(
                cappedSurface, cellEntityIdsArrayName, elementSizeMode=elementSizeMode,
                targetEdgeLength=targetEdgeLength,
                targetEdgeLengthArrayName=targetEdgeLengthArrayName,
                targetEdgeLengthFactor=targetEdgeLengthFactor,
                triangleSplitFactor=triangleSplitFactor,
                maxEdgeLength=maxEdgeLength, minEdgeLength=minEdgeLength,
                excludedEntityIds=self.wallFaceIdsOf(cappedSurface, cellEntityIdsArrayName)
                if remeshCapsOnly else [])

        # A size per point, where the surface was meshed to one and the mesher can read one. The
        # remesher was given the same array to size its triangles by, so the volume elements come
        # out graded the way the surface is. TetGen is not offered it: the switch that reads a
        # size per point answers differently each run (see runTetGen), so it is sized by one
        # number throughout, as it was before any other mesher was a choice.
        sizingField = None
        if (Mesher(mesher).sizesByPosition
                and elementSizeMode == ElementSizeMode.EDGE_LENGTH_ARRAY.value):
            self.log(_("Building sizing field"))
            sizingField = self.edgeLengthSizingField(
                remeshedSurface if remeshedSurface.GetPointData().GetArray(
                    targetEdgeLengthArrayName) else cappedSurface,
                targetEdgeLengthArrayName,
                factor=targetEdgeLengthFactor * volumeElementScaleFactor,
                minEdgeLength=minEdgeLength, maxEdgeLength=maxEdgeLength)
            if sizingField is None:
                logging.warning(
                    "The surface carries no %s array to size the volume elements by, so they are "
                    "all sized alike.", targetEdgeLengthArrayName)

        # The size the volume elements aim for, from the size the surface was meshed at. Where
        # each mesher takes it as one number for the whole volume and where it takes a number per
        # point is a difference between them; see fillVolume.
        volumeMeshing = VolumeMeshing(
            mesher=mesher,
            edgeLength=targetEdgeLength * volumeElementScaleFactor,
            sizingField=sizingField,
            surfaceTolerance=surfaceTolerance,
            stopEnergy=stopEnergy,
            maxOptimizationPasses=maxOptimizationPasses,
            coarsen=coarsen,
            netgenGrading=netgenGrading,
            netgenOptimizationSteps=netgenOptimizationSteps)

        if not boundaryLayer:
            mesh = self.fillWithTetrahedra(remeshedSurface, cellEntityIdsArrayName,
                                           volumeMeshing, outputSurfaceElements=True)
        else:
            # The closed surface the layer's direction is read off; see outwardNormals. The one
            # that came in, where it arrived closed and had its caps taken off; the capped one
            # otherwise, made here for the purpose if the layer is to stay off the caps of a
            # surface that arrived open.
            if self.numberOfOpenBoundaries(cappedSurface) == 0:
                orientationReference = cappedSurface
            elif capsTakenOff:
                orientationReference = surface
            else:
                orientationReference = self.capSurface(
                    cappedSurface, cellEntityIdsArrayName, cappingMethod)
            mesh = self.meshWithBoundaryLayer(
                remeshedSurface, cappedSurface, cellEntityIdsArrayName,
                elementSizeMode=elementSizeMode,
                targetEdgeLength=targetEdgeLength,
                targetEdgeLengthArrayName=targetEdgeLengthArrayName,
                targetEdgeLengthFactor=targetEdgeLengthFactor,
                triangleSplitFactor=triangleSplitFactor,
                endcapsEdgeLengthFactor=endcapsEdgeLengthFactor,
                maxEdgeLength=maxEdgeLength, minEdgeLength=minEdgeLength,
                cappingMethod=cappingMethod,
                volumeMeshing=volumeMeshing,
                boundaryLayerOnCaps=boundaryLayerOnCaps,
                numberOfSubLayers=numberOfSubLayers,
                subLayerRatio=subLayerRatio,
                boundaryLayerThicknessFactor=boundaryLayerThicknessFactor,
                numberOfSubsteps=numberOfSubsteps,
                relaxation=relaxation,
                localCorrectionFactor=localCorrectionFactor,
                orientationReference=orientationReference,
                capsTakenOff=capsTakenOff,
                boundaryLabelsArrayName=boundaryLabelsArrayName,
                boundaryPointOrderArrayName=boundaryPointOrderArrayName)

        if tetrahedralize:
            self.log(_("Tetrahedralizing"))
            tetrahedralizeFilter = vtkvmtkMisc.vtkvmtkUnstructuredGridTetraFilter()
            tetrahedralizeFilter.SetInputData(mesh)
            tetrahedralizeFilter.Update()
            mesh = tetrahedralizeFilter.GetOutput()

        if carriedCellArrays:
            # Said once, not once per output.
            for name in carriedCellArrays:
                if surface.GetCellData().GetArray(name) is None:
                    logging.warning("The input surface carries no cell array named %s, so there "
                                    "is nothing to carry onto the mesh under that name.", name)
            carried = [name for name in carriedCellArrays
                       if surface.GetCellData().GetArray(name) is not None]
            for output in (mesh, remeshedSurface):
                self.carryCellArrays(output, surface, cellEntityIdsArrayName, carried)

        self._finishStepLog()
        return mesh, remeshedSurface

    def carryCellArrays(self, mesh, surface, cellEntityIdsArrayName, arrayNames,
                        fillValue=-1):
        """Copy the named cell data arrays of the input surface onto the faces of the output.

        Face by face rather than cell by cell: no cell of the input survives the pipeline as
        itself - the remesher retriangulates the wall, the caps are made afresh, fTetWild answers
        with a boundary of its own - but the face a cell belongs to does, held by its entity id
        the whole way through. So every cell of the output that stands on a face of the input is
        given the value the input's cells on that face carry, and everything else - the volume
        elements, and any cap that was made here rather than brought in - is given fillValue.
        Which is what a solver reading, say, an inlet and outlet numbering off a surface whose
        faces were labelled by something else needs: the numbering on the mesh, with the faces
        told apart exactly rather than by proximity.

        A face whose input cells do not all carry the same value is given the value most of them
        carry, and a warning says so: the face is one thing to the ids and several to the array,
        which is a question about the input rather than one this can answer.
        """
        import numpy as np
        from vtk.util import numpy_support

        meshIdsArray = mesh.GetCellData().GetArray(cellEntityIdsArrayName)
        if meshIdsArray is None:
            logging.warning("The mesh carries no %s array, so no cell array can be carried onto "
                            "its faces.", cellEntityIdsArrayName)
            return
        meshIds = numpy_support.vtk_to_numpy(meshIdsArray).astype(np.int64).ravel()
        inputIdsArray = surface.GetCellData().GetArray(cellEntityIdsArrayName)
        if inputIdsArray is not None:
            inputIds = numpy_support.vtk_to_numpy(inputIdsArray).astype(np.int64).ravel()
        else:
            # The input had no faces of its own, so it was made one face - the wall - on its way
            # in (see withCellEntityIds and capSurface).
            inputIds = np.full(surface.GetNumberOfCells(), self.wallCellEntityId, dtype=np.int64)

        # The volume elements stand on no face, whatever id they carry. A surface has none.
        if mesh.IsA("vtkUnstructuredGrid"):
            cellTypes = numpy_support.vtk_to_numpy(mesh.GetCellTypesArray())
            isVolume = np.isin(cellTypes, [vtk.VTK_TETRA, vtk.VTK_WEDGE, vtk.VTK_HEXAHEDRON,
                                           vtk.VTK_PYRAMID, vtk.VTK_QUADRATIC_TETRA,
                                           vtk.VTK_QUADRATIC_WEDGE, vtk.VTK_QUADRATIC_HEXAHEDRON])
        else:
            isVolume = np.zeros(mesh.GetNumberOfCells(), dtype=bool)

        for name in arrayNames:
            inputArray = surface.GetCellData().GetArray(name)
            if inputArray is None:
                continue
            values = numpy_support.vtk_to_numpy(inputArray).reshape(surface.GetNumberOfCells(), -1)
            carried = np.full((mesh.GetNumberOfCells(), values.shape[1]), fillValue,
                              dtype=values.dtype)
            for faceId in np.unique(inputIds):
                faceValues, counts = np.unique(values[inputIds == faceId], axis=0,
                                               return_counts=True)
                if len(faceValues) > 1:
                    logging.warning("The cells of face %d of the input surface do not all carry "
                                    "the same %s value; the mesh is given the one most of them "
                                    "carry.", faceId, name)
                carried[(meshIds == faceId) & ~isVolume] = faceValues[counts.argmax()]
            carriedArray = numpy_support.numpy_to_vtk(
                np.ascontiguousarray(carried), deep=True, array_type=inputArray.GetDataType())
            carriedArray.SetName(name)
            mesh.GetCellData().AddArray(carriedArray)

    #
    # Which faces are caps.
    #

    def capFaceIdsOf(self, surface, cellEntityIdsArrayName, capIdsArrayName):
        """The face ids of the surface that are caps, read off its cap ids array.

        :return: (the set of face ids whose cells the cap ids array marks as caps, the largest
          face id the surface carries), or (None, None) where the surface carries no cap ids
          array or no face ids array - the id convention then decides; see isCapId().
        """
        import numpy as np
        from vtk.util import numpy_support

        if not capIdsArrayName:
            return None, None
        capIdsArray = surface.GetCellData().GetArray(capIdsArrayName)
        faceIdsArray = surface.GetCellData().GetArray(cellEntityIdsArrayName)
        if capIdsArray is None or faceIdsArray is None:
            return None, None
        capIds = numpy_support.vtk_to_numpy(capIdsArray).reshape(surface.GetNumberOfCells(), -1)
        faceIds = numpy_support.vtk_to_numpy(faceIdsArray).astype(np.int64).ravel()
        isCap = capIds[:, 0] >= 1
        capFaceIds = set()
        for faceId in np.unique(faceIds):
            onFace = isCap[faceIds == faceId]
            capCells = int(onFace.sum())
            if capCells == 0:
                continue
            if capCells < onFace.size:
                logging.warning(
                    "Face %d of the %s array is part cap and part wall by the %s array (%d of "
                    "%d cells are cap), and a face is one or the other; it is taken for %s.",
                    faceId, cellEntityIdsArrayName, capIdsArrayName, capCells, onFace.size,
                    "a cap" if 2 * capCells >= onFace.size else "wall")
                if 2 * capCells < onFace.size:
                    continue
            capFaceIds.add(int(faceId))
        return capFaceIds, int(faceIds.max()) if faceIds.size else self.wallCellEntityId

    def isCapId(self, entityId):
        """Whether a face id is a cap's.

        By the cap ids array of the input where it has one: the faces it marks, and any face
        numbered above every face of the input - which is a cap this pipeline made, the capper
        numbering its caps above whatever it was given. Otherwise by the convention this module
        and Clip Vessel number faces by: the wall is wallCellEntityId, and every face above it
        is a cap.
        """
        entityId = int(entityId)
        if self._capFaceIds is None:
            return entityId > self.wallCellEntityId
        return entityId in self._capFaceIds or entityId > self._largestInputFaceId

    def wallFaceIdsOf(self, mesh, cellEntityIdsArrayName):
        """The face ids the mesh carries that are not caps' - the wall, in however many faces."""
        import numpy as np
        from vtk.util import numpy_support

        array = mesh.GetCellData().GetArray(cellEntityIdsArrayName)
        if array is None:
            return [self.wallCellEntityId]
        return [int(faceId) for faceId in np.unique(numpy_support.vtk_to_numpy(array))
                if not self.isCapId(faceId)]

    def capCells(self, mesh, cellEntityIdsArrayName, keep):
        """The cells of the mesh that are on a cap, or the ones that are not, as an
        unstructured grid."""
        import numpy as np
        from vtk.util import numpy_support

        array = mesh.GetCellData().GetArray(cellEntityIdsArrayName)
        faceIds = numpy_support.vtk_to_numpy(array).astype(np.int64).ravel()
        isCap = np.array([self.isCapId(faceId) for faceId in faceIds], dtype=bool) \
            if faceIds.size else np.zeros(0, dtype=bool)
        cellIds = vtk.vtkIdList()
        for cellId in np.flatnonzero(isCap if keep else ~isCap):
            cellIds.InsertNextId(int(cellId))
        extract = vtk.vtkExtractCells()
        extract.SetInputData(mesh)
        extract.SetCellList(cellIds)
        extract.Update()
        return extract.GetOutput()

    #
    # The steps of the pipeline, one per vmtk script that vmtkmeshgenerator drives.
    #

    def capSurface(self, surface, cellEntityIdsArrayName, cappingMethod, capsTakenOff=None,
                   boundaryLabelsArrayName=None, boundaryPointOrderArrayName=None):
        """The surface with every open boundary closed, each cap under an id of its own, and the
        cells that came from the input under wallCellEntityId (vmtksurfacecapper).

        :param capsTakenOff: the caps this surface's ends were closed with before they were taken
          off, as openCappedEnds() records them, so that the caps made now can be given their ids
          back. See nameCapsAfterTheirVesselEnd() for how a cap is matched to the end it closes.
        :param boundaryLabelsArrayName: point data array the boundary labels are read from; None
          (or an empty name) uses the one the logic is configured with.
        :param boundaryPointOrderArrayName: point data array the boundary point order is read
          from; None (or an empty name) uses the one the logic is configured with.
        """
        import vtkvmtkMiscPython as vtkvmtkMisc

        if cappingMethod == CappingMethod.SIMPLE.value:
            capper = vtkvmtkMisc.vtkvmtkSimpleCapPolyData()
        elif cappingMethod == CappingMethod.ANNULAR.value:
            capper = vtkvmtkMisc.vtkvmtkAnnularCapPolyData()
        elif cappingMethod == CappingMethod.CONCAVE_ANNULAR.value:
            try:
                import vtkvmtkContribPython as vtkvmtkContrib
            except ImportError:
                raise RuntimeError(_("The concave annular capping method is not available in this "
                                     "build of the VMTK library. Choose another capping method."))
            capper = vtkvmtkContrib.vtkvmtkConcaveAnnularCapPolyData()
        else:
            raise ValueError(_("Unknown capping method: {method}").format(method=cappingMethod))

        capper.SetInputData(surface)
        capper.SetCellEntityIdsArrayName(cellEntityIdsArrayName)
        capper.SetCellEntityIdOffset(self.wallCellEntityId)
        self.nameCapsAfterTheirVesselEnd(
            capper, surface, capsTakenOff,
            boundaryLabelsArrayName=boundaryLabelsArrayName,
            boundaryPointOrderArrayName=boundaryPointOrderArrayName)
        capper.Update()
        return capper.GetOutput()

    def nameCapsAfterTheirVesselEnd(self, capper, surface, capsTakenOff=None,
                                    boundaryLabelsArrayName=None,
                                    boundaryPointOrderArrayName=None):
        """Tell the capper what id to give the cap of each boundary it is about to close.

        Left to itself the capper numbers the caps in the order the boundaries came out of the
        extractor, which is an order nothing else knows. Where the surface still says which vessel
        end each boundary is - Clip Vessel writes that into it, and the filters here carry it
        across - the cap of an end can be named after the end instead: the same id every run, and
        the id Clip Vessel gives it. Where the surface arrived capped and those caps were taken
        off to keep the boundary layer away from them, the id to give back is the one the cap that
        closed that end was carrying.

        The ids the capper is given are indexed by boundary id, and what a boundary id means is
        what the labels are worth: the label itself where they still describe the surface, and the
        position in the extraction order where they do not. Which of the two it will be is asked
        here rather than assumed, because being wrong about it means naming an inlet after an
        outlet.

        With the labels in use and no cap to give an id back to, there is nothing to say: a label
        is already the cell entity id of the cap that closes its boundary - the labeler numbers
        the boundaries of a surface above the wall, where this module numbers its caps - so the
        capper left to itself gives every cap the id this would have chosen for it anyway.
        """
        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry

        # The annular cappers close the ring between two boundaries rather than one boundary each,
        # and take no labels; which end is which is not a question they answer.
        if not hasattr(capper, "SetBoundaryCellEntityIds"):
            return

        boundaryLabelsArrayName = boundaryLabelsArrayName or self.boundaryLabelsArrayName
        boundaryPointOrderArrayName = (boundaryPointOrderArrayName
                                       or self.boundaryPointOrderArrayName)

        boundaries = vtk.vtkPolyData()
        boundaryLabels = vtk.vtkIdList()
        useLabels = vtkvmtkComputationalGeometry.vtkvmtkBoundaryLabels.GetOrExtractBoundaries(
            surface, boundaryLabelsArrayName, boundaryPointOrderArrayName,
            boundaries, boundaryLabels)
        if useLabels:
            capper.SetBoundaryLabelsArrayName(boundaryLabelsArrayName)
            capper.SetBoundaryPointOrderArrayName(boundaryPointOrderArrayName)

        capsTakenOff = capsTakenOff or {}
        capIdsByLabel = {cap["label"]: capId for capId, cap in capsTakenOff.items()
                         if cap["label"] is not None}
        chosenIds = {}
        for index in range(boundaries.GetNumberOfCells()):
            boundaryId = int(boundaryLabels.GetId(index)) if useLabels else index
            if useLabels and boundaryId in capIdsByLabel:
                chosenIds[boundaryId] = capIdsByLabel[boundaryId]
            elif capsTakenOff:
                # Nothing says which end this is, so the cap that stood here says it: the new one
                # is built on the surface the old one's rim was swept to, a layer's thickness away
                # at most, and the vessel ends are further apart than that.
                centre = self.boundaryCentre(boundaries, index)
                chosenIds[boundaryId] = min(
                    capsTakenOff,
                    key=lambda capId: vtk.vtkMath.Distance2BetweenPoints(
                        centre, capsTakenOff[capId]["centre"]))

        if not chosenIds:
            return
        if len(set(chosenIds.values())) != len(chosenIds):
            logging.warning("Two of the caps that were taken off this surface would be put back "
                            "under the same id, so every cap is left to the id its boundary "
                            "carries instead.")
            return

        # Indexed by boundary id, with -1 for any the capper is left to number itself.
        boundaryCellEntityIds = vtk.vtkIdTypeArray()
        for boundaryId in range(max(chosenIds) + 1):
            boundaryCellEntityIds.InsertNextValue(chosenIds.get(boundaryId, -1))
        capper.SetBoundaryCellEntityIds(boundaryCellEntityIds)

    @staticmethod
    def boundaryCentre(boundaries, index):
        """The middle of one of the boundaries the extractor found."""
        points = boundaries.GetCell(index).GetPoints()
        total = [0.0, 0.0, 0.0]
        for pointIndex in range(points.GetNumberOfPoints()):
            point = points.GetPoint(pointIndex)
            for axis in range(3):
                total[axis] += point[axis]
        return tuple(value / max(1, points.GetNumberOfPoints()) for value in total)

    @staticmethod
    def withCellEntityIds(surface, cellEntityIdsArrayName):
        """The surface, given an all-zero entity id array if it does not already carry one.

        A copy, because the pipeline goes on to hand this to filters that read the array, and the
        caller's surface is not ours to add arrays to.
        """
        copied = vtk.vtkPolyData()
        copied.DeepCopy(surface)
        if copied.GetCellData().GetArray(cellEntityIdsArrayName) is None:
            cellEntityIdsArray = vtk.vtkIntArray()
            cellEntityIdsArray.SetName(cellEntityIdsArrayName)
            cellEntityIdsArray.SetNumberOfTuples(copied.GetNumberOfCells())
            cellEntityIdsArray.FillComponent(0, 0.0)
            copied.GetCellData().AddArray(cellEntityIdsArray)
        return copied

    def openCappedEnds(self, surface, cellEntityIdsArrayName, boundaryLabelsArrayName=None):
        """The surface with the caps it arrived with taken off, and where each of them was.

        A cap is what isCapId() says: a face the cap ids array marks, or, without one, a face
        numbered above the wall, which is how this module numbers the caps it makes and how Clip
        Vessel numbers the ones it makes. A surface that carries none - one whose ends are still
        open, which is what vmtkmeshgenerator expects to be given - comes back untouched.

        :return: (surface, capsTakenOff), the surface with its cap faces removed and, for each cap
          taken off, what is needed to give the cap made in its place the same id: the vessel end
          it closed where the surface says which that is, and the middle of it either way.
        """
        entityIdsArray = surface.GetCellData().GetArray(cellEntityIdsArrayName)
        if entityIdsArray is None:
            return surface, {}
        boundaryLabels = surface.GetPointData().GetArray(
            boundaryLabelsArrayName or self.boundaryLabelsArrayName)

        pointSums = {}
        pointCounts = {}
        labelCounts = {}
        for cellId in range(surface.GetNumberOfCells()):
            entityId = int(entityIdsArray.GetTuple1(cellId))
            if not self.isCapId(entityId):
                continue
            cell = surface.GetCell(cellId)
            for index in range(cell.GetNumberOfPoints()):
                pointId = cell.GetPointId(index)
                point = surface.GetPoint(pointId)
                total = pointSums.setdefault(entityId, [0.0, 0.0, 0.0])
                for axis in range(3):
                    total[axis] += point[axis]
                pointCounts[entityId] = pointCounts.get(entityId, 0) + 1
                if boundaryLabels is not None:
                    # A cap's own points carry no label; the ones it shares with the rim of the
                    # vessel end it closes carry that end's.
                    label = int(boundaryLabels.GetTuple1(pointId))
                    if label >= 0:
                        counts = labelCounts.setdefault(entityId, {})
                        counts[label] = counts.get(label, 0) + 1

        capsTakenOff = {}
        for entityId, total in pointSums.items():
            counts = labelCounts.get(entityId, {})
            capsTakenOff[entityId] = {
                "centre": tuple(value / pointCounts[entityId] for value in total),
                "label": max(counts, key=counts.get) if counts else None,
            }

        if not capsTakenOff:
            return surface, {}

        self.log(_("Opening the capped ends"))
        geometryFilter = vtk.vtkGeometryFilter()
        geometryFilter.SetInputData(self.capCells(surface, cellEntityIdsArrayName, keep=False))
        geometryFilter.Update()
        opened = self.cleanSurface(geometryFilter.GetOutput())

        # Numbering the wall 1 and the caps above it is this module's convention and Clip Vessel's,
        # but the ids on a surface from somewhere else mean whatever that somewhere else meant by
        # them, and cutting the wrong faces out of a vessel wall is not a small mistake. What the
        # faces were taken to be is therefore checked against what taking them off did: lifting a
        # cap off leaves exactly one hole where it was.
        holes = self.numberOfOpenBoundaries(opened)
        if holes != len(capsTakenOff):
            if self._capFaceIds is None:
                logging.warning(
                    "The faces numbered above %d in the %s array are not the caps of this "
                    "surface - taking them off left %d hole(s) where %d were expected - so it "
                    "is meshed as it arrived, with the boundary layer grown over them.",
                    self.wallCellEntityId, cellEntityIdsArrayName, holes, len(capsTakenOff))
            else:
                logging.warning(
                    "The faces of the %s array marked as caps (%s) do not come off this surface "
                    "one cap each - taking them off left %d hole(s) where %d were expected - so "
                    "it is meshed as it arrived, with the boundary layer grown over them.",
                    cellEntityIdsArrayName, ", ".join(str(faceId) for faceId in sorted(capsTakenOff)),
                    holes, len(capsTakenOff))
            return surface, {}

        logging.info("Took %d cap(s) off the input surface, so that the boundary layer is not "
                     "grown over them.", len(capsTakenOff))
        return opened, capsTakenOff

    @staticmethod
    def numberOfOpenBoundaries(surface):
        """How many separate holes the surface has."""
        featureEdges = vtk.vtkFeatureEdges()
        featureEdges.SetInputData(surface)
        featureEdges.BoundaryEdgesOn()
        featureEdges.FeatureEdgesOff()
        featureEdges.NonManifoldEdgesOff()
        featureEdges.ManifoldEdgesOff()
        featureEdges.Update()
        if featureEdges.GetOutput().GetNumberOfCells() == 0:
            return 0
        connectivity = vtk.vtkPolyDataConnectivityFilter()
        connectivity.SetInputData(featureEdges.GetOutput())
        connectivity.SetExtractionModeToAllRegions()
        connectivity.Update()
        return connectivity.GetNumberOfExtractedRegions()

    def remeshSurface(self, surface, cellEntityIdsArrayName, *, elementSizeMode, targetEdgeLength,
                      targetEdgeLengthArrayName, targetEdgeLengthFactor, triangleSplitFactor,
                      maxEdgeLength, minEdgeLength, excludedEntityIds):
        """The surface retriangulated into near equilateral cells of the wanted size
        (vmtksurfaceremeshing).

        Cells of an excluded entity are left exactly as they are, and so are the points they use,
        so that remeshing the caps alone leaves the wall - and the rim they share - untouched.
        """
        import vtkvmtkDifferentialGeometryPython as vtkvmtkDifferentialGeometry

        triangleFilter = vtk.vtkTriangleFilter()
        triangleFilter.SetInputData(self.cleanSurface(surface))
        triangleFilter.Update()
        surface = triangleFilter.GetOutput()

        # The remesher sizes cells by area throughout; an edge length is the area of the
        # equilateral triangle of that side.
        targetAreaArrayName = "TargetArea"
        fromArray = elementSizeMode == ElementSizeMode.EDGE_LENGTH_ARRAY.value
        if fromArray:
            if not targetEdgeLengthArrayName:
                raise ValueError(_("No target edge length array name was given"))
            if surface.GetPointData().GetArray(targetEdgeLengthArrayName) is None:
                raise ValueError(_("The input surface carries no point data array named "
                                   "{name}").format(name=targetEdgeLengthArrayName))
            calculator = vtk.vtkArrayCalculator()
            calculator.SetInputData(surface)
            calculator.AddScalarArrayName(targetEdgeLengthArrayName, 0)
            calculator.SetFunction("%f^2 * 0.25 * sqrt(3) * %s^2"
                                   % (targetEdgeLengthFactor, targetEdgeLengthArrayName))
            calculator.SetResultArrayName(targetAreaArrayName)
            calculator.Update()
            surface = calculator.GetOutput()

        excludedIds = vtk.vtkIdList()
        for excludedId in excludedEntityIds:
            excludedIds.InsertNextId(int(excludedId))

        remeshing = vtkvmtkDifferentialGeometry.vtkvmtkPolyDataSurfaceRemeshing()
        remeshing.SetInputData(surface)
        if cellEntityIdsArrayName:
            remeshing.SetCellEntityIdsArrayName(cellEntityIdsArrayName)
        if fromArray:
            remeshing.SetElementSizeModeToTargetAreaArray()
            remeshing.SetTargetAreaArrayName(targetAreaArrayName)
        else:
            remeshing.SetElementSizeModeToTargetArea()
        remeshing.SetTargetArea(self.equilateralTriangleArea(targetEdgeLength))
        remeshing.SetTriangleSplitFactor(triangleSplitFactor)
        # vmtksurfaceremeshing asks for a smaller collapse angle threshold than the filter itself
        # defaults to, and vmtkmeshgenerator does not offer it. It is worth setting rather than
        # inheriting: with the filter's own value the remesher collapses edges it should leave
        # alone, and hands back a surface with edges shared by three cells, which is not something
        # TetGen can fill - it walks off the end of such a mesh and takes the process with it.
        remeshing.SetCollapseAngleThreshold(self.collapseAngleThreshold)
        remeshing.SetMaxArea(self.equilateralTriangleArea(maxEdgeLength))
        remeshing.SetMinArea(self.equilateralTriangleArea(minEdgeLength))
        remeshing.SetExcludedEntityIds(excludedIds)
        remeshing.Update()
        return remeshing.GetOutput()

    def outwardNormals(self, surface, closedReference):
        """The surface carrying a normal per point that points out of the vessel, oriented by a
        closed surface standing where it does.

        Which way is out is a question about a closed surface: asked of an open one - the wall
        with its caps taken off - vtkPolyDataNormals answers by the winding of the first cell
        it meets, and the remesher hands back cells wound either way. So the cells are first
        wound consistently with one another, then the whole is turned round wherever it faces
        the other way from the closed reference at the nearest point - per connected piece, a
        surface of several vessels being several answers. The normals are then taken from the
        winding, which the boundary layer generator reads too: a prism is only the right way
        out when its base is wound to face the way its warp vector does not.
        """
        import numpy as np
        from vtk.util import numpy_support

        withoutNormals = vtk.vtkPolyData()
        withoutNormals.ShallowCopy(surface)
        withoutNormals.GetPointData().SetNormals(None)
        withoutNormals.GetCellData().SetNormals(None)
        consistency = vtk.vtkPolyDataNormals()
        consistency.SetInputData(withoutNormals)
        consistency.SetAutoOrientNormals(0)
        consistency.SetConsistency(1)
        consistency.ComputeCellNormalsOn()
        consistency.SplittingOff()
        consistency.Update()
        consistent = consistency.GetOutput()
        polys = consistent.GetPolys()
        if polys.IsHomogeneous() != 3 or consistent.GetNumberOfCells() != consistent.GetNumberOfPolys():
            return self.surfaceNormals(surface)

        reference = self.surfaceNormals(closedReference)
        referenceNormals = numpy_support.vtk_to_numpy(reference.GetPointData().GetNormals())
        locator = vtk.vtkPointLocator()
        locator.SetDataSet(reference)
        locator.BuildLocator()

        points = numpy_support.vtk_to_numpy(consistent.GetPoints().GetData())
        cells = numpy_support.vtk_to_numpy(polys.GetConnectivityArray()).reshape(-1, 3)
        cellNormals = numpy_support.vtk_to_numpy(consistent.GetCellData().GetNormals())
        centroids = points[cells].mean(axis=1)
        nearest = np.array([locator.FindClosestPoint([float(value) for value in centroid])
                            for centroid in centroids])
        agreement = (cellNormals * referenceNormals[nearest]).sum(axis=1)

        pieces = vtk.vtkPolyDataConnectivityFilter()
        pieces.SetInputData(consistent)
        pieces.SetExtractionModeToAllRegions()
        pieces.ColorRegionsOn()
        pieces.Update()
        pointRegions = numpy_support.vtk_to_numpy(
            pieces.GetOutput().GetPointData().GetArray("RegionId"))
        cellRegions = pointRegions[cells[:, 0]]

        turned = np.zeros(len(cells), dtype=bool)
        for region in np.unique(cellRegions):
            onPiece = cellRegions == region
            if agreement[onPiece].sum() < 0.0:
                turned[onPiece] = True
        if turned.any():
            logging.info("Turning %d of %d surface cells round to face out of the vessel.",
                         int(turned.sum()), len(cells))
            rewound = cells.copy()
            rewound[turned] = rewound[turned][:, [0, 2, 1]]
            newPolys = vtk.vtkCellArray()
            newPolys.SetData(
                numpy_support.numpy_to_vtkIdTypeArray(
                    np.arange(0, 3 * len(cells) + 1, 3, dtype=np.int64), deep=True),
                numpy_support.numpy_to_vtkIdTypeArray(
                    np.ascontiguousarray(rewound.ravel(), dtype=np.int64), deep=True))
            consistent.SetPolys(newPolys)
        return self.surfaceNormals(consistent, autoOrient=False)

    def growLayerOutwards(self, innerBoundary, cellEntityIdsArrayName, *, boundaryLayerOnCaps,
                          referenceSurface, elementSizeMode, targetEdgeLength,
                          targetEdgeLengthArrayName, targetEdgeLengthFactor, maxEdgeLength,
                          numberOfSubLayers, subLayerRatio, boundaryLayerThicknessFactor,
                          numberOfSubsteps, relaxation, localCorrectionFactor):
        """A boundary layer grown outwards from the boundary of a volume already meshed.

        The other way round from the sweep that precedes it, and for a mesher that will not be
        told where to put its boundary: fTetWild answers with a triangulation of its own, so a
        layer swept inwards before it would not meet what it returns. The layer is grown from
        what it returns instead, outwards, and the wall of the vessel ends up where the outside
        of the layer lands rather than exactly where the surface was - within the thickness of
        the layer of it, which is the same order as the surface tolerance already allows.

        :return: (the layer cells, the surface bounding it on the outside, the cap cells set
          aside, or None when the layer is grown over the caps as well)
        """
        import vtkvmtkMiscPython as vtkvmtkMisc

        if boundaryLayerOnCaps:
            sweptSurface, caps = innerBoundary, None
        else:
            # The caps are not swept: each of them stays one flat face for the flow to meet.
            sweptSurface = self.meshToSurface(
                self.capCells(innerBoundary, cellEntityIdsArrayName, keep=False))
            caps = self.capCells(innerBoundary, cellEntityIdsArrayName, keep=True)

        if targetEdgeLengthArrayName:
            # The thickness is read per point where it is not constant, and the boundary fTetWild
            # returns carries no arrays at all, so it is fetched from the surface it stands for.
            projection = vtkvmtkMisc.vtkvmtkSurfaceProjection()
            projection.SetInputData(sweptSurface)
            projection.SetReferenceSurface(referenceSurface)
            projection.Update()
            sweptSurface = projection.GetOutput()

        # The boundary of a set of tetrahedra is already wound to face outwards, and asking which
        # way is out of a wall with no caps on it would be asking about the wrong shape, so the
        # normals are taken from the winding as it stands.
        sweptSurface = self.surfaceNormals(sweptSurface, autoOrient=False)

        # The prisms are built from the swept cell and its copy one layer along, in that order,
        # and a prism is only the right way out if the normal of the first face points away from
        # the second. Sweeping outwards puts the second face on the side the normals point to, so
        # the cells are wound the other way before the sweep - the normals, which say where to
        # sweep, are left alone.
        reversed = vtk.vtkReverseSense()
        reversed.SetInputData(sweptSurface)
        reversed.ReverseCellsOn()
        reversed.ReverseNormalsOff()
        reversed.Update()
        sweptMesh = self.surfaceToMesh(reversed.GetOutput())

        self.log(_("Growing boundary layer"))
        generator = vtkvmtkMisc.vtkvmtkBoundaryLayerGenerator()
        generator.SetInputData(sweptMesh)
        generator.SetWarpVectorsArrayName("Normals")
        # The normals point out of the surface and this layer grows outwards along them.
        generator.SetNegateWarpVectors(False)
        generator.SetLayerThicknessArrayName(targetEdgeLengthArrayName)
        generator.SetConstantThickness(elementSizeMode == ElementSizeMode.EDGE_LENGTH.value)
        generator.SetIncludeSurfaceCells(0)
        generator.SetIncludeSidewallCells(1)
        generator.SetNumberOfSubLayers(numberOfSubLayers)
        generator.SetNumberOfSubsteps(numberOfSubsteps)
        generator.SetRelaxation(relaxation)
        generator.SetLocalCorrectionFactor(localCorrectionFactor)
        # The sublayers are counted from the surface handed over, and that surface is now the
        # inner face of the layer rather than the wall, so the ratio between them is inverted to
        # keep the thinnest prism against the wall, which is what it is there for.
        generator.SetSubLayerRatio(1.0 / subLayerRatio if subLayerRatio > 0.0 else 1.0)
        generator.SetLayerThickness(boundaryLayerThicknessFactor * targetEdgeLength)
        generator.SetLayerThicknessRatio(boundaryLayerThicknessFactor * targetEdgeLengthFactor)
        generator.SetMaximumLayerThickness(boundaryLayerThicknessFactor * maxEdgeLength)
        generator.SetCellEntityIdsArrayName(cellEntityIdsArrayName)
        generator.SetSidewallCellEntityId(self.placeholderCellEntityId)
        generator.SetInnerSurfaceCellEntityId(self.wallCellEntityId)
        generator.Update()

        # The outermost copy of the swept surface is the wall of the vessel. It comes back under
        # one id, and the ids it went in with - which for a layer grown over the caps say which
        # cells are wall and which are cap - are put back on it; the generator copies the surface
        # cell for cell, so they are the same cells in the same order.
        outerGrid = generator.GetInnerSurface()
        outerGrid.GetCellData().GetArray(cellEntityIdsArrayName).DeepCopy(
            sweptMesh.GetCellData().GetArray(cellEntityIdsArrayName))
        # Wound back the way a surface bounding a volume is wound.
        outward = vtk.vtkReverseSense()
        outward.SetInputData(self.meshToSurface(outerGrid))
        outward.ReverseCellsOn()
        outward.ReverseNormalsOff()
        outward.Update()
        return generator.GetOutput(), self.surfaceToMesh(outward.GetOutput()), caps

    def edgeLengthSizingField(self, surface, targetEdgeLengthArrayName, factor,
                              minEdgeLength, maxEdgeLength):
        """A background mesh carrying the target edge length at each of its points, for a mesher
        that sizes its elements by position.

        The sizes live on the surface, and the volume behind it has to be given them too, so they
        are carried onto the points of a grid laid over the whole shape - each point taking the
        size of the surface point nearest it. What the mesher then reads at any point of the
        volume is those sizes interpolated over the cell of the grid it falls in.

        A regular grid split into tetrahedra rather than a triangulation of the surface points
        themselves: the surfaces here are rings of points around a tube and flat discs closing
        it, which is the arrangement a Delaunay triangulation is least able to make sense of.

        :return: (points, tetrahedra, edge lengths) as arrays, or None if the surface carries no
          such array.
        """
        import math

        import numpy as np
        from vtk.util import numpy_support
        import vtkvmtkMiscPython as vtkvmtkMisc

        lengths = surface.GetPointData().GetArray(targetEdgeLengthArrayName)
        if lengths is None:
            return None
        lengths = numpy_support.vtk_to_numpy(lengths).astype(np.float64).ravel() * factor
        positive = lengths[lengths > 0.0]
        if positive.size == 0:
            return None

        # Fine enough to hold the smallest size asked for, and coarse enough that the grid stays
        # a lookup table rather than a mesh in its own right.
        bounds = surface.GetBounds()
        diagonal = surface.GetLength()
        spacing = min(max(float(positive.min()), diagonal / 100.0), diagonal / 8.0)
        padding = 2.0 * spacing

        image = vtk.vtkImageData()
        image.SetOrigin(bounds[0] - padding, bounds[2] - padding, bounds[4] - padding)
        image.SetSpacing(spacing, spacing, spacing)
        image.SetDimensions(*[
            int(math.ceil((bounds[2 * axis + 1] - bounds[2 * axis] + 2.0 * padding) / spacing)) + 1
            for axis in range(3)])

        toTetrahedra = vtk.vtkDataSetTriangleFilter()
        toTetrahedra.SetInputData(image)
        toTetrahedra.TetrahedraOnlyOn()
        toTetrahedra.Update()
        background = toTetrahedra.GetOutput()

        # The projection wants a surface to read from and points to write onto; the grid's own
        # points, with no cells, are all it needs of the grid.
        nodes = vtk.vtkPolyData()
        nodes.SetPoints(background.GetPoints())
        projection = vtkvmtkMisc.vtkvmtkSurfaceProjection()
        projection.SetInputData(nodes)
        projection.SetReferenceSurface(surface)
        projection.Update()

        values = numpy_support.vtk_to_numpy(
            projection.GetOutput().GetPointData().GetArray(targetEdgeLengthArrayName))
        values = values.astype(np.float64).ravel() * factor
        # A size of zero or less is not a size, and the mesher refuses the whole field over one.
        floor = max(minEdgeLength, 1e-6 * diagonal)
        ceiling = maxEdgeLength if maxEdgeLength < UNLIMITED_EDGE_LENGTH else None
        values = np.clip(values, floor, ceiling)

        points = numpy_support.vtk_to_numpy(
            background.GetPoints().GetData()).astype(np.float64)
        tetrahedra = numpy_support.vtk_to_numpy(
            background.GetCells().GetConnectivityArray()).reshape(-1, 4)
        # The field is read by finding the tetrahedron a point falls in, which asks that they be
        # wound the right way round.
        corners = points[tetrahedra]
        inverted = np.einsum(
            "ij,ij->i",
            np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]),
            corners[:, 3] - corners[:, 0]) < 0.0
        tetrahedra[inverted] = tetrahedra[inverted][:, [0, 2, 1, 3]]

        return points, np.ascontiguousarray(tetrahedra, dtype=np.int32), values

    def fillWithTetrahedra(self, surface, cellEntityIdsArrayName, volumeMeshing,
                           outputSurfaceElements):
        """The volume enclosed by the surface, filled with tetrahedra (vmtktetgen)."""
        surfaceMesh = self.surfaceToMesh(surface)

        mesh = self.fillVolume(surfaceMesh, cellEntityIdsArrayName, outputSurfaceElements,
                               volumeMeshing)

        if self.numberOfVolumeCells(mesh) == 0 and surfaceMesh.GetNumberOfCells() > 0:
            logging.warning("An error occurred during tetrahedralization. "
                            "Only the surface mesh is returned.")
            self.lastTetrahedralizationFailed = True
            return surfaceMesh
        return mesh

    def meshWithBoundaryLayer(self, remeshedSurface, referenceSurface, cellEntityIdsArrayName, *,
                              elementSizeMode, targetEdgeLength, targetEdgeLengthArrayName,
                              targetEdgeLengthFactor, triangleSplitFactor, endcapsEdgeLengthFactor,
                              maxEdgeLength, minEdgeLength, cappingMethod,
                              volumeMeshing, boundaryLayerOnCaps, numberOfSubLayers,
                              subLayerRatio, boundaryLayerThicknessFactor, numberOfSubsteps,
                              relaxation, localCorrectionFactor, capsTakenOff=None,
                              boundaryLabelsArrayName=None,
                              boundaryPointOrderArrayName=None,
                              orientationReference=None):
        """The surface lined on the inside with layers of prisms, and everything those leave free
        filled with tetrahedra.

        The prisms are made by sweeping the surface inwards along its own normals; what is still
        empty inside is meshed against the innermost swept surface, and the two are put back
        together at the end.

        :param orientationReference: a closed surface standing where this one does, for the
          normals to be oriented by; see outwardNormals. None orients them by the surface
          itself, which is only reliable when the surface is closed.
        """
        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
        import vtkvmtkMiscPython as vtkvmtkMisc

        # The remesher keeps no point data, so the array the layer thickness is read from is
        # carried back onto the remeshed surface from the surface it was given on.
        projection = vtkvmtkMisc.vtkvmtkSurfaceProjection()
        projection.SetInputData(remeshedSurface)
        projection.SetReferenceSurface(referenceSurface)
        projection.Update()

        # Normals that point out of the vessel whatever the winding of the surface as it arrived
        # and whatever was taken off it: the layer is swept the other way along them, and one
        # swept outwards is a layer through the wall. Asked of the closed surface, which is the
        # one shape the question has an answer for.
        if orientationReference is not None:
            outerSurface = self.outwardNormals(projection.GetOutput(), orientationReference)
        else:
            outerSurface = self.surfaceNormals(projection.GetOutput())
        outerSurfaceMesh = self.surfaceToMesh(outerSurface)

        self.log(_("Generating boundary layer"))
        boundaryLayerGenerator = vtkvmtkMisc.vtkvmtkBoundaryLayerGenerator()
        boundaryLayerGenerator.SetInputData(outerSurfaceMesh)
        boundaryLayerGenerator.SetWarpVectorsArrayName("Normals")
        # The normals point out of the surface and the layer grows into it.
        boundaryLayerGenerator.SetNegateWarpVectors(True)
        boundaryLayerGenerator.SetLayerThicknessArrayName(targetEdgeLengthArrayName)
        boundaryLayerGenerator.SetConstantThickness(
            elementSizeMode == ElementSizeMode.EDGE_LENGTH.value)
        # The surface cells are added back below, from the surfaces they belong to. The sidewall
        # cells are not: they are the strips the open boundaries sweep out, which stand where the
        # caps are about to be made and belong to no other surface, so without them the labelled
        # boundary of the mesh has a gap around every vessel end.
        boundaryLayerGenerator.SetIncludeSurfaceCells(0)
        boundaryLayerGenerator.SetIncludeSidewallCells(1)
        boundaryLayerGenerator.SetNumberOfSubLayers(numberOfSubLayers)
        boundaryLayerGenerator.SetNumberOfSubsteps(numberOfSubsteps)
        boundaryLayerGenerator.SetRelaxation(relaxation)
        boundaryLayerGenerator.SetLocalCorrectionFactor(localCorrectionFactor)
        boundaryLayerGenerator.SetSubLayerRatio(subLayerRatio)
        boundaryLayerGenerator.SetLayerThickness(boundaryLayerThicknessFactor * targetEdgeLength)
        boundaryLayerGenerator.SetLayerThicknessRatio(
            boundaryLayerThicknessFactor * targetEdgeLengthFactor)
        boundaryLayerGenerator.SetMaximumLayerThickness(
            boundaryLayerThicknessFactor * maxEdgeLength)
        boundaryLayerGenerator.SetCellEntityIdsArrayName(cellEntityIdsArrayName)
        # What the inner surface is called matters to the mesher that fills it: fTetWild reads the
        # ids off the surface it is given to label the boundary it returns.
        boundaryLayerGenerator.SetInnerSurfaceCellEntityId(self.wallCellEntityId)
        if not boundaryLayerOnCaps:
            # The sidewalls are the strips that the open boundaries sweep out, so each of them
            # stands where a cap is about to be made. They are marked here and handed the id of
            # that cap at the end. A surface swept with its caps on has no open boundary and so
            # no sidewalls at all.
            boundaryLayerGenerator.SetSidewallCellEntityId(self.placeholderCellEntityId)
        boundaryLayerGenerator.Update()

        innerGrid = boundaryLayerGenerator.GetInnerSurface()
        if boundaryLayerOnCaps:
            # The inner surface comes back under one id, being all of it wall as far as the sweep
            # is concerned. It is a closed surface here, though - the caps were swept along with
            # the rest - so it is handed the ids of the surface it was swept from, which say
            # which of its cells are cap. The sweep copies the surface cell for cell, so they are
            # the same cells in the same order. What reads them is the mesher: a boundary that
            # comes back retriangulated is labelled from the surface it was made for.
            innerGrid.GetCellData().GetArray(cellEntityIdsArrayName).DeepCopy(
                outerSurfaceMesh.GetCellData().GetArray(cellEntityIdsArrayName))
        innerSurface = self.meshToSurface(innerGrid)

        # A layer swept inwards folds over itself if it is thicker than the vessel has room for,
        # and it goes first where the surface turns a corner - the rim where a cap meets the wall.
        # TetGen does not merely fail on what comes out of that: it walks off the end of the
        # tangled surface and takes the application down with it, so the sweep is asked for the
        # one thing that has to be true of it before TetGen is handed anything. A surface swept
        # inwards covers less than it started with; one that has folded through itself can cover
        # more. This is a net rather than a proof - a small enough fold adds little area - but it
        # is what catches the case that is worth catching.
        outerArea = self.surfaceArea(remeshedSurface)
        innerArea = self.surfaceArea(innerSurface)
        if outerArea > 0.0 and innerArea > 1.05 * outerArea:
            raise RuntimeError(_(
                "The boundary layer folded over itself: swept inwards, it covers more than the "
                "surface it was grown from. Make the layer thinner, ask for fewer sublayers, or "
                "give it more substeps to settle over; turning \"Layer on caps\" off also keeps "
                "it away from the corner where a cap meets the wall, which is where a layer "
                "folds first."))

        if not boundaryLayerOnCaps:
            self.log(_("Capping inner surface"))
            # Where the surface arrived with caps of its own, the ids they carried are the ones a
            # solver has been told to read, so the caps built in their place are given them back.
            innerSurface = self.triangulate(
                self.capSurface(innerSurface, cellEntityIdsArrayName, cappingMethod,
                                capsTakenOff,
                                boundaryLabelsArrayName=boundaryLabelsArrayName,
                                boundaryPointOrderArrayName=boundaryPointOrderArrayName))

            self.log(_("Remeshing endcaps"))
            innerSurface = self.remeshSurface(
                innerSurface, cellEntityIdsArrayName, elementSizeMode=elementSizeMode,
                targetEdgeLength=targetEdgeLength * endcapsEdgeLengthFactor,
                targetEdgeLengthArrayName=targetEdgeLengthArrayName,
                targetEdgeLengthFactor=targetEdgeLengthFactor * endcapsEdgeLengthFactor,
                triangleSplitFactor=triangleSplitFactor,
                maxEdgeLength=maxEdgeLength, minEdgeLength=minEdgeLength,
                excludedEntityIds=self.wallFaceIdsOf(innerSurface, cellEntityIdsArrayName))

        innerSurfaceMesh = self.surfaceToMesh(innerSurface)

        # A mesher that keeps the surface it is given - TetGen, Netgen - needs nothing back from
        # the space it filled but the tetrahedra: the face against the boundary layer is one the
        # layer already carries. A mesher that answers with a boundary of its own is asked for
        # that boundary, because the layer is then grown from it rather than the other way about.
        keepsTheSurface = Mesher(volumeMeshing.mesher).keepsTheSurface
        filled = self.fillVolume(innerSurfaceMesh, cellEntityIdsArrayName,
                                 outputSurfaceElements=not keepsTheSurface,
                                 volumeMeshing=volumeMeshing)
        if self.numberOfVolumeCells(filled) == 0 and outerSurfaceMesh.GetNumberOfCells() > 0:
            logging.warning("An error occurred during tetrahedralization. Only the surface mesh "
                            "and the boundary layer are returned.")
            self.lastTetrahedralizationFailed = True

        self.log(_("Assembling final mesh"))
        appendFilter = vtkvmtkComputationalGeometry.vtkvmtkAppendFilter()

        if keepsTheSurface:
            if not boundaryLayerOnCaps:
                # The outer surface was never capped, so every one of its cells is wall. A cell
                # under no face at all - the surface arrived without face ids - is given the
                # wall's; a wall numbered in several faces keeps them.
                outerIds = outerSurfaceMesh.GetCellData().GetArray(cellEntityIdsArrayName)
                for cellId in range(outerIds.GetNumberOfTuples()):
                    if outerIds.GetTuple1(cellId) == 0:
                        outerIds.SetTuple1(cellId, self.wallCellEntityId)
            appendFilter.AddInputData(outerSurfaceMesh)
            appendFilter.AddInputData(boundaryLayerGenerator.GetOutput())
            appendFilter.AddInputData(filled)
            if not boundaryLayerOnCaps:
                # The caps were made on the inner surface, past the boundary layer, so they are
                # taken from there.
                appendFilter.AddInputData(
                    self.capCells(innerSurfaceMesh, cellEntityIdsArrayName, keep=True))
        else:
            # The layer swept inwards has served its purpose: it said how much room to leave
            # inside the surface, and the mesher has filled what was left. The layer that ends up
            # in the mesh is grown back out of what came back, so that its inner face is made of
            # the very cells the tetrahedra are bounded by.
            volumeMesh, innerBoundary = self.splitByDimension(filled)
            layerMesh, outerMesh, capsMesh = self.growLayerOutwards(
                innerBoundary, cellEntityIdsArrayName,
                boundaryLayerOnCaps=boundaryLayerOnCaps,
                referenceSurface=referenceSurface,
                elementSizeMode=elementSizeMode,
                targetEdgeLength=targetEdgeLength,
                targetEdgeLengthArrayName=targetEdgeLengthArrayName,
                targetEdgeLengthFactor=targetEdgeLengthFactor,
                maxEdgeLength=maxEdgeLength,
                numberOfSubLayers=numberOfSubLayers,
                subLayerRatio=subLayerRatio,
                boundaryLayerThicknessFactor=boundaryLayerThicknessFactor,
                numberOfSubsteps=numberOfSubsteps,
                relaxation=relaxation,
                localCorrectionFactor=localCorrectionFactor)

            # The same question the inward sweep is asked, of the sweep that goes the other way:
            # a layer grown outwards folds where the surface turns a concave corner.
            grownArea = self.surfaceArea(self.meshToSurface(outerMesh))
            if outerArea > 0.0 and grownArea > 1.5 * outerArea:
                raise RuntimeError(_(
                    "The boundary layer folded over itself as it was grown outwards from the "
                    "volume mesh. Make the layer thinner, or ask for fewer sublayers."))

            appendFilter.AddInputData(outerMesh)
            appendFilter.AddInputData(layerMesh)
            appendFilter.AddInputData(volumeMesh)
            if capsMesh is not None:
                appendFilter.AddInputData(capsMesh)

        appendFilter.Update()
        mesh = appendFilter.GetOutput()

        if not boundaryLayerOnCaps:
            self.nameSidewallsAfterTheirCap(mesh, cellEntityIdsArrayName)
        return mesh

    @staticmethod
    def maximumElementVolume(edgeLength):
        """The volume a tetrahedron is allowed to reach: that of the regular one whose edge is
        the size asked for."""
        return edgeLength ** 3 / (6.0 * 2.0 ** 0.5)

    @staticmethod
    def numberOfVolumeCells(mesh):
        """How many three dimensional cells the mesh holds. What says a fill worked: a mesh may
        carry the boundary triangles of a volume that was never filled."""
        return sum(1 for cellId in range(mesh.GetNumberOfCells())
                   if mesh.GetCell(cellId).GetCellDimension() == 3)

    def fillVolume(self, surfaceMesh, cellEntityIdsArrayName, outputSurfaceElements,
                   volumeMeshing):
        """The surface mesh filled with tetrahedra by the mesher that was asked for.

        Every mesher answers the same way: the tetrahedra first, under entity id 0, and then -
        when asked for - the triangles bounding them, each under the id of the face of the input
        it stands on. What differs is everything behind that; see runTetGen, runFTetWild and
        runNetgen.
        """
        self.log(_("Generating volume mesh ({mesher})").format(
            mesher=Mesher(volumeMeshing.mesher).label()))
        # Asked of both meshers before either is handed the surface. fTetWild answers a surface
        # with a hole by meshing the part of it that is closed; TetGen walks off the end of it
        # and takes its process with it, which is reported as a crash and says nothing about
        # why. A remeshed surface, or one capped after a sweep, is where a hole comes from.
        openEdges = self.numberOfOpenEdges(self.meshToSurface(surfaceMesh))
        if openEdges:
            raise RuntimeError(_(
                "The surface to be filled is not closed: {count} of its edges are open or shared "
                "by more than two triangles, and a mesher cannot fill a surface with a hole in "
                "it. Remeshing is the usual cause when the target edge length is far from the "
                "size of the triangles the surface arrived with; try a target closer to those, "
                "or turn remeshing off.").format(count=openEdges))
        if volumeMeshing.mesher == Mesher.TETGEN.value:
            return self.runTetGen(
                surfaceMesh, cellEntityIdsArrayName, outputSurfaceElements,
                maxElementVolume=self.maximumElementVolume(volumeMeshing.edgeLength))
        if volumeMeshing.mesher == Mesher.NETGEN.value:
            return self.runNetgen(surfaceMesh, cellEntityIdsArrayName, outputSurfaceElements,
                                  volumeMeshing)
        return self.runFTetWild(surfaceMesh, cellEntityIdsArrayName, outputSurfaceElements,
                                volumeMeshing)

    def runTetGen(self, surfaceMesh, cellEntityIdsArrayName, outputSurfaceElements,
                  maxElementVolume):
        """The surface mesh filled with tetrahedra of at most the given volume (vmtktetgen).
        The tetrahedra come out under entity id 0.

        The size is asked for as a cap on the volume of an element rather than through the point
        by point sizing function vmtkmeshgenerator hands over, because the switch that reads that
        function - TetGen's -m - takes its sizes from a background mesh, and with none given
        TetGen builds one by duplicating the mesh it is refining. What comes of that is not a
        refusal but a coin toss: the same surface, meshed twice over in one session, comes back
        forty thousand tetrahedra one time and empty the next. A volume cap goes through the
        switch TetGen has had since its first release, and gives the same mesh every time - on a
        clipped aorta, a slightly finer one than the sizing function was asking for, and better
        shaped at its worst.
        """
        import vtkvmtkMiscPython as vtkvmtkMisc

        tetgen = vtkvmtkMisc.vtkvmtkTetGenWrapper()
        tetgen.SetInputData(surfaceMesh)
        # Mesh the volume bounded by the given faces (a piecewise linear complex), keeping those
        # faces as they are, and drop the worst of the flat tetrahedra that meshing leaves behind.
        tetgen.SetPLC(1)
        tetgen.SetQuality(1)
        tetgen.SetNoBoundarySplit(1)
        tetgen.SetRemoveSliver(1)
        tetgen.SetOrder(1)
        # The quality bounds vmtktetgen asks for, which are not the ones the wrapper defaults to:
        # a radius-edge ratio no worse than sqrt(2), and dihedral angles inside 10 to 165 degrees.
        tetgen.SetMinRatio(1.414)
        tetgen.SetMinDihedral(10.0)
        tetgen.SetMaxDihedral(165.0)
        tetgen.SetFixedVolume(1)
        tetgen.SetMaxVolume(maxElementVolume)
        tetgen.SetCellEntityIdsArrayName(cellEntityIdsArrayName)
        tetgen.SetOutputSurfaceElements(1 if outputSurfaceElements else 0)
        tetgen.SetOutputVolumeElements(1)
        tetgen.Update()
        # A TetGen run that threw hands back an empty mesh rather than raising; what it makes of
        # that is left to the caller, as it is in vmtkmeshgenerator.
        return tetgen.GetOutput()

    def runFTetWild(self, surfaceMesh, cellEntityIdsArrayName, outputSurfaceElements,
                    volumeMeshing):
        """The surface mesh filled with tetrahedra by fTetWild. The tetrahedra come out under
        entity id 0, and the triangles bounding them under the id of the face they stand on.

        fTetWild does not fill the surface it is given so much as mesh the shape that surface
        describes: it keeps every tetrahedron whose winding number says it is inside, and the
        boundary it returns is its own triangulation, sitting within the tolerance of the one it
        was handed rather than on it. So the surface has to be closed and facing outwards, and
        the ids have to be read back off it afterwards by position, neither of which TetGen ever
        needed. What is gained for that is a mesher that answers where TetGen fails, and one that
        takes a size per point.
        """
        import numpy as np
        from vtk.util import numpy_support

        # Orienting only reorders the corners of a triangle, so the cells stay in their order and
        # keep their ids - which is what lets the ids be read off this surface further down.
        surface = self.surfaceNormals(self.triangulate(self.meshToSurface(surfaceMesh)))
        polys = surface.GetPolys()
        if surface.GetNumberOfCells() != surface.GetNumberOfPolys() or not polys.IsHomogeneous():
            raise ValueError(_("fTetWild takes a surface of triangles, and this one holds other "
                               "cells as well."))

        # A hole in the surface is not something fTetWild refuses. It decides what is inside by
        # winding number, and that number leaks out through a hole: what comes back is a mesh
        # filling part of the shape, which looks like a mesh and is not one. Asked here, where it
        # can still be said which surface was wrong, rather than discovered in a solver.
        openEdges = self.numberOfOpenEdges(surface)
        if openEdges:
            raise RuntimeError(_(
                "The surface to be filled is not closed: {count} of its edges are open or shared "
                "by more than two triangles. fTetWild answers such a surface with a mesh of the "
                "part of it that is closed rather than refusing, so it is refused here. Remeshing "
                "is the usual cause when the target edge length is far from the size of the "
                "triangles the surface arrived with; try a target closer to those, or turn "
                "remeshing off.").format(count=openEdges))

        vertices = np.ascontiguousarray(
            numpy_support.vtk_to_numpy(surface.GetPoints().GetData()), dtype=np.float64)
        faces = np.ascontiguousarray(
            numpy_support.vtk_to_numpy(polys.GetConnectivityArray()).reshape(-1, 3),
            dtype=np.int32)

        # The tolerance is asked for in mm and given as a fraction of the bounding box diagonal,
        # which is what fTetWild measures it in.
        diagonal = surface.GetLength()
        epsilon = (volumeMeshing.surfaceTolerance / diagonal
                   if volumeMeshing.surfaceTolerance > 0.0 and diagonal > 0.0 else 1e-3)

        arguments = dict(
            edge_length_abs=volumeMeshing.edgeLength,
            epsilon=epsilon,
            stop_energy=volumeMeshing.stopEnergy,
            num_opt_iter=volumeMeshing.maxOptimizationPasses,
            coarsen=volumeMeshing.coarsen,
            optimize=True,
            # fTetWild numbers the corners of a tetrahedron the other way round from VTK.
            vtk_ordering=True,
            quiet=True)
        if volumeMeshing.sizingField is not None:
            backgroundPoints, backgroundTetrahedra, backgroundLengths = volumeMeshing.sizingField
            arguments.update(
                # The sizes in the field are absolute, and the mesh is refined onto them from
                # whatever it was built at; starting from the largest of them means refining
                # everywhere the field asks for something smaller, and nowhere else.
                edge_length_abs=float(backgroundLengths.max()),
                bg_vertices=backgroundPoints,
                bg_tets=backgroundTetrahedra,
                bg_values=backgroundLengths)

        try:
            meshPoints, tetrahedra = FTetWild.tetrahedralize(
                vertices, faces, python=self.fTetWildPython, **arguments)
        except FTetWild.TetrahedralizationError:
            # Answering an unfillable surface with an empty mesh rather than an exception is what
            # the TetGen wrapper does, and what the callers of both are written around.
            logging.exception("fTetWild failed to fill the surface")
            self.lastTetrahedralizationFailed = True
            return vtk.vtkUnstructuredGrid()

        # Single precision on purpose. Everything else in the pipeline holds its points that way
        # - the boundary layer generator allocates plain vtkPoints - and the filter that puts the
        # layer and the tetrahedra back together welds points by comparing coordinates, so a mesh
        # carrying doubles would sit against the layer without ever joining it.
        meshPoints = np.ascontiguousarray(meshPoints, dtype=np.float32)
        tetrahedra = np.ascontiguousarray(tetrahedra, dtype=np.int64)

        boundary = self.boundaryFacesOfTetrahedra(tetrahedra)
        boundaryIds = self.nearestCellEntityIds(
            surface, cellEntityIdsArrayName, meshPoints[boundary].mean(axis=1))
        if not outputSurfaceElements:
            boundary = boundary[:0]
            boundaryIds = boundaryIds[:0]
        return self.meshFromArrays(meshPoints, tetrahedra, boundary, boundaryIds,
                                   cellEntityIdsArrayName)

    def runNetgen(self, surfaceMesh, cellEntityIdsArrayName, outputSurfaceElements,
                  volumeMeshing):
        """The surface mesh filled with tetrahedra by Netgen. The tetrahedra come out under
        entity id 0, and the triangles bounding them - which are the input's own - under the id
        of the face each arrived with.

        Netgen is asked TetGen's question: here is a boundary, fill the inside of it. It keeps
        every triangle and every point it is given, so the boundary needs no reading back by
        position, and a boundary layer swept from the surface meets the tetrahedra exactly, as
        it does with TetGen. What it has over TetGen is that it takes a size per point, and that
        a surface it cannot fill is answered with nothing rather than with a crash.
        """
        import numpy as np
        from vtk.util import numpy_support

        # Orienting only reorders the corners of a triangle, so the cells stay in their order and
        # keep their ids. Netgen fills the side the triangles face away from, so they must face
        # out; a surface that faces inwards as a whole is turned round again in Netgen itself.
        surface = self.surfaceNormals(self.triangulate(self.meshToSurface(surfaceMesh)))
        polys = surface.GetPolys()
        if surface.GetNumberOfCells() != surface.GetNumberOfPolys() or not polys.IsHomogeneous():
            raise ValueError(_("Netgen takes a surface of triangles, and this one holds other "
                               "cells as well."))

        vertices = np.ascontiguousarray(
            numpy_support.vtk_to_numpy(surface.GetPoints().GetData()), dtype=np.float64)
        faces = np.ascontiguousarray(
            numpy_support.vtk_to_numpy(polys.GetConnectivityArray()).reshape(-1, 3),
            dtype=np.int32)
        ids = surface.GetCellData().GetArray(cellEntityIdsArrayName)
        if ids is not None:
            faceIds = numpy_support.vtk_to_numpy(ids).astype(np.int32).ravel()
        else:
            faceIds = np.zeros(len(faces), dtype=np.int32)

        arguments = dict(
            maxh=volumeMeshing.edgeLength,
            grading=volumeMeshing.netgenGrading,
            optimizationSteps=volumeMeshing.netgenOptimizationSteps)
        if volumeMeshing.sizingField is not None:
            backgroundPoints, _backgroundTetrahedra, backgroundLengths = volumeMeshing.sizingField
            # The sizes in the field are absolute, and Netgen's field is only ever lowered from
            # the size asked for overall; starting from the largest of them means going finer
            # everywhere the field asks for something smaller, and nowhere else. The tetrahedra
            # of the background mesh are for fTetWild, which interpolates over them; Netgen
            # holds a field of its own and is told the sizes at the points alone.
            arguments.update(
                maxh=float(backgroundLengths.max()),
                sizingPoints=backgroundPoints,
                sizingLengths=backgroundLengths)

        try:
            meshPoints, tetrahedra, boundary, boundaryIds = Netgen.tetrahedralize(
                vertices, faces, faceIds, **arguments)
        except Netgen.TetrahedralizationError:
            # Answering an unfillable surface with an empty mesh rather than an exception is what
            # the TetGen wrapper does, and what the callers of every mesher are written around.
            logging.exception("Netgen failed to fill the surface")
            self.lastTetrahedralizationFailed = True
            return vtk.vtkUnstructuredGrid()

        # Netgen gives up on a surface it cannot finish without saying so in anything but its
        # own output, and what it leaves then is a mesh of part of the volume: tetrahedra whose
        # outside is not the surface they were to fill. Told apart here by counting the faces
        # of the tetrahedra that no second tetrahedron shares, which are the surface when the
        # volume was filled and more than the surface when it was not.
        if len(self.boundaryFacesOfTetrahedra(tetrahedra)) != len(boundary):
            logging.error("Netgen filled only part of the surface: the tetrahedra it made are "
                          "bounded by %d triangles where the surface has %d",
                          len(self.boundaryFacesOfTetrahedra(tetrahedra)), len(boundary))
            self.lastTetrahedralizationFailed = True
            return vtk.vtkUnstructuredGrid()

        # Single precision, as for fTetWild: the filter that puts the boundary layer and the
        # tetrahedra back together welds points by comparing coordinates, and the layer holds
        # its points that way. The points of the surface were single precision to begin with,
        # so they come back through Netgen unchanged to the bit, and the layer welds to them
        # exactly; the points Netgen added inside are rounded, which nothing else stands on.
        meshPoints = np.ascontiguousarray(meshPoints, dtype=np.float32)
        tetrahedra = np.ascontiguousarray(tetrahedra, dtype=np.int64)
        boundary = np.ascontiguousarray(boundary, dtype=np.int64)
        boundaryIds = np.ascontiguousarray(boundaryIds, dtype=np.int32)
        if not outputSurfaceElements:
            boundary = boundary[:0]
            boundaryIds = boundaryIds[:0]
        return self.meshFromArrays(meshPoints, tetrahedra, boundary, boundaryIds,
                                   cellEntityIdsArrayName)

    @staticmethod
    def meshFromArrays(meshPoints, tetrahedra, boundary, boundaryIds, cellEntityIdsArrayName):
        """An unstructured grid of the given tetrahedra, under entity id 0, followed by the
        given boundary triangles, each under its own id: the shape every mesher's answer takes.

        :param meshPoints: the points, as an (n, 3) float32 array.
        :param tetrahedra: (t, 4) point ids, wound the way VTK winds a tetrahedron.
        :param boundary: (b, 3) point ids of the triangles bounding them; may be empty.
        :param boundaryIds: (b,) the entity id of each of those triangles.
        """
        import numpy as np
        from vtk.util import numpy_support

        points = vtk.vtkPoints()
        points.SetData(numpy_support.numpy_to_vtk(meshPoints, deep=True,
                                                  array_type=vtk.VTK_FLOAT))

        connectivity = np.concatenate([tetrahedra.ravel(), boundary.ravel()])
        offsets = np.concatenate([
            np.arange(0, 4 * len(tetrahedra) + 1, 4, dtype=np.int64),
            4 * len(tetrahedra) + np.arange(3, 3 * len(boundary) + 1, 3, dtype=np.int64)])
        cells = vtk.vtkCellArray()
        cells.SetData(numpy_support.numpy_to_vtkIdTypeArray(offsets, deep=True),
                      numpy_support.numpy_to_vtkIdTypeArray(connectivity, deep=True))
        cellTypes = np.concatenate([
            np.full(len(tetrahedra), vtk.VTK_TETRA, dtype=np.uint8),
            np.full(len(boundary), vtk.VTK_TRIANGLE, dtype=np.uint8)])

        mesh = vtk.vtkUnstructuredGrid()
        mesh.SetPoints(points)
        mesh.SetCells(numpy_support.numpy_to_vtk(cellTypes, deep=True,
                                                 array_type=vtk.VTK_UNSIGNED_CHAR), cells)

        ids = numpy_support.numpy_to_vtk(
            np.concatenate([np.zeros(len(tetrahedra), dtype=np.int32),
                            np.asarray(boundaryIds, dtype=np.int32)]),
            deep=True, array_type=vtk.VTK_INT)
        ids.SetName(cellEntityIdsArrayName)
        mesh.GetCellData().AddArray(ids)
        return mesh

    @staticmethod
    def numberOfOpenEdges(surface):
        """How many edges of the surface are open or shared by more than two cells, which is how
        many places it is not the boundary of a solid."""
        edges = vtk.vtkFeatureEdges()
        edges.SetInputData(surface)
        edges.BoundaryEdgesOn()
        edges.NonManifoldEdgesOn()
        edges.FeatureEdgesOff()
        edges.ManifoldEdgesOff()
        edges.Update()
        return edges.GetOutput().GetNumberOfCells()

    @staticmethod
    def boundaryFacesOfTetrahedra(tetrahedra):
        """The faces of the given tetrahedra that no second tetrahedron shares, facing outwards.

        Read off the connectivity rather than out of a filter, so that the faces are made of the
        same point ids the tetrahedra are - which is what lets the layer that is grown from them
        join them again.
        """
        import numpy as np

        # VTK's face table for a tetrahedron. Each face is wound so that its normal points out of
        # a tetrahedron whose own corners are numbered the way VTK numbers them.
        faces = tetrahedra[:, [[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]]].reshape(-1, 3)
        _, first, counts = np.unique(np.sort(faces, axis=1), axis=0,
                                     return_index=True, return_counts=True)
        return faces[np.sort(first[counts == 1])]

    @staticmethod
    def nearestCellEntityIds(surface, cellEntityIdsArrayName, points):
        """The face id of the surface cell nearest each of the given points.

        This is how a boundary that was retriangulated gets its face ids back. It holds because
        the new boundary lies within the tolerance of the old one, which is far smaller than the
        cells of either; the one place it can be read either way is the line where two faces
        meet, and a cell astride that line is on the line whichever id it is given.
        """
        import numpy as np

        ids = surface.GetCellData().GetArray(cellEntityIdsArrayName)
        if ids is None:
            return np.zeros(len(points), dtype=np.int32)

        locator = vtk.vtkStaticCellLocator()
        locator.SetDataSet(surface)
        locator.BuildLocator()

        cell = vtk.vtkGenericCell()
        closestPoint = [0.0, 0.0, 0.0]
        cellId = vtk.reference(0)
        subId = vtk.reference(0)
        squaredDistance = vtk.reference(0.0)

        found = np.empty(len(points), dtype=np.int32)
        for index, point in enumerate(points):
            locator.FindClosestPoint([float(value) for value in point], closestPoint, cell,
                                     cellId, subId, squaredDistance)
            found[index] = int(ids.GetTuple1(cellId.get()))
        return found

    @staticmethod
    def splitByDimension(mesh):
        """The mesh split into its volume elements and the surface cells bounding them."""
        volume = vtk.vtkExtractCellsByType()
        volume.SetInputData(mesh)
        for cellType in (vtk.VTK_TETRA, vtk.VTK_WEDGE, vtk.VTK_HEXAHEDRON):
            volume.AddCellType(cellType)
        volume.Update()

        boundary = vtk.vtkExtractCellsByType()
        boundary.SetInputData(mesh)
        for cellType in (vtk.VTK_TRIANGLE, vtk.VTK_QUAD):
            boundary.AddCellType(cellType)
        boundary.Update()

        surface = vtk.vtkGeometryFilter()
        surface.SetInputData(boundary.GetOutput())
        surface.MergingOff()
        surface.Update()
        return volume.GetOutput(), surface.GetOutput()

    def nameSidewallsAfterTheirCap(self, mesh, cellEntityIdsArrayName):
        """Hand every sidewall cell of the boundary layer the id of the cap it runs into.

        A boundary layer that stopped short of the caps swept each open boundary into a strip of
        cells standing where the vessel end is, between the cap made on the inner surface and the
        rim of the outer one. Those strips are part of that end and have to answer to the same
        boundary condition, but they were made before the caps were numbered, so they come out
        under a placeholder id. Each strip touches its own cap and no other, so the id spreads
        from the cap cells outwards over everything still carrying the placeholder.
        """
        surfaceCellTypes = (vtk.VTK_TRIANGLE, vtk.VTK_QUADRATIC_TRIANGLE, vtk.VTK_QUAD)
        cellEntityIdsArray = mesh.GetCellData().GetArray(cellEntityIdsArrayName)
        if cellEntityIdsArray is None:
            return
        mesh.BuildLinks()

        cellPointIds = vtk.vtkIdList()
        singlePointId = vtk.vtkIdList()
        singlePointId.SetNumberOfIds(1)
        neighbourCellIds = vtk.vtkIdList()

        def spreadFrom(seedCellId, capEntityId):
            frontier = [seedCellId]
            while frontier:
                cellId = frontier.pop()
                mesh.GetCellPoints(cellId, cellPointIds)
                for index in range(cellPointIds.GetNumberOfIds()):
                    singlePointId.SetId(0, cellPointIds.GetId(index))
                    mesh.GetCellNeighbors(cellId, singlePointId, neighbourCellIds)
                    for neighbourIndex in range(neighbourCellIds.GetNumberOfIds()):
                        neighbourCellId = neighbourCellIds.GetId(neighbourIndex)
                        if mesh.GetCellType(neighbourCellId) not in surfaceCellTypes:
                            continue
                        if cellEntityIdsArray.GetTuple1(neighbourCellId) != self.placeholderCellEntityId:
                            continue
                        cellEntityIdsArray.SetTuple1(neighbourCellId, capEntityId)
                        frontier.append(neighbourCellId)

        for cellId in range(mesh.GetNumberOfCells()):
            if mesh.GetCellType(cellId) not in surfaceCellTypes:
                continue
            cellEntityId = int(cellEntityIdsArray.GetTuple1(cellId))
            if cellEntityId == self.placeholderCellEntityId or not self.isCapId(cellEntityId):
                continue
            spreadFrom(cellId, cellEntityId)

    #
    # Small conversions, one per vmtk script that only wraps a VTK filter.
    #

    @staticmethod
    def cleanSurface(surface):
        """The surface with its coincident points merged into one and its unused points dropped.

        A cell that the merge leaves degenerate is dropped rather than turned into a line or a
        vertex, which is what vtkCleanPolyData does if it is let. A line lying among the polygons
        is no use to anything downstream - TetGen refuses one, and the sizing function skips it -
        and it is not harmless either: vtkTriangleFilter loses track of the cell data of a surface
        that carries both, so the face ids come back scattered over the wrong cells. Dropping the
        cell instead leaves the surface closed and manifold, because a triangle whose two
        coincident corners have become one point covers its one remaining edge twice over.
        """
        cleaner = vtk.vtkCleanPolyData()
        cleaner.SetInputData(surface)
        cleaner.ConvertPolysToLinesOff()
        cleaner.ConvertLinesToPointsOff()
        cleaner.ConvertStripsToPolysOff()
        cleaner.Update()
        return cleaner.GetOutput()

    def surfaceToMesh(self, surface):
        """The surface as an unstructured grid, cleaned first (vmtksurfacetomesh)."""
        import vtkvmtkMiscPython as vtkvmtkMisc

        surfaceToMeshFilter = vtkvmtkMisc.vtkvmtkPolyDataToUnstructuredGridFilter()
        surfaceToMeshFilter.SetInputData(self.cleanSurface(surface))
        surfaceToMeshFilter.Update()
        return surfaceToMeshFilter.GetOutput()

    @staticmethod
    def meshToSurface(mesh):
        """The surface of an unstructured grid (vmtkmeshtosurface)."""
        meshToSurfaceFilter = vtk.vtkGeometryFilter()
        meshToSurfaceFilter.SetInputData(mesh)
        meshToSurfaceFilter.Update()
        return meshToSurfaceFilter.GetOutput()

    @staticmethod
    def surfaceNormals(surface, autoOrient=True):
        """The surface carrying an outward normal per point (vmtksurfacenormals).

        Since the VTK 9.4 refactor vtkPolyDataNormals passes normals it was given through
        untouched, so any the surface came with are dropped first - the boundary layer is swept
        along these, and one left pointing the wrong way sweeps a layer out of the vessel rather
        than into it.

        autoOrient off computes the normals from the winding of the cells as they are, and leaves
        that winding alone. For a surface already known to face outwards it is the more careful
        of the two: deciding which way is out is a question about the whole surface, so asking it
        of a piece of one - a wall with its caps taken off, say - answers about the piece.
        """
        withoutNormals = vtk.vtkPolyData()
        withoutNormals.ShallowCopy(surface)
        withoutNormals.GetPointData().SetNormals(None)
        withoutNormals.GetCellData().SetNormals(None)

        normalsFilter = vtk.vtkPolyDataNormals()
        normalsFilter.SetInputData(withoutNormals)
        normalsFilter.SetAutoOrientNormals(1 if autoOrient else 0)
        normalsFilter.SetConsistency(1 if autoOrient else 0)
        normalsFilter.ComputeCellNormalsOff()
        normalsFilter.SplittingOff()
        normalsFilter.Update()
        surfaceWithNormals = normalsFilter.GetOutput()
        surfaceWithNormals.GetPointData().GetNormals().SetName("Normals")
        return surfaceWithNormals

    @classmethod
    def triangulate(cls, surface):
        """The surface with every cell split into triangles.

        vtkTriangleFilter does the splitting, except for polygons of five corners or more - the
        caps - which are ear-cut here first. The filter hands those to vtkPolygon's ear cut,
        which ranks the ears by their perimeter-to-area ratio and, on some perfectly ordinary cap
        outlines - the inlet of an aorta, forty-two corners, planar to a tenth of a millimetre
        and nowhere near crossing itself - runs out of ears with three corners still unused. The
        cap then comes back short of a notch, with the rim edges beside it open, and the hole is
        only found when a mesher refuses the surface. Ranking the ears by angle triangulates the
        same outline in full, so that is tried first, then the other two rankings and the
        unbiased ear cut, and the first that uses every corner is taken. Only a polygon none of
        them can do is left to the filter.
        """
        import numpy as np
        from vtk.util import numpy_support

        polys = surface.GetPolys()
        if polys.GetNumberOfCells() == 0 or surface.GetNumberOfStrips() > 0:
            return cls._triangleFilter(surface)
        offsets = numpy_support.vtk_to_numpy(polys.GetOffsetsArray()).astype(np.int64)
        connectivity = numpy_support.vtk_to_numpy(polys.GetConnectivityArray()).astype(np.int64)
        sizes = np.diff(offsets)
        large = np.flatnonzero(sizes > 4)
        if large.size == 0:
            return cls._triangleFilter(surface)

        # The polygons are rebuilt in their order, each large one replaced by its triangles, so
        # that the cell data can be carried across by which polygon each cell came from.
        chunks = []  # (connectivity, sizes, source polygon index per cell)
        start = 0
        for index in large:
            if index > start:
                chunks.append((connectivity[offsets[start]:offsets[index]], sizes[start:index],
                               np.arange(start, index)))
            pointIds = connectivity[offsets[index]:offsets[index + 1]]
            triangles = cls.earCut(surface.GetPoints(), pointIds)
            if triangles is None:
                chunks.append((pointIds, sizes[index:index + 1], np.array([index])))
            else:
                chunks.append((triangles.ravel(), np.full(len(triangles), 3),
                               np.full(len(triangles), index)))
            start = index + 1
        if start < len(sizes):
            chunks.append((connectivity[offsets[start]:], sizes[start:],
                           np.arange(start, len(sizes))))
        newConnectivity = np.concatenate([chunk[0] for chunk in chunks])
        newSizes = np.concatenate([chunk[1] for chunk in chunks])
        sources = np.concatenate([chunk[2] for chunk in chunks])
        newOffsets = np.concatenate([[0], np.cumsum(newSizes)])

        cells = vtk.vtkCellArray()
        cells.SetData(numpy_support.numpy_to_vtkIdTypeArray(newOffsets, deep=True),
                      numpy_support.numpy_to_vtkIdTypeArray(newConnectivity, deep=True))
        rebuilt = vtk.vtkPolyData()
        rebuilt.SetPoints(surface.GetPoints())
        rebuilt.SetPolys(cells)
        rebuilt.GetPointData().ShallowCopy(surface.GetPointData())
        # The polygons are the cells after any vertices and lines, which are dropped here as
        # the filter drops them.
        sources += surface.GetNumberOfVerts() + surface.GetNumberOfLines()
        cellData = surface.GetCellData()
        for arrayIndex in range(cellData.GetNumberOfArrays()):
            array = cellData.GetArray(arrayIndex)
            if array is None:
                continue
            values = numpy_support.vtk_to_numpy(array)
            copied = numpy_support.numpy_to_vtk(np.ascontiguousarray(values[sources]), deep=True,
                                                array_type=array.GetDataType())
            copied.SetName(array.GetName())
            rebuilt.GetCellData().AddArray(copied)
        return cls._triangleFilter(rebuilt)

    @staticmethod
    def _triangleFilter(surface):
        triangleFilter = vtk.vtkTriangleFilter()
        triangleFilter.SetInputData(surface)
        triangleFilter.PassLinesOff()
        triangleFilter.PassVertsOff()
        triangleFilter.Update()
        return triangleFilter.GetOutput()

    @staticmethod
    def earCut(points, pointIds):
        """The polygon over the given point ids cut into triangles, as an (n - 2, 3) array of
        point ids, or None if no ear cut could use every corner; see triangulate."""
        import numpy as np

        count = len(pointIds)
        polygon = vtk.vtkPolygon()
        polygon.GetPointIds().SetNumberOfIds(count)
        polygon.GetPoints().SetNumberOfPoints(count)
        for local, pointId in enumerate(pointIds):
            polygon.GetPointIds().SetId(local, int(pointId))
            polygon.GetPoints().SetPoint(local, points.GetPoint(int(pointId)))
        triangles = vtk.vtkIdList()
        attempts = [(polygon.EarCutTriangulation, measure) for measure in (
            vtk.vtkPolygon.DOT_PRODUCT, vtk.vtkPolygon.PERIMETER2_TO_AREA_RATIO,
            vtk.vtkPolygon.BEST_QUALITY)]
        for method, measure in attempts + [(None, vtk.vtkPolygon.DOT_PRODUCT)]:
            triangles.Reset()
            if method is None:
                polygon.UnbiasedEarCutTriangulation(0, triangles, measure)
            else:
                method(triangles, measure)
            if triangles.GetNumberOfIds() == 3 * (count - 2):
                local = np.array([triangles.GetId(k) for k in range(triangles.GetNumberOfIds())])
                return np.asarray(pointIds)[local].reshape(-1, 3)
        return None

    @staticmethod
    def surfaceArea(surface):
        """The total area of the surface. It says nothing about the surface being closed, which
        is what makes it usable on the vessel wall before its ends are capped."""
        massProperties = vtk.vtkMassProperties()
        massProperties.SetInputData(surface)
        massProperties.Update()
        return massProperties.GetSurfaceArea()

    @staticmethod
    def equilateralTriangleArea(edgeLength):
        """The area of the equilateral triangle of the given side, which is what an edge length
        comes to for a remesher that sizes its cells by area."""
        return 0.25 * 3.0 ** 0.5 * edgeLength ** 2

    @staticmethod
    def meshLengthLimit(edgeLength):
        """An edge length limit, with 0 read as no limit at all.

        vmtkmeshgenerator writes "no limit" as an edge length past any real mesh; 0 says the same
        thing without the reader having to recognise the number.
        """
        return UNLIMITED_EDGE_LENGTH if edgeLength <= 0.0 else edgeLength

    def log(self, message):
        """Say which step of the pipeline is running, and log how long the step before it took.

        Each step takes long enough to be worth reporting on its own - the step announced is the
        only sign of progress a long meshing run gives - and logging its duration once it is
        known, rather than at the moment it is measured, is what keeps one line per step instead
        of two. The last step of a run is timed too; see _finishStepLog.
        """
        self._finishStepLog()
        self._stepName = message
        self._stepStartTime = time.time()
        # Announced before it is logged: a reader of both - the module relays the worker's
        # output - takes the log line that follows an announcement as the same message. The
        # ellipsis says the step is under way; its completion is reported separately.
        if self.stepCallback:
            self.stepCallback(message + "...")
        logging.info("%s...", message)

    def note(self, message):
        """Say something that is not a step - that one was skipped, say - as one line, with
        no completion to follow. It closes the step before it, as a step would."""
        self._finishStepLog()
        logging.info("%s.", message)

    def _finishStepLog(self):
        """Log how long the step log() last announced took, if one is still open."""
        if self._stepName is not None:
            logging.info("%s completed in %.2f s.", self._stepName,
                         time.time() - self._stepStartTime)
            self._stepName = None
            self._stepStartTime = None

