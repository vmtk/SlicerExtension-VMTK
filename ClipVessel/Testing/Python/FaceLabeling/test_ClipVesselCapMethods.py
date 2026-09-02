"""The choice of cap method must not change which cut a cap is named after.

A cap carries the id of the clip point whose cut opened the boundary it closes, which is what
makes the face labels mean anything. That id reaches the cap through the boundary labels on the
surface, and until every capping filter read them it was only the default centre-point capper
that could be trusted with it: the other two numbered their caps by the order the boundaries came
out of the extractor, so picking a different cap shape silently renamed the faces.
"""

import unittest

import numpy as np
import vtk
from vtk.util.numpy_support import vtk_to_numpy
import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry

import ClipVessel

CELL_ENTITY_IDS = "CellEntityIds"
WALL_ID = 9


def openTube(numberOfAxialPoints=8, numberOfCircumferentialPoints=20, height=10.0, radius=1.0):
    """A tube open at both ends, so it has one boundary at each."""
    points, polys = vtk.vtkPoints(), vtk.vtkCellArray()
    for axialIndex in range(numberOfAxialPoints):
        z = height * axialIndex / (numberOfAxialPoints - 1)
        for circumferentialIndex in range(numberOfCircumferentialPoints):
            angle = 2 * np.pi * circumferentialIndex / numberOfCircumferentialPoints
            points.InsertNextPoint(radius * np.cos(angle), radius * np.sin(angle), z)
    for axialIndex in range(numberOfAxialPoints - 1):
        for circumferentialIndex in range(numberOfCircumferentialPoints):
            first = axialIndex * numberOfCircumferentialPoints + circumferentialIndex
            second = axialIndex * numberOfCircumferentialPoints + (circumferentialIndex + 1) % numberOfCircumferentialPoints
            third = (axialIndex + 1) * numberOfCircumferentialPoints + circumferentialIndex
            fourth = (axialIndex + 1) * numberOfCircumferentialPoints + (circumferentialIndex + 1) % numberOfCircumferentialPoints
            polys.InsertNextCell(3, [first, second, fourth])
            polys.InsertNextCell(3, [first, fourth, third])
    surface = vtk.vtkPolyData()
    surface.SetPoints(points)
    surface.SetPolys(polys)
    return surface


class ClipVesselCapMethodsTest(unittest.TestCase):

    def setUp(self):
        self.logic = ClipVessel.ClipVesselLogic()
        labeler = vtkvmtkComputationalGeometry.vtkvmtkPolyDataBoundaryLabeler()
        labeler.SetInputData(openTube())
        labeler.SetBoundaryLabelsArrayName(self.logic.boundaryLabelsArrayName)
        labeler.SetBoundaryPointOrderArrayName(self.logic.boundaryPointOrderArrayName)
        labeler.Update()
        self.labelledSurface = labeler.GetOutput()
        self.boundaryLabels = sorted(labeler.GetBoundaryLabels().GetId(i)
                                     for i in range(labeler.GetNumberOfBoundaries()))
        self.assertEqual(self.boundaryLabels, [0, 1])

    def capIds(self, capMethod):
        capped = self.logic.capSurface(self.labelledSurface, CELL_ENTITY_IDS, WALL_ID,
                                       capMethod=capMethod)
        array = capped.GetCellData().GetArray(CELL_ENTITY_IDS)
        self.assertIsNotNone(array, "%s produced no %s array" % (capMethod, CELL_ENTITY_IDS))
        return sorted(set(int(value) for value in vtk_to_numpy(array)))

    def test_every_method_names_a_cap_after_the_boundary_it_closes(self):
        """A cap carries the label of the boundary it closes, whichever filter built it, so the
        cut a cap belongs to is readable off the cap with nothing to translate."""
        for capMethod in ClipVessel._CAP_METHOD_IDS:
            with self.subTest(capMethod=capMethod):
                self.assertEqual(self.capIds(capMethod),
                                 sorted(set([WALL_ID]) | set(self.boundaryLabels)))

    def test_every_method_caps_every_boundary(self):
        """Whatever the shape of the cap, the surface comes back closed: two caps for the two
        ends, and no open boundary left."""
        for capMethod in ClipVessel._CAP_METHOD_IDS:
            with self.subTest(capMethod=capMethod):
                capped = self.logic.capSurface(self.labelledSurface, CELL_ENTITY_IDS, WALL_ID,
                                               capMethod=capMethod)
                featureEdges = vtk.vtkFeatureEdges()
                featureEdges.SetInputData(capped)
                featureEdges.BoundaryEdgesOn()
                featureEdges.FeatureEdgesOff()
                featureEdges.NonManifoldEdgesOff()
                featureEdges.ManifoldEdgesOff()
                featureEdges.Update()
                self.assertEqual(featureEdges.GetOutput().GetNumberOfCells(), 0,
                                 "%s left an open boundary" % capMethod)

    def test_an_unknown_method_falls_back_to_the_default(self):
        """A method the module does not know is a caller's mistake, not a reason to fail: it says
        so and caps as it would have anyway."""
        self.assertEqual(self.capIds("NO_SUCH_METHOD"),
                         self.capIds(ClipVessel._DEFAULT_CAP_METHOD))


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
