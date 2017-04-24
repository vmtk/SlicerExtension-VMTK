# slicer imports
import os
import unittest
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
import logging

#from __main__ import vtk, qt, ctk, slicer

# vmtk includes
import SlicerVmtkCommonLib


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
    self.parent.helpText = """
"""
    self.parent.acknowledgementText = """
""" # replace with organization, grant and thanks.

#
# VesselnessFilteringWidget
#


class VesselnessFilteringWidget(ScriptedLoadableModuleWidget):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__( self, parent=None ):
    ScriptedLoadableModuleWidget.__init__(self, parent)

    # the pointer to the logic
    self.__logic = SlicerVmtkCommonLib.VesselnessFilteringLogic()

    if not parent:
      # after setup, be ready for events
      self.parent.show()
    else:
      # register default slots
      self.parent.connect( 'mrmlSceneChanged(vtkMRMLScene*)', self.onMRMLSceneChanged )

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    #
    # the I/O panel
    #

    ioCollapsibleButton = ctk.ctkCollapsibleButton()
    ioCollapsibleButton.text = "Input/Output"
    self.layout.addWidget( ioCollapsibleButton )
    ioFormLayout = qt.QFormLayout( ioCollapsibleButton )

    # inputVolume selector
    self.__inputVolumeNodeSelector = slicer.qMRMLNodeComboBox()
    self.__inputVolumeNodeSelector.objectName = 'inputVolumeNodeSelector'
    self.__inputVolumeNodeSelector.toolTip = "Select the input volume."
    self.__inputVolumeNodeSelector.nodeTypes = ['vtkMRMLScalarVolumeNode']
    self.__inputVolumeNodeSelector.noneEnabled = False
    self.__inputVolumeNodeSelector.addEnabled = False
    self.__inputVolumeNodeSelector.removeEnabled = False
    ioFormLayout.addRow( "Input Volume:", self.__inputVolumeNodeSelector )
    self.__inputVolumeNodeSelector.connect( 'currentNodeChanged(vtkMRMLNode*)', self.onInputVolumeChanged )
    self.parent.connect( 'mrmlSceneChanged(vtkMRMLScene*)',
                        self.__inputVolumeNodeSelector, 'setMRMLScene(vtkMRMLScene*)' )

    # seed selector
    self.__seedFiducialsNodeSelector = slicer.qSlicerSimpleMarkupsWidget()
    self.__seedFiducialsNodeSelector.objectName = 'seedFiducialsNodeSelector'
    self.__seedFiducialsNodeSelector = slicer.qSlicerSimpleMarkupsWidget()
    self.__seedFiducialsNodeSelector.objectName = 'seedFiducialsNodeSelector'
    self.__seedFiducialsNodeSelector.toolTip = "Select a point in the largest vessel. Preview will be shown around this point. This is point is also used for determining maximum vessel diameter if automatic filtering parameters computation is enabled."
    self.__seedFiducialsNodeSelector.setNodeBaseName("DiameterSeed")
    self.__seedFiducialsNodeSelector.tableWidget().hide()
    self.__seedFiducialsNodeSelector.defaultNodeColor = qt.QColor(255,0,0) # red
    self.__seedFiducialsNodeSelector.markupsSelectorComboBox().noneEnabled = False
    self.__seedFiducialsNodeSelector.markupsPlaceWidget().placeMultipleMarkups = slicer.qSlicerMarkupsPlaceWidget.ForcePlaceSingleMarkup
    ioFormLayout.addRow( "Seed point:", self.__seedFiducialsNodeSelector )
    self.parent.connect( 'mrmlSceneChanged(vtkMRMLScene*)',
                        self.__seedFiducialsNodeSelector, 'setMRMLScene(vtkMRMLScene*)' )

    # outputVolume selector
    self.__outputVolumeNodeSelector = slicer.qMRMLNodeComboBox()
    self.__outputVolumeNodeSelector.toolTip = "Select the output labelmap."
    self.__outputVolumeNodeSelector.nodeTypes = ['vtkMRMLScalarVolumeNode']
    self.__outputVolumeNodeSelector.baseName = "VesselnessFiltered"
    self.__outputVolumeNodeSelector.noneEnabled = True
    self.__outputVolumeNodeSelector.noneDisplay = "Create new volume"
    self.__outputVolumeNodeSelector.addEnabled = True
    self.__outputVolumeNodeSelector.selectNodeUponCreation = True
    self.__outputVolumeNodeSelector.removeEnabled = True
    ioFormLayout.addRow( "Output Volume:", self.__outputVolumeNodeSelector )
    self.parent.connect( 'mrmlSceneChanged(vtkMRMLScene*)',
                        self.__outputVolumeNodeSelector, 'setMRMLScene(vtkMRMLScene*)' )
                        
    #
    # Advanced area
    #

    self.advancedCollapsibleButton = ctk.ctkCollapsibleButton()
    self.advancedCollapsibleButton.text = "Advanced"
    self.advancedCollapsibleButton.collapsed = True
    self.layout.addWidget(self.advancedCollapsibleButton)
    advancedFormLayout = qt.QFormLayout(self.advancedCollapsibleButton)

    # previewVolume selector
    self.__previewVolumeNodeSelector = slicer.qMRMLNodeComboBox()
    self.__previewVolumeNodeSelector.toolTip = "Select the preview volume."
    self.__previewVolumeNodeSelector.nodeTypes = ['vtkMRMLScalarVolumeNode']
    self.__previewVolumeNodeSelector.baseName = "VesselnessPreview"
    self.__previewVolumeNodeSelector.noneEnabled = False
    self.__previewVolumeNodeSelector.addEnabled = True
    self.__previewVolumeNodeSelector.selectNodeUponCreation = True
    self.__previewVolumeNodeSelector.removeEnabled = True
    advancedFormLayout.addRow( "Preview Volume:", self.__previewVolumeNodeSelector )
    self.parent.connect( 'mrmlSceneChanged(vtkMRMLScene*)',
                        self.__previewVolumeNodeSelector, 'setMRMLScene(vtkMRMLScene*)' )

    # lock button
    self.__detectPushButton = qt.QPushButton()
    self.__detectPushButton.text = "Compute vessel diameters and contrast from seed point"
    self.__detectPushButton.checkable = True
    self.__detectPushButton.checked = True
    #self.__detectPushButton.connect("clicked()", self.calculateParameters())
    advancedFormLayout.addRow( self.__detectPushButton )                        
                        
    self.__minimumDiameterSpinBox = qt.QSpinBox()
    self.__minimumDiameterSpinBox.minimum = 0
    self.__minimumDiameterSpinBox.maximum = 1000
    self.__minimumDiameterSpinBox.singleStep = 1
    self.__minimumDiameterSpinBox.suffix = " voxels"
    self.__minimumDiameterSpinBox.enabled = False
    self.__minimumDiameterSpinBox.toolTip = "Tubular structures that have minimum this diameter will be enhanced."
    advancedFormLayout.addRow( "Minimum vessel diameter:", self.__minimumDiameterSpinBox )
    self.__detectPushButton.connect("toggled(bool)", self.__minimumDiameterSpinBox.setDisabled)

    self.__maximumDiameterSpinBox = qt.QSpinBox()
    self.__maximumDiameterSpinBox.minimum = 0
    self.__maximumDiameterSpinBox.maximum = 1000
    self.__maximumDiameterSpinBox.singleStep = 1
    self.__maximumDiameterSpinBox.suffix = " voxels"
    self.__maximumDiameterSpinBox.enabled = False
    self.__maximumDiameterSpinBox.toolTip = "Tubular structures that have maximum this diameter will be enhanced."
    advancedFormLayout.addRow( "Maximum vessel diameter:", self.__maximumDiameterSpinBox )
    self.__detectPushButton.connect("toggled(bool)", self.__maximumDiameterSpinBox.setDisabled)

    self.__contrastSlider = ctk.ctkSliderWidget()
    self.__contrastSlider.decimals = 0
    self.__contrastSlider.minimum = 0
    self.__contrastSlider.maximum = 500
    self.__contrastSlider.singleStep = 10
    self.__contrastSlider.enabled = False
    self.__contrastSlider.toolTip = "If the intensity contrast in the input image between vessel and background is high, choose a high value else choose a low value."
    advancedFormLayout.addRow( "Vessel contrast:", self.__contrastSlider )
    self.__detectPushButton.connect("toggled(bool)", self.__contrastSlider.setDisabled)

    self.__suppressPlatesSlider = ctk.ctkSliderWidget()
    self.__suppressPlatesSlider.decimals = 0
    self.__suppressPlatesSlider.minimum = 0
    self.__suppressPlatesSlider.maximum = 100
    self.__suppressPlatesSlider.singleStep = 1
    self.__suppressPlatesSlider.suffix = " %"
    self.__suppressPlatesSlider.toolTip = "A higher value filters out more plate-like structures."
    advancedFormLayout.addRow( "Suppress plates:", self.__suppressPlatesSlider )

    self.__suppressBlobsSlider = ctk.ctkSliderWidget()
    self.__suppressBlobsSlider.decimals = 0
    self.__suppressBlobsSlider.minimum = 0
    self.__suppressBlobsSlider.maximum = 100
    self.__suppressBlobsSlider.singleStep = 1
    self.__suppressBlobsSlider.suffix = " %"
    self.__suppressBlobsSlider.toolTip = "A higher value filters out more blob-like structures."
    advancedFormLayout.addRow( "Suppress blobs:", self.__suppressBlobsSlider )

    #
    # Reset, preview and apply buttons
    #

    self.__buttonBox = qt.QDialogButtonBox()
    self.__resetButton = self.__buttonBox.addButton( self.__buttonBox.RestoreDefaults )
    self.__resetButton.toolTip = "Click to reset all input elements to default."
    self.__previewButton = self.__buttonBox.addButton( self.__buttonBox.Discard )
    self.__previewButton.setIcon( qt.QIcon() )
    self.__previewButton.text = "Preview"
    self.__previewButton.toolTip = "Click to refresh the preview."
    self.__startButton = self.__buttonBox.addButton( self.__buttonBox.Apply )
    self.__startButton.setIcon( qt.QIcon() )
    self.__startButton.text = "Start"
    self.__startButton.enabled = False
    self.__startButton.toolTip = "Click to start the filtering."
    self.layout.addWidget( self.__buttonBox )
    self.__resetButton.connect( "clicked()", self.restoreDefaults )
    self.__previewButton.connect( "clicked()", self.onPreviewButtonClicked )
    self.__startButton.connect( "clicked()", self.onStartButtonClicked )

    self.__inputVolumeNodeSelector.setMRMLScene( slicer.mrmlScene )
    self.__seedFiducialsNodeSelector.setMRMLScene( slicer.mrmlScene )
    self.__outputVolumeNodeSelector.setMRMLScene( slicer.mrmlScene )
    self.__previewVolumeNodeSelector.setMRMLScene( slicer.mrmlScene )

    # set default values
    self.restoreDefaults()

    # compress the layout
    self.layout.addStretch( 1 )

  def onMRMLSceneChanged( self ):
    logging.debug( "onMRMLSceneChanged" )
    self.restoreDefaults()

  def onInputVolumeChanged( self ):
    logging.debug( "onInputVolumeChanged" )
    # TODO: update threshold slider range - maybe not needed?

  def onStartButtonClicked( self ):
    if self.__detectPushButton.checked:
      self.calculateParameters()

    # this is no preview
    qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)
    self.start( False )
    qt.QApplication.restoreOverrideCursor()

  def onPreviewButtonClicked( self ):
      '''
      '''
      if self.__detectPushButton.checked:
          #self.restoreDefaults()
          self.calculateParameters()

      # calculate the preview
      self.start( True )

      # activate startButton
      self.__startButton.enabled = True


  def calculateParameters( self ):
    '''
    '''

    logging.debug( "calculateParameters" )

    # first we need the nodes
    currentVolumeNode = self.__inputVolumeNodeSelector.currentNode()
    currentSeedsNode = self.__seedFiducialsNodeSelector.currentNode()

    if not currentVolumeNode:
        # we need a input volume node
        logging.debug( "calculateParameters: Have no valid volume node" )
        return False

    if not currentSeedsNode:
        # we need a seeds node
        logging.debug( "calculateParameters: Have no valid fiducial node" )
        return False

    image = currentVolumeNode.GetImageData()

    currentCoordinatesRAS = [0, 0, 0]

    # grab the current coordinates
    n = currentSeedsNode.GetNumberOfFiducials()
    currentSeedsNode.GetNthFiducialPosition(n-1,currentCoordinatesRAS)

    seed = SlicerVmtkCommonLib.Helper.ConvertRAStoIJK( currentVolumeNode, currentCoordinatesRAS )

    # we detect the diameter in IJK space (image has spacing 1,1,1) with IJK coordinates
    detectedDiameter = self.__logic.getDiameter( image, int( seed[0] ), int( seed[1] ), int( seed[2] ) )
    logging.debug( "Diameter detected: " + str( detectedDiameter ) )

    contrastMeasure = self.__logic.calculateContrastMeasure( image, int( seed[0] ), int( seed[1] ), int( seed[2] ), detectedDiameter )
    logging.debug( "Contrast measure: " + str( contrastMeasure ) )

    self.__maximumDiameterSpinBox.value = detectedDiameter
    self.__contrastSlider.value = contrastMeasure

    return True

  def restoreDefaults( self ):
    logging.debug("restoreDefaults")

    self.__detectPushButton.checked = True
    self.__minimumDiameterSpinBox.value = 1
    self.__maximumDiameterSpinBox.value = 7
    self.__suppressPlatesSlider.value = 10
    self.__suppressBlobsSlider.value = 10
    self.__contrastSlider.value = 100

    self.__startButton.enabled = False

    # if a volume is selected, the threshold slider values have to match it
    self.onInputVolumeChanged()


  def start( self, preview=False ):
    '''
    '''
    logging.debug( "Starting Vesselness Filtering.." )

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
        return False

    fitToAllSliceViews = False
    if not currentOutputVolumeNode or currentOutputVolumeNode.GetID() == currentVolumeNode.GetID():
        newVolumeNode = slicer.mrmlScene.CreateNodeByClass( "vtkMRMLScalarVolumeNode" )
        newVolumeNode.UnRegister(None)        
        newVolumeNode.SetName( slicer.mrmlScene.GetUniqueNameByString( currentOutputVolumeNodeSelector.baseName ) )
        currentOutputVolumeNode = slicer.mrmlScene.AddNode( newVolumeNode )
        currentOutputVolumeNode.CreateDefaultDisplayNodes()
        currentOutputVolumeNodeSelector.setCurrentNode( currentOutputVolumeNode )
        fitToAllSliceViews = True

    if preview and not currentSeedsNode:
        # we need a seedsNode for preview
        logging.error( "Seed point is required to use the preview mode")
        return False


    # we get the fiducial coordinates
    if currentSeedsNode:

        currentCoordinatesRAS = [0, 0, 0]

        # grab the current coordinates
        n = currentSeedsNode.GetNumberOfFiducials()
        currentSeedsNode.GetNthFiducialPosition(n-1,currentCoordinatesRAS)

    inputImage = currentVolumeNode.GetImageData()

    #
    # vesselness parameters
    #

    # we need to convert diameter to mm, we use the minimum spacing to multiply the voxel value
    minimumDiameter = self.__minimumDiameterSpinBox.value * min( currentVolumeNode.GetSpacing() )
    maximumDiameter = self.__maximumDiameterSpinBox.value * min( currentVolumeNode.GetSpacing() )

    logging.debug( minimumDiameter )
    logging.debug( maximumDiameter )

    alpha = 0.000 + 3.0 * pow((self.__suppressPlatesSlider.value)/100.0,2)
    beta  = 0.001 + 1.0 * pow((100.0-self.__suppressBlobsSlider.value)/100.0,2)

    logging.info("alpha = {0}".format(alpha))
    logging.info("beta = {0}".format(beta))
    
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
        SlicerVmtkCommonLib.Helper.extractROI( currentVolumeNode.GetID(), currentOutputVolumeNode.GetID(), currentCoordinatesRAS, self.__maximumDiameterSpinBox.value )

        # get the new cutted imageData
        image.DeepCopy( currentOutputVolumeNode.GetImageData() )

    else:

        # there was no ROI extraction, so just clone the inputImage
        image.DeepCopy( inputImage )

    # attach the spacing and origin to get accurate vesselness computation
    image.SetSpacing( currentVolumeNode.GetSpacing() )
    image.SetOrigin( currentVolumeNode.GetOrigin() )

    # we now compute the vesselness in RAS space, image has spacing and origin attached, the diameters are converted to mm
    # we use RAS space to support anisotropic datasets
    outImage.DeepCopy( self.__logic.performFrangiVesselness( image, minimumDiameter, maximumDiameter, 5, alpha, beta, contrastMeasure ) )

    # let's remove spacing and origin attached to outImage
    outImage.SetSpacing( 1, 1, 1 )
    outImage.SetOrigin( 0, 0, 0 )

    # we only want to copy the orientation from input to output when we are not in preview mode
    if not preview:
        currentOutputVolumeNode.CopyOrientation( currentVolumeNode )

    # we set the outImage which has spacing 1,1,1. The ijkToRas matrix of the node will take care of that
    currentOutputVolumeNode.SetAndObserveImageData( outImage )

    # for preview: show the inputVolume as background and the outputVolume as foreground in the slice viewers
    #    note: that's the only way we can have the preview as an overlay of the originalvolume
    # for not preview: show the outputVolume as background and the inputVolume as foreground in the slice viewers
    if preview:
        fgVolumeID = currentOutputVolumeNode.GetID()
        bgVolumeID = currentVolumeNode.GetID()
    else:
        bgVolumeID = currentOutputVolumeNode.GetID()
        fgVolumeID = currentVolumeNode.GetID()

    selectionNode = slicer.app.applicationLogic().GetSelectionNode()
    selectionNode.SetReferenceActiveVolumeID( bgVolumeID )
    selectionNode.SetReferenceSecondaryVolumeID( fgVolumeID )
    slicer.app.applicationLogic().PropagateVolumeSelection(False)

    # renew auto window/level for the output
    currentOutputVolumeNode.GetDisplayNode().AutoWindowLevelOff()
    currentOutputVolumeNode.GetDisplayNode().AutoWindowLevelOn()

    # show foreground volume
    numberOfCompositeNodes = slicer.mrmlScene.GetNumberOfNodesByClass( 'vtkMRMLSliceCompositeNode' )
    for n in xrange( numberOfCompositeNodes ):
      compositeNode = slicer.mrmlScene.GetNthNodeByClass( n, 'vtkMRMLSliceCompositeNode' )
      if compositeNode:
          if preview:
              # the preview is the foreground volume, so we want to show it fully
              compositeNode.SetForegroundOpacity( 1.0 )
          else:
              # now the background volume is the vesselness output, we want to show it fully
              compositeNode.SetForegroundOpacity( 0.0 )

    # fit slice to all sliceviewers
    if fitToAllSliceViews:
      slicer.app.applicationLogic().FitSliceToAll()

    if preview:
      # jump all sliceViewers to the fiducial point, if one was used
      if currentSeedsNode:
          numberOfSliceNodes = slicer.mrmlScene.GetNumberOfNodesByClass( 'vtkMRMLSliceNode' )
          for n in xrange( numberOfSliceNodes ):
              sliceNode = slicer.mrmlScene.GetNthNodeByClass( n, "vtkMRMLSliceNode" )
              if sliceNode:
                  sliceNode.JumpSliceByOffsetting( currentCoordinatesRAS[0], currentCoordinatesRAS[1], currentCoordinatesRAS[2] )

    currentVolumeNode.SetAndObserveNodeReferenceID("Vesselness", currentOutputVolumeNode.GetID())
                  
    logging.debug( "End of Vesselness Filtering.." )

    return True

