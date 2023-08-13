import logging
import os
from typing import Annotated, Optional

import vtk

import slicer
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
        self.parent.helpText = """
Segment calcifications around an arterial lumen within a margin.
See more information in <a href="href="https://github.com/vmtk/SlicerExtension-VMTK/">module documentation</a>.
"""
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
"""

#
# ArterialCalcificationPreProcessorParameterNode
#

@parameterNodeWrapper
class ArterialCalcificationPreProcessorParameterNode:
    """
    The parameters needed by module.
    """
    inputVolume: slicer.vtkMRMLScalarVolumeNode
    marginSize: float = 4.0

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
        self._parameterNodeGuiTag = None

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

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

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
        # Do not react to parameter node changes (GUI will be updated when the user enters into the module)
        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self._parameterNodeGuiTag = None

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
        Ensure parameter node exists and observed.
        """
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

        self.setParameterNode(self.logic.getParameterNode())

    def setParameterNode(self, inputParameterNode: Optional[ArterialCalcificationPreProcessorParameterNode]) -> None:
        """
        Set and observe parameter node.
        Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
        """

        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
        self._parameterNode = inputParameterNode
        if self._parameterNode:
            # Note: in the .ui file, a Qt dynamic property called "SlicerParameterName" is set on each
            # ui element that needs connection.
            self._parameterNodeGuiTag = self._parameterNode.connectGui(self.ui)

    def onApplyButton(self) -> None:

        with slicer.util.tryWithErrorDisplay("Failed to compute results.", waitCursor=True):
            
            # Compute output
            self.logic.process(self.ui.segmentSelector.currentNode(),
                               self._parameterNode.inputVolume,
                               self.ui.segmentSelector.currentSegmentID(),
                               self._parameterNode.marginSize)

#
# ArterialCalcificationPreProcessorLogic
#

class ArterialCalcificationPreProcessorLogic(ScriptedLoadableModuleLogic):

    def __init__(self) -> None:
        """
        Called when the logic class is instantiated. Can be used for initializing member variables.
        """
        ScriptedLoadableModuleLogic.__init__(self)

    def getParameterNode(self):
        return ArterialCalcificationPreProcessorParameterNode(super().getParameterNode())

    def process(self,
                inputSegmentation: slicer.vtkMRMLSegmentationNode,
                inputVolume: slicer.vtkMRMLScalarVolumeNode,
                segmentID,
                marginSize: float = 4.0) -> None:

        if not inputSegmentation or not inputVolume or not segmentID or segmentID == "":
            raise ValueError("Input segmentation, volume or segment ID is invalid")
        
        import time
        startTime = time.time()
        logging.info('Processing started')
        
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
        
        # Create slicer.modules.SegmentEditorWidget
        slicer.modules.segmenteditor.widgetRepresentation()
        seWidget = slicer.modules.SegmentEditorWidget.editor
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
        calcifHURange = ((medianSegmentHU + maxSegmentHU) / 2.0, maxVolumeHU * 0.95 )
        seWidget.mrmlSegmentEditorNode().SetMaskMode(slicer.vtkMRMLSegmentationNode.EditAllowedOutsideVisibleSegments)
        seWidget.mrmlSegmentEditorNode().SourceVolumeIntensityMaskOn()
        seWidget.mrmlSegmentEditorNode().SetSourceVolumeIntensityMaskRange(calcifHURange[0], calcifHURange[1])
        
        # Grow by margin within intensity range.
        seWidget.setActiveEffectByName("Margin")
        effect = seWidget.activeEffect()
        effect.setParameter("ApplyToAllVisibleSegments", str(0))
        effect.setParameter("MarginSizeMm", str(marginSize))
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
        logging.info(f'Processing completed in {stopTime-startTime:.2f} seconds')

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

        self.delayDisplay("Starting the test")

        self.delayDisplay('Test passed')
