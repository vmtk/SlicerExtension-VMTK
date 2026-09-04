"""The aorta case the end-to-end tests here work on.

Not a test: the name does not match pytest's default pattern, so it is imported rather than
collected. It builds the case once per process and hands the same one to every test that asks,
because extracting the centerline is the expensive part and none of them modify it.
"""

import numpy as np
import slicer
import vtk
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy

import ClipVessel

_case = None


def ensureClipVesselModuleRegistered():
    """Make slicer.modules.clipvessel exist, registering it if this Slicer did not.

    Building the module's widget needs the module itself registered, not merely importable:
    ScriptedLoadableModuleWidget.setup() asks slicer.util.modulePath() where the module lives so
    that it can find its .ui file, and that reads slicer.modules.clipvessel.

    A Slicer started through the extension's own launcher has it. One started as the application
    binary directly does not, because the module paths are given to the launcher rather than
    carried in the environment it passes on -- which is what SlicerPythonTestRunner does when it
    spawns an instance per test file. The module is still importable there, so the file to
    register is the one already imported."""
    import qt

    if hasattr(slicer.modules, "clipvessel"):
        return
    factoryManager = slicer.app.moduleManager().factoryManager()
    factoryManager.registerModule(qt.QFileInfo(ClipVessel.__file__))
    factoryManager.loadModules(["ClipVessel"])
    if not hasattr(slicer.modules, "clipvessel"):
        raise RuntimeError("could not register the ClipVessel module from %s" % ClipVessel.__file__)


def clipVesselModuleWidget():
    """The module's own widget, the one the application drives.

    Slicer builds the widget, parents it, gives it the scene and runs setup(), so a test gets the
    same object a user does without assembling it around a qMRMLWidget itself. It also owns it:
    the module manager tears the widget down before the scene at exit, so a test must not call
    cleanup() on it or hand its scene back.

    Selecting the module is what makes the application build the widget, but it needs the module
    selector in the main window, which is not there when the test runner starts Slicer with
    --no-main-window. getModuleWidget builds the widget representation on demand either way, so
    the selection is best effort.
    """
    ensureClipVesselModuleRegistered()
    try:
        slicer.util.selectModule("ClipVessel")
    except RuntimeError:
        pass
    return slicer.util.getModuleWidget("ClipVessel")


def newClipVesselModuleWidget():
    """A second, independent module widget, with its own parameter node.

    For the one test that needs a widget which has not seen what the first one did. Slicer makes
    it, but does not keep it, so this one is the caller's to clean up.
    """
    ensureClipVesselModuleRegistered()
    return slicer.util.getNewModuleWidget("ClipVessel")


class AortaCase:
    """A real vessel surface, its centerline, and a clip point at each vessel end."""

    def __init__(self):
        import ExtractCenterline
        import SampleData

        self.inputSurfaceModelNode = downloadAortaSurface()
        self.inputPolyData = self.inputSurfaceModelNode.GetPolyData()

        extractCenterlineLogic = ExtractCenterline.ExtractCenterlineLogic()
        self.preprocessedPolyData = extractCenterlineLogic.preprocess(self.inputPolyData, 5000.0, 4.0, False)

        endPointsMarkupsNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "Centerline endpoints")
        networkPolyData = extractCenterlineLogic.extractNetwork(self.preprocessedPolyData, endPointsMarkupsNode)
        for position in extractCenterlineLogic.getEndPoints(networkPolyData, startPointPosition=None):
            endPointsMarkupsNode.AddControlPoint(vtk.vtkVector3d(position))
        centerlinePolyData, _voronoi = extractCenterlineLogic.extractCenterline(
            self.preprocessedPolyData, endPointsMarkupsNode)
        self.centerlineModelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Centerline model")
        self.centerlineModelNode.SetAndObserveMesh(centerlinePolyData)

        self.logic = ClipVessel.ClipVesselLogic()
        self.clipPointsMarkupsNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "Clip points")
        for terminus in self.logic.detectCenterlineTerminusClipPoints(self.centerlineModelNode, 1.5):
            pointIndex = self.clipPointsMarkupsNode.AddControlPointWorld(vtk.vtkVector3d(terminus["position"]))
            self.clipPointsMarkupsNode.SetNthControlPointLabel(pointIndex, terminus["label"])
        self.numberOfClipPoints = self.clipPointsMarkupsNode.GetNumberOfControlPoints()

        self.clipPlanes = [self.logic.automaticClipPlane(self.centerlineModelNode, self.clipPointsMarkupsNode, i)
                           for i in range(self.numberOfClipPoints)]
        self.clipPointPositions = np.array([plane[0] for plane in self.clipPlanes])

    def clip(self, cap=True, addFlowExtensions=False, labelModelFaces=True, surface=None):
        """Run the module's own pipeline, the way the widget's Apply does."""
        return self.logic.clipVessel(
            surface if surface is not None else self.preprocessedPolyData,
            self.centerlineModelNode, self.clipPointsMarkupsNode,
            cap, addFlowExtensions, 2.0, "BOUNDARY_NORMAL", transitionRatio=0.5,
            labelModelFaces=labelModelFaces)


