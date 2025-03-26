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

from slicer import vtkMRMLVolumeNode

#
# QuickArterySegmentation
#

class QuickArterySegmentation(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Quick artery segmentation"
    self.parent.categories = ["Vascular Modeling Toolkit"]
    self.parent.dependencies = ["ExtractCenterline"]
    self.parent.contributors = ["Saleem Edah-Tally [Surgeon] [Hobbyist developer]", "Andras Lasso (PerkLab)"]
    self.parent.helpText = _("""
This <a href="https://github.com/vmtk/SlicerExtension-VMTK/">module</a> is intended to create a segmentation from a contrast enhanced CT angioscan, and to finally extract centerlines from the surface model.
<br><br>It assumes that data acquisition of the input volume is nearly perfect, and that fiducial points are placed in the contrasted lumen.
<br><br>The 'Flood filling' effect of the '<a href="https://github.com/lassoan/SlicerSegmentEditorExtraEffects">Segment editor extra effects</a>' is used for segmentation.
<br><br>The '<a href="https://github.com/vmtk/SlicerExtension-VMTK/tree/master/ExtractCenterline/">SlicerExtension-VMTK Extract centerline</a>' module is required.
""")
    # TODO: replace with organization, grant and thanks
    self.parent.acknowledgementText = _("""
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
""")

#
# QuickArterySegmentationWidget
#

class QuickArterySegmentationWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/QuickArterySegmentation.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    # Create logic class. Logic implements all computations that should be possible to run
    # in batch mode, without a graphical user interface.
    self.logic = QuickArterySegmentationLogic()
    self.ui.parameterSetSelector.addAttribute("vtkMRMLScriptedModuleNode", "ModuleName", self.moduleName)

    self.ui.floodFillingCollapsibleGroupBox.checked = False
    self.ui.regionInfoLabel.setVisible(False)
    self.ui.fixRegionToolButton.setVisible(False)

    # Connections

    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    # Application connections
    self.ui.inputFiducialSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onFiducialNode)
    self.ui.inputSliceNodeSelector.connect("currentNodeChanged(vtkMRMLNode*)", lambda node: self.onMrmlNodeChanged(ROLE_INPUT_SLICE, node))
    self.ui.inputROISelector.connect("currentNodeChanged(vtkMRMLNode*)", lambda node: self.onMrmlNodeChanged(ROLE_INPUT_ROI, node))
    self.ui.outputSegmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", lambda node: self.onMrmlNodeChanged(ROLE_OUTPUT_SEGMENTATION, node))
    self.ui.intensityToleranceSpinBox.connect("valueChanged(int)", lambda value: self.onSpinBoxChanged(ROLE_INPUT_INTENSITY_TOLERANCE, value))
    self.ui.neighbourhoodSizeDoubleSpinBox.connect("valueChanged(double)", lambda value: self.onSpinBoxChanged(ROLE_INPUT_NEIGHBOURHOOD_SIZE, value))
    self.ui.extractCenterlinesCheckBox.connect("toggled(bool)", lambda checked: self.onBooleanToggled(ROLE_OPTION_EXTRACT_CENTERLINES, checked))

    self.ui.preFitROIToolButton.connect("clicked()", self.preFitROI)
    self.ui.fixRegionToolButton.connect("clicked()", self.replaceSegmentByRegion)

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

    # A hidden one for the curious! For developers.
    shortcut = qt.QShortcut(self.ui.QuickArterySegmentation)
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

  def onFiducialNode(self, node) -> None:
    if not self._parameterNode:
      return
    self.onMrmlNodeChanged(ROLE_INPUT_FIDUCIAL, node) # This functions seems to be called before parameter node gets updated.
    if node is None:
        return
    numberOfControlPoints = node.GetNumberOfControlPoints()
    if numberOfControlPoints < 2:
        self.inform(_("Fiducial node must have at least 2 points."))
        self.ui.inputFiducialSelector.setCurrentNode(None)

  # The ROI will have to be manually adjusted.
  def preFitROI(self) -> None:
    inputFiducialNode = self._parameterNode.GetNodeReference(ROLE_INPUT_FIDUCIAL)
    inputROINode = self._parameterNode.GetNodeReference(ROLE_INPUT_ROI)
    if (inputFiducialNode is None) or (inputROINode is None):
        return
    fiducialBounds = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    inputFiducialNode.GetBounds(fiducialBounds)
    """
    Very often, 2 fiducial points are placed in the same slice view.
    The bounds will then be the same on one axis, and resizing the ROI on this
    axis is not possible.
    Improve ROI resizing by slightly altering the bounds on such an axis.
    """
    for axis in range(0, 6, 2):
      if fiducialBounds[axis] == fiducialBounds[axis + 1]:
        fiducialBounds[axis] -= 5.0
        fiducialBounds[axis + 1] += 5.0
    vFiducialBounds=vtk.vtkBoundingBox()
    vFiducialBounds.SetBounds(fiducialBounds)
    center = [0.0, 0.0, 0.0]
    vFiducialBounds.GetCenter(center)
    inputROINode.SetCenter(center)
    lengths = [0.0, 0.0, 0.0]
    vFiducialBounds.GetLengths(lengths)
    inputROINode.SetRadiusXYZ((lengths[0] / 2, lengths[1] / 2, lengths[2] / 2))
    inputROINode.SetDisplayVisibility(True)

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

    self._parameterNode.SetParameter(ROLE_INPUT_INTENSITY_TOLERANCE, str(100))
    self._parameterNode.SetParameter(ROLE_INPUT_NEIGHBOURHOOD_SIZE, str(2.0))
    self._parameterNode.SetParameter(ROLE_OPTION_EXTRACT_CENTERLINES, str(0))
    self._parameterNode.SetParameter(ROLE_OPTION_USE_LARGEST_REGION, str(1))
    self._parameterNode.SetParameter(ROLE_INITIALIZED, str(1))

  def onApplyButton(self) -> None:
    """
    Run processing when user clicks "Apply" button.
    """
    try:
      inputFiducialNode = self._parameterNode.GetNodeReference(ROLE_INPUT_FIDUCIAL)
      inputSliceNode = self._parameterNode.GetNodeReference(ROLE_INPUT_SLICE)
      inputROINode = self._parameterNode.GetNodeReference(ROLE_INPUT_ROI)
      if inputFiducialNode is None:
        self.inform(_("No input fiducial node specified."))
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
      # We no longer preprocess input surface in 'Extract centerline', to avoid crashes. Force a ROI to reduce computation time.
      if inputROINode is None:
        self.inform(_("No input ROI node specified."))
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

    self.ui.inputFiducialSelector.setCurrentNode(self._parameterNode.GetNodeReference(ROLE_INPUT_FIDUCIAL))
    self.ui.inputSliceNodeSelector.setCurrentNode(self._parameterNode.GetNodeReference(ROLE_INPUT_SLICE))
    self.ui.inputROISelector.setCurrentNode(self._parameterNode.GetNodeReference(ROLE_INPUT_ROI))
    self.ui.outputSegmentationSelector.setCurrentNode(self._parameterNode.GetNodeReference(ROLE_OUTPUT_SEGMENTATION))
    self.ui.intensityToleranceSpinBox.setValue(int(self._parameterNode.GetParameter(ROLE_INPUT_INTENSITY_TOLERANCE)))
    self.ui.neighbourhoodSizeDoubleSpinBox.setValue(float(self._parameterNode.GetParameter(ROLE_INPUT_NEIGHBOURHOOD_SIZE)))
    self.ui.extractCenterlinesCheckBox.setChecked(int(self._parameterNode.GetParameter(ROLE_OPTION_EXTRACT_CENTERLINES)))
    self._useLargestSegmentRegion.setChecked(int(self._parameterNode.GetParameter(ROLE_OPTION_USE_LARGEST_REGION)))

    self._updatingGUIFromParameterNode = False

  # Handy during development
  def removeOutputNodes(self) -> None:
    if not self._parameterNode:
        return

    segmentation = self._parameterNode.GetNodeReference(ROLE_OUTPUT_SEGMENTATION)
    if (segmentation):
      segmentID = self._parameterNode.GetParameter(ROLE_OUTPUT_SEGMENT)
      segment = segmentation.GetSegmentation().GetSegment(segmentID)
      if segment:
        segmentation.GetSegmentation().RemoveSegment(segment)
        self._parameterNode.SetParameter(ROLE_OUTPUT_SEGMENT, "")
    # Remove child centerline curves of self.outputCenterlineCurve
    outputCenterlineCurveNode = self._parameterNode.GetNodeReference(ROLE_OUTPUT_CENTERLINE_CURVE)
    if outputCenterlineCurveNode:
      shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
      outputCurveMainId = shNode.GetItemByDataNode(outputCenterlineCurveNode)
      if (outputCurveMainId > 0) and (outputCurveMainId != shNode.GetSceneItemID()):
        while shNode.GetNumberOfItemChildren(outputCurveMainId):
            outputCurveChildId = shNode.GetItemByPositionUnderParent(outputCurveMainId, 0)
            outputCurveChild = shNode.GetItemDataNode(outputCurveChildId)
            slicer.mrmlScene.RemoveNode(outputCurveChild)
            
      slicer.mrmlScene.RemoveNode(outputCenterlineCurveNode)
      self.onMrmlNodeChanged(ROLE_OUTPUT_CENTERLINE_CURVE, None)

    outputCenterlineModelNode = self._parameterNode.GetNodeReference(ROLE_OUTPUT_CENTERLINE_MODEL)
    if outputCenterlineModelNode:
      slicer.mrmlScene.RemoveNode(outputCenterlineModelNode)
      self.onMrmlNodeChanged(ROLE_OUTPUT_CENTERLINE_MODEL, None)

  def updateRegionInfo(self):
    if not self._parameterNode:
      self.ui.regionInfoLabel.setVisible(False)
      self.ui.fixRegionToolButton.setVisible(False)
      return
    segmentation = self._parameterNode.GetNodeReference(ROLE_OUTPUT_SEGMENTATION)
    segmentID = self._parameterNode.GetParameter(ROLE_OUTPUT_SEGMENT)
    if (not segmentation) or (not segmentID):
      self.inform(_("Invalid segmentation or segmentID."))
      self.ui.regionInfoLabel.setVisible(False)
      self.ui.fixRegionToolButton.setVisible(False)
      return
    
    numberOfRegions = self.logic.getNumberOfRegionsInSegment(segmentation, segmentID)
    if numberOfRegions == 0:
      self.ui.regionInfoLabel.clear()
      self.ui.regionInfoLabel.setVisible(False)
      self.ui.fixRegionToolButton.setVisible(False)
      return
    regionInfo = _("Number of regions in segment: ") + str(numberOfRegions)
    self.ui.regionInfoLabel.setText(regionInfo)
    self.ui.regionInfoLabel.setVisible(True)
    self.ui.fixRegionToolButton.setVisible(numberOfRegions > 1)

  def replaceSegmentByRegion(self):
    if not self._parameterNode:
      return
    segmentation = self._parameterNode.GetNodeReference(ROLE_OUTPUT_SEGMENTATION)
    segmentID = self._parameterNode.GetParameter(ROLE_OUTPUT_SEGMENT)
    if (not segmentation) or (not segmentID):
      self.inform(_("Invalid segmentation or segmentID."))
      self.ui.regionInfoLabel.setVisible(False)
      return
    self.logic.replaceSegmentByLargestRegion(segmentation, segmentID)
    self.updateRegionInfo()
