import os
import unittest
import logging
import vtk, qt, ctk, slicer
import numpy
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

"""
  CenterlineMetrics
  This file is almost totally derived from LineProfile.py.
  The core diameter calculation code is poked from VMTK's
  README.md file.
"""

class CenterlineMetrics(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Centerline metrics"
    self.parent.categories = ["Vascular Modeling Toolkit"]
    self.parent.dependencies = []
    self.parent.contributors = ["SET (Surgeon) (Hobbyist developer)"]
    self.parent.helpText = """
This module plots average diameters around a VMTK centerline model. It is intended for non-bifurcated centerlines. Documentation is available
    <a href="https://github.com/chir-set/CenterlineMetrics">here</a>.
"""  
    self.parent.acknowledgementText = """
This file was originally developed by SET. Many thanks to Andras Lasso for sanitizing the code.
"""  # TODO: replace with organization, grant and thanks.

#
# CenterlineMetricsWidget
#

class CenterlineMetricsWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/CenterlineMetrics.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)
    
    # Add vertical spacer
    self.layout.addStretch(1) 

    # Set scene in MRML widgets. Make sure that in Qt designer
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    self.logic = CenterlineMetricsLogic()
    self.resetMoveToPointSliderWidget()
    self.ui.advancedCollapsibleButton.checked = False
    self.setUnitNodePrecision()
    self.ui.toggleLayoutButton.visible = False
    self.previousLayoutId = slicer.app.layoutManager().layout
    self.ui.segmentationCollapsibleButton.collapsed = True
    self.ui.coordinatesCollapsibleButton.collapsed = True

    # connections
    self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)
    self.ui.inputModelSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelectNode)
    self.ui.outputPlotSeriesSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelectNode)
    self.ui.outputTableSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelectNode)
    self.ui.radioLPS.connect("clicked()", self.onRadioLPS)
    self.ui.radioRAS.connect("clicked()", self.onRadioRAS)
    self.ui.distinctColumnsCheckBox.connect("clicked()", self.onDistinctCoordinatesCheckBox)
    self.ui.moveToPointSliderWidget.connect("valueChanged(double)", self.moveSliceView)
    self.ui.jumpCentredInSliceNodeCheckBox.connect("clicked()", self.onJumpCentredInSliceNodeCheckBox)
    self.ui.moveToMinimumPushButton.connect("clicked()", self.moveSliceViewToMinimumDiameter)
    self.ui.moveToMaximumPushButton.connect("clicked()", self.moveSliceViewToMaximumDiameter)
    self.ui.toggleLayoutButton.connect("clicked()", self.toggleLayout)
    self.ui.segmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelectSegmentationNodes)
    self.ui.segmentSelector.connect("currentSegmentChanged(QString)", self.onSelectSegmentationNodes)
    self.ui.showAvailableCrossSectionsButton.connect("clicked()", self.onShowAvailableCrossSections)

    # Refresh Apply button state
    self.onSelectNode()
    
  def cleanup(self):
    """
    Called when the application closes and the module widget is destroyed.
    """
    self.removeObservers()
  
  def onSelectNode(self):
    self.logic.setInputModelNode(self.ui.inputModelSelector.currentNode())
    self.ui.applyButton.enabled = self.logic.isInputModelValid()
    self.logic.setOutputTableNode(self.ui.outputTableSelector.currentNode())
    self.logic.setOutputPlotSeriesNode(self.ui.outputPlotSeriesSelector.currentNode())
    self.ui.moveToPointSliderWidget.setValue(0)
    self.resetMoveToPointSliderWidget()
    self.resetUIWithEmptyMetrics()

  def createOutputNodes(self):
    if not self.ui.outputTableSelector.currentNode():
      outputTableNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLTableNode")
      self.ui.outputTableSelector.setCurrentNode(outputTableNode)
    if not self.ui.outputPlotSeriesSelector.currentNode():
      outputPlotSeriesNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotSeriesNode")
      self.ui.outputPlotSeriesSelector.setCurrentNode(outputPlotSeriesNode)

  def onApplyButton(self):
    if not self.logic.isInputModelValid():
        msg = "Input is invalid."
        slicer.util.showStatusMessage(msg, 3000)
        logging.info(msg)
        return # Just don't do anything
    self.resetUIWithEmptyMetrics()
    self.resetSurfaceAreaUIWithEmptyMetrics()
    self.createOutputNodes()
    self.logic.run()
    self.ui.moveToPointSliderWidget.maximum = self.logic.outputTableNode.GetTable().GetNumberOfRows() -1 -1 
    self.ui.toggleLayoutButton.visible = True
    
  def onRadioLPS(self):
    self.logic.coordinateSystemColumnRAS = False
  
  def onRadioRAS(self):
    self.logic.coordinateSystemColumnRAS = True
    
  def onDistinctCoordinatesCheckBox(self):
    self.logic.coordinateSystemColumnSingle = not self.ui.distinctColumnsCheckBox.checked
  
  def onJumpCentredInSliceNodeCheckBox(self):
    self.logic.jumpCentredInSliceNode = self.ui.jumpCentredInSliceNodeCheckBox.checked
    
  def moveSliceView(self, value):
    # +++, else, crash !!
    if not self.logic.isInputModelValid():
      return
    self.logic.moveSliceView(self.ui.sliceViewSelector.currentNode(), value)
    self.updateUIWithMetrics(value)
    self.updateSurfaceAreaUIWithMetrics(value)
  
  def updateUIWithMetrics(self, value):
    tableNode = self.logic.outputTableNode
    if tableNode is None:
        return
    coordinateArray = self.logic.getRASCoordinatesAtIndex(value)
    distance = self.logic.getUnitNodeDisplayString(tableNode.GetTable().GetValue(int(value), 0).ToDouble(), "length")
    diameter = self.logic.getUnitNodeDisplayString(tableNode.GetTable().GetValue(int(value), 1).ToDouble(), "length")
    coordinate = "R " + str(round(coordinateArray[0], 1))
    coordinate += ", A " + str(round(coordinateArray[1], 1))
    coordinate += ", S" + str(round(coordinateArray[2], 1))
    self.ui.distanceValueLabel.setText(distance)
    self.ui.diameterValueLabel.setText(diameter)
    self.ui.coordinatesValueLabel.setText(coordinate)
  
  # Show the surface area. In addition, derive the diameter of the circle having this area. Show also the difference and the ratio to the VMTK diameter.
  def updateSurfaceAreaUIWithMetrics(self, value):
    surfaceArea = self.logic.currentSurfaceArea
    if surfaceArea == 0.0:
        self.resetSurfaceAreaUIWithEmptyMetrics()
        return
    tableNode = self.logic.outputTableNode
    if tableNode is None:
        return
    vmtkDiameter = tableNode.GetTable().GetValue(int(value), 1).ToDouble()
    derivedDiameter = (numpy.sqrt(surfaceArea / numpy.pi)) * 2
    diameterDifference = (derivedDiameter - vmtkDiameter)
    diameterPercentDifference = (diameterDifference / vmtkDiameter) * 100
    operator = ("+" if diameterDifference >= 0 else "-")
    self.ui.surfaceAreaValueLabel.setText(self.logic.getUnitNodeDisplayString(surfaceArea, "area"))
    derivedValues = self.logic.getUnitNodeDisplayString(derivedDiameter, "length")
    # Using str().strip() to remove a leading space
    derivedValues += " (MIS diameter " + operator + " " + self.logic.getUnitNodeDisplayString(abs(diameterDifference), "length").strip()
    derivedValues += ", " + operator + str(round(abs(diameterPercentDifference), 2)) + "%)"
    self.ui.derivedDiameterValueLabel.setText(derivedValues)
    
  def resetUIWithEmptyMetrics(self):
    self.ui.distanceValueLabel.setText("")
    self.ui.diameterValueLabel.setText("")
    self.ui.coordinatesValueLabel.setText("")
  
  def resetSurfaceAreaUIWithEmptyMetrics(self):
    self.ui.surfaceAreaValueLabel.setText("")
    self.ui.derivedDiameterValueLabel.setText("")
    
  def resetMoveToPointSliderWidget(self):
    slider = self.ui.moveToPointSliderWidget
    slider.minimum = 0
    slider.maximum = 0
    slider.setValue(0)

  def moveSliceViewToMinimumDiameter(self):
    point = self.logic.getExtremeDiameterPoint(False)
    if point == -1:
        return
    self.ui.moveToPointSliderWidget.setValue(point)
  
  def moveSliceViewToMaximumDiameter(self):
    point = self.logic.getExtremeDiameterPoint(True)
    if point == -1:
        return
    self.ui.moveToPointSliderWidget.setValue(point)
    
  def setUnitNodePrecision(self):
    selectionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLSelectionNodeSingleton")
    unitNode = slicer.mrmlScene.GetNodeByID(selectionNode.GetUnitNodeID("length"))
    unitNode.SetPrecision(2)
    unitNode = slicer.mrmlScene.GetNodeByID(selectionNode.GetUnitNodeID("area"))
    unitNode.SetPrecision(2)
  
  # Useful UI enhancement. Get back to the previous layout that would most certainly have a 3D view before we plot the diameter distribution chart. And back to the plot layout.
  def toggleLayout(self):
    wasCurrentLayoutId = slicer.app.layoutManager().layout
    slicer.app.layoutManager().setLayout(self.previousLayoutId)
    self.previousLayoutId = wasCurrentLayoutId
  
  # Every time we select a segmentation or a segment.
  def onSelectSegmentationNodes(self):
    self.logic.segmentationNode = self.ui.segmentationSelector.currentNode()
    self.logic.currentSegmentID = self.ui.segmentSelector.currentSegmentID()
    self.resetSurfaceAreaUIWithEmptyMetrics()
    self.logic.currentSurfaceArea = 0.0
    # Create cross-section models at start point
    self.logic.moveSliceView(self.ui.sliceViewSelector.currentNode() , self.ui.moveToPointSliderWidget.value)
    
  def onShowAvailableCrossSections(self):
    self.logic.setShowAvailableCrossSections( self.ui.showAvailableCrossSectionsButton.checked)

