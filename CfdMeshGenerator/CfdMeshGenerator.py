"""Generate a volume mesh suitable for CFD from a vessel surface.

This is VMTK's vmtkmeshgenerator script as a Slicer module. The script itself cannot be run here:
it drives the pipeline through the `vmtk` Python package, which the Slicer extension does not
install - only the wrapped C++ classes are available. The pipeline below is the same one, built
out of those classes directly, and every parameter the script exposes is exposed here under the
same name, meaning and default - bar the few a dialog reads better asking the other way round: a
surface is asked to be capped and remeshed rather than to have capping and remeshing skipped, and
an edge length limit of 0 is the script's "no limit".
"""

import dataclasses
import enum
import importlib
import logging
import sys
import time
import types
import unittest
from typing import Annotated

import qt
import vtk

import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from slicer.parameterNodeWrapper import parameterNodeWrapper, Minimum

from slicer import vtkMRMLModelNode


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

# What to install when fTetWild is asked for. Pinned rather than floating: the mesh a version
# gives is the mesh it gives, and a solver run is worth being able to repeat.
FTETWILD_REQUIREMENT = "pytetwild==0.4.2"


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

    fTetWild is not built into the extension: it arrives as the pytetwild package, downloaded
    from PyPI the first time it is asked for.
    """

    TETGEN = "tetgen"
    FTETWILD = "ftetwild"

    def label(self):
        return {
            Mesher.TETGEN: _("TetGen"),
            Mesher.FTETWILD: _("fTetWild"),
        }[self]


#
# CfdMeshGenerator
#


class CfdMeshGenerator(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("CFD Mesh Generator")
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Vascular Modeling Toolkit")]
        self.parent.dependencies = []
        self.parent.contributors = ["Luca Antiga (Orobix)", "David Steinman (University of Toronto)"]
        self.parent.helpText = _("""
Fill a vessel surface with tetrahedra, ready for a computational fluid dynamics solver. The
surface is capped, remeshed into near equilateral triangles, optionally lined on the inside with a
prismatic boundary layer, and filled by TetGen or fTetWild. Every cell of the result carries the id of the
face it belongs to - the wall, or one cap per vessel end - so that a boundary condition can be
assigned per face.
This is the pipeline of VMTK's vmtkmeshgenerator script, with the same parameters.
Documentation is available <a href="https://github.com/vmtk/SlicerExtension-VMTK/blob/master/Docs/CfdMeshGenerator.md">here</a>.
""")
        self.parent.acknowledgementText = _("""
