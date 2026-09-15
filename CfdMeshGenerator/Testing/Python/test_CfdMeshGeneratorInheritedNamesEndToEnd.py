"""Clip to mesh, on the path a real workflow takes, checking the names land on the right faces.

The other suites check the two halves separately: that Clip Vessel writes the record, and that
this module carries it across. Neither would catch the thing most likely to go wrong, which is
the two halves disagreeing about the numbering - and they are worked out in different modules,
from different data, at different times.

So this clips a real vessel the way the Fontan workflow clips it, with **capping and face
labeling both off**, meshes it here, and checks that every face id the record names is a face
the mesh actually has. That combination is the one that matters and the one that looks least
likely to work: the clipped surface carries no caps and no face id array at all, and the ids
its mesh ends up with come from the BoundaryLabels point data.
"""

import json
import logging
import unittest

import numpy as np
import slicer
import vtk
from vtk.util.numpy_support import vtk_to_numpy

from CfdMeshGenerator import CfdMeshGeneratorLogic, Mesher
from CfdMeshGeneratorTestFixture import CfdMeshGeneratorTestCase

FACE_ID_MAP_ATTRIBUTE, WALL_FACE_ID_ATTRIBUTE = CfdMeshGeneratorLogic.nameSourceAttributeNames
CLIP_POINTS_ROLE = CfdMeshGeneratorLogic.clipPointsNodeReferenceRole


