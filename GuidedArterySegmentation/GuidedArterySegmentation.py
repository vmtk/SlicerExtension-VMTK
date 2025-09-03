import logging
import os
from typing import Annotated, Optional

import vtk, ctk, qt

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
# GuidedArterySegmentation
#

class GuidedArterySegmentation(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent) -> None:
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Guided artery segmentation"
    self.parent.categories = ["Vascular Modeling Toolkit"]
    self.parent.dependencies = ["ExtractCenterline"]
    self.parent.contributors = ["Saleem Edah-Tally [Surgeon] [Hobbyist developer]", "Andras Lasso (PerkLab)"]
    self.parent.helpText = _("""
This <a href="https://github.com/vmtk/SlicerExtension-VMTK/">module</a> is intended to create a segmentation from a contrast enhanced CT angioscan, and to finally extract centerlines from the surface model.
<br><br>It assumes that curve control points are placed in the contrasted lumen.
<br><br>The 'Flood filling' and 'Split volume' effects of the '<a href="https://github.com/lassoan/SlicerSegmentEditorExtraEffects">Segment editor extra effects</a>' are used.
<br><br>The '<a href="https://github.com/vmtk/SlicerExtension-VMTK/tree/master/ExtractCenterline/">SlicerExtension-VMTK Extract centerline</a>' module is required.
""")
    # TODO: replace with organization, grant and thanks
    self.parent.acknowledgementText = _("""
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
""")

class GuidedArterySegmentationWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
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
    self._useLargestSegmentRegion = None

  def setup(self) -> None:
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer).
    # Additional widgets can be instantiated manually and added to self.layout.
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/GuidedArterySegmentation.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    # Create logic class. Logic implements all computations that should be possible to run
    # in batch mode, without a graphical user interface.
    self.logic = GuidedArterySegmentationLogic()
    self.ui.parameterSetSelector.addAttribute("vtkMRMLScriptedModuleNode", "ModuleName", self.moduleName)

    self.ui.floodFillingCollapsibleGroupBox.checked = False
    self.ui.extentCollapsibleGroupBox.checked = False
    self.ui.regionInfoLabel.setVisible(False)
    self.ui.fixRegionToolButton.setVisible(False)

    # Connections

    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    # Application connections
    self.ui.inputCurveSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onCurveNode)
    self.ui.inputShapeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onShapeNode)

    self.ui.inputSliceNodeSelector.connect("currentNodeChanged(vtkMRMLNode*)", lambda node: self.onMrmlNodeChanged(ROLE_INPUT_SLICE, node))
    self.ui.outputSegmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", lambda node: self.onMrmlNodeChanged(ROLE_OUTPUT_SEGMENTATION, node))
    self.ui.tubeDiameterSpinBox.connect("valueChanged(double)", lambda value: self.onSpinBoxChanged(ROLE_INPUT_DIAMETER, value))
    self.ui.intensityToleranceSpinBox.connect("valueChanged(int)", lambda value: self.onSpinBoxChanged(ROLE_INPUT_INTENSITY_TOLERANCE, value))
    self.ui.neighbourhoodSizeDoubleSpinBox.connect("valueChanged(double)", lambda value: self.onSpinBoxChanged(ROLE_INPUT_NEIGHBOURHOOD_SIZE, value))
    self.ui.extractCenterlinesCheckBox.connect("toggled(bool)", lambda checked: self.onBooleanToggled(ROLE_OPTION_EXTRACT_CENTERLINES, checked))
    self.ui.kernelSizeSpinBox.connect("valueChanged(double)", lambda value: self.onSpinBoxChanged(ROLE_INPUT_KERNEL_SIZE, value))

    self.ui.fixRegionToolButton.connect("clicked()", self.updateSegmentBySmoothClosing)

    self.ui.parameterSetSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.setParameterNode)
    self.ui.parameterSetUpdateUIToolButton.connect("clicked(bool)", self.onParameterSetUpdateUiClicked)

    self.ui.applyButton.menu().clear()
    self._useLargestSegmentRegion = qt.QAction(_("Use the largest region of the segment"))
    self._useLargestSegmentRegion.setCheckable(True)
    self._useLargestSegmentRegion.setChecked(True)
    self.ui.applyButton.menu().addAction(self._useLargestSegmentRegion)

    self.ui.applyButton.menu().clear()
    self._useLargestSegmentRegion = qt.QAction(_("Use the largest region of the segment"))
    self._useLargestSegmentRegion.setCheckable(True)
    self._useLargestSegmentRegion.setChecked(True)
    self.ui.applyButton.menu().addAction(self._useLargestSegmentRegion)

    # Buttons
    self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)
    self._useLargestSegmentRegion.connect("toggled(bool)", lambda value: self.onBooleanToggled(ROLE_OPTION_USE_LARGEST_REGION, value))

    # Make sure parameter node is initialized (needed for module reload)
    self.initializeParameterNode()

    # A hidden one for the curious !
    shortcut = qt.QShortcut(self.ui.GuidedArterySegmentation)
    shortcut.setKey(qt.QKeySequence('Meta+d'))
    shortcut.connect( 'activated()', lambda: self.removeOutputNodes())

    extensionName = "SegmentEditorExtraEffects"
    em = slicer.app.extensionsManagerModel()
    em.interactive = True
    restart = True
    if not em.installExtensionFromServer(extensionName, restart):
      raise ValueError(_("Failed to install {nameOfExtension} extension").format(nameOfExtension=extensionName))

  def inform(self, message) -> None:
    slicer.util.showStatusMessage(message, 3000)
    logging.info(message)

  def onCurveNode(self, node) -> None:
    if (not self._parameterNode) or (not node):
      return;
    numberOfControlPoints = node.GetNumberOfControlPoints()
    if numberOfControlPoints < 3:
        self.inform(_("Curve node must have at least 3 points."))
        return
    self.onMrmlNodeChanged(ROLE_INPUT_CURVE, node)

  def onShapeNode(self, node) -> None:
    self.onMrmlNodeChanged(ROLE_INPUT_SHAPE, node) # Always +++.
    if node is None:
        self.ui.tubeDiameterSpinBoxLabel.setVisible(True)
        self.ui.tubeDiameterSpinBox.setVisible(True)
        return
    if node.GetShapeName() != slicer.vtkMRMLMarkupsShapeNode().Tube:
        self.inform(_("Shape node is not a Tube."))
        inputShapeNode = None
        self.ui.tubeDiameterSpinBoxLabel.setVisible(True)
        self.ui.tubeDiameterSpinBox.setVisible(True)
        return
    numberOfControlPoints = node.GetNumberOfControlPoints()
    if numberOfControlPoints < 4:
        self.inform(_("Shape node must have at least 4 points."))
        inputShapeNode = None
        self.ui.tubeDiameterSpinBoxLabel.setVisible(True)
        self.ui.tubeDiameterSpinBox.setVisible(True)
        return
    self.ui.tubeDiameterSpinBoxLabel.setVisible(False)
    self.ui.tubeDiameterSpinBox.setVisible(False)

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
    Ensure parameter node exists and observed.
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
      self.onParameterSetUpdateUiClicked()
      self.updateRegionInfo()

  def setDefaultValues(self):
    if not self._parameterNode:
      return

    if self._parameterNode.HasParameter(ROLE_INITIALIZED):
      return

    self._parameterNode.SetParameter(ROLE_INPUT_DIAMETER, str(8.0))
    self._parameterNode.SetParameter(ROLE_INPUT_INTENSITY_TOLERANCE, str(100))
    self._parameterNode.SetParameter(ROLE_INPUT_NEIGHBOURHOOD_SIZE, str(2.0))
    self._parameterNode.SetParameter(ROLE_INPUT_KERNEL_SIZE, str(1.1))
    self._parameterNode.SetParameter(ROLE_OPTION_EXTRACT_CENTERLINES, str(0))
    self._parameterNode.SetParameter(ROLE_OPTION_USE_LARGEST_REGION, str(1))
    self._parameterNode.SetParameter(ROLE_INITIALIZED, str(1))

  def onApplyButton(self) -> None:
    """
    Run processing when user clicks "Apply" button.
    """
    try:
      inputCurveNode = self._parameterNode.GetNodeReference(ROLE_INPUT_CURVE)
      inputSliceNode = self._parameterNode.GetNodeReference(ROLE_INPUT_SLICE)
      if inputCurveNode is None:
          self.inform(_("No input curve node specified."))
          return
      if inputCurveNode.GetNumberOfControlPoints() < 3:
          self.inform(_("Input curve node must have at least 3 control points."))
          return
      if inputSliceNode is None:
          self.inform(_("No input slice node specified."))
          return
      # Ensure there's a background volume node.
      sliceWidget = slicer.app.layoutManager().sliceWidget(inputSliceNode.GetName())
      volumeNode = sliceWidget.sliceLogic().GetBackgroundLayer().GetVolumeNode()
      if volumeNode is None:
          self.inform(_("No volume node selected in input slice node."))
          return
      # Compute output
      self.logic.process()
      # Update segmentation selector if it was none
      outputSegmentationNode = self._parameterNode.GetNodeReference(ROLE_OUTPUT_SEGMENTATION)
      self.ui.outputSegmentationSelector.setCurrentNode(outputSegmentationNode)
      # Inform about the number of regions in the output segment.
      self.updateRegionInfo()

    except Exception as e:
      slicer.util.errorDisplay(_("Failed to compute results: ") + str(e))
      import traceback
      traceback.print_exc()

  def onParameterSetUpdateUiClicked(self):
    if not self._parameterNode:
      return

    outputSegmentation = self._parameterNode.GetNodeReference(ROLE_OUTPUT_SEGMENTATION)
    inputVolume = self._parameterNode.GetNodeReference(ROLE_INPUT_VOLUME)

    if outputSegmentation:
      # Create segment editor object if needed.
      segmentEditorModuleWidget = slicer.util.getModuleWidget("SegmentEditor")
      seWidget = segmentEditorModuleWidget.editor
      seWidget.setSegmentationNode(outputSegmentation)
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

    self.ui.inputCurveSelector.setCurrentNode(self._parameterNode.GetNodeReference(ROLE_INPUT_CURVE))
    self.ui.inputSliceNodeSelector.setCurrentNode(self._parameterNode.GetNodeReference(ROLE_INPUT_SLICE))
    self.ui.inputShapeSelector.setCurrentNode(self._parameterNode.GetNodeReference(ROLE_INPUT_SHAPE))
    self.ui.outputSegmentationSelector.setCurrentNode(self._parameterNode.GetNodeReference(ROLE_OUTPUT_SEGMENTATION))
    self.ui.intensityToleranceSpinBox.setValue(int(self._parameterNode.GetParameter(ROLE_INPUT_INTENSITY_TOLERANCE)))
    self.ui.neighbourhoodSizeDoubleSpinBox.setValue(float(self._parameterNode.GetParameter(ROLE_INPUT_NEIGHBOURHOOD_SIZE)))
    self.ui.tubeDiameterSpinBox.setValue(float(self._parameterNode.GetParameter(ROLE_INPUT_DIAMETER)))
    self.ui.extractCenterlinesCheckBox.setChecked(int(self._parameterNode.GetParameter(ROLE_OPTION_EXTRACT_CENTERLINES)))
    self._useLargestSegmentRegion.setChecked(int(self._parameterNode.GetParameter(ROLE_OPTION_USE_LARGEST_REGION)))
    self.ui.kernelSizeSpinBox.setValue(float(self._parameterNode.GetParameter(ROLE_INPUT_KERNEL_SIZE))
                                       if self._parameterNode.GetParameter(ROLE_INPUT_KERNEL_SIZE) else 1.1)

    self._updatingGUIFromParameterNode = False

  # Handy during development
  def removeOutputNodes(self) -> None:
    if not self._parameterNode:
        return
    outputFiducialNode = self._parameterNode.GetNodeReference(ROLE_OUTPUT_FIDUCIAL)
    if (outputFiducialNode):
      slicer.mrmlScene.RemoveNode(outputFiducialNode)
      self.onMrmlNodeChanged(ROLE_OUTPUT_FIDUCIAL, None)
    outputCenterlineModel = self._parameterNode.GetNodeReference(ROLE_OUTPUT_CENTERLINE_MODEL)
    if (outputCenterlineModel):
      slicer.mrmlScene.RemoveNode(outputCenterlineModel)
      self.onMrmlNodeChanged(ROLE_OUTPUT_CENTERLINE_MODEL, None)
    outputCenterlineCurve = self._parameterNode.GetNodeReference(ROLE_OUTPUT_CENTERLINE_CURVE)
    if (outputCenterlineCurve):
      slicer.mrmlScene.RemoveNode(outputCenterlineCurve)
      self.onMrmlNodeChanged(ROLE_OUTPUT_CENTERLINE_CURVE, None)

    # Remove segment.
    segmentation = self._parameterNode.GetNodeReference(ROLE_OUTPUT_SEGMENTATION)
    if segmentation:
      segmentID = self._parameterNode.GetParameter(ROLE_OUTPUT_SEGMENT)
      segment = segmentation.GetSegmentation().GetSegment(segmentID)
      if segment:
          segmentation.GetSegmentation().RemoveSegment(segment)
          self._parameterNode.SetParameter(ROLE_OUTPUT_SEGMENT, "")

  def updateRegionInfo(self):
    if not self._parameterNode:
      self.ui.regionInfoLabel.setVisible(False)
      self.ui.fixRegionToolButton.setVisible(False)
      self.ui.kernelSizeSpinBox.setVisible(False)
      return
    segmentation = self._parameterNode.GetNodeReference(ROLE_OUTPUT_SEGMENTATION)
    segmentID = self._parameterNode.GetParameter(ROLE_OUTPUT_SEGMENT)
    if (not segmentation) or (not segmentID):
      self.inform(_("Invalid segmentation or segmentID."))
      self.ui.regionInfoLabel.setVisible(False)
      self.ui.fixRegionToolButton.setVisible(False)
      self.ui.kernelSizeSpinBox.setVisible(False)
      return

    sm3Logic = slicer.modules.stenosismeasurement3d.logic()
    numberOfRegions = sm3Logic.GetNumberOfRegionsInSegment(segmentation, segmentID)
    if numberOfRegions == 0:
      self.ui.regionInfoLabel.clear()
      self.ui.regionInfoLabel.setVisible(False)
      self.ui.fixRegionToolButton.setVisible(False)
      self.ui.kernelSizeSpinBox.setVisible(False)
      return
    regionInfo = _("Region count: ") + str(numberOfRegions)
    self.ui.regionInfoLabel.setText(regionInfo)
    self.ui.regionInfoLabel.setVisible(True)
    self.ui.fixRegionToolButton.setVisible(numberOfRegions > 1)
    self.ui.kernelSizeSpinBox.setVisible(numberOfRegions > 1)

  def updateSegmentBySmoothClosing(self):
    if not self._parameterNode:
      return
    segmentation = self._parameterNode.GetNodeReference(ROLE_OUTPUT_SEGMENTATION)
    segmentID = self._parameterNode.GetParameter(ROLE_OUTPUT_SEGMENT)
    if (not segmentation) or (not segmentID):
      self.inform(_("Invalid segmentation or segmentID."))
      self.ui.regionInfoLabel.setVisible(False)
      return
    kernelSize = self._parameterNode.GetParameter(ROLE_INPUT_KERNEL_SIZE)
    sm3Logic = slicer.modules.stenosismeasurement3d.logic()
    sm3Logic.UpdateSegmentBySmoothClosing(segmentation, segmentID, float(kernelSize))
    self.updateRegionInfo()

