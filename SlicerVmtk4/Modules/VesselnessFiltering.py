# slicer imports
from __main__ import vtk, qt, ctk, slicer

# vmtk includes
import SlicerVmtk4CommonLib


#
# Vesselness Filtering using VMTK based Tools
#

class VesselnessFiltering:
  def __init__(self, parent):
    parent.title = "Vesselness Filtering"
    parent.categories = ["Vascular Modeling Toolkit",]
    parent.contributors = ["Daniel Haehn (Boston Children's Hospital)", "Luca Antiga (Orobix)", "Steve Pieper (Isomics)"]
    parent.helpText = """dsfdsf"""
    parent.acknowledgementText = """sdfsdfdsf"""
    self.parent = parent


class VesselnessFilteringWidget:
  def __init__(self, parent=None):
    if not parent:
      self.parent = slicer.qMRMLWidget()
      self.parent.setLayout(qt.QVBoxLayout())
      self.parent.setMRMLScene(slicer.mrmlScene)      
    else:
      self.parent = parent
    self.layout = self.parent.layout()

    # this flag is 1 if there is an update in progress
    self.__updating = 1
    
    # the pointer to the logic
    self.__logic = None    

    if not parent:
      self.setup()
      self.__inputVolumeNodeSelector.setMRMLScene(slicer.mrmlScene)
      self.__seedFiducialsNodeSelector.setMRMLScene(slicer.mrmlScene)
      self.__outputVolumeNodeSelector.setMRMLScene(slicer.mrmlScene)
      self.__previewVolumeNodeSelector.setMRMLScene(slicer.mrmlScene)
      # after setup, be ready for events
      self.__updating = 0
      
      self.parent.show()
      
    # register default slots
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)', self.onMRMLSceneChanged)      

    
  def GetLogic(self):
    '''
    '''
    if not self.__logic:
        
        self.__logic = SlicerVmtk4CommonLib.VesselnessFilteringLogic()
        
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
    self.__inputVolumeNodeSelector.addAttribute("vtkMRMLScalarVolumeNode", "LabelMap", "0")    
    ioFormLayout.addRow("Input Volume:", self.__inputVolumeNodeSelector)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                        self.__inputVolumeNodeSelector, 'setMRMLScene(vtkMRMLScene*)')
    self.__inputVolumeNodeSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.onInputVolumeChanged)
    
    # seed selector
    self.__seedFiducialsNodeSelector = slicer.qMRMLNodeComboBox()
    self.__seedFiducialsNodeSelector.objectName = 'seedFiducialsNodeSelector'
    self.__seedFiducialsNodeSelector.toolTip = "Select a fiducial to use as a Seed to detect the maximal diameter."
    self.__seedFiducialsNodeSelector.nodeTypes = ['vtkMRMLAnnotationFiducialNode']
    self.__seedFiducialsNodeSelector.baseName = "DiameterSeed"
    self.__seedFiducialsNodeSelector.noneEnabled = False
    self.__seedFiducialsNodeSelector.addEnabled = False
    self.__seedFiducialsNodeSelector.removeEnabled = False
    ioFormLayout.addRow("Seed in largest Vessel:", self.__seedFiducialsNodeSelector)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                        self.__seedFiducialsNodeSelector, 'setMRMLScene(vtkMRMLScene*)')   
    self.__seedFiducialsNodeSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.onSeedChanged)
    
    self.__ioAdvancedToggle = qt.QCheckBox("Show Advanced Properties")
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

    # lock button
    self.__detectPushButton = qt.QPushButton()
    self.__detectPushButton.text = "Detect parameters automatically"
    self.__detectPushButton.checkable = True
    self.__detectPushButton.checked = True
    #self.__unLockPushButton.connect("clicked()", self.calculateParameters())
    ioAdvancedFormLayout.addRow(self.__detectPushButton)

    # outputVolume selector
    self.__outputVolumeNodeSelector = slicer.qMRMLNodeComboBox()
    self.__outputVolumeNodeSelector.toolTip = "Select the output labelmap."
    self.__outputVolumeNodeSelector.nodeTypes = ['vtkMRMLScalarVolumeNode']
    self.__outputVolumeNodeSelector.baseName = "VesselnessFiltered"
    self.__outputVolumeNodeSelector.noneEnabled = False
    self.__outputVolumeNodeSelector.addEnabled = True
    self.__outputVolumeNodeSelector.selectNodeUponCreation = True
    self.__outputVolumeNodeSelector.removeEnabled = True
    ioAdvancedFormLayout.addRow("Output Volume:", self.__outputVolumeNodeSelector)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                        self.__outputVolumeNodeSelector, 'setMRMLScene(vtkMRMLScene*)')   
    
    # previewVolume selector
    self.__previewVolumeNodeSelector = slicer.qMRMLNodeComboBox()
    self.__previewVolumeNodeSelector.toolTip = "Select the preview volume."
    self.__previewVolumeNodeSelector.nodeTypes = ['vtkMRMLScalarVolumeNode']
    self.__previewVolumeNodeSelector.baseName = "VesselnessPreview"
    self.__previewVolumeNodeSelector.noneEnabled = False
    self.__previewVolumeNodeSelector.addEnabled = True
    self.__previewVolumeNodeSelector.selectNodeUponCreation = True
    self.__previewVolumeNodeSelector.removeEnabled = True
    ioAdvancedFormLayout.addRow("Preview Volume:", self.__previewVolumeNodeSelector)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                        self.__previewVolumeNodeSelector, 'setMRMLScene(vtkMRMLScene*)')       

    self.__minimumDiameterSpinBox = qt.QSpinBox()
    self.__minimumDiameterSpinBox.minimum = 0
    self.__minimumDiameterSpinBox.maximum = 1000
    self.__minimumDiameterSpinBox.singleStep = 1
    self.__minimumDiameterSpinBox.toolTip = "Specify the minimum Diameter manually."
    ioAdvancedFormLayout.addRow("Minimum Diameter [vx]:", self.__minimumDiameterSpinBox)

    self.__maximumDiameterSpinBox = qt.QSpinBox()
    self.__maximumDiameterSpinBox.minimum = 0
    self.__maximumDiameterSpinBox.maximum = 1000
    self.__maximumDiameterSpinBox.singleStep = 1
    self.__maximumDiameterSpinBox.toolTip = "Specify the maximum Diameter manually."
    ioAdvancedFormLayout.addRow("Maximum Diameter [vx]:", self.__maximumDiameterSpinBox)
    
    # add empty row
    ioAdvancedFormLayout.addRow("", qt.QWidget())

    # alpha slider
    alphaLabel = qt.QLabel()
    alphaLabel.text = "more Tubes <-> more Plates" + SlicerVmtk4CommonLib.Helper.CreateSpace(16)
    alphaLabel.setAlignment(4)
    alphaLabel.toolTip = "A lower value detects tubes rather than plate-like structures."
    ioAdvancedFormLayout.addRow(alphaLabel)
    
    self.__alphaSlider = ctk.ctkSliderWidget()
    self.__alphaSlider.decimals = 1
    self.__alphaSlider.minimum = 0.1
    self.__alphaSlider.maximum = 500
    self.__alphaSlider.singleStep = 0.1
    self.__alphaSlider.toolTip = alphaLabel.toolTip
    ioAdvancedFormLayout.addRow(self.__alphaSlider)

    # beta slider
    betaLabel = qt.QLabel()
    betaLabel.text = "more Blobs <-> more Tubes" + SlicerVmtk4CommonLib.Helper.CreateSpace(16)
    betaLabel.setAlignment(4)
    betaLabel.toolTip = "A higher value detects tubes rather than blobs."
    ioAdvancedFormLayout.addRow(betaLabel)
    
    self.__betaSlider = ctk.ctkSliderWidget()
    self.__betaSlider.decimals = 1
    self.__betaSlider.minimum = 0.1
    self.__betaSlider.maximum = 500
    self.__betaSlider.singleStep = 0.1
    self.__betaSlider.toolTip = betaLabel.toolTip
    ioAdvancedFormLayout.addRow(self.__betaSlider)    

    # contrast slider
    contrastLabel = qt.QLabel()
    contrastLabel.text = "low Input Contrast <-> high Input Contrast" + SlicerVmtk4CommonLib.Helper.CreateSpace(14)
    contrastLabel.setAlignment(4)
    contrastLabel.toolTip = "If the intensity contrast in the input image between vessel and background is high, choose a high value else choose a low value."
    ioAdvancedFormLayout.addRow(contrastLabel)    
    
    self.__contrastSlider = ctk.ctkSliderWidget()
    self.__contrastSlider.decimals = 0
    self.__contrastSlider.minimum = 0
    self.__contrastSlider.maximum = 500
    self.__contrastSlider.singleStep = 10
    self.__contrastSlider.toolTip = contrastLabel.toolTip
    ioAdvancedFormLayout.addRow(self.__contrastSlider)   
    
    #
    # Reset, preview and apply buttons
    #
    
    self.__buttonBox = qt.QDialogButtonBox()
    self.__resetButton = self.__buttonBox.addButton(self.__buttonBox.RestoreDefaults)
    self.__resetButton.toolTip = "Click to reset all input elements to default."
    self.__previewButton = self.__buttonBox.addButton(self.__buttonBox.Discard)
    self.__previewButton.setIcon(qt.QIcon())
    self.__previewButton.text = "Preview.."
    self.__previewButton.toolTip = "Click to refresh the preview."
    self.__startButton = self.__buttonBox.addButton(self.__buttonBox.Apply)
    self.__startButton.setIcon(qt.QIcon())
    self.__startButton.text = "Start!"
    self.__startButton.enabled = False
    self.__startButton.toolTip = "Click to start the filtering."
    self.layout.addWidget(self.__buttonBox)
    self.__resetButton.connect("clicked()", self.restoreDefaults)
    self.__previewButton.connect("clicked()", self.onRefreshButtonClicked)
    self.__startButton.connect("clicked()", self.onStartButtonClicked)
    
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
        
        # do nothing right now
                    
        self.__updating = 0

  def onSeedChanged(self):
    '''
    '''
    if not self.__updating:

        self.__updating = 1

        # nothing yet

        self.__updating = 0  
        
  def onStartButtonClicked(self):
      '''
      '''
      if self.__detectPushButton.checked:
          self.restoreDefaults()
          self.calculateParameters()      

      self.__startButton.enabled = True
      
      # this is no preview
      self.start(False)
      
  def onRefreshButtonClicked(self):
      '''
      '''
      if self.__detectPushButton.checked:
          self.restoreDefaults()
          self.calculateParameters()
          
      # calculate the preview
      self.start(True)
      
      # activate startButton
      self.__startButton.enabled = True
      

  def calculateParameters(self):
    '''
    '''
    
    SlicerVmtk4CommonLib.Helper.Debug("calculateParameters")
    
    # first we need the nodes
    currentVolumeNode = self.__inputVolumeNodeSelector.currentNode()
    currentSeedsNode = self.__seedFiducialsNodeSelector.currentNode()
    
    if not currentVolumeNode:
        # we need a input volume node
        SlicerVmtk4CommonLib.Helper.Debug("calculateParameters: Have no valid volume node")
        return False
    
    if not currentSeedsNode:
        # we need a seeds node
        SlicerVmtk4CommonLib.Helper.Debug("calculateParameters: Have no valid fiducial node")
        return False
    
    image = currentVolumeNode.GetImageData()
    
    currentCoordinatesRAS = [0, 0, 0]
    
    # grab the current coordinates
    currentSeedsNode.GetFiducialCoordinates(currentCoordinatesRAS)
    
    seed = SlicerVmtk4CommonLib.Helper.ConvertRAStoIJK(currentVolumeNode, currentCoordinatesRAS)    
    
    # we detect the diameter in IJK space (image has spacing 1,1,1) with IJK coordinates
    detectedDiameter = self.GetLogic().getDiameter(image, int(seed[0]), int(seed[1]), int(seed[2]))
    SlicerVmtk4CommonLib.Helper.Debug("Diameter detected: " + str(detectedDiameter))
    
    contrastMeasure = self.GetLogic().calculateContrastMeasure(image, int(seed[0]), int(seed[1]), int(seed[2]), detectedDiameter)
    SlicerVmtk4CommonLib.Helper.Debug("Contrast measure: " + str(contrastMeasure))
    
    self.__maximumDiameterSpinBox.value = detectedDiameter
    self.__contrastSlider.value = contrastMeasure
    
    return True
    
    
    

  def onIOAdvancedToggle(self):
    '''
    Show the I/O Advanced panel
    '''
    #re-calculate parameter
    self.calculateParameters()
    
    if self.__ioAdvancedToggle.checked:
      self.__ioAdvancedPanel.show()
    else:
      self.__ioAdvancedPanel.hide()

  def restoreDefaults(self):
    '''
    '''
    if not self.__updating:
        
        self.__updating = 1
        
        SlicerVmtk4CommonLib.Helper.Debug("restoreDefaults")
        
        self.__detectPushButton.checked = True
        self.__minimumDiameterSpinBox.value = 1
        self.__maximumDiameterSpinBox.value = 7
        self.__alphaSlider.value = 0.3
        self.__betaSlider.value = 500
        self.__contrastSlider.value = 100
        
        self.__startButton.enabled = False

        self.__updating = 0
        
        # if a volume is selected, the threshold slider values have to match it
        self.onInputVolumeChanged()         


  def start(self, preview=False):
    '''
    '''
    SlicerVmtk4CommonLib.Helper.Debug("Starting Vesselness Filtering..")
    
    # first we need the nodes
    currentVolumeNode = self.__inputVolumeNodeSelector.currentNode()
    currentSeedsNode = self.__seedFiducialsNodeSelector.currentNode()
    
    if preview:
        # if previewMode, get the node selector of the preview volume
        currentOutputVolumeNodeSelector = self.__previewVolumeNodeSelector
    else:
        currentOutputVolumeNodeSelector = self.__outputVolumeNodeSelector
        
    currentOutputVolumeNode = currentOutputVolumeNodeSelector.currentNode()

    if not currentVolumeNode:
        # we need a input volume node
        return 0
    
    if not currentOutputVolumeNode or currentOutputVolumeNode.GetID() == currentVolumeNode.GetID():
        # we need an output volume node
        newVolumeDisplayNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLScalarVolumeDisplayNode")
        newVolumeDisplayNode.SetDefaultColorMap()
        newVolumeDisplayNode.SetScene(slicer.mrmlScene)
        slicer.mrmlScene.AddNode(newVolumeDisplayNode)        
        
        newVolumeNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLScalarVolumeNode")
        newVolumeNode.SetScene(slicer.mrmlScene)
        newVolumeNode.SetName(slicer.mrmlScene.GetUniqueNameByString(currentOutputVolumeNodeSelector.baseName))
        newVolumeNode.SetAndObserveDisplayNodeID(newVolumeDisplayNode.GetID())
        slicer.mrmlScene.AddNode(newVolumeNode)
        currentOutputVolumeNode = newVolumeNode
        currentOutputVolumeNodeSelector.setCurrentNode(currentOutputVolumeNode)  
    
    if preview and not currentSeedsNode:
        # we need a seedsNode for preview
        SlicerVmtk4CommonLib.Helper.Info("A seed point is required to use the preview mode.")
        return 0    
            
    
    # we get the fiducial coordinates
    if currentSeedsNode:
    
        currentCoordinatesRAS = [0, 0, 0]
    
        # grab the current coordinates
        currentSeedsNode.GetFiducialCoordinates(currentCoordinatesRAS)
        
        
    inputImage = currentVolumeNode.GetImageData()
    
    #
    # vesselness parameters
    #
    
    # we need to convert diameter to mm, we use the minimum spacing to multiply the voxel value
    minimumDiameter = self.__minimumDiameterSpinBox.value * min(currentVolumeNode.GetSpacing())
    maximumDiameter = self.__maximumDiameterSpinBox.value * min(currentVolumeNode.GetSpacing())
    
    SlicerVmtk4CommonLib.Helper.Debug(minimumDiameter)
    SlicerVmtk4CommonLib.Helper.Debug(maximumDiameter)
    
    alpha = self.__alphaSlider.value
    beta = self.__betaSlider.value
    
    contrastMeasure = self.__contrastSlider.value
    
    #
    # end of vesselness parameters
    #
    
    # this image will later hold the inputImage
    image = vtk.vtkImageData()
    
    # this image will later hold the outputImage
    outImage = vtk.vtkImageData()
    
    # if we are in previewMode, we have to cut the ROI first for speed
    if preview:

        # we extract the ROI of currentVolumeNode and save it to currentOutputVolumeNode
        # we work in RAS space
        SlicerVmtk4CommonLib.Helper.extractROI(currentVolumeNode.GetID(), currentOutputVolumeNode.GetID(), currentCoordinatesRAS, self.__maximumDiameterSpinBox.value)
    
        # get the new cutted imageData
        image.DeepCopy(currentOutputVolumeNode.GetImageData())
        image.Update()
    
    else:
        
        # there was no ROI extraction, so just clone the inputImage
        image.DeepCopy(inputImage)
        image.Update()
    
    # attach the spacing and origin to get accurate vesselness computation
    image.SetSpacing(currentVolumeNode.GetSpacing())
    image.SetOrigin(currentVolumeNode.GetOrigin())
    
    # we now compute the vesselness in RAS space, image has spacing and origin attached, the diameters are converted to mm
    # we use RAS space to support anisotropic datasets
    outImage.DeepCopy(self.GetLogic().performFrangiVesselness(image, minimumDiameter, maximumDiameter, 5, alpha, beta, contrastMeasure))
    outImage.Update()
    
    # let's remove spacing and origin attached to outImage
    outImage.SetSpacing(1, 1, 1)
    outImage.SetOrigin(0, 0, 0)
    
    # we only want to copy the orientation from input to output when we are not in preview mode
    if not preview:
        currentOutputVolumeNode.CopyOrientation(currentVolumeNode)        
    
    # we set the outImage which has spacing 1,1,1. The ijkToRas matrix of the node will take care of that
    currentOutputVolumeNode.SetAndObserveImageData(outImage)

    # for preview: show the inputVolume as background and the outputVolume as foreground in the slice viewers
    #    note: that's the only way we can have the preview as an overlay of the originalvolume
    # for not preview: show the outputVolume as background and the inputVolume as foreground in the slice viewers
    if preview:
        fgVolumeID = currentOutputVolumeNode.GetID()
        bgVolumeID = currentVolumeNode.GetID()
    else:
        bgVolumeID = currentOutputVolumeNode.GetID()
        fgVolumeID = currentVolumeNode.GetID()        
    
    selectionNode = slicer.app.mrmlApplicationLogic().GetSelectionNode()
    selectionNode.SetReferenceActiveVolumeID(bgVolumeID)
    selectionNode.SetReferenceSecondaryVolumeID(fgVolumeID)
    slicer.app.mrmlApplicationLogic().PropagateVolumeSelection()    

    # renew auto window/level for the output
    currentOutputVolumeNode.GetDisplayNode().AutoWindowLevelOff()
    currentOutputVolumeNode.GetDisplayNode().AutoWindowLevelOn()
    
    # show foreground volume
    numberOfCompositeNodes = slicer.mrmlScene.GetNumberOfNodesByClass('vtkMRMLSliceCompositeNode')
    for n in xrange(numberOfCompositeNodes):
      compositeNode = slicer.mrmlScene.GetNthNodeByClass(n, 'vtkMRMLSliceCompositeNode')
      if compositeNode:
          if preview:
              # the preview is the foreground volume, so we want to show it fully
              compositeNode.SetForegroundOpacity(1.0)
          else:
              # now the background volume is the vesselness output, we want to show it fully
              compositeNode.SetForegroundOpacity(0.0)    
    
    # fit slice to all sliceviewers
    slicer.app.mrmlApplicationLogic().FitSliceToAll()    
    
    # jump all sliceViewers to the fiducial point, if one was used
    if currentSeedsNode:
        numberOfSliceNodes = slicer.mrmlScene.GetNumberOfNodesByClass('vtkMRMLSliceNode')
        for n in xrange(numberOfSliceNodes):
            sliceNode = slicer.mrmlScene.GetNthNodeByClass(n, "vtkMRMLSliceNode")
            if sliceNode:
                sliceNode.JumpSliceByOffsetting(currentCoordinatesRAS[0], currentCoordinatesRAS[1], currentCoordinatesRAS[2])

    SlicerVmtk4CommonLib.Helper.Debug("End of Vesselness Filtering..")


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
