"""Closing the ends of a real vessel, with each of the shapes the module can close them with.

test_ClipVesselCapMethods.py asks what the cappers do to a tube; this asks what they do to the
aorta, through the module's own pipeline. What every method has to produce is the same: a
watertight surface of triangles, facing outward, carrying no normals of its own, with each cap
a face in its own right. What they may differ in is the shape of the cap, and only a smooth cap
given enough roundness may reach out of the plane of the cut it closes.
"""

import unittest

import numpy as np
import vtk
from vtk.util.numpy_support import vtk_to_numpy

from ClipVesselTestFixture import aortaCase


# Every capping method, and the roundness to give it. Smooth appears twice: flat, like the other
# two, and domed, which is the one case that may leave the plane of the cut.
CAP_METHODS = [("CENTERPOINT", 0.0), ("SIMPLE", 0.0), ("SMOOTH", 0.0), ("SMOOTH", 2.0)]


def describe(capMethod, capRoundness):
    return capMethod if capMethod != "SMOOTH" else "%s, roundness %g" % (capMethod, capRoundness)


def openBoundaryEdgeCount(polyData):
    edges = vtk.vtkFeatureEdges()
    edges.SetInputData(polyData)
    edges.BoundaryEdgesOn()
    edges.FeatureEdgesOff()
    edges.NonManifoldEdgesOff()
    edges.ManifoldEdgesOff()
    edges.Update()
    return edges.GetOutput().GetNumberOfCells()


class ClipVesselCappingOnAVesselTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.case = aortaCase()
        cls.capped = {}
        for capMethod, capRoundness in CAP_METHODS:
            cls.capped[describe(capMethod, capRoundness)] = cls.case.logic.clipVessel(
                cls.case.preprocessedPolyData, cls.case.centerlineModelNode,
                cls.case.clipPointsMarkupsNode, True, False, 2.0, "BOUNDARY_NORMAL",
                clippingMethod="PLANE_PATCH", labelModelFaces=True,
                capMethod=capMethod, capConstraintFactor=capRoundness)

    def test_every_method_closes_the_vessel_with_triangles(self):
        for description, output in self.capped.items():
            with self.subTest(capMethod=description):
                self.assertEqual(output.GetPolys().IsHomogeneous(), 3, "a cell is not a triangle")
                self.assertEqual(output.GetNumberOfCells(), output.GetNumberOfPolys())
                self.assertEqual(openBoundaryEdgeCount(output), 0, "the surface is not closed")

    def test_every_method_winds_its_caps_outward(self):
        """Re-orienting the output must find nothing to re-wind. Two of the three cappers wind
        their caps inwards on their own, so without the fix in capSurface the caps would render
        as though lit from inside."""
        for description, output in self.capped.items():
            with self.subTest(capMethod=description):
                oriented = vtk.vtkPolyDataNormals()
                oriented.SetInputData(output)
                oriented.ComputePointNormalsOff()
                oriented.ComputeCellNormalsOn()
                oriented.ConsistencyOn()
                oriented.AutoOrientNormalsOn()
                oriented.SplittingOff()
                oriented.Update()
                self.assertTrue(np.array_equal(
                    vtk_to_numpy(output.GetPolys().GetConnectivityArray()),
                    vtk_to_numpy(oriented.GetOutput().GetPolys().GetConnectivityArray())))

    def test_no_normals_survive_capping(self):
        """The simple capper hands its cap vertices the normals the vessel wall left on them,
        which shades the cap as though it were wall."""
        for description, output in self.capped.items():
            with self.subTest(capMethod=description):
                for attributes in (output.GetPointData(), output.GetCellData()):
                    self.assertIsNone(attributes.GetNormals())
                    self.assertIsNone(attributes.GetArray("Normals"))

    def test_every_cap_is_a_face_of_its_own(self):
        expected = set(range(1, self.case.numberOfClipPoints + 2))
        for description, output in self.capped.items():
            with self.subTest(capMethod=description):
                faceIds = vtk_to_numpy(output.GetCellData().GetArray("ModelFaceID"))
                self.assertEqual(set(int(value) for value in np.unique(faceIds)), expected)

    def test_a_cap_of_no_roundness_is_flat(self):
        """Measured as the spread of the cap's points along the normal of their own best fit
        plane, against the width of the cap itself, so that it says "flat" rather than "small"."""
        for capMethod, capRoundness in CAP_METHODS:
            if capRoundness != 0.0:
                continue
            description = describe(capMethod, capRoundness)
            output = self.capped[description]
            faceIds = vtk_to_numpy(output.GetCellData().GetArray("ModelFaceID"))
            points = vtk_to_numpy(output.GetPoints().GetData())
            for capFaceId in range(2, self.case.numberOfClipPoints + 2):
                with self.subTest(capMethod=description, capFaceId=capFaceId):
                    capPointIds = set()
                    for cellId in np.nonzero(faceIds == capFaceId)[0]:
                        cell = output.GetCell(int(cellId))
                        for pointIndex in range(cell.GetNumberOfPoints()):
                            capPointIds.add(cell.GetPointId(pointIndex))
                    self.assertGreater(len(capPointIds), 3, "cap %d has no cells" % capFaceId)
                    capPoints = points[sorted(capPointIds)]
                    centered = capPoints - capPoints.mean(axis=0)
                    singularValues, rightVectors = np.linalg.svd(centered)[1:]
                    outOfPlane = np.abs(centered @ rightVectors[-1]).max()
                    capWidth = singularValues[0]
                    self.assertLess(outOfPlane, 0.01 * capWidth,
                                    "%s cap %d is %g out of plane across a width of %g"
                                    % (description, capFaceId, outOfPlane, capWidth))

    def test_only_a_round_cap_reaches_past_the_vessel(self):
        """A flat cap adds nothing to the extent of the surface, whichever method made it, so all
        three agree with the centre point capper. Roundness is what changes that, and it has to be
        enough of it: a modest dome is still inside the bounding box of the vessel, which is set
        by the vessel rather than by its ends, so the box only grows once the cap reaches past it.
        """
        diagonals = {description: vtk.vtkBoundingBox(output.GetBounds()).GetDiagonalLength()
                     for description, output in self.capped.items()}

        self.assertAlmostEqual(diagonals["SIMPLE"], diagonals["CENTERPOINT"], delta=0.01)
        self.assertAlmostEqual(diagonals["SMOOTH, roundness 0"], diagonals["CENTERPOINT"], delta=0.01)
        self.assertGreater(diagonals["SMOOTH, roundness 2"], diagonals["CENTERPOINT"])


if __name__ == "__main__":
    import sys
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise AssertionError("%d failure(s) and %d error(s) in %d test(s)"
                             % (len(result.failures), len(result.errors), result.testsRun))
