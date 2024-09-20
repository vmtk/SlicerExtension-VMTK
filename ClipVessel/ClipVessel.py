import os 
import unittest
import logging
import vtk, qt, ctk, slicer
import numpy as np
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry

"""
  ClipVessel
"""

class ClipVessel(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Clip Vessel"
    self.parent.categories = ["Vascular Modeling Toolkit"]
    self.parent.dependencies = []
    self.parent.contributors = ["David Molony (NGHS)", "Andras Lasso (PerkLab)"]
    self.parent.helpText = """
This module clips a surface model given a VMTK centerline and markups indicating where the model will be clipped. The first marker indicates the inlet. Optionally, the user can cap and add flow extensions.
    <a href="https://github.com/vmtk/SlicerExtension-VMTK/">here</a>.
"""
    self.parent.acknowledgementText = """
This file was developed by David Molony, Georgia Heart Institute, Northeast Georgia Health System and was partially funded by NIH grant R01 HL118019.
"""  # TODO: replace with organization, grant and thanks.

#
# ClipVesselWidget
#

class ClipVesselWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
    self.updatingGUIFromParameterNode = False

  def setup(self):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer)
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/ClipVessel.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    self.nodeSelectors = [
        (self.ui.inputSurfaceSelector, "InputSurface"),
        (self.ui.inputCenterlinesSelector, "InputCenterlines"),        
        (self.ui.clipPointsMarkupsSelector, "ClipPoints"),
        (self.ui.outputSurfaceModelSelector, "OutputSurfaceModel"),
        (self.ui.outputPreprocessedSurfaceModelSelector, "PreprocessedSurface"),
        ]

    # Add vertical spacer
    #self.layout.addStretch(1)

    # Set scene in MRML widgets. Make sure that in Qt designer
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    self.logic = ClipVesselLogic()
    self.ui.parameterNodeSelector.addAttribute("vtkMRMLScriptedModuleNode", "ModuleName", self.moduleName)
    self.setParameterNode(self.logic.getParameterNode())

    # Connections
    self.ui.capOutputSurfaceModelCheckBox.connect("toggled(bool)", self.updateParameterNodeFromGUI)
    self.ui.addFlowExtensionsCheckBox.connect("toggled(bool)", self.updateParameterNodeFromGUI)
    self.ui.parameterNodeSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.setParameterNode)
    self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)
    self.ui.preprocessInputSurfaceModelCheckBox.connect("toggled(bool)", self.updateParameterNodeFromGUI)
    self.ui.subdivideInputSurfaceModelCheckBox.connect("toggled(bool)", self.updateParameterNodeFromGUI)
    self.ui.targetKPointCountWidget.connect('valueChanged(double)', self.updateParameterNodeFromGUI)
    self.ui.decimationAggressivenessWidget.connect('valueChanged(double)', self.updateParameterNodeFromGUI)
    self.ui.extensionLengthWidget.connect('valueChanged(double)', self.updateParameterNodeFromGUI)
    self.ui.inputSegmentSelectorWidget.connect('currentSegmentChanged(QString)', self.updateParameterNodeFromGUI)
    self.ui.extensionModeComboBox.addItems(["centerlinedirection", "boundarynormal", "linear", "thinplatespline"])
    self.ui.extensionModeComboBox.connect('currentIndexChanged(int)', self.updateParameterNodeFromGUI)
    self.ui.extensionModeComboBox.setCurrentIndex(1)

    for nodeSelector, roleName in self.nodeSelectors:
      nodeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
      
    self.updateGUIFromParameterNode()
    

  def cleanup(self):
    """
    Called when the application closes and the module widget is destroyed.
    """
    self.removeObservers()

  def setParameterNode(self, inputParameterNode):
    """
    Adds observers to the selected parameter node. Observation is needed because when the
    parameter node is changed then the GUI must be updated immediately.
    """

    if inputParameterNode:
        self.logic.setDefaultParameters(inputParameterNode)

    # Set parameter node in the parameter node selector widget
    wasBlocked = self.ui.parameterNodeSelector.blockSignals(True)
    self.ui.parameterNodeSelector.setCurrentNode(inputParameterNode)
    self.ui.parameterNodeSelector.blockSignals(wasBlocked)

    if inputParameterNode == self._parameterNode:
        # No change
        return

    # Unobserve previusly selected parameter node and add an observer to the newly selected.
    # Changes of parameter node are observed so that whenever parameters are changed by a script or any other module
    # those are reflected immediately in the GUI.
    if self._parameterNode is not None:
        self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
    if inputParameterNode is not None:
        self.addObserver(inputParameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
    self._parameterNode = inputParameterNode

    # Initial GUI update
    self.updateGUIFromParameterNode()

  def updateGUIFromParameterNode(self, caller=None, event=None):
    """
    This method is called whenever parameter node is changed.
    The module GUI is updated to show the current state of the parameter node.
    """
    # Disable all sections if no parameter node is selected
    parameterNode = self._parameterNode
    if not slicer.mrmlScene.IsNodePresent(parameterNode):
        parameterNode = None
    self.ui.inputsCollapsibleButton.enabled = parameterNode is not None
    self.ui.outputsCollapsibleButton.enabled = parameterNode is not None
    self.ui.advancedCollapsibleButton.enabled = parameterNode is not None
    if parameterNode is None:
        return

    if self.updatingGUIFromParameterNode:
        return

    self.updatingGUIFromParameterNode = True

    # Update each widget from parameter node
    # Need to temporarily block signals to prevent infinite recursion (MRML node update triggers
    # GUI update, which triggers MRML node update, which triggers GUI update, ...)
    for nodeSelector, roleName in self.nodeSelectors:
        nodeSelector.setCurrentNode(self._parameterNode.GetNodeReference(roleName))

    inputSurfaceNode = self._parameterNode.GetNodeReference("InputSurface")
    if inputSurfaceNode and inputSurfaceNode.IsA("vtkMRMLSegmentationNode"):
        self.ui.inputSegmentSelectorWidget.setCurrentSegmentID(self._parameterNode.GetParameter("InputSegmentID"))
        self.ui.inputSegmentSelectorWidget.setVisible(True)
    else:
        self.ui.inputSegmentSelectorWidget.setVisible(False)

    #self.ui.inputCenterlinesSelector.setVisible(True)

    self.ui.targetKPointCountWidget.value = float(self._parameterNode.GetParameter("TargetNumberOfPoints"))/1000.0

    self.ui.decimationAggressivenessWidget.value = float(self._parameterNode.GetParameter("DecimationAggressiveness"))
    

    # do not block signals so that related widgets are enabled/disabled according to its state
    self.ui.preprocessInputSurfaceModelCheckBox.checked = (self._parameterNode.GetParameter("PreprocessInputSurface") == "true")

    self.ui.subdivideInputSurfaceModelCheckBox.checked = (self._parameterNode.GetParameter("SubdivideInputSurface") == "true")
    self.ui.capOutputSurfaceModelCheckBox.checked = (self._parameterNode.GetParameter("CapOutputSurface") == "true")    
    self.ui.addFlowExtensionsCheckBox.checked = (self._parameterNode.GetParameter("ExtendOutputSurface") == "true")    
    self.ui.extensionLengthWidget.value = float(self._parameterNode.GetParameter("ExtensionLength"))
    self.ui.extensionModeComboBox.currentText = self._parameterNode.GetParameter("ExtensionMode")
    
    # Update buttons states and tooltips
    if self._parameterNode.GetNodeReference("InputSurface") and self._parameterNode.GetNodeReference("InputCenterlines") and self._parameterNode.GetNodeReference("ClipPoints") and self._parameterNode.GetNodeReference("OutputSurfaceModel"):
        self.ui.applyButton.toolTip = "Clip vessel"
        self.ui.applyButton.enabled = True
    else:
        self.ui.applyButton.toolTip = "Select input and output model nodes"
        self.ui.applyButton.enabled = False

    self.updatingGUIFromParameterNode = False

  def updateParameterNodeFromGUI(self, caller=None, event=None):
    """
    This method is called when the user makes any change in the GUI.
    The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
    """

    if self._parameterNode is None:
        return

    for nodeSelector, roleName in self.nodeSelectors:
        self._parameterNode.SetNodeReferenceID(roleName, nodeSelector.currentNodeID)

    inputSurfaceNode = self._parameterNode.GetNodeReference("InputSurface")
    if inputSurfaceNode and inputSurfaceNode.IsA("vtkMRMLSegmentationNode"):
        self._parameterNode.SetParameter("InputSegmentID", self.ui.inputSegmentSelectorWidget.currentSegmentID())

    self.ui.inputSegmentSelectorWidget.setCurrentSegmentID(self._parameterNode.GetParameter("InputSegmentID"))
    self.ui.inputSegmentSelectorWidget.setVisible(inputSurfaceNode and inputSurfaceNode.IsA("vtkMRMLSegmentationNode"))

    wasModify = self._parameterNode.StartModify()
    self._parameterNode.SetParameter("TargetNumberOfPoints", str(self.ui.targetKPointCountWidget.value*1000.0))
    self._parameterNode.SetParameter("DecimationAggressiveness", str(self.ui.decimationAggressivenessWidget.value))
    self._parameterNode.SetParameter("PreprocessInputSurface", "true" if self.ui.preprocessInputSurfaceModelCheckBox.checked else "false")
    self._parameterNode.SetParameter("SubdivideInputSurface", "true" if self.ui.subdivideInputSurfaceModelCheckBox.checked else "false")
    self._parameterNode.SetParameter("CapOutputSurface", "true" if self.ui.capOutputSurfaceModelCheckBox.checked else "false")
    self._parameterNode.SetParameter("ExtendOutputSurface", "true" if self.ui.addFlowExtensionsCheckBox.checked else "false")
    self._parameterNode.SetParameter("ExtensionLength", str(self.ui.extensionLengthWidget.value))
    self._parameterNode.SetParameter("ExtensionMode", self.ui.extensionModeComboBox.currentText)
    self._parameterNode.EndModify(wasModify)

  def getPreprocessedPolyData(self):
  
    inputSurfacePolyData = self.logic.polyDataFromNode(self._parameterNode.GetNodeReference("InputSurface"),
                                                       self._parameterNode.GetParameter("InputSegmentID"))
    if not inputSurfacePolyData or inputSurfacePolyData.GetNumberOfPoints() == 0:
        raise ValueError("Valid input surface is required")

    preprocessEnabled = (self._parameterNode.GetParameter("PreprocessInputSurface") == "true")
    if not preprocessEnabled:
        return inputSurfacePolyData
    targetNumberOfPoints = float(self._parameterNode.GetParameter("TargetNumberOfPoints"))
    decimationAggressiveness = float(self._parameterNode.GetParameter("DecimationAggressiveness"))
    subdivideInputSurface = (self._parameterNode.GetParameter("SubdivideInputSurface") == "true")
    preprocessedPolyData = self.logic.preprocess(inputSurfacePolyData, targetNumberOfPoints, decimationAggressiveness, subdivideInputSurface)
    print(f"Target points: {targetNumberOfPoints}... Number of points in preprocessed surface:  {preprocessedPolyData.GetNumberOfPoints()}")
    return preprocessedPolyData

  def onApplyButton(self):
    """
    Run processing when user clicks "Apply" button.
    """
    qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)
    try:
        # Preprocessing
        slicer.util.showStatusMessage("Preprocessing...")
        slicer.app.processEvents()  # force update
        preprocessedPolyData = self.getPreprocessedPolyData()
        # Save preprocessing result to model node
        preprocessedSurfaceModelNode = self._parameterNode.GetNodeReference("PreprocessedSurface")
        if preprocessedSurfaceModelNode:
            preprocessedSurfaceModelNode.SetAndObserveMesh(preprocessedPolyData)
            if not preprocessedSurfaceModelNode.GetDisplayNode():
                preprocessedSurfaceModelNode.CreateDefaultDisplayNodes()
                preprocessedSurfaceModelNode.GetDisplayNode().SetColor(1.0, 1.0, 0.0)
                preprocessedSurfaceModelNode.GetDisplayNode().SetOpacity(0.4)
                preprocessedSurfaceModelNode.GetDisplayNode().SetLineWidth(2)

        clipPointsMarkupsNode = self._parameterNode.GetNodeReference("ClipPoints")
        inputSurfaceModelNode = self._parameterNode.GetNodeReference("InputSurface")
        centerlinesModelNode = self._parameterNode.GetNodeReference("InputCenterlines")
        outputModelNode = self._parameterNode.GetNodeReference("OutputSurfaceModel")
        extensionLength = float(self._parameterNode.GetParameter("ExtensionLength"))

        cap = self.ui.capOutputSurfaceModelCheckBox.checked
        addFlowExtensions = self.ui.addFlowExtensionsCheckBox.checked
        extensionMode = self._parameterNode.GetParameter("ExtensionMode")

        slicer.util.showStatusMessage("Clipping model...")
        slicer.app.processEvents()  # force update

        outputPolyData = self.logic.clipVessel(preprocessedPolyData, centerlinesModelNode, clipPointsMarkupsNode, cap, addFlowExtensions, extensionLength, extensionMode)
        

        outputModelNode.SetAndObserveMesh(outputPolyData)
        if not outputModelNode.GetDisplayNode():
            outputModelNode.CreateDefaultDisplayNodes()
            outputModelNode.GetDisplayNode().SetColor(0.0, 1.0, 0.0)
            outputModelNode.GetDisplayNode().SetLineWidth(3)
            inputSurfaceModelNode.GetDisplayNode().SetOpacity(0.4)

    except Exception as e:
        slicer.util.errorDisplay("Failed to compute results: "+str(e))
        import traceback
        traceback.print_exc()
    qt.QApplication.restoreOverrideCursor()
    slicer.util.showStatusMessage("Clipping vessel complete.", 3000)

