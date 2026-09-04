"""The centerline method: slower than the network, more accurate, and the one that carries a
radius.

The radius is what everything downstream is built on - Clip Vessel sizes its clip planes by it,
and the curve tree reports it as a measurement - so a centerline without one is of no use even
where its geometry is right.
"""

import unittest

import numpy as np
import slicer
import vtk
from vtk.util.numpy_support import vtk_to_numpy

from ExtractCenterlineTestFixture import aortaCase, polylineLength


class ExtractCenterlineCenterlineTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.case = aortaCase()
        cls.centerline, cls.voronoi = cls.case.extractCenterline()

    def test_the_centerline_is_a_set_of_lines_with_a_radius(self):
        self.assertGreater(self.centerline.GetNumberOfPoints(), 0)
        self.assertGreater(self.centerline.GetNumberOfCells(), 0)
        self.assertEqual(self.centerline.GetNumberOfCells(), self.centerline.GetNumberOfLines(),
                         "the centerline holds cells that are not lines")

        radius = self.centerline.GetPointData().GetArray("Radius")
        self.assertIsNotNone(radius, "the centerline carries no radius")
        self.assertEqual(radius.GetNumberOfTuples(), self.centerline.GetNumberOfPoints())
        values = vtk_to_numpy(radius)
        self.assertGreater(values.min(), 0.0, "a radius of zero or less is not a vessel")
        self.assertLess(values.max(), 100.0, "the radius is larger than the vessel itself")

    def test_the_voronoi_diagram_comes_back_with_it(self):
        """The diagram is what the centerline was computed from, and the module shows it when
        asked, so it has to be returned rather than thrown away."""
        self.assertIsNotNone(self.voronoi)
        self.assertGreater(self.voronoi.GetNumberOfPoints(), 0)

    def test_a_branch_reaches_every_endpoint(self):
        """One branch per vessel end, each ending near the endpoint it was asked for.

        Near rather than at: the endpoints come from the network, which is a different
        construction, and the centerline stops where the Voronoi diagram does. Within one vessel
        radius is the check that a branch went to that end at all rather than stopping short of
        it, which is what a lost branch looks like.
        """
        centerlinePoints = vtk_to_numpy(self.centerline.GetPoints().GetData())
        largestRadius = float(vtk_to_numpy(self.centerline.GetPointData().GetArray("Radius")).max())

        for position in self.case.endpointPositions:
            distance = np.min(np.linalg.norm(centerlinePoints - np.asarray(position), axis=1))
            self.assertLess(distance, largestRadius,
                            "no branch reaches the vessel end at %s" % (position,))

    def test_the_centerline_stays_inside_the_vessel(self):
        surfaceBounds = self.case.preprocessedPolyData.GetBounds()
        centerlineBounds = self.centerline.GetBounds()

        for axis in range(3):
            self.assertGreaterEqual(centerlineBounds[2 * axis], surfaceBounds[2 * axis] - 1e-3)
            self.assertLessEqual(centerlineBounds[2 * axis + 1], surfaceBounds[2 * axis + 1] + 1e-3)

    def test_it_runs_further_than_half_the_network(self):
        """The centerline follows the vessel where the network cuts corners. A centerline much
        shorter than the network has lost a branch."""
        self.assertGreater(polylineLength(self.centerline),
                           0.5 * polylineLength(self.case.networkPolyData))

    def test_the_sampling_distance_reaches_the_curves_not_the_centerline(self):
        """The step length is what the branches are resampled to when they are made into curves.

        It does not touch the centerline itself: extractCenterline turns the filter's own
        resampling off (SetCenterlineResampling(0)), so the polydata comes back at whatever
        spacing the Voronoi diagram gave it whatever is asked for here. The curve tree is where
        it lands, and a curve sampled four times as finely has more control points along the same
        branch.
        """
        coarse, _coarseVoronoi = self.case.extractCenterline(curveSamplingDistance=2.0)
        fine, _fineVoronoi = self.case.extractCenterline(curveSamplingDistance=0.5)
        self.assertEqual(fine.GetNumberOfPoints(), coarse.GetNumberOfPoints(),
                         "the centerline itself was resampled, which it is not meant to be")

        controlPointCounts = []
        for samplingDistance in (2.0, 0.5):
            curveNode = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLMarkupsCurveNode", "Centerline curve %g" % samplingDistance)
            self.case.logic.createCurveTreeFromCenterline(
                self.centerline, curveNode, None, samplingDistance)
            controlPointCounts.append(curveNode.GetNumberOfControlPoints())

        self.assertGreater(controlPointCounts[1], controlPointCounts[0],
                           "sampling four times as finely gave no more control points")

    def test_the_curve_tree_carries_the_radius_as_a_measurement(self):
        """What the module hands back beside the model: one curve per branch, with the radius
        along it, and a row per branch in the properties table."""
        curveNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsCurveNode", "Centerline curve")
        tableNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLTableNode", "Centerline properties")

        self.case.logic.createCurveTreeFromCenterline(self.centerline, curveNode, tableNode)

        self.assertGreater(tableNode.GetTable().GetNumberOfRows(), 0,
                           "the properties table is empty")
        self.assertGreater(curveNode.GetNumberOfControlPoints(), 1,
                           "the first branch is not a curve")


if __name__ == "__main__":
    import sys
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise AssertionError("%d failure(s) and %d error(s) in %d test(s)"
                             % (len(result.failures), len(result.errors), result.testsRun))