#
# GuidedArterySegmentationLogic
#

class GuidedArterySegmentationLogic(ScriptedLoadableModuleLogic):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget.
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self) -> None:
    """
    Called when the logic class is instantiated. Can be used for initializing member variables.
    """
    ScriptedLoadableModuleLogic.__init__(self)
    self._parameterNode = None

  def setParameterNode(self, inputParameterNode):
    self._parameterNode = inputParameterNode

  def showStatusMessage(self, messages) -> None:
    separator = " "
    msg = separator.join(messages)
    slicer.util.showStatusMessage(msg, 3000)
    slicer.app.processEvents()

  def process(self) -> None:
    if not self._parameterNode:
      raise ValueError(_("Parameter node is None."))

    import time
    startTime = time.time()
    logging.info((_("Processing started")))

    slicer.util.showStatusMessage(_("Segment editor setup"))
    slicer.app.processEvents()

    # Create a new segmentation if none is specified.
    segmentation = self._parameterNode.GetNodeReference(ROLE_OUTPUT_SEGMENTATION)
    if not segmentation:
      segmentation = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
      self._parameterNode.SetNodeReferenceID(ROLE_OUTPUT_SEGMENTATION, segmentation.GetID())

    # Create segment editor object if needed.
    segmentEditorModuleWidget = slicer.util.getModuleWidget("SegmentEditor")
    seWidget = segmentEditorModuleWidget.editor

    # Get volume node
    inputSliceNode = self._parameterNode.GetNodeReference(ROLE_INPUT_SLICE)
    sliceWidget = slicer.app.layoutManager().sliceWidget(inputSliceNode.GetName())
    volumeNode = sliceWidget.sliceLogic().GetBackgroundLayer().GetVolumeNode()
    if not volumeNode:
      raise ValueError(_("Background volume node in the selected slice node is None."))
    self._parameterNode.SetNodeReferenceID(ROLE_INPUT_VOLUME, volumeNode.GetID())

    # Set segment editor controls
    seWidget.setSegmentationNode(segmentation)
    seWidget.setSourceVolumeNode(volumeNode)
    segmentation.SetReferenceImageGeometryParameterFromVolumeNode(volumeNode)

    # Show the input curve. Colour of control points change on selection, helps to wait.
    inputCurveNode = self._parameterNode.GetNodeReference(ROLE_INPUT_CURVE)
    inputCurveNode.SetDisplayVisibility(True)
    # Reset segment editor masking widgets. Values set by previous work must not interfere here.
    seWidget.mrmlSegmentEditorNode().SetMaskMode(slicer.vtkMRMLSegmentationNode.EditAllowedEverywhere)
    seWidget.mrmlSegmentEditorNode().SourceVolumeIntensityMaskOff()
    seWidget.mrmlSegmentEditorNode().SetOverwriteMode(seWidget.mrmlSegmentEditorNode().OverwriteNone)

    inputShapeNode = self._parameterNode.GetNodeReference(ROLE_INPUT_SHAPE)
    if inputShapeNode is None:
      #---------------------- Draw tube with VTK---------------------
      # https://discourse.slicer.org/t/converting-markupscurve-to-markupsfiducial/20246/3
      tubeDiameter = float(self._parameterNode.GetParameter(ROLE_INPUT_DIAMETER))
      tube = vtk.vtkTubeFilter()
      tube.SetInputData(inputCurveNode.GetCurveWorld())
      tube.SetRadius(tubeDiameter / 2)
      tube.SetNumberOfSides(30)
      tube.CappingOn()
      tube.Update()
      tubeMaskSegmentId = segmentation.AddSegmentFromClosedSurfaceRepresentation(tube.GetOutput(), "TubeMask")
    else:
      #---------------------- Draw tube from Shape node ---------------------
      tubeMaskSegmentId = segmentation.AddSegmentFromClosedSurfaceRepresentation(inputShapeNode.GetCappedTubeWorld(), "TubeMask")
    # Select it so that Split Volume can work on this specific segment only.
    seWidget.setCurrentSegmentID(tubeMaskSegmentId)

    #---------------------- Split volume ---------------------
    slicer.util.showStatusMessage("Split volume")
    slicer.app.processEvents()
    intensityRange = volumeNode.GetImageData().GetScalarRange()
    seWidget.setActiveEffectByName("Split volume")
    svEffect = seWidget.activeEffect()
    svEffect.setParameter("FillValue", intensityRange[0])
    # Work on the TubeMask segment only.
    svEffect.setParameter("ApplyToAllVisibleSegments", 0)
    svEffect.self().onApply()
    seWidget.setActiveEffectByName(None)

    # Get output split volume
    allScalarVolumeNodes = slicer.mrmlScene.GetNodesByClass("vtkMRMLScalarVolumeNode")
    outputSplitVolumeNode = allScalarVolumeNodes.GetItemAsObject(allScalarVolumeNodes.GetNumberOfItems() - 1)
    # Remove no longer needed drawn tube segment
    segment = segmentation.GetSegmentation().GetSegment(tubeMaskSegmentId)
    segmentation.GetSegmentation().RemoveSegment(segment)
    # Replace master volume of segmentation
    seWidget.setSourceVolumeNode(outputSplitVolumeNode)
    segmentation.SetReferenceImageGeometryParameterFromVolumeNode(outputSplitVolumeNode)

    """
    Split Volume creates a folder that contains the segmentation node,
    and the split volume(s) it creates.
    Here, we need to get rid of the split volume. There is no reason to keep
    around the created folder, that takes owneship of the segmentation node.
    So we'll later move the segmentation node to the Scene node and remove the
    residual empty folder.
    """
    shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
    shSplitVolumeId = shNode.GetItemByDataNode(outputSplitVolumeNode)
    shSplitVolumeParentId = shNode.GetItemParent(shSplitVolumeId)
    shSegmentationId = shNode.GetItemByDataNode(segmentation)
    shSceneId = shNode.GetSceneItemID()

    #---------------------- Manage segment --------------------
    # Remove a segment node and keep its color
    segment = None
    segmentColor = []
    """
    Control the segment ID.
    It will be the same in all segmentations.
    We can reach it precisely.
    """
    segmentID = "Segment_" + inputCurveNode.GetID()
    self._parameterNode.SetParameter(ROLE_OUTPUT_SEGMENT, segmentID)
    segment = segmentation.GetSegmentation().GetSegment(segmentID)
    if segment:
        segmentColor = segment.GetColor()
        segmentation.GetSegmentation().RemoveSegment(segment)

    # Add a new segment, with controlled ID and known color.
    object = segmentation.GetSegmentation().AddEmptySegment(segmentID)
    segment = segmentation.GetSegmentation().GetSegment(object)
    if len(segmentColor):
        segment.SetColor(segmentColor)
    # Select new segment
    seWidget.setCurrentSegmentID(segmentID)

    #---------------------- Flood filling ---------------------
    # Set parameters
    intensityTolerance = int(self._parameterNode.GetParameter(ROLE_INPUT_INTENSITY_TOLERANCE))
    neighbourhoodSize = float(self._parameterNode.GetParameter(ROLE_INPUT_NEIGHBOURHOOD_SIZE))
    seWidget.setActiveEffectByName("Flood filling")
    ffEffect = seWidget.activeEffect()
    ffEffect.setParameter("IntensityTolerance", intensityTolerance)
    ffEffect.setParameter("NeighborhoodSizeMm", neighbourhoodSize)
    # +++ If an alien ROI is set, segmentation may fail and take an infinite time.
    ffEffect.parameterSetNode().SetNodeReferenceID("FloodFilling.ROI", None)
    ffEffect.updateGUIFromMRML()

    # Get input curve control points
    curveControlPoints = vtk.vtkPoints()
    inputCurveNode.GetControlPointPositionsWorld(curveControlPoints)
    numberOfCurveControlPoints = curveControlPoints.GetNumberOfPoints()

    # Apply flood filling at curve control points. Ignore first and last point as the resulting segment would be a big lump. The voxels of split volume at -1000 would be included in the segment.
    for i in range(1, numberOfCurveControlPoints - 1):
        # Show progress in status bar. Helpful to wait.
        t = time.time()
        durationValue = '%.2f' % (t-startTime)
        msg = _("Flood filling: {duration} seconds - ").format(duration=durationValue)
        self.showStatusMessage((msg, str(i + 1), "/", str(numberOfCurveControlPoints)))

        rasPoint = curveControlPoints.GetPoint(i)
        slicer.vtkMRMLSliceNode.JumpSlice(sliceWidget.sliceLogic().GetSliceNode(), *rasPoint)
        point3D = qt.QVector3D(rasPoint[0], rasPoint[1], rasPoint[2])
        point2D = ffEffect.rasToXy(point3D, sliceWidget)
        qIjkPoint = ffEffect.xyToIjk(point2D, sliceWidget, ffEffect.self().getClippedSourceImageData())
        ffEffect.self().floodFillFromPoint((int(qIjkPoint.x()), int(qIjkPoint.y()), int(qIjkPoint.z())))

    # Switch off active effect
    seWidget.setActiveEffect(None)
    # Replace master volume of segmentation
    seWidget.setSourceVolumeNode(volumeNode)
    segmentation.SetReferenceImageGeometryParameterFromVolumeNode(volumeNode)
    # Remove no longer needed split volume.
    slicer.mrmlScene.RemoveNode(outputSplitVolumeNode)

    # Remove folder created by Split Volume.
    # First, reparent the segmentation item to scene item.
    shNode.SetItemParent(shSegmentationId, shSceneId)
    """
    Remove an empty folder directly. Keep it if there are volumes from other
    work.
    """
    if shNode.GetNumberOfItemChildren(shSplitVolumeParentId) == 0:
        if shNode.GetItemLevel(shSplitVolumeParentId) == "Folder":
            shNode.RemoveItem(shSplitVolumeParentId)

    # Show segment. Poked from qMRMLSegmentationShow3DButton.cxx
    if segmentation.GetSegmentation().CreateRepresentation(slicer.vtkSegmentationConverter.GetSegmentationClosedSurfaceRepresentationName()):
        segmentation.GetDisplayNode().SetPreferredDisplayRepresentationName3D(slicer.vtkSegmentationConverter.GetSegmentationClosedSurfaceRepresentationName())

    optionExtractCenterlines = int(self._parameterNode.GetParameter(ROLE_OPTION_EXTRACT_CENTERLINES))
    if not optionExtractCenterlines:
        stopTime = time.time()
        durationValue = '%.2f' % (stopTime-startTime)
        message = _("Processing completed in {duration} seconds").format(duration=durationValue)
        logging.info(message)
        slicer.util.showStatusMessage(message, 5000)
        return segmentID

    #---------------------- Extract centerlines ---------------------
    slicer.util.showStatusMessage(_("Extract centerline setup"))
    slicer.app.processEvents()
    ecWidget = slicer.util.getModuleWidget('ExtractCenterline')
    ecUi = ecWidget.ui

    inputSurfaceComboBox = ecUi.inputSurfaceSelector
    inputSegmentSelectorWidget = ecUi.inputSegmentSelectorWidget
    endPointsMarkupsSelector = ecUi.endPointsMarkupsSelector
    outputCenterlineModelSelector = ecUi.outputCenterlineModelSelector
    outputCenterlineCurveSelector = ecUi.outputCenterlineCurveSelector
    preprocessInputSurfaceModelCheckBox = ecUi.preprocessInputSurfaceModelCheckBox
    applyButton = ecUi.applyButton
    outputNetworkGroupBox = ecUi.CollapsibleGroupBox

    """
    On request, fix the segment to a single region if necessary.
    The largest region is then used, the others are often holes we want to get rid of,
    but may be disconnected segmented islands. The final result will not be
    satisfactory, but will mean the study has to be reviewed.
    """
    optionUseLargestRegion = int(self._parameterNode.GetParameter(ROLE_OPTION_USE_LARGEST_REGION))
    if optionUseLargestRegion:
      sm3Logic = slicer.modules.stenosismeasurement3d.logic()
      numberOfRegions = sm3Logic.GetNumberOfRegionsInSegment(segmentation, segmentID)
      if (numberOfRegions > 1):
        kernelSize = self._parameterNode.GetParameter(ROLE_INPUT_KERNEL_SIZE)
        sm3Logic.UpdateSegmentBySmoothClosing(segmentation, segmentID, float(kernelSize))

    # Set input segmentation
    inputSurfaceComboBox.setCurrentNode(segmentation)
    inputSegmentSelectorWidget.setCurrentSegmentID(segmentID)
    # Create 2 fiducial endpoints, at start and end of input curve. We call it output because it is not user input.
    outputFiducialNode = self._parameterNode.GetNodeReference(ROLE_OUTPUT_FIDUCIAL)
    if not outputFiducialNode:
      endpointsName = slicer.mrmlScene.GenerateUniqueName("Endpoints")
      outputFiducialNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", endpointsName)
      firstInputCurveControlPoint = inputCurveNode.GetNthControlPointPositionVector(0)
      outputFiducialNode.AddControlPointWorld(firstInputCurveControlPoint)
      lastInputCurveControlPoint = inputCurveNode.GetNthControlPointPositionVector(curveControlPoints.GetNumberOfPoints() - 1)
      outputFiducialNode.AddControlPointWorld(lastInputCurveControlPoint)
      self._parameterNode.SetNodeReferenceID(ROLE_OUTPUT_FIDUCIAL, outputFiducialNode.GetID())
    endPointsMarkupsSelector.setCurrentNode(outputFiducialNode)

    # Output centerline model. A single node throughout.
    centerlineModel = self._parameterNode.GetNodeReference(ROLE_OUTPUT_CENTERLINE_MODEL)
    if not centerlineModel:
      centerlineModelName = slicer.mrmlScene.GenerateUniqueName("Centerline_model")
      centerlineModel = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", centerlineModelName)
      self._parameterNode.SetNodeReferenceID(ROLE_OUTPUT_CENTERLINE_MODEL, centerlineModel.GetID())
    outputCenterlineModelSelector.setCurrentNode(centerlineModel)

    # Output centerline curve. A single node throughout.
    centerlineCurve = self._parameterNode.GetNodeReference(ROLE_OUTPUT_CENTERLINE_CURVE)
    if not centerlineCurve:
      centerlineCurveName = slicer.mrmlScene.GenerateUniqueName("Centerline_curve")
      centerlineCurve = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsCurveNode", centerlineCurveName)
      self._parameterNode.SetNodeReferenceID(ROLE_OUTPUT_CENTERLINE_CURVE, centerlineCurve.GetID())
    else:
      """
      Avoid this warning:
      Generic Warning: In vtkCurveMeasurementsCalculator.cxx, line 635
      vtkCurveMeasurementsCalculator::InterpolateArray: pedigreeIdsArray contain values between 0 and 27, but there are only 2 values in the input array

      This can be seen on repeat runs when we toggle the largest region option with a created segment of poor quality.
      """
      centerlineCurve.Reset(None)
      centerlineCurve.CreateDefaultDisplayNodes()
    outputCenterlineCurveSelector.setCurrentNode(centerlineCurve)
    """
    Don't preprocess input surface. Decimation error may crash Slicer. Quadric method for decimation is slower but more reliable.
    """
    preprocessInputSurfaceModelCheckBox.setChecked(False)
    # Apply
    applyButton.click()
    # Hide the input curve to show the centerlines
    inputCurveNode.SetDisplayVisibility(False)
    # Close network pane; we don't use this here.
    outputNetworkGroupBox.collapsed = True

    slicer.util.mainWindow().moduleSelector().selectModule('ExtractCenterline')

    stopTime = time.time()
    durationValue = '%.2f' % (stopTime-startTime)
    message = _("Processing completed in {duration} seconds").format(duration=durationValue)
    logging.info(message)
    slicer.util.showStatusMessage(message, 5000)
    return segmentID

