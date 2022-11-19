import os
import unittest
import logging
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

#
# StenosisMeasurement2D
#

class StenosisMeasurement2D(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Stenosis measurement : 2D"
    self.parent.categories = ["Vascular Modeling Toolkit"]
    self.parent.dependencies = []
    self.parent.contributors = ["Saleem Edah-Tally [Surgeon] [Hobbyist developer]", "Andras Lasso, PerkLab"]
    self.parent.helpText = """
This <a href="https://github.com/vmtk/SlicerExtension-VMTK/">module</a> calculates the surface area of segments cut by a slice plane in its orientation. It is intended for quick two dimensional arterial stenosis evaluation, but is actually purpose agnostic.
"""
    # TODO: replace with organization, grant and thanks
    self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
"""

class StenosisMeasurement2DWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
    self.currentFiducialNode = None
    self.currentControlPointID = "-1" # API gets/sets it as a string

    # Observe JumpToPointEvent of the fiducial display node.
    self.fiducialDisplayNodeObservation = None
    # Menus
    self.tableMenu = qt.QMenu()

  def setup(self):
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
    
    # Connections

    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
    # (in the selected parameter node).
    self.ui.inputSliceNodeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.inputFiducialSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.inputSegmentSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.applyToAllSegmentsCheckBox.connect("toggled(bool)", self.updateParameterNodeFromGUI)
    self.ui.limitToClosestIslandCheckBox.connect("toggled(bool)", self.updateParameterNodeFromGUI)

    # Buttons
    self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)

    # Make sure parameter node is initialized (needed for module reload)
    self.initializeParameterNode()
    
    # Application connections
    self.ui.inputFiducialSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.observeFiducialNode)
    self.ui.resetSliceViewsPushButton.connect("clicked()", self.restoreAllViews)
    
    # Defaults
    self.ui.optionsCollapsibleButton.collapsed = True
    self.ui.moreOptionsCollapsibleGroupBox.collapsed = True
    # Prepare table
    outputTable = self.ui.outputTableWidget
    outputTable.setColumnCount(5)
    columnLabels = ("Control point", "Segment", "Surface area", "Model visibility", "Segment visibility")
    outputTable.setHorizontalHeaderLabels(columnLabels)
    """
    We need a currentRow() when we toggle the visibility of an output model.
    The row is selected in a lambda function.
    But we don't need to select the whole row visually.
    """
    outputTable.setSelectionMode(qt.QAbstractItemView.SelectItems)
    """
    Table context menu.
    Using self.parent as the menu's parent allows the menu items to lay in the
    foreground.
    """
    outputTable.setContextMenuPolicy(qt.Qt.CustomContextMenu)
    outputTable.connect("customContextMenuRequested(QPoint)", self.showTableMenu)
    outputTable.connect("currentCellChanged(int, int, int, int)", self.onCurrentRowChanged)

  def showTableMenu(self, qpoint):
    # Start from zero.
    self.tableMenu.clear()
    
    """
    If we do this in setup, when we first enter the module, a weird background
    rectangle is seen from the left of the module window.
    Just workaround it.
    """
    self.tableMenu.setParent(self.parent)
    
    # Simple menu item to remove a single row.
    actionRemoveRow = self.tableMenu.addAction("Remove row")
    actionRemoveRow.setData(OUTPUT_TABLE_MENU_REMOVE_ROW)
    actionRemoveRow.connect("triggered()", self.onTableMenuItem)
    
    # Simple menu item to remove all rows.
    actionEmptyTable = self.tableMenu.addAction("Empty table")
    actionEmptyTable.setData(OUTPUT_TABLE_MENU_EMPTY_TABLE)
    actionEmptyTable.connect("triggered()", self.onTableMenuItem)
    
    self.tableMenu.addSeparator()
    # Clicking anywhere does not hide menu.
    actionCancel = self.tableMenu.addAction("Dismiss menu")
    actionCancel.connect("triggered()", self.onTableMenuItem)
    """
    Set menu position.
    In developer mode, the height of the additional collapsible button is not
    taken into account, and influences the menu position.
    """
    outputTableWidget = self.ui.outputTableWidget
    menuPosition = qt.QPoint()
    menuPosition.setX(qpoint.x() + outputTableWidget.x)
    menuPosition.setY(qpoint.y() + outputTableWidget.y)
    self.tableMenu.popup(menuPosition)
    
  def onTableMenuItem(self):
    action = self.tableMenu.activeAction()
    data = action.data()
    outputTable = self.ui.outputTableWidget
    # Remove the current row.
    if data == OUTPUT_TABLE_MENU_REMOVE_ROW:
        self.removeTableRow(outputTable.currentRow())
    # Remove all rows.
    elif data == OUTPUT_TABLE_MENU_EMPTY_TABLE:
        while (outputTable.rowCount):
            self.removeTableRow(0)
    self.tableMenu.hide()

  # Remove a single table row and an associated model.
  def removeTableRow(self, rowIndex):
    outputTable = self.ui.outputTableWidget
    fiducialCellItem = outputTable.item(rowIndex, 0)
    if fiducialCellItem:
        cutModel = fiducialCellItem.data(qt.Qt.UserRole)
        if cutModel:
            slicer.mrmlScene.RemoveNode(cutModel)
    outputTable.removeRow(rowIndex)

  # Show or hide the output model.
  def onShowModelCheckBox(self, checkStatus):
    outputTable = self.ui.outputTableWidget
    fiducialCellItem = outputTable.item(outputTable.currentRow(), 0)
    if fiducialCellItem:
        cutModel = fiducialCellItem.data(qt.Qt.UserRole)
        if cutModel:
            cutModel.SetDisplayVisibility(checkStatus)

  # Show or hide the input segment.
  def onShowSegmentCheckBox(self, checkStatus):
    segmentation = self.ui.inputSegmentSelector.currentNode()
    if not segmentation:
        self.showStatusMessage(("Input segmentation is invalid",), True)
        return
    outputTable = self.ui.outputTableWidget
    segmentCellItem = outputTable.item(outputTable.currentRow(), 1)
    if segmentCellItem:
        segmentID = segmentCellItem.data(qt.Qt.UserRole)
        if (segmentID):
             segmentation.GetDisplayNode().SetSegmentVisibility(segmentID, checkStatus)

  def cleanup(self):
    """
    Called when the application closes and the module widget is destroyed.
    """
    self.removeObservers()
    # Remove our observations.
    if self.currentFiducialNode and self.fiducialDisplayNodeObservation:
        self.currentFiducialNode.RemoveObserver(self.fiducialDisplayNodeObservation)

  def enter(self):
    """
    Called each time the user opens this module.
    """
    # Make sure parameter node exists and observed
    self.initializeParameterNode()
    # Observe input fiducial.
    if self.currentFiducialNode:
        self.observeFiducialNode(self.currentFiducialNode)

  def exit(self):
    """
    Called each time the user opens a different module.
    """
    # Do not react to parameter node changes (GUI wlil be updated when the user enters into the module)
    self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
    # Unobserve input fiducial.
    if self.currentFiducialNode and self.fiducialDisplayNodeObservation:
        self.currentFiducialNode.RemoveObserver(self.fiducialDisplayNodeObservation)

  def onSceneStartClose(self, caller, event):
    """
    Called just before the scene is closed.
    """
    # Parameter node will be reset, do not use it anymore
    self.setParameterNode(None)
    # Unobserve input fiducial.
    if self.currentFiducialNode and self.fiducialDisplayNodeObservation:
        self.currentFiducialNode.RemoveObserver(self.fiducialDisplayNodeObservation)

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
    self.ui.inputSliceNodeSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputSliceNode"))
    self.ui.inputFiducialSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputFiducial"))
    self.ui.inputSegmentSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputSegmentation"))
    self.ui.applyToAllSegmentsCheckBox.setChecked(False if (self._parameterNode.GetParameter("ApplyToAllSegments") == "0") else True)
    self.ui.limitToClosestIslandCheckBox.setChecked(False if (self._parameterNode.GetParameter("LimitToClosestIsland") == "0") else True)
    # Define input fiducial.
    fiducialNode = self.ui.inputFiducialSelector.currentNode()

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
    self._parameterNode.SetNodeReferenceID("InputSliceNode", self.ui.inputSliceNodeSelector.currentNodeID)
    self._parameterNode.SetNodeReferenceID("InputFiducial", self.ui.inputFiducialSelector.currentNodeID)
    self._parameterNode.SetNodeReferenceID("InputSegmentation", self.ui.inputSegmentSelector.currentNodeID())
    self._parameterNode.SetParameter("ApplyToAllSegments", "0" if not  self.ui.applyToAllSegmentsCheckBox.checked else "1")
    self._parameterNode.SetParameter("LimitToClosestIsland", "0" if not  self.ui.limitToClosestIslandCheckBox.checked else "1")
    
    self._parameterNode.EndModify(wasModified)

  def onApplyButton(self):
    if not self.ui.inputSliceNodeSelector.currentNode():
        self.showStatusMessage(("Select a slice node",), True)
        return
    if not self.ui.inputFiducialSelector.currentNode():
        self.showStatusMessage(("Select a fiducial node",), True)
        return
    if not self.ui.inputSegmentSelector.currentNode():
        self.showStatusMessage(("Select a segmentation node",), True)
        return
    if int(self.currentControlPointID) < 0:
        self.showStatusMessage(("Click on a fiducial control point",), True)
        return
    with slicer.util.tryWithErrorDisplay("Failed to compute results.", waitCursor=True):
        # Get control point index, position and label.
        fiducialNode = self.currentFiducialNode
        controlPointIndex = fiducialNode.GetNthControlPointIndexByID(self.currentControlPointID)
        currentControlPointPosition = fiducialNode.GetNthControlPointPositionWorld(controlPointIndex)
        currentControlPointLabel = fiducialNode.GetNthControlPointLabel(
        controlPointIndex)
        
        # Define parameters for logic functions.
        inputSegmentation = self.ui.inputSegmentSelector.currentNode()
        segmentID = self.ui.inputSegmentSelector.currentSegmentID()
        center = (currentControlPointPosition.GetX(),
                  currentControlPointPosition.GetY(),
                  currentControlPointPosition.GetZ())
        mrmlSliceNode = self.ui.inputSliceNodeSelector.currentNode()
        sliceToRAS = mrmlSliceNode.GetSliceToRAS()
        normal = (sliceToRAS.GetElement(0, 2),
                  sliceToRAS.GetElement(1, 2),
                  sliceToRAS.GetElement(2, 2))
        closestIsland = self.ui.limitToClosestIslandCheckBox.checked
        applyToAllSegments = self.ui.applyToAllSegmentsCheckBox.checked
        optionCreateCutModel = self.ui.createModelCheckBox.checked
        tuples = {}
        # Call logic functions.
        if applyToAllSegments:
            # tuples is a dictionary : [segmentID] = (area, model)
            tuples = self.logic.processVisibleSegments(inputSegmentation,
                            center, normal, closestIsland,
                            optionCreateCutModel, currentControlPointLabel)
        else:
            segment = inputSegmentation.GetSegmentation().GetSegment(segmentID)
            modelName = currentControlPointLabel + "_" + segment.GetName()
            tuple = self.logic.processSegment(inputSegmentation, segmentID,
                           center, normal, closestIsland,
                           optionCreateCutModel, currentControlPointLabel)
            tuples[segmentID] = tuple
        # Append results in table.
        self.populateOutputTable(tuples)

  # Append mode only. tuples is a dictionary : [segmentID] = (area, model)
  def populateOutputTable(self, tuples):
    fiducialNode = self.currentFiducialNode
    # Get current control point label.
    controlPointIndex = fiducialNode.GetNthControlPointIndexByID(self.currentControlPointID)
    controlPointLabel = self.currentFiducialNode.GetNthControlPointLabel(
        controlPointIndex)
    # Get list of segment IDs.
    segmentIDs = tuples.keys()
    
    segmentation = self.ui.inputSegmentSelector.currentNode()
    outputTable = self.ui.outputTableWidget
    
    # Get unit for area.
    selectionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLSelectionNodeSingleton")
    areaUnitNode = slicer.mrmlScene.GetNodeByID(selectionNode.GetUnitNodeID("area"))
    # For each segment, append control point label, segment name and area.
    # Reference the output polydata model in the label item (column 0).
    for segmentID in segmentIDs:
        rowIndex = outputTable.rowCount
        outputTable.insertRow(rowIndex)
        # Control point label
        item = qt.QTableWidgetItem()
        item.setText(controlPointLabel)
        # Reference the cut model here. We can show/hide/delete it later.
        cutModel = tuples[segmentID][1]
        item.setData(qt.Qt.UserRole, cutModel)
        outputTable.setItem(rowIndex, 0, item)
        # Segment
        item = qt.QTableWidgetItem()
        item.setText(segmentation.GetSegmentation().GetSegment(segmentID).GetName())
        item.setData(qt.Qt.UserRole, segmentID)
        outputTable.setItem(rowIndex, 1, item)
        # Surface area
        item = qt.QTableWidgetItem()
        content = areaUnitNode.GetDisplayStringFromValue(tuples[segmentID][0])
        item.setText(content)
        outputTable.setItem(rowIndex, 2, item)
        # Model visibility. Use a checkbox aligned in a layout.
        """
        The checkbox is always left aligned this way.
        Either we accept it's not good looking, or we do some more complex things.
          item = qt.QTableWidgetItem()
          item.setCheckState(False)
        https://falsinsoft.blogspot.com/2013/11/qtablewidget-center-checkbox-inside-cell.html
        """
        modelWidget = qt.QWidget()
        modelCheckBox = qt.QCheckBox(modelWidget)
        modelLayout = qt.QHBoxLayout(modelWidget)
        modelLayout.addWidget(modelCheckBox)
        modelLayout.setAlignment(qt.Qt.AlignCenter)
        modelLayout.setContentsMargins(0, 0, 0, 0)
        modelWidget.setLayout(modelLayout)
        outputTable.setCellWidget(rowIndex, 3, modelWidget)
        modelCheckBox.connect("toggled(bool)", self.onShowModelCheckBox)
        # Hide it by default. See onCurrentRowChanged() comment.
        modelCheckBox.hide()
        modelCheckBox.checked = cutModel.GetDisplayVisibility()
        
        # Segment visibility.
        segmentWidget = qt.QWidget()
        segmentCheckBox = qt.QCheckBox(segmentWidget)
        segmentLayout = qt.QHBoxLayout(segmentWidget)
        segmentLayout.addWidget(segmentCheckBox)
        segmentLayout.setAlignment(qt.Qt.AlignCenter)
        segmentLayout.setContentsMargins(0, 0, 0, 0)
        segmentWidget.setLayout(segmentLayout)
        outputTable.setCellWidget(rowIndex, 4, segmentWidget)
        segmentCheckBox.connect("toggled(bool)", self.onShowSegmentCheckBox)
        segmentCheckBox.hide()
        segmentCheckBox.checked = segmentation.GetDisplayNode().GetSegmentVisibility(segmentID)

  """
  Clicking on the model/segment visibility checkbox does not trigger anything in
  the table. Namely, no row/cell is selected. The checkbox does not know in what
  row it is. The user must select a cell. We show the checkbox in the current
  row only. Else, toggling a checkbox in another row will always toggle the
  visibility of the model/segment referenced in the current row.
  """
  def onCurrentRowChanged(self, currentRow, currentColumn, previousRow, previousColumn):
    outputTable = self.ui.outputTableWidget
    for column in 3, 4:
        previousCellWidget = outputTable.cellWidget(previousRow, column)
        if previousCellWidget:
            previousCheckBox = previousCellWidget.children()[0]
            previousCheckBox.hide()
        currentCellWidget = outputTable.cellWidget(currentRow, column)
        if currentCellWidget:
            currentCheckBox = currentCellWidget.children()[0]
            currentCheckBox.show()

  # messages is a sequence.
  def showStatusMessage(self, messages, console = False):
    separator = " "
    msg = separator.join(messages)
    slicer.util.showStatusMessage(msg, 3000)
    slicer.app.processEvents()
    if console:
        logging.info(msg)

  # Convenience process to track the slice orientation at control points.
  # Called when a fiducial node is clicked.
  def observeFiducialNode(self, fiducialNode):
    if self.currentFiducialNode and self.currentFiducialNode.GetDisplayNode() and self.fiducialDisplayNodeObservation:
        # Unobserve an already observed input fiducial node.
        self.currentFiducialNode.GetDisplayNode().RemoveObserver(self.fiducialDisplayNodeObservation)
        self.fiducialDisplayNodeObservation = None
        message = ("Fiducial node is no longer observed",)
        self.showStatusMessage(message)
    # None is selected in UI.
    if not fiducialNode:
        self.currentFiducialNode = None
        return
    # Observe a selected fiducial node.
    self.currentFiducialNode = fiducialNode
    displayNode = fiducialNode.GetDisplayNode()
    if displayNode:
        self.fiducialDisplayNodeObservation = displayNode.AddObserver(slicer.vtkMRMLMarkupsFiducialDisplayNode.JumpToPointEvent, self.onJumpToPoint)
        message = ("Fiducial node is being observed",)
        self.showStatusMessage(message)

  def GetNthControlPointOrientationMatrixWorldByID(id):
    controlPointIndex = self.fiducialNode.GetNthControlPointIndexByID(id)
    controlPointOrientationMatrix = vtk.vtkMatrix3x3()
    self.fiducialNode.GetNthControlPointOrientationMatrixWorld(controlPointIndex, controlPointOrientationMatrix)
    return controlPointOrientationMatrix

  """
  Store, restore or reset the orientation part of a sliceToRAS matrix with/from
  a control point's Get/SetOrientation() function.
  """
  def onJumpToPoint(self, caller, event):
    fiducialNode = caller.GetMarkupsNode()
    controlPointIndex = caller.GetActiveControlPoint()
    # Use the UI input slice node.
    mrmlSliceNode = self.ui.inputSliceNodeSelector.currentNode()
    if not mrmlSliceNode:
        message = ("Slice node not set",)
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
        message = ("Slice orientation recorded",)
        self.showStatusMessage(message)
    else:
        # Restore the orientation part of a sliceToRAS matrix.
        for col in range(3):
            for row in range(3):
                value = controlPointOrientationMatrix.GetElement(row, col)
                sliceToRAS.SetElement(row, col, value)
        # Update slice orientation in UI.
        mrmlSliceNode.UpdateMatrices()
        message = ("Slice orientation restored",)
        self.showStatusMessage(message)
    
    # Execute a request to reset a control point orientation matrix.
    if self.ui.resetOrientationCheckBox.checked:
        identityMatrix = vtk.vtkMatrix3x3()
        fiducialNode.SetNthControlPointOrientationMatrixWorld(controlPointIndex, identityMatrix)
        message = ("Reset orientation at point", fiducialNode.GetNthControlPointLabel(controlPointIndex))
        self.showStatusMessage(message)
    # Always set the checkbox to false.
    self.ui.resetOrientationCheckBox.checked = False

  """
  Helper function.
  If we use 'Ctrl+Alt+Left click' to orient the input slice view, the other
  slice views will change too. We can thus restore default orientation for all
  views, then click on a control point to orient the input slice view only.
  A single slice view's orientation may also be defined with the 'Reformat
  widget', or in the 'Reformat' module.
  """
  def restoreAllViews(self):
    views = slicer.app.layoutManager().sliceViewNames()
    for view in views:
        sliceNode = slicer.app.layoutManager().sliceWidget(view).mrmlSliceNode()
        sliceNode.SetOrientationToDefault()
#
# StenosisMeasurement2DLogic
#

class StenosisMeasurement2DLogic(ScriptedLoadableModuleLogic):
  def __init__(self):
    """
    Called when the logic class is instantiated. Can be used for initializing member variables.
    """
    ScriptedLoadableModuleLogic.__init__(self)

  def setDefaultParameters(self, parameterNode):
    pass

  # Core function.
  def processSegment(self, inputSegmentation, segmentID,
              center, normal, closestIsland = True,
              createModel = False, controlPointLabel = None):
    if not inputSegmentation:
      raise ValueError("Input segmentation is invalid")
    if segmentID == "":
      raise ValueError("Input segment ID is invalid")

    import time
    startTime = time.time()
    logging.info('Processing started')
    
    # ---------------------- Generate cut polydata ---------
    closedSurfacePolyData = vtk.vtkPolyData()
    inputSegmentation.CreateClosedSurfaceRepresentation()
    inputSegmentation.GetClosedSurfaceRepresentation(segmentID, closedSurfacePolyData)
    # Cut through thresholded result.
    plane = vtk.vtkPlane()
    plane.SetOrigin(center)
    plane.SetNormal(normal)
    cutter = vtk.vtkCutter()
    cutter.SetCutFunction(plane)
    cutter.SetInputData(closedSurfacePolyData)
    cutter.Update()
    # Triangulate the contour points
    contourTriangulator = vtk.vtkContourTriangulator()
    # Keep the closest closed surface
    if closestIsland:
        connectivityFilter = vtk.vtkConnectivityFilter()
        connectivityFilter.SetInputData(cutter.GetOutput())
        connectivityFilter.SetClosestPoint(center)
        connectivityFilter.SetExtractionModeToClosestPointRegion()
        connectivityFilter.Update()
        contourTriangulator.SetInputData(connectivityFilter.GetPolyDataOutput())
    else:
        contourTriangulator.SetInputData(cutter.GetOutput())
    contourTriangulator.Update()
    # Get result
    polydata = contourTriangulator.GetOutput()
    # Get surface area
    massProperties = vtk.vtkMassProperties()
    massProperties.SetInputData(polydata)
    massProperties.Update()
    surfaceArea = massProperties.GetSurfaceArea()
    
    # Create a model of the polydata. Hidden by default, with no lighting.
    cutModel = None
    if createModel:
        cutModel = slicer.modules.models.logic().AddModel(polydata)
        cutModel.SetDisplayVisibility(False)
        cutModel.GetDisplayNode().SetLighting(False)
        # Set model's name : control point label + segment name.
        segment = inputSegmentation.GetSegmentation().GetSegment(segmentID)
        if controlPointLabel and segment:
            modelName = controlPointLabel + "_" + segment.GetName()
            cutModel.SetName(modelName)
        # The model's color follows the segment's color.
        if segment:
            cutModel.GetDisplayNode().SetColor(segment.GetColor())
    
    stopTime = time.time()
    logging.info(f'Processing completed in {stopTime-startTime:.2f} seconds')
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

    self.delayDisplay("Starting the test")

    self.delayDisplay('Test passed')

# Menu constants.
MENU_CANCEL = 0
OUTPUT_TABLE_MENU_REMOVE_ROW = 1
OUTPUT_TABLE_MENU_EMPTY_TABLE = 2
