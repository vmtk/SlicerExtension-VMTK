"""The face id layout labelModelFaces() produces.

Faces the input already carried are compacted onto 1..K in ascending order of their original id,
the vessel wall takes the next id, and the caps follow it in clip point order. The surfaces here
are fabricated rather than clipped -- one small independent triangle per cell -- so that each case
is exactly the cell layout it is about, with nothing else in it.
"""

import unittest

import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy

import ClipVessel


def clipPointSpecification(index, label, origin, normal):
    return {"index": index, "label": label, "origin": tuple(origin), "normal": tuple(normal),
            "radius": 1.0}


INLET_OUTLET = [clipPointSpecification(0, "Inlet", (0, 0, 0), (0, 0, -1)),
                clipPointSpecification(1, "Outlet", (0, 0, 10), (0, 0, 1))]
INLET_ONLY = [clipPointSpecification(0, "Inlet", (0, 0, 0), (0, 0, -1))]


# A cell of the fabricated surface that came from the input rather than from a cap.
WALL = "wall"
# A cap closing a hole no clip point opened, which the labeler gives a fresh label above the
# clip points' own.
UNACCOUNTED_HOLE = "hole"


def layoutFor(inputFaceIds, firstFaceId):
    """(wallFaceId, firstCapFaceId) for a surface whose input cells carried inputFaceIds, the same
    way ClipVesselLogic.faceIdLayout() works it out. The tests state the ids of their caps relative
    to this, because that is what they are: a boundary is labelled with the face id its cap will
    take, so the two are the same numbering."""
    inputFaceIds = list(inputFaceIds or [])
    numberOfExistingFaces = len(set(value for value in inputFaceIds if value > 0))
    hasWallCells = not inputFaceIds or any(value <= 0 for value in inputFaceIds)
    wallFaceId = firstFaceId + numberOfExistingFaces
    return wallFaceId, wallFaceId + 1 if hasWallCells else wallFaceId


def capCellEntityIdsFor(cellPlan, firstCapFaceId, numberOfClipPoints):
    """The values the capper would have written into its private array for cellPlan, which lists
    WALL, a clip point index, or UNACCOUNTED_HOLE for each cell in turn."""
    wallCellEntityId = firstCapFaceId - 1
    ids = []
    for entry in cellPlan:
        if entry is WALL:
            ids.append(wallCellEntityId)
        elif entry is UNACCOUNTED_HOLE:
            # above every clip point's id, which is where the labeler puts a fresh label
            ids.append(firstCapFaceId + numberOfClipPoints + 7)
        else:
            ids.append(firstCapFaceId + entry)
    return ids


def makeSurface(capCellEntityIds, planeSpecifications, existingFaceIds=None,
                wallCellEntityId=None):
    """A surface standing in for a capped one, one independent triangle per cell.

    capCellEntityIds is what the capper would have written into the private array: wallCellEntityId
    for a cell that came from the input, and for a cap cell the label of the boundary it closes,
    which is the face id of that cap.

    Returns (surface, existingForCall). existingForCall is existingFaceIds trimmed to the cells that
    came from the input, which is what clipVessel passes: it reads those values off the surface
    *before* capping, so the array it hands over is shorter than the capped output. The capper drops
    all other cell data, so on a capped surface the face id array is genuinely absent -- only the
    uncapped case still carries it.
    """
    numberOfCells = len(capCellEntityIds) if capCellEntityIds is not None else len(existingFaceIds)
    points, polys = vtk.vtkPoints(), vtk.vtkCellArray()
    offsets = np.array([[0.02, 0.0, 0.0], [-0.01, 0.02, 0.0], [-0.01, -0.02, 0.0]])
    for cellIndex in range(numberOfCells):
        centroid = np.array([0.0, 0.0, float(cellIndex)])
        polys.InsertNextCell(3, [points.InsertNextPoint(*(centroid + offset)) for offset in offsets])
    surface = vtk.vtkPolyData()
    surface.SetPoints(points)
    surface.SetPolys(polys)

    existingForCall = None if existingFaceIds is None else np.asarray(existingFaceIds, dtype=np.int64)
    if capCellEntityIds is not None:
        capArray = numpy_to_vtk(np.asarray(capCellEntityIds, dtype=np.int64), deep=True,
                                array_type=vtk.VTK_ID_TYPE)
        capArray.SetName(ClipVessel.ClipVesselLogic.capBoundaryIdsArrayName)
        surface.GetCellData().AddArray(capArray)
        if existingForCall is not None:
            inputCellCount = int(np.count_nonzero(np.asarray(capCellEntityIds) == wallCellEntityId))
            existingForCall = existingForCall[:inputCellCount]
    elif existingForCall is not None:
        # Uncapped: the array is still on the surface, so exercise the read-it-back path.
        faceIdArray = numpy_to_vtk(np.asarray(existingFaceIds, dtype=np.int32), deep=True,
                                   array_type=vtk.VTK_INT)
        faceIdArray.SetName("ModelFaceID")
        surface.GetCellData().AddArray(faceIdArray)
        existingForCall = None
    return surface, existingForCall