#
# QuickArterySegmentationLogic
#

class QuickArterySegmentationLogic(ScriptedLoadableModuleLogic):
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
    logging.info(_("Processing started"))

    slicer.util.showStatusMessage(_("Segment editor setup"))
    slicer.app.processEvents()

    # Get volume node
    inputSliceNode = self._parameterNode.GetNodeReference(ROLE_INPUT_SLICE)
    sliceWidget = slicer.app.layoutManager().sliceWidget(inputSliceNode.GetName())
    volumeNode = sliceWidget.sliceLogic().GetBackgroundLayer().GetVolumeNode()
    if not volumeNode:
      raise ValueError(_("Background volume node in the selected slice node is None."))
    self._parameterNode.SetNodeReferenceID(ROLE_INPUT_VOLUME, volumeNode.GetID())

    # Create a new segmentation if none is specified.
    segmentation = self._parameterNode.GetNodeReference(ROLE_OUTPUT_SEGMENTATION)
    if not segmentation:
      segmentation = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
      self._parameterNode.SetNodeReferenceID(ROLE_OUTPUT_SEGMENTATION, segmentation.GetID())

    # Create segment editor object if needed.
    segmentEditorModuleWidget = slicer.util.getModuleWidget("SegmentEditor")
    seWidget = segmentEditorModuleWidget.editor

    # Set segment editor controls
    seWidget.setSegmentationNode(segmentation)
    seWidget.setSourceVolumeNode(volumeNode)
    segmentation.SetReferenceImageGeometryParameterFromVolumeNode(volumeNode)

    #---------------------- Manage segment --------------------
    # Remove a segment node and keep its color
    segment = None
    segmentColor = []
    """
    Control the segment ID.
    It will be the same in all segmentations.
    We can reach it precisely.
    """
    inputFiducialNode = self._parameterNode.GetNodeReference(ROLE_INPUT_FIDUCIAL)
    segmentID = "Segment_" + inputFiducialNode.GetID()
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

    #---------------------- Flood filling --------------------
    # Each fiducial point will be a user click.
    # Set parameters
    inputIntensityTolerance = int(self._parameterNode.GetParameter(ROLE_INPUT_INTENSITY_TOLERANCE))
    inputNeighbourhoodSize = float(self._parameterNode.GetParameter(ROLE_INPUT_NEIGHBOURHOOD_SIZE))
    inputROINode = self._parameterNode.GetNodeReference(ROLE_INPUT_ROI)
    seWidget.setActiveEffectByName("Flood filling")
    ffEffect = seWidget.activeEffect()
    ffEffect.setParameter("IntensityTolerance", inputIntensityTolerance)
    ffEffect.setParameter("NeighborhoodSizeMm", inputNeighbourhoodSize)
    ffEffect.parameterSetNode().SetNodeReferenceID("FloodFilling.ROI", inputROINode.GetID() if inputROINode else None)
    ffEffect.updateGUIFromMRML()
    # Reset segment editor masking widgets. Values set by previous work must not interfere here.
    seWidget.mrmlSegmentEditorNode().SetMaskMode(slicer.vtkMRMLSegmentationNode.EditAllowedEverywhere)
    seWidget.mrmlSegmentEditorNode().SourceVolumeIntensityMaskOff()
    seWidget.mrmlSegmentEditorNode().SetOverwriteMode(seWidget.mrmlSegmentEditorNode().OverwriteNone)

    # Apply flood filling at each fiducial point.
    points=vtk.vtkPoints()
    inputFiducialNode.GetControlPointPositionsWorld(points)
    numberOfFiducialControlPoints = points.GetNumberOfPoints()
    for i in range(numberOfFiducialControlPoints):
      # Show progress in status bar. Helpful to wait.
      t = time.time()
      durationValue = '%.2f' % (t-startTime)
      msg = _("Flood filling: {duration} seconds - ").format(duration = durationValue)
      self.showStatusMessage((msg, str(i + 1), "/", str(numberOfFiducialControlPoints)))

      rasPoint = points.GetPoint(i)
      slicer.vtkMRMLSliceNode.JumpSlice(sliceWidget.sliceLogic().GetSliceNode(), *rasPoint)
      point3D = qt.QVector3D(rasPoint[0], rasPoint[1], rasPoint[2])
      point2D = ffEffect.rasToXy(point3D, sliceWidget)
      qIjkPoint = ffEffect.xyToIjk(point2D, sliceWidget, ffEffect.self().getClippedSourceImageData())
      ffEffect.self().floodFillFromPoint((int(qIjkPoint.x()), int(qIjkPoint.y()), int(qIjkPoint.z())))

    # Switch off active effect
    seWidget.setActiveEffect(None)
    # Show segment. Poked from qMRMLSegmentationShow3DButton.cxx
    if segmentation.GetSegmentation().CreateRepresentation(slicer.vtkSegmentationConverter.GetSegmentationClosedSurfaceRepresentationName()):
      segmentation.GetDisplayNode().SetPreferredDisplayRepresentationName3D(slicer.vtkSegmentationConverter.GetSegmentationClosedSurfaceRepresentationName())
    # Hide ROI
    if inputROINode:
      inputROINode.SetDisplayVisibility(False)

    optionExtractCenterlines = int(self._parameterNode.GetParameter(ROLE_OPTION_EXTRACT_CENTERLINES))
    if not optionExtractCenterlines:
      stopTime = time.time()
      durationValue = '%.2f' % (stopTime - startTime)
      message = _("Processing completed in {duration} seconds").format(duration = durationValue)
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

    # On request, fix the segment to a single region if necessary.
    # The largest region is then used, the others are holes we want to get rid of.
    optionUseLargestRegion = int(self._parameterNode.GetParameter(ROLE_OPTION_USE_LARGEST_REGION))
    if optionUseLargestRegion:
      numberOfRegions = self.getNumberOfRegionsInSegment(segmentation, segmentID)
      if (numberOfRegions > 1):
        self.replaceSegmentByLargestRegion(segmentation, segmentID)

    # Set input segmentation and endpoints
    inputSurfaceComboBox.setCurrentNode(segmentation)
    inputSegmentSelectorWidget.setCurrentSegmentID(segmentID)
    endPointsMarkupsSelector.setCurrentNode(inputFiducialNode)

    # Output centerline model. A single node throughout.
    outputCenterlineModelNode = self._parameterNode.GetNodeReference(ROLE_OUTPUT_CENTERLINE_MODEL)
    if not outputCenterlineModelNode:
      centerlineModelName = slicer.mrmlScene.GenerateUniqueName("Centerline_model")
      outputCenterlineModelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", centerlineModelName)
      self._parameterNode.SetNodeReferenceID(ROLE_OUTPUT_CENTERLINE_MODEL, outputCenterlineModelNode.GetID())
    outputCenterlineModelSelector.setCurrentNode(outputCenterlineModelNode)

    # Output centerline curve. A single node throughout.
    outputCenterlineCurveNode = self._parameterNode.GetNodeReference(ROLE_OUTPUT_CENTERLINE_CURVE)
    if not outputCenterlineCurveNode:
      centerlineCurveName = slicer.mrmlScene.GenerateUniqueName("Centerline_curve")
      outputCenterlineCurveNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsCurveNode", centerlineCurveName)
      self._parameterNode.SetNodeReferenceID(ROLE_OUTPUT_CENTERLINE_CURVE, outputCenterlineCurveNode.GetID())
    else:
      # See notes in GuidedArterySegmentation.
      outputCenterlineCurveNode.Reset(None)
      outputCenterlineCurveNode.CreateDefaultDisplayNodes()
    outputCenterlineCurveSelector.setCurrentNode(outputCenterlineCurveNode)

    """
    Don't preprocess input surface. Decimation error may crash Slicer. Quadric method for decimation is slower but more reliable.
    """
    preprocessInputSurfaceModelCheckBox.setChecked(False)
    # Apply
    applyButton.click()
    # Close network pane; we don't use this here.
    outputNetworkGroupBox.collapsed = True

    slicer.util.mainWindow().moduleSelector().selectModule('ExtractCenterline')

    stopTime = time.time()
    duration = '%.2f' % (stopTime - startTime)
    message = _("Processing completed in {duration} seconds").format(duration = durationValue)
    logging.info(message)
    slicer.util.showStatusMessage(message, 5000)
    return segmentID

  def getNumberOfRegionsInSegment(self, segmentation, segmentID):
    if (not segmentation) or (not segmentID):
      raise ValueError(_("Segmentation or segmentID is invalid."))
    if not segmentation.GetSegmentation().GetSegment(segmentID):
      raise ValueError(_("Segment not found in the segmentation."))

    closedSurfacePolyData = vtk.vtkPolyData()
    segmentation.CreateClosedSurfaceRepresentation()
    segmentation.GetClosedSurfaceRepresentation(segmentID, closedSurfacePolyData)
    regionFilter = vtk.vtkPolyDataConnectivityFilter()
    regionFilter.SetInputData(closedSurfacePolyData)
    regionFilter.SetExtractionModeToAllRegions()
    regionFilter.Update()
    return regionFilter.GetNumberOfExtractedRegions()

  def replaceSegmentByLargestRegion(self, segmentation, segmentID):
    if (not segmentation) or (not segmentID):
      raise ValueError(_("Segmentation or segmentID is invalid."))
    if not segmentation.GetSegmentation().GetSegment(segmentID):
      raise ValueError(_("Segment not found in the segmentation."))

    closedSurfacePolyData = vtk.vtkPolyData()
    segmentation.CreateClosedSurfaceRepresentation()
    segmentation.GetClosedSurfaceRepresentation(segmentID, closedSurfacePolyData)
    regionExtrator = vtk.vtkPolyDataConnectivityFilter()
    regionExtrator.SetExtractionModeToLargestRegion()
    regionExtrator.SetInputData(closedSurfacePolyData)
    regionExtrator.Update()

    cleaner = vtk.vtkCleanPolyData()
    cleaner.SetInputConnection(regionExtrator.GetOutputPort())
    cleaner.Update()

    segment = segmentation.GetSegmentation().GetSegment(segmentID)
    segmentName = segment.GetName()
    segmentColour = segment.GetColor()
    segmentation.GetSegmentation().RemoveSegment(segmentID)
    newSegmentID = segmentation.AddSegmentFromClosedSurfaceRepresentation(cleaner.GetOutput(), segmentName, segmentColour, segmentID)
    if newSegmentID != segmentID: # A few years ago, segmentID was being ignored in AddSegmentFromClosedSurfaceRepresentation.
      logging.warning("Mismatch between requested and created segment ids from AddSegmentFromClosedSurfaceRepresentation.")

    return newSegmentID # Must be the same as segmentID.

