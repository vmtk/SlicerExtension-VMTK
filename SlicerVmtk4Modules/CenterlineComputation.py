# slicer imports
from __main__ import vtk, qt, ctk, slicer

# vmtk includes
import SlicerVmtk4CommonLib


#
# Centerline Computation using VMTK based Tools
#

class CenterlineComputation:
  def __init__(self, parent):
    parent.title = "Centerline Computation"
    parent.category = "Vascular Modeling Toolkit"
    parent.contributor = "Daniel Haehn <haehn@bwh.harvard.edu>"
    parent.helpText = """dsfdsf"""
    parent.acknowledgementText = """sdfsdfdsf"""
    self.parent = parent


class CenterlineComputationWidget:
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
      self.__inputModelNodeSelector.setMRMLScene(slicer.mrmlScene)
      self.__seedFiducialsNodeSelector.setMRMLScene(slicer.mrmlScene)
      self.__outputModelNodeSelector.setMRMLScene(slicer.mrmlScene)
      self.__voronoiModelNodeSelector.setMRMLScene(slicer.mrmlScene)
      # after setup, be ready for events
      self.__updating = 0
      
      self.parent.show()
      
    # register default slots
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)', self.onMRMLSceneChanged)      

    
  def GetLogic(self):
    '''
    '''
    if not self.__logic:
        
        self.__logic = SlicerVmtk4CommonLib.CenterlineComputationLogic()
        
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
    self.__inputModelNodeSelector = slicer.qMRMLNodeComboBox()
    self.__inputModelNodeSelector.objectName = 'inputModelNodeSelector'
    self.__inputModelNodeSelector.toolTip = "Select the input model."
    self.__inputModelNodeSelector.nodeTypes = ['vtkMRMLModelNode']
    self.__inputModelNodeSelector.hideChildNodeTypes = ['vtkMRMLAnnotationNode'] # hide all annotation nodes
    self.__inputModelNodeSelector.noneEnabled = False
    self.__inputModelNodeSelector.addEnabled = False
    self.__inputModelNodeSelector.removeEnabled = False    
    ioFormLayout.addRow("Input Model:", self.__inputModelNodeSelector)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                        self.__inputModelNodeSelector, 'setMRMLScene(vtkMRMLScene*)')
    self.__inputModelNodeSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.onInputModelChanged)
    
    # seed selector
    self.__seedFiducialsNodeSelector = slicer.qMRMLNodeComboBox()
    self.__seedFiducialsNodeSelector.objectName = 'seedFiducialsNodeSelector'
    self.__seedFiducialsNodeSelector.toolTip = "Select a fiducial to use as the origin of the Centerline."
    self.__seedFiducialsNodeSelector.nodeTypes = ['vtkMRMLAnnotationFiducialNode']
    self.__seedFiducialsNodeSelector.baseName = "OriginSeed"
    self.__seedFiducialsNodeSelector.noneEnabled = False
    self.__seedFiducialsNodeSelector.addEnabled = False
    self.__seedFiducialsNodeSelector.removeEnabled = False
    ioFormLayout.addRow("Start Point:", self.__seedFiducialsNodeSelector)
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

    # outputModel selector
    self.__outputModelNodeSelector = slicer.qMRMLNodeComboBox()
    self.__outputModelNodeSelector.objectName = 'outputModelNodeSelector'
    self.__outputModelNodeSelector.toolTip = "Select the output model for the Centerlines."
    self.__outputModelNodeSelector.nodeTypes = ['vtkMRMLModelNode']
    self.__outputModelNodeSelector.baseName = "CenterlineComputationModel"
    self.__outputModelNodeSelector.hideChildNodeTypes = ['vtkMRMLAnnotationNode'] # hide all annotation nodes
    self.__outputModelNodeSelector.noneEnabled = False
    self.__outputModelNodeSelector.addEnabled = True
    self.__outputModelNodeSelector.selectNodeUponCreation = True
    self.__outputModelNodeSelector.removeEnabled = True
    ioAdvancedFormLayout.addRow("Output Centerline Model:", self.__outputModelNodeSelector)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                        self.__outputModelNodeSelector, 'setMRMLScene(vtkMRMLScene*)')     

    # voronoiModel selector
    self.__voronoiModelNodeSelector = slicer.qMRMLNodeComboBox()
    self.__voronoiModelNodeSelector.objectName = 'voronoiModelNodeSelector'
    self.__voronoiModelNodeSelector.toolTip = "Select the output model for the Voronoi Diagram."
    self.__voronoiModelNodeSelector.nodeTypes = ['vtkMRMLModelNode']
    self.__voronoiModelNodeSelector.baseName = "VoronoiModel"
    self.__voronoiModelNodeSelector.hideChildNodeTypes = ['vtkMRMLAnnotationNode'] # hide all annotation nodes
    self.__voronoiModelNodeSelector.noneEnabled = False
    self.__voronoiModelNodeSelector.addEnabled = True
    self.__voronoiModelNodeSelector.selectNodeUponCreation = True
    self.__voronoiModelNodeSelector.removeEnabled = True
    ioAdvancedFormLayout.addRow("Output Voronoi Model:", self.__voronoiModelNodeSelector)
    self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                        self.__voronoiModelNodeSelector, 'setMRMLScene(vtkMRMLScene*)')     

    

    
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

  def onInputModelChanged(self):
    '''
    '''
    if not self.__updating:

        self.__updating = 1
        
        SlicerVmtk4CommonLib.Helper.Debug("onInputModelChanged")
        
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

      self.__startButton.enabled = True
      
      # this is no preview
      self.start(False)
      
  def onRefreshButtonClicked(self):
      '''
      '''

      # calculate the preview
      self.start(True)
      
      # activate startButton
      self.__startButton.enabled = True
      


  def onIOAdvancedToggle(self):
    '''
    Show the I/O Advanced panel
    '''
    
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
        
        
        self.__startButton.enabled = False

        self.__updating = 0
        
        
        self.onInputModelChanged()         


  def start(self, preview=False):
    '''
    '''
    SlicerVmtk4CommonLib.Helper.Debug("Starting Centerline Computation..")
    
    # first we need the nodes
    currentModelNode = self.__inputModelNodeSelector.currentNode()
    currentSeedsNode = self.__seedFiducialsNodeSelector.currentNode()
    currentOutputModelNode = self.__outputModelNodeSelector.currentNode()
    currentVoronoiModelNode = self.__voronoiModelNodeSelector.currentNode()
    
    if not currentModelNode:
        # we need a input volume node
        return 0
    
    if not currentSeedsNode:
        # we need a seeds node
        return 0  
    
    if not currentOutputModelNode or currentOutputModelNode.GetID() == currentModelNode.GetID():
        # we need a current model node, the display node is created later
        newModelNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLModelNode")
        newModelNode.SetScene(slicer.mrmlScene)
        newModelNode.SetName(slicer.mrmlScene.GetUniqueNameByString(self.__outputModelNodeSelector.baseName))        
        slicer.mrmlScene.AddNode(newModelNode)
        currentOutputModelNode = newModelNode
        
        self.__outputModelNodeSelector.setCurrentNode(currentOutputModelNode)        

    # the output model
    model = vtk.vtkPolyData()
    
    currentCoordinatesRAS = [0, 0, 0]

    # grab the current coordinates
    currentSeedsNode.GetFiducialCoordinates(currentCoordinatesRAS)
    
    # prepare the model
    model.DeepCopy(self.GetLogic().prepareModel(currentModelNode.GetPolyData()))
    model.Update()
    
    # open the model at the seed
    model.DeepCopy(self.GetLogic().openSurfaceAtPoint(model,currentCoordinatesRAS))
    model.Update()
    
    # extract Network
    model.DeepCopy(self.GetLogic().extractNetwork(model))
    model.Update()
    
    # place fiducials at endpoints
    endPointIds = self.GetLogic().getEndPointsOfNetwork(model)
    
    for i in range(endPointIds.GetNumberOfIds()):
        
        endpointId = endPointIds.GetId(i)
        coordinates = model.GetPoint(endpointId)
        
        #coordinates = point.GetPoint()
        currentFiducialNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLAnnotationFiducialNode")
        currentFiducialNode.SetFiducialCoordinates(coordinates)
        currentFiducialNode.Initialize(slicer.mrmlScene)                
    
    
    # update the display of the original model
    currentModelDisplayNode = currentModelNode.GetDisplayNode()
    
    if not currentModelDisplayNode:
        
        # create new displayNode
        currentModelDisplayNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLModelDisplayNode")
        slicer.mrmlScene.AddNode(currentModelDisplayNode)
            
    currentModelDisplayNode.SetOpacity(0.4)
    currentModelDisplayNode.Modified()
    currentModelDisplayNode.SetModifiedSinceRead(1)

    # update the reference between model node and it's display node
    currentModelNode.SetAndObserveDisplayNodeID(currentModelDisplayNode.GetID())   
    currentModelNode.Modified()
    currentModelNode.SetModifiedSinceRead(1)
    
    # finally:
    # propagate output model to nodes
    currentOutputModelNode.SetAndObservePolyData(model)
    currentOutputModelNode.Modified()
    currentOutputModelNode.SetModifiedSinceRead(1)
    
    currentOutputModelDisplayNode = currentOutputModelNode.GetDisplayNode()
    
    if not currentOutputModelDisplayNode:
    
        # create new displayNode
        currentOutputModelDisplayNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLModelDisplayNode")
        slicer.mrmlScene.AddNode(currentOutputModelDisplayNode)
        
    # always configure the displayNode to show the model
    currentOutputModelDisplayNode.SetPolyData(currentOutputModelNode.GetPolyData())
    currentOutputModelDisplayNode.SetColor(0.0, 0.0, 0.4) # red
    currentOutputModelDisplayNode.SetBackfaceCulling(0)
    currentOutputModelDisplayNode.SetSliceIntersectionVisibility(0)
    currentOutputModelDisplayNode.SetVisibility(1)
    currentOutputModelDisplayNode.SetOpacity(1.0)
    currentOutputModelDisplayNode.Modified()
    currentOutputModelDisplayNode.SetModifiedSinceRead(1)

    # update the reference between model node and it's display node
    currentOutputModelNode.SetAndObserveDisplayNodeID(currentOutputModelDisplayNode.GetID())   
    currentOutputModelNode.Modified()
    currentOutputModelNode.SetModifiedSinceRead(1)
    
    
    
    SlicerVmtk4CommonLib.Helper.Debug("End of Centerline Computation..")


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

class CenterlineComputationSlicelet(Slicelet):
  """ Creates the interface when module is run as a stand alone gui app.
  """

  def __init__(self):
    super(CenterlineComputationSlicelet, self).__init__(CenterlineComputationWidget)


if __name__ == "__main__":
  # TODO: need a way to access and parse command line arguments
  # TODO: ideally command line args should handle --xml

  import sys
  print(sys.argv)

  slicelet = CenterlineComputationSlicelet()
