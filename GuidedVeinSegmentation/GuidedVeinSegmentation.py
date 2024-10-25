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
        self._parameterNode = None
        self._parameterNodeGuiTag = None

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
        self.ui.parameterSetSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.parameterSetChanged)
        self.ui.parameterSetSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.updateSliceViews)

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
        
        # Buttons
        self.ui.applyButton.connect('clicked(bool)', self.onApply)

        # Refrain from adding a new parameter set.
        
    def cleanup(self) -> None:
        """
        Called when the application closes and the module widget is destroyed.
        """
        self.removeObservers()

    def enter(self) -> None:
        """Called each time the user opens this module."""
        # Make sure parameter node exists and observed
        if self._parameterNode:
            self._parameterNodeGuiTag = self._parameterNode.connectGui(self.ui)

    def exit(self) -> None:
        """Called each time the user opens a different module."""
        # Do not react to parameter node changes (GUI will be updated when the user enters into the module)
        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self._parameterNodeGuiTag = None

    def onSceneStartClose(self, caller, event) -> None:
        """Called just before the scene is closed."""

    def onSceneEndClose(self, caller, event) -> None:
        """Called just after the scene is closed."""
        self.parameterSetChanged(None)

    def setParameterNode(self, inputParameterNode: Optional[GuidedVeinSegmentationParameterNode]) -> None:
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
        self.logic.setParameterNode(self._parameterNode)

    def parameterSetChanged(self, newParameterSet):
        # Refrain from adding a new vtkMRMLScriptedModuleNode to scene if parameterNode is None.
        # When nodes are deleted, the wrapper outputs errors and alien nodes appear in the selector.
        if not newParameterSet:
            self.setParameterNode(None)
            return
        nextParameterNode = GuidedVeinSegmentationParameterNode(newParameterSet)
        self.setParameterNode(nextParameterNode)

    def updateSliceViews(self):
        parameterNode = self._parameterNode
        if (not parameterNode) or (not parameterNode.inputVolume):
            return
        slicer.util.setSliceViewerLayers(background = parameterNode.inputVolume.GetID(), fit = True)

    def onApply(self) -> None:
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
        self._parameterNode = None

    def setParameterNode(self, parameterNode):
        self._parameterNode = parameterNode

    def getParameterNode(self):
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
