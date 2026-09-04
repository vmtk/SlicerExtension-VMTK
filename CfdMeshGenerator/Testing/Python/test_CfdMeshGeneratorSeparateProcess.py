"""The pipeline in a process of its own, which is how Apply runs it.

What has to be true of it: the mesh that comes back is the mesh the pipeline makes, a run can be
stopped, what the pipeline says on its way is heard here, and a worker that dies is reported as
having died rather than as having made nothing."""

import logging
import unittest

import qt
import slicer
import vtk

from CfdMeshGenerator import CfdMeshGeneratorLogic, MeshingCancelledError, Mesher
from CfdMeshGeneratorTestFixture import CfdMeshGeneratorTestCase


class CfdMeshGeneratorSeparateProcessTest(CfdMeshGeneratorTestCase):

    def parameterNode(self, logic, surface):
        inputNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "tube")
        inputNode.SetAndObserveMesh(surface)
        outputNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "mesh")
        parameterNode = logic.getParameterNode()
        parameterNode.inputSurface = inputNode
        parameterNode.outputMesh = outputNode
        parameterNode.targetEdgeLength = 0.4
        parameterNode.boundaryLayer = False
        return parameterNode

    def test_CfdMeshGeneratorProcessMeshesLikeThePipeline(self):
        """The mesh a run in a separate process hands back is the mesh the pipeline makes here.

        Same surface, same parameters, same cells: nothing is lost on the way out to the worker
        and back - not the face ids, which a solver reads its boundary conditions off, and not
        the remeshed surface either.
        """
        logic = CfdMeshGeneratorLogic()
        if not logic.isTetGenAvailable():
            self.skipTest("this installation was built without TetGen")
        surface = self.openTube()
        parameterNode = self.parameterNode(logic, surface)
        remeshedNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "remeshed")
        parameterNode.outputRemeshedSurface = remeshedNode
        parameterNode.carriedCellArrays = ""

        logic.process(parameterNode)

        expectedMesh, expectedSurface = logic.generateMesh(
            surface, targetEdgeLength=0.4, mesher=Mesher.TETGEN.value)
        mesh = parameterNode.outputMesh.GetMesh()
        self.assertEqual(mesh.GetNumberOfCells(), expectedMesh.GetNumberOfCells())
        self.assertEqual(mesh.GetNumberOfPoints(), expectedMesh.GetNumberOfPoints())
        self.assertEqual(self.cellEntityIds(mesh), {0, 1, 2, 3})
        self.assertEqual(remeshedNode.GetMesh().GetNumberOfCells(),
                         expectedSurface.GetNumberOfCells())
        self.assertBoundaryIsLabelled(mesh, "CellEntityIds")
        self.assertFalse(logic.lastTetrahedralizationFailed)
        self.assertFalse(logic.isRunning)

    def test_CfdMeshGeneratorProcessCanBeCancelled(self):
        """A run can be stopped part way, and stopping it is not an error.

        This is the first reason the pipeline runs in a process of its own: a VTK filter cannot
        be interrupted, so a run that was going to take an hour used to take an hour. The cancel
        arrives from the event loop, the way a press of the button does, once the worker has
        announced its first step - so it is known to be running, and known to be heard.
        """
        logic = CfdMeshGeneratorLogic()
        if not logic.isTetGenAvailable():
            self.skipTest("this installation was built without TetGen")
        # Fine enough to take a while: cancel has to land before the run is over.
        parameterNode = self.parameterNode(
            logic, self.openTube(numberOfAxialPoints=60, numberOfCircumferentialPoints=120))
        parameterNode.targetEdgeLength = 0.1

        stepsSeen = []
        showStep = logic.showStep

        def cancelOnFirstStep(message):
            stepsSeen.append(message)
            showStep(message)
            if len(stepsSeen) == 1:
                qt.QTimer.singleShot(0, logic.cancel)

        logic.stepCallback = cancelOnFirstStep
        logic.relayWorkerLine = self._relayThroughStepCallback(logic)

        with self.assertRaises(MeshingCancelledError):
            logic.process(parameterNode)

        self.assertTrue(stepsSeen, "the worker announced no step before it was stopped")
        self.assertIsNone(parameterNode.outputMesh.GetMesh(),
                          "a cancelled run still wrote a mesh")
        self.assertFalse(logic.isRunning)

    @staticmethod
    def _relayThroughStepCallback(logic):
        """The logic's line relay, with the steps routed through its stepCallback rather than
        straight to the status bar, so that a test can listen for them."""
        from CfdMeshGeneratorLib import MeshingWorker

        original = CfdMeshGeneratorLogic.relayWorkerLine

        def relay(line):
            if line.startswith(MeshingWorker.STEP_PREFIX):
                logic.stepCallback(line[len(MeshingWorker.STEP_PREFIX):])
            else:
                original(logic, line)
        return relay

    def test_CfdMeshGeneratorProcessRelaysWhatTheWorkerSays(self):
        """What the pipeline logs in the worker arrives in this process's log, at its level.

        The log is where a run explains itself - which array it read the faces from, how long
        each step took, what it warned about - and none of that would be worth much in a process
        that has ended and taken its output with it.
        """
        logic = CfdMeshGeneratorLogic()
        if not logic.isTetGenAvailable():
            self.skipTest("this installation was built without TetGen")
        parameterNode = self.parameterNode(logic, self.openTube())
        # Asking for an array the input does not carry is a warning the pipeline logs.
        parameterNode.carriedCellArrays = "NoSuchArray"

        records = []
        handler = logging.Handler()
        handler.emit = records.append
        logging.getLogger().addHandler(handler)
        try:
            logic.process(parameterNode)
        finally:
            logging.getLogger().removeHandler(handler)

        messages = [(record.levelname, record.getMessage()) for record in records]
        self.assertTrue(any(level == "INFO" and "Capping surface" in message
                            for level, message in messages),
                        "the steps the worker logged were not relayed: %s" % messages)
        self.assertTrue(any(level == "WARNING" and "NoSuchArray" in message
                            for level, message in messages),
                        "a warning the worker logged was not relayed as one: %s" % messages)

    def test_CfdMeshGeneratorProcessReportsAWorkerThatDied(self):
        """A worker that dies without a result is reported as having died.

        This is the second reason for the separate process: TetGen walks off the end of a surface
        it cannot fill and takes its process with it. Here the worker is made to die by being
        handed a Python that is not one, which is the one death this test can arrange without a
        surface that crashes a mesher.
        """
        logic = CfdMeshGeneratorLogic()
        parameterNode = self.parameterNode(logic, self.openTube())
        logic.pythonSlicerExecutable = lambda: "no-such-python-anywhere"

        with self.assertRaises((RuntimeError, OSError)):
            logic.process(parameterNode)
        self.assertFalse(logic.isRunning)


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