#
# CenterlineMetricsLogic
#

class CenterlineMetricsLogic(ScriptedLoadableModuleLogic):
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
    self.coordinateSystemColumnSingle = True
    self.coordinateSystemColumnRAS = True  # LPS or RAS
    self.jumpCentredInSliceNode = False
    self.islandModelNode = None
    self.segmentationNode = None
    self.currentSegmentID = ""
    self.currentSurfaceArea = 0.0
    # Stack of cross-sections
    self.appendedPolyData = vtk.vtkAppendPolyData()
    self.appendedModelNode = None
    self.appendedModelNodeId = ""
    ## Do not re-append
    self.appendedPointIndices = vtk.vtkIntArray()
    ## To reset things if the appended model is removed by the user
    self.sceneNodeRemovedObservation = None
    self.showAvailableCrossSections = False

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

  def setShowAvailableCrossSections(self, checked):
    self.showAvailableCrossSections = checked
    if self.appendedModelNode is not None:
        self.appendedModelNode.GetDisplayNode().SetVisibility(self.showAvailableCrossSections)

  def isInputModelValid(self):
    if not self.inputModelNode:
      return False
    if not self.inputModelNode.HasPointScalarName("Radius"):
      return False
    return True
    
  def run(self):
    if not self.isInputModelValid():
        msg = "Input is invalid."
        slicer.util.showStatusMessage(msg, 3000)
        raise ValueError(msg)

    logging.info('Processing started')
    self.emptyOutputTableNode()
    self.updateOutputTable(self.inputModelNode, self.outputTableNode)
    self.updatePlot(self.outputPlotSeriesNode, self.outputTableNode, self.inputModelNode.GetName())
    self.showPlot()
    logging.info('Processing completed')  

  def emptyOutputTableNode(self):
    # Clears the plot also.
    while self.outputTableNode.GetTable().GetNumberOfColumns():
        self.outputTableNode.GetTable().RemoveColumn(0)
    self.outputTableNode.GetTable().Modified()
    
  def getArrayFromTable(self, outputTable, arrayName):
    columnArray = outputTable.GetTable().GetColumnByName(arrayName)
    if columnArray:
      return columnArray
    columnArray = vtk.vtkDoubleArray()
    columnArray.SetName(arrayName)
    # outputTable.AddColumn must be used because outputTable.GetTable().AddColumn
    # does not initialize the column to the right initial size.
    outputTable.AddColumn(columnArray)
    return columnArray

  def updateOutputTable(self, inputModel, outputTable):
    # Create arrays of data
    distanceArray = self.getArrayFromTable(outputTable, DISTANCE_ARRAY_NAME)
    diameterArray = self.getArrayFromTable(outputTable, DIAMETER_ARRAY_NAME)
    if self.coordinateSystemColumnSingle:
        coordinatesArray = self.getArrayFromTable(outputTable, "RAS" if self.coordinateSystemColumnRAS else "LPS")
        coordinatesArray.SetNumberOfComponents(3)
        coordinatesArray.SetComponentName(0, "R" if self.coordinateSystemColumnRAS else "L")
        coordinatesArray.SetComponentName(1, "A" if self.coordinateSystemColumnRAS else "P")
        coordinatesArray.SetComponentName(2, "S")
        # Add a custom attribute to the table. We may easily know how the coordinates are stored.
        outputTable.SetAttribute("columnSingle", "y")
    else:
      coordinatesArray = [
        self.getArrayFromTable(outputTable, "R" if self.coordinateSystemColumnRAS else "L"),
        self.getArrayFromTable(outputTable, "A" if self.coordinateSystemColumnRAS else "P"),
        self.getArrayFromTable(outputTable, "S")
        ]
      outputTable.SetAttribute("columnSingle", "n")
    # Custom attribute for quick access to coordinates type.
    outputTable.SetAttribute("type", "RAS" if self.coordinateSystemColumnRAS else "LPS")
    
    # From VMTK README.md
    points = slicer.util.arrayFromModelPoints(inputModel)
    radii = slicer.util.arrayFromModelPointData(inputModel, 'Radius')
    outputTable.GetTable().SetNumberOfRows(radii.size)

    cumArray = vtk.vtkDoubleArray()
    self.cumulateDistances(points, cumArray)
    for i, radius in enumerate(radii):
        distanceArray.SetValue(i, cumArray.GetValue(i))
        diameterArray.SetValue(i, radius * 2)
        # Convert each point coordinate
        if self.coordinateSystemColumnRAS:
          coordinateValues = points[i]
        else:
          coordinateValues = [-points[i][0], -points[i][1], points[i][2]]
        if self.coordinateSystemColumnSingle:
            coordinatesArray.SetTuple3(i, coordinateValues[0], coordinateValues[1], coordinateValues[2])
        else:
            coordinatesArray[0].SetValue(i, coordinateValues[0])
            coordinatesArray[1].SetValue(i, coordinateValues[1])
            coordinatesArray[2].SetValue(i, coordinateValues[2])
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

