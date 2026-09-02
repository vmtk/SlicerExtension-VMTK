"""A remeshed cap must be uniform inside and still be the same cap on the outside.

Every capper meshes a boundary by following its rim: the centre point capper makes a fan of
slivers meeting at one interior point, the simple capper adds no interior point at all, and the
rings of a smooth cap crowd together towards its middle. Remeshing evens the cap out, but only if
it leaves everything else exactly as it was - the wall it is attached to, the rim it shares with
it, and the id that says which cut the cap belongs to. Those are what these check, because a
remesher let loose on the whole surface would quietly rebuild the vessel too, and one that did not
hold the rim would leave the surface open along it.
"""

import unittest

import numpy as np
import vtk
from vtk.util.numpy_support import vtk_to_numpy
import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry

import ClipVessel

from test_ClipVesselCapMethods import CELL_ENTITY_IDS, WALL_ID, openTube

# The tube the caps are cut into. Its cells are near equilateral - the axial spacing is set to
# match the circumferential one - so that "as finely as the surface around it" is a size the caps
# can be measured against, rather than one inherited from a stretched wall.
NUMBER_OF_CIRCUMFERENTIAL_POINTS = 20
RADIUS = 1.0
HEIGHT = 10.0
CIRCUMFERENTIAL_SPACING = 2 * np.pi * RADIUS / NUMBER_OF_CIRCUMFERENTIAL_POINTS
NUMBER_OF_AXIAL_POINTS = int(round(HEIGHT / CIRCUMFERENTIAL_SPACING)) + 1


def cellEntityIds(surface):
    return vtk_to_numpy(surface.GetCellData().GetArray(CELL_ENTITY_IDS)).astype(np.int64)


def cellPointIds(surface, cellId):
    pointIds = vtk.vtkIdList()
    surface.GetCellPoints(cellId, pointIds)
    return [pointIds.GetId(index) for index in range(pointIds.GetNumberOfIds())]


def pointIdsOf(surface, cellIds):
    """The ids of the points the given cells use."""
    pointIds = set()
    for cellId in cellIds:
        pointIds.update(cellPointIds(surface, int(cellId)))
    return pointIds


def interiorPointCount(surface, entityId):
    """How many points the entity has to itself: those no cell outside it uses.

    This is what tells a remeshed cap from a capped one at a glance - a fan has exactly one
    whatever its rim looks like, and a simple cap none at all.
    """
    entityIds = cellEntityIds(surface)
    own = pointIdsOf(surface, np.nonzero(entityIds == entityId)[0])
    shared = pointIdsOf(surface, np.nonzero(entityIds != entityId)[0])
    return len(own - shared)


def edgeLengthRatios(surface, entityId):
    """Longest over shortest edge of each cell of the entity: 1 for an equilateral triangle.

    Cell area says nothing here - a fan over a regular polygon is made of congruent slivers, so
    it is perfectly even by area while being as far from equilateral as its rim is from its
    centre. The shape of the cells is the thing that has to improve.
    """
    ratios = []
    for cellId in np.nonzero(cellEntityIds(surface) == entityId)[0]:
        points = [np.array(surface.GetPoint(pointId))
                  for pointId in cellPointIds(surface, int(cellId))]
        lengths = [np.linalg.norm(points[index] - points[(index + 1) % len(points)])
                   for index in range(len(points))]
        if min(lengths) > 0.0:
            ratios.append(max(lengths) / min(lengths))
    return np.array(ratios)


def meanEdgeLength(surface, entityId):
    lengths = []
    for cellId in np.nonzero(cellEntityIds(surface) == entityId)[0]:
        points = [np.array(surface.GetPoint(pointId))
                  for pointId in cellPointIds(surface, int(cellId))]
        lengths.extend(np.linalg.norm(points[index] - points[(index + 1) % len(points)])
                       for index in range(len(points)))
    return float(np.mean(lengths))


def openBoundaryCellCount(surface):
    featureEdges = vtk.vtkFeatureEdges()
    featureEdges.SetInputData(surface)
    featureEdges.BoundaryEdgesOn()
    featureEdges.FeatureEdgesOff()
    featureEdges.NonManifoldEdgesOff()
    featureEdges.ManifoldEdgesOff()
    featureEdges.Update()
    return featureEdges.GetOutput().GetNumberOfCells()


def pointCoordinates(surface, pointIds):
    """The coordinates of the given points, rounded, as a set that survives renumbering.

    The remesher hands back its own point array, so a wall point keeps neither its id nor its
    position in the array; where it is in space is the thing that must not have moved.
    """
    return set(tuple(round(coordinate, 9) for coordinate in surface.GetPoint(int(pointId)))
               for pointId in pointIds)


