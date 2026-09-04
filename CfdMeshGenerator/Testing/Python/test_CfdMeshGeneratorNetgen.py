"""What is true of Netgen alone: it is fetched before it is used, it keeps the surface it is
given, and it reads a size per point."""

import sys
import unittest

import vtk

from CfdMeshGenerator import CfdMeshGeneratorLogic, ElementSizeMode, Mesher
from CfdMeshGeneratorTestFixture import CfdMeshGeneratorTestCase


class CfdMeshGeneratorNetgenTest(CfdMeshGeneratorTestCase):

    def test_CfdMeshGeneratorNetgenSizesByPosition(self):
        """A size asked for per point has to come out as elements of that size.

        This is what Netgen has over TetGen, which sizes the volume it fills by one number
        however finely the surface is graded: a vessel that is narrow in one place and wide in
        another wants the mesh fine in the narrow part and no finer than it has to be elsewhere.
        The same question the fTetWild test asks, of the other mesher that can answer it.
        """
        self.requireNetgen()

        logic = CfdMeshGeneratorLogic()
        # A tube whose lower half asks for cells a third the size of its upper half. Finer than
        # the tube the other tests use: asked to grade a surface into triangles far from the size
        # of the ones it was given, the remesher hands back one with holes in it.
        surface = logic.capSurface(
            self.openTube(numberOfAxialPoints=40, numberOfCircumferentialPoints=48),
            "CellEntityIds", "simple")
        sizes = vtk.vtkDoubleArray()
        sizes.SetName("Size")
        sizes.SetNumberOfTuples(surface.GetNumberOfPoints())
        for pointId in range(surface.GetNumberOfPoints()):
            sizes.SetTuple1(pointId, 0.2 if surface.GetPoint(pointId)[2] < 5.0 else 0.6)
        surface.GetPointData().AddArray(sizes)

        mesh, _remeshedSurface = logic.generateMesh(
            surface, mesher=Mesher.NETGEN.value, skipCapping=True,
            elementSizeMode=ElementSizeMode.EDGE_LENGTH_ARRAY.value,
            targetEdgeLengthArrayName="Size", volumeElementScaleFactor=1.0)
        self.assertFalse(logic.lastTetrahedralizationFailed)

        volumes = {True: [], False: []}
        for cellId in range(mesh.GetNumberOfCells()):
            if mesh.GetCellType(cellId) != vtk.VTK_TETRA:
                continue
            cell = mesh.GetCell(cellId)
            points = [mesh.GetPoint(cell.GetPointId(index)) for index in range(4)]
            middle = sum(point[2] for point in points) / 4.0
            volumes[middle < 5.0].append(abs(vtk.vtkTetra.ComputeVolume(*points)))

        self.assertTrue(volumes[True] and volumes[False], "the mesh does not span the tube")
        fine = sum(volumes[True]) / len(volumes[True])
        coarse = sum(volumes[False]) / len(volumes[False])
        # Three times the edge length is twenty-seven times the volume; anything past a few times
        # says the field was read, and nothing like it says the field was ignored.
        self.assertGreater(coarse / fine, 4.0,
                           "the half asked for coarse cells got cells %.2f times the size of the "
                           "half asked for fine ones" % (coarse / fine))
        self.assertTetrahedraArePositive(mesh)

    def test_CfdMeshGeneratorNetgenIsAskedForBeforeItIsUsed(self):
        """A mesher that is not installed has to say so, and say what would install it.

        Netgen is downloaded rather than built in, so a scene set to it can be opened on a
        machine that has never had it. What comes of pressing Apply there should be a sentence
        naming the package, not an ImportError out of the middle of the pipeline.
        """
        logic = CfdMeshGeneratorLogic()

        class Blocked:
            """Stands in for a machine that has never installed the package: asked for it, the
            import machinery finds nothing, which is what it does when it is not there."""
            @staticmethod
            def find_spec(name, path=None, target=None):
                if name.split(".")[0] in ("netgen", "pyngcore"):
                    raise ModuleNotFoundError("No module named %r" % name, name=name)
                return None

        hidden = {name: module for name, module in sys.modules.items()
                  if name.split(".")[0] in ("netgen", "pyngcore")}
        for name in hidden:
            del sys.modules[name]
        sys.meta_path.insert(0, Blocked)
        try:
            self.assertFalse(logic.isNetgenAvailable(),
                             "Netgen was reported available with its package hidden")
            with self.assertRaises(RuntimeError) as raised:
                logic.generateMesh(self.openTube(), mesher=Mesher.NETGEN.value)
            self.assertIn("netgen-mesher", str(raised.exception),
                          "the message does not name the package to install")
        finally:
            sys.meta_path.remove(Blocked)
            sys.modules.update(hidden)

        # And with the package back, the same call gets as far as meshing.
        self.assertTrue(logic.isNetgenAvailable() or not hidden,
                        "the package was not put back after the test hid it")

    def test_CfdMeshGeneratorNetgenKeepsTheSurface(self):
        """The surface handed to Netgen is the surface that comes back, triangle for triangle,
        with the tetrahedra behind it.

        This is what tells Netgen from fTetWild, which answers with a boundary of its own within
        a tolerance of the one it was given, and what lets a boundary layer swept from the
        surface meet the tetrahedra exactly. Asked of the points and of the triangles: every
        point of the remeshed surface has to be a point of the mesh, where it was, and the
        triangles of the mesh have to be the triangles of the surface and no others.
        """
        self.requireNetgen()
        logic = CfdMeshGeneratorLogic()
        mesh, remeshedSurface = logic.generateMesh(
            self.openTube(), targetEdgeLength=0.4, mesher=Mesher.NETGEN.value)
        self.assertFalse(logic.lastTetrahedralizationFailed)

        # The points the surface's triangles stand on. The remesher leaves behind the points of
        # the edges it collapsed, which no cell refers to and which the pipeline cleans off
        # before the surface is handed to a mesher.
        referenced = set()
        for cellId in range(remeshedSurface.GetNumberOfCells()):
            cell = remeshedSurface.GetCell(cellId)
            referenced.update(cell.GetPointId(index) for index in range(cell.GetNumberOfPoints()))
        self.assertGreater(len(referenced), 0)

        locator = vtk.vtkPointLocator()
        locator.SetDataSet(mesh)
        locator.BuildLocator()
        for pointId in sorted(referenced):
            point = remeshedSurface.GetPoint(pointId)
            nearest = mesh.GetPoint(locator.FindClosestPoint(point))
            # The mesh holds its points in single precision, so this is the rounding of one
            # coordinate and nothing like the tolerance a mesher that moves the surface works to.
            self.assertLess(vtk.vtkMath.Distance2BetweenPoints(point, nearest), 1e-10,
                            "point %d of the surface is not a point of the mesh" % pointId)

        def triangles(dataset):
            found = set()
            for cellId in range(dataset.GetNumberOfCells()):
                if dataset.GetCellType(cellId) != vtk.VTK_TRIANGLE:
                    continue
                cell = dataset.GetCell(cellId)
                corners = [dataset.GetPoint(cell.GetPointId(index)) for index in range(3)]
                found.add(frozenset(tuple(round(value, 5) for value in corner)
                                    for corner in corners))
            return found

        surfaceTriangles = triangles(remeshedSurface)
        self.assertEqual(len(surfaceTriangles), remeshedSurface.GetNumberOfCells(),
                         "the remeshed surface is not all triangles")
        self.assertEqual(triangles(mesh), surfaceTriangles,
                         "the triangles of the mesh are not the triangles of the surface")
        self.assertEqual(self.cellEntityIds(mesh), {0, 1, 2, 3})
        self.assertBoundaryIsLabelled(mesh, "CellEntityIds")
        self.assertTetrahedraArePositive(mesh)

    def test_CfdMeshGeneratorNetgenBoundaryLayerWelds(self):
        """With a boundary layer, the tetrahedra Netgen makes have to join the prisms: one
        mesh, not a layer and a core that happen to touch. The layer's inner face is the surface
        Netgen is handed, and Netgen keeps it, so the two share their points and the filter that
        puts them together welds them - which is what this asks."""
        self.requireNetgen()
        logic = CfdMeshGeneratorLogic()
        for onCaps in (True, False):
            where = "(on caps: %s)" % onCaps
            mesh, _remeshedSurface = logic.generateMesh(
                self.openTube(), targetEdgeLength=0.4, boundaryLayer=True,
                boundaryLayerOnCaps=onCaps, mesher=Mesher.NETGEN.value)
            self.assertFalse(logic.lastTetrahedralizationFailed, where)

            connectivity = vtk.vtkConnectivityFilter()
            connectivity.SetInputData(mesh)
            connectivity.SetExtractionModeToAllRegions()
            connectivity.Update()
            self.assertEqual(connectivity.GetNumberOfExtractedRegions(), 1,
                             "the tetrahedra and the boundary layer are not one mesh " + where)
            self.assertTetrahedraArePositive(mesh, where)
            self.assertBoundaryIsLabelled(mesh, "CellEntityIds", where)


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
