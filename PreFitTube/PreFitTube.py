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
# PreFitTube
#

class PreFitTube(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("Pre-fit tube") 
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Vascular Modeling Toolkit")]
        self.parent.dependencies = []
        self.parent.contributors = ["Saleem Edah-Tally [Surgeon] [Hobbyist developer]"] 
        self.parent.helpText = _("""
Pre-fit a Shape::Tube markups node guided by a markups curve.
See more information in <a href="https://github.com/vmtk/SlicerExtension-VMTK/">module documentation</a>.
""")
        self.parent.acknowledgementText = _("""
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
""")

#
# PreFitTubeParameterNode
#

@parameterNodeWrapper
class PreFitTubeParameterNode:
    inputVolumeNode: slicer.vtkMRMLScalarVolumeNode
    inputCurveNode: slicer.vtkMRMLMarkupsCurveNode
    dimensionPreset: int = 3
    outputShapeNode: slicer.vtkMRMLMarkupsShapeNode
    outputSegmentationNode: slicer.vtkMRMLSegmentationNode

class dimensionPresets:
    tiny = {
        "extrusionKernelSize": 0.5,
        "gaussianStandardDeviation": 0.5,
        "seedRadius": 0.5,
        "shellMargin": 5.0,
        "shellThickness": 0.8
    }
    small = {
        "extrusionKernelSize": 1.5,
        "gaussianStandardDeviation": 0.8,
        "seedRadius": 0.8,
        "shellMargin": 9.0,
        "shellThickness": 1.1
    }
    medium = {
        "extrusionKernelSize": 3.2,
        "gaussianStandardDeviation": 1.2,
        "seedRadius": 1.0,
        "shellMargin": 13.0,
        "shellThickness": 1.5
    }
    big = {
        "extrusionKernelSize": 4.1,
        "gaussianStandardDeviation": 1.6,
        "seedRadius": 1.0,
        "shellMargin": 22.0,
        "shellThickness": 2.0
    }
    huge = {
        "extrusionKernelSize": 5.1,
        "gaussianStandardDeviation": 2.1,
        "seedRadius": 1.0,
        "shellMargin": 32.0,
        "shellThickness": 2.2
    }

    presets = (tiny, small, medium, big, huge)
    def getPreset(self, index):
        if index < 1 or index > len(self.presets):
            raise ValueError("Preset index out of range.")
        return self.presets[index - 1]
#
# PreFitTubeWidget
#

class PreFitTubeWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None
        self._parameterNodeGuiTag = None
        self._updatingGuiFromParameterNode = False

    def setup(self) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath("UI/PreFitTube.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = PreFitTubeLogic()

        self.ui.dimensionComboBox.addItem(_("Tiny"), DIMENSION_TINY)
        self.ui.dimensionComboBox.addItem(_("Small"), DIMENSION_SMALL)
        self.ui.dimensionComboBox.addItem(_("Medium"), DIMENSION_MEDIUM)
        self.ui.dimensionComboBox.addItem(_("Big"), DIMENSION_BIG)
        self.ui.dimensionComboBox.addItem(_("Huge"), DIMENSION_HUGE)

        # Connections
        self.ui.dimensionComboBox.connect('currentIndexChanged(int)', self.onDimensionPresetChanged)

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # Buttons
        self.ui.applyButton.connect("clicked(bool)", self.onApplyButton)

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

    def cleanup(self) -> None:
        """Called when the application closes and the module widget is destroyed."""
        self.removeObservers()

    def enter(self) -> None:
        """Called each time the user opens this module."""
        # Make sure parameter node exists and observed
        self.initializeParameterNode()

    def exit(self) -> None:
        """Called each time the user opens a different module."""
        # Do not react to parameter node changes (GUI will be updated when the user enters into the module)
        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self._parameterNodeGuiTag = None

    def onSceneStartClose(self, caller, event) -> None:
        """Called just before the scene is closed."""
        # Parameter node will be reset, do not use it anymore
        self.setParameterNode(None)

    def onSceneEndClose(self, caller, event) -> None:
        """Called just after the scene is closed."""
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        if self.parent.isEntered:
            self.initializeParameterNode()

    def initializeParameterNode(self) -> None:
        """Ensure parameter node exists and observed."""
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

        self.setParameterNode(self.logic.getParameterNode())

    def setParameterNode(self, inputParameterNode: Optional[PreFitTubeParameterNode]) -> None:
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
            self.updateGuiFromParameterNode()

    def onApplyButton(self) -> None:
        """Run processing when user clicks "Apply" button."""
        with slicer.util.tryWithErrorDisplay(_("Failed to compute results."), waitCursor=True):
            self.logic.process()

    def onDimensionPresetChanged(self, index):
        if self._parameterNode:
            self._parameterNode.dimensionPreset = self.ui.dimensionComboBox.currentData

    def updateGuiFromParameterNode(self):
        if not self._parameterNode or self._updatingGuiFromParameterNode:
            return
        self._updatingGuiFromParameterNode = True
        
        index = self.ui.dimensionComboBox.findData(self._parameterNode.dimensionPreset)
        self.ui.dimensionComboBox.setCurrentIndex(index)
        self.ui.ouitputOptionsCollapsibleButton.collapsed = (self._parameterNode.outputSegmentationNode is None)

        self._updatingGuiFromParameterNode = False
#
# PreFitTubeLogic
#

class PreFitTubeLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self) -> None:
        """Called when the logic class is instantiated. Can be used for initializing member variables."""
        ScriptedLoadableModuleLogic.__init__(self)
        self._parameterNode = None

    def getParameterNode(self):
        self._parameterNode = PreFitTubeParameterNode(super().getParameterNode())
        return self._parameterNode

    # 56.56s for 10⁴ points.
    def getFarthestPoints(self, points : vtk.vtkPoints):
        numberOfPoints = points.GetNumberOfPoints()
        distances = vtk.vtkFloatArray()
        distances.SetNumberOfComponents(7)
        for i in range(numberOfPoints):
            referencePoint = [0] * 3
            points.GetPoint(i, referencePoint)
            for j in range(numberOfPoints):
                nextPoint = [0] * 3
                points.GetPoint(j, nextPoint)
                distance2 = vtk.vtkMath.Distance2BetweenPoints(referencePoint, nextPoint)
                distances.InsertNextTuple((referencePoint[0], referencePoint[1], referencePoint[2],
                                            nextPoint[0], nextPoint[1], nextPoint[2],
                                            distance2))

        sorter = vtk.vtkSortDataArray()
        sorter.SortArrayByComponent(distances, 6, 1)
        farthest = distances.GetTuple(0)

        result = vtk.vtkPoints()
        result.InsertNextPoint((farthest[0], farthest[1], farthest[2]))
        result.InsertNextPoint((farthest[3], farthest[4], farthest[5]))

        return result

    def process(self) -> None:

        import time

        startTime = time.time()
        logging.info(_("Processing started."))

        curveNode = self._parameterNode.inputCurveNode
        if not curveNode:
            raise ValueError("No input curve node specified.")

        volumeNode = self._parameterNode.inputVolumeNode
        if not volumeNode:
            raise ValueError("No input volume node specified.")

        shapeNode = self._parameterNode.outputShapeNode
        if not shapeNode:
            raise ValueError("No output shape node specified.")

        segmentationNode = self._parameterNode.outputSegmentationNode
        if not segmentationNode:
            segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")

        profiles = dimensionPresets()
        profile = profiles.getPreset(self._parameterNode.dimensionPreset)

        """
        Create a segment than can overlap on contrast calcifications and soft
        lesions. The more the curve can pass through each type of structure,
        the better. But the curve should represent the axis of the vessel.
        """
        import GuidedVeinSegmentation
        gvsLogic = GuidedVeinSegmentation.GuidedVeinSegmentationLogic()
        segmentID = gvsLogic.process(
            inputCurve = curveNode,
            inputVolume =  volumeNode,
            inputSegmentation = segmentationNode,
            extrusionKernelSize = profile["extrusionKernelSize"],
            gaussianStandardDeviation = profile["gaussianStandardDeviation"],
            seedRadius = profile["seedRadius"],
            shellMargin = profile["shellMargin"],
            shellThickness = profile["shellThickness"],
            subtractOtherSegments = False # Do not account for prior work in the same segmentation.
            )
        segmentationNode.CreateClosedSurfaceRepresentation()
        # At this step, the segment editor is already setup.

        # Get segment as polydata.
        segmentPolyData = vtk.vtkPolyData()
        if not segmentationNode.GetClosedSurfaceRepresentation(segmentID, segmentPolyData):
            if not self._parameterNode.outputSegmentationNode:
                slicer.mrmlScene.RemoveNode(segmentationNode)
            raise RuntimeError(_("Failed to get segment polydata."))

        # Reset shape node and ensure it is a Tube.
        shapeNode.RemoveAllControlPoints()
        shapeNode.SetShapeName(slicer.vtkMRMLMarkupsShapeNode.Tube)
        shapeNode.CreateDefaultDisplayNodes()

        numberOfControlPoints = curveNode.GetNumberOfControlPoints()
        curvePolyData = curveNode.GetCurveWorld()
        for controlPointindex in range(numberOfControlPoints):
            curvePointIndex = curveNode.GetCurvePointIndexFromControlPointIndex(controlPointindex)
            # GetCurveDirectionAtPointIndexWorld() can be troublesome.
            p1 = [0.0] * 3
            p2 = [0.0] * 3
            planeOrigin = [0.0] * 3
            if controlPointindex < (numberOfControlPoints - 1):
                curvePolyData.GetPoint(curvePointIndex, p1)
                curvePolyData.GetPoint(curvePointIndex + 1, p2)
                vtk.vtkMath.Assign(p1, planeOrigin)
            else:
                curvePolyData.GetPoint(curvePointIndex - 1, p1)
                curvePolyData.GetPoint(curvePointIndex, p2)
                vtk.vtkMath.Assign(p2, planeOrigin)
            direction = [0.0] * 3
            vtk.vtkMath.Subtract(p2, p1, direction)

            # Place a plane perpendicular to the curve.
            plane = vtk.vtkPlane()
            plane.SetOrigin(planeOrigin)
            plane.SetNormal(direction)

            # Cut through the segment closed surface and get the points of the contour.
            planeCut = vtk.vtkCutter()
            planeCut.SetInputData(segmentPolyData)
            planeCut.SetCutFunction(plane)
            planeCut.Update()
            planePoints = planeCut.GetOutput().GetPoints()
            if (not planePoints) or (planePoints.GetNumberOfPoints == 0):
                logging.info(_("Skipping empty section."))
                continue

            # Keep the closest connected region around the control point.
            connectivityFilter = vtk.vtkConnectivityFilter()
            connectivityFilter.SetInputData(planeCut.GetOutput())
            connectivityFilter.SetClosestPoint(planeOrigin)
            connectivityFilter.SetExtractionModeToClosestPointRegion()
            connectivityFilter.Update()
            closestPoints = connectivityFilter.GetOutput().GetPoints()
            if (not closestPoints) or (closestPoints.GetNumberOfPoints == 0):
                logging.info(_("Skipping empty closest section.")) # !
                continue

            # Get farthest points of the contour.
            farthestPoints = self.getFarthestPoints(closestPoints)

            # Add control points to the tube.
            shapeNode.AddControlPoint(farthestPoints.GetPoint(0))
            shapeNode.AddControlPoint(farthestPoints.GetPoint(1))

        # If we created the segmentation, remove it.
        if not self._parameterNode.outputSegmentationNode:
                slicer.mrmlScene.RemoveNode(segmentationNode)

        stopTime = time.time()
        durationValue = '%.2f' % (stopTime-startTime)
        logging.info(_("Processing completed in {duration} seconds").format(duration=durationValue))

#
# PreFitTubeTest
#


class PreFitTubeTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """Do whatever is needed to reset the state - typically a scene clear will be enough."""
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here."""
        self.setUp()
        self.test_PreFitTube1()

    def test_PreFitTube1(self):
        """Ideally you should have several levels of tests.  At the lowest level
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

        self.delayDisplay("Test passed")

DIMENSION_TINY = 1
DIMENSION_SMALL = 2
DIMENSION_MEDIUM = 3
DIMENSION_BIG = 4
DIMENSION_HUGE = 5