#
# ClipVesselLogic
#

class ClipVesselLogic(ScriptedLoadableModuleLogic):
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
    self.radiusArrayName = 'Radius'
    self.blankingArrayName = 'Blanking'
    self.groupIdsArrayName = 'GroupIds'
    self.tractIdsArrayName = 'TractIds'
    self.centerlineIdsArrayName = 'CenterlineIds'
    
    self.gapLength = 1.0
    self.tolerance = 0.01
    self.clipValue = 0.0
    self.cutoffRadiusFactor = 1E16

    self.groupIds = []

    self.useRadiusInformation = 1

    self.Sigma = 1
    self.AdaptiveExtensionLength = 0
    self.AdaptiveExtensionRadius = 1
    self.AdaptiveNumberOfBoundaryPoints = 0
    self.ExtensionRatio = 2
    self.ExtensionRadius = 1
    self.TransitionRatio = 0.25
    self.CenterlineNormalEstimationDistanceRatio = 1.0
    self.TargetNumberOfBoundaryPoints = 50
    
  def setDefaultParameters(self, parameterNode):
    """
    Initialize parameter node with default settings.
    """
    # We choose a small target point number value, so that we can get fast speed
    # for smooth meshes. Actual mesh size will mainly determined by DecimationAggressiveness value.
    if not parameterNode.GetParameter("TargetNumberOfPoints"):
        parameterNode.SetParameter("TargetNumberOfPoints", "50000")
    if not parameterNode.GetParameter("DecimationAggressiveness"):
        parameterNode.SetParameter("DecimationAggressiveness", "4.0")
    if not parameterNode.GetParameter("PreprocessInputSurface"):
        parameterNode.SetParameter("PreprocessInputSurface", "true")
    if not parameterNode.GetParameter("SubdivideInputSurface"):
        parameterNode.SetParameter("SubdivideInputSurface", "false")
    if not parameterNode.GetParameter("ExtensionLength"):
        parameterNode.SetParameter("ExtensionLength", "5")
        
  def polyDataFromNode(self, surfaceNode, segmentId):
    if not surfaceNode:
        logging.error("Invalid input surface node")
        return None
    if surfaceNode.IsA("vtkMRMLModelNode"):
        return surfaceNode.GetPolyData()
    elif surfaceNode.IsA("vtkMRMLSegmentationNode"):
        # Segmentation node
        polyData = vtk.vtkPolyData()
        surfaceNode.CreateClosedSurfaceRepresentation()
        surfaceNode.GetClosedSurfaceRepresentation(segmentId, polyData)
        return polyData
    else:
        logging.error("Surface can only be loaded from model or segmentation node")
        return None
            
  def capSurface(self, surface):
    capDisplacement = 0.0
    surfaceCapper = vtkvmtkComputationalGeometry.vtkvmtkCapPolyData()
    surfaceCapper.SetInputData(surface)
    surfaceCapper.SetDisplacement(capDisplacement)
    surfaceCapper.SetInPlaneDisplacement(capDisplacement)
    surfaceCapper.Update()
    surface = surfaceCapper.GetOutput()
    return surface

  def preprocess(self, inputSurfacePolyData, targetNumberOfPoints, decimationAggressiveness, subdivideInputSurface):
    import ExtractCenterline
    extractCenterlineLogic = ExtractCenterline.ExtractCenterlineLogic()
    extractCenterlineLogic.preprocess(inputSurfacePolyData, targetNumberOfPoints, decimationAggressiveness, subdivideInputSurface)

  def clipModel(self, surface, centerlines, point, reverse):
    """Clips the model at the given point. Reverse flag indicates whether the clip
     should be in the direction of the centerline tangent or not"""
    import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry

    centerlineGeometry = vtkvmtkComputationalGeometry.vtkvmtkCenterlineGeometry()
    centerlineGeometry.SetInputData(centerlines)
    centerlineGeometry.SetLengthArrayName("Length")
    centerlineGeometry.SetCurvatureArrayName("Curvature")
    centerlineGeometry.SetTorsionArrayName("Torsion")
    centerlineGeometry.SetTortuosityArrayName("Tortuosity")
    centerlineGeometry.SetFrenetTangentArrayName("FrenetTangent")
    centerlineGeometry.SetFrenetNormalArrayName("FrenetNormal")
    centerlineGeometry.SetFrenetBinormalArrayName("FrenetBinormal")
    centerlineGeometry.SetLineSmoothing(0)
    centerlineGeometry.SetOutputSmoothedLines(0)
    centerlineGeometry.SetNumberOfSmoothingIterations(50)
    centerlineGeometry.SetSmoothingFactor(0.1)
    centerlineGeometry.Update()
    centerlines = centerlineGeometry.GetOutput()

    locator = vtk.vtkPointLocator()
    locator.SetDataSet(centerlines)
    locator.BuildLocator()
    pointId = locator.FindClosestPoint(point)
    
    if reverse:
        tangent = [val*-1 for val in centerlines.GetPointData().GetArray("FrenetTangent").GetTuple3(pointId)]
    else:
        tangent = centerlines.GetPointData().GetArray("FrenetTangent").GetTuple3(pointId)
    
    # define plane normal to the centerlines
    clipFunctionPlane = vtk.vtkPlane()
    clipFunctionPlane.SetNormal(tangent)
    clipFunctionPlane.SetOrigin(point)
    
    # define sphere at centerlines point
    clipFunctionSphere = vtk.vtkSphere()
    clipFunctionSphere.SetCenter(centerlines.GetPoint(pointId))
    clipFunctionSphere.SetRadius(centerlines.GetPointData().GetArray("Radius").GetValue(pointId)*2)

    # boolean merge the implicit plane and sphere so that the end result is a hemi-sphere
    clipFunctionCombined = vtk.vtkImplicitBoolean()
    clipFunctionCombined.AddFunction(clipFunctionPlane)
    clipFunctionCombined.AddFunction(clipFunctionSphere)
    clipFunctionCombined.SetOperationTypeToIntersection()
       
    clipper = vtk.vtkClipPolyData()
    clipper.SetInputData(surface)
    clipper.GenerateClippedOutputOn()
    clipper.SetInsideOut(0)
    clipper.GenerateClipScalarsOff()
    clipper.SetValue(0.0)
    
    # clip the surface with the hemi-sphere
    clipper.SetClipFunction(clipFunctionCombined)
        
    cutter = vtk.vtkCutter()
    cutter.SetInputData(surface)
    cutter.SetCutFunction(clipFunctionPlane)
    
    clippedSurface = vtk.vtkPolyData()
    cutLines = vtk.vtkPolyData()
    clipper.Update()
    
    surface.DeepCopy(clipper.GetOutput())
    clippedSurface.DeepCopy(clipper.GetClippedOutput())
    cutter.Update()
    cutLines.DeepCopy(cutter.GetOutput())
    
    cleaner = vtk.vtkCleanPolyData()
    cleaner.SetInputData(surface)
    cleaner.Update()    
    surface = cleaner.GetOutput()
    
    cleaner = vtk.vtkCleanPolyData()
    cleaner.SetInputData(clippedSurface)
    cleaner.Update()    
    clippedSurface = cleaner.GetOutput()

    cleaner = vtk.vtkCleanPolyData()
    cleaner.SetInputData(cutLines)
    cleaner.Update()
    stripper = vtk.vtkStripper()
    stripper.SetInputData(cleaner.GetOutput())
    stripper.Update()
    cutLines = stripper.GetOutput()
    
    return clippedSurface
    
    
  def set_clipper(self, surface, splitCenterlines, groupIds):
    # if we work under the assumption that group 0 is always kept it will eliminate the use of user interaction to select which groups to keep.
    branchClipper = vtkvmtkComputationalGeometry.vtkvmtkPolyDataCenterlineGroupsClipper()
    branchClipper.SetCenterlineGroupIdsArrayName(self.groupIdsArrayName)
    branchClipper.SetGroupIdsArrayName(self.groupIdsArrayName)
    branchClipper.SetCenterlineRadiusArrayName(self.radiusArrayName)
    branchClipper.SetBlankingArrayName(self.blankingArrayName)
    branchClipper.SetCutoffRadiusFactor(self.cutoffRadiusFactor)
    branchClipper.SetClipValue(self.clipValue)
    branchClipper.SetUseRadiusInformation(self.useRadiusInformation)
    if groupIds.GetNumberOfIds() > 0:
      branchClipper.ClipAllCenterlineGroupIdsOff()
      branchClipper.SetCenterlineGroupIds(groupIds)
      branchClipper.GenerateClippedOutputOn()
    else:
      branchClipper.ClipAllCenterlineGroupIdsOn()
    branchClipper.SetInputData(surface)
    branchClipper.SetCenterlines(splitCenterlines)
    branchClipper.Update()
    return branchClipper

  def resampleCenterline(self, polydata, spacing=0.5):
    """Resamples centerline with a spline filter to a desired spacing"""
    splineFilter = vtk.vtkSplineFilter()
    splineFilter.SetInputData(polydata)
    splineFilter.SetSubdivideToLength()
    splineFilter.SetLength(spacing)
    splineFilter.Update()
    polydata = splineFilter.GetOutput()
    return polydata
        
  def extendVessel(self, surfacePolyData, centerlinesPolyData, extensionLength, extensionMode):
    """Adds flow extensions to all boundaries"""
    
    extensionsFilter = vtkvmtkComputationalGeometry.vtkvmtkPolyDataFlowExtensionsFilter()
    extensionsFilter.SetInputData(surfacePolyData)
    extensionsFilter.SetCenterlines(centerlinesPolyData)
    extensionsFilter.SetSigma(self.Sigma)
    extensionsFilter.SetAdaptiveExtensionLength(self.AdaptiveExtensionLength)
    extensionsFilter.SetAdaptiveExtensionRadius(self.AdaptiveExtensionRadius)
    extensionsFilter.SetAdaptiveNumberOfBoundaryPoints(self.AdaptiveNumberOfBoundaryPoints)
    extensionsFilter.SetExtensionLength(extensionLength)
    extensionsFilter.SetExtensionRatio(self.ExtensionRatio)
    extensionsFilter.SetExtensionRadius(self.ExtensionRadius)
    extensionsFilter.SetTransitionRatio(self.TransitionRatio)
    extensionsFilter.SetCenterlineNormalEstimationDistanceRatio(self.CenterlineNormalEstimationDistanceRatio)
    extensionsFilter.SetNumberOfBoundaryPoints(self.TargetNumberOfBoundaryPoints)
    if extensionMode == "centerlinedirection":
        extensionsFilter.SetExtensionModeToUseCenterlineDirection()
    elif extensionMode == "boundarynormal":
        extensionsFilter.SetExtensionModeToUseNormalToBoundary()
    if extensionMode == "linear":
        extensionsFilter.SetInterpolationModeToLinear()
    elif extensionMode == "thinplatespline":
        extensionsFilter.SetInterpolationModeToThinPlateSpline()
    #extensionsFilter.SetBoundaryIds(boundaryIds)
    extensionsFilter.Update()
    return extensionsFilter.GetOutput()

  def clipVessel(self, surfacePolyData, centerlinesNode, clipPointsMarkupsNode, cap, addFlowExtensions, extensionLength, extensionMode):
    """Clips the vessel.
    :param surfacePolyData: input surface
    :param centerlinesPolyData: input centerlines
    :param clipPointsMarkupsNode: markup node containing clip points
    :param cap: flag indicating whether to cap the model:
    :param addFlowExtensions: flag indicating whether to add flow extensions:
    :param extensionLength: float value specifying the extension length:
    :param extensionMode: string specifying the extension mode:
    :return: polydata containing clipped vessel
    """
    
    import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry

    centerlinesPolyData = centerlinesNode.GetPolyData()
    centerlinesPolyData = self.resampleCenterline(centerlinesPolyData, spacing=0.5)

    numberOfControlPoints = clipPointsMarkupsNode.GetNumberOfControlPoints()
    if numberOfControlPoints == 0:
        raise ValueError("Failed to clip vessel (no output was generated)")

    # identify closest point on centerline to clipPointsMarkups
    pointLocator = vtk.vtkPointLocator()
    pointLocator.SetDataSet(centerlinesPolyData)
    pointLocator.BuildLocator()
    
    clipPoints = []
    pos = [0.0, 0.0, 0.0]
    
    for controlPointIndex in range(numberOfControlPoints):
        clipPointsMarkupsNode.GetNthControlPointPosition(controlPointIndex, pos)
        pointId = pointLocator.FindClosestPoint(pos)
        clipPoints.append(centerlinesPolyData.GetPoint(pointId))

    
    # create the centerline split extractor
    pointSplitExtractor = vtkvmtkComputationalGeometry.vtkvmtkCenterlineSplitExtractor()
    pointSplitExtractor.SetInputData(centerlinesPolyData)
    pointSplitExtractor.SetRadiusArrayName(self.radiusArrayName)
    pointSplitExtractor.SetGroupIdsArrayName(self.groupIdsArrayName)
    pointSplitExtractor.SetTractIdsArrayName(self.tractIdsArrayName)
    pointSplitExtractor.SetCenterlineIdsArrayName(self.centerlineIdsArrayName)
    pointSplitExtractor.SetBlankingArrayName(self.blankingArrayName)
    pointSplitExtractor.SetGapLength(self.gapLength)
    pointSplitExtractor.SetTolerance(self.tolerance)    

    groupIds = vtk.vtkIdList()
    groupIds.InsertNextId(0)

    surface = surfacePolyData
    # clip with branchclipper (slightly off the clip point)
    # clip the stub with plane (clippolydata)
    # merge the clipped stub and the large vessel from branch clipper

    for controlPointIndex in range(numberOfControlPoints):
        pointId = pointLocator.FindClosestPoint(clipPoints[controlPointIndex])
        # set the centerline clipping point to be slightly off the clip point
        # this is to to generate a stub which can be clipped and then merged with the main vessel
        if controlPointIndex == 0:
            splitPoint = centerlinesPolyData.GetPoint(pointId+1)
            reverse = True
        else:
            reverse = False
            splitPoint = centerlinesPolyData.GetPoint(pointId-1)    

        pointSplitExtractor.SetSplitPoint(splitPoint)
        pointSplitExtractor.Update()
        splitCenterlines = pointSplitExtractor.GetOutput()
        
        # separate surface into groups based on the split centerlines
        branchClipper = self.set_clipper(surface, splitCenterlines, groupIds)

        # create a stub and surface using the clipped centerlines
        if clipPointsMarkupsNode:
            if controlPointIndex == 0:
                surface = branchClipper.GetClippedOutput()
                stub = branchClipper.GetOutput()
            else:
                surface = branchClipper.GetOutput()  
                stub = branchClipper.GetClippedOutput()  
        else:
            surface = branchClipper.GetOutput()

        # clip the stub at the clipping point
        cutSegment = self.clipModel(stub, centerlinesPolyData, clipPoints[controlPointIndex], reverse)
        
        # merge stub and main vessel
        append=vtk.vtkAppendPolyData()
        append.AddInputData(surface)
        append.AddInputData(cutSegment)
        append.Update()
        clean = vtk.vtkCleanPolyData()
        clean.SetInputData(append.GetOutput())
        clean.Update()
        surface = clean.GetOutput()

        # remove any disconnected pieces
        connectFilter = vtk.vtkPolyDataConnectivityFilter()
        connectFilter.SetInputData(surface)
        connectFilter.SetExtractionModeToAllRegions()
        connectFilter.ColorRegionsOn()
        connectFilter.Update()
        surface = connectFilter.GetOutput()

        # if the centerline does not cover the entire surface 
        # there may be pieces that are not connected. Identify and remove them.
        num_regions = int(surface.GetPointData().GetArray("RegionId").GetRange()[1])

        if num_regions > 0:
            # find region closest to clip point
            locator = vtk.vtkPointLocator()
            locator.SetDataSet(surface)
            locator.BuildLocator()
            closestPointId = locator.FindClosestPoint(clipPoints[controlPointIndex])
            region_id = surface.GetPointData().GetArray("RegionId").GetValue(closestPointId)

            threshold = vtk.vtkThreshold()
            threshold.SetInputData(surface)
            threshold.SetInputArrayToProcess(0, 0, 0, "vtkDataObject::FIELD_ASSOCIATION_POINTS", "RegionId")
            threshold.SetLowerThreshold(region_id)
            threshold.SetUpperThreshold(region_id)
            threshold.Update()
            surface = threshold.GetOutput()

            geoFilter = vtk.vtkGeometryFilter()
            geoFilter.SetInputData(surface)
            geoFilter.Update()
            surface = geoFilter.GetOutput()

    if addFlowExtensions:
        slicer.util.showStatusMessage("Adding extensions...")
        slicer.app.processEvents() 
        surface = self.extendVessel(surface, centerlinesPolyData, extensionLength, extensionMode)

    # Cap all the holes that are in the surface
    if cap:
        slicer.util.showStatusMessage("Capping surface...")
        slicer.app.processEvents() 
        surface = self.capSurface(surface)

    surfacePolyData = vtk.vtkPolyData()
    surfacePolyData.DeepCopy(surface)

    logging.debug("End of Clip Vessel Computation..")
    return surfacePolyData

#
# ClipVesselTest
#

class ClipVesselTest(ScriptedLoadableModuleTest):
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

