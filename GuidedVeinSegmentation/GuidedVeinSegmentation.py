import logging
import os
from typing import Annotated, Optional

import vtk

import slicer
import slicer
from slicer.i18n import tr as _
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from slicer.parameterNodeWrapper import (
    parameterNodeWrapper,
    WithinRange,
)

from slicer import vtkMRMLScalarVolumeNode


#
# GuidedVeinSegmentation
#

class GuidedVeinSegmentation(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Guided vein segmentation"
        self.parent.categories = ["Vascular Modeling Toolkit"]
        self.parent.dependencies = []
        self.parent.contributors = ["Saleem Edah-Tally [Surgeon] [Hobbyist developer]"]
        self.parent.helpText = _("""
This <a href="https://github.com/vmtk/SlicerExtension-VMTK/">module</a> attempts to segment major veins using effects of the 'Segment editor'.
""")
        self.parent.acknowledgementText = _("""
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
""")

#
# GuidedVeinSegmentationWidget
#

class GuidedVeinSegmentationWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None) -> None:
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None
        self._updatingGUIFromParameterNode = False

    def setup(self) -> None:
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/GuidedVeinSegmentation.ui'))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        self.ui.optionCollapsibleButton.collapsed = True
        self.ui.parameterCollapsibleButton.collapsed = True

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = GuidedVeinSegmentationLogic()
        self.ui.parameterSetSelector.addAttribute("vtkMRMLScriptedModuleNode", "ModuleName", self.moduleName)

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # Application connections
        self.ui.curveSelector.connect("currentNodeChanged(vtkMRMLNode*)", lambda node: self.onMrmlNodeChanged(ROLE_INPUT_CURVE, node))
        self.ui.volumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", lambda node: self.onMrmlNodeChanged(ROLE_INPUT_VOLUME, node))
        self.ui.segmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", lambda node: self.onMrmlNodeChanged(ROLE_INPUT_SEGMENTATION, node))
        self.ui.shellMarginSpinBox.connect("valueChanged(double)", lambda value: self.onSpinBoxChanged(ROLE_SHELL_MARGIN, value))
        self.ui.extrusionKernelSizeSpinBox.connect("valueChanged(double)", lambda value: self.onSpinBoxChanged(ROLE_EXTRUSION_KERNEL_SIZE, value))
        self.ui.gaussianStandardDeviationSpinBox.connect("valueChanged(double)", lambda value: self.onSpinBoxChanged(ROLE_GAUSSIAN_STANDARD_DEVIATION, value))
        self.ui.seedRadiusSpinBox.connect("valueChanged(double)", lambda value: self.onSpinBoxChanged(ROLE_SEED_RADIUS, value))
        self.ui.shellThicknessSpinBox.connect("valueChanged(double)", lambda value: self.onSpinBoxChanged(ROLE_SHELL_THICKNESS, value))
        self.ui.subtractOtherSegmentsCheckBox.connect("toggled(bool)", lambda checked: self.onBooleanToggled(ROLE_SUBTRACT_OTHER_SEGMENTS, checked))
        self.ui.parameterSetSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.setParameterNode)
        self.ui.parameterSetUpdateUIToolButton.connect("clicked(bool)", self.onParameterSetUpdateUiClicked)

        # Buttons
        self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

    def cleanup(self) -> None:
        """
        Called when the application closes and the module widget is destroyed.
        """
        self.removeObservers()

    def enter(self) -> None:
        """
        Called each time the user opens this module.
        """
        # Make sure parameter node exists and observed
        self.initializeParameterNode()

    def exit(self) -> None:
        """
        Called each time the user opens a different module.
        """
        pass

    def onSceneStartClose(self, caller, event) -> None:
        """
        Called just before the scene is closed.
        """
        # Parameter node will be reset, do not use it anymore
        self.setParameterNode(None)

    def onSceneEndClose(self, caller, event) -> None:
        """
        Called just after the scene is closed.
        """
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        if self.parent.isEntered:
            self.initializeParameterNode()

    def initializeParameterNode(self) -> None:
        """
        Ensure parameter node exists.
        """
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

        # The initial parameter node originates from logic and is picked up by the parameter set combobox.
        # Other parameter nodes are created by the parameter set combobox and used here.
        if not self._parameterNode:
            self.setParameterNode(self.logic.getParameterNode())
            wasBlocked = self.ui.parameterSetSelector.blockSignals(True)
            self.ui.parameterSetSelector.setCurrentNode(self._parameterNode)
            self.ui.parameterSetSelector.blockSignals(wasBlocked)

    def setParameterNode(self, inputParameterNode: slicer.vtkMRMLScriptedModuleNode) -> None:
        if inputParameterNode == self._parameterNode:
            return
        self._parameterNode = inputParameterNode

        self.logic.setParameterNode(self._parameterNode)
        if self._parameterNode:
            self.setDefaultValues()
            self.updateGUIFromParameterNode()

    def setDefaultValues(self):
        if not self._parameterNode:
            return

        if self._parameterNode.HasParameter(ROLE_INITIALIZED):
            return

        self._parameterNode.SetParameter(ROLE_EXTRUSION_KERNEL_SIZE, str(5.0))
        self._parameterNode.SetParameter(ROLE_GAUSSIAN_STANDARD_DEVIATION, str(2.0))
        self._parameterNode.SetParameter(ROLE_SEED_RADIUS, str(1.0))
        self._parameterNode.SetParameter(ROLE_SHELL_MARGIN, str(18.0))
        self._parameterNode.SetParameter(ROLE_SHELL_THICKNESS, str(2.0))
        self._parameterNode.SetParameter(ROLE_SUBTRACT_OTHER_SEGMENTS, str(1))
        self._parameterNode.SetParameter(ROLE_INITIALIZED, str(1))

    def onApplyButton(self) -> None:
        """
        Run processing when user clicks "Apply" button.
        """
        with slicer.util.tryWithErrorDisplay(_("Failed to compute results."), waitCursor=True):

            # Compute output
            self.logic.process()

    def onParameterSetUpdateUiClicked(self):
        if not self._parameterNode:
            return
    
        inputSegmentation = self._parameterNode.GetNodeReference(ROLE_INPUT_SEGMENTATION)
        inputVolume = self._parameterNode.GetNodeReference(ROLE_INPUT_VOLUME)

        if inputSegmentation:
            # Create segment editor object if needed.
            segmentEditorModuleWidget = slicer.util.getModuleWidget("SegmentEditor")
            seWidget = segmentEditorModuleWidget.editor
            seWidget.setSegmentationNode(inputSegmentation)
        if inputVolume:
            slicer.util.setSliceViewerLayers(background = inputVolume.GetID(), fit = True)

    def onMrmlNodeChanged(self, role, node):
        if self._parameterNode:
            self._parameterNode.SetNodeReferenceID(role, node.GetID() if node else None)

    def onSpinBoxChanged(self, role, value):
        if self._parameterNode:
            self._parameterNode.SetParameter(role, str(value))

    def onBooleanToggled(self, role, checked):
        if self._parameterNode:
            self._parameterNode.SetParameter(role, str(1) if checked else str(0))

    def updateGUIFromParameterNode(self):
        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
        self._updatingGUIFromParameterNode = True

        self.ui.curveSelector.setCurrentNode(self._parameterNode.GetNodeReference(ROLE_INPUT_CURVE))
        self.ui.volumeSelector.setCurrentNode(self._parameterNode.GetNodeReference(ROLE_INPUT_VOLUME))
        self.ui.segmentationSelector.setCurrentNode(self._parameterNode.GetNodeReference(ROLE_INPUT_SEGMENTATION))
        self.ui.shellMarginSpinBox.setValue(float(self._parameterNode.GetParameter(ROLE_SHELL_MARGIN)))
        self.ui.extrusionKernelSizeSpinBox.setValue(float(self._parameterNode.GetParameter(ROLE_EXTRUSION_KERNEL_SIZE)))
        self.ui.gaussianStandardDeviationSpinBox.setValue(float(self._parameterNode.GetParameter(ROLE_GAUSSIAN_STANDARD_DEVIATION)))
        self.ui.seedRadiusSpinBox.setValue(float(self._parameterNode.GetParameter(ROLE_SEED_RADIUS)))
        self.ui.shellThicknessSpinBox.setValue(float(self._parameterNode.GetParameter(ROLE_SHELL_THICKNESS)))
        self.ui.subtractOtherSegmentsCheckBox.setChecked(int(self._parameterNode.GetParameter(ROLE_SUBTRACT_OTHER_SEGMENTS)))

        self._updatingGUIFromParameterNode = False
