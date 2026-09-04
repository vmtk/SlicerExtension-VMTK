"""What is true of fTetWild alone: it is fetched before it is used, and it is the mesher that
reads a size per point."""

import sys
import unittest

import slicer
import vtk

from CfdMeshGenerator import CfdMeshGeneratorLogic, ElementSizeMode, Mesher
from CfdMeshGeneratorTestFixture import CfdMeshGeneratorTestCase


class CfdMeshGeneratorFTetWildTest(CfdMeshGeneratorTestCase):

    def test_CfdMeshGeneratorFTetWildSizesByPosition(self):
        """A size asked for per point has to come out as elements of that size.

        This is what fTetWild is here for that TetGen cannot do: the switch TetGen reads a size
        function through answers differently each run, so the volume it fills is sized by one
        number throughout however finely the surface is graded. A vessel that is narrow in one
        place and wide in another wants the mesh fine in the narrow part and no finer than it has
        to be elsewhere, which is the whole of the saving.
        """
        self.requireFTetWild()

        logic = CfdMeshGeneratorLogic()
        # A tube whose lower half asks for cells a third the size of its upper half. Finer than
        # the tube the other tests use: asked to grade a surface into triangles far from the size
        # of the ones it was given, the remesher hands back one with holes in it, and no mesher
        # can do anything with that (the run refuses, which is the next test but one).
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
            surface, mesher=Mesher.FTETWILD.value, skipCapping=True,
            elementSizeMode=ElementSizeMode.EDGE_LENGTH_ARRAY.value,
            targetEdgeLengthArrayName="Size", volumeElementScaleFactor=1.0,
            maxOptimizationPasses=20)

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


    def test_CfdMeshGeneratorFTetWildIsAskedForBeforeItIsUsed(self):
        """A mesher that is not installed has to say so, and say what would install it.

        fTetWild is downloaded rather than built in, so a scene set to it can be opened on a
        machine that has never had it. What comes of pressing Apply there should be a sentence
        naming the package, not an ImportError out of the middle of the pipeline.
        """
        logic = CfdMeshGeneratorLogic()

        class Blocked:
            """Stands in for a machine that has never installed the package: asked for it, the
            import machinery finds nothing, which is what it does when it is not there."""
            @staticmethod
            def find_spec(name, path=None, target=None):
                if name.split(".")[0] == "pytetwild":
                    raise ModuleNotFoundError("No module named %r" % name, name=name)
                return None

        hidden = {name: module for name, module in sys.modules.items()
                  if name.split(".")[0] == "pytetwild"}
        for name in hidden:
            del sys.modules[name]
        sys.meta_path.insert(0, Blocked)
        try:
            self.assertFalse(logic.isFTetWildAvailable(),
                             "fTetWild was reported available with its package hidden")
            with self.assertRaises(RuntimeError) as raised:
                logic.generateMesh(self.openTube(), mesher=Mesher.FTETWILD.value)
            self.assertIn("pytetwild", str(raised.exception),
                          "the message does not name the package to install")
        finally:
            sys.meta_path.remove(Blocked)
            sys.modules.update(hidden)

        # And with the package back, the same call gets as far as meshing.
        self.assertTrue(logic.isFTetWildAvailable() or not hidden,
                        "the package was not put back after the test hid it")

    def test_CfdMeshGeneratorFTetWildRunsInAnotherPython(self):
        """fTetWild can be run in a Python other than the one the pipeline runs in, and the
        mesh is the same mesh.

        This is what a Mac running an Intel build of Slicer on an Apple silicon processor needs:
        there is no pytetwild for the Python it has, and there is one for the processor. The
        pipeline hands the surface to the other interpreter by file and reads the tetrahedra
        back the same way. Here the other interpreter is this one, started afresh - what is put
        to the test is the handing over, and that needs no second Python to be wrong about.
        """
        self.requireFTetWild()
        logic = CfdMeshGeneratorLogic()
        if logic.fTetWildPython is not None:
            self.skipTest("fTetWild already runs in another Python here")

        surface = self.openTube()
        inProcess, _surface = logic.generateMesh(
            surface, targetEdgeLength=0.4, mesher=Mesher.FTETWILD.value,
            **self.fasterFTetWild(Mesher.FTETWILD.value))

        logic.fTetWildPython = sys.executable
        self.assertTrue(logic.isFTetWildAvailable(),
                        "fTetWild was not found in %s" % sys.executable)
        elsewhere, _surface = logic.generateMesh(
            surface, targetEdgeLength=0.4, mesher=Mesher.FTETWILD.value,
            **self.fasterFTetWild(Mesher.FTETWILD.value))

        self.assertFalse(logic.lastTetrahedralizationFailed)
        # Near enough rather than the same: fTetWild does not give the same mesh twice even in
        # one process, so what is asked is that the same surface came back meshed the same way.
        self.assertAlmostEqual(
            elsewhere.GetNumberOfCells() / inProcess.GetNumberOfCells(), 1.0, delta=0.1,
            msg="the mesh made in another Python (%d cells) is not the mesh made here (%d)"
                % (elsewhere.GetNumberOfCells(), inProcess.GetNumberOfCells()))
        self.assertEqual(self.cellEntityIds(elsewhere), {0, 1, 2, 3})
        self.assertBoundaryIsLabelled(elsewhere, "CellEntityIds")

    def test_CfdMeshGeneratorFTetWildReportsAPythonThatCannotRunIt(self):
        """An interpreter that cannot run fTetWild is reported as such, not as a surface that
        could not be filled: the two are told apart, because they are answered differently."""
        logic = CfdMeshGeneratorLogic()
        logic.fTetWildPython = "no-such-python-anywhere"
        self.assertFalse(logic.isFTetWildAvailable())
        with self.assertRaises(RuntimeError) as raised:
            logic.generateMesh(self.openTube(), mesher=Mesher.FTETWILD.value)
        self.assertIn("pytetwild", str(raised.exception))


    def test_CfdMeshGeneratorFTetWildEnvironmentIsOnlyForRosetta(self):
        """A Python environment of its own is asked for only where Slicer's Python cannot host
        fTetWild, and that is one place: an Intel Slicer under Rosetta on an Apple silicon Mac.

        Everywhere else the interpreter is run as itself and no Python is looked for on the
        machine, so the answer here says which side of that line this machine is on and that
        the pieces agree with each other about it.
        """
        from CfdMeshGeneratorLib import FTetWild

        separate = FTetWild.needsSeparateEnvironment()
        if sys.platform != "darwin":
            self.assertFalse(separate, "a separate environment was asked for off macOS")
        if separate:
            self.assertEqual(FTetWild.interpreterCommand("python")[:2], ["arch", "-arm64"])
            self.assertEqual(FTetWild.hardwareArchitecture(), "aarch64")
        else:
            self.assertEqual(FTetWild.interpreterCommand("python"), ["python"])
            self.assertIsNone(FTetWild.findSystemPython() if sys.platform != "darwin" else None)
        # The commands that make an environment are built without running anything, and each
        # of the two ways ends by installing the pinned package into the venv.
        for commands in (FTetWild.venvCommands("dir", "python3"),
                         FTetWild.uvCommands("dir", "uv")):
            self.assertEqual(len(commands), 2)
            self.assertIn(FTetWild.REQUIREMENT, commands[1][0])


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
