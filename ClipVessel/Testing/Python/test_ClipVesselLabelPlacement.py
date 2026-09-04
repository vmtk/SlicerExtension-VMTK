"""Do the labels the input carried end up on the geometry they came from?

Clipping splits triangles and capping adds new ones, so the output's cells are not the input's.
The check is spatial rather than by index: for every output cell that is not part of a cap, the
input cell it sits on is found with a cell locator, and the face id it carries has to be the one
that input cell's id was renumbered to.

A cell locator rather than the nearest centroid, because a cut cell's centroid can sit nearer a
neighbour's centroid than its own parent's, which would make a correct label look wrong.

This began as a diagnostic to be pasted into a session after an Apply. It now builds its own case,
so what it used to print is checked instead.
"""

import unittest

import numpy as np
import vtk
from vtk.util.numpy_support import vtk_to_numpy

from ClipVesselTestFixture import aortaCase, cellCentroids, withLabelledPatches

ARRAY_NAME = "ModelFaceID"

# Cells that disagree are the ones a cut rebuilt, which sit off the input surface. A few percent
# of a real surface is expected; scattering would be far more than that.
MAXIMUM_DISAGREEMENT_FRACTION = 0.05

# How far a labeled patch's centre of mass may move between input and output. Clipping takes
# material off the ends, which shifts a patch a little, but a patch that has moved across the
# surface has not stayed on its own geometry.
MAXIMUM_PATCH_SHIFT_MM = 5.0


class LabelPlacementTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.case = aortaCase()
        # The aorta surface carries no labels of its own, so give it two to carry through.
        cls.labelledInput = withLabelledPatches(cls.case.preprocessedPolyData,
                                                cls.case.clipPointPositions, ARRAY_NAME)
        cls.output = cls.case.clip(cap=True, addFlowExtensions=False, labelModelFaces=True,
                                   surface=cls.labelledInput)
        cls.remap = dict(cls.case.logic.lastExistingFaceIdMap)
        cls.capIds = {faceId for faceId, _label in cls.case.logic.lastFaceIdAssignments}
        cls.wallId = cls.case.logic.lastWallFaceId

    def test_the_input_faces_were_carried_through(self):
        self.assertEqual(sorted(self.remap.keys()), [1, 2],
                         "both labeled input faces should have been recognised: %s" % (self.remap,))
        outputIds = vtk_to_numpy(self.output.GetCellData().GetArray(ARRAY_NAME))
        for originalId, newId in self.remap.items():
            self.assertGreater(int(np.count_nonzero(outputIds == newId)), 0,
                               "input face %d became %d but no output cell carries it"
                               % (originalId, newId))

    def test_non_cap_cells_keep_the_label_of_the_input_they_sit_on(self):
        inputIds = vtk_to_numpy(self.labelledInput.GetCellData().GetArray(ARRAY_NAME))
        outputIds = vtk_to_numpy(self.output.GetCellData().GetArray(ARRAY_NAME))
        outputCentroids = cellCentroids(self.output)

        locator = vtk.vtkCellLocator()
        locator.SetDataSet(self.labelledInput)
        locator.BuildLocator()
        closestPoint = [0.0, 0.0, 0.0]
        cellId, subId, squaredDistance = vtk.mutable(0), vtk.mutable(0), vtk.mutable(0.0)

        agree = disagree = 0
        examples = []
        for i, centroid in enumerate(outputCentroids):
            faceId = int(outputIds[i])
            if faceId in self.capIds:
                continue                      # a cap is new geometry, with no input cell under it
            locator.FindClosestPoint(list(centroid), closestPoint, cellId, subId, squaredDistance)
            expected = self.remap.get(int(inputIds[int(cellId)]), self.wallId)
            if faceId == expected:
                agree += 1
            else:
                disagree += 1
                if len(examples) < 5:
                    examples.append("cell %d carries %d, the input under it says %d, %.4f mm away"
                                    % (i, faceId, expected, float(squaredDistance) ** 0.5))

        total = agree + disagree
        self.assertGreater(total, 0, "no non-cap cells to check")
        fraction = disagree / float(total)
        self.assertLess(fraction, MAXIMUM_DISAGREEMENT_FRACTION,
                        "%d of %d non-cap cells (%.2f%%) carry a label the input under them does "
                        "not: %s" % (disagree, total, 100.0 * fraction, examples))

    def test_each_labelled_patch_stays_where_it_was(self):
        inputIds = vtk_to_numpy(self.labelledInput.GetCellData().GetArray(ARRAY_NAME))
        outputIds = vtk_to_numpy(self.output.GetCellData().GetArray(ARRAY_NAME))
        inputCentroids = cellCentroids(self.labelledInput)
        outputCentroids = cellCentroids(self.output)

        for originalId, newId in sorted(self.remap.items()):
            inputMask, outputMask = inputIds == originalId, outputIds == newId
            self.assertTrue(inputMask.any() and outputMask.any(),
                            "face %d -> %d is empty on one side" % (originalId, newId))
            shift = float(np.linalg.norm(inputCentroids[inputMask].mean(axis=0)
                                         - outputCentroids[outputMask].mean(axis=0)))
            self.assertLess(shift, MAXIMUM_PATCH_SHIFT_MM,
                            "input face %d became %d and its centre of mass moved %.3f mm, so it "
                            "is not on the geometry it started on" % (originalId, newId, shift))


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
