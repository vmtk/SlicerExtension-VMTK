# slicer imports
import os
import unittest
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
import logging

# vmtk includes
import SlicerVmtkCommonLib

# python includes
import math

#
# Centerline Computation using VMTK based Tools
#

class CenterlineComputation(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """
  def __init__( self, parent ):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Centerline Computation"
    self.parent.categories = ["Vascular Modeling Toolkit"]
    self.parent.dependencies = []
    self.parent.contributors = ["Daniel Haehn (Boston Children's Hospital)", "Luca Antiga (Orobix)", "Steve Pieper (Isomics)"]
    self.parent.helpText = """
"""
    self.parent.acknowledgementText = """
""" # replace with organization, grant and thanks.

class CenterlineComputationWidget(ScriptedLoadableModuleWidget):
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

        self.__logic = SlicerVmtkCommonLib.CenterlineComputationLogic()

    return self.__logic


  def setup( self ):
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
    self.__inputModelNodeSelector = slicer.qMRMLNodeComboBox()
    self.__inputModelNodeSelector.objectName = 'inputModelNodeSelector'
    self.__inputModelNodeSelector.toolTip = "Select the input model."
    self.__inputModelNodeSelector.nodeTypes = ['vtkMRMLModelNode']
    self.__inputModelNodeSelector.hideChildNodeTypes = ['vtkMRMLAnnotationNode']  # hide all annotation nodes
    self.__inputModelNodeSelector.noneEnabled = False
    self.__inputModelNodeSelector.addEnabled = False
    self.__inputModelNodeSelector.removeEnabled = False
    ioFormLayout.addRow( "Input Model:", self.__inputModelNodeSelector )
    self.parent.connect( 'mrmlSceneChanged(vtkMRMLScene*)',
                        self.__inputModelNodeSelector, 'setMRMLScene(vtkMRMLScene*)' )
    self.__inputModelNodeSelector.connect( 'currentNodeChanged(vtkMRMLNode*)', self.onInputModelChanged )

    # seed selector
    self.__seedFiducialsNodeSelector = slicer.qMRMLNodeComboBox()
    self.__seedFiducialsNodeSelector.objectName = 'seedFiducialsNodeSelector'
    self.__seedFiducialsNodeSelector.toolTip = "Select a fiducial to use as the origin of the Centerline."
    self.__seedFiducialsNodeSelector.nodeTypes = ['vtkMRMLMarkupsFiducialNode']
    self.__seedFiducialsNodeSelector.baseName = "OriginSeed"
    self.__seedFiducialsNodeSelector.noneEnabled = False
    self.__seedFiducialsNodeSelector.addEnabled = False
    self.__seedFiducialsNodeSelector.removeEnabled = False
    ioFormLayout.addRow( "Start Point:", self.__seedFiducialsNodeSelector )
    self.parent.connect( 'mrmlSceneChanged(vtkMRMLScene*)',
                        self.__seedFiducialsNodeSelector, 'setMRMLScene(vtkMRMLScene*)' )
    self.__seedFiducialsNodeSelector.connect( 'currentNodeChanged(vtkMRMLNode*)', self.onSeedChanged )


    self.__ioAdvancedToggle = qt.QCheckBox( "Show Advanced Properties" )
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

    # outputModel selector
    self.__outputModelNodeSelector = slicer.qMRMLNodeComboBox()
    self.__outputModelNodeSelector.objectName = 'outputModelNodeSelector'
    self.__outputModelNodeSelector.toolTip = "Select the output model for the Centerlines."
    self.__outputModelNodeSelector.nodeTypes = ['vtkMRMLModelNode']
    self.__outputModelNodeSelector.baseName = "CenterlineComputationModel"
    self.__outputModelNodeSelector.hideChildNodeTypes = ['vtkMRMLAnnotationNode']  # hide all annotation nodes
    self.__outputModelNodeSelector.noneEnabled = False
    self.__outputModelNodeSelector.addEnabled = True
    self.__outputModelNodeSelector.selectNodeUponCreation = True
    self.__outputModelNodeSelector.removeEnabled = True
    ioAdvancedFormLayout.addRow( "Output Centerline Model:", self.__outputModelNodeSelector )
    self.parent.connect( 'mrmlSceneChanged(vtkMRMLScene*)',
                        self.__outputModelNodeSelector, 'setMRMLScene(vtkMRMLScene*)' )

    # voronoiModel selector
    self.__voronoiModelNodeSelector = slicer.qMRMLNodeComboBox()
    self.__voronoiModelNodeSelector.objectName = 'voronoiModelNodeSelector'
    self.__voronoiModelNodeSelector.toolTip = "Select the output model for the Voronoi Diagram."
    self.__voronoiModelNodeSelector.nodeTypes = ['vtkMRMLModelNode']
    self.__voronoiModelNodeSelector.baseName = "VoronoiModel"
    self.__voronoiModelNodeSelector.hideChildNodeTypes = ['vtkMRMLAnnotationNode']  # hide all annotation nodes
    self.__voronoiModelNodeSelector.noneEnabled = False
    self.__voronoiModelNodeSelector.addEnabled = True
    self.__voronoiModelNodeSelector.selectNodeUponCreation = True
    self.__voronoiModelNodeSelector.removeEnabled = True
    ioAdvancedFormLayout.addRow( "Output Voronoi Model:", self.__voronoiModelNodeSelector )
    self.parent.connect( 'mrmlSceneChanged(vtkMRMLScene*)',
                        self.__voronoiModelNodeSelector, 'setMRMLScene(vtkMRMLScene*)' )




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

    self.__inputModelNodeSelector.setMRMLScene( slicer.mrmlScene )
    self.__seedFiducialsNodeSelector.setMRMLScene( slicer.mrmlScene )
    self.__outputModelNodeSelector.setMRMLScene( slicer.mrmlScene )
    self.__voronoiModelNodeSelector.setMRMLScene( slicer.mrmlScene )

    # be ready for events
    self.__updating = 0

    # set default values
    self.restoreDefaults()

    # compress the layout
    self.layout.addStretch( 1 )




  def onMRMLSceneChanged( self ):
    '''
    '''
    SlicerVmtkCommonLib.Helper.Debug( "onMRMLSceneChanged" )
    self.restoreDefaults()

  def onInputModelChanged( self ):
    '''
    '''
    if not self.__updating:

        self.__updating = 1

        SlicerVmtkCommonLib.Helper.Debug( "onInputModelChanged" )

        # do nothing right now

        self.__updating = 0

  def onSeedChanged( self ):
    '''
    '''
    if not self.__updating:

        self.__updating = 1

        # nothing yet

        self.__updating = 0

  def onStartButtonClicked( self ):
      '''
      '''

      self.__startButton.enabled = True

      # this is no preview
      self.start( False )

  def onRefreshButtonClicked( self ):
      '''
      '''

      # calculate the preview
      self.start( True )

      # activate startButton
      self.__startButton.enabled = True



  def onIOAdvancedToggle( self ):
    '''
    Show the I/O Advanced panel
    '''

    if self.__ioAdvancedToggle.checked:
      self.__ioAdvancedPanel.show()
    else:
      self.__ioAdvancedPanel.hide()

  def restoreDefaults( self ):
    '''
    '''
    if not self.__updating:

        self.__updating = 1

        SlicerVmtkCommonLib.Helper.Debug( "restoreDefaults" )


        self.__startButton.enabled = False

        self.__updating = 0


        self.onInputModelChanged()


  def start( self, preview=False ):
    '''
    '''
    SlicerVmtkCommonLib.Helper.Debug( "Starting Centerline Computation.." )

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
        newModelNode = slicer.mrmlScene.CreateNodeByClass( "vtkMRMLModelNode" )
        newModelNode.SetScene( slicer.mrmlScene )
        newModelNode.SetName( slicer.mrmlScene.GetUniqueNameByString( self.__outputModelNodeSelector.baseName ) )
        slicer.mrmlScene.AddNode( newModelNode )
        currentOutputModelNode = newModelNode

        self.__outputModelNodeSelector.setCurrentNode( currentOutputModelNode )

    if not currentVoronoiModelNode or currentVoronoiModelNode.GetID() == currentModelNode.GetID() or currentVoronoiModelNode.GetID() == currentOutputModelNode.GetID():
        # we need a current model node, the display node is created later
        newModelNode = slicer.mrmlScene.CreateNodeByClass( "vtkMRMLModelNode" )
        newModelNode.SetScene( slicer.mrmlScene )
        newModelNode.SetName( slicer.mrmlScene.GetUniqueNameByString( self.__voronoiModelNodeSelector.baseName ) )
        slicer.mrmlScene.AddNode( newModelNode )
        currentVoronoiModelNode = newModelNode

        self.__voronoiModelNodeSelector.setCurrentNode( currentVoronoiModelNode )

    # the output models
    preparedModel = vtk.vtkPolyData()
    model = vtk.vtkPolyData()
    network = vtk.vtkPolyData()
    voronoi = vtk.vtkPolyData()

    currentCoordinatesRAS = [0, 0, 0]

    # grab the current coordinates
    currentSeedsNode.GetNthFiducialPosition(0,currentCoordinatesRAS)

    # prepare the model
    preparedModel.DeepCopy( self.GetLogic().prepareModel( currentModelNode.GetPolyData() ) )

    # decimate the model (only for network extraction)
    model.DeepCopy( self.GetLogic().decimateSurface( preparedModel ) )

    # open the model at the seed (only for network extraction)
    model.DeepCopy( self.GetLogic().openSurfaceAtPoint( model, currentCoordinatesRAS ) )

    # extract Network
    network.DeepCopy( self.GetLogic().extractNetwork( model ) )

    #
    #
    # not preview mode: real computation!
    if not preview:
        # here we start the actual centerline computation which is mathematically more robust and accurate but takes longer than the network extraction

        # clip surface at endpoints identified by the network extraction
        tupel = self.GetLogic().clipSurfaceAtEndPoints( network, currentModelNode.GetPolyData() )
        clippedSurface = tupel[0]
        endpoints = tupel[1]

        # now find the one endpoint which is closest to the seed and use it as the source point for centerline computation
        # all other endpoints are the target points
        sourcePoint = [0, 0, 0]

        # the following arrays have the same indexes and are synchronized at all times
        distancesToSeed = []
        targetPoints = []

        # we now need to loop through the endpoints two times

        # first loop is to detect the endpoint resulting in the tiny hole we poked in the surface
        # this is very close to our seed but not the correct sourcePoint
        for i in range( endpoints.GetNumberOfPoints() ):

            currentPoint = endpoints.GetPoint( i )
            # get the euclidean distance
            currentDistanceToSeed = math.sqrt( math.pow( ( currentPoint[0] - currentCoordinatesRAS[0] ), 2 ) +
                                               math.pow( ( currentPoint[1] - currentCoordinatesRAS[1] ), 2 ) +
                                               math.pow( ( currentPoint[2] - currentCoordinatesRAS[2] ), 2 ) )

            targetPoints.append( currentPoint )
            distancesToSeed.append( currentDistanceToSeed )

        # now we have a list of distances with the corresponding points
        # the index with the most minimal distance is the holePoint, we want to ignore it
        # the index with the second minimal distance is the point closest to the seed, we want to set it as sourcepoint
        # all other points are the targetpoints

        # get the index of the holePoint, which we want to remove from our endPoints
        holePointIndex = distancesToSeed.index( min( distancesToSeed ) )
        # .. and remove it
        distancesToSeed.pop( holePointIndex )
        targetPoints.pop( holePointIndex )

        # now find the sourcepoint
        sourcePointIndex = distancesToSeed.index( min( distancesToSeed ) )
        # .. and remove it after saving it as the sourcePoint
        sourcePoint = targetPoints[sourcePointIndex]
        distancesToSeed.pop( sourcePointIndex )
        targetPoints.pop( sourcePointIndex )

        # again, at this point we have a) the sourcePoint and b) a list of real targetPoints


        # now create the sourceIdList and targetIdList for the actual centerline computation
        sourceIdList = vtk.vtkIdList()
        targetIdList = vtk.vtkIdList()

        pointLocator = vtk.vtkPointLocator()
        pointLocator.SetDataSet( preparedModel )
        pointLocator.BuildLocator()

        # locate the source on the surface
        sourceId = pointLocator.FindClosestPoint( sourcePoint )
        sourceIdList.InsertNextId( sourceId )

        f = slicer.mrmlScene.GetNodeByID(slicer.modules.markups.logic().AddNewFiducialNode("Centerline endpoints"))
        fdn = f.GetDisplayNode()
        fdn.SetTextScale(0)
        f.AddFiducialFromArray(sourcePoint)

        # locate the endpoints on the surface
        for p in targetPoints:

                fid = f.AddFiducialFromArray(p)
                f.SetNthFiducialSelected(fid,False)

                id = pointLocator.FindClosestPoint( p )
                targetIdList.InsertNextId( id )


        tupel = self.GetLogic().computeCenterlines( preparedModel, sourceIdList, targetIdList )
        network.DeepCopy( tupel[0] )
        voronoi.DeepCopy( tupel[1] )

    #
    #
    # update the display of the original model in terms of opacity
    currentModelDisplayNode = currentModelNode.GetDisplayNode()

    if not currentModelDisplayNode:

        # create new displayNode
        currentModelDisplayNode = slicer.mrmlScene.CreateNodeByClass( "vtkMRMLModelDisplayNode" )
        slicer.mrmlScene.AddNode( currentModelDisplayNode )

    currentModelDisplayNode.SetOpacity( 0.4 )
    currentModelDisplayNode.Modified()

    # update the reference between model node and it's display node
    currentModelNode.SetAndObserveDisplayNodeID( currentModelDisplayNode.GetID() )
    currentModelNode.Modified()

    #
    # finally:
    # propagate output model to nodes
    currentOutputModelNode.SetAndObservePolyData( network )
    currentOutputModelNode.Modified()

    currentOutputModelDisplayNode = currentOutputModelNode.GetDisplayNode()

    if not currentOutputModelDisplayNode:

        # create new displayNode
        currentOutputModelDisplayNode = slicer.mrmlScene.CreateNodeByClass( "vtkMRMLModelDisplayNode" )
        slicer.mrmlScene.AddNode( currentOutputModelDisplayNode )

    # always configure the displayNode to show the model
    currentOutputModelDisplayNode.SetColor( 0.0, 0.0, 0.4 )  # red
    currentOutputModelDisplayNode.SetBackfaceCulling( 0 )
    currentOutputModelDisplayNode.SetSliceIntersectionVisibility( 0 )
    currentOutputModelDisplayNode.SetVisibility( 1 )
    currentOutputModelDisplayNode.SetOpacity( 1.0 )
    currentOutputModelDisplayNode.Modified()

    # update the reference between model node and it's display node
    currentOutputModelNode.SetAndObserveDisplayNodeID( currentOutputModelDisplayNode.GetID() )
    currentOutputModelNode.Modified()

    # only update the voronoi node if we are not in preview mode

    if not preview:
        currentVoronoiModelNode.SetAndObservePolyData( voronoi )
        currentVoronoiModelNode.Modified()

        currentVoronoiModelDisplayNode = currentVoronoiModelNode.GetDisplayNode()

        if not currentVoronoiModelDisplayNode:

            # create new displayNode
            currentVoronoiModelDisplayNode = slicer.mrmlScene.CreateNodeByClass( "vtkMRMLModelDisplayNode" )
            slicer.mrmlScene.AddNode( currentVoronoiModelDisplayNode )

        # always configure the displayNode to show the model
        currentVoronoiModelDisplayNode.SetScalarVisibility( 1 )
        currentVoronoiModelDisplayNode.SetBackfaceCulling( 0 )
        currentVoronoiModelDisplayNode.SetActiveScalarName( "Radius" )
        currentVoronoiModelDisplayNode.SetAndObserveColorNodeID( slicer.mrmlScene.GetNodesByName( "Labels" ).GetItemAsObject( 0 ).GetID() )
        currentVoronoiModelDisplayNode.SetSliceIntersectionVisibility( 0 )
        currentVoronoiModelDisplayNode.SetVisibility( 1 )
        currentVoronoiModelDisplayNode.SetOpacity( 0.5 )
        currentVoronoiModelDisplayNode.Modified()

        # update the reference between model node and it's display node
        currentVoronoiModelNode.SetAndObserveDisplayNodeID( currentVoronoiModelDisplayNode.GetID() )
        currentVoronoiModelNode.Modified()



    SlicerVmtkCommonLib.Helper.Debug( "End of Centerline Computation.." )


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

class CenterlineComputationSlicelet( Slicelet ):
  """ Creates the interface when module is run as a stand alone gui app.
  """

  def __init__( self ):
    super( CenterlineComputationSlicelet, self ).__init__( CenterlineComputationWidget )


if __name__ == "__main__":
  # TODO: need a way to access and parse command line arguments
  # TODO: ideally command line args should handle --xml

  import sys
  print( sys.argv )

  slicelet = CenterlineComputationSlicelet()
