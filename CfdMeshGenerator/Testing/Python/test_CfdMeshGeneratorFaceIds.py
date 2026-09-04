"""Which face each cell of the output belongs to, and which vessel end each cap closes.

This is what a solver reads its boundary conditions off, so a cap under the wrong id is an
inlet condition on an outlet."""

import unittest

import slicer
import vtk

from CfdMeshGenerator import CfdMeshGeneratorLogic, Mesher
from CfdMeshGeneratorTestFixture import CfdMeshGeneratorTestCase


class CfdMeshGeneratorFaceIdsTest(CfdMeshGeneratorTestCase):

    def test_CfdMeshGeneratorNamesCapsAfterVesselEnds(self):
        """A cap is named after the vessel end it closes, whether the surface says which end that
        is or only where it is.

        A surface from Clip Vessel carries the labels that say it, and then the id of an end is
        the one Clip Vessel gives it - the same one every run, whatever order the boundaries come
        out of the extractor in. A surface that has lost them falls back to where the cap was,
        which has to reach the same answer or a solver reads the inlet condition off the outlet.
        """
        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry

        logic = CfdMeshGeneratorLogic()
        labeler = vtkvmtkComputationalGeometry.vtkvmtkPolyDataBoundaryLabeler()
        labeler.SetInputData(self.openTube())
        labeler.SetBoundaryLabelsArrayName(logic.boundaryLabelsArrayName)
        labeler.SetBoundaryPointOrderArrayName(logic.boundaryPointOrderArrayName)
        # A label is the id of the cap that closes its boundary, so the boundaries are numbered
        # above the wall this module sets its caps into. It is the labeler's own default too; said
        # here because a surface labelled for some other wall would be capped over the wall's face.
        labeler.SetCellEntityIdOffset(logic.wallCellEntityId)
        labeler.Update()

        def middleOfEachFace(mesh):
            """How far along the tube each face sits, so that an id can be read against the end
            it is on: the tube runs from z = 0 to z = 10."""
            array = mesh.GetCellData().GetArray("ModelFaceID")
            sums, counts = {}, {}
            for cellId in range(mesh.GetNumberOfCells()):
                if mesh.GetCellType(cellId) not in (vtk.VTK_TRIANGLE, vtk.VTK_QUAD,
                                                    vtk.VTK_POLYGON):
                    continue
                entityId = int(array.GetTuple1(cellId))
                cell = mesh.GetCell(cellId)
                for index in range(cell.GetNumberOfPoints()):
                    sums[entityId] = sums.get(entityId, 0.0) + mesh.GetPoint(
                        cell.GetPointId(index))[2]
                    counts[entityId] = counts.get(entityId, 0) + 1
            return {faceId: sums[faceId] / counts[faceId] for faceId in sums}

        labelled = labeler.GetOutput()
        capped = logic.capSurface(labelled, "ModelFaceID", "simple")
        middles = middleOfEachFace(capped)
        self.assertEqual(sorted(middles), [1, 2, 3])
        # the point data and the cell data are one numbering: the end labelled 2 is face 2
        boundaryLabels = set(
            int(labelled.GetPointData().GetArray(logic.boundaryLabelsArrayName).GetTuple1(pointId))
            for pointId in range(labelled.GetNumberOfPoints()))
        self.assertEqual(sorted(label for label in boundaryLabels if label >= 0), [2, 3])
        self.assertLess(middles[2], 1.0, "the cap of the first vessel end is not face 2")
        self.assertGreater(middles[3], 9.0, "the cap of the second vessel end is not face 3")

        # Taken off and rebuilt past a boundary layer, with and without anything saying which end
        # is which, the ids have to come back on the same ends.
        for mesher in self.meshers():
            for keepLabels in (True, False):
                where = "(%s, labels kept: %s)" % (mesher, keepLabels)
                surface = vtk.vtkPolyData()
                surface.DeepCopy(capped)
                if not keepLabels:
                    surface.GetPointData().RemoveArray(logic.boundaryLabelsArrayName)
                    surface.GetPointData().RemoveArray(logic.boundaryPointOrderArrayName)

                mesh, _remeshedSurface = logic.generateMesh(
                    surface, targetEdgeLength=0.4, cellEntityIdsArrayName="ModelFaceID",
                    skipCapping=True, boundaryLayer=True, boundaryLayerOnCaps=False,
                    mesher=mesher, **self.fasterFTetWild(mesher))

                middles = middleOfEachFace(mesh)
                self.assertLess(middles[2], 1.0, "face 2 came back on the wrong end " + where)
                self.assertGreater(middles[3], 9.0, "face 3 came back on the wrong end " + where)


    def test_CfdMeshGeneratorKeepsTheLabelsOfTheInput(self):
        """A surface that arrives already capped and labelled - as one from Clip Vessel does -
        keeps its faces, and the rim between a cap and the wall survives remeshing.

        The ids are what hold the two apart while the remesher works. Read under the wrong name
        the surface is one face as far as the remesher is concerned, and it smooths the rim away:
        the cap stops being flat, which is what a solver's inlet condition needs it to be.
        """
        logic = CfdMeshGeneratorLogic()
        labelled = logic.capSurface(self.openTube(), "ModelFaceID", "simple")
        _mesh, remeshedSurface = logic.generateMesh(
            labelled, targetEdgeLength=0.4, cellEntityIdsArrayName="ModelFaceID", skipCapping=True)

        ids = remeshedSurface.GetCellData().GetArray("ModelFaceID")
        self.assertIsNotNone(ids, "the labels of the input were not carried through")
        self.assertEqual(sorted(set(int(ids.GetTuple1(index))
                                    for index in range(ids.GetNumberOfTuples()))), [1, 2, 3])

        for capId in (2, 3):
            heights = []
            for cellId in range(remeshedSurface.GetNumberOfCells()):
                if int(ids.GetTuple1(cellId)) != capId:
                    continue
                cell = remeshedSurface.GetCell(cellId)
                heights.extend(remeshedSurface.GetPoint(cell.GetPointId(index))[2]
                               for index in range(cell.GetNumberOfPoints()))
            self.assertTrue(heights, "cap %d lost every cell it had" % capId)
            self.assertLess(max(heights) - min(heights), 1e-6,
                            "cap %d is no longer flat, so its rim was not held" % capId)


    def test_CfdMeshGeneratorCarriesCellArraysFaceByFace(self):
        """An array of the input surface asked to be carried arrives on the output, face by face.

        A surface that numbers its caps by an array of its own - one number for the inlet and
        one for every outlet, say - keeps that numbering on the mesh: every cell of a face the
        input had gets the value the face had, whatever the remesher made of its cells, and the
        volume elements get -1, which no face is. The remeshed surface carries it too.
        """
        logic = CfdMeshGeneratorLogic()
        # Capped here, and labelled so that the caps are two faces - 2 and 3 - which the array
        # numbers 1 and 1: the case of two outlets under one number, which a face id cannot
        # express and a carried array can.
        surface = logic.capSurface(self.openTube(), "CellEntityIds", "simple")
        faceIds = surface.GetCellData().GetArray("CellEntityIds")
        capIds = vtk.vtkIntArray()
        capIds.SetName("CapID")
        capIds.SetNumberOfTuples(surface.GetNumberOfCells())
        for cellId in range(surface.GetNumberOfCells()):
            capIds.SetTuple1(cellId, 1 if faceIds.GetTuple1(cellId) > 1 else -1)
        surface.GetCellData().AddArray(capIds)

        for mesher in self.meshers():
            mesh, remeshedSurface = logic.generateMesh(
                surface, targetEdgeLength=0.4, skipCapping=True, mesher=mesher,
                carriedCellArrays=["CapID", "NoSuchArray"], **self.fasterFTetWild(mesher))

            for output in (mesh, remeshedSurface):
                carried = output.GetCellData().GetArray("CapID")
                self.assertIsNotNone(carried, "CapID was not carried onto the output (%s)" % mesher)
                self.assertIsNone(output.GetCellData().GetArray("NoSuchArray"))
                ids = output.GetCellData().GetArray("CellEntityIds")
                for cellId in range(output.GetNumberOfCells()):
                    faceId = int(ids.GetTuple1(cellId))
                    expected = (-1 if output.GetCell(cellId).GetCellDimension() == 3
                                else 1 if faceId > 1 else -1)
                    self.assertEqual(int(carried.GetTuple1(cellId)), expected,
                                     "cell %d on face %d carries the wrong CapID (%s)"
                                     % (cellId, faceId, mesher))
            self.assertIn(1, set(int(mesh.GetCellData().GetArray("CapID").GetTuple1(cellId))
                                 for cellId in range(mesh.GetNumberOfCells())),
                          "no cell of the mesh is a cap (%s)" % mesher)

    def test_CfdMeshGeneratorReadsTheFacesFromWhicheverNameTheSurfaceCarries(self):
        """The face ids array is the first of the names offered that the surface carries, and
        the first name of all when it carries none.

        A surface arrives labelled under whatever name the tool that labelled it uses - VMTK's
        CellEntityIds, SimVascular's ModelFaceID - and both are offered by default, so that
        either is read as labelled without the name being typed in.
        """
        logic = CfdMeshGeneratorLogic()
        choose = logic.chooseCellEntityIdsArrayName

        unlabelled = self.openTube()
        self.assertEqual(choose(unlabelled, "CellEntityIds, ModelFaceID"), "CellEntityIds")
        self.assertEqual(choose(unlabelled, ["ModelFaceID", "CellEntityIds"]), "ModelFaceID")

        fromSimVascular = logic.capSurface(self.openTube(), "ModelFaceID", "simple")
        self.assertEqual(choose(fromSimVascular, "CellEntityIds, ModelFaceID"), "ModelFaceID")
        # Whitespace around the commas is not part of a name.
        self.assertEqual(choose(fromSimVascular, "  CellEntityIds ,ModelFaceID , "), "ModelFaceID")
        # The first the surface carries, in the order offered, where it carries more than one.
        both = vtk.vtkPolyData()
        both.DeepCopy(fromSimVascular)
        secondName = vtk.vtkIntArray()
        secondName.DeepCopy(both.GetCellData().GetArray("ModelFaceID"))
        secondName.SetName("CellEntityIds")
        both.GetCellData().AddArray(secondName)
        self.assertEqual(choose(both, "CellEntityIds, ModelFaceID"), "CellEntityIds")
        self.assertEqual(choose(both, "ModelFaceID, CellEntityIds"), "ModelFaceID")

        with self.assertRaises(ValueError):
            choose(unlabelled, " , ")

        # And through the parameter node, the way Apply goes: a surface labelled under
        # ModelFaceID comes out labelled under ModelFaceID, ids kept.
        inputNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "tube")
        inputNode.SetAndObserveMesh(fromSimVascular)
        outputNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "mesh")
        parameterNode = logic.getParameterNode()
        parameterNode.inputSurface = inputNode
        parameterNode.outputMesh = outputNode
        parameterNode.targetEdgeLength = 0.4
        parameterNode.boundaryLayer = False
        self.assertEqual(parameterNode.cellEntityIdsArrayNames, "CellEntityIds, ModelFaceID")
        self.assertEqual(logic.meshingArguments(parameterNode)["cellEntityIdsArrayName"],
                         "ModelFaceID")
        if logic.isTetGenAvailable():
            logic.process(parameterNode)
            mesh = outputNode.GetMesh()
            self.assertIsNone(mesh.GetCellData().GetArray("CellEntityIds"))
            self.assertEqual(self.cellEntityIds(mesh, "ModelFaceID"), {0, 1, 2, 3})


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
