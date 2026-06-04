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
# StenosisMeasurement2D
#

class StenosisMeasurement2D(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Stenosis measurement: 2D"
    self.parent.categories = ["Vascular Modeling Toolkit"]
    self.parent.dependencies = []
    self.parent.contributors = ["Saleem Edah-Tally [Surgeon] [Hobbyist developer]", "Andras Lasso, PerkLab"]
    self.parent.helpText = _("""
This <a href="https://github.com/vmtk/SlicerExtension-VMTK/">module</a> calculates the surface area of segments cut by a slice plane in its orientation. It is intended for quick two dimensional arterial stenosis evaluation, but is actually purpose agnostic.
""")
    # TODO: replace with organization, grant and thanks
    self.parent.acknowledgementText = _("""
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
""")

class StenosisMeasurement2DWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
    self._updatingGUIFromParameterNode = False
    self.currentControlPointID = "-1" # API gets/sets it as a string

    # Observe JumpToPointEvent of the fiducial display node.
    self.fiducialDisplayNodeObservation = None

    self._optionsMainMenu = None
    self._optionsSubMenu1 = None
    self._applyToAllSegmentsAction = None
    self._limitToClosestIslandsAction = None
    self._createOutputModelsAction = None
    self._resetOrientationAction = None
    self._restoreSliceViewsOrientation = None

  def setup(self) -> None:
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer).
    # Additional widgets can be instantiated manually and added to self.layout.
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/StenosisMeasurement2D.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    # Create logic class. Logic implements all computations that should be possible to run
    # in batch mode, without a graphical user interface.
    self.logic = StenosisMeasurement2DLogic()
    self.ui.parameterSetSelector.addAttribute("vtkMRMLScriptedModuleNode", "ModuleName", self.moduleName)

    # Connections

    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    # Buttons
    self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)

    # Options menu
    self._optionsMainMenu = self.ui.applyButton.menu()
    self._optionsMainMenu.clear()
    self._optionsMainMenu.setToolTipsVisible(True)
    self._optionsSubMenu1 = qt.QMenu(_("More options"))
    self._optionsSubMenu1.setToolTipsVisible(True)
    self._applyToAllSegmentsAction = self._optionsMainMenu.addAction(_("Apply to all segments"))
    self._applyToAllSegmentsAction.setCheckable(True)
    self._applyToAllSegmentsAction.setToolTip(_("If unchecked, only the selected segment will be processed."))
    self._limitToClosestIslandsAction = self._optionsMainMenu.addAction("Limit to closest island")
    self._limitToClosestIslandsAction.setCheckable(True)
    self._limitToClosestIslandsAction.checked = True
    self._limitToClosestIslandsAction.setToolTip(_("Calculate the surface area of the closest island to the ficucial control point."))
    self._optionsMainMenu.addMenu(self._optionsSubMenu1)

    self._createOutputModelsAction = self._optionsSubMenu1.addAction(_("Create an output model."))
    self._createOutputModelsAction.setCheckable(True)
    self._createOutputModelsAction.checked = True
    self._createOutputModelsAction.setToolTip(_("Create a model for each cut segment.\nThis allows to view the model from which the surface area is calculated.\n\nThe result is influenced by:\n - holes in the segments\n - point placement, if 'Closest island' option is selected,\n - smoothing level in the 'Segment editor'."))
    self._resetOrientationAction = self._optionsSubMenu1.addAction(_("Reset control point orientation"))
    self._resetOrientationAction.setCheckable(True)
    self._resetOrientationAction.setToolTip(_("Click on a control point to reset its recorded slice orientation."))
    self._optionsSubMenu1.addSeparator()
    self._restoreSliceViewsOrientation = self._optionsSubMenu1.addAction(_("Restore orientation of all slice views"))
    self._restoreSliceViewsOrientation.setToolTip(_("... to their default orientation."))

    # Application connections
    self.ui.inputFiducialSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.observeFiducialNode)
    self._restoreSliceViewsOrientation.connect("triggered()", self.restoreAllViews)

    self.ui.inputSliceNodeSelector.connect("currentNodeChanged(vtkMRMLNode*)", lambda node: self.onMrmlNodeChanged(ROLE_INPUT_SLICE, node))
    self.ui.inputFiducialSelector.connect("currentNodeChanged(vtkMRMLNode*)", lambda node: self.onMrmlNodeChanged(ROLE_INPUT_FIDUCIAL, node)) # Must be after the first connection.
    self.ui.inputSegmentSelector.connect("currentNodeChanged(vtkMRMLNode*)", lambda node: self.onMrmlNodeChanged(ROLE_INPUT_SEGMENTATION, node))
    self.ui.inputSegmentSelector.connect("currentSegmentChanged(QString)", lambda value: self.onStringChanged(ROLE_INPUT_SEGMENT, value))

    self._applyToAllSegmentsAction.connect("toggled(bool)", lambda value: self.onBooleanToggled(ROLE_APPLY_TO_ALL_SEGMENTS, value))
    self._limitToClosestIslandsAction.connect("toggled(bool)", lambda value: self.onBooleanToggled(ROLE_LIMIT_TO_CLOSEST_ISLAND, value))
    self._createOutputModelsAction.connect("toggled(bool)", lambda value: self.onBooleanToggled(ROLE_CREATE_OUTPUT_MODEL, value))
    self._resetOrientationAction.connect("toggled(bool)", lambda value: self.onBooleanToggled(ROLE_RESET_ORIENTATION, value))

    self.ui.parameterSetSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.setParameterNode)
    self.ui.parameterSetUpdateUIToolButton.connect("clicked(bool)", self.onParameterSetUpdateUiClicked)

    # Prepare the tree table.
    outputTree = self.ui.outputTreeWidget
    outputTree.setColumnCount(3)
    columnLabels = (_("Control point"), _("Segment"), _("Surface area"))
    outputTree.setHeaderLabels(columnLabels)
    outputTree.connect("currentItemChanged(QTreeWidgetItem*, QTreeWidgetItem*)", self._onTreeItemChanged)

    # Make sure parameter node is initialized (needed for module reload)
    self.initializeParameterNode()

  # Show or hide the output model.
  def onShowModelCheckBox2(self, checkStatus) -> None:
    treeItem = self.ui.outputTreeWidget.currentItem()
    if (not treeItem):
      self.showStatusMessage((_("No item is currently selected in the tree widget."),), True)
      return
    cutModel = treeItem.data(2, qt.Qt.UserRole)
    if (cutModel):
      cutModel.SetDisplayVisibility(checkStatus)

  # Show or hide the input segment.
  def onShowSegmentCheckBox2(self, checkStatus) -> None:
    segmentation = self.ui.inputSegmentSelector.currentNode()
    if not segmentation:
        self.showStatusMessage((_("Input segmentation is invalid"),), True)
        return
    treeItem = self.ui.outputTreeWidget.currentItem()
    if (not treeItem):
      self.showStatusMessage((_("No item is currently selected in the tree widget."),), True)
      return
    segmentID = treeItem.data(1, qt.Qt.UserRole)
    if (segmentID):
      segmentation.GetDisplayNode().SetSegmentVisibility(segmentID, checkStatus)

  def cleanup(self) -> None:
    """
    Called when the application closes and the module widget is destroyed.
    """
    self.removeObservers()
    # Remove our observations.
    inputFiducialNode = self._parameterNode.GetNodeReference(ROLE_INPUT_FIDUCIAL)
    if inputFiducialNode and self.fiducialDisplayNodeObservation:
        inputFiducialNode.RemoveObserver(self.fiducialDisplayNodeObservation)

  def enter(self) -> None:
    """
    Called each time the user opens this module.
    """
    # Make sure parameter node exists and observed
    self.initializeParameterNode()
    # Observe input fiducial.
    inputFiducialNode = self._parameterNode.GetNodeReference(ROLE_INPUT_FIDUCIAL)
    if inputFiducialNode:
        self.observeFiducialNode(inputFiducialNode)

  def exit(self) -> None:
    """
    Called each time the user opens a different module.
    """
    # Unobserve input fiducial.
    inputFiducialNode = self._parameterNode.GetNodeReference(ROLE_INPUT_FIDUCIAL)
    if inputFiducialNode and self.fiducialDisplayNodeObservation:
        inputFiducialNode.RemoveObserver(self.fiducialDisplayNodeObservation)

  def onSceneStartClose(self, caller, event) -> None:
    """
    Called just before the scene is closed.
    """
    # Unobserve input fiducial.
    inputFiducialNode = self._parameterNode.GetNodeReference(ROLE_INPUT_FIDUCIAL)
    if inputFiducialNode and self.fiducialDisplayNodeObservation:
        inputFiducialNode.RemoveObserver(self.fiducialDisplayNodeObservation)
    # Parameter node will be reset, do not use it anymore
    self.setParameterNode(None)

  def onSceneEndClose(self, caller, event) -> None:
    """
    Called just after the scene is closed.
    """
    # If this module is shown while the scene is closed then recreate a new parameter node immediately
    if self.parent.isEntered:
      self.initializeParameterNode()

  def initializeParameterNode(self) -> None:
    """
    Ensure parameter node exists and observed.
    """
    # Parameter node stores all user choices in parameter values, node selections, etc.
    # so that when the scene is saved and reloaded, these settings are restored.

    # The initial parameter node originates from logic and is picked up by the parameter set combobox.
    # Other parameter nodes are created by the parameter set combobox and used here.
    if not self._parameterNode:
      self.setParameterNode(self.logic.getParameterNode())
      wasBlocked = self.ui.parameterSetSelector.blockSignals(True)
      self.ui.parameterSetSelector.setCurrentNode(self._parameterNode)
      self.ui.parameterSetSelector.blockSignals(wasBlocked)

  def setParameterNode(self, inputParameterNode: slicer.vtkMRMLScriptedModuleNode) -> None:
    if inputParameterNode == self._parameterNode:
      return
    self._parameterNode = inputParameterNode

    if self._parameterNode:
      self.setDefaultParameters()
      self.updateGUIFromParameterNode()

  def setDefaultParameters(self):
    if not self._parameterNode:
      return

    # Ensure all parameters exist in the parameter node.
    # Existing parameters are not modified.
    if (not self._parameterNode.HasParameter(ROLE_APPLY_TO_ALL_SEGMENTS)):
      self._parameterNode.SetParameter(ROLE_APPLY_TO_ALL_SEGMENTS, str(0))
    if (not self._parameterNode.HasParameter(ROLE_LIMIT_TO_CLOSEST_ISLAND)):
      self._parameterNode.SetParameter(ROLE_LIMIT_TO_CLOSEST_ISLAND, str(1))
    if (not self._parameterNode.HasParameter(ROLE_CREATE_OUTPUT_MODEL)):
      self._parameterNode.SetParameter(ROLE_CREATE_OUTPUT_MODEL, str(1))
    if (not self._parameterNode.HasParameter(ROLE_RESET_ORIENTATION)):
      self._parameterNode.SetParameter(ROLE_RESET_ORIENTATION, str(0))

  def onApplyButton(self) -> None:
    mrmlSliceNode = self._parameterNode.GetNodeReference(ROLE_INPUT_SLICE)
    fiducialNode = self._parameterNode.GetNodeReference(ROLE_INPUT_FIDUCIAL)
    segmentationNode = self._parameterNode.GetNodeReference(ROLE_INPUT_SEGMENTATION)
    segmentID = self._parameterNode.GetParameter(ROLE_INPUT_SEGMENT)
    closestIsland = int(self._parameterNode.GetParameter(ROLE_LIMIT_TO_CLOSEST_ISLAND))
    applyToAllSegments = int(self._parameterNode.GetParameter(ROLE_APPLY_TO_ALL_SEGMENTS))
    optionCreateCutModel = int(self._parameterNode.GetParameter(ROLE_CREATE_OUTPUT_MODEL))
    
    if not mrmlSliceNode:
      self.showStatusMessage((_("Select a slice node"),), True)
      return
    if not fiducialNode:
      self.showStatusMessage((_("Select a fiducial node"),), True)
      return
    if not segmentationNode:
      self.showStatusMessage((_("Select a segmentation node"),), True)
      return
    if int(self.currentControlPointID) < 0:
      self.showStatusMessage((_("Click on a fiducial control point"),), True)
      return
    with slicer.util.tryWithErrorDisplay(_("Failed to compute results."), waitCursor=True):
      # Get control point index, position and label.
      controlPointIndex = fiducialNode.GetNthControlPointIndexByID(self.currentControlPointID)
      currentControlPointPosition = fiducialNode.GetNthControlPointPositionWorld(controlPointIndex)
      currentControlPointLabel = fiducialNode.GetNthControlPointLabel(controlPointIndex)

      # Define more parameters for logic functions.
      center = (currentControlPointPosition.GetX(),
                currentControlPointPosition.GetY(),
                currentControlPointPosition.GetZ())
      sliceToRAS = mrmlSliceNode.GetSliceToRAS()
      normal = (sliceToRAS.GetElement(0, 2),
                sliceToRAS.GetElement(1, 2),
                sliceToRAS.GetElement(2, 2))
      tuples = {}
      # Call logic functions.
      if applyToAllSegments:
          # tuples is a dictionary: [segmentID] = (area, model)
          tuples = self.logic.processVisibleSegments(segmentationNode,
                          center, normal, closestIsland,
                          optionCreateCutModel, currentControlPointLabel)
      else:
          segment = segmentationNode.GetSegmentation().GetSegment(segmentID)
          modelName = currentControlPointLabel + "_" + segment.GetName()
          tuple = self.logic.processSegment(segmentationNode, segmentID,
                          center, normal, closestIsland,
                          optionCreateCutModel, currentControlPointLabel)
          tuples[segmentID] = tuple
      # Append results in table.
      self.populateOutputTable(tuples)

  def onParameterSetUpdateUiClicked(self):
    if not self._parameterNode:
      return

    inputSegmentation = self._parameterNode.GetNodeReference(ROLE_INPUT_SEGMENTATION)

    if inputSegmentation:
      # Create segment editor object if needed.
      segmentEditorModuleWidget = slicer.util.getModuleWidget("SegmentEditor")
      seWidget = segmentEditorModuleWidget.editor
      seWidget.setSegmentationNode(inputSegmentation)

  def onMrmlNodeChanged(self, role, node):
    if self._parameterNode:
      self._parameterNode.SetNodeReferenceID(role, node.GetID() if node else None)

  def onBooleanToggled(self, role, checked):
    if self._parameterNode:
      self._parameterNode.SetParameter(role, str(1) if checked else str(0))

  def onStringChanged(self, role, value):
    if self._parameterNode:
      self._parameterNode.SetParameter(role, value)

  def updateGUIFromParameterNode(self):
    if self._parameterNode is None or self._updatingGUIFromParameterNode:
        return

    # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
    self._updatingGUIFromParameterNode = True

    self.ui.inputSliceNodeSelector.setCurrentNode(self._parameterNode.GetNodeReference(ROLE_INPUT_SLICE))
    self.ui.inputFiducialSelector.setCurrentNode(self._parameterNode.GetNodeReference(ROLE_INPUT_FIDUCIAL))
    self.ui.inputSegmentSelector.setCurrentNode(self._parameterNode.GetNodeReference(ROLE_INPUT_SEGMENTATION))
    self.ui.inputSegmentSelector.setCurrentSegmentID(self._parameterNode.GetParameter(ROLE_INPUT_SEGMENT))
    
    self._applyToAllSegmentsAction.setChecked(int(self._parameterNode.GetParameter(ROLE_APPLY_TO_ALL_SEGMENTS)))
    self._limitToClosestIslandsAction.setChecked(int(self._parameterNode.GetParameter(ROLE_LIMIT_TO_CLOSEST_ISLAND)))
    self._createOutputModelsAction.setChecked(int(self._parameterNode.GetParameter(ROLE_CREATE_OUTPUT_MODEL)))
    self._resetOrientationAction.setChecked(int(self._parameterNode.GetParameter(ROLE_RESET_ORIENTATION)))

    self._updatingGUIFromParameterNode = False

  # Get a top level tree item by the fiducial node it is referencing.
  def _getTreeTopLevelItemByFiducialNode(self, tree, fiducialNode):
    if (not tree) or (not fiducialNode):
      return None
    for i in range(tree.topLevelItemCount):
      item = tree.topLevelItem(i)
      itemData = item.data(0, qt.Qt.UserRole)
      if (itemData) and (itemData == fiducialNode):
        return item
    return None

  # Get a tree item by the crontrol point ID it is referencing.
  def _getTreeItemByControlPointId(self, parentItem, controlPoindId):
    if (not parentItem) or (int(controlPoindId) < 0):
      return None
    for i in range(parentItem.childCount()):
      childItem = parentItem.child(i)
      if (childItem.data(0, qt.Qt.UserRole) == controlPoindId):
        return childItem
    return None

  # Remove the current tree item or top level tree item.
  def _removeCurrentTreeItem(self):
    outputTree = self.ui.outputTreeWidget
    treeItem = outputTree.currentItem()
    if (not treeItem):
      self.showStatusMessage((_("No item is currently selected in the tree widget."),), True)
      return
    if (treeItem.parent()):
      treeItem.parent().removeChild(treeItem)
    else:
      # Top level tree item.
      outputTree.invisibleRootItem().removeChild(treeItem)

  # In a tree item, place the tool button (input widget) in a parent QWidget
  # having a horizontal layout and a stretch on its right.
  def _constrainWidgetInHLayout(self, widget):
    newWidget = qt.QWidget()
    newWidget.setObjectName(self.moduleName + ".TreeWidgetItemWidget")
    newWidget.setFocusPolicy(qt.Qt.FocusPolicy.StrongFocus)
    hlayout = qt.QHBoxLayout()
    newWidget.setLayout(hlayout)
    hlayout.addWidget(widget)
    hlayout.addStretch()
    widget.setSizePolicy(qt.QSizePolicy.Minimum, qt.QSizePolicy.Fixed)
    widget.setVisible(False)

    return newWidget

  # Let the tool button be visible in the curretnyt tree item only.
  def _onTreeItemChanged(self, currentItem, previousItem):
    controllerObjectName = self.moduleName + ".TreeWidgetItemController"
    outputTree = self.ui.outputTreeWidget
    for item in (currentItem, previousItem):
      if (not item):
        continue
      for i in range(outputTree.columnCount):
        # In this tree item, find the widget containing the tool button in it's layout.
        widget = outputTree.itemWidget(item, i)
        if (not widget) or (widget.objectName != self.moduleName + ".TreeWidgetItemWidget"):
          continue
        # Find the tool button.
        controller = widget.findChild(qt.QToolButton, controllerObjectName)
        if (controller):
          controller.setVisible(item == currentItem)

  # When the menu is opened, synchronise the visibily status of the segment or cut model
  # with the checked property of the menu actions.
  def _onTreeItemControllerMenuAboutToShow(self):
    menu = None
    outputTree = self.ui.outputTreeWidget
    treeItem = outputTree.currentItem()
    # Find the tool button and the menu.
    controllerObjectName = self.moduleName + ".TreeWidgetItemController"
    for i in range(outputTree.columnCount):
      widget = outputTree.itemWidget(treeItem, i)
      if (not widget) or (widget.objectName != self.moduleName + ".TreeWidgetItemWidget"):
        continue
      controller = widget.findChild(qt.QToolButton, controllerObjectName)
      if (controller):
        menu = controller.menu()
    if (not menu):
      return
    # Find and synchronise the menu action handling the segment's visibility.
    showSegmentAction = menu.findChild(qt.QAction, self.moduleName + ".ShowSegmentAction")
    if (showSegmentAction):
      segmentation = self.ui.inputSegmentSelector.currentNode()
      treeItem = self.ui.outputTreeWidget.currentItem()
      if segmentation and treeItem:
        segmentID = treeItem.data(1, qt.Qt.UserRole)
        if (segmentID):
          showSegmentAction.setChecked(segmentation.GetDisplayNode().GetSegmentVisibility(segmentID))
    # # Find and synchronise the menu action handling the model's visibility.
    showModelAction = menu.findChild(qt.QAction, self.moduleName + ".ShowModelAction")
    if (showModelAction):
      treeItem = self.ui.outputTreeWidget.currentItem()
      if (treeItem):
        cutModel = treeItem.data(2, qt.Qt.UserRole)
        if (cutModel):
          showModelAction.setChecked(cutModel.GetDisplayVisibility())

  # Append mode only. tuples is a dictionary: [segmentID] = (area, model)
  def populateOutputTable(self, tuples) -> None:
    fiducialNode = self._parameterNode.GetNodeReference(ROLE_INPUT_FIDUCIAL)
    # Get current control point label.
    controlPointIndex = fiducialNode.GetNthControlPointIndexByID(self.currentControlPointID)
    controlPointLabel = fiducialNode.GetNthControlPointLabel(controlPointIndex)
    # Get the list of segment IDs.
    segmentIDs = tuples.keys()

    segmentation = self.ui.inputSegmentSelector.currentNode()
    outputTree = self.ui.outputTreeWidget
    
    # Create a top level item for the fiducial node.
    topLevelItem = self._getTreeTopLevelItemByFiducialNode(outputTree, fiducialNode)
    if (not topLevelItem):
      topLevelItem = qt.QTreeWidgetItem()
      outputTree.addTopLevelItem(topLevelItem)
      topLevelItem.setText(0, fiducialNode.GetName())
      topLevelItem.setData(0, qt.Qt.UserRole, fiducialNode)
      topLevelItem.setExpanded(True)
      # Add a tool button for the removal of the top level item.
      topLevelItemController = qt.QToolButton()
      topLevelItemController.setObjectName(self.moduleName + ".TreeWidgetItemController")
      topLevelItemController.setText("-")
      topLevelItemController.setToolTip(_("Remove this item."))
      topLevelItemController.connect("clicked()", self._removeCurrentTreeItem)
      topLevelItemWidget = self._constrainWidgetInHLayout(topLevelItemController)
      outputTree.setItemWidget(topLevelItem, 2, topLevelItemWidget)
    # Create a tree item for the control point of the fiducial node, identified by the control point's ID.
    controlPointItem = self._getTreeItemByControlPointId(topLevelItem, self.currentControlPointID)
    if (not controlPointItem):
      controlPointItem = qt.QTreeWidgetItem() # For the control point
      topLevelItem.addChild(controlPointItem)
      controlPointItem.setText(0, controlPointLabel)
      controlPointItem.setData(0, qt.Qt.UserRole, self.currentControlPointID)
      controlPointItem.setExpanded(True)
      # Add a tool button for the removal of this item.
      controlPointItemController = qt.QToolButton()
      controlPointItemController.setObjectName(self.moduleName + ".TreeWidgetItemController")
      controlPointItemController.setText("-")
      controlPointItemController.setToolTip(_("Remove this item."))
      controlPointItemController.connect("clicked()", self._removeCurrentTreeItem)
      controlPointItemWidget = self._constrainWidgetInHLayout(controlPointItemController)
      outputTree.setItemWidget(controlPointItem, 2, controlPointItemWidget)

    # Get unit for area.
    selectionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLSelectionNodeSingleton")
    areaUnitNode = slicer.mrmlScene.GetNodeByID(selectionNode.GetUnitNodeID("area"))
    # For each segment, create a tree item with a tool button, the segment name and area.
    for segmentID in segmentIDs:
        measurementItem = qt.QTreeWidgetItem()
        controlPointItem.addChild(measurementItem)
        """
        Add a tool button in column 0 with a menu that
        - allows to remove this tree item,
        - handles the visibility of the segment,
        - handles the visibility of the cut model.
        """
        measurementController = qt.QToolButton()
        measurementController.setObjectName(self.moduleName + ".TreeWidgetItemController")
        measurementControllerMenu = qt.QMenu(measurementController)
        removeMeasurementAction = measurementControllerMenu.addAction(_("Remove"))
        removeMeasurementAction.setObjectName(self.moduleName + ".RemoveMeasurementAction")
        removeMeasurementAction.connect("triggered()", self._removeCurrentTreeItem)
        showSegmentAction = measurementControllerMenu.addAction(_("Segment visibility"))
        showSegmentAction.setObjectName(self.moduleName + ".ShowSegmentAction")
        showSegmentAction.setCheckable(True)
        showSegmentAction.connect("toggled(bool)", self.onShowSegmentCheckBox2)
        showModelAction = measurementControllerMenu.addAction(_("Model visibility"))
        showModelAction.setObjectName(self.moduleName + ".ShowModelAction")
        showModelAction.setCheckable(True)
        showModelAction.connect("toggled(bool)", self.onShowModelCheckBox2)
        measurementController.setMenu(measurementControllerMenu)
        measurementController.connect("clicked()", measurementController.showMenu)
        measurementControllerWidget = self._constrainWidgetInHLayout(measurementController)
        measurementControllerMenu.connect("aboutToShow()", self._onTreeItemControllerMenuAboutToShow)
        outputTree.setItemWidget(measurementItem, 0, measurementControllerWidget)
        # Show the segment name in column 1, and reference the segment ID.
        measurementItem.setData(1, qt.Qt.UserRole, segmentID)
        measurementItem.setText(1, segmentation.GetSegmentation().GetSegment(segmentID).GetName())
        # Show the area in column 2, and reference the cut model.
        cutModel = tuples[segmentID][1]
        measurementItem.setData(2, qt.Qt.UserRole, cutModel)
        area = areaUnitNode.GetDisplayStringFromValue(tuples[segmentID][0])
        measurementItem.setText(2, area)

  # messages is a sequence.
  def showStatusMessage(self, messages, console = False) -> None:
    separator = " "
    msg = separator.join(messages)
    slicer.util.showStatusMessage(msg, 3000)
    slicer.app.processEvents()
    if console:
        logging.info(msg)

  # Convenience process to track the slice orientation at control points.
  # Called when a fiducial node is clicked.
  def observeFiducialNode(self, fiducialNode) -> None:
    if self._parameterNode is None:
      return

    inputFiducialNode = self._parameterNode.GetNodeReference(ROLE_INPUT_FIDUCIAL)
    if inputFiducialNode and inputFiducialNode.GetDisplayNode() and self.fiducialDisplayNodeObservation:
        # Unobserve an already observed input fiducial node.
        inputFiducialNode.GetDisplayNode().RemoveObserver(self.fiducialDisplayNodeObservation)
        self.fiducialDisplayNodeObservation = None
        message = (_("Fiducial node is no longer observed"),)
        self.showStatusMessage(message)
    # Observe a selected fiducial node.
    displayNode = fiducialNode.GetDisplayNode() if fiducialNode else None
    if displayNode:
        self.fiducialDisplayNodeObservation = displayNode.AddObserver(slicer.vtkMRMLMarkupsFiducialDisplayNode.JumpToPointEvent, self.onJumpToPoint)
        message = (_("Fiducial node is being observed"),)
        self.showStatusMessage(message)

  """
  Store, restore or reset the orientation part of a sliceToRAS matrix with/from
  a control point's Get/SetOrientation() function.
  """
  def onJumpToPoint(self, caller, event) -> None:
    fiducialNode = caller.GetMarkupsNode()
    controlPointIndex = caller.GetActiveControlPoint()
    # Use the UI input slice node.
    mrmlSliceNode = self._parameterNode.GetNodeReference(ROLE_INPUT_SLICE)
    if not mrmlSliceNode:
        message = (_("Slice node not set"),)
        self.showStatusMessage(message, True)
        return
    # Get control point orientation matrix.
    self.currentControlPointID = fiducialNode.GetNthControlPointID(controlPointIndex)
    controlPointOrientationMatrix = vtk.vtkMatrix3x3()
    fiducialNode.GetNthControlPointOrientationMatrixWorld(controlPointIndex, controlPointOrientationMatrix)
    sliceToRAS = mrmlSliceNode.GetSliceToRAS()
    # Control point orientation has not been set, or has been reset.
    if controlPointOrientationMatrix.IsIdentity():
        # Store the orientation part of a sliceToRAS matrix.
        sliceToRASOrientationMatrix = vtk.vtkMatrix3x3()
        for col in range(3):
            for row in range(3):
                value = sliceToRAS.GetElement(row, col)
                sliceToRASOrientationMatrix.SetElement(row, col, value)
        fiducialNode.SetNthControlPointOrientationMatrixWorld(controlPointIndex, sliceToRASOrientationMatrix)
        message = (_("Slice orientation recorded"),)
        self.showStatusMessage(message)
    else:
        # Restore the orientation part of a sliceToRAS matrix.
        for col in range(3):
            for row in range(3):
                value = controlPointOrientationMatrix.GetElement(row, col)
                sliceToRAS.SetElement(row, col, value)
        # Update slice orientation in UI.
        mrmlSliceNode.UpdateMatrices()
        message = (_("Slice orientation restored"),)
        self.showStatusMessage(message)

    # Execute a request to reset a control point orientation matrix.
    if self._resetOrientationAction.checked:
        identityMatrix = vtk.vtkMatrix3x3()
        fiducialNode.SetNthControlPointOrientationMatrixWorld(controlPointIndex, identityMatrix)
        message = (_("Reset orientation at point"), fiducialNode.GetNthControlPointLabel(controlPointIndex))
        self.showStatusMessage(message)
    # Always set the checkbox to false.
    self._resetOrientationAction.checked = False

  """
  Helper function.
  If we use 'Ctrl+Alt+Left click' to orient the input slice view, the other
  slice views will change too. We can thus restore default orientation for all
  views, then click on a control point to orient the input slice view only.
  A single slice view's orientation may also be defined with the 'Reformat
  widget', or in the 'Reformat' module.
  """
  def restoreAllViews(self) -> None:
    views = slicer.app.layoutManager().sliceViewNames()
    for view in views:
        sliceNode = slicer.app.layoutManager().sliceWidget(view).mrmlSliceNode()
        sliceNode.SetOrientationToDefault()
