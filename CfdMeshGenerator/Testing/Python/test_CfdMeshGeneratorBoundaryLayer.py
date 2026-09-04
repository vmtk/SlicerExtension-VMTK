"""The layer of prisms along the wall, which is what resolves the wall shear stress."""

import unittest

import slicer
import vtk

from CfdMeshGenerator import CfdMeshGeneratorLogic, Mesher
from CfdMeshGeneratorTestFixture import CfdMeshGeneratorTestCase


class CfdMeshGeneratorBoundaryLayerTest(CfdMeshGeneratorTestCase):

    def test_CfdMeshGeneratorBoundaryLayer(self):
        """The same tube, lined with prisms, whether the layer is grown over the caps or stops
        short of them. The layer must be made of prisms and the space it leaves must still be
        filled with tetrahedra - a mesh that came back hollow would look like a mesh until a
        solver opened it. The caps must be there to carry the flow conditions too, including the
        sidewall cells swept out of each open end, which are named after the cap they belong to
        only once everything has been put together."""
        logic = CfdMeshGeneratorLogic()
        for mesher in self.meshers():
            for onCaps in (True, False):
                where = "(%s, on caps: %s)" % (mesher, onCaps)
                mesh, _remeshedSurface = logic.generateMesh(
                    self.openTube(), targetEdgeLength=0.4, boundaryLayer=True,
                    boundaryLayerOnCaps=onCaps, mesher=mesher, **self.fasterFTetWild(mesher))

                cellTypes = vtk.vtkCellTypes()
                mesh.GetCellTypes(cellTypes)
                self.assertTrue(cellTypes.IsType(vtk.VTK_WEDGE),
                                "the boundary layer holds no prisms " + where)
                self.assertTrue(cellTypes.IsType(vtk.VTK_TETRA),
                                "the mesh is hollow inside its boundary layer " + where)
                self.assertFalse(logic.lastTetrahedralizationFailed, where)
                ids = self.cellEntityIds(mesh)
                self.assertEqual(ids, {0, 1, 2, 3}, where)
                self.assertNotIn(CfdMeshGeneratorLogic.placeholderCellEntityId, ids,
                                 "a sidewall cell was left under the placeholder id " + where)
                if not onCaps:
                    # The strips swept out of the open ends, which stand between the rim of the
                    # outer surface and the cap made past the layer. Nothing else is a quad.
                    self.assertTrue(cellTypes.IsType(vtk.VTK_QUAD),
                                    "the open ends were swept into no sidewall cells " + where)
                self.assertBoundaryIsLabelled(mesh, "CellEntityIds", where)
                self.assertTetrahedraArePositive(mesh, where)


    def test_CfdMeshGeneratorFoldedBoundaryLayer(self):
        """A layer too thick for the vessel folds through itself, and TetGen does not survive
        being handed the result, so it must be turned away before it gets there."""
        logic = CfdMeshGeneratorLogic()
        with self.assertRaises(RuntimeError):
            logic.generateMesh(self.openTube(), targetEdgeLength=0.4, boundaryLayer=True,
                               boundaryLayerThicknessFactor=8.0)


    def test_CfdMeshGeneratorLayerOffImportedCaps(self):
        """"Layer on caps" has to mean something for a surface that arrives capped as well.

        Not capping is what keeps a layer off the caps of a surface whose ends are still open, but
        it does nothing for one that was closed before it got here: the sweep runs over the caps
        it already has. The caps have to come off first, and the ids they carried have to come
        back on the caps made in their place, or a solver reading the inlet by its number reads
        the wrong end of the vessel.
        """
        logic = CfdMeshGeneratorLogic()
        closed = logic.capSurface(self.openTube(), "ModelFaceID", "simple")
        targetEdgeLength = 0.4
        layerThickness = 0.25 * targetEdgeLength

        def gapToTheInlet(mesh):
            """How far the tetrahedra keep from the cap at z = 0. A layer grown over that cap
            stands between the two; without one they meet it directly. The cap face itself looks
            the same either way, so this is what the flag can be read off."""
            gap = None
            for cellId in range(mesh.GetNumberOfCells()):
                if mesh.GetCellType(cellId) != vtk.VTK_TETRA:
                    continue
                cell = mesh.GetCell(cellId)
                for index in range(cell.GetNumberOfPoints()):
                    z = mesh.GetPoint(cell.GetPointId(index))[2]
                    gap = z if gap is None else min(gap, z)
            return gap

        for mesher in self.meshers():
            for onCaps in (False, True):
                where = "(%s, on caps: %s)" % (mesher, onCaps)
                mesh, _remeshedSurface = logic.generateMesh(
                    closed, targetEdgeLength=targetEdgeLength,
                    cellEntityIdsArrayName="ModelFaceID", skipCapping=True, boundaryLayer=True,
                    boundaryLayerOnCaps=onCaps, mesher=mesher, **self.fasterFTetWild(mesher))

                gap = gapToTheInlet(mesh)
                self.assertIsNotNone(gap, "the mesh holds no tetrahedra " + where)
                if onCaps:
                    self.assertGreater(gap, 0.5 * layerThickness,
                                       "no layer was grown over the cap " + where)
                else:
                    self.assertLess(gap, 0.5 * layerThickness,
                                    "the layer was grown over the cap after all " + where)
                self.assertEqual(
                    self.cellEntityIds(mesh, "ModelFaceID"), {0, 1, 2, 3},
                    "the caps did not come back under the ids they arrived with " + where)



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
