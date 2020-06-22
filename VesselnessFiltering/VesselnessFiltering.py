# slicer imports
import os
import unittest
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
import logging

#
# Vesselness Filtering using VMTK based Tools
#

class VesselnessFiltering(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Vesselness Filtering"
    self.parent.categories = ["Vascular Modeling Toolkit"]
    self.parent.dependencies = []
    self.parent.contributors = ["Daniel Haehn (Boston Children's Hospital)", "Luca Antiga (Orobix)", "Steve Pieper (Isomics)", "Andras Lasso (PerkLab)"]
    self.parent.helpText = """Documentation is available <a href="https://github.com/vmtk/SlicerExtension-VMTK">here</a>.
"""
    self.parent.acknowledgementText = """
""" # replace with organization, grant and thanks.

    # Perform initializations that can only be performed when Slicer has started up
    slicer.app.connect("startupCompleted()", self.registerCustomVrPresets)

  def registerCustomVrPresets(self):
    moduleDir = os.path.dirname(self.parent.path)
    usPresetsScenePath = os.path.join(moduleDir, 'Resources', 'VesselnessVrPresets.mrml')

    # Read scene
    usPresetsScene = slicer.vtkMRMLScene()
    vrPropNode = slicer.vtkMRMLVolumePropertyNode()
    usPresetsScene.RegisterNodeClass(vrPropNode)
    usPresetsScene.SetURL(usPresetsScenePath)
    usPresetsScene.Connect()

    # Add presets to volume rendering logic
    vrLogic = slicer.modules.volumerendering.logic()
    presetsScene = vrLogic.GetPresetsScene()
    vrNodes = usPresetsScene.GetNodesByClass("vtkMRMLVolumePropertyNode")
    vrNodes.UnRegister(None)
    for itemNum in range(vrNodes.GetNumberOfItems()):
      node = vrNodes.GetItemAsObject(itemNum)
      vrLogic.AddPreset(node)

#
# VesselnessFilteringWidget
#


class VesselnessFilteringWidget(ScriptedLoadableModuleWidget):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent=None):
    self.logic = VesselnessFilteringLogic()
    ScriptedLoadableModuleWidget.__init__(self, parent)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)', self.onMRMLSceneChanged)

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    try:
      import vtkvmtkSegmentationPython as vtkvmtkSegmentation
    except ImportError:
      self.layout.addWidget(qt.QLabel("Failed to load VMTK libraries"))
      return

    #
    # the I/O panel
    #

    ioCollapsibleButton = ctk.ctkCollapsibleButton()
    ioCollapsibleButton.text = "Input/Output"
    self.layout.addWidget(ioCollapsibleButton)
    ioFormLayout = qt.QFormLayout(ioCollapsibleButton)

    # inputVolume selector
    self.inputVolumeNodeSelector = slicer.qMRMLNodeComboBox()
    self.inputVolumeNodeSelector.objectName = 'inputVolumeNodeSelector'
    self.inputVolumeNodeSelector.toolTip = "Select the input volume."
    self.inputVolumeNodeSelector.nodeTypes = ['vtkMRMLScalarVolumeNode']
    self.inputVolumeNodeSelector.noneEnabled = False
    self.inputVolumeNodeSelector.addEnabled = False
    self.inputVolumeNodeSelector.removeEnabled = False
    ioFormLayout.addRow("Input Volume:", self.inputVolumeNodeSelector)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                        self.inputVolumeNodeSelector, 'setMRMLScene(vtkMRMLScene*)')

    # seed selector
    self.seedFiducialsNodeSelector = slicer.qSlicerSimpleMarkupsWidget()
    self.seedFiducialsNodeSelector.objectName = 'seedFiducialsNodeSelector'
    self.seedFiducialsNodeSelector = slicer.qSlicerSimpleMarkupsWidget()
    self.seedFiducialsNodeSelector.objectName = 'seedFiducialsNodeSelector'
    self.seedFiducialsNodeSelector.toolTip = "Select a point in the largest vessel. Preview will be shown around this point. This is point is also used for determining maximum vessel diameter if automatic filtering parameters computation is enabled."
    self.seedFiducialsNodeSelector.setNodeBaseName("DiameterSeed")
    self.seedFiducialsNodeSelector.tableWidget().hide()
    self.seedFiducialsNodeSelector.defaultNodeColor = qt.QColor(255,0,0) # red
    self.seedFiducialsNodeSelector.markupsSelectorComboBox().noneEnabled = False
    self.seedFiducialsNodeSelector.markupsPlaceWidget().placeMultipleMarkups = slicer.qSlicerMarkupsPlaceWidget.ForcePlaceSingleMarkup
    ioFormLayout.addRow("Seed point:", self.seedFiducialsNodeSelector)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                        self.seedFiducialsNodeSelector, 'setMRMLScene(vtkMRMLScene*)')

    # outputVolume selector
    self.outputVolumeNodeSelector = slicer.qMRMLNodeComboBox()
    self.outputVolumeNodeSelector.toolTip = "Select the output labelmap."
    self.outputVolumeNodeSelector.nodeTypes = ['vtkMRMLScalarVolumeNode']
    self.outputVolumeNodeSelector.baseName = "VesselnessFiltered"
    self.outputVolumeNodeSelector.noneEnabled = True
    self.outputVolumeNodeSelector.noneDisplay = "Create new volume"
    self.outputVolumeNodeSelector.addEnabled = True
    self.outputVolumeNodeSelector.selectNodeUponCreation = True
    self.outputVolumeNodeSelector.removeEnabled = True
    ioFormLayout.addRow("Output Volume:", self.outputVolumeNodeSelector)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                        self.outputVolumeNodeSelector, 'setMRMLScene(vtkMRMLScene*)')

    #
    # Advanced area
    #

    self.advancedCollapsibleButton = ctk.ctkCollapsibleButton()
    self.advancedCollapsibleButton.text = "Advanced"
    self.advancedCollapsibleButton.collapsed = True
    self.layout.addWidget(self.advancedCollapsibleButton)
    advancedFormLayout = qt.QFormLayout(self.advancedCollapsibleButton)

    # previewVolume selector
    self.previewVolumeNodeSelector = slicer.qMRMLNodeComboBox()
    self.previewVolumeNodeSelector.toolTip = "Select the preview volume."
    self.previewVolumeNodeSelector.nodeTypes = ['vtkMRMLScalarVolumeNode']
    self.previewVolumeNodeSelector.baseName = "VesselnessPreview"
    self.previewVolumeNodeSelector.noneEnabled = True
    self.previewVolumeNodeSelector.noneDisplay = "Create new volume"
    self.previewVolumeNodeSelector.addEnabled = True
    self.previewVolumeNodeSelector.selectNodeUponCreation = True
    self.previewVolumeNodeSelector.removeEnabled = True
    advancedFormLayout.addRow("Preview volume:", self.previewVolumeNodeSelector)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                        self.previewVolumeNodeSelector, 'setMRMLScene(vtkMRMLScene*)')

    self.displayThresholdSlider = ctk.ctkSliderWidget()
    self.displayThresholdSlider.decimals = 2
    self.displayThresholdSlider.minimum = 0
    self.displayThresholdSlider.maximum = 1.0
    self.displayThresholdSlider.singleStep = 0.01
    self.displayThresholdSlider.toolTip = "Voxels below this vesselness value will be hidden. It does not change the voxel values, only how the vesselness volume is displayed."
    advancedFormLayout.addRow("Display threshold:", self.displayThresholdSlider)
    self.displayThresholdSlider.connect('valueChanged(double)', self.onDisplayThresholdChanged)

    self.previewVolumeDiameterVoxelSlider = ctk.ctkSliderWidget()
    self.previewVolumeDiameterVoxelSlider.decimals = 0
    self.previewVolumeDiameterVoxelSlider.minimum = 10
    self.previewVolumeDiameterVoxelSlider.maximum = 200
    self.previewVolumeDiameterVoxelSlider.singleStep = 5
    self.previewVolumeDiameterVoxelSlider.suffix = " voxels"
    self.previewVolumeDiameterVoxelSlider.toolTip = "Diameter of the preview area in voxels."
    advancedFormLayout.addRow("Preview volume size:", self.previewVolumeDiameterVoxelSlider)

    # detect filterint parameters
    self.detectPushButton = qt.QPushButton()
    self.detectPushButton.text = "Compute vessel diameters and contrast from seed point"
    self.detectPushButton.checkable = True
    self.detectPushButton.checked = True
    advancedFormLayout.addRow(self.detectPushButton)
    self.detectPushButton.connect("clicked()", self.onNodeSelectionChanged)

    self.minimumDiameterSpinBox = qt.QSpinBox()
    self.minimumDiameterSpinBox.minimum = 1
    self.minimumDiameterSpinBox.maximum = 1000
    self.minimumDiameterSpinBox.singleStep = 1
    self.minimumDiameterSpinBox.suffix = " voxels"
    self.minimumDiameterSpinBox.enabled = False
    self.minimumDiameterSpinBox.toolTip = "Tubular structures that have minimum this diameter will be enhanced."
    advancedFormLayout.addRow("Minimum vessel diameter:", self.minimumDiameterSpinBox)
    self.detectPushButton.connect("toggled(bool)", self.minimumDiameterSpinBox.setDisabled)

    self.maximumDiameterSpinBox = qt.QSpinBox()
    self.maximumDiameterSpinBox.minimum = 0
    self.maximumDiameterSpinBox.maximum = 1000
    self.maximumDiameterSpinBox.singleStep = 1
    self.maximumDiameterSpinBox.suffix = " voxels"
    self.maximumDiameterSpinBox.enabled = False
    self.maximumDiameterSpinBox.toolTip = "Tubular structures that have maximum this diameter will be enhanced."
    advancedFormLayout.addRow("Maximum vessel diameter:", self.maximumDiameterSpinBox)
    self.detectPushButton.connect("toggled(bool)", self.maximumDiameterSpinBox.setDisabled)

    self.contrastSlider = ctk.ctkSliderWidget()
    self.contrastSlider.decimals = 0
    self.contrastSlider.minimum = 0
    self.contrastSlider.maximum = 500
    self.contrastSlider.singleStep = 10
    self.contrastSlider.enabled = False
    self.contrastSlider.toolTip = "If the intensity contrast in the input image between vessel and background is high, choose a high value else choose a low value."
    advancedFormLayout.addRow("Vessel contrast:", self.contrastSlider)
    self.detectPushButton.connect("toggled(bool)", self.contrastSlider.setDisabled)

    self.suppressPlatesSlider = ctk.ctkSliderWidget()
    self.suppressPlatesSlider.decimals = 0
    self.suppressPlatesSlider.minimum = 0
    self.suppressPlatesSlider.maximum = 100
    self.suppressPlatesSlider.singleStep = 1
    self.suppressPlatesSlider.suffix = " %"
    self.suppressPlatesSlider.toolTip = "A higher value filters out more plate-like structures."
    advancedFormLayout.addRow("Suppress plates:", self.suppressPlatesSlider)

    self.suppressBlobsSlider = ctk.ctkSliderWidget()
    self.suppressBlobsSlider.decimals = 0
    self.suppressBlobsSlider.minimum = 0
    self.suppressBlobsSlider.maximum = 100
    self.suppressBlobsSlider.singleStep = 1
    self.suppressBlobsSlider.suffix = " %"
    self.suppressBlobsSlider.toolTip = "A higher value filters out more blob-like structures."
    advancedFormLayout.addRow("Suppress blobs:", self.suppressBlobsSlider)

    #
    # Reset, preview and apply buttons
    #

    self.buttonBox = qt.QDialogButtonBox()
    self.resetButton = self.buttonBox.addButton(self.buttonBox.RestoreDefaults)
    self.resetButton.toolTip = "Click to reset all input elements to default."
    self.previewButton = self.buttonBox.addButton(self.buttonBox.Discard)
    self.previewButton.setIcon(qt.QIcon())
    self.previewButton.text = "Preview"
    self.startButton = self.buttonBox.addButton(self.buttonBox.Apply)
    self.startButton.setIcon(qt.QIcon())
    self.startButton.text = "Start"
    self.startButton.enabled = False
    self.layout.addWidget(self.buttonBox)
    self.resetButton.connect("clicked()", self.restoreDefaults)
    self.previewButton.connect("clicked()", self.onPreviewButtonClicked)
    self.startButton.connect("clicked()", self.onStartButtonClicked)

    self.inputVolumeNodeSelector.setMRMLScene(slicer.mrmlScene)
    self.seedFiducialsNodeSelector.setMRMLScene(slicer.mrmlScene)
    self.outputVolumeNodeSelector.setMRMLScene(slicer.mrmlScene)
    self.previewVolumeNodeSelector.setMRMLScene(slicer.mrmlScene)

    self.inputVolumeNodeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onNodeSelectionChanged)
    self.seedFiducialsNodeSelector.markupsSelectorComboBox().connect("currentNodeChanged(vtkMRMLNode*)", self.onNodeSelectionChanged)
    self.seedFiducialsNodeSelector.connect("updateFinished()", self.onNodeSelectionChanged)

    # set default values
    self.restoreDefaults()

    self.onNodeSelectionChanged()

    # compress the layout
    self.layout.addStretch(1)

  def onMRMLSceneChanged(self):
    logging.debug("onMRMLSceneChanged")
    self.restoreDefaults()

  def onNodeSelectionChanged(self, node=None):
    if not self.inputVolumeNodeSelector.currentNode():
      self.previewButton.enabled = False
      self.startButton.enabled = False
      return

    seedSelected = self.seedFiducialsNodeSelector.currentNode() and self.seedFiducialsNodeSelector.currentNode().GetNumberOfFiducials()>0

    if seedSelected:
      self.previewButton.toolTip = "Click to refresh the preview."
      self.previewButton.enabled = True
    else:
      self.previewButton.toolTip = "Select a seed point to specify preview region and compute filtering parameters automatically."
      self.previewButton.enabled = False

    if self.detectPushButton.checked and not seedSelected:
      self.startButton.toolTip = "Select a seed point to allow automatic computation of filtering parameters."
      self.startButton.enabled = False
    else:
      self.startButton.toolTip = "Click to start the vessel enhancement filtering."
      self.startButton.enabled = True

  def onDisplayThresholdChanged(self, value):
    for volume in [self.outputVolumeNodeSelector.currentNode(), self.previewVolumeNodeSelector.currentNode()]:
      if volume is not None and volume.GetDisplayNode() is not None:
        volume.GetDisplayNode().AutoThresholdOff()
        volume.GetDisplayNode().ApplyThresholdOn()
        volume.GetDisplayNode().SetLowerThreshold(value)

  def onStartButtonClicked(self):
    if self.detectPushButton.checked:
      self.calculateParameters()

    # this is no preview
    qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)
    self.start(False)
    qt.QApplication.restoreOverrideCursor()

  def onPreviewButtonClicked(self):
      if self.detectPushButton.checked:
        self.calculateParameters()

      # calculate the preview
      qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)
      self.start(True)
      qt.QApplication.restoreOverrideCursor()

      # activate startButton
      self.startButton.enabled = True

  def calculateParameters(self):
    logging.debug("calculateParameters")

    currentVolumeNode = self.inputVolumeNodeSelector.currentNode()
    if not currentVolumeNode:
      raise ValueError("Input volume node is invalid")

    currentSeedsNode = self.seedFiducialsNodeSelector.currentNode()
    if not currentVolumeNode:
      raise ValueError("Input seed node is invalid")

    vesselPositionIJK = self.logic.getIJKFromRAS(currentVolumeNode, self.logic.getSeedPositionRAS(currentSeedsNode))

    # we detect the diameter in IJK space (image has spacing 1,1,1) with IJK coordinates
    detectedDiameter = self.logic.getDiameter(currentVolumeNode.GetImageData(), vesselPositionIJK)
    logging.debug("Diameter detected: " + str(detectedDiameter))

    contrastMeasure = self.logic.calculateContrastMeasure(currentVolumeNode.GetImageData(), vesselPositionIJK, detectedDiameter)
    logging.debug("Contrast measure: " + str(contrastMeasure))

    self.maximumDiameterSpinBox.value = detectedDiameter
    self.contrastSlider.value = contrastMeasure

  def restoreDefaults(self):
    logging.debug("restoreDefaults")

    self.detectPushButton.checked = True
    self.previewVolumeDiameterVoxelSlider.value = 20
    self.minimumDiameterSpinBox.value = 1
    self.maximumDiameterSpinBox.value = 7
    self.suppressPlatesSlider.value = 10
    self.suppressBlobsSlider.value = 10
    self.contrastSlider.value = 100
    self.displayThresholdSlider.value = 0.25

    self.startButton.enabled = False


  def start(self, preview=False):
    # first we need the nodes
    currentVolumeNode = self.inputVolumeNodeSelector.currentNode()
    currentSeedsNode = self.seedFiducialsNodeSelector.currentNode()

    # Determine output volume node
    if preview:
      # if previewMode, get the node selector of the preview volume
      currentOutputVolumeNodeSelector = self.previewVolumeNodeSelector
      # preview region
      previewRegionSizeVoxel = self.previewVolumeDiameterVoxelSlider.value
      previewRegionCenterRAS = self.logic.getSeedPositionRAS(currentSeedsNode)
    else:
      currentOutputVolumeNodeSelector = self.outputVolumeNodeSelector
      # preview region
      previewRegionSizeVoxel = -1
      previewRegionCenterRAS = None
    currentOutputVolumeNode = currentOutputVolumeNodeSelector.currentNode()

   # Create output voluem if does not exist yet
    if not currentOutputVolumeNode or currentOutputVolumeNode.GetID() == currentVolumeNode.GetID():
      newVolumeNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLScalarVolumeNode")
      newVolumeNode.UnRegister(None)
      newVolumeNode.SetName(slicer.mrmlScene.GetUniqueNameByString(currentOutputVolumeNodeSelector.baseName))
      currentOutputVolumeNode = slicer.mrmlScene.AddNode(newVolumeNode)
      currentOutputVolumeNode.CreateDefaultDisplayNodes()

      outputDisplayNode = currentOutputVolumeNode.GetDisplayNode()

      # Set threshold
      outputDisplayNode.AutoThresholdOff()
      lowerThreshold = self.displayThresholdSlider.value
      outputDisplayNode.SetLowerThreshold(lowerThreshold)
      outputDisplayNode.SetUpperThreshold(1.0)
      outputDisplayNode.ApplyThresholdOn()

      # Set red colormap
      outputDisplayNode.SetAndObserveColorNodeID('vtkMRMLColorTableNodeRed')
      outputDisplayNode.AutoWindowLevelOff()
      outputDisplayNode.SetWindowLevelMinMax(-0.6, 1.0)

      currentOutputVolumeNodeSelector.setCurrentNode(currentOutputVolumeNode)
      fitToAllSliceViews = True
    else:
      fitToAllSliceViews = False

    # we need to convert diameter to mm, we use the minimum spacing to multiply the voxel value
    minimumDiameterMm = self.minimumDiameterSpinBox.value * min(currentVolumeNode.GetSpacing())
    maximumDiameterMm = self.maximumDiameterSpinBox.value * min(currentVolumeNode.GetSpacing())

    alpha = self.logic.alphaFromSuppressPlatesPercentage(self.suppressPlatesSlider.value)
    beta = self.logic.betaFromSuppressBlobsPercentage(self.suppressBlobsSlider.value)
    contrastMeasure = self.contrastSlider.value

    self.logic.computeVesselnessVolume(currentVolumeNode, currentOutputVolumeNode, previewRegionCenterRAS, previewRegionSizeVoxel,
      minimumDiameterMm, maximumDiameterMm, alpha, beta, contrastMeasure)

    if fitToAllSliceViews:

      if preview:
        # Set up FOV to show preview
        slicer.util.setSliceViewerLayers(background=currentOutputVolumeNode)
        slicer.app.applicationLogic().FitSliceToAll()
        # jump all sliceViewers to the fiducial point, if one was used
        slicer.modules.markups.logic().JumpSlicesToNthPointInMarkup(currentSeedsNode.GetID(), currentSeedsNode.GetNumberOfFiducials()-1)
      else:
        slicer.util.setSliceViewerLayers(background=currentVolumeNode, foreground=currentOutputVolumeNode, foregroundOpacity=0.8)
        slicer.app.applicationLogic().FitSliceToAll()

      # Set up layer order and opacity
      slicer.util.setSliceViewerLayers(background=currentVolumeNode, foreground=currentOutputVolumeNode, foregroundOpacity=0.8)

    else:

      # Set up layer order
      slicer.util.setSliceViewerLayers(background=currentVolumeNode, foreground=currentOutputVolumeNode)