This module wraps the mesh generation pipeline of the Vascular Modeling Toolkit (www.vmtk.org),
developed by Luca Antiga and David Steinman.
The volume mesh is generated by TetGen, by Hang Si, or by fTetWild.
TetGen is licensed under the terms of the MIT license with exceptions, one of which is that
distribution of it for any commercial purpose is permissible only by direct arrangement with the
copyright owner. For private, research and educational purposes it can be used at no cost and
without further arrangements. Anyone putting this module to commercial use should read TetGen's
license first.
fTetWild is "Fast Tetrahedral Meshing in the Wild", by Yixin Hu, Teseo Schneider, Bolun Wang,
Denis Zorin and Daniele Panozzo (ACM Transactions on Graphics 39(4), SIGGRAPH 2020), under the
Mozilla Public License 2.0. It is used through the pytetwild package of the PyVista project,
which the module downloads from PyPI the first time fTetWild is asked for.
""")


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

    # A target edge length per point of a background mesh, as (points, tetrahedra, lengths), for
    # fTetWild to interpolate over. None asks for one size throughout. TetGen ignores it: the
    # switch that reads a size per point takes it from a background mesh of its own making and
    # answers differently each run (see runTetGen).
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


#
# CfdMeshGeneratorParameterNode
#


@parameterNodeWrapper
class CfdMeshGeneratorParameterNode:
    """The parameters of the meshing pipeline, stored in the scene.

    inputSurface - the surface to fill with tetrahedra; its open boundaries are capped first
    outputMesh - model node the volume mesh is written into
    outputRemeshedSurface - optional model node the remeshed surface alone is written into

    The rest are the parameters of vmtkmeshgenerator, described one by one on
    CfdMeshGeneratorLogic.generateMesh(), which keeps the names and the senses the script uses:
    capSurface, remeshSurface and remeshWall here are its skipCapping, skipRemeshing and
    remeshCapsOnly negated.
    """

    inputSurface: vtkMRMLModelNode
    outputMesh: vtkMRMLModelNode
    outputRemeshedSurface: vtkMRMLModelNode

    # Surface mesh
    elementSizeMode: ElementSizeMode = ElementSizeMode.EDGE_LENGTH
    targetEdgeLength: Annotated[float, Minimum(0.0)] = 1.0
    targetEdgeLengthArrayName: str = ""
    targetEdgeLengthFactor: Annotated[float, Minimum(0.0)] = 1.0
    maxEdgeLength: Annotated[float, Minimum(0.0)] = 0.0
    minEdgeLength: Annotated[float, Minimum(0.0)] = 0.0
    triangleSplitFactor: Annotated[float, Minimum(0.0)] = 5.0
    remeshSurface: bool = True
    remeshWall: bool = True

    # Capping
    capSurface: bool = True
    cappingMethod: CappingMethod = CappingMethod.SIMPLE

    # Volume mesh
    mesher: Mesher = Mesher.TETGEN
    volumeElementScaleFactor: Annotated[float, Minimum(0.0)] = 0.8
    surfaceTolerance: Annotated[float, Minimum(0.0)] = 0.0
    stopEnergy: Annotated[float, Minimum(3.0)] = 10.0
    maxOptimizationPasses: Annotated[int, Minimum(1)] = 80
    coarsen: bool = False
    tetrahedralize: bool = False
    cellEntityIdsArrayName: str = "CellEntityIds"
    boundaryLabelsArrayName: str = DEFAULT_BOUNDARY_LABELS_ARRAY_NAME
    boundaryPointOrderArrayName: str = DEFAULT_BOUNDARY_POINT_ORDER_ARRAY_NAME

    # Boundary layer
    boundaryLayer: bool = False
    boundaryLayerOnCaps: bool = True
    numberOfSubLayers: Annotated[int, Minimum(0)] = 2
    subLayerRatio: Annotated[float, Minimum(0.0)] = 0.5
    boundaryLayerThicknessFactor: Annotated[float, Minimum(0.0)] = 0.25
    endcapsEdgeLengthFactor: Annotated[float, Minimum(0.0)] = 1.0
    numberOfSubsteps: Annotated[int, Minimum(MINIMUM_SUBSTEPS)] = 2000
    relaxation: Annotated[float, Minimum(0.0)] = 0.01
    localCorrectionFactor: Annotated[float, Minimum(0.0)] = 0.45


#
# CfdMeshGeneratorWidget
#


class CfdMeshGeneratorWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None
        self._parameterNodeGuiTag = None
        # The input surface the outputs are currently named after, so that picking another one
        # is told apart from any other change to the parameter node (see _followInputSurface),
        # and the node itself while it is watched for a surface arriving in it.
        self._followedInputSurfaceId = None
        self._observedInputSurfaceNode = None

    def setup(self) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        uiWidget = slicer.util.loadUI(self.resourcePath("UI/CfdMeshGenerator.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal is connected to each MRML widget's
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        self.logic = CfdMeshGeneratorLogic()

        # These connections ensure that we update the parameter node when the scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # Until a surface is picked to name them after (see _followInputSurface), so that a node
        # created from the selector is at least called what it is.
        self.ui.outputMeshSelector.baseName = _("volumetric mesh")
        self.ui.outputRemeshedSurfaceSelector.baseName = _("remeshed surface")

        # A show/hide and an edges button beside each node selector. Neither carries a checked
        # state: it would be saying what the display node holds, and nothing tells it when that
        # changes elsewhere, so the mark would sooner or later contradict the scene. Each reads
        # the state at the moment it is pressed and turns it around.
        self.visibilityButtons = [
            (self.ui.inputSurfaceVisibilityButton, self.ui.inputSurfaceEdgesButton, "inputSurface"),
            (self.ui.outputMeshVisibilityButton, self.ui.outputMeshEdgesButton, "outputMesh"),
            (self.ui.outputRemeshedSurfaceVisibilityButton, self.ui.outputRemeshedSurfaceEdgesButton,
             "outputRemeshedSurface"),
        ]
        # A tool button asks for a taller box than the selector beside it - it sizes itself around
        # its icon - so the row would come out ragged. The height to keep is the selector's, and
        # the icons are scaled to what is left inside once the frame has taken its share. Asked of
        # the widgets rather than written down as a number, so that it stays right whatever the
        # font size, the style and the screen make of them.
        rowHeight = self.ui.inputSurfaceSelector.sizeHint.height()
        for visibilityButton, edgesButton, nodeName in self.visibilityButtons:
            visibilityButton.setIcon(qt.QIcon(":/Icons/Medium/SlicerVisibleInvisible.png"))
            edgesButton.setIcon(qt.QIcon(self.resourcePath("Icons/ToggleEdges.svg")))
            for button in (edgesButton, visibilityButton):
                button.setAutoRaise(True)
                button.setFixedHeight(rowHeight)
                button.setIconSize(qt.QSize(rowHeight - 8, rowHeight - 8))
            visibilityButton.connect("clicked()",
                                     lambda nodeName=nodeName: self.onToggleVisibility(nodeName))
            edgesButton.connect("clicked()",
                                lambda nodeName=nodeName: self.onToggleEdgeVisibility(nodeName))

        # The volume mesh has one more: what is worth looking at in it is inside it.
        self.ui.outputMeshClipButton.setIcon(qt.QIcon(self.resourcePath("Icons/ToggleClipping.svg")))
        self.ui.outputMeshClipButton.setAutoRaise(True)
        self.ui.outputMeshClipButton.setFixedHeight(rowHeight)
        self.ui.outputMeshClipButton.setIconSize(qt.QSize(rowHeight - 8, rowHeight - 8))
        self.ui.outputMeshClipButton.connect("clicked()", self.onToggleClipping)

        self.ui.applyButton.connect("clicked(bool)", self.onApplyButton)

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

    def cleanup(self) -> None:
        """Called when the application closes and the module widget is destroyed."""
        self.removeObservers()

    def enter(self) -> None:
        """Called each time the user opens this module."""
        self.initializeParameterNode()

    def exit(self) -> None:
        """Called each time the user opens a different module."""
        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self._parameterNodeGuiTag = None
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._onParameterNodeModified)

    def onSceneStartClose(self, caller, event) -> None:
        """Called just before the scene is closed."""
        self.setParameterNode(None)

    def onSceneEndClose(self, caller, event) -> None:
        """Called just after the scene is closed."""
        if self.parent.isEntered:
            self.initializeParameterNode()

    def initializeParameterNode(self) -> None:
        """Ensure parameter node exists and observed."""
        self.setParameterNode(self.logic.getParameterNode())

        # Select the first surface in the scene if nothing is selected yet, to save a few clicks.
        # Not simply the first model node: a scene holds model nodes of Slicer's own - the slice
        # view planes among them - which are hidden from the selectors, so picking one would set
        # the module to a surface the user cannot see chosen and cannot choose again.
        if not self._parameterNode.inputSurface:
            for index in range(slicer.mrmlScene.GetNumberOfNodesByClass("vtkMRMLModelNode")):
                modelNode = slicer.mrmlScene.GetNthNodeByClass(index, "vtkMRMLModelNode")
                if modelNode.GetHideFromEditors() or not modelNode.GetPolyData():
                    continue
                self._parameterNode.inputSurface = modelNode
                break

    def setParameterNode(self, inputParameterNode: CfdMeshGeneratorParameterNode | None) -> None:
        """Set and observe the parameter node, so that the GUI follows it."""
        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._onParameterNodeModified)
        self._parameterNode = inputParameterNode
        if self._parameterNode:
            # Note: in the .ui file, a Qt dynamic property called "SlicerParameterName" is set on
            # each ui element that needs connection.
            self._parameterNodeGuiTag = self._parameterNode.connectGui(self.ui)
            # After connecting, not once at setup: connecting is what fills the combo box, and it
            # fills it afresh each time.
            self._updateMesherChoices()
            self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._onParameterNodeModified)
            self._onParameterNodeModified()

    def _onParameterNodeModified(self, caller=None, event=None) -> None:
        self._followInputSurface()
        self._updateApplyButton()
        self._updateEnabledStates()
        self._updateVisibilityButtons()

    def displayNodeOf(self, nodeName):
        """The display node of one of the module's own model nodes, made if the node has none.

        A node picked from a selector need not have one yet - an output node is created empty -
        and it is the press of a button that says the node is about to be looked at.
        """
        node = getattr(self._parameterNode, nodeName) if self._parameterNode else None
        if not node:
            return None
        if not node.GetDisplayNode():
            node.CreateDefaultDisplayNodes()
        return node.GetDisplayNode()

    def _updateVisibilityButtons(self) -> None:
        """Offer each pair of buttons only while there is a node for them to act on.

        On the node being there, and not on what is in it or how it is being shown: those change
        without the parameter node changing, and nothing here would hear of it, so a button that
        went by them could be greyed out over a surface that is on screen. What state the node is
        in is not asked either - the buttons say nothing about it, so there is nothing about them
        to keep in step.
        """
        for visibilityButton, edgesButton, nodeName in self.visibilityButtons:
            hasNode = (getattr(self._parameterNode, nodeName) if self._parameterNode else None) is not None
            visibilityButton.enabled = hasNode
            edgesButton.enabled = hasNode
        self.ui.outputMeshClipButton.enabled = (
            self._parameterNode is not None and self._parameterNode.outputMesh is not None)

    def onToggleVisibility(self, nodeName) -> None:
        displayNode = self.displayNodeOf(nodeName)
        if displayNode:
            displayNode.SetVisibility(not displayNode.GetVisibility())

    def onToggleEdgeVisibility(self, nodeName) -> None:
        displayNode = self.displayNodeOf(nodeName)
        if displayNode:
            displayNode.SetEdgeVisibility(not displayNode.GetEdgeVisibility())

    def onToggleClipping(self) -> None:
        """Cut the volume mesh open, and once it is cut, turn the cutting off and on.

        The first press has to make the thing that does the cutting, and where to put it is a
        guess; every press after that is about a box the user has since moved to where they
        wanted it, so it turns the clipping off rather than putting the box back.
        """
        displayNode = self.displayNodeOf("outputMesh")
        if not displayNode:
            return
        if displayNode.GetClipNode():
            displayNode.SetClipping(not displayNode.GetClipping())
            return
        self.logic.clipWithABoxThroughTheMiddle(self._parameterNode.outputMesh)

    def _followInputSurface(self) -> None:
        """Take what the outputs are called, and the array the faces are told apart by, from the
        surface that was picked.

        The array matters more than it looks: it is what holds the wall and the caps apart while
        the surface is remeshed, and a surface that arrives already labelled - as one from Clip
        Vessel does, under "ModelFaceID" - carries its labels under a name of its own. Left
        pointing at a name the input does not use, the pipeline would renumber every cell of it
        into one face and the remesher would then be free to smooth the rim between a cap and the
        wall away, so the name is taken from the input rather than waited for.
        """
        surfaceNode = self._parameterNode.inputSurface if self._parameterNode else None
        surfaceNodeId = surfaceNode.GetID() if surfaceNode else None
        justPicked = surfaceNodeId != self._followedInputSurfaceId
        if justPicked:
            self._followedInputSurfaceId = surfaceNodeId
            # A node is often picked before it holds anything - the module picks the first model
            # in the scene when it opens, and a surface is written into a node that was made for
            # it - and there is nothing to read the name of a face ids array from until it does.
            if self._observedInputSurfaceNode:
                self.removeObserver(self._observedInputSurfaceNode,
                                    vtkMRMLModelNode.MeshModifiedEvent, self._onParameterNodeModified)
            self._observedInputSurfaceNode = surfaceNode
            if surfaceNode:
                self.addObserver(surfaceNode, vtkMRMLModelNode.MeshModifiedEvent,
                                 self._onParameterNodeModified)

        if not surfaceNode:
            return

        if justPicked:
            # The name a new output node gets when one is created from the selector.
            self.ui.outputMeshSelector.baseName = _("{name} volumetric").format(
                name=surfaceNode.GetName())
            self.ui.outputRemeshedSurfaceSelector.baseName = _("{name} remeshed").format(
                name=surfaceNode.GetName())

        surface = surfaceNode.GetPolyData()
        if surface is None or surface.GetCellData().GetArray(
                self._parameterNode.cellEntityIdsArrayName) is not None:
            return
        candidates = self.faceIdsArrayNames(surface)
        if len(candidates) == 1:
            logging.info("Reading the faces of %s from its %s array.",
                         surfaceNode.GetName(), candidates[0])
            self._parameterNode.cellEntityIdsArrayName = candidates[0]
        elif candidates and justPicked:
            logging.warning("%s carries more than one array its faces could be read from (%s); "
                            "leaving the face ids array name as it is.",
                            surfaceNode.GetName(), ", ".join(candidates))

    @staticmethod
    def faceIdsArrayNames(surface):
        """The names of the cell arrays the surface could be labelling its faces by: one integer
        per cell, which is what a face id is."""
        integerTypes = (vtk.VTK_ID_TYPE, vtk.VTK_INT, vtk.VTK_UNSIGNED_INT, vtk.VTK_SHORT,
                        vtk.VTK_UNSIGNED_SHORT, vtk.VTK_LONG, vtk.VTK_UNSIGNED_LONG,
                        vtk.VTK_LONG_LONG, vtk.VTK_UNSIGNED_LONG_LONG, vtk.VTK_CHAR,
                        vtk.VTK_SIGNED_CHAR, vtk.VTK_UNSIGNED_CHAR)
        cellData = surface.GetCellData()
        arrays = [cellData.GetArray(index) for index in range(cellData.GetNumberOfArrays())]
        return [array.GetName() for array in arrays
                if array.GetName() and array.GetNumberOfComponents() == 1
                and array.GetDataType() in integerTypes]

    def _updateApplyButton(self) -> None:
        if self._parameterNode and self._parameterNode.inputSurface and self._parameterNode.outputMesh:
            self.ui.applyButton.toolTip = _("Generate the volume mesh")
            self.ui.applyButton.enabled = True
        else:
            self.ui.applyButton.toolTip = _("Select an input surface and an output mesh node")
            self.ui.applyButton.enabled = False

    def _updateMesherChoices(self) -> None:
        """Offer a mesher only where it can be run.

        TetGen's licence makes building it a decision, and an installation built without it has
        no TetGen to offer; saying so in the list it would have been chosen from is more use than
        letting it be chosen and refusing afterwards.
        """
        available = self.logic.availableMeshers()
        for index, mesher in enumerate(Mesher):
            if mesher in available:
                continue
            # The role a combo box keeps an item's flags under. Cleared, the item is shown but
            # cannot be picked.
            self.ui.mesherComboBox.setItemData(index, 0, qt.Qt.UserRole - 1)
            self.ui.mesherComboBox.setItemData(
                index, _("This installation was built without it"), qt.Qt.ToolTipRole)
        if self._parameterNode and self._parameterNode.mesher not in available and available:
            self._parameterNode.mesher = available[0]

    def _updateEnabledStates(self) -> None:
        """Grey out the parameters that the current choices leave without an effect."""
        if not self._parameterNode:
            return

        # What only fTetWild reads: TetGen keeps the surface it is given rather than staying
        # within a tolerance of it, and stops when its own quality bounds are met.
        usingFTetWild = self._parameterNode.mesher == Mesher.FTETWILD
        for widget in (self.ui.surfaceToleranceLabel, self.ui.surfaceToleranceSpinBox,
                       self.ui.stopEnergyLabel, self.ui.stopEnergySpinBox,
                       self.ui.maxOptimizationPassesLabel, self.ui.maxOptimizationPassesSpinBox,
                       self.ui.coarsenLabel, self.ui.coarsenCheckBox):
            widget.enabled = usingFTetWild

        # A constant edge length is one number, so neither the array nor its factor is read.
        fromArray = self._parameterNode.elementSizeMode == ElementSizeMode.EDGE_LENGTH_ARRAY
        self.ui.targetEdgeLengthArrayNameLabel.enabled = fromArray
        self.ui.targetEdgeLengthArrayNameLineEdit.enabled = fromArray
        self.ui.targetEdgeLengthFactorLabel.enabled = fromArray
        self.ui.targetEdgeLengthFactorSpinBox.enabled = fromArray

        remeshing = self._parameterNode.remeshSurface
        self.ui.remeshWallLabel.enabled = remeshing
        self.ui.remeshWallCheckBox.enabled = remeshing

        capping = self._parameterNode.capSurface
        self.ui.cappingMethodLabel.enabled = capping
        self.ui.cappingMethodComboBox.enabled = capping

        boundaryLayer = self._parameterNode.boundaryLayer
        for widget in (self.ui.boundaryLayerOnCapsLabel, self.ui.boundaryLayerOnCapsCheckBox,
                       self.ui.numberOfSubLayersLabel, self.ui.numberOfSubLayersSpinBox,
                       self.ui.subLayerRatioLabel, self.ui.subLayerRatioSpinBox,
                       self.ui.boundaryLayerThicknessFactorLabel, self.ui.boundaryLayerThicknessFactorSpinBox,
                       self.ui.numberOfSubstepsLabel, self.ui.numberOfSubstepsSpinBox,
                       self.ui.relaxationLabel, self.ui.relaxationSpinBox,
                       self.ui.localCorrectionFactorLabel, self.ui.localCorrectionFactorSpinBox):
            widget.enabled = boundaryLayer
        # The caps are only remeshed on their own when the boundary layer stops short of them.
        endcaps = boundaryLayer and not self._parameterNode.boundaryLayerOnCaps
        self.ui.endcapsEdgeLengthFactorLabel.enabled = endcaps
        self.ui.endcapsEdgeLengthFactorSpinBox.enabled = endcaps

    def onApplyButton(self) -> None:
        """Run processing when user clicks "Apply" button."""
        # Once more before running: a node is often picked before it holds a surface, and until it
        # does there is nothing to read the name of its face ids array from.
        self._followInputSurface()
        if self._parameterNode.mesher == Mesher.FTETWILD and not self.logic.isFTetWildAvailable():
            if not self.offerToInstallFTetWild():
                return
        try:
            with slicer.util.tryWithErrorDisplay(_("Failed to generate the mesh."), waitCursor=True):
                self.logic.process(self._parameterNode)
        finally:
            # The outputs have their display nodes now, so their buttons have something to act on.
            # In a finally, because a run that stopped half way still wrote what it had.
            self._updateVisibilityButtons()

    def offerToInstallFTetWild(self) -> bool:
        """Ask to download fTetWild, and say whether it can be used afterwards.

        Asking rather than simply doing it: this reaches out to the network and installs software
        into the application, which is not something a press of Apply should be taken to mean.
        """
        if not slicer.util.confirmOkCancelDisplay(_(
                "fTetWild is not installed. It comes as the Python package {requirement}, under "
                "the Mozilla Public License 2.0, which can be downloaded and installed now. This "
                "needs an internet connection and takes a moment; it is only done once."
        ).format(requirement=FTETWILD_REQUIREMENT)):
            return False
        with slicer.util.tryWithErrorDisplay(_("Failed to install fTetWild."), waitCursor=True):
            slicer.util.pip_install(FTETWILD_REQUIREMENT)
        return self.logic.isFTetWildAvailable()


#
# CfdMeshGeneratorLogic
#


class CfdMeshGeneratorLogic(ScriptedLoadableModuleLogic):
    """The meshing pipeline, with no GUI of its own, so that it can be scripted.

    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
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
        ScriptedLoadableModuleLogic.__init__(self)
        # Whether the last run ended with the mesher refusing to fill the surface it was given.
        # The mesh is handed back anyway - what there is of it is the thing to look at to see why
        # - so this is what says the result is not a finished mesh (see process).
        self.lastTetrahedralizationFailed = False
        # The step log() is currently announcing, and when it started, so that the next call - or
        # the end of the run - can say how long it took. None between runs and once the last step
        # of one has been reported.
        self._stepName = None
        self._stepStartTime = None

    #
    # Which meshers this installation can offer.
    #

    @staticmethod
    def isTetGenAvailable():
        """Whether VMTK was built with TetGen. Its licence makes that a decision, so a build
        that was made without it has no wrapper class at all rather than one that refuses."""
        import vtkvmtkMiscPython as vtkvmtkMisc

        return hasattr(vtkvmtkMisc, "vtkvmtkTetGenWrapper")

    @staticmethod
    def importPyTetWild():
        """The pytetwild module, which is fTetWild. Raises RuntimeError if it is not installed.

        The import is worth a wrapper of its own because pytetwild 0.4.2 imports pyvista at the
        top of its package - for an accessor it registers on pyvista's own classes - without
        guarding it, so importing pytetwild alone fails on an installation that has no pyvista.
        Installing pyvista to answer that would bring a second VTK into a process that already
        has one, which is a worse thing to be wrong about than a missing accessor, so an empty
        module stands in its place for the length of the import and is taken out again after.
        """
        stub = "pyvista" not in sys.modules
        if stub:
            sys.modules["pyvista"] = types.ModuleType("pyvista")
        try:
            return importlib.import_module("pytetwild")
        except ImportError as error:
            # A failed import can leave the half-built package behind, and a later import would
            # then hand back what it got to instead of trying again.
            for name in [name for name in sys.modules if name.split(".")[0] == "pytetwild"]:
                del sys.modules[name]
            raise RuntimeError(_(
                "fTetWild is not installed. It comes as the Python package {requirement}, which "
                "the module offers to download when fTetWild is chosen and Apply is pressed."
            ).format(requirement=FTETWILD_REQUIREMENT)) from error
        finally:
            if stub:
                del sys.modules["pyvista"]

    @classmethod
    def isFTetWildAvailable(cls):
        """Whether fTetWild can be used right now. It is imported rather than looked for: a
        package that is installed but cannot be imported is not one to offer."""
        try:
            cls.importPyTetWild()
        except RuntimeError:
            return False
        return True

    @classmethod
    def availableMeshers(cls):
        """The meshers this installation can offer, in the order they are presented."""
        return [mesher for mesher in Mesher
                if mesher != Mesher.TETGEN or cls.isTetGenAvailable()]

    def getParameterNode(self):
        return CfdMeshGeneratorParameterNode(super().getParameterNode())

    def process(self, parameters: CfdMeshGeneratorParameterNode) -> None:
        """Mesh the input surface of the given parameter node into its output nodes."""
        if not parameters.inputSurface:
            raise ValueError(_("No input surface"))
        if not parameters.inputSurface.GetPolyData():
            raise ValueError(_("The input model holds no surface. A model holding a volume mesh "
                               "is already meshed; this module takes the surface that bounds one."))
        if not parameters.outputMesh:
            raise ValueError(_("No output mesh node"))

        startTime = time.time()

        mesh, remeshedSurface = self.generateMesh(
            parameters.inputSurface.GetPolyData(),
            targetEdgeLength=parameters.targetEdgeLength,
            targetEdgeLengthArrayName=parameters.targetEdgeLengthArrayName,
            targetEdgeLengthFactor=parameters.targetEdgeLengthFactor,
            triangleSplitFactor=parameters.triangleSplitFactor,
            endcapsEdgeLengthFactor=parameters.endcapsEdgeLengthFactor,
            maxEdgeLength=parameters.maxEdgeLength,
            minEdgeLength=parameters.minEdgeLength,
            cellEntityIdsArrayName=parameters.cellEntityIdsArrayName,
            boundaryLabelsArrayName=parameters.boundaryLabelsArrayName,
            boundaryPointOrderArrayName=parameters.boundaryPointOrderArrayName,
            elementSizeMode=parameters.elementSizeMode.value,
            cappingMethod=parameters.cappingMethod.value,
            skipCapping=not parameters.capSurface,
            skipRemeshing=not parameters.remeshSurface,
            remeshCapsOnly=not parameters.remeshWall,
            mesher=parameters.mesher.value,
            volumeElementScaleFactor=parameters.volumeElementScaleFactor,
            surfaceTolerance=parameters.surfaceTolerance,
            stopEnergy=parameters.stopEnergy,
            maxOptimizationPasses=parameters.maxOptimizationPasses,
            coarsen=parameters.coarsen,
            boundaryLayer=parameters.boundaryLayer,
            boundaryLayerOnCaps=parameters.boundaryLayerOnCaps,
            numberOfSubLayers=parameters.numberOfSubLayers,
            subLayerRatio=parameters.subLayerRatio,
            boundaryLayerThicknessFactor=parameters.boundaryLayerThicknessFactor,
            numberOfSubsteps=parameters.numberOfSubsteps,
            relaxation=parameters.relaxation,
            localCorrectionFactor=parameters.localCorrectionFactor,
            tetrahedralize=parameters.tetrahedralize)

        parameters.outputMesh.SetAndObserveMesh(mesh)
        self.showMeshInScene(parameters.outputMesh, parameters.cellEntityIdsArrayName)
        if parameters.outputRemeshedSurface:
            parameters.outputRemeshedSurface.SetAndObserveMesh(remeshedSurface)
            self.showMeshInScene(parameters.outputRemeshedSurface, parameters.cellEntityIdsArrayName)

        logging.info("Meshing completed in %.2f seconds: %d cells, %d points",
                     time.time() - startTime, mesh.GetNumberOfCells(), mesh.GetNumberOfPoints())

        # Said out loud rather than left in the log: what comes back is a hollow shell that looks
        # like a mesh until it is opened, and a solver would not accept it.
        if self.lastTetrahedralizationFailed:
            mesherName = parameters.mesher.label()
            if parameters.boundaryLayer:
                raise RuntimeError(_(
                    "{mesher} could not fill the space left inside the boundary layer, so the "
                    "output holds the layer and the surface but no tetrahedra. The layer has "
                    "most likely folded over itself, which it does first where a cap meets the "
                    "wall at a corner: turn \"Layer on caps\" off, make the layer thinner, or "
                    "give it more substeps to settle over.").format(mesher=mesherName))
            raise RuntimeError(_(
                "{mesher} could not fill the surface with tetrahedra, so the output holds only "
                "the surface. The surface it was given is not one it can fill: check that the "
                "input is closed and does not cross itself.").format(mesher=mesherName))

    def generateMesh(self, surface, *,
                     targetEdgeLength=1.0,
                     targetEdgeLengthArrayName="",
                     targetEdgeLengthFactor=1.0,
                     triangleSplitFactor=5.0,
                     endcapsEdgeLengthFactor=1.0,
                     maxEdgeLength=0.0,
                     minEdgeLength=0.0,
                     cellEntityIdsArrayName="CellEntityIds",
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
                     boundaryLayer=False,
                     boundaryLayerOnCaps=True,
                     numberOfSubLayers=2,
                     subLayerRatio=0.5,
                     boundaryLayerThicknessFactor=0.25,
                     numberOfSubsteps=2000,
                     relaxation=0.01,
                     localCorrectionFactor=0.45,
                     tetrahedralize=False):
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
        :param mesher: which mesher fills the surface, "tetgen" or "ftetwild"; see Mesher.
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
                                 "makes a decision rather than a default. Choose fTetWild."))
        if mesher == Mesher.FTETWILD.value:
            self.importPyTetWild()

        boundaryLabelsArrayName = boundaryLabelsArrayName or self.boundaryLabelsArrayName
        boundaryPointOrderArrayName = (boundaryPointOrderArrayName
                                       or self.boundaryPointOrderArrayName)

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
            self.log(_("Not capping surface"))
            cappedSurface = self.withCellEntityIds(surface, cellEntityIdsArrayName)
            if layerOffTheCaps:
                # A surface that arrived capped - one from Clip Vessel has been closed already -
                # is opened again here. Not capping it is not enough to keep the layer off its
                # caps when the caps are already part of it: the sweep would run straight over
                # them, whatever the setting says.
                cappedSurface, capsTakenOff = self.openCappedEnds(
                    cappedSurface, cellEntityIdsArrayName,
                    boundaryLabelsArrayName=boundaryLabelsArrayName)
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
                excludedEntityIds=[self.wallCellEntityId] if remeshCapsOnly else [])

        # A size per point, where the surface was meshed to one and the mesher can read one. The
        # remesher was given the same array to size its triangles by, so the volume elements come
        # out graded the way the surface is. TetGen is not offered it: the switch that reads a
        # size per point answers differently each run (see runTetGen), so it is sized by one
        # number throughout, as it was before either mesher was a choice.
        sizingField = None
        if (mesher == Mesher.FTETWILD.value
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
            coarsen=coarsen)

        if not boundaryLayer:
            mesh = self.fillWithTetrahedra(remeshedSurface, cellEntityIdsArrayName,
                                           volumeMeshing, outputSurfaceElements=True)
        else:
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
                capsTakenOff=capsTakenOff,
                boundaryLabelsArrayName=boundaryLabelsArrayName,
                boundaryPointOrderArrayName=boundaryPointOrderArrayName)

        if tetrahedralize:
            self.log(_("Tetrahedralizing"))
            tetrahedralizeFilter = vtkvmtkMisc.vtkvmtkUnstructuredGridTetraFilter()
            tetrahedralizeFilter.SetInputData(mesh)
            tetrahedralizeFilter.Update()
            mesh = tetrahedralizeFilter.GetOutput()

        self._finishStepLog()
        return mesh, remeshedSurface

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

        A cap is a face numbered above the wall, which is how this module numbers the caps it
        makes and how Clip Vessel numbers the ones it makes. A surface that carries none - one
        whose ends are still open, which is what vmtkmeshgenerator expects to be given - comes
        back untouched.

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
            if entityId <= self.wallCellEntityId:
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
        threshold = vtk.vtkThreshold()
        threshold.SetInputData(surface)
        threshold.SetInputArrayToProcess(0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_CELLS,
                                         cellEntityIdsArrayName)
        threshold.SetThresholdFunction(vtk.vtkThreshold.THRESHOLD_LOWER)
        threshold.SetLowerThreshold(self.wallCellEntityId + 0.5)
        threshold.Update()
        geometryFilter = vtk.vtkGeometryFilter()
        geometryFilter.SetInputData(threshold.GetOutput())
        geometryFilter.Update()
        opened = self.cleanSurface(geometryFilter.GetOutput())

        # Numbering the wall 1 and the caps above it is this module's convention and Clip Vessel's,
        # but the ids on a surface from somewhere else mean whatever that somewhere else meant by
        # them, and cutting the wrong faces out of a vessel wall is not a small mistake. What the
        # faces were taken to be is therefore checked against what taking them off did: lifting a
        # cap off leaves exactly one hole where it was.
        holes = self.numberOfOpenBoundaries(opened)
        if holes != len(capsTakenOff):
            logging.warning(
                "The faces numbered above %d are not the caps of this surface - taking them off "
                "left %d hole(s) where %d were expected - so it is meshed as it arrived, with the "
                "boundary layer grown over them.",
                self.wallCellEntityId, holes, len(capsTakenOff))
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
            sweptSurface = self.meshToSurface(self.cellsWithEntityId(
                innerBoundary, cellEntityIdsArrayName, self.wallCellEntityId, keepAbove=False))
            caps = self.cellsWithEntityId(
                innerBoundary, cellEntityIdsArrayName, self.wallCellEntityId, keepAbove=True)

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

    @staticmethod
    def cellsWithEntityId(mesh, cellEntityIdsArrayName, entityId, keepAbove):
        """The cells of the mesh whose face id is above the given one, or at most it."""
        threshold = vtk.vtkThreshold()
        threshold.SetInputData(mesh)
        threshold.SetInputArrayToProcess(0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_CELLS,
                                         cellEntityIdsArrayName)
        if keepAbove:
            threshold.SetThresholdFunction(vtk.vtkThreshold.THRESHOLD_UPPER)
            threshold.SetUpperThreshold(entityId + 0.5)
        else:
            threshold.SetThresholdFunction(vtk.vtkThreshold.THRESHOLD_LOWER)
            threshold.SetLowerThreshold(entityId + 0.5)
        threshold.Update()
        return threshold.GetOutput()

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
                              boundaryPointOrderArrayName=None):
        """The surface lined on the inside with layers of prisms, and everything those leave free
        filled with tetrahedra.

        The prisms are made by sweeping the surface inwards along its own normals; what is still
        empty inside is meshed against the innermost swept surface, and the two are put back
        together at the end.
        """
        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
        import vtkvmtkMiscPython as vtkvmtkMisc

        # The remesher keeps no point data, so the array the layer thickness is read from is
        # carried back onto the remeshed surface from the surface it was given on.
        projection = vtkvmtkMisc.vtkvmtkSurfaceProjection()
        projection.SetInputData(remeshedSurface)
        projection.SetReferenceSurface(referenceSurface)
        projection.Update()

        outerSurfaceMesh = self.surfaceToMesh(self.surfaceNormals(projection.GetOutput()))

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
                excludedEntityIds=[self.wallCellEntityId])

        innerSurfaceMesh = self.surfaceToMesh(innerSurface)

        # A mesher that keeps the surface it is given needs nothing back from the space it filled
        # but the tetrahedra: the face against the boundary layer is one the layer already
        # carries. A mesher that answers with a boundary of its own is asked for that boundary,
        # because the layer is then grown from it rather than the other way about.
        keepsTheSurface = volumeMeshing.mesher == Mesher.TETGEN.value
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
                # The outer surface was never capped, so every one of its cells is wall.
                outerSurfaceMesh.GetCellData().GetArray(cellEntityIdsArrayName).FillComponent(
                    0, self.wallCellEntityId)
            appendFilter.AddInputData(outerSurfaceMesh)
            appendFilter.AddInputData(boundaryLayerGenerator.GetOutput())
            appendFilter.AddInputData(filled)
            if not boundaryLayerOnCaps:
                # The caps were made on the inner surface, past the boundary layer, so they are
                # taken from there: everything the capper numbered above the wall.
                appendFilter.AddInputData(self.cellsWithEntityId(
                    innerSurfaceMesh, cellEntityIdsArrayName, self.wallCellEntityId,
                    keepAbove=True))
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

        Both meshers answer the same way: the tetrahedra first, under entity id 0, and then -
        when asked for - the triangles bounding them, each under the id of the face of the input
        it stands on. What differs is everything behind that; see runTetGen and runFTetWild.
        """
        self.log(_("Generating volume mesh ({mesher})").format(
            mesher=Mesher(volumeMeshing.mesher).label()))
        if volumeMeshing.mesher == Mesher.TETGEN.value:
            return self.runTetGen(
                surfaceMesh, cellEntityIdsArrayName, outputSurfaceElements,
                maxElementVolume=self.maximumElementVolume(volumeMeshing.edgeLength))
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

        pytetwild = self.importPyTetWild()

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
            meshPoints, tetrahedra = pytetwild.tetrahedralize(vertices, faces, **arguments)
        except Exception:
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
            np.concatenate([np.zeros(len(tetrahedra), dtype=np.int32), boundaryIds]),
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
            cellEntityId = cellEntityIdsArray.GetTuple1(cellId)
            if cellEntityId in (0, self.wallCellEntityId, self.placeholderCellEntityId):
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

    @staticmethod
    def triangulate(surface):
        """The surface with every cell split into triangles."""
        triangleFilter = vtk.vtkTriangleFilter()
        triangleFilter.SetInputData(surface)
        triangleFilter.PassLinesOff()
        triangleFilter.PassVertsOff()
        triangleFilter.Update()
        return triangleFilter.GetOutput()

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

        Each step takes long enough to be worth reporting on its own - the status bar is the only
        sign of progress a long meshing run gives - and logging its duration once it is known,
        rather than at the moment it is measured, is what keeps one line per step instead of two.
        The last step of a run is timed too; see _finishStepLog.
        """
        self._finishStepLog()
        self._stepName = message
        self._stepStartTime = time.time()
        logging.info(message)
        slicer.util.showStatusMessage(message)
        slicer.app.processEvents()

    def _finishStepLog(self):
        """Log how long the step log() last announced took, if one is still open."""
        if self._stepName is not None:
            logging.info("%s: %.2fs", self._stepName, time.time() - self._stepStartTime)
            self._stepName = None
            self._stepStartTime = None

    # Marks a node this module has already given a display to, so that a second Apply writes the
    # new mesh into the node it was given and leaves everything else as the user has since set it.
    def clipWithABoxThroughTheMiddle(self, modelNode):
        """Clip the model to a box laid over the middle of it, and show the box.

        The box is the model's own bounding box, halved along the model's shortest side: a slab
        through the middle of a vessel mesh, which is what shows the elements inside it. It is a
        starting point rather than an answer - it is left visible, and thinly filled, so that it
        can be taken hold of and moved to wherever the cut is wanted.

        Whole elements are kept: an element the box crosses is either in or out, never cut
        through. A mesh sliced through its elements shows faces that are not element faces, and
        the reason for looking inside is to see the elements as they are.

        :return: the clip node now driving the model's display.
        """
        if not modelNode.GetDisplayNode():
            modelNode.CreateDefaultDisplayNodes()
        displayNode = modelNode.GetDisplayNode()
        if not displayNode:
            return None

        bounds = [0.0] * 6
        modelNode.GetRASBounds(bounds)
        size = [bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4]]
        center = [(bounds[0] + bounds[1]) / 2.0, (bounds[2] + bounds[3]) / 2.0,
                  (bounds[4] + bounds[5]) / 2.0]
        size[size.index(min(size))] *= 0.5

        roiNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsROINode", _("{name} clip box").format(name=modelNode.GetName()))
        roiNode.SetCenter(center)
        roiNode.SetSize(size)
        roiNode.CreateDefaultDisplayNodes()
        roiDisplayNode = roiNode.GetDisplayNode()
        if roiDisplayNode:
            # Enough fill to see which way round the box lies, little enough to see the mesh
            # through it.
            roiDisplayNode.SetFillVisibility(True)
            roiDisplayNode.SetFillOpacity(0.05)
            roiDisplayNode.SetVisibility(True)

        clipNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLClipNode", _("{name} clip").format(name=modelNode.GetName()))
        clipNode.SetClippingMethod(slicer.vtkMRMLClipNode.WholeCells)
        clipNode.AddAndObserveClippingNodeID(roiNode.GetID())
        clipNode.SetClippingNodeState(roiNode, slicer.vtkMRMLClipNode.ClipNegativeSpace)

        displayNode.SetAndObserveClipNodeID(clipNode.GetID())
        displayNode.SetClipping(True)
        return clipNode

    displaySetUpAttributeName = "CfdMeshGenerator.DisplaySetUp"

    def showMeshInScene(self, modelNode, cellEntityIdsArrayName):
        """Show the mesh, coloured by the face each of its cells belongs to.

        Once per node: a node that has been shown before carries whatever has been made of it
        since - a colour, a scalar array, its visibility, an opacity chosen to see inside it - and
        rerunning Apply to try another edge length is no reason to undo any of that.
        """
        if modelNode.GetAttribute(self.displaySetUpAttributeName) == "true":
            return
        modelNode.SetAttribute(self.displaySetUpAttributeName, "true")

        if not modelNode.GetDisplayNode():
            modelNode.CreateDefaultDisplayNodes()
        displayNode = modelNode.GetDisplayNode()
        if not displayNode:
            return
        mesh = modelNode.GetMesh()
        if mesh and mesh.GetCellData().GetArray(cellEntityIdsArrayName):
            displayNode.SetActiveScalar(cellEntityIdsArrayName, vtk.vtkAssignAttribute.CELL_DATA)
            # Over the ids the mesh actually carries, and through a table that is opaque
            # throughout. A discrete label table would read the ids as the label numbers they are,
            # but the entry it gives label 0 is transparent - and 0 is what every cell of a mesh
            # whose faces were never told apart carries, so the whole thing would come up
            # invisible, which is no way to hand back an hour of meshing.
            displayNode.SetAndObserveColorNodeID("vtkMRMLColorTableNodeRainbow")
            displayNode.SetScalarRangeFlag(slicer.vtkMRMLDisplayNode.UseDataScalarRange)
            displayNode.SetScalarVisibility(True)
        else:
            displayNode.SetScalarVisibility(False)
        displayNode.SetVisibility(True)


