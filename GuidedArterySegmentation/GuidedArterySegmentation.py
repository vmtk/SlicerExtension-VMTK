import os
import unittest
import logging
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

#
# GuidedArterySegmentation
#

class GuidedArterySegmentation(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Guided artery segmentation"
    self.parent.categories = ["Vascular Modeling Toolkit"]
    # NOTE: This is a workaround. DrawTube and FloodFilling are not part of
    # Slicer, but are hosted in an external repository. During testing they are
    # not going to be preseent in the environment, so we don't consider them as
    # dependencies when called by testing. Generic tests are called with no main
    # window; a fingerprint for this is the absence of layout manager.
    if slicer.app.layoutManager() is None:
      self.parent.dependencies = ["ExtractCenterline"]
    else:
      self.parent.dependencies = ["SegmentEditorDrawTube","SegmentEditorFloodFilling","ExtractCenterline"]
    self.parent.contributors = ["Saleem Edah-Tally [Surgeon] [Hobbyist developer]"]
    self.parent.helpText = """
This <a href="https://github.com/vmtk/SlicerExtension-VMTK/">module</a> is intended to create a segmentation from a contrast enhanced CT angioscan, and to finally extract centerlines from the surface model.
<br><br>It assumes that curve control points are placed in the contrasted lumen.
<br><br>The 'Flood filling' and 'Split volume' effects of the '<a href="https://github.com/lassoan/SlicerSegmentEditorExtraEffects">Segment editor extra effects</a>' are used.
<br><br>The '<a href="https://github.com/vmtk/SlicerExtension-VMTK/tree/master/ExtractCenterline/">SlicerExtension-VMTK Extract centerline</a>' module is required.
"""
    # TODO: replace with organization, grant and thanks
    self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
"""

#
# GuidedArterySegmentationWidget
#

class GuidedArterySegmentationWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent=None):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.__init__(self, parent)
    VTKObservationMixin.__init__(self)  # needed for parameter node observation
    self.logic = None
    self._parameterNode = None
    self._updatingGUIFromParameterNode = False

  def setup(self):
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

    self.ui.floodFillingCollapsibleGroupBox.checked = False
    
    # Connections

    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
    # (in the selected parameter node).
    self.ui.inputCurveSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.inputSliceNodeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.tubeDiameterSpinBox.connect("valueChanged(double)", self.updateParameterNodeFromGUI)
    self.ui.intensityToleranceSpinBox.connect("valueChanged(int)", self.updateParameterNodeFromGUI)
    self.ui.neighbourhoodSizeDoubleSpinBox.connect("valueChanged(double)", self.updateParameterNodeFromGUI)
    self.ui.extractCenterlinesCheckBox.connect("toggled(bool)", self.updateParameterNodeFromGUI)
    
    # Application connections
    self.ui.inputCurveSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onCurveNode)
    self.ui.inputSliceNodeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSliceNode)
    self.ui.tubeDiameterSpinBox.connect("valueChanged(double)", self.logic.setTubeDiameter)
    self.ui.intensityToleranceSpinBox.connect("valueChanged(int)", self.logic.setIntensityTolerance)
    self.ui.neighbourhoodSizeDoubleSpinBox.connect("valueChanged(double)", self.logic.setNeighbourhoodSize)
    self.ui.extractCenterlinesCheckBox.connect("toggled(bool)", self.logic.setExtractCenterlines)
    self.ui.restoreSliceViewToolButton.connect("clicked()", self.onRestoreSliceViews)

    # Buttons
    self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)

    # Make sure parameter node is initialized (needed for module reload)
    self.initializeParameterNode()
    
    # A hidden one for the curious !
    shortcut = qt.QShortcut(self.ui.GuidedArterySegmentation)
    shortcut.setKey(qt.QKeySequence('Meta+d'))
    shortcut.connect( 'activated()', lambda: self.removeOutputNodes())
    
    self.installExtensionFromServer("SegmentEditorExtraEffects")
    
  def installExtensionFromServer(self, extensionName):
    # From Modules/Scripted/ExtensionWizard/ExtensionWizardLib/LoadModulesDialog.py
    developerModeEnabled = slicer.util.settingsValue('Developer/DeveloperMode', False, converter=slicer.util.toBool)
    # https://slicer.readthedocs.io/en/latest/developer_guide/script_repository.html#download-and-install-extension
    em = slicer.app.extensionsManagerModel()
    if not em.isExtensionInstalled(extensionName):
      # Don't disturb the developers.
      if developerModeEnabled:
        raise ValueError(f"Aborting installation of {extensionName} in developer mode.")
      
      em.interactive = False
      result = em.updateExtensionsMetadataFromServer(True, True)
      if (not result):
        raise ValueError(f"Could not update metadata from server to install {extensionName}.")
      
      reply = slicer.util.confirmYesNoDisplay(f"{extensionName} must be installed. Do you want to install it now ?")
      if (not reply):
        raise ValueError(f"This module cannot be used without {extensionName}.")
      
      if not em.downloadAndInstallExtensionByName(extensionName, True, True):
        raise ValueError(f"Failed to install {extensionName} extension.")
      
      reply = slicer.util.confirmYesNoDisplay(f"{extensionName} has been installed from server.\n\nSlicer must be restarted. Do you want to restart now ?")
      if reply:
        slicer.util.restart()

  def inform(self, message):
    slicer.util.showStatusMessage(message, 3000)
    logging.info(message)

  def onCurveNode(self, node):
    if node is None:
        self.logic.setInputCurveNode(None)
        return
    numberOfControlPoints = node.GetNumberOfControlPoints()
    if numberOfControlPoints < 2: # Possible ?
        self.inform("Curve node must have at least 2 points.")
        self.ui.inputCurveSelector.setCurrentNode(None)
        self.logic.setInputCurveNode(None)
        return
    self.logic.setInputCurveNode(node)
    # Update UI with previous referenced segmentation. May be changed before logic.process().
    referencedSegmentationNode = node.GetNodeReference("OutputSegmentation")
    if referencedSegmentationNode:
        self.ui.outputSegmentationSelector.setCurrentNode(referencedSegmentationNode)
    # Show last known volume used for segmentation.
    referencedInputVolume = node.GetNodeReference("InputVolumeNode")
    self.updateSliceViews(referencedInputVolume)
    # Reuse last known parameters
    self.updateGUIParametersFromInputNode()
  
  def onSliceNode(self, node):
    if node is None:
        self.logic.setInputSliceNode(None)
        return
    self.logic.setInputSliceNode(node)

  def updateSliceViews(self, node):
    # Don't allow None node, is very annoying.
    if not node:
        return
    sliceNode = self.logic.inputSliceNode
    if not sliceNode:
        return
    # Don't upset UI if we have the right volume node
    sliceWidget = slicer.app.layoutManager().sliceWidget(sliceNode.GetName())
    volumeNode = sliceWidget.sliceLogic().GetBackgroundLayer().GetVolumeNode()
    if node == volumeNode:
        return
    views = slicer.app.layoutManager().sliceViewNames()
    for view in views:
        sliceWidget = slicer.app.layoutManager().sliceWidget(view)
        sliceCompositeNode = sliceWidget.sliceLogic().GetSliceCompositeNode()
        if node is not None:
            sliceCompositeNode.SetBackgroundVolumeID(node.GetID())
            sliceWidget.sliceLogic().FitSliceToAll()
        else:
            sliceCompositeNode.SetBackgroundVolumeID(None)

  def onRestoreSliceViews(self):
    # Show last known volume used for segmentation.
    inputCurveNode = self.ui.inputCurveSelector.currentNode()
    if not inputCurveNode:
        return
    referencedInputVolume = inputCurveNode.GetNodeReference("InputVolumeNode")
    self.updateSliceViews(referencedInputVolume)
    
  def cleanup(self):
    """
    Called when the application closes and the module widget is destroyed.
    """
    self.removeObservers()

  def enter(self):
    """
    Called each time the user opens this module.
    """
    # Make sure parameter node exists and observed
    self.initializeParameterNode()

  def exit(self):
    """
    Called each time the user opens a different module.
    """
    # Do not react to parameter node changes (GUI wlil be updated when the user enters into the module)
    self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

  def onSceneStartClose(self, caller, event):
    """
    Called just before the scene is closed.
    """
    # Parameter node will be reset, do not use it anymore
    self.setParameterNode(None)

  def onSceneEndClose(self, caller, event):
    """
    Called just after the scene is closed.
    """
    # If this module is shown while the scene is closed then recreate a new parameter node immediately
    if self.parent.isEntered:
      self.initializeParameterNode()
    self.logic.initMemberVariables()

  def initializeParameterNode(self):
    """
    Ensure parameter node exists and observed.
    """
    # Parameter node stores all user choices in parameter values, node selections, etc.
    # so that when the scene is saved and reloaded, these settings are restored.

    self.setParameterNode(self.logic.getParameterNode())

  def setParameterNode(self, inputParameterNode):
    """
    Set and observe parameter node.
    Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
    """

    if inputParameterNode:
      self.logic.setDefaultParameters(inputParameterNode)

    # Unobserve previously selected parameter node and add an observer to the newly selected.
    # Changes of parameter node are observed so that whenever parameters are changed by a script or any other module
    # those are reflected immediately in the GUI.
    if self._parameterNode is not None:
      self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
    self._parameterNode = inputParameterNode
    if self._parameterNode is not None:
      self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

    # Initial GUI update
    self.updateGUIFromParameterNode()

  def updateGUIFromParameterNode(self, caller=None, event=None):
    """
    This method is called whenever parameter node is changed.
    The module GUI is updated to show the current state of the parameter node.
    """

    if self._parameterNode is None or self._updatingGUIFromParameterNode:
      return

    # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
    self._updatingGUIFromParameterNode = True

    # Update node selectors and sliders
    self.ui.inputCurveSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputCurveNode"))
    self.ui.inputSliceNodeSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputSliceNode"))
    self.ui.tubeDiameterSpinBox.value = float(self._parameterNode.GetParameter("TubeDiameter"))
    self.ui.intensityToleranceSpinBox.value = int(self._parameterNode.GetParameter("IntensityTolerance"))
    self.ui.neighbourhoodSizeDoubleSpinBox.value = float(self._parameterNode.GetParameter("NeighbourhoodSize"))
    self.ui.extractCenterlinesCheckBox.setChecked (self._parameterNode.GetParameter("ExtractCenterlines") == "True")

    # All the GUI updates are done
    self._updatingGUIFromParameterNode = False

  def updateParameterNodeFromGUI(self, caller=None, event=None):
    """
    This method is called when the user makes any change in the GUI.
    The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
    """

    if self._parameterNode is None or self._updatingGUIFromParameterNode:
      return

    wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch

    self._parameterNode.SetNodeReferenceID("InputCurveNode", self.ui.inputCurveSelector.currentNodeID)
    self._parameterNode.SetNodeReferenceID("InputSliceNode", self.ui.inputSliceNodeSelector.currentNodeID)
    self._parameterNode.SetParameter("TubeDiameter", str(self.ui.tubeDiameterSpinBox.value))
    self._parameterNode.SetParameter("IntensityTolerance", str(self.ui.intensityToleranceSpinBox.value))
    self._parameterNode.SetParameter("NeighbourhoodSize", str(self.ui.neighbourhoodSizeDoubleSpinBox.value))
    self._parameterNode.SetParameter("ExtractCenterlines", str(self.ui.extractCenterlinesCheckBox.isChecked()))

    self._parameterNode.EndModify(wasModified)

  """
  Let each one trace last used parameter values and output nodes.
  These can be restored when an input curve is selected again.
  """
  def UpdateInputNodeWithThisOutputNode(self, outputNode, referenceID):
    outputNodeID = ""
    if outputNode:
        outputNodeID = outputNode.GetID()
    self.logic.inputCurveNode.SetNodeReferenceID(referenceID, outputNodeID)
    
  def UpdateInputNodeWithOutputNodes(self):
    if not self.logic.inputCurveNode:
        return
    wasModified = self.logic.inputCurveNode.StartModify()
    self.UpdateInputNodeWithThisOutputNode(self.logic.outputFiducialNode, "OutputFiducialNode")
    self.UpdateInputNodeWithThisOutputNode(self.logic.outputSegmentation, "OutputSegmentation")
    self.UpdateInputNodeWithThisOutputNode(self.logic.outputCenterlineModel, "OutputCenterlineModel")
    self.UpdateInputNodeWithThisOutputNode(self.logic.outputCenterlineCurve, "OutputCenterlineCurve")
    self.logic.inputCurveNode.EndModify(wasModified)

  def UpdateInputNodeWithParameters(self):
    if not self.logic.inputCurveNode:
        return
    wasModified = self.logic.inputCurveNode.StartModify()
    
    sliceNode = self.logic.inputSliceNode
    sliceWidget = slicer.app.layoutManager().sliceWidget(sliceNode.GetName())
    volumeNode = sliceWidget.sliceLogic().GetBackgroundLayer().GetVolumeNode()
    self.logic.inputCurveNode.SetNodeReferenceID("InputVolumeNode", volumeNode.GetID())
    
    self.logic.inputCurveNode.SetAttribute("TubeDiameter", str(self.ui.tubeDiameterSpinBox.value))
    self.logic.inputCurveNode.SetAttribute("InputIntensityTolerance", str(self.ui.intensityToleranceSpinBox.value))
    self.logic.inputCurveNode.SetAttribute("NeighbourhoodSize", str(self.ui.neighbourhoodSizeDoubleSpinBox.value))
    self.logic.inputCurveNode.EndModify(wasModified)

  # Restore parameters from input curve
  def updateGUIParametersFromInputNode(self):
    if not self.logic.inputCurveNode:
        return
    tubeDiameter = self.logic.inputCurveNode.GetAttribute("TubeDiameter")
    if tubeDiameter:
        self.ui.tubeDiameterSpinBox.value = float(tubeDiameter)
    intensityTolerance = self.logic.inputCurveNode.GetAttribute("InputIntensityTolerance")
    if intensityTolerance:
        self.ui.intensityToleranceSpinBox.value = int(intensityTolerance)
    neighbourhoodSize = self.logic.inputCurveNode.GetAttribute("NeighbourhoodSize")
    if neighbourhoodSize:
        self.ui.neighbourhoodSizeDoubleSpinBox.value = float(neighbourhoodSize)

  # Restore output nodes in logic
  def UpdateLogicWithOutputNodes(self):
    if not self.logic.inputCurveNode:
        return
    self.logic.outputFiducialNode = self.logic.inputCurveNode.GetNodeReference("OutputFiducialNode")
    # Here we use a segmentation specified in UI, not the one referenced in the input fiducial.
    self.logic.outputSegmentation = self.ui.outputSegmentationSelector.currentNode()
    self.logic.outputCenterlineModel = self.logic.inputCurveNode.GetNodeReference("OutputCenterlineModel")
    self.logic.outputCenterlineCurve = self.logic.inputCurveNode.GetNodeReference("OutputCenterlineCurve")

  def onApplyButton(self):
    """
    Run processing when user clicks "Apply" button.
    """
    try:
        if self.logic.inputCurveNode is None:
            self.inform("No input curve node specified.")
            return
        if self.logic.inputCurveNode.GetNumberOfControlPoints() < 3:
            self.inform("Input curve node must have at least 3 control points.")
            return
        if self.logic.inputSliceNode is None:
            self.inform("No input slice node specified.")
            return
        # Ensure there's a background volume node.
        sliceNode = self.logic.inputSliceNode
        sliceWidget = slicer.app.layoutManager().sliceWidget(sliceNode.GetName())
        volumeNode = sliceWidget.sliceLogic().GetBackgroundLayer().GetVolumeNode()
        if volumeNode is None:
            self.inform("No volume node selected in input slice node.")
            return
        # Restore logic output objects with referenced ones.
        self.UpdateLogicWithOutputNodes()
        # Compute output
        self.logic.process()
        # Update parameter node with references to new output nodes.
        self.UpdateInputNodeWithOutputNodes()
        # Update input node with input parameters.
        self.UpdateInputNodeWithParameters()
        # Update segmentation selector if it was none
        self.ui.outputSegmentationSelector.setCurrentNode(self.logic.outputSegmentation)

    except Exception as e:
      slicer.util.errorDisplay("Failed to compute results: "+str(e))
      import traceback
      traceback.print_exc()

  # Handy during development
  def removeOutputNodes(self):
    inputCurveNode = self.ui.inputCurveSelector.currentNode()
    if not inputCurveNode:
        return
    slicer.mrmlScene.RemoveNode(inputCurveNode.GetNodeReference("OutputFiducialNode"))
    slicer.mrmlScene.RemoveNode(inputCurveNode.GetNodeReference("OutputCenterlineModel"))
    slicer.mrmlScene.RemoveNode(inputCurveNode.GetNodeReference("OutputCenterlineCurve"))
    self.logic.outputCurveNode = None
    self.logic.outputCenterlineModel = None
    self.logic.outputCenterlineCurve = None
    
    # Remove segment, ID is controlled.
    segmentation = inputCurveNode.GetNodeReference("OutputSegmentation")
    segmentID = "Segment_" + inputCurveNode.GetID()
    segment = segmentation.GetSegmentation().GetSegment(segmentID)
    if segment:
        segmentation.GetSegmentation().RemoveSegment(segment)
    # Remove node references to centerlines and enpoint fiducial
    self.UpdateInputNodeWithOutputNodes()
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

  def __init__(self):
    """
    Called when the logic class is instantiated. Can be used for initializing member variables.
    """
    ScriptedLoadableModuleLogic.__init__(self)
    self.initMemberVariables()
    
  def initMemberVariables(self):
    self.inputCurveNode = None
    self.inputSliceNode = None
    self.tubeDiameter = 8.0
    self.intensityTolerance = 100
    self.neighbourhoodSize = 2.0
    self.extractCenterlines = False
    self.outputFiducialNode = None # 'Extract centerline' endpoints
    self.outputSegmentation = None
    self.outputCenterlineModel = None
    self.outputCenterlineCurve = None
    self.segmentEditorWidgets = None
    self.extractCenterlineWidgets = None

  def setInputCurveNode(self, node):
    if self.inputCurveNode == node:
        return
    self.inputCurveNode = node
    
  def setInputSliceNode(self, node):
    if self.inputSliceNode == node:
        return
    self.inputSliceNode = node

  def setTubeDiameter(self, value):
    self.tubeDiameter = value
    
  def setIntensityTolerance(self, value):
    self.intensityTolerance = value

  def setNeighbourhoodSize(self, value):
    self.neighbourhoodSize = value

  def setExtractCenterlines(self, value):
    self.extractCenterlines = value

  def setDefaultParameters(self, parameterNode):
    """
    Initialize parameter node with default settings.
    """
    if not parameterNode.GetParameter("TubeDiameter"):
      parameterNode.SetParameter("TubeDiameter", "8.0")
    if not parameterNode.GetParameter("IntensityTolerance"):
      parameterNode.SetParameter("IntensityTolerance", "100")
    if not parameterNode.GetParameter("NeighbourhoodSize"):
      parameterNode.SetParameter("NeighbourhoodSize", "2.0")
      """
    Though we want to extract centerlines, we default this flag to False.
    Check that an accurate model is generated first.
    Else, it can be very lengthy and disappointing if there is too much leakage. Also, Slicer may crash during centerline extraction.
    """
    if not parameterNode.GetParameter("ExtractCenterlines"):
      parameterNode.SetParameter("ExtractCenterlines", "False")

  def showStatusMessage(self, messages):
    separator = " "
    msg = separator.join(messages)
    slicer.util.showStatusMessage(msg, 3000)
    slicer.app.processEvents()

  def process(self):
    import time
    startTime = time.time()
    logging.info('Processing started')
    
    slicer.util.showStatusMessage("Segment editor setup")
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
    if not self.outputSegmentation:
        segmentation=slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")
        self.outputSegmentation = segmentation
    else:
        # Prefer a local reference for readability
        segmentation = self.outputSegmentation

    # Local direct reference to slicer.modules.SegmentEditorWidget.editor
    seWidgetEditor=self.segmentEditorWidgets.widgetEditor

    # Get volume node
    sliceWidget = slicer.app.layoutManager().sliceWidget(self.inputSliceNode.GetName())
    volumeNode = sliceWidget.sliceLogic().GetBackgroundLayer().GetVolumeNode()
    
    # Set segment editor controls
    seWidgetEditor.setSegmentationNode(segmentation)
    seWidgetEditor.setSourceVolumeNode(volumeNode)
    """
    This geometry update does the speed-up magic ! No need to crop the master volume.
    We don't strictly need it right here because it is the first master volume of the segmentation. It's however required below each time the master volume node is changed.
    https://discourse.slicer.org/t/resampled-segmentation-limited-by-a-bounding-box-not-the-whole-volume/18772/3
    """
    segmentation.SetReferenceImageGeometryParameterFromVolumeNode(volumeNode)
    
    # Go to Segment Editor.
    mainWindow = slicer.util.mainWindow()
    mainWindow.moduleSelector().selectModule('SegmentEditor')
    
    # Show the input curve. Colour of control points change on selection, helps to wait.
    self.inputCurveNode.SetDisplayVisibility(True)
    # Reset segment editor masking widgets. Values set by previous work must not interfere here.
    self.segmentEditorWidgets.resetMaskingWidgets()
    
    #---------------------- Draw tube with VTK---------------------
    # https://discourse.slicer.org/t/converting-markupscurve-to-markupsfiducial/20246/3
    tube = vtk.vtkTubeFilter()
    tube.SetInputData(self.inputCurveNode.GetCurveWorld())
    tube.SetRadius(self.tubeDiameter / 2)
    tube.SetNumberOfSides(30)
    tube.CappingOn()
    tube.Update()
    segmentation.AddSegmentFromClosedSurfaceRepresentation(tube.GetOutput(), "TubeMask")
    # Select it so that Split Volume can work on this specific segment only.
    seWidgetEditor.setCurrentSegmentID("TubeMask")
    
    #---------------------- Split volume ---------------------
    slicer.util.showStatusMessage("Split volume")
    slicer.app.processEvents()
    seWidgetEditor.setActiveEffectByName("Split volume")
    svEffect = seWidgetEditor.activeEffect()
    svEffect.setParameter("FillValue", -1000)
    # Work on the TubeMask segment only.
    svEffect.setParameter("ApplyToAllVisibleSegments", 0)
    svEffect.self().onApply()
    seWidgetEditor.setActiveEffectByName(None)
    
    # Get output split volume
    allScalarVolumeNodes = slicer.mrmlScene.GetNodesByClass("vtkMRMLScalarVolumeNode")
    outputSplitVolumeNode = allScalarVolumeNodes.GetItemAsObject(allScalarVolumeNodes.GetNumberOfItems() - 1)
    # Remove no longer needed drawn tube segment
    segment = segmentation.GetSegmentation().GetSegment("TubeMask")
    segmentation.GetSegmentation().RemoveSegment(segment)
    # Replace master volume of segmentation
    seWidgetEditor.setSourceVolumeNode(outputSplitVolumeNode)
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
    segmentID = "Segment_" + self.inputCurveNode.GetID()
    segment = segmentation.GetSegmentation().GetSegment(segmentID)
    if segment:
        segmentColor = segment.GetColor()
        segmentation.GetSegmentation().RemoveSegment(segment)
    
    # Add a new segment, with controlled ID and known color.
    object = segmentation.GetSegmentation().AddEmptySegment(segmentID)
    segment = segmentation.GetSegmentation().GetSegment(object)
    # Visually identify the segment by the input fiducial name
    segmentName = "Segment_" + self.inputCurveNode.GetName()
    segment.SetName(segmentName)
    if len(segmentColor):
        segment.SetColor(segmentColor)
    # Select new segment
    seWidgetEditor.setCurrentSegmentID(segmentID)
    
    #---------------------- Flood filling ---------------------
    # Set parameters
    seWidgetEditor.setActiveEffectByName("Flood filling")
    ffEffect = seWidgetEditor.activeEffect()
    ffEffect.setParameter("IntensityTolerance", self.intensityTolerance)
    ffEffect.setParameter("NeighborhoodSizeMm", self.neighbourhoodSize)
    # +++ If an alien ROI is set, segmentation may fail and take an infinite time.
    ffEffect.parameterSetNode().SetNodeReferenceID("FloodFilling.ROI", None)
    ffEffect.updateGUIFromMRML()

    # Get input curve control points
    curveControlPoints = vtk.vtkPoints()
    self.inputCurveNode.GetControlPointPositionsWorld(curveControlPoints)
    numberOfCurveControlPoints = curveControlPoints.GetNumberOfPoints()

    # Apply flood filling at curve control points. Ignore first and last point as the resulting segment would be a big lump. The voxels of split volume at -1000 would be included in the segment.
    for i in range(1, numberOfCurveControlPoints - 1):
        # Show progress in status bar. Helpful to wait.
        t = time.time()
        msg = f'Flood filling : {t-startTime:.2f} seconds - '
        self.showStatusMessage((msg, str(i + 1), "/", str(numberOfCurveControlPoints)))
        
        rasPoint = curveControlPoints.GetPoint(i)
        slicer.vtkMRMLSliceNode.JumpSlice(sliceWidget.sliceLogic().GetSliceNode(), *rasPoint)
        point3D = qt.QVector3D(rasPoint[0], rasPoint[1], rasPoint[2])
        point2D = ffEffect.rasToXy(point3D, sliceWidget)
        qIjkPoint = ffEffect.xyToIjk(point2D, sliceWidget, ffEffect.self().getClippedSourceImageData())
        ffEffect.self().floodFillFromPoint((int(qIjkPoint.x()), int(qIjkPoint.y()), int(qIjkPoint.z())))
    
    # Switch off active effect
    seWidgetEditor.setActiveEffect(None)
    # Replace master volume of segmentation
    seWidgetEditor.setSourceVolumeNode(volumeNode)
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
    
    if not self.extractCenterlines:
        stopTime = time.time()
        message = f'Processing completed in {stopTime-startTime:.2f} seconds'
        logging.info(message)
        slicer.util.showStatusMessage(message, 5000)
        return
    
    #---------------------- Extract centerlines ---------------------
    slicer.util.showStatusMessage("Extract centerline setup")
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
    
    # Set input segmentation
    inputSurfaceComboBox.setCurrentNode(segmentation)
    inputSegmentSelectorWidget.setCurrentSegmentID(segmentID)
    # Create 2 fiducial endpoints, at start and end of input curve. We call it output because it is not user input.
    outputFiducialNode = self.outputFiducialNode
    if not outputFiducialNode:
        outputFiducialNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode")
        # Visually identify the segment by the input fiducial name
        outputFiducialNode.SetName("Endpoints_" + self.inputCurveNode.GetName())
        firstInputCurveControlPoint = self.inputCurveNode.GetNthControlPointPositionVector(0)
        outputFiducialNode.AddControlPointWorld(firstInputCurveControlPoint)
        endPointsMarkupsSelector.setCurrentNode(outputFiducialNode)
        lastInputCurveControlPoint = self.inputCurveNode.GetNthControlPointPositionVector(curveControlPoints.GetNumberOfPoints() - 1)
        outputFiducialNode.AddControlPointWorld(lastInputCurveControlPoint)
        endPointsMarkupsSelector.setCurrentNode(outputFiducialNode)
        self.outputFiducialNode = outputFiducialNode
    # Account for rename. Control points are not remaned though.
    outputFiducialNode.SetName("Endpoints_" + self.inputCurveNode.GetName())
    
    # Output centerline model. A single node throughout.
    centerlineModel = self.outputCenterlineModel
    if not centerlineModel:
        centerlineModel = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode")
        # Visually identify the segment by the input fiducial name
        centerlineModel.SetName("Centerline_model_" + self.inputCurveNode.GetName())
        self.outputCenterlineModel = centerlineModel
    # Account for rename
    centerlineModel.SetName("Centerline_model_" + self.inputCurveNode.GetName())
    outputCenterlineModelSelector.setCurrentNode(centerlineModel)
    
    # Output centerline curve. A single node throughout.
    centerlineCurve = self.outputCenterlineCurve
    if not centerlineCurve:
        centerlineCurve = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsCurveNode")
        # Visually identify the segment by the input fiducial name
        centerlineCurve.SetName("Centerline_curve_" + self.inputCurveNode.GetName())
        self.outputCenterlineCurve = centerlineCurve
    # Account for rename
    centerlineCurve.SetName("Centerline_curve_" + self.inputCurveNode.GetName())
    
    outputCenterlineCurveSelector.setCurrentNode(centerlineCurve)
    """
    Don't preprocess input surface. Decimation error may crash Slicer. Quadric method for decimation is slower but more reliable.
    """
    preprocessInputSurfaceModelCheckBox.setChecked(False)
    # Apply
    applyButton.click()
    # Hide the input curve to show the centerlines
    self.inputCurveNode.SetDisplayVisibility(False)
    # Close network pane; we don't use this here.
    self.extractCenterlineWidgets.outputNetworkGroupBox.collapsed = True

    stopTime = time.time()
    message = f'Processing completed in {stopTime-startTime:.2f} seconds'
    logging.info(message)
    slicer.util.showStatusMessage(message, 5000)

#
# GuidedArterySegmentationTest
#

class GuidedArterySegmentationTest(ScriptedLoadableModuleTest):
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
    self.test_GuidedArterySegmentation1()

  def test_GuidedArterySegmentation1(self):
    self.delayDisplay("Starting the test")

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
        # Get segment editor controls
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
    def resetMaskingWidgets(self):
        self.widgetEditor.mrmlSegmentEditorNode().SetMaskMode(slicer.vtkMRMLSegmentationNode.EditAllowedEverywhere)
        self.widgetEditor.mrmlSegmentEditorNode().SourceVolumeIntensityMaskOff()
        self.widgetEditor.mrmlSegmentEditorNode().SetOverwriteMode(self.widgetEditor.mrmlSegmentEditorNode().OverwriteAllSegments)

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