class InheritedNamesEndToEndTest(CfdMeshGeneratorTestCase):

    @classmethod
    def setUpClass(cls):
        import sys

        # The fixture lives with Clip Vessel's tests; both modules are on the path of a Slicer
        # that has the extension, but only this module's test directory is on sys.path.
        import ClipVessel
        clipVesselTests = ClipVessel.__file__.rsplit("/", 1)[0] + "/Testing/Python"
        if clipVesselTests not in sys.path:
            sys.path.append(clipVesselTests)
        from ClipVesselTestFixture import aortaCase
        cls.case = aortaCase()

    @staticmethod
    def controlPointPosition(markups, index):
        position = [0.0, 0.0, 0.0]
        markups.GetNthControlPointPositionWorld(index, position)
        return position

    @staticmethod
    def capCentres(mesh, cellEntityIdsArrayName, wallFaceId):
        """Where each cap of the mesh is: {face id: centre of its cells}, wall and volume left out."""
        ids = vtk_to_numpy(mesh.GetCellData().GetArray(cellEntityIdsArrayName)).astype(np.int64)
        centers = vtk.vtkCellCenters()
        centers.SetInputData(mesh)
        centers.Update()
        points = vtk_to_numpy(centers.GetOutput().GetPoints().GetData())
        return {int(faceId): points[ids == faceId].mean(axis=0)
                for faceId in np.unique(ids) if int(faceId) > wallFaceId}

    def clippedWithNothingButTheRecord(self):
        """The aorta clipped as the workflow clips it, and a model node carrying the record.

        The clip points node is put back into the scene first. The case is built once in
        setUpClass because building it extracts a real centerline, and the base setUp clears
        the scene between tests - which takes the markups node out from under it, and a node
        reference to a node the scene has not got resolves to nothing.
        """
        case = self.case
        if not slicer.mrmlScene.IsNodePresent(case.clipPointsMarkupsNode):
            slicer.mrmlScene.AddNode(case.clipPointsMarkupsNode)
        surface = case.clip(cap=False, labelModelFaces=False)
        self.assertIsNone(surface.GetCellData().GetArray("ModelFaceID"),
                          "this run is meant to produce no face id array")

        node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Clipped surface")
        node.SetAndObserveMesh(surface)
        case.logic.recordNameSource(node, case.clipPointsMarkupsNode)
        self.assertIsNotNone(node.GetAttribute(FACE_ID_MAP_ATTRIBUTE),
                             "the record has to be written even with labeling off")
        return case, node

    def assertNamesSurviveMeshing(self, **meshingArguments):
        """The record Clip Vessel wrote and the ids this module hands out are one numbering.

        The assertion that matters is not that the attributes were copied - another test covers
        that - but that they still mean something at the far end: every face id the record names
        is a face the finished mesh has cells on, and the wall is the wall.
        """
        case, surfaceNode = self.clippedWithNothingButTheRecord()
        logic = CfdMeshGeneratorLogic()

        mesh = logic.generateMesh(
            surfaceNode.GetPolyData(),
            targetEdgeLength=2.0,
            cellEntityIdsArrayName="ModelFaceID",
            boundaryLabelsArrayName=logic.boundaryLabelsArrayName,
            boundaryPointOrderArrayName=logic.boundaryPointOrderArrayName,
            cappingMethod="simple",
            mesher=Mesher.TETGEN.value,
            **meshingArguments,
        )[0]

        meshNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Volume mesh")
        meshNode.SetAndObserveMesh(mesh)

        warnings = []
        logic.say = lambda text, level=logging.INFO: (
            warnings.append(text) if level >= logging.WARNING else None)
        logic.copyNameSource(surfaceNode, meshNode, mesh, "ModelFaceID")

        recorded = {int(faceId) for faceId in json.loads(surfaceNode.GetAttribute(FACE_ID_MAP_ATTRIBUTE))}
        onTheMesh = set(self.cellEntityIds(mesh, "ModelFaceID"))
        self.assertTrue(recorded, "nothing was recorded, so this test asserts nothing")
        self.assertTrue(recorded <= onTheMesh,
                        "the record names face(s) the mesh has not got: %s"
                        % sorted(recorded - onTheMesh))
        self.assertEqual(warnings, [], "a complete mesh should draw no warning")

        # The wall is on the mesh too, and is not one of the caps.
        wallFaceId = int(meshNode.GetAttribute(WALL_FACE_ID_ATTRIBUTE))
        self.assertIn(wallFaceId, onTheMesh)
        self.assertNotIn(wallFaceId, recorded)

        # The assertion that matters: every recorded face's cap is at the clip point the record
        # names it after. Comparing the resolved names against the labels in clip point order
        # would prove nothing - the record is built from that order, so it holds by construction
        # whatever the mesh did with the ids.
        markups = meshNode.GetNodeReference(CLIP_POINTS_ROLE)
        self.assertIsNotNone(markups, "the mesh should point at the clip points")
        capCentres = self.capCentres(mesh, "ModelFaceID", wallFaceId)
        for faceId, controlPointId in json.loads(meshNode.GetAttribute(FACE_ID_MAP_ATTRIBUTE)).items():
            faceId = int(faceId)
            index = markups.GetNthControlPointIndexByID(controlPointId)
            self.assertGreaterEqual(index, 0, "face %d names a clip point that is gone" % faceId)
            self.assertIn(faceId, capCentres, "face %d has no cap on the mesh" % faceId)

            distances = sorted((float(np.linalg.norm(np.array(self.controlPointPosition(markups, other))
                                                     - capCentres[faceId])), other)
                               for other in range(markups.GetNumberOfControlPoints()))
            nearest, nearestIndex = distances[0]
            runnerUp = distances[1][0] if len(distances) > 1 else float("inf")
            self.assertEqual(
                index, nearestIndex,
                "the cap carrying face id %d sits at clip point %d (%r, %.2f mm away), not at "
                "the one the record names it after (%r)"
                % (faceId, nearestIndex, markups.GetNthControlPointLabel(nearestIndex), nearest,
                   markups.GetNthControlPointLabel(index)))
            self.assertLess(nearest * 4, runnerUp,
                            "cap %d is %.2f mm from its clip point and %.2f mm from the next, "
                            "too close to tell apart" % (faceId, nearest, runnerUp))

        # The wall should be far and away the largest face; a record that had the wall and a cap
        # the wrong way round would still satisfy everything above.
        faceIds = vtk_to_numpy(mesh.GetCellData().GetArray("ModelFaceID"))
        wallCells = int((faceIds == wallFaceId).sum())
        for faceId in recorded:
            self.assertLess(int((faceIds == faceId).sum()), wallCells,
                            "face %d has more cells than the wall" % faceId)

    def test_every_inherited_name_lands_on_a_face_the_mesh_has(self):
        self.assertNamesSurviveMeshing()

    def test_the_names_survive_a_boundary_layer_stripping_and_remaking_the_caps(self):
        """The case the numbering is least likely to survive, and the one the workflow runs.

        A boundary layer means the caps the surface arrived with are taken off and new ones made
        on the inner surface, so every cap cell in the finished mesh is a cell that did not exist
        when Clip Vessel wrote the record. What carries the identity across is the BoundaryLabels
        point data, which the extension and capping filters move with the points rather than
        renumber - the documented claim this test is here to see rather than take on trust.
        """
        self.assertNamesSurviveMeshing(boundaryLayer=True, boundaryLayerOnCaps=False,
                                       tetrahedralize=True)


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
