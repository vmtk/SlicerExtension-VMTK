import os
import unittest
import logging
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

#
# StenosisMeasurement1D
#

class StenosisMeasurement1D(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Stenosis measurement : 1D"
    self.parent.categories = ["Vascular Modeling Toolkit"]
    self.parent.dependencies = []
    self.parent.contributors = ["Saleem Edah-Tally [Surgeon] [Hobbyist developer]", "Andras Lasso, PerkLab"]
    self.parent.helpText = """
This <a href="https://github.com/vmtk/SlicerExtension-VMTK/">module</a> straightens an open input markups curve and displays cumulative and individual lengths between control points. It is intended for quick one dimensional arterial stenosis evaluation, but is actually purpose agnostic.
"""
    # TODO: replace with organization, grant and thanks
    self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
"""

#
# StenosisMeasurement1DWidget
#

class StenosisMeasurement1DWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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

  def setup(self):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer).
    # Additional widgets can be instantiated manually and added to self.layout.
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/StenosisMeasurement1D.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    # Create logic class. Logic implements all computations that should be possible to run
    # in batch mode, without a graphical user interface.
    self.logic = StenosisMeasurement1DLogic()

    # Connections

    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
    
    # Make sure parameter node is initialized (needed for module reload)
    self.initializeParameterNode()

    # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
    # (in the selected parameter node).
    self.ui.inputMarkupsSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    
    # Application connections
    self.ui.inputMarkupsSelector.connect("currentNodeChanged(vtkMRMLNode*)", lambda node: self.setInputCurve(node))
    
    # Update logic from parameter node
    self.logic.setInputCurve(self._parameterNode.GetNodeReference("InputCurve"))
    
    # Fill the table through a callback from logic.
    self.logic.widgetCallback = self.populateTable

  def cleanup(self):
    """
    Called when the application closes and the module widget is destroyed.
    """
    self.removeObservers()

  def enter(self):
    """
    Called each time the user opens this module.
    """
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
    self.logic.InitMemberVariables()

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
    self.ui.inputMarkupsSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputCurve"))

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

    self._parameterNode.SetNodeReferenceID("InputCurve", self.ui.inputMarkupsSelector.currentNodeID)

    self._parameterNode.EndModify(wasModified)

  def setInputCurve(self, curveNode):
    self.logic.setInputCurve(curveNode)
    self.populateTable()
    self.logic.widgetCallback = self.populateTable

  def populateTable(self):
    inputCurve = self.ui.inputMarkupsSelector.currentNode()
    outputTable = self.ui.outputTableWidget
    # Clean table completely.
    outputTable.clear()
    outputTable.setRowCount(0)
    outputTable.setColumnCount(0)
    if not inputCurve:
        return
    numberOfControlPoints = inputCurve.GetNumberOfControlPoints()
    # Setup table.
    if outputTable.columnCount == 0:
        outputTable.setColumnCount(4)
        outputTable.setRowCount(numberOfControlPoints - 1)
        columnLabels = ("Cumulative", "Cumulative %", "Partial", "Partial %")
        outputTable.setHorizontalHeaderLabels(columnLabels)
    # Get global variables.
    curveTotalLength = inputCurve.GetCurveLengthWorld()
    curveControlPoints = vtk.vtkPoints()
    inputCurve.GetControlPointPositionsWorld(curveControlPoints)
    partDistance = 0.0
    measurementLength = inputCurve.GetMeasurement("length")
    measurementLengthUnit = measurementLength.GetUnits()
    """
    Iterate over control points.
    Start at index 1, we measure backwards.
    """
    for pointIndex in range(1, numberOfControlPoints):
        curvePoint = curveControlPoints.GetPoint(pointIndex)
        controlPointIndex = inputCurve.GetClosestCurvePointIndexToPositionWorld(curvePoint)
        # Distance of control point from start.
        cumulativeDistance = inputCurve.GetCurveLengthBetweenStartEndPointsWorld(
            0, controlPointIndex)

        item = qt.QTableWidgetItem()
        content = f"{cumulativeDistance:.1f} {measurementLengthUnit}"
        item.setText(content)
        outputTable.setItem(pointIndex - 1, 0, item)
        # Proportional cumulative distance, with respect to total length.
        item = qt.QTableWidgetItem()
        content = f"{(cumulativeDistance / curveTotalLength) * 100:.1f} %"
        item.setText(content)
        outputTable.setItem(pointIndex - 1, 1, item)
        
        # Distance between two adjacent points.
        previousCurvePoint = curveControlPoints.GetPoint(pointIndex - 1)
        previousControlPointIndex = inputCurve.GetClosestCurvePointIndexToPositionWorld(previousCurvePoint)
        partDistance = inputCurve.GetCurveLengthBetweenStartEndPointsWorld(
            previousControlPointIndex, controlPointIndex)
        
        item = qt.QTableWidgetItem()
        content = f"{partDistance:.1f} {measurementLengthUnit}"
        item.setText(content)
        outputTable.setItem(pointIndex - 1, 2, item)
        # Proportional distance between two adjacent points, with respect to total length.
        item = qt.QTableWidgetItem()
        content = f"{(partDistance / curveTotalLength) * 100:.1f} %"
        item.setText(content)
        outputTable.setItem(pointIndex - 1, 3, item)

#
# StenosisMeasurement1DLogic
#

class StenosisMeasurement1DLogic(ScriptedLoadableModuleLogic):

  def __init__(self):
    """
    Called when the logic class is instantiated. Can be used for initializing member variables.
    """
    ScriptedLoadableModuleLogic.__init__(self)
    self.InitMemberVariables()
    
  def InitMemberVariables(self):
    self.inputCurve = None
    self.observations = []
    self.widgetCallback = None
    
  def setDefaultParameters(self, parameterNode):
    """
    Initialize parameter node with default settings.
    """
    pass

  def setInputCurve(self, curveNode):
    # Remove all observations on current curve
    if self.inputCurve:
        for observation in self.observations:
            self.inputCurve.RemoveObserver(observation)
    self.observations.clear()
    
    self.inputCurve = curveNode
    # React when points are moved, removed or added.
    if self.inputCurve:
        self.observations.append(self.inputCurve.AddObserver(slicer.vtkMRMLMarkupsNode.PointEndInteractionEvent, self.onCurveControlPointEvent))
        # Don't use PointAddedEvent. It is fired on mouse move in views.
        self.observations.append(self.inputCurve.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self.onCurveControlPointEvent))
        self.observations.append(self.inputCurve.AddObserver(slicer.vtkMRMLMarkupsNode.PointRemovedEvent, self.onCurveControlPointEvent))
        self.process()
    else:
        msg = "No curve."
        slicer.util.showStatusMessage(msg, 4000)
        slicer.app.processEvents()
        logging.info(msg)
        # Signal widget to clear the table.
        if self.widgetCallback:
            self.widgetCallback()

  def onCurveControlPointEvent(self, caller, event):
    self.process()

  def process(self):
    if not self.inputCurve:
      msg = "No curve."
      slicer.util.showStatusMessage(msg, 4000)
      slicer.app.processEvents()
      logging.info(msg)
      return
    # Don't do anything if there are 2 points only, already a line.
    if (self.inputCurve.GetNumberOfControlPoints() == 2):
        # Just signal widget to fill the table with results.
        if self.widgetCallback:
            self.widgetCallback()
        return

    # Generate a linear polydata from first and last control point.
    numberOfControlPoints = self.inputCurve.GetNumberOfControlPoints()
    lineSource = vtk.vtkLineSource()
    curveControlPoints = vtk.vtkPoints()
    self.inputCurve.GetControlPointPositionsWorld(curveControlPoints)
    firstControlPointPosition = curveControlPoints.GetPoint(0)
    lastControlPointPosition = curveControlPoints.GetPoint(numberOfControlPoints - 1)
    lineSource.SetPoint1(firstControlPointPosition)
    lineSource.SetPoint2(lastControlPointPosition)
    lineSource.Update()
    linePolyData = lineSource.GetOutput()
    
    # The polydata contains 2 points. Generate more points.
    polydataSampler = vtk.vtkPolyDataPointSampler()
    polydataSampler.SetInputData(linePolyData)
    polydataSampler.Update()
    # This is the reference line polydata.
    straightLinePolyData = polydataSampler.GetOutput()
    
    startPoint = curveControlPoints.GetPoint(0)
    cumulativeDistanceArray = [[0.0, startPoint]]
    # Iterate over all curve points, ignoring first and last.
    for pointIndex in range(1, numberOfControlPoints - 1):
        point = curveControlPoints.GetPoint(pointIndex)
        closestIdOnStraightLine = straightLinePolyData.FindPoint(point)
        closestPointOnStraightLine = straightLinePolyData.GetPoint(closestIdOnStraightLine)
        cumulativeDistanceOfClosestPoint = vtk.vtkMath.Distance2BetweenPoints(
            startPoint, closestPointOnStraightLine)
        cumulativeDistanceArray.append([cumulativeDistanceOfClosestPoint,
                                        closestPointOnStraightLine])

    """
    Move each control point to the closest point on the virtual line.
    If we have n control points ABCD..., C can be pushed
    between A and B on the virtual line. The curve is still valid, though
    the points are in zig-zag order. Distances will be less or not meaningful.
    Sort the points by distance from start to avoid this.
    """
    sortedCumulativeDistanceArray = sorted(cumulativeDistanceArray,
                                           key=lambda distance: distance[0])
    for pointIndex in range(1, numberOfControlPoints - 1):
        self.inputCurve.SetNthControlPointPosition(pointIndex,
                                                   sortedCumulativeDistanceArray[pointIndex][1])
    
    # Signal widget to fill the table with results.
    if self.widgetCallback:
        self.widgetCallback()

#
# StenosisMeasurement1DTest
#

class StenosisMeasurement1DTest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setUp(self):
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    slicer.mrmlScene.Clear()

  def runTest(self):
    """Run as few or as many tests as needed here.
    """
    self.setUp()
    self.test_StenosisMeasurement1D1()

  def test_StenosisMeasurement1D1(self):
    """ Ideally you should have several levels of tests.  At the lowest level
    tests should exercise the functionality of the logic with different inputs
    (both valid and invalid).  At higher levels your tests should emulate the
    way the user would interact with your code and confirm that it still works
    the way you intended.
    One of the most important features of the tests is that it should alert other
    developers when their changes will have an impact on the behavior of your
    module.  For example, if a developer removes a feature that you depend on,
    your test should break so they know that the feature is needed.
    """

    self.delayDisplay("Starting the test")

    self.delayDisplay('Test passed')
