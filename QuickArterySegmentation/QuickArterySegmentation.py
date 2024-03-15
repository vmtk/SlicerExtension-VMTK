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
    outputCenterlineModelNode: slicer.vtkMRMLModelNode
    outputCenterlineCurveNode: slicer.vtkMRMLMarkupsCurveNode
    

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

    # Connections

    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    # Application connections
    self.ui.inputFiducialSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onFiducialNode)
    self.ui.preFitROIToolButton.connect("clicked()", self.preFitROI)
    self.ui.restoreSliceViewToolButton.connect("clicked()", self.onRestoreSliceViews)

    # Buttons
    self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)

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
    self._parameterNode.inputFiducialNode = node # This functions seems to be called before parameter node gets updated.
    if node is None:
        return
    numberOfControlPoints = node.GetNumberOfControlPoints()
    if numberOfControlPoints < 2:
        self.inform(_("Fiducial node must have at least 2 points."))
        self.ui.inputFiducialSelector.setCurrentNode(None)
        return
    # Update UI with previous referenced segmentation. May be changed before logic.process().
    referencedSegmentationNode = node.GetNodeReference("OutputSegmentation")
    if referencedSegmentationNode:
        self.ui.outputSegmentationSelector.setCurrentNode(node.GetNodeReference("OutputSegmentation"))
    # Show last known volume used for segmentation.
    referencedInputVolume = node.GetNodeReference("InputVolumeNode")
    self.updateSliceViews(referencedInputVolume)
    # Reuse last known parameters
    self.updateGUIParametersFromInputNode(node)

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
    # Don't upset UI if we have the right volume node
    sliceWidget = slicer.app.layoutManager().sliceWidget(sliceNode.GetName())
    backgroudVolumeNode = sliceWidget.sliceLogic().GetBackgroundLayer().GetVolumeNode()
    if volumeNode == backgroudVolumeNode:
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
    # Show last known volume used for segmentation.
    inputFiducialNode = self.ui.inputFiducialSelector.currentNode()
    if not inputFiducialNode:
        return
    referencedInputVolume = inputFiducialNode.GetNodeReference("InputVolumeNode")
    self.updateSliceViews(referencedInputVolume)
  
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

  """
  Let each one trace last used parameter values and output nodes.
  These can be restored when an input fiducial is selected again.
  """
  def UpdateInputNodeWithThisOutputNode(self, outputNode, referenceID) -> None:
    outputNodeID = ""
    if outputNode:
        outputNodeID = outputNode.GetID()
    self._parameterNode.inputFiducialNode.SetNodeReferenceID(referenceID, outputNodeID)
    
  def UpdateInputNodeWithOutputNodes(self) -> None:
    if not self._parameterNode.inputFiducialNode:
        return
    wasModified = self._parameterNode.inputFiducialNode.StartModify()
    self.UpdateInputNodeWithThisOutputNode(self._parameterNode.outputSegmentationNode, "OutputSegmentation")
    self.UpdateInputNodeWithThisOutputNode(self._parameterNode.outputCenterlineModelNode, "OutputCenterlineModel")
    self.UpdateInputNodeWithThisOutputNode(self._parameterNode.outputCenterlineCurveNode, "OutputCenterlineCurve")
    self._parameterNode.inputFiducialNode.EndModify(wasModified)

  def UpdateInputNodeWithParameters(self) -> None:
    if not self._parameterNode.inputFiducialNode:
        return
    wasModified = self._parameterNode.inputFiducialNode.StartModify()
    
    sliceNode = self._parameterNode.inputSliceNode
    sliceWidget = slicer.app.layoutManager().sliceWidget(sliceNode.GetName())
    volumeNode = sliceWidget.sliceLogic().GetBackgroundLayer().GetVolumeNode()
    self._parameterNode.inputFiducialNode.SetNodeReferenceID("InputVolumeNode", volumeNode.GetID())
    
    inputROINodeID = self._parameterNode.inputROINode.GetID()
    self._parameterNode.inputFiducialNode.SetNodeReferenceID("InputROINode", inputROINodeID)
    self._parameterNode.inputFiducialNode.SetAttribute("InputIntensityTolerance", str(self.ui.intensityToleranceSpinBox.value))
    self._parameterNode.inputFiducialNode.SetAttribute("NeighbourhoodSize", str(self.ui.neighbourhoodSizeDoubleSpinBox.value))
    self._parameterNode.inputFiducialNode.EndModify(wasModified)

  # Restore parameters from input fiducial
  def updateGUIParametersFromInputNode(self, node) -> None:
    if not node:
        return
    self.ui.inputROISelector.setCurrentNode(node.GetNodeReference("InputROINode"))
    inputIntensityTolerance = node.GetAttribute("InputIntensityTolerance")
    if inputIntensityTolerance:
        self.ui.intensityToleranceSpinBox.value = int(inputIntensityTolerance)
    inputNeighbourhoodSize = node.GetAttribute("NeighbourhoodSize")
    if inputNeighbourhoodSize:
        self.ui.neighbourhoodSizeDoubleSpinBox.value = float(inputNeighbourhoodSize)
  
  # Restore output nodes in logic
  def UpdateParameterWithOutputNodes(self) -> None:
    if not self._parameterNode.inputFiducialNode:
        return
    # Here we use a segmentation specified in UI, not the one referenced in the input fiducial.
    self._parameterNode.outputSegmentationNode = self.ui.outputSegmentationSelector.currentNode()
    self._parameterNode.outputCenterlineModelNode = self._parameterNode.inputFiducialNode.GetNodeReference("OutputCenterlineModel")
    self._parameterNode.outputCenterlineCurveNode = self._parameterNode.inputFiducialNode.GetNodeReference("OutputCenterlineCurve")
    
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
        sliceNode = self._parameterNode.inputSliceNode
        sliceWidget = slicer.app.layoutManager().sliceWidget(sliceNode.GetName())
        volumeNode = sliceWidget.sliceLogic().GetBackgroundLayer().GetVolumeNode()
        if volumeNode is None:
            self.inform(_("No volume node selected in input slice node."))
            return
        # We no longer preprocess input surface in 'Extract centerline', to avoid crashes. Force a ROI to reduce computation time.
        if self._parameterNode.inputROINode is None:
            self.inform(_("No input ROI node specified."))
            return
        # Restore logic output objects relevant to the input fiducial.
        self.UpdateParameterWithOutputNodes()
        # Compute output
        self.logic.process()
        # Update input node with references to new output nodes.
        self.UpdateInputNodeWithOutputNodes()
        # Update input node with input parameters.
        self.UpdateInputNodeWithParameters()
        # Update segmentation selector if it was none
        self.ui.outputSegmentationSelector.setCurrentNode(self._parameterNode.outputSegmentationNode)

    except Exception as e:
        slicer.util.errorDisplay(_("Failed to compute results: ") + str(e))
        import traceback
        traceback.print_exc()

  # Handy during development
  def removeOutputNodes(self) -> None:
    inputFiducialNode = self.ui.inputFiducialSelector.currentNode()
    if not inputFiducialNode:
        return
    # Remove segment, ID is controlled.
    segmentID = "Segment_" + inputFiducialNode.GetID()
    segmentation = self._parameterNode.outputSegmentationNode
    segment = segmentation.GetSegmentation().GetSegment(segmentID)
    if segment:
        segmentation.GetSegmentation().RemoveSegment(segment)
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
    # Remove node references to centerlines
    self.UpdateInputNodeWithOutputNodes()
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
    self.segmentEditorWidgets = None
    self.extractCenterlineWidgets = None

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
    """
    Find segment editor widgets.
    Use a dedicated class to store widget references once only.
    Not reasonable to dig through the UI on every run.
    """
    if not self.segmentEditorWidgets:
        self.segmentEditorWidgets = SegmentEditorWidgets()
        self.segmentEditorWidgets.findWidgets()
    # Create a new segmentation if none is specified.
    if not self._parameterNode.outputSegmentationNode:
        segmentation=slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
        self._parameterNode.outputSegmentationNode = segmentation
    else:
        # Prefer a local reference for readability
        segmentation = self._parameterNode.outputSegmentationNode
        
    # Local direct reference to slicer.modules.SegmentEditorWidget.editor
    seWidgetEditor=self.segmentEditorWidgets.widgetEditor

    # Get volume node
    sliceWidget = slicer.app.layoutManager().sliceWidget(self._parameterNode.inputSliceNode.GetName())
    volumeNode = sliceWidget.sliceLogic().GetBackgroundLayer().GetVolumeNode()
    
    # Set segment editor controls
    seWidgetEditor.setSegmentationNode(segmentation)
    seWidgetEditor.setSourceVolumeNode(volumeNode)
    
    # Go to Segment Editor.
    mainWindow = slicer.util.mainWindow()
    mainWindow.moduleSelector().selectModule('SegmentEditor')
    
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
    seWidgetEditor.setCurrentSegmentID(segmentID)
    
    #---------------------- Flood filling --------------------
    # Each fiducial point will be a user click.
    # Set parameters
    seWidgetEditor.setActiveEffectByName("Flood filling")
    ffEffect = seWidgetEditor.activeEffect()
    ffEffect.setParameter("IntensityTolerance", self._parameterNode.inputIntensityTolerance)
    ffEffect.setParameter("NeighborhoodSizeMm", self._parameterNode.inputNeighbourhoodSize)
    ffEffect.parameterSetNode().SetNodeReferenceID("FloodFilling.ROI", self._parameterNode.inputROINode.GetID() if self._parameterNode.inputROINode else None)
    ffEffect.updateGUIFromMRML()
    # Reset segment editor masking widgets. Values set by previous work must not interfere here.
    self.segmentEditorWidgets.setMaskingOptionsToAllowOverlap()
    
    # Apply flood filling at each fiducial point.
    points=vtk.vtkPoints()
    self._parameterNode.inputFiducialNode.GetControlPointPositionsWorld(points)
    numberOfFiducialControlPoints = points.GetNumberOfPoints()
    for i in range(numberOfFiducialControlPoints):
        # Show progress in status bar. Helpful to wait.
        t = time.time()
        durationValue = '%.2f' % (t-startTime)
        msg = _("Flood filling : {duration} seconds - ").format(duration = durationValue)
        self.showStatusMessage((msg, str(i + 1), "/", str(numberOfFiducialControlPoints)))
        
        rasPoint = points.GetPoint(i)
        slicer.vtkMRMLSliceNode.JumpSlice(sliceWidget.sliceLogic().GetSliceNode(), *rasPoint)
        point3D = qt.QVector3D(rasPoint[0], rasPoint[1], rasPoint[2])
        point2D = ffEffect.rasToXy(point3D, sliceWidget)
        qIjkPoint = ffEffect.xyToIjk(point2D, sliceWidget, ffEffect.self().getClippedSourceImageData())
        ffEffect.self().floodFillFromPoint((int(qIjkPoint.x()), int(qIjkPoint.y()), int(qIjkPoint.z())))
    
    # Switch off active effect
    seWidgetEditor.setActiveEffect(None)
    # Show segment
    show3DctkMenuButton = self.segmentEditorWidgets.show3DctkMenuButton
    # Don't use click() here, smoothing options make a mess.
    show3DctkMenuButton.setChecked(True)
    # Hide ROI
    if self._parameterNode.inputROINode:
        self._parameterNode.inputROINode.SetDisplayVisibility(False)
    
    if not self._parameterNode.optionExtractCenterlines:
        stopTime = time.time()
        durationValue = '%.2f' % (stopTime - startTime)
        message = _("Processing completed in {duration} seconds").format(duration = durationValue)
        logging.info(message)
        slicer.util.showStatusMessage(message, 5000)
        return
    
    #---------------------- Extract centerlines ---------------------
    slicer.util.showStatusMessage(_("Extract centerline setup"))
    slicer.app.processEvents()
    mainWindow.moduleSelector().selectModule('ExtractCenterline')
    if not self.extractCenterlineWidgets:
        self.extractCenterlineWidgets = ExtractCenterlineWidgets()
        self.extractCenterlineWidgets.findWidgets()
    
    inputSurfaceComboBox = self.extractCenterlineWidgets.inputSurfaceComboBox
    inputSegmentSelectorWidget = self.extractCenterlineWidgets.inputSegmentSelectorWidget
    endPointsMarkupsSelector = self.extractCenterlineWidgets.endPointsMarkupsSelector
    outputCenterlineModelSelector = self.extractCenterlineWidgets.outputCenterlineModelSelector
    outputCenterlineCurveSelector = self.extractCenterlineWidgets.outputCenterlineCurveSelector
    preprocessInputSurfaceModelCheckBox = self.extractCenterlineWidgets.preprocessInputSurfaceModelCheckBox
    applyButton = self.extractCenterlineWidgets.applyButton
    
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
    self.extractCenterlineWidgets.outputNetworkGroupBox.collapsed = True
    
    stopTime = time.time()
    duration = '%.2f' % (stopTime - startTime)
    message = _("Processing completed in {duration} seconds").format(duration = durationValue)
    logging.info(message)
    slicer.util.showStatusMessage(message, 5000)

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

