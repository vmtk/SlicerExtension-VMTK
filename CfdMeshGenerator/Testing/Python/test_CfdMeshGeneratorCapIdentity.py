"""Does each cap carry the id of the vessel end it actually closes?

Every other test here asks which face ids the output *has*. That is not the same question, and a
permutation satisfies it: a mesh whose caps all swapped ids still has wall 1 and caps 2, 3, 4,
still passes `assertBoundaryIsLabelled`, and still looks right in the views. The only way to
catch it is to ask where each cap physically is, and the surface says where each vessel end is -
its boundary points carry that end's label - so the two can be compared.

They were not equal. Growing a boundary layer with "layer on caps" off permuted the cap ids:
the caps are remade on the inner surface the sweep leaves behind, and while the BoundaryLabels
point array comes through that untouched, BoundaryPointOrder does not - the inner boundaries are
coarser than the ones the order was written for, so the order values are no longer one run per
boundary. vtkvmtkBoundaryLabels::GetOrExtractBoundaries refuses the pair whole when that happens,
the capper was left to number the caps in the order its extractor found the boundaries, and that
order is a rotation of the labels. Every cap took another vessel end's id.

That matters beyond the ids: a cap's id becomes a mesh-surfaces file name and a solver's
Add_BC name, so an inflow waveform meant for one vessel lands on another - and nothing further
down the chain can notice, because every id is present and in range.
"""

import unittest

import numpy as np
import slicer
import vtk
from vtk.util.numpy_support import vtk_to_numpy

from CfdMeshGenerator import CfdMeshGeneratorLogic, Mesher
from CfdMeshGeneratorTestFixture import CfdMeshGeneratorTestCase

# Coarse enough to mesh in seconds, fine enough to follow the vessel.
TARGET_EDGE_LENGTH = 1.5

# A boundary layer thick enough that the caps are genuinely remade well inside the surface they
# arrived on, which is what breaks the point order. A thin layer would pass either way.
BOUNDARY_LAYER = dict(boundaryLayer=True, boundaryLayerOnCaps=False, numberOfSubLayers=6,
                      subLayerRatio=0.5, boundaryLayerThicknessFactor=0.25,
                      numberOfSubsteps=2000, relaxation=0.01, localCorrectionFactor=0.45)


