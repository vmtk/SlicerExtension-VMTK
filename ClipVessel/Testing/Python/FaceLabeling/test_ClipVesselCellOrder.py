"""Vert and line cells must not shift the face labels.

A vtkPolyData indexes its cells verts, lines, polys, strips, while vtkvmtkCapPolyData copies
only GetPolys(). Labels read off the surface by cell index therefore have to be trimmed to the
poly cells, or every one of them lands a cell out of step and the labelled patch scatters over
the surface. vtkCleanPolyData makes vert cells out of degenerate triangles, so this is not a
hypothetical input.
"""

import unittest

import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy

import ClipVessel


def openTube(numberOfAxialPoints=8, numberOfCircumferentialPoints=20, height=10.0, radius=1.0,
             numberOfVerts=0, numberOfLines=0):
    """A tube open at both ends, optionally carrying vert and line cells ahead of its polys."""
    points, polys = vtk.vtkPoints(), vtk.vtkCellArray()
    for axialIndex in range(numberOfAxialPoints):
        z = height * axialIndex / (numberOfAxialPoints - 1)
        for circumferentialIndex in range(numberOfCircumferentialPoints):
            angle = 2 * np.pi * circumferentialIndex / numberOfCircumferentialPoints
            points.InsertNextPoint(radius * np.cos(angle), radius * np.sin(angle), z)
    for axialIndex in range(numberOfAxialPoints - 1):
        for circumferentialIndex in range(numberOfCircumferentialPoints):
            first = axialIndex * numberOfCircumferentialPoints + circumferentialIndex
            second = (axialIndex * numberOfCircumferentialPoints
                      + (circumferentialIndex + 1) % numberOfCircumferentialPoints)
            polys.InsertNextCell(3, [first, second, second + numberOfCircumferentialPoints])
            polys.InsertNextCell(3, [first, second + numberOfCircumferentialPoints,
                                     first + numberOfCircumferentialPoints])
    surface = vtk.vtkPolyData()
    surface.SetPoints(points)
    surface.SetPolys(polys)
    if numberOfVerts:
        verts = vtk.vtkCellArray()
        for pointId in range(numberOfVerts):
            verts.InsertNextCell(1, [pointId])
        surface.SetVerts(verts)
    if numberOfLines:
        lines = vtk.vtkCellArray()
        for pointId in range(numberOfLines):
            lines.InsertNextCell(2, [pointId, pointId + 1])
        surface.SetLines(lines)
    return surface


def clipPointSpecification(index, label, origin, normal):
    return {"index": index, "label": label, "origin": tuple(origin), "normal": tuple(normal),
            "radius": 1.0}


INLET_OUTLET = [clipPointSpecification(0, "Inlet", (0.0, 0.0, 0.0), (0.0, 0.0, -1.0)),
                clipPointSpecification(1, "Outlet", (0.0, 0.0, 10.0), (0.0, 0.0, 1.0))]


def cellCentroids(surface):
    cellCenters = vtk.vtkCellCenters()
    cellCenters.SetInputData(surface)
    cellCenters.Update()
    return vtk_to_numpy(cellCenters.GetOutput().GetPoints().GetData())


def capAndLabel(logic, surface, planeSpecifications, existingFaceIds):
    """Cap and label the way clipVessel does: label each boundary with the clip point that opened
    it, so the capper puts that clip point's id on its cap."""
    wallCellEntityId = len(planeSpecifications) + 1
    surface, _ = logic.labelClipBoundaries(surface, planeSpecifications)
    boundaryCellEntityIds = [specification["index"] + 1 for specification in planeSpecifications]
    capped = logic.capSurface(surface, logic.capBoundaryIdsArrayName, wallCellEntityId,
                              boundaryCellEntityIds)
    assignments = logic.labelModelFaces(capped, planeSpecifications, "ModelFaceID",
                                        existingFaceIds, wallCellEntityId)
    return capped, assignments


class CellOrderTest(unittest.TestCase):

    def setUp(self):
        self.logic = ClipVessel.ClipVesselLogic()

    def assertLabelsStayWithTheirCells(self, numberOfVerts, numberOfLines):
        surface = openTube(numberOfVerts=numberOfVerts, numberOfLines=numberOfLines)

        # A patch labelled geometrically: the poly cells above the midpoint of the tube.
        centroids = cellCentroids(surface)
        patchValues = np.where(centroids[:, 2] > 7.0, 3, 1).astype(np.int32)
        faceIdArray = numpy_to_vtk(patchValues, deep=True, array_type=vtk.VTK_INT)
        faceIdArray.SetName("ModelFaceID")
        surface.GetCellData().AddArray(faceIdArray)

        # what clipVessel hands to labelModelFaces: the labels of the poly cells alone
        existingFaceIds = vtk_to_numpy(surface.GetCellData().GetArray("ModelFaceID")).astype(np.int64)
        firstPolyCell = surface.GetNumberOfVerts() + surface.GetNumberOfLines()
        existingFaceIds = existingFaceIds[firstPolyCell:firstPolyCell + surface.GetNumberOfPolys()]

        capped, assignments = capAndLabel(self.logic, surface, INLET_OUTLET, existingFaceIds)

        faceIds = vtk_to_numpy(capped.GetCellData().GetArray("ModelFaceID"))
        capFaceIds = [faceId for faceId, _label in assignments]
        isCap = np.isin(faceIds, capFaceIds)

        self.assertEqual(self.logic.lastExistingFaceIdMap, {1: 1, 3: 2})
        # the input labelled every cell, so no id is set aside for a wall
        self.assertIsNone(self.logic.lastWallFaceId)

        # face 2 is the compacted former id 3, and must still be exactly the cells above z = 7
        shouldBeFace2 = cellCentroids(capped)[:, 2] > 7.0
        misplaced = int(np.count_nonzero(((faceIds == 2) != shouldBeFace2) & ~isCap))
        self.assertEqual(misplaced, 0,
                         "%d of %d non-cap cells carry the wrong label with %d vert(s) and %d line(s)"
                         % (misplaced, int(np.count_nonzero(~isCap)), numberOfVerts, numberOfLines))

    def test_labels_are_placed_correctly_without_vert_or_line_cells(self):
        self.assertLabelsStayWithTheirCells(0, 0)

    def test_a_single_vert_cell_does_not_shift_the_labels(self):
        self.assertLabelsStayWithTheirCells(1, 0)

    def test_a_single_line_cell_does_not_shift_the_labels(self):
        self.assertLabelsStayWithTheirCells(0, 1)

    def test_several_vert_and_line_cells_do_not_shift_the_labels(self):
        self.assertLabelsStayWithTheirCells(3, 2)


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
