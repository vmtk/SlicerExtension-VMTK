"""A hole no clip point accounts for must be filled into the face around it.

A single missing triangle leaves a three-point boundary that the capper closes just like a
vessel end. Turning that into a face of its own would hand a CFD setup a boundary condition
surface that is really a defect in the mesh, so the fill takes the id of the surface around it
instead.
"""

import unittest

import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy

import ClipVessel

from test_ClipVesselCellOrder import INLET_OUTLET, capAndLabel


def tubeWithMissingTriangles(numberOfAxialPoints=10, numberOfCircumferentialPoints=20, dropped=()):
    """An open tube with the numbered triangles left out, each leaving a hole in the wall."""
    points, polys = vtk.vtkPoints(), vtk.vtkCellArray()
    for axialIndex in range(numberOfAxialPoints):
        for circumferentialIndex in range(numberOfCircumferentialPoints):
            angle = 2 * np.pi * circumferentialIndex / numberOfCircumferentialPoints
            points.InsertNextPoint(np.cos(angle), np.sin(angle),
                                   10.0 * axialIndex / (numberOfAxialPoints - 1))
    triangleIndex = 0
    for axialIndex in range(numberOfAxialPoints - 1):
        for circumferentialIndex in range(numberOfCircumferentialPoints):
            first = axialIndex * numberOfCircumferentialPoints + circumferentialIndex
            second = (axialIndex * numberOfCircumferentialPoints
                      + (circumferentialIndex + 1) % numberOfCircumferentialPoints)
            for triangle in ([first, second, second + numberOfCircumferentialPoints],
                             [first, second + numberOfCircumferentialPoints,
                              first + numberOfCircumferentialPoints]):
                if triangleIndex not in dropped:
                    polys.InsertNextCell(3, triangle)
                triangleIndex += 1
    surface = vtk.vtkPolyData()
    surface.SetPoints(points)
    surface.SetPolys(polys)
    return surface


class DefectHoleTest(unittest.TestCase):

    def setUp(self):
        self.logic = ClipVessel.ClipVesselLogic()

    def labelTube(self, dropped=(), existingFaceIdsFor=None):
        surface = tubeWithMissingTriangles(dropped=dropped)
        existingFaceIds = None
        if existingFaceIdsFor is not None:
            values = existingFaceIdsFor(surface)
            faceIdArray = numpy_to_vtk(values, deep=True, array_type=vtk.VTK_INT)
            faceIdArray.SetName("ModelFaceID")
            surface.GetCellData().AddArray(faceIdArray)
            existingFaceIds = values.astype(np.int64)
        capped, assignments = capAndLabel(self.logic, surface, INLET_OUTLET, existingFaceIds)
        faceIds = vtk_to_numpy(capped.GetCellData().GetArray("ModelFaceID"))
        return assignments, sorted(int(value) for value in np.unique(faceIds))

    def test_a_clean_tube_gets_one_face_per_clip_point(self):
        assignments, faceIds = self.labelTube()

        self.assertEqual(len(assignments), 2)
        self.assertEqual(faceIds, [1, 2, 3])                # wall, inlet cap, outlet cap
        self.assertEqual([label for _faceId, label in assignments], ["Inlet", "Outlet"])

    def test_one_missing_triangle_does_not_become_a_face(self):
        assignments, faceIds = self.labelTube(dropped=(100,))

        self.assertEqual(len(assignments), 2)
        self.assertEqual(faceIds, [1, 2, 3], "the fill was given a face of its own")
        self.assertEqual([label for _faceId, label in assignments], ["Inlet", "Outlet"])

    def test_two_missing_triangles_far_apart_do_not_become_faces(self):
        assignments, faceIds = self.labelTube(dropped=(60, 300))

        self.assertEqual(len(assignments), 2)
        self.assertEqual(faceIds, [1, 2, 3])

    def test_a_hole_inside_a_labelled_patch_joins_that_patch(self):
        def upperHalfPatch(surface):
            cellCenters = vtk.vtkCellCenters()
            cellCenters.SetInputData(surface)
            cellCenters.Update()
            z = vtk_to_numpy(cellCenters.GetOutput().GetPoints().GetData())[:, 2]
            return np.where(z > 4.0, 7, 0).astype(np.int32)

        # cell 300 lies in the upper half, inside the patch
        assignments, faceIds = self.labelTube(dropped=(300,), existingFaceIdsFor=upperHalfPatch)

        self.assertEqual(self.logic.lastExistingFaceIdMap, {7: 1})
        self.assertEqual(self.logic.lastWallFaceId, 2)
        self.assertEqual(len(assignments), 2)
        self.assertEqual(faceIds, [1, 2, 3, 4], "the fill was given a face of its own")


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
