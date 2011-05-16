# slicer imports
from __main__ import vtk, qt, ctk, slicer

# vmtk includes
import SlicerVmtk4CommonLib

#
# Level Set Segmentation using VMTK based Tools
#

class LevelSetSegmentation:
  def __init__(self, parent):
    parent.title = "Level Set Segmentation"
    parent.category = "Vascular Modeling Toolkit"
    parent.contributor = "Daniel Haehn <haehn@bwh.harvard.edu>"
    parent.helpText = """dsfdsf"""
    parent.acknowledgementText = """sdfsdfdsf"""
    self.parent = parent


class LevelSetSegmentationWidget:
  def __init__(self, parent=None):
    if not parent:
      self.parent = slicer.qMRMLWidget()
      self.parent.setLayout(qt.QVBoxLayout())
      self.parent.setMRMLScene(slicer.mrmlScene)      
    else:
      self.parent = parent
    self.layout = self.parent.layout()

    if not parent:
      self.setup()
      self.inputVolumeNodeSelector.setMRMLScene(slicer.mrmlScene)
      self.seedFiducialsNodeSelector.setMRMLScene(slicer.mrmlScene)
      self.parent.show()
      
    # register default slots
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)', self.onMRMLSceneChanged)      
    
    # the pointer to the logic
    self.__logic = None
    
    # this flag is 1 if there is an update in progress
    
    self.__updating = 1

    
  def GetLogic(self):
    '''
    '''
    if not self.__logic:
        
        self.__logic = SlicerVmtk4CommonLib.LevelSetSegmentationLogic()
        
    return self.__logic
    
    
  def setup(self):

    # check if the SlicerVmtk4 module is installed properly
    #self.__vmtkInstalled = SlicerVmtk4CommonLib.Helper.CheckIfVmtkIsInstalled()
    #Helper.Debug("VMTK found: " + self.__vmtkInstalled)

    #
    # the I/O panel
    #
    
    ioCollapsibleButton = ctk.ctkCollapsibleButton()
    ioCollapsibleButton.text = "Input/Output"
    self.layout.addWidget(ioCollapsibleButton)
    
    ioFormLayout = qt.QFormLayout(ioCollapsibleButton)
    
    # inputVolume selector
    self.__inputVolumeNodeSelector = slicer.qMRMLNodeComboBox()
    self.__inputVolumeNodeSelector.objectName = 'inputVolumeNodeSelector'
    self.__inputVolumeNodeSelector.toolTip = "Select the input volume."
    self.__inputVolumeNodeSelector.nodeTypes = ['vtkMRMLScalarVolumeNode']
    self.__inputVolumeNodeSelector.noneEnabled = False
    self.__inputVolumeNodeSelector.addEnabled = False
    self.__inputVolumeNodeSelector.removeEnabled = False
    ioFormLayout.addRow("Input Volume:", self.__inputVolumeNodeSelector)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                        self.__inputVolumeNodeSelector, 'setMRMLScene(vtkMRMLScene*)')
    self.__inputVolumeNodeSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.onInputVolumeChanged)
    
    # seed selector
    self.__seedFiducialsNodeSelector = slicer.qMRMLNodeComboBox()
    self.__seedFiducialsNodeSelector.objectName = 'seedFiducialsNodeSelector'
    self.__seedFiducialsNodeSelector.toolTip = "Select a hierarchy containing the fiducials to use as Seeds."
    self.__seedFiducialsNodeSelector.nodeTypes = ['vtkMRMLAnnotationHierarchyNode']
    self.__seedFiducialsNodeSelector.baseName = "Seeds"
    self.__seedFiducialsNodeSelector.noneEnabled = False
    self.__seedFiducialsNodeSelector.addEnabled = False
    self.__seedFiducialsNodeSelector.removeEnabled = False
    ioFormLayout.addRow("Seeds:", self.__seedFiducialsNodeSelector)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                        self.__seedFiducialsNodeSelector, 'setMRMLScene(vtkMRMLScene*)')     
    
    self.__ioAdvancedToggle = qt.QCheckBox("Show Advanced I/O Properties")
    self.__ioAdvancedToggle.setChecked(False)
    ioFormLayout.addRow(self.__ioAdvancedToggle)
    
    #
    # I/O advanced panel
    #
    
    self.__ioAdvancedPanel = qt.QFrame(ioCollapsibleButton)
    self.__ioAdvancedPanel.hide()
    self.__ioAdvancedPanel.setFrameStyle(6)
    ioFormLayout.addRow(self.__ioAdvancedPanel)
    self.__ioAdvancedToggle.connect("clicked()", self.onIOAdvancedToggle) 
    
    ioAdvancedFormLayout = qt.QFormLayout(self.__ioAdvancedPanel)

    # stopper selector
    self.__stopperFiducialsNodeSelector = slicer.qMRMLNodeComboBox()
    self.__stopperFiducialsNodeSelector.objectName = 'stopperFiducialsNodeSelector'
    self.__stopperFiducialsNodeSelector.toolTip = "Select a hierarchy containing the fiducials to use as Stoppers. Whenever one stopper is reached, the segmentation stops."
    self.__stopperFiducialsNodeSelector.nodeTypes = ['vtkMRMLAnnotationHierarchyNode']
    self.__stopperFiducialsNodeSelector.baseName = "Stoppers"
    self.__stopperFiducialsNodeSelector.noneEnabled = False
    self.__stopperFiducialsNodeSelector.addEnabled = True
    self.__stopperFiducialsNodeSelector.removeEnabled = False
    ioAdvancedFormLayout.addRow("Stoppers:", self.__stopperFiducialsNodeSelector)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                        self.__stopperFiducialsNodeSelector, 'setMRMLScene(vtkMRMLScene*)')     
    
    # outputVolume selector
    self.__outputVolumeNodeSelector = slicer.qMRMLNodeComboBox()
    self.__outputVolumeNodeSelector.toolTip = "Select the output labelmap."
    self.__outputVolumeNodeSelector.nodeTypes = ['vtkMRMLScalarVolumeNode']
    self.__outputVolumeNodeSelector.baseName = "LevelSetSegmentation"
    self.__outputVolumeNodeSelector.noneEnabled = False
    self.__outputVolumeNodeSelector.addEnabled = True
    self.__outputVolumeNodeSelector.selectNodeUponCreation = True
    self.__outputVolumeNodeSelector.addAttribute( "vtkMRMLScalarVolumeNode", "LabelMap", "1" )
    self.__outputVolumeNodeSelector.removeEnabled = True
    ioAdvancedFormLayout.addRow("Output Labelmap:", self.__outputVolumeNodeSelector)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                        self.__outputVolumeNodeSelector, 'setMRMLScene(vtkMRMLScene*)')   
    
    # outputModel selector
    self.__outputModelNodeSelector = slicer.qMRMLNodeComboBox()
    self.__outputModelNodeSelector.objectName = 'outputModelNodeSelector'
    self.__outputModelNodeSelector.toolTip = "Select the output model."
    self.__outputModelNodeSelector.nodeTypes = ['vtkMRMLModelNode']
    self.__outputModelNodeSelector.baseName = "LevelSetSegmentationModel"
    self.__outputModelNodeSelector.noneEnabled = False
    self.__outputModelNodeSelector.addEnabled = True
    self.__outputModelNodeSelector.selectNodeUponCreation = True
    self.__outputModelNodeSelector.removeEnabled = True
    ioAdvancedFormLayout.addRow("Output Model:", self.__outputModelNodeSelector)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                        self.__outputModelNodeSelector, 'setMRMLScene(vtkMRMLScene*)')     
    
    
    #
    # the segmentation panel
    #
    
    segmentationCollapsibleButton = ctk.ctkCollapsibleButton()
    segmentationCollapsibleButton.text = "Segmentation"
    self.layout.addWidget(segmentationCollapsibleButton)    

    segmentationFormLayout = qt.QFormLayout(segmentationCollapsibleButton)
    
    # Threshold slider
    thresholdLabel = qt.QLabel()
    thresholdLabel.text = "Thresholding" + SlicerVmtk4CommonLib.Helper.CreateSpace(7)
    thresholdLabel.toolTip = "Choose the intensity range to segment."
    thresholdLabel.setAlignment(4)
    segmentationFormLayout.addRow(thresholdLabel)
        
    self.__thresholdSlider = slicer.qMRMLRangeWidget()
    segmentationFormLayout.addRow(self.__thresholdSlider)
    self.__thresholdSlider.connect('valuesChanged(double,double)', self.onThresholdSliderChanged)
    
    self.__segmentationAdvancedToggle = qt.QCheckBox("Show Advanced Segmentation Properties")
    self.__segmentationAdvancedToggle.setChecked(False)
    segmentationFormLayout.addRow(self.__segmentationAdvancedToggle)    
    
    #
    # segmentation advanced panel
    #

    self.__segmentationAdvancedPanel = qt.QFrame(segmentationCollapsibleButton)
    self.__segmentationAdvancedPanel.hide()
    self.__segmentationAdvancedPanel.setFrameStyle(6)
    segmentationFormLayout.addRow(self.__segmentationAdvancedPanel)
    self.__segmentationAdvancedToggle.connect("clicked()", self.onSegmentationAdvancedToggle) 
    
    segmentationAdvancedFormLayout = qt.QFormLayout(self.__segmentationAdvancedPanel)
    
    # inflation slider
    inflationLabel = qt.QLabel()
    inflationLabel.text = "less inflation <-> more inflation" + SlicerVmtk4CommonLib.Helper.CreateSpace(14)
    inflationLabel.setAlignment(4)
    inflationLabel.toolTip = "Define how fast the segmentation expands."
    segmentationAdvancedFormLayout.addRow(inflationLabel)
    
    self.__inflationSlider = ctk.ctkSliderWidget()
    self.__inflationSlider.decimals = 0
    self.__inflationSlider.minimum = -100
    self.__inflationSlider.maximum = 100
    self.__inflationSlider.singleStep = 10
    self.__inflationSlider.toolTip = inflationLabel.toolTip
    segmentationAdvancedFormLayout.addRow(self.__inflationSlider)   
    
    # curvature slider
    curvatureLabel = qt.QLabel()
    curvatureLabel.text = "less curvature <-> more curvature" + SlicerVmtk4CommonLib.Helper.CreateSpace(14)
    curvatureLabel.setAlignment(4)
    curvatureLabel.toolTip = "Choose a high curvature to generate a smooth segmentation."
    segmentationAdvancedFormLayout.addRow(curvatureLabel)
    
    self.__curvatureSlider = ctk.ctkSliderWidget()
    self.__curvatureSlider.decimals = 0
    self.__curvatureSlider.minimum = -100
    self.__curvatureSlider.maximum = 100
    self.__curvatureSlider.singleStep = 10
    self.__curvatureSlider.toolTip = curvatureLabel.toolTip
    segmentationAdvancedFormLayout.addRow(self.__curvatureSlider)   

    # attraction slider
    attractionLabel = qt.QLabel()
    attractionLabel.text = "less attraction to gradient <-> more attraction to gradient" + SlicerVmtk4CommonLib.Helper.CreateSpace(14)
    attractionLabel.setAlignment(4)
    attractionLabel.toolTip = "Configure how the segmentation travels towards gradient ridges (vessel lumen wall)."
    segmentationAdvancedFormLayout.addRow(attractionLabel)
    
    self.__attractionSlider = ctk.ctkSliderWidget()
    self.__attractionSlider.decimals = 0
    self.__attractionSlider.minimum = -100
    self.__attractionSlider.maximum = 100
    self.__attractionSlider.singleStep = 10
    self.__attractionSlider.toolTip = attractionLabel.toolTip
    segmentationAdvancedFormLayout.addRow(self.__attractionSlider)
    
    # iteration spinbox
    self.__iterationSpinBox = qt.QSpinBox()
    self.__iterationSpinBox.minimum = 0
    self.__iterationSpinBox.maximum = 5000
    self.__iterationSpinBox.singleStep = 10
    self.__iterationSpinBox.toolTip = "Choose the number of evolution iterations."
    segmentationAdvancedFormLayout.addRow(SlicerVmtk4CommonLib.Helper.CreateSpace(120) + "Iterations:", self.__iterationSpinBox)
    
    #
    # Reset and apply buttons
    #
    
    self.__buttonBox = qt.QDialogButtonBox()
    self.__resetButton = self.__buttonBox.addButton(self.__buttonBox.RestoreDefaults)
    self.__resetButton.toolTip = "Click to reset all input elements to default."
    self.__startButton = self.__buttonBox.addButton(self.__buttonBox.Apply)
    self.__startButton.setIcon(qt.QIcon())
    self.__startButton.text = "Start!"
    self.__startButton.toolTip = "Click to start the segmentation."
    self.layout.addWidget(self.__buttonBox)
    self.__resetButton.connect("clicked()", self.restoreDefaults)
    self.__startButton.connect("clicked()", self.start)
    
    # be ready for events
    self.__updating = 0
    
    # set default values
    self.restoreDefaults()
    
    # compress the layout
    self.layout.addStretch(1)    
    

          

  def onMRMLSceneChanged(self):
    '''
    '''
    SlicerVmtk4CommonLib.Helper.Debug("onMRMLSceneChanged")
    self.restoreDefaults()

  def onInputVolumeChanged(self):
    '''
    '''
    if not self.__updating:

        self.__updating = 1
        
        SlicerVmtk4CommonLib.Helper.Debug("onInputVolumeChanged")
        
        # reset the thresholdSlider
        self.__thresholdSlider.minimum = 0
        self.__thresholdSlider.maximum = 100
        self.__thresholdSlider.minimumValue = 0
        self.__thresholdSlider.maximumValue = 100
        
        currentNode = self.__inputVolumeNodeSelector.currentNode()
        
        if currentNode:
            
            currentImageData = currentNode.GetImageData()
            currentDisplayNode = currentNode.GetDisplayNode()
            
            if currentImageData:
                currentScalarRange = currentImageData.GetScalarRange()
                minimumScalarValue = round(currentScalarRange[0], 0)
                maximumScalarValue = round(currentScalarRange[1], 0)
                self.__thresholdSlider.minimum = minimumScalarValue
                self.__thresholdSlider.maximum = maximumScalarValue
                
                if currentDisplayNode:
                    
                    if currentDisplayNode.GetApplyThreshold():
                        
                        # if a threshold is already applied, use it!
                        self.__thresholdSlider.minimumValue = currentDisplayNode.GetLowerThreshold()
                        self.__thresholdSlider.maximumValue = currentDisplayNode.GetUpperThreshold()
                        
                    else:
                        
                        # don't use a threshold, use the scalar range
                        SlicerVmtk4CommonLib.Helper.Debug("Reset thresholdSlider's values.")
                        self.__thresholdSlider.minimumValue = minimumScalarValue
                        self.__thresholdSlider.maximumValue = maximumScalarValue
                        
                    
        self.__updating = 0
        
  def resetThresholdOnDisplayNode(self):
    '''
    '''
    if not self.__updating:

        self.__updating = 1
        
        SlicerVmtk4CommonLib.Helper.Debug("resetThresholdOnDisplayNode")
        
        currentNode = self.__inputVolumeNodeSelector.currentNode()
        
        if currentNode:
            currentDisplayNode = currentNode.GetDisplayNode()
            
            if currentDisplayNode:
                currentDisplayNode.SetApplyThreshold(0)        
        
        self.__updating = 0
        
  def onThresholdSliderChanged(self):
    '''
    '''
    if not self.__updating:
        
        self.__updating = 1
        
        currentNode = self.__inputVolumeNodeSelector.currentNode()
        
        if currentNode:
            currentDisplayNode = currentNode.GetDisplayNode()
            
            if currentDisplayNode:
                
                currentDisplayNode.SetLowerThreshold(self.__thresholdSlider.minimumValue)
                currentDisplayNode.SetUpperThreshold(self.__thresholdSlider.maximumValue)
                currentDisplayNode.SetApplyThreshold(1)
            
        self.__updating = 0


  def onIOAdvancedToggle(self):
    '''
    Show the I/O Advanced panel
    '''
    if self.__ioAdvancedToggle.checked:
      self.__ioAdvancedPanel.show()
    else:
      self.__ioAdvancedPanel.hide()

  def onSegmentationAdvancedToggle(self):
    '''
    Show the Segmentation Advanced panel
    '''
    if self.__segmentationAdvancedToggle.checked:
      self.__segmentationAdvancedPanel.show()
    else:
      self.__segmentationAdvancedPanel.hide()

  def restoreDefaults(self, scope=0):
    '''
    scope == 0: reset all
    scope == 1: reset only threshold slider
    '''
    if not self.__updating:
        
        self.__updating = 1
        
        SlicerVmtk4CommonLib.Helper.Debug("restoreDefaults(" + str(scope) + ")")
        
        self.__thresholdSlider.minimum = 0
        self.__thresholdSlider.maximum = 100
        self.__thresholdSlider.minimumValue = 0
        self.__thresholdSlider.maximumValue = 100
    
        self.__ioAdvancedToggle.setChecked(False)
        self.__segmentationAdvancedToggle.setChecked(False)
        self.__ioAdvancedPanel.hide()
        self.__segmentationAdvancedPanel.hide()
    
    
        self.__inflationSlider.value = 0
        self.__curvatureSlider.value = 70
        self.__attractionSlider.value = 50    
        self.__iterationSpinBox.value = 10

        self.__updating = 0
        
        # reset threshold on display node
        self.resetThresholdOnDisplayNode()
        # if a volume is selected, the threshold slider values have to match it
        #self.onInputVolumeChanged()         



    
  def start(self):
    '''
    '''
    SlicerVmtk4CommonLib.Helper.Debug("Starting Level Set Segmentation..")
    
    # first we need the nodes
    currentVolumeNode = self.__inputVolumeNodeSelector.currentNode()
    currentSeedsNode = self.__seedFiducialsNodeSelector.currentNode()
    currentStoppersNode = self.__stopperFiducialsNodeSelector.currentNode()
    currentLabelMapNode = self.__outputVolumeNodeSelector.currentNode()
    currentModelNode = self.__outputModelNodeSelector.currentNode()
    
    if not currentVolumeNode:
        # we need a input volume node
        return 0
    
    if not currentSeedsNode:
        # we need a seeds node
        return 0
    
    #if not currentStoppersNode or currentStoppersNode.GetID() == currentSeedsNode.GetID():
        # we need a current stopper node
        #self.__stopperFiducialsNodeSelector.addNode()
    
    if not currentLabelMapNode or currentLabelMapNode.GetID() == currentVolumeNode.GetID():
        # we need a current labelMap node
        newLabelMapDisplayNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLLabelMapVolumeDisplayNode")
        newLabelMapDisplayNode.SetScene(slicer.mrmlScene)
        newLabelMapDisplayNode.SetDefaultColorMap()
        slicer.mrmlScene.AddNodeNoNotify(newLabelMapDisplayNode)        
        
        newLabelMapNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLScalarVolumeNode")
        newLabelMapNode.CopyOrientation(currentVolumeNode)
        newLabelMapNode.SetScene(slicer.mrmlScene)
        newLabelMapNode.SetName(slicer.mrmlScene.GetUniqueNameByString(self.__outputVolumeNodeSelector.baseName))
        newLabelMapNode.LabelMapOn()
        newLabelMapNode.SetAndObserveDisplayNodeID(newLabelMapDisplayNode.GetID())
        slicer.mrmlScene.AddNode(newLabelMapNode)
        currentLabelMapNode = newLabelMapNode
        self.__outputVolumeNodeSelector.setCurrentNode(currentLabelMapNode)
        
    if not currentModelNode:
        # we need a current model node, the display node is created later
        newModelNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLModelNode")
        newModelNode.SetScene(slicer.mrmlScene)
        newModelNode.SetName(slicer.mrmlScene.GetUniqueNameByString(self.__outputModelNodeSelector.baseName))        
        slicer.mrmlScene.AddNode(newModelNode)
        currentModelNode = newModelNode
        
        self.__outputModelNodeSelector.setCurrentNode(currentModelNode)        
        
    # now we need to convert the fiducials to vtkIdLists
    seeds = SlicerVmtk4CommonLib.Helper.convertFiducialHierarchyToVtkIdList(currentSeedsNode, currentVolumeNode)
    stoppers = vtk.vtkIdList()
    #stoppers = self.convertFiducialHierarchyToVtkIdList(currentStoppersNode, currentVolumeNode)
    
    # perform the initialization
    outputImageData = self.GetLogic().performInitialization(currentVolumeNode.GetImageData(),
                                                            self.__thresholdSlider.minimumValue,
                                                            self.__thresholdSlider.maximumValue,
                                                            seeds,
                                                            stoppers,
                                                            0) # TODO sidebranch ignore feature
    
    if not outputImageData.GetPointData().GetScalars():
        # something went wrong, the image is empty
        SlicerVmtk4CommonLib.Helper.Info("Segmentation failed - the output was empty..")
        return -1
    
    outputImageData = self.GetLogic().performEvolution(currentVolumeNode.GetImageData(),
                                                       outputImageData,
                                                       self.__iterationSpinBox.value,
                                                       self.__inflationSlider.value,
                                                       self.__curvatureSlider.value,
                                                       self.__attractionSlider.value,
                                                       'geodesic')
    
    labelMap = self.GetLogic().buildSimpleLabelMap(outputImageData, 0, 5)

    # propagate the label map to the node
    currentLabelMapNode.SetAndObserveImageData(labelMap)
    currentLabelMapNode.SetModifiedSinceRead(1)
    
    # deactivate the threshold in the GUI
    self.resetThresholdOnDisplayNode()
    #self.onInputVolumeChanged()
    
    # show the segmentation results in the GUI
    selectionNode = slicer.app.mrmlApplicationLogic().GetSelectionNode()
    selectionNode.SetReferenceActiveVolumeID(currentVolumeNode.GetID())
    selectionNode.SetReferenceActiveLabelVolumeID(currentLabelMapNode.GetID())
    slicer.app.mrmlApplicationLogic().PropagateVolumeSelection()
    
    # generate 3D model
    model = vtk.vtkPolyData()
    
    # we need the ijkToRas transform for the marching cubes call
    ijkToRasMatrix = vtk.vtkMatrix4x4()
    currentLabelMapNode.GetIJKToRASMatrix(ijkToRasMatrix)
    
    # call marching cubes
    model.DeepCopy(self.GetLogic().marchingCubes(outputImageData, ijkToRasMatrix, 0.0))
    model.Update()
    
    # propagate model to nodes
    currentModelNode.SetAndObservePolyData(model)
    currentModelNode.SetModifiedSinceRead(1)
    
    if not currentModelNode.GetDisplayNode():
    
        # create new displayNode
        currentModelDisplayNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLModelDisplayNode")
        slicer.mrmlScene.AddNode(currentModelDisplayNode)
        
    # always configure the displayNode to show the model
    currentModelDisplayNode.SetPolyData(currentModelNode.GetPolyData())
    currentModelDisplayNode.SetColor(1.0, 0.55, 0.4) # red
    currentModelDisplayNode.SetBackfaceCulling(0)
    currentModelDisplayNode.SetSliceIntersectionVisibility(0)
    currentModelDisplayNode.SetVisibility(1)
    currentModelDisplayNode.SetOpacity(1.0)

    # update the reference between model node and it's display node
    currentModelNode.SetAndObserveDisplayNodeID(currentModelDisplayNode.GetID())    
    