# Get the coordinates of a point of the centerline as RAS. value is index of point.
  def getRASCoordinatesAtIndex(self, value):
    tableNode = self.outputTableNode
    columnSingle = (tableNode.GetAttribute("columnSingle") == "y")
    coordinateTypeIsRAS = (tableNode.GetAttribute("type") == "RAS")
    if columnSingle:
        coordinatesArray = tableNode.GetTable().GetValue(int(value), 2).ToArray()
        coordinateR = coordinatesArray.GetValue(0) if coordinateTypeIsRAS else -coordinatesArray.GetValue(0)
        coordinateA = coordinatesArray.GetValue(1) if coordinateTypeIsRAS else -coordinatesArray.GetValue(1)
        coordinateS = coordinatesArray.GetValue(2)
    else:
        coordinateR = tableNode.GetTable().GetValue(int(value), 2).ToDouble() if coordinateTypeIsRAS else -tableNode.GetTable().GetValue(int(value), 2).ToDouble()
        coordinateA = tableNode.GetTable().GetValue(int(value), 3).ToDouble() if coordinateTypeIsRAS else -tableNode.GetTable().GetValue(int(value), 4).ToDouble()
        coordinateS = tableNode.GetTable().GetValue(int(value), 4).ToDouble()
    return [coordinateR, coordinateA, coordinateS];

