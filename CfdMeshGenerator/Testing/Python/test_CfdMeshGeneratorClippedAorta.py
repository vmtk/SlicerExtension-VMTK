"""Meshing a real vessel rather than a tube.

The surface is the clipped aorta of VMTK's test data, in the two states Clip Vessel leaves one
in: three ends still open, and the same three ends closed. A tube is a fair test of the pipeline
but not of the surface a user actually arrives with - the aorta is thousands of cells, curved,
of varying radius, and its ends are neither round nor the same size.

Meshed coarsely on purpose. What is being asked is whether the pipeline holds together on a real
surface with each mesher, not how fine a mesh it can make; the size is chosen so that both
meshers finish in seconds.
"""

import unittest

import slicer
import vtk

from CfdMeshGenerator import CfdMeshGeneratorLogic, Mesher
from CfdMeshGeneratorTestFixture import CfdMeshGeneratorTestCase


# Coarse enough for both meshers to finish quickly, fine enough to follow the vessel. The aorta
# is about 40 mm across its bounds and arrives meshed at about 0.5 mm.
TARGET_EDGE_LENGTH = 1.5

# Wall, and one cap per clipped end. The surfaces carry boundary labels 2, 3 and 4, one per end,
# and a cap takes the label of the boundary it closes - so these are the ids whatever order the
# boundaries come out of the extractor in, and whichever mesher fills the surface.
VOLUME_ID = 0
WALL_ID = 1
CAP_IDS = {2, 3, 4}


class CfdMeshGeneratorClippedAortaTest(CfdMeshGeneratorTestCase):

    def assertIsAWellFormedMesh(self, mesh, message):
        cellTypes = vtk.vtkCellTypes()
        mesh.GetCellTypes(cellTypes)
        self.assertTrue(cellTypes.IsType(vtk.VTK_TETRA), "the mesh holds no tetrahedra " + message)
        self.assertTetrahedraArePositive(mesh, message)
        self.assertBoundaryIsLabelled(mesh, "CellEntityIds", message)

    def test_an_open_vessel_is_capped_and_filled(self):
        """The ordinary case: a surface whose ends Clip Vessel left open. Each end gets a cap of
        its own, under the id its boundary label gives it, and the space inside gets tetrahedra."""
        surface = self.requireClippedAorta(capped=False)

        for mesher in self.meshers():
            with self.subTest(mesher=mesher):
                logic = CfdMeshGeneratorLogic()
                mesh, remeshedSurface = logic.generateMesh(
                    surface, targetEdgeLength=TARGET_EDGE_LENGTH, mesher=mesher,
                    **self.fasterFTetWild(mesher))

                self.assertFalse(logic.lastTetrahedralizationFailed,
                                 "%s could not fill the aorta" % mesher)
                self.assertGreater(remeshedSurface.GetNumberOfCells(), 0)
                self.assertEqual(self.cellEntityIds(mesh), {VOLUME_ID, WALL_ID} | CAP_IDS,
                                 "the three ends are not three faces (%s)" % mesher)
                self.assertIsAWellFormedMesh(mesh, "(%s)" % mesher)

    def test_a_vessel_that_is_already_capped_is_not_capped_again(self):
        """Capping asked for on a surface whose ends are already closed.

        The boundary labels stay on a rim after it has been capped, as a record of which end it
        was, so this used to have a second cap laid over each of the three - leaving the surface
        closed, of very nearly the right size, and non-manifold along every rim. Nothing said so
        until the boundary layer generator was handed it and its untangle procedure never
        finished.
        """
        surface = self.requireClippedAorta(capped=True)
        logic = CfdMeshGeneratorLogic()

        capped = logic.capSurface(surface, "CellEntityIds", "simple")

        self.assertEqual(capped.GetNumberOfCells(), surface.GetNumberOfCells(),
                         "cells were added to a surface that had no boundary left to cap")
        nonManifold = vtk.vtkFeatureEdges()
        nonManifold.SetInputData(capped)
        nonManifold.BoundaryEdgesOff()
        nonManifold.FeatureEdgesOff()
        nonManifold.NonManifoldEdgesOn()
        nonManifold.ManifoldEdgesOff()
        nonManifold.Update()
        self.assertEqual(nonManifold.GetOutput().GetNumberOfCells(), 0,
                         "capping a closed surface left it non-manifold")

    def test_a_vessel_that_is_already_capped_still_meshes(self):
        """The whole pipeline over an already-closed surface, capping and all, which is what the
        module is given when Clip Vessel capped its output. It has to finish, and finish with a
        mesh."""
        surface = self.requireClippedAorta(capped=True)

        for mesher in self.meshers():
            with self.subTest(mesher=mesher):
                logic = CfdMeshGeneratorLogic()
                mesh, _remeshedSurface = logic.generateMesh(
                    surface, targetEdgeLength=TARGET_EDGE_LENGTH, mesher=mesher,
                    **self.fasterFTetWild(mesher))

                self.assertFalse(logic.lastTetrahedralizationFailed,
                                 "%s could not fill the capped aorta" % mesher)
                self.assertIsAWellFormedMesh(mesh, "(%s)" % mesher)

    def test_a_boundary_layer_is_grown_on_a_capped_vessel(self):
        """The case that was reported as never finishing: capping on, the input already capped,
        and a boundary layer to sweep. TetGen alone - it is the mesher that keeps the surface it
        is given, so it is the one the layer is assembled against."""
        if Mesher.TETGEN.value not in self.meshers():
            self.skipTest("this installation was built without TetGen")
        surface = self.requireClippedAorta(capped=True)
        logic = CfdMeshGeneratorLogic()

        mesh, _remeshedSurface = logic.generateMesh(
            surface, targetEdgeLength=TARGET_EDGE_LENGTH, mesher=Mesher.TETGEN.value,
            boundaryLayer=True, boundaryLayerOnCaps=False)

        self.assertFalse(logic.lastTetrahedralizationFailed, "the capped aorta could not be filled")
        cellTypes = vtk.vtkCellTypes()
        mesh.GetCellTypes(cellTypes)
        self.assertTrue(cellTypes.IsType(vtk.VTK_WEDGE), "the mesh holds no boundary layer prisms")
        self.assertTrue(cellTypes.IsType(vtk.VTK_TETRA), "the mesh holds no tetrahedra")
        self.assertNotIn(CfdMeshGeneratorLogic.placeholderCellEntityId, self.cellEntityIds(mesh),
                         "a sidewall cell was left under the placeholder id")
        self.assertTetrahedraArePositive(mesh)


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
