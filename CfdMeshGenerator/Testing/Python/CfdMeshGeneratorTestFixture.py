"""The case every meshing test here works on, and what they all check of a mesh.

Not a test: the name does not match pytest's default pattern, so it is imported rather than
collected. Every test class here derives from CfdMeshGeneratorTestCase, which is where the
surfaces, the list of meshers and the assertions about a finished mesh live.
"""

import logging
import os
import unittest

import slicer
import vtk

from CfdMeshGenerator import CfdMeshGeneratorLogic, Mesher


def ensureCfdMeshGeneratorModuleRegistered():
    """Make slicer.modules.cfdmeshgenerator exist, registering it if this Slicer did not.

    Building the module's widget needs the module itself registered, not merely importable:
    ScriptedLoadableModuleWidget.setup() asks slicer.util.modulePath() where the module lives so
    that it can find its .ui file. A Slicer started through the extension's own launcher has it;
    one started as the application binary directly does not, because the module paths are given
    to the launcher rather than carried in the environment it passes on.
    """
    import qt

    import CfdMeshGenerator

    if hasattr(slicer.modules, "cfdmeshgenerator"):
        return
    factoryManager = slicer.app.moduleManager().factoryManager()
    factoryManager.registerModule(qt.QFileInfo(CfdMeshGenerator.__file__))
    factoryManager.loadModules(["CfdMeshGenerator"])
    if not hasattr(slicer.modules, "cfdmeshgenerator"):
        raise RuntimeError("could not register the CfdMeshGenerator module from %s"
                           % CfdMeshGenerator.__file__)


def cfdMeshGeneratorModuleWidget():
    """The module's own widget, the one the application drives.

    Slicer builds it, parents it, gives it the scene and runs setup(), so a test gets the same
    object a user does. It also owns it: the module manager tears the widget down before the
    scene at exit, so a test must not call cleanup() on it.
    """
    ensureCfdMeshGeneratorModuleRegistered()
    try:
        slicer.util.selectModule("CfdMeshGenerator")
    except RuntimeError:
        pass
    return slicer.util.getModuleWidget("CfdMeshGenerator")


# Surfaces that are a real vessel rather than a tube, kept in VMTK's test data repository. They
# live in a build tree and not in an installed extension, so a test that needs one says why it
# cannot run rather than failing where the data is simply not there.
_TEST_DATA_ENVIRONMENT_VARIABLE = "VMTK_TEST_DATA_DIR"
_TEST_DATA_RELATIVE_PATH = os.path.join("VMTK", "tests", "vmtk-test-data", "input")


def vmtkTestDataDirectory():
    """Where VMTK's test inputs are, or None.

    VMTK_TEST_DATA_DIR names it outright. Failing that it is found by walking up from this
    module: the extension source sits beside the build tree that the superbuild checks VMTK out
    into, and the tests are run from the source either way.
    """
    fromEnvironment = os.environ.get(_TEST_DATA_ENVIRONMENT_VARIABLE)
    if fromEnvironment and os.path.isdir(fromEnvironment):
        return fromEnvironment
    directory = os.path.dirname(os.path.abspath(__file__))
    while True:
        parent = os.path.dirname(directory)
        if parent == directory:
            return None
        directory = parent
        for sibling in sorted(os.listdir(directory)) if os.path.isdir(directory) else []:
            candidate = os.path.join(directory, sibling, _TEST_DATA_RELATIVE_PATH)
            if os.path.isdir(candidate):
                return candidate


def clippedAortaSurface(capped):
    """The clipped aorta of VMTK's test data, with its three ends closed or still open.

    Both carry the boundary label arrays Clip Vessel writes, so a cap is named after the vessel
    end it closes. Neither carries a face id array: they are what Clip Vessel leaves with "label
    mesh faces" off, which is the input this module is most often handed.

    :return: the surface, or None where the test data is not in this build.
    """
    directory = vmtkTestDataDirectory()
    if directory is None:
        return None
    name = "aorta-surface-clipped-%s.vtp" % ("capped" if capped else "uncapped")
    path = os.path.join(directory, name)
    if not os.path.isfile(path):
        return None
    reader = vtk.vtkXMLPolyDataReader()
    reader.SetFileName(path)
    reader.Update()
    return reader.GetOutput()


