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
    self.parent.contributors = ["Daniel Haehn (Boston Children's Hospital)", "Luca Antiga (Orobix)", "Steve Pieper (Isomics)", "Andras Lasso (PerkLab)"]
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

    # the pointer to the logic
    self.__logic = SlicerVmtkCommonLib.CenterlineComputationLogic()

    if not parent:
      # after setup, be ready for events
      self.parent.show()
    else:
      # register default slots
      self.parent.connect( 'mrmlSceneChanged(vtkMRMLScene*)', self.onMRMLSceneChanged )

  def setup( self ):
    ScriptedLoadableModuleWidget.setup(self)

    # check if the SlicerVmtk module is installed properly
    # self.__vmtkInstalled = SlicerVmtkCommonLib.Helper.CheckIfVmtkIsInstalled()
    # Helper.Debug("VMTK found: " + self.__vmtkInstalled)

    #
    # Inputs
    #

    inputsCollapsibleButton = ctk.ctkCollapsibleButton()
    inputsCollapsibleButton.text = "Inputs"
    self.layout.addWidget( inputsCollapsibleButton )
    inputsFormLayout = qt.QFormLayout( inputsCollapsibleButton )

    # inputVolume selector
    self.__inputModelNodeSelector = slicer.qMRMLNodeComboBox()
    self.__inputModelNodeSelector.objectName = 'inputModelNodeSelector'
    self.__inputModelNodeSelector.toolTip = "Select the input model."
    self.__inputModelNodeSelector.nodeTypes = ['vtkMRMLModelNode']
    self.__inputModelNodeSelector.hideChildNodeTypes = ['vtkMRMLAnnotationNode']  # hide all annotation nodes
    self.__inputModelNodeSelector.noneEnabled = False
    self.__inputModelNodeSelector.addEnabled = False
    self.__inputModelNodeSelector.removeEnabled = False
    inputsFormLayout.addRow( "Vessel tree model:", self.__inputModelNodeSelector )
    self.parent.connect( 'mrmlSceneChanged(vtkMRMLScene*)',
                        self.__inputModelNodeSelector, 'setMRMLScene(vtkMRMLScene*)' )

    # seed selector
    self.__seedFiducialsNodeSelector = slicer.qSlicerSimpleMarkupsWidget()
    self.__seedFiducialsNodeSelector.objectName = 'seedFiducialsNodeSelector'
    self.__seedFiducialsNodeSelector = slicer.qSlicerSimpleMarkupsWidget()
    self.__seedFiducialsNodeSelector.objectName = 'seedFiducialsNodeSelector'
    self.__seedFiducialsNodeSelector.toolTip = "Select a fiducial to use as the origin of the Centerline."
    self.__seedFiducialsNodeSelector.setNodeBaseName("OriginSeed")
    self.__seedFiducialsNodeSelector.defaultNodeColor = qt.QColor(0,255,0)
    self.__seedFiducialsNodeSelector.tableWidget().hide()
    self.__seedFiducialsNodeSelector.markupsSelectorComboBox().noneEnabled = False
    self.__seedFiducialsNodeSelector.markupsPlaceWidget().placeMultipleMarkups = slicer.qSlicerMarkupsPlaceWidget.ForcePlaceSingleMarkup
    inputsFormLayout.addRow( "Start point:", self.__seedFiducialsNodeSelector )
    self.parent.connect( 'mrmlSceneChanged(vtkMRMLScene*)',
                        self.__seedFiducialsNodeSelector, 'setMRMLScene(vtkMRMLScene*)' )

    #
    # Outputs
    #

    outputsCollapsibleButton = ctk.ctkCollapsibleButton()
    outputsCollapsibleButton.text = "Outputs"
    self.layout.addWidget( outputsCollapsibleButton )
    outputsFormLayout = qt.QFormLayout( outputsCollapsibleButton )
                        
    # outputModel selector
    self.__outputModelNodeSelector = slicer.qMRMLNodeComboBox()
    self.__outputModelNodeSelector.objectName = 'outputModelNodeSelector'
    self.__outputModelNodeSelector.toolTip = "Select the output model for the Centerlines."
    self.__outputModelNodeSelector.nodeTypes = ['vtkMRMLModelNode']
    self.__outputModelNodeSelector.baseName = "CenterlineComputationModel"
    self.__outputModelNodeSelector.hideChildNodeTypes = ['vtkMRMLAnnotationNode']  # hide all annotation nodes
    self.__outputModelNodeSelector.noneEnabled = True
    self.__outputModelNodeSelector.noneDisplay = "Create new model"
    self.__outputModelNodeSelector.addEnabled = True
    self.__outputModelNodeSelector.selectNodeUponCreation = True
    self.__outputModelNodeSelector.removeEnabled = True
    outputsFormLayout.addRow( "Centerline model:", self.__outputModelNodeSelector )
    self.parent.connect( 'mrmlSceneChanged(vtkMRMLScene*)',
                        self.__outputModelNodeSelector, 'setMRMLScene(vtkMRMLScene*)' )

    self.__outputEndPointsNodeSelector = slicer.qMRMLNodeComboBox()
    self.__outputEndPointsNodeSelector.objectName = 'outputEndPointsNodeSelector'
    self.__outputEndPointsNodeSelector.toolTip = "Select the output model for the Centerlines."
    self.__outputEndPointsNodeSelector.nodeTypes = ['vtkMRMLMarkupsFiducialNode']
    self.__outputEndPointsNodeSelector.baseName = "Centerline endpoints"
    self.__outputEndPointsNodeSelector.noneEnabled = True
    self.__outputEndPointsNodeSelector.noneDisplay = "Create new markups fiducial"
    self.__outputEndPointsNodeSelector.addEnabled = True
    self.__outputEndPointsNodeSelector.selectNodeUponCreation = True
    self.__outputEndPointsNodeSelector.removeEnabled = True
    outputsFormLayout.addRow( "Centerline endpoints:", self.__outputEndPointsNodeSelector )
    self.parent.connect( 'mrmlSceneChanged(vtkMRMLScene*)',
                        self.__outputEndPointsNodeSelector, 'setMRMLScene(vtkMRMLScene*)' )
                        
    # voronoiModel selector
    self.__voronoiModelNodeSelector = slicer.qMRMLNodeComboBox()
    self.__voronoiModelNodeSelector.objectName = 'voronoiModelNodeSelector'
    self.__voronoiModelNodeSelector.toolTip = "Select the output model for the Voronoi Diagram."
    self.__voronoiModelNodeSelector.nodeTypes = ['vtkMRMLModelNode']
    self.__voronoiModelNodeSelector.baseName = "VoronoiModel"
    self.__voronoiModelNodeSelector.hideChildNodeTypes = ['vtkMRMLAnnotationNode']  # hide all annotation nodes
    self.__voronoiModelNodeSelector.noneEnabled = True
    self.__voronoiModelNodeSelector.addEnabled = True
    self.__voronoiModelNodeSelector.selectNodeUponCreation = True
    self.__voronoiModelNodeSelector.removeEnabled = True
    outputsFormLayout.addRow( "Voronoi Model:", self.__voronoiModelNodeSelector )
    self.parent.connect( 'mrmlSceneChanged(vtkMRMLScene*)',
                        self.__voronoiModelNodeSelector, 'setMRMLScene(vtkMRMLScene*)' )

    #
    # Reset, preview and apply buttons
    #

    self.__buttonBox = qt.QDialogButtonBox()
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
    self.__previewButton.connect( "clicked()", self.onPreviewButtonClicked )
    self.__startButton.connect( "clicked()", self.onStartButtonClicked )

    self.__inputModelNodeSelector.setMRMLScene( slicer.mrmlScene )
    self.__seedFiducialsNodeSelector.setMRMLScene( slicer.mrmlScene )
    self.__outputModelNodeSelector.setMRMLScene( slicer.mrmlScene )
    self.__outputEndPointsNodeSelector.setMRMLScene( slicer.mrmlScene )
    self.__voronoiModelNodeSelector.setMRMLScene( slicer.mrmlScene )

    # compress the layout
    self.layout.addStretch( 1 )

  def onMRMLSceneChanged( self ):
    logging.debug( "onMRMLSceneChanged" )

  def onStartButtonClicked( self ):
    qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)
    # this is no preview
    self.start( False )
    qt.QApplication.restoreOverrideCursor()

  def onPreviewButtonClicked( self ):
      # calculate the preview
      self.start( True )
      # activate startButton
      self.__startButton.enabled = True

  def start( self, preview=False ):
    logging.debug( "Starting Centerline Computation.." )

    # first we need the nodes
    currentModelNode = self.__inputModelNodeSelector.currentNode()
    currentSeedsNode = self.__seedFiducialsNodeSelector.currentNode()
    currentOutputModelNode = self.__outputModelNodeSelector.currentNode()
    currentEndPointsMarkupsNode = self.__outputEndPointsNodeSelector.currentNode()
    currentVoronoiModelNode = self.__voronoiModelNodeSelector.currentNode()

    if not currentModelNode:
      # we need a input volume node
      logging.error("Input model node required")
      return False

    if not currentSeedsNode:
      # we need a seeds node
      logging.error("Input seeds node required")
      return False

    if not currentOutputModelNode or currentOutputModelNode.GetID() == currentModelNode.GetID():
      # we need a current model node, the display node is created later
      newModelNode = slicer.mrmlScene.CreateNodeByClass( "vtkMRMLModelNode" )
      newModelNode.UnRegister(None)
      newModelNode.SetName( slicer.mrmlScene.GetUniqueNameByString( self.__outputModelNodeSelector.baseName ) )
      currentOutputModelNode = slicer.mrmlScene.AddNode( newModelNode )
      currentOutputModelNode.CreateDefaultDisplayNodes()
      self.__outputModelNodeSelector.setCurrentNode( currentOutputModelNode )

    if not currentEndPointsMarkupsNode or currentEndPointsMarkupsNode.GetID() == currentSeedsNode.GetID():
      # we need a current seed node, the display node is created later
      currentEndPointsMarkupsNode = slicer.mrmlScene.GetNodeByID(slicer.modules.markups.logic().AddNewFiducialNode("Centerline endpoints"))
      self.__outputEndPointsNodeSelector.setCurrentNode( currentEndPointsMarkupsNode )

    # the output models
    preparedModel = vtk.vtkPolyData()
    model = vtk.vtkPolyData()
    network = vtk.vtkPolyData()
    voronoi = vtk.vtkPolyData()

    currentCoordinatesRAS = [0, 0, 0]

    # grab the current coordinates
    currentSeedsNode.GetNthFiducialPosition(0,currentCoordinatesRAS)

    # prepare the model
    preparedModel.DeepCopy( self.__logic.prepareModel( currentModelNode.GetPolyData() ) )

    # decimate the model (only for network extraction)
    model.DeepCopy( self.__logic.decimateSurface( preparedModel ) )

    # open the model at the seed (only for network extraction)
    model.DeepCopy( self.__logic.openSurfaceAtPoint( model, currentCoordinatesRAS ) )

    # extract Network
    network.DeepCopy( self.__logic.extractNetwork( model ) )

    #
    #
    # not preview mode: real computation!
    if not preview:
      # here we start the actual centerline computation which is mathematically more robust and accurate but takes longer than the network extraction

      # clip surface at endpoints identified by the network extraction
      tupel = self.__logic.clipSurfaceAtEndPoints( network, currentModelNode.GetPolyData() )
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

      currentEndPointsMarkupsNode.GetDisplayNode().SetTextScale(0)
      currentEndPointsMarkupsNode.RemoveAllMarkups()
      
      currentEndPointsMarkupsNode.AddFiducialFromArray(sourcePoint)

      # locate the endpoints on the surface
      for p in targetPoints:
        fid = currentEndPointsMarkupsNode.AddFiducialFromArray(p)
        currentEndPointsMarkupsNode.SetNthFiducialSelected(fid,False)
        id = pointLocator.FindClosestPoint( p )
        targetIdList.InsertNextId( id )

      tupel = self.__logic.computeCenterlines( preparedModel, sourceIdList, targetIdList )
      network.DeepCopy( tupel[0] )
      voronoi.DeepCopy( tupel[1] )

    currentOutputModelNode.SetAndObservePolyData( network )

        
    # Make model node semi-transparent to make centerline inside visible
    currentModelNode.CreateDefaultDisplayNodes()
    currentModelDisplayNode = currentModelNode.GetDisplayNode()
    currentModelDisplayNode.SetOpacity( 0.4 )

    if currentVoronoiModelNode:
      # Configure the displayNode to show the centerline and Voronoi model
      currentOutputModelNode.CreateDefaultDisplayNodes()
      currentOutputModelDisplayNode = currentOutputModelNode.GetDisplayNode()
      currentOutputModelDisplayNode.SetColor( 0.0, 0.0, 0.4 )  # red
      currentOutputModelDisplayNode.SetBackfaceCulling( 0 )
      currentOutputModelDisplayNode.SetSliceIntersectionVisibility( 0 )
      currentOutputModelDisplayNode.SetVisibility( 1 )
      currentOutputModelDisplayNode.SetOpacity( 1.0 )

    # only update the voronoi node if we are not in preview mode

    if currentVoronoiModelNode and not preview:
      currentVoronoiModelNode.SetAndObservePolyData( voronoi )
      currentVoronoiModelNode.CreateDefaultDisplayNodes()
      currentVoronoiModelDisplayNode = currentVoronoiModelNode.GetDisplayNode()

      # always configure the displayNode to show the model
      currentVoronoiModelDisplayNode.SetScalarVisibility( 1 )
      currentVoronoiModelDisplayNode.SetBackfaceCulling( 0 )
      currentVoronoiModelDisplayNode.SetActiveScalarName( "Radius" )
      currentVoronoiModelDisplayNode.SetAndObserveColorNodeID( slicer.mrmlScene.GetNodesByName( "Labels" ).GetItemAsObject( 0 ).GetID() )
      currentVoronoiModelDisplayNode.SetSliceIntersectionVisibility( 0 )
      currentVoronoiModelDisplayNode.SetVisibility( 1 )
      currentVoronoiModelDisplayNode.SetOpacity( 0.5 )

    logging.debug( "End of Centerline Computation.." )

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
