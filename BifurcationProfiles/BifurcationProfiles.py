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
# BifurcationProfiles
# This module is based on vmtkbifurcationprofiles.py.
#

class BifurcationProfiles(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("Bifurcation profiles")
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Vascular Modeling Toolkit")]
        self.parent.dependencies = ["BranchClipper"]
        self.parent.contributors = ["Saleem Edah-Tally [Surgeon] [Hobbyist developer]"]
        self.parent.helpText = _("""
Create models of bifurcation profiles, i.e. the bifurcation splitting lines.
See more information in the <a href="https://github.com/vmtk/SlicerExtension-VMTK/">module documentation</a>.
""")
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = _("""
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
""")

#
# BifurcationProfilesParameterNode
#

@parameterNodeWrapper
class BifurcationProfilesParameterNode:
    inputCenterline: slicer.vtkMRMLModelNode
    # Doesn't work for vtkMRMLSemgentationNode

#
# BifurcationProfilesWidget
#

class BifurcationProfilesWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
        uiWidget = slicer.util.loadUI(self.resourcePath("UI/BifurcationProfiles.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = BifurcationProfilesLogic()

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

    def setParameterNode(self, inputParameterNode: Optional[BifurcationProfilesParameterNode]) -> None:
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
            
            if (self._parameterNode.inputCenterline is None
                or self.ui.segmentationSelector.currentNode() is None
                or self.ui.segmentSelector.currentSegmentID() == ""):
                raise ValueError("Input is invalid.")
        
            centerlinePolyData = self._parameterNode.inputCenterline.GetPolyData()
            segmentation = self.ui.segmentationSelector.currentNode()
            segmentAsPolyData = vtk.vtkPolyData()
            segmentation.GetClosedSurfaceRepresentation(self.ui.segmentSelector.currentSegmentID(),
                                                        segmentAsPolyData)
            
            profiledPolyDatas = self.logic.process(centerlinePolyData, segmentAsPolyData)
            if not profiledPolyDatas:
                return
            
            shFolderId = self._createSubjectHierarchyFolderNode("Bifurcation profiles")
            # Seed with a constant for predictable random table and colours.
            vtk.vtkMath().RandomSeed(7)
            for i in range(len(profiledPolyDatas)):
                colour = [ vtk.vtkMath().Random(), vtk.vtkMath().Random(), vtk.vtkMath().Random() ]
                profileModel = slicer.modules.models.logic().AddModel(profiledPolyDatas[i])
                profileModel.GetDisplayNode().SetColor(colour)
                self._reparentNodeToSubjectHierarchyFolderNode(shFolderId, profileModel)

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
# BifurcationProfilesLogic
#

class BifurcationProfilesLogic(ScriptedLoadableModuleLogic):

    def __init__(self) -> None:
        """
        Called when the logic class is instantiated. Can be used for initializing member variables.
        """
        ScriptedLoadableModuleLogic.__init__(self)

    def getParameterNode(self):
        return BifurcationProfilesParameterNode(super().getParameterNode())

    def _createPolyDataFromCell(self, cellId, profiledOutput):
        cellArray = vtk.vtkCellArray()
        polyLine = profiledOutput.GetCell(cellId)
        cellArray.InsertNextCell(polyLine.GetNumberOfPoints() + 1) # *
        for i in range(polyLine.GetNumberOfPoints()):
            cellArray.InsertCellPoint(i)
        cellArray.InsertCellPoint(polyLine.GetNumberOfPoints()) # *
        polyData = vtk.vtkPolyData()
        cellPoints = vtk.vtkPoints()
        cellPoints.DeepCopy(polyLine.GetPoints())
        cellPoints.InsertNextPoint(cellPoints.GetPoint(0)) # * Visually close line
        polyData.SetLines(cellArray)
        polyData.SetPoints(cellPoints)
        return polyData

    def process(self,
                inputCenterline: vtk.vtkPolyData,
                inputSurface: vtk.vtkPolyData,) -> None:

        if not inputCenterline or not inputSurface:
            raise ValueError("Input centerline or surface is invalid")

        import time
        startTime = time.time()
        logging.info("Processing started")
        
        profiledPolyDatas = []
        
        # Create splt centerline and surface.
        branchClipperLogic = slicer.modules.branchclipper.logic()
        branchClipperLogic.SetSurface(inputSurface)
        branchClipperLogic.SetCenterlines(inputCenterline)
        branchClipperLogic.Execute() # May be long; less is better here.
        
        # Work on copies.
        groupedSurface = vtk.vtkPolyData()
        groupedCenterlines = vtk.vtkPolyData()
        groupedSurface.DeepCopy(branchClipperLogic.GetOutput())
        groupedCenterlines.DeepCopy(branchClipperLogic.GetOutputCenterlines())
        
        # Compute the bifurcation profiles.
        # The result is a single polydata with scalar arrays of other interest.
        # Each cell of the result polydata is a splitting line of a bifurcation.
        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
        bifurcationProfiles = vtkvmtkComputationalGeometry.vtkvmtkPolyDataBifurcationProfiles()
        bifurcationProfiles.SetInputData(groupedSurface)
        bifurcationProfiles.SetGroupIdsArrayName(groupIdsArrayName)
        bifurcationProfiles.SetCenterlines(groupedCenterlines)
        bifurcationProfiles.SetCenterlineRadiusArrayName(radiusArrayName)
        bifurcationProfiles.SetCenterlineGroupIdsArrayName(groupIdsArrayName)
        bifurcationProfiles.SetCenterlineIdsArrayName(centerlineIdsArrayName)
        bifurcationProfiles.SetCenterlineTractIdsArrayName(tractIdsArrayName)
        bifurcationProfiles.SetBlankingArrayName(blankingArrayName)
        bifurcationProfiles.SetBifurcationProfileGroupIdsArrayName(bifurcationProfileGroupIdsArrayName)
        bifurcationProfiles.SetBifurcationProfileBifurcationGroupIdsArrayName(bifurcationProfileBifurcationGroupIdsArrayName)
        bifurcationProfiles.SetBifurcationProfileOrientationArrayName(bifurcationProfileOrientationArrayName)
        bifurcationProfiles.Update()
        profiledOutput = bifurcationProfiles.GetOutput()
        
        for i in range(profiledOutput.GetNumberOfCells()): # For every cell.
            cellPolyData = self._createPolyDataFromCell(i, profiledOutput)
            profiledPolyDatas.append(cellPolyData)

        stopTime = time.time()
        logging.info(f"Processing completed in {stopTime-startTime:.2f} seconds")
        return profiledPolyDatas

#
# BifurcationProfilesTest
#

class BifurcationProfilesTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """ Do whatever is needed to reset the state - typically a scene clear will be enough.
        """
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here.
        """
        self.setUp()
        self.test_BifurcationProfiles1()

    def test_BifurcationProfiles1(self):
        self.delayDisplay("Starting the test")

        self.delayDisplay("Test passed")

blankingArrayName = 'Blanking'
radiusArrayName = 'Radius'  # maximum inscribed sphere radius
groupIdsArrayName = 'GroupIds'
centerlineIdsArrayName = 'CenterlineIds'
tractIdsArrayName = 'TractIds'

bifurcationProfileGroupIdsArrayName = 'BifurcationProfileGroupIds'
bifurcationProfileBifurcationGroupIdsArrayName = 'BifurcationProfileBifurcationGroupIds'
bifurcationProfileOrientationArrayName = 'BifurcationProfileOrientation'
