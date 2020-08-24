import os
import unittest
import logging
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
import numpy
from slicer.util import VTKObservationMixin

#
# CrossSectionAnalysis
# renamed from
# PathReformat
#

class CrossSectionAnalysis(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Cross-section analysis"  # TODO: make this more human readable by adding spaces
    self.parent.categories = ["Vascular Modeling Toolkit"]  # TODO: set categories (folders where the module shows up in the module selector)
    self.parent.dependencies = []  # TODO: add here list of module names that this module requires
    self.parent.contributors = ["SET (Hobbyist)"]  # TODO: replace with "Firstname Lastname (Organization)"
    # TODO: update with short description of the module and a link to online module documentation
    self.parent.helpText = """
Moves a selected view along a path, and orients the plane at right angle to the path. It is intended to view cross-sections of blood vessels.
See more information in <a href="https://github.com/chir-set/PathReformat">module documentation</a>.
"""
    # TODO: replace with organization, grant and thanks
    self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
"""

#
# CrossSectionAnalysisWidget
#

class CrossSectionAnalysisWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
    # Widget level observations to update module UI. Logic class has its own.
    self.widgetMarkupPointsObservations = []
    # Remove observers on previous path when currrent node has changed
    self.currentPathNode = None

  def setup(self):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer).
    # Additional widgets can be instantiated manually and added to self.layout.
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/CrossSectionAnalysis.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    # Create logic class. Logic implements all computations that should be possible to run
    # in batch mode, without a graphical user interface.
    self.logic = CrossSectionAnalysisLogic()
    
    # Hide diameter labels. Concern only VMTK centerline models.
    self.showDiameterLabels(False)
    
    self.ui.moreCollapsibleButton.collapsed = True
    self.ui.advancedCollapsibleButton.collapsed = True
    self.ui.roiCollapsibleButton.collapsed = True
    self.resetSliderWidget()
    """
    Unfortunately, it does not select a default node in ui.sliceNodeSelector at this step.
    enter() does the job.
    Very bad situation. We must go to another module,
    and back here for sliceNodeSelector to have a valid node.
    sliceNodeSelector is created in designer without noneEnabled though.
    """
    self.initializeSliceNodeSelector()

    # Connections
    
    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
    
    # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
    # (in the selected parameter node).
    self.ui.inputSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.sliceNodeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.positionIndexSliderWidget.connect("valueChanged(double)", self.updateParameterNodeFromGUI)
    
    # Application connections
    self.ui.inputSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelectPathNode)
    self.ui.sliceNodeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.logic.selectSliceNode)
    self.ui.positionIndexSliderWidget.connect("valueChanged(double)", self.logic.process)
    # Feedback on module UI
    self.ui.positionIndexSliderWidget.connect("valueChanged(double)", self.showCurrentPositionData)
    self.ui.hideCheckBox.connect("clicked()", self.onHidePath)
    self.ui.createMarkupsCurvePushButton.connect("clicked()", self.createMarksupCurve)
    self.ui.roiSelector.connect("nodeAddedByUser(vtkMRMLNode*)", self.logic.onCreateROI)
    self.ui.roiSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onCurrentROIChanged)
    self.ui.hideROICheckBox.connect("clicked()", self.onHideROI)
    
  def cleanup(self):
    """
    Called when the application closes and the module widget is destroyed.
    """
    self.removeObservers()
    self.logic.removeMarkupObservers()
    self.removeWidgetMarkupObservers(self.ui.inputSelector.currentNode())
    
  def enter(self):
    """
    Called each time the user opens this module.
    """    
    # The reformat module must always edit the same node.
    self.initializeSliceNodeSelector()
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
    self.ui.inputSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputPath"))
    self.ui.sliceNodeSelector.setCurrentNode(self._parameterNode.GetNodeReference("SliceNode"))
    self.ui.positionIndexSliderWidget.value = float(self._parameterNode.GetParameter("IndexAlongPath"))

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
    
    self._parameterNode.SetNodeReferenceID("InputPath", self.ui.inputSelector.currentNodeID)
    self._parameterNode.SetNodeReferenceID("SliceNode", self.ui.sliceNodeSelector.currentNodeID)
    self._parameterNode.SetParameter("IndexAlongPath", str(self.ui.positionIndexSliderWidget.value))

    self._parameterNode.EndModify(wasModified)
      
  def initializeSliceNodeSelector(self):
    # When Slicer starts, even if noneEnabled is false,
    # no slice node is selected. Force the red node.
    sliceNode = self.ui.sliceNodeSelector.currentNode()
    if sliceNode is None:
        print("none")
        sliceNode = slicer.util.getNode("vtkMRMLSliceNodeRed")
        self.ui.sliceNodeSelector.setCurrentNode(sliceNode)
    # Synchronize slice node in logic and Reformat Module
    self.logic.selectSliceNode(sliceNode)
        
  def onSelectPathNode(self):
    # sliceNodeSelector may be unexpectedly None !! Workaround it.
    self.initializeSliceNodeSelector()
    
    self.removeWidgetMarkupObservers(self.currentPathNode)
    inputPath = self.ui.inputSelector.currentNode()
    self.logic.selectNode(inputPath)
    self.setSliderWidget()
    if inputPath is not None:
        self.ui.hideCheckBox.setChecked(not inputPath.GetDisplayVisibility())
    # Position slice view at first point
    self.ui.positionIndexSliderWidget.setValue(0)
    self.logic.process(0)
    self.showCurrentPositionData(0)
    # Remember this path to remove observers later
    self.addWidgetMarkupObservers()
    self.currentPathNode = inputPath
    # Select in markups module if appropriate
    self.logic.selectCurveInMarkupsModule()
    # Diameters can be shown for VMTK centerline models only
    if inputPath is not None and inputPath.GetClassName() == "vtkMRMLModelNode":
        self.showDiameterLabels(True)
    else:
        self.showDiameterLabels(False)
    
  def onHidePath(self):
    path = self.ui.inputSelector.currentNode()
    if path is None:
        return
    path.SetDisplayVisibility(not self.ui.hideCheckBox.checked)
    
  def resetSliderWidget(self):
    sliderWidget = self.ui.positionIndexSliderWidget
    sliderWidget.setDisabled(True)
    sliderWidget.minimum = 0
    sliderWidget.maximum = 0
    sliderWidget.setValue(0)
    sliderWidget.singleStep = 1
    sliderWidget.decimals = 0
    
  def setSliderWidget(self):
    inputPath = self.ui.inputSelector.currentNode()
    sliderWidget = self.ui.positionIndexSliderWidget
    if inputPath is None:
        self.resetSliderWidget()
        return
    sliderWidget.setDisabled(False)
    sliderWidget.minimum = 0
    sliderWidget.maximum = 0
    # if control points are deleted one by one
    if self.logic.pathArray.size > 1:
        sliderWidget.maximum = (self.logic.pathArray.size / 3) - 1 - 1
    
  # logic.onWidgetMarkupPointAdded gets called first
  def onWidgetMarkupPointAdded(self, caller, event):
    self.setSliderWidget()
    self.ui.positionIndexSliderWidget.setValue(0)
    self.showCurrentPositionData(0)

  def onWidgetMarkupPointRemoved(self, caller, event):
    self.setSliderWidget()
    self.ui.positionIndexSliderWidget.setValue(0)
    self.showCurrentPositionData(0)
  
  # Position on path is not reset here
  def onWidgetMarkupPointEndInteraction(self, caller, event):
    self.showCurrentPositionData(self.logic.lastValue)

  def addWidgetMarkupObservers(self):
      inputPath = self.ui.inputSelector.currentNode()
      if inputPath is not None and inputPath.GetClassName() == "vtkMRMLMarkupsCurveNode":
        widgetMarkupPointObservation = inputPath.AddObserver(slicer.vtkMRMLMarkupsNode.PointEndInteractionEvent, self.onWidgetMarkupPointEndInteraction)
        widgetMarkupPointAddedObservation = inputPath.AddObserver(slicer.vtkMRMLMarkupsNode.PointAddedEvent, self.onWidgetMarkupPointAdded)
        widgetMarkupPointRemovedObservation = inputPath.AddObserver(slicer.vtkMRMLMarkupsNode.PointRemovedEvent, self.onWidgetMarkupPointRemoved)
        self.widgetMarkupPointsObservations = [widgetMarkupPointObservation, widgetMarkupPointAddedObservation, widgetMarkupPointRemovedObservation]
        
  def removeWidgetMarkupObservers(self, inputPath):
    if inputPath is not None:
        for observation in self.widgetMarkupPointsObservations:
            inputPath.RemoveObserver(observation)
        
  def showCurrentPositionData(self, value):
    # Get coordinates on path
    currentPoint = self.logic.currentPosition(value);
    if currentPoint.size == 0:
        self.ui.locationLabel.setText("")
        self.ui.distanceLabel.setText("")
        self.ui.lengthLabel.setText("")
        self.ui.orientationLabel.setText("")
        return
    position = "R " + str(round(currentPoint[0], 1)) + ", " + "A " + str(round(currentPoint[1], 1)) + ", " + "S " + str(round(currentPoint[2], 1))
    self.ui.locationLabel.setText(position)
    # Get path length
    sizeOfArray = int(self.logic.cumDistancesArray.size)
    length = str(round(self.logic.cumDistancesArray[sizeOfArray - 1], 1))
    self.ui.lengthLabel.setText(length + " mm")
    # Distance from start
    distance = str(round(self.logic.cumDistancesArray[int(value)], 1))
    self.ui.distanceLabel.setText(distance + " mm")
    # VMTK centerline radius
    inputPath = self.ui.inputSelector.currentNode()
    if inputPath is not None and inputPath.GetClassName() == "vtkMRMLModelNode" and self.logic.vmtkCenterlineRadii.size > 0:
        diameter = str(round(self.logic.vmtkCenterlineRadii[int(value)] * 2, 1))
        self.ui.diameterLabel.setText(diameter + " mm")
    # Orientation
    orient = self.logic.getSliceOrientation()
    orientation = "R " + str(round(orient[0], 1)) + "°,"
    orientation += " A " + str(round(orient[1], 1)) + "°,"
    orientation += " S " + str(round(orient[2], 1)) + "°"
    self.ui.orientationLabel.setText(orientation)

  # True : for VMTK centerline models only
  def showDiameterLabels(self, show):
    self.ui.diameterLabelIndicator.setVisible(show)
    self.ui.diameterLabel.setVisible(show)

  # Created with the default name
  def createMarksupCurve(self):
    self.ui.inputSelector.setCurrentNode(None)
    self.logic.createMarksupCurve();
  
  def onCurrentROIChanged(self):
    currentROI = self.ui.roiSelector.currentNode()
    if currentROI is None:
        self.ui.hideROICheckBox.setChecked(False)
        return
    self.ui.hideROICheckBox.setChecked(not currentROI.GetDisplayVisibility())
    
  def onHideROI(self):
    roi = self.ui.roiSelector.currentNode()
    if roi is None:
        return
    roi.SetDisplayVisibility(not self.ui.hideROICheckBox.checked)
#
# CrossSectionAnalysisLogic
#

class CrossSectionAnalysisLogic(ScriptedLoadableModuleLogic):
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
    self.inputPath = None
    self.inputSliceNode = None
    self.reformatLogic = slicer.modules.reformat.logic()
    self.pathArray = numpy.zeros(0)
    # Use independent observers to reprocess the slice when a markup curve is modified
    self.markupPointObservations = []
    # on markup change, reprocess last point
    self.lastValue = 0
    self.cumDistancesArray = numpy.zeros(0)
    self.vmtkCenterlineRadii = numpy.zeros(0)
    # self.backgroundVolumeNode = slicer.app.layoutManager().sliceWidget(self.inputSliceNode.GetName()).sliceLogic().GetBackgroundLayer().GetVolumeNode()
  
  def setDefaultParameters(self, parameterNode):
    """
    Initialize parameter node with default settings.
    """
    if not parameterNode.GetParameter("IndexAlongPath"):
      parameterNode.SetParameter("IndexAlongPath", "0.0")
    
  def resetSliceNodeOrientationToDefault(self):
    if self.inputPath is None or self.inputSliceNode is None:
        return
    self.inputSliceNode.SetOrientationToDefault()

  # Get the path's array of points
  def fillPathArray(self):
    if self.inputPath is None or self.inputSliceNode is None:
        self.pathArray = numpy.zeros(0)
        self.cumDistancesArray = numpy.zeros(0)
        self.vmtkCenterlineRadii = numpy.zeros(0)
        return
    if self.inputPath.GetClassName() == "vtkMRMLMarkupsCurveNode" or self.inputPath.GetClassName() == "vtkMRMLMarkupsClosedCurveNode":
        self.vmtkCenterlineRadii = numpy.zeros(0)
        # All control points have been deleted except one
        if self.inputPath.GetNumberOfControlPoints() < 2:
            self.pathArray = numpy.zeros(0)
            self.cumDistancesArray = numpy.zeros(0)
            return
        self.pathArray = slicer.util.arrayFromMarkupsCurvePoints(self.inputPath)
    # For VMTK centerline models, get the array of radii
    if self.inputPath.GetClassName() == "vtkMRMLModelNode":
        self.pathArray = slicer.util.arrayFromModelPoints(self.inputPath)
        self.vmtkCenterlineRadii = slicer.util.arrayFromModelPointData(self.inputPath, 'Radius')
    # Compute the distances for each point once
    self.cumulateDistances()

  # Move the reformated slice along path, and point it to the next point
  def process(self, value):
    if self.inputSliceNode is None or self.inputPath is None or (self.pathArray.size == 0):
        return
    point = self.pathArray[int(value)]
    direction = self.pathArray[int(value) + 1] - point
    self.reformatLogic.SetSliceOrigin(self.inputSliceNode, point[0], point[1], point[2])
    self.reformatLogic.SetSliceNormal(self.inputSliceNode, direction[0], direction[1], direction[2])
    self.lastValue = value

  def selectNode(self, inputPath):
    # Observe the selected markup path only. Remove from previous.
    self.removeMarkupObservers()
    self.inputPath = inputPath
    self.resetSliceNodeOrientationToDefault()
    self.fillPathArray()
    self.addMarkupObservers()
    
  def selectSliceNode(self, sliceNode):
    self.inputSliceNode = sliceNode
    slicer.modules.reformat.widgetRepresentation().setEditedNode(sliceNode)
    
  def addMarkupObservers(self):
    # Observe markup curve. VMTK centerlines don't seem to have UI handles.
    if self.inputPath is not None and self.inputPath.GetClassName() == "vtkMRMLMarkupsCurveNode":
        markupPointObservation = self.inputPath.AddObserver(slicer.vtkMRMLMarkupsNode.PointEndInteractionEvent, self.onMarkupPointEndInteraction)
        markupPointRemovedObservation = self.inputPath.AddObserver(slicer.vtkMRMLMarkupsNode.PointRemovedEvent, self.onMarkupPointRemoved)
        markupPointAddedObservation = self.inputPath.AddObserver(slicer.vtkMRMLMarkupsNode.PointAddedEvent, self.onMarkupPointAdded)
        self.markupPointObservations = [markupPointObservation, markupPointRemovedObservation, markupPointAddedObservation]
        
  def removeMarkupObservers(self):
    if self.inputPath is not None:
        for observation in self.markupPointObservations:
            self.inputPath.RemoveObserver(observation)
        
  # Reposition the slice if a markup control point is moved
  def onMarkupPointEndInteraction(self, caller, event):
    self.fillPathArray()
    self.process(self.lastValue)
    
  # Reposition the slice to start if a markup control point is removed
  def onMarkupPointRemoved(self, caller, event):
    self.fillPathArray()
    self.process(0)

  # Reposition the slice to start if a markup control point is added
  def onMarkupPointAdded(self, caller, event):
    self.fillPathArray()
    self.process(0)
    
  # Get RAS current position on path
  def currentPosition(self, value):
    if self.pathArray.size == 0:
        return numpy.zeros(0)
    return self.pathArray[int(value)]
  
  # Calculate distance of each point from start of path
  def cumulateDistances(self):
    self.cumDistancesArray = numpy.zeros(int(self.pathArray.size / 3))
    previous = self.pathArray[0]
    dist = 0
    for i, point in enumerate(self.pathArray):
      # https://stackoverflow.com/questions/1401712/how-can-the-euclidean-distance-be-calculated-with-numpy
      dist += numpy.linalg.norm(point - previous)
      self.cumDistancesArray[i] = dist
      previous = point

  # This information is added because it is easily available.
  # How useful is it ?
  # In any case, it is the slice orientation in the RAS coordinate system.
  def getSliceOrientation(self):
    sliceToRAS = self.inputSliceNode.GetSliceToRAS()
    orient = numpy.zeros(3)
    vtk.vtkTransform().GetOrientation(orient, sliceToRAS)
    return orient

  # Center the ROI on the path, and resize it to the path's bounds.
  # The ROI name follows the path's name.
  def onCreateROI(self, roiNode):
    if self.inputPath is None:
        slicer.mrmlScene.RemoveNode(roiNode)
        return;
    bounds = numpy.zeros(6)
    self.inputPath.GetRASBounds(bounds)
    box = vtk.vtkBoundingBox(bounds)
    center = [0.0, 0.0, 0.0]
    box.GetCenter(center)
    roiNode.SetName("ROI " + self.inputPath.GetName())
    roiNode.SetXYZ(center)
    roiNode.SetRadiusXYZ(box.GetLength(0) / 2, box.GetLength(1) / 2, box.GetLength(2) / 2)
    
  # But other modules can do that on their own.
  def createMarksupCurve(self):
    slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsCurveNode")
    
  # Select the path there for future point addition on that path
  def selectCurveInMarkupsModule(self):
    markupsWidget = slicer.modules.markups.widgetRepresentation()
    if self.inputPath is None:
        # The markups module keeps selecting the last node ! Future points will be added to that curve.
        markupsWidget.setEditedNode(None)
        return
    if self.inputPath.GetClassName() != "vtkMRMLModelNode":
        markupsWidget.setEditedNode(self.inputPath)
    else:
        markupsWidget.setEditedNode(None)

#
# CrossSectionAnalysisTest
#

class CrossSectionAnalysisTest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setUp(self):
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    slicer.mrmlScene.Clear()
