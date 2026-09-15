"""Where the names of a mesh's faces are to be found, carried from the clipped surface onto it.

The face ids already survive meshing (test_CfdMeshGeneratorFaceIds). A face id is a number,
though, and a boundary condition is per vessel: the names are control point labels on the clip
points markups node, and what has to travel is the pointer to them. Losing it costs an operator
twenty-odd caps named by eye; carrying a stale one is worse, because it names them wrongly and
says nothing about it.
"""

import json
import logging
import unittest

import slicer
import vtk

from CfdMeshGenerator import CfdMeshGeneratorLogic
from CfdMeshGeneratorTestFixture import CfdMeshGeneratorTestCase

FACE_ID_MAP_ATTRIBUTE, WALL_FACE_ID_ATTRIBUTE = CfdMeshGeneratorLogic.nameSourceAttributeNames
CLIP_POINTS_ROLE = CfdMeshGeneratorLogic.clipPointsNodeReferenceRole


class RecordingLogic(CfdMeshGeneratorLogic):
    """Logic that keeps what it says, so a warning can be asserted on rather than read in a log."""

    def __init__(self):
        CfdMeshGeneratorLogic.__init__(self)
        self.said = []

    def say(self, text, level=logging.INFO):
        self.said.append((level, text))

    @property
    def warnings(self):
        return [text for level, text in self.said if level >= logging.WARNING]


