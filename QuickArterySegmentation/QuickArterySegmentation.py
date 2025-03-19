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
# QuickArterySegmentationParameterNode
#

@parameterNodeWrapper
class QuickArterySegmentationParameterNode:
    inputFiducialNode: slicer.vtkMRMLMarkupsFiducialNode
    inputSliceNode: slicer.vtkMRMLSliceNode
    inputROINode: slicer.vtkMRMLMarkupsROINode
    inputIntensityTolerance: int = 100
    inputNeighbourhoodSize: float = 2.0
    optionExtractCenterlines: bool = False
    outputSegmentationNode: slicer.vtkMRMLSegmentationNode
    # These do not have widget counterparts.
    inputVolumeNode: slicer.vtkMRMLVolumeNode
    outputCenterlineModelNode: slicer.vtkMRMLModelNode
    outputCenterlineCurveNode: slicer.vtkMRMLMarkupsCurveNode
    outputSegmentID: str = ""
    optionUseLargestSegmentRegion: bool = True

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
    self._parameterNodeGuiTag = None
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

    self.ui.floodFillingCollapsibleGroupBox.checked = False
    self.ui.regionInfoLabel.setVisible(False)
    self.ui.fixRegionToolButton.setVisible(False)

    # Connections

    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    # Application connections
    self.ui.inputFiducialSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onFiducialNode)
    self.ui.inputSliceNodeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSliceNode)
    self.ui.outputSegmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSegmentationNode)
    self.ui.preFitROIToolButton.connect("clicked()", self.preFitROI)
    self.ui.fixRegionToolButton.connect("clicked()", self.replaceSegmentByRegion)
    self.ui.restoreSliceViewToolButton.connect("clicked()", self.onRestoreSliceViews)

    self.ui.applyButton.menu().clear()
    self._useLargestSegmentRegion = qt.QAction(_("Use the largest region of the segment"))
    self._useLargestSegmentRegion.setCheckable(True)
    self._useLargestSegmentRegion.setChecked(True)
    self.ui.applyButton.menu().addAction(self._useLargestSegmentRegion)

    # Buttons
    self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)
    self._useLargestSegmentRegion.connect("toggled(bool)", self.onUseLargestSegmentRegionToggled)

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
    numberOfControlPoints = node.GetNumberOfControlPoints()
    if numberOfControlPoints < 2:
        self.inform(_("Fiducial node must have at least 2 points."))
        self.ui.inputFiducialSelector.setCurrentNode(None)

  def onSliceNode(self, node):
    self.ui.regionInfoLabel.setVisible(False)
    self.ui.fixRegionToolButton.setVisible(False)
    if not self._parameterNode:
      return
    """
    Unless we do that, this function gets called twice,
    with node being None the second time, if inputVolume is set.
    This is seen with a qMRMLNodeComboBox handling vtkMRMLSliceNode only.
    """
    self._parameterNode.parameterNode.DisableModifiedEventOn()
    if node:
      sliceWidget = slicer.app.layoutManager().sliceWidget(node.GetName())
      backgroudVolumeNode = sliceWidget.sliceLogic().GetBackgroundLayer().GetVolumeNode()
      self._parameterNode.inputVolumeNode = backgroudVolumeNode
    else:
      self._parameterNode.inputVolumeNode = None
    self._parameterNode.parameterNode.DisableModifiedEventOff()

  def onSegmentationNode(self, node):
    self.ui.regionInfoLabel.setVisible(False)
    self.ui.fixRegionToolButton.setVisible(False)

  # The ROI will have to be manually adjusted.
  def preFitROI(self) -> None:
    inputFiducialNode = self.ui.inputFiducialSelector.currentNode()
    inputROINode = self.ui.inputROISelector.currentNode()
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

  def updateSliceViews(self, volumeNode) -> None:
    # Don't allow None node, is very annoying.
    if not volumeNode:
        return
    sliceNode = self._parameterNode.inputSliceNode
    if not sliceNode:
        return

    views = slicer.app.layoutManager().sliceViewNames()
    for view in views:
        sliceWidget = slicer.app.layoutManager().sliceWidget(view)
        sliceCompositeNode = sliceWidget.sliceLogic().GetSliceCompositeNode()
        if volumeNode is not None:
            sliceCompositeNode.SetBackgroundVolumeID(volumeNode.GetID())
            sliceWidget.sliceLogic().FitSliceToAll()
        else:
            sliceCompositeNode.SetBackgroundVolumeID(None)

  def onRestoreSliceViews(self) -> None:
    self.updateSliceViews(self._parameterNode.inputVolumeNode)

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
    self.logic.initMemberVariables()
    if self.parent.isEntered:
      self.initializeParameterNode()

  def initializeParameterNode(self) -> None:
    """
    Ensure parameter node exists and observed.
    """
    # Parameter node stores all user choices in parameter values, node selections, etc.
    # so that when the scene is saved and reloaded, these settings are restored.

    self.setParameterNode(self.logic.getParameterNode())

  def setParameterNode(self, inputParameterNode) -> None:
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
    """
    Run processing when user clicks "Apply" button.
    """
    try:
        if self._parameterNode.inputFiducialNode is None:
            self.inform(_("No input fiducial node specified."))
            return
        if self._parameterNode.inputSliceNode is None:
            self.inform(_("No input slice node specified."))
            return
        # Ensure there's a background volume node.
        if self._parameterNode.inputVolumeNode is None:
            self.inform(_("Unknown volume node."))
            return
        self.onRestoreSliceViews()
        # We no longer preprocess input surface in 'Extract centerline', to avoid crashes. Force a ROI to reduce computation time.
        if self._parameterNode.inputROINode is None:
            self.inform(_("No input ROI node specified."))
            return
        # Compute output
        self.logic.process()
        # Update segmentation selector if it was none
        self.ui.outputSegmentationSelector.setCurrentNode(self._parameterNode.outputSegmentationNode)
        # Inform about the number of regions in the output segment.
        self.updateRegionInfo()

    except Exception as e:
        slicer.util.errorDisplay(_("Failed to compute results: ") + str(e))
        import traceback
        traceback.print_exc()

  def onUseLargestSegmentRegionToggled(self, checked):
    self._parameterNode.optionUseLargestSegmentRegion = checked

  # Handy during development
  def removeOutputNodes(self) -> None:
    segmentation = self._parameterNode.outputSegmentationNode
    if segmentation:
      segment = segmentation.GetSegmentation().GetSegment(self._parameterNode.outputSegmentID)
      if segment:
          segmentation.GetSegmentation().RemoveSegment(segment)
          self._parameterNode.outputSegmentID = ""
    # Remove child centerline curves of self.outputCenterlineCurve
    shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
    outputCurveMainId = shNode.GetItemByDataNode(self._parameterNode.outputCenterlineCurveNode)
    if (outputCurveMainId > 0) and (outputCurveMainId != shNode.GetSceneItemID()):
        while shNode.GetNumberOfItemChildren(outputCurveMainId):
            outputCurveChildId = shNode.GetItemByPositionUnderParent(outputCurveMainId, 0)
            outputCurveChild = shNode.GetItemDataNode(outputCurveChildId)
            slicer.mrmlScene.RemoveNode(outputCurveChild)

    slicer.mrmlScene.RemoveNode(self._parameterNode.outputCenterlineModelNode)
    slicer.mrmlScene.RemoveNode(self._parameterNode.outputCenterlineCurveNode)
    self._parameterNode.outputCenterlineModelNode = None
    self._parameterNode.outputCenterlineCurveNode = None

  def updateRegionInfo(self):
    if not self._parameterNode:
      self.ui.regionInfoLabel.setVisible(False)
      self.ui.fixRegionToolButton.setVisible(False)
      return
    segmentation = self._parameterNode.outputSegmentationNode
    segmentID = self._parameterNode.outputSegmentID
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
    segmentation = self._parameterNode.outputSegmentationNode
    segmentID = self._parameterNode.outputSegmentID
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
    self.initMemberVariables()

  def getParameterNode(self):
    return self._parameterNode

  def initMemberVariables(self) -> None:
    self._parameterNode = QuickArterySegmentationParameterNode(super().getParameterNode())

  def showStatusMessage(self, messages) -> None:
    separator = " "
    msg = separator.join(messages)
    slicer.util.showStatusMessage(msg, 3000)
    slicer.app.processEvents()

  def process(self) -> None:
    import time
    startTime = time.time()
    logging.info(_("Processing started"))

    slicer.util.showStatusMessage(_("Segment editor setup"))
    slicer.app.processEvents()

    # Create a new segmentation if none is specified.
    if not self._parameterNode.outputSegmentationNode:
        segmentation=slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
        self._parameterNode.outputSegmentationNode = segmentation
    else:
        # Prefer a local reference for readability
        segmentation = self._parameterNode.outputSegmentationNode

    # Create segment editor object if needed.
    segmentEditorModuleWidget = slicer.util.getModuleWidget("SegmentEditor")
    seWidget = segmentEditorModuleWidget.editor

    # Get volume node
    sliceWidget = slicer.app.layoutManager().sliceWidget(self._parameterNode.inputSliceNode.GetName())
    volumeNode = sliceWidget.sliceLogic().GetBackgroundLayer().GetVolumeNode()

    # Set segment editor controls
    seWidget.setSegmentationNode(segmentation)
    seWidget.setSourceVolumeNode(volumeNode)

    #---------------------- Manage segment --------------------
    # Remove a segment node and keep its color
    segment = None
    segmentColor = []
    """
    Control the segment ID.
    It will be the same in all segmentations.
    We can reach it precisely.
    """
    segmentID = "Segment_" + self._parameterNode.inputFiducialNode.GetID()
    self._parameterNode.outputSegmentID = segmentID
    segment = segmentation.GetSegmentation().GetSegment(segmentID)
    if segment:
        segmentColor = segment.GetColor()
        segmentation.GetSegmentation().RemoveSegment(segment)

    # Add a new segment, with controlled ID and known color.
    object = segmentation.GetSegmentation().AddEmptySegment(segmentID)
    segment = segmentation.GetSegmentation().GetSegment(object)
    # Visually identify the segment by the input fiducial name
    segmentName = "Segment_" + self._parameterNode.inputFiducialNode.GetName()
    segment.SetName(segmentName)
    if len(segmentColor):
        segment.SetColor(segmentColor)
    # Select new segment
    seWidget.setCurrentSegmentID(segmentID)

    #---------------------- Flood filling --------------------
    # Each fiducial point will be a user click.
    # Set parameters
    seWidget.setActiveEffectByName("Flood filling")
    ffEffect = seWidget.activeEffect()
    ffEffect.setParameter("IntensityTolerance", self._parameterNode.inputIntensityTolerance)
    ffEffect.setParameter("NeighborhoodSizeMm", self._parameterNode.inputNeighbourhoodSize)
    ffEffect.parameterSetNode().SetNodeReferenceID("FloodFilling.ROI", self._parameterNode.inputROINode.GetID() if self._parameterNode.inputROINode else None)
    ffEffect.updateGUIFromMRML()
    # Reset segment editor masking widgets. Values set by previous work must not interfere here.
    seWidget.mrmlSegmentEditorNode().SetMaskMode(slicer.vtkMRMLSegmentationNode.EditAllowedEverywhere)
    seWidget.mrmlSegmentEditorNode().SourceVolumeIntensityMaskOff()
    seWidget.mrmlSegmentEditorNode().SetOverwriteMode(seWidget.mrmlSegmentEditorNode().OverwriteNone)

    # Apply flood filling at each fiducial point.
    points=vtk.vtkPoints()
    self._parameterNode.inputFiducialNode.GetControlPointPositionsWorld(points)
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
    if self._parameterNode.inputROINode:
        self._parameterNode.inputROINode.SetDisplayVisibility(False)

    if not self._parameterNode.optionExtractCenterlines:
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
    if self._parameterNode.optionUseLargestSegmentRegion:
      numberOfRegions = self.getNumberOfRegionsInSegment(segmentation, segmentID)
      if (numberOfRegions > 1):
        self.replaceSegmentByLargestRegion(segmentation, segmentID)

    # Set input segmentation and endpoints
    inputSurfaceComboBox.setCurrentNode(segmentation)
    inputSegmentSelectorWidget.setCurrentSegmentID(segmentID)
    endPointsMarkupsSelector.setCurrentNode(self._parameterNode.inputFiducialNode)

    # Output centerline model. A single node throughout.
    if not self._parameterNode.outputCenterlineModelNode:
        self._parameterNode.outputCenterlineModelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode")
        # Visually identify the segment by the input fiducial name
        self._parameterNode.outputCenterlineModelNode.SetName("Centerline_model_" + self._parameterNode.inputFiducialNode.GetName())
    # Account for rename
    self._parameterNode.outputCenterlineModelNode.SetName("Centerline_model_" + self._parameterNode.inputFiducialNode.GetName())
    outputCenterlineModelSelector.setCurrentNode(self._parameterNode.outputCenterlineModelNode)

    # Output centerline curve. A single node throughout.
    centerlineCurve = self._parameterNode.outputCenterlineCurveNode
    if not self._parameterNode.outputCenterlineCurveNode:
        self._parameterNode.outputCenterlineCurveNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsCurveNode")
        # Visually identify the segment by the input fiducial name
        self._parameterNode.outputCenterlineCurveNode.SetName("Centerline_curve_" + self._parameterNode.inputFiducialNode.GetName())
    # Account for rename
    self._parameterNode.outputCenterlineCurveNode.SetName("Centerline_curve_" + self._parameterNode.inputFiducialNode.GetName())
    outputCenterlineCurveSelector.setCurrentNode(self._parameterNode.outputCenterlineCurveNode)

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
