import os
import unittest
import logging
import vtk, qt, ctk, slicer
import numpy
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

"""
  CenterLineMetrics
  This file is almost totally derived from LineProfile.py.
  The core diameter calculation code is poked from VMTK's
  README.md file.
"""

class CenterLineMetrics(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Centerline metrics"  # TODO: make this more human readable by adding spaces
    self.parent.categories = ["Vascular Modeling Toolkit"]  # TODO: set categories (folders where the module shows up in the module selector)
    self.parent.dependencies = []  # TODO: add here list of module names that this module requires
    self.parent.contributors = ["SET (Hobbyist)"]  # TODO: replace with "Firstname Lastname (Organization)"
    self.parent.helpText = """
This module plots average diameters around a VMTK centerline model. It is intended for non-bifurcated centerlines. Documentation is available
    <a href="https://github.com/chir-set/CenterLineMetrics">here</a>.
"""  
    self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
"""  # TODO: replace with organization, grant and thanks.

#
# CenterLineMetricsWidget
#

class CenterLineMetricsWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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

  def setup(self):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer)
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/CenterLineMetrics.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    # Set scene in MRML widgets. Make sure that in Qt designer
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    self.logic = CenterLineMetricsLogic()
    self.ui.radioCumulative.setChecked(True) # Default to cumulative distance
    self.ui.axisLabel.hide()
    self.ui.axisGroup.hide()
    self.ui.radioS.setChecked(True) # Default to superior

    # connections
    self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)
    self.ui.inputModelSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelectNode)
    self.ui.outputPlotSeriesSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelectNode)
    self.ui.outputTableSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelectNode)
    self.ui.radioR.connect("clicked()", self.onRadioR)
    self.ui.radioA.connect("clicked()", self.onRadioA)
    self.ui.radioS.connect("clicked()", self.onRadioS)
    self.ui.radioCumulative.connect("clicked()", self.onRadioCumulative)
    self.ui.radioProjected.connect("clicked()", self.onRadioProjected)

    # Refresh Apply button state
    self.onSelectNode()
    
  def cleanup(self):
    """
    Called when the application closes and the module widget is destroyed.
    """
    self.removeObservers()
    
  def onApplyButton(self):
    """
    Run processing when user clicks "Apply" button.
    """
    try:
      self.createOutputNodes()
      self.logic.run()

    except Exception as e:
      slicer.util.errorDisplay("Failed to compute results: "+str(e))
      import traceback
      traceback.print_exc()
  
  def onSelectNode(self):
    self.ui.applyButton.enabled = self.ui.inputModelSelector.currentNode()
    self.logic.setInputModelNode(self.ui.inputModelSelector.currentNode())
    self.logic.setOutputTableNode(self.ui.outputTableSelector.currentNode())
    self.logic.setOutputPlotSeriesNode(self.ui.outputPlotSeriesSelector.currentNode())

  def createOutputNodes(self):
    if not self.ui.outputTableSelector.currentNode():
      outputTableNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLTableNode")
      self.ui.outputTableSelector.setCurrentNode(outputTableNode)
    if not self.ui.outputPlotSeriesSelector.currentNode():
      outputPlotSeriesNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotSeriesNode")
      self.ui.outputPlotSeriesSelector.setCurrentNode(outputPlotSeriesNode)

  def onApplyButton(self):
    self.createOutputNodes()
    self.logic.run()
  
  def onRadioR(self):
    self.logic.setAxis(0)
    
  def onRadioA(self):
    self.logic.setAxis(1)
    
  def onRadioS(self):
    self.logic.setAxis(2)
    
  def onRadioCumulative(self):
    self.ui.axisLabel.hide()
    self.ui.axisGroup.hide()
    self.logic.distanceMode = 0

  def onRadioProjected(self):
    self.ui.axisLabel.show()
    self.ui.axisGroup.show()
    self.logic.distanceMode = 1

#
# CenterLineMetricsLogic
#

class CenterLineMetricsLogic(ScriptedLoadableModuleLogic):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget.
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """
  def __init__(self):
    self.inputModelNode = None
    self.outputPlotSeriesNode = None
    self.outputTableNode = None
    self.plotChartNode = None
    self.axis = 2 # Default to vertical
    self.distanceMode = 0 # Default to cumulative

  def setInputModelNode(self, modelNode):
    if self.inputModelNode == modelNode:
      return
    self.inputModelNode = modelNode

  def setOutputTableNode(self, tableNode):
    if self.outputTableNode == tableNode:
      return
    self.outputTableNode = tableNode

  def setOutputPlotSeriesNode(self, plotSeriesNode):
    if self.outputPlotSeriesNode == plotSeriesNode:
      return
    self.outputPlotSeriesNode = plotSeriesNode
    
  def setAxis(self, selAxis):
    self.axis = selAxis
    
  def run(self):
    if not self.inputModelNode:
      raise ValueError("Input is invalid")

    logging.info('Processing started')
    self.updateOutputTable(self.inputModelNode, self.outputTableNode)
    self.updatePlot(self.outputPlotSeriesNode, self.outputTableNode, self.inputModelNode.GetName())
    self.showPlot()
    logging.info('Processing completed')
    
  def getArrayFromTable(self, outputTable, arrayName):
    distanceArray = outputTable.GetTable().GetColumnByName(arrayName)
    if distanceArray:
      return distanceArray
    newArray = vtk.vtkDoubleArray()
    newArray.SetName(arrayName)
    outputTable.GetTable().AddColumn(newArray)
    return newArray

  def updateOutputTable(self, inputModel, outputTable):

    # Create arrays of data
    distanceArray = self.getArrayFromTable(outputTable, DISTANCE_ARRAY_NAME)
    diameterArray = self.getArrayFromTable(outputTable, DIAMETER_ARRAY_NAME)

    # From VMTK README.md
    points = slicer.util.arrayFromModelPoints(inputModel)
    radii = slicer.util.arrayFromModelPointData(inputModel, 'Radius')
    outputTable.GetTable().SetNumberOfRows(radii.size)
    if self.distanceMode == 0:
        cumArray = vtk.vtkDoubleArray()
        self.cumulateDistances(points, cumArray)
    for i, radius in enumerate(radii):
        if self.distanceMode != 0:
            distanceArray.SetValue(i, points[i][self.axis])
        else:
            distanceArray.SetValue(i, cumArray.GetValue(i))
        diameterArray.SetValue(i, radius * 2)
    distanceArray.Modified()
    diameterArray.Modified()
    outputTable.GetTable().Modified()

  def updatePlot(self, outputPlotSeries, outputTable, name=None):

    # Create plot
    if name:
      outputPlotSeries.SetName(name)
    outputPlotSeries.SetAndObserveTableNodeID(outputTable.GetID())
    outputPlotSeries.SetXColumnName(DISTANCE_ARRAY_NAME)
    outputPlotSeries.SetYColumnName(DIAMETER_ARRAY_NAME)
    outputPlotSeries.SetPlotType(slicer.vtkMRMLPlotSeriesNode.PlotTypeScatter)
    outputPlotSeries.SetMarkerStyle(slicer.vtkMRMLPlotSeriesNode.MarkerStyleNone)
    outputPlotSeries.SetColor(0, 0.6, 1.0)

  def showPlot(self):

    # Create chart and add plot
    if not self.plotChartNode:
      plotChartNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotChartNode")
      self.plotChartNode = plotChartNode
      self.plotChartNode.SetXAxisTitle(DISTANCE_ARRAY_NAME+" (mm)")
      self.plotChartNode.SetYAxisTitle(DIAMETER_ARRAY_NAME+" (mm)")
      self.plotChartNode.AddAndObservePlotSeriesNodeID(self.outputPlotSeriesNode.GetID())

    # Show plot in layout
    slicer.modules.plots.logic().ShowChartInLayout(self.plotChartNode)
    slicer.app.layoutManager().plotWidget(0).plotView().fitToContent()
    
  def cumulateDistances(self, arrPoints, cumArray):
    cumArray.SetNumberOfValues(arrPoints.size)
    previous = arrPoints[0]
    dist = 0
    for i, point in enumerate(arrPoints):
      # https://stackoverflow.com/questions/1401712/how-can-the-euclidean-distance-be-calculated-with-numpy
      dist += numpy.linalg.norm(point - previous)
      cumArray.SetValue(i, dist)
      previous = point

#
# CenterLineMetricsTest
#

class CenterLineMetricsTest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setUp(self):
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    slicer.mrmlScene.Clear(0)

  def runTest(self):
    """
    """

  def test_CenterLineMetrics1(self):
    """
    """

DISTANCE_ARRAY_NAME = "Distance"
DIAMETER_ARRAY_NAME = "Diameter"