"""
Weird and unusual approach to remote control modules, but very efficient.
Get reference to widgets exposed by an API.
Widgets can be removed, or their names may change.
That's true for library interfaces also.
"""
class SegmentEditorWidgets(ScriptedLoadableModule):
    def __init__(self):
        self.widgetEditor = None
        self.segmentationNodeComboBox = None
        self.sourceVolumeNodeComboBox = None
        self.newSegmentQPushButton = None
        self.removeSegmentQPushButton = None
        self.show3DctkMenuButton = None
        self.maskingGroupBox = None
        self.maskModeComboBox = None
        self.sourceVolumeIntensityMaskCheckBox = None
        self.sourceVolumeIntensityMaskRangeWidget = None
        self.overwriteModeComboBox = None
    
    # Find widgets we are using only
    def findWidgets(self):
        # Create slicer.modules.SegmentEditorWidget
        slicer.modules.segmenteditor.widgetRepresentation()
        self.widgetEditor = slicer.modules.SegmentEditorWidget.editor
        
        # widgetEditor.children()
        # Get segment editor controls and set values
        self.segmentationNodeComboBox = self.widgetEditor.findChild(slicer.qMRMLNodeComboBox, "SegmentationNodeComboBox")
        self.sourceVolumeNodeComboBox = self.widgetEditor.findChild(slicer.qMRMLNodeComboBox, "SourceVolumeNodeComboBox")
        self.newSegmentQPushButton = self.widgetEditor.findChild(qt.QPushButton, "AddSegmentButton")
        self.removeSegmentQPushButton = self.widgetEditor.findChild(qt.QPushButton, "RemoveSegmentButton")
        self.show3DctkMenuButton = self.widgetEditor.findChild(ctk.ctkMenuButton, "Show3DButton")
        
        # Get segment editor masking groupbox and its widgets
        self.maskingGroupBox = self.widgetEditor.findChild(qt.QGroupBox, "MaskingGroupBox")
        self.maskModeComboBox = self.maskingGroupBox.findChild(qt.QComboBox, "MaskModeComboBox")
        self.sourceVolumeIntensityMaskCheckBox = self.maskingGroupBox.findChild(ctk.ctkCheckBox, "SourceVolumeIntensityMaskCheckBox")
        self.sourceVolumeIntensityMaskRangeWidget = self.maskingGroupBox.findChild(ctk.ctkRangeWidget, "SourceVolumeIntensityMaskRangeWidget")
        self.overwriteModeComboBox = self.maskingGroupBox.findChild(qt.QComboBox, "OverwriteModeComboBox")

    """
    findWidgets() must have been called first.
    Must be called when the first used effect is activated.
    """
    def setMaskingOptionsToAllowOverlap(self):
        self.widgetEditor.mrmlSegmentEditorNode().SetMaskMode(slicer.vtkMRMLSegmentationNode.EditAllowedEverywhere)
        self.widgetEditor.mrmlSegmentEditorNode().SourceVolumeIntensityMaskOff()
        self.widgetEditor.mrmlSegmentEditorNode().SetOverwriteMode(self.widgetEditor.mrmlSegmentEditorNode().OverwriteNone)

