"""Every way the module has of cutting a vessel end off.

The methods differ in what they cut with - an infinite plane, a plane bounded by a sphere, a
plane applied to one patch of the surface, a box - and so in how much of the vessel a single cut
can take away. What they must agree on is the result: every clip point makes a cut, and what
comes back is a surface that can be capped.
"""

import unittest

import vtk

from ClipVesselTestFixture import aortaCase


# Every clipping method the module offers, in the order the widget lists them.
CLIPPING_METHODS = ["PLANE", "PLANE_SPHERE", "PLANE_PATCH", "BOX"]


def openBoundaryEdgeCount(polyData):
    edges = vtk.vtkFeatureEdges()
    edges.SetInputData(polyData)
    edges.BoundaryEdgesOn()
    edges.FeatureEdgesOff()
    edges.NonManifoldEdgesOff()
    edges.ManifoldEdgesOff()
    edges.Update()
    return edges.GetOutput().GetNumberOfCells()


class ClipVesselClippingMethodsTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.case = aortaCase()

    def test_every_method_cuts_at_every_clip_point(self):
        """A clip point that made no cut is a vessel end left on the model, and the module says
        so in lastUnclippedPoints rather than quietly returning the surface it was given."""
        case = self.case
        for clippingMethod in CLIPPING_METHODS:
            with self.subTest(clippingMethod=clippingMethod):
                output = case.logic.clipVessel(
                    case.preprocessedPolyData, case.centerlineModelNode, case.clipPointsMarkupsNode,
                    True, False, 2.0, "BOUNDARY_NORMAL", clippingMethod=clippingMethod)

                self.assertIsNotNone(output)
                self.assertGreater(output.GetNumberOfCells(), 0)
                self.assertEqual(case.logic.lastUnclippedPoints, [])

    def test_a_planar_method_cuts_flat_and_caps_watertight(self):
        """The three methods that cut with a plane have to leave a planar boundary, because a cut
        that is not planar turns capping off - and then the output is not closed.

        PLANE_SPHERE is left out on purpose: its cut follows the sphere wherever the sphere is
        the active constraint, which is not planar and is not meant to be.
        """
        case = self.case
        for clippingMethod in [method for method in CLIPPING_METHODS if method != "PLANE_SPHERE"]:
            with self.subTest(clippingMethod=clippingMethod):
                output = case.logic.clipVessel(
                    case.preprocessedPolyData, case.centerlineModelNode, case.clipPointsMarkupsNode,
                    True, False, 2.0, "BOUNDARY_NORMAL", clippingMethod=clippingMethod)

                self.assertEqual(case.logic.lastPlanarityFailures, [])
                self.assertEqual(openBoundaryEdgeCount(output), 0,
                                 "the capped output is not closed (%s)" % clippingMethod)


if __name__ == "__main__":
    import sys
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise AssertionError("%d failure(s) and %d error(s) in %d test(s)"
                             % (len(result.failures), len(result.errors), result.testsRun))
