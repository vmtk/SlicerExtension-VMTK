import logging
import os
from typing import Annotated, Optional

import vtk
import  qt

import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from slicer.parameterNodeWrapper import (
    parameterNodeWrapper,
    WithinRange,
)

from slicer import vtkMRMLScalarVolumeNode


#
# ArterialCalcificationPreProcessor
#

class ArterialCalcificationPreProcessor(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Arterial calcification pre-processor"
        self.parent.categories = ["Vascular Modeling Toolkit"]
        self.parent.dependencies = [] 
        self.parent.contributors = ["Saleem Edah-Tally [Surgeon] [Hobbyist developer]"]  # TODO: replace with "Firstname Lastname (Organization)"
        # TODO: update with short description of the module and a link to online module documentation
        self.parent.helpText = _("""
Segment calcifications around an arterial lumen within a margin.
See more information in <a href="href="https://github.com/vmtk/SlicerExtension-VMTK/">module documentation</a>.
""")
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = _("""
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
""")

#
# ArterialCalcificationPreProcessorWidget
#

class ArterialCalcificationPreProcessorWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
        self._show3DAction = None

    def setup(self) -> None:
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/ArterialCalcificationPreProcessor.ui'))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = ArterialCalcificationPreProcessorLogic()
        self.ui.parameterSetSelector.addAttribute("vtkMRMLScriptedModuleNode", "ModuleName", self.moduleName)

        self.ui.optionsCollapsibleButton.collapsed = True

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        self.ui.inputSegmentSelector.connect("currentNodeChanged(vtkMRMLNode*)", lambda node: self.onMrmlNodeChanged(ROLE_INPUT_SEGMENTATION, node))
        self.ui.inputSegmentSelector.connect("currentSegmentChanged(QString)", lambda value: self.onStringChanged(ROLE_INPUT_SEGMENT, value))
        self.ui.inputVolumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", lambda node: self.onMrmlNodeChanged(ROLE_INPUT_VOLUME, node))
        self.ui.inputMarginSpinBox.connect("valueChanged(double)", lambda value: self.onSpinBoxChanged(ROLE_INPUT_MARGIN, value))
        self.ui.intensityRangeLowerSpinBox.connect("valueChanged(double)", lambda value: self.onSpinBoxChanged(ROLE_INPUT_LOWER_INTENSITY_BOUND, value))
        self.ui.intensityRangeUpperSpinBox.connect("valueChanged(double)", lambda value: self.onSpinBoxChanged(ROLE_INPUT_UPPER_INTENSITY_BOUND, value))
        self.ui.intensityRangeProbeButton.connect("clicked()", lambda: self.updateDisplayedIntensityRange(False))
        self.ui.intensityRangeResetButton.connect("clicked()", lambda: self.updateDisplayedIntensityRange(True))
        self.ui.parameterSetSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.setParameterNode)
        self.ui.parameterSetUpdateUIToolButton.connect("clicked(bool)", self.onParameterSetUpdateUiClicked)

        self.ui.inputSegmentSelector.connect("currentNodeChanged(vtkMRMLNode*)", lambda: self.updateDisplayedIntensityRange(True))
        self.ui.inputSegmentSelector.connect("currentSegmentChanged(QString)", lambda value: self.updateDisplayedIntensityRange(True))
        self.ui.inputVolumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", lambda node: self.updateDisplayedIntensityRange(True))
        self.ui.inputVolumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateWidgetIntensityBounds)

        self.ui.applyButton.menu().clear()
        self._show3DAction = qt.QAction(_("Show 3D on success"))
        self._show3DAction.setCheckable(True)
        self._show3DAction.setChecked(True)
        self.ui.applyButton.menu().addAction(self._show3DAction)

        # Buttons
        self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)
        self._show3DAction.connect("toggled(bool)", lambda value: self.onBooleanToggled(ROLE_SHOW3D, value))

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

        # Ensure all parameters exist in the parameter node.
        # Existing parameters are not modified.
        if (not self._parameterNode.HasParameter(ROLE_INPUT_MARGIN)):
            self._parameterNode.SetParameter(ROLE_INPUT_MARGIN, str(4.0))
        if (not self._parameterNode.HasParameter(ROLE_INPUT_LOWER_INTENSITY_BOUND)):
            self._parameterNode.SetParameter(ROLE_INPUT_LOWER_INTENSITY_BOUND, str(0.0))
        if (not self._parameterNode.HasParameter(ROLE_INPUT_UPPER_INTENSITY_BOUND)):
            self._parameterNode.SetParameter(ROLE_INPUT_UPPER_INTENSITY_BOUND, str(0.0))
        if (not self._parameterNode.HasParameter(ROLE_SHOW3D)):
            self._parameterNode.SetParameter(ROLE_SHOW3D, str(1))
        if (not self._parameterNode.HasParameter(ROLE_SHOW3D)):
            self._parameterNode.SetParameter(ROLE_SHOW3D, str(1))

    def onApplyButton(self) -> None:

        inputSegmentation = self.ui.inputSegmentSelector.currentNode()
        optionShow3D = self._show3DAction.checked
        
        with slicer.util.tryWithErrorDisplay(_("Failed to compute results."), waitCursor=True):
            
            # Compute output
            self.logic.process()
        
        if (not optionShow3D) or (not inputSegmentation):
            return
        
        # Poked from qMRMLSegmentationShow3DButton.cxx
        if inputSegmentation.GetSegmentation().CreateRepresentation(slicer.vtkSegmentationConverter.GetSegmentationClosedSurfaceRepresentationName()):
            inputSegmentation.GetDisplayNode().SetPreferredDisplayRepresentationName3D(slicer.vtkSegmentationConverter.GetSegmentationClosedSurfaceRepresentationName())

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

    def onStringChanged(self, role, value):
        if self._parameterNode:
            self._parameterNode.SetParameter(role, value)

    def updateGUIFromParameterNode(self):
        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
        self._updatingGUIFromParameterNode = True

        self.ui.inputSegmentSelector.setCurrentNode(self._parameterNode.GetNodeReference(ROLE_INPUT_SEGMENTATION))
        self.ui.inputSegmentSelector.setCurrentSegmentID(self._parameterNode.GetParameter(ROLE_INPUT_SEGMENT))
        self.ui.inputVolumeSelector.setCurrentNode(self._parameterNode.GetNodeReference(ROLE_INPUT_VOLUME))
        self.ui.inputMarginSpinBox.setValue(float(self._parameterNode.GetParameter(ROLE_INPUT_MARGIN)))
        self.ui.intensityRangeLowerSpinBox.setValue(float(self._parameterNode.GetParameter(ROLE_INPUT_LOWER_INTENSITY_BOUND)))
        self.ui.intensityRangeUpperSpinBox.setValue(float(self._parameterNode.GetParameter(ROLE_INPUT_UPPER_INTENSITY_BOUND)))
        self._show3DAction.setChecked(int(self._parameterNode.GetParameter(ROLE_SHOW3D)))

        self._updatingGUIFromParameterNode = False

    def updateDisplayedIntensityRange(self, reset):
        if reset:
            self.ui.intensityRangeLowerSpinBox.setValue(0.0)
            self.ui.intensityRangeUpperSpinBox.setValue(0.0)
        else:
            self.updateWidgetIntensityBounds()
            with slicer.util.tryWithErrorDisplay(_("Failed to probe the intensity range."), waitCursor=True):
                calcifHURange = self.logic.probeCalcificationIntensityRange()
                self.ui.intensityRangeLowerSpinBox.setValue(calcifHURange[0])
                self.ui.intensityRangeUpperSpinBox.setValue(calcifHURange[1])

    def updateWidgetIntensityBounds(self):
        if self._parameterNode is None:
            return
        with slicer.util.tryWithErrorDisplay(_("Failed to determine the intensity range."), waitCursor=True):
            inputVolume = self._parameterNode.GetNodeReference(ROLE_INPUT_VOLUME)
            if (inputVolume is None):
                return
            volumeIntensityRange = inputVolume.GetImageData().GetScalarRange()
            self.ui.intensityRangeLowerSpinBox.setRange(volumeIntensityRange[0], volumeIntensityRange[1])
            self.ui.intensityRangeUpperSpinBox.setRange(volumeIntensityRange[0], volumeIntensityRange[1])

