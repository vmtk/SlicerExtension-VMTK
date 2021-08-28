import os
import unittest
import logging
import vtk, qt, ctk, slicer
import numpy as np
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

    # TODO: a module must not change the application-wide unit format
    # If format is not nice enough then some formatting customization must be implemented.
    # selectionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLSelectionNodeSingleton")
    # unitNode = slicer.mrmlScene.GetNodeByID(selectionNode.GetUnitNodeID("length"))
    # unitNode.SetPrecision(2)
    # unitNode = slicer.mrmlScene.GetNodeByID(selectionNode.GetUnitNodeID("area"))
    # unitNode.SetPrecision(2)

    self.ui.segmentSelector.setVisible(False)
    self.ui.browseCollapsibleButton.collapsed = True

    self.ui.toggleTableLayoutButton.visible = False
    self.ui.toggleTableLayoutButton.setIcon(qt.QIcon(':/Icons/Medium/SlicerVisibleInvisible.png'))
    self.ui.togglePlotLayoutButton.visible = False
    self.ui.togglePlotLayoutButton.setIcon(qt.QIcon(':/Icons/Medium/SlicerVisibleInvisible.png'))
    self.previousLayoutId = slicer.app.layoutManager().layout

    self.ui.jumpCentredInSliceNodeCheckBox.setIcon(qt.QIcon(':/Icons/ViewCenter.png'))
    # Until we know where to browse available icons, to use another one. ViewCenter.png has not been found in ./Slicer-*/*. Probably in a resource bundle somewhere.
    self.ui.orthogonalReformatInSliceNodeCheckBox.setIcon(qt.QIcon(':/Icons/ViewCenter.png'))

    # connections
    self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)
    self.ui.inputCenterlineSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelectNode)
    self.ui.outputPlotSeriesSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelectNode)
    self.ui.outputTableSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelectNode)
    self.ui.radioLPS.connect("clicked()", self.onRadioLPS)
    self.ui.radioRAS.connect("clicked()", self.onRadioRAS)
    self.ui.distinctColumnsCheckBox.connect("clicked()", self.onDistinctCoordinatesCheckBox)
    self.ui.moveToPointSliderWidget.connect("valueChanged(double)", self.setCurrentPointIndex)
    self.ui.jumpCentredInSliceNodeCheckBox.connect("clicked()", self.onJumpCentredInSliceNodeCheckBox)
    self.ui.orthogonalReformatInSliceNodeCheckBox.connect("clicked()", self.onOrthogonalReformatInSliceNodeCheckBox)
    self.ui.moveToMinimumPushButton.connect("clicked()", self.moveSliceViewToMinimumDiameter)
    self.ui.moveToMaximumPushButton.connect("clicked()", self.moveSliceViewToMaximumDiameter)
    self.ui.toggleTableLayoutButton.connect("clicked()", self.toggleTableLayout)
    self.ui.togglePlotLayoutButton.connect("clicked()", self.togglePlotLayout)
    self.ui.segmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelectSegmentationNodes)
    self.ui.segmentSelector.connect("currentSegmentChanged(QString)", self.onSelectSegmentationNodes)
    self.ui.showCrossSectionButton.connect("clicked()", self.onShowCrossSection)
    self.ui.showMISDiameterPushButton.connect("clicked()", self.onShowMaximumInscribedSphere)
    self.ui.sliceViewSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelectSliceNode)

    # Refresh Apply button state
    self.onSelectNode()
    
  def cleanup(self):
    """
    Called when the application closes and the module widget is destroyed.
    """
    self.removeObservers()
  
  def onSelectNode(self):
    self.logic.setInputCenterlineNode(self.ui.inputCenterlineSelector.currentNode())
    self.ui.applyButton.enabled = self.logic.isInputCenterlineValid()
    self.logic.setOutputTableNode(self.ui.outputTableSelector.currentNode())
    self.logic.setOutputPlotSeriesNode(self.ui.outputPlotSeriesSelector.currentNode())
    self.ui.moveToPointSliderWidget.setValue(0)
    self.resetMoveToPointSliderWidget()
    self.clearMetrics()

  def createOutputNodes(self):
    if self.logic.isCenterlineRadiusAvailable():
      if not self.ui.outputTableSelector.currentNode():
        outputTableNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLTableNode")
        self.ui.outputTableSelector.setCurrentNode(outputTableNode)
      if not self.ui.outputPlotSeriesSelector.currentNode():
        outputPlotSeriesNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotSeriesNode")
        self.ui.outputPlotSeriesSelector.setCurrentNode(outputPlotSeriesNode)

  def onApplyButton(self):
    if not self.logic.isInputCenterlineValid():
        msg = "Input is invalid."
        slicer.util.showStatusMessage(msg, 3000)
        logging.info(msg)
        return # Just don't do anything

    self.previousLayoutId = slicer.app.layoutManager().layout
    self.clearMetrics()
    self.createOutputNodes()
    self.logic.run()

    self.ui.browseCollapsibleButton.collapsed = False

    isCenterlineRadiusAvailable = self.logic.isCenterlineRadiusAvailable()
    self.ui.toggleTableLayoutButton.visible = isCenterlineRadiusAvailable and (self.logic.outputTableNode is not None)
    self.ui.togglePlotLayoutButton.visible = isCenterlineRadiusAvailable and (self.logic.outputPlotSeriesNode is not None)
    self.ui.moveToMinimumPushButton.enabled = isCenterlineRadiusAvailable
    self.ui.moveToMaximumPushButton.enabled = isCenterlineRadiusAvailable
    self.ui.showMISDiameterPushButton.enabled = isCenterlineRadiusAvailable

    self.ui.showCrossSectionButton.enabled = self.logic.lumenSurfaceNode is not None

    numberOfPoints = self.logic.getNumberOfPoints()
    # Prevent going to the endpoint (direction computation is only implemented for models with forward difference)
    numberOfPoints -= 1

    self.ui.moveToPointSliderWidget.maximum = numberOfPoints - 1
    self.updateMeasurements()

  def onRadioLPS(self):
    self.logic.coordinateSystemColumnRAS = False
  
  def onRadioRAS(self):
    self.logic.coordinateSystemColumnRAS = True
    
  def onDistinctCoordinatesCheckBox(self):
    self.logic.coordinateSystemColumnSingle = not self.ui.distinctColumnsCheckBox.checked
  
  def onJumpCentredInSliceNodeCheckBox(self):
    self.logic.jumpCentredInSliceNode = self.ui.jumpCentredInSliceNodeCheckBox.checked
  
  def onOrthogonalReformatInSliceNodeCheckBox (self):
    self.logic.orthogonalReformatInSliceNode = self.ui.orthogonalReformatInSliceNodeCheckBox.checked
    inputSliceNode = self.ui.sliceViewSelector.currentNode()
    if self.ui.orthogonalReformatInSliceNodeCheckBox.checked:
        if inputSliceNode and self.ui.inputCenterlineSelector.currentNode():
            self.logic.updateSliceView(inputSliceNode, self.ui.moveToPointSliderWidget.value)
    else:
        if inputSliceNode:
            inputSliceNode.SetOrientationToDefault()
    self.updateSliceViewOrientationMetrics()
  
  def onSelectSliceNode(self, sliceNode):
    self.logic.selectSliceNode(sliceNode)
    self.updateSliceViewOrientationMetrics()
    if sliceNode is None:
        self.ui.orientationValueLabel.setText("")
    
  def updateUIWithMetrics(self, value):
    pointIndex = int(value)

    coordinateArray = self.logic.getCurvePointPositionAtIndex(value)
    self.ui.coordinatesValueLabel.setText(f"R {round(coordinateArray[0], 1)}, A {round(coordinateArray[1], 1)}, S {round(coordinateArray[2], 1)}")

    tableNode = self.logic.outputTableNode
    if tableNode:
      # Use precomputed values
      distanceStr = self.logic.getUnitNodeDisplayString(tableNode.GetTable().GetValue(int(value), 0).ToDouble(), "length").strip()
      misDiameter = tableNode.GetTable().GetValue(int(value), 1).ToDouble()
      diameterStr = self.logic.getUnitNodeDisplayString(misDiameter, "length").strip()
    else:
      # Compute values on-the-fly
      # radius
      if self.logic.isCenterlineRadiusAvailable():
        position, misRadius = self.logic.getPositionMaximumInscribedSphereRadius(pointIndex)
        misDiameter = misRadius * 2
        diameterStr = self.logic.getUnitNodeDisplayString(misDiameter, "length")
      else:
        diameterStr = ""
        misDiameter = 0.0
      # distance
      if self.logic.inputCenterlineNode.IsTypeOf("vtkMRMLModelNode"):
        distanceStr = ""  # TODO: implement for models
      else:
        distanceStr = self.logic.getUnitNodeDisplayString(self.logic.inputCenterlineNode.GetCurveLengthWorld(0, pointIndex), "length").strip()
    self.ui.distanceValueLabel.setText(distanceStr)
    self.ui.diameterValueLabel.setText(diameterStr)
    
    # Cross-section area metrics

    surfaceArea = self.logic.getCrossSectionArea(pointIndex)
    if surfaceArea > 0.0:
      self.ui.surfaceAreaValueLabel.setText(self.logic.getUnitNodeDisplayString(surfaceArea, "area").strip())
    else:
      self.ui.surfaceAreaValueLabel.setText("N/A (input lumen surface not specified)")

    if surfaceArea > 0.0:
      derivedDiameter = (np.sqrt(surfaceArea / np.pi)) * 2
      derivedDiameterStr = self.logic.getUnitNodeDisplayString(derivedDiameter, "length").strip()
  
      if misDiameter > 0.0:
        diameterDifference = (derivedDiameter - misDiameter)
        """
        Taking misDiameter as reference because in practice, misDiameter
        is almost always smaller than derivedDiameter, at least in diseased arteries. That would also be true in tendons and trachea.
        Easier to read 'referenceDiameter plus excess'
        rather than 'referenceDiameter less excess'
        where excess refers to a virtual circle,
        while MIS is a real in-situ viewable sphere.
        """
        diameterPercentDifference = (diameterDifference / misDiameter) * 100
        diameterDifferenceSign = "+" if diameterPercentDifference >=0 else "-"
        derivedDiameterStr += f" (MIS diameter {diameterDifferenceSign}"
        # Using str().strip() to remove a leading space
        derivedDiameterStr += self.logic.getUnitNodeDisplayString(abs(diameterDifference), "length").strip()
        derivedDiameterStr += f", {diameterDifferenceSign}{round(abs(diameterPercentDifference), 2)}%)"

      self.ui.derivedDiameterValueLabel.setText(derivedDiameterStr)
    else:
      self.ui.derivedDiameterValueLabel.setText("")
    # Orientation
    self.updateSliceViewOrientationMetrics()
    
  def updateSliceViewOrientationMetrics(self):
    if self.ui.sliceViewSelector.currentNode():
        orient = self.logic.getSliceOrientation(self.ui.sliceViewSelector.currentNode())
        orientation = "R " + str(round(orient[0], 1)) + "°,"
        orientation += " A " + str(round(orient[1], 1)) + "°,"
        orientation += " S " + str(round(orient[2], 1)) + "°"
        self.ui.orientationValueLabel.setText(orientation)


  def clearMetrics(self):
    self.ui.coordinatesValueLabel.setText("")
    self.ui.distanceValueLabel.setText("")
    self.ui.diameterValueLabel.setText("")
    self.ui.surfaceAreaValueLabel.setText("")
    self.ui.derivedDiameterValueLabel.setText("")
    self.ui.orientationValueLabel.setText("")

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

  def toggleTableLayout(self):
    """Useful UI enhancement. Get back to the previous layout that would most certainly
    have a 3D view before we plot the diameter distribution chart. And back to the plot layout.
    """
    if not self.logic.setOutputTableNode:
      return
    if self.logic.isTableVisible():
      slicer.app.layoutManager().setLayout(self.previousLayoutId)
    else:
      self.logic.showTable()

  def togglePlotLayout(self):
    """Useful UI enhancement. Get back to the previous layout that would most certainly
    have a 3D view before we plot the diameter distribution chart. And back to the plot layout.
    """
    if not self.logic.outputPlotSeriesNode:
      return
    if self.logic.isPlotVisible():
      slicer.app.layoutManager().setLayout(self.previousLayoutId)
    else:
      self.logic.showPlot()

  # Every time we select a segmentation or a segment.
  def onSelectSegmentationNodes(self):
    self.logic.setLumenSurface(self.ui.segmentationSelector.currentNode(), self.ui.segmentSelector.currentSegmentID())
    self.ui.segmentSelector.setVisible(self.ui.segmentationSelector.currentNode() is not None
      and self.ui.segmentationSelector.currentNode().IsTypeOf("vtkMRMLSegmentationNode"))
    # Update measurements (surface can be changed dynamically, after Apply)
    self.ui.showCrossSectionButton.enabled = self.logic.lumenSurfaceNode is not None
    self.updateMeasurements()
    
  def onShowCrossSection(self):
    show = self.ui.showCrossSectionButton.checked
    self.logic.setShowCrossSection(show)
    if not show:
      self.logic.deleteCrossSection()
    self.updateMeasurements()

  def onShowMaximumInscribedSphere(self):
    show = self.ui.showMISDiameterPushButton.checked
    self.logic.setShowMaximumInscribedSphereDiameter(show)
    if not show:
      self.logic.deleteMaximumInscribedSphere()
    self.updateMeasurements()

  def updateMeasurements(self):
    self.setCurrentPointIndex(self.ui.moveToPointSliderWidget.value)

  def setCurrentPointIndex(self, value):
    if not self.logic.isInputCenterlineValid():
      return
    pointIndex = int(value)

    # Update slice view position
    if self.ui.sliceViewSelector.currentNode():
      self.logic.updateSliceView(self.ui.sliceViewSelector.currentNode(), pointIndex)

    # Update maximum inscribed radius sphere model
    if self.logic.isCenterlineRadiusAvailable():
      self.logic.updateMaximumInscribedSphereModel(pointIndex)
    else:
      self.logic.deleteMaximumInscribedSphere()

    # Update cross-section model
    if self.ui.showCrossSectionButton.checked and self.logic.lumenSurfaceNode:
      self.logic.updateCrossSection(pointIndex)
    else:
      self.logic.deleteCrossSection()

    self.updateUIWithMetrics(value)


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
    self.inputCenterlineNode = None
    self.outputPlotSeriesNode = None
    self.outputTableNode = None
    self.plotChartNode = None
    self.coordinateSystemColumnSingle = True
    self.coordinateSystemColumnRAS = True  # LPS or RAS
    self.jumpCentredInSliceNode = False
    self.lumenSurfaceNode = None
    self.currentSegmentID = ""
    self.crossSectionPolyDataCache = {}
    # Stack of cross-sections
    self.appendedPolyData = vtk.vtkAppendPolyData()
    self.allCrossSectionsModelNode = None
    self.crossSectionColor = [0.2, 0.2, 1.0]
    ## Do not re-append
    self.crossSectionsPointIndices = vtk.vtkIntArray()
    ## To reset things if the appended model is removed by the user
    self.sceneNodeRemovedObservation = None
    self.showCrossSection = False
    self.crossSectionModelNode = None
    self.maximumInscribedSphereModelNode = None
    self.showMaximumInscribedSphere = False
    self.maximumInscribedSphereColor = [0.2, 1.0, 0.4]
    self.orthogonalReformatInSliceNode = False

  def resetCrossSections(self):
    self.crossSectionPolyDataCache = {}

  def setInputCenterlineNode(self, centerlineNode):
    if self.inputCenterlineNode == centerlineNode:
      return
    self.inputCenterlineNode = centerlineNode
    self.resetCrossSections()

  def setLumenSurface(self, lumenSurfaceNode, currentSegmentID):
    if (self.lumenSurfaceNode == lumenSurfaceNode) and (self.currentSegmentID == currentSegmentID):
      return
    self.resetCrossSections()
    self.lumenSurfaceNode = lumenSurfaceNode
    self.currentSegmentID = currentSegmentID

  def setOutputTableNode(self, tableNode):
    if self.outputTableNode == tableNode:
      return
    self.outputTableNode = tableNode

  def setOutputPlotSeriesNode(self, plotSeriesNode):
    if self.outputPlotSeriesNode == plotSeriesNode:
      return
    self.outputPlotSeriesNode = plotSeriesNode

  def selectSliceNode(self, sliceNode):
    # Don't modify Reformat module if we don't plan to use it.
    if sliceNode is None:
        return
    slicer.modules.reformat.widgetRepresentation().setEditedNode(sliceNode)

  def setShowCrossSection(self, checked):
    self.showCrossSection = checked
    if self.crossSectionModelNode is not None:
        self.crossSectionModelNode.GetDisplayNode().SetVisibility(self.showCrossSection)

  def deleteCrossSection(self):
    if self.crossSectionModelNode is not None:
        slicer.mrmlScene.RemoveNode(self.crossSectionModelNode)
    self.crossSectionModelNode = None

  def setShowMaximumInscribedSphereDiameter(self, checked):
    self.showMaximumInscribedSphere = checked
    if self.maximumInscribedSphereModelNode is not None:
        self.maximumInscribedSphereModelNode.GetDisplayNode().SetVisibility(self.showMaximumInscribedSphere)

  def deleteMaximumInscribedSphere(self):
    if self.maximumInscribedSphereModelNode is not None:
        slicer.mrmlScene.RemoveNode(self.maximumInscribedSphereModelNode)
        # Not calling onSceneNodeRemoved here
        self.maximumInscribedSphereModelNode = None

  def isInputCenterlineValid(self):
    return self.inputCenterlineNode is not None

  def isCenterlineRadiusAvailable(self):
    if not self.inputCenterlineNode:
      return False
    if self.inputCenterlineNode.IsTypeOf("vtkMRMLModelNode"):
        return self.inputCenterlineNode.HasPointScalarName("Radius")
    else:
        radiusMeasurement = self.inputCenterlineNode.GetMeasurement('Radius')
        if not radiusMeasurement:
          return False
        if (not radiusMeasurement.GetControlPointValues()) or (radiusMeasurement.GetControlPointValues().GetNumberOfValues()<1):
          return False
        return True

  def getNumberOfPoints(self):
    if not self.inputCenterlineNode:
      return 0
    if self.inputCenterlineNode.IsTypeOf("vtkMRMLModelNode"):
        return self.inputCenterlineNode.GetPolyData().GetNumberOfPoints()
    else:
        return self.inputCenterlineNode.GetCurvePointsWorld().GetNumberOfPoints()

  def run(self):
    self.resetCrossSections()
    if not self.isInputCenterlineValid():
        msg = "Input is invalid."
        slicer.util.showStatusMessage(msg, 3000)
        raise ValueError(msg)

    logging.info('Processing started')
    if self.outputTableNode:
      self.emptyOutputTableNode()
      self.updateOutputTable(self.inputCenterlineNode, self.outputTableNode)
    if self.outputPlotSeriesNode:
      self.updatePlot(self.outputPlotSeriesNode, self.outputTableNode, self.inputCenterlineNode.GetName())
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

  def updateOutputTable(self, inputCenterline, outputTable):
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

    if (inputCenterline.IsTypeOf("vtkMRMLModelNode")):
        pointsLocal = slicer.util.arrayFromModelPoints(inputCenterline)
        points = np.zeros(pointsLocal.shape)
        for pointIndex in range(len(pointsLocal)):
          inputCenterline.TransformPointToWorld(pointsLocal[pointIndex], points[pointIndex])
        radii = slicer.util.arrayFromModelPointData(inputCenterline, 'Radius')
    else:
        points = slicer.util.arrayFromMarkupsCurvePoints(inputCenterline, world=True)
        numberOfPoints = len(points)
        radii = np.zeros(numberOfPoints)
        controlPointFloatIndices = inputCenterline.GetCurveWorld().GetPointData().GetArray('PedigreeIDs')
        controlPointRadiusValues = inputCenterline.GetMeasurement('Radius').GetControlPointValues()
        for pointIndex in range(numberOfPoints-1):
            controlPointFloatIndex = controlPointFloatIndices.GetValue(pointIndex)
            controlPointIndexA = int(controlPointFloatIndex)
            controlPointIndexB = controlPointIndexA + 1
            radiusA = controlPointRadiusValues.GetValue(controlPointIndexA)
            radiusB = controlPointRadiusValues.GetValue(controlPointIndexB)
            radius = radiusA * (controlPointFloatIndex - controlPointIndexA) + radiusB * (controlPointIndexB - controlPointFloatIndex)
            radii[pointIndex] = radius
        radii[numberOfPoints-1] = controlPointRadiusValues.GetValue(controlPointRadiusValues.GetNumberOfValues()-1)

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

  def showTable(self):
    # Create chart and add plot
    if not self.outputTableNode:
      return
    layoutWithTable = slicer.modules.tables.logic().GetLayoutWithTable(slicer.app.layoutManager().layout)
    slicer.app.layoutManager().setLayout(layoutWithTable)
    slicer.app.applicationLogic().GetSelectionNode().SetActiveTableID(self.outputTableNode.GetID())
    slicer.app.applicationLogic().PropagateTableSelection()

  def isTableVisible(self):
    if not self.outputPlotSeriesNode:
      return False
    # Find the table in the displayed views
    layoutManager = slicer.app.layoutManager()
    for tableViewIndex in range(layoutManager.tableViewCount):
      tableViewNode = layoutManager.tableWidget(tableViewIndex).tableView().mrmlTableViewNode()
      if not tableViewNode or not tableViewNode.IsMappedInLayout() or not tableViewNode.GetTableNode():
        continue
      if tableViewNode.GetTableNode() == self.outputTableNode:
        # found this table displayed in a view
        return True
    # Table is not visible
    return False

  def showPlot(self):
    # Create chart
    if not self.plotChartNode:
      plotChartNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotChartNode")
      self.plotChartNode = plotChartNode
      self.plotChartNode.SetXAxisTitle(DISTANCE_ARRAY_NAME+" (mm)")
      self.plotChartNode.SetYAxisTitle(DIAMETER_ARRAY_NAME+" (mm)")
    # Make sure the plot is in the chart
    if not self.plotChartNode.HasPlotSeriesNodeID(self.outputPlotSeriesNode.GetID()):
      self.plotChartNode.AddAndObservePlotSeriesNodeID(self.outputPlotSeriesNode.GetID())
    # Show plot in layout
    slicer.modules.plots.logic().ShowChartInLayout(self.plotChartNode)
    slicer.app.layoutManager().plotWidget(0).plotView().fitToContent()

  def isPlotVisible(self):
    if not self.outputPlotSeriesNode:
      return False
    # Find the plot in the displayed views
    layoutManager = slicer.app.layoutManager()
    for plotViewIndex in range(layoutManager.plotViewCount):
      plotViewNode = layoutManager.plotWidget(plotViewIndex).mrmlPlotViewNode()
      if not plotViewNode or not plotViewNode.IsMappedInLayout() or not plotViewNode.GetPlotChartNode():
        continue
      if plotViewNode.GetPlotChartNode().HasPlotSeriesNodeID(self.outputPlotSeriesNode.GetID()):
        # found this series in a displayed chart
        return True
    # Plot series is not visible
    return False

  def cumulateDistances(self, arrPoints, cumArray):
    cumArray.SetNumberOfValues(arrPoints.size)
    previous = arrPoints[0]
    dist = 0
    for i, point in enumerate(arrPoints):
      # https://stackoverflow.com/questions/1401712/how-can-the-euclidean-distance-be-calculated-with-numpy
      dist += np.linalg.norm(point - previous)
      cumArray.SetValue(i, dist)
      previous = point

  def getCurvePointPositionAtIndex(self, value):
    """Get the coordinates of a point of the centerline as RAS. value is index of point.
    """
    pointIndex = int(value)
    position = np.zeros(3)
    if (self.inputCenterlineNode.IsTypeOf("vtkMRMLModelNode")):
        positionLocal = slicer.util.arrayFromModelPoints(self.inputCenterlineNode)[pointIndex]
        self.inputCenterlineNode.TransformPointToWorld(positionLocal, position)
    else:
        self.inputCenterlineNode.GetCurvePointsWorld().GetPoint(pointIndex, position)
    return position

  def updateSliceView(self, sliceNode, value):
    """Move the selected slice view to a point of the centerline, optionally centering on the point.
    The slice view orientation, reformat or not, is not changed.
    """
    position = self.getCurvePointPositionAtIndex(value)
    
    if self.jumpCentredInSliceNode:
        slicer.vtkMRMLSliceNode.JumpSliceByCentering(sliceNode, *position)
    else:
        slicer.vtkMRMLSliceNode.JumpSlice(sliceNode, *position)
    
    if self.orthogonalReformatInSliceNode:
        reformatLogic = slicer.modules.reformat.logic()
        direction = self.getCurvePointPositionAtIndex(value + 1) - position
        reformatLogic.SetSliceOrigin(sliceNode, position[0], position[1], position[2])
        reformatLogic.SetSliceNormal(sliceNode, direction[0], direction[1], direction[2])

  def getExtremeDiameterPoint(self, boolMaximum):
    """Convenience function to get the point of minimum or maximum diameter.
    Is useful for arterial stenosis (minimum) or aneurysm (maximum).
    """
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

  def computeCrossSectionPolydata(self, pointIndex):
    center = np.zeros(3)
    if self.inputCenterlineNode.IsTypeOf("vtkMRMLModelNode"):
        centerLocal = slicer.util.arrayFromModelPoints(self.inputCenterlineNode)[pointIndex]
        self.inputCenterlineNode.TransformPointToWorld(centerLocal, center)
        centerInc = np.zeros(3)
        centerLocalInc = slicer.util.arrayFromModelPoints(self.inputCenterlineNode)[pointIndex+1] # note that this +1 does not work for the last point
        self.inputCenterlineNode.TransformPointToWorld(centerLocalInc, centerInc)
        normal = centerInc - center
    else:
        normal = np.zeros(3)
        self.inputCenterlineNode.GetCurvePointsWorld().GetPoint(pointIndex, center)
        # There is a bug in GetCurveDirectionAtPointIndexWorld therefore for now
        # we use GetCurvePointToWorldTransformAtPointIndex instead.
        # self.inputCenterlineNode.GetCurveDirectionAtPointIndexWorld(pointIndex, normal)
        curvePointToWorld = vtk.vtkMatrix4x4()
        self.inputCenterlineNode.GetCurvePointToWorldTransformAtPointIndex(pointIndex, curvePointToWorld)
        for i in range(3):
          normal[i] = curvePointToWorld.GetElement(i, 2)

    # Place a plane perpendicular to the centerline
    plane = vtk.vtkPlane()
    plane.SetOrigin(center)
    plane.SetNormal(normal)

    # Work on the segment's closed surface
    closedSurfacePolyData = vtk.vtkPolyData()
    if self.lumenSurfaceNode.GetClassName() == "vtkMRMLSegmentationNode":
      self.lumenSurfaceNode.GetClosedSurfaceRepresentation(self.currentSegmentID, closedSurfacePolyData)
    else:
      closedSurfacePolyData = self.lumenSurfaceNode.GetPolyData()

    # If segmentation is transformed, apply it to the cross-section model. All computations are performed in the world coordinate system.
    if self.lumenSurfaceNode.GetParentTransformNode():
      surfaceTransformToWorld = vtk.vtkGeneralTransform()
      slicer.vtkMRMLTransformNode.GetTransformBetweenNodes(self.lumenSurfaceNode.GetParentTransformNode(), None, surfaceTransformToWorld)
      transformFilterToWorld = vtk.vtkTransformPolyDataFilter()
      transformFilterToWorld.SetTransform(surfaceTransformToWorld)
      transformFilterToWorld.SetInputData(closedSurfacePolyData)
      transformFilterToWorld.Update()
      closedSurfacePolyData = transformFilterToWorld.GetOutput()

    # Cut through the closed surface and get the points of the contour.
    planeCut = vtk.vtkCutter()
    planeCut.SetInputData(closedSurfacePolyData)
    planeCut.SetCutFunction(plane)
    planeCut.Update()
    planePoints = vtk.vtkPoints()
    planePoints = planeCut.GetOutput().GetPoints()
    # self.lumenSurfaceNode.GetDisplayNode().GetSegmentVisibility3D(self.currentSegmentID) doesn't work as expected. Even if the segment is hidden in 3D view, it returns True.
    if planePoints is None:
        msg = "Could not cut segment. Is it visible in 3D view?"
        slicer.util.showStatusMessage(msg, 3000)
        raise ValueError(msg)
    if planePoints.GetNumberOfPoints() < 3:
        logging.info("Not enough points to create surface")
        return None
    
    # Keep the closed surface around the centerline
    vCenter = [center[0], center[1], center[2]]
    connectivityFilter = vtk.vtkConnectivityFilter()
    connectivityFilter.SetInputData(planeCut.GetOutput())
    connectivityFilter.SetClosestPoint(vCenter)
    connectivityFilter.SetExtractionModeToClosestPointRegion()
    connectivityFilter.Update()

    # Triangulate the contour points
    contourTriangulator = vtk.vtkContourTriangulator()
    contourTriangulator.SetInputData(connectivityFilter.GetPolyDataOutput())
    contourTriangulator.Update()

    return contourTriangulator.GetOutput()

  def updateCrossSection(self, pointIndex):
    """Create an exact-fit model representing the cross-section.
    """

    if pointIndex in self.crossSectionPolyDataCache:
      # found polydata cached
      crossSectionPolyData = self.crossSectionPolyDataCache[pointIndex]
    else:
      # cross-section is not found in the cache, compute it now and store in cache
      crossSectionPolyData = self.computeCrossSectionPolydata(pointIndex)
      self.crossSectionPolyDataCache[pointIndex] = crossSectionPolyData

    # Finally create/update the model node
    if self.crossSectionModelNode is None:
      self.crossSectionModelNode = slicer.modules.models.logic().AddModel(crossSectionPolyData)
      name = "Cross section for "
      if (self.lumenSurfaceNode.GetClassName() == "vtkMRMLSegmentationNode"):
        name += self.lumenSurfaceNode.GetSegmentation().GetSegment(self.currentSegmentID).GetName()
      else:
        name += self.lumenSurfaceNode.GetName()
      self.crossSectionModelNode.SetName(name)
      crossSectionModelDisplayNode = self.crossSectionModelNode.GetDisplayNode()
      crossSectionModelDisplayNode.SetColor(self.crossSectionColor)
      crossSectionModelDisplayNode.SetOpacity(0.75)
    else:
      self.crossSectionModelNode.SetAndObservePolyData(crossSectionPolyData)

  def getCrossSectionArea(self, pointIndex):
    """Get the cross-section surface area"""

    if self.lumenSurfaceNode is None:
      return 0.0

    if pointIndex in self.crossSectionPolyDataCache:
      # found polydata cached
      crossSectionPolyData = self.crossSectionPolyDataCache[pointIndex]
    else:
      # cross-section is not found in the cache, compute it now and store in cache
      crossSectionPolyData = self.computeCrossSectionPolydata(pointIndex)
      self.crossSectionPolyDataCache[pointIndex] = crossSectionPolyData

    crossSectionProperties = vtk.vtkMassProperties()
    crossSectionProperties.SetInputData(crossSectionPolyData)
    currentSurfaceArea = crossSectionProperties.GetSurfaceArea()

    return currentSurfaceArea

  def getPositionMaximumInscribedSphereRadius(self, pointIndex):
    if not self.isCenterlineRadiusAvailable:
      raise ValueError("Maximim inscribed sphere radius is not available")
    position = np.zeros(3)
    if self.inputCenterlineNode.IsTypeOf("vtkMRMLModelNode"):
      positionLocal = slicer.util.arrayFromModelPoints(self.inputCenterlineNode)[pointIndex]
      self.inputCenterlineNode.TransformPointToWorld(positionLocal, position)
      radius = slicer.util.arrayFromModelPointData(self.inputCenterlineNode, 'Radius')[pointIndex]
    else:
      self.inputCenterlineNode.GetCurveWorld().GetPoints().GetPoint(pointIndex, position)
      # Get curve point radius by interpolating control point measurements
      # Need to compute manually until this method becomes available:
      #  radius = self.inputCenterlineNode.GetMeasurement('Radius').GetCurvePointValue(pointIndex)
      controlPointFloatIndex = self.inputCenterlineNode.GetCurveWorld().GetPointData().GetArray('PedigreeIDs').GetValue(pointIndex)
      controlPointIndexA = int(controlPointFloatIndex)
      controlPointIndexB = controlPointIndexA + 1
      controlPointRadiusValues = self.inputCenterlineNode.GetMeasurement('Radius').GetControlPointValues()
      radiusA = controlPointRadiusValues.GetValue(controlPointIndexA)
      radiusB = controlPointRadiusValues.GetValue(controlPointIndexB)
      radius = radiusA * (controlPointFloatIndex - controlPointIndexA) + radiusB * (controlPointIndexB - controlPointFloatIndex)
    return position, radius

  def updateAllCrossSectionsModel(self):
    # TODO: make this method create a merged model of all cross-sections in the cache
    pass

    # # precompute all lumen surfaces
    # if self.logic.lumenSurfaceNode:
    #   for pointIndex in range(numberOfPoints):
    #     self.logic.getCrossSectionArea(pointIndex)

    # if self.allCrossSectionsModelNode is not None:
    #     self.allCrossSectionsModelNode.GetDisplayNode().SetVisibility(self.showCrossSection)
    # # Don't append again if already done at a centerline point
    # for i in range(self.crossSectionsPointIndices.GetNumberOfValues()):
    #     if self.crossSectionsPointIndices.GetValue(i) == pointIndex:
    #         return
    
    # # Work on a copy of the input polydata for the stack model
    # islandPolyDataCopy = vtk.vtkPolyData()
    # islandPolyDataCopy.DeepCopy(islandPolyData)
    # # Set same scalar value to each point of polydata.
    # intArray = vtk.vtkIntArray()
    # intArray.SetName("PointIndex")
    # for i in range(islandPolyDataCopy.GetNumberOfPoints()):
    #     intArray.InsertNextValue(int(pointIndex))
    # islandPolyDataCopy.GetPointData().SetScalars(intArray)
    # islandPolyDataCopy.Modified()
    
    # self.appendedPolyData.AddInputData(islandPolyDataCopy)
    # self.appendedPolyData.Update()
    
    # # Remember where it's already done
    # self.crossSectionsPointIndices.InsertNextValue(int(pointIndex))
    
    # # Remove stack model and observation
    # if self.allCrossSectionsModelNode is not None:
    #     # Don't react if we remove it from scene on our own
    #     slicer.mrmlScene.RemoveObserver(self.sceneNodeRemovedObservation)
    #     slicer.mrmlScene.RemoveNode(self.allCrossSectionsModelNode)
    # # Create a new stack model
    # self.crossSectionsModelNode = slicer.modules.models.logic().AddModel(self.appendedPolyData.GetOutputPort())
    # separator = " for " if surfaceName else ""
    # self.crossSectionsModelNode.SetName("Cross-section stack" + separator + surfaceName)
    # self.crossSectionsModelNode.GetDisplayNode().SetVisibility(self.showCrossSection)
    # # Remember stack model by id
    # self.crossSectionsModelNodeId = self.crossSectionsModelNode.GetID()
    # # Add an observation if stack model is deleted by the user
    # self.sceneNodeRemovedObservation = slicer.mrmlScene.AddObserver(slicer.vtkMRMLScene.NodeRemovedEvent, self.onSceneNodeRemoved)

  def updateMaximumInscribedSphereModel(self, value):
    pointIndex = int(value)

    position, radius = self.getPositionMaximumInscribedSphereRadius(pointIndex)

    sphere = vtk.vtkSphereSource()
    sphere.SetRadius(radius)
    sphere.SetCenter(position)
    sphere.SetPhiResolution(30)
    sphere.SetThetaResolution(30)
    sphere.Update()

    if self.maximumInscribedSphereModelNode:
      self.maximumInscribedSphereModelNode.SetAndObservePolyData(sphere.GetOutput())
    else:
      self.maximumInscribedSphereModelNode = slicer.modules.models.logic().AddModel(sphere.GetOutput())
      # Set model visibility
      sphereModelDisplayNode = self.maximumInscribedSphereModelNode.GetDisplayNode()
      sphereModelDisplayNode.SetOpacity(0.33)
      sphereModelDisplayNode.SetVisibility(self.showMaximumInscribedSphere)
      sphereModelDisplayNode.SetVisibility2D(True)
      sphereModelDisplayNode.SetVisibility3D(True)
      # Set model name
      name = "Maximum inscribed sphere"
      if self.lumenSurfaceNode:
        if (self.lumenSurfaceNode.GetClassName() == "vtkMRMLSegmentationNode"):
            name += " for " + self.lumenSurfaceNode.GetSegmentation().GetSegment(self.currentSegmentID).GetName()
        else:
            name += " for " + self.lumenSurfaceNode.GetName()
      self.maximumInscribedSphereModelNode.SetName(name)
      # Set sphere color
      sphereModelDisplayNode.SetColor(self.maximumInscribedSphereColor[0], self.maximumInscribedSphereColor[1], self.maximumInscribedSphereColor[2])

  # This information is added because it is easily available.
  # How useful is it ?
  # In any case, it is the slice orientation in the RAS coordinate system.
  def getSliceOrientation(self, sliceNode):
    sliceToRAS = sliceNode.GetSliceToRAS()
    orient = np.zeros(3)
    vtk.vtkTransform().GetOrientation(orient, sliceToRAS)
    return orient
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