class ClipVesselCapRemeshingTest(unittest.TestCase):

    def setUp(self):
        self.logic = ClipVessel.ClipVesselLogic()
        labeler = vtkvmtkComputationalGeometry.vtkvmtkPolyDataBoundaryLabeler()
        labeler.SetInputData(openTube(numberOfAxialPoints=NUMBER_OF_AXIAL_POINTS,
                                      numberOfCircumferentialPoints=NUMBER_OF_CIRCUMFERENTIAL_POINTS,
                                      height=HEIGHT, radius=RADIUS))
        labeler.SetBoundaryLabelsArrayName(self.logic.boundaryLabelsArrayName)
        labeler.SetBoundaryPointOrderArrayName(self.logic.boundaryPointOrderArrayName)
        labeler.Update()
        self.labelledSurface = labeler.GetOutput()
        self.capIds = sorted(labeler.GetBoundaryLabels().GetId(index)
                             for index in range(labeler.GetNumberOfBoundaries()))
        self.assertEqual(self.capIds, [0, 1])

    def cappedSurface(self, capMethod=ClipVessel._DEFAULT_CAP_METHOD):
        return self.logic.capSurface(self.labelledSurface, CELL_ENTITY_IDS, WALL_ID,
                                     capMethod=capMethod)

    def remeshed(self, capMethod=ClipVessel._DEFAULT_CAP_METHOD, targetEdgeLength=0.0):
        return self.logic.remeshCaps(self.cappedSurface(capMethod), CELL_ENTITY_IDS,
                                     self.capIds, targetEdgeLength)

    def test_a_remeshed_cap_is_meshed_across_its_area_not_from_its_rim(self):
        """The point of the whole thing: a cap that had one interior point, or none, comes back
        with a mesh spread over the area it covers."""
        capped = self.cappedSurface()
        remeshedSurface = self.remeshed()
        for capId in self.capIds:
            with self.subTest(capId=capId):
                self.assertEqual(interiorPointCount(capped, capId), 1,
                                 "the centre point capper is expected to leave a single fan point")
                self.assertGreater(interiorPointCount(remeshedSurface, capId), 10)

    def test_a_remeshed_cap_is_made_of_near_equilateral_cells(self):
        """A fan over a regular rim is even by area and nowhere near equilateral, so the shape of
        the cells is what says whether remeshing did anything."""
        capped = self.cappedSurface()
        remeshedSurface = self.remeshed()
        for capId in self.capIds:
            with self.subTest(capId=capId):
                before = float(np.mean(edgeLengthRatios(capped, capId)))
                after = float(np.mean(edgeLengthRatios(remeshedSurface, capId)))
                self.assertGreater(before, 2.0, "the fan is expected to be made of slivers")
                self.assertLess(after, 1.6)
                self.assertLess(after, before)

    def test_the_wall_comes_through_untouched(self):
        """Only the caps are remeshed. The wall keeps every one of its cells and every one of its
        points stays where it was, which is what makes this safe to leave on."""
        capped = self.cappedSurface()
        remeshedSurface = self.remeshed()
        wallCellsBefore = np.nonzero(cellEntityIds(capped) == WALL_ID)[0]
        wallCellsAfter = np.nonzero(cellEntityIds(remeshedSurface) == WALL_ID)[0]
        self.assertEqual(len(wallCellsAfter), len(wallCellsBefore))
        self.assertEqual(pointCoordinates(remeshedSurface, pointIdsOf(remeshedSurface, wallCellsAfter)),
                         pointCoordinates(capped, pointIdsOf(capped, wallCellsBefore)))

    def test_the_rim_still_holds_the_cap_to_the_wall(self):
        """The remesher is free to move points of the cap, so the one thing that could go wrong
        is it pulling the cap away from the wall along the rim it shares with it."""
        self.assertEqual(openBoundaryCellCount(self.remeshed()), 0)

    def test_a_cap_keeps_the_id_that_says_which_cut_it_closes(self):
        """The face labels are read off these ids, so a cap that came back under a different one -
        or that lost the cells carrying it - would be labelled as a different cut."""
        remeshedSurface = self.remeshed()
        self.assertEqual(sorted(set(int(value) for value in cellEntityIds(remeshedSurface))),
                         sorted(set([WALL_ID]) | set(self.capIds)))

    def test_a_cap_is_sized_after_the_surface_around_it(self):
        """With no length given, a cap is meshed as finely as the wall it is attached to, so that
        one on a small branch does not come back meshed like one on a large vessel."""
        remeshedSurface = self.remeshed()
        wallEdgeLength = meanEdgeLength(remeshedSurface, WALL_ID)
        for capId in self.capIds:
            with self.subTest(capId=capId):
                self.assertAlmostEqual(meanEdgeLength(remeshedSurface, capId) / wallEdgeLength,
                                       1.0, delta=0.4)

    def test_a_given_edge_length_is_what_the_cap_is_meshed_to(self):
        """A length asked for is a length delivered, and asking for a coarser one gives a coarser
        cap - so the setting does something more than switch remeshing on."""
        fine = self.remeshed(targetEdgeLength=0.15)
        coarse = self.remeshed(targetEdgeLength=0.4)
        for capId in self.capIds:
            with self.subTest(capId=capId):
                self.assertAlmostEqual(meanEdgeLength(fine, capId), 0.15, delta=0.05)
                self.assertLess(meanEdgeLength(fine, capId), meanEdgeLength(coarse, capId))

    def test_every_cap_method_can_be_remeshed(self):
        """The cap shapes differ in what they hand the remesher - a fan, a single polygon, rings
        of quads - and all three have to come back as an even mesh on a closed surface."""
        for capMethod in ClipVessel._CAP_METHOD_IDS:
            with self.subTest(capMethod=capMethod):
                remeshedSurface = self.remeshed(capMethod)
                self.assertEqual(openBoundaryCellCount(remeshedSurface), 0)
                for capId in self.capIds:
                    self.assertGreater(interiorPointCount(remeshedSurface, capId), 10)
                    self.assertLess(float(np.mean(edgeLengthRatios(remeshedSurface, capId))), 1.6)

    def test_nothing_asked_for_is_nothing_done(self):
        """An empty list of caps leaves the surface alone rather than remeshing everything, which
        is what an excluded-entity list built from no caps at all would come to."""
        capped = self.cappedSurface()
        untouched = self.logic.remeshCaps(capped, CELL_ENTITY_IDS, [])
        self.assertEqual(untouched.GetNumberOfCells(), capped.GetNumberOfCells())
        self.assertEqual(untouched.GetNumberOfPoints(), capped.GetNumberOfPoints())


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