class Slicelet( object ):
  """A slicer slicelet is a module widget that comes up in stand alone mode
  implemented as a python class.
  This class provides common wrapper functionality used by all slicer modlets.
  """
  # TODO: put this in a SliceletLib
  # TODO: parse command line arge


  def __init__( self, widgetClass=None ):
    self.parent = qt.QFrame()
    self.parent.setLayout( qt.QVBoxLayout() )

    # TODO: should have way to pop up python interactor
    self.buttons = qt.QFrame()
    self.buttons.setLayout( qt.QHBoxLayout() )
    self.parent.layout().addWidget( self.buttons )
    self.addDataButton = qt.QPushButton( "Add Data" )
    self.buttons.layout().addWidget( self.addDataButton )
    self.addDataButton.connect( "clicked()", slicer.app.ioManager().openAddDataDialog )
    self.loadSceneButton = qt.QPushButton( "Load Scene" )
    self.buttons.layout().addWidget( self.loadSceneButton )
    self.loadSceneButton.connect( "clicked()", slicer.app.ioManager().openLoadSceneDialog )

    if widgetClass:
      self.widget = widgetClass( self.parent )
      self.widget.setup()
    self.parent.show()

class VesselnessFilteringSlicelet( Slicelet ):
  """ Creates the interface when module is run as a stand alone gui app.
  """

  def __init__( self ):
    super( VesselnessFilteringSlicelet, self ).__init__( VesselnessFilteringWidget )


if __name__ == "__main__":
 # TODO: need a way to access and parse command line arguments
 # TODO: ideally command line args should handle --xml

 import sys
 print( sys.argv )

 slicelet = VesselnessFilteringSlicelet()
