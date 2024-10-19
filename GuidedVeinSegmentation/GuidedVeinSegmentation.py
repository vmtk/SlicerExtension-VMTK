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
# GuidedVeinSegmentationParameterNode
#

@parameterNodeWrapper
class GuidedVeinSegmentationParameterNode:
    inputCurve: slicer.vtkMRMLMarkupsCurveNode
    inputVolume: slicer.vtkMRMLScalarVolumeNode
    inputSegmentation: slicer.vtkMRMLSegmentationNode
    extrusionKernelSize: float = 5.0
    gaussianStandardDeviation: float = 2.0
    seedRadius: float = 1.0
    shellMargin: float = 18.0
    shellThickness: float = 2.0
    subtractOtherSegments: bool = True

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
        self._wrappedParameterNode = None
        self._mrmlParameterNode = None
        self._parameterNodeGuiTag = None
        self._parameterNodeBeingModified = False

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
        '''
        Do not use the 'ModuleName' attribute. The logic's vtkMRMLScriptedModuleNode inner
        parameter node has the same 'ModuleName' attribute with the module's name as value.
        This inner MRML parameter node will appear as a default node in the combobox, and
        it must not be used here at all. Ensure that the basename of the selector is not
        the same as the module's name.
        '''
        parameterSetBaseName = self.ui.parameterSetSelector.baseName
        if parameterSetBaseName == self.moduleName:
            logging.warning("The basename of the parameter set selector must not be equal to the module's name.")
            # Don't return, though bad things will happen.
        self.ui.parameterSetSelector.addAttribute("vtkMRMLScriptedModuleNode", "BaseName", parameterSetBaseName)

        # Connections
        self.ui.parameterSetSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.onMrmlParameterNodeChanged)
        self.ui.parameterSetSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.updateSliceViews)
        
        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
        
        # Buttons
        self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)
        
        # Make sure parameter node is initialized (needed for module reload)
        self.initializeWrappedParameterNode()

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
        if not self._wrappedParameterNode:
            self.initializeWrappedParameterNode()
        else:
            self.onMrmlParameterNodeChanged(self.ui.parameterSetSelector.currentNode())

    def exit(self) -> None:
        """
        Called each time the user opens a different module.
        """

    def onSceneStartClose(self, caller, event) -> None:
        """
        Called just before the scene is closed.
        """

    def onSceneEndClose(self, caller, event) -> None:
        """
        Called just after the scene is closed.
        """
        # Restore wrapped parameter node to defaults and set MRML parameter node to None.
        self.onMrmlParameterNodeChanged(None)

    def restoreWrappedParameterNode(self) -> None:
        if not self._wrappedParameterNode:
            return
        # Restore to default values.
        self._wrappedParameterNode.inputCurve = None
        self._wrappedParameterNode.inputVolume = None
        self._wrappedParameterNode.inputSegmentation = None
        self._wrappedParameterNode.extrusionKernelSize = 5.0
        self._wrappedParameterNode.gaussianStandardDeviation = 2.0
        self._wrappedParameterNode.seedRadius = 1.0
        self._wrappedParameterNode.shellMargin = 18.0
        self._wrappedParameterNode.shellThickness = 2.0
        self._wrappedParameterNode.subtractOtherSegments = True

    def initializeWrappedParameterNode(self) -> None:
        """
        Ensure parameter node exists and observed.
        """
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

        # Called only once.
        self.setWrappedParameterNode(self.logic.getParameterNode())

    def setWrappedParameterNode(self, inputParameterNode: Optional[GuidedVeinSegmentationParameterNode]) -> None:
        """
        Set and observe parameter node.
        Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
        """
        # If the wrapped parameter node has already been initialized, don't do anything.
        if self._wrappedParameterNode:
            return

        # We get here once only throughout a Slicer's session.
        self._wrappedParameterNode = inputParameterNode

        if self._wrappedParameterNode:
            # Note: in the .ui file, a Qt dynamic property called "SlicerParameterName" is set on each
            # ui element that needs connection.
            self._parameterNodeGuiTag = self._wrappedParameterNode.connectGui(self.ui)
            self.addObserver(self._wrappedParameterNode, vtk.vtkCommand.ModifiedEvent, self.updateMrmlParameterNode)
            # Add an initial MRML parameter node.
            if self.ui.parameterSetSelector.nodeCount() == 0:
                self.ui.parameterSetSelector.addNode("vtkMRMLScriptedModuleNode")

    def onMrmlParameterNodeChanged(self, parameterNode: slicer.vtkMRMLScriptedModuleNode):
        # The current item has changed in the selector.
        if not self._wrappedParameterNode:
            return

        self._mrmlParameterNode = parameterNode
        if not self._mrmlParameterNode:
            self.restoreWrappedParameterNode()
            return
        
        if parameterNode.GetParameterCount() == 0:
            # Set default values of an empty MRML parameter node.
            parameterNode.AddNodeReferenceID("inputCurve", None)
            parameterNode.AddNodeReferenceID("inputVolume", None)
            parameterNode.AddNodeReferenceID("inputSegmentation", None)
            parameterNode.SetParameter("extrusionKernelSize", "5.0")
            parameterNode.SetParameter("gaussianStandardDeviation", "2.0")
            parameterNode.SetParameter("seedRadius", "1.0")
            parameterNode.SetParameter("shellMargin", "18.0")
            parameterNode.SetParameter("shellThickness", "2.0")
            parameterNode.SetParameter("subtractOtherSegments", "1")
        
        # Avoid a loop with updateMrmlParameterNode.
        self._parameterNodeBeingModified = True

        # Update the wrapped parameter node and the connected GUI.
        wrappedParameterNode = self._wrappedParameterNode
        wrappedParameterNode.inputCurve = parameterNode.GetNodeReference("inputCurve")
        wrappedParameterNode.inputVolume = parameterNode.GetNodeReference("inputVolume")
        wrappedParameterNode.inputSegmentation = parameterNode.GetNodeReference("inputSegmentation")
        wrappedParameterNode.extrusionKernelSize = float(parameterNode.GetParameter("extrusionKernelSize"))
        wrappedParameterNode.gaussianStandardDeviation = float(parameterNode.GetParameter("gaussianStandardDeviation"))
        wrappedParameterNode.seedRadius = float(parameterNode.GetParameter("seedRadius"))
        wrappedParameterNode.shellMargin = float(parameterNode.GetParameter("shellMargin"))
        wrappedParameterNode.shellThickness = float(parameterNode.GetParameter("shellThickness"))
        wrappedParameterNode.subtractOtherSegments = False if (parameterNode.GetParameter("subtractOtherSegments") == "False") else True

        self._parameterNodeBeingModified = False

    def updateMrmlParameterNode(self, caller=None, event=None):
        # Avoid a loop with onMrmlParameterNodeChanged.
        if self._parameterNodeBeingModified:
            return
        if not self._wrappedParameterNode:
            return

        # Update the MRML parameter node of the combobox when a widget is changed bu user interaction.
        mrmlParameterNode = self._mrmlParameterNode
        wrappedParameterNode = self._wrappedParameterNode
        if mrmlParameterNode:
            mrmlParameterNode.SetNodeReferenceID("inputCurve", None if not wrappedParameterNode.inputCurve else wrappedParameterNode.inputCurve.GetID())
            mrmlParameterNode.SetNodeReferenceID("inputVolume", None if not wrappedParameterNode.inputVolume else wrappedParameterNode.inputVolume.GetID())
            mrmlParameterNode.SetNodeReferenceID("inputSegmentation", None if not wrappedParameterNode.inputSegmentation else wrappedParameterNode.inputSegmentation.GetID())
            mrmlParameterNode.SetParameter("extrusionKernelSize", str(wrappedParameterNode.extrusionKernelSize))
            mrmlParameterNode.SetParameter("gaussianStandardDeviation", str(wrappedParameterNode.gaussianStandardDeviation))
            mrmlParameterNode.SetParameter("seedRadius", str(wrappedParameterNode.seedRadius))
            mrmlParameterNode.SetParameter("shellMargin", str(wrappedParameterNode.shellMargin))
            mrmlParameterNode.SetParameter("shellThickness", str(wrappedParameterNode.shellThickness))
            mrmlParameterNode.SetParameter("subtractOtherSegments", str(wrappedParameterNode.subtractOtherSegments))

    def updateSliceViews(self):
        wrappedParameterNode = self._wrappedParameterNode
        if (not wrappedParameterNode) or (not wrappedParameterNode.inputVolume):
            return
        slicer.util.setSliceViewerLayers(background = wrappedParameterNode.inputVolume.GetID(), fit = True)

    def onApplyButton(self) -> None:
        """
        Run processing when user clicks "Apply" button.
        """
        with slicer.util.tryWithErrorDisplay(_("Failed to compute results."), waitCursor=True):
            if not self.ui.parameterSetSelector.currentNode():
                slicer.util.showStatusMessage(_("No parameter set defined."), 3000)
                logging.error("No parameter set defined.")
                return

            # Compute output
            self.logic.process()

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
        '''
        Connecting a wrapped parameter node:
            self._parameterNodeGuiTag = self._wrappedParameterNode.connectGui(self.ui)

        _parameterNodeGuiTag is always None because connectGui() does not return.
        Hence disconnectGui() doesn't seem to do anything.

        Use a single wrapped parameter node in this Slicers' session.
        Avoid connecting multiple wrapped parameter nodes disputing the UI.
        Update this parameter node explicitly whenever required.
        '''
        self._parameterNode = None
        self.initializeParameterNode()

    def initializeParameterNode(self):
        self._parameterNode = GuidedVeinSegmentationParameterNode(super().getParameterNode())

    def getParameterNode(self):
        '''
        A single wrapped parameter node throughout, because a connected GUI is never disconnected.
        This is consistent with the fact that super().getParameterNode()
        gives a same vtkMRMLScriptedModuleNode object.
        Update this wrapped parameter node whenever the parameter set changes.
        '''
        return self._parameterNode

    def process(self) -> None:
        inputCurve = self._parameterNode.inputCurve
        inputVolume = self._parameterNode.inputVolume
        inputSegmentation = self._parameterNode.inputSegmentation
        extrusionKernelSize = self._parameterNode.extrusionKernelSize
        gaussianStandardDeviation = self._parameterNode.gaussianStandardDeviation
        seedRadius = self._parameterNode.seedRadius
        shellMargin = self._parameterNode.shellMargin
        shellThickness = self._parameterNode.shellThickness
        subtractOtherSegments = self._parameterNode.subtractOtherSegments

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