#
# GuidedVeinSegmentationLogic
#

class GuidedVeinSegmentationLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self) -> None:
        """
        Called when the logic class is instantiated. Can be used for initializing member variables.
        """
        ScriptedLoadableModuleLogic.__init__(self)
        self._parameterNode = None

    def setParameterNode(self, inputParameterNode):
        self._parameterNode = inputParameterNode

    def process(self) -> None:

        if not self._parameterNode:
            raise ValueError(_("Parameter node is None."))

        inputCurve = self._parameterNode.GetNodeReference(ROLE_INPUT_CURVE)
        inputVolume = self._parameterNode.GetNodeReference(ROLE_INPUT_VOLUME)
        inputSegmentation = self._parameterNode.GetNodeReference(ROLE_INPUT_SEGMENTATION)
        extrusionKernelSize = float(self._parameterNode.GetParameter(ROLE_EXTRUSION_KERNEL_SIZE))
        gaussianStandardDeviation = float(self._parameterNode.GetParameter(ROLE_GAUSSIAN_STANDARD_DEVIATION))
        seedRadius = float(self._parameterNode.GetParameter(ROLE_SEED_RADIUS))
        shellMargin = float(self._parameterNode.GetParameter(ROLE_SHELL_MARGIN))
        shellThickness = float(self._parameterNode.GetParameter(ROLE_SHELL_THICKNESS))
        subtractOtherSegments = int(self._parameterNode.GetParameter(ROLE_SUBTRACT_OTHER_SEGMENTS))

        if not inputCurve or not inputVolume or not inputSegmentation:
            raise ValueError(_("Input curve or volume or segmentation is invalid."))

        if (extrusionKernelSize <= 0.0
            or gaussianStandardDeviation <= 0.0
            or seedRadius <= 0.0
            or shellMargin <= 0.0
            or shellThickness <= 0.0):
            raise ValueError(_("Extrusion kernel size or Gaussian standard deviation\
                or seed radius or shell margin or shell thickness is invalid."))

        import time
        startTime = time.time()
        logging.info(_("Processing started"))

        # Create segment editor object if needed.
        segmentEditorModuleWidget = slicer.util.getModuleWidget("SegmentEditor")
        seWidget = segmentEditorModuleWidget.editor
        seWidget.setSegmentationNode(inputSegmentation)
        seWidget.setSourceVolumeNode(inputVolume)
        inputSegmentation.SetReferenceImageGeometryParameterFromVolumeNode(inputVolume)

        # Use OverwriteNone to preserve other segments.
        seWidget.mrmlSegmentEditorNode().SetMaskMode(slicer.vtkMRMLSegmentationNode.EditAllowedEverywhere)
        seWidget.mrmlSegmentEditorNode().SourceVolumeIntensityMaskOff()
        seWidget.mrmlSegmentEditorNode().SetOverwriteMode(seWidget.mrmlSegmentEditorNode().OverwriteNone)

        # Hide all existing segments for we will be using 'Grow from seeds'. Restore visibility at the end.
        allSegments = inputSegmentation.GetSegmentation().GetSegmentIDs()
        visibleSegmentIDs = vtk.vtkStringArray()
        inputSegmentation.GetDisplayNode().GetVisibleSegmentIDs(visibleSegmentIDs)
        if allSegments:
            for segmentId in allSegments:
                inputSegmentation.GetDisplayNode().SetSegmentVisibility(segmentId, False)

        # Create a seed segment using the curve polydata.
        seedSegmentName = inputCurve.GetName() + "_" + _("Segment")
        seedSegmentName = slicer.mrmlScene.GenerateUniqueName(seedSegmentName)
        tube = vtk.vtkTubeFilter()
        tube.SetInputData(inputCurve.GetCurveWorld())
        tube.SetRadius(seedRadius)
        tube.SetNumberOfSides(30)
        tube.CappingOn()
        tube.Update()
        seedSegmentId = inputSegmentation.AddSegmentFromClosedSurfaceRepresentation(tube.GetOutput(), seedSegmentName)
        seWidget.mrmlSegmentEditorNode().SetSelectedSegmentID(seedSegmentId)
        # Tag the seed segment.
        tagSourceCurveId = "SourceCurveId"
        segment = inputSegmentation.GetSegmentation().GetSegment(seedSegmentId)
        reference = vtk.reference(inputCurve.GetID())
        segment.SetTag(tagSourceCurveId, reference)

        # Create a shell segment using the curve polydata: a new tube that will grow and get hollow.
        shell = vtk.vtkTubeFilter()
        shell.SetInputData(inputCurve.GetCurveWorld())
        shell.SetRadius(seedRadius)
        shell.SetNumberOfSides(30)
        shell.CappingOn()
        shell.Update()
        shellSegmentId = inputSegmentation.AddSegmentFromClosedSurfaceRepresentation(shell.GetOutput(), "Shell")
        seWidget.mrmlSegmentEditorNode().SetSelectedSegmentID(shellSegmentId)
        # Grow
        seWidget.setActiveEffectByName("Margin")
        effect = seWidget.activeEffect()
        effect.setParameter("ApplyToAllVisibleSegments", str(0))
        effect.setParameter("MarginSizeMm", str(shellMargin))
        effect.self().onApply()
        seWidget.setActiveEffectByName(None)
        # Hollow
        seWidget.setActiveEffectByName("Hollow")
        effect = seWidget.activeEffect()
        effect.setParameter("ApplyToAllVisibleSegments", str(0))
        effect.setParameter("ShellMode", "OUTSIDE_SURFACE")
        effect.setParameter("ShellThicknessMm", str(shellThickness))
        effect.self().onApply()
        seWidget.setActiveEffectByName(None)

        # Grow the seed within the shell.
        seWidget.mrmlSegmentEditorNode().SetSelectedSegmentID(seedSegmentId)
        seWidget.setActiveEffectByName("Grow from seeds")
        effect = seWidget.activeEffect()
        effect.self().onPreview()
        effect.self().onApply()
        seWidget.setActiveEffectByName(None)

        # Smoothing: remove extrusion then Gaussian.
        import SegmentEditorSmoothingEffect
        seWidget.setActiveEffectByName("Smoothing")
        effect = seWidget.activeEffect()
        effect.setParameter("ApplyToAllVisibleSegments", str(0))
        effect.setParameter("SmoothingMethod", SegmentEditorSmoothingEffect.MORPHOLOGICAL_OPENING)
        effect.setParameter("KernelSizeMm", str(extrusionKernelSize))
        effect.self().onApply()
        effect.setParameter("SmoothingMethod", SegmentEditorSmoothingEffect.GAUSSIAN)
        effect.setParameter("GaussianStandardDeviationMm", str(gaussianStandardDeviation))
        effect.self().onApply()
        seWidget.setActiveEffectByName(None)

        # The shell segment is no longer needed.
        inputSegmentation.GetSegmentation().RemoveSegment(shellSegmentId)

        """
        Remove overlaps with all other segments. Duplicate segments originating
        from the same input curve, due to repeat runs, are excluded.
        It's a good idea to segment nearby bones and arteries before processing
        the veins, which may overlap on the former.
        """
        if subtractOtherSegments:
            seWidget.setActiveEffectByName("Logical operators")
            effect = seWidget.activeEffect()
            effect.setParameter("BypassMasking", str(1))
            effect.setParameter("Operation", "SUBTRACT")
            if allSegments: # Previous ones.
                for segmentId in allSegments:
                    segment = inputSegmentation.GetSegmentation().GetSegment(segmentId)
                    reference = vtk.reference("")
                    segment.GetTag(tagSourceCurveId, reference)
                    if reference.get() != inputCurve.GetID(): # Segment does not spring from this unput curve.
                        effect.setParameter("ModifierSegmentID", segmentId)
                        effect.self().onApply()
            seWidget.setActiveEffectByName(None)

        # Restore segment visibility.
        for segmentIndex in range(visibleSegmentIDs.GetNumberOfValues()):
            inputSegmentation.GetDisplayNode().SetSegmentVisibility(visibleSegmentIDs.GetValue(segmentIndex), True)

        stopTime = time.time()
        durationValue = '%.2f' % (stopTime-startTime)
        logging.info(_("Processing completed in {duration} seconds").format(duration=durationValue))
        return seedSegmentId

#
# GuidedVeinSegmentationTest
#

class GuidedVeinSegmentationTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """ Do whatever is needed to reset the state - typically a scene clear will be enough.
        """
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here.
        """
        self.setUp()
        self.test_GuidedVeinSegmentation1()

    def test_GuidedVeinSegmentation1(self):
        self.delayDisplay(_("Starting the test"))

        self.delayDisplay(_("Test passed"))

ROLE_INPUT_CURVE = "InputCurve"
ROLE_INPUT_VOLUME = "InputVolume"
ROLE_INPUT_SEGMENTATION = "InputSegmentation"
ROLE_EXTRUSION_KERNEL_SIZE = "ExtrusionKernelSize"
ROLE_GAUSSIAN_STANDARD_DEVIATION = "GaussianStandardDeviation"
ROLE_SEED_RADIUS = "SeedRadius"
ROLE_SHELL_MARGIN = "ShellMargin"
ROLE_SHELL_THICKNESS = "ShellThickness"
ROLE_SUBTRACT_OTHER_SEGMENTS = "SubtractOtherSegments"
ROLE_INITIALIZED = "Initialized"