class CfdMeshGeneratorTestCase(unittest.TestCase):
    """What the meshing tests share: the surfaces they mesh, the meshers they put each behaviour
    to, and the questions asked of every finished mesh."""

    def setUp(self):
        slicer.mrmlScene.Clear()

    def requireClippedAorta(self, capped):
        """The clipped aorta, or a skip saying the test data is not in this build."""
        surface = clippedAortaSurface(capped)
        if surface is None:
            self.skipTest("VMTK's test data is not in this build; set %s to point at its input "
                          "directory to run this" % _TEST_DATA_ENVIRONMENT_VARIABLE)
        return surface

    @staticmethod
    def meshers():
        """The meshers to put each behaviour to, which is every one this installation has.

        fTetWild and Netgen are installed if they are missing - wherever the module would
        install them, which for fTetWild on a Mac running an Intel build on Apple silicon is a
        Python environment of its own - so that a machine with a network connection tests all
        three; one without tests what it has, which is the same choice a user has there.
        """
        logic = CfdMeshGeneratorLogic()
        found = []
        if logic.isTetGenAvailable():
            found.append(Mesher.TETGEN.value)
        for mesher, isAvailable, install in (
                (Mesher.FTETWILD, logic.isFTetWildAvailable, logic.installFTetWild),
                (Mesher.NETGEN, logic.isNetgenAvailable, logic.installNetgen)):
            if not isAvailable():
                try:
                    install()
                except Exception:
                    logging.warning("%s could not be installed, so it is left untested.",
                                    mesher.label())
            if isAvailable():
                found.append(mesher.value)
        return found

    def requireFTetWild(self):
        """Skip the test that called this if fTetWild is not to be had."""
        if Mesher.FTETWILD.value not in self.meshers():
            self.skipTest("fTetWild is not installed and could not be installed")

    def requireNetgen(self):
        """Skip the test that called this if Netgen is not to be had."""
        if Mesher.NETGEN.value not in self.meshers():
            self.skipTest("Netgen is not installed and could not be installed")

    @staticmethod
    def fasterFTetWild(mesher):
        """The arguments that keep an fTetWild run in a test suite short. Its default is eighty
        passes of improvement, which is more than a tube of two thousand elements needs."""
        if mesher != Mesher.FTETWILD.value:
            return {}
        return dict(maxOptimizationPasses=20)

    @staticmethod
    def openTube(numberOfAxialPoints=12, numberOfCircumferentialPoints=24, height=10.0, radius=1.0):
        """A tube open at both ends, standing in for a clipped vessel."""
        import math
        points, polys = vtk.vtkPoints(), vtk.vtkCellArray()
        for axialIndex in range(numberOfAxialPoints):
            z = height * axialIndex / (numberOfAxialPoints - 1)
            for circumferentialIndex in range(numberOfCircumferentialPoints):
                angle = 2.0 * math.pi * circumferentialIndex / numberOfCircumferentialPoints
                points.InsertNextPoint(radius * math.cos(angle), radius * math.sin(angle), z)
        for axialIndex in range(numberOfAxialPoints - 1):
            for circumferentialIndex in range(numberOfCircumferentialPoints):
                nextIndex = (circumferentialIndex + 1) % numberOfCircumferentialPoints
                first = axialIndex * numberOfCircumferentialPoints + circumferentialIndex
                second = axialIndex * numberOfCircumferentialPoints + nextIndex
                third = (axialIndex + 1) * numberOfCircumferentialPoints + circumferentialIndex
                fourth = (axialIndex + 1) * numberOfCircumferentialPoints + nextIndex
                polys.InsertNextCell(3, [first, second, fourth])
                polys.InsertNextCell(3, [first, fourth, third])
        surface = vtk.vtkPolyData()
        surface.SetPoints(points)
        surface.SetPolys(polys)
        return surface

    @staticmethod
    def cellEntityIds(mesh, arrayName="CellEntityIds"):
        array = mesh.GetCellData().GetArray(arrayName)
        if array is None:
            return set()
        return set(int(array.GetTuple1(index)) for index in range(array.GetNumberOfTuples()))

    @staticmethod
    def surfaceAreaOfCells(mesh, keep):
        """The total area of the cells of the mesh that keep(cellId) says to count."""
        total = 0.0
        for cellId in range(mesh.GetNumberOfCells()):
            if not keep(cellId):
                continue
            cell = mesh.GetCell(cellId)
            if cell.GetCellDimension() != 2:
                continue
            points = [cell.GetPoints().GetPoint(index) for index in range(cell.GetNumberOfPoints())]
            # Fan the polygon about its first corner. Every 2D cell here is a triangle or a
            # planar quad, so the fan covers it exactly.
            for index in range(1, len(points) - 1):
                total += vtk.vtkTriangle.TriangleArea(points[0], points[index], points[index + 1])
        return total

    def assertTetrahedraArePositive(self, mesh, message=""):
        """Every volume element must be wound the way VTK winds one.

        A solver handed an element that is inside out reads a negative volume for it, and the
        mesh it computes on is not the mesh it was shown. It is worth asking wherever a sweep or
        a mesher decides the order of an element's corners for itself.
        """
        inverted = 0
        for cellId in range(mesh.GetNumberOfCells()):
            cell = mesh.GetCell(cellId)
            if cell.GetCellDimension() != 3:
                continue
            points = [mesh.GetPoint(cell.GetPointId(index))
                      for index in range(cell.GetNumberOfPoints())]
            if cell.GetCellType() == vtk.VTK_TETRA:
                if vtk.vtkTetra.ComputeVolume(*points[:4]) <= 0.0:
                    inverted += 1
            elif cell.GetCellType() == vtk.VTK_WEDGE:
                # The base triangle's normal has to point away from the face opposite it.
                normal = [0.0, 0.0, 0.0]
                vtk.vtkTriangle.ComputeNormal(points[0], points[1], points[2], normal)
                base = [sum(point[axis] for point in points[:3]) / 3.0 for axis in range(3)]
                top = [sum(point[axis] for point in points[3:]) / 3.0 for axis in range(3)]
                if sum(normal[axis] * (top[axis] - base[axis]) for axis in range(3)) > 0.0:
                    inverted += 1
        self.assertEqual(inverted, 0,
                         "%d volume elements are inside out %s" % (inverted, message))

    def assertBoundaryIsLabelled(self, mesh, arrayName, message=""):
        """Every face on the outside of the volume must be a labelled cell of the mesh.

        A boundary condition is assigned per face id, so a solver reading this mesh has to find
        one on every face it can reach from the outside. Areas rather than cells, because the
        volume elements and the surface cells that stand against them need not be split the same
        way: what has to match is the surface they cover.
        """
        volume = vtk.vtkExtractCellsByType()
        volume.SetInputData(mesh)
        for cellType in (vtk.VTK_TETRA, vtk.VTK_WEDGE, vtk.VTK_HEXAHEDRON,
                         vtk.VTK_QUADRATIC_TETRA, vtk.VTK_QUADRATIC_WEDGE):
            volume.AddCellType(cellType)
        volume.Update()
        outside = vtk.vtkGeometryFilter()
        outside.SetInputData(volume.GetOutput())
        outside.MergingOff()
        outside.Update()

        outsideArea = self.surfaceAreaOfCells(outside.GetOutput(), lambda cellId: True)
        ids = mesh.GetCellData().GetArray(arrayName)
        labelledArea = self.surfaceAreaOfCells(
            mesh, lambda cellId: ids is not None and int(ids.GetTuple1(cellId)) >= 1)
        self.assertGreater(outsideArea, 0.0, "the mesh has no volume elements %s" % message)
        self.assertAlmostEqual(
            labelledArea / outsideArea, 1.0, delta=0.01,
            msg="the labelled faces cover %.1f%% of the outside of the volume %s"
                % (100.0 * labelledArea / outsideArea, message))

