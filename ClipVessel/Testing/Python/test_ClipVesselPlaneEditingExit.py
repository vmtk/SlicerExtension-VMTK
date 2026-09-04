"""Leaving the module finishes plane editing.

The plane is drawn in every view, not only in Clip Vessel's own panel, so one left being adjusted
follows the user into whatever module they switch to.
"""
import unittest

import slicer
import vtk

from ClipVesselTestFixture import clipVesselModuleWidget, downloadAortaSurface
import ExtractCenterline


class ClipVesselPlaneEditingExitTest(unittest.TestCase):

    def setUp(self):
        slicer.mrmlScene.Clear()
        self.widget = clipVesselModuleWidget()
        parameterNode = self.widget._parameterNode

        surfaceNode = downloadAortaSurface()
        centerlineLogic = ExtractCenterline.ExtractCenterlineLogic()
        preprocessed = centerlineLogic.preprocess(surfaceNode.GetPolyData(), 5000.0, 4.0, False)
        endPoints = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "eps")
        for position in centerlineLogic.getEndPoints(
                centerlineLogic.extractNetwork(preprocessed, endPoints), startPointPosition=None):
            endPoints.AddControlPoint(vtk.vtkVector3d(position))
        centerlines, _voronoi = centerlineLogic.extractCenterline(preprocessed, endPoints)
        centerlineNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Centerline model")
        centerlineNode.SetAndObserveMesh(centerlines)

        self.clipPointsNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "clip points")
        for terminus in self.widget.logic.detectCenterlineTerminusClipPoints(centerlineNode, 1.5):
            index = self.clipPointsNode.AddControlPointWorld(vtk.vtkVector3d(terminus["position"]))
            self.clipPointsNode.SetNthControlPointLabel(index, terminus["label"])

        parameterNode.SetNodeReferenceID("InputSurface", surfaceNode.GetID())
        parameterNode.SetNodeReferenceID("InputCenterlines", centerlineNode.GetID())
        parameterNode.SetNodeReferenceID("ClipPoints", self.clipPointsNode.GetID())

    def planeVisibility(self):
        parameterNode = self.widget._parameterNode
        visibilities = []
        for roleName in ("ManualClipPlane", "ManualClipPlaneNormalHandle"):
            node = parameterNode.GetNodeReference(roleName)
            if node:
                visibilities.append(bool(node.GetDisplayVisibility()))
        return visibilities

    def test_leaving_the_module_finishes_plane_editing(self):
        self.widget.showInteractiveClipPlane(0)
        self.assertTrue(self.widget._planeEditing, "the plane was never put up to be adjusted")
        self.assertIn(True, self.planeVisibility(), "no plane is visible to be left behind")

        self.widget.exit()

        self.assertFalse(self.widget._planeEditing, "the module was left still adjusting a plane")
        self.assertEqual(self.planeVisibility(), [False] * len(self.planeVisibility()),
                         "a plane was left in the views of the module switched to")
        self.assertEqual(self.widget._activeClipPointIndex, -1, "a clip point is still being edited")
        self.assertFalse(self.widget.ui.finishPlaneEditingButton.enabled,
                         "the Finish button is still offered with nothing to finish")

    def test_leaving_without_editing_leaves_the_status_line_alone(self):
        """A module switch is not a Finish: with no plane up, nothing is reported."""
        self.widget.ui.clipStatusLabel.text = "All cuts are planar."

        self.widget.exit()

        self.assertEqual(self.widget.ui.clipStatusLabel.text, "All cuts are planar.",
                         "leaving the module wrote over what the last run reported")


if __name__ == "__main__":
    import sys
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise AssertionError("%d failure(s) and %d error(s) in %d test(s)"
                             % (len(result.failures), len(result.errors), result.testsRun))
