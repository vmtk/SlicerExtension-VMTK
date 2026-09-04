"""Where the open boundaries are at each stage of a real run.

Every open boundary the surface still has when it reaches the capper becomes a cap, and every cap
becomes a face. So a boundary that is not a vessel end -- a hole left by a missing triangle, say --
turns into a face of its own that no clip point accounts for, which is how a run ends up with more
faces than clip points. This walks the surface through the stages and checks that the only
boundaries present are the ones the cuts opened.

This began as a diagnostic to be pasted into a session after an Apply. It now builds its own case,
so what it used to print is checked instead.
"""

import unittest

import numpy as np

from ClipVesselTestFixture import aortaCase, openBoundaries

# A vessel end of this surface is a loop of many points. A boundary of only a handful of points is
# a mesh defect: too small to be an end, and large enough to be capped as a face.
DEFECT_BOUNDARY_POINTS = 6


class BoundaryStagesTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.case = aortaCase()

    def assertNoDefectBoundaries(self, polyData, stage):
        defects = [b for b in openBoundaries(polyData) if b[0] <= DEFECT_BOUNDARY_POINTS]
        self.assertEqual(
            defects, [],
            "%s carries %d boundary(ies) of at most %d points, which would be capped as faces of "
            "their own: %s" % (stage, len(defects), DEFECT_BOUNDARY_POINTS,
                               [(n, np.round(c, 1).tolist(), round(e, 3)) for n, c, e in defects]))

    def test_the_input_surface_has_only_its_own_vessel_ends(self):
        self.assertNoDefectBoundaries(self.case.inputPolyData, "the input surface")

    def test_preprocessing_opens_no_new_boundary(self):
        before = len(openBoundaries(self.case.inputPolyData))
        after = openBoundaries(self.case.preprocessedPolyData)
        self.assertNoDefectBoundaries(self.case.preprocessedPolyData, "the preprocessed surface")
        self.assertEqual(len(after), before,
                         "preprocessing changed the number of open boundaries from %d to %d"
                         % (before, len(after)))

    def test_each_clip_point_accounts_for_one_boundary_after_clipping(self):
        # Uncapped, so the boundaries the cuts opened are still open and can be counted.
        clipped = self.case.clip(cap=False, addFlowExtensions=False, labelModelFaces=False)
        boundaries = openBoundaries(clipped)
        self.assertNoDefectBoundaries(clipped, "the clipped surface")
        self.assertEqual(len(boundaries), self.case.numberOfClipPoints,
                         "%d open boundaries after clipping but %d clip points; the extra ones "
                         "would each be capped as a face no clip point accounts for"
                         % (len(boundaries), self.case.numberOfClipPoints))

    def test_every_boundary_after_clipping_sits_at_a_clip_point(self):
        clipped = self.case.clip(cap=False, addFlowExtensions=False, labelModelFaces=False)
        for numberOfPoints, centroid, extent in openBoundaries(clipped):
            distance = float(np.min(np.linalg.norm(self.case.clipPointPositions - centroid, axis=1)))
            self.assertLess(distance, extent + 1.0,
                            "a boundary of %d points at %s is %.2f mm from the nearest clip point, "
                            "so it is not one the cuts opened"
                            % (numberOfPoints, np.round(centroid, 1).tolist(), distance))


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