class FaceIdLayoutTest(unittest.TestCase):

    def setUp(self):
        self.logic = ClipVessel.ClipVesselLogic()

    def label(self, cellPlan, planeSpecifications, existingFaceIds=None,
              faceIdArrayName="ModelFaceID"):
        """Label a fabricated surface the way clipVessel does.

        cellPlan lists what each cell is - WALL, the index of the clip point whose cap it belongs
        to, or UNACCOUNTED_HOLE - or is None for a surface that was never capped. The face id
        layout is worked out first, from the ids the input cells carried, and both the cap labels
        and labelModelFaces() are given it, exactly as clipVessel does.
        """
        inputFaceIds = None
        if existingFaceIds is not None:
            inputCellCount = (len(existingFaceIds) if cellPlan is None
                              else sum(1 for entry in cellPlan if entry is WALL))
            inputFaceIds = list(existingFaceIds)[:inputCellCount]
        wallFaceId, firstCapFaceId = layoutFor(inputFaceIds, self.logic.firstFaceId)
        wallCellEntityId = firstCapFaceId - 1

        capCellEntityIds = None if cellPlan is None else capCellEntityIdsFor(
            cellPlan, firstCapFaceId, len(planeSpecifications))
        surface, existingForCall = makeSurface(capCellEntityIds, planeSpecifications,
                                               existingFaceIds, wallCellEntityId)
        assignments = self.logic.labelModelFaces(
            surface, planeSpecifications, faceIdArrayName, existingForCall,
            wallCellEntityId if capCellEntityIds is not None else 0,
            wallFaceId=wallFaceId, firstCapFaceId=firstCapFaceId)
        faceIds = list(vtk_to_numpy(surface.GetCellData().GetArray(faceIdArrayName)))
        return surface, assignments, faceIds

    def test_without_pre_existing_labels_the_wall_is_1_and_caps_follow_clip_point_order(self):
        # The cap cells are deliberately in the opposite order to the clip points: each carries the
        # face id of the boundary it closes, so its position is irrelevant.
        surface, assignments, faceIds = self.label([WALL, WALL, WALL, 1, 0], INLET_OUTLET)

        self.assertEqual(faceIds[:3], [1, 1, 1], "wall cells")
        self.assertEqual(faceIds[3], 3, "the cap carrying the Outlet's id")
        self.assertEqual(faceIds[4], 2, "the cap carrying the Inlet's id")
        self.assertEqual(self.logic.lastWallFaceId, 1)
        self.assertEqual(self.logic.lastExistingFaceIdMap, {})
        self.assertEqual(assignments, [(2, "Inlet"), (3, "Outlet")])
        self.assertTrue(surface.GetCellData().GetArray("ModelFaceID").IsA("vtkIntArray"))
        self.assertEqual(surface.GetCellData().GetScalars().GetName(), "ModelFaceID")
        self.assertIsNone(surface.GetCellData().GetArray(self.logic.capBoundaryIdsArrayName),
                          "the private cap array leaked into the output")

    def test_a_pre_existing_face_is_never_fused_with_a_cap(self):
        # A patch already carrying id 2, which is also what the first cap would be numbered.
        _surface, assignments, faceIds = self.label([WALL, WALL, WALL, 0, 1], INLET_OUTLET,
                                                    [2, 2, 0, 0, 0])

        self.assertEqual(self.logic.lastExistingFaceIdMap, {2: 1})
        self.assertEqual(faceIds[:2], [1, 1], "the pre-existing patch")
        self.assertEqual(faceIds[2], 2, "the wall")
        self.assertEqual(self.logic.lastWallFaceId, 2)
        self.assertEqual(faceIds[3], 3, "the inlet cap, fused into the patch if this fails")
        self.assertEqual(faceIds[4], 4, "the outlet cap")
        self.assertEqual(assignments, [(3, "Inlet"), (4, "Outlet")])
        self.assertEqual(len(set(faceIds)), 4, "every face must be distinct")

    def test_a_lone_pre_existing_face_compacts_to_1_and_pushes_the_wall_to_2(self):
        _surface, assignments, faceIds = self.label([WALL, WALL, 0, 1], INLET_OUTLET, [10, 0, 0, 0])

        self.assertEqual(self.logic.lastExistingFaceIdMap, {10: 1})
        self.assertEqual(self.logic.lastWallFaceId, 2)
        self.assertEqual(faceIds, [1, 2, 3, 4])
        self.assertEqual(assignments[0], (3, "Inlet"))

    def test_several_pre_existing_faces_compact_in_ascending_order_of_their_original_id(self):
        _surface, assignments, faceIds = self.label([WALL, WALL, WALL, WALL, 0, 1], INLET_OUTLET,
                                                    [50, 7, 22, 0, 0, 0])

        self.assertEqual(self.logic.lastExistingFaceIdMap, {7: 1, 22: 2, 50: 3})
        self.assertEqual(faceIds[:4], [3, 1, 2, 4])
        self.assertEqual(self.logic.lastWallFaceId, 4)
        self.assertEqual(assignments, [(5, "Inlet"), (6, "Outlet")])

    def test_an_input_that_labels_every_cell_sets_no_id_aside_for_a_wall(self):
        _surface, assignments, faceIds = self.label([WALL, WALL, 0], INLET_ONLY, [1, 4, 0])

        self.assertEqual(self.logic.lastExistingFaceIdMap, {1: 1, 4: 2})
        self.assertIsNone(self.logic.lastWallFaceId)
        self.assertEqual(assignments, [(3, "Inlet")], "the cap must take the next id, not skip one")
        self.assertEqual(sorted(set(faceIds)), [1, 2, 3], "a phantom face was left in the numbering")

    def test_mis_sized_existing_labels_are_dropped_rather_than_smeared(self):
        wallFaceId, firstCapFaceId = layoutFor(None, self.logic.firstFaceId)
        wall = firstCapFaceId - 1
        surface, _existingForCall = makeSurface(
            capCellEntityIdsFor([WALL, WALL, 0], firstCapFaceId, len(INLET_ONLY)),
            INLET_ONLY, wallCellEntityId=wall)
        # five values for two non-cap cells: they cannot be matched up cell for cell
        assignments = self.logic.labelModelFaces(surface, INLET_ONLY, "ModelFaceID",
                                                 np.array([7, 7, 7, 7, 7], dtype=np.int64), wall,
                                                 wallFaceId=wallFaceId,
                                                 firstCapFaceId=firstCapFaceId)
        faceIds = list(vtk_to_numpy(surface.GetCellData().GetArray("ModelFaceID")))

        self.assertEqual(self.logic.lastExistingFaceIdMap, {})
        self.assertEqual(faceIds, [1, 1, 2], "labels were applied to the wrong cells")
        self.assertEqual(assignments, [(2, "Inlet")])

    def test_non_positive_existing_ids_count_as_unlabelled(self):
        _surface, _assignments, faceIds = self.label([WALL, WALL, 0], INLET_ONLY, [0, -3, 0])

        self.assertEqual(faceIds[:2], [1, 1], "0 and -3 must both count as wall")
        self.assertEqual(self.logic.lastExistingFaceIdMap, {})

    def test_an_uncapped_surface_is_labelled_from_the_array_it_carries(self):
        _surface, assignments, faceIds = self.label(None, INLET_ONLY, [10, 0])

        self.assertEqual(self.logic.lastExistingFaceIdMap, {10: 1})
        self.assertEqual(faceIds, [1, 2])
        self.assertEqual(assignments, [], "an uncapped surface has no caps to assign")

    def test_a_clip_point_that_made_no_cut_leaves_its_id_unused(self):
        threePoints = [clipPointSpecification(0, "First", (0, 0, 0), (0, 0, -1)),
                       clipPointSpecification(1, "NoCut", (0, 0, 10), (1, 0, 0)),
                       clipPointSpecification(2, "Third", (0, 0, 20), (0, 0, 1))]
        # only the first and third clip points opened a boundary
        _surface, assignments, faceIds = self.label([WALL, 0, 2], threePoints)

        self.assertEqual(faceIds[1:], [2, 4], "id 3 belongs to NoCut and must be left unused")
        self.assertEqual(assignments, [(2, "First"), (4, "Third")])

    def test_a_hole_no_clip_point_opened_joins_the_face_around_it(self):
        # the last cell is a cap closing a hole no clip point opened, which the labeler gave a
        # fresh label above the clip points' own
        _surface, assignments, faceIds = self.label([WALL, WALL, 0, 1, UNACCOUNTED_HOLE],
                                                    INLET_OUTLET)

        self.assertEqual(len(assignments), 2, "the fill was given a face of its own")
        self.assertEqual(sorted(set(faceIds)), [1, 2, 3], "no fourth face may be invented")

    def test_the_ids_are_written_under_the_array_name_given(self):
        surface, _assignments, faceIds = self.label([WALL, 0], INLET_ONLY,
                                                    faceIdArrayName="CellEntityIds")

        self.assertEqual(faceIds, [1, 2])
        self.assertIsNone(surface.GetCellData().GetArray("ModelFaceID"))


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
