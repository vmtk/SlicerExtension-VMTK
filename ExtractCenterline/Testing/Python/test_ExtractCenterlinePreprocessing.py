"""Getting a surface into a state the centerline extraction can work on.

The extraction builds a Voronoi diagram of the surface, which grows with the number of points, so
a surface has to be decimated before it is affordable. Its topology matters too: a non-manifold
edge is a place the surface is not a surface, and the extraction has no answer there.
"""

import unittest

import slicer
import vtk

from ExtractCenterlineTestFixture import aortaCase


class ExtractCenterlinePreprocessingTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.case = aortaCase()

    def test_decimation_reaches_about_the_number_of_points_asked_for(self):
        original = self.case.inputPolyData

        for targetNumberOfPoints in (2000.0, 5000.0):
            with self.subTest(targetNumberOfPoints=targetNumberOfPoints):
                decimated = self.case.logic.preprocess(original, targetNumberOfPoints, 4.0, False)

                self.assertGreater(decimated.GetNumberOfPoints(), 0)
                self.assertLess(decimated.GetNumberOfPoints(), original.GetNumberOfPoints())
                # Decimation stops when it can go no further without changing the shape, so the
                # target is an upper bound rather than a promise; twice it is the check that the
                # number asked for was actually aimed at.
                self.assertLess(decimated.GetNumberOfPoints(), 2.0 * targetNumberOfPoints)

    def test_a_target_above_the_input_leaves_it_alone(self):
        """Nothing is decimated when there is nothing to gain, which is why turning preprocessing
        on for an already coarse surface is a no-op rather than a further loss of detail."""
        original = self.case.inputPolyData

        untouched = self.case.logic.preprocess(
            original, 10.0 * original.GetNumberOfPoints(), 4.0, False)

        self.assertGreaterEqual(untouched.GetNumberOfPoints(), original.GetNumberOfPoints())

    def test_subdividing_adds_points(self):
        original = self.case.inputPolyData

        plain = self.case.logic.preprocess(original, 5000.0, 4.0, False)
        subdivided = self.case.logic.preprocess(original, 5000.0, 4.0, True)

        self.assertGreater(subdivided.GetNumberOfPoints(), plain.GetNumberOfPoints())

    def test_the_preprocessed_surface_keeps_the_shape_of_the_vessel(self):
        """Decimation may remove points but must not move the surface: the bounds have to agree
        with the input's to within a fraction of the vessel."""
        original = self.case.inputPolyData
        decimated = self.case.preprocessedPolyData
        span = max(original.GetBounds()[2 * axis + 1] - original.GetBounds()[2 * axis]
                   for axis in range(3))

        for index in range(6):
            self.assertAlmostEqual(decimated.GetBounds()[index], original.GetBounds()[index],
                                   delta=0.05 * span)

    def test_a_clean_surface_has_no_non_manifold_edges(self):
        """The check the module runs before extracting, and what it reports when it finds one."""
        edges = vtk.vtkPolyData()

        positions = self.case.logic.extractNonManifoldEdges(self.case.preprocessedPolyData, edges)

        self.assertEqual(positions, [], "the sample vessel is not a clean surface")
        self.assertEqual(edges.GetNumberOfCells(), 0)

    def test_a_non_manifold_edge_is_found_and_placed(self):
        """Three triangles on one edge, which is what a surface that folds back on itself looks
        like locally. The module has to find it and say where it is."""
        points = vtk.vtkPoints()
        for position in ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1)):
            points.InsertNextPoint(*position)
        polys = vtk.vtkCellArray()
        for triangle in ((0, 1, 2), (0, 1, 3), (0, 1, 4)):
            polys.InsertNextCell(3, triangle)
        surface = vtk.vtkPolyData()
        surface.SetPoints(points)
        surface.SetPolys(polys)
        edges = vtk.vtkPolyData()

        positions = self.case.logic.extractNonManifoldEdges(surface, edges)

        self.assertEqual(len(positions), 1, "the shared edge was not reported")
        self.assertEqual(edges.GetNumberOfCells(), 1)
        # the edge runs from (0,0,0) to (1,0,0), so its middle is halfway along x
        self.assertAlmostEqual(positions[0][0], 0.5, delta=1e-6)


if __name__ == "__main__":
    import sys
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise AssertionError("%d failure(s) and %d error(s) in %d test(s)"
                             % (len(result.failures), len(result.errors), result.testsRun))
