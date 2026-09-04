"""Growing a tube out of each clipped vessel end, so that a solver's inlet condition is applied
somewhere the flow has settled rather than at the cut itself.

What is checked here is that an extension is grown at all, that each way of blending the original
cross-section into the extension's produces one, and that a length asked for at one vessel end is
applied to that end and to no other.
"""

import unittest

import numpy as np
import vtk
from vtk.util.numpy_support import vtk_to_numpy

from ClipVesselTestFixture import aortaCase


EXTENSION_RATIO = 2.0
TRANSITION_RATIO = 0.5

# Each way of blending the clipped cross-section into the extension's, and whether the extension
# is to end up circular. The last pair is the same blend over a cross-section left as it was.
TRANSITION_OPTIONS = [("LINEAR", True), ("THIN_PLATE_SPLINE", True), ("RAMP", True), ("RAMP", False)]


def describe(transitionMethod, transitionToCircularCrossSection):
    return "%s%s" % (transitionMethod,
                     "" if transitionToCircularCrossSection else ", preserved cross-section")


def extensionTipDistance(polyData, origin, normal, radius):
    """How far the surface reaches beyond a clip plane along its outward normal, within a cylinder
    of twice the local vessel radius around the extension axis.

    The reach is measured near the extension itself because a clip plane is infinite and oblique:
    distant parts of the vessel lie beyond it too, and the localized clipping methods leave them
    there.
    """
    offsets = vtk_to_numpy(polyData.GetPoints().GetData()) - np.asarray(origin)
    heights = offsets.dot(np.asarray(normal))
    lateralDistances = np.linalg.norm(offsets - np.outer(heights, np.asarray(normal)), axis=1)
    return float(np.max(heights[lateralDistances < 2.0 * radius]))


class ClipVesselFlowExtensionsTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.case = aortaCase()
        cls.clippedOnly = cls.case.clip(cap=True, addFlowExtensions=False, labelModelFaces=False)

    def test_every_transition_method_grows_an_extension(self):
        """Whatever the blend, the model has to come out larger than the plain clipped one: that
        is what says an extension was grown rather than silently skipped."""
        case = self.case
        clippedDiagonal = vtk.vtkBoundingBox(self.clippedOnly.GetBounds()).GetDiagonalLength()

        for transitionMethod, toCircular in TRANSITION_OPTIONS:
            with self.subTest(transition=describe(transitionMethod, toCircular)):
                extended = case.logic.clipVessel(
                    case.preprocessedPolyData, case.centerlineModelNode, case.clipPointsMarkupsNode,
                    True, True, EXTENSION_RATIO, "BOUNDARY_NORMAL",
                    transitionRatio=TRANSITION_RATIO, transitionMethod=transitionMethod,
                    transitionToCircularCrossSection=toCircular)

                self.assertIsNotNone(extended)
                self.assertGreater(extended.GetNumberOfCells(), 0)
                self.assertEqual(case.logic.lastUnclippedPoints, [])
                self.assertGreater(vtk.vtkBoundingBox(extended.GetBounds()).GetDiagonalLength(),
                                   clippedDiagonal)

    def test_a_length_asked_for_at_one_end_reaches_no_other(self):
        """A scale factor is given per clip point, so scaling the inlet must leave the outlets the
        common length.

        Clipped with the infinite plane method so that each cut removes the whole end piece: the
        localized methods can leave slivers of the original vessel end beyond the clip plane,
        which would be measured as extension length.
        """
        case = self.case
        inletScaleFactor = 2.5
        inletPointId = case.clipPointsMarkupsNode.GetNthControlPointID(0)

        def clipWith(extensionScaleFactors):
            return case.logic.clipVessel(
                case.preprocessedPolyData, case.centerlineModelNode, case.clipPointsMarkupsNode,
                False, True, EXTENSION_RATIO, "BOUNDARY_NORMAL", clippingMethod="PLANE",
                transitionRatio=TRANSITION_RATIO, transitionMethod="RAMP",
                extensionScaleFactors=extensionScaleFactors)

        unscaled = clipWith(None)
        scaled = clipWith({inletPointId: inletScaleFactor})
        self.assertEqual(case.logic.lastUnclippedPoints, [])

        for index in range(case.numberOfClipPoints):
            with self.subTest(clipPoint=index):
                origin, normal, radius = case.clipPlanes[index]
                unscaledLength = extensionTipDistance(unscaled, origin, normal, radius)
                scaledLength = extensionTipDistance(scaled, origin, normal, radius)
                if index == 0:
                    # Extensions are built in whole layers, so the length only matches to within
                    # a layer.
                    self.assertGreater(scaledLength, 0.8 * inletScaleFactor * unscaledLength)
                    self.assertLess(scaledLength, 1.2 * inletScaleFactor * unscaledLength)
                else:
                    self.assertAlmostEqual(scaledLength, unscaledLength, delta=0.01)


if __name__ == "__main__":
    import sys
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise AssertionError("%d failure(s) and %d error(s) in %d test(s)"
                             % (len(result.failures), len(result.errors), result.testsRun))
