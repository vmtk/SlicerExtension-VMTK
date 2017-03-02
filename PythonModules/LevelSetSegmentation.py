# slicer imports
import os
import unittest
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
import logging

# vmtk includes
import SlicerVmtkCommonLib

#
# Level Set Segmentation using VMTK based Tools
#

class LevelSetSegmentation(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """
  def __init__( self, parent ):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Level Set Segmentation"
    self.parent.categories = ["Vascular Modeling Toolkit"]
    self.parent.dependencies = []
    self.parent.contributors = ["Daniel Haehn (Boston Children's Hospital)", "Luca Antiga (Orobix)", "Steve Pieper (Isomics)"]
    self.parent.helpText = """
"""
    self.parent.acknowledgementText = """
""" # replace with organization, grant and thanks.

class LevelSetSegmentationWidget(ScriptedLoadableModuleWidget):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__( self, parent=None ):
    ScriptedLoadableModuleWidget.__init__(self, parent)

    # this flag is 1 if there is an update in progress
    self.__updating = 1

    # the pointer to the logic
    self.__logic = None

    if not parent:
      # after setup, be ready for events
      self.parent.show()
    else:
      # register default slots
      self.parent.connect( 'mrmlSceneChanged(vtkMRMLScene*)', self.onMRMLSceneChanged )

  def GetLogic( self ):
    '''
    '''
    if not self.__logic:

        self.__logic = SlicerVmtkCommonLib.LevelSetSegmentationLogic()

    return self.__logic


  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    # check if the SlicerVmtk module is installed properly
    # self.__vmtkInstalled = SlicerVmtkCommonLib.Helper.CheckIfVmtkIsInstalled()
    # Helper.Debug("VMTK found: " + self.__vmtkInstalled)

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
    self.__inputVolumeNodeSelector.toolTip = "Select the input volume. This should always be the original image and not a vesselness image, if possible."
    self.__inputVolumeNodeSelector.nodeTypes = ['vtkMRMLScalarVolumeNode']
    self.__inputVolumeNodeSelector.noneEnabled = False
    self.__inputVolumeNodeSelector.addEnabled = False
    self.__inputVolumeNodeSelector.removeEnabled = False
    ioFormLayout.addRow( "Input Volume:", self.__inputVolumeNodeSelector )
    self.parent.connect( 'mrmlSceneChanged(vtkMRMLScene*)',
                        self.__inputVolumeNodeSelector, 'setMRMLScene(vtkMRMLScene*)' )
    self.__inputVolumeNodeSelector.connect( 'currentNodeChanged(vtkMRMLNode*)', self.onInputVolumeChanged )
    self.__inputVolumeNodeSelector.connect( 'nodeActivated(vtkMRMLNode*)', self.onInputVolumeChanged )

    # seed selector
    self.__seedFiducialsNodeSelector = slicer.qMRMLNodeComboBox()
    self.__seedFiducialsNodeSelector.objectName = 'seedFiducialsNodeSelector'
    self.__seedFiducialsNodeSelector.toolTip = "Select a hierarchy containing the fiducials to use as Seeds."
    self.__seedFiducialsNodeSelector.nodeTypes = ['vtkMRMLMarkupsFiducialNode']
    self.__seedFiducialsNodeSelector.baseName = "Seeds"
    self.__seedFiducialsNodeSelector.noneEnabled = False
    self.__seedFiducialsNodeSelector.addEnabled = False
    self.__seedFiducialsNodeSelector.removeEnabled = False
    ioFormLayout.addRow( "Seeds:", self.__seedFiducialsNodeSelector )
    self.parent.connect( 'mrmlSceneChanged(vtkMRMLScene*)',
                        self.__seedFiducialsNodeSelector, 'setMRMLScene(vtkMRMLScene*)' )

    self.__ioAdvancedToggle = qt.QCheckBox( "Show Advanced I/O Properties" )
    self.__ioAdvancedToggle.setChecked( False )
    ioFormLayout.addRow( self.__ioAdvancedToggle )

    #
    # I/O advanced panel
    #

    self.__ioAdvancedPanel = qt.QFrame( ioCollapsibleButton )
    self.__ioAdvancedPanel.hide()
    self.__ioAdvancedPanel.setFrameStyle( 6 )
    ioFormLayout.addRow( self.__ioAdvancedPanel )
    self.__ioAdvancedToggle.connect( "clicked()", self.onIOAdvancedToggle )

    ioAdvancedFormLayout = qt.QFormLayout( self.__ioAdvancedPanel )

    # inputVolume selector
    self.__vesselnessVolumeNodeSelector = slicer.qMRMLNodeComboBox()
    self.__vesselnessVolumeNodeSelector.objectName = 'vesselnessVolumeNodeSelector'
    self.__vesselnessVolumeNodeSelector.toolTip = "Select the input vesselness volume. This is optional input."
    self.__vesselnessVolumeNodeSelector.nodeTypes = ['vtkMRMLScalarVolumeNode']
    self.__vesselnessVolumeNodeSelector.noneEnabled = True
    self.__vesselnessVolumeNodeSelector.addEnabled = False
    self.__vesselnessVolumeNodeSelector.removeEnabled = False
    ioAdvancedFormLayout.addRow( "Vesselness Volume:", self.__vesselnessVolumeNodeSelector )
    self.parent.connect( 'mrmlSceneChanged(vtkMRMLScene*)',
                        self.__vesselnessVolumeNodeSelector, 'setMRMLScene(vtkMRMLScene*)' )
    self.__vesselnessVolumeNodeSelector.setCurrentNode( None )

    # stopper selector
    self.__stopperFiducialsNodeSelector = slicer.qMRMLNodeComboBox()
    self.__stopperFiducialsNodeSelector.objectName = 'stopperFiducialsNodeSelector'
    self.__stopperFiducialsNodeSelector.toolTip = "Select a hierarchy containing the fiducials to use as Stoppers. Whenever one stopper is reached, the segmentation stops."
    self.__stopperFiducialsNodeSelector.nodeTypes = ['vtkMRMLMarkupsFiducialNode']
    self.__stopperFiducialsNodeSelector.baseName = "Stoppers"
    self.__stopperFiducialsNodeSelector.noneEnabled = False
    self.__stopperFiducialsNodeSelector.addEnabled = True
    self.__stopperFiducialsNodeSelector.removeEnabled = False
    ioAdvancedFormLayout.addRow( "Stoppers:", self.__stopperFiducialsNodeSelector )
    self.parent.connect( 'mrmlSceneChanged(vtkMRMLScene*)',
                        self.__stopperFiducialsNodeSelector, 'setMRMLScene(vtkMRMLScene*)' )

    # outputVolume selector
    self.__outputVolumeNodeSelector = slicer.qMRMLNodeComboBox()
    self.__outputVolumeNodeSelector.toolTip = "Select the output labelmap."
    self.__outputVolumeNodeSelector.nodeTypes = ['vtkMRMLLabelMapVolumeNode']
    self.__outputVolumeNodeSelector.baseName = "LevelSetSegmentation"
    self.__outputVolumeNodeSelector.noneEnabled = False
    self.__outputVolumeNodeSelector.addEnabled = True
    self.__outputVolumeNodeSelector.selectNodeUponCreation = True
    self.__outputVolumeNodeSelector.removeEnabled = True
    ioAdvancedFormLayout.addRow( "Output Labelmap:", self.__outputVolumeNodeSelector )
    self.parent.connect( 'mrmlSceneChanged(vtkMRMLScene*)',
                        self.__outputVolumeNodeSelector, 'setMRMLScene(vtkMRMLScene*)' )

    # outputModel selector
    self.__outputModelNodeSelector = slicer.qMRMLNodeComboBox()
    self.__outputModelNodeSelector.objectName = 'outputModelNodeSelector'
    self.__outputModelNodeSelector.toolTip = "Select the output model."
    self.__outputModelNodeSelector.nodeTypes = ['vtkMRMLModelNode']
    self.__outputModelNodeSelector.baseName = "LevelSetSegmentationModel"
    self.__outputModelNodeSelector.hideChildNodeTypes = ['vtkMRMLMarkupsFiducialNode']# hide all annotation nodes
    self.__outputModelNodeSelector.noneEnabled = False
    self.__outputModelNodeSelector.addEnabled = True
    self.__outputModelNodeSelector.selectNodeUponCreation = True
    self.__outputModelNodeSelector.removeEnabled = True
    ioAdvancedFormLayout.addRow( "Output Model:", self.__outputModelNodeSelector )
    self.parent.connect( 'mrmlSceneChanged(vtkMRMLScene*)',
                        self.__outputModelNodeSelector, 'setMRMLScene(vtkMRMLScene*)' )


    #
    # the segmentation panel
    #

    segmentationCollapsibleButton = ctk.ctkCollapsibleButton()
    segmentationCollapsibleButton.text = "Segmentation"
    self.layout.addWidget( segmentationCollapsibleButton )

    segmentationFormLayout = qt.QFormLayout( segmentationCollapsibleButton )

    # Threshold slider
    thresholdLabel = qt.QLabel()
    thresholdLabel.text = "Thresholding" + SlicerVmtkCommonLib.Helper.CreateSpace( 7 )
    thresholdLabel.toolTip = "Choose the intensity range to segment."
    thresholdLabel.setAlignment( 4 )
    segmentationFormLayout.addRow( thresholdLabel )

    self.__thresholdSlider = slicer.qMRMLRangeWidget()
    segmentationFormLayout.addRow( self.__thresholdSlider )
    self.__thresholdSlider.connect( 'valuesChanged(double,double)', self.onThresholdSliderChanged )

    self.__segmentationAdvancedToggle = qt.QCheckBox( "Show Advanced Segmentation Properties" )
    self.__segmentationAdvancedToggle.setChecked( False )
    segmentationFormLayout.addRow( self.__segmentationAdvancedToggle )

    #
    # segmentation advanced panel
    #

    self.__segmentationAdvancedPanel = qt.QFrame( segmentationCollapsibleButton )
    self.__segmentationAdvancedPanel.hide()
    self.__segmentationAdvancedPanel.setFrameStyle( 6 )
    segmentationFormLayout.addRow( self.__segmentationAdvancedPanel )
    self.__segmentationAdvancedToggle.connect( "clicked()", self.onSegmentationAdvancedToggle )

    segmentationAdvancedFormLayout = qt.QFormLayout( self.__segmentationAdvancedPanel )

    # inflation slider
    inflationLabel = qt.QLabel()
    inflationLabel.text = "less inflation <-> more inflation" + SlicerVmtkCommonLib.Helper.CreateSpace( 14 )
    inflationLabel.setAlignment( 4 )
    inflationLabel.toolTip = "Define how fast the segmentation expands."
    segmentationAdvancedFormLayout.addRow( inflationLabel )

    self.__inflationSlider = ctk.ctkSliderWidget()
    self.__inflationSlider.decimals = 0
    self.__inflationSlider.minimum = -100
    self.__inflationSlider.maximum = 100
    self.__inflationSlider.singleStep = 10
    self.__inflationSlider.toolTip = inflationLabel.toolTip
    segmentationAdvancedFormLayout.addRow( self.__inflationSlider )

    # curvature slider
    curvatureLabel = qt.QLabel()
    curvatureLabel.text = "less curvature <-> more curvature" + SlicerVmtkCommonLib.Helper.CreateSpace( 14 )
    curvatureLabel.setAlignment( 4 )
    curvatureLabel.toolTip = "Choose a high curvature to generate a smooth segmentation."
    segmentationAdvancedFormLayout.addRow( curvatureLabel )

    self.__curvatureSlider = ctk.ctkSliderWidget()
    self.__curvatureSlider.decimals = 0
    self.__curvatureSlider.minimum = -100
    self.__curvatureSlider.maximum = 100
    self.__curvatureSlider.singleStep = 10
    self.__curvatureSlider.toolTip = curvatureLabel.toolTip
    segmentationAdvancedFormLayout.addRow( self.__curvatureSlider )

    # attraction slider
    attractionLabel = qt.QLabel()
    attractionLabel.text = "less attraction to gradient <-> more attraction to gradient" + SlicerVmtkCommonLib.Helper.CreateSpace( 14 )
    attractionLabel.setAlignment( 4 )
    attractionLabel.toolTip = "Configure how the segmentation travels towards gradient ridges (vessel lumen wall)."
    segmentationAdvancedFormLayout.addRow( attractionLabel )

    self.__attractionSlider = ctk.ctkSliderWidget()
    self.__attractionSlider.decimals = 0
    self.__attractionSlider.minimum = -100
    self.__attractionSlider.maximum = 100
    self.__attractionSlider.singleStep = 10
    self.__attractionSlider.toolTip = attractionLabel.toolTip
    segmentationAdvancedFormLayout.addRow( self.__attractionSlider )

    # iteration spinbox
    self.__iterationSpinBox = qt.QSpinBox()
    self.__iterationSpinBox.minimum = 0
    self.__iterationSpinBox.maximum = 5000
    self.__iterationSpinBox.singleStep = 10
    self.__iterationSpinBox.toolTip = "Choose the number of evolution iterations."
    segmentationAdvancedFormLayout.addRow( SlicerVmtkCommonLib.Helper.CreateSpace( 100 ) + "Iterations:", self.__iterationSpinBox )

    #
    # Reset, preview and apply buttons
    #

    self.__buttonBox = qt.QDialogButtonBox()
    self.__resetButton = self.__buttonBox.addButton( self.__buttonBox.RestoreDefaults )
    self.__resetButton.toolTip = "Click to reset all input elements to default."
    self.__previewButton = self.__buttonBox.addButton( self.__buttonBox.Discard )
    self.__previewButton.setIcon( qt.QIcon() )
    self.__previewButton.text = "Preview.."
    self.__previewButton.toolTip = "Click to refresh the preview."
    self.__startButton = self.__buttonBox.addButton( self.__buttonBox.Apply )
    self.__startButton.setIcon( qt.QIcon() )
    self.__startButton.text = "Start!"
    self.__startButton.enabled = False
    self.__startButton.toolTip = "Click to start the filtering."
    self.layout.addWidget( self.__buttonBox )
    self.__resetButton.connect( "clicked()", self.restoreDefaults )
    self.__previewButton.connect( "clicked()", self.onRefreshButtonClicked )
    self.__startButton.connect( "clicked()", self.onStartButtonClicked )

    self.__inputVolumeNodeSelector.setMRMLScene( slicer.mrmlScene )
    self.__seedFiducialsNodeSelector.setMRMLScene( slicer.mrmlScene )
    self.__vesselnessVolumeNodeSelector.setMRMLScene( slicer.mrmlScene )
    self.__outputVolumeNodeSelector.setMRMLScene( slicer.mrmlScene )
    self.__outputModelNodeSelector.setMRMLScene( slicer.mrmlScene )
    self.__stopperFiducialsNodeSelector.setMRMLScene( slicer.mrmlScene )

    # be ready for events
    self.__updating = 0

    # set default values
    self.restoreDefaults()

    # compress the layout
    self.layout.addStretch( 1 )


  def onStartButtonClicked( self ):
      '''
      '''
      # this is no preview
      self.start( False )


  def onRefreshButtonClicked( self ):
      '''
      '''

      # perform the preview
      self.start( True )

      # activate startButton
      self.__startButton.enabled = True


  def onMRMLSceneChanged( self ):
    '''
    '''
    SlicerVmtkCommonLib.Helper.Debug( "onMRMLSceneChanged" )
    self.restoreDefaults()

  def selectVesselnessVolume( self ):
    '''
    '''
    currentNode = self.__inputVolumeNodeSelector.currentNode()
    currentVesselnessNode = self.__vesselnessVolumeNodeSelector.currentNode()

    if currentVesselnessNode:
        return currentVesselnessNode

    # check if we have a corresponding vesselness node in the scene and set it then
    v = None
    vesselnessCollection = slicer.mrmlScene.GetNodesByClassByName( "vtkMRMLScalarVolumeNode", "VesselnessFiltered" )
    numberOfVesselnessNodes = vesselnessCollection.GetNumberOfItems()
    SlicerVmtkCommonLib.Helper.Debug( "Found " + str( numberOfVesselnessNodes ) + " Vesselness node(s).." )
    for i in xrange( numberOfVesselnessNodes ):
        v = vesselnessCollection.GetItemAsObject( i )
        if ( v.GetImageData().GetDimensions() == currentNode.GetImageData().GetDimensions() and
            v.GetSpacing() == currentNode.GetSpacing() and
            v.GetOrigin() == currentNode.GetOrigin() ):

            # this is likely the corresponding vesselness node
            SlicerVmtkCommonLib.Helper.Debug( "Configuring vesselnessVolumeNodeSelector to use: " + str( v.GetName() ) + " id: " + str( v.GetID() ) )
            self.__vesselnessVolumeNodeSelector.setCurrentNode( v )

            # jump out of loop
            break

    return v



  def onInputVolumeChanged( self ):
    '''
    '''
    if not self.__updating:

        self.__updating = 1

        SlicerVmtkCommonLib.Helper.Debug( "onInputVolumeChanged" )

        # reset the thresholdSlider
        self.__thresholdSlider.minimum = 0
        self.__thresholdSlider.maximum = 100
        self.__thresholdSlider.minimumValue = 0
        self.__thresholdSlider.maximumValue = 100

        currentNode = self.__inputVolumeNodeSelector.currentNode()

        if currentNode:

            v = self.selectVesselnessVolume()

            # if we have a vesselnessNode, we will configure the threshold slider for it instead of the original image
            # if not, the currentNode is the input volume
            if v:
                SlicerVmtkCommonLib.Helper.Debug( "Using Vesselness volume to configure thresholdSlider.." )
                currentNode = v

            currentImageData = currentNode.GetImageData()
            currentDisplayNode = currentNode.GetDisplayNode()

            if currentImageData:
                currentScalarRange = currentImageData.GetScalarRange()
                minimumScalarValue = round( currentScalarRange[0], 0 )
                maximumScalarValue = round( currentScalarRange[1], 0 )
                self.__thresholdSlider.minimum = minimumScalarValue
                self.__thresholdSlider.maximum = maximumScalarValue

                # if the image has a small scalarRange, we have to adjust the singleStep
                if maximumScalarValue <= 10:
                    self.__thresholdSlider.singleStep = 0.1

                if currentDisplayNode:

                    if currentDisplayNode.GetApplyThreshold():

                        # if a threshold is already applied, use it!
                        self.__thresholdSlider.minimumValue = currentDisplayNode.GetLowerThreshold()
                        self.__thresholdSlider.maximumValue = currentDisplayNode.GetUpperThreshold()

                    else:

                        # don't use a threshold, use the scalar range
                        SlicerVmtkCommonLib.Helper.Debug( "Reset thresholdSlider's values." )
                        self.__thresholdSlider.minimumValue = minimumScalarValue
                        self.__thresholdSlider.maximumValue = maximumScalarValue




        self.__updating = 0


  def resetThresholdOnDisplayNode( self ):
    '''
    '''
    if not self.__updating:

        self.__updating = 1

        SlicerVmtkCommonLib.Helper.Debug( "resetThresholdOnDisplayNode" )

        currentNode = self.__inputVolumeNodeSelector.currentNode()

        if currentNode:
            currentDisplayNode = currentNode.GetDisplayNode()

            if currentDisplayNode:
                currentDisplayNode.SetApplyThreshold( 0 )

        self.__updating = 0

  def onThresholdSliderChanged( self ):
    '''
    '''
    if not self.__updating:

        self.__updating = 1

        # first, check if we have a vesselness node
        currentNode = self.selectVesselnessVolume()

        if currentNode:
            SlicerVmtkCommonLib.Helper.Debug( "There was a vesselness node: " + str( currentNode.GetName() ) )
        else:
            SlicerVmtkCommonLib.Helper.Debug( "There was no vesselness node.." )
            # if we don't have a vesselness node, check if we have an original input node
            currentNode = self.__inputVolumeNodeSelector.currentNode()

        if currentNode:
            currentDisplayNode = currentNode.GetDisplayNode()

            if currentDisplayNode:

                currentDisplayNode.SetLowerThreshold( self.__thresholdSlider.minimumValue )
                currentDisplayNode.SetUpperThreshold( self.__thresholdSlider.maximumValue )
                currentDisplayNode.SetApplyThreshold( 1 )

        self.__updating = 0


  def onIOAdvancedToggle( self ):
    '''
    Show the I/O Advanced panel
    '''
    if self.__ioAdvancedToggle.checked:
      self.__ioAdvancedPanel.show()
    else:
      self.__ioAdvancedPanel.hide()

  def onSegmentationAdvancedToggle( self ):
    '''
    Show the Segmentation Advanced panel
    '''
    if self.__segmentationAdvancedToggle.checked:
      self.__segmentationAdvancedPanel.show()
    else:
      self.__segmentationAdvancedPanel.hide()

  def restoreDefaults( self ):
    '''
    scope == 0: reset all
    scope == 1: reset only threshold slider
    '''
    if not self.__updating:

        self.__updating = 1

        SlicerVmtkCommonLib.Helper.Debug( "restoreDefaults" )

        self.__thresholdSlider.minimum = 0
        self.__thresholdSlider.maximum = 100
        self.__thresholdSlider.minimumValue = 0
        self.__thresholdSlider.maximumValue = 100
        self.__thresholdSlider.singleStep = 1

        self.__ioAdvancedToggle.setChecked( False )
        self.__segmentationAdvancedToggle.setChecked( False )
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
        self.onInputVolumeChanged()




  def start( self, preview=False ):
    '''
    '''
    SlicerVmtkCommonLib.Helper.Debug( "Starting Level Set Segmentation.." )

    # first we need the nodes
    currentVolumeNode = self.__inputVolumeNodeSelector.currentNode()
    currentSeedsNode = self.__seedFiducialsNodeSelector.currentNode()
    currentVesselnessNode = self.__vesselnessVolumeNodeSelector.currentNode()
    currentStoppersNode = self.__stopperFiducialsNodeSelector.currentNode()
    currentLabelMapNode = self.__outputVolumeNodeSelector.currentNode()
    currentModelNode = self.__outputModelNodeSelector.currentNode()

    if not currentVolumeNode:
        # we need a input volume node
        return 0

    if not currentSeedsNode:
        # we need a seeds node
        return 0

    if not currentStoppersNode or currentStoppersNode.GetID() == currentSeedsNode.GetID():
        # we need a current stopper node
        # self.__stopperFiducialsNodeSelector.addNode()
        pass

    if not currentLabelMapNode or currentLabelMapNode.GetID() == currentVolumeNode.GetID():
        # we need a current labelMap node
        newLabelMapDisplayNode = slicer.mrmlScene.CreateNodeByClass( "vtkMRMLLabelMapVolumeDisplayNode" )
        newLabelMapDisplayNode.SetScene( slicer.mrmlScene )
        newLabelMapDisplayNode.SetDefaultColorMap()
        slicer.mrmlScene.AddNode( newLabelMapDisplayNode )

        newLabelMapNode = slicer.mrmlScene.CreateNodeByClass( "vtkMRMLLabelMapVolumeNode" )
        newLabelMapNode.CopyOrientation( currentVolumeNode )
        newLabelMapNode.SetScene( slicer.mrmlScene )
        newLabelMapNode.SetName( slicer.mrmlScene.GetUniqueNameByString( self.__outputVolumeNodeSelector.baseName ) )
        newLabelMapNode.SetAndObserveDisplayNodeID( newLabelMapDisplayNode.GetID() )
        slicer.mrmlScene.AddNode( newLabelMapNode )
        currentLabelMapNode = newLabelMapNode
        self.__outputVolumeNodeSelector.setCurrentNode( currentLabelMapNode )

    if not currentModelNode:
        # we need a current model node, the display node is created later
        newModelNode = slicer.mrmlScene.CreateNodeByClass( "vtkMRMLModelNode" )
        newModelNode.SetScene( slicer.mrmlScene )
        newModelNode.SetName( slicer.mrmlScene.GetUniqueNameByString( self.__outputModelNodeSelector.baseName ) )
        slicer.mrmlScene.AddNode( newModelNode )
        currentModelNode = newModelNode

        self.__outputModelNodeSelector.setCurrentNode( currentModelNode )

    # now we need to convert the fiducials to vtkIdLists
    seeds = SlicerVmtkCommonLib.Helper.convertFiducialHierarchyToVtkIdList( currentSeedsNode, currentVolumeNode )
    # stoppers = SlicerVmtkCommonLib.Helper.convertFiducialHierarchyToVtkIdList(currentStoppersNode, currentVolumeNode)
    stoppers = vtk.vtkIdList()  # TODO

    # the input image for the initialization
    inputImage = vtk.vtkImageData()

    # check if we have a vesselnessNode - this will be our input for the initialization then
    if currentVesselnessNode:
        # yes, there is one
        inputImage.DeepCopy( currentVesselnessNode.GetImageData() )
    else:
        # no, there is none - we use the original image
        inputImage.DeepCopy( currentVolumeNode.GetImageData() )

    # initialization
    initImageData = vtk.vtkImageData()

    # evolution
    evolImageData = vtk.vtkImageData()

    # perform the initialization
    initImageData.DeepCopy( self.GetLogic().performInitialization( inputImage,
                                                                 self.__thresholdSlider.minimumValue,
                                                                 self.__thresholdSlider.maximumValue,
                                                                 seeds,
                                                                 stoppers,
                                                                 0 ) )  # TODO sidebranch ignore feature

    if not initImageData.GetPointData().GetScalars():
        # something went wrong, the image is empty
        SlicerVmtkCommonLib.Helper.Info( "Segmentation failed - the output was empty.." )
        return -1

    # check if it is a preview call
    if preview:

        # if this is a preview call, we want to skip the evolution
        evolImageData.DeepCopy( initImageData )

    else:

        # no preview, run the whole thing! we never use the vesselness node here, just the original one
        evolImageData.DeepCopy( self.GetLogic().performEvolution( currentVolumeNode.GetImageData(),
                                                                initImageData,
                                                                self.__iterationSpinBox.value,
                                                                self.__inflationSlider.value,
                                                                self.__curvatureSlider.value,
                                                                self.__attractionSlider.value,
                                                                'geodesic' ) )


    # create segmentation labelMap
    labelMap = vtk.vtkImageData()
    labelMap.DeepCopy( self.GetLogic().buildSimpleLabelMap( evolImageData, 5, 0 ) )

    currentLabelMapNode.CopyOrientation( currentVolumeNode )

    # propagate the label map to the node
    currentLabelMapNode.SetAndObserveImageData( labelMap )
    currentLabelMapNode.Modified()

    # deactivate the threshold in the GUI
    self.resetThresholdOnDisplayNode()
    # self.onInputVolumeChanged()

    # show the segmentation results in the GUI
    selectionNode = slicer.app.applicationLogic().GetSelectionNode()

    if preview and currentVesselnessNode:
        # if preview and a vesselnessNode was configured, show it
        selectionNode.SetReferenceActiveVolumeID( currentVesselnessNode.GetID() )
    else:
        # if not preview, show the original volume
        if currentVesselnessNode:
            selectionNode.SetReferenceSecondaryVolumeID( currentVesselnessNode.GetID() )
        selectionNode.SetReferenceActiveVolumeID( currentVolumeNode.GetID() )
    selectionNode.SetReferenceActiveLabelVolumeID( currentLabelMapNode.GetID() )
    slicer.app.applicationLogic().PropagateVolumeSelection()

    # generate 3D model
    model = vtk.vtkPolyData()

    # we need the ijkToRas transform for the marching cubes call
    ijkToRasMatrix = vtk.vtkMatrix4x4()
    currentLabelMapNode.GetIJKToRASMatrix( ijkToRasMatrix )

    # call marching cubes
    model.DeepCopy( self.GetLogic().marchingCubes( evolImageData, ijkToRasMatrix, 0.0 ) )

    # propagate model to nodes
    currentModelNode.SetAndObservePolyData( model )
    currentModelNode.Modified()

    currentModelDisplayNode = currentModelNode.GetDisplayNode()

    if not currentModelDisplayNode:

        # create new displayNode
        currentModelDisplayNode = slicer.mrmlScene.CreateNodeByClass( "vtkMRMLModelDisplayNode" )
        slicer.mrmlScene.AddNode( currentModelDisplayNode )

    # always configure the displayNode to show the model
    currentModelDisplayNode.SetColor( 1.0, 0.55, 0.4 )  # red
    currentModelDisplayNode.SetBackfaceCulling( 0 )
    currentModelDisplayNode.SetSliceIntersectionVisibility( 0 )
    currentModelDisplayNode.SetVisibility( 1 )
    currentModelDisplayNode.SetOpacity( 1.0 )
    currentModelDisplayNode.Modified()

    # update the reference between model node and it's display node
    currentModelNode.SetAndObserveDisplayNodeID( currentModelDisplayNode.GetID() )
    currentModelNode.Modified()

    # fit slice to all sliceviewers
    slicer.app.applicationLogic().FitSliceToAll()

    # jump all sliceViewers to the first fiducial point, if one was used
    if currentSeedsNode:

        currentCoordinatesRAS = [0, 0, 0]

        if isinstance( currentSeedsNode, slicer.vtkMRMLMarkupsFiducialNode ):

            # let's get the first children
            currentSeedsNode.GetNthFiducialPosition(0,currentCoordinatesRAS)

        numberOfSliceNodes = slicer.mrmlScene.GetNumberOfNodesByClass( 'vtkMRMLSliceNode' )
        for n in xrange( numberOfSliceNodes ):
            sliceNode = slicer.mrmlScene.GetNthNodeByClass( n, "vtkMRMLSliceNode" )
            if sliceNode:
                sliceNode.JumpSliceByOffsetting( currentCoordinatesRAS[0], currentCoordinatesRAS[1], currentCoordinatesRAS[2] )


    # center 3D view(s) on the new model
    if currentCoordinatesRAS:
        for d in range( slicer.app.layoutManager().threeDViewCount ):

            threeDView = slicer.app.layoutManager().threeDWidget( d ).threeDView()

            # reset the focal point
            threeDView.resetFocalPoint()

            # and fly to our seed point
            interactor = threeDView.interactor()
            renderer = threeDView.renderWindow().GetRenderers().GetItemAsObject( 0 )
            interactor.FlyTo( renderer, currentCoordinatesRAS[0], currentCoordinatesRAS[1], currentCoordinatesRAS[2] )

    SlicerVmtkCommonLib.Helper.Debug( "End of Level Set Segmentation.." )


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

class LevelSetSegmentationSlicelet( Slicelet ):
  """ Creates the interface when module is run as a stand alone gui app.
  """

  def __init__( self ):
    super( LevelSetSegmentationSlicelet, self ).__init__( LevelSetSegmentationWidget )


if __name__ == "__main__":
  # TODO: need a way to access and parse command line arguments
  # TODO: ideally command line args should handle --xml

  import sys
  print( sys.argv )

  slicelet = LevelSetSegmentationSlicelet()

