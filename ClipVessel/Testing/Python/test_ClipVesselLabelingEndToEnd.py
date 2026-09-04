"""The whole pipeline on a real vessel surface, capped, with and without flow extensions.

The other suites here drive the logic on synthetic tubes, which pins down the rules but not
whether they survive a real surface, real centerlines and clip points placed by the module
itself. This one runs what Apply runs and checks that every cap carries the id of the clip point
that opened it, and that it sits where that clip point is.
"""

import unittest

import numpy as np
import vtk
from vtk.util.numpy_support import vtk_to_numpy

from ClipVesselTestFixture import aortaCase, cellCentroids


class LabelingEndToEndTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.case = aortaCase()

    def assertLabelsDescribeTheOutput(self, addFlowExtensions):
        case = self.case
        output = case.clip(cap=True, addFlowExtensions=addFlowExtensions)

        faceIdArray = output.GetCellData().GetArray("ModelFaceID")
        self.assertIsNotNone(faceIdArray, "no ModelFaceID array on the output")
        self.assertTrue(faceIdArray.IsA("vtkIntArray"), faceIdArray.GetClassName())
        self.assertEqual(faceIdArray.GetNumberOfTuples(), output.GetNumberOfCells(),
                         "one id per cell")
        scalars = output.GetCellData().GetScalars()
        self.assertIsNotNone(scalars)
        self.assertEqual(scalars.GetName(), "ModelFaceID")

        faceIds = vtk_to_numpy(faceIdArray)
        expected = set(range(1, case.numberOfClipPoints + 2))
        self.assertEqual(set(int(v) for v in np.unique(faceIds)), expected,
                         "ids should be the wall and one per clip point")
        self.assertGreater(np.count_nonzero(faceIds == 1), np.count_nonzero(faceIds != 1),
                           "the wall should be the largest face")
        self.assertEqual(len(case.logic.lastFaceIdAssignments), case.numberOfClipPoints,
                         case.logic.lastFaceIdAssignments)

        centers = cellCentroids(output)
        for faceId, pointLabel in case.logic.lastFaceIdAssignments:
            clipPointIndex = faceId - 2
            self.assertEqual(pointLabel,
                             case.clipPointsMarkupsNode.GetNthControlPointLabel(clipPointIndex),
                             "id %d should name clip point %d" % (faceId, clipPointIndex))

            capCentroid = centers[faceIds == faceId].mean(axis=0)
            origin, normal, radius = case.clipPlanes[clipPointIndex]
            offset = capCentroid - np.array(origin)
            alongNormal = float(np.dot(offset, normal))
            perpendicular = float(np.linalg.norm(offset - alongNormal * np.array(normal)))

            if addFlowExtensions:
                # the cap is out at the tip of the extension, along the clip plane's own normal
                self.assertGreater(alongNormal, 0.0,
                                   "cap %d should be beyond its clip plane" % faceId)
                self.assertLess(perpendicular, radius,
                                "cap %d should stay on the plane axis" % faceId)
            else:
                # without extensions the cap sits in the plane, so it is nearest its own clip point
                nearest = int(np.argmin(np.linalg.norm(case.clipPointPositions - capCentroid, axis=1)))
                self.assertEqual(nearest, clipPointIndex,
                                 "cap %d is nearest clip point %d, not its own" % (faceId, nearest))

    def test_capped_without_flow_extensions(self):
        self.assertLabelsDescribeTheOutput(addFlowExtensions=False)

    def test_capped_with_flow_extensions(self):
        self.assertLabelsDescribeTheOutput(addFlowExtensions=True)


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