#
# ArterialCalcificationPreProcessorLogic
#

class ArterialCalcificationPreProcessorLogic(ScriptedLoadableModuleLogic):

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

        # Create segment editor object if needed.
        segmentEditorModuleWidget = slicer.util.getModuleWidget("SegmentEditor")
        seWidget = segmentEditorModuleWidget.editor

        inputSegmentation = self._parameterNode.GetNodeReference(ROLE_INPUT_SEGMENTATION)
        inputVolume = self._parameterNode.GetNodeReference(ROLE_INPUT_VOLUME)
        segmentID = self._parameterNode.GetParameter(ROLE_INPUT_SEGMENT)
        marginSize = float(self._parameterNode.GetParameter(ROLE_INPUT_MARGIN))

        if not inputSegmentation or not inputVolume or not segmentID or segmentID == "" or not marginSize:
            raise ValueError(_("Input segmentation, volume, segment ID or margin size is invalid."))

        if (seWidget.segmentationNode() is not inputSegmentation
            or seWidget.sourceVolumeNode() is not inputVolume):
            logging.info(_("Input segmentation or volume mismatch with the segment editor... fixing."))
            seWidget.setSegmentationNode(inputSegmentation)
            seWidget.setSourceVolumeNode(inputVolume)
            inputSegmentation.SetReferenceImageGeometryParameterFromVolumeNode(inputVolume)

        import time
        startTime = time.time()
        logging.info(_("Processing started"))

        inputSegmentation.SetReferenceImageGeometryParameterFromVolumeNode(inputVolume)
        # Ensure the segment is visible so that SegmentStatistics can process it.
        inputSegmentation.GetDisplayNode().SetSegmentVisibility(segmentID, True)

        lowerIntensity = float(self._parameterNode.GetParameter(ROLE_INPUT_LOWER_INTENSITY_BOUND))
        upperIntensity = float(self._parameterNode.GetParameter(ROLE_INPUT_UPPER_INTENSITY_BOUND))
        if (lowerIntensity !=0) and (upperIntensity != 0):
            calcifHURange = [lowerIntensity, upperIntensity]
        else:
            calcifHURange = self.probeCalcificationIntensityRange()

        seWidget.mrmlSegmentEditorNode().SetMaskMode(slicer.vtkMRMLSegmentationNode.EditAllowedEverywhere)
        seWidget.mrmlSegmentEditorNode().SourceVolumeIntensityMaskOff()
        seWidget.mrmlSegmentEditorNode().SetOverwriteMode(seWidget.mrmlSegmentEditorNode().OverwriteNone)
        
        # Create calcification segment by duplicating the lumen.
        lumenSegmentName = inputSegmentation.GetSegmentation().GetSegment(segmentID).GetName()
        calcifSegmentID = segmentID + "_Dense_Calcification"
        calcifSegmentName = lumenSegmentName + "_Dense_Calcification"
        if inputSegmentation.GetSegmentation().GetSegment(calcifSegmentID):
            inputSegmentation.GetSegmentation().RemoveSegment(calcifSegmentID)
        calcifSegmentID = inputSegmentation.GetSegmentation().AddEmptySegment(calcifSegmentID)
        seWidget.mrmlSegmentEditorNode().SetSelectedSegmentID(calcifSegmentID)
        seWidget.setActiveEffectByName("Logical operators")
        effect = seWidget.activeEffect()
        effect.setParameter("BypassMasking", str(1))
        effect.setParameter("Operation", "COPY")
        effect.setParameter("ModifierSegmentID", segmentID)
        effect.self().onApply()
        seWidget.setActiveEffectByName(None)
        inputSegmentation.GetSegmentation().GetSegment(calcifSegmentID).SetName(calcifSegmentName)
        
        # Calculate and set calcification intensity range, a reasonable arbitrary range.
        seWidget.mrmlSegmentEditorNode().SetMaskMode(slicer.vtkMRMLSegmentationNode.EditAllowedOutsideVisibleSegments)
        seWidget.mrmlSegmentEditorNode().SourceVolumeIntensityMaskOn()
        seWidget.mrmlSegmentEditorNode().SetSourceVolumeIntensityMaskRange(calcifHURange[0], calcifHURange[1])
        
        # Grow by margin within intensity range.
        seWidget.setActiveEffectByName("Margin")
        effect = seWidget.activeEffect()
        effect.setParameter("ApplyToAllVisibleSegments", str(0))
        effect.setParameter("MarginSizeMm", marginSize)
        effect.self().onApply()
        seWidget.setActiveEffectByName(None)
        
        seWidget.mrmlSegmentEditorNode().SetMaskMode(slicer.vtkMRMLSegmentationNode.EditAllowedEverywhere)
        seWidget.mrmlSegmentEditorNode().SourceVolumeIntensityMaskOff()
        
        # Subtract the lumen.
        seWidget.setActiveEffectByName("Logical operators")
        effect = seWidget.activeEffect()
        effect.setParameter("BypassMasking", str(1))
        effect.setParameter("Operation", "SUBTRACT")
        effect.setParameter("ModifierSegmentID", segmentID)
        effect.self().onApply()
        seWidget.setActiveEffectByName(None)
        
        seWidget.mrmlSegmentEditorNode().SetSelectedSegmentID(calcifSegmentID)
        inputSegmentation.GetDisplayNode().SetSegmentOpacity3D(segmentID, 0.5)
        inputSegmentation.GetDisplayNode().SetSegmentOpacity3D(calcifSegmentID, 0.5)

        stopTime = time.time()
        durationValue = '%.2f' % (stopTime-startTime)
        logging.info(_("Processing completed in {duration} seconds").format(duration=durationValue))

        return calcifSegmentID

    def probeCalcificationIntensityRange(self):
        if not self._parameterNode:
            raise ValueError(_("Parameter node is None."))

        inputSegmentation = self._parameterNode.GetNodeReference(ROLE_INPUT_SEGMENTATION)
        inputVolume = self._parameterNode.GetNodeReference(ROLE_INPUT_VOLUME)
        segmentID = self._parameterNode.GetParameter(ROLE_INPUT_SEGMENT)

        if not inputSegmentation or not inputVolume or not segmentID or segmentID == "":
            raise ValueError(_("Input segmentation, volume, segment ID or margin size is invalid."))

        """
        We need the volume to get intensity values.
        We don't set the segment editor's volume input. They are expected to be
        the same.
        """
        import SegmentStatistics
        ssLogic = SegmentStatistics.SegmentStatisticsLogic()
        ssLogic.getParameterNode().SetParameter("Segmentation", inputSegmentation.GetID())
        ssLogic.getParameterNode().SetParameter("ScalarVolume", inputVolume.GetID())
        ssLogic.computeStatistics()
        
        # k = ssLogic.getNonEmptyKeys()
        medianSegmentHU = float(ssLogic.getStatisticsValueAsString(segmentID, "ScalarVolumeSegmentStatisticsPlugin.median"))
        maxSegmentHU = float(ssLogic.getStatisticsValueAsString(segmentID, "ScalarVolumeSegmentStatisticsPlugin.max"))
        maxVolumeHU = inputVolume.GetImageData().GetScalarRange()[1]

        return ((medianSegmentHU + maxSegmentHU) / 2.0, maxVolumeHU * 0.95 )
#
# ArterialCalcificationPreProcessorTest
#

class ArterialCalcificationPreProcessorTest(ScriptedLoadableModuleTest):

    def setUp(self):
        """ Do whatever is needed to reset the state - typically a scene clear will be enough.
        """
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here.
        """
        self.setUp()
        self.test_ArterialCalcificationPreProcessor1()

    def test_ArterialCalcificationPreProcessor1(self):

        self.delayDisplay(_("Starting the test"))

        self.delayDisplay(_("Test passed"))

ROLE_INPUT_SEGMENTATION = "InputSegmentation"
ROLE_INPUT_SEGMENT = "InputSegment"
ROLE_INPUT_VOLUME = "InputVolume"
ROLE_INPUT_MARGIN = "InputMargin"
ROLE_INPUT_LOWER_INTENSITY_BOUND = "InputLowerIntensity"
ROLE_INPUT_UPPER_INTENSITY_BOUND = "InputUpperIntensity"
ROLE_SHOW3D = "Show3D"
ROLE_INITIALIZED = "Initialized"