def downloadAortaSurface():
    """The sample surface, as a model node, or a clear failure.

    SampleData hands back a list whose entry is None when the download did not produce a node,
    which several instances fetching the same file at once can cause -- and the test runner runs
    four at a time by default. Left alone that surfaces much later as an AttributeError on None,
    naming neither the file nor the download, so it is checked here instead."""
    import SampleData

    nodes = SampleData.downloadFromURL(
        fileNames="aorta-surface.stl", nodeNames="aorta-surface",
        uris="https://raw.githubusercontent.com/vmtk/vmtk-test-data/master/input/aorta-surface.stl")
    node = nodes[0] if nodes else None
    if node is None or node.GetPolyData() is None or node.GetPolyData().GetNumberOfPoints() == 0:
        raise RuntimeError(
            "could not download aorta-surface.stl, or it arrived empty; SampleData returned %r. "
            "Several instances fetching it at once can do this." % (nodes,))
    return node


def aortaCase():
    """The case, built on first use and reused after that."""
    global _case
    if _case is None:
        _case = AortaCase()
    return _case


def cellCentroids(polyData):
    cellCenters = vtk.vtkCellCenters()
    cellCenters.SetInputData(polyData)
    cellCenters.Update()
    return vtk_to_numpy(cellCenters.GetOutput().GetPoints().GetData())


def withLabelledPatches(polyData, clipPointPositions, arrayName="ModelFaceID"):
    """A copy of polyData carrying two labeled patches, so that a run has input faces to carry
    through.

    The patches are picked by position rather than by cell index, so that they are contiguous on
    the surface and their extent can be compared before and after. They are kept well away from
    every clip point: a patch sitting on a vessel end is mostly cut away, and what is left of it
    has a centre of mass a long way from where the whole patch's was, which says nothing about
    whether the labels stayed on their geometry."""
    labelled = vtk.vtkPolyData()
    labelled.DeepCopy(polyData)
    centroids = cellCentroids(labelled)

    distanceToNearestClipPoint = np.min(
        np.linalg.norm(centroids[:, None, :] - np.asarray(clipPointPositions)[None, :, :], axis=2),
        axis=1)
    # the half of the surface furthest from any cut, split in two by height
    farEnough = distanceToNearestClipPoint > np.percentile(distanceToNearestClipPoint, 50.0)
    zMedian = np.median(centroids[farEnough, 2])

    faceIds = np.zeros(labelled.GetNumberOfCells(), dtype=np.int32)
    faceIds[farEnough & (centroids[:, 2] <= zMedian)] = 1
    faceIds[farEnough & (centroids[:, 2] > zMedian)] = 2
    array = numpy_to_vtk(faceIds, deep=True, array_type=vtk.VTK_INT)
    array.SetName(arrayName)
    labelled.GetCellData().AddArray(array)
    return labelled


def openBoundaries(polyData):
    """The open boundaries of polyData as (number of points, centroid, extent), the way the
    capping filter sees them."""
    import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
    extractor = vtkvmtkComputationalGeometry.vtkvmtkPolyDataBoundaryExtractor()
    extractor.SetInputData(polyData)
    extractor.Update()
    extracted = extractor.GetOutput()
    boundaries = []
    for i in range(extracted.GetNumberOfCells()):
        cell = extracted.GetCell(i)
        points = np.array([cell.GetPoints().GetPoint(j) for j in range(cell.GetNumberOfPoints())])
        boundaries.append((cell.GetNumberOfPoints(), points.mean(axis=0),
                           float(np.linalg.norm(points.max(0) - points.min(0)))))
    return boundaries
