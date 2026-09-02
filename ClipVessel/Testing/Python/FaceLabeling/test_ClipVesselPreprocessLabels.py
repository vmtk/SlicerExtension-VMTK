"""Face labels must survive preprocessing, including on the meshes that break it.

Preprocessing rebuilds the mesh, and what it leaves of a cell array cannot be relied on: a
degenerate triangle -- which vtkCleanPolyData turns into a vert and vtkTriangleFilter then drops --
leaves the array at twice the cell count and misaligned, and decimation drops it outright. The
labels are therefore re-derived from the original surface by position, which is what is measured
here: a misplaced label shows up as a label on the wrong geometry, not as a missing array.
"""

import unittest

import numpy as np
import slicer
import vtk
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy

from ClipVesselTestFixture import clipVesselModuleWidget


def tube(numberOfAxialPoints=12, numberOfCircumferentialPoints=24, height=10.0, radius=1.0,
         numberOfDegenerateTriangles=0):
    """A tube whose triangles share no points, optionally with degenerate triangles appended."""
    points, polys = vtk.vtkPoints(), vtk.vtkCellArray()

    def position(axialIndex, circumferentialIndex):
        angle = 2 * np.pi * circumferentialIndex / numberOfCircumferentialPoints
        return (radius * np.cos(angle), radius * np.sin(angle),
                height * axialIndex / (numberOfAxialPoints - 1))

    for axialIndex in range(numberOfAxialPoints - 1):
        for circumferentialIndex in range(numberOfCircumferentialPoints):
            for triangle in ((position(axialIndex, circumferentialIndex),
                              position(axialIndex, circumferentialIndex + 1),
                              position(axialIndex + 1, circumferentialIndex + 1)),
                             (position(axialIndex, circumferentialIndex),
                              position(axialIndex + 1, circumferentialIndex + 1),
                              position(axialIndex + 1, circumferentialIndex))):
                polys.InsertNextCell(3, [points.InsertNextPoint(*point) for point in triangle])
    for _ in range(numberOfDegenerateTriangles):
        pointId = points.InsertNextPoint(0.0, 0.0, 0.0)
        polys.InsertNextCell(3, [pointId, pointId, pointId])

    surface = vtk.vtkPolyData()
    surface.SetPoints(points)
    surface.SetPolys(polys)
    return surface


def cellCentroids(surface):
    cellCenters = vtk.vtkCellCenters()
    cellCenters.SetInputData(surface)
    cellCenters.Update()
    return vtk_to_numpy(cellCenters.GetOutput().GetPoints().GetData())


NO_DECIMATION = 500000.0
PATCH_BOUNDARY_Z = 1.0


class ClipVesselPreprocessLabelsTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """The module's own widget, one for the whole suite: clearing the scene under a widget
        that is observing it wedges the application."""
        cls.widget = clipVesselModuleWidget()
        cls.inputNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Input surface")


    @classmethod
    def tearDownClass(cls):
        """Let go of the widget without tearing it down. The module manager owns it and destroys
        it before the scene, so a test that called cleanup() on it would be pulling the module
        apart under the application."""
        cls.widget = None
        slicer.mrmlScene.Clear()

    def setUp(self):
        parameterNode = self.widget._parameterNode
        parameterNode.SetNodeReferenceID("InputSurface", self.inputNode.GetID())
        parameterNode.SetParameter("LabelModelFaces", "true")
        parameterNode.SetParameter("ModelFaceIdArrayName", "ModelFaceID")
        parameterNode.SetParameter("PreprocessInputSurface", "true")
        parameterNode.SetParameter("SubdivideInputSurface", "false")

    def preprocessLabelledTube(self, numberOfDegenerateTriangles, targetNumberOfPoints):
        """Label an inlet patch at the low-z end, preprocess, and return the result."""
        surface = tube(numberOfDegenerateTriangles=numberOfDegenerateTriangles)
        faceIds = np.where(cellCentroids(surface)[:, 2] < PATCH_BOUNDARY_Z, 3, 1).astype(np.int32)
        faceIdArray = numpy_to_vtk(faceIds, deep=True, array_type=vtk.VTK_INT)
        faceIdArray.SetName("ModelFaceID")
        surface.GetCellData().AddArray(faceIdArray)

        self.inputNode.SetAndObserveMesh(surface)
        self.widget._parameterNode.SetParameter("TargetNumberOfPoints", str(targetNumberOfPoints))
        self.widget._preprocessedCacheKey = None        # the input changed underneath the cache
        return self.widget.getPreprocessedPolyData()

    def assertLabelsFollowTheGeometry(self, numberOfDegenerateTriangles, targetNumberOfPoints):
        preprocessed = self.preprocessLabelledTube(numberOfDegenerateTriangles, targetNumberOfPoints)

        faceIdArray = preprocessed.GetCellData().GetArray("ModelFaceID")
        self.assertIsNotNone(faceIdArray, "the labels did not survive preprocessing at all")
        self.assertEqual(faceIdArray.GetNumberOfTuples(), preprocessed.GetNumberOfCells(),
                         "the array no longer has one value per cell, so it is misaligned")

        faceIds = vtk_to_numpy(faceIdArray)
        centroids = cellCentroids(preprocessed)
        # Decimation legitimately moves the patch edge by about a cell, so only cells clear of the
        # edge are held to their label.
        cellSize = (float(np.linalg.norm(centroids.max(0) - centroids.min(0)))
                    / max(1.0, preprocessed.GetNumberOfCells() ** 0.5))
        clearOfTheEdge = np.abs(centroids[:, 2] - PATCH_BOUNDARY_Z) > 2.0 * cellSize
        shouldBePatch = centroids[:, 2] < PATCH_BOUNDARY_Z
        misplaced = int(np.count_nonzero(((faceIds == 3) != shouldBePatch) & clearOfTheEdge))

        self.assertEqual(misplaced, 0, "%d of %d cells clear of the patch edge carry the wrong label"
                                       % (misplaced, int(clearOfTheEdge.sum())))

    def test_labels_survive_a_clean_mesh(self):
        self.assertLabelsFollowTheGeometry(0, NO_DECIMATION)

    def test_labels_survive_a_few_degenerate_triangles(self):
        self.assertLabelsFollowTheGeometry(5, NO_DECIMATION)

    def test_labels_survive_many_degenerate_triangles(self):
        self.assertLabelsFollowTheGeometry(40, NO_DECIMATION)

    def test_labels_survive_decimation(self):
        self.assertLabelsFollowTheGeometry(5, 200.0)
if __name__ == "__main__":
    # Run by slicer_add_python_test as "Slicer --python-script", which reports the outcome through
    # the exit code: an exception fails the test, a clean return passes it. unittest.main() is not
    # used because it exits the interpreter itself, taking Slicer down before it can report.
    import sys
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise AssertionError("%d failure(s) and %d error(s) in %d test(s)"
                             % (len(result.failures), len(result.errors), result.testsRun))
