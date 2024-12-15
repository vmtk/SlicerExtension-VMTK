import logging
import os
from typing import Annotated, Optional

import vtk, qt

import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from slicer.parameterNodeWrapper import (
    parameterNodeWrapper,
    WithinRange,
)

from slicer import vtkMRMLScalarVolumeNode

#
# StenosisMeasurement1D
#

class StenosisMeasurement1D(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Stenosis measurement: 1D"
    self.parent.categories = ["Vascular Modeling Toolkit"]
    self.parent.dependencies = []
    self.parent.contributors = ["Saleem Edah-Tally [Surgeon] [Hobbyist developer]", "Andras Lasso, PerkLab"]
    self.parent.helpText = _("""
This <a href="https://github.com/vmtk/SlicerExtension-VMTK/">module</a> straightens an open input markups curve and displays cumulative and individual lengths between control points. It is intended for quick one dimensional arterial stenosis evaluation, but is actually purpose agnostic.
""")
    # TODO: replace with organization, grant and thanks
    self.parent.acknowledgementText = _("""
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
""")

#
# StenosisMeasurement1DParameterNode
#

@parameterNodeWrapper
class StenosisMeasurement1DParameterNode:
    inputCurveNode: slicer.vtkMRMLMarkupsCurveNode

#
# StenosisMeasurement1DWidget
#

class StenosisMeasurement1DWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent=None) -> None:
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.__init__(self, parent)
    VTKObservationMixin.__init__(self)  # needed for parameter node observation
    self.logic = None
    self._parameterNode = None
    self._parameterNodeGuiTag = None

  def setup(self) -> None:
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
    
    # Application connections
    self.ui.inputMarkupsSelector.connect("currentNodeChanged(vtkMRMLNode*)", lambda node: self.setInputCurve(node))
    
    # Fill the table through a callback from logic.
    self.logic._widgetCallback = self.populateTable

  def cleanup(self) -> None:
    """
    Called when the application closes and the module widget is destroyed.
    """
    self.removeObservers()

  def enter(self) -> None:
    """
    Called each time the user opens this module.
    """
    # Make sure parameter node exists and observed
    self.initializeParameterNode()
    self.setInputCurve(self._parameterNode.inputCurveNode)

  def exit(self) -> None:
    """
    Called each time the user opens a different module.
    """
    self.logic.updateCurveObservations(None)
    self.logic.setWidgetCallback(None)
    # Do not react to parameter node changes (GUI will be updated when the user enters into the module)
    if self._parameterNode:
        self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
        self._parameterNodeGuiTag = None

  def onSceneStartClose(self, caller, event) -> None:
    """
    Called just before the scene is closed.
    """
    # Parameter node will be reset, do not use it anymore
    self.setParameterNode(None)

  def onSceneEndClose(self, caller, event) -> None:
    """
    Called just after the scene is closed.
    """
    # If this module is shown while the scene is closed then recreate a new parameter node immediately
    if self.parent.isEntered:
      self.initializeParameterNode()
    self.logic.InitMemberVariables()

  def initializeParameterNode(self) -> None:
    """
    Ensure parameter node exists and observed.
    """
    # Parameter node stores all user choices in parameter values, node selections, etc.
    # so that when the scene is saved and reloaded, these settings are restored.

    self.setParameterNode(self.logic.getParameterNode())

  def setParameterNode(self, inputParameterNode: Optional[StenosisMeasurement1DParameterNode]) -> None:
    """
    Set and observe parameter node.
    Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
    """
    if self._parameterNode:
        self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
    self._parameterNode = inputParameterNode
    if self._parameterNode:
        # Note: in the .ui file, a Qt dynamic property called "SlicerParameterName" is set on each
        # ui element that needs connection.
        self._parameterNodeGuiTag = self._parameterNode.connectGui(self.ui)

  def setInputCurve(self, curveNode) -> None:
    if not curveNode:
      self.populateTable(None) # Clear the table.
    self.logic.setWidgetCallback(None)
    self.logic.updateCurveObservations(None)
    if self._parameterNode:
      self._parameterNode.inputCurveNode = curveNode
      self.logic.updateCurveObservations(curveNode)
      self.logic.setWidgetCallback(self.populateTable)
      self.logic.process()

  def populateTable(self, distancesArray: vtk.vtkDoubleArray) -> None:
    inputCurve = None
    if self._parameterNode:
      inputCurve = self._parameterNode.inputCurveNode
    outputTable = self.ui.outputTableWidget
    # Clean table completely.
    outputTable.clear()
    outputTable.setRowCount(0)
    outputTable.setColumnCount(0)
    if not inputCurve or not distancesArray:
        return

    numberOfTuples = distancesArray.GetNumberOfTuples()
    # Setup table.
    if outputTable.columnCount == 0:
        outputTable.setColumnCount(4)
        outputTable.setRowCount(numberOfTuples - 1)
        columnLabels = (_("Cumulative"), _("Cumulative %"), _("Partial"), _("Partial %"))
        outputTable.setHorizontalHeaderLabels(columnLabels)
    # Get length units.
    measurementLength = inputCurve.GetMeasurement("length")
    measurementLengthUnit = measurementLength.GetUnits()
    """
    Iterate over control points.
    Start at index 1, we measure backwards.
    In the first row, all values are 0.0.
    """
    for pointIndex in range(1, numberOfTuples):
        distances = distancesArray.GetTuple(pointIndex)
        cumulativeDistance = distances[0]
        relativeCumulativeDistance = distances[1]
        partialDistance = distances[2]
        relativePartialDistance = distances[3]

        item = qt.QTableWidgetItem()
        content = f"{cumulativeDistance:.1f} {measurementLengthUnit}"
        item.setText(content)
        outputTable.setItem(pointIndex - 1, 0, item)
        # Proportional cumulative distance, with respect to total length.
        item = qt.QTableWidgetItem()
        content = f"{relativeCumulativeDistance * 100:.1f} %"
        item.setText(content)
        outputTable.setItem(pointIndex - 1, 1, item)

        # Distance between two adjacent points.
        item = qt.QTableWidgetItem()
        content = f"{partialDistance:.1f} {measurementLengthUnit}"
        item.setText(content)
        outputTable.setItem(pointIndex - 1, 2, item)
        # Proportional distance between two adjacent points, with respect to total length.
        item = qt.QTableWidgetItem()
        content = f"{relativePartialDistance * 100:.1f} %"
        item.setText(content)
        outputTable.setItem(pointIndex - 1, 3, item)

