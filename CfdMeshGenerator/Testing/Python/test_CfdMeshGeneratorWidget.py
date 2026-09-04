"""The module widget: what a press of a button does, and what it leaves the scene like."""

import unittest

import slicer
import vtk

from CfdMeshGenerator import CfdMeshGeneratorLogic, Mesher
from CfdMeshGeneratorTestFixture import CfdMeshGeneratorTestCase, cfdMeshGeneratorModuleWidget


class CfdMeshGeneratorWidgetTest(CfdMeshGeneratorTestCase):

    def test_CfdMeshGeneratorClipping(self):
        """The clip box is the model's own bounding box, halved along its shortest side, and it
        keeps whole elements.

        Cutting through the elements would show faces that are not element faces, which is
        exactly what someone looking inside a mesh must not be shown.
        """
        logic = CfdMeshGeneratorLogic()
        modelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "mesh")
        modelNode.SetAndObserveMesh(self.openTube(height=10.0, radius=1.0))

        clipNode = logic.clipWithABoxThroughTheMiddle(modelNode)
        self.assertIsNotNone(clipNode)
        self.assertEqual(clipNode.GetClippingMethod(), slicer.vtkMRMLClipNode.WholeCells)
        self.assertTrue(modelNode.GetDisplayNode().GetClipping())
        self.assertIs(modelNode.GetDisplayNode().GetClipNode(), clipNode)

        roiNode = clipNode.GetNthClippingNode(0)
        self.assertTrue(roiNode.IsA("vtkMRMLMarkupsROINode"))
        # The tube is 2 across and 10 long, so the box is halved across and left alone along it.
        self.assertEqual([round(value, 3) for value in roiNode.GetSize()], [1.0, 2.0, 10.0])
        self.assertEqual([round(value, 3) for value in roiNode.GetCenter()], [0.0, 0.0, 5.0])
        self.assertTrue(roiNode.GetDisplayNode().GetVisibility())
        self.assertAlmostEqual(roiNode.GetDisplayNode().GetFillOpacity(), 0.05)


    def test_CfdMeshGeneratorReapplyLeavesTheDisplayAlone(self):
        """A second Apply writes the new mesh into the node it was given and touches nothing else.

        Meshing is something to try a few times at different sizes, and each try would otherwise
        undo the colour, the opacity and the visibility the last one was being looked at through.
        """
        logic = CfdMeshGeneratorLogic()
        modelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "mesh")
        modelNode.SetAndObserveMesh(logic.capSurface(self.openTube(), "CellEntityIds", "simple"))

        logic.showMeshInScene(modelNode, "CellEntityIds")
        displayNode = modelNode.GetDisplayNode()
        self.assertIsNotNone(displayNode, "the first run gave the output no display")
        self.assertTrue(displayNode.GetScalarVisibility(), "the faces are not coloured apart")

        displayNode.SetColor(0.1, 0.8, 0.3)
        displayNode.SetOpacity(0.4)
        displayNode.SetScalarVisibility(False)
        displayNode.SetVisibility(False)

        logic.showMeshInScene(modelNode, "CellEntityIds")
        self.assertIs(modelNode.GetDisplayNode(), displayNode, "the display node was replaced")
        self.assertEqual(displayNode.GetColor(), (0.1, 0.8, 0.3))
        self.assertAlmostEqual(displayNode.GetOpacity(), 0.4)
        self.assertFalse(displayNode.GetScalarVisibility())
        self.assertFalse(displayNode.GetVisibility())


    def test_CfdMeshGeneratorCreatesTheOutputNodeItself(self):
        """Apply with the output left at "(Create New)" makes the node to write into.

        Picking where the mesh is to go before there is a mesh is a step with no decision in it,
        and the module already knows what the node should be called - it names it after the input.
        Pressing Apply a second time writes into the node the first press made rather than leaving
        a trail of half-finished ones behind.
        """
        slicer.mrmlScene.Clear()
        widget = cfdMeshGeneratorModuleWidget()
        widget.enter()

        inputNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "tube")
        inputNode.SetAndObserveMesh(self.openTube())
        parameterNode = widget._parameterNode
        parameterNode.inputSurface = inputNode
        parameterNode.outputMesh = None
        # The size the other tests here mesh this tube at; a coarser one leaves TetGen a surface
        # it cannot fill, which would fail this test for a reason that has nothing to do with it.
        parameterNode.targetEdgeLength = 0.4
        parameterNode.boundaryLayer = False

        self.assertEqual(widget.ui.outputMeshSelector.noneDisplay, "(Create New)",
                         "the empty entry does not say a node will be made")
        self.assertTrue(widget.ui.applyButton.enabled,
                        "Apply is refused with no output node, so none can ever be made")

        widget.onApplyButton()

        outputNode = parameterNode.outputMesh
        self.assertIsNotNone(outputNode, "Apply made no node to write into")
        self.assertIsNotNone(outputNode.GetMesh(), "the node it made holds no mesh")
        self.assertGreater(outputNode.GetMesh().GetNumberOfCells(), 0)
        # named after the input, the way the selector's own "Create new" entry names one
        self.assertIn("tube", outputNode.GetName())

        widget.onApplyButton()
        self.assertIs(parameterNode.outputMesh, outputNode,
                      "a second Apply made a second node instead of writing into the first")



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