#
# QuickArterySegmentationTest
#

class QuickArterySegmentationTest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setUp(self):
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    slicer.mrmlScene.Clear()

  def runTest(self):
    """Run as few or as many tests as needed here.
    """
    self.setUp()
    self.test_QuickArterySegmentation1()

  def test_QuickArterySegmentation1(self):

    self.delayDisplay("Starting the test")

    # Test the module logic

    logic = QuickArterySegmentationLogic()

    self.delayDisplay('Test passed')

ROLE_INPUT_FIDUCIAL = "InputFiducial"
ROLE_INPUT_SLICE = "InputSlice"
ROLE_INPUT_VOLUME = "InputVolume" # Set in logic
ROLE_INPUT_ROI = "InputROI"
ROLE_OUTPUT_SEGMENTATION = "OutputSegmentation"
ROLE_OUTPUT_SEGMENT = "OutputSegment" # Set in logic
ROLE_INPUT_INTENSITY_TOLERANCE = "InputIntensityTolerance"
ROLE_INPUT_NEIGHBOURHOOD_SIZE = "InputNeighbourhoodSize"
ROLE_OPTION_EXTRACT_CENTERLINES = "OptionExtractCenterlines"
ROLE_OUTPUT_CENTERLINE_MODEL = "OutputCenterlineModel" # Set in logic
ROLE_OUTPUT_CENTERLINE_CURVE = "OutputCenterlineCurve" # Set in logic
ROLE_OPTION_USE_LARGEST_REGION = "OptionUseLargestRegion"
ROLE_INITIALIZED = "Initialized"
