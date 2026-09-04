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


    def test_CfdMeshGeneratorTriangulatesACapWhole(self):
        """A cap polygon has to be cut into triangles that use every one of its corners.

        This outline is the inlet of a patient's aorta after the boundary layer had been swept
        in: forty-two corners, planar to a tenth of a millimetre, nowhere near crossing itself.
        vtkTriangleFilter cuts it into thirty-seven triangles and leaves three corners unused,
        so the cap came back short of a notch and the surface that was to be filled had a hole
        beside it, which every mesher refused. Nothing said which cap or why.
        """
        corners = [
            (-16.83, -18.26, -104.03), (-18.53, -18.41, -105.92), (-20.26, -18.27, -107.82),
            (-21.95, -18.06, -109.70), (-23.60, -18.09, -111.62), (-25.15, -18.63, -113.56),
            (-26.53, -19.83, -115.42), (-27.64, -21.58, -117.11), (-28.36, -23.76, -118.42),
            (-28.65, -26.32, -119.30), (-28.47, -29.03, -119.69), (-27.82, -31.61, -119.49),
            (-26.77, -33.86, -118.75), (-25.45, -35.87, -117.66), (-24.01, -37.84, -116.48),
            (-22.58, -39.88, -115.35), (-21.21, -41.98, -114.29), (-19.81, -43.99, -113.16),
            (-18.30, -45.74, -111.84), (-16.61, -47.08, -110.24), (-14.84, -47.95, -108.44),
            (-13.06, -48.34, -106.51), (-11.32, -48.19, -104.51), (-9.72, -47.49, -102.54),
            (-8.31, -46.29, -100.65), (-7.21, -44.50, -98.97), (-6.41, -42.30, -97.58),
            (-5.79, -39.87, -96.33), (-5.11, -37.40, -95.03), (-4.33, -35.04, -93.66),
            (-3.62, -32.73, -92.39), (-3.24, -30.30, -91.50), (-3.36, -27.82, -91.18),
            (-4.04, -25.41, -91.46), (-5.04, -23.21, -92.11), (-6.26, -21.29, -93.05),
            (-7.63, -19.66, -94.20), (-9.11, -18.44, -95.57), (-10.65, -17.61, -97.07),
            (-12.17, -17.31, -98.71), (-13.69, -17.47, -100.42), (-15.23, -17.87, -102.18),
        ]
        points = vtk.vtkPoints()
        for corner in corners:
            points.InsertNextPoint(corner)
        # A triangle and a quad beside it, standing in for the wall, so that the cells around a
        # cap are seen to come through in their order with their ids.
        for corner in ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)):
            points.InsertNextPoint(corner)
        polys = vtk.vtkCellArray()
        polys.InsertNextCell(3, [42, 43, 44])
        polys.InsertNextCell(len(corners), list(range(len(corners))))
        polys.InsertNextCell(4, [42, 43, 44, 45])
        surface = vtk.vtkPolyData()
        surface.SetPoints(points)
        surface.SetPolys(polys)
        ids = vtk.vtkIntArray()
        ids.SetName("CellEntityIds")
        for value in (1, 8, 1):
            ids.InsertNextValue(value)
        surface.GetCellData().AddArray(ids)

        triangulated = CfdMeshGeneratorLogic.triangulate(surface)

        self.assertEqual(triangulated.GetNumberOfCells(), 1 + (len(corners) - 2) + 2)
        outIds = triangulated.GetCellData().GetArray("CellEntityIds")
        capIds = [cellId for cellId in range(triangulated.GetNumberOfCells())
                  if int(outIds.GetTuple1(cellId)) == 8]
        self.assertEqual(len(capIds), len(corners) - 2, "the cap is short of triangles")
        self.assertEqual(capIds, list(range(1, len(corners) - 1)),
                         "the cap's triangles are not where the cap was")
        # Every rim edge exactly once, and every other edge twice: a cap with no hole in it.
        edges = {}
        for cellId in capIds:
            cell = triangulated.GetCell(cellId)
            corner = [cell.GetPointId(index) for index in range(3)]
            for a, b in ((0, 1), (1, 2), (2, 0)):
                key = (min(corner[a], corner[b]), max(corner[a], corner[b]))
                edges[key] = edges.get(key, 0) + 1
        rim = {(min(k, (k + 1) % len(corners)), max(k, (k + 1) % len(corners)))
               for k in range(len(corners))}
        self.assertEqual({edge for edge, count in edges.items() if count == 1}, rim,
                         "the cap's open edges are not its rim")
        self.assertEqual(set(range(len(corners))), {corner for edge in edges for corner in edge},
                         "a corner of the cap was left out")

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
