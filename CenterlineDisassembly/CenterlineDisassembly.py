import logging
import os
from typing import Annotated, Optional

import vtk
import qt

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
# CenterlineDisassembly
#

class CenterlineDisassembly(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("Centerline disassembly")
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Vascular Modeling Toolkit")]
        self.parent.dependencies = []
        self.parent.contributors = ["Saleem Edah-Tally [Surgeon] [Hobbyist developer]"]
        self.parent.helpText = _("""
Break down a centerline model into parts.
This module makes use of the 'ExtractCenterline' module to generate curves.
See more information in the <a href="https://github.com/vmtk/SlicerExtension-VMTK/">module documentation</a>.
""")
        self.parent.acknowledgementText = _("""
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
""")

#
# CenterlineDisassemblyParameterNode
#

@parameterNodeWrapper
class CenterlineDisassemblyParameterNode:
    inputCenterline: slicer.vtkMRMLModelNode
    # QToolButton is not handled here.

#
# CenterlineDisassemblyWidget
#

class CenterlineDisassemblyWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
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
        self._createdCurveVisibilityAction = None

    def setup(self) -> None:
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath("UI/CenterlineDisassembly.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = CenterlineDisassemblyLogic()
        
        self.ui.componentCheckableComboBox.addItem(_("Bifurcations"), BIFURCATIONS_ITEM_ID)
        self.ui.componentCheckableComboBox.addItem(_("Branches"), BRANCHES_ITEM_ID)
        self.ui.componentCheckableComboBox.addItem(_("Centerlines"), CENTERLINES_ITEM_ID)
        
        # When there are too many curves, the UI is obliterated.
        # When there are a few, the curve names are nevertheless informative.
        self.ui.optionCreateCurvesMenuButton.menu().clear()
        self._createdCurveVisibilityAction = qt.QAction(_("Show curve names"))
        self._createdCurveVisibilityAction.setCheckable(True)
        self.ui.optionCreateCurvesMenuButton.menu().addAction(self._createdCurveVisibilityAction)

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # Buttons
        self.ui.applyButton.connect("clicked(bool)", self.onApplyButton)

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

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

    def exit(self) -> None:
        """
        Called each time the user opens a different module.
        """
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

    def initializeParameterNode(self) -> None:
        """
        Ensure parameter node exists and observed.
        """
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

        self.setParameterNode(self.logic.getParameterNode())

    def setParameterNode(self, inputParameterNode: Optional[CenterlineDisassemblyParameterNode]) -> None:
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

    def onApplyButton(self) -> None:
        """
        Run processing when user clicks "Apply" button.
        """
        optionCreateModels = self.ui.optionCreateModelsToolButton.checked
        optionCreateCurves = self.ui.optionCreateCurvesMenuButton.checked
        optionShowCurveNames = self._createdCurveVisibilityAction.checked
        
        with slicer.util.tryWithErrorDisplay(_("Failed to compute results."), waitCursor=True):
            components = self.ui.componentCheckableComboBox.checkedIndexes()
            numberOfComponents = len(components)
            if (numberOfComponents == 0):
                raise ValueError(_("Please select the components to create."))
            
            if (optionCreateModels is False) and \
                (optionCreateCurves is False):
                raise ValueError(_("Please specify whether centerline 'Models' and/or 'Curves' should be generated."))
            
            self.showStatusMessage( (_("Splitting centerline"),) )
            # Compute output
            self.logic.splitCenterlines(self._parameterNode.inputCenterline.GetPolyData()) # Once only for all selections
            shFolderId = -1
            
            # The total procesing time is significantly reduced when there are too many components.
            slicer.mrmlScene.StartState(slicer.mrmlScene.BatchProcessState)
            
            for idx in range(numberOfComponents): # For every selection
                modelIndex = components[idx]
                component = modelIndex.data(qt.Qt.UserRole)
                componentLabel = modelIndex.data()
                if component == BIFURCATIONS_ITEM_ID:
                    bifurcationsPolyDatas = self.logic.processGroupIds(True)
                    if (len(bifurcationsPolyDatas)):
                        if optionCreateModels:
                            shFolderId = self._createSubjectHierarchyFolderNode(componentLabel + " - " + self._parameterNode.inputCenterline.GetName() + _(" models"))
                        
                        if optionCreateCurves:
                            shCurveFolderId = self._createCurveSubjectHierarchyFolderNode(componentLabel + " - " + self._parameterNode.inputCenterline.GetName() + _(" curves"))
                    
                    self.showStatusMessage( (_("Creating bifurcations"),) )
                    for bifurcationPolyData in bifurcationsPolyDatas:
                        if optionCreateModels:
                            self._createModelComponent(bifurcationPolyData, _("Bifurcation_Model"), [0.67, 1.0, 1.0], shFolderId)
                        
                        if optionCreateCurves:
                            self._createCurveComponent(bifurcationPolyData, _("Bifurcation_Curve"),
                                                       [0.33, 0.0, 0.0], shCurveFolderId, optionShowCurveNames)
                        
                elif component == BRANCHES_ITEM_ID:
                    branchesPolyDatas = self.logic.processGroupIds(False)
                    if (len(branchesPolyDatas)):
                        if optionCreateModels:
                            shFolderId = self._createSubjectHierarchyFolderNode(componentLabel + " - " + self._parameterNode.inputCenterline.GetName() + _(" models"))
                        
                        if optionCreateCurves:
                            shCurveFolderId = self._createCurveSubjectHierarchyFolderNode(componentLabel + " - " + self._parameterNode.inputCenterline.GetName() + _(" curves"))
                    
                    self.showStatusMessage( (_("Creating branches"),) )
                    for branchPolyData in branchesPolyDatas:
                        if optionCreateModels:
                            self._createModelComponent(branchPolyData, _("Branch_Model"), [0.0, 0.0, 1.0], shFolderId)
                        
                        if optionCreateCurves:
                            self._createCurveComponent(branchPolyData, _("Branch_Curve"),
                                                       [1.0, 1.0, 0.0], shCurveFolderId, optionShowCurveNames)
                        
                elif component == CENTERLINES_ITEM_ID:
                    centerlinesPolyDatas = self.logic.processCenterlineIds()
                    if (len(centerlinesPolyDatas)):
                        if optionCreateModels:
                            shFolderId = self._createSubjectHierarchyFolderNode(componentLabel + " - " + self._parameterNode.inputCenterline.GetName() + _(" models"))
                        
                        if optionCreateCurves:
                            shCurveFolderId = self._createCurveSubjectHierarchyFolderNode(componentLabel + " - " + self._parameterNode.inputCenterline.GetName() + _(" curves"))
                    
                    self.showStatusMessage( (_("Creating centerlines"),) )
                    for centerlinePolyData in centerlinesPolyDatas:
                        if optionCreateModels:
                            self._createModelComponent(centerlinePolyData, _("Centerline_Model"), [1.0, 0.0, 0.5], shFolderId)
                        
                        if optionCreateCurves:
                            self._createCurveComponent(centerlinePolyData, _("Centerline_Curve"),
                                                       [0.0, 1.0, 0.5], shCurveFolderId, optionShowCurveNames)
                else:
                    slicer.mrmlScene.EndState(slicer.mrmlScene.BatchProcessState)
                    message = _("Invalid component")
                    self.showStatusMessage( (message,) )
                    raise ValueError( (message,) )
            
            slicer.mrmlScene.EndState(slicer.mrmlScene.BatchProcessState)
            self.showStatusMessage( (_("Finished"),) )

    def _createSubjectHierarchyFolderNode(self, label):
        if self._parameterNode.inputCenterline is None:
            return
        shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
        shMasterCenterlineId = shNode.GetItemByDataNode(self._parameterNode.inputCenterline)
        shFolderId = shNode.CreateFolderItem(shMasterCenterlineId, label)
        shNode.SetItemExpanded(shFolderId, False)
        return shFolderId
    
    def _createCurveSubjectHierarchyFolderNode(self, label):
        if self._parameterNode.inputCenterline is None:
            return
        shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
        shFolderId = shNode.CreateFolderItem(shNode.GetSceneItemID(), label)
        shNode.SetItemExpanded(shFolderId, False)
        return shFolderId
        
    def _reparentNodeToSubjectHierarchyFolderNode(self, shFolderId, anyObject) -> None:
        if shFolderId < 0:
            return
        shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
        shObjectId = shNode.GetItemByDataNode(anyObject)
        shNode.SetItemParent(shObjectId, shFolderId)
    
    def _createModelComponent(self, polydata, basename, color, parentFolderId):
        name = slicer.mrmlScene.GenerateUniqueName(basename)
        model = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", name)
        model.CreateDefaultDisplayNodes()
        model.SetAndObservePolyData(polydata)
        model.GetDisplayNode().SetColor(color)
        self._reparentNodeToSubjectHierarchyFolderNode(parentFolderId, model)
        return model
    
    def _createCurveComponent(self, polydata, basename, color, parentFolderId, showCurveName):
        name = slicer.mrmlScene.GenerateUniqueName(basename)
        curve = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsCurveNode", name)
        curve.CreateDefaultDisplayNodes()
        curve.GetDisplayNode().SetPropertiesLabelVisibility(showCurveName)
        self.logic.createCenterlineCurve(polydata, curve)
        curve.GetDisplayNode().SetSelectedColor(color)
        self._reparentNodeToSubjectHierarchyFolderNode(parentFolderId, curve)
        return curve
    
    def showStatusMessage(self, messages, console = False) -> None:
        separator = " "
        msg = separator.join(messages)
        slicer.util.showStatusMessage(msg, 3000)
        slicer.app.processEvents()
        if console:
            logging.info(msg)
#
# CenterlineDisassemblyLogic
#

class CenterlineDisassemblyLogic(ScriptedLoadableModuleLogic):
    def __init__(self) -> None:
        """
        Called when the logic class is instantiated. Can be used for initializing member variables.
        """
        ScriptedLoadableModuleLogic.__init__(self)
        self._splitCenterlines = None

    def getParameterNode(self):
        return CenterlineDisassemblyParameterNode(super().getParameterNode())

    def splitCenterlines(self, inputCenterline: vtk.vtkPolyData):

        if not inputCenterline:
            raise ValueError(_("Input centerline is invalid"))

        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
        
        branchExtractor = vtkvmtkComputationalGeometry.vtkvmtkCenterlineBranchExtractor()
        branchExtractor.SetInputData(inputCenterline)
        branchExtractor.SetBlankingArrayName(blankingArrayName)
        branchExtractor.SetRadiusArrayName(radiusArrayName)
        branchExtractor.SetGroupIdsArrayName(groupIdsArrayName)
        branchExtractor.SetCenterlineIdsArrayName(centerlineIdsArrayName)
        branchExtractor.SetTractIdsArrayName(tractIdsArrayName)
        branchExtractor.Update()
        self._splitCenterlines = branchExtractor.GetOutput()
        return self._splitCenterlines

    def getNumberOfCenterlines(self):
        if not self._splitCenterlines:
            raise ValueError(_("Call 'splitCenterlines()' with an input centerline polydata first."))

        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
        centerlineIdsArray = self._splitCenterlines.GetCellData().GetArray(centerlineIdsArrayName)
        centerlineIdsValueRange = centerlineIdsArray.GetValueRange()
        # centerlineIdsValueRange[0] is always seen as 0.
        return (centerlineIdsValueRange[1] - centerlineIdsValueRange[0]) + 1

    def getNumberOfBifurcations(self):
        # Logical bifurcations, not by anatomy.
        if not self._splitCenterlines:
            raise ValueError(_("Call 'splitCenterlines()' with an input centerline polydata first."))

        groupIdsArray = vtk.vtkIdList()
        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
        centerlineUtilities = vtkvmtkComputationalGeometry.vtkvmtkCenterlineUtilities()
        centerlineUtilities.GetBlankedGroupsIdList(self._splitCenterlines, groupIdsArrayName,
                                                       blankingArrayName, groupIdsArray)
        return groupIdsArray.GetNumberOfIds()

    def getNumberOfBranches(self):
        # Logical branches, not by anatomy.
        if not self._splitCenterlines:
            raise ValueError(_("Call 'splitCenterlines()' with an input centerline polydata first."))

        groupIdsArray = vtk.vtkIdList()
        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
        centerlineUtilities = vtkvmtkComputationalGeometry.vtkvmtkCenterlineUtilities()
        centerlineUtilities.GetNonBlankedGroupsIdList(self._splitCenterlines, groupIdsArrayName,
                                                       blankingArrayName, groupIdsArray)
        return groupIdsArray.GetNumberOfIds()

    def _createPolyData(self, cellIds):
        if not self._splitCenterlines:
            raise ValueError(_("Call 'splitCenterlines()' with an input centerline polydata first."))

        masterRadiusArray = self._splitCenterlines.GetPointData().GetArray(radiusArrayName)
        masterEdgeArray = self._splitCenterlines.GetPointData().GetArray(edgeArrayName)
        masterEdgePCoordArray = self._splitCenterlines.GetPointData().GetArray(edgePCoordArrayName)

        resultPolyDatas = [] # One per cell
        nbIds = cellIds.GetNumberOfIds() # Number of cells

        for i in range(nbIds): # For every cell
            unitCellPolyData = None
            pointId = 0
            # Read new{points, cellArray,...}
            points = vtk.vtkPoints()
            cellArray = vtk.vtkCellArray()
            radiusArray = vtk.vtkDoubleArray()
            radiusArray.SetName(radiusArrayName)
            if masterEdgeArray:
                edgeArray = vtk.vtkDoubleArray()
                edgeArray.SetName("EdgeArray")
                edgeArray.SetNumberOfComponents(2)
            if masterEdgePCoordArray:
                edgePCoordArray = vtk.vtkDoubleArray()
                edgePCoordArray.SetName("EdgePCoordArray")
            
            masterCellId = cellIds.GetId(i)
            masterCellPolyLine = self._splitCenterlines.GetCell(masterCellId)
            masterCellPointIds = masterCellPolyLine.GetPointIds()
            numberOfMasterCellPointIds = masterCellPointIds.GetNumberOfIds()
            cellArray.InsertNextCell(numberOfMasterCellPointIds)
            for idx in range(numberOfMasterCellPointIds):
                point = [0.0, 0.0, 0.0]
                masterPointId = masterCellPointIds.GetId(idx)
                self._splitCenterlines.GetPoint(masterPointId, point)
                points.InsertNextPoint(point)
                cellArray.InsertCellPoint(pointId)
                radiusArray.InsertNextValue(masterRadiusArray.GetValue(masterPointId))
                if masterEdgeArray:
                    edgeArray.InsertNextTuple2(masterEdgeArray.GetTuple2(masterPointId)[0], 
                                            masterEdgeArray.GetTuple2(masterPointId)[1])
                if masterEdgePCoordArray:
                    edgePCoordArray.InsertNextValue(masterEdgePCoordArray.GetValue(masterPointId))
                pointId = pointId + 1

            if (numberOfMasterCellPointIds):
                unitCellPolyData = vtk.vtkPolyData()
                unitCellPolyData.SetPoints(points)
                unitCellPolyData.SetLines(cellArray)
                unitCellPolyData.GetPointData().AddArray(radiusArray)
                if masterEdgeArray:
                    unitCellPolyData.GetPointData().AddArray(edgeArray)
                if masterEdgePCoordArray:
                    unitCellPolyData.GetPointData().AddArray(edgePCoordArray)
                resultPolyDatas.append(unitCellPolyData)
        return resultPolyDatas
    
    def _mergeCenterlineCells(self, centerlinePolyData):
        """
        1. ExtractCenterline::_addCenterline works on a single cellId.
        
        centerlinePolyData for bifurcations and branches always has a single cell.
        
        centerlinePolyData for centerlines has more than one cell.
        We need to merge all the cells into a single cell to pass to
        ExtractCenterline::addCenterlineCurves.
        
        2. If the centerline cells are not merged, bifurcations will be identified if the centerline
        is reprocessed here, while it does not have any bifurcation.
        """
        if not centerlinePolyData:
            raise ValueError("Centerline polydata is None.")
        if centerlinePolyData.GetNumberOfCells() == 0:
            raise ValueError("Centerline polydata does not have any cell.")
            return centerlinePolyData
        if centerlinePolyData.GetNumberOfCells() == 1:
            logging.info("Centerline polydata already has a single cell.")
            return centerlinePolyData

        masterRadiusArray = centerlinePolyData.GetPointData().GetArray(radiusArrayName)
        masterEdgeArray = centerlinePolyData.GetPointData().GetArray(edgeArrayName)
        masterEdgePCoordArray = centerlinePolyData.GetPointData().GetArray(edgePCoordArrayName)

        newPolyData = None
        pointId = 0
        # Read new{points, cellArray,...}
        points = vtk.vtkPoints()
        cellArray = vtk.vtkCellArray()
        radiusArray = vtk.vtkDoubleArray()
        radiusArray.SetName(radiusArrayName)
        if masterEdgeArray:
            edgeArray = vtk.vtkDoubleArray()
            edgeArray.SetName("EdgeArray")
            edgeArray.SetNumberOfComponents(2)
        if masterEdgePCoordArray:
            edgePCoordArray = vtk.vtkDoubleArray()
            edgePCoordArray.SetName("EdgePCoordArray")

        # The new cell array must allocate for points of all input cells.
        cellArray.InsertNextCell(centerlinePolyData.GetNumberOfPoints())

        for cellId in range(centerlinePolyData.GetNumberOfCells()): # For every cell
            masterCellPolyLine = centerlinePolyData.GetCell(cellId)
            masterCellPointIds = masterCellPolyLine.GetPointIds()
            numberOfMasterCellPointIds = masterCellPointIds.GetNumberOfIds()

            for idx in range(numberOfMasterCellPointIds):
                point = [0.0, 0.0, 0.0]
                masterPointId = masterCellPointIds.GetId(idx)
                centerlinePolyData.GetPoint(masterPointId, point)
                points.InsertNextPoint(point)
                cellArray.InsertCellPoint(pointId)
                radiusArray.InsertNextValue(masterRadiusArray.GetValue(masterPointId))
                if masterEdgeArray:
                    edgeArray.InsertNextTuple2(masterEdgeArray.GetTuple2(masterPointId)[0], 
                                            masterEdgeArray.GetTuple2(masterPointId)[1])
                if masterEdgePCoordArray:
                    edgePCoordArray.InsertNextValue(masterEdgePCoordArray.GetValue(masterPointId))
                pointId = pointId + 1

        # All cells from the input centerline have been processed.
        if (pointId):
            newPolyData = vtk.vtkPolyData()
            newPolyData.SetPoints(points)
            newPolyData.SetLines(cellArray)
            newPolyData.GetPointData().AddArray(radiusArray)
            if masterEdgeArray:
                newPolyData.GetPointData().AddArray(edgeArray)
            if masterEdgePCoordArray:
                newPolyData.GetPointData().AddArray(edgePCoordArray)

        return newPolyData

    def createCenterlineCurve(self, centerlinePolyData, curveNode):
        """
        The mergedCenterlines in createCurveTreeFromCenterline does not get a GroupIds array
        if the input polydata has fewer than 2 points.

        groupId = mergedCenterlines.GetCellData().GetArray(self.groupIdsArrayName).GetValue(cellId)
        -> AttributeError: 'NoneType' object has no attribute 'GetValue'
        """
        if (centerlinePolyData and centerlinePolyData.GetNumberOfPoints() < 3):
            logging.warning("Not enough points (<3) from polydata to create a markups curve.")
            return

        import time
        startTime = time.time()
        logging.info(_("Processing curve creation started"))

        if curveNode and centerlinePolyData:
            import ExtractCenterline
            ecLogic = ExtractCenterline.ExtractCenterlineLogic()
            ecLogic.createCurveTreeFromCenterline(centerlinePolyData, centerlineCurveNode = curveNode)
            curveName = curveNode.GetName()
            curveName = curveName[0:(len(curveName) - 4)] # Remove ' (0)'
            curveNode.SetName(curveName)

        stopTime = time.time()
        durationValue = '%.2f' % (stopTime-startTime)
        logging.info(_("Processing curve creation completed in {duration} seconds").format(duration=durationValue))
    
    def processCenterlineIds(self):

        if not self._splitCenterlines:
            raise ValueError(_("Call 'splitCenterlines()' with an input centerline polydata first."))

        import time
        startTime = time.time()
        logging.info(_("Processing centerline ids started"))

        centerlinePolyDatas = []
        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
        centerlineIdsArray = self._splitCenterlines.GetCellData().GetArray(centerlineIdsArrayName)
        centerlineIdsValueRange = centerlineIdsArray.GetValueRange()
        centerlineUtilities = vtkvmtkComputationalGeometry.vtkvmtkCenterlineUtilities()
        for centerlineId in range(centerlineIdsValueRange[0], (centerlineIdsValueRange[1] + 1)):
            centerlineCellIdsArray = vtk.vtkIdList()
            centerlineUtilities.GetCenterlineCellIds(self._splitCenterlines, centerlineIdsArrayName,
                                                     centerlineId, centerlineCellIdsArray)
            unitCellPolyDatas = self._createPolyData(centerlineCellIdsArray) # One per cell
            appendPolyData = vtk.vtkAppendPolyData() # We want a complete centerline
            for resultPolyData in unitCellPolyDatas:
                appendPolyData.AddInputData(resultPolyData)
            appendPolyData.Update() # The scalar arrays are rightly merged... fortunately.
            mergedCellsPolyData = self._mergeCenterlineCells(appendPolyData.GetOutput())
            centerlinePolyDatas.append(mergedCellsPolyData)

        stopTime = time.time()
        durationValue = '%.2f' % (stopTime-startTime)
        logging.info(_("Processing centerline ids completed in {duration} seconds").format(duration=durationValue))
        return centerlinePolyDatas

    def processGroupIds(self, bifurcations):

        if not self._splitCenterlines:
            raise ValueError(_("Call 'splitCenterlines()' with an input centerline polydata first."))

        import time
        startTime = time.time()
        logging.info(_("Processing group ids started"))

        groupIdsPolyDatas = []
        groupIdsArray = vtk.vtkIdList()
        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
        centerlineUtilities = vtkvmtkComputationalGeometry.vtkvmtkCenterlineUtilities()
        if (bifurcations):
            # Blanked
            centerlineUtilities.GetBlankedGroupsIdList(self._splitCenterlines, groupIdsArrayName,
                                                       blankingArrayName, groupIdsArray)
            for idx in range(groupIdsArray.GetNumberOfIds()):
                groupCellIdsArray = vtk.vtkIdList()
                groupCellId = groupIdsArray.GetId(idx)
                centerlineUtilities.GetGroupUniqueCellIds(self._splitCenterlines, groupIdsArrayName,
                                                          groupCellId, groupCellIdsArray)
                unitCellPolyDatas = self._createPolyData(groupCellIdsArray)
                for unitCellPolyData in unitCellPolyDatas:
                    groupIdsPolyDatas.append(unitCellPolyData)
        else:
            # Non-blanked
            centerlineUtilities.GetNonBlankedGroupsIdList(self._splitCenterlines, groupIdsArrayName,
                                                          blankingArrayName, groupIdsArray)
            for idx in range(groupIdsArray.GetNumberOfIds()):
                groupCellIdsArray = vtk.vtkIdList()
                groupCellId = groupIdsArray.GetId(idx)
                centerlineUtilities.GetGroupUniqueCellIds(self._splitCenterlines, groupIdsArrayName,
                                                          groupCellId, groupCellIdsArray)
                unitCellPolyDatas = self._createPolyData(groupCellIdsArray)
                for unitCellPolyData in unitCellPolyDatas:
                    groupIdsPolyDatas.append(unitCellPolyData)

        stopTime = time.time()
        durationValue = '%.2f' % (stopTime-startTime)
        logging.info(_("Processing group ids completed in {duration} seconds").format(duration=durationValue))
        return groupIdsPolyDatas
#
# CenterlineDisassemblyTest
#

class CenterlineDisassemblyTest(ScriptedLoadableModuleTest):

    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        self.test_CenterlineDisassembly1()

    def test_CenterlineDisassembly1(self):
        self.delayDisplay(_("Starting the test"))

        self.delayDisplay(_("Test passed"))


BIFURCATIONS_ITEM_ID = 1
BRANCHES_ITEM_ID = 2
CENTERLINES_ITEM_ID = 3

blankingArrayName = 'Blanking'
radiusArrayName = 'Radius'  # maximum inscribed sphere radius
groupIdsArrayName = 'GroupIds'
centerlineIdsArrayName = 'CenterlineIds'
tractIdsArrayName = 'TractIds'
edgeArrayName = 'EdgeArray'
edgePCoordArrayName = 'EdgePCoordArray'
