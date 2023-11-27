import logging
import os
from typing import Annotated, Optional

import vtk

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
        
        self.ui.componentComboBox.addItem(_("Bifurcations"), BIFURCATIONS_ITEM_ID)
        self.ui.componentComboBox.addItem(_("Branches"), BRANCHES_ITEM_ID)
        self.ui.componentComboBox.addItem(_("Centerlines"), CENTERLINES_ITEM_ID)

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
        with slicer.util.tryWithErrorDisplay(_("Failed to compute results."), waitCursor=True):

            # Compute output
            component = self.ui.componentComboBox.currentData
            shFolderId = -1
            if component == 1:
                bifurcationsPolyDatas = self.logic.processGroupIds(self._parameterNode.inputCenterline, True)
                if (len(bifurcationsPolyDatas)):
                    shFolderId = self._createSubjectHierarchyFolderNode(self.ui.componentComboBox.currentText)
                for bifurcationPolyData in bifurcationsPolyDatas:
                    bifurcationModel = slicer.modules.models.logic().AddModel(bifurcationPolyData)
                    bifurcationModel.GetDisplayNode().SetColor([0.67, 1.0, 1.0])
                    self._reparentNodeToSubjectHierarchyFolderNode(shFolderId, bifurcationModel)
            elif component == 2:
                branchesPolyDatas = self.logic.processGroupIds(self._parameterNode.inputCenterline, False)
                if (len(branchesPolyDatas)):
                    shFolderId = self._createSubjectHierarchyFolderNode(self.ui.componentComboBox.currentText)
                for branchPolyData in branchesPolyDatas:
                    branchModel = slicer.modules.models.logic().AddModel(branchPolyData)
                    branchModel.GetDisplayNode().SetColor([0.0, 0.0, 1.0])
                    self._reparentNodeToSubjectHierarchyFolderNode(shFolderId, branchModel)
            elif component == 3:
                centerlinesPolyDatas = self.logic.processCenterlineIds(self._parameterNode.inputCenterline)
                if (len(centerlinesPolyDatas)):
                    shFolderId = self._createSubjectHierarchyFolderNode(self.ui.componentComboBox.currentText)
                for centerlinePolyData in centerlinesPolyDatas:
                    centerlineModel = slicer.modules.models.logic().AddModel(centerlinePolyData)
                    centerlineModel.GetDisplayNode().SetColor([1.0, 0.0, 0.5])
                    self._reparentNodeToSubjectHierarchyFolderNode(shFolderId, centerlineModel)
            else:
                raise ValueError(_("Invalid component"))

    def _createSubjectHierarchyFolderNode(self, label):
        if self._parameterNode.inputCenterline is None:
            return
        shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
        shMasterCenterlineId = shNode.GetItemByDataNode(self._parameterNode.inputCenterline)
        shFolderId = shNode.CreateFolderItem(shMasterCenterlineId, label)
        shNode.SetItemExpanded(shFolderId, False)
        return shFolderId
        
    def _reparentNodeToSubjectHierarchyFolderNode(self, shFolderId, anyObject):
        if shFolderId < 0:
            return
        shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
        shObjectId = shNode.GetItemByDataNode(anyObject)
        shNode.SetItemParent(shObjectId, shFolderId)
#
# CenterlineDisassemblyLogic
#

