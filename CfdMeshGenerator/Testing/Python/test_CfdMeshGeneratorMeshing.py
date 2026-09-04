"""Filling a surface with tetrahedra: the thing the module is for.

Each behaviour is put to every mesher this installation has, because the two answer differently
shaped questions and a mesh is only as good as the one that made it."""

import unittest

import slicer
import vtk

from CfdMeshGenerator import CfdMeshGeneratorLogic, Mesher
from CfdMeshGeneratorTestFixture import CfdMeshGeneratorTestCase


class CfdMeshGeneratorMeshingTest(CfdMeshGeneratorTestCase):

    def test_CfdMeshGenerator1(self):
        """An open tube must come back as a volume mesh: capped, filled with tetrahedra, and with
        the wall and each of the two caps under an id of its own, so that a boundary condition can
        be assigned to each of them."""
        logic = CfdMeshGeneratorLogic()
        for mesher in self.meshers():
            mesh, remeshedSurface = logic.generateMesh(
                self.openTube(), targetEdgeLength=0.4, mesher=mesher,
                **self.fasterFTetWild(mesher))

            self.assertGreater(remeshedSurface.GetNumberOfCells(), 0)
            cellTypes = vtk.vtkCellTypes()
            mesh.GetCellTypes(cellTypes)
            self.assertTrue(cellTypes.IsType(vtk.VTK_TETRA),
                            "the mesh holds no tetrahedra (%s)" % mesher)
            # 0 for the tetrahedra, 1 for the wall, and one id per cap above it.
            self.assertEqual(self.cellEntityIds(mesh), {0, 1, 2, 3}, mesher)
            self.assertBoundaryIsLabelled(mesh, "CellEntityIds", "(%s)" % mesher)
            self.assertTetrahedraArePositive(mesh, mesher)


    def test_CfdMeshGeneratorWithoutRemeshing(self):
        """A surface asked to be filled as it arrived still has to be filled.

        Remeshing is what used to triangulate the surface on its way past, and a cap is one
        polygon until something does: the sizing function has nothing to say about a cell that is
        not a triangle, and TetGen, handed a face it was given no sizes for, does not fail on it
        so much as take the application with it.
        """
        logic = CfdMeshGeneratorLogic()
        surface = self.openTube()
        for mesher in self.meshers():
            mesh, remeshedSurface = logic.generateMesh(
                surface, skipRemeshing=True, mesher=mesher, **self.fasterFTetWild(mesher))

            self.assertEqual(set(remeshedSurface.GetCellType(cellId)
                                 for cellId in range(remeshedSurface.GetNumberOfCells())),
                             {vtk.VTK_TRIANGLE},
                             "the surface was handed on with a polygon in it")
            # The wall it arrived with, kept: only the caps are new.
            self.assertLess(remeshedSurface.GetNumberOfCells(), surface.GetNumberOfCells() + 100)
            cellTypes = vtk.vtkCellTypes()
            mesh.GetCellTypes(cellTypes)
            self.assertTrue(cellTypes.IsType(vtk.VTK_TETRA),
                            "the mesh holds no tetrahedra (%s)" % mesher)
            self.assertEqual(self.cellEntityIds(mesh), {0, 1, 2, 3}, mesher)


    def test_CfdMeshGeneratorRemeshingTheCapsAlone(self):
        """The wall can be left as it arrived while the caps are remeshed.

        That is the point of excluding a face from the remesher: it edits no cell of an excluded
        face and moves no point one of them uses, so the wall keeps every cell it had and the caps
        go on meeting it along the rim they share.
        """
        logic = CfdMeshGeneratorLogic()
        surface = self.openTube()
        capped = logic.capSurface(surface, "CellEntityIds", "simple")

        remeshed = logic.remeshSurface(
            capped, "CellEntityIds", elementSizeMode="edgelength", targetEdgeLength=0.4,
            targetEdgeLengthArrayName="", targetEdgeLengthFactor=1.0, triangleSplitFactor=5.0,
            maxEdgeLength=1e16, minEdgeLength=0.0,
            excludedEntityIds=[CfdMeshGeneratorLogic.wallCellEntityId])

        ids = remeshed.GetCellData().GetArray("CellEntityIds")
        wallCells = sum(1 for cellId in range(remeshed.GetNumberOfCells())
                        if int(ids.GetTuple1(cellId)) == CfdMeshGeneratorLogic.wallCellEntityId)
        self.assertEqual(wallCells, surface.GetNumberOfCells(),
                         "the wall was remeshed after all")
        self.assertGreater(remeshed.GetNumberOfCells() - wallCells, 60,
                           "the caps were not remeshed")

        edges = vtk.vtkFeatureEdges()
        edges.SetInputData(remeshed)
        edges.BoundaryEdgesOn()
        edges.NonManifoldEdgesOn()
        edges.FeatureEdgesOff()
        edges.ManifoldEdgesOff()
        edges.Update()
        self.assertEqual(edges.GetOutput().GetNumberOfCells(), 0,
                         "the caps no longer meet the wall along their rim")



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
