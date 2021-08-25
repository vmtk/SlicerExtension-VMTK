# slicer imports
import os
import unittest
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
import logging

#
# Level Set Segmentation using VMTK based Tools
#

class LevelSetSegmentation(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """
  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Level Set Segmentation"
    self.parent.categories = ["Vascular Modeling Toolkit"]
    self.parent.dependencies = []
    self.parent.contributors = ["Daniel Haehn (Boston Children's Hospital)", "Luca Antiga (Orobix)", "Steve Pieper (Isomics)"]
    self.parent.helpText = """Documentation is available <a href="https://github.com/vmtk/SlicerExtension-VMTK">here</a>.
"""
    self.parent.acknowledgementText = """
""" # replace with organization, grant and thanks.

class LevelSetSegmentationWidget(ScriptedLoadableModuleWidget):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent=None):
    ScriptedLoadableModuleWidget.__init__(self, parent)

    # the pointer to the logic
    self.logic = LevelSetSegmentationLogic()

    if not parent:
      # after setup, be ready for events
      self.parent.show()
    else:
      # register default slots
      self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)', self.onMRMLSceneChanged)

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    #
    # the I/O panel
    #

    inputsCollapsibleButton = ctk.ctkCollapsibleButton()
    inputsCollapsibleButton.text = "Inputs"
    self.layout.addWidget(inputsCollapsibleButton)
    inputsFormLayout = qt.QFormLayout(inputsCollapsibleButton)

    # inputVolume selector
    self.inputVolumeNodeSelector = slicer.qMRMLNodeComboBox()
    self.inputVolumeNodeSelector.objectName = 'inputVolumeNodeSelector'
    self.inputVolumeNodeSelector.toolTip = "Select the input volume. This should always be the original image and not a vesselness image, if possible."
    self.inputVolumeNodeSelector.nodeTypes = ['vtkMRMLScalarVolumeNode']
    self.inputVolumeNodeSelector.noneEnabled = False
    self.inputVolumeNodeSelector.addEnabled = False
    self.inputVolumeNodeSelector.removeEnabled = False
    inputsFormLayout.addRow("Input Volume:", self.inputVolumeNodeSelector)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                        self.inputVolumeNodeSelector, 'setMRMLScene(vtkMRMLScene*)')
    self.inputVolumeNodeSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.onInputVolumeChanged)

    # vesselnessVolume selector
    self.vesselnessVolumeNodeSelector = slicer.qMRMLNodeComboBox()
    self.vesselnessVolumeNodeSelector.objectName = 'vesselnessVolumeNodeSelector'
    self.vesselnessVolumeNodeSelector.toolTip = "Select the input vesselness volume."
    self.vesselnessVolumeNodeSelector.nodeTypes = ['vtkMRMLScalarVolumeNode']
    self.vesselnessVolumeNodeSelector.noneEnabled = True
    self.vesselnessVolumeNodeSelector.addEnabled = False
    self.vesselnessVolumeNodeSelector.removeEnabled = False
    inputsFormLayout.addRow("Vesselness Volume:", self.vesselnessVolumeNodeSelector)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                        self.vesselnessVolumeNodeSelector, 'setMRMLScene(vtkMRMLScene*)')
    self.vesselnessVolumeNodeSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.onVesselnessVolumeChanged)
    self.vesselnessVolumeNodeSelector.setCurrentNode(None)

    # seed selector
    self.seedFiducialsNodeSelector = slicer.qSlicerSimpleMarkupsWidget()
    self.seedFiducialsNodeSelector.objectName = 'seedFiducialsNodeSelector'
    self.seedFiducialsNodeSelector.toolTip = "Select start and end point of the vessel branch. Only the first and last point in the list are used."
    self.seedFiducialsNodeSelector.defaultNodeColor = qt.QColor(0,0,255) # blue
    self.seedFiducialsNodeSelector.jumpToSliceEnabled = True
    self.seedFiducialsNodeSelector.markupsPlaceWidget().placeMultipleMarkups = slicer.qSlicerMarkupsPlaceWidget.ForcePlaceMultipleMarkups
    self.seedFiducialsNodeSelector.setNodeBaseName("seeds")
    self.seedFiducialsNodeSelector.markupsSelectorComboBox().baseName = "Seeds"
    self.seedFiducialsNodeSelector.markupsSelectorComboBox().noneEnabled = False
    self.seedFiducialsNodeSelector.markupsSelectorComboBox().removeEnabled = True
    inputsFormLayout.addRow("Seeds:", self.seedFiducialsNodeSelector)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                        self.seedFiducialsNodeSelector, 'setMRMLScene(vtkMRMLScene*)')

    # stopper selector
    self.stopperFiducialsNodeSelector = slicer.qSlicerSimpleMarkupsWidget()
    self.stopperFiducialsNodeSelector.objectName = 'stopperFiducialsNodeSelector'
    self.stopperFiducialsNodeSelector.toolTip = "(Optional) Select a hierarchy containing the fiducials to use as Stoppers. Whenever one stopper is reached, the segmentation stops."
    self.stopperFiducialsNodeSelector.defaultNodeColor = qt.QColor(0,0,255) # blue
    self.stopperFiducialsNodeSelector.setNodeBaseName("seeds")
    self.stopperFiducialsNodeSelector.tableWidget().hide()
    self.stopperFiducialsNodeSelector.markupsSelectorComboBox().baseName = "Stoppers"
    self.stopperFiducialsNodeSelector.markupsSelectorComboBox().noneEnabled = True
    self.stopperFiducialsNodeSelector.markupsSelectorComboBox().removeEnabled = True
    inputsFormLayout.addRow("Stoppers:", self.stopperFiducialsNodeSelector)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                        self.stopperFiducialsNodeSelector, 'setMRMLScene(vtkMRMLScene*)')

    #
    # Outputs
    #

    outputsCollapsibleButton = ctk.ctkCollapsibleButton()
    outputsCollapsibleButton.text = "Outputs"
    self.layout.addWidget(outputsCollapsibleButton)
    outputsFormLayout = qt.QFormLayout(outputsCollapsibleButton)

    # outputVolume selector
    self.outputVolumeNodeSelector = slicer.qMRMLNodeComboBox()
    self.outputVolumeNodeSelector.toolTip = "Select the output labelmap."
    self.outputVolumeNodeSelector.nodeTypes = ['vtkMRMLLabelMapVolumeNode']
    self.outputVolumeNodeSelector.baseName = "LevelSetSegmentation"
    self.outputVolumeNodeSelector.noneEnabled = False
    self.outputVolumeNodeSelector.addEnabled = True
    self.outputVolumeNodeSelector.selectNodeUponCreation = True
    self.outputVolumeNodeSelector.removeEnabled = True
    outputsFormLayout.addRow("Output Labelmap:", self.outputVolumeNodeSelector)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                        self.outputVolumeNodeSelector, 'setMRMLScene(vtkMRMLScene*)')

    # outputModel selector
    self.outputModelNodeSelector = slicer.qMRMLNodeComboBox()
    self.outputModelNodeSelector.objectName = 'outputModelNodeSelector'
    self.outputModelNodeSelector.toolTip = "Select the output model."
    self.outputModelNodeSelector.nodeTypes = ['vtkMRMLModelNode']
    self.outputModelNodeSelector.hideChildNodeTypes = ['vtkMRMLAnnotationNode']  # hide all annotation nodes
    self.outputModelNodeSelector.baseName = "LevelSetSegmentationModel"
    self.outputModelNodeSelector.noneEnabled = False
    self.outputModelNodeSelector.addEnabled = True
    self.outputModelNodeSelector.selectNodeUponCreation = True
    self.outputModelNodeSelector.removeEnabled = True
    outputsFormLayout.addRow("Output Model:", self.outputModelNodeSelector)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                        self.outputModelNodeSelector, 'setMRMLScene(vtkMRMLScene*)')


    #
    # the segmentation panel
    #

    segmentationCollapsibleButton = ctk.ctkCollapsibleButton()
    segmentationCollapsibleButton.text = "Segmentation"
    self.layout.addWidget(segmentationCollapsibleButton)

    segmentationFormLayout = qt.QFormLayout(segmentationCollapsibleButton)

    # Threshold slider
    thresholdLabel = qt.QLabel()
    thresholdLabel.text = "Thresholding" + (' '*7)
    thresholdLabel.toolTip = "Choose the intensity range to segment."
    thresholdLabel.setAlignment(4)
    segmentationFormLayout.addRow(thresholdLabel)

    self.thresholdSlider = slicer.qMRMLRangeWidget()
    segmentationFormLayout.addRow(self.thresholdSlider)
    self.thresholdSlider.connect('valuesChanged(double,double)', self.onThresholdSliderChanged)

    self.segmentationAdvancedToggle = qt.QCheckBox("Show Advanced Segmentation Properties")
    self.segmentationAdvancedToggle.setChecked(False)
    segmentationFormLayout.addRow(self.segmentationAdvancedToggle)

    #
    # segmentation advanced panel
    #

    self.segmentationAdvancedPanel = qt.QFrame(segmentationCollapsibleButton)
    self.segmentationAdvancedPanel.hide()
    self.segmentationAdvancedPanel.setFrameStyle(6)
    segmentationFormLayout.addRow(self.segmentationAdvancedPanel)
    self.segmentationAdvancedToggle.connect("clicked()", self.onSegmentationAdvancedToggle)

    segmentationAdvancedFormLayout = qt.QFormLayout(self.segmentationAdvancedPanel)

    # inflation slider
    inflationLabel = qt.QLabel()
    inflationLabel.text = "less inflation <-> more inflation" + (' '*14)
    inflationLabel.setAlignment(4)
    inflationLabel.toolTip = "Define how fast the segmentation expands."
    segmentationAdvancedFormLayout.addRow(inflationLabel)

    self.inflationSlider = ctk.ctkSliderWidget()
    self.inflationSlider.decimals = 0
    self.inflationSlider.minimum = -100
    self.inflationSlider.maximum = 100
    self.inflationSlider.singleStep = 10
    self.inflationSlider.toolTip = inflationLabel.toolTip
    segmentationAdvancedFormLayout.addRow(self.inflationSlider)

    # curvature slider
    curvatureLabel = qt.QLabel()
    curvatureLabel.text = "less curvature <-> more curvature" + (' '*14)
    curvatureLabel.setAlignment(4)
    curvatureLabel.toolTip = "Choose a high curvature to generate a smooth segmentation."
    segmentationAdvancedFormLayout.addRow(curvatureLabel)

    self.curvatureSlider = ctk.ctkSliderWidget()
    self.curvatureSlider.decimals = 0
    self.curvatureSlider.minimum = -100
    self.curvatureSlider.maximum = 100
    self.curvatureSlider.singleStep = 10
    self.curvatureSlider.toolTip = curvatureLabel.toolTip
    segmentationAdvancedFormLayout.addRow(self.curvatureSlider)

    # attraction slider
    attractionLabel = qt.QLabel()
    attractionLabel.text = "less attraction to gradient <-> more attraction to gradient" + (' '*14)
    attractionLabel.setAlignment(4)
    attractionLabel.toolTip = "Configure how the segmentation travels towards gradient ridges (vessel lumen wall)."
    segmentationAdvancedFormLayout.addRow(attractionLabel)

    self.attractionSlider = ctk.ctkSliderWidget()
    self.attractionSlider.decimals = 0
    self.attractionSlider.minimum = -100
    self.attractionSlider.maximum = 100
    self.attractionSlider.singleStep = 10
    self.attractionSlider.toolTip = attractionLabel.toolTip
    segmentationAdvancedFormLayout.addRow(self.attractionSlider)

    # iteration spinbox
    self.iterationSpinBox = qt.QSpinBox()
    self.iterationSpinBox.minimum = 0
    self.iterationSpinBox.maximum = 5000
    self.iterationSpinBox.singleStep = 10
    self.iterationSpinBox.toolTip = "Choose the number of evolution iterations."
    segmentationAdvancedFormLayout.addRow((' '*100) + "Iterations:", self.iterationSpinBox)

    #
    # Reset, preview and apply buttons
    #

    self.buttonBox = qt.QDialogButtonBox()
    self.resetButton = self.buttonBox.addButton(self.buttonBox.RestoreDefaults)
    self.resetButton.toolTip = "Click to reset all input elements to default."
    self.previewButton = self.buttonBox.addButton(self.buttonBox.Discard)
    self.previewButton.setIcon(qt.QIcon())
    self.previewButton.text = "Preview"
    self.previewButton.toolTip = "Click to refresh the preview."
    self.startButton = self.buttonBox.addButton(self.buttonBox.Apply)
    self.startButton.setIcon(qt.QIcon())
    self.startButton.text = "Start"
    self.startButton.enabled = False
    self.startButton.toolTip = "Click to start the filtering."
    self.layout.addWidget(self.buttonBox)
    self.resetButton.connect("clicked()", self.restoreDefaults)
    self.previewButton.connect("clicked()", self.onPreviewButtonClicked)
    self.startButton.connect("clicked()", self.onStartButtonClicked)

    self.inputVolumeNodeSelector.setMRMLScene(slicer.mrmlScene)
    self.seedFiducialsNodeSelector.setMRMLScene(slicer.mrmlScene)
    self.vesselnessVolumeNodeSelector.setMRMLScene(slicer.mrmlScene)
    self.outputVolumeNodeSelector.setMRMLScene(slicer.mrmlScene)
    self.outputModelNodeSelector.setMRMLScene(slicer.mrmlScene)
    self.stopperFiducialsNodeSelector.setMRMLScene(slicer.mrmlScene)

    # set default values
    self.restoreDefaults()
    self.onInputVolumeChanged()

    # compress the layout
    self.layout.addStretch(1)


  def onStartButtonClicked(self):
    qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)
    # this is no preview
    self.start(False)
    qt.QApplication.restoreOverrideCursor()

  def onPreviewButtonClicked(self):
      '''
      '''

      # perform the preview
      self.start(True)

      # activate startButton
      self.startButton.enabled = True


  def onMRMLSceneChanged(self):
    logging.debug("onMRMLSceneChanged")
    self.restoreDefaults()

  def onInputVolumeChanged(self):

    logging.debug("onInputVolumeChanged")

    currentNode = self.inputVolumeNodeSelector.currentNode()
    if not currentNode:
      return

    v = currentNode.GetNodeReference("Vesselness")
    if v:
      self.vesselnessVolumeNodeSelector.setCurrentNode(v)

    self.updateThresholdRange()

  def onVesselnessVolumeChanged(self):
    vesselnessNode = self.vesselnessVolumeNodeSelector.currentNode()
    inputVolumeNode = self.inputVolumeNodeSelector.currentNode()
    if inputVolumeNode and vesselnessNode:
      inputVolumeNode.SetNodeReferenceID("Vesselness", vesselnessNode.GetID())

    self.updateThresholdRange()

  def updateThresholdRange(self):

    # if we have a vesselnessNode, we will configure the threshold slider for it instead of the original image
    # if not, the currentNode is the input volume
    currentNode = self.vesselnessVolumeNodeSelector.currentNode()
    if not currentNode:
        currentNode = self.inputVolumeNodeSelector.currentNode()

    if not currentNode or not currentNode.GetImageData():
      wasBlocked = self.thresholdSlider.blockSignals(True)
      # reset the thresholdSlider
      self.thresholdSlider.minimum = 0
      self.thresholdSlider.maximum = 100
      self.thresholdSlider.minimumValue = 0
      self.thresholdSlider.maximumValue = 100
      self.thresholdSlider.blockSignals(wasBlocked)
      return

    currentImageData = currentNode.GetImageData()
    currentDisplayNode = currentNode.GetDisplayNode()

    currentScalarRange = currentImageData.GetScalarRange()
    minimumScalarValue = round(currentScalarRange[0], 0)
    maximumScalarValue = round(currentScalarRange[1], 0)

    wasBlocked = self.thresholdSlider.blockSignals(True)

    self.thresholdSlider.minimum = minimumScalarValue
    self.thresholdSlider.maximum = maximumScalarValue

    # if the image has a small scalarRange, we have to adjust the singleStep
    if maximumScalarValue <= 10:
      self.thresholdSlider.singleStep = 0.01

    if currentDisplayNode:
      if currentDisplayNode.GetApplyThreshold():
        # if a threshold is already applied, use it
        self.thresholdSlider.minimumValue = currentDisplayNode.GetLowerThreshold()
        self.thresholdSlider.maximumValue = currentDisplayNode.GetUpperThreshold()
      else:
        # don't use a threshold, use the scalar range
        logging.debug("Reset thresholdSlider's values.")
        self.thresholdSlider.minimumValue = minimumScalarValue+(maximumScalarValue-minimumScalarValue)*0.10
        self.thresholdSlider.maximumValue = maximumScalarValue

    self.thresholdSlider.blockSignals(wasBlocked)

  def resetThresholdOnDisplayNode(self):
    logging.debug("resetThresholdOnDisplayNode")
    currentNode = self.inputVolumeNodeSelector.currentNode()
    if currentNode:
      currentDisplayNode = currentNode.GetDisplayNode()
      if currentDisplayNode:
        currentDisplayNode.SetApplyThreshold(0)

  def onThresholdSliderChanged(self):
    # first, check if we have a vesselness node
    currentNode = self.vesselnessVolumeNodeSelector.currentNode()
    if currentNode:
      logging.debug("There was a vesselness node: " + str(currentNode.GetName()))
    else:
      logging.debug("There was no vesselness node..")
      # if we don't have a vesselness node, check if we have an original input node
      currentNode = self.inputVolumeNodeSelector.currentNode()

    if currentNode:
      currentDisplayNode = currentNode.GetDisplayNode()
      if currentDisplayNode:
        currentDisplayNode.SetLowerThreshold(self.thresholdSlider.minimumValue)
        currentDisplayNode.SetUpperThreshold(self.thresholdSlider.maximumValue)
        currentDisplayNode.SetApplyThreshold(1)

  def onSegmentationAdvancedToggle(self):
    '''
    Show the Segmentation Advanced panel
    '''
    if self.segmentationAdvancedToggle.checked:
      self.segmentationAdvancedPanel.show()
    else:
      self.segmentationAdvancedPanel.hide()

  def restoreDefaults(self):
    '''
    scope == 0: reset all
    scope == 1: reset only threshold slider
    '''
    logging.debug("restoreDefaults")

    self.thresholdSlider.minimum = 0
    self.thresholdSlider.maximum = 100
    self.thresholdSlider.minimumValue = 0
    self.thresholdSlider.maximumValue = 100
    self.thresholdSlider.singleStep = 1

    self.segmentationAdvancedToggle.setChecked(False)
    self.segmentationAdvancedPanel.hide()

    self.inflationSlider.value = 0
    self.curvatureSlider.value = 70
    self.attractionSlider.value = 50
    self.iterationSpinBox.value = 10

    # reset threshold on display node
    self.resetThresholdOnDisplayNode()
    # if a volume is selected, the threshold slider values have to match it
    self.onInputVolumeChanged()

  def start(self, preview=False):
    logging.debug("Starting Level Set Segmentation..")

    # first we need the nodes
    currentVolumeNode = self.inputVolumeNodeSelector.currentNode()
    currentSeedsNode = self.seedFiducialsNodeSelector.currentNode()
    currentVesselnessNode = self.vesselnessVolumeNodeSelector.currentNode()
    currentStoppersNode = self.stopperFiducialsNodeSelector.currentNode()
    currentLabelMapNode = self.outputVolumeNodeSelector.currentNode()
    currentModelNode = self.outputModelNodeSelector.currentNode()

    if not currentVolumeNode:
        # we need a input volume node
        return False

    if not currentSeedsNode:
        # we need a seeds node
        return False

    if not currentStoppersNode or currentStoppersNode.GetID() == currentSeedsNode.GetID():
        # we need a current stopper node
        # self.stopperFiducialsNodeSelector.addNode()
        pass

    if not currentLabelMapNode or currentLabelMapNode.GetID() == currentVolumeNode.GetID():
        newLabelMapNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLLabelMapVolumeNode")
        newLabelMapNode.UnRegister(None)
        newLabelMapNode.CopyOrientation(currentVolumeNode)
        newLabelMapNode.SetName(slicer.mrmlScene.GetUniqueNameByString(self.outputVolumeNodeSelector.baseName))
        currentLabelMapNode = slicer.mrmlScene.AddNode(newLabelMapNode)
        currentLabelMapNode.CreateDefaultDisplayNodes()
        self.outputVolumeNodeSelector.setCurrentNode(currentLabelMapNode)

    if not currentModelNode:
        # we need a current model node, the display node is created later
        newModelNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLModelNode")
        newModelNode.UnRegister(None)
        newModelNode.SetName(slicer.mrmlScene.GetUniqueNameByString(self.outputModelNodeSelector.baseName))
        currentModelNode = slicer.mrmlScene.AddNode(newModelNode)
        currentModelNode.CreateDefaultDisplayNodes()

        self.outputModelNodeSelector.setCurrentNode(currentModelNode)

    # now we need to convert the fiducials to vtkIdLists
    seeds = LevelSetSegmentationWidget.convertFiducialHierarchyToVtkIdList(currentSeedsNode, currentVolumeNode)
    if currentStoppersNode:
      stoppers = LevelSetSegmentationWidget.convertFiducialHierarchyToVtkIdList(currentStoppersNode, currentVolumeNode)
    else:
      stoppers = vtk.vtkIdList()

    # the input image for the initialization
    inputImage = vtk.vtkImageData()

    # check if we have a vesselnessNode - this will be our input for the initialization then
    if currentVesselnessNode:
        # yes, there is one
        inputImage.DeepCopy(currentVesselnessNode.GetImageData())
    else:
        # no, there is none - we use the original image
        inputImage.DeepCopy(currentVolumeNode.GetImageData())

    # initialization
    initImageData = vtk.vtkImageData()

    # evolution
    evolImageData = vtk.vtkImageData()

    # perform the initialization
    initImageData.DeepCopy(self.logic.performInitialization(inputImage,
                                                                 self.thresholdSlider.minimumValue,
                                                                 self.thresholdSlider.maximumValue,
                                                                 seeds,
                                                                 stoppers,
                                                                 'collidingfronts'))

    if not initImageData.GetPointData().GetScalars():
        # something went wrong, the image is empty
        logging.error("Segmentation failed - the output was empty..")
        return False

    # check if it is a preview call
    if preview:

        # if this is a preview call, we want to skip the evolution
        evolImageData.DeepCopy(initImageData)

    else:

        # no preview, run the whole thing! we never use the vesselness node here, just the original one
        evolImageData.DeepCopy(self.logic.performEvolution(currentVolumeNode.GetImageData(),
                                                                initImageData,
                                                                self.iterationSpinBox.value,
                                                                self.inflationSlider.value,
                                                                self.curvatureSlider.value,
                                                                self.attractionSlider.value,
                                                                'geodesic'))


    # create segmentation labelMap
    labelMap = vtk.vtkImageData()
    labelMap.DeepCopy(self.logic.buildSimpleLabelMap(evolImageData, 5, 0))

    currentLabelMapNode.CopyOrientation(currentVolumeNode)

    # propagate the label map to the node
    currentLabelMapNode.SetAndObserveImageData(labelMap)

    # deactivate the threshold in the GUI
    self.resetThresholdOnDisplayNode()
    # self.onInputVolumeChanged()

    # show the segmentation results in the GUI
    selectionNode = slicer.app.applicationLogic().GetSelectionNode()

    # preview
    # currentVesselnessNode
    slicer.util.setSliceViewerLayers(background=currentVolumeNode, foreground=currentVesselnessNode, label=currentLabelMapNode,
      foregroundOpacity = 0.6 if preview else 0.1)

    # generate 3D model
    model = vtk.vtkPolyData()

    # we need the ijkToRas transform for the marching cubes call
    ijkToRasMatrix = vtk.vtkMatrix4x4()
    currentLabelMapNode.GetIJKToRASMatrix(ijkToRasMatrix)

    # call marching cubes
    model.DeepCopy(self.logic.marchingCubes(evolImageData, ijkToRasMatrix, 0.0))

    # propagate model to nodes
    currentModelNode.SetAndObservePolyData(model)

    currentModelNode.CreateDefaultDisplayNodes()
    currentModelDisplayNode = currentModelNode.GetDisplayNode()

    # always configure the displayNode to show the model
    currentModelDisplayNode.SetColor(1.0, 0.55, 0.4)  # red
    currentModelDisplayNode.SetBackfaceCulling(0)
    currentModelDisplayNode.SetSliceIntersectionVisibility(0)
    currentModelDisplayNode.SetVisibility(1)
    currentModelDisplayNode.SetOpacity(1.0)

    # fit slice to all sliceviewers
    slicer.app.applicationLogic().FitSliceToAll()

    # jump all sliceViewers to the first fiducial point, if one was used
    if currentSeedsNode:

        currentCoordinatesRAS = [0, 0, 0]

        if isinstance(currentSeedsNode, slicer.vtkMRMLMarkupsFiducialNode):

            # let's get the first children
            currentSeedsNode.GetNthFiducialPosition(0,currentCoordinatesRAS)

        numberOfSliceNodes = slicer.mrmlScene.GetNumberOfNodesByClass('vtkMRMLSliceNode')
        for n in range(numberOfSliceNodes):
            sliceNode = slicer.mrmlScene.GetNthNodeByClass(n, "vtkMRMLSliceNode")
            if sliceNode:
                sliceNode.JumpSliceByOffsetting(currentCoordinatesRAS[0], currentCoordinatesRAS[1], currentCoordinatesRAS[2])


    # center 3D view(s) on the new model
    if currentCoordinatesRAS:
        for d in range(slicer.app.layoutManager().threeDViewCount):

            threeDView = slicer.app.layoutManager().threeDWidget(d).threeDView()

            # reset the focal point
            threeDView.resetFocalPoint()

            # and fly to our seed point
            interactor = threeDView.interactor()
            renderer = threeDView.renderWindow().GetRenderers().GetItemAsObject(0)
            interactor.FlyTo(renderer, currentCoordinatesRAS[0], currentCoordinatesRAS[1], currentCoordinatesRAS[2])

    logging.debug("End of Level Set Segmentation..")
    return True

  @staticmethod
  def convertFiducialHierarchyToVtkIdList(hierarchyNode,volumeNode):
    outputIds = vtk.vtkIdList()

    if not hierarchyNode or not volumeNode:
      return outputIds

    if isinstance(hierarchyNode,slicer.vtkMRMLMarkupsFiducialNode) and isinstance(volumeNode,slicer.vtkMRMLScalarVolumeNode):

      image = volumeNode.GetImageData()

      # now we have the children which are fiducialNodes - let's loop!
      for n in range(hierarchyNode.GetNumberOfFiducials()):

        currentCoordinatesRAS = [0,0,0]

        # grab the current coordinates
        hierarchyNode.GetNthFiducialPosition(n,currentCoordinatesRAS)

        # convert the RAS to IJK
        currentCoordinatesIJK = LevelSetSegmentationWidget.ConvertRAStoIJK(volumeNode,currentCoordinatesRAS)

        # strip the last element since we need a 3based tupel
        currentCoordinatesIJKlist = (int(currentCoordinatesIJK[0]),int(currentCoordinatesIJK[1]),int(currentCoordinatesIJK[2]))
        outputIds.InsertNextId(int(image.ComputePointId(currentCoordinatesIJKlist)))

    # IdList was created, return it even if it might be empty
    return outputIds

  @staticmethod
  def ConvertRAStoIJK(volumeNode,rasCoordinates):
    rasToIjkMatrix = vtk.vtkMatrix4x4()
    volumeNode.GetRASToIJKMatrix(rasToIjkMatrix)

    # the RAS coordinates need to be 4
    if len(rasCoordinates) < 4:
        rasCoordinates.append(1)

    ijkCoordinates = rasToIjkMatrix.MultiplyPoint(rasCoordinates)

    return ijkCoordinates

class LevelSetSegmentationLogic(object):
    '''
    classdocs
    '''


    def __init__(self):
        '''
        Constructor
        '''


    def performInitialization(self, image, lowerThreshold, upperThreshold, sourceSeedIds, targetSeedIds, method="collidingfronts"):
        '''
        '''
        # import the vmtk libraries
        try:
            import vtkvmtkSegmentationPython as vtkvmtkSegmentation
        except ImportError:
            logging.error("Unable to import the SlicerVmtk libraries")

        cast = vtk.vtkImageCast()
        cast.SetInputData(image)
        cast.SetOutputScalarTypeToFloat()
        cast.Update()
        image = cast.GetOutput()

        scalarRange = image.GetScalarRange()

        imageDimensions = image.GetDimensions()
        maxImageDimensions = max(imageDimensions)

        threshold = vtk.vtkImageThreshold()
        threshold.SetInputData(image)
        threshold.ThresholdBetween(lowerThreshold, upperThreshold)
        threshold.ReplaceInOff()
        threshold.ReplaceOutOn()
        threshold.SetOutValue(scalarRange[0] - scalarRange[1])
        threshold.Update()

        thresholdedImage = threshold.GetOutput()

        scalarRange = thresholdedImage.GetScalarRange()

        shiftScale = vtk.vtkImageShiftScale()
        shiftScale.SetInputData(thresholdedImage)
        shiftScale.SetShift(-scalarRange[0])
        shiftScale.SetScale(1.0 / (scalarRange[1] - scalarRange[0]))
        shiftScale.Update()

        speedImage = shiftScale.GetOutput()

        if method == "collidingfronts":
            # ignore sidebranches, use colliding fronts
            logging.debug("Using colliding fronts algorithm")
            logging.debug("number of vtk ids: " + str(sourceSeedIds.GetNumberOfIds()))
            logging.debug("SourceSeedIds:")
            logging.debug(sourceSeedIds)
            collidingFronts = vtkvmtkSegmentation.vtkvmtkCollidingFrontsImageFilter()
            collidingFronts.SetInputData(speedImage)
            sourceSeedId1 = vtk.vtkIdList()
            sourceSeedId1.InsertNextId(sourceSeedIds.GetId(0))
            collidingFronts.SetSeeds1(sourceSeedId1)
            sourceSeedId2 = vtk.vtkIdList()
            sourceSeedId2.InsertNextId(sourceSeedIds.GetId(sourceSeedIds.GetNumberOfIds()-1))
            collidingFronts.SetSeeds2(sourceSeedId2)
            collidingFronts.ApplyConnectivityOn()
            collidingFronts.StopOnTargetsOn()
            collidingFronts.Update()

            subtract = vtk.vtkImageMathematics()
            subtract.SetInputData(collidingFronts.GetOutput())
            subtract.SetOperationToAddConstant()
            subtract.SetConstantC(-10 * collidingFronts.GetNegativeEpsilon())
            subtract.Update()

        elif method == "fastmarching":
            logging.debug("Using fast marching algorithm")
            fastMarching = vtkvmtkSegmentation.vtkvmtkFastMarchingUpwindGradientImageFilter()
            fastMarching.SetInputData(speedImage)
            fastMarching.SetSeeds(sourceSeedIds)
            fastMarching.GenerateGradientImageOn()
            fastMarching.SetTargetOffset(0.0)
            fastMarching.SetTargets(targetSeedIds)
            if targetSeedIds.GetNumberOfIds() > 0:
                fastMarching.SetTargetReachedModeToOneTarget()
            else:
                fastMarching.SetTargetReachedModeToNoTargets()
            fastMarching.Update()

            if targetSeedIds.GetNumberOfIds() > 0:
                subtract = vtk.vtkImageMathematics()
                subtract.SetInputData(fastMarching.GetOutput())
                subtract.SetOperationToAddConstant()
                subtract.SetConstantC(-fastMarching.GetTargetValue())
                subtract.Update()

            else:
                subtract = vtk.vtkImageThreshold()
                subtract.SetInputData(fastMarching.GetOutput())
                subtract.ThresholdByLower(2000)  # TODO find robust value
                subtract.ReplaceInOff()
                subtract.ReplaceOutOn()
                subtract.SetOutValue(-1)
                subtract.Update()

        elif method == "threshold":
            raise NotImplementedError()
        elif method == "isosurface":
            raise NotImplementedError()
        elif method == "seeds":
            raise NotImplementedError()
        else:
            raise NameError('Unsupported InitializationType')

        outImageData = vtk.vtkImageData()
        outImageData.DeepCopy(subtract.GetOutput())

        return outImageData



    def performEvolution(self, originalImage, segmentationImage, numberOfIterations, inflation, curvature, attraction, levelSetsType='geodesic'):
        '''

        '''
        # import the vmtk libraries
        try:
            import vtkvmtkSegmentationPython as vtkvmtkSegmentation
        except ImportError:
            logging.error("Unable to import the SlicerVmtk libraries")

        featureDerivativeSigma = 0.0
        maximumRMSError = 1E-20
        isoSurfaceValue = 0.0

        logging.debug("NumberOfIterations: " + str(numberOfIterations))
        logging.debug("inflation: " + str(inflation))
        logging.debug("curvature: " + str(curvature))
        logging.debug("attraction: " + str(attraction))

        if levelSetsType == 'geodesic':
            logging.debug("using vtkvmtkGeodesicActiveContourLevelSetImageFilter")
            levelSets = vtkvmtkSegmentation.vtkvmtkGeodesicActiveContourLevelSetImageFilter()
            levelSets.SetFeatureImage(self.buildGradientBasedFeatureImage(originalImage))
            levelSets.SetDerivativeSigma(featureDerivativeSigma)
            levelSets.SetAutoGenerateSpeedAdvection(1)
            levelSets.SetPropagationScaling(inflation * (-1))
            levelSets.SetCurvatureScaling(curvature)
            levelSets.SetAdvectionScaling(attraction * (-1))
        elif levelSetsType == 'curves':
            levelSets = vtkvmtkSegmentation.vtkvmtkCurvesLevelSetImageFilter()
            levelSets.SetFeatureImage(self.buildGradientBasedFeatureImage(originalImage))
            levelSets.SetDerivativeSigma(featureDerivativeSigma)
            levelSets.SetAutoGenerateSpeedAdvection(1)
            levelSets.SetPropagationScaling(inflation * (-1))
            levelSets.SetCurvatureScaling(curvature)
            levelSets.SetAdvectionScaling(attraction * (-1))
        elif levelSetsType == 'threshold':
            raise NotImplementedError()
        elif levelSetsType == 'laplacian':
            raise NotImplementedError()
        else:
            raise NameError('Unsupported LevelSetsType')

        levelSets.SetInputData(segmentationImage)
        levelSets.SetNumberOfIterations(numberOfIterations)
        levelSets.SetIsoSurfaceValue(isoSurfaceValue)
        levelSets.SetMaximumRMSError(maximumRMSError)
        levelSets.SetInterpolateSurfaceLocation(1)
        levelSets.SetUseImageSpacing(1)
        levelSets.Update()

        outImageData = vtk.vtkImageData()
        outImageData.DeepCopy(levelSets.GetOutput())

        return outImageData


    def buildGradientBasedFeatureImage(self, imageData):
        '''
        '''
        # import the vmtk libraries
        try:
            import vtkvmtkSegmentationPython as vtkvmtkSegmentation
        except ImportError:
            logging.error("Unable to import the SlicerVmtk libraries")

        derivativeSigma = 0.0
        sigmoidRemapping = 1

        cast = vtk.vtkImageCast()
        cast.SetInputData(imageData)
        cast.SetOutputScalarTypeToFloat()
        cast.Update()

        if (derivativeSigma > 0.0):
            gradientMagnitude = vtkvmtkSegmentation.vtkvmtkGradientMagnitudeRecursiveGaussianImageFilter()
            gradientMagnitude.SetInputData(cast.GetOutput())
            gradientMagnitude.SetSigma(derivativeSigma)
            gradientMagnitude.SetNormalizeAcrossScale(0)
            gradientMagnitude.Update()
        else:
            gradientMagnitude = vtkvmtkSegmentation.vtkvmtkGradientMagnitudeImageFilter()
            gradientMagnitude.SetInputData(cast.GetOutput())
            gradientMagnitude.Update()

        featureImage = None
        if sigmoidRemapping == 1:
            scalarRange = gradientMagnitude.GetOutput().GetPointData().GetScalars().GetRange()
            inputMinimum = scalarRange[0]
            inputMaximum = scalarRange[1]
            alpha = -(inputMaximum - inputMinimum) / 6.0
            beta = (inputMaximum + inputMinimum) / 2.0

            sigmoid = vtkvmtkSegmentation.vtkvmtkSigmoidImageFilter()
            sigmoid.SetInputData(gradientMagnitude.GetOutput())
            sigmoid.SetAlpha(alpha)
            sigmoid.SetBeta(beta)
            sigmoid.SetOutputMinimum(0.0)
            sigmoid.SetOutputMaximum(1.0)
            sigmoid.Update()
            featureImage = sigmoid.GetOutput()
        else:
            boundedReciprocal = vtkvmtkSegmentation.vtkvmtkBoundedReciprocalImageFilter()
            boundedReciprocal.SetInputData(gradientMagnitude.GetOutput())
            boundedReciprocal.Update()
            featureImage = boundedReciprocal.GetOutput()

        outImageData = vtk.vtkImageData()
        outImageData.DeepCopy(featureImage)

        return outImageData

    def buildSimpleLabelMap(self, image, inValue, outValue):

        threshold = vtk.vtkImageThreshold()
        threshold.SetInputData(image)
        threshold.ThresholdByLower(0)
        threshold.ReplaceInOn()
        threshold.ReplaceOutOn()
        threshold.SetOutValue(outValue)
        threshold.SetInValue(inValue)
        threshold.Update()

        outVolumeData = vtk.vtkImageData()
        outVolumeData.DeepCopy(threshold.GetOutput())

        return outVolumeData

    def marchingCubes(self, image, ijkToRasMatrix, threshold):


        transformIJKtoRAS = vtk.vtkTransform()
        transformIJKtoRAS.SetMatrix(ijkToRasMatrix)

        marchingCubes = vtk.vtkMarchingCubes()
        marchingCubes.SetInputData(image)
        marchingCubes.SetValue(0, threshold)
        marchingCubes.ComputeScalarsOn()
        marchingCubes.ComputeGradientsOn()
        marchingCubes.ComputeNormalsOn()
        marchingCubes.ReleaseDataFlagOn()
        marchingCubes.Update()


        if transformIJKtoRAS.GetMatrix().Determinant() < 0:
            reverser = vtk.vtkReverseSense()
            reverser.SetInputData(marchingCubes.GetOutput())
            reverser.ReverseNormalsOn()
            reverser.ReleaseDataFlagOn()
            reverser.Update()
            correctedOutput = reverser.GetOutput()
        else:
            correctedOutput = marchingCubes.GetOutput()

        transformer = vtk.vtkTransformPolyDataFilter()
        transformer.SetInputData(correctedOutput)
        transformer.SetTransform(transformIJKtoRAS)
        transformer.ReleaseDataFlagOn()
        transformer.Update()

        normals = vtk.vtkPolyDataNormals()
        normals.ComputePointNormalsOn()
        normals.SetInputData(transformer.GetOutput())
        normals.SetFeatureAngle(60)
        normals.SetSplitting(1)
        normals.ReleaseDataFlagOn()
        normals.Update()

        stripper = vtk.vtkStripper()
        stripper.SetInputData(normals.GetOutput())
        stripper.ReleaseDataFlagOff()
        stripper.Update()
        stripper.GetOutput()

        result = vtk.vtkPolyData()
        result.DeepCopy(stripper.GetOutput())

        return result


class Slicelet(object):
  """A slicer slicelet is a module widget that comes up in stand alone mode
  implemented as a python class.
  This class provides common wrapper functionality used by all slicer modlets.
  """
  # TODO: put this in a SliceletLib
  # TODO: parse command line arge


  def __init__(self, widgetClass=None):
    self.parent = qt.QFrame()
    self.parent.setLayout(qt.QVBoxLayout())

    # TODO: should have way to pop up python interactor
    self.buttons = qt.QFrame()
    self.buttons.setLayout(qt.QHBoxLayout())
    self.parent.layout().addWidget(self.buttons)
    self.addDataButton = qt.QPushButton("Add Data")
    self.buttons.layout().addWidget(self.addDataButton)
    self.addDataButton.connect("clicked()", slicer.app.ioManager().openAddDataDialog)
    self.loadSceneButton = qt.QPushButton("Load Scene")
    self.buttons.layout().addWidget(self.loadSceneButton)
    self.loadSceneButton.connect("clicked()", slicer.app.ioManager().openLoadSceneDialog)

    if widgetClass:
      self.widget = widgetClass(self.parent)
      self.widget.setup()
    self.parent.show()

class LevelSetSegmentationSlicelet(Slicelet):
  """ Creates the interface when module is run as a stand alone gui app.
  """

  def __init__(self):
    super(LevelSetSegmentationSlicelet, self).__init__(LevelSetSegmentationWidget)


if __name__ == "__main__":
  # TODO: need a way to access and parse command line arguments
  # TODO: ideally command line args should handle --xml

  import sys
  print(sys.argv)

  slicelet = LevelSetSegmentationSlicelet()