class ExtractCenterlineWidgets(ScriptedLoadableModule):
    def __init__(self):
        self.mainContainer = None
        self.inputCollapsibleButton = None
        self.outputCollapsibleButton = None
        self.advancedCollapsibleButton = None
        self.applyButton = None
        self.inputSurfaceComboBox = None
        self.endPointsMarkupsSelector = None
        self.inputSegmentSelectorWidget = None
        self.outputNetworkGroupBox = None
        self.outputTreeGroupBox = None
        self.outputCenterlineModelSelector = None
        self.outputCenterlineCurveSelector = None
        self.preprocessInputSurfaceModelCheckBox = None
    
    def findWidgets(self):
        ecWidgetRepresentation = slicer.modules.extractcenterline.widgetRepresentation()
        
        # Containers
        self.mainContainer = ecWidgetRepresentation.findChild(slicer.qMRMLWidget, "ExtractCenterline")
        self.inputCollapsibleButton = self.mainContainer.findChild(ctk.ctkCollapsibleButton, "inputsCollapsibleButton")
        self.outputCollapsibleButton = self.mainContainer.findChild(ctk.ctkCollapsibleButton, "outputsCollapsibleButton")
        self.advancedCollapsibleButton = self.mainContainer.findChild(ctk.ctkCollapsibleButton, "advancedCollapsibleButton")
        self.applyButton = self.mainContainer.findChild(qt.QPushButton, "applyButton")
        
        # Input widgets
        self.inputSurfaceComboBox = self.inputCollapsibleButton.findChild(slicer.qMRMLNodeComboBox, "inputSurfaceSelector")
        self.endPointsMarkupsSelector = self.inputCollapsibleButton.findChild(slicer.qMRMLNodeComboBox, "endPointsMarkupsSelector")
        self.inputSegmentSelectorWidget = self.inputCollapsibleButton.findChild(slicer.qMRMLSegmentSelectorWidget, "inputSegmentSelectorWidget")
        
        # Output widgets
        self.outputNetworkGroupBox = self.outputCollapsibleButton.findChild(ctk.ctkCollapsibleGroupBox, "CollapsibleGroupBox")
        self.outputTreeGroupBox = self.outputCollapsibleButton.findChild(ctk.ctkCollapsibleGroupBox, "CollapsibleGroupBox_2")
        self.outputCenterlineModelSelector = self.outputTreeGroupBox.findChild(slicer.qMRMLNodeComboBox, "outputCenterlineModelSelector")
        self.outputCenterlineCurveSelector = self.outputTreeGroupBox.findChild(slicer.qMRMLNodeComboBox, "outputCenterlineCurveSelector")
        
        # Advanced widgets
        self.preprocessInputSurfaceModelCheckBox = self.advancedCollapsibleButton.findChild(qt.QCheckBox, "preprocessInputSurfaceModelCheckBox")
        