#
# StenosisMeasurement1DLogic
#

class StenosisMeasurement1DLogic(ScriptedLoadableModuleLogic):

  def __init__(self) -> None:
    """
    Called when the logic class is instantiated. Can be used for initializing member variables.
    """
    ScriptedLoadableModuleLogic.__init__(self)
    self.InitMemberVariables()
  
  def getParameterNode(self):
    return self._parameterNode

  def InitMemberVariables(self) -> None:
    self._parameterNode = StenosisMeasurement1DParameterNode(super().getParameterNode())
    self._observations = []
    self._widgetCallback = None
  
  def setWidgetCallback(self, widgetCallback):
    self._widgetCallback = widgetCallback

  def updateCurveObservations(self, curveNode) -> None:
    # Remove all observations on current curve
    if curveNode:
        for observation in self._observations:
            curveNode.RemoveObserver(observation)
    self._observations.clear()

    # React when points are moved, removed or added.
    if curveNode:
        self._observations.append(curveNode.AddObserver(slicer.vtkMRMLMarkupsNode.PointEndInteractionEvent, self.onCurveControlPointEvent))
        # Don't use PointAddedEvent. It is fired on mouse move in views.
        self._observations.append(curveNode.AddObserver(slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self.onCurveControlPointEvent))
        self._observations.append(curveNode.AddObserver(slicer.vtkMRMLMarkupsNode.PointRemovedEvent, self.onCurveControlPointEvent))
        self.process()
    else:
        msg = _("No curve.")
        slicer.util.showStatusMessage(msg, 4000)
        slicer.app.processEvents()
        logging.info(msg)
        # Signal widget to clear the table.
        if self._widgetCallback:
            self._widgetCallback(None)

  def onCurveControlPointEvent(self, caller, event) -> None:
    self.process()

  def process(self) -> vtk.vtkDoubleArray:
    inputCurve = self._parameterNode.inputCurveNode
    if not inputCurve:
      msg = _("No curve.")
      slicer.util.showStatusMessage(msg, 4000)
      slicer.app.processEvents()
      logging.info(msg)
      return

    # Generate a linear polydata from first and last control point.
    numberOfControlPoints = inputCurve.GetNumberOfControlPoints()
    lineSource = vtk.vtkLineSource()
    curveControlPoints = vtk.vtkPoints()
    inputCurve.GetControlPointPositionsWorld(curveControlPoints)
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
        inputCurve.SetNthControlPointPosition(pointIndex,
                                                   sortedCumulativeDistanceArray[pointIndex][1])

    curveTotalLength = inputCurve.GetCurveLengthWorld()
    inputCurve.GetControlPointPositionsWorld(curveControlPoints)
    startPoint = curveControlPoints.GetPoint(0)
    partialDistance = 0.0
    results = vtk.vtkDoubleArray()
    results.SetNumberOfComponents(4)
    for pointIndex in range(0, numberOfControlPoints):
        controlPointPosition = curveControlPoints.GetPoint(pointIndex) # A coordinate.
        controlPointIndex = inputCurve.GetClosestCurvePointIndexToPositionWorld(controlPointPosition) # An integer.
        # Distance of control point from start.
        cumulativeDistance = inputCurve.GetCurveLengthBetweenStartEndPointsWorld(
            0, controlPointIndex)
        relativeCumulativeDistance = cumulativeDistance / curveTotalLength

        # Distance between two adjacent points.
        previousControlPointPosition = curveControlPoints.GetPoint(pointIndex - 1) if pointIndex else startPoint
        previousControlPointIndex = inputCurve.GetClosestCurvePointIndexToPositionWorld(previousControlPointPosition) if pointIndex else inputCurve.GetClosestCurvePointIndexToPositionWorld(startPoint)
        partialDistance = inputCurve.GetCurveLengthBetweenStartEndPointsWorld(
            previousControlPointIndex, controlPointIndex)
        relativePartialDistance = partialDistance / curveTotalLength

        results.InsertNextTuple( (cumulativeDistance, relativeCumulativeDistance, partialDistance, relativePartialDistance) )

    # Signal widget to fill the table with results.
    if self._widgetCallback:
        self._widgetCallback(results)

    # This is for python scripting if there is no callback.
    return results
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

    self.delayDisplay(_("Starting the test"))

    self.delayDisplay(_("Test passed"))