class CenterlineDisassemblyLogic(ScriptedLoadableModuleLogic):
    def __init__(self) -> None:
        """
        Called when the logic class is instantiated. Can be used for initializing member variables.
        """
        ScriptedLoadableModuleLogic.__init__(self)
        self.centerlines = None

    def getParameterNode(self):
        return CenterlineDisassemblyParameterNode(super().getParameterNode())

    def _extractCenterlines(self, inputCenterline: slicer.vtkMRMLModelNode):

        if not inputCenterline:
            raise ValueError(_("Input centerline is invalid"))
        
        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
        
        branchExtractor = vtkvmtkComputationalGeometry.vtkvmtkCenterlineBranchExtractor()
        branchExtractor.SetInputData(inputCenterline.GetPolyData())
        branchExtractor.SetBlankingArrayName(blankingArrayName)
        branchExtractor.SetRadiusArrayName(radiusArrayName)
        branchExtractor.SetGroupIdsArrayName(groupIdsArrayName)
        branchExtractor.SetCenterlineIdsArrayName(centerlineIdsArrayName)
        branchExtractor.SetTractIdsArrayName(tractIdsArrayName)
        branchExtractor.Update()
        self.centerlines = branchExtractor.GetOutput()
    
    def _createPolyData(self, cellIds):
        masterRadiusArray = self.centerlines.GetPointData().GetArray(radiusArrayName)
        masterEdgeArray = self.centerlines.GetPointData().GetArray(edgeArrayName)
        masterEdgePCoordArray = self.centerlines.GetPointData().GetArray(edgePCoordArrayName)

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
            edgeArray = vtk.vtkDoubleArray()
            edgeArray.SetName("EdgeArray")
            edgeArray.SetNumberOfComponents(2)
            edgePCoordArray = vtk.vtkDoubleArray()
            edgePCoordArray.SetName("EdgePCoordArray")
            
            masterCellId = cellIds.GetId(i)
            masterCellPolyLine = self.centerlines.GetCell(masterCellId)
            masterCellPointIds = masterCellPolyLine.GetPointIds()
            numberOfMasterCellPointIds = masterCellPointIds.GetNumberOfIds()
            cellArray.InsertNextCell(numberOfMasterCellPointIds)
            for idx in range(numberOfMasterCellPointIds):
                point = [0.0, 0.0, 0.0]
                masterPointId = masterCellPointIds.GetId(idx)
                self.centerlines.GetPoint(masterPointId, point)
                points.InsertNextPoint(point)
                cellArray.InsertCellPoint(pointId)
                radiusArray.InsertNextValue(masterRadiusArray.GetValue(masterPointId))
                edgeArray.InsertNextTuple2(masterEdgeArray.GetTuple2(masterPointId)[0], 
                                           masterEdgeArray.GetTuple2(masterPointId)[1])
                edgePCoordArray.InsertNextValue(masterEdgePCoordArray.GetValue(masterPointId))
                pointId = pointId + 1

            if (numberOfMasterCellPointIds):
                unitCellPolyData = vtk.vtkPolyData()
                unitCellPolyData.SetPoints(points)
                unitCellPolyData.SetLines(cellArray)
                unitCellPolyData.GetPointData().AddArray(radiusArray)
                unitCellPolyData.GetPointData().AddArray(edgeArray)
                unitCellPolyData.GetPointData().AddArray(edgePCoordArray)
                resultPolyDatas.append(unitCellPolyData)
        return resultPolyDatas
        
    def processCenterlineIds(self, inputCenterline: slicer.vtkMRMLModelNode):

        if not inputCenterline:
            raise ValueError(_("Input centerline is invalid"))

        import time
        startTime = time.time()
        logging.info(_("Processing started"))

        self._extractCenterlines(inputCenterline)
        centerlinePolyDatas = []
        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
        centerlineIdsArray = self.centerlines.GetCellData().GetArray(centerlineIdsArrayName)
        centerlineIdsValueRange = centerlineIdsArray.GetValueRange()
        centerlineUtilities = vtkvmtkComputationalGeometry.vtkvmtkCenterlineUtilities()
        for centerlineId in range(centerlineIdsValueRange[0], (centerlineIdsValueRange[1] + 1)):
            centerlineCellIdsArray = vtk.vtkIdList()
            centerlineUtilities.GetCenterlineCellIds(self.centerlines, centerlineIdsArrayName,
                                                     centerlineId, centerlineCellIdsArray)
            unitCellPolyDatas = self._createPolyData(centerlineCellIdsArray) # One per cell
            appendPolyData = vtk.vtkAppendPolyData() # We want a complete centerline
            for resultPolyData in unitCellPolyDatas:
                appendPolyData.AddInputData(resultPolyData)
            appendPolyData.Update() # The scalar arrays are rightly merged... fortunately.
            centerlinePolyDatas.append(appendPolyData.GetOutput())
        
        self.centerlines = None
        stopTime = time.time()
        logging.info(f"Processing completed in {stopTime-startTime:.2f} seconds")
        return centerlinePolyDatas

    def processGroupIds(self, inputCenterline: slicer.vtkMRMLModelNode, bifurcations):

        if not inputCenterline:
            raise ValueError(_("Input centerline is invalid"))

        import time
        startTime = time.time()
        logging.info(_("Processing started"))

        self._extractCenterlines(inputCenterline)
        groupIdsPolyDatas = []
        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
        groupIdsArray = vtk.vtkIdList()
        centerlineUtilities = vtkvmtkComputationalGeometry.vtkvmtkCenterlineUtilities()
        if (bifurcations):
            # Blanked
            centerlineUtilities.GetBlankedGroupsIdList(self.centerlines, groupIdsArrayName,
                                                       blankingArrayName, groupIdsArray)
            for idx in range(groupIdsArray.GetNumberOfIds()):
                groupCellIdsArray = vtk.vtkIdList()
                groupCellId = groupIdsArray.GetId(idx)
                centerlineUtilities.GetGroupUniqueCellIds(self.centerlines, groupIdsArrayName,
                                                          groupCellId, groupCellIdsArray)
                unitCellPolyDatas = self._createPolyData(groupCellIdsArray)
                for unitCellPolyData in unitCellPolyDatas:
                    groupIdsPolyDatas.append(unitCellPolyData)
        else:
            # Non-blanked
            centerlineUtilities.GetNonBlankedGroupsIdList(self.centerlines, groupIdsArrayName,
                                                          blankingArrayName, groupIdsArray)
            for idx in range(groupIdsArray.GetNumberOfIds()):
                groupCellIdsArray = vtk.vtkIdList()
                groupCellId = groupIdsArray.GetId(idx)
                centerlineUtilities.GetGroupUniqueCellIds(self.centerlines, groupIdsArrayName,
                                                          groupCellId, groupCellIdsArray)
                unitCellPolyDatas = self._createPolyData(groupCellIdsArray)
                for unitCellPolyData in unitCellPolyDatas:
                    groupIdsPolyDatas.append(unitCellPolyData)
        
        self.centerlines = None
        stopTime = time.time()
        logging.info(f"Processing completed in {stopTime-startTime:.2f} seconds")
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