#
# StenosisMeasurement2DLogic
#

class StenosisMeasurement2DLogic(ScriptedLoadableModuleLogic):
  def __init__(self) -> None:
    """
    Called when the logic class is instantiated. Can be used for initializing member variables.
    """
    ScriptedLoadableModuleLogic.__init__(self)

  # Core function.
  def processSegment(self, inputSegmentation, segmentID,
                    center, normal, closestIsland = True,
                    createModel = False, controlPointLabel = None):
    if not inputSegmentation:
      raise ValueError(_("Input segmentation is invalid"))
    if segmentID == "":
      raise ValueError(_("Input segment ID is invalid"))

    import time
    startTime = time.time()
    logging.info(_("Processing started"))

    # ---------------------- Generate cut polydata ---------
    closedSurfacePolyData = vtk.vtkPolyData()
    inputSegmentation.CreateClosedSurfaceRepresentation()
    inputSegmentation.GetClosedSurfaceRepresentation(segmentID, closedSurfacePolyData)
    # Cut the segment.
    plane = vtk.vtkPlane()
    plane.SetOrigin(center)
    plane.SetNormal(normal)

    result = vtk.vtkPolyData()
    import vtkSlicerCrossSectionAnalysisModuleLogicPython as vtkSlicerCrossSectionAnalysisModuleLogic
    crossSectionWorker = vtkSlicerCrossSectionAnalysisModuleLogic.vtkCrossSectionCompute()
    ret = crossSectionWorker.CreateCrossSection(result, closedSurfacePolyData, plane,
                                                 crossSectionWorker.ClosestPoint if closestIsland else crossSectionWorker.AllRegions,
                                                 True)
    if (ret != crossSectionWorker.Success):
      logging.error("Error creating a cross-section polydata of the segment: #" + str(ret))

    # Get surface area
    massProperties = vtk.vtkMassProperties()
    massProperties.SetInputData(result)
    massProperties.Update()
    surfaceArea = massProperties.GetSurfaceArea()

    # Create a model of the polydata. Hidden by default, with no lighting.
    cutModel = None
    if createModel:
        cutModel = slicer.modules.models.logic().AddModel(result)
        cutModel.SetDisplayVisibility(False)
        cutModel.GetDisplayNode().SetLighting(False)
        cutModel.GetDisplayNode().SetScalarVisibility(not closestIsland)
        # Set model's name: control point label + segment name.
        segment = inputSegmentation.GetSegmentation().GetSegment(segmentID)
        if controlPointLabel and segment:
            modelName = controlPointLabel + "_" + segment.GetName()
            cutModel.SetName(modelName)
        # The model's color follows the segment's colour.
        # If closestIsland is False, the displayed colour depends on the scalar value of each region.
        if segment:
            cutModel.GetDisplayNode().SetColor(segment.GetColor())

    stopTime = time.time()
    durationValue = '%.2f' % (stopTime - startTime)
    logging.info(_("Processing completed in {duration} seconds").format(duration = durationValue))
    return (surfaceArea, cutModel)

  # Helper function.
  def processVisibleSegments(self, inputSegmentation,
              center, normal, closestIsland = True,
              createModel = False, controlPointLabel = None):
    visibleSegmentIDs = vtk.vtkStringArray()
    inputSegmentation.GetDisplayNode().GetVisibleSegmentIDs(visibleSegmentIDs)
    tuples = {}
    for segmentIndex in range(visibleSegmentIDs.GetNumberOfValues()):
        segmentID = visibleSegmentIDs.GetValue(segmentIndex)
        tuple = self.processSegment(inputSegmentation, segmentID,
                        center, normal, closestIsland,
                        createModel, controlPointLabel)
        tuples[segmentID] = tuple
    return tuples

#
# StenosisMeasurement2DTest
#

class StenosisMeasurement2DTest(ScriptedLoadableModuleTest):
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
    self.test_StenosisMeasurement2D1()

  def test_StenosisMeasurement2D1(self):
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

# Parameter node role names
ROLE_INPUT_SLICE = "InputSlice"
ROLE_INPUT_FIDUCIAL = "InputFiducial"
ROLE_INPUT_SEGMENTATION = "InputSegmentation"
ROLE_INPUT_SEGMENT = "InputSegment"
ROLE_APPLY_TO_ALL_SEGMENTS = "ApplyToAllSegments"
ROLE_LIMIT_TO_CLOSEST_ISLAND = "LimitToClosestIsland"
ROLE_CREATE_OUTPUT_MODEL = "CreateOutputModel"
ROLE_RESET_ORIENTATION = "ResetControlPointOrientation"