class CfdMeshGeneratorNameSourceTest(CfdMeshGeneratorTestCase):

    def gridWithFaceIds(self, faceIds, arrayName="ModelFaceID"):
        """A grid whose cells carry the given face ids, one triangle each.

        Nothing here reads the geometry - only which ids the mesh has cells on - so the cells are
        the cheapest thing that can carry one.
        """
        grid = vtk.vtkUnstructuredGrid()
        points = vtk.vtkPoints()
        for index in range(len(faceIds)):
            points.InsertNextPoint(index, 0, 0)
            points.InsertNextPoint(index, 1, 0)
            points.InsertNextPoint(index, 0, 1)
        grid.SetPoints(points)
        for index in range(len(faceIds)):
            triangle = vtk.vtkTriangle()
            for corner in range(3):
                triangle.GetPointIds().SetId(corner, 3 * index + corner)
            grid.InsertNextCell(triangle.GetCellType(), triangle.GetPointIds())
        array = vtk.vtkIntArray()
        array.SetName(arrayName)
        for faceId in faceIds:
            array.InsertNextValue(faceId)
        grid.GetCellData().AddArray(array)
        return grid

    def clippedSurface(self, faceIdToClipPointId, wallFaceId=1):
        """A model node standing in for Clip Vessel's output: the record, and the node it points at."""
        markups = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "Clip points")
        surface = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Clipped surface")
        surface.SetNodeReferenceID(CLIP_POINTS_ROLE, markups.GetID())
        surface.SetAttribute(FACE_ID_MAP_ATTRIBUTE,
                             json.dumps({str(faceId): controlPointId for faceId, controlPointId
                                         in sorted(faceIdToClipPointId.items())},
                                        separators=(",", ":")))
        surface.SetAttribute(WALL_FACE_ID_ATTRIBUTE, str(wallFaceId))
        return surface, markups

    def test_CfdMeshGeneratorCarriesTheNameSourceOntoTheMesh(self):
        """The reference and both attributes arrive on the mesh, and resolve to the same names.

        Checked by resolving them rather than by comparing the strings: what the chain is for is
        getting from a face id to a vessel name, and that is the only thing about the format worth
        holding this module to.
        """
        surface, markups = self.clippedSurface({2: "vtkMRMLMarkupsFiducialNode1_1",
                                                3: "vtkMRMLMarkupsFiducialNode1_2"})
        for label in ("RSVC", "IVC"):
            markups.SetNthControlPointLabel(markups.AddControlPoint([0.0, 0.0, 0.0]), label)
        controlPointIds = [markups.GetNthControlPointID(index) for index in range(2)]
        surface.SetAttribute(FACE_ID_MAP_ATTRIBUTE,
                             json.dumps({"2": controlPointIds[0], "3": controlPointIds[1]},
                                        separators=(",", ":")))

        mesh = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Mesh")
        logic = RecordingLogic()
        logic.copyNameSource(surface, mesh, self.gridWithFaceIds([1, 1, 2, 3]), "ModelFaceID")

        self.assertEqual(mesh.GetNodeReference(CLIP_POINTS_ROLE), markups)
        self.assertEqual(mesh.GetAttribute(WALL_FACE_ID_ATTRIBUTE), "1")
        self.assertEqual(logic.warnings, [])

        stored = json.loads(mesh.GetAttribute(FACE_ID_MAP_ATTRIBUTE))
        resolved = {}
        for faceId, controlPointId in stored.items():
            index = markups.GetNthControlPointIndexByID(controlPointId)
            resolved[int(faceId)] = markups.GetNthControlPointLabel(index) if index >= 0 else None
        self.assertEqual(resolved, {2: "RSVC", 3: "IVC"})

    def test_CfdMeshGeneratorKeepsNamesOffFacesTheDeletedClipPointNamed(self):
        """Deleting a clip point leaves its face unnamed and every other face where it was.

        This is what keying the map by control point ID rather than by index buys, and the only
        test here that would fail if it were keyed by index instead. A cap's face id is
        firstCapFaceId + clip point index, so deleting the middle of three clip points shifts the
        last one's index down onto the deleted one's face: by index the third vessel's name would
        move silently onto the second vessel's cap, which downstream is an inflow waveform on the
        wrong vein. By ID the deleted point fails the lookup and its face falls back to unnamed.
        """
        markups = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "Clip points")
        for label in ("RSVC", "IVC", "LPA"):
            markups.SetNthControlPointLabel(markups.AddControlPoint([0.0, 0.0, 0.0]), label)
        controlPointIds = [markups.GetNthControlPointID(index) for index in range(3)]
        surface = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Clipped surface")
        surface.SetNodeReferenceID(CLIP_POINTS_ROLE, markups.GetID())
        surface.SetAttribute(FACE_ID_MAP_ATTRIBUTE, json.dumps(
            {"2": controlPointIds[0], "3": controlPointIds[1], "4": controlPointIds[2]},
            separators=(",", ":")))
        surface.SetAttribute(WALL_FACE_ID_ATTRIBUTE, "1")

        mesh = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Mesh")
        RecordingLogic().copyNameSource(surface, mesh, self.gridWithFaceIds([1, 2, 3, 4]),
                                        "ModelFaceID")

        markups.RemoveNthControlPoint(1)   # the IVC, whose cap is face 3

        stored = json.loads(mesh.GetAttribute(FACE_ID_MAP_ATTRIBUTE))
        resolved = {}
        for faceId, controlPointId in stored.items():
            index = markups.GetNthControlPointIndexByID(controlPointId)
            resolved[int(faceId)] = markups.GetNthControlPointLabel(index) if index >= 0 else None
        self.assertEqual(resolved, {2: "RSVC", 3: None, 4: "LPA"})

    def test_CfdMeshGeneratorSaysWhenAFaceItNamesHasNoCells(self):
        """A recorded face the mesh has no cells on is said out loud.

        The last point at which a lost cap is cheap to notice. Meshing can drop one - a boundary
        layer strips the caps and remakes them - and a name with no face to attach to becomes, in
        a case setup, a boundary condition on whatever is left.
        """
        surface, _markups = self.clippedSurface({2: "cp2", 3: "cp3", 4: "cp4"})
        mesh = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Mesh")

        logic = RecordingLogic()
        logic.copyNameSource(surface, mesh, self.gridWithFaceIds([1, 2, 4]), "ModelFaceID")

        self.assertEqual(len(logic.warnings), 1)
        self.assertIn("3", logic.warnings[0])
        # Carried on all the same: the two faces that are there are still named, and the operator
        # has been told which one is not.
        self.assertEqual(sorted(json.loads(mesh.GetAttribute(FACE_ID_MAP_ATTRIBUTE))), ["2", "3", "4"])

    def test_CfdMeshGeneratorClearsTheNameSourceOfAnUnclippedInput(self):
        """A mesh made from a surface that was not clipped here keeps no record from the one before.

        The output node is reused across runs, so what is left on it is the previous mesh's. Left
        behind, it would name this mesh's faces after another case's vessels - and every one of
        them plausibly, since both are just numbers.
        """
        surface, markups = self.clippedSurface({2: "cp2"})
        mesh = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Mesh")
        logic = RecordingLogic()
        logic.copyNameSource(surface, mesh, self.gridWithFaceIds([1, 2]), "ModelFaceID")
        self.assertIsNotNone(mesh.GetAttribute(FACE_ID_MAP_ATTRIBUTE))

        plain = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Never clipped")
        logic.copyNameSource(plain, mesh, self.gridWithFaceIds([1, 2]), "ModelFaceID")

        self.assertIsNone(mesh.GetNodeReference(CLIP_POINTS_ROLE))
        self.assertIsNone(mesh.GetAttribute(FACE_ID_MAP_ATTRIBUTE))
        self.assertIsNone(mesh.GetAttribute(WALL_FACE_ID_ATTRIBUTE))

    # -- the geometric check ------------------------------------------------------------
    def gridWithFacesAt(self, positionsByFaceId):
        """A grid with a few cells on each face id, clustered at the given position.

        Enough for the check under test, which reads only where the cells of a face average out.
        """
        grid = vtk.vtkUnstructuredGrid()
        points = vtk.vtkPoints()
        array = vtk.vtkIntArray()
        array.SetName("ModelFaceID")
        for faceId, position in sorted(positionsByFaceId.items()):
            for corner in ((0.0, 0.0, 0.0), (0.1, 0.0, 0.0), (0.0, 0.1, 0.0)):
                points.InsertNextPoint(position[0] + corner[0], position[1] + corner[1],
                                       position[2] + corner[2])
            first = points.GetNumberOfPoints() - 3
            triangle = vtk.vtkTriangle()
            for corner in range(3):
                triangle.GetPointIds().SetId(corner, first + corner)
            grid.InsertNextCell(triangle.GetCellType(), triangle.GetPointIds())
            array.InsertNextValue(faceId)
        grid.SetPoints(points)
        grid.GetCellData().AddArray(array)
        return grid

    def clipPointsAt(self, positions):
        """A markups node with a control point at each position, and its control point IDs."""
        markups = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "Clip points")
        ids = []
        for index, position in enumerate(positions):
            markups.AddControlPoint(list(position))
            markups.SetNthControlPointLabel(index, "end %d" % index)
            ids.append(markups.GetNthControlPointID(index))
        return markups, ids

    def test_CfdMeshGeneratorAcceptsCapsThatSitAtTheirOwnClipPoints(self):
        """Nothing said when the record and the geometry agree."""
        markups, ids = self.clipPointsAt([(0.0, 0.0, 0.0), (50.0, 0.0, 0.0)])
        mesh = self.gridWithFacesAt({2: (0.0, 0.0, 0.0), 3: (50.0, 0.0, 0.0)})
        faceIdMap = json.dumps({"2": ids[0], "3": ids[1]})

        logic = RecordingLogic()
        logic.checkCapsSitAtTheirClipPoints(markups, faceIdMap, mesh, "ModelFaceID")
        self.assertEqual(logic.warnings, [])

    def test_CfdMeshGeneratorSaysWhenTwoCapIdsAreSwapped(self):
        """The fault no other check can see.

        The ids are the expected set, every one is present and in range, and each names a real
        clip point - they are simply on each other's caps. Only the geometry disagrees.
        """
        markups, ids = self.clipPointsAt([(0.0, 0.0, 0.0), (50.0, 0.0, 0.0)])
        mesh = self.gridWithFacesAt({2: (0.0, 0.0, 0.0), 3: (50.0, 0.0, 0.0)})
        swapped = json.dumps({"2": ids[1], "3": ids[0]})

        logic = RecordingLogic()
        logic.checkCapsSitAtTheirClipPoints(markups, swapped, mesh, "ModelFaceID")
        self.assertEqual(len(logic.warnings), 1)
        self.assertIn("2", logic.warnings[0])
        self.assertIn("3", logic.warnings[0])

    def test_CfdMeshGeneratorSaysWhenThreeCapIdsAreRotated(self):
        """A rotation rather than a swap, which is what the boundary layer bug actually did."""
        markups, ids = self.clipPointsAt([(0.0, 0.0, 0.0), (50.0, 0.0, 0.0), (0.0, 50.0, 0.0)])
        mesh = self.gridWithFacesAt({2: (0.0, 0.0, 0.0), 3: (50.0, 0.0, 0.0), 4: (0.0, 50.0, 0.0)})
        rotated = json.dumps({"2": ids[1], "3": ids[2], "4": ids[0]})

        logic = RecordingLogic()
        logic.checkCapsSitAtTheirClipPoints(markups, rotated, mesh, "ModelFaceID")
        self.assertEqual(len(logic.warnings), 1)

    def test_CfdMeshGeneratorSaysNothingAboutASingleVesselEnd(self):
        """One end, so there is nothing a permutation could have done and nothing to report."""
        markups, ids = self.clipPointsAt([(0.0, 0.0, 0.0)])
        mesh = self.gridWithFacesAt({2: (40.0, 0.0, 0.0)})

        logic = RecordingLogic()
        logic.checkCapsSitAtTheirClipPoints(markups, json.dumps({"2": ids[0]}), mesh, "ModelFaceID")
        self.assertEqual(logic.warnings, [])

    def test_CfdMeshGeneratorSaysNothingWhenAClipPointIsGone(self):
        """A face whose clip point was deleted comes out unnamed downstream, which is the right
        answer already; there is nothing left to hold it against."""
        markups, ids = self.clipPointsAt([(0.0, 0.0, 0.0), (50.0, 0.0, 0.0)])
        mesh = self.gridWithFacesAt({2: (0.0, 0.0, 0.0), 3: (50.0, 0.0, 0.0)})
        faceIdMap = json.dumps({"2": ids[0], "3": ids[1]})
        markups.RemoveNthControlPoint(1)

        logic = RecordingLogic()
        logic.checkCapsSitAtTheirClipPoints(markups, faceIdMap, mesh, "ModelFaceID")
        self.assertEqual(logic.warnings, [])

    def test_CfdMeshGeneratorChecksTheGeometryFromCopyNameSource(self):
        """The check is reached by the ordinary path, not only when called directly."""
        markups, ids = self.clipPointsAt([(0.0, 0.0, 0.0), (50.0, 0.0, 0.0)])
        surface = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Clipped surface")
        surface.SetNodeReferenceID(CLIP_POINTS_ROLE, markups.GetID())
        surface.SetAttribute(FACE_ID_MAP_ATTRIBUTE, json.dumps({"2": ids[1], "3": ids[0]}))
        surface.SetAttribute(WALL_FACE_ID_ATTRIBUTE, "1")
        mesh = self.gridWithFacesAt({2: (0.0, 0.0, 0.0), 3: (50.0, 0.0, 0.0)})
        meshNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Mesh")

        logic = RecordingLogic()
        logic.copyNameSource(surface, meshNode, mesh, "ModelFaceID")
        self.assertTrue(any("not where" in text for text in logic.warnings),
                        "copyNameSource should report the swap: %s" % logic.warnings)

    def test_CfdMeshGeneratorNameSourceSurvivesASavedScene(self):
        """The record comes back with the scene, which is what makes naming a mesh worth doing once.

        A node reference and a node attribute both serialize into MRML, so this asks nothing of
        this module beyond using them - which is the reason they were chosen over a file beside
        the mesh or an array on it.
        """
        surface, markups = self.clippedSurface({2: "cp2", 3: "cp3"})
        markups.SetNthControlPointLabel(markups.AddControlPoint([0.0, 0.0, 0.0]), "RSVC")
        mesh = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Mesh")
        mesh.SetName("Mesh to reload")
        RecordingLogic().copyNameSource(surface, mesh, self.gridWithFaceIds([1, 2, 3]),
                                        "ModelFaceID")
        # A model node with no mesh is not written into the bundle, and a reference to a node
        # that was not saved does not come back.
        sphere = vtk.vtkSphereSource()
        sphere.Update()
        mesh.SetAndObserveMesh(sphere.GetOutput())
        expectedMap = mesh.GetAttribute(FACE_ID_MAP_ATTRIBUTE)

        bundle = slicer.app.temporaryPath + "/CfdMeshGeneratorNameSource.mrb"
        self.assertTrue(slicer.util.saveScene(bundle))
        slicer.mrmlScene.Clear(False)
        self.assertTrue(slicer.util.loadScene(bundle))

        reloaded = slicer.util.getNode("Mesh to reload")
        self.assertEqual(reloaded.GetAttribute(FACE_ID_MAP_ATTRIBUTE), expectedMap)
        self.assertEqual(reloaded.GetAttribute(WALL_FACE_ID_ATTRIBUTE), "1")
        reloadedMarkups = reloaded.GetNodeReference(CLIP_POINTS_ROLE)
        self.assertIsNotNone(reloadedMarkups)
        self.assertEqual(reloadedMarkups.GetNthControlPointLabel(0), "RSVC")


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
