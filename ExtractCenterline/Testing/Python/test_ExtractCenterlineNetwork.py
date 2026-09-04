"""The network method: a tree through the vessel, extracted straight from the surface.

It is the cheap answer, and the one the module uses to find where the vessel ends are before the
centerline proper is asked for. What it has to produce is a connected tree that reaches every end
of the vessel, and endpoints that lie on the surface rather than somewhere in the middle of it.
"""

import unittest

import numpy as np
import slicer
import vtk
from vtk.util.numpy_support import vtk_to_numpy

from ExtractCenterlineTestFixture import aortaCase, polylineLength


class ExtractCenterlineNetworkTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.case = aortaCase()

    def test_the_network_is_a_tree_of_line_cells(self):
        network = self.case.networkPolyData

        self.assertGreater(network.GetNumberOfPoints(), 0)
        self.assertGreater(network.GetNumberOfCells(), 0)
        self.assertEqual(network.GetNumberOfCells(), network.GetNumberOfLines(),
                         "the network holds cells that are not lines")
        self.assertGreater(polylineLength(network), 0.0)

    def test_the_network_stays_inside_the_vessel(self):
        """A centerline that leaves the surface is not a centerline. Checked as a bounding box
        test, which is loose but catches a tree built on the wrong geometry outright."""
        network = self.case.networkPolyData
        surfaceBounds = self.case.preprocessedPolyData.GetBounds()
        networkBounds = network.GetBounds()

        for axis in range(3):
            self.assertGreaterEqual(networkBounds[2 * axis], surfaceBounds[2 * axis] - 1e-3)
            self.assertLessEqual(networkBounds[2 * axis + 1], surfaceBounds[2 * axis + 1] + 1e-3)

    def test_an_endpoint_is_found_for_every_vessel_end(self):
        """The aorta surface has one inlet and two iliac outlets, and the largest radius end - the
        inlet - is put first so that a caller can tell it from the outlets."""
        positions = self.case.endpointPositions

        self.assertGreaterEqual(len(positions), 3)
        for position in positions:
            self.assertEqual(len(position), 3)

        # every endpoint is a point of the network, not somewhere off it
        networkPoints = vtk_to_numpy(self.case.networkPolyData.GetPoints().GetData())
        for position in positions:
            distance = np.min(np.linalg.norm(networkPoints - np.asarray(position), axis=1))
            self.assertLess(distance, 1e-3, "endpoint %s is not on the network" % (position,))

    def test_endpoints_are_far_apart(self):
        """Two endpoints at the same vessel end would have the module cut it twice."""
        positions = np.asarray(self.case.endpointPositions)
        distances = np.linalg.norm(positions[:, None, :] - positions[None, :, :], axis=2)
        np.fill_diagonal(distances, np.inf)

        self.assertGreater(distances.min(), 1.0,
                           "two endpoints are within a millimetre of each other")

    def test_a_start_point_puts_the_nearest_end_first(self):
        """Asking for a start point is how a caller says which end is the inlet, so that end has
        to come back first however the network was walked."""
        positions = self.case.endpointPositions
        chosen = positions[-1]

        reordered = self.case.logic.getEndPoints(self.case.networkPolyData,
                                                 startPointPosition=chosen)

        self.assertGreaterEqual(len(reordered), 3)
        self.assertLess(float(np.linalg.norm(np.asarray(reordered[0]) - np.asarray(chosen))), 1e-3,
                        "the end nearest the requested start point did not come back first")

    def test_the_network_can_carry_its_geometry(self):
        """With computeGeometry on, the network arrives with the per-point arrays the properties
        table is built from."""
        network = self.case.logic.extractNetwork(
            self.case.preprocessedPolyData, self.case.endPointsMarkupsNode, computeGeometry=True)

        self.assertGreater(network.GetNumberOfPoints(), 0)
        self.assertIsNotNone(network.GetPointData().GetArray("Radius"),
                             "the network carries no radius")

    def test_network_properties_describe_every_branch(self):
        network = self.case.logic.extractNetwork(
            self.case.preprocessedPolyData, self.case.endPointsMarkupsNode, computeGeometry=True)
        tableNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLTableNode", "Network properties")

        self.case.logic.addNetworkProperties(network, tableNode)

        table = tableNode.GetTable()
        self.assertGreater(table.GetNumberOfRows(), 0, "the properties table is empty")
        self.assertGreater(table.GetNumberOfColumns(), 0)


if __name__ == "__main__":
    import sys
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise AssertionError("%d failure(s) and %d error(s) in %d test(s)"
                             % (len(result.failures), len(result.errors), result.testsRun))
