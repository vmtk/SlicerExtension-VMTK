import os
import unittest
import logging
import vtk, qt, ctk, slicer
import numpy as np
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

"""
  CrossSectionAnalysis : renamed from CenterlineMetrics, and merged with former deprecated CrossSectionAnalysis module.
  This file was originally derived from LineProfile.py.
  Many more features have been added since.
"""

class CrossSectionAnalysis(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Cross-section analysis"
    self.parent.categories = ["Vascular Modeling Toolkit"]
    self.parent.dependencies = []
    self.parent.contributors = ["SET (Surgeon) (Hobbyist developer)"]
    self.parent.helpText = """
This module describes cross-sections along a VMTK centerline model, a VMTK centerline markups curve or an arbitrary markups curve. Documentation is available
    <a href="https://github.com/chir-set/CenterlineMetrics">here</a>.
"""  
    self.parent.acknowledgementText = """
This file was originally developed by SET. Many thanks to Andras Lasso for sanitizing the code and UI, and for guidance throughout.
"""  # TODO: replace with organization, grant and thanks.

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

  def setup(self):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer)
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/CrossSectionAnalysis.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)
    
    # Add vertical spacer
    self.layout.addStretch(1) 

    # Set scene in MRML widgets. Make sure that in Qt designer
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    self.logic = CrossSectionAnalysisLogic()
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
    self.ui.orthogonalReformatInSliceNodeCheckBox.setIcon(qt.QIcon(':/Icons/MouseRotateMode.png'))

    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
    
    # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
    # (in the selected parameter node).
    self.ui.inputCenterlineSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.segmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.segmentSelector.connect("currentSegmentChanged(QString)", self.updateParameterNodeFromGUI)
    self.ui.outputTableSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.outputPlotSeriesSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.sliceViewSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.moveToPointSliderWidget.connect("valueChanged(double)", self.updateParameterNodeFromGUI)
    self.ui.radioRAS.connect("clicked()", self.updateParameterNodeFromGUI)
    self.ui.radioLPS.connect("clicked()", self.updateParameterNodeFromGUI)
    self.ui.distinctColumnsCheckBox.connect("clicked()", self.updateParameterNodeFromGUI)
    self.ui.jumpCentredInSliceNodeCheckBox.connect("clicked()", self.updateParameterNodeFromGUI)
    self.ui.orthogonalReformatInSliceNodeCheckBox.connect("clicked()", self.updateParameterNodeFromGUI)
    
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
    self.ui.useCurrentPointAsOriginButton.connect("clicked()", self.onUseCurrentPointAsOrigin)
    self.ui.goToOriginButton.connect("clicked()", self.onGoToOriginPoint)
    self.ui.moveToMinimumPushButton.connect("clicked()", self.moveSliceViewToMinimumMISDiameter)
    self.ui.moveToMaximumPushButton.connect("clicked()", self.moveSliceViewToMaximumMISDiameter)
    self.ui.toggleTableLayoutButton.connect("clicked()", self.toggleTableLayout)
    self.ui.togglePlotLayoutButton.connect("clicked()", self.togglePlotLayout)
    self.ui.segmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelectSegmentationNodes)
    self.ui.segmentSelector.connect("currentSegmentChanged(QString)", self.onSelectSegmentationNodes)
    self.ui.showCrossSectionButton.connect("clicked()", self.onShowCrossSection)
    self.ui.showMISDiameterPushButton.connect("clicked()", self.onShowMaximumInscribedSphere)
    self.ui.sliceViewSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelectSliceNode)
    self.ui.torsionSliderWidget.connect("valueChanged(double)", self.onTorsionSliderWidget)

    # Refresh Apply button state
    self.onSelectNode()
    
  def cleanup(self):
    """
    Called when the application closes and the module widget is destroyed.
    """
    self.removeObservers()
  
  def enter(self):
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
    # Clean up logic variables too.
    self.logic.initMemberVariables()
      
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
    self.ui.inputCenterlineSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputCenterline"))
    self.ui.segmentationSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputSegmentation"))
    self.ui.segmentSelector.setCurrentSegmentID(self._parameterNode.GetParameter("InputSegment"))
    self.ui.outputTableSelector.setCurrentNode(self._parameterNode.GetNodeReference("OutputTable"))
    self.ui.outputPlotSeriesSelector.setCurrentNode(self._parameterNode.GetNodeReference("OutputPlotSeries"))
    self.ui.sliceViewSelector.setCurrentNode(self._parameterNode.GetNodeReference("SliceNode"))
    if self._parameterNode.GetParameter("UseLPS") == "True":
        self.ui.radioLPS.setChecked(True)
        self.onRadioLPS()
    else:
        self.ui.radioRAS.setChecked(True)
        self.onRadioRAS()
    self.ui.distinctColumnsCheckBox.setChecked (self._parameterNode.GetParameter("DistinctColumns") == "True")
    self.ui.jumpCentredInSliceNodeCheckBox.setChecked (self._parameterNode.GetParameter("CentreInSliceView") == "True")
    self.ui.orthogonalReformatInSliceNodeCheckBox.setChecked (self._parameterNode.GetParameter("OrthogonalReformat") == "True")
    self.ui.showMISDiameterPushButton.setChecked (self._parameterNode.GetParameter("ShowMISModel") == "True")
    
    # The check events are not triggered by above.
    self.onDistinctCoordinatesCheckBox()
    self.onJumpCentredInSliceNodeCheckBox()
    self.onOrthogonalReformatInSliceNodeCheckBox()
    
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
    
    self._parameterNode.SetNodeReferenceID("InputCenterline", self.ui.inputCenterlineSelector.currentNodeID)
    self._parameterNode.SetNodeReferenceID("InputSegmentation", self.ui.segmentationSelector.currentNodeID)
    self._parameterNode.SetParameter("InputSegment", self.ui.segmentSelector.currentSegmentID())
    self._parameterNode.SetNodeReferenceID("OutputTable", self.ui.outputTableSelector.currentNodeID)
    self._parameterNode.SetNodeReferenceID("OutputPlotSeries", self.ui.outputPlotSeriesSelector.currentNodeID)
    self._parameterNode.SetNodeReferenceID("SliceNode", self.ui.sliceViewSelector.currentNodeID)
    self._parameterNode.SetParameter("UseLPS", "True" if (self.ui.radioLPS.isChecked()) else "False")
    self._parameterNode.SetParameter("DistinctColumns", "True" if (self.ui.distinctColumnsCheckBox.isChecked()) else "False")
    self._parameterNode.SetParameter("CentreInSliceView", "True" if (self.ui.jumpCentredInSliceNodeCheckBox.isChecked()) else "False")
    self._parameterNode.SetParameter("OrthogonalReformat", "True" if (self.ui.orthogonalReformatInSliceNodeCheckBox.isChecked()) else "False")
    self._parameterNode.SetParameter("ShowMISModel", "True" if (self.ui.showMISDiameterPushButton.isChecked()) else "False")
    
    self._parameterNode.EndModify(wasModified)
    
  def onSelectNode(self):
    self.logic.setInputCenterlineNode(self.ui.inputCenterlineSelector.currentNode())
    self.ui.applyButton.enabled = self.logic.isInputCenterlineValid()
    self.logic.setOutputTableNode(self.ui.outputTableSelector.currentNode())
    self.logic.setOutputPlotSeriesNode(self.ui.outputPlotSeriesSelector.currentNode())
    self.ui.moveToPointSliderWidget.setValue(0)
    self.resetMoveToPointSliderWidget()
    self.clearMetrics()

  def createOutputNodes(self):
    if self.logic.isCenterlineRadiusAvailable(False):
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

    isCenterlineRadiusAvailable = self.logic.isCenterlineRadiusAvailable(False)
    isCenterlineRadiusAvailableInTable = self.logic.isCenterlineRadiusAvailable(True)
    self.ui.toggleTableLayoutButton.visible = isCenterlineRadiusAvailableInTable and (self.logic.outputTableNode is not None)
    self.ui.togglePlotLayoutButton.visible = isCenterlineRadiusAvailableInTable and (self.logic.outputPlotSeriesNode is not None)
    self.ui.moveToMinimumPushButton.enabled = isCenterlineRadiusAvailable
    self.ui.moveToMaximumPushButton.enabled = isCenterlineRadiusAvailable
    self.ui.showMISDiameterPushButton.enabled = isCenterlineRadiusAvailable

    self.ui.showCrossSectionButton.enabled = self.logic.lumenSurfaceNode is not None

    numberOfPoints = self.logic.getNumberOfPoints()
    # Prevent going to the endpoint (direction computation is only implemented for models with forward difference)
    numberOfPoints -= 1

    self.ui.moveToPointSliderWidget.maximum = numberOfPoints - 1
    self.updateMeasurements()
    self.ui.torsionSliderWidget.value = 0.0
    sliceNode = self.ui.sliceViewSelector.currentNode()
    if sliceNode:
        sliceNode.SetAttribute("currentTilt", "0.0")

  def onRadioLPS(self):
    self.logic.coordinateSystemColumnRAS = False
  
  def onRadioRAS(self):
    self.logic.coordinateSystemColumnRAS = True
    
  def onDistinctCoordinatesCheckBox(self):
    self.logic.coordinateSystemColumnSingle = not self.ui.distinctColumnsCheckBox.checked
  
  def onJumpCentredInSliceNodeCheckBox(self):
    self.logic.jumpCentredInSliceNode = self.ui.jumpCentredInSliceNodeCheckBox.checked
    if self.ui.sliceViewSelector.currentNode():
        self.setCurrentPointIndex(self.ui.moveToPointSliderWidget.value)
        self.updateSliceViewOrientationMetrics()
  
  def onOrthogonalReformatInSliceNodeCheckBox(self):
    self.logic.orthogonalReformatInSliceNode = self.ui.orthogonalReformatInSliceNodeCheckBox.checked
    self.ui.torsionSliderWidget.value = 0.0
    sliceNode = self.ui.sliceViewSelector.currentNode()
    if sliceNode:
        self.setCurrentPointIndex(self.ui.moveToPointSliderWidget.value)
        self.updateSliceViewOrientationMetrics()
        if not self.ui.orthogonalReformatInSliceNodeCheckBox.checked:
            sliceNode.SetAttribute("currentTilt", "0.0")

  def onUseCurrentPointAsOrigin(self):
    self.logic.relativeOriginPointIndex = int(self.ui.moveToPointSliderWidget.value)
    self.updateMeasurements()
    
    # Update table, to show distances relative to new origin.
    if self.logic.outputTableNode:
        self.logic.updateOutputTable(self.logic.inputCenterlineNode, self.logic.outputTableNode)
        # Update plot view. Else X-axis always starts at 0, truncating the graph.
        slicer.app.layoutManager().plotWidget(0).plotView().fitToContent()

  def onGoToOriginPoint(self):
    self.ui.moveToPointSliderWidget.value = self.logic.relativeOriginPointIndex

  def onSelectSliceNode(self, sliceNode):
    self.logic.selectSliceNode(sliceNode)
    self.updateSliceViewOrientationMetrics()
    if sliceNode is None:
        self.ui.orientationValueLabel.setText("")
    else:
        sliceNode.SetAttribute("currentTilt", "0.0")
    self.ui.torsionSliderWidget.value = 0.0
    
  def updateUIWithMetrics(self, value):
    pointIndex = int(value)

    coordinateArray = self.logic.getCurvePointPositionAtIndex(value)
    self.ui.coordinatesValueLabel.setText(f"R {round(coordinateArray[0], 1)}, A {round(coordinateArray[1], 1)}, S {round(coordinateArray[2], 1)}")

    tableNode = self.logic.outputTableNode
    if tableNode:
      # Use precomputed values
      distanceStr = self.logic.getUnitNodeDisplayString(self.logic.calculateRelativeDistance(value), "length").strip()
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
        if self.logic.relativeOriginPointIndex <= pointIndex:
            distanceFromOrigin = self.logic.inputCenterlineNode.GetCurveLengthBetweenStartEndPointsWorld(self.logic.relativeOriginPointIndex, pointIndex)
        else:
            distanceFromOrigin = -self.logic.inputCenterlineNode.GetCurveLengthBetweenStartEndPointsWorld(pointIndex, self.logic.relativeOriginPointIndex)
        distanceStr = self.logic.getUnitNodeDisplayString(distanceFromOrigin, "length").strip()
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
        orientation = "R " + str(round(orient[0], 1)) + chr(0xb0) + ","
        orientation += " A " + str(round(orient[1], 1)) + chr(0xb0) + ","
        orientation += " S " + str(round(orient[2], 1)) + chr(0xb0)
        self.ui.orientationValueLabel.setText(orientation)

  def showRelativeDistance(self):
    if not self.logic.outputTableNode:
        return
    value = self.ui.moveToPointSliderWidget.value
    distanceStr = self.logic.getUnitNodeDisplayString(self.logic.calculateRelativeDistance(value), "length").strip()
    self.ui.distanceValueLabel.setText(distanceStr)

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
    self.ui.torsionSliderWidget.setValue(0.0)

  def moveSliceViewToMinimumMISDiameter(self):
    point = self.logic.getExtremeMISDiameterPoint(False)
    if point == -1:
        return
    self.ui.moveToPointSliderWidget.setValue(point)
  
  def moveSliceViewToMaximumMISDiameter(self):
    point = self.logic.getExtremeMISDiameterPoint(True)
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

  def onTorsionSliderWidget(self):
    sliceNode = self.ui.sliceViewSelector.currentNode()
    if sliceNode is None:
        return
    angle = self.ui.torsionSliderWidget.value
    self.logic.rotateAroundZ(sliceNode, angle)

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
    ScriptedLoadableModuleLogic.__init__(self)
    self.initMemberVariables()

  def initMemberVariables(self):
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
    self.relativeOriginPointIndex = 0

  @property
  def relativeOriginPointIndex(self):
    originPointIndexStr = self.getParameterNode().GetParameter("originPointIndex")
    originPointIndex = int(float(originPointIndexStr)) if originPointIndexStr else 0
    return originPointIndex

  @relativeOriginPointIndex.setter
  def relativeOriginPointIndex(self, originPointIndex):
    self.getParameterNode().SetParameter("originPointIndex", str(originPointIndex))

  def setDefaultParameters(self, parameterNode):
    """
    Initialize parameter node with default settings.
    """
    pass
    
  def resetCrossSections(self):
    self.crossSectionPolyDataCache = {}

  def setInputCenterlineNode(self, centerlineNode):
    if self.inputCenterlineNode == centerlineNode:
      return
    self.inputCenterlineNode = centerlineNode
    self.resetCrossSections()
    self.relativeOriginPointIndex = 0

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

  def isCenterlineRadiusAvailable(self, queryTable = True):
    if not self.inputCenterlineNode:
      return False
    if self.inputCenterlineNode.IsTypeOf("vtkMRMLModelNode"):
        return self.inputCenterlineNode.HasPointScalarName("Radius")
    else:
        radiusMeasurement = self.inputCenterlineNode.GetMeasurement('Radius')
        if not radiusMeasurement:
          forcedInRadius = None
          if self.outputTableNode and queryTable:
            forcedInRadius = self.outputTableNode.GetAttribute("forcedInZeroRadius")
          return (forcedInRadius is not None)
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
    misDiameterArray = self.getArrayFromTable(outputTable, MIS_DIAMETER_ARRAY_NAME)
    ceDiameterArray = self.getArrayFromTable(outputTable, CE_DIAMETER_ARRAY_NAME)
    crossSectionAreaArray = self.getArrayFromTable(outputTable, CROSS_SECTION_AREA_ARRAY_NAME)
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
        radiusMeasurement = inputCenterline.GetMeasurement("Radius")
        controlPointRadiusValues = vtk.vtkDoubleArray()
        if not radiusMeasurement:
            controlPointRadiusValues.SetNumberOfValues(numberOfPoints)
            controlPointRadiusValues.Fill(0.0)
            outputTable.SetAttribute("forcedInZeroRadius", "True")
        else :
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
    relArray = vtk.vtkDoubleArray()
    self.updateCumulativeDistancesToRelativeOrigin(cumArray, relArray)
    for i, radius in enumerate(radii):
        distanceArray.SetValue(i, relArray.GetValue(i))
        misDiameterArray.SetValue(i, radius * 2)
        
        if (inputCenterline.IsTypeOf("vtkMRMLModelNode")):
            # Exclude last point where area cannot be computed
            if i < (len(radii) - 1):
                crossSectionArea = self.getCrossSectionArea(i)
                ceDiameter = (np.sqrt(crossSectionArea / np.pi)) * 2
                crossSectionAreaArray.SetValue(i, crossSectionArea)
                ceDiameterArray.SetValue(i, ceDiameter)
            else:
                crossSectionAreaArray.SetValue(i, 0.0)
                ceDiameterArray.SetValue(i, 0.0)
        else:
            crossSectionArea = self.getCrossSectionArea(i)
            ceDiameter = (np.sqrt(crossSectionArea / np.pi)) * 2
            crossSectionAreaArray.SetValue(i, crossSectionArea)
            ceDiameterArray.SetValue(i, ceDiameter)
        
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
    misDiameterArray.Modified()
    crossSectionAreaArray.Modified()
    ceDiameterArray.Modified()
    outputTable.GetTable().Modified()

  def updatePlot(self, outputPlotSeries, outputTable, name=None):

    # Create plot
    if name:
      outputPlotSeries.SetName(name)
    outputPlotSeries.SetAndObserveTableNodeID(outputTable.GetID())
    outputPlotSeries.SetXColumnName(DISTANCE_ARRAY_NAME)
    outputPlotSeries.SetYColumnName(MIS_DIAMETER_ARRAY_NAME)
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
      self.plotChartNode.SetYAxisTitle(MIS_DIAMETER_ARRAY_NAME+" (mm)")
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
  
  def updateCumulativeDistancesToRelativeOrigin(self, cumArray, relArray):
    distanceAtRelativeOrigin = cumArray.GetValue(self.relativeOriginPointIndex)
    numberOfValues = cumArray.GetNumberOfValues()
    relArray.SetNumberOfValues(numberOfValues)
    for i in range(numberOfValues):
      relArray.SetValue(i, cumArray.GetValue(i) - distanceAtRelativeOrigin)  

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
    """Move the selected slice view to a point of the centerline, optionally centering on the point, and with optional orthogonal reformat.
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
    else:
        sliceNode.SetOrientationToDefault()

  def getExtremeMISDiameterPoint(self, boolMaximum):
    """Convenience function to get the point of minimum or maximum diameter.
    Is useful for arterial stenosis (minimum) or aneurysm (maximum).
    """
    if self.outputTableNode is None:
        return -1
    misDiameterArray = self.outputTableNode.GetTable().GetColumnByName(MIS_DIAMETER_ARRAY_NAME)
    # GetRange or GetValueRange ?
    misDiameterRange = misDiameterArray.GetRange()
    target = -1
    # Until we find a smart function, kind of vtkDoubleArray::Find(value)
    for i in range(misDiameterArray.GetNumberOfValues()):
        if misDiameterArray.GetValue(i) == misDiameterRange[1 if boolMaximum else 0]:
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
      self.lumenSurfaceNode.CreateClosedSurfaceRepresentation()
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
      raise ValueError("Maximum inscribed sphere radius is not available")
    position = np.zeros(3)
    if self.inputCenterlineNode.IsTypeOf("vtkMRMLModelNode"):
      positionLocal = slicer.util.arrayFromModelPoints(self.inputCenterlineNode)[pointIndex]
      self.inputCenterlineNode.TransformPointToWorld(positionLocal, position)
      radius = slicer.util.arrayFromModelPointData(self.inputCenterlineNode, 'Radius')[pointIndex]
    else:
      self.inputCenterlineNode.GetCurveWorld().GetPoints().GetPoint(pointIndex, position)
      radiusMeasurement = self.inputCenterlineNode.GetMeasurement('Radius')
      if not radiusMeasurement:
          return position, 0.0
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

  # Calculate distance from point and the relative origin
  def calculateRelativeDistance(self, pointIndex):
    if self.outputTableNode is None:
        return 0.0
    distanceArray = self.outputTableNode.GetTable().GetColumnByName(DISTANCE_ARRAY_NAME)
    if not distanceArray:
        return 0.0
    # Distance of the relative origin from start of path
    relativeOriginPointIndex = int(self.relativeOriginPointIndex)
    if relativeOriginPointIndex >= distanceArray.GetNumberOfValues():
      relativeOriginPointIndex = distanceArray.GetNumberOfValues()
    relativeOriginDistance = distanceArray.GetValue(relativeOriginPointIndex)
    # Distance of point from start of path
    distanceFromStart = distanceArray.GetValue(int(pointIndex))
    return distanceFromStart - relativeOriginDistance

  """
  Rotate slice view around it's Z-axis.
  It is relative to the previous rotation, stored as a slice node attribute.
  The view is tilted by the difference between the requested angle from the slider and the buffered angle.
  The buffered angle may not always start at 0.0.
  """
  def rotateAroundZ(self, sliceNode, angle):
    if sliceNode is None:
        return;
    currentTilt = 0.0
    if sliceNode.GetAttribute("currentTilt"):
        currentTilt = float(sliceNode.GetAttribute("currentTilt"))
    finalAngle = angle - currentTilt
    SliceToRAS = sliceNode.GetSliceToRAS()
    transform=vtk.vtkTransform()
    transform.SetMatrix(SliceToRAS)
    transform.RotateZ(finalAngle)
    SliceToRAS.DeepCopy(transform.GetMatrix())
    sliceNode.UpdateMatrices()
    sliceNode.SetAttribute("currentTilt", str(angle))
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
    slicer.mrmlScene.Clear(0)

  def runTest(self):
    """
    """

  def test_CrossSectionAnalysis1(self):
    """
    """

DISTANCE_ARRAY_NAME = "Distance"
MIS_DIAMETER_ARRAY_NAME = "Diameter (MIS)"
CE_DIAMETER_ARRAY_NAME = "Diameter (CE)"
CROSS_SECTION_AREA_ARRAY_NAME = "Cross-section area"