#
# CfdMeshGeneratorTest
#


class CfdMeshGeneratorTest(ScriptedLoadableModuleTest):
    """Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """Do whatever is needed to reset the state - typically a scene clear will be enough."""
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here."""
        self.setUp()
        for test in (self.test_CfdMeshGenerator1,
                     self.test_CfdMeshGeneratorWithoutRemeshing,
                     self.test_CfdMeshGeneratorRemeshingTheCapsAlone,
                     self.test_CfdMeshGeneratorBoundaryLayer,
                     self.test_CfdMeshGeneratorFoldedBoundaryLayer,
                     self.test_CfdMeshGeneratorKeepsTheLabelsOfTheInput,
                     self.test_CfdMeshGeneratorLayerOffImportedCaps,
                     self.test_CfdMeshGeneratorNamesCapsAfterVesselEnds,
                     self.test_CfdMeshGeneratorClipping,
                     self.test_CfdMeshGeneratorReapplyLeavesTheDisplayAlone,
                     self.test_CfdMeshGeneratorFTetWildSizesByPosition,
                     self.test_CfdMeshGeneratorFTetWildIsAskedForBeforeItIsUsed):
            try:
                test()
            except unittest.SkipTest as reason:
                # Reload and Test calls this rather than the unittest runner, and a skip raised
                # here would look like a failed run rather than a test that had nothing to do.
                self.delayDisplay("Skipped %s: %s" % (test.__name__, reason))

    @staticmethod
    def meshers():
        """The meshers to put each behaviour to, which is every one this installation has.

        fTetWild is installed if it is missing, so that a machine with a network connection tests
        both; one without tests what it has, which is the same choice a user has there.
        """
        logic = CfdMeshGeneratorLogic()
        found = []
        if logic.isTetGenAvailable():
            found.append(Mesher.TETGEN.value)
        if logic.isFTetWildAvailable():
            found.append(Mesher.FTETWILD.value)
        else:
            try:
                slicer.util.pip_install(FTETWILD_REQUIREMENT)
            except Exception:
                logging.warning("fTetWild could not be installed, so it is left untested.")
            else:
                if logic.isFTetWildAvailable():
                    found.append(Mesher.FTETWILD.value)
        return found

    def requireFTetWild(self):
        """Skip the test that called this if fTetWild is not to be had."""
        if Mesher.FTETWILD.value not in self.meshers():
            self.skipTest("fTetWild is not installed and could not be installed")

    @staticmethod
    def fasterFTetWild(mesher):
        """The arguments that keep an fTetWild run in a test suite short. Its default is eighty
        passes of improvement, which is more than a tube of two thousand elements needs."""
        if mesher != Mesher.FTETWILD.value:
            return {}
        return dict(maxOptimizationPasses=20)

    @staticmethod
    def openTube(numberOfAxialPoints=12, numberOfCircumferentialPoints=24, height=10.0, radius=1.0):
        """A tube open at both ends, standing in for a clipped vessel."""
        import math
        points, polys = vtk.vtkPoints(), vtk.vtkCellArray()
        for axialIndex in range(numberOfAxialPoints):
            z = height * axialIndex / (numberOfAxialPoints - 1)
            for circumferentialIndex in range(numberOfCircumferentialPoints):
                angle = 2.0 * math.pi * circumferentialIndex / numberOfCircumferentialPoints
                points.InsertNextPoint(radius * math.cos(angle), radius * math.sin(angle), z)
        for axialIndex in range(numberOfAxialPoints - 1):
            for circumferentialIndex in range(numberOfCircumferentialPoints):
                nextIndex = (circumferentialIndex + 1) % numberOfCircumferentialPoints
                first = axialIndex * numberOfCircumferentialPoints + circumferentialIndex
                second = axialIndex * numberOfCircumferentialPoints + nextIndex
                third = (axialIndex + 1) * numberOfCircumferentialPoints + circumferentialIndex
                fourth = (axialIndex + 1) * numberOfCircumferentialPoints + nextIndex
                polys.InsertNextCell(3, [first, second, fourth])
                polys.InsertNextCell(3, [first, fourth, third])
        surface = vtk.vtkPolyData()
        surface.SetPoints(points)
        surface.SetPolys(polys)
        return surface

    @staticmethod
    def cellEntityIds(mesh, arrayName="CellEntityIds"):
        array = mesh.GetCellData().GetArray(arrayName)
        if array is None:
            return set()
        return set(int(array.GetTuple1(index)) for index in range(array.GetNumberOfTuples()))

    @staticmethod
    def surfaceAreaOfCells(mesh, keep):
        """The total area of the cells of the mesh that keep(cellId) says to count."""
        total = 0.0
        for cellId in range(mesh.GetNumberOfCells()):
            if not keep(cellId):
                continue
            cell = mesh.GetCell(cellId)
            if cell.GetCellDimension() != 2:
                continue
            points = [cell.GetPoints().GetPoint(index) for index in range(cell.GetNumberOfPoints())]
            # Fan the polygon about its first corner. Every 2D cell here is a triangle or a
            # planar quad, so the fan covers it exactly.
            for index in range(1, len(points) - 1):
                total += vtk.vtkTriangle.TriangleArea(points[0], points[index], points[index + 1])
        return total

    def assertTetrahedraArePositive(self, mesh, message=""):
        """Every volume element must be wound the way VTK winds one.

        A solver handed an element that is inside out reads a negative volume for it, and the
        mesh it computes on is not the mesh it was shown. It is worth asking wherever a sweep or
        a mesher decides the order of an element's corners for itself.
        """
        inverted = 0
        for cellId in range(mesh.GetNumberOfCells()):
            cell = mesh.GetCell(cellId)
            if cell.GetCellDimension() != 3:
                continue
            points = [mesh.GetPoint(cell.GetPointId(index))
                      for index in range(cell.GetNumberOfPoints())]
            if cell.GetCellType() == vtk.VTK_TETRA:
                if vtk.vtkTetra.ComputeVolume(*points[:4]) <= 0.0:
                    inverted += 1
            elif cell.GetCellType() == vtk.VTK_WEDGE:
                # The base triangle's normal has to point away from the face opposite it.
                normal = [0.0, 0.0, 0.0]
                vtk.vtkTriangle.ComputeNormal(points[0], points[1], points[2], normal)
                base = [sum(point[axis] for point in points[:3]) / 3.0 for axis in range(3)]
                top = [sum(point[axis] for point in points[3:]) / 3.0 for axis in range(3)]
                if sum(normal[axis] * (top[axis] - base[axis]) for axis in range(3)) > 0.0:
                    inverted += 1
        self.assertEqual(inverted, 0,
                         "%d volume elements are inside out %s" % (inverted, message))

    def assertBoundaryIsLabelled(self, mesh, arrayName, message=""):
        """Every face on the outside of the volume must be a labelled cell of the mesh.

        A boundary condition is assigned per face id, so a solver reading this mesh has to find
        one on every face it can reach from the outside. Areas rather than cells, because the
        volume elements and the surface cells that stand against them need not be split the same
        way: what has to match is the surface they cover.
        """
        volume = vtk.vtkExtractCellsByType()
        volume.SetInputData(mesh)
        for cellType in (vtk.VTK_TETRA, vtk.VTK_WEDGE, vtk.VTK_HEXAHEDRON,
                         vtk.VTK_QUADRATIC_TETRA, vtk.VTK_QUADRATIC_WEDGE):
            volume.AddCellType(cellType)
        volume.Update()
        outside = vtk.vtkGeometryFilter()
        outside.SetInputData(volume.GetOutput())
        outside.MergingOff()
        outside.Update()

        outsideArea = self.surfaceAreaOfCells(outside.GetOutput(), lambda cellId: True)
        ids = mesh.GetCellData().GetArray(arrayName)
        labelledArea = self.surfaceAreaOfCells(
            mesh, lambda cellId: ids is not None and int(ids.GetTuple1(cellId)) >= 1)
        self.assertGreater(outsideArea, 0.0, "the mesh has no volume elements %s" % message)
        self.assertAlmostEqual(
            labelledArea / outsideArea, 1.0, delta=0.01,
            msg="the labelled faces cover %.1f%% of the outside of the volume %s"
                % (100.0 * labelledArea / outsideArea, message))

    def test_CfdMeshGenerator1(self):
        """An open tube must come back as a volume mesh: capped, filled with tetrahedra, and with
        the wall and each of the two caps under an id of its own, so that a boundary condition can
        be assigned to each of them."""
        self.delayDisplay("Starting the test")

        logic = CfdMeshGeneratorLogic()
        for mesher in self.meshers():
            mesh, remeshedSurface = logic.generateMesh(
                self.openTube(), targetEdgeLength=0.4, mesher=mesher,
                **self.fasterFTetWild(mesher))

            self.assertGreater(remeshedSurface.GetNumberOfCells(), 0)
            cellTypes = vtk.vtkCellTypes()
            mesh.GetCellTypes(cellTypes)
            self.assertTrue(cellTypes.IsType(vtk.VTK_TETRA),
                            "the mesh holds no tetrahedra (%s)" % mesher)
            # 0 for the tetrahedra, 1 for the wall, and one id per cap above it.
            self.assertEqual(self.cellEntityIds(mesh), {0, 1, 2, 3}, mesher)
            self.assertBoundaryIsLabelled(mesh, "CellEntityIds", "(%s)" % mesher)
            self.assertTetrahedraArePositive(mesh, mesher)

        self.delayDisplay("Test passed")

    def test_CfdMeshGeneratorWithoutRemeshing(self):
        """A surface asked to be filled as it arrived still has to be filled.

        Remeshing is what used to triangulate the surface on its way past, and a cap is one
        polygon until something does: the sizing function has nothing to say about a cell that is
        not a triangle, and TetGen, handed a face it was given no sizes for, does not fail on it
        so much as take the application with it.
        """
        self.delayDisplay("Starting the test without remeshing")

        logic = CfdMeshGeneratorLogic()
        surface = self.openTube()
        for mesher in self.meshers():
            mesh, remeshedSurface = logic.generateMesh(
                surface, skipRemeshing=True, mesher=mesher, **self.fasterFTetWild(mesher))

            self.assertEqual(set(remeshedSurface.GetCellType(cellId)
                                 for cellId in range(remeshedSurface.GetNumberOfCells())),
                             {vtk.VTK_TRIANGLE},
                             "the surface was handed on with a polygon in it")
            # The wall it arrived with, kept: only the caps are new.
            self.assertLess(remeshedSurface.GetNumberOfCells(), surface.GetNumberOfCells() + 100)
            cellTypes = vtk.vtkCellTypes()
            mesh.GetCellTypes(cellTypes)
            self.assertTrue(cellTypes.IsType(vtk.VTK_TETRA),
                            "the mesh holds no tetrahedra (%s)" % mesher)
            self.assertEqual(self.cellEntityIds(mesh), {0, 1, 2, 3}, mesher)

        self.delayDisplay("Test without remeshing passed")

    def test_CfdMeshGeneratorRemeshingTheCapsAlone(self):
        """The wall can be left as it arrived while the caps are remeshed.

        That is the point of excluding a face from the remesher: it edits no cell of an excluded
        face and moves no point one of them uses, so the wall keeps every cell it had and the caps
        go on meeting it along the rim they share.
        """
        self.delayDisplay("Starting the caps-only remeshing test")

        logic = CfdMeshGeneratorLogic()
        surface = self.openTube()
        capped = logic.capSurface(surface, "CellEntityIds", "simple")

        remeshed = logic.remeshSurface(
            capped, "CellEntityIds", elementSizeMode="edgelength", targetEdgeLength=0.4,
            targetEdgeLengthArrayName="", targetEdgeLengthFactor=1.0, triangleSplitFactor=5.0,
            maxEdgeLength=1e16, minEdgeLength=0.0,
            excludedEntityIds=[CfdMeshGeneratorLogic.wallCellEntityId])

        ids = remeshed.GetCellData().GetArray("CellEntityIds")
        wallCells = sum(1 for cellId in range(remeshed.GetNumberOfCells())
                        if int(ids.GetTuple1(cellId)) == CfdMeshGeneratorLogic.wallCellEntityId)
        self.assertEqual(wallCells, surface.GetNumberOfCells(),
                         "the wall was remeshed after all")
        self.assertGreater(remeshed.GetNumberOfCells() - wallCells, 60,
                           "the caps were not remeshed")

        edges = vtk.vtkFeatureEdges()
        edges.SetInputData(remeshed)
        edges.BoundaryEdgesOn()
        edges.NonManifoldEdgesOn()
        edges.FeatureEdgesOff()
        edges.ManifoldEdgesOff()
        edges.Update()
        self.assertEqual(edges.GetOutput().GetNumberOfCells(), 0,
                         "the caps no longer meet the wall along their rim")

        self.delayDisplay("Caps-only remeshing test passed")

    def test_CfdMeshGeneratorBoundaryLayer(self):
        """The same tube, lined with prisms, whether the layer is grown over the caps or stops
        short of them. The layer must be made of prisms and the space it leaves must still be
        filled with tetrahedra - a mesh that came back hollow would look like a mesh until a
        solver opened it. The caps must be there to carry the flow conditions too, including the
        sidewall cells swept out of each open end, which are named after the cap they belong to
        only once everything has been put together."""
        self.delayDisplay("Starting the boundary layer test")

        logic = CfdMeshGeneratorLogic()
        for mesher in self.meshers():
            for onCaps in (True, False):
                where = "(%s, on caps: %s)" % (mesher, onCaps)
                mesh, _remeshedSurface = logic.generateMesh(
                    self.openTube(), targetEdgeLength=0.4, boundaryLayer=True,
                    boundaryLayerOnCaps=onCaps, mesher=mesher, **self.fasterFTetWild(mesher))

                cellTypes = vtk.vtkCellTypes()
                mesh.GetCellTypes(cellTypes)
                self.assertTrue(cellTypes.IsType(vtk.VTK_WEDGE),
                                "the boundary layer holds no prisms " + where)
                self.assertTrue(cellTypes.IsType(vtk.VTK_TETRA),
                                "the mesh is hollow inside its boundary layer " + where)
                self.assertFalse(logic.lastTetrahedralizationFailed, where)
                ids = self.cellEntityIds(mesh)
                self.assertEqual(ids, {0, 1, 2, 3}, where)
                self.assertNotIn(CfdMeshGeneratorLogic.placeholderCellEntityId, ids,
                                 "a sidewall cell was left under the placeholder id " + where)
                if not onCaps:
                    # The strips swept out of the open ends, which stand between the rim of the
                    # outer surface and the cap made past the layer. Nothing else is a quad.
                    self.assertTrue(cellTypes.IsType(vtk.VTK_QUAD),
                                    "the open ends were swept into no sidewall cells " + where)
                self.assertBoundaryIsLabelled(mesh, "CellEntityIds", where)
                self.assertTetrahedraArePositive(mesh, where)

        self.delayDisplay("Boundary layer test passed")

    def test_CfdMeshGeneratorFoldedBoundaryLayer(self):
        """A layer too thick for the vessel folds through itself, and TetGen does not survive
        being handed the result, so it must be turned away before it gets there."""
        self.delayDisplay("Starting the folded boundary layer test")

        logic = CfdMeshGeneratorLogic()
        with self.assertRaises(RuntimeError):
            logic.generateMesh(self.openTube(), targetEdgeLength=0.4, boundaryLayer=True,
                               boundaryLayerThicknessFactor=8.0)

        self.delayDisplay("Folded boundary layer test passed")

    def test_CfdMeshGeneratorLayerOffImportedCaps(self):
        """"Layer on caps" has to mean something for a surface that arrives capped as well.

        Not capping is what keeps a layer off the caps of a surface whose ends are still open, but
        it does nothing for one that was closed before it got here: the sweep runs over the caps
        it already has. The caps have to come off first, and the ids they carried have to come
        back on the caps made in their place, or a solver reading the inlet by its number reads
        the wrong end of the vessel.
        """
        self.delayDisplay("Starting the imported caps test")

        logic = CfdMeshGeneratorLogic()
        closed = logic.capSurface(self.openTube(), "ModelFaceID", "simple")
        targetEdgeLength = 0.4
        layerThickness = 0.25 * targetEdgeLength

        def gapToTheInlet(mesh):
            """How far the tetrahedra keep from the cap at z = 0. A layer grown over that cap
            stands between the two; without one they meet it directly. The cap face itself looks
            the same either way, so this is what the flag can be read off."""
            gap = None
            for cellId in range(mesh.GetNumberOfCells()):
                if mesh.GetCellType(cellId) != vtk.VTK_TETRA:
                    continue
                cell = mesh.GetCell(cellId)
                for index in range(cell.GetNumberOfPoints()):
                    z = mesh.GetPoint(cell.GetPointId(index))[2]
                    gap = z if gap is None else min(gap, z)
            return gap

        for mesher in self.meshers():
            for onCaps in (False, True):
                where = "(%s, on caps: %s)" % (mesher, onCaps)
                mesh, _remeshedSurface = logic.generateMesh(
                    closed, targetEdgeLength=targetEdgeLength,
                    cellEntityIdsArrayName="ModelFaceID", skipCapping=True, boundaryLayer=True,
                    boundaryLayerOnCaps=onCaps, mesher=mesher, **self.fasterFTetWild(mesher))

                gap = gapToTheInlet(mesh)
                self.assertIsNotNone(gap, "the mesh holds no tetrahedra " + where)
                if onCaps:
                    self.assertGreater(gap, 0.5 * layerThickness,
                                       "no layer was grown over the cap " + where)
                else:
                    self.assertLess(gap, 0.5 * layerThickness,
                                    "the layer was grown over the cap after all " + where)
                self.assertEqual(
                    self.cellEntityIds(mesh, "ModelFaceID"), {0, 1, 2, 3},
                    "the caps did not come back under the ids they arrived with " + where)

        self.delayDisplay("Imported caps test passed")

    def test_CfdMeshGeneratorNamesCapsAfterVesselEnds(self):
        """A cap is named after the vessel end it closes, whether the surface says which end that
        is or only where it is.

        A surface from Clip Vessel carries the labels that say it, and then the id of an end is
        the one Clip Vessel gives it - the same one every run, whatever order the boundaries come
        out of the extractor in. A surface that has lost them falls back to where the cap was,
        which has to reach the same answer or a solver reads the inlet condition off the outlet.
        """
        self.delayDisplay("Starting the cap naming test")

        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry

        logic = CfdMeshGeneratorLogic()
        labeler = vtkvmtkComputationalGeometry.vtkvmtkPolyDataBoundaryLabeler()
        labeler.SetInputData(self.openTube())
        labeler.SetBoundaryLabelsArrayName(logic.boundaryLabelsArrayName)
        labeler.SetBoundaryPointOrderArrayName(logic.boundaryPointOrderArrayName)
        # A label is the id of the cap that closes its boundary, so the boundaries are numbered
        # above the wall this module sets its caps into. It is the labeler's own default too; said
        # here because a surface labelled for some other wall would be capped over the wall's face.
        labeler.SetCellEntityIdOffset(logic.wallCellEntityId)
        labeler.Update()

        def middleOfEachFace(mesh):
            """How far along the tube each face sits, so that an id can be read against the end
            it is on: the tube runs from z = 0 to z = 10."""
            array = mesh.GetCellData().GetArray("ModelFaceID")
            sums, counts = {}, {}
            for cellId in range(mesh.GetNumberOfCells()):
                if mesh.GetCellType(cellId) not in (vtk.VTK_TRIANGLE, vtk.VTK_QUAD,
                                                    vtk.VTK_POLYGON):
                    continue
                entityId = int(array.GetTuple1(cellId))
                cell = mesh.GetCell(cellId)
                for index in range(cell.GetNumberOfPoints()):
                    sums[entityId] = sums.get(entityId, 0.0) + mesh.GetPoint(
                        cell.GetPointId(index))[2]
                    counts[entityId] = counts.get(entityId, 0) + 1
            return {faceId: sums[faceId] / counts[faceId] for faceId in sums}

        labelled = labeler.GetOutput()
        capped = logic.capSurface(labelled, "ModelFaceID", "simple")
        middles = middleOfEachFace(capped)
        self.assertEqual(sorted(middles), [1, 2, 3])
        # the point data and the cell data are one numbering: the end labelled 2 is face 2
        boundaryLabels = set(
            int(labelled.GetPointData().GetArray(logic.boundaryLabelsArrayName).GetTuple1(pointId))
            for pointId in range(labelled.GetNumberOfPoints()))
        self.assertEqual(sorted(label for label in boundaryLabels if label >= 0), [2, 3])
        self.assertLess(middles[2], 1.0, "the cap of the first vessel end is not face 2")
        self.assertGreater(middles[3], 9.0, "the cap of the second vessel end is not face 3")

        # Taken off and rebuilt past a boundary layer, with and without anything saying which end
        # is which, the ids have to come back on the same ends.
        for mesher in self.meshers():
            for keepLabels in (True, False):
                where = "(%s, labels kept: %s)" % (mesher, keepLabels)
                surface = vtk.vtkPolyData()
                surface.DeepCopy(capped)
                if not keepLabels:
                    surface.GetPointData().RemoveArray(logic.boundaryLabelsArrayName)
                    surface.GetPointData().RemoveArray(logic.boundaryPointOrderArrayName)

                mesh, _remeshedSurface = logic.generateMesh(
                    surface, targetEdgeLength=0.4, cellEntityIdsArrayName="ModelFaceID",
                    skipCapping=True, boundaryLayer=True, boundaryLayerOnCaps=False,
                    mesher=mesher, **self.fasterFTetWild(mesher))

                middles = middleOfEachFace(mesh)
                self.assertLess(middles[2], 1.0, "face 2 came back on the wrong end " + where)
                self.assertGreater(middles[3], 9.0, "face 3 came back on the wrong end " + where)

        self.delayDisplay("Cap naming test passed")

    def test_CfdMeshGeneratorClipping(self):
        """The clip box is the model's own bounding box, halved along its shortest side, and it
        keeps whole elements.

        Cutting through the elements would show faces that are not element faces, which is
        exactly what someone looking inside a mesh must not be shown.
        """
        self.delayDisplay("Starting the clipping test")

        logic = CfdMeshGeneratorLogic()
        modelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "mesh")
        modelNode.SetAndObserveMesh(self.openTube(height=10.0, radius=1.0))

        clipNode = logic.clipWithABoxThroughTheMiddle(modelNode)
        self.assertIsNotNone(clipNode)
        self.assertEqual(clipNode.GetClippingMethod(), slicer.vtkMRMLClipNode.WholeCells)
        self.assertTrue(modelNode.GetDisplayNode().GetClipping())
        self.assertIs(modelNode.GetDisplayNode().GetClipNode(), clipNode)

        roiNode = clipNode.GetNthClippingNode(0)
        self.assertTrue(roiNode.IsA("vtkMRMLMarkupsROINode"))
        # The tube is 2 across and 10 long, so the box is halved across and left alone along it.
        self.assertEqual([round(value, 3) for value in roiNode.GetSize()], [1.0, 2.0, 10.0])
        self.assertEqual([round(value, 3) for value in roiNode.GetCenter()], [0.0, 0.0, 5.0])
        self.assertTrue(roiNode.GetDisplayNode().GetVisibility())
        self.assertAlmostEqual(roiNode.GetDisplayNode().GetFillOpacity(), 0.05)

        self.delayDisplay("Clipping test passed")

    def test_CfdMeshGeneratorReapplyLeavesTheDisplayAlone(self):
        """A second Apply writes the new mesh into the node it was given and touches nothing else.

        Meshing is something to try a few times at different sizes, and each try would otherwise
        undo the colour, the opacity and the visibility the last one was being looked at through.
        """
        self.delayDisplay("Starting the reapply test")

        logic = CfdMeshGeneratorLogic()
        modelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "mesh")
        modelNode.SetAndObserveMesh(logic.capSurface(self.openTube(), "CellEntityIds", "simple"))

        logic.showMeshInScene(modelNode, "CellEntityIds")
        displayNode = modelNode.GetDisplayNode()
        self.assertIsNotNone(displayNode, "the first run gave the output no display")
        self.assertTrue(displayNode.GetScalarVisibility(), "the faces are not coloured apart")

        displayNode.SetColor(0.1, 0.8, 0.3)
        displayNode.SetOpacity(0.4)
        displayNode.SetScalarVisibility(False)
        displayNode.SetVisibility(False)

        logic.showMeshInScene(modelNode, "CellEntityIds")
        self.assertIs(modelNode.GetDisplayNode(), displayNode, "the display node was replaced")
        self.assertEqual(displayNode.GetColor(), (0.1, 0.8, 0.3))
        self.assertAlmostEqual(displayNode.GetOpacity(), 0.4)
        self.assertFalse(displayNode.GetScalarVisibility())
        self.assertFalse(displayNode.GetVisibility())

        self.delayDisplay("Reapply test passed")

    def test_CfdMeshGeneratorKeepsTheLabelsOfTheInput(self):
        """A surface that arrives already capped and labelled - as one from Clip Vessel does -
        keeps its faces, and the rim between a cap and the wall survives remeshing.

        The ids are what hold the two apart while the remesher works. Read under the wrong name
        the surface is one face as far as the remesher is concerned, and it smooths the rim away:
        the cap stops being flat, which is what a solver's inlet condition needs it to be.
        """
        self.delayDisplay("Starting the kept labels test")

        logic = CfdMeshGeneratorLogic()
        labelled = logic.capSurface(self.openTube(), "ModelFaceID", "simple")
        _mesh, remeshedSurface = logic.generateMesh(
            labelled, targetEdgeLength=0.4, cellEntityIdsArrayName="ModelFaceID", skipCapping=True)

        ids = remeshedSurface.GetCellData().GetArray("ModelFaceID")
        self.assertIsNotNone(ids, "the labels of the input were not carried through")
        self.assertEqual(sorted(set(int(ids.GetTuple1(index))
                                    for index in range(ids.GetNumberOfTuples()))), [1, 2, 3])

        for capId in (2, 3):
            heights = []
            for cellId in range(remeshedSurface.GetNumberOfCells()):
                if int(ids.GetTuple1(cellId)) != capId:
                    continue
                cell = remeshedSurface.GetCell(cellId)
                heights.extend(remeshedSurface.GetPoint(cell.GetPointId(index))[2]
                               for index in range(cell.GetNumberOfPoints()))
            self.assertTrue(heights, "cap %d lost every cell it had" % capId)
            self.assertLess(max(heights) - min(heights), 1e-6,
                            "cap %d is no longer flat, so its rim was not held" % capId)

        self.delayDisplay("Kept labels test passed")

    def test_CfdMeshGeneratorFTetWildSizesByPosition(self):
        """A size asked for per point has to come out as elements of that size.

        This is what fTetWild is here for that TetGen cannot do: the switch TetGen reads a size
        function through answers differently each run, so the volume it fills is sized by one
        number throughout however finely the surface is graded. A vessel that is narrow in one
        place and wide in another wants the mesh fine in the narrow part and no finer than it has
        to be elsewhere, which is the whole of the saving.
        """
        self.requireFTetWild()
        self.delayDisplay("Starting the sizing by position test")

        logic = CfdMeshGeneratorLogic()
        # A tube whose lower half asks for cells a third the size of its upper half. Finer than
        # the tube the other tests use: asked to grade a surface into triangles far from the size
        # of the ones it was given, the remesher hands back one with holes in it, and no mesher
        # can do anything with that (the run refuses, which is the next test but one).
        surface = logic.capSurface(
            self.openTube(numberOfAxialPoints=40, numberOfCircumferentialPoints=48),
            "CellEntityIds", "simple")
        sizes = vtk.vtkDoubleArray()
        sizes.SetName("Size")
        sizes.SetNumberOfTuples(surface.GetNumberOfPoints())
        for pointId in range(surface.GetNumberOfPoints()):
            sizes.SetTuple1(pointId, 0.2 if surface.GetPoint(pointId)[2] < 5.0 else 0.6)
        surface.GetPointData().AddArray(sizes)

        mesh, _remeshedSurface = logic.generateMesh(
            surface, mesher=Mesher.FTETWILD.value, skipCapping=True,
            elementSizeMode=ElementSizeMode.EDGE_LENGTH_ARRAY.value,
            targetEdgeLengthArrayName="Size", volumeElementScaleFactor=1.0,
            maxOptimizationPasses=20)

        volumes = {True: [], False: []}
        for cellId in range(mesh.GetNumberOfCells()):
            if mesh.GetCellType(cellId) != vtk.VTK_TETRA:
                continue
            cell = mesh.GetCell(cellId)
            points = [mesh.GetPoint(cell.GetPointId(index)) for index in range(4)]
            middle = sum(point[2] for point in points) / 4.0
            volumes[middle < 5.0].append(abs(vtk.vtkTetra.ComputeVolume(*points)))

        self.assertTrue(volumes[True] and volumes[False], "the mesh does not span the tube")
        fine = sum(volumes[True]) / len(volumes[True])
        coarse = sum(volumes[False]) / len(volumes[False])
        # Three times the edge length is twenty-seven times the volume; anything past a few times
        # says the field was read, and nothing like it says the field was ignored.
        self.assertGreater(coarse / fine, 4.0,
                           "the half asked for coarse cells got cells %.2f times the size of the "
                           "half asked for fine ones" % (coarse / fine))

        self.delayDisplay("Sizing by position test passed")

    def test_CfdMeshGeneratorFTetWildIsAskedForBeforeItIsUsed(self):
        """A mesher that is not installed has to say so, and say what would install it.

        fTetWild is downloaded rather than built in, so a scene set to it can be opened on a
        machine that has never had it. What comes of pressing Apply there should be a sentence
        naming the package, not an ImportError out of the middle of the pipeline.
        """
        self.delayDisplay("Starting the missing fTetWild test")

        logic = CfdMeshGeneratorLogic()

        class Blocked:
            """Stands in for a machine that has never installed the package: asked for it, the
            import machinery finds nothing, which is what it does when it is not there."""

            @staticmethod
            def find_spec(name, path=None, target=None):
                if name.split(".")[0] == "pytetwild":
                    raise ModuleNotFoundError("No module named %r" % name, name=name)
                return None

        hidden = {name: module for name, module in sys.modules.items()
                  if name.split(".")[0] == "pytetwild"}
        for name in hidden:
            del sys.modules[name]
        sys.meta_path.insert(0, Blocked)
        try:
            self.assertFalse(logic.isFTetWildAvailable(),
                             "fTetWild was reported available with its package hidden")
            with self.assertRaises(RuntimeError) as raised:
                logic.generateMesh(self.openTube(), mesher=Mesher.FTETWILD.value)
            self.assertIn("pytetwild", str(raised.exception),
                          "the message does not name the package to install")
        finally:
            sys.meta_path.remove(Blocked)
            sys.modules.update(hidden)

        # And with the package back, the same call gets as far as meshing.
        self.assertTrue(logic.isFTetWildAvailable() or not hidden,
                        "the package was not put back after the test hid it")

        self.delayDisplay("Missing fTetWild test passed")
