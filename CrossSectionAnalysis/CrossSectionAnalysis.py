import os
import unittest
import logging
import vtk, qt, ctk, slicer
from slicer.i18n import tr as _
from slicer.i18n import translate

import numpy as np
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

"""
  CrossSectionAnalysis: renamed from CenterlineMetrics, and merged with former deprecated CrossSectionAnalysis module.
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
    self.parent.contributors = ["Saleem Edah-Tally (Surgeon) (Hobbyist developer)", "Andras Lasso (PerkLab)"]
    self.parent.helpText = _("""
This module describes cross-sections along a VMTK centerline model, a VMTK centerline markups curve or an arbitrary markups curve. Documentation is available <a href="https://github.com/vmtk/SlicerExtension-VMTK/">here</a>.
""")
    self.parent.acknowledgementText = _("""
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
""")  # TODO: replace with organization, grant and thanks.

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
    self.ui.parameterSetSelector.addAttribute("vtkMRMLScriptedModuleNode", "ModuleName", self.moduleName)
    self.initializeParameterNode()

    # Track the polydata regions identified in the lumen surface.
    self._lumenRegions = []
    # The paint effect and the fast fix buttons must not be visible by default.
    self.ui.surfaceInformationPaintToolButton.setVisible(False)
    self.ui.surfaceInformationFastFixToolButton.setVisible(False)
    # Position the crosshair on a lumen region.
    self.crosshair=slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLCrosshairNode")

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
    self.ui.toolsTabWidget.setTabText(0, _("Regions"))
    self.ui.toolsTabWidget.setTabText(1, _("Coordinates"))
    self.ui.clipLumenToolButton.setVisible(False)

    layoutManager = slicer.app.layoutManager()
    if layoutManager is not None: # NOTE: We need the check because some tests can run without main window
      self.previousLayoutId = slicer.app.layoutManager().layout

    self.ui.jumpCentredInSliceNodeCheckBox.setIcon(qt.QIcon(':/Icons/ViewCenter.png'))
    self.ui.orthogonalReformatInSliceNodeCheckBox.setIcon(qt.QIcon(':/Icons/MouseRotateMode.png'))

    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    # Update parameter node if the user interacts with the widgets
    self.ui.inputCenterlineSelector.connect("currentNodeChanged(vtkMRMLNode*)", lambda node: self.setNodeReferenceInParameterNode(ROLE_INPUT_CENTERLINE, node))
    self.ui.segmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", lambda node: self.setNodeReferenceInParameterNode(ROLE_INPUT_SEGMENTATION, node))
    self.ui.outputTableSelector.connect("currentNodeChanged(vtkMRMLNode*)", lambda node: self.setNodeReferenceInParameterNode(ROLE_OUTPUT_TABLE, node))
    self.ui.outputPlotSeriesSelector.connect("currentNodeChanged(vtkMRMLNode*)", lambda node: self.setNodeReferenceInParameterNode(ROLE_OUTPUT_PLOT_SERIES, node))
    self.ui.axialSliceViewSelector.connect("currentNodeChanged(vtkMRMLNode*)", lambda node: self.setNodeReferenceInParameterNode(ROLE_AXIAL_SLICE_NODE, node))
    self.ui.longitudinalSliceViewSelector.connect("currentNodeChanged(vtkMRMLNode*)", lambda node: self.setNodeReferenceInParameterNode(ROLE_LONGITUDINAL_SLICE_NODE, node))
    self.ui.segmentSelector.connect("currentSegmentChanged(QString)", lambda value: self.setValueInParameterNode(ROLE_INPUT_SEGMENT_ID, value))
    self.ui.useCurrentPointAsOriginButton.connect("clicked()", lambda: self.setValueInParameterNode(ROLE_ORIGIN_POINT_INDEX, int(self.ui.moveToPointSliderWidget.value)))
    self.ui.radioRAS.connect("clicked()", lambda: self.setValueInParameterNode(ROLE_USE_LPS, False))
    self.ui.radioLPS.connect("clicked()", lambda: self.setValueInParameterNode(ROLE_USE_LPS, True))
    self.ui.distinctColumnsCheckBox.connect("toggled(bool)", lambda value: self.setValueInParameterNode(ROLE_USE_DISTINCT_COLUMLNS, "True" if value else "False"))
    self.ui.jumpCentredInSliceNodeCheckBox.connect("toggled(bool)", lambda value: self.setValueInParameterNode(ROLE_CENTRE_IN_SLICE_VIEW, "True" if value else "False"))
    self.ui.orthogonalReformatInSliceNodeCheckBox.connect("toggled(bool)", lambda value: self.setValueInParameterNode(ROLE_ORTHOGONAL_REFORMAT, "True" if value else "False"))
    self.ui.rotationSliderWidget.connect("valueChanged(double)", lambda value: self.setValueInParameterNode(ROLE_ROTATIONAL_ANGLE, value))
    self.ui.axialSpinSliderWidget.connect("valueChanged(double)", lambda value: self.setValueInParameterNode(ROLE_AXIAL_SPIN_ANGLE, value))
    self.ui.longitudinalSpinSliderWidget.connect("valueChanged(double)", lambda value: self.setValueInParameterNode(ROLE_LONGITUDINAL_SPIN_ANGLE, value))
    self.ui.showMISDiameterButton.connect("toggled(bool)", lambda value: self.setValueInParameterNode(ROLE_SHOW_MIS_MODEL, "True" if value else "False"))
    self.ui.showCrossSectionButton.connect("toggled(bool)", lambda value: self.setValueInParameterNode(ROLE_SHOW_CROSS_SECTION_MODEL, "True" if value else "False"))
    self.ui.axialSliceHorizontalFlipCheckBox.connect("clicked()", lambda: self.setValueInParameterNode(ROLE_AXIAL_HORIZONTAL_FLIP, str(self.ui.axialSliceHorizontalFlipCheckBox.isChecked())))
    self.ui.axialSliceVerticalFlipCheckBox.connect("clicked()", lambda : self.setValueInParameterNode(ROLE_AXIAL_VERTICAL_FLIP, str(self.ui.axialSliceVerticalFlipCheckBox.isChecked())))
    self.ui.surfaceInformationGoToToolButton.connect("toggled(bool)", lambda value: self.setValueInParameterNode(ROLE_GOTO_REGION, "True" if value else "False"))

    # connections
    self.ui.parameterSetSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.onParameterNodeChanged)
    self.ui.parameterSetUpdateUIToolButton.connect("clicked(bool)", self.onParameterSetUpdateUiClicked)
    self.ui.applyButton.connect('clicked(bool)', self.onApply)

    self.ui.inputCenterlineSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.setInputCenterlineNode)
    self.ui.segmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onInputSegmentationNode)
    self.ui.segmentSelector.connect("currentSegmentChanged(QString)", self.onInputSegmentationNode) # Need to perform the same tasks as with segmentationSelector.
    self.ui.outputPlotSeriesSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.resetOutput)
    self.ui.outputTableSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.resetOutput)

    self.ui.moveToPointSliderWidget.connect("valueChanged(double)", self.setCurrentPointIndex)
    self.ui.useCurrentPointAsOriginButton.connect("clicked()", self.onUseCurrentPointAsOrigin)
    self.ui.goToOriginButton.connect("clicked()", self.onGoToOriginPoint)
    self.ui.moveToMinimumMISDiameterButton.connect("clicked()", lambda: self.moveSliceViewToExtremeMeasurement(MIS_DIAMETER_ARRAY_NAME, False))
    self.ui.moveToMaximumMISDiameterButton.connect("clicked()", lambda: self.moveSliceViewToExtremeMeasurement(MIS_DIAMETER_ARRAY_NAME, True))
    self.ui.moveToMinimumAreaButton.connect("clicked()", lambda: self.moveSliceViewToExtremeMeasurement(CROSS_SECTION_AREA_ARRAY_NAME, False))
    self.ui.moveToMaximumAreaButton.connect("clicked()", lambda: self.moveSliceViewToExtremeMeasurement(CROSS_SECTION_AREA_ARRAY_NAME, True))
    self.ui.minWallSurfaceAreaButton.connect("clicked()", lambda: self.moveSliceViewToExtremeMeasurement(WALL_CROSS_SECTION_AREA_ARRAY_NAME, False))
    self.ui.maxWallSurfaceAreaButton.connect("clicked()", lambda: self.moveSliceViewToExtremeMeasurement(WALL_CROSS_SECTION_AREA_ARRAY_NAME, True))
    self.ui.toggleTableLayoutButton.connect("clicked()", self.toggleTableLayout)
    self.ui.togglePlotLayoutButton.connect("clicked()", self.togglePlotLayout)

    self.ui.outputPlotSeriesTypeComboBox.connect("currentIndexChanged(int)", self.setPlotSeriesType)
    self.ui.axialSliceHorizontalFlipCheckBox.connect("clicked()", self.setHorizontalFlip)
    self.ui.axialSliceVerticalFlipCheckBox.connect("clicked()", self.setVerticalFlip)
    self.ui.maxSurfaceAreaStenosisButton.connect("clicked()", self.moveSliceViewToMaximumSurfaceAreaStenosis)

    self.ui.surfaceInformationGetToolButton.connect("clicked()", self.onGetRegionsButton)
    self.ui.surfaceInformationSpinBox.connect("valueChanged(int)", self.onRegionSelected)
    self.ui.surfaceInformationGoToToolButton.connect("toggled(bool)", self.onSurfaceInformationGoToToggled)
    self.ui.surfaceInformationPaintToolButton.connect("toggled(bool)", self.onSurfaceInformationPaintToggled)
    self.ui.surfaceInformationFastFixToolButton.connect("clicked()", self.onSurfaceInformationFastFix)
    self.ui.clipLumenToolButton.connect("clicked()", self.createClippedLumen)

    # Ensure the combo is populated and restored when loading a saved scene.
    self.updatePlotOptions()
    # Refresh Apply button state
    self.updateGUIFromParameterNode()
    # Refresh wall result widgets
    self.updateWallLabelsVisibility()

  def initializeParameterNode(self):
    """
    Ensure parameter node exists and observed.
    """
    # Parameter node stores all user choices in parameter values, node selections, etc.
    # so that when the scene is saved and reloaded, these settings are restored.

    # The initial parameter node originates from logic and added to the parameter set node.
    # Other parameter nodes are created by the parameter set node and used here.
    if not self._parameterNode:
      self.setParameterNode(self.logic.getParameterNode())
      wasBlocked = self.ui.parameterSetSelector.blockSignals(True)
      self.ui.parameterSetSelector.setCurrentNode(self._parameterNode)
      self.ui.parameterSetSelector.blockSignals(wasBlocked)

  def onParameterNodeChanged(self, parameterNode):
    # Distinguish between a new and used parameter node.
    pointIndex = 0
    if parameterNode.HasParameter(ROLE_INITIALIZED):
      pointIndex = parameterNode.GetParameter(ROLE_BROWSE_POINT_INDEX)
    self.setParameterNode(parameterNode)
    self.updatePlotChartView(parameterNode)
    self.resetOutput()
    if parameterNode.HasParameter(ROLE_INITIALIZED):
      self.onApply(True)
      self.ui.moveToPointSliderWidget.setValue(float(pointIndex))

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
    self.ui.surfaceInformationPaintToolButton.setChecked(False)

  def onSceneStartClose(self, caller, event):
    """
    Called just before the scene is closed.
    """
    self.logic.initMemberVariables()
    self._lumenRegions.clear()
    self.ui.browseCollapsibleButton.collapsed = True
    # Parameter node will be reset, do not use it anymore
    self.setParameterNode(None)

  def onSceneEndClose(self, caller, event):
    """
    Called just after the scene is closed.
    """
    # Clean up logic variables first. Avoids some Python console errors.

  def setParameterNode(self, inputParameterNode):
    """
    Set and observe parameter node.
    Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
    """

    if inputParameterNode == self._parameterNode:
        # No change
        return

    # Unobserve previously selected parameter node and add an observer to the newly selected.
    # Changes of parameter node are observed so that whenever parameters are changed by a script or any other module
    # those are reflected immediately in the GUI.
    if self._parameterNode is not None:
      self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
    self._parameterNode = inputParameterNode
    if self._parameterNode is not None:
      self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
      # Do not set defaults each time.
      if not self._parameterNode.HasParameter(ROLE_INITIALIZED):
        self.logic.setDefaultParameters(self._parameterNode)
      else:
        # Initial GUI update
        # This comboBox would always set itself to the first item otherwise.
        wasBlocked = self.ui.outputPlotSeriesTypeComboBox.blockSignals(True)
        self.updateGUIFromParameterNode()
        self.ui.outputPlotSeriesTypeComboBox.blockSignals(wasBlocked)

  def resetOutput(self):
    # Only UI widgets, output tables and plot chart/series are left untouched.
    self.ui.moveToPointSliderWidget.setValue(0)
    self.resetMoveToPointSliderWidget()
    self.clearMetrics()
    self.ui.browseCollapsibleButton.collapsed = True

  def updatePlotChartNode(self, parameterNode):
    plotChartNode = parameterNode.GetNodeReference("PlotChartNode")
    if not plotChartNode:
      plotChartNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotChartNode")
      plotChartNode.SetName(parameterNode.GetName()) # Name in the parameter set combobox.
      parameterNode.SetNodeReferenceID("PlotChartNode", plotChartNode.GetID())
    self.logic.plotChartNode = plotChartNode

  def updatePlotChartView(self, parameterNode = None):
    if not slicer.app.layoutManager().plotWidget(0):
      return
    if self.logic.plotChartNode:
      slicer.app.layoutManager().plotWidget(0).mrmlPlotViewNode().SetPlotChartNodeID(self.logic.plotChartNode.GetID())
    if not slicer.app.layoutManager().plotWidget(0).visible:
      return
    if self.logic.outputPlotSeriesNode:
      self.logic.showPlot()

  def updateGUIFromParameterNode(self, caller=None, event=None):
    """
    This method is called whenever parameter node is changed.
    The module GUI is updated to show the current state of the parameter node.
    """

    if self._parameterNode is None or self._updatingGUIFromParameterNode:
      return

    # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
    self._updatingGUIFromParameterNode = True
    # Update the logic

    self.logic.setInputCenterlineNode(self._parameterNode.GetNodeReference(ROLE_INPUT_CENTERLINE))
    self.logic.setLumenSurface(self._parameterNode.GetNodeReference(ROLE_INPUT_SEGMENTATION), self._parameterNode.GetParameter(ROLE_INPUT_SEGMENT_ID))
    self.logic.setOutputTableNode(self._parameterNode.GetNodeReference(ROLE_OUTPUT_TABLE))
    self.logic.setOutputPlotSeriesNode(self._parameterNode.GetNodeReference(ROLE_OUTPUT_PLOT_SERIES))
    self.logic.coordinateSystemColumnSingle = self._parameterNode.GetParameter(ROLE_USE_DISTINCT_COLUMLNS) != "True"
    self.logic.coordinateSystemColumnRAS = self._parameterNode.GetParameter(ROLE_USE_LPS) != "True"
    self.logic.jumpCentredInSliceNode = self._parameterNode.GetParameter(ROLE_CENTRE_IN_SLICE_VIEW) == "True"
    self.logic.orthogonalReformatInSliceNode = self._parameterNode.GetParameter(ROLE_ORTHOGONAL_REFORMAT) == "True"
    self.logic.axialSliceNode = self._parameterNode.GetNodeReference(ROLE_AXIAL_SLICE_NODE)
    self.logic.longitudinalSliceNode = self._parameterNode.GetNodeReference(ROLE_LONGITUDINAL_SLICE_NODE)
    self.logic.rotationAngleDeg = float(self._parameterNode.GetParameter(ROLE_ROTATIONAL_ANGLE)) if self._parameterNode.GetParameter(ROLE_ROTATIONAL_ANGLE) else 0.0
    self.logic.axialSpinAngleDeg = float(self._parameterNode.GetParameter(ROLE_AXIAL_SPIN_ANGLE)) if self._parameterNode.GetParameter(ROLE_AXIAL_SPIN_ANGLE) else 0.0
    self.logic.longitudinalSpinAngleDeg = float(self._parameterNode.GetParameter(ROLE_LONGITUDINAL_SPIN_ANGLE)) if self._parameterNode.GetParameter(ROLE_LONGITUDINAL_SPIN_ANGLE) else 0.0
    self.logic.setShowMaximumInscribedSphereDiameter(self._parameterNode.GetParameter(ROLE_SHOW_MIS_MODEL) == "True")
    self.logic.setShowCrossSection(self._parameterNode.GetParameter(ROLE_SHOW_CROSS_SECTION_MODEL) == "True")
    self.logic.axialSliceHorizontalFlip = (self._parameterNode.GetParameter(ROLE_AXIAL_HORIZONTAL_FLIP) == "True") if self._parameterNode.GetParameter(ROLE_AXIAL_HORIZONTAL_FLIP) else False
    self.logic.axialSliceVerticalFlip = (self._parameterNode.GetParameter(ROLE_AXIAL_VERTICAL_FLIP) == "True") if self._parameterNode.GetParameter(ROLE_AXIAL_VERTICAL_FLIP) else False
    self.logic.relativeOriginPointIndex = int(self._parameterNode.GetParameter(ROLE_ORIGIN_POINT_INDEX)) if self._parameterNode.GetParameter(ROLE_ORIGIN_POINT_INDEX) else 0

    # Update node selectors and sliders

    self.ui.inputCenterlineSelector.setCurrentNode(self._parameterNode.GetNodeReference(ROLE_INPUT_CENTERLINE))
    self.ui.segmentationSelector.setCurrentNode(self._parameterNode.GetNodeReference(ROLE_INPUT_SEGMENTATION))
    self.ui.segmentSelector.setCurrentSegmentID(self._parameterNode.GetParameter(ROLE_INPUT_SEGMENT_ID))
    self.ui.outputTableSelector.setCurrentNode(self._parameterNode.GetNodeReference(ROLE_OUTPUT_TABLE))
    self.ui.outputPlotSeriesSelector.setCurrentNode(self._parameterNode.GetNodeReference(ROLE_OUTPUT_PLOT_SERIES))
    self.ui.axialSliceViewSelector.setCurrentNode(self._parameterNode.GetNodeReference(ROLE_AXIAL_SLICE_NODE))
    self.ui.longitudinalSliceViewSelector.setCurrentNode(self._parameterNode.GetNodeReference(ROLE_LONGITUDINAL_SLICE_NODE))
    if self._parameterNode.GetParameter(ROLE_USE_LPS) == "True":
        self.ui.radioLPS.setChecked(True)
    else:
        self.ui.radioRAS.setChecked(True)
    self.ui.distinctColumnsCheckBox.setChecked(not self.logic.coordinateSystemColumnSingle)
    self.ui.jumpCentredInSliceNodeCheckBox.setChecked(self.logic.jumpCentredInSliceNode)
    self.ui.orthogonalReformatInSliceNodeCheckBox.setChecked(self.logic.orthogonalReformatInSliceNode)
    self.ui.rotationSliderWidget.setValue(self.logic.rotationAngleDeg)
    self.ui.axialSpinSliderWidget.setValue(self.logic.axialSpinAngleDeg)
    self.ui.longitudinalSpinSliderWidget.setValue(self.logic.longitudinalSpinAngleDeg)
    self.ui.showMISDiameterButton.setChecked(self.logic.showMaximumInscribedSphere)
    self.ui.showCrossSectionButton.setChecked(self.logic.showCrossSection)
    self.ui.axialSliceHorizontalFlipCheckBox.setChecked(self.logic.axialSliceHorizontalFlip)
    self.ui.axialSliceVerticalFlipCheckBox.setChecked(self.logic.axialSliceVerticalFlip)

    itemIndex = self.ui.outputPlotSeriesTypeComboBox.findData(self._parameterNode.GetParameter(ROLE_OUTPUT_PLOT_SERIES_TYPE))
    self.ui.outputPlotSeriesTypeComboBox.setCurrentIndex(itemIndex)

    # Update button states

    self.ui.segmentSelector.setVisible(self.logic.lumenSurfaceNode is not None
      and self.logic.lumenSurfaceNode.IsTypeOf("vtkMRMLSegmentationNode"))

    self.ui.applyButton.enabled = self.logic.isInputCenterlineValid()

    reformatEnabled = self.ui.orthogonalReformatInSliceNodeCheckBox.isChecked()
    self.ui.axialSpinSliderWidget.setEnabled(reformatEnabled and self.ui.axialSliceViewSelector.currentNodeID)
    self.ui.rotationSliderWidget.setEnabled(reformatEnabled and self.ui.longitudinalSliceViewSelector.currentNodeID)
    self.ui.longitudinalSpinSliderWidget.setEnabled(reformatEnabled and self.ui.longitudinalSliceViewSelector.currentNodeID)

    self.ui.moveToMinimumAreaButton.enabled = self.logic.lumenSurfaceNode is not None
    self.ui.moveToMaximumAreaButton.enabled = self.logic.lumenSurfaceNode is not None
    self.ui.showCrossSectionButton.enabled = self.logic.lumenSurfaceNode is not None

    self.ui.surfaceInformationGoToToolButton.setChecked(self._parameterNode.GetParameter(ROLE_GOTO_REGION) == "True")

    # Update outputs
    self.updateMeasurements()

    self.updateClipButtonVisibility()

    # All the GUI updates are done
    self._updatingGUIFromParameterNode = False

  def setNodeReferenceInParameterNode(self, referenceRole, referencedNode):
    if self._parameterNode:
      self._parameterNode.SetNodeReferenceID(referenceRole, referencedNode.GetID() if referencedNode else None)

  def setValueInParameterNode(self, parameterName, value):
    if self._parameterNode:
      self._parameterNode.SetParameter(parameterName, str(value))

  def createOutputNodes(self):
    if not self.ui.outputTableSelector.currentNode():
      outputTableNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLTableNode")
      self.ui.outputTableSelector.setCurrentNode(outputTableNode)
    if not self.ui.outputPlotSeriesSelector.currentNode():
      outputPlotSeriesNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotSeriesNode")
      self.ui.outputPlotSeriesSelector.setCurrentNode(outputPlotSeriesNode)
    # Update/create the plot chart node in logic. There is no widget tracking the chart node.
    self.updatePlotChartNode(self._parameterNode)

  def onApply(self, replay = False):
    with slicer.util.tryWithErrorDisplay(_("Failed to compute results."), waitCursor=True):

      if not self.logic.isInputCenterlineValid():
        raise ValueError(_("Input is invalid."))

      if not replay:
        self.previousLayoutId = slicer.app.layoutManager().layout
        self.clearMetrics()
        self.createOutputNodes()
        self.logic.run()
        self.onGoToOriginPoint()

      tableHasData = (self.logic.outputTableNode and self.logic.outputTableNode.GetNumberOfRows())
      self.ui.browseCollapsibleButton.collapsed = (not tableHasData)

      isCenterlineRadiusAvailable = self.logic.isCenterlineRadiusAvailable()
      self.ui.toggleTableLayoutButton.visible = self.logic.outputTableNode is not None
      self.ui.togglePlotLayoutButton.visible = self.logic.outputPlotSeriesNode is not None
      self.ui.moveToMinimumMISDiameterButton.enabled = isCenterlineRadiusAvailable
      self.ui.moveToMaximumMISDiameterButton.enabled = isCenterlineRadiusAvailable
      self.ui.showMISDiameterButton.enabled = isCenterlineRadiusAvailable

      self.ui.moveToMinimumAreaButton.enabled = self.logic.lumenSurfaceNode is not None
      self.ui.moveToMaximumAreaButton.enabled = self.logic.lumenSurfaceNode is not None
      self.ui.showCrossSectionButton.enabled = self.logic.lumenSurfaceNode is not None

      if tableHasData:
        numberOfPoints = self.logic.getNumberOfPoints()
        ## Prevent going to the endpoint (direction computation is only implemented for models with forward difference)
        #numberOfPoints -= 1
        self.ui.moveToPointSliderWidget.maximum = numberOfPoints - 1
        self.updateMeasurements()
        self.updateWallLabelsVisibility()
      if self.logic.plotChartNode and self.logic.outputPlotSeriesNode:
        self.updatePlotChartView()

  def onParameterSetUpdateUiClicked(self):
    if not self._parameterNode:
      return

    inputSegmentation = self._parameterNode.GetNodeReference(ROLE_INPUT_SEGMENTATION)
    if (not inputSegmentation):
      logging.warning("Invalid segmentation.")
      return
    if (inputSegmentation.GetClassName() == "vtkMRMLModelNode"):
      return

    # Create segment editor object if needed.
    segmentEditorModuleWidget = slicer.util.getModuleWidget("SegmentEditor")
    seWidget = segmentEditorModuleWidget.editor
    seWidget.setSegmentationNode(inputSegmentation)
    # The segmentation sets its volume in the slice views.
    slicer.util.setSliceViewerLayers(fit = True)

  def onUseCurrentPointAsOrigin(self):
    slicer.app.setOverrideCursor(qt.Qt.WaitCursor)
    self.logic.relativeOriginPointIndex = int(self.ui.moveToPointSliderWidget.value)
    self.updateMeasurements()

    # Update table, to show distances relative to new origin.
    if self.logic.outputTableNode:
        self.logic.updateOutputTable(self.logic.inputCenterlineNode, self.logic.outputTableNode)
        # Update plot view. Else X-axis always starts at 0, truncating the graph.
        firstPlotWidget = slicer.app.layoutManager().plotWidget(0)
        # The plot widget may be None if no plot has ever been shown.
        # The wait cursor would persist, even if we show a plot and set
        # a new origin.
        if firstPlotWidget:
            firstPlotWidget.plotView().fitToContent()

    slicer.app.restoreOverrideCursor()

  def onGoToOriginPoint(self):
    self.ui.moveToPointSliderWidget.value = self.logic.relativeOriginPointIndex

  def updateUIWithMetrics(self, value):
    pointIndex = int(value)

    coordinateArray = self.logic.getCurvePointPositionAtIndex(value)
    self.ui.coordinatesValueLabel.setText(f"R {round(coordinateArray[0], 1)}, A {round(coordinateArray[1], 1)}, S {round(coordinateArray[2], 1)}")

    tableNode = self.logic.outputTableNode
    if tableNode:
      # Use precomputed values only.
      relativeDistance = self.logic.calculateRelativeDistance(value)
      distanceStr = self.logic.getUnitNodeDisplayString(relativeDistance, "length").strip()
      misDiameterVariant = tableNode.GetTable().GetValueByName(int(value), MIS_DIAMETER_ARRAY_NAME)
      misDiameter = misDiameterVariant.ToDouble() if misDiameterVariant.IsValid() else 0.0
      diameterStr = self.logic.getUnitNodeDisplayString(misDiameter, "length").strip() if misDiameter else ""
    else:
      relativeDistance = 0.0
      distanceStr = ""
      misDiameter = 0.0
      diameterStr = ""
    self.ui.distanceValueLabel.setText(distanceStr)
    self.ui.distanceValueLabel.setToolTip(str(relativeDistance))
    self.ui.diameterValueLabel.setText(diameterStr)
    self.ui.diameterValueLabel.setToolTip(misDiameter)

    # Cross-section area metrics

    surfaceArea = self.logic.getCrossSectionArea(pointIndex)
    if surfaceArea > 0.0:
      self.ui.surfaceAreaValueLabel.setText(self.logic.getUnitNodeDisplayString(surfaceArea, "area").strip())
      self.ui.surfaceAreaValueLabel.setToolTip(str(surfaceArea))
    else:
      self.ui.surfaceAreaValueLabel.setText(_("N/A (input lumen surface not specified)"))

    if surfaceArea > 0.0:
      derivedDiameterVariant = tableNode.GetTable().GetValueByName(int(value), CE_DIAMETER_ARRAY_NAME)
      derivedDiameter = derivedDiameterVariant.ToDouble() if derivedDiameterVariant.IsValid() else 0.0
      derivedDiameterStr = self.logic.getUnitNodeDisplayString(derivedDiameter, "length").strip() if derivedDiameter else ""

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
        derivedDiameterStr += _(" (MIS diameter {sign}").format(sign=diameterDifferenceSign)
        # Using str().strip() to remove a leading space
        derivedDiameterStr += self.logic.getUnitNodeDisplayString(abs(diameterDifference), "length").strip()
        derivedDiameterStr += f", {diameterDifferenceSign}{round(abs(diameterPercentDifference), 2)}%)"

      self.ui.derivedDiameterValueLabel.setText(derivedDiameterStr)
      self.ui.derivedDiameterValueLabel.setToolTip(str(derivedDiameter))
    else:
      self.ui.derivedDiameterValueLabel.setText("")
    # Orientation
    self.updateSliceViewOrientationMetrics()
    # Duplicated lumen metrics for single glance understanding.
    self.showPreComputedDoubleData(value, CE_DIAMETER_ARRAY_NAME, self.ui.lumenDiameterValueLabel, "length")
    self.showPreComputedDoubleData(value, CROSS_SECTION_AREA_ARRAY_NAME, self.ui.lumenSurfaceAreaValueLabel, "area")
    # Wall metrics
    self.showPreComputedDoubleData(value, WALL_DIAMETER_ARRAY_NAME, self.ui.wallDiameterValueLabel, "length")
    self.showPreComputedDoubleData(value, WALL_CROSS_SECTION_AREA_ARRAY_NAME, self.ui.wallSurfaceAreaValueLabel, "area")
    self.showPreComputedDoubleData(value, DIAMETER_STENOSIS_ARRAY_NAME, self.ui.diameterStenosisValueLabel, "%")
    self.showPreComputedDoubleData(value, SURFACE_AREA_STENOSIS_ARRAY_NAME, self.ui.surfaceAreaStenosisValueLabel, "%")

  def showPreComputedDoubleData(self, pointIndex, columnArrayName, uiWidget, category):
    if self.logic.outputTableNode is None:
      uiWidget.setText("")
      return

    dataVariant = self.logic.outputTableNode.GetTable().GetValueByName(int(pointIndex), columnArrayName)
    data = dataVariant.ToDouble() if dataVariant.IsValid() else 0.0
    if category == "length" or category == "area" or category == "volume":
      dataStr = self.logic.getUnitNodeDisplayString(data, category).strip() if data else ""
    elif category == "%":
      dataStr = f"{round(data, 2)} %"
    else:
      dataStr = str(data)
    uiWidget.setText(str(dataStr))
    uiWidget.setToolTip(str(data))

  def updateSliceViewOrientationMetrics(self):
    if self.ui.axialSliceViewSelector.currentNode():
        orient = self.logic.getSliceOrientation(self.ui.axialSliceViewSelector.currentNode())
        orientation = "R " + str(round(orient[0], 1)) + chr(0xb0) + ","
        orientation += " A " + str(round(orient[1], 1)) + chr(0xb0) + ","
        orientation += " S " + str(round(orient[2], 1)) + chr(0xb0)
        self.ui.orientationValueLabel.setText(orientation)
    else:
        self.ui.orientationValueLabel.setText("")

  def clearMetrics(self):
    self.ui.coordinatesValueLabel.setText("")
    self.ui.distanceValueLabel.setText("")
    self.ui.diameterValueLabel.setText("")
    self.ui.surfaceAreaValueLabel.setText("")
    self.ui.derivedDiameterValueLabel.setText("")
    self.ui.orientationValueLabel.setText("")
    self.ui.wallDiameterValueLabel.setText("")
    self.ui.wallSurfaceAreaValueLabel.setText("")
    self.ui.diameterStenosisValueLabel.setText("")
    self.ui.surfaceAreaStenosisValueLabel.setText("")

  def resetMoveToPointSliderWidget(self):
    slider = self.ui.moveToPointSliderWidget
    slider.minimum = 0
    slider.maximum = 0
    slider.setValue(0)

  def moveSliceViewToExtremeMeasurement(self, arrayName, max):
    point = self.logic.getExtremeMetricPoint(arrayName, max)
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

  def updateMeasurements(self):
    self.setCurrentPointIndex(self.ui.moveToPointSliderWidget.value)

  def setCurrentPointIndex(self, value):
    if not self.logic.isInputCenterlineValid():
      return
    self.setValueInParameterNode(ROLE_BROWSE_POINT_INDEX, value)
    pointIndex = int(value)

    # Update slice view position
    self.logic.updateSliceView(pointIndex)

    # Update maximum inscribed radius sphere model
    if self.logic.isCenterlineRadiusAvailable():
      self.logic.updateMaximumInscribedSphereModel(pointIndex)
    else:
      self.logic.hideMaximumInscribedSphere()

    # Update cross-section model
    if self.ui.showCrossSectionButton.checked and self.logic.lumenSurfaceNode:
      self.logic.updateCrossSection(pointIndex)
    else:
      self.logic.deleteCrossSection()

    self.updateUIWithMetrics(value)

  def setPlotSeriesType(self, type):
    self.setValueInParameterNode(ROLE_OUTPUT_PLOT_SERIES_TYPE, self.ui.outputPlotSeriesTypeComboBox.currentData)
    self.logic.setPlotSeriesType(self.ui.outputPlotSeriesTypeComboBox.currentData)

  def setHorizontalFlip(self):
    pointIndex = int(self.ui.moveToPointSliderWidget.value)
    self.logic.updateSliceView(pointIndex)

  def setVerticalFlip(self):
    pointIndex = int(self.ui.moveToPointSliderWidget.value)
    self.logic.updateSliceView(pointIndex)

  def setInputCenterlineNode(self, centerlineNode):
    if (centerlineNode is not None) and (centerlineNode.IsTypeOf("vtkMRMLMarkupsShapeNode")):
      if centerlineNode.GetShapeName() != slicer.vtkMRMLMarkupsShapeNode.Tube:
        self.logic.showStatusMessage((_("Selected Shape node is not a Tube."),))
        self.ui.inputCenterlineSelector.setCurrentNode(None)
        self.logic.setInputCenterlineNode(None)
        return
    if (centerlineNode is not None) and (centerlineNode.IsTypeOf("vtkMRMLModelNode")):
      if not centerlineNode.HasPointScalarName("Radius"):
        self.logic.showStatusMessage((_("Selected model node does not have radius information."),))
        self.ui.inputCenterlineSelector.setCurrentNode(None)
        self.logic.setInputCenterlineNode(None)
        return
    self.resetOutput()
    # Notes:  updateGUIFromParameterNode() has already done this.
    self.logic.setInputCenterlineNode(centerlineNode)
    self.updatePlotOptions()
    self.updateWallLabelsVisibility()
    self.updateClipButtonVisibility()

  def onInputSegmentationNode(self):
    self.resetOutput()
    self.updatePlotOptions()
    self.updateWallLabelsVisibility()
    self.resetLumenRegions()
    self.updateClipButtonVisibility()

  # The output table columns vary according to the input types; this defines what can be plotted.
  def updatePlotOptions(self):
    comboBox = self.ui.outputPlotSeriesTypeComboBox
    wasBlocked = comboBox.blockSignals(True)
    comboBox.clear()

    if self.logic.isCenterlineRadiusAvailable():
        comboBox.addItem(_("MIS diameter"), MIS_DIAMETER)
    if self.logic.lumenSurfaceNode:
      comboBox.addItem(_("CE diameter"), CE_DIAMETER)
      comboBox.addItem(_("Cross-section area"), CROSS_SECTION_AREA)
    if self.logic.inputCenterlineNode and self.logic.inputCenterlineNode.IsTypeOf("vtkMRMLMarkupsShapeNode"):
      comboBox.addItem(_("Wall diameter"), WALL_CE_DIAMETER)
      comboBox.addItem(_("Wall cross-section area"), WALL_CROSS_SECTION_AREA)
      if self.logic.lumenSurfaceNode:
        comboBox.addItem(_("Stenosis by diameter (CE)"), DIAMETER_STENOSIS)
        comboBox.addItem(_("Stenosis by surface area"), SURFACE_AREA_STENOSIS)

    if (comboBox.count):
      comboBox.setCurrentIndex(0)

    comboBox.blockSignals(wasBlocked)
    if self._parameterNode:
      itemIndex = self.ui.outputPlotSeriesTypeComboBox.findData(self._parameterNode.GetParameter("OutputPlotSeriesType"))
      if itemIndex > -1:
        self.ui.outputPlotSeriesTypeComboBox.setCurrentIndex(itemIndex)

  def updateClipButtonVisibility(self):
    self.ui.clipLumenToolButton.setVisible(
      self.logic.inputCenterlineNode
      and self.logic.inputCenterlineNode.IsTypeOf("vtkMRMLMarkupsShapeNode")
      and self.logic.lumenSurfaceNode)

  def createClippedLumen(self):
    if not (
        self.logic.inputCenterlineNode
        and self.logic.inputCenterlineNode.IsTypeOf("vtkMRMLMarkupsShapeNode")
        and self.logic.lumenSurfaceNode):
      self.logic.showStatusMessage(_(("Invalid centerline or lumen surface: cannot clip the lumen.",)))
      return

    with slicer.util.tryWithErrorDisplay(_("Failed to clip lumen in tube."), waitCursor=True):
      clippedLumen = vtk.vtkPolyData()
      if not self.logic.clipLumenInTube(clippedLumen):
        self.logic.showStatusMessage(_(("Failed to clip the lumen inside the tube.",)))
        return

      clippedLumenName = slicer.mrmlScene.GenerateUniqueName("Clipped lumen")
      if self.logic.lumenSurfaceNode.IsTypeOf("vtkMRMLSegmentationNode"):
        segmentId = self.logic.lumenSurfaceNode.AddSegmentFromClosedSurfaceRepresentation(clippedLumen,
                                    clippedLumenName)
        self.ui.segmentSelector.setCurrentSegmentID(segmentId)
      else:
        clippedModel = slicer.modules.models.logic().AddModel(clippedLumen)
        clippedModel.SetName(clippedLumenName)
        self.ui.segmentationSelector.setCurrentNode(clippedModel)

  def updateWallLabelsVisibility(self):
    visibility = self.logic.inputCenterlineNode and self.logic.inputCenterlineNode.IsTypeOf("vtkMRMLMarkupsShapeNode")
    self.ui.wallGroupBox.setVisible(visibility) # Always show or hide
    # With or without a shape node as input centerline.
    self.ui.wallRowLabel.setVisible(visibility)
    self.ui.wallDiameterValueLabel.setVisible(visibility)
    self.ui.wallSurfaceAreaValueLabel.setVisible(visibility)
    self.ui.minWallSurfaceAreaButton.setVisible(visibility)
    self.ui.maxWallSurfaceAreaButton.setVisible(visibility)

    visibility = self.logic.inputCenterlineNode and self.logic.inputCenterlineNode.IsTypeOf("vtkMRMLMarkupsShapeNode") and self.logic.lumenSurfaceNode
    # With or without a segmentation or model node as input lumen.
    self.ui.lumenRowLabel.setVisible(visibility)
    self.ui.lumenDiameterValueLabel.setVisible(visibility)
    self.ui.lumenSurfaceAreaValueLabel.setVisible(visibility)
    self.ui.stenosisRowLabel.setVisible(visibility)
    self.ui.diameterStenosisValueLabel.setVisible(visibility)
    self.ui.surfaceAreaStenosisValueLabel.setVisible(visibility)
    self.ui.maxSurfaceAreaStenosisButton.setVisible(visibility)

  # We would definitely want to go directly to the maximum stenosis.
  def moveSliceViewToMaximumSurfaceAreaStenosis(self):
    point = self.logic.getExtremeMetricPoint(SURFACE_AREA_STENOSIS_ARRAY_NAME, True)
    if point == -1:
        return
    self.ui.moveToPointSliderWidget.setValue(point)

  def resetLumenRegions(self):
    if self._lumenRegions:
      self._lumenRegions.clear()
    self.ui.surfaceInformationLabel.clear()
    self.ui.surfaceInformationSpinBox.setValue(0)
    self.ui.surfaceInformationSpinBox.setMaximum(0)
    # Set the current effect to None.
    self.checkAndSetSegmentEditor(False)
    self.ui.surfaceInformationPaintToolButton.setChecked(False)
    self.ui.surfaceInformationPaintToolButton.setVisible(False)
    self.ui.surfaceInformationFastFixToolButton.setVisible(False)

  # Identify and track all regions of the lumen surface.
  def onGetRegionsButton(self):
    self.resetLumenRegions()
    self._lumenRegions = self.logic.getRegionsOfLumenSurface()
    if (not self._lumenRegions):
      logging.error("Invalid regions identified.")
      return
    numberOfRegions = len(self._lumenRegions)
    self.ui.surfaceInformationSpinBox.setMaximum(numberOfRegions)
    self.onRegionSelected(0)

    inputSurface = self.logic.lumenSurfaceNode
    if (inputSurface.GetClassName() == "vtkMRMLSegmentationNode"):
      # If there's only 1 region, there's nothing to fix.
      self.ui.surfaceInformationPaintToolButton.setVisible((numberOfRegions > 1) and self.checkAndSetSegmentEditor(True))
      self.ui.surfaceInformationFastFixToolButton.setVisible(numberOfRegions > 1)
      if (numberOfRegions == 1) and (self.checkAndSetSegmentEditor(False)):
        # Create segment editor object if needed.
        segmentEditorModuleWidget = slicer.util.getModuleWidget("SegmentEditor")
        seWidget = segmentEditorModuleWidget.editor
        seWidget.setActiveEffectByName(None)
    else:
      self.ui.surfaceInformationPaintToolButton.setVisible(False)
      self.ui.surfaceInformationFastFixToolButton.setVisible(False)

  # Initialise the segment editor if needed.
  # If the lumen surface is a segmentation, select it in the 'Segment editor'.
  # Always deactivate the current effect.
  def checkAndSetSegmentEditor(self, setNodes = False):
    inputSurface = self.logic.lumenSurfaceNode
    if (not inputSurface):
      logging.error("Invalid input surface node.")
      return False;

    if (inputSurface.GetClassName() != "vtkMRMLSegmentationNode"):
      return False # Silently

    if (not self.logic.currentSegmentID) or len(self.logic.currentSegmentID) == 0:
      logging.error("Invalid input segment ID.")
      return False

    # Create segment editor object if needed.
    segmentEditorModuleWidget = slicer.util.getModuleWidget("SegmentEditor")
    seWidget = segmentEditorModuleWidget.editor
    seWidget.setActiveEffectByName(None)

    if not setNodes:
      return True

    seWidget.setSegmentationNode(inputSurface)
    inputVolume = seWidget.sourceVolumeNode()
    if inputVolume == None:
      logging.error("Invalid input volume node.")
      return False
    inputSurface.SetReferenceImageGeometryParameterFromVolumeNode(inputVolume)
    seWidget.mrmlSegmentEditorNode().SetSelectedSegmentID(self.logic.currentSegmentID)

    return True

  """"
  Show the number of points and the number of cells of the selected region.
  Optionally locate the region in all slice views.
  The 'Paint' tool of the 'Segment editor' may then be used to fix a hole in a lumen.
  Notes: some regions may be as small as 3 points with the same coordinates, invisible.
  """
  def onRegionSelected(self, id):
    if (not self._lumenRegions):
      logging.info(_("Collection of lumen regions is unexpectedly None."))
      return

    numberOfRegions = len(self._lumenRegions)
    if (id > numberOfRegions):
      logging.info(_("Requested region is beyond range."))
      return

    label = str(id) + "/" + str(numberOfRegions)
    if (id > 0):
      region = self._lumenRegions[id - 1]
      numberOfPoints = region.GetNumberOfPoints()
      numberOfCells = region.GetNumberOfCells()
      label = label + " - " + str(numberOfPoints) + _(" points") + ", " + str(numberOfCells) + _(" cells")

      # If there is only one region, there's nothing to fix, no need to move the slice views.
      if self.ui.surfaceInformationGoToToolButton.checked and (numberOfRegions > 1):
        sliceNodes = [slicer.app.layoutManager().sliceWidget(viewName).mrmlSliceNode() for viewName in slicer.app.layoutManager().sliceViewNames()]
        firstPoint = region.GetPoint(0)
        for sliceNode in sliceNodes:
          slicer.vtkMRMLSliceNode.JumpSliceByCentering(sliceNode, *firstPoint)

        self.crosshair.SetCrosshairRAS(firstPoint)

    self.ui.surfaceInformationLabel.setText(label)

  # Jump to the selected region as we enable the toogle button.
  def onSurfaceInformationGoToToggled(self, checked):
    if not checked:
      return
    regionId = self.ui.surfaceInformationSpinBox.value
    self.onRegionSelected(regionId)

  # Activate the 'Paint' effect of the 'Segment editor' with a sphere brush.
  def onSurfaceInformationPaintToggled(self, checked):
    if not self.checkAndSetSegmentEditor(checked):
      logging.info(_("Could not prepare the segment editor."))
      return

    # Create segment editor object if needed.
    segmentEditorModuleWidget = slicer.util.getModuleWidget("SegmentEditor")
    seWidget = segmentEditorModuleWidget.editor

    if checked:
      seWidget.setActiveEffectByName("Paint")
      effect = seWidget.activeEffect()
      effect.setParameter("BrushSphere", str(1))
    else:
      seWidget.setActiveEffectByName(None)

  def onSurfaceInformationFastFix(self):
    segmentation = self.logic.lumenSurfaceNode
    segmentID = self.logic.currentSegmentID
    if (not segmentation) or (segmentation.GetClassName() != "vtkMRMLSegmentationNode") or (segmentID is None):
      logging.error("Invalid segmentation or segment ID.")
      return
    import QuickArterySegmentation
    qasLogic = QuickArterySegmentation.QuickArterySegmentationLogic()
    qasLogic.replaceSegmentByLargestRegion(segmentation, segmentID)
    self.onGetRegionsButton()

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
    # For a Shape markups node, inputCenterlineNode is the node itself: wall + invisible spline as centerline.
    self.inputCenterlineNode = None
    self.outputPlotSeriesNode = None
    self.outputTableNode = None
    self.plotChartNode = None
    self.coordinateSystemColumnSingle = True
    self.coordinateSystemColumnRAS = True  # LPS or RAS
    self.lumenSurfaceNode = None
    self.currentSegmentID = ""
    self.crossSectionPolyDataCache = {}
    self.crossSectionColor = [0.2, 0.2, 1.0]
    self.showCrossSection = False
    self.crossSectionModelNode = None
    self.maximumInscribedSphereModelNode = None
    self.showMaximumInscribedSphere = False
    self.maximumInscribedSphereColor = [0.2, 1.0, 0.4]
    self.relativeOriginPointIndex = 0
    self.outputPlotSeriesType = MIS_DIAMETER
    # Slice browsing
    self.axialSliceNode = None
    self.longitudinalSliceNode = None
    self.jumpCentredInSliceNode = True
    self.orthogonalReformatInSliceNode = True
    self.axialSpinAngleDeg = 0.0
    self.longitudinalSpinAngleDeg = 0.0
    self.rotationAngleDeg = 0.0
    self.axialSliceHorizontalFlip = False
    self.axialSliceVerticalFlip = False

  def showStatusMessage(self, messages):
    separator = " "
    msg = separator.join(messages)
    slicer.util.showStatusMessage(msg, 3000)
    slicer.app.processEvents()

  def setDefaultParameters(self, parameterNode):
    """
    Initialize parameter node with default settings.
    """
    parameterNode.SetParameter(ROLE_ORIGIN_POINT_INDEX, "0")
    parameterNode.SetParameter(ROLE_USE_LPS, "False")
    parameterNode.SetParameter(ROLE_USE_DISTINCT_COLUMLNS, "False")
    parameterNode.SetParameter(ROLE_CENTRE_IN_SLICE_VIEW, "True")
    parameterNode.SetParameter(ROLE_ORTHOGONAL_REFORMAT, "True")
    parameterNode.SetParameter(ROLE_SHOW_MIS_MODEL, "False")
    parameterNode.SetParameter(ROLE_SHOW_CROSS_SECTION_MODEL, "False")
    parameterNode.SetParameter(ROLE_OUTPUT_PLOT_SERIES_TYPE, MIS_DIAMETER)
    parameterNode.SetParameter(ROLE_BROWSE_POINT_INDEX, "0")
    parameterNode.SetParameter(ROLE_INITIALIZED, "1")

  def resetCrossSections(self):
    self.crossSectionPolyDataCache = {}

  def setInputCenterlineNode(self, centerlineNode):
    if self.inputCenterlineNode == centerlineNode:
      return
    self.inputCenterlineNode = centerlineNode
    self.resetCrossSections()
    self.relativeOriginPointIndex = 0

  def setLumenSurface(self, lumenSurfaceNode, currentSegmentID):
    # Eliminate a None surface, whatever be its type.
    if not lumenSurfaceNode:
      self.lumenSurfaceNode = None
      self.currentSegmentID = ""
      self.resetCrossSections()
      return
    # We may get an invalid (obsolete, empty, ...) segment ID.
    # In this case, use the first segment.
    verifiedSegmentID = ""
    if lumenSurfaceNode.GetClassName() == "vtkMRMLSegmentationNode":
      if lumenSurfaceNode.GetSegmentation().GetSegment(currentSegmentID):
        verifiedSegmentID = currentSegmentID
      else:
        verifiedSegmentID = lumenSurfaceNode.GetSegmentation().GetNthSegmentID(0)
    self.lumenSurfaceNode = lumenSurfaceNode
    self.currentSegmentID = verifiedSegmentID

    self.resetCrossSections()

  def setOutputTableNode(self, tableNode):
    if self.outputTableNode == tableNode:
      return
    self.outputTableNode = tableNode

  def setOutputPlotSeriesNode(self, plotSeriesNode):
    if self.outputPlotSeriesNode == plotSeriesNode:
      return
    self.outputPlotSeriesNode = plotSeriesNode

  def setShowCrossSection(self, checked):
    self.showCrossSection = checked
    if self.crossSectionModelNode is not None:
        self.crossSectionModelNode.GetDisplayNode().SetVisibility(self.showCrossSection)
    if not checked:
      self.deleteCrossSection()

  # type is item data of QComboBox, not item index
  def setPlotSeriesType(self, type):
    self.outputPlotSeriesType = type
    if self.outputPlotSeriesNode and self.outputTableNode and self.inputCenterlineNode:
        self.updatePlot(self.outputPlotSeriesNode, self.outputTableNode)
    if self.isPlotVisible():
        self.showPlot()

  def deleteCrossSection(self):
    if self.crossSectionModelNode is not None:
        slicer.mrmlScene.RemoveNode(self.crossSectionModelNode)
    self.crossSectionModelNode = None

  def setShowMaximumInscribedSphereDiameter(self, checked):
    self.showMaximumInscribedSphere = checked
    if self.maximumInscribedSphereModelNode is not None:
        self.maximumInscribedSphereModelNode.GetDisplayNode().SetVisibility(self.showMaximumInscribedSphere)
    if not checked:
      self.hideMaximumInscribedSphere()

  def hideMaximumInscribedSphere(self):
    if self.maximumInscribedSphereModelNode is not None:
        displayNode = self.maximumInscribedSphereModelNode.GetDisplayNode()
        if (displayNode): # ?
          displayNode.SetVisibility(False)

  # Identify the regions of the input lumen based on polydata connectivity.
  def getRegionsOfLumenSurface(self):
    closedSurfacePolyData = vtk.vtkPolyData()
    self.getClosedSurfacePolyData(closedSurfacePolyData)
    if (closedSurfacePolyData.GetNumberOfPoints() == 0):
      logging.error(_("Invalid surface polydata."))
      return

    regionFilter = vtk.vtkPolyDataConnectivityFilter()
    regionFilter.SetInputData(closedSurfacePolyData)
    regionFilter.SetExtractionModeToAllRegions()
    regionFilter.Update()
    numberOfRegions = regionFilter.GetNumberOfExtractedRegions()

    regions = []
    for regionId in range(numberOfRegions):
      regionExtrator = vtk.vtkPolyDataConnectivityFilter()
      regionExtrator.SetExtractionModeToSpecifiedRegions()
      regionExtrator.SetColorRegions(True)
      regionExtrator.AddSpecifiedRegion(regionId)
      regionExtrator.SetInputData(closedSurfacePolyData)
      regionExtrator.Update()

      # Remove isolated points.
      cleaner = vtk.vtkCleanPolyData()
      cleaner.SetInputConnection(regionExtrator.GetOutputPort())
      cleaner.Update()

      region = vtk.vtkPolyData()
      region.DeepCopy(cleaner.GetOutput())
      regions.append(region)

    return regions

  def isInputCenterlineValid(self):
    if self.inputCenterlineNode is None:
      return False
    if self.inputCenterlineNode.IsTypeOf("vtkMRMLMarkupsShapeNode"):
      if self.inputCenterlineNode.GetShapeName() != slicer.vtkMRMLMarkupsShapeNode.Tube:
        return False
      if self.inputCenterlineNode.GetNumberOfControlPoints() < 4:
        return False
      if self.inputCenterlineNode.GetShapeWorld() is None:
        return False
      if self.inputCenterlineNode.GetSplineWorld() is None:
        return False
      """
      If the Shape markups node has an odd number of points,
      or if it has unplaced points,
      it is sort of deactivated in UI, but there's still a spline and a wall.
      """
    return True

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
    if not self.isInputCenterlineValid(): # See remarks for Shape node.
      return 0
    if self.inputCenterlineNode.IsTypeOf("vtkMRMLModelNode"):
        return self.inputCenterlineNode.GetPolyData().GetNumberOfPoints()
    elif self.inputCenterlineNode.IsTypeOf("vtkMRMLMarkupsShapeNode"):
      trimmedSpline = vtk.vtkPolyData()
      if not self.inputCenterlineNode.GetTrimmedSplineWorld(trimmedSpline):
        return self.inputCenterlineNode.GetSplineWorld().GetNumberOfPoints()
      else:
        return trimmedSpline.GetNumberOfPoints()
    else:
        return self.inputCenterlineNode.GetCurvePointsWorld().GetNumberOfPoints()

  def run(self):
    self.resetCrossSections()
    if not self.isInputCenterlineValid():
        msg = _("Input is invalid.")
        slicer.util.showStatusMessage(msg, 3000)
        raise ValueError(msg)

    logging.info(_("Processing started"))
    if self.outputTableNode:
      self.emptyOutputTableNode()
      self.updateOutputTable(self.inputCenterlineNode, self.outputTableNode)
    if self.outputPlotSeriesNode:
      self.updatePlot(self.outputPlotSeriesNode, self.outputTableNode)
    logging.info(_("Processing completed"))

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
    import time
    startTime = time.time()
    # Create arrays of data
    distanceArray = self.getArrayFromTable(outputTable, DISTANCE_ARRAY_NAME)
    if (not inputCenterline.IsTypeOf("vtkMRMLMarkupsShapeNode")):
      if (inputCenterline.IsTypeOf("vtkMRMLModelNode")):
        if (inputCenterline.HasPointScalarName("Radius")): # VMTK centerline model
          misDiameterArray = self.getArrayFromTable(outputTable, MIS_DIAMETER_ARRAY_NAME)
        else:
          misDiameterArray = None
      else:
          radiusMeasurement = inputCenterline.GetMeasurement("Radius")
          if radiusMeasurement: # VMTK centerline curve
            misDiameterArray = self.getArrayFromTable(outputTable, MIS_DIAMETER_ARRAY_NAME)
          else: # Arbitrary curve
            misDiameterArray = None
    else:
      misDiameterArray = None
      wallDiameterArray = self.getArrayFromTable(outputTable, WALL_DIAMETER_ARRAY_NAME)
      wallCrossSectionAreaArray = self.getArrayFromTable(outputTable, WALL_CROSS_SECTION_AREA_ARRAY_NAME)
      if self.lumenSurfaceNode:
        diameterStenosisArray = self.getArrayFromTable(outputTable, DIAMETER_STENOSIS_ARRAY_NAME)
        surfaceAreaStenosisArray = self.getArrayFromTable(outputTable, SURFACE_AREA_STENOSIS_ARRAY_NAME)

    if self.lumenSurfaceNode:
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
        numberOfPoints = len(points)
        for pointIndex in range(len(pointsLocal)):
          inputCenterline.TransformPointToWorld(pointsLocal[pointIndex], points[pointIndex])
        if inputCenterline.HasPointScalarName("Radius"):
          radii = slicer.util.arrayFromModelPointData(inputCenterline, 'Radius')
        else:
          radii = np.zeros(0)
    else: # Shape, VMTK curve centerline or arbitrary curve centerline
        if (inputCenterline.IsTypeOf("vtkMRMLMarkupsShapeNode")):
          trimmedSpline = vtk.vtkPolyData()
          trimmedSplineAvailable = False
          if not inputCenterline.GetTrimmedSplineWorld(trimmedSpline):
            numberOfPoints = inputCenterline.GetSplineWorld().GetNumberOfPoints()
          else:
            numberOfPoints = trimmedSpline.GetNumberOfPoints()
            trimmedSplineAvailable = True
          points = np.zeros([numberOfPoints, 3])
          for p in range(numberOfPoints):
            point = np.zeros(3)
            if not trimmedSplineAvailable:
              inputCenterline.GetSplineWorld().GetPoint(p, point)
            else:
              trimmedSpline.GetPoint(p, point)
            points[p] = point
        else: # VMTK curve centerline or arbitrary curve centerline
          points = slicer.util.arrayFromMarkupsCurvePoints(inputCenterline, world=True)
          controlPointFloatIndices = inputCenterline.GetCurveWorld().GetPointData().GetArray('PedigreeIDs')
          numberOfPoints = len(points)

        radii = np.zeros(numberOfPoints)
        radiusMeasurement = inputCenterline.GetMeasurement("Radius")
        controlPointRadiusValues = vtk.vtkDoubleArray()
        if radiusMeasurement: # VMTK curve centerline
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
        else:
          radii = np.zeros(0)

    outputTable.GetTable().SetNumberOfRows(numberOfPoints)

    """
    Fill in cross-section areas in C++ threads.
    """
    import vtkSlicerCrossSectionAnalysisModuleLogicPython as vtkSlicerCrossSectionAnalysisModuleLogic
    crossSectionCompute = vtkSlicerCrossSectionAnalysisModuleLogic.vtkCrossSectionCompute()
    # If numberOfThreads > number of cores, excessive threads would be in infinite loop.
    numberOfThreads = os.cpu_count() if (numberOfPoints >= os.cpu_count()) else numberOfPoints
    crossSectionCompute.SetNumberOfThreads(numberOfThreads)
    if self.isInputCenterlineValid():
        if inputCenterline.IsTypeOf("vtkMRMLModelNode"):
            crossSectionCompute.SetInputCenterlinePolyData(inputCenterline.GetPolyData())
        elif inputCenterline.IsTypeOf("vtkMRMLMarkupsShapeNode"):
            trimmedSpline = vtk.vtkPolyData()
            if not inputCenterline.GetTrimmedSplineWorld(trimmedSpline):
              crossSectionCompute.SetInputCenterlinePolyData(inputCenterline.GetSplineWorld())
            else:
              crossSectionCompute.SetInputCenterlinePolyData(trimmedSpline)
        else:
            crossSectionCompute.SetInputCenterlinePolyData(inputCenterline.GetCurveWorld())
    if self.lumenSurfaceNode:
        crossSectionCompute.SetInputSurfaceNode(self.lumenSurfaceNode, self.currentSegmentID)
        self.showStatusMessage((_("Waiting for background jobs..."), ))
        emptySectionIds = vtk.vtkIdList()
        if (not crossSectionCompute.UpdateTable(crossSectionAreaArray, ceDiameterArray, emptySectionIds)):
          raise RuntimeError("Failed to compute cross-sections.")
        surfaceName = self.lumenSurfaceNode.GetName()
        if self.lumenSurfaceNode.IsTypeOf("vtkMRMLSegmentationNode") and self.currentSegmentID:
          surfaceName = surfaceName + " - " + self.lumenSurfaceNode.GetSegmentation().GetSegment(self.currentSegmentID).GetName()
        self._informAboutEmptySections(emptySectionIds, surfaceName)

    """
    We may also use the TubeRadius scalar array of the spline. This may prevent
    weird measurements at both ends of the tube. Not tested.
    We elect to slice the wall so as to use the same method of slicing the lumen.
    Good ? Bad ?
    """
    if inputCenterline.IsTypeOf("vtkMRMLMarkupsShapeNode"):
      wallCrossSectionCompute = vtkSlicerCrossSectionAnalysisModuleLogic.vtkCrossSectionCompute()
      wallCrossSectionCompute.SetNumberOfThreads(numberOfThreads)
      # Internally, the segment ID is not used; the axial spline is the centerline polydata.
      wallCrossSectionCompute.SetInputSurfaceNode(inputCenterline, self.currentSegmentID)
      trimmedSpline = vtk.vtkPolyData()
      if not inputCenterline.GetTrimmedSplineWorld(trimmedSpline):
        wallCrossSectionCompute.SetInputCenterlinePolyData(inputCenterline.GetSplineWorld())
      else:
        wallCrossSectionCompute.SetInputCenterlinePolyData(trimmedSpline)
      self.showStatusMessage((_("Waiting for background jobs..."), ))
      wallEmptySectionIds = vtk.vtkIdList()
      if (not wallCrossSectionCompute.UpdateTable(wallCrossSectionAreaArray, wallDiameterArray, wallEmptySectionIds)):
        raise RuntimeError("Failed to compute cross-sections.")
      self._informAboutEmptySections(wallEmptySectionIds, inputCenterline.GetName())

    cumArray = vtk.vtkDoubleArray()
    self.cumulateDistances(points, cumArray)
    relArray = vtk.vtkDoubleArray()
    self.updateCumulativeDistancesToRelativeOrigin(cumArray, relArray)

    for i in range(numberOfPoints):
      if (((i + 1) % 25) == 0):
          self.showStatusMessage((_("Updating table:"), str(i + 1), "/", str(numberOfPoints)))
      # Distance from relative origin
      distanceArray.SetValue(i, relArray.GetValue(i))
      # Radii
      if radii.size and misDiameterArray:
            misDiameterArray.SetValue(i, radii[i] * 2)
      # Diameter and surface area stenosis
      if (inputCenterline.IsTypeOf("vtkMRMLMarkupsShapeNode")) and self.lumenSurfaceNode:
        # The resolution of the Tube may be too low and can be increased.
        diameterStenosis = -1.0
        surfaceAreaStenosis = -1.0
        if (wallDiameterArray.GetValue(i)) and (wallCrossSectionAreaArray.GetValue(i)):
          diameterStenosis = ((wallDiameterArray.GetValue(i) - ceDiameterArray.GetValue(i)) / wallDiameterArray.GetValue(i)) * 100
          surfaceAreaStenosis = ((wallCrossSectionAreaArray.GetValue(i) - crossSectionAreaArray.GetValue(i)) / wallCrossSectionAreaArray.GetValue(i)) * 100
        # vtkCrossSectionCompute has already provided the indices; don't flood the console.
        surfaceAreaStenosisArray.SetValue(i, surfaceAreaStenosis)
        diameterStenosisArray.SetValue(i, diameterStenosis)
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
    if misDiameterArray:
      misDiameterArray.Modified()
    if (inputCenterline.IsTypeOf("vtkMRMLMarkupsShapeNode")):
      wallDiameterArray.Modified()
      wallCrossSectionAreaArray.Modified()
      if self.lumenSurfaceNode:
        surfaceAreaStenosisArray.Modified()
    if self.lumenSurfaceNode:
      crossSectionAreaArray.Modified()
      ceDiameterArray.Modified()
    outputTable.GetTable().Modified()

    stopTime = time.time()
    durationValue = '%.2f' % (stopTime-startTime)
    message = _("Processing completed in {duration} seconds - {countOfPoints} points").format(duration=durationValue, countOfPoints=numberOfPoints)
    logging.info(message)
    slicer.util.showStatusMessage(message, 5000)

  def updatePlot(self, outputPlotSeries, outputTable):

    # Create plot
    outputPlotSeries.SetAndObserveTableNodeID(outputTable.GetID())
    outputPlotSeries.SetXColumnName(DISTANCE_ARRAY_NAME)
    if self.outputPlotSeriesType == MIS_DIAMETER:
        outputPlotSeries.SetYColumnName(MIS_DIAMETER_ARRAY_NAME)
    elif self.outputPlotSeriesType == CE_DIAMETER:
        outputPlotSeries.SetYColumnName(CE_DIAMETER_ARRAY_NAME)
    elif self.outputPlotSeriesType == CROSS_SECTION_AREA:
        outputPlotSeries.SetYColumnName(CROSS_SECTION_AREA_ARRAY_NAME)
    elif self.outputPlotSeriesType == WALL_CE_DIAMETER:
        outputPlotSeries.SetYColumnName(WALL_DIAMETER_ARRAY_NAME)
    elif self.outputPlotSeriesType == WALL_CROSS_SECTION_AREA:
        outputPlotSeries.SetYColumnName(WALL_CROSS_SECTION_AREA_ARRAY_NAME)
    elif self.outputPlotSeriesType == DIAMETER_STENOSIS:
        outputPlotSeries.SetYColumnName(DIAMETER_STENOSIS_ARRAY_NAME)
    elif self.outputPlotSeriesType == SURFACE_AREA_STENOSIS:
        outputPlotSeries.SetYColumnName(SURFACE_AREA_STENOSIS_ARRAY_NAME)
    else:
      pass
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
    lengthUnit = self.getUnitNodeUnitDisplayString(0.0, "length")
    areaUnit = self.getUnitNodeUnitDisplayString(0.0, "area")
    self.plotChartNode.SetXAxisTitle("{nameOfDistanceArray} ( {unitOfLength})".format(nameOfDistanceArray=DISTANCE_ARRAY_NAME, unitOfLength=lengthUnit))
    if self.outputPlotSeriesType == MIS_DIAMETER:
        self.plotChartNode.SetYAxisTitle(_("Diameter ({unitOfLength})").format(unitOfLength=lengthUnit))
    if self.outputPlotSeriesType == CE_DIAMETER:
        self.plotChartNode.SetYAxisTitle(_("Diameter ({unitOfLength})").format(unitOfLength=lengthUnit))
    elif self.outputPlotSeriesType == CROSS_SECTION_AREA:
        self.plotChartNode.SetYAxisTitle(_("Area ({unitOfArea})").format(unitOfArea=areaUnit))
    elif self.outputPlotSeriesType == WALL_CE_DIAMETER:
        self.plotChartNode.SetYAxisTitle(_("Diameter ({unitOfLength})").format(unitOfLength=lengthUnit))
    elif self.outputPlotSeriesType == WALL_CROSS_SECTION_AREA:
        self.plotChartNode.SetYAxisTitle(_("Area ({unitOfArea})").format(unitOfArea=areaUnit))
    elif self.outputPlotSeriesType == DIAMETER_STENOSIS:
        self.plotChartNode.SetYAxisTitle(_("Stenosis (%)"))
    elif self.outputPlotSeriesType == SURFACE_AREA_STENOSIS:
        self.plotChartNode.SetYAxisTitle(_("Stenosis (%)"))
    else:
      pass
    # Reset the chart.
    self.plotChartNode.RemoveAllPlotSeriesNodeIDs()
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
        self.plotChartNode = plotViewNode.GetPlotChartNode()
        return True
    # Plot series is not visible
    return False

  def cumulateDistances(self, arrPoints, cumArray):
    cumArray.SetNumberOfValues(len(arrPoints))
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
    if not self.isInputCenterlineValid():
      return position
    if (self.inputCenterlineNode.IsTypeOf("vtkMRMLModelNode")):
        positionLocal = slicer.util.arrayFromModelPoints(self.inputCenterlineNode)[pointIndex]
        self.inputCenterlineNode.TransformPointToWorld(positionLocal, position)
    elif (self.inputCenterlineNode.IsTypeOf("vtkMRMLMarkupsShapeNode")):
        trimmedSpline = vtk.vtkPolyData()
        if not self.inputCenterlineNode.GetTrimmedSplineWorld(trimmedSpline):
          self.inputCenterlineNode.GetSplineWorld().GetPoint(pointIndex, position)
        else:
          trimmedSpline.GetPoint(pointIndex, position)
    else:
        self.inputCenterlineNode.GetCurvePointsWorld().GetPoint(pointIndex, position)
    return position

  def updateSliceView(self, pointIndex):
    """Move the selected slice view to a point of the centerline, optionally centering on the point, and with optional orthogonal reformat.
    """
    curvePointToWorld = self.getCurvePointToWorldTransformAtPointIndex(pointIndex)

    if self.orthogonalReformatInSliceNode:

      if self.axialSliceNode:
        rotationTransform = vtk.vtkTransform()
        rotationTransform.SetMatrix(curvePointToWorld)
        rotationTransform.RotateZ(self.axialSpinAngleDeg)
        if self.axialSliceHorizontalFlip:
            rotationTransform.RotateX(180.0)
        if self.axialSliceVerticalFlip:
            rotationTransform.RotateY(180.0)
        rotationMatrix = rotationTransform.GetMatrix()
        self.axialSliceNode.SetSliceToRASByNTP(
          rotationMatrix.GetElement(0, 2), rotationMatrix.GetElement(1, 2), rotationMatrix.GetElement(2, 2),
          rotationMatrix.GetElement(0, 0), rotationMatrix.GetElement(1, 0), rotationMatrix.GetElement(2, 0),
          rotationMatrix.GetElement(0, 3), rotationMatrix.GetElement(1, 3), rotationMatrix.GetElement(2, 3), 0)
        if self.jumpCentredInSliceNode:
          self.axialSliceNode.SetXYZOrigin(0, 0, 0)

      if self.longitudinalSliceNode:
        rotationTransform = vtk.vtkTransform()
        rotationTransform.SetMatrix(curvePointToWorld)
        rotationTransform.RotateZ(self.rotationAngleDeg)
        rotationTransform.RotateX(self.longitudinalSpinAngleDeg)
        rotationMatrix = rotationTransform.GetMatrix()
        self.longitudinalSliceNode.SetSliceToRASByNTP(
          rotationMatrix.GetElement(0, 2), rotationMatrix.GetElement(1, 2), rotationMatrix.GetElement(2, 2),
          rotationMatrix.GetElement(0, 0), rotationMatrix.GetElement(1, 0), rotationMatrix.GetElement(2, 0),
          rotationMatrix.GetElement(0, 3), rotationMatrix.GetElement(1, 3), rotationMatrix.GetElement(2, 3), 1)
        if self.jumpCentredInSliceNode:
          self.longitudinalSliceNode.SetXYZOrigin(0, 0, 0)

    else:
      center = [curvePointToWorld.GetElement(i, 3) for i in range(3)]
      for sliceNode in [self.axialSliceNode, self.longitudinalSliceNode]:
        if not sliceNode:
          continue
        if self.jumpCentredInSliceNode:
          slicer.vtkMRMLSliceNode.JumpSliceByCentering(sliceNode, *center)
        else:
          slicer.vtkMRMLSliceNode.JumpSlice(sliceNode, *center)

  def getExtremeMetricPoint(self, arrayName, boolMaximum):
    """Convenience function to get the point of minimum or maximum diameter.
    Is useful for arterial stenosis (minimum) or aneurysm (maximum).
    """
    if self.outputTableNode is None:
        return -1
    metricArray = self.outputTableNode.GetTable().GetColumnByName(arrayName)
    if metricArray is None:
        return -1
    # GetRange or GetValueRange ?
    metricRange = metricArray.GetRange()
    target = -1
    # Until we find a smart function, kind of vtkDoubleArray::Find(value)
    for i in range(metricArray.GetNumberOfValues()):
        if metricArray.GetValue(i) == metricRange[1 if boolMaximum else 0]:
            target = i
            # If there more points with the same value, they are ignored. First point only.
            break
    return target

  def getUnitNodeDisplayString(self, value, category):
    selectionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLSelectionNodeSingleton")
    unitNode = slicer.mrmlScene.GetNodeByID(selectionNode.GetUnitNodeID(category))
    return unitNode.GetDisplayStringFromValue(value)

  def getUnitNodeUnitDisplayString(self, value, category):
    selectionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLSelectionNodeSingleton")
    unitNode = slicer.mrmlScene.GetNodeByID(selectionNode.GetUnitNodeID(category))
    displayString = unitNode.GetDisplayStringFromValue(value)
    splitString = displayString.split()
    return splitString[len(splitString) - 1]

  def getCurvePointToWorldTransformAtPointIndex(self, pointIndex):

    curvePointToWorld = vtk.vtkMatrix4x4()
    if self.inputCenterlineNode.IsTypeOf("vtkMRMLModelNode") or self.inputCenterlineNode.IsTypeOf("vtkMRMLMarkupsShapeNode"):
      curveCoordinateSystemGenerator = slicer.vtkParallelTransportFrame()
      if self.inputCenterlineNode.IsTypeOf("vtkMRMLModelNode"):
        curveCoordinateSystemGenerator.SetInputData(self.inputCenterlineNode.GetPolyData())
      else:
        if not self.isInputCenterlineValid():
          return
        trimmedSpline = vtk.vtkPolyData()
        if not self.inputCenterlineNode.GetTrimmedSplineWorld(trimmedSpline):
          curveCoordinateSystemGenerator.SetInputData(self.inputCenterlineNode.GetSplineWorld())
        else:
          curveCoordinateSystemGenerator.SetInputData(trimmedSpline)
      curveCoordinateSystemGenerator.Update()
      curvePoly = curveCoordinateSystemGenerator.GetOutput()
      pointData = curvePoly.GetPointData()
      normals = pointData.GetAbstractArray(curveCoordinateSystemGenerator.GetNormalsArrayName())
      binormals = pointData.GetAbstractArray(curveCoordinateSystemGenerator.GetBinormalsArrayName())
      tangents = pointData.GetAbstractArray(curveCoordinateSystemGenerator.GetTangentsArrayName())
      normal = normals.GetTuple3(pointIndex)
      binormal = binormals.GetTuple3(pointIndex)
      tangent = tangents.GetTuple3(pointIndex)
      position = curvePoly.GetPoint(pointIndex)
      for row in range(3):
        curvePointToWorld.SetElement(row, 0, normal[row])
        curvePointToWorld.SetElement(row, 1, binormal[row])
        curvePointToWorld.SetElement(row, 2, tangent[row])
        curvePointToWorld.SetElement(row, 3, position[row])
      # TODO: transform from local to world
    else:
      self.inputCenterlineNode.GetCurvePointToWorldTransformAtPointIndex(pointIndex, curvePointToWorld)

    return curvePointToWorld

  def clipLumenInTube(self, clippedSurface : vtk.vtkPolyData):
    if not self.inputCenterlineNode or not self.lumenSurfaceNode:
      raise ValueError(_("Input centerline node or input lumen surface node is None."))
    if not self.inputCenterlineNode.IsTypeOf("vtkMRMLMarkupsShapeNode"):
      raise ValueError(_("Input centerline node is not a Shape node."))
    lumenSurface = vtk.vtkPolyData()
    self.getClosedSurfacePolyData(lumenSurface)
    if lumenSurface.GetNumberOfPoints() == 0:
      raise ValueError(_("Empty lumen surface retrieved."))
    tubeSurface = self.inputCenterlineNode.GetCappedTubeWorld()

    sm3Logic = slicer.modules.stenosismeasurement3d.logic()
    clippedLumenRaw = vtk.vtkPolyData()
    clipped = sm3Logic.GetClosedSurfaceEnclosingType(
                  tubeSurface, lumenSurface, clippedLumenRaw)
    if (clipped == sm3Logic.Distinct) or (clipped == sm3Logic.EnclosingType_Last):
      return False
    else:
      # Clip any excess from vtkBooleanOperationPolyDataFilter at each end.
      # If the lumen is a loop, the result may be curious.
      spline = self.inputCenterlineNode.GetSplineWorld()
      curveCoordinateSystemGenerator = slicer.vtkParallelTransportFrame()
      curveCoordinateSystemGenerator.SetInputData(spline)
      curveCoordinateSystemGenerator.Update()
      curvePoly = curveCoordinateSystemGenerator.GetOutput()
      pointData = curvePoly.GetPointData()
      tangents = pointData.GetAbstractArray(curveCoordinateSystemGenerator.GetTangentsArrayName())
      startTangent = tangents.GetTuple3(0)
      lastTangent = tangents.GetTuple3(spline.GetNumberOfPoints() - 1)
      endTangent = [lastTangent[0] * -1, lastTangent[1] * -1, lastTangent[2] * -1]
      startPoint = curvePoly.GetPoints().GetPoint(0)
      endPoint = curvePoly.GetPoints().GetPoint(spline.GetNumberOfPoints() - 1)

      clippedLumenFixed = vtk.vtkPolyData()
      if sm3Logic.ClipClosedSurfaceWithClosedOutput(clippedLumenRaw, clippedLumenFixed,
                                                 startPoint, startTangent,
                                                 endPoint, endTangent):
        # Remesh the polydata using a segmentation.
        if not sm3Logic.UpdateClosedSurfaceMesh(clippedLumenFixed, clippedSurface):
          clippedSurface.Initialize()
          clippedSurface.DeepCopy(clippedLumenFixed)
          return False
      else:
        clippedSurface.Initialize()
        clippedSurface.DeepCopy(clippedLumenRaw)
        return False

    return True

  def getClosedSurfacePolyData(self, closedSurfacePolyData):
    if (not self.lumenSurfaceNode):
      logging.error(_("Lumen surface node is not set."))
      return
    # Work on the segment's closed surface
    if self.lumenSurfaceNode.GetClassName() == "vtkMRMLSegmentationNode":
      self.lumenSurfaceNode.CreateClosedSurfaceRepresentation()
      self.lumenSurfaceNode.GetClosedSurfaceRepresentation(self.currentSegmentID, closedSurfacePolyData)
    else:
      closedSurfacePolyData.DeepCopy(self.lumenSurfaceNode.GetPolyData())

  def computeCrossSectionPolydata(self, pointIndex):
    curvePointToWorld = self.getCurvePointToWorldTransformAtPointIndex(pointIndex)
    center = np.zeros(3)
    normal = np.zeros(3)
    for i in range(3):
      center[i] = curvePointToWorld.GetElement(i, 3)
      normal[i] = curvePointToWorld.GetElement(i, 2)

    # Place a plane perpendicular to the centerline
    plane = vtk.vtkPlane()
    plane.SetOrigin(center)
    plane.SetNormal(normal)

    closedSurfacePolyData = vtk.vtkPolyData()
    self.getClosedSurfacePolyData(closedSurfacePolyData)

    # If segmentation is transformed, apply it to the cross-section model. All computations are performed in the world coordinate system.
    if self.lumenSurfaceNode.GetParentTransformNode():
      surfaceTransformToWorld = vtk.vtkGeneralTransform()
      slicer.vtkMRMLTransformNode.GetTransformBetweenNodes(self.lumenSurfaceNode.GetParentTransformNode(), None, surfaceTransformToWorld)
      transformFilterToWorld = vtk.vtkTransformPolyDataFilter()
      transformFilterToWorld.SetTransform(surfaceTransformToWorld)
      transformFilterToWorld.SetInputData(closedSurfacePolyData)
      transformFilterToWorld.Update()
      closedSurfacePolyData = transformFilterToWorld.GetOutput()

    result = vtk.vtkPolyData()
    import vtkSlicerCrossSectionAnalysisModuleLogicPython as vtkSlicerCrossSectionAnalysisModuleLogic
    crossSectionWorker = vtkSlicerCrossSectionAnalysisModuleLogic.vtkCrossSectionCompute()
    ret = crossSectionWorker.CreateCrossSection(result, closedSurfacePolyData, plane, crossSectionWorker.ClosestPoint, True)
    if (ret == crossSectionWorker.Empty):
      logging.error(_("Error creating a cross-section polydata of the lumen at point index {indexOfPoint}.").format(indexOfPoint=pointIndex))

    return result

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
      basename = _("Cross-section")
      name = slicer.mrmlScene.GenerateUniqueName(basename)
      self.crossSectionModelNode.SetName(name)
      crossSectionModelDisplayNode = self.crossSectionModelNode.GetDisplayNode()
      crossSectionModelDisplayNode.SetColor(self.crossSectionColor)
      crossSectionModelDisplayNode.SetOpacity(0.75)
      crossSectionModelDisplayNode.SetLighting(False)
    else:
      self.crossSectionModelNode.SetAndObservePolyData(crossSectionPolyData)

  def getCrossSectionArea(self, pointIndex):
    """Get the pre-computed cross-section surface area"""
    if self.outputTableNode is None or self.lumenSurfaceNode is None:
      return 0.0

    currentSurfaceAreaVariant = self.outputTableNode.GetTable().GetValueByName(int(pointIndex), CROSS_SECTION_AREA_ARRAY_NAME)
    currentSurfaceArea = currentSurfaceAreaVariant.ToDouble() if currentSurfaceAreaVariant.IsValid() else 0.0
    return currentSurfaceArea

  def getPositionMaximumInscribedSphereRadius(self, pointIndex):
    if not self.isCenterlineRadiusAvailable():
      raise ValueError(_("Maximum inscribed sphere radius is not available"))
    position = np.zeros(3)
    if self.inputCenterlineNode.IsTypeOf("vtkMRMLModelNode"):
      positionLocal = slicer.util.arrayFromModelPoints(self.inputCenterlineNode)[pointIndex]
      self.inputCenterlineNode.TransformPointToWorld(positionLocal, position)
      radius = slicer.util.arrayFromModelPointData(self.inputCenterlineNode, 'Radius')[pointIndex]
    elif self.inputCenterlineNode.IsTypeOf("vtkMRMLMarkupsShapeNode"):
      # Maximum inscribed sphere is not concerned here.
      trimmedSpline = vtk.vtkPolyData()
      if not self.inputCenterlineNode.GetTrimmedSplineWorld(trimmedSpline):
        self.inputCenterlineNode.GetSplineWorld().GetPoint(pointIndex, position)
      else:
        trimmedSpline.GetPoint(pointIndex, position)
      return position, 0.0
    else:
      self.inputCenterlineNode.GetCurveWorld().GetPoints().GetPoint(pointIndex, position)
      radiusMeasurement = self.inputCenterlineNode.GetMeasurement('Radius')
      if not radiusMeasurement:
          return position, 0.0
      # Get curve point radius by interpolating control point measurements
      # Need to compute manually until this method becomes available:
      #  radius = self.inputCenterlineNode.GetMeasurement('Radius').GetCurvePointValue(pointIndex)
      if pointIndex < (self.getNumberOfPoints() - 1):
        controlPointFloatIndex = self.inputCenterlineNode.GetCurveWorld().GetPointData().GetArray('PedigreeIDs').GetValue(pointIndex)
      else:
        """
        Don't go beyond the last point with controlPointIndexB
        Else,
            radiusB = controlPointRadiusValues.GetValue(controlPointIndexB)
        will fail.
        """
        controlPointFloatIndex = self.inputCenterlineNode.GetCurveWorld().GetPointData().GetArray('PedigreeIDs').GetValue(pointIndex - 1)
      controlPointIndexA = int(controlPointFloatIndex)
      controlPointIndexB = controlPointIndexA + 1
      controlPointRadiusValues = self.inputCenterlineNode.GetMeasurement('Radius').GetControlPointValues()
      radiusA = controlPointRadiusValues.GetValue(controlPointIndexA)
      radiusB = controlPointRadiusValues.GetValue(controlPointIndexB)
      radius = radiusA * (controlPointFloatIndex - controlPointIndexA) + radiusB * (controlPointIndexB - controlPointFloatIndex)
    return position, radius

  def updateMaximumInscribedSphereModel(self, value):
    if self.inputCenterlineNode.IsTypeOf("vtkMRMLMarkupsShapeNode"):
      # 'Centerline' is an invisible spline of a Tube, not a lumen centerline.
      return
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
      basename = _("Maximum inscribed sphere")
      name = slicer.mrmlScene.GenerateUniqueName(basename)
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

  def _informAboutEmptySections(self, ids:vtk. vtkIdList, surfaceName):
    numberOfIds = ids.GetNumberOfIds()
    if numberOfIds == 0:
      return
    statusMessage = str(numberOfIds) + " " + _("empty sections have been detected; consider improving the input lumen {nameOfSurface}." ).format(nameOfSurface=surfaceName)
    consoleMessage = "Empty sections have been created at these point ids of the centerline: "
    idList = ""
    sorter = vtk.vtkSortDataArray()
    sorter.Sort(ids)
    for i in range(numberOfIds):
      idList = idList + ", " + str(ids.GetId(i))
    idList = idList[2 : len(idList)]
    consoleMessage = consoleMessage + idList + "; consider improving the input lumen (" + surfaceName +")."
    self.showStatusMessage((statusMessage,))
    logging.warning(consoleMessage)

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

DISTANCE_ARRAY_NAME = _("Distance")
MIS_DIAMETER_ARRAY_NAME = _("Diameter (MIS)")
CE_DIAMETER_ARRAY_NAME = _("Diameter (CE)")
CROSS_SECTION_AREA_ARRAY_NAME = _("Cross-section area")
WALL_DIAMETER_ARRAY_NAME = _("Wall diameter")
WALL_CROSS_SECTION_AREA_ARRAY_NAME = _("Wall cross-section area")
SURFACE_AREA_STENOSIS_ARRAY_NAME = _("Stenosis by surface area")
DIAMETER_STENOSIS_ARRAY_NAME = _("Stenosis by diameter (CE)")

MIS_DIAMETER = "MIS_DIAMETER"
CE_DIAMETER = "CE_DIAMETER"
CROSS_SECTION_AREA = "CROSS_SECTION_AREA"
WALL_CE_DIAMETER = "WALL_CE_DIAMETER"
WALL_CROSS_SECTION_AREA = "WALL_CROSS_SECTION_AREA"
DIAMETER_STENOSIS = "DIAMETER_STENOSIS"
SURFACE_AREA_STENOSIS = "SURFACE_AREA_STENOSIS"

ROLE_INPUT_CENTERLINE = "InputCenterline"
ROLE_INPUT_SEGMENTATION = "InputSegmentation"
ROLE_INPUT_SEGMENT_ID = "InputSegment"
ROLE_OUTPUT_TABLE = "OutputTable"
ROLE_OUTPUT_PLOT_SERIES = "OutputPlotSeries"
ROLE_AXIAL_SLICE_NODE = "AxialSliceNode"
ROLE_LONGITUDINAL_SLICE_NODE = "LongitudinalSliceNode"
ROLE_ORIGIN_POINT_INDEX = "OriginPointIndex"
ROLE_USE_LPS = "UseLPS"
ROLE_USE_DISTINCT_COLUMLNS = "DistinctColumns"
ROLE_CENTRE_IN_SLICE_VIEW = "CentreInSliceView"
ROLE_ORTHOGONAL_REFORMAT = "OrthogonalReformat"
ROLE_ROTATIONAL_ANGLE = "RotationAngleDeg"
ROLE_AXIAL_SPIN_ANGLE = "AxialSpinAngleDeg"
ROLE_LONGITUDINAL_SPIN_ANGLE = "LongitudinalSpinAngleDeg"
ROLE_SHOW_MIS_MODEL = "ShowMISModel"
ROLE_SHOW_CROSS_SECTION_MODEL = "ShowCrossSectionModel"
ROLE_AXIAL_HORIZONTAL_FLIP = "AxialSliceHorizontalFlip"
ROLE_AXIAL_VERTICAL_FLIP = "AxialSliceVerticalFlip"
ROLE_GOTO_REGION = "GoToRegion"
ROLE_BROWSE_POINT_INDEX = "BrowsePointIndex"
ROLE_OUTPUT_PLOT_SERIES_TYPE = "OutputPlotSeriesType"
ROLE_INITIALIZED = "Initialized"