class VesselnessFilteringLogic(ScriptedLoadableModuleLogic):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget.
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self):
    ScriptedLoadableModuleLogic.__init__(self)
    # the pointer to the logic

  def getSeedPositionRAS(self, seedNode):
    if not seedNode:
        raise ValueError("Input seed node is invalid")
    n = seedNode.GetNumberOfFiducials()
    seedPositionRAS = [0, 0, 0]
    seedNode.GetNthFiducialPosition(n-1,seedPositionRAS)
    return seedPositionRAS

  def getIJKFromRAS(self, volumeNode, ras):
    ijk = VesselnessFilteringLogic.ConvertRAStoIJK(volumeNode, ras)
    return [int(ijk[0]), int(ijk[1]), int(ijk[2])]

  def alphaFromSuppressPlatesPercentage(self, suppressPlatesPercentage):
    return 0.000 + 3.0 * pow(suppressPlatesPercentage/100.0,2)

  def betaFromSuppressBlobsPercentage(self, suppressBlobsPercentage):
    return 0.001 + 1.0 * pow((100.0-suppressBlobsPercentage)/100.0,2)

  def computeVesselnessVolume(self, currentVolumeNode, currentOutputVolumeNode,
    previewRegionCenterRAS=None, previewRegionSizeVoxel=-1, minimumDiameterMm=0, maximumDiameterMm=25,
    alpha=0.3, beta=0.3, contrastMeasure=150):

    logging.debug("Vesselness filtering started: diameter min={0}, max={1}, alpha={2}, beta={3}, contrastMeasure={4}".format(
      minimumDiameterMm, maximumDiameterMm, alpha, beta, contrastMeasure))

    if not currentVolumeNode:
      raise ValueError("Output volume node is invalid")

    # this image will later hold the inputImage
    inImage = vtk.vtkImageData()

    # if we are in previewMode, we have to cut the ROI first for speed
    if previewRegionSizeVoxel>0:
        # we extract the ROI of currentVolumeNode and save it to currentOutputVolumeNode
        # we work in RAS space
        imageclipper = vtk.vtkImageConstantPad()
        imageclipper.SetInputData(currentVolumeNode.GetImageData())
        previewRegionCenterIJK = self.getIJKFromRAS(currentVolumeNode, previewRegionCenterRAS)
        previewRegionRadiusVoxel = int(round(previewRegionSizeVoxel/2+0.5))
        imageclipper.SetOutputWholeExtent(
          previewRegionCenterIJK[0]-previewRegionRadiusVoxel, previewRegionCenterIJK[0]+previewRegionRadiusVoxel,
          previewRegionCenterIJK[1]-previewRegionRadiusVoxel, previewRegionCenterIJK[1]+previewRegionRadiusVoxel,
          previewRegionCenterIJK[2]-previewRegionRadiusVoxel, previewRegionCenterIJK[2]+previewRegionRadiusVoxel)
        imageclipper.Update()
        currentOutputVolumeNode.SetAndObserveImageData(imageclipper.GetOutput())
        currentOutputVolumeNode.CopyOrientation(currentVolumeNode)
        currentOutputVolumeNode.ShiftImageDataExtentToZeroStart()
        inImage.DeepCopy(currentOutputVolumeNode.GetImageData())
    else:
        # there was no ROI extraction, so just clone the inputImage
        inImage.DeepCopy(currentVolumeNode.GetImageData())
        currentOutputVolumeNode.CopyOrientation(currentVolumeNode)

    # temporarily set spacing to allow vesselness computation performed in physical space
    inImage.SetSpacing(currentVolumeNode.GetSpacing())

    # we now compute the vesselness in RAS space, inImage has spacing and origin attached, the diameters are converted to mm
    # we use RAS space to support anisotropic datasets

    import vtkvmtkSegmentationPython as vtkvmtkSegmentation

    cast = vtk.vtkImageCast()
    cast.SetInputData(inImage)
    cast.SetOutputScalarTypeToFloat()
    cast.Update()
    inImage = cast.GetOutput()

    discretizationSteps = 5

    v = vtkvmtkSegmentation.vtkvmtkVesselnessMeasureImageFilter()
    v.SetInputData(inImage)
    v.SetSigmaMin(minimumDiameterMm)
    v.SetSigmaMax(maximumDiameterMm)
    v.SetNumberOfSigmaSteps(discretizationSteps)
    v.SetAlpha(alpha)
    v.SetBeta(beta)
    v.SetGamma(contrastMeasure)
    v.Update()

    outImage = vtk.vtkImageData()
    outImage.DeepCopy(v.GetOutput())
    outImage.GetPointData().GetScalars().Modified()

    # restore Slicer-compliant image spacing
    outImage.SetSpacing(1, 1, 1)

    # we set the outImage which has spacing 1,1,1. The ijkToRas matrix of the node will take care of that
    currentOutputVolumeNode.SetAndObserveImageData(outImage)

    # save which volume node vesselness filterint result was saved to
    currentVolumeNode.SetAndObserveNodeReferenceID("Vesselness", currentOutputVolumeNode.GetID())

    logging.debug("Vesselness filtering completed")


  def getDiameter(self, image, ijk):
      edgeImage = self.performLaplaceOfGaussian(image)

      foundDiameter = False

      # was cmp in python2 https://stackoverflow.com/questions/22490366/how-to-use-cmp-in-python-3
      compareValues = lambda a,b: (a > b) - (a < b) 

      edgeImageSeedValue = edgeImage.GetScalarComponentAsFloat(ijk[0], ijk[1], ijk[2], 0)
      seedValueSign = compareValues(edgeImageSeedValue, 0)  # returns 1 if >0 or -1 if <0

      # the list of hits
      # [left, right, top, bottom, front, back]
      hits = [False, False, False, False, False, False]

      distanceFromSeed = 1
      while not foundDiameter:

          if (distanceFromSeed >= edgeImage.GetDimensions()[0]
              or distanceFromSeed >= edgeImage.GetDimensions()[1]
              or distanceFromSeed >= edgeImage.GetDimensions()[2]):
              # we are out of bounds
              break

          # get the values for the lookahead directions in the edgeImage
          edgeValues = [edgeImage.GetScalarComponentAsFloat(ijk[0] - distanceFromSeed, ijk[1], ijk[2], 0),  # left
                        edgeImage.GetScalarComponentAsFloat(ijk[0] + distanceFromSeed, ijk[1], ijk[2], 0),  # right
                        edgeImage.GetScalarComponentAsFloat(ijk[0], ijk[1] + distanceFromSeed, ijk[2], 0),  # top
                        edgeImage.GetScalarComponentAsFloat(ijk[0], ijk[1] - distanceFromSeed, ijk[2], 0),  # bottom
                        edgeImage.GetScalarComponentAsFloat(ijk[0], ijk[1], ijk[2] + distanceFromSeed, 0),  # front
                        edgeImage.GetScalarComponentAsFloat(ijk[0], ijk[1], ijk[2] - distanceFromSeed, 0)]  # back

          # first loop, check if we have hits
          for v in range(len(edgeValues)):

              if not hits[v] and compareValues(edgeValues[v], 0) != seedValueSign:
                  # hit
                  hits[v] = True

          # now check if we have two hits in opposite directions
          if hits[0] and hits[1]:
              # we have the diameter!
              foundDiameter = True
              break

          if hits[2] and hits[3]:
              foundDiameter = True
              break

          if hits[4] and hits[5]:
              foundDiameter = True
              break

          # increase distance from seed for next iteration
          distanceFromSeed += 1

      # we now just return the distanceFromSeed
      # if the diameter was not detected properly, this can equal one of the image dimensions
      return distanceFromSeed


  def performLaplaceOfGaussian(self, image):
      gaussian = vtk.vtkImageGaussianSmooth()
      gaussian.SetInputData(image)
      gaussian.Update()

      laplacian = vtk.vtkImageLaplacian()
      laplacian.SetInputData(gaussian.GetOutput())
      laplacian.Update()

      outImageData = vtk.vtkImageData()
      outImageData.DeepCopy(laplacian.GetOutput())

      return outImageData


  def calculateContrastMeasure(self, image, ijk, diameter):
      seedValue = image.GetScalarComponentAsFloat(ijk[0], ijk[1], ijk[2], 0)

      outsideValues = [seedValue - image.GetScalarComponentAsFloat(ijk[0] + (2 * diameter), ijk[1], ijk[2], 0),  # right
                       seedValue - image.GetScalarComponentAsFloat(ijk[0] - (2 * diameter), ijk[1], ijk[2], 0),  # left
                       seedValue - image.GetScalarComponentAsFloat(ijk[0], ijk[1] + (2 * diameter), ijk[2], 0),  # top
                       seedValue - image.GetScalarComponentAsFloat(ijk[0], ijk[1] - (2 * diameter), ijk[2], 0),  # bottom
                       seedValue - image.GetScalarComponentAsFloat(ijk[0], ijk[1], ijk[2] + (2 * diameter), 0),  # front
                       seedValue - image.GetScalarComponentAsFloat(ijk[0], ijk[1], ijk[2] - (2 * diameter), 0)]  # back

      differenceValue = max(outsideValues)

      contrastMeasure = differenceValue / 10  # get 1/10 of it

      return 2 * contrastMeasure


  @staticmethod
  def ConvertRAStoIJK(volumeNode,rasCoordinates):
      rasToIjkMatrix = vtk.vtkMatrix4x4()
      volumeNode.GetRASToIJKMatrix(rasToIjkMatrix)

      # the RAS coordinates need to be 4
      if len(rasCoordinates) < 4:
          rasCoordinates.append(1)

      ijkCoordinates = rasToIjkMatrix.MultiplyPoint(rasCoordinates)

      return ijkCoordinates