#
# GuidedArterySegmentationTest
#

class GuidedArterySegmentationTest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setUp(self) -> None:
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    slicer.mrmlScene.Clear()

  def runTest(self) -> None:
    """Run as few or as many tests as needed here.
    """
    self.setUp()
    self.test_GuidedArterySegmentation1()

  def test_GuidedArterySegmentation1(self) -> None:
    self.delayDisplay(_("Starting the test"))

    self.delayDisplay(_("Test passed"))

ROLE_INPUT_CURVE = "InputCurve"
ROLE_INPUT_SLICE = "InputSlice"
ROLE_INPUT_VOLUME = "InputVolume" # Set in logic
ROLE_INPUT_SHAPE = "InputShape"
ROLE_INPUT_DIAMETER = "InputDiameter"
ROLE_OUTPUT_SEGMENTATION = "OutputSegmentation"
ROLE_OUTPUT_SEGMENT = "OutputSegment" # Set in logic
ROLE_INPUT_INTENSITY_TOLERANCE = "InputIntensityTolerance"
ROLE_INPUT_NEIGHBOURHOOD_SIZE = "InputNeighbourhoodSize"
ROLE_INPUT_KERNEL_SIZE = "InputKernelSize"
ROLE_OPTION_EXTRACT_CENTERLINES = "OptionExtractCenterlines"
ROLE_OUTPUT_CENTERLINE_MODEL = "OutputCenterlineModel" # Set in logic
ROLE_OUTPUT_CENTERLINE_CURVE = "OutputCenterlineCurve" # Set in logic
ROLE_OUTPUT_FIDUCIAL = "OutputFiducial" # Set in logic; 'Extract centerline' endpoints
ROLE_OPTION_USE_LARGEST_REGION = "OptionUseLargestRegion"
ROLE_INITIALIZED = "Initialized"
