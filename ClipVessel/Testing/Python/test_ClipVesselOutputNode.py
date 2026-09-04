"""The output model is made when Apply is pressed, and not before.

Picking an input surface used to be enough to have one made, which left an empty model behind
after any look at the module that went no further.
"""
import unittest

import slicer
import vtk

from ClipVesselTestFixture import clipVesselModuleWidget, downloadAortaSurface
import ExtractCenterline


def modelNodeNames():
    return set(slicer.mrmlScene.GetNthNodeByClass(index, "vtkMRMLModelNode").GetName()
               for index in range(slicer.mrmlScene.GetNumberOfNodesByClass("vtkMRMLModelNode")))


class ClipVesselOutputNodeTest(unittest.TestCase):

    def setUp(self):
        slicer.mrmlScene.Clear()
        self.widget = clipVesselModuleWidget()
        parameterNode = self.widget._parameterNode

        self.surfaceNode = downloadAortaSurface()
        centerlineLogic = ExtractCenterline.ExtractCenterlineLogic()
        preprocessed = centerlineLogic.preprocess(self.surfaceNode.GetPolyData(), 5000.0, 4.0, False)
        endPoints = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "eps")
        for position in centerlineLogic.getEndPoints(
                centerlineLogic.extractNetwork(preprocessed, endPoints), startPointPosition=None):
            endPoints.AddControlPoint(vtk.vtkVector3d(position))
        centerlines, _voronoi = centerlineLogic.extractCenterline(preprocessed, endPoints)
        centerlineNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Centerline model")
        centerlineNode.SetAndObserveMesh(centerlines)

        clipPointsNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "clip points")
        for terminus in self.widget.logic.detectCenterlineTerminusClipPoints(centerlineNode, 1.5):
            index = clipPointsNode.AddControlPointWorld(vtk.vtkVector3d(terminus["position"]))
            clipPointsNode.SetNthControlPointLabel(index, terminus["label"])

        parameterNode.SetNodeReferenceID("InputSurface", self.surfaceNode.GetID())
        parameterNode.SetNodeReferenceID("InputCenterlines", centerlineNode.GetID())
        parameterNode.SetNodeReferenceID("ClipPoints", clipPointsNode.GetID())
        self.widget.updateGUIFromParameterNode()

    def test_the_empty_entry_says_a_node_will_be_made(self):
        self.assertEqual(self.widget.ui.outputSurfaceModelSelector.noneDisplay, "(Create New)")

    def test_picking_an_input_makes_no_output_node(self):
        """Everything is chosen but Apply: the scene must be as it was."""
        self.assertIsNone(self.widget._parameterNode.GetNodeReference("OutputSurfaceModel"),
                          "an output node was made before Apply was pressed")
        self.assertNotIn("aorta-surface clipped", modelNodeNames())
        self.assertTrue(self.widget.ui.applyButton.enabled,
                        "Apply is refused with no output node, so none can ever be made")

    def test_apply_makes_the_output_node_and_writes_into_it(self):
        self.widget.onApplyButton()

        outputNode = self.widget._parameterNode.GetNodeReference("OutputSurfaceModel")
        self.assertIsNotNone(outputNode, "Apply made no node to write into")
        self.assertIsNotNone(outputNode.GetPolyData(), "the node it made holds no surface")
        self.assertGreater(outputNode.GetPolyData().GetNumberOfCells(), 0)
        # named after the input, the way the selector's own "Create new" entry names one
        self.assertIn(self.surfaceNode.GetName(), outputNode.GetName())
        self.assertIs(self.widget.ui.outputSurfaceModelSelector.currentNode(), outputNode,
                      "the node was made but not selected, so a second Apply would make another")

        self.widget.onApplyButton()
        self.assertIs(self.widget._parameterNode.GetNodeReference("OutputSurfaceModel"), outputNode,
                      "a second Apply made a second node instead of writing into the first")

    def test_live_update_does_not_make_the_node_by_itself(self):
        """Auto-apply follows a result the user asked for; it must not be what conjures one."""
        self.widget.ui.applyButton.checked = True
        self.widget.scheduleAutoApply()

        self.assertFalse(self.widget.autoApplyTimer.isActive(),
                         "live update was scheduled with nowhere to put the result")
        self.assertIsNone(self.widget._parameterNode.GetNodeReference("OutputSurfaceModel"))


if __name__ == "__main__":
    import sys
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise AssertionError("%d failure(s) and %d error(s) in %d test(s)"
                             % (len(result.failures), len(result.errors), result.testsRun))