# Move the selected slice view to a point of the centerline, optionally centering on the point. The slice view orientation, reformat or not, is not changed.
  def moveSliceView(self, sliceNode, value):
    tableNode = self.outputTableNode
    if tableNode is None:
        return;
    coordinateArray = self.getRASCoordinatesAtIndex(value)
    
    if self.jumpCentredInSliceNode:
        slicer.vtkMRMLSliceNode.JumpSliceByCentering(sliceNode, coordinateArray[0], coordinateArray[1], coordinateArray[2])
    else:
        slicer.vtkMRMLSliceNode.JumpSlice(sliceNode, coordinateArray[0], coordinateArray[1], coordinateArray[2])
        
    centerlinePoints = slicer.util.arrayFromModelPoints(self.inputModelNode)
    point = centerlinePoints[int(value)]
    direction = centerlinePoints[int(value) + 1] - point
    self.createCrossSection(point, direction, value)

# Convenience function to get the point of minimum or maximum diameter. Is useful for arterial stenosis (minimum) or aneurysm (maximum).
  def getExtremeDiameterPoint(self, boolMaximum):
    if self.outputTableNode is None:
        return -1
    diameterArray = self.outputTableNode.GetTable().GetColumnByName(DIAMETER_ARRAY_NAME)
    # GetRange or GetValueRange ?
    diameterRange = diameterArray.GetRange()
    target = -1
    # Until we find a smart function, kind of vtkDoubleArray::Find(value)
    for i in range(diameterArray.GetNumberOfValues()):
        if diameterArray.GetValue(i) == diameterRange[1 if boolMaximum else 0]:
            target = i
            # If there more points with the same value, they are ignored. First point only.
            break
    return target

  def getUnitNodeDisplayString(self, value, category):
    selectionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLSelectionNodeSingleton")
    unitNode = slicer.mrmlScene.GetNodeByID(selectionNode.GetUnitNodeID(category))
    return unitNode.GetDisplayStringFromValue(value)
    
  
  def createCrossSection(self, center, normal, pointIndex):
    if self.segmentationNode is None or self.currentSegmentID == "":
        # Don't print any message, is perhaps intended.
        return
    
    # Place a plane perpendicular to the centerline
    plane = vtk.vtkPlane()
    plane.SetOrigin(center)
    plane.SetNormal(normal)
    
    # If segmentation is transformed, apply it to the cross-section model. We suppose that the centerline model has been transformed similarly.
    segmentationTransform = vtk.vtkGeneralTransform()
    slicer.vtkMRMLTransformNode.GetTransformBetweenNodes(self.segmentationNode.GetParentTransformNode(), None, segmentationTransform)
    
    # Work on the segment's closed surface
    closedSurfacePolyData = vtk.vtkPolyData()
    self.segmentationNode.GetClosedSurfaceRepresentation(self.currentSegmentID, closedSurfacePolyData)
    
    # Though not needed here, it was surprising that vtkSegment::GetId() is missing.
    currentSegment =  self.segmentationNode.GetSegmentation().GetSegment(self.currentSegmentID)
    
    # Cut through the closed surface and get the points of the contour.
    planeCut = vtk.vtkCutter()
    planeCut.SetInputData(closedSurfacePolyData)
    planeCut.SetCutFunction(plane)
    planeCut.Update()
    planePoints = vtk.vtkPoints()
    planePoints = planeCut.GetOutput().GetPoints()
    # self.segmentationNode.GetDisplayNode().GetSegmentVisibility3D(self.currentSegmentID) doesn't work as expected. Even if the segment is hidden in 3D view, it returns True.
    if planePoints is None:
        msg = "Could not cut segment. Is it visible in 3D view?"
        slicer.util.showStatusMessage(msg, 3000)
        raise ValueError(msg)
    if planePoints.GetNumberOfPoints() < 3:
        logging.info("Not enough points to create surface")
        return
    
    # Keep the closed surface around the centerline
    vCenter = [center[0], center[1], center[2]]
    connectivityFilter = vtk.vtkConnectivityFilter()
    connectivityFilter.SetInputData(planeCut.GetOutput())
    connectivityFilter.SetClosestPoint(vCenter)
    connectivityFilter.SetExtractionModeToClosestPointRegion()
    connectivityFilter.Update()

    # Prefer an inverted color for the model
    segmentColor = currentSegment.GetColor()
    crossSectionColor = [1 - segmentColor[0], 1 - segmentColor[1], 1 - segmentColor[2]]
    
    # Triangulate the contour points
    contourTriangulator = vtk.vtkContourTriangulator()
    contourTriangulator.SetInputData(connectivityFilter.GetPolyDataOutput())
    contourTriangulator.Update()
    
    # Finally create and show the model
    self.currentSurfaceArea = self.createCrossSectionModel(contourTriangulator.GetOutput(), pointIndex, crossSectionColor, currentSegment.GetName())
    
    # Let the models follow a transformed input segmentation
    if self.islandModelNode and segmentationTransform:
        self.islandModelNode.ApplyTransform(segmentationTransform)
    if self.appendedModelNode and segmentationTransform:
        self.appendedModelNode.ApplyTransform(segmentationTransform)

  # Create an exact-fit model representing the cross-section.
  def createCrossSectionModel(self, islandPolyData, pointIndex, color = [1, 1, 0], segmentName = ""):

    # Replace the model at each point.
    if self.islandModelNode is not None:
        slicer.mrmlScene.RemoveNode(self.islandModelNode)
    self.islandModelNode = None
    self.islandModelNode = slicer.modules.models.logic().AddModel(islandPolyData)
    separator = " for " if segmentName else ""
    self.islandModelNode.SetName("Cross-section" + separator + segmentName)
    islandModelDisplayNode = self.islandModelNode.GetDisplayNode()
    islandModelDisplayNode.SetColor(color[0], color[1], color[2])
    islandModelDisplayNode.SetOpacity(0.75)
    
    # N.B. : Cross-sections are not necessarily contiguous
    self.updateAppendedModel(islandPolyData, pointIndex, segmentName)
    
    # Get the surface area.
    islandProperties = vtk.vtkMassProperties()
    islandProperties.SetInputData(islandPolyData)
    return islandProperties.GetSurfaceArea()

  def updateAppendedModel(self, islandPolyData, pointIndex, segmentName = ""):
    if self.appendedModelNode is not None:
        self.appendedModelNode.GetDisplayNode().SetVisibility(self.showAvailableCrossSections)
    # Don't append again if already done at a centerline point
    for i in range(self.appendedPointIndices.GetNumberOfValues()):
        if self.appendedPointIndices.GetValue(i) == pointIndex:
            return
    
    # Work on a copy of the input polydata for the stack model
    islandPolyDataCopy = vtk.vtkPolyData()
    islandPolyDataCopy.DeepCopy(islandPolyData)
    # Set same scalar value to each point of polydata.
    intArray = vtk.vtkIntArray()
    intArray.SetName("PointIndex")
    for i in range(islandPolyDataCopy.GetNumberOfPoints()):
        intArray.InsertNextValue(int(pointIndex))
    islandPolyDataCopy.GetPointData().SetScalars(intArray)
    islandPolyDataCopy.Modified()
    
    self.appendedPolyData.AddInputData(islandPolyDataCopy)
    self.appendedPolyData.Update()
    
    # Remember where it's already done
    self.appendedPointIndices.InsertNextValue(int(pointIndex))
    
    # Remove stack model and observation
    if self.appendedModelNode is not None:
        # Don't react if we remove it from scene on our own
        slicer.mrmlScene.RemoveObserver(self.sceneNodeRemovedObservation)
        slicer.mrmlScene.RemoveNode(self.appendedModelNode)
    # Create a new stack model
    self.appendedModelNode = slicer.modules.models.logic().AddModel(self.appendedPolyData.GetOutputPort())
    separator = " for " if segmentName else ""
    self.appendedModelNode.SetName("Cross-section stack" + separator + segmentName)
    self.appendedModelNode.GetDisplayNode().SetVisibility(self.showAvailableCrossSections)
    # Remember stack model by id
    self.appendedModelNodeId = self.appendedModelNode.GetID()
    # Add an observation if stack model is deleted by the user
    self.sceneNodeRemovedObservation = slicer.mrmlScene.AddObserver(slicer.vtkMRMLScene.NodeRemovedEvent, self.onSceneNodeRemoved)
  
  # Clean up if stack model is removed by user
  def onSceneNodeRemoved(self, scene, eventString):
    self.appendedModelNode = slicer.mrmlScene.GetNodeByID(self.appendedModelNodeId)
    if self.appendedModelNode is None:
        self.appendedModelNodeId = ""
        self.appendedPolyData.RemoveAllInputs()
        self.appendedPointIndices.Reset()
        slicer.mrmlScene.RemoveObserver(self.sceneNodeRemovedObservation)
    
#
# CenterlineMetricsTest
#

class CenterlineMetricsTest(ScriptedLoadableModuleTest):
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

  def test_CenterlineMetrics1(self):
    """
    """

DISTANCE_ARRAY_NAME = "Distance"
DIAMETER_ARRAY_NAME = "Diameter"
