"""The vessel every centerline test here works on.

Not a test: the name does not match pytest's default pattern, so it is imported rather than
collected. The surface is decimated and the network extracted once per process and handed to
every test that asks, because that is the expensive part and none of them modify it.
"""

import slicer
import vtk

import ExtractCenterline

_case = None

# What the module's own defaults decimate to, and what the other modules' tests use, so that a
# centerline extracted here is the one they are written against.
TARGET_NUMBER_OF_POINTS = 5000.0
DECIMATION_AGGRESSIVENESS = 4.0


def downloadAortaSurface():
    """The sample vessel, as a model node, or a clear failure.

    SampleData hands back a list whose entry is None when the download did not produce a node,
    which several instances fetching the same file at once can cause. Left alone that surfaces
    much later as an AttributeError on None, naming neither the file nor the download.
    """
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


class AortaCase:
    """A real vessel surface, decimated, with its network and the endpoints read off it."""

    def __init__(self):
        self.logic = ExtractCenterline.ExtractCenterlineLogic()
        self.inputSurfaceModelNode = downloadAortaSurface()
        self.inputPolyData = self.inputSurfaceModelNode.GetPolyData()
        self.preprocessedPolyData = self.logic.preprocess(
            self.inputPolyData, TARGET_NUMBER_OF_POINTS, DECIMATION_AGGRESSIVENESS, False)

        self.endPointsMarkupsNode = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLMarkupsFiducialNode", "Centerline endpoints")
        self.networkPolyData = self.logic.extractNetwork(
            self.preprocessedPolyData, self.endPointsMarkupsNode)
        self.endpointPositions = self.logic.getEndPoints(self.networkPolyData, startPointPosition=None)
        for position in self.endpointPositions:
            self.endPointsMarkupsNode.AddControlPoint(vtk.vtkVector3d(position))

    def extractCenterline(self, **keywordArguments):
        return self.logic.extractCenterline(
            self.preprocessedPolyData, self.endPointsMarkupsNode, **keywordArguments)


def aortaCase():
    """The case, built on first use and reused after that."""
    global _case
    if _case is None:
        _case = AortaCase()
    return _case


def polylineLength(polyData):
    """The total length of every line cell of polyData."""
    total = 0.0
    for cellId in range(polyData.GetNumberOfCells()):
        cell = polyData.GetCell(cellId)
        points = cell.GetPoints()
        for index in range(points.GetNumberOfPoints() - 1):
            total += vtk.vtkMath.Distance2BetweenPoints(
                points.GetPoint(index), points.GetPoint(index + 1)) ** 0.5
    return total
