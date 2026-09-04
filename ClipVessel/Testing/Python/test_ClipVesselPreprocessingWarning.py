"""The confirmation before preprocessing rebuilds a labelled input.

Decimating moves the face boundaries by about a cell, so Apply asks first. It must ask in exactly
that case and stay silent in every other, and it must never interrupt an interactive drag with a
modal dialog. slicer.util.confirmOkCancelDisplay is stubbed throughout so nothing blocks.
"""

import unittest

import numpy as np
import slicer
import vtk
from vtk.util.numpy_support import numpy_to_vtk

from ClipVesselTestFixture import clipVesselModuleWidget


class ClipVesselPreprocessingWarningTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """The module's own widget, one for the whole suite: clearing the scene under a widget
        that is observing it wedges the application."""
        cls.widget = clipVesselModuleWidget()

        sphere = vtk.vtkSphereSource()
        sphere.SetThetaResolution(30)
        sphere.SetPhiResolution(30)
        sphere.Update()

        cls.labelledSurface = vtk.vtkPolyData()
        cls.labelledSurface.DeepCopy(sphere.GetOutput())
        faceIds = np.zeros(cls.labelledSurface.GetNumberOfCells(), dtype=np.int32)
        faceIds[:50] = 10
        faceIdArray = numpy_to_vtk(faceIds, deep=True, array_type=vtk.VTK_INT)
        faceIdArray.SetName("ModelFaceID")
        cls.labelledSurface.GetCellData().AddArray(faceIdArray)

        cls.plainSurface = vtk.vtkPolyData()
        cls.plainSurface.DeepCopy(sphere.GetOutput())

        cls.numberOfInputPoints = cls.labelledSurface.GetNumberOfPoints()
        cls.inputNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Input surface")


    @classmethod
    def tearDownClass(cls):
        """Let go of the widget without tearing it down. The module manager owns it and destroys
        it before the scene, so a test that called cleanup() on it would be pulling the module
        apart under the application."""
        cls.widget = None
        slicer.mrmlScene.Clear()

    def setUp(self):
        self.shownMessages = []
        self.answer = True
        self.realConfirm = slicer.util.confirmOkCancelDisplay

        def stubConfirm(text, windowTitle=None, parent=None, **kwargs):
            self.shownMessages.append(text)
            return self.answer

        slicer.util.confirmOkCancelDisplay = stubConfirm

        self.inputNode.SetAndObserveMesh(self.labelledSurface)
        self.parameterNode = self.widget._parameterNode
        self.parameterNode.SetNodeReferenceID("InputSurface", self.inputNode.GetID())
        self.parameterNode.SetParameter("LabelModelFaces", "true")
        self.parameterNode.SetParameter("PreprocessInputSurface", "true")
        self.parameterNode.SetParameter("ModelFaceIdArrayName", "ModelFaceID")
        # below the input's own point count, so preprocessing would decimate
        self.parameterNode.SetParameter("TargetNumberOfPoints", str(self.numberOfInputPoints // 2))

    def tearDown(self):
        slicer.util.confirmOkCancelDisplay = self.realConfirm

    def ask(self):
        """(whether the run should go ahead, how many popups it took to decide)."""
        del self.shownMessages[:]
        proceed = self.widget.confirmPreprocessingDiscardsFaceLabels()
        return proceed, len(self.shownMessages)

    def test_it_warns_when_preprocessing_will_decimate_a_labelled_input(self):
        proceed, numberOfPopups = self.ask()

        self.assertEqual(numberOfPopups, 1)
        self.assertTrue(proceed, "clicking OK must let the run go ahead")

    def test_the_warning_says_what_will_happen_and_how_to_avoid_it(self):
        self.ask()
        message = self.shownMessages[0]

        self.assertIn("ModelFaceID", message, "the array is not named")
        self.assertIn("shift", message, "does not say the boundaries can shift")
        self.assertIn("no face is lost", message)
        self.assertNotIn("discard", message, "says the faces are discarded, which they are not")
        self.assertIn("Preprocess input surface", message, "does not say how to keep the labels")
        self.assertIn(str(self.numberOfInputPoints), message,
                      "does not say what to raise the target above")

    def test_cancel_aborts_the_run(self):
        self.answer = False

        proceed, _numberOfPopups = self.ask()

        self.assertFalse(proceed)

    def test_it_is_silent_when_the_target_is_above_the_input_point_count(self):
        self.parameterNode.SetParameter("TargetNumberOfPoints", str(self.numberOfInputPoints * 2))

        _proceed, numberOfPopups = self.ask()

        self.assertEqual(numberOfPopups, 0, "no decimation, so nothing to warn about")

    def test_it_is_silent_when_preprocessing_is_off(self):
        self.parameterNode.SetParameter("PreprocessInputSurface", "false")

        _proceed, numberOfPopups = self.ask()

        self.assertEqual(numberOfPopups, 0)

    def test_it_is_silent_when_face_labelling_is_off(self):
        self.parameterNode.SetParameter("LabelModelFaces", "false")

        _proceed, numberOfPopups = self.ask()

        self.assertEqual(numberOfPopups, 0)

    def test_it_is_silent_when_the_input_carries_no_face_labels(self):
        self.inputNode.SetAndObserveMesh(self.plainSurface)

        _proceed, numberOfPopups = self.ask()

        self.assertEqual(numberOfPopups, 0)

    def test_it_is_silent_when_the_configured_array_name_is_absent(self):
        self.parameterNode.SetParameter("ModelFaceIdArrayName", "SomeOtherName")

        _proceed, numberOfPopups = self.ask()

        self.assertEqual(numberOfPopups, 0)

    def test_auto_apply_never_shows_the_popup(self):
        """A modal dialog mid-drag would be intolerable, so auto-apply must not go through the
        click path that asks.

        Apply itself is stood in for. What is being pinned down is which path auto-apply takes,
        and running the real pipeline here would say nothing about that while requiring a fully
        configured scene: this suite's surface has no centerlines, so Apply would fail, and a
        failing Apply raises an error dialog of its own that has nothing to do with the
        confirmation being counted -- outside testing mode it blocks the run waiting to be
        dismissed. The stand-in also lets the test check the other half of the contract, that
        auto-apply does reach Apply at all."""
        del self.shownMessages[:]
        applied = []
        realApply = self.widget.onApplyButton
        self.widget.onApplyButton = lambda: applied.append(True)
        try:
            self.widget.onAutoApplyTimeout()
        finally:
            self.widget.onApplyButton = realApply

        self.assertEqual(applied, [True], "auto-apply should have run Apply")
        self.assertEqual(self.shownMessages, [], "auto-apply must not ask before running")


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