class VesselnessFilteringTest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setUp(self):
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    slicer.mrmlScene.Clear(0)
    import SampleData
    sampleDataLogic = SampleData.SampleDataLogic()
    self.inputAngioVolume = sampleDataLogic.downloadCTACardio()

    self.vesselPositionRas = [176.9, -17.4, 52.7]

    # make the output volume appear in all the slice views
    selectionNode = slicer.app.applicationLogic().GetSelectionNode()
    selectionNode.SetReferenceActiveVolumeID(self.inputAngioVolume.GetID())
    slicer.app.applicationLogic().PropagateVolumeSelection(1)

  def runTest(self):
    """Run as few or as many tests as needed here.
    """
    self.setUp()
    self.test_BasicVesselSegmentation()

  def test_BasicVesselSegmentation(self):
    self.delayDisplay("Testing BasicVesselSegmentation")

    logic = VesselnessFilteringLogic()

    vesselPositionIJK = logic.getIJKFromRAS(self.inputAngioVolume, self.vesselPositionRas)
    detectedDiameter = logic.getDiameter(self.inputAngioVolume.GetImageData(), vesselPositionIJK)
    logging.info("Diameter detected: " + str(detectedDiameter))

    contrastMeasure = logic.calculateContrastMeasure(self.inputAngioVolume.GetImageData(), vesselPositionIJK, detectedDiameter)
    logging.info("Contrast measure: " + str(contrastMeasure))

    previewVolumeNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLScalarVolumeNode")
    previewVolumeNode.UnRegister(None)
    previewVolumeNode.SetName(slicer.mrmlScene.GetUniqueNameByString('VesselnessPreview'))
    previewVolumeNode = slicer.mrmlScene.AddNode(previewVolumeNode)
    previewVolumeNode.CreateDefaultDisplayNodes()

    logic.computeVesselnessVolume(self.inputAngioVolume, previewVolumeNode, previewRegionCenterRAS=self.vesselPositionRas, previewRegionSizeVoxel=60, minimumDiameterMm=0.2, maximumDiameterMm=detectedDiameter, alpha=0.03, beta=0.03, contrastMeasure=200)

    slicer.util.setSliceViewerLayers(background=self.inputAngioVolume, foreground=previewVolumeNode)

    self.delayDisplay('Testing BasicVesselSegmentation completed successfully')

class Slicelet(object):
  """A slicer slicelet is a module widget that comes up in stand alone mode
  implemented as a python class.
  This class provides common wrapper functionality used by all slicer modlets.
  """
  # TODO: parse command line args

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

class VesselnessFilteringSlicelet(Slicelet):
  """ Creates the interface when module is run as a stand alone gui app.
  """

  def __init__(self):
    super(VesselnessFilteringSlicelet, self).__init__(VesselnessFilteringWidget)


if __name__ == "__main__":
 # TODO: need a way to access and parse command line arguments
 # TODO: ideally command line args should handle --xml

 import sys
 print(sys.argv)

 slicelet = VesselnessFilteringSlicelet()