class CfdMeshGeneratorCapIdentityTest(CfdMeshGeneratorTestCase):

    def vesselEndCentres(self, surface, boundaryLabelsArrayName="BoundaryLabels"):
        """Where each labelled vessel end of the input is: {label: centre of its rim points}.

        This is the ground truth the caps are held against, and it comes from the input itself
        rather than from anything the pipeline produced.
        """
        labels = vtk_to_numpy(surface.GetPointData().GetArray(boundaryLabelsArrayName)).astype(int)
        points = vtk_to_numpy(surface.GetPoints().GetData())
        return {int(label): points[labels == label].mean(axis=0)
                for label in np.unique(labels) if int(label) >= 0}

    def capCentres(self, mesh, cellEntityIdsArrayName):
        """Where each cap of the finished mesh is: {face id: centre of its cells}."""
        ids = vtk_to_numpy(mesh.GetCellData().GetArray(cellEntityIdsArrayName)).astype(int)
        centers = vtk.vtkCellCenters()
        centers.SetInputData(mesh)
        centers.Update()
        points = vtk_to_numpy(centers.GetOutput().GetPoints().GetData())
        return {int(faceId): points[ids == faceId].mean(axis=0)
                for faceId in np.unique(ids) if int(faceId) > self.logicWallId}

    logicWallId = 1

    def assertEachCapCarriesItsOwnEndsId(self, surface, mesh, cellEntityIdsArrayName, message):
        """Every cap sits at the vessel end whose id it carries, and no other."""
        ends = self.vesselEndCentres(surface)
        caps = self.capCentres(mesh, cellEntityIdsArrayName)
        self.assertTrue(caps, "the mesh has no caps at all " + message)
        for faceId, capCentre in sorted(caps.items()):
            distances = sorted((float(np.linalg.norm(centre - capCentre)), label)
                               for label, centre in ends.items())
            nearest, nearestLabel = distances[0]
            runnerUp = distances[1][0] if len(distances) > 1 else float("inf")
            self.assertEqual(
                faceId, nearestLabel,
                "cap %d sits at vessel end %d, %.2f mm away, not at end %d %s"
                % (faceId, nearestLabel, nearest, faceId, message))
            # The match has to be unambiguous, or the assertion above proves nothing: a cap
            # equidistant from two ends would pass by luck.
            self.assertLess(nearest * 4, runnerUp,
                            "cap %d is %.2f mm from end %d and %.2f mm from the next, too close "
                            "to tell apart %s" % (faceId, nearest, nearestLabel, runnerUp, message))

    def test_a_boundary_layer_does_not_move_the_cap_ids(self):
        """The case that was wrong: uncapped in, layer swept, caps made on the inner surface.

        This is the ordinary clinical configuration - capping is left to this module so the caps
        land past the layer, where they belong - so it is the run that most needs the identity and
        the one that lost it.
        """
        surface = self.requireClippedAorta(capped=False)
        logic = CfdMeshGeneratorLogic()
        mesh = logic.generateMesh(surface, targetEdgeLength=TARGET_EDGE_LENGTH,
                                  cellEntityIdsArrayName="CellEntityIds",
                                  mesher=Mesher.TETGEN.value, **BOUNDARY_LAYER)[0]
        self.assertEachCapCarriesItsOwnEndsId(surface, mesh, "CellEntityIds",
                                              "(uncapped in, boundary layer off the caps)")

    def test_a_layer_grown_over_the_caps_does_not_move_them_either(self):
        """The other way round: the layer goes over the caps, so they are not remade at all."""
        surface = self.requireClippedAorta(capped=False)
        logic = CfdMeshGeneratorLogic()
        arguments = dict(BOUNDARY_LAYER, boundaryLayerOnCaps=True)
        mesh = logic.generateMesh(surface, targetEdgeLength=TARGET_EDGE_LENGTH,
                                  cellEntityIdsArrayName="CellEntityIds",
                                  mesher=Mesher.TETGEN.value, **arguments)[0]
        self.assertEachCapCarriesItsOwnEndsId(surface, mesh, "CellEntityIds",
                                              "(uncapped in, boundary layer over the caps)")

    def test_without_a_layer_the_ids_are_right_too(self):
        """The configuration that always worked, kept so that a regression here is localised:
        if this fails as well, the labels themselves are wrong rather than the layer."""
        surface = self.requireClippedAorta(capped=False)
        logic = CfdMeshGeneratorLogic()
        mesh = logic.generateMesh(surface, targetEdgeLength=TARGET_EDGE_LENGTH,
                                  cellEntityIdsArrayName="CellEntityIds",
                                  mesher=Mesher.TETGEN.value, boundaryLayer=False)[0]
        self.assertEachCapCarriesItsOwnEndsId(surface, mesh, "CellEntityIds",
                                              "(uncapped in, no boundary layer)")

    def test_a_surface_that_arrives_capped_keeps_its_cap_ids(self):
        """A surface whose ends are already closed: the caps come off for the layer and go back.

        The other path through nameCapsAfterTheirVesselEnd - the one that has caps to give ids
        back to - and it has to agree with the rest about which end is which.

        The input is capped here rather than read from the test data, because the capped surface
        in the test data has nothing to tell its caps from its wall by; capping it through the
        pipeline is what gives the caps ids in the first place.
        """
        logic = CfdMeshGeneratorLogic()
        openSurface = self.requireClippedAorta(capped=False)
        capped = logic.capSurface(
            logic.withCellEntityIds(openSurface, "CellEntityIds"), "CellEntityIds", "simple",
            boundaryLabelsArrayName="BoundaryLabels",
            boundaryPointOrderArrayName="BoundaryPointOrder")
        cappedIds = set(self.cellEntityIds(capped, "CellEntityIds"))
        self.assertTrue({2, 3, 4} <= cappedIds,
                        "capping should give each end's cap the id its label says: %s" % sorted(cappedIds))

        mesh = logic.generateMesh(capped, targetEdgeLength=TARGET_EDGE_LENGTH,
                                  cellEntityIdsArrayName="CellEntityIds",
                                  mesher=Mesher.TETGEN.value, **BOUNDARY_LAYER)[0]
        self.assertEachCapCarriesItsOwnEndsId(openSurface, mesh, "CellEntityIds",
                                              "(capped in, boundary layer off the caps)")

    def test_the_labels_are_recovered_from_the_points_the_order_array_cannot_describe(self):
        """The mechanism, on its own: labels present, point order stale, association recoverable.

        Held separately from the meshing tests because it is the thing that was actually wrong and
        it is cheap to check. Stripping the point order array is what the boundary layer does to
        it in effect - leaves values that no longer describe the boundaries - and the labels still
        say which end each boundary is.
        """
        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry

        surface = self.requireClippedAorta(capped=False)
        damaged = vtk.vtkPolyData()
        damaged.DeepCopy(surface)
        damaged.GetPointData().RemoveArray("BoundaryPointOrder")

        boundaries = vtk.vtkPolyData()
        boundaryLabels = vtk.vtkIdList()
        useLabels = vtkvmtkComputationalGeometry.vtkvmtkBoundaryLabels.GetOrExtractBoundaries(
            damaged, "BoundaryLabels", "BoundaryPointOrder", boundaries, boundaryLabels)
        self.assertFalse(useLabels, "without a usable point order the pair should be refused")
        self.assertGreater(boundaries.GetNumberOfCells(), 0)

        logic = CfdMeshGeneratorLogic()
        recovered = logic.labelsFromBoundaryPoints(damaged, boundaries, "BoundaryLabels")
        self.assertEqual(len(recovered), boundaries.GetNumberOfCells(),
                         "every boundary's own points should say which end it is")

        # And what was recovered is what the geometry says.
        ends = self.vesselEndCentres(surface)
        for index, label in recovered.items():
            centre = np.array(logic.boundaryCentre(boundaries, index))
            nearest = min(ends, key=lambda end: np.linalg.norm(ends[end] - centre))
            self.assertEqual(label, nearest,
                             "boundary %d was read as end %d but sits at end %d"
                             % (index, label, nearest))


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
