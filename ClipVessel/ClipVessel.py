import colorsys
import json
import logging
import vtk, qt, slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
import numpy as np
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry

# Older scenes stored lowercase keywords in the parameter node; map those legacy values
# to the current identifiers when reading.
_LEGACY_MODE_IDS = {
    "centerlinedirection": "CENTERLINE_DIRECTION",
    "boundarynormal": "BOUNDARY_NORMAL",
    "linear": "LINEAR",
    "thinplatespline": "THIN_PLATE_SPLINE",
}

# Direction of the flow extension and the interpolation that blends the clipped cross-section
# into the target cross-section of the extension are independent settings of the flow
# extensions filter (earlier module versions offered them in a single list).
_EXTENSION_MODE_IDS = ("CENTERLINE_DIRECTION", "BOUNDARY_NORMAL")
_INTERPOLATION_MODE_IDS = ("LINEAR", "THIN_PLATE_SPLINE", "RAMP")

# Name of the cell data array that the optional face labeling writes the per-face ids into.
# "ModelFaceID" is the name SimVascular and its meshing tools read the faces of a model by.
_DEFAULT_MODEL_FACE_ID_ARRAY_NAME = "ModelFaceID"

# Shape of the mesh that closes a clipped end, one VMTK capping filter each (the methods of the
# vmtksurfacecapper script that apply to a surface with single, unpaired open boundaries).
_CAP_METHOD_IDS = ("CENTERPOINT", "SIMPLE", "SMOOTH")
_DEFAULT_CAP_METHOD = "CENTERPOINT"
# Neither the simple nor the smooth capper triangulates what it makes - the first fills a
# boundary with one polygon, the second with rings of quads - and the smooth one reads its input
# as triangles.
_CAP_METHODS_NEEDING_TRIANGLES = ("SIMPLE", "SMOOTH")
# Bulge of a smooth cap out of the plane of the cut, as a fraction of an eighth of the diagonal
# of the boundary. 0 keeps the cap in the plane of the cut, which is what the other two methods
# do, so that switching to smooth only changes how the cap is meshed and not where it sits.
_DEFAULT_CAP_CONSTRAINT_FACTOR = 0.0
_DEFAULT_CAP_NUMBER_OF_RINGS = 8
# Edge length a uniform cap mesh is remeshed to, in mm. 0 sizes each cap after the surface
# around its own rim, so that caps come out meshed as finely as the vessel they close.
_DEFAULT_CAP_TARGET_EDGE_LENGTH = 0.0

def _normalizedModeId(value):
    return _LEGACY_MODE_IDS.get(value, value)


def _faceColor(faceId, isWall):
    """Color for a face id: neutral grey for the wall, otherwise a hue spaced by the golden
    angle so that any number of faces stay far apart. The hue follows the id, so renumbering a
    face also changes its color."""
    if isWall:
        return (0.78, 0.78, 0.81)
    return colorsys.hsv_to_rgb((faceId * 0.6180339887498949) % 1.0, 0.62, 0.95)

"""
  ClipVessel
"""

class ClipVessel(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = _("Clip Vessel")
    self.parent.categories = [translate("qSlicerAbstractCoreModule", "Vascular Modeling Toolkit")]
    self.parent.dependencies = []
    self.parent.contributors = ["David Molony (NGHS)", "Andras Lasso (PerkLab)"]
    self.parent.helpText = _("""
This module clips a surface model given a VMTK centerline and markups indicating where the model will be clipped. The first marker indicates the inlet. Optionally, the user can cap and add flow extensions.
    Documentation is available <a href="https://github.com/vmtk/SlicerExtension-VMTK/blob/ClipVessel/Docs/ClipVessel.md">here</a>.
""")
    self.parent.acknowledgementText = _("""
This file was developed by David Molony, Georgia Heart Institute, Northeast Georgia Health System and was partially funded by NIH grant R01 HL118019.
""")

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
    self._observedClipPointsNode = None
    self._observedInteractivePlaneNode = None
    self._observedNormalHandleNode = None
    self._activeClipPointIndex = -1
    self._activeClipPointId = None
    self._updatingInteractivePlane = False
    self._manualPlaneNormals = {}
    self._manualPlaneOrigins = {}
    self._extensionLengthScaleFactors = {}
    self._normalHandleDistance = 1.0
    self._planeEditing = False
    self._updatingManualPlaneButtons = False
    self._preprocessedCacheKey = None
    self._preprocessedPolyData = None
    self._applying = False
    self._clipPointDragStartPosition = None
    self.autoApplyTimer = None

  def setup(self):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer)
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/ClipVessel.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)
    # Kept so that cleanup() can hand the scene back (see there).

    self.nodeSelectors = [
        (self.ui.inputSurfaceSelector, "InputSurface"),
        (self.ui.inputCenterlinesSelector, "InputCenterlines"),        
        (self.ui.clipPointsMarkupsSelector, "ClipPoints"),
        (self.ui.outputSurfaceModelSelector, "OutputSurfaceModel"),
        (self.ui.outputPreprocessedSurfaceModelSelector, "PreprocessedSurface"),
        ]

    # Set scene in MRML widgets. Make sure that in Qt designer
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    self.logic = ClipVesselLogic()
    self.ui.parameterNodeSelector.addAttribute("vtkMRMLScriptedModuleNode", "ModuleName", self.moduleName)

    self.autoApplyTimer = qt.QTimer()
    self.autoApplyTimer.setSingleShot(True)
    self.autoApplyTimer.setInterval(60)
    self.autoApplyTimer.connect("timeout()", self.onAutoApplyTimeout)

    self.inputVisibilityButtons = [
        (self.ui.toggleInputSurfaceVisibilityButton, "InputSurface", _("input surface")),
        (self.ui.toggleCenterlinesVisibilityButton, "InputCenterlines", _("centerlines")),
        (self.ui.toggleClipPointsVisibilityButton, "ClipPoints", _("clip points")),
    ]

    self.setParameterNode(self.logic.getParameterNode())

    # Connections
    self.ui.capOutputSurfaceModelCheckBox.connect("toggled(bool)", self.updateParameterNodeFromGUI)
    self.ui.capMethodComboBox.addItem(_("Center point"), "CENTERPOINT")
    self.ui.capMethodComboBox.addItem(_("Simple"), "SIMPLE")
    self.ui.capMethodComboBox.addItem(_("Smooth"), "SMOOTH")
    self.ui.capMethodComboBox.connect('currentIndexChanged(int)', self.updateParameterNodeFromGUI)
    self.ui.capConstraintFactorWidget.connect('valueChanged(double)', self.updateParameterNodeFromGUI)
    self.ui.capNumberOfRingsWidget.connect('valueChanged(double)', self.updateParameterNodeFromGUI)
    self.ui.remeshCapsCheckBox.connect("toggled(bool)", self.updateParameterNodeFromGUI)
    self.ui.capTargetEdgeLengthWidget.connect('valueChanged(double)', self.updateParameterNodeFromGUI)
    self.ui.labelModelFacesCheckBox.connect("toggled(bool)", self.onLabelModelFacesToggled)
    self.ui.modelFaceIdArrayNameLineEdit.connect("editingFinished()", self.onModelFaceIdArrayNameEditingFinished)
    self.ui.addFlowExtensionsCheckBox.connect("toggled(bool)", self.updateParameterNodeFromGUI)
    self.ui.parameterNodeSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.setParameterNode)
    self.ui.applyButton.connect('clicked(bool)', self.onApplyButtonClicked)
    self.ui.applyButton.connect('checkBoxToggled(bool)', self.updateParameterNodeFromGUI)
    self.ui.preprocessInputSurfaceModelCheckBox.connect("toggled(bool)", self.updateParameterNodeFromGUI)
    self.ui.subdivideInputSurfaceModelCheckBox.connect("toggled(bool)", self.updateParameterNodeFromGUI)
    self.ui.targetKPointCountWidget.connect('valueChanged(double)', self.updateParameterNodeFromGUI)
    self.ui.decimationAggressivenessWidget.connect('valueChanged(double)', self.updateParameterNodeFromGUI)
    self.ui.extensionRatioWidget.connect('valueChanged(double)', self.updateParameterNodeFromGUI)
    self.ui.transitionRatioWidget.connect('valueChanged(double)', self.updateParameterNodeFromGUI)
    self.ui.inputSegmentSelectorWidget.connect('currentSegmentChanged(QString)', self.updateParameterNodeFromGUI)
    # Combobox item data holds a stable, non-translated identifier that is stored in the
    # parameter node (and used by the logic); only the displayed item text is translatable.
    # The current items are selected from the parameter node by updateGUIFromParameterNode
    # (called at the end of this method), therefore no initial index is set here.
    self.ui.extensionModeComboBox.addItem(_("Centerline direction"), "CENTERLINE_DIRECTION")
    self.ui.extensionModeComboBox.addItem(_("Boundary normal"), "BOUNDARY_NORMAL")
    self.ui.extensionModeComboBox.connect('currentIndexChanged(int)', self.updateParameterNodeFromGUI)
    self.ui.interpolationModeComboBox.addItem(_("Linear"), "LINEAR")
    self.ui.interpolationModeComboBox.addItem(_("Thin plate spline"), "THIN_PLATE_SPLINE")
    self.ui.interpolationModeComboBox.addItem(_("Ramp"), "RAMP")
    self.ui.interpolationModeComboBox.connect('currentIndexChanged(int)', self.updateParameterNodeFromGUI)
    self.ui.preserveCrossSectionShapeCheckBox.connect("toggled(bool)", self.updateParameterNodeFromGUI)
    self.ui.clipPointInsetFactorWidget.connect('valueChanged(double)', self.updateParameterNodeFromGUI)
    self.ui.clippingMethodComboBox.addItem(_("Plane"), "PLANE")
    self.ui.clippingMethodComboBox.addItem(_("Plane + sphere"), "PLANE_SPHERE")
    self.ui.clippingMethodComboBox.addItem(_("Plane + patch"), "PLANE_PATCH")
    self.ui.clippingMethodComboBox.addItem(_("Box"), "BOX")
    self.ui.clippingMethodComboBox.connect('currentIndexChanged(int)', self.onClippingMethodChanged)
    self.ui.localSphereRadiusFactorWidget.connect('valueChanged(double)', self.updateParameterNodeFromGUI)
    self.ui.freeNormalHandleCheckBox.connect("toggled(bool)", self.onFreeNormalHandleToggled)
    self.ui.detectClipPointsButton.connect('clicked(bool)', self.onDetectClipPointsButton)
    self.ui.snapClipPointsToCenterlineCheckBox.connect("toggled(bool)", self.onSnapClipPointsToCenterlineToggled)
    self.ui.enableManualPlaneOrigin.connect("toggled(bool)", self.onEnableManualPlaneOriginToggled)
    self.ui.enableManualPlaneNormal.connect("toggled(bool)", self.onEnableManualPlaneNormalToggled)
    self.ui.extensionScaleWidget.connect('valueChanged(double)', self.onExtensionScaleChanged)
    self.ui.enableManualPlaneOrigin.setIcon(qt.QIcon(self.resourcePath('Icons/ManualPlaneOrigin.svg')))
    self.ui.enableManualPlaneNormal.setIcon(qt.QIcon(self.resourcePath('Icons/ManualPlaneNormal.svg')))
    self.ui.toggleOutputVisibilityButton.connect("toggled(bool)", self.onToggleOutputVisibilityButton)
    self.ui.toggleOutputEdgesButton.connect("toggled(bool)", self.onToggleOutputEdgesButton)
    self.ui.finishPlaneEditingButton.connect("clicked(bool)", self.finishPlaneEditing)
    self.ui.toggleOutputVisibilityButton.setIcon(qt.QIcon(':/Icons/Medium/SlicerVisibleInvisible.png'))
    self.ui.toggleOutputVisibilityButton.setAutoRaise(True)
    self.ui.toggleOutputEdgesButton.setAutoRaise(True)
    for button, roleName, objectName in self.inputVisibilityButtons:
        button.setIcon(qt.QIcon(':/Icons/Medium/SlicerVisibleInvisible.png'))
        button.setAutoRaise(True)
        button.connect("toggled(bool)",
                       lambda checked, roleName=roleName, button=button, objectName=objectName:
                       self.onToggleNodeVisibility(roleName, checked, button, objectName))

    for nodeSelector, roleName in self.nodeSelectors:
      nodeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
      
    self.addObserver(slicer.mrmlScene, slicer.vtkMRMLScene.EndBatchProcessEvent,
                     self.onSceneBatchProcessEnded)
    self.updateGUIFromParameterNode()
    

  def cleanup(self):
    """
    Called when the application closes and the module widget is destroyed.
    """
    self.removeObservers()
    # removeObservers() dropped every observation already; clear the trackers so that any
    # signal still arriving during teardown does not attempt a second removal (which would
    # emit a "does not have observer" warning).
    self._observedClipPointsNode = None
    self._observedInteractivePlaneNode = None
    self._observedNormalHandleNode = None
    if self.autoApplyTimer:
        self.autoApplyTimer.stop()

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

    self.observeClipPointsNode(inputParameterNode.GetNodeReference("ClipPoints") if inputParameterNode else None)
    if inputParameterNode:
        self._manualPlaneNormals = self.manualPlaneNormalsFromParameterNode()
        self._manualPlaneOrigins = self.manualPlaneOriginsFromParameterNode()
        self._extensionLengthScaleFactors = self.extensionScaleFactorsFromParameterNode()
        self.observeInteractivePlaneNode(inputParameterNode.GetNodeReference("ManualClipPlane"))
        self.observeNormalHandleNode(inputParameterNode.GetNodeReference("ManualClipPlaneNormalHandle"))

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

    # A parameter node restored from an older scene, or re-created after a scene clear, may
    # be missing some parameters; fill in defaults so that the value reads below never fail.
    self.logic.setDefaultParameters(self._parameterNode)

    # Update each widget from parameter node
    # Need to temporarily block signals to prevent infinite recursion (MRML node update triggers
    # GUI update, which triggers MRML node update, which triggers GUI update, ...)
    for nodeSelector, roleName in self.nodeSelectors:
        nodeSelector.setCurrentNode(self._parameterNode.GetNodeReference(roleName))

    inputSurfaceNode = self._parameterNode.GetNodeReference("InputSurface")
    inputSurfaceName = inputSurfaceNode.GetName() if inputSurfaceNode else None
    self.ui.outputSurfaceModelSelector.baseName = (
        inputSurfaceName + " clipped" if inputSurfaceName else "Output surface model")
    self.ensureOutputSurfaceNode(inputSurfaceNode)
    if inputSurfaceNode and inputSurfaceNode.IsA("vtkMRMLSegmentationNode"):
        self.ui.inputSegmentSelectorWidget.setCurrentSegmentID(self._parameterNode.GetParameter("InputSegmentID"))
        self.ui.inputSegmentSelectorWidget.setVisible(True)
    else:
        self.ui.inputSegmentSelectorWidget.setVisible(False)
    self.updateInputSurfaceOpacity(inputSurfaceNode)

    #self.ui.inputCenterlinesSelector.setVisible(True)

    self.ui.targetKPointCountWidget.value = float(self._parameterNode.GetParameter("TargetNumberOfPoints"))/1000.0

    self.ui.decimationAggressivenessWidget.value = float(self._parameterNode.GetParameter("DecimationAggressiveness"))
    

    # do not block signals so that related widgets are enabled/disabled according to its state
    self.ui.preprocessInputSurfaceModelCheckBox.checked = (self._parameterNode.GetParameter("PreprocessInputSurface") == "true")

    self.ui.subdivideInputSurfaceModelCheckBox.checked = (self._parameterNode.GetParameter("SubdivideInputSurface") == "true")
    cap = (self._parameterNode.GetParameter("CapOutputSurface") == "true")
    self.ui.capOutputSurfaceModelCheckBox.checked = cap
    capMethod = self._parameterNode.GetParameter("CapMethod") or _DEFAULT_CAP_METHOD
    capMethodIndex = self.ui.capMethodComboBox.findData(capMethod)
    if capMethodIndex < 0:
        # Unknown value (e.g. from a scene saved by a different version): fall back to the
        # method the module has always used.
        capMethodIndex = self.ui.capMethodComboBox.findData(_DEFAULT_CAP_METHOD)
        capMethod = _DEFAULT_CAP_METHOD
    self.ui.capMethodComboBox.currentIndex = capMethodIndex
    self.ui.capConstraintFactorWidget.value = float(self._parameterNode.GetParameter("CapConstraintFactor"))
    self.ui.capNumberOfRingsWidget.value = float(self._parameterNode.GetParameter("CapNumberOfRings"))
    remeshCaps = (self._parameterNode.GetParameter("RemeshCaps") == "true")
    self.ui.remeshCapsCheckBox.checked = remeshCaps
    self.ui.capTargetEdgeLengthWidget.value = float(self._parameterNode.GetParameter("CapTargetEdgeLength"))
    self.updateCapMethodUI(cap, capMethod, remeshCaps)
    labelModelFaces = (self._parameterNode.GetParameter("LabelModelFaces") == "true")
    self.ui.labelModelFacesCheckBox.checked = labelModelFaces
    # Only write the line edit when it differs, so a GUI refresh does not move the text cursor.
    modelFaceIdArrayName = self._parameterNode.GetParameter("ModelFaceIdArrayName")
    if self.ui.modelFaceIdArrayNameLineEdit.text != modelFaceIdArrayName:
        self.ui.modelFaceIdArrayNameLineEdit.text = modelFaceIdArrayName
    self.ui.modelFaceIdArrayNameLabel.enabled = labelModelFaces
    self.ui.modelFaceIdArrayNameLineEdit.enabled = labelModelFaces
    addFlowExtensions = (self._parameterNode.GetParameter("ExtendOutputSurface") == "true")
    self.ui.addFlowExtensionsCheckBox.checked = addFlowExtensions
    # The per-endpoint extension length scale only has an effect when flow extensions are added.
    self.ui.extensionScaleLabel.setVisible(addFlowExtensions)
    self.ui.extensionScaleWidget.setVisible(addFlowExtensions)
    self.ui.extensionRatioWidget.value = float(self._parameterNode.GetParameter("ExtensionRatio"))
    self.ui.transitionRatioWidget.value = float(self._parameterNode.GetParameter("ExtensionTransitionRatio"))
    extensionModeIndex = self.ui.extensionModeComboBox.findData(_normalizedModeId(self._parameterNode.GetParameter("ExtensionMode")))
    if extensionModeIndex >= 0:
        self.ui.extensionModeComboBox.currentIndex = extensionModeIndex
    interpolationModeIndex = self.ui.interpolationModeComboBox.findData(_normalizedModeId(self._parameterNode.GetParameter("InterpolationMode")))
    if interpolationModeIndex >= 0:
        self.ui.interpolationModeComboBox.currentIndex = interpolationModeIndex
    self.ui.preserveCrossSectionShapeCheckBox.checked = (self._parameterNode.GetParameter("PreserveCrossSectionShape") == "true")
    autoApply = self._parameterNode.GetParameter("AutoApplyPlane") == "true"
    self.ui.applyButton.checkable = autoApply
    self.ui.applyButton.checked = autoApply
    self.ui.clipPointInsetFactorWidget.value = float(self._parameterNode.GetParameter("ClipPointInsetFactor"))
    self.ui.detectClipPointsButton.enabled = self._parameterNode.GetNodeReference("InputCenterlines") is not None
    self.ui.snapClipPointsToCenterlineCheckBox.checked = (self._parameterNode.GetParameter("SnapClipPointsToCenterline") == "true")
    self.updateManualPlaneButtonStates()
    clippingMethod = self._parameterNode.GetParameter("ClippingMethod") or "PLANE_PATCH"
    clippingMethodIndex = self.ui.clippingMethodComboBox.findData(clippingMethod)
    if clippingMethodIndex < 0:
        # Unknown value (e.g. from a scene saved by a different version): fall back to the
        # first method and keep the rest of the GUI consistent with that choice.
        clippingMethodIndex = 0
        clippingMethod = self.ui.clippingMethodComboBox.itemData(clippingMethodIndex)
    self.ui.clippingMethodComboBox.currentIndex = clippingMethodIndex
    self.ui.localSphereRadiusFactorWidget.value = float(self._parameterNode.GetParameter("LocalSphereRadiusFactor"))
    self.updateClippingMethodUI(clippingMethod)
    self.ui.freeNormalHandleCheckBox.checked = (self._parameterNode.GetParameter("FreeNormalHandle") == "true")
    self.updatePlaneHandleMode()
    self.observeClipPointsNode(self._parameterNode.GetNodeReference("ClipPoints"))
    self.updateClipPointsSnapMode()
    self.updateOutputVisibilityButton()
    self.updateOutputEdgesButton()
    self.updateInputVisibilityButtons()

    if self.logic.lastPlanarityFailures:
        failedLabels = [result["label"] for result in self.logic.lastPlanarityFailures]
        self.ui.clipStatusLabel.text = _("Non-planar cuts: {failed_labels}").format(failed_labels=", ".join(failedLabels))
        self.ui.clipStatusLabel.styleSheet = "QLabel { color: #d08000; }"
    elif self.logic.lastPlanarityResults:
        self.ui.clipStatusLabel.text = _("All cuts are planar.")
        self.ui.clipStatusLabel.styleSheet = "QLabel { color: #008000; }"
    else:
        self.ui.clipStatusLabel.text = _("Click a clip point to show and adjust its clip plane.")
    
    # Update buttons states and tooltips
    if self._parameterNode.GetNodeReference("InputSurface") and self._parameterNode.GetNodeReference("InputCenterlines") and self._parameterNode.GetNodeReference("ClipPoints") and self._parameterNode.GetNodeReference("OutputSurfaceModel"):
        self.ui.applyButton.toolTip = _("Clip vessel")
        self.ui.applyButton.enabled = True
    else:
        self.ui.applyButton.toolTip = _("Select input and output model nodes")
        self.ui.applyButton.enabled = False

    self.updatingGUIFromParameterNode = False
    if not slicer.mrmlScene.IsBatchProcessing():
        self.scheduleAutoApply()

  def onSceneBatchProcessEnded(self, caller=None, event=None):
    """Refresh restored parameters and apply them after scene loading finishes."""
    if self._parameterNode and slicer.mrmlScene.IsNodePresent(self._parameterNode):
        self.updateGUIFromParameterNode()

  def ensureOutputSurfaceNode(self, inputSurfaceNode):
    """Create and select a default output model when an input surface is available."""
    if not inputSurfaceNode or self._parameterNode.GetNodeReference("OutputSurfaceModel"):
        return
    outputName = inputSurfaceNode.GetName() + " clipped"
    outputModelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", outputName)
    outputModelNode.CreateDefaultDisplayNodes()
    self._parameterNode.SetNodeReferenceID("OutputSurfaceModel", outputModelNode.GetID())
    self.ui.outputSurfaceModelSelector.setCurrentNode(outputModelNode)

  def updateParameterNodeFromGUI(self, caller=None, event=None):
    """
    This method is called when the user makes any change in the GUI.
    The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
    """

    if self._parameterNode is None or self.updatingGUIFromParameterNode:
        # The updatingGUIFromParameterNode guard is essential: while updateGUIFromParameterNode
        # synchronizes the widgets (e.g. when switching between parameter set nodes), the node
        # selectors fire currentNodeChanged one by one, and writing the still-stale widget
        # states back here would wipe the node references of the newly selected parameter node
        # (leaving the Apply button disabled, among other data loss).
        return

    # Hold a local reference: reentrant signals (e.g. the parameter node selector switching
    # or the scene closing) can set self._parameterNode to None while this method runs.
    parameterNode = self._parameterNode

    for nodeSelector, roleName in self.nodeSelectors:
        parameterNode.SetNodeReferenceID(roleName, nodeSelector.currentNodeID)

    inputSurfaceNode = parameterNode.GetNodeReference("InputSurface")
    if inputSurfaceNode and inputSurfaceNode.IsA("vtkMRMLSegmentationNode"):
        parameterNode.SetParameter("InputSegmentID", self.ui.inputSegmentSelectorWidget.currentSegmentID())

    self.ui.inputSegmentSelectorWidget.setCurrentSegmentID(parameterNode.GetParameter("InputSegmentID"))
    self.ui.inputSegmentSelectorWidget.setVisible(inputSurfaceNode and inputSurfaceNode.IsA("vtkMRMLSegmentationNode"))

    wasModify = parameterNode.StartModify()
    parameterNode.SetParameter("TargetNumberOfPoints", str(self.ui.targetKPointCountWidget.value*1000.0))
    parameterNode.SetParameter("DecimationAggressiveness", str(self.ui.decimationAggressivenessWidget.value))
    parameterNode.SetParameter("PreprocessInputSurface", "true" if self.ui.preprocessInputSurfaceModelCheckBox.checked else "false")
    parameterNode.SetParameter("SubdivideInputSurface", "true" if self.ui.subdivideInputSurfaceModelCheckBox.checked else "false")
    parameterNode.SetParameter("CapOutputSurface", "true" if self.ui.capOutputSurfaceModelCheckBox.checked else "false")
    capMethod = self.ui.capMethodComboBox.currentData
    if capMethod:
        parameterNode.SetParameter("CapMethod", capMethod)
    parameterNode.SetParameter("CapConstraintFactor", str(self.ui.capConstraintFactorWidget.value))
    parameterNode.SetParameter("CapNumberOfRings", str(int(round(self.ui.capNumberOfRingsWidget.value))))
    parameterNode.SetParameter("RemeshCaps", "true" if self.ui.remeshCapsCheckBox.checked else "false")
    parameterNode.SetParameter("CapTargetEdgeLength", str(self.ui.capTargetEdgeLengthWidget.value))
    parameterNode.SetParameter("LabelModelFaces", "true" if self.ui.labelModelFacesCheckBox.checked else "false")
    parameterNode.SetParameter("ExtendOutputSurface", "true" if self.ui.addFlowExtensionsCheckBox.checked else "false")
    parameterNode.SetParameter("ExtensionRatio", str(self.ui.extensionRatioWidget.value))
    parameterNode.SetParameter("ExtensionTransitionRatio", str(self.ui.transitionRatioWidget.value))
    # currentData is None while the combobox is still empty (during widget setup); skip the
    # write instead of passing None to SetParameter.
    extensionMode = self.ui.extensionModeComboBox.currentData
    if extensionMode:
        parameterNode.SetParameter("ExtensionMode", extensionMode)
    interpolationMode = self.ui.interpolationModeComboBox.currentData
    if interpolationMode:
        parameterNode.SetParameter("InterpolationMode", interpolationMode)
    parameterNode.SetParameter("PreserveCrossSectionShape", "true" if self.ui.preserveCrossSectionShapeCheckBox.checked else "false")
    parameterNode.SetParameter("AutoApplyPlane", "true" if self.ui.applyButton.checked else "false")
    parameterNode.SetParameter("ClipPointInsetFactor", str(self.ui.clipPointInsetFactorWidget.value))
    parameterNode.SetParameter("SnapClipPointsToCenterline", "true" if self.ui.snapClipPointsToCenterlineCheckBox.checked else "false")
    clippingMethod = self.ui.clippingMethodComboBox.currentData
    if clippingMethod:
        parameterNode.SetParameter("ClippingMethod", clippingMethod)
    parameterNode.SetParameter("LocalSphereRadiusFactor", str(self.ui.localSphereRadiusFactorWidget.value))
    parameterNode.SetParameter("FreeNormalHandle", "true" if self.ui.freeNormalHandleCheckBox.checked else "false")
    parameterNode.EndModify(wasModify)
    # Changing a node reference (or re-writing an unchanged parameter value) does not emit a
    # ModifiedEvent on the parameter node, so GUI state that depends on the references - the
    # auto-created output node, the Apply button enabled state, etc. - would not refresh when
    # only a node selector changed. Refresh explicitly; the updatingGUIFromParameterNode flag
    # makes this recursion-safe.
    self.updateGUIFromParameterNode()
    self.scheduleAutoApply()

  def observeClipPointsNode(self, clipPointsNode):
    """Observe point interaction, not display hover, to select the endpoint plane."""
    if clipPointsNode == self._observedClipPointsNode:
        return
    if self._observedClipPointsNode:
        self.removeObserver(self._observedClipPointsNode, slicer.vtkMRMLMarkupsNode.PointStartInteractionEvent, self.onClipPointInteractionStarted)
        self.removeObserver(self._observedClipPointsNode, slicer.vtkMRMLMarkupsNode.PointModifiedEvent, self.onClipPointModified)
        self.removeObserver(self._observedClipPointsNode, slicer.vtkMRMLMarkupsNode.PointEndInteractionEvent, self.onClipPointInteractionEnded)
        self.removeObserver(self._observedClipPointsNode, slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self.onClipPointAdded)
        self.removeObserver(self._observedClipPointsNode, slicer.vtkMRMLMarkupsNode.PointRemovedEvent, self.onClipPointRemoved)
    self._observedClipPointsNode = clipPointsNode
    if clipPointsNode:
        clipPointsNode.CreateDefaultDisplayNodes()
        displayNode = clipPointsNode.GetDisplayNode()
        if displayNode:
            displayNode.SetPointLabelsVisibility(True)
            if hasattr(displayNode, "SetOccludedVisibility"):
                displayNode.SetOccludedVisibility(True)
        self.addObserver(clipPointsNode, slicer.vtkMRMLMarkupsNode.PointStartInteractionEvent, self.onClipPointInteractionStarted)
        self.addObserver(clipPointsNode, slicer.vtkMRMLMarkupsNode.PointModifiedEvent, self.onClipPointModified)
        self.addObserver(clipPointsNode, slicer.vtkMRMLMarkupsNode.PointEndInteractionEvent, self.onClipPointInteractionEnded)
        # Placing or deleting a point changes the clip just as much as dragging one does, but
        # neither goes through the interaction events above (placement ends with a defined
        # position, deletion happens from the markups list or the Delete key), so the output
        # would have stayed stale until the next unrelated edit.
        self.addObserver(clipPointsNode, slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent, self.onClipPointAdded)
        self.addObserver(clipPointsNode, slicer.vtkMRMLMarkupsNode.PointRemovedEvent, self.onClipPointRemoved)
        self.updateClipPointsSnapMode()

  def activeClipPointId(self):
    """Control point ID of the clip point whose plane is being edited, or None."""
    clipPointsNode = self._parameterNode.GetNodeReference("ClipPoints") if self._parameterNode else None
    if not clipPointsNode or not (0 <= self._activeClipPointIndex < clipPointsNode.GetNumberOfControlPoints()):
        return None
    return clipPointsNode.GetNthControlPointID(self._activeClipPointIndex)

  def onLabelModelFacesToggled(self, checked=None):
    self.updateParameterNodeFromGUI()
    # An output already in the scene follows the checkbox straight away, not at the next Apply.
    self.updateOutputFaceColoring()

  def faceColorTable(self, create=True):
    """The color table naming and coloring each face, referenced from the parameter node so that
    it is saved with the scene."""
    node = self._parameterNode.GetNodeReference("FaceColorTable") if self._parameterNode else None
    if node is None and create and self._parameterNode is not None:
        node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLColorTableNode", _("Clip Vessel face colors"))
        node.SetTypeToUser()
        self._parameterNode.SetNodeReferenceID("FaceColorTable", node.GetID())
    return node

  def updateFaceColorTable(self):
    """Rebuild the color table naming each face from what the last run recorded, or return None
    before the first labeling run, when there are no names to show."""
    outputModelNode = self._parameterNode.GetNodeReference("OutputSurfaceModel") if self._parameterNode else None
    outputPolyData = outputModelNode.GetPolyData() if outputModelNode else None
    nameByFaceId = dict(self.logic.lastFaceIdLayout(outputPolyData))
    colorTableNode = self.faceColorTable() if nameByFaceId else None
    if colorTableNode is None:
        return None
    numberOfColors = max(nameByFaceId) + 1
    wasModifying = colorTableNode.StartModify()
    colorTableNode.SetNumberOfColors(numberOfColors)
    for faceId in range(numberOfColors):
        name = nameByFaceId.get(faceId)
        if name is None:
            # Entry 0, and any gap left by a clip point that made no cut. Opaque, because one
            # transparent entry makes VTK treat the whole model as translucent, but undefined so
            # that the legend leaves it out - it lists exactly the entries with GetColorDefined.
            colorTableNode.SetColor(faceId, "", 0.35, 0.35, 0.35, 1.0)
            colorTableNode.SetColorDefined(faceId, False)
        else:
            colorTableNode.SetColor(faceId, name, *_faceColor(faceId, faceId == self.logic.lastWallFaceId), 1.0)
    # A color table's lookup table spans 0-255 whatever its size, which would land every face id
    # on entry 0. Make the range describe the table so that face id N resolves to entry N.
    colorTableNode.GetLookupTable().SetTableRange(0, numberOfColors)
    colorTableNode.EndModify(wasModifying)
    return colorTableNode

  def updateOutputFaceColoring(self):
    """Color the output model by its face id array, with a legend naming each face, while
    labeling is on; plain surface color and no legend when it is off."""
    if self._parameterNode is None:
        return
    outputModelNode = self._parameterNode.GetNodeReference("OutputSurfaceModel")
    displayNode = outputModelNode.GetDisplayNode() if outputModelNode else None
    if displayNode is None:
        return
    arrayName = (self._parameterNode.GetParameter("ModelFaceIdArrayName")
                 or _DEFAULT_MODEL_FACE_ID_ARRAY_NAME)
    # Only color by the array if it is there: the checkbox can be ticked before the output has
    # ever been computed with labeling enabled.
    outputPolyData = outputModelNode.GetPolyData()
    colorTableNode = None
    if (self._parameterNode.GetParameter("LabelModelFaces") == "true" and outputPolyData is not None
            and outputPolyData.GetCellData().GetArray(arrayName) is not None):
        colorTableNode = self.faceColorTable(create=False) or self.updateFaceColorTable()
    displayNode.SetScalarVisibility(colorTableNode is not None)

    legendDisplayNode = slicer.modules.colors.logic().GetColorLegendDisplayNode(outputModelNode)
    if colorTableNode is None:
        if legendDisplayNode:
            legendDisplayNode.SetVisibility(False)
        return
    displayNode.SetActiveScalarName(arrayName)
    displayNode.SetActiveAttributeLocation(vtk.vtkAssignAttribute.CELL_DATA)
    displayNode.SetAndObserveColorNodeID(colorTableNode.GetID())
    displayNode.SetScalarRangeFlag(slicer.vtkMRMLDisplayNode.UseColorNodeScalarRange)

    if legendDisplayNode is None:
        legendDisplayNode = slicer.modules.colors.logic().AddDefaultColorLegendDisplayNode(outputModelNode)
        if legendDisplayNode is None:
            return
    legendDisplayNode.SetTitleText(arrayName)
    # The label format has to be set alongside UseColorNamesForLabels: turned on from code rather
    # than from the Colors module GUI it stays at the numeric default, and the scalar bar then
    # renders "(none)" for every row. Everything else the legend needs it takes from the model's
    # own display node, or decides for itself in this mode.
    legendDisplayNode.SetUseColorNamesForLabels(True)
    legendDisplayNode.SetLabelFormat(legendDisplayNode.GetDefaultTextLabelFormat())
    legendDisplayNode.SetVisibility(True)

  def onModelFaceIdArrayNameEditingFinished(self):
    """Write the face id array name back to the parameter node once the user is done editing
    it. An empty name cannot address a cell array, so it falls back to the default."""
    if self._parameterNode is None:
        return
    modelFaceIdArrayName = self.ui.modelFaceIdArrayNameLineEdit.text.strip()
    if not modelFaceIdArrayName:
        modelFaceIdArrayName = _DEFAULT_MODEL_FACE_ID_ARRAY_NAME
        self.ui.modelFaceIdArrayNameLineEdit.text = modelFaceIdArrayName
    self._parameterNode.SetParameter("ModelFaceIdArrayName", modelFaceIdArrayName)
    self.updateOutputFaceColoring()

  def onSnapClipPointsToCenterlineToggled(self, checked=None):
    self.updateParameterNodeFromGUI()
    self.updateClipPointsSnapMode()

  def onEnableManualPlaneOriginToggled(self, checked=None):
    self.updateClipPointsSnapMode()
    self.updatePlaneHandleMode()
    if self.updatingGUIFromParameterNode or self._updatingManualPlaneButtons:
        # The button is being synchronized to the active point's stored state, not toggled
        # by the user: don't modify the stored manual origins.
        return
    pointId = self.activeClipPointId()
    planeNode = self._parameterNode.GetNodeReference("ManualClipPlane") if self._parameterNode else None
    if pointId is None or not planeNode:
        return
    origin, normal = self.logic.manualPlaneOriginNormal(planeNode)
    if checked:
        # Keep the current origin as a manual override for this point.
        self._manualPlaneOrigins[pointId] = list(origin)
    else:
        # Back to centerline-based: drop the manual override and move the plane (and its
        # clip point) onto the centerline. Snap directly (not via snapOriginToCenterline)
        # so this works regardless of the global drag-snapping checkbox.
        self._manualPlaneOrigins.pop(pointId, None)
        centerlinesNode = self._parameterNode.GetNodeReference("InputCenterlines")
        snappedOrigin = self.logic.closestPointOnCenterline(centerlinesNode, origin) if centerlinesNode else None
        if snappedOrigin is not None:
            origin = list(snappedOrigin)
        normal = self.snapNormalToCenterline(origin, normal)
        clipPointsNode = self._parameterNode.GetNodeReference("ClipPoints")
        self._updatingInteractivePlane = True
        clipPointsNode.SetNthControlPointPositionWorld(self._activeClipPointIndex, origin)
        planeNode.SetOriginWorld(origin)
        planeNode.SetNormalWorld(normal)
        self.repositionNormalHandle(origin, normal)
        self._updatingInteractivePlane = False
    self.saveManualPlaneNormals()
    self.scheduleAutoApply()

  def onEnableManualPlaneNormalToggled(self, checked=None):
    self.updatePlaneHandleMode()
    if self.updatingGUIFromParameterNode or self._updatingManualPlaneButtons:
        # The button is being synchronized to the active point's stored state, not toggled
        # by the user: don't modify the stored manual normals.
        return
    pointId = self.activeClipPointId()
    planeNode = self._parameterNode.GetNodeReference("ManualClipPlane") if self._parameterNode else None
    if pointId is None or not planeNode:
        return
    origin, normal = self.logic.manualPlaneOriginNormal(planeNode)
    if checked:
        # Keep the current normal as a manual override for this point.
        self._manualPlaneNormals[pointId] = list(normal)
    else:
        # Back to centerline-based: drop the manual override and re-orient the plane along
        # the centerline.
        self._manualPlaneNormals.pop(pointId, None)
        normal = self.snapNormalToCenterline(origin, normal)
        self._updatingInteractivePlane = True
        planeNode.SetNormalWorld(normal)
        self.repositionNormalHandle(origin, normal)
        self._updatingInteractivePlane = False
    self.saveManualPlaneNormals()
    self.scheduleAutoApply()

  def updateManualPlaneButtonStates(self):
    """Sync the manual-adjustment buttons and the per-endpoint extension length scale slider
    with the active clip point: a button is pressed when the point has a manual override in
    the corresponding list (released means the plane follows the centerline), the slider shows
    the point's extension length scale factor (1.0 when it has none), and the widgets are only
    enabled while a clip plane is being edited."""
    pointId = self.activeClipPointId() if self._planeEditing else None
    self.ui.enableManualPlaneOrigin.enabled = pointId is not None
    self.ui.enableManualPlaneNormal.enabled = pointId is not None
    self.ui.extensionScaleWidget.enabled = pointId is not None
    self._updatingManualPlaneButtons = True
    self.ui.enableManualPlaneOrigin.checked = pointId is not None and pointId in self._manualPlaneOrigins
    self.ui.enableManualPlaneNormal.checked = pointId is not None and pointId in self._manualPlaneNormals
    self.ui.extensionScaleWidget.value = self._extensionLengthScaleFactors.get(pointId, 1.0) if pointId is not None else 1.0
    self._updatingManualPlaneButtons = False
    self.updateClipPointsSnapMode()

  def onExtensionScaleChanged(self, value=None):
    if self.updatingGUIFromParameterNode or self._updatingManualPlaneButtons:
        # The slider is being synchronized to the active point's stored factor, not moved by
        # the user: don't modify the stored factors.
        return
    pointId = self.activeClipPointId() if self._planeEditing else None
    if pointId is None:
        return
    scaleFactor = self.ui.extensionScaleWidget.value
    if abs(scaleFactor - 1.0) < 1e-6:
        # 1.0 is the neutral factor: store nothing so the endpoint keeps following the common
        # extension length settings.
        self._extensionLengthScaleFactors.pop(pointId, None)
    else:
        self._extensionLengthScaleFactors[pointId] = scaleFactor
    self.saveManualPlaneNormals()
    self.scheduleAutoApply()

  def onFreeNormalHandleToggled(self, checked=None):
    self.updateParameterNodeFromGUI()
    self.updatePlaneHandleMode()

  def updateCapMethodUI(self, cap, capMethod, remeshCaps=False):
    """Show the cap method next to the cap checkbox, the shape controls of the smooth capper only
    when that method is the one selected, and the cap element size only when the caps are being
    remeshed to a uniform mesh."""
    self.ui.capMethodLabel.setVisible(cap)
    self.ui.capMethodComboBox.setVisible(cap)
    smooth = cap and capMethod == "SMOOTH"
    self.ui.capConstraintFactorLabel.setVisible(smooth)
    self.ui.capConstraintFactorWidget.setVisible(smooth)
    self.ui.capNumberOfRingsLabel.setVisible(smooth)
    self.ui.capNumberOfRingsWidget.setVisible(smooth)
    self.ui.remeshCapsLabel.setVisible(cap)
    self.ui.remeshCapsCheckBox.setVisible(cap)
    self.ui.capTargetEdgeLengthLabel.setVisible(cap and remeshCaps)
    self.ui.capTargetEdgeLengthWidget.setVisible(cap and remeshCaps)

  def onClippingMethodChanged(self, index=None):
    self.updateParameterNodeFromGUI()
    self.updateClippingMethodUI(self.ui.clippingMethodComboBox.currentData)

  def updateClippingMethodUI(self, clippingMethod):
    localMethod = clippingMethod in ("PLANE_SPHERE", "PLANE_PATCH", "BOX")
    self.ui.localSphereRadiusFactorLabel.setVisible(localMethod)
    self.ui.localSphereRadiusFactorWidget.setVisible(localMethod)
    if clippingMethod == "BOX":
        self.ui.localSphereRadiusFactorLabel.text = _("Local box size:")
    elif clippingMethod == "PLANE_PATCH":
        self.ui.localSphereRadiusFactorLabel.text = _("Local patch radius:")
    else:
        self.ui.localSphereRadiusFactorLabel.text = _("Local sphere radius:")

  def updatePlaneHandleMode(self):
    planeNode = self._parameterNode.GetNodeReference("ManualClipPlane") if self._parameterNode else None
    normalHandleNode = self._parameterNode.GetNodeReference("ManualClipPlaneNormalHandle") if self._parameterNode else None
    useFreeNormalHandle = self.ui.freeNormalHandleCheckBox.checked if self._parameterNode else False
    manualPlaneOrigin = self.ui.enableManualPlaneOrigin.checked if self._parameterNode else True
    manualPlaneNormal = self.ui.enableManualPlaneNormal.checked if self._parameterNode else True
    useStandardHandles = not useFreeNormalHandle
    if planeNode and planeNode.GetDisplayNode():
        displayNode = planeNode.GetDisplayNode()
        displayNode.SetHandlesInteractive(useStandardHandles)
        # While the orientation follows the centerline, rotating the plane manually would be
        # immediately undone, so the rotation handles are hidden.
        displayNode.SetRotationHandleVisibility(useStandardHandles and manualPlaneNormal)
        # Rotating the plane about its own normal (the blue z handle) never changes the cut,
        # and the free in-plane (view plane) rotation ring is redundant with the x/y rings,
        # so both are always hidden.
        displayNode.SetRotationHandleComponentVisibility(True, True, False, False)
        displayNode.SetTranslationHandleVisibility(useStandardHandles)
        if manualPlaneOrigin:
            displayNode.SetTranslationHandleComponentVisibility(True, True, True, True)
        else:
            # The origin is locked onto the centerline: in-plane (x/y) translation would be
            # immediately undone, so only sliding along the normal axis remains available.
            displayNode.SetTranslationHandleComponentVisibility(False, False, True, True)
        displayNode.SetScaleHandleVisibility(False)
    if normalHandleNode:
        normalHandleNode.SetDisplayVisibility(self._planeEditing and useFreeNormalHandle)

  def snapOriginToCenterline(self, origin):
    """Return origin snapped onto the input centerline, or origin unchanged if manual origin
    adjustment is enabled for the active point, global centerline snapping is disabled, no
    centerline is set, or the centerline has no points."""
    if self.ui.enableManualPlaneOrigin.checked or not self.ui.snapClipPointsToCenterlineCheckBox.checked:
        return origin
    centerlinesNode = self._parameterNode.GetNodeReference("InputCenterlines")
    if not centerlinesNode:
        return origin
    snappedOrigin = self.logic.closestPointOnCenterline(centerlinesNode, origin)
    return snappedOrigin if snappedOrigin is not None else origin

  def snapNormalToCenterline(self, origin, normal):
    """Return the centerline direction (oriented toward the branch end) at origin, or normal
    unchanged if manual normal adjustment is enabled for the active point."""
    if self.ui.enableManualPlaneNormal.checked:
        return normal
    centerlinesNode = self._parameterNode.GetNodeReference("InputCenterlines")
    if not centerlinesNode:
        return normal
    snappedNormal = self.logic.centerlineDirectionAtPosition(centerlinesNode, origin)
    return list(snappedNormal) if snappedNormal is not None else normal

  def updateClipPointsSnapMode(self):
    """While clip points follow the centerline (global snapping enabled and no manual origin
    adjustment for the active point), custom logic in onClipPointModified() takes over
    positioning, so the native display-node snap mode is left unconstrained. Otherwise fall
    back to Slicer's built-in snap-to-visible-surface behavior."""
    clipPointsNode = self._observedClipPointsNode
    if not clipPointsNode:
        return
    displayNode = clipPointsNode.GetDisplayNode()
    if not displayNode:
        return
    if not self.ui.enableManualPlaneOrigin.checked and self.ui.snapClipPointsToCenterlineCheckBox.checked:
        displayNode.SetSnapMode(slicer.vtkMRMLMarkupsDisplayNode.SnapModeUnconstrained)
    else:
        displayNode.SetSnapMode(slicer.vtkMRMLMarkupsDisplayNode.SnapModeToVisibleSurface)

  def updateInputSurfaceOpacity(self, inputSurfaceNode, opacity=0.4):
    """Keep the input surface see-through so clip points and their planes, which sit on or
    near its surface, stay visible underneath it. Handles both model and segmentation inputs."""
    if not inputSurfaceNode:
        return
    if not inputSurfaceNode.GetDisplayNode():
        inputSurfaceNode.CreateDefaultDisplayNodes()
    displayNode = inputSurfaceNode.GetDisplayNode()
    if not displayNode:
        return
    if inputSurfaceNode.IsA("vtkMRMLSegmentationNode"):
        displayNode.SetOpacity3D(opacity)
    else:
        displayNode.SetOpacity(opacity)

  def updateOutputVisibilityButton(self):
    """Sync the Outputs show/hide button with the output model's actual display visibility,
    without triggering onToggleOutputVisibilityButton (which would otherwise flip visibility
    right back)."""
    outputModelNode = self._parameterNode.GetNodeReference("OutputSurfaceModel") if self._parameterNode else None
    displayNode = outputModelNode.GetDisplayNode() if outputModelNode else None
    self.ui.toggleOutputVisibilityButton.enabled = displayNode is not None
    visible = displayNode.GetVisibility() if displayNode else True
    wasBlocked = self.ui.toggleOutputVisibilityButton.blockSignals(True)
    self.ui.toggleOutputVisibilityButton.checked = visible
    self.ui.toggleOutputVisibilityButton.toolTip = _("Hide output surface") if visible else _("Show output surface")
    self.ui.toggleOutputVisibilityButton.blockSignals(wasBlocked)

  def onToggleOutputVisibilityButton(self, checked=None):
    outputModelNode = self._parameterNode.GetNodeReference("OutputSurfaceModel") if self._parameterNode else None
    displayNode = outputModelNode.GetDisplayNode() if outputModelNode else None
    if displayNode:
        displayNode.SetVisibility(checked)
    self.ui.toggleOutputVisibilityButton.toolTip = _("Hide output surface") if checked else _("Show output surface")

  def updateOutputEdgesButton(self):
    """Sync the Outputs edge toggle with the output model display node."""
    outputModelNode = self._parameterNode.GetNodeReference("OutputSurfaceModel") if self._parameterNode else None
    displayNode = outputModelNode.GetDisplayNode() if outputModelNode else None
    self.ui.toggleOutputEdgesButton.enabled = displayNode is not None
    edgeVisible = displayNode.GetEdgeVisibility() if displayNode else False
    wasBlocked = self.ui.toggleOutputEdgesButton.blockSignals(True)
    self.ui.toggleOutputEdgesButton.checked = edgeVisible
    self.ui.toggleOutputEdgesButton.blockSignals(wasBlocked)

  def onToggleOutputEdgesButton(self, checked=None):
    outputModelNode = self._parameterNode.GetNodeReference("OutputSurfaceModel") if self._parameterNode else None
    displayNode = outputModelNode.GetDisplayNode() if outputModelNode else None
    if displayNode:
        displayNode.SetEdgeVisibility(checked)

  def updateInputVisibilityButtons(self):
    for button, roleName, objectName in self.inputVisibilityButtons:
        node = self._parameterNode.GetNodeReference(roleName) if self._parameterNode else None
        displayNode = node.GetDisplayNode() if node else None
        button.enabled = displayNode is not None
        visible = displayNode.GetVisibility() if displayNode else True
        wasBlocked = button.blockSignals(True)
        button.checked = visible
        button.toolTip = (_("Hide {object_name}") if visible else _("Show {object_name}")).format(object_name=objectName)
        button.blockSignals(wasBlocked)

  def onToggleNodeVisibility(self, roleName, checked, button, objectName):
    node = self._parameterNode.GetNodeReference(roleName) if self._parameterNode else None
    displayNode = node.GetDisplayNode() if node else None
    if displayNode:
        displayNode.SetVisibility(checked)
    button.toolTip = (_("Hide {object_name}") if checked else _("Show {object_name}")).format(object_name=objectName)

  def finishPlaneEditing(self):
    """Hide temporary plane markups and leave interactive plane editing mode."""
    planeNode = self._parameterNode.GetNodeReference("ManualClipPlane") if self._parameterNode else None
    normalHandleNode = self._parameterNode.GetNodeReference("ManualClipPlaneNormalHandle") if self._parameterNode else None
    if planeNode:
        planeNode.SetDisplayVisibility(False)
    if normalHandleNode:
        normalHandleNode.SetDisplayVisibility(False)
    self._activeClipPointIndex = -1
    self._activeClipPointId = None
    self._planeEditing = False
    self.updateManualPlaneButtonStates()
    self.ui.finishPlaneEditingButton.enabled = False
    self.ui.clipStatusLabel.text = _("Plane editing finished. Click a clip point to edit another plane.")
    self.ui.clipStatusLabel.styleSheet = ""

  def observeInteractivePlaneNode(self, planeNode):
    if planeNode == self._observedInteractivePlaneNode:
        return
    if self._observedInteractivePlaneNode:
        self.removeObserver(self._observedInteractivePlaneNode, slicer.vtkMRMLMarkupsNode.PointModifiedEvent, self.onInteractivePlaneModified)
        self.removeObserver(self._observedInteractivePlaneNode, slicer.vtkMRMLMarkupsNode.PointEndInteractionEvent, self.onInteractivePlaneInteractionEnded)
    self._observedInteractivePlaneNode = planeNode
    if planeNode:
        self.addObserver(planeNode, slicer.vtkMRMLMarkupsNode.PointModifiedEvent, self.onInteractivePlaneModified)
        self.addObserver(planeNode, slicer.vtkMRMLMarkupsNode.PointEndInteractionEvent, self.onInteractivePlaneInteractionEnded)

  def observeNormalHandleNode(self, handleNode):
    """Observe the separate draggable point that represents the tip of the plane's normal vector."""
    if handleNode == self._observedNormalHandleNode:
        return
    if self._observedNormalHandleNode:
        self.removeObserver(self._observedNormalHandleNode, slicer.vtkMRMLMarkupsNode.PointModifiedEvent, self.onNormalHandleModified)
        self.removeObserver(self._observedNormalHandleNode, slicer.vtkMRMLMarkupsNode.PointEndInteractionEvent, self.onNormalHandleInteractionEnded)
    self._observedNormalHandleNode = handleNode
    if handleNode:
        self.addObserver(handleNode, slicer.vtkMRMLMarkupsNode.PointModifiedEvent, self.onNormalHandleModified)
        self.addObserver(handleNode, slicer.vtkMRMLMarkupsNode.PointEndInteractionEvent, self.onNormalHandleInteractionEnded)

  def repositionNormalHandle(self, origin, normal):
    """Keep the normal handle glued to the plane: origin + normal * (last chosen handle distance)."""
    normalHandleNode = self._parameterNode.GetNodeReference("ManualClipPlaneNormalHandle") if self._parameterNode else None
    if not normalHandleNode or normalHandleNode.GetNumberOfControlPoints() == 0:
        return
    newHandlePosition = [origin[axis] + normal[axis] * self._normalHandleDistance for axis in range(3)]
    normalHandleNode.SetNthControlPointPositionWorld(0, newHandlePosition)

  def manualPlaneNormalsFromParameterNode(self):
    try:
        normals = json.loads(self._parameterNode.GetParameter("ManualClipPlaneNormals") or "{}")
        return {pointId: [float(value) for value in normal] for pointId, normal in normals.items()}
    except (ValueError, TypeError):
        logging.warning("Ignoring invalid saved Clip Vessel plane normals")
        return {}

  def manualPlaneOriginsFromParameterNode(self):
    try:
        origins = json.loads(self._parameterNode.GetParameter("ManualClipPlaneOrigins") or "{}")
        return {pointId: [float(value) for value in origin] for pointId, origin in origins.items()}
    except (ValueError, TypeError):
        logging.warning("Ignoring invalid saved Clip Vessel plane origins")
        return {}

  def extensionScaleFactorsFromParameterNode(self):
    try:
        factors = json.loads(self._parameterNode.GetParameter("ExtensionLengthScaleFactors") or "{}")
        return {pointId: float(value) for pointId, value in factors.items()}
    except (ValueError, TypeError):
        logging.warning("Ignoring invalid saved Clip Vessel extension length scale factors")
        return {}

  def saveManualPlaneNormals(self):
    if self._parameterNode:
        self._parameterNode.SetParameter("ManualClipPlaneNormals", json.dumps(self._manualPlaneNormals, separators=(",", ":")))
        self._parameterNode.SetParameter("ManualClipPlaneOrigins", json.dumps(self._manualPlaneOrigins, separators=(",", ":")))
        self._parameterNode.SetParameter("ExtensionLengthScaleFactors", json.dumps(self._extensionLengthScaleFactors, separators=(",", ":")))

  def onClipPointInteractionStarted(self, caller=None, event=None):
    displayNode = caller.GetDisplayNode() if caller else None
    if not displayNode or displayNode.GetActiveComponentType() != slicer.vtkMRMLMarkupsDisplayNode.ComponentControlPoint:
        return
    pointIndex = displayNode.GetActiveComponentIndex()
    if 0 <= pointIndex < caller.GetNumberOfControlPoints():
        # A plain click to select an endpoint fires Start/End the same as a real drag, even
        # with no movement in between. Remember where the point started so the End handler
        # can tell the two apart and skip re-clipping when nothing actually moved.
        startPosition = [0.0, 0.0, 0.0]
        caller.GetNthControlPointPositionWorld(pointIndex, startPosition)
        self._clipPointDragStartPosition = tuple(startPosition)
        self.showInteractiveClipPlane(pointIndex)

  def showInteractiveClipPlane(self, pointIndex):
    clipPointsNode = self._parameterNode.GetNodeReference("ClipPoints")
    centerlinesNode = self._parameterNode.GetNodeReference("InputCenterlines")
    if not clipPointsNode or not centerlinesNode:
        return

    planeNode = self._parameterNode.GetNodeReference("ManualClipPlane")
    if not planeNode:
        planeNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsPlaneNode", "Clip plane adjustment")
        planeNode.CreateDefaultDisplayNodes()
        planeNode.SetHideFromEditors(True)
        planeDisplayNode = planeNode.GetDisplayNode()
        if planeDisplayNode:
            # Hide the floating "Clip plane adjustment" name/measurement annotation.
            planeDisplayNode.SetPropertiesLabelVisibility(False)
            planeDisplayNode.SetPointLabelsVisibility(False)
        self._parameterNode.SetNodeReferenceID("ManualClipPlane", planeNode.GetID())
    self.observeInteractivePlaneNode(planeNode)

    normalHandleNode = self._parameterNode.GetNodeReference("ManualClipPlaneNormalHandle")
    if not normalHandleNode:
        normalHandleNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "Clip plane normal handle")
        normalHandleNode.CreateDefaultDisplayNodes()
        normalHandleNode.SetHideFromEditors(True)
        handleDisplayNode = normalHandleNode.GetDisplayNode()
        if handleDisplayNode:
            handleDisplayNode.SetGlyphScale(2.0)
            handleDisplayNode.SetColor(1.0, 0.6, 0.0)
            handleDisplayNode.SetSelectedColor(1.0, 0.6, 0.0)
            handleDisplayNode.SetPointLabelsVisibility(False)
            handleDisplayNode.SetPropertiesLabelVisibility(False)
            # Don't let this handle snap onto the model surface while dragging: it represents
            # a direction in free space, not a point on the vessel.
            handleDisplayNode.SetSnapMode(slicer.vtkMRMLMarkupsDisplayNode.SnapModeUnconstrained)
        self._parameterNode.SetNodeReferenceID("ManualClipPlaneNormalHandle", normalHandleNode.GetID())
    self.observeNormalHandleNode(normalHandleNode)

    automaticOrigin, automaticNormal, radius = self.logic.automaticClipPlane(centerlinesNode, clipPointsNode, pointIndex)
    pointId = clipPointsNode.GetNthControlPointID(pointIndex)
    origin = self._manualPlaneOrigins.get(pointId, automaticOrigin)
    normal = self._manualPlaneNormals.get(pointId, automaticNormal)
    self._normalHandleDistance = max(radius * 2.0, 1.0)

    self._activeClipPointIndex = pointIndex
    self._activeClipPointId = pointId
    self._planeEditing = True
    # Reflect this point's stored manual-override state in the snap buttons before the
    # handle visibility (which depends on the button states) is updated below.
    self.updateManualPlaneButtonStates()
    self._updatingInteractivePlane = True  # suppress re-entrant modified events during setup
    wasModify = planeNode.StartModify()
    planeNode.RemoveAllControlPoints()
    planeNode.SetPlaneType(slicer.vtkMRMLMarkupsPlaneNode.PlaneTypePointNormal)
    planeNode.AddControlPointWorld(vtk.vtkVector3d(origin))
    planeNode.SetNormalWorld(normal)
    # Inside a StartModify batch, SetNormalWorld resets the plane's not-yet-synchronized
    # origin (the control point just added above) to (0,0,0); restore it explicitly.
    planeNode.SetOriginWorld(origin)
    # Purely cosmetic: the rendered rectangle's size has no effect on the actual cut, which is
    # now an infinite plane bounded only by mesh connectivity.
    planeNode.SetSize(radius * 4.0, radius * 4.0)
    planeNode.EndModify(wasModify)
    planeNode.SetDisplayVisibility(True)
    handleWasModify = normalHandleNode.StartModify()
    normalHandleNode.RemoveAllControlPoints()
    normalHandlePoint = [origin[axis] + normal[axis] * self._normalHandleDistance for axis in range(3)]
    normalHandleNode.AddControlPointWorld(vtk.vtkVector3d(normalHandlePoint))
    normalHandleNode.SetNthControlPointLabel(0, _("Normal"))
    normalHandleNode.EndModify(handleWasModify)
    normalHandleNode.SetDisplayVisibility(True)
    self.updatePlaneHandleMode()
    self._updatingInteractivePlane = False

    slicer.modules.markups.logic().SetActiveListID(planeNode)
    self.ui.finishPlaneEditingButton.enabled = True
    applyHint = _("Changes apply when released.") if self.ui.applyButton.checked else _("Click Apply when ready.")
    self.ui.clipStatusLabel.text = _("Adjusting {point_label}: drag the center point to move it, or drag the orange handle to set the normal. {apply_hint}").format(
        point_label=clipPointsNode.GetNthControlPointLabel(pointIndex), apply_hint=applyHint)
    self.ui.clipStatusLabel.styleSheet = ""

  def onInteractivePlaneModified(self, caller=None, event=None):
    if self._updatingInteractivePlane or self._activeClipPointIndex < 0:
        return
    clipPointsNode = self._parameterNode.GetNodeReference("ClipPoints")
    if not clipPointsNode or self._activeClipPointIndex >= clipPointsNode.GetNumberOfControlPoints():
        return
    origin, normal = self.logic.manualPlaneOriginNormal(caller)
    # The plane markup's control point sits on top of the clip-point fiducial, so dragging the
    # plane lands here instead of in onClipPointModified; snap it the same way so it stays on the
    # centerline rather than being pulled onto the input surface.
    origin = self.snapOriginToCenterline(origin)
    normal = self.snapNormalToCenterline(origin, normal)
    pointId = clipPointsNode.GetNthControlPointID(self._activeClipPointIndex)
    # Only points with manual adjustment enabled carry an override; the other points always
    # derive their plane from the centerline.
    if self.ui.enableManualPlaneOrigin.checked:
        self._manualPlaneOrigins[pointId] = list(origin)
    if self.ui.enableManualPlaneNormal.checked:
        self._manualPlaneNormals[pointId] = list(normal)
    self._updatingInteractivePlane = True  # suppress re-entrant modified events from our writes
    clipPointsNode.SetNthControlPointPositionWorld(self._activeClipPointIndex, origin)
    caller.SetOriginWorld(origin)  # keep the plane on the snapped origin too
    caller.SetNormalWorld(normal)  # keep the plane orientation snapped too
    self.repositionNormalHandle(origin, normal)
    self._updatingInteractivePlane = False

  def onClipPointModified(self, caller=None, event=None):
    if self._updatingInteractivePlane or self._activeClipPointIndex < 0:
        return
    planeNode = self._parameterNode.GetNodeReference("ManualClipPlane")
    if not planeNode or self._activeClipPointIndex >= caller.GetNumberOfControlPoints():
        return
    origin = [0.0, 0.0, 0.0]
    caller.GetNthControlPointPositionWorld(self._activeClipPointIndex, origin)
    # Keep the dragged point on the centerline (no-op when snapping is disabled).
    origin = self.snapOriginToCenterline(origin)

    self._updatingInteractivePlane = True  # suppress re-entrant modified events from our writes
    caller.SetNthControlPointPositionWorld(self._activeClipPointIndex, origin)
    planeNode.SetOriginWorld(origin)
    normal = [0.0, 0.0, 1.0]
    planeNode.GetNormalWorld(normal)
    # Keep the plane orientation locked to the centerline while the point slides along it
    # (no-op when orientation snapping is disabled).
    normal = self.snapNormalToCenterline(origin, normal)
    planeNode.SetNormalWorld(normal)
    self.repositionNormalHandle(origin, normal)
    self._updatingInteractivePlane = False

  def onNormalHandleModified(self, caller=None, event=None):
    """Fires while the user drags the orange normal-handle point; re-orients the plane to match."""
    if self._updatingInteractivePlane or self._activeClipPointIndex < 0:
        return
    planeNode = self._parameterNode.GetNodeReference("ManualClipPlane")
    if not planeNode or not caller or caller.GetNumberOfControlPoints() == 0:
        return
    origin = [0.0, 0.0, 0.0]
    planeNode.GetOriginWorld(origin)
    handlePosition = [0.0, 0.0, 0.0]
    caller.GetNthControlPointPositionWorld(0, handlePosition)
    normal = [handlePosition[axis] - origin[axis] for axis in range(3)]
    length = vtk.vtkMath.Norm(normal)
    if length < 1e-6:
        # Handle dragged onto the origin: ignore, keep the previous normal.
        return
    vtk.vtkMath.Normalize(normal)
    # With orientation snapping enabled the handle only adjusts its own distance; the plane
    # normal stays locked to the centerline and the handle is pulled back onto that axis.
    normal = self.snapNormalToCenterline(origin, normal)
    self._normalHandleDistance = length
    self._updatingInteractivePlane = True
    planeNode.SetNormalWorld(normal)
    self.repositionNormalHandle(origin, normal)
    self._updatingInteractivePlane = False

  def onNormalHandleInteractionEnded(self, caller=None, event=None):
    self.onNormalHandleModified(caller, event)
    clipPointsNode = self._parameterNode.GetNodeReference("ClipPoints")
    planeNode = self._parameterNode.GetNodeReference("ManualClipPlane")
    if clipPointsNode and planeNode and 0 <= self._activeClipPointIndex < clipPointsNode.GetNumberOfControlPoints():
        pointId = clipPointsNode.GetNthControlPointID(self._activeClipPointIndex)
        origin, normal = self.logic.manualPlaneOriginNormal(planeNode)
        if self.ui.enableManualPlaneOrigin.checked:
            self._manualPlaneOrigins[pointId] = list(origin)
        if self.ui.enableManualPlaneNormal.checked:
            self._manualPlaneNormals[pointId] = list(normal)
        self.saveManualPlaneNormals()
    self.scheduleAutoApply()

  def onInteractivePlaneInteractionEnded(self, caller=None, event=None):
    self.onInteractivePlaneModified(caller, event)
    self.saveManualPlaneNormals()
    self.scheduleAutoApply()

  def onClipPointInteractionEnded(self, caller=None, event=None):
    self.onClipPointModified(caller, event)
    planeNode = self._parameterNode.GetNodeReference("ManualClipPlane")
    if planeNode:
        self.onInteractivePlaneModified(planeNode)
        self.saveManualPlaneNormals()

    # Only re-clip if the point actually moved. A plain click to select a different
    # endpoint fires this same End event with zero movement; it should just show that
    # endpoint's plane (already done above), not trigger a re-clip.
    moved = True
    if caller and self._clipPointDragStartPosition is not None and 0 <= self._activeClipPointIndex < caller.GetNumberOfControlPoints():
        endPosition = [0.0, 0.0, 0.0]
        caller.GetNthControlPointPositionWorld(self._activeClipPointIndex, endPosition)
        moved = vtk.vtkMath.Distance2BetweenPoints(self._clipPointDragStartPosition, endPosition) > 1e-8
    self._clipPointDragStartPosition = None

    if moved:
        self.scheduleAutoApply()

  def onClipPointAdded(self, caller=None, event=None):
    """A newly placed clip point adds a cut, so refresh the output. Observing the
    position-defined event rather than the point-added event skips the preview point that
    follows the mouse while placement is still in progress."""
    if self._updatingInteractivePlane:
        return
    self.scheduleAutoApply()

  def onClipPointRemoved(self, caller=None, event=None):
    """A deleted clip point removes a cut, so refresh the output."""
    if self._updatingInteractivePlane:
        return
    self.forgetRemovedClipPointOverrides(caller)
    self.resyncActiveClipPointIndex(caller)
    self.scheduleAutoApply()

  def forgetRemovedClipPointOverrides(self, clipPointsNode):
    """Drop the manual plane and extension length overrides of points that no longer exist,
    so they neither accumulate in the saved scene nor come back to life if a control point ID
    is ever reused."""
    remainingIds = set()
    if clipPointsNode:
        remainingIds = {clipPointsNode.GetNthControlPointID(index)
                        for index in range(clipPointsNode.GetNumberOfControlPoints())}
    removedAny = False
    for overrides in (self._manualPlaneNormals, self._manualPlaneOrigins, self._extensionLengthScaleFactors):
        for pointId in [pointId for pointId in overrides if pointId not in remainingIds]:
            del overrides[pointId]
            removedAny = True
    if removedAny:
        self.saveManualPlaneNormals()

  def resyncActiveClipPointIndex(self, clipPointsNode):
    """Deleting a point shifts the indices of every point after it, so re-find the point
    whose plane is being edited by its ID; if that point is the deleted one, stop editing."""
    if self._activeClipPointIndex < 0:
        return
    newIndex = -1
    if clipPointsNode and self._activeClipPointId is not None:
        for index in range(clipPointsNode.GetNumberOfControlPoints()):
            if clipPointsNode.GetNthControlPointID(index) == self._activeClipPointId:
                newIndex = index
                break
    if newIndex < 0:
        self.finishPlaneEditing()
    else:
        self._activeClipPointIndex = newIndex

  def onDetectClipPointsButton(self):
    """Populate ClipPoints with one point per centerline terminus (the inlet plus every
    branch outlet), each pulled inward from the vessel surface by the configured inset.
    ExtractCenterline places its endpoints exactly on the vessel surface, which previously
    meant the user had to manually drag every clip point inward before its plane was
    positioned correctly; this detects and insets them automatically instead."""
    if not self._parameterNode:
        return
    centerlinesNode = self._parameterNode.GetNodeReference("InputCenterlines")
    if not centerlinesNode:
        slicer.util.errorDisplay(_("Select input centerlines first."))
        return

    insetFactor = self.ui.clipPointInsetFactorWidget.value
    # As in onApplyButton: the details section carries the traceback, nothing is shown while
    # testing, and the failure is re-raised rather than reported and stepped over.
    with slicer.util.tryWithErrorDisplay(_("Failed to detect clip points."), waitCursor=True):
        terminuses = self.logic.detectCenterlineTerminusClipPoints(centerlinesNode, insetFactor)
    if not terminuses:
        slicer.util.errorDisplay(_("Could not detect any centerline terminuses. Check the input centerlines."))
        return

    clipPointsNode = self._parameterNode.GetNodeReference("ClipPoints")
    if not clipPointsNode:
        clipPointsNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", _("Clip points"))
        self._parameterNode.SetNodeReferenceID("ClipPoints", clipPointsNode.GetID())
    elif clipPointsNode.GetNumberOfControlPoints() > 0:
        if not slicer.util.confirmYesNoDisplay(
                _("This will replace the {point_count} existing clip point(s) with points detected from the centerline. Continue?")
                .format(point_count=clipPointsNode.GetNumberOfControlPoints())):
            return

    # Stop showing/adjusting whatever plane was up before the points underneath it are replaced.
    self._activeClipPointIndex = -1
    self._activeClipPointId = None
    self._planeEditing = False
    self.ui.finishPlaneEditingButton.enabled = False
    planeNode = self._parameterNode.GetNodeReference("ManualClipPlane")
    if planeNode:
        planeNode.SetDisplayVisibility(False)
    normalHandleNode = self._parameterNode.GetNodeReference("ManualClipPlaneNormalHandle")
    if normalHandleNode:
        normalHandleNode.SetDisplayVisibility(False)

    wasModify = clipPointsNode.StartModify()
    clipPointsNode.RemoveAllControlPoints()
    for terminus in terminuses:
        index = clipPointsNode.AddControlPointWorld(vtk.vtkVector3d(terminus["position"]))
        clipPointsNode.SetNthControlPointLabel(index, terminus["label"])
    clipPointsNode.EndModify(wasModify)

    # Previously saved manual normal/origin overrides and extension length scale factors were
    # keyed by the old (now removed) control point IDs; drop them so each new point starts
    # from its own automatic plane and the common extension length.
    self._manualPlaneNormals = {}
    self._manualPlaneOrigins = {}
    self._extensionLengthScaleFactors = {}
    self.saveManualPlaneNormals()

    self.updateGUIFromParameterNode()
    self.ui.clipStatusLabel.text = _("Detected {point_count} clip point(s) from the centerline (inlet + {outlet_count} outlet(s)).").format(
        point_count=len(terminuses), outlet_count=len(terminuses) - 1)
    self.ui.clipStatusLabel.styleSheet = "QLabel { color: #008000; }"

  def scheduleAutoApply(self):
    if (not self._applying and not self.updatingGUIFromParameterNode
        and self.ui.applyButton.checked
        and self.ui.applyButton.enabled
        and self.hasClipPoints()):
        self.autoApplyTimer.start()

  def hasClipPoints(self):
    """There is nothing to clip without clip points, and clipping raises rather than
    producing an uncut surface. Deleting the last point should leave the previous output
    alone, not pop an error dialog; an explicit Apply click still reports the problem."""
    clipPointsNode = self._parameterNode.GetNodeReference("ClipPoints") if self._parameterNode else None
    return bool(clipPointsNode) and clipPointsNode.GetNumberOfControlPoints() > 0

  def onAutoApplyTimeout(self):
    if not self._applying and not self.updatingGUIFromParameterNode:
        self.onApplyButton()

  def getPreprocessedPolyData(self):
    inputSurfaceNode = self._parameterNode.GetNodeReference("InputSurface")
    if not inputSurfaceNode:
        raise ValueError(_("Valid input surface is required"))
    segmentId = self._parameterNode.GetParameter("InputSegmentID")

    # Cheap staleness check BEFORE materializing the input surface. For a segmentation node,
    # self.logic.polyDataFromNode() below calls CreateClosedSurfaceRepresentation() plus a full
    # mesh copy, which is expensive and was previously being re-run on every single apply/drag
    # release regardless of whether the segmentation had actually changed. Use the source node's
    # own MTime (or the model's polydata MTime) as a cheap proxy instead, and only pay for the
    # real extraction when something has actually changed.
    if inputSurfaceNode.IsA("vtkMRMLSegmentationNode"):
        sourceMTime = inputSurfaceNode.GetMTime()
    else:
        existingPolyData = inputSurfaceNode.GetPolyData() if inputSurfaceNode.IsA("vtkMRMLModelNode") else None
        sourceMTime = existingPolyData.GetMTime() if existingPolyData else inputSurfaceNode.GetMTime()

    preprocessEnabled = (self._parameterNode.GetParameter("PreprocessInputSurface") == "true")
    targetNumberOfPoints = float(self._parameterNode.GetParameter("TargetNumberOfPoints"))
    decimationAggressiveness = float(self._parameterNode.GetParameter("DecimationAggressiveness"))
    subdivideInputSurface = (self._parameterNode.GetParameter("SubdivideInputSurface") == "true")
    labelModelFaces = (self._parameterNode.GetParameter("LabelModelFaces") == "true")
    modelFaceIdArrayName = (self._parameterNode.GetParameter("ModelFaceIdArrayName")
                            or _DEFAULT_MODEL_FACE_ID_ARRAY_NAME)
    cacheKey = (self._parameterNode.GetNodeReferenceID("InputSurface"), sourceMTime, segmentId,
                preprocessEnabled, targetNumberOfPoints, decimationAggressiveness, subdivideInputSurface,
                labelModelFaces, modelFaceIdArrayName)
    if cacheKey == self._preprocessedCacheKey and self._preprocessedPolyData is not None:
        return self._preprocessedPolyData

    inputSurfacePolyData = self.logic.polyDataFromNode(inputSurfaceNode, segmentId)
    if not inputSurfacePolyData or inputSurfacePolyData.GetNumberOfPoints() == 0:
        raise ValueError(_("Valid input surface is required"))

    if not preprocessEnabled:
        resultPolyData = inputSurfacePolyData
    else:
        resultPolyData = self.logic.preprocess(inputSurfacePolyData, targetNumberOfPoints, decimationAggressiveness, subdivideInputSurface)
        print(f"Target points: {targetNumberOfPoints}... Number of points in preprocessed surface:  {resultPolyData.GetNumberOfPoints()}")
        if labelModelFaces:
            # Re-derive the labels by position rather than trusting what preprocessing left of
            # the cell array (see transferFaceLabels).
            self.logic.transferFaceLabels(inputSurfacePolyData, resultPolyData, modelFaceIdArrayName)

    self._preprocessedCacheKey = cacheKey
    self._preprocessedPolyData = vtk.vtkPolyData()
    self._preprocessedPolyData.DeepCopy(resultPolyData)
    return self._preprocessedPolyData

  def onApplyButtonClicked(self, clicked=False):
    """Apply, warning first if preprocessing will rebuild a labeled input. Only the explicit
    click comes through here, so a modal dialog cannot interrupt an interactive plane drag."""
    if self.confirmPreprocessingDiscardsFaceLabels():
        self.onApplyButton()

  def confirmPreprocessingDiscardsFaceLabels(self):
    """True if the run should go ahead. Only decimation - which happens when the target point
    count is below the input's own - moves the face boundaries, so only that is worth asking
    about."""
    parameterNode = self._parameterNode
    if (parameterNode is None
            or parameterNode.GetParameter("LabelModelFaces") != "true"
            or parameterNode.GetParameter("PreprocessInputSurface") != "true"):
        return True
    inputSurfaceNode = parameterNode.GetNodeReference("InputSurface")
    inputPolyData = (inputSurfaceNode.GetPolyData()
                     if inputSurfaceNode and inputSurfaceNode.IsA("vtkMRMLModelNode") else None)
    faceIdArrayName = (parameterNode.GetParameter("ModelFaceIdArrayName")
                       or _DEFAULT_MODEL_FACE_ID_ARRAY_NAME)
    if inputPolyData is None or inputPolyData.GetCellData().GetArray(faceIdArrayName) is None:
        return True
    targetNumberOfPoints = float(parameterNode.GetParameter("TargetNumberOfPoints"))
    if targetNumberOfPoints >= inputPolyData.GetNumberOfPoints():
        # No decimation, so preprocessing carries the labels through intact.
        return True
    return slicer.util.confirmOkCancelDisplay(
        _("Preprocessing will decimate this surface to {target_point_count} points. Its "
          "'{array_name}' face labels are carried onto the new cells by position, so no face is lost, "
          "but face boundaries can shift by about one cell.\n\n"
          "Cancel to turn off 'Preprocess input surface', or to raise the target above "
          "{input_point_count} points.").format(
              array_name=faceIdArrayName,
              target_point_count=int(targetNumberOfPoints),
              input_point_count=inputPolyData.GetNumberOfPoints()),
        windowTitle=_("Clip Vessel"))

  def onApplyButton(self):
    """
    Run processing when user clicks "Apply" button (also called after every interactive
    plane edit, debounced). Always runs the full pipeline, including capping, flow
    extensions, and the planarity check, so the displayed model is always the real result.
    """
    if self._applying:
        return
    if self.autoApplyTimer.isActive():
        self.autoApplyTimer.stop()
    self._applying = True
    try:
        # tryWithErrorDisplay puts the whole traceback in the dialog's details section,
        # which is the only way to tell from a report where a failure actually came from.
        # It stays silent when Slicer is in testing mode, so an automated run is not left
        # waiting on a dialog nobody will dismiss, and it re-raises, so a run that failed
        # is reported as failed rather than passing quietly.
        with slicer.util.tryWithErrorDisplay(_("Failed to compute results."), waitCursor=True):
            # Preprocessing
            slicer.util.showStatusMessage(_("Preprocessing..."))
            slicer.app.processEvents()  # force update
            preprocessedPolyData = self.getPreprocessedPolyData()
            # Save preprocessing result to model node. Skip the (surprisingly non-trivial)
            # SetAndObserveMesh + render update when it's the exact same cached polydata as
            # last time, which is the common case while only a clip plane is being edited.
            preprocessedSurfaceModelNode = self._parameterNode.GetNodeReference("PreprocessedSurface")
            if preprocessedSurfaceModelNode and preprocessedSurfaceModelNode.GetPolyData() is not preprocessedPolyData:
                preprocessedSurfaceModelNode.SetAndObserveMesh(preprocessedPolyData)
                if not preprocessedSurfaceModelNode.GetDisplayNode():
                    preprocessedSurfaceModelNode.CreateDefaultDisplayNodes()
                    preprocessedSurfaceModelNode.GetDisplayNode().SetColor(1.0, 1.0, 0.0)
                    preprocessedSurfaceModelNode.GetDisplayNode().SetOpacity(0.4)
                    preprocessedSurfaceModelNode.GetDisplayNode().SetLineWidth(2)

            clipPointsMarkupsNode = self._parameterNode.GetNodeReference("ClipPoints")
            centerlinesModelNode = self._parameterNode.GetNodeReference("InputCenterlines")
            outputModelNode = self._parameterNode.GetNodeReference("OutputSurfaceModel")
            extensionRatio = float(self._parameterNode.GetParameter("ExtensionRatio"))
            transitionRatio = float(self._parameterNode.GetParameter("ExtensionTransitionRatio"))
            self.saveManualPlaneNormals()

            # Read processing options from the parameter node. The GUI may still be
            # synchronizing after a saved scene is restored.
            cap = self._parameterNode.GetParameter("CapOutputSurface") == "true"
            capMethod = self._parameterNode.GetParameter("CapMethod") or _DEFAULT_CAP_METHOD
            capConstraintFactor = float(self._parameterNode.GetParameter("CapConstraintFactor"))
            capNumberOfRings = int(float(self._parameterNode.GetParameter("CapNumberOfRings")))
            remeshCaps = self._parameterNode.GetParameter("RemeshCaps") == "true"
            capTargetEdgeLength = float(self._parameterNode.GetParameter("CapTargetEdgeLength"))
            labelModelFaces = self._parameterNode.GetParameter("LabelModelFaces") == "true"
            modelFaceIdArrayName = (self._parameterNode.GetParameter("ModelFaceIdArrayName")
                                    or _DEFAULT_MODEL_FACE_ID_ARRAY_NAME)
            addFlowExtensions = self._parameterNode.GetParameter("ExtendOutputSurface") == "true"
            extensionMode = _normalizedModeId(self._parameterNode.GetParameter("ExtensionMode"))
            interpolationMode = _normalizedModeId(self._parameterNode.GetParameter("InterpolationMode"))
            preserveCrossSectionShape = self._parameterNode.GetParameter("PreserveCrossSectionShape") == "true"
            clippingMethod = self._parameterNode.GetParameter("ClippingMethod") or "PLANE_PATCH"
            sphereRadiusFactor = float(self._parameterNode.GetParameter("LocalSphereRadiusFactor"))

            slicer.util.showStatusMessage(_("Clipping model..."))
            slicer.app.processEvents()  # force update

            outputPolyData = self.logic.clipVessel(preprocessedPolyData, centerlinesModelNode, clipPointsMarkupsNode,
                                                   cap, addFlowExtensions, extensionRatio, extensionMode,
                                                   self._manualPlaneNormals, self._manualPlaneOrigins,
                                                   self._activeClipPointIndex, clippingMethod, sphereRadiusFactor,
                                                   transitionRatio, interpolationMode, preserveCrossSectionShape,
                                                   self._extensionLengthScaleFactors,
                                                   labelModelFaces, modelFaceIdArrayName,
                                                   capMethod, capConstraintFactor, capNumberOfRings,
                                                   remeshCaps, capTargetEdgeLength)

            outputModelNode.SetAndObserveMesh(outputPolyData)
            if not outputModelNode.GetDisplayNode():
                outputModelNode.CreateDefaultDisplayNodes()
                outputModelNode.GetDisplayNode().SetColor(0.75, 0.75, 0.75)
                outputModelNode.GetDisplayNode().SetLineWidth(3)
            # Table first: it names each face in the legend, and the names are only known now.
            self.updateFaceColorTable()
            self.updateOutputFaceColoring()
            self.updateOutputVisibilityButton()
            self.updateOutputEdgesButton()

            if self.logic.lastUnclippedPoints:
                self.ui.clipStatusLabel.text = _("No cut made at: {point_labels}. These points are positioned exactly at, or beyond, the vessel end — move them slightly inward.").format(
                    point_labels=", ".join(self.logic.lastUnclippedPoints))
                self.ui.clipStatusLabel.styleSheet = "QLabel { color: #d08000; }"
            elif self.logic.lastPlanarityFailures:
                failedLabels = [result["label"] for result in self.logic.lastPlanarityFailures]
                self.ui.clipStatusLabel.text = _("Capping skipped; non-planar cuts: {failed_labels}").format(failed_labels=", ".join(failedLabels))
                self.ui.clipStatusLabel.styleSheet = "QLabel { color: #d08000; }"
            else:
                self.ui.clipStatusLabel.text = _("All cuts are planar.")
                self.ui.clipStatusLabel.styleSheet = "QLabel { color: #008000; }"

            # Which face id landed on which cap is the one thing about the labeling that cannot be
            # read off the 3D view, and it is what a boundary condition setup is written against.
            if labelModelFaces:
                parts = ["%d\u2192%d" % item for item in sorted(self.logic.lastExistingFaceIdMap.items())]
                parts = [_("existing faces {faces}").format(faces=", ".join(parts))] if parts else []
                if self.logic.lastWallFaceId is not None:
                    parts.append(_("wall={wall_face_id}").format(wall_face_id=self.logic.lastWallFaceId))
                parts += ["%d=%s" % assignment for assignment in self.logic.lastFaceIdAssignments]
                self.ui.clipStatusLabel.text += " %s: %s." % (modelFaceIdArrayName, ", ".join(parts))

    finally:
        self._applying = False
    slicer.util.showStatusMessage(_("Clipping vessel complete."), 3000)

#
# ClipVesselLogic
#

class ClipVesselLogic(ScriptedLoadableModuleLogic, VTKObservationMixin):
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
    VTKObservationMixin.__init__(self)  # needed to observe the scene closing
    self.radiusArrayName = 'Radius'

    # whether to use an adaptive extension length, expressed as a multiple of the boundary's mean radius
    self.AdaptiveExtensionLength = True
    # length of the extension, expressed as a multiple of the boundary's mean radius, used when AdaptiveExtensionLength is on
    self.ExtensionRatio = 2.0
    # length of the extension in mm, used when AdaptiveExtensionLength is off
    self.ExtensionLength = 5.0

    # whether to use an adaptive number of boundary points
    self.AdaptiveNumberOfBoundaryPoints = True
    # used when AdaptiveNumberOfBoundaryPoints is off
    self.TargetNumberOfBoundaryPoints = 50
    
    # whether to use an adaptive extension radius, expressed as a multiple of the boundary's mean radius
    self.AdaptiveExtensionRadius = True
    # used when AdaptiveExtensionRadius is off
    self.ExtensionRadius = 1

    # Length of the transition from the original cross-section to the target one,
    # as a fraction of the extension length. Used when the caller does not specify one.
    self.TransitionRatio = 0.25
    # How the original cross-section is blended into the target one. Used when the caller
    # does not specify one.
    self.InterpolationMode = "RAMP"
    # whether the extension keeps the cross-sectional shape of the boundary it grows from,
    # instead of morphing it into a circle
    self.PreserveCrossSectionShape = False
    self.CenterlineNormalEstimationDistanceRatio = 1.0

    # Lowest face id the module hands out when face labeling is enabled. Any labels the input
    # surface already carried are compacted onto firstFaceId, firstFaceId+1, ...; the vessel
    # wall takes the id after those, and the caps follow it in clip point order.
    self.firstFaceId = 1
    self.planarityToleranceMm = 0.01

    self.resetRunState()
    # Everything resetRunState() clears describes the scene it was computed from, so none of it
    # may outlive that scene: a legend built afterwards would otherwise still carry the face
    # names of a surface that is gone, and the caches would answer for nodes that no longer
    # exist.
    self.addObserver(slicer.mrmlScene, slicer.vtkMRMLScene.EndCloseEvent, self.onSceneEndClose)

  def resetRunState(self):
    """Forget the last run: what it produced, and what it cached in order to produce it."""
    # Filled in by labelModelFaces(). lastWallFaceId is None both before any run and when the
    # input labeled every cell, leaving no wall to label.
    self.lastWallFaceId = None
    self.lastExistingFaceIdMap = {}
    # Filled in by clipVessel() rather than by labelModelFaces(), so a caller that labels a
    # surface directly leaves whatever the last clip put here -- which is how the cap names of
    # one run used to turn up in the legend of the next.
    self.lastFaceIdAssignments = []
    self.lastPlanarityResults = []
    self.lastPlanarityFailures = []
    self.lastUnclippedPoints = []
    self._incrementalClipCacheKey = None
    self._incrementalClipBaseSurface = None
    self._centerlineGeometryCacheKey = None
    self._centerlineGeometryCache = None
    self._centerlineLocatorCacheKey = None
    self._centerlineLocator = None
    # The poly data the run labeled, and its modification time as of then. What the run recorded
    # describes that poly data and nothing else, so this is what makes it possible to tell
    # whether it still applies to the surface being asked about.
    self._runStateSurface = None
    self._runStateSurfaceMTime = None

  def onSceneEndClose(self, caller=None, event=None):
    """The scene the last run described is gone, so nothing it left behind still applies."""
    self.resetRunState()

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
    if not parameterNode.GetParameter("CapOutputSurface"):
        parameterNode.SetParameter("CapOutputSurface", "true")
    if parameterNode.GetParameter("CapMethod") not in _CAP_METHOD_IDS:
        parameterNode.SetParameter("CapMethod", _DEFAULT_CAP_METHOD)
    if not parameterNode.GetParameter("CapConstraintFactor"):
        parameterNode.SetParameter("CapConstraintFactor", str(_DEFAULT_CAP_CONSTRAINT_FACTOR))
    if not parameterNode.GetParameter("CapNumberOfRings"):
        parameterNode.SetParameter("CapNumberOfRings", str(_DEFAULT_CAP_NUMBER_OF_RINGS))
    if not parameterNode.GetParameter("RemeshCaps"):
        parameterNode.SetParameter("RemeshCaps", "false")
    if not parameterNode.GetParameter("CapTargetEdgeLength"):
        parameterNode.SetParameter("CapTargetEdgeLength", str(_DEFAULT_CAP_TARGET_EDGE_LENGTH))
    if not parameterNode.GetParameter("LabelModelFaces"):
        parameterNode.SetParameter("LabelModelFaces", "false")
    if not parameterNode.GetParameter("ModelFaceIdArrayName"):
        parameterNode.SetParameter("ModelFaceIdArrayName", _DEFAULT_MODEL_FACE_ID_ARRAY_NAME)
    if not parameterNode.GetParameter("ExtensionRatio"):
        parameterNode.SetParameter("ExtensionRatio", "2")
    if not parameterNode.GetParameter("ExtensionTransitionRatio"):
        parameterNode.SetParameter("ExtensionTransitionRatio", "0.25")
    # Earlier module versions offered the extension direction and the interpolation method in
    # a single list, storing both in the ExtensionMode parameter. When an interpolation method
    # was chosen there, the extension direction was left at the filter default (centerline
    # direction), so scenes saved that way are migrated accordingly.
    extensionMode = _normalizedModeId(parameterNode.GetParameter("ExtensionMode"))
    interpolationMode = _normalizedModeId(parameterNode.GetParameter("InterpolationMode"))
    if extensionMode in _INTERPOLATION_MODE_IDS:
        interpolationMode = extensionMode
        extensionMode = "CENTERLINE_DIRECTION"
    extensionMode = extensionMode if extensionMode in _EXTENSION_MODE_IDS else "BOUNDARY_NORMAL"
    interpolationMode = interpolationMode if interpolationMode in _INTERPOLATION_MODE_IDS else "RAMP"
    if extensionMode != parameterNode.GetParameter("ExtensionMode"):
        parameterNode.SetParameter("ExtensionMode", extensionMode)
    if interpolationMode != parameterNode.GetParameter("InterpolationMode"):
        parameterNode.SetParameter("InterpolationMode", interpolationMode)
    if not parameterNode.GetParameter("PreserveCrossSectionShape"):
        parameterNode.SetParameter("PreserveCrossSectionShape", "false")
    if not parameterNode.GetParameter("ManualClipPlaneNormals"):
        parameterNode.SetParameter("ManualClipPlaneNormals", "{}")
    if not parameterNode.GetParameter("ManualClipPlaneOrigins"):
        parameterNode.SetParameter("ManualClipPlaneOrigins", "{}")
    if not parameterNode.GetParameter("ExtensionLengthScaleFactors"):
        parameterNode.SetParameter("ExtensionLengthScaleFactors", "{}")
    if not parameterNode.GetParameter("AutoApplyPlane"):
        parameterNode.SetParameter("AutoApplyPlane", "false")
    if not parameterNode.GetParameter("ClipPointInsetFactor"):
        parameterNode.SetParameter("ClipPointInsetFactor", "0.5")
    if not parameterNode.GetParameter("SnapClipPointsToCenterline"):
        parameterNode.SetParameter("SnapClipPointsToCenterline", "true")
    if not parameterNode.GetParameter("ClippingMethod"):
        parameterNode.SetParameter("ClippingMethod", "PLANE_PATCH")
    if not parameterNode.GetParameter("LocalSphereRadiusFactor"):
        parameterNode.SetParameter("LocalSphereRadiusFactor", "2.5")
    if not parameterNode.GetParameter("FreeNormalHandle"):
        parameterNode.SetParameter("FreeNormalHandle", "false")

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
            
  @staticmethod
  def triangulateSurface(surface):
    """The surface with every cell split into triangles. Cell data is carried over to each
    triangle a cell is split into, so cell arrays survive."""
    triangleFilter = vtk.vtkTriangleFilter()
    triangleFilter.SetInputData(surface)
    triangleFilter.PassLinesOff()
    triangleFilter.PassVertsOff()
    triangleFilter.Update()
    return triangleFilter.GetOutput()

  @staticmethod
  def orientSurfaceOutwards(surface):
    """The surface with every cell wound so that its normal points out of the enclosed volume,
    and with any normals array dropped. Two things about the capped surface would otherwise be
    shaded wrongly, and the cappers differ in which of them they get right:
      - the simple and smooth cappers wind their cap cells the opposite way round from the
        vessel wall (the center point capper does not), so the caps come out lit from inside;
      - the simple capper is the only one that carries the point data of the input over to its
        output, and since it closes a boundary without adding any point, every vertex of its cap
        is a boundary vertex whose normal is the one the vessel wall left there. The cap is then
        shaded as though it were wall - the normals do not even face the same way across it.
    Dropping the normals leaves the renderer to shade the surface by its geometry, which is what
    it already does for the other two cappers. The cells keep their order, so cell arrays still
    line up. Assumes the surface is closed, as it is once capped.
    """
    normalsFilter = vtk.vtkPolyDataNormals()
    normalsFilter.SetInputData(surface)
    # The consistency pass is what re-winds the cells, and the filter only runs it when it has
    # normals to compute; the cell normals are the cheaper of the two and are dropped again.
    normalsFilter.ComputePointNormalsOff()
    normalsFilter.ComputeCellNormalsOn()
    normalsFilter.ConsistencyOn()
    normalsFilter.AutoOrientNormalsOn()
    normalsFilter.SplittingOff()
    normalsFilter.Update()
    surface = normalsFilter.GetOutput()
    for attributes in (surface.GetPointData(), surface.GetCellData()):
        attributes.SetNormals(None)
        attributes.RemoveArray("Normals")
    return surface

  def capSurface(self, surface, cellEntityIdsArrayName=None, cellEntityIdOffset=0,
                 capMethod=_DEFAULT_CAP_METHOD,
                 constraintFactor=_DEFAULT_CAP_CONSTRAINT_FACTOR,
                 numberOfRings=_DEFAULT_CAP_NUMBER_OF_RINGS):
    """Close every open boundary of the surface. capMethod picks the shape of the cap mesh, one
    VMTK capping filter each:
      "CENTERPOINT" - a fan of triangles from the barycenter of the hole (vtkvmtkCapPolyData)
      "SIMPLE"      - a flat fill of the hole that adds no points (vtkvmtkSimpleCapPolyData)
      "SMOOTH"      - a cap of concentric rings of cells (vtkvmtkSmoothCapPolyData);
                      constraintFactor sets how far it bulges out of the plane of the cut,
                      following the shape of the surface at the rim (0 keeps it in the plane),
                      and numberOfRings how finely it is meshed
    Whichever method is used, the output is triangulated, consistently oriented outwards and
    free of the stale normals that would otherwise shade the caps wrongly.

    When cellEntityIdsArrayName is set, the filter also tags each cell in a cell array of that
    name: input cells get cellEntityIdOffset, and the cap closing the i-th boundary gets
    i+1+cellEntityIdOffset. Caution: if the input already carries that array the filter keeps
    its values but still numbers the caps from cellEntityIdOffset up, so new cap ids land on ids
    already in use - clipVessel() passes a private array name for that reason.

    Each cap takes the label of the boundary it closes, which is the index of the clip point
    that opened it (see labelClipBoundaries), so a cap can be traced back to its cut without
    anything having to be numbered or translated. All three cappers read the labels, so that
    holds whichever method is chosen. A hole no cut opened carries no label, and its cap keeps
    the i+1+cellEntityIdOffset the capper derives from the extraction order - which is why the
    offset has to sit above every clip point index.

    Caution: the simple and smooth cappers need a triangulated input to leave the cells of the
    input alone (see _CAP_METHODS_NEEDING_TRIANGLES); callers that match cells of the output up
    with cells of the input must triangulate before calling.
    """
    if capMethod not in _CAP_METHOD_IDS:
        logging.warning("Unknown cap method %s, capping with %s instead.", capMethod, _DEFAULT_CAP_METHOD)
        capMethod = _DEFAULT_CAP_METHOD

    if capMethod == "CENTERPOINT":
        capDisplacement = 0.0
        surfaceCapper = vtkvmtkComputationalGeometry.vtkvmtkCapPolyData()
        surfaceCapper.SetInputData(surface)
        surfaceCapper.SetDisplacement(capDisplacement)
        surfaceCapper.SetInPlaneDisplacement(capDisplacement)
    else:
        import vtkvmtkMiscPython as vtkvmtkMisc
        if capMethod == "SIMPLE":
            surfaceCapper = vtkvmtkMisc.vtkvmtkSimpleCapPolyData()
        else:
            surfaceCapper = vtkvmtkMisc.vtkvmtkSmoothCapPolyData()
            surfaceCapper.SetConstraintFactor(constraintFactor)
            surfaceCapper.SetNumberOfRings(max(2, int(numberOfRings)))
        surfaceCapper.SetInputData(surface)

    # Read the boundaries from the labels rather than extracting them again, which is what makes
    # a boundary id here mean the clip point that opened it. Every capper reads them, so the
    # choice of method does not change which cut a cap is named after. A surface that does not
    # carry them is not one this module produced: the filter says so and falls back to its own
    # numbering, rather than this module quietly identifying boundaries by extraction order.
    surfaceCapper.SetBoundaryLabelsArrayName(self.boundaryLabelsArrayName)
    surfaceCapper.SetBoundaryPointOrderArrayName(self.boundaryPointOrderArrayName)

    if cellEntityIdsArrayName:
        surfaceCapper.SetCellEntityIdsArrayName(cellEntityIdsArrayName)
        surfaceCapper.SetCellEntityIdOffset(cellEntityIdOffset)
    surfaceCapper.Update()
    surface = surfaceCapper.GetOutput()

    if capMethod in _CAP_METHODS_NEEDING_TRIANGLES:
        # The caps are polygons (simple) or quads (smooth); the rest of the pipeline, and
        # anything reading the output as a surface mesh, expects triangles throughout.
        surface = self.triangulateSurface(surface)

    # Two of the three cappers wind their caps inwards; a no-op for the third.
    surface = self.orientSurfaceOutwards(surface)

    return surface

  # Carries the capping filter's per-boundary ids from capSurface() to labelModelFaces(). The
  # name must be one no input surface uses, or the filter inherits its values (see capSurface).
  capBoundaryIdsArrayName = "__ClipVesselCapBoundaryIds"

  # Carry which clip point opened which boundary through the filters that rebuild the mesh, in the
  # surface's own point data (see labelClipBoundaries). Private names, so that a surface the user
  # brought in with arrays of its own cannot be mistaken for a labeled one.
  boundaryLabelsArrayName = "__ClipVesselBoundaryLabels"
  boundaryPointOrderArrayName = "__ClipVesselBoundaryPointOrder"

  def capTargetArea(self, surface, entityIds, capEntityId, targetEdgeLength=0.0):
    """The triangle area a uniform mesh of the cap carrying capEntityId should aim for.

    A given edge length asks for the equilateral triangle of that side. Otherwise the cap is
    sized after the cells the surface has around its own rim - those sharing a point with it -
    so that each cap is meshed as finely as the vessel it closes, rather than every cap in the
    surface being meshed alike.

    None if the cap has no cells, which leaves it to be skipped.
    """
    if targetEdgeLength > 0.0:
        return float(np.sqrt(3.0) / 4.0 * targetEdgeLength ** 2)

    capCellIds = np.nonzero(entityIds == capEntityId)[0]
    if capCellIds.size == 0:
        return None

    surface.BuildLinks()
    pointIds = vtk.vtkIdList()
    cellIds = vtk.vtkIdList()
    rimNeighbourIds = set()
    for capCellId in capCellIds:
        surface.GetCellPoints(int(capCellId), pointIds)
        for pointIndex in range(pointIds.GetNumberOfIds()):
            surface.GetPointCells(pointIds.GetId(pointIndex), cellIds)
            for neighbourIndex in range(cellIds.GetNumberOfIds()):
                neighbourId = int(cellIds.GetId(neighbourIndex))
                if entityIds[neighbourId] != capEntityId:
                    rimNeighbourIds.add(neighbourId)

    # A cap with nothing around it - the whole surface is that one cap - has only itself to go by.
    areaCellIds = rimNeighbourIds if rimNeighbourIds else set(int(value) for value in capCellIds)
    areas = [surface.GetCell(cellId).ComputeArea() for cellId in areaCellIds]
    areas = [area for area in areas if area > 0.0]
    if not areas:
        return None
    return float(np.mean(areas))

  # Passes the remesher makes over a cap. Each one splits, collapses, flips and relocates once;
  # VMTK's own remeshing script defaults to ten, but a cap is a small, nearly flat patch and
  # eight passes already even it out - the further two only cost time.
  capRemeshingIterations = 8

  # Rings of cells kept around a cap when it is remeshed (see remeshCaps). One would do to make
  # the rim an entity boundary; a second costs almost nothing and leaves every cell that touches
  # the rim with a complete ring of neighbours of its own.
  capRemeshingCollarRings = 2

  @staticmethod
  def extractCells(surface, cellMask):
    """The cells of the surface that cellMask selects, as a surface of their own, carrying the
    cell data of the ones they came from."""
    maskArrayName = "__ClipVesselExtractCells"
    maskArray = numpy_to_vtk(np.asarray(cellMask, dtype=np.int8), deep=True,
                             array_type=vtk.VTK_SIGNED_CHAR)
    maskArray.SetName(maskArrayName)
    # Carried on a copy of the surface rather than on the surface itself. The caller may well
    # hand in a filter's output, and adding an array to one of those marks it modified: the
    # filter that made it runs again on the next update and hands back a fresh output without
    # the array, leaving nothing to threshold on and dropping the cell data being extracted.
    masked = vtk.vtkPolyData()
    masked.ShallowCopy(surface)
    masked.GetCellData().AddArray(maskArray)

    threshold = vtk.vtkThreshold()
    threshold.SetInputData(masked)
    threshold.SetInputArrayToProcess(0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_CELLS,
                                     maskArrayName)
    threshold.SetLowerThreshold(0.5)
    threshold.SetUpperThreshold(1.5)
    threshold.Update()
    geometryFilter = vtk.vtkGeometryFilter()
    geometryFilter.SetInputData(threshold.GetOutput())
    geometryFilter.Update()

    extracted = vtk.vtkPolyData()
    extracted.DeepCopy(geometryFilter.GetOutput())
    extracted.GetCellData().RemoveArray(maskArrayName)
    return extracted

  def cellNeighbourhood(self, surface, cellMask, rings):
    """A mask over the cells of the surface covering the ones cellMask selects and the given
    number of rings of cells around them, a ring being everything sharing a point with the last."""
    surface.BuildLinks()
    selected = np.asarray(cellMask, dtype=bool).copy()
    frontier = np.nonzero(selected)[0]
    pointIds, cellIds = vtk.vtkIdList(), vtk.vtkIdList()
    for _ in range(rings):
        nextFrontier = []
        for cellId in frontier:
            surface.GetCellPoints(int(cellId), pointIds)
            for pointIndex in range(pointIds.GetNumberOfIds()):
                surface.GetPointCells(pointIds.GetId(pointIndex), cellIds)
                for neighbourIndex in range(cellIds.GetNumberOfIds()):
                    neighbour = int(cellIds.GetId(neighbourIndex))
                    if not selected[neighbour]:
                        selected[neighbour] = True
                        nextFrontier.append(neighbour)
        if not nextFrontier:
            break
        frontier = nextFrontier
    return selected

  def remeshCaps(self, surface, cellEntityIdsArrayName, capEntityIds,
                 targetEdgeLength=_DEFAULT_CAP_TARGET_EDGE_LENGTH):
    """The surface with the cells of each of capEntityIds retriangulated to a uniform point
    distribution, leaving every other cell of the surface untouched.

    Every capper meshes a boundary by following its rim rather than the area it spans: the center
    point capper makes a fan of slivers meeting at a single interior point, the simple capper
    adds no interior point at all, and the rings of a smooth cap crowd together towards its
    middle. This puts the cap cells - and only those - through VMTK's surface remesher, which
    splits, collapses and flips them until they are near equilateral and of an even size.

    The remesher edits no cell of an excluded entity and moves no point that one of them uses, so
    the vessel wall comes through unchanged and the cap goes on sharing the rim with it, still
    watertight and point for point. That also fixes the spacing of the rim itself: it is the
    interior of the cap that is made uniform, while its rim keeps the spacing the wall gives it.

    Each cap is remeshed on a neighbourhood of itself - the cap plus a collar of the cells around
    it - rather than on the whole surface, and the pieces are put back together at the end. The
    remesher walks every cell and every point of its input on each of its iterations whether it
    may edit them or not, so handing it the whole vessel to retouch a few hundred cap cells costs
    the best part of ten times what handing it the neighbourhood does, for the same result. The
    collar is what makes that safe: it is excluded like the rest of the wall was, so the rim stays
    a boundary between two entities and its points stay frozen, and it comes back untouched, which
    is what lets the remeshed cap be stitched back on to a rim that still matches point for point.
    Remeshing a cap on its own instead would not do - the rim would then be an open boundary, and
    PreserveBoundaryEdges stops the remesher editing boundary edges but not relocating the points
    on them, so the rim would come back moved and the cap would no longer meet the wall.

    :param cellEntityIdsArrayName: cell array naming the face each cell belongs to. Its values
      must not be negative: the remesher reads -1 as "no entity", and would then stop reading the
      rim as a boundary between two faces - which is what stops it pulling the cap off the wall.
    :param capEntityIds: the values in that array that name the caps to remesh.
    :param targetEdgeLength: edge length to aim for, in mm; 0 sizes each cap after the surface
      around its rim (see capTargetArea).
    :return: the remeshed surface. Caution: the mesh is rebuilt around the caps, so the cells come
      back neither the same in number nor in the same order, and only cellEntityIdsArrayName
      survives - the remesher keeps no other cell data, and no point data.
    """
    import vtkvmtkDifferentialGeometryPython as vtkvmtkDifferentialGeometry

    capEntityIds = [int(value) for value in capEntityIds]
    if not capEntityIds:
        return surface

    # The remesher reads its input as triangles and stops on anything else.
    surface = self.triangulateSurface(surface)

    entityIdsArray = surface.GetCellData().GetArray(cellEntityIdsArrayName)
    if entityIdsArray is None or entityIdsArray.GetNumberOfTuples() != surface.GetNumberOfCells():
        logging.warning("Clip Vessel skipped remeshing the caps: the surface carries no usable %s "
                        "cell array to tell them apart by.", cellEntityIdsArrayName)
        return surface
    entityIds = vtk_to_numpy(entityIdsArray).astype(np.int64)

    remeshedCaps = []
    remeshedCapEntityIds = []
    for capEntityId in capEntityIds:
        capCellMask = entityIds == capEntityId
        targetArea = self.capTargetArea(surface, entityIds, capEntityId, targetEdgeLength)
        if targetArea is None or not capCellMask.any():
            continue

        neighbourhood = self.extractCells(
            surface, self.cellNeighbourhood(surface, capCellMask, self.capRemeshingCollarRings))
        neighbourhoodIdsArray = neighbourhood.GetCellData().GetArray(cellEntityIdsArrayName)
        if neighbourhoodIdsArray is None:
            continue
        neighbourhoodIds = vtk_to_numpy(neighbourhoodIdsArray).astype(np.int64)

        # Everything but this cap - the collar included - is left to the remesher as it is, which
        # is what freezes the rim. One pass per cap, because TargetArea is a single value for a
        # run: sizing every cap by one number would mesh a cap on a small branch as coarsely as
        # one on the aorta.
        excludedEntityIds = vtk.vtkIdList()
        for entityId in np.unique(neighbourhoodIds):
            if int(entityId) != capEntityId:
                excludedEntityIds.InsertNextId(int(entityId))

        remesher = vtkvmtkDifferentialGeometry.vtkvmtkPolyDataSurfaceRemeshing()
        remesher.SetInputData(neighbourhood)
        remesher.SetCellEntityIdsArrayName(cellEntityIdsArrayName)
        remesher.SetExcludedEntityIds(excludedEntityIds)
        remesher.SetElementSizeModeToTargetArea()
        remesher.SetTargetArea(targetArea)
        remesher.SetNumberOfIterations(self.capRemeshingIterations)
        # PreserveBoundaryEdges is for open boundaries, and the collar leaves the cap without any.
        # The rim is held by the entity ids instead: the remesher never edits across a boundary
        # between two entities, whether that flag is set or not.
        remesher.Update()
        remeshedNeighbourhood = remesher.GetOutput()

        remeshedNeighbourhoodIdsArray = remeshedNeighbourhood.GetCellData().GetArray(cellEntityIdsArrayName)
        if remeshedNeighbourhoodIdsArray is None:
            continue
        # Only the cap is taken back; the collar came in as part of the wall and is still there.
        remeshedIds = vtk_to_numpy(remeshedNeighbourhoodIdsArray).astype(np.int64)
        remeshedCaps.append(self.extractCells(remeshedNeighbourhood, remeshedIds == capEntityId))
        remeshedCapEntityIds.append(capEntityId)

    if not remeshedCaps:
        return surface

    # The surface with the old caps cut out, and the remeshed ones put in their place. Their rim
    # points were never moved, so they still coincide exactly with the ones left around the holes
    # and merging brings the two back together into one watertight surface.
    pieces = [self.extractCells(surface, ~np.isin(entityIds, remeshedCapEntityIds))] + remeshedCaps
    appendFilter = vtk.vtkAppendPolyData()
    pieceEntityIds = []
    for piece in pieces:
        appendFilter.AddInputData(piece)
        pieceArray = piece.GetCellData().GetArray(cellEntityIdsArrayName)
        pieceEntityIds.append(vtk_to_numpy(pieceArray).astype(np.int64) if pieceArray is not None
                              else np.zeros(piece.GetNumberOfCells(), np.int64))
    appendFilter.Update()
    appended = appendFilter.GetOutput()

    # Put the ids back by hand. The append carries a cell array through only when every input has
    # it under the same name and of the same type, and these do not: the capper writes the ids as
    # a vtkIdTypeArray and the remesher writes them as a vtkIntArray, so the array is dropped
    # without a word. Rebuilding it is exact anyway - the filter appends cells in input order.
    appendedEntityIds = np.concatenate(pieceEntityIds) if pieceEntityIds else np.zeros(0, np.int64)
    if appendedEntityIds.size == appended.GetNumberOfCells():
        appendedArray = numpy_to_vtk(appendedEntityIds.astype(np.int32), deep=True,
                                     array_type=vtk.VTK_INT)
        appendedArray.SetName(cellEntityIdsArrayName)
        appended.GetCellData().RemoveArray(cellEntityIdsArrayName)
        appended.GetCellData().AddArray(appendedArray)
    else:
        logging.warning("Clip Vessel could not carry the %s ids across the remeshed caps: %d ids "
                        "for %d cells.", cellEntityIdsArrayName, appendedEntityIds.size,
                        appended.GetNumberOfCells())

    cleanFilter = vtk.vtkCleanPolyData()
    cleanFilter.SetInputData(appended)
    cleanFilter.PointMergingOn()
    # Only points that are already in the same place, which the rim points of the two pieces are.
    # A tolerance relative to the bounding box would pull the finer cells of a cap together.
    cleanFilter.ToleranceIsAbsoluteOn()
    cleanFilter.SetAbsoluteTolerance(0.0)
    # A cell that came out degenerate stays a degenerate triangle rather than turning into a line
    # or a vert, which would leave cells the face labels do not line up with (see clipVessel).
    cleanFilter.ConvertPolysToLinesOff()
    cleanFilter.ConvertLinesToPointsOff()
    cleanFilter.ConvertStripsToPolysOff()
    cleanFilter.Update()

    # The remesher rebuilds the cap cells, so their winding is its own rather than the one the
    # capper left consistent with the wall.
    return self.orientSurfaceOutwards(cleanFilter.GetOutput())

  def surroundingFaceId(self, surface, capCellIndices, faceIds, isCapCell, fallbackFaceId):
    """The commonest face id among the cells around the hole this cap closed, so that a fill over
    a mesh defect joins the face it sits in instead of becoming a boundary of its own."""
    surface.BuildLinks()
    pointIds = vtk.vtkIdList()
    cellIds = vtk.vtkIdList()
    neighbourFaceIds = []
    for cellIndex in capCellIndices:
        surface.GetCellPoints(int(cellIndex), pointIds)
        for pointIndex in range(pointIds.GetNumberOfIds()):
            surface.GetPointCells(pointIds.GetId(pointIndex), cellIds)
            for neighbourIndex in range(cellIds.GetNumberOfIds()):
                neighbour = int(cellIds.GetId(neighbourIndex))
                if not isCapCell[neighbour]:
                    neighbourFaceIds.append(int(faceIds[neighbour]))
    if not neighbourFaceIds:
        return fallbackFaceId
    values, counts = np.unique(neighbourFaceIds, return_counts=True)
    return int(values[np.argmax(counts)])

  def labelModelFaces(self, surface, planeSpecifications, faceIdArrayName, existingFaceIds=None,
                      wallCellEntityId=0):
    """Tag every cell of the output surface with an integer face id, in the faceIdArrayName cell
    data array, so that a CFD setup can assign a boundary condition per face and a remesher can
    keep the wall/cap boundaries as sharp feature edges.

    Layout: any face the input already carried (a non-positive id counts as unlabeled) is
    renumbered onto firstFaceId, firstFaceId+1, ... in ascending order of its original id; the
    vessel wall - every cell left unlabeled, flow extensions included - takes the next id, unless
    the input labeled every cell and there is no wall; then the caps, in clip point order. With
    nothing pre-existing that is just wall=1, caps=2,3,...

    Caps follow the clip points rather than the capping filter's own boundary order, which
    shifts as clip points move and would renumber the faces of a configured simulation between
    runs. Which cap belongs to which clip point is settled by labelClipBoundaries(), which writes
    the clip point's index onto the points of the boundary it opened; the capper reads those
    labels and puts the clip point's id on the cap closing each. A clip point that made no cut
    leaves its id unused rather than shifting the others.

    :param existingFaceIds: the ids the input carried, one per input cell, in cell order;
      clipVessel reads them before capping, which does not carry cell data through. When None
      they are read off the surface, which is only correct if it has not been capped since.
    :param wallCellEntityId: the value the capping filter left on the cells it copied from its
      input, which is what tells a cap cell from a wall cell. A cap carries the id of the clip point
      whose cut opened the boundary it closes (i+1 for clip point i); a cap closing a boundary no cut
      opened carries an id the capper derived itself, which falls outside that range.
    :return: [(faceId, clipPointLabel)] for the caps. lastWallFaceId and lastExistingFaceIdMap
      describe the rest.
    """
    numberOfCells = surface.GetNumberOfCells()

    # The capping filter writes 0 for cells that came from its input and i+1 for the cap that
    # closed boundary i - the only thing that tells a new cap cell from a pre-existing one.
    capBoundaryArray = surface.GetCellData().GetArray(self.capBoundaryIdsArrayName)
    capBoundaryIds = (vtk_to_numpy(capBoundaryArray).astype(np.int64)
                      if capBoundaryArray is not None
                      and capBoundaryArray.GetNumberOfTuples() == numberOfCells else None)

    if existingFaceIds is None:
        # Direct caller that has not been through clipVessel.
        existingArray = surface.GetCellData().GetArray(faceIdArrayName)
        if existingArray is not None and existingArray.GetNumberOfTuples() == numberOfCells:
            existingFaceIds = vtk_to_numpy(existingArray)
    existingFaceIds = (np.zeros(0, np.int64) if existingFaceIds is None
                       else np.asarray(existingFaceIds, dtype=np.int64))
    # The capper writes wallCellEntityId on the cells it copied from its input and something else
    # on every cap cell, whether that is a clip point id carried on the boundary or an id derived
    # from the boundary's position in the capper's own list.
    isCapCell = (capBoundaryIds != wallCellEntityId) if capBoundaryIds is not None else np.zeros(numberOfCells, bool)
    nonCapCellCount = int(np.count_nonzero(~isCapCell))
    if existingFaceIds.size and existingFaceIds.size != nonCapCellCount:
        # They are matched to output cells by index, so a count mismatch means they would land
        # on the wrong cells. Drop them rather than smear them.
        logging.warning("Clip Vessel ignored the %d face labels the input carried: the output has %d "
                        "non-cap cells, so they cannot be matched up cell for cell.",
                        existingFaceIds.size, nonCapCellCount)
        existingFaceIds = np.zeros(0, np.int64)

    # Faces the input already carried, compacted onto firstFaceId, firstFaceId+1, ...
    # existingFaceIds covers only the input cells; capping appends the cap cells after them.
    compactedIds = np.zeros(numberOfCells, dtype=np.int64)
    existingFaceIdMap = {}
    inputFaceIds = existingFaceIds[:min(existingFaceIds.size, numberOfCells)]
    compactedHead = compactedIds[:inputFaceIds.size]
    for compacted, originalId in enumerate(
            sorted(int(value) for value in np.unique(inputFaceIds) if int(value) > 0),
            start=self.firstFaceId):
        existingFaceIdMap[originalId] = compacted
        compactedHead[inputFaceIds == originalId] = compacted

    # The wall is every cell left unlabeled. An input that labels every cell has no wall, and
    # then no id is set aside for one, or the caps would start past a face that does not exist.
    wallFaceId = self.firstFaceId + len(existingFaceIdMap)
    faceIds = np.where(compactedIds > 0, compactedIds, wallFaceId)
    hasWallCells = bool(np.any((compactedIds == 0) & ~isCapCell))
    firstCapFaceId = wallFaceId + 1 if hasWallCells else wallFaceId

    # Caps, numbered in clip point order.
    capAssignments = []
    if capBoundaryIds is not None:
        boundaryIds = [int(value) for value in np.unique(capBoundaryIds[isCapCell])]

        # Each cap carries the id of the clip point whose cut opened the boundary it closes, put
        # there by clipModel() and brought this far by the capper; a cap value outside the clip
        # point range belongs to a hole no cut accounts for.
        numberOfClipPoints = len(planeSpecifications)
        faceIdByBoundaryId = {}
        for boundaryId in boundaryIds:
            if 0 <= boundaryId < numberOfClipPoints:
                faceIdByBoundaryId[boundaryId] = firstCapFaceId + boundaryId

        labelByPointIndex = {specification["index"]: specification["label"]
                             for specification in planeSpecifications}
        unaccountedCaps = []
        for boundaryId in boundaryIds:
            capCellIndices = np.nonzero(capBoundaryIds == boundaryId)[0]
            faceId = faceIdByBoundaryId.get(boundaryId)
            if faceId is None:
                # No clip point made this hole, so it is a mesh defect rather than a vessel end -
                # a single missing triangle leaves a three point boundary. The fill joins the
                # face it sits in instead of becoming a boundary condition surface of its own.
                faceId = self.surroundingFaceId(surface, capCellIndices, faceIds, isCapCell, wallFaceId)
                unaccountedCaps.append((len(capCellIndices), faceId))
                faceIds[capCellIndices] = faceId
                continue
            faceIds[capCellIndices] = faceId
            capAssignments.append(
                (faceId, labelByPointIndex.get(faceId - firstCapFaceId, _("unmatched boundary"))))
        capAssignments.sort(key=lambda assignment: assignment[0])
        if unaccountedCaps:
            logging.warning("Clip Vessel closed %d hole(s) that no clip point accounts for, most likely "
                            "defects in the input mesh; each was given the face id of the surface around "
                            "it rather than a face of its own (%s). Put a clip point on one of these if "
                            "it should be its own face.",
                            len(unaccountedCaps),
                            ", ".join("%d cells -> face %d" % (cellCount, faceId)
                                      for cellCount, faceId in unaccountedCaps))

    self.lastWallFaceId = wallFaceId if hasWallCells else None
    self.lastExistingFaceIdMap = existingFaceIdMap

    faceIdArray = numpy_to_vtk(faceIds.astype(np.int32), deep=True, array_type=vtk.VTK_INT)
    faceIdArray.SetName(faceIdArrayName)
    surface.GetCellData().RemoveArray(faceIdArrayName)
    surface.GetCellData().AddArray(faceIdArray)
    surface.GetCellData().RemoveArray(self.capBoundaryIdsArrayName)   # internal bookkeeping
    # Active scalars so the model can be colored by face without picking the array by hand.
    surface.GetCellData().SetActiveScalars(faceIdArrayName)
    self.rememberRunStateSurface(surface)
    return capAssignments

  def rememberRunStateSurface(self, surface):
    """Record that what the run state holds describes surface, as it stands now."""
    self._runStateSurface = surface
    self._runStateSurfaceMTime = surface.GetMTime() if surface is not None else None

  def runStateDescribes(self, surface):
    """Whether what the last run recorded still describes surface.

    The face ids a run hands out mean something only for the poly data it labeled: they say
    nothing about another surface that happens to carry the same array, and nothing about this
    one either once something has changed it. Identity alone is not enough, so the modification
    time is checked too."""
    if surface is None or self._runStateSurface is None:
        return False
    return surface is self._runStateSurface and surface.GetMTime() == self._runStateSurfaceMTime

  def lastFaceIdLayout(self, surface):
    """The faces of the last labelModelFaces() call as an ordered [(faceId, name)] - the input's
    own labels, then the wall, then the caps - so the legend can name them.

    Empty unless the run still describes surface, so that a legend is never named after a run
    that produced something else."""
    if not self.runStateDescribes(surface):
        return []
    layout = [(newId, _("Input face {original_id}").format(original_id=originalId))
              for originalId, newId in sorted(self.lastExistingFaceIdMap.items(), key=lambda item: item[1])]
    if self.lastWallFaceId is not None:
        layout.append((self.lastWallFaceId, _("Wall")))
    layout.extend(self.lastFaceIdAssignments)
    return layout

  def transferFaceLabels(self, sourcePolyData, targetPolyData, faceIdArrayName):
    """Give every cell of targetPolyData the face id of the nearest cell of sourcePolyData.

    Preprocessing rebuilds the mesh and what it leaves of an existing cell array cannot be
    relied on: decimation drops it outright, and a degenerate triangle - which vtkCleanPolyData
    turns into a vert and vtkTriangleFilter then drops - leaves it at twice the cell count and
    misaligned, so the labels come through scrambled rather than missing. Taking them off the
    original surface by position is independent of all that.
    """
    sourceArray = sourcePolyData.GetCellData().GetArray(faceIdArrayName) if sourcePolyData else None
    if (sourceArray is None or targetPolyData is None
            or sourceArray.GetNumberOfTuples() != sourcePolyData.GetNumberOfCells()
            or targetPolyData.GetNumberOfCells() == 0):
        return
    sourceFaceIds = vtk_to_numpy(sourceArray)
    sourceCenters = vtk.vtkCellCenters()
    sourceCenters.SetInputData(sourcePolyData)
    sourceCenters.Update()
    targetCenters = vtk.vtkCellCenters()
    targetCenters.SetInputData(targetPolyData)
    targetCenters.Update()
    sourceCentroids = vtk.vtkPolyData()
    sourceCentroids.SetPoints(sourceCenters.GetOutput().GetPoints())
    locator = vtk.vtkStaticPointLocator()
    locator.SetDataSet(sourceCentroids)
    locator.BuildLocator()
    transferred = np.empty(targetPolyData.GetNumberOfCells(), dtype=np.int32)
    for cellIndex, center in enumerate(vtk_to_numpy(targetCenters.GetOutput().GetPoints().GetData())):
        transferred[cellIndex] = sourceFaceIds[locator.FindClosestPoint(center)]
    faceIdArray = numpy_to_vtk(transferred, deep=True, array_type=vtk.VTK_INT)
    faceIdArray.SetName(faceIdArrayName)
    targetPolyData.GetCellData().RemoveArray(faceIdArrayName)
    targetPolyData.GetCellData().AddArray(faceIdArray)

  def preprocess(self, inputSurfacePolyData, targetNumberOfPoints, decimationAggressiveness, subdivideInputSurface):
    import ExtractCenterline
    extractCenterlineLogic = ExtractCenterline.ExtractCenterlineLogic()
    prepocessedPolyData = extractCenterlineLogic.preprocess(inputSurfacePolyData, targetNumberOfPoints, decimationAggressiveness, subdivideInputSurface)
    return prepocessedPolyData
    
  def computeCenterlineGeometry(self, centerlines):
    """Compute centerline tangents once so they can be reused for every cut."""
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
    output = vtk.vtkPolyData()
    output.DeepCopy(centerlineGeometry.GetOutput())
    return output

  def getCachedCenterlineGeometry(self, centerlinesNode):
    """Resampling the centerline and computing Frenet frames is expensive and its result only
    depends on the centerline node, not on where the clip points/planes are. While the user is
    dragging a clip plane, this same result would otherwise be recomputed on every single apply
    and every endpoint click, which is the main reason interactive edits felt slow. Cache it and
    only recompute when the centerline itself actually changes."""
    centerlinesPolyData = centerlinesNode.GetPolyData()
    cacheKey = (centerlinesNode.GetID(), centerlinesPolyData.GetMTime() if centerlinesPolyData else None)
    if cacheKey == self._centerlineGeometryCacheKey and self._centerlineGeometryCache is not None:
        return self._centerlineGeometryCache
    resampledCenterline = self.resampleCenterline(centerlinesPolyData, spacing=0.5)
    centerlineGeometry = self.computeCenterlineGeometry(resampledCenterline)
    self._centerlineGeometryCacheKey = cacheKey
    self._centerlineGeometryCache = centerlineGeometry
    return centerlineGeometry

  def getCachedCenterlineLocator(self, centerlinesNode):
    """Point locator over the cached, resampled centerline geometry. Kept in sync with
    getCachedCenterlineGeometry's own cache key so that snapping a clip point to the
    centerline on every mouse-move tick during a drag doesn't rebuild a spatial index
    each time."""
    centerlines = self.getCachedCenterlineGeometry(centerlinesNode)
    if self._centerlineLocator is not None and self._centerlineLocatorCacheKey == self._centerlineGeometryCacheKey:
        return self._centerlineLocator
    locator = vtk.vtkPointLocator()
    locator.SetDataSet(centerlines)
    locator.BuildLocator()
    self._centerlineLocator = locator
    self._centerlineLocatorCacheKey = self._centerlineGeometryCacheKey
    return locator

  def closestPointOnCenterline(self, centerlinesNode, position):
    """World-space position of the centerline point closest to position, or None if the
    centerline has no points."""
    centerlines = self.getCachedCenterlineGeometry(centerlinesNode)
    if centerlines.GetNumberOfPoints() == 0:
        return None
    locator = self.getCachedCenterlineLocator(centerlinesNode)
    pointId = locator.FindClosestPoint(position)
    if pointId < 0:
        return None
    return centerlines.GetPoint(pointId)

  def centerlineDirectionAtPosition(self, centerlinesNode, position):
    """Centerline tangent (oriented toward the branch end) at the centerline point closest to
    position, or None if the centerline has no points or no tangent information."""
    centerlines = self.getCachedCenterlineGeometry(centerlinesNode)
    tangentArray = centerlines.GetPointData().GetArray("FrenetTangent")
    if centerlines.GetNumberOfPoints() == 0 or tangentArray is None:
        return None
    locator = self.getCachedCenterlineLocator(centerlinesNode)
    pointId = locator.FindClosestPoint(position)
    if pointId < 0:
        return None
    normal = list(tangentArray.GetTuple3(pointId))
    normal = self.orientNormalTowardBranchEnd(centerlines, centerlines.GetPoint(pointId), normal)
    vtk.vtkMath.Normalize(normal)
    return normal

  def labelClipBoundaries(self, surface, planeSpecifications, tolerance=None):
    """Label each open boundary of the clipped surface with the index of the clip point that opened it.

    A boundary is attributed to a clip point only when *every* one of its points lies in that clip
    point's plane, so a hole the input already had, or another cut's boundary, cannot be claimed by
    the wrong plane. This is the same measurement validateClipPlanes() makes, against the same
    tolerance: a cut that is not planar to within planarityToleranceMm is reported there and turns
    capping off, so a boundary too far out of plane to be recognised here is one that would not
    have been capped anyway.

    The answer is written into the surface's own point data rather than returned as a position in
    a list, which is what lets it survive the filters that follow. Growing a flow extension
    replaces a boundary with a new one at the tip of the extension, made of points that did not
    exist before, and cleaning or smoothing renumbers and moves points; a boundary id that is a
    position in some filter's extraction order means something different after each of those, and
    used to have to be translated across every one of them. A label carried by the points does
    not: vtkvmtkPolyDataFlowExtensionsFilter moves it to the tip of the extension it grows, and
    vtkvmtkCapPolyData reads it to decide which cap is which.

    A boundary no clip point opened gets a label above the last clip point index, so it can never
    be mistaken for one that was cut.

    :return: (labeled surface, set of clip point indices that were matched to no boundary). A clip
      point is unmatched when it never cut, or when a later cut removed the boundary it opened.
    """
    if tolerance is None:
        tolerance = self.planarityToleranceMm

    planeOrigins = vtk.vtkPoints()
    planeNormals = vtk.vtkDoubleArray()
    planeNormals.SetNumberOfComponents(3)
    planeLabels = vtk.vtkIdList()
    for specification in planeSpecifications:
        planeOrigins.InsertNextPoint(specification["origin"])
        planeNormals.InsertNextTuple3(*specification["normal"])
        # The label of a boundary is the index of the clip point that opened it, so that every
        # per-boundary list below is indexed by clip point without a translation step.
        planeLabels.InsertNextId(specification["index"])

    labeler = vtkvmtkComputationalGeometry.vtkvmtkPolyDataBoundaryLabeler()
    labeler.SetInputData(surface)
    labeler.SetBoundaryLabelsArrayName(self.boundaryLabelsArrayName)
    labeler.SetBoundaryPointOrderArrayName(self.boundaryPointOrderArrayName)
    labeler.SetLabelingModeToOnPlane()
    labeler.SetMaximumDistanceFromPlane(tolerance)
    # MaximumDistanceFromPlaneOrigin is left unset: a single distance would have to be loose
    # enough for the widest vessel end, which makes it no constraint at all on the narrow ones.
    labeler.SetPlaneOrigins(planeOrigins)
    labeler.SetPlaneNormals(planeNormals)
    labeler.SetPlaneLabels(planeLabels)
    labeler.Update()

    unmatched = labeler.GetUnmatchedPlaneLabels()
    unmatchedClipPointIndices = set(unmatched.GetId(index) for index in range(unmatched.GetNumberOfIds()))
    return labeler.GetOutput(), unmatchedClipPointIndices

  def clipModel(self, surface, planeOrigin, planeNormal, localRadius=None, clippingMethod="PLANE_PATCH", sphereRadiusFactor=2.5):
    """Remove the end region of the vessel beyond a single plane. planeNormal should point
    away from the vessel interior, toward the branch end (see orientNormalTowardBranchEnd):
    everything on that side of the plane is a candidate for removal. In a large branching
    tree, the same (infinite) plane can also cross other, unrelated branches far from this
    clip point; connectivity is used to isolate just the one specific connected piece nearest
    planeOrigin - the actual local end region - and leave anything else the plane happens to
    also cross untouched.
    Returns (outputPolyData, clipped, reason). clipped is False when the cut had no effect,
    in which case reason is "no_surface": nothing exists on the discard side to remove (e.g.
    the clip point sits exactly at, or beyond, the vessel end). reason is None when clipped
    is True. Whether a cut that DID happen looks right is left to the user to judge (e.g. via
    the output status/visualization) rather than rejected automatically here.
    clippingMethod selects how the cut is confined: "PLANE" clips with the infinite plane and
    relies on connectivity alone. "PLANE_SPHERE" clips with the intersection of the
    plane and a sphere of radius sphereRadiusFactor*localRadius around planeOrigin; this
    confines the cut, but also cuts and re-stitches the mesh along the sphere surface, which
    can leave a visible seam ring on the vessel wall. "PLANE_PATCH" achieves the same
    confinement without a seam: the plain-plane cut is restricted to whole cells within the
    same sphere, so no new points are created at the sphere boundary and the cut stays exactly
    planar. "BOX" clips with an open-ended oriented box whose base face lies
    exactly in the cut plane (lateral half-width sphereRadiusFactor*localRadius), which keeps
    the cut planar while confining it laterally - but the box side faces will cut (and leave
    seams on) anything they happen to pass through."""
    clipFunctionPlane = vtk.vtkPlane()
    clipFunctionPlane.SetOrigin(planeOrigin)
    clipFunctionPlane.SetNormal(planeNormal)

    # "Plane + patch" limits the cut to a neighborhood around the selected vessel end.
    # The mesh is partitioned into whole cells near the clip point (the local patch) and the
    # untouched remainder, and only the patch is clipped with the plain plane. Unlike the
    # "Plane + sphere" implicit intersection below, this never cuts the mesh open along
    # the sphere itself (where vtkSphere's quadratic function also misplaces the linearly
    # interpolated cut points), so no seam ring appears on the vessel wall. The whole-cell
    # partition creates no new points at the sphere boundary, so patch and remainder share
    # their original border vertices and merge back seamlessly, and the cut surface stays
    # exactly planar.
    remainderSurface = None
    clipInputSurface = surface
    if clippingMethod == "PLANE_PATCH" and localRadius and localRadius > 0:
        localSphere = vtk.vtkSphere()
        localSphere.SetCenter(planeOrigin)
        localSphere.SetRadius(max(localRadius * sphereRadiusFactor, 1.0))
        # Local patch: every cell with at least one point inside the sphere.
        patchExtractor = vtk.vtkExtractPolyDataGeometry()
        patchExtractor.SetInputData(surface)
        patchExtractor.SetImplicitFunction(localSphere)
        patchExtractor.ExtractInsideOn()
        patchExtractor.ExtractBoundaryCellsOn()
        patchExtractor.Update()
        # Remainder: the complement, cells with all points outside the sphere.
        remainderExtractor = vtk.vtkExtractPolyDataGeometry()
        remainderExtractor.SetInputData(surface)
        remainderExtractor.SetImplicitFunction(localSphere)
        remainderExtractor.ExtractInsideOff()
        remainderExtractor.ExtractBoundaryCellsOff()
        remainderExtractor.Update()
        if patchExtractor.GetOutput().GetNumberOfCells() == 0:
            # No surface anywhere near the clip point: nothing to cut.
            output = vtk.vtkPolyData()
            output.DeepCopy(surface)
            return output, False, "no_surface"
        clipInputSurface = patchExtractor.GetOutput()
        remainderSurface = remainderExtractor.GetOutput()

    # "Box" confines the cut with a single oriented box whose base face lies
    # exactly in the cut plane and which extends past the vessel end. The only place its
    # boundary should meet the surface is that flat base face, so the cut stays planar and
    # seam-free without cutting the mesh along a sphere - provided the side faces clear the
    # surface (choose the size factor accordingly).
    clipFunction = clipFunctionPlane
    # InsideOut(1) keeps the negative-normal (vessel interior) side of the plane as the main
    # output, and puts the positive-normal (branch end) side - the discard candidate - in the
    # clipped output. For the box, the discard region is the box interior (negative function
    # values), so InsideOut is off to retain the exterior instead.
    clipInsideOut = 1
    if clippingMethod == "PLANE_SPHERE" and localRadius and localRadius > 0:
        # Limit the implicit cut to a neighborhood around the selected vessel end by
        # intersecting the plane with a sphere. This also cuts and re-stitches the mesh
        # along the sphere surface, which can leave a visible seam ring on the vessel wall;
        # "Plane + patch" (above) is the seam-free alternative.
        localSphere = vtk.vtkSphere()
        localSphere.SetCenter(planeOrigin)
        localSphere.SetRadius(max(localRadius * sphereRadiusFactor, 1.0))
        sphereImplicitFunction = vtk.vtkImplicitBoolean()
        sphereImplicitFunction.SetOperationTypeToIntersection()
        sphereImplicitFunction.AddFunction(clipFunctionPlane)
        sphereImplicitFunction.AddFunction(localSphere)
        clipFunction = sphereImplicitFunction
    if clippingMethod == "BOX" and localRadius and localRadius > 0:
        boxAxisZ = list(planeNormal)
        vtk.vtkMath.Normalize(boxAxisZ)
        boxAxisX = [0.0, 0.0, 0.0]
        boxAxisY = [0.0, 0.0, 0.0]
        vtk.vtkMath.Perpendiculars(boxAxisZ, boxAxisX, boxAxisY, 0.0)
        # Long enough to always reach past the branch end, wherever it is on the surface.
        bounds = surface.GetBounds()
        boxLength = np.linalg.norm([bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4]])
        halfWidth = max(localRadius * sphereRadiusFactor, 1.0)
        localToWorldMatrix = vtk.vtkMatrix4x4()
        for row in range(3):
            localToWorldMatrix.SetElement(row, 0, boxAxisX[row])
            localToWorldMatrix.SetElement(row, 1, boxAxisY[row])
            localToWorldMatrix.SetElement(row, 2, boxAxisZ[row])
            localToWorldMatrix.SetElement(row, 3, planeOrigin[row])
        # vtkImplicitFunction applies its transform to each query point before evaluation,
        # so the box (defined in its local frame) needs the world-to-local transform.
        worldToLocalTransform = vtk.vtkTransform()
        worldToLocalTransform.SetMatrix(localToWorldMatrix)
        worldToLocalTransform.Inverse()
        localBox = vtk.vtkBox()
        localBox.SetBounds(-halfWidth, halfWidth, -halfWidth, halfWidth, 0.0, boxLength)
        localBox.SetTransform(worldToLocalTransform)
        clipFunction = localBox
        clipInsideOut = 0

    clipper = vtk.vtkClipPolyData()
    clipper.SetInputData(clipInputSurface)
    clipper.GenerateClippedOutputOn()
    clipper.SetInsideOut(clipInsideOut)
    clipper.GenerateClipScalarsOff()
    clipper.SetValue(0.0)
    clipper.SetClipFunction(clipFunction)
    clipper.Update()

    retainedSurface = clipper.GetOutput()
    targetSurface = clipper.GetClippedOutput()
    # A clip point placed exactly at (or beyond) the vessel end can leave one side of the cut
    # with points but no complete cells (a degenerate sliver): GetNumberOfPoints() alone
    # won't catch that, but connectivity/region-coloring below requires actual cells to work
    # with. Treat that the same as an empty side: there's nothing meaningful to cut away, so
    # leave the surface unchanged instead of continuing into a filter that would fail.
    if (retainedSurface.GetNumberOfPoints() == 0 or retainedSurface.GetNumberOfCells() == 0
            or targetSurface.GetNumberOfPoints() == 0 or targetSurface.GetNumberOfCells() == 0):
        output = vtk.vtkPolyData()
        output.DeepCopy(surface)
        return output, False, "no_surface"

    # The discarded side can contain more than one disconnected piece (e.g. the same infinite
    # plane also crossing another, unrelated branch elsewhere); isolate the one nearest the
    # clip point itself as the intended local end region, and keep any other piece (debris
    # still attached to the vessel via the retained side) rather than discarding it too.
    connectivity = vtk.vtkPolyDataConnectivityFilter()
    connectivity.SetInputData(targetSurface)
    connectivity.SetExtractionModeToAllRegions()
    connectivity.ColorRegionsOn()
    connectivity.Update()
    coloredSurface = connectivity.GetOutput()
    locator = vtk.vtkPointLocator()
    locator.SetDataSet(coloredSurface)
    locator.BuildLocator()
    closestPointId = locator.FindClosestPoint(planeOrigin)
    regionIdArray = coloredSurface.GetPointData().GetArray("RegionId")
    if regionIdArray is None or closestPointId < 0:
        # Degenerate cut: the piece being cut away had no identifiable connected region
        # (e.g. the clip plane sits exactly at the vessel end with nothing beyond it).
        # Leave the surface unchanged rather than fail with a cryptic AttributeError.
        output = vtk.vtkPolyData()
        output.DeepCopy(surface)
        return output, False, "no_surface"
    targetRegionId = int(regionIdArray.GetValue(closestPointId))
    numberOfTargetRegions = connectivity.GetNumberOfExtractedRegions()

    nonTargetRegions = vtk.vtkPolyDataConnectivityFilter()
    nonTargetRegions.SetInputData(targetSurface)
    nonTargetRegions.SetExtractionModeToSpecifiedRegions()
    for regionId in range(numberOfTargetRegions):
        if regionId != targetRegionId:
            nonTargetRegions.AddSpecifiedRegion(regionId)
    nonTargetRegions.Update()

    # The piece actually being cut away is just the target region (any other, non-target
    # regions on this side are debris left attached via the retained side, and get kept).
    append = vtk.vtkAppendPolyData()
    append.AddInputData(retainedSurface)
    append.AddInputConnection(nonTargetRegions.GetOutputPort())
    if remainderSurface is not None and remainderSurface.GetNumberOfCells() > 0:
        # Cells outside the local sphere were never fed to the clipper; put them back. They
        # share their original border vertices with the patch, so cleaning merges them
        # without leaving a seam.
        append.AddInputData(remainderSurface)
    append.Update()
    clean = vtk.vtkCleanPolyData()
    clean.SetInputConnection(append.GetOutputPort())
    clean.Update()
    output = vtk.vtkPolyData()
    output.DeepCopy(clean.GetOutput())
    return output, True, None

  def automaticClipPlane(self, centerlinesNode, clipPointsMarkupsNode, controlPointIndex):
    """Return the automatic plane origin, normal, and local radius for a clip point."""
    centerlines = self.getCachedCenterlineGeometry(centerlinesNode)
    locator = self.getCachedCenterlineLocator(centerlinesNode)
    position = [0.0, 0.0, 0.0]
    clipPointsMarkupsNode.GetNthControlPointPositionWorld(controlPointIndex, position)
    pointId = locator.FindClosestPoint(position)
    origin = centerlines.GetPoint(pointId)
    normal = list(centerlines.GetPointData().GetArray("FrenetTangent").GetTuple3(pointId))
    normal = self.orientNormalTowardBranchEnd(centerlines, origin, normal)
    radius = centerlines.GetPointData().GetArray(self.radiusArrayName).GetValue(pointId)
    return origin, normal, radius

  def findSharedRootEndpoint(self, centerlines, cellEndpointIds):
    """Given each cell's (startPointId, endPointId), return whichever point id is a shared
    endpoint of every cell (within a small tolerance), or None if there isn't one (e.g. a
    single non-branching centerline, or unexpected topology)."""
    if not cellEndpointIds:
        return None
    toleranceSquared = 0.0025  # 0.05 mm
    for candidatePointId in cellEndpointIds[0]:
        candidatePosition = centerlines.GetPoint(candidatePointId)
        sharedByAll = True
        for otherStart, otherEnd in cellEndpointIds[1:]:
            startPosition = centerlines.GetPoint(otherStart)
            endPosition = centerlines.GetPoint(otherEnd)
            if (vtk.vtkMath.Distance2BetweenPoints(candidatePosition, startPosition) > toleranceSquared and
                    vtk.vtkMath.Distance2BetweenPoints(candidatePosition, endPosition) > toleranceSquared):
                sharedByAll = False
                break
        if sharedByAll:
            return candidatePointId
    return None

  def detectCenterlineTerminusClipPoints(self, centerlinesNode, insetFactor):
    """Find one clip point per centerline terminus: the shared root (inlet) plus every
    distinct branch tip (outlet), each pulled inward along the centerline from the vessel
    surface by insetFactor times the local vessel radius. This avoids landing clip points
    exactly on the vessel surface (where ExtractCenterline places its endpoints).
    Returns a list of {"label", "position", "normal"} dicts, inlet first.
    """
    centerlines = self.getCachedCenterlineGeometry(centerlinesNode)
    numberOfCells = centerlines.GetNumberOfCells()
    if numberOfCells == 0:
        return []

    tangentArray = centerlines.GetPointData().GetArray("FrenetTangent")
    radiusArray = centerlines.GetPointData().GetArray(self.radiusArrayName)
    if tangentArray is None or radiusArray is None:
        raise ValueError(_("Centerline is missing tangent/radius information. Re-run centerline extraction and try again."))

    cellEndpointIds = []
    for cellIndex in range(numberOfCells):
        cell = centerlines.GetCell(cellIndex)
        numberOfPoints = cell.GetNumberOfPoints()
        if numberOfPoints < 2:
            cellEndpointIds.append(None)
            continue
        cellEndpointIds.append((cell.GetPointId(0), cell.GetPointId(numberOfPoints - 1)))
    validCellIndices = [index for index, endpoints in enumerate(cellEndpointIds) if endpoints is not None]
    if not validCellIndices:
        return []

    rootPointId = self.findSharedRootEndpoint(centerlines, [cellEndpointIds[index] for index in validCellIndices])

    def insetFromEndpoint(cell, endpointOffset, step):
        """Walk along cell from its endpointOffset end, toward the interior, until
        insetFactor * local radius of arc length has been covered (or the cell runs out).
        With insetFactor 0, this stays at the endpoint itself."""
        numberOfPoints = cell.GetNumberOfPoints()
        endpointPointId = cell.GetPointId(endpointOffset)
        targetDistance = insetFactor * radiusArray.GetValue(endpointPointId)
        accumulatedDistance = 0.0
        previousPosition = centerlines.GetPoint(endpointPointId)
        reachedPointId = endpointPointId
        index = endpointOffset
        while accumulatedDistance < targetDistance:
            nextIndex = index + step
            if nextIndex < 0 or nextIndex >= numberOfPoints:
                break
            nextPointId = cell.GetPointId(nextIndex)
            nextPosition = centerlines.GetPoint(nextPointId)
            accumulatedDistance += vtk.vtkMath.Distance2BetweenPoints(previousPosition, nextPosition) ** 0.5
            previousPosition = nextPosition
            reachedPointId = nextPointId
            index = nextIndex
        position = centerlines.GetPoint(reachedPointId)
        normal = list(tangentArray.GetTuple3(reachedPointId))
        normal = self.orientNormalTowardBranchEnd(centerlines, position, normal)
        vtk.vtkMath.Normalize(normal)
        return tuple(position), tuple(normal)

    # Locate the root (inlet) using whichever cell actually contains the shared root point.
    rootPosition = None
    rootNormal = None
    if rootPointId is not None:
        for cellIndex in validCellIndices:
            startId, endId = cellEndpointIds[cellIndex]
            cell = centerlines.GetCell(cellIndex)
            if startId == rootPointId:
                rootPosition, rootNormal = insetFromEndpoint(cell, 0, +1)
                break
            if endId == rootPointId:
                rootPosition, rootNormal = insetFromEndpoint(cell, cell.GetNumberOfPoints() - 1, -1)
                break
    if rootPosition is None:
        # No unambiguous shared root found (e.g. a single, non-branching centerline):
        # fall back to the first cell's start point as the inlet.
        firstCellIndex = validCellIndices[0]
        rootPointId = cellEndpointIds[firstCellIndex][0]
        rootPosition, rootNormal = insetFromEndpoint(centerlines.GetCell(firstCellIndex), 0, +1)

    terminuses = [{"label": _("Inlet"), "position": rootPosition, "normal": rootNormal}]

    seenLeafPositions = []
    outletNumber = 0
    for cellIndex in validCellIndices:
        startId, endId = cellEndpointIds[cellIndex]
        cell = centerlines.GetCell(cellIndex)
        numberOfPoints = cell.GetNumberOfPoints()
        if startId == rootPointId:
            leafOffset = numberOfPoints - 1
        elif endId == rootPointId:
            leafOffset = 0
        else:
            # Cell touches neither identified root endpoint (unexpected topology): treat its
            # far end as a leaf too, rather than silently dropping it.
            leafOffset = numberOfPoints - 1
        leafPointId = cell.GetPointId(leafOffset)
        leafPosition = centerlines.GetPoint(leafPointId)
        if any(vtk.vtkMath.Distance2BetweenPoints(leafPosition, seen) < 0.0025 for seen in seenLeafPositions):
            continue
        seenLeafPositions.append(leafPosition)
        outletNumber += 1
        step = -1 if leafOffset == numberOfPoints - 1 else +1
        outletPosition, outletNormal = insetFromEndpoint(cell, leafOffset, step)
        terminuses.append({"label": _("Outlet {number}").format(number=outletNumber), "position": outletPosition, "normal": outletNormal})

    return terminuses

  def orientNormalTowardBranchEnd(self, centerlines, origin, normal):
    """Orient a tangent away from the vessel interior using the nearest polyline endpoint."""
    closestEndpoint = None
    closestInteriorPoint = None
    closestDistance2 = float("inf")
    for cellIndex in range(centerlines.GetNumberOfCells()):
        cell = centerlines.GetCell(cellIndex)
        numberOfPoints = cell.GetNumberOfPoints()
        if numberOfPoints < 2:
            continue
        for endpointOffset, interiorOffset in ((0, min(2, numberOfPoints - 1)),
                                               (numberOfPoints - 1, max(0, numberOfPoints - 3))):
            endpoint = centerlines.GetPoint(cell.GetPointId(endpointOffset))
            distance2 = vtk.vtkMath.Distance2BetweenPoints(origin, endpoint)
            if distance2 < closestDistance2:
                closestDistance2 = distance2
                closestEndpoint = endpoint
                closestInteriorPoint = centerlines.GetPoint(cell.GetPointId(interiorOffset))
    if closestEndpoint is not None:
        outward = [closestEndpoint[axis] - closestInteriorPoint[axis] for axis in range(3)]
        if vtk.vtkMath.Dot(normal, outward) < 0.0:
            normal = [-value for value in normal]
    return normal

  def manualPlaneOriginNormal(self, planeNode):
    """Read the interactive plane in world coordinates."""
    origin = [0.0, 0.0, 0.0]
    normal = [0.0, 0.0, 1.0]
    planeNode.GetOriginWorld(origin)
    planeNode.GetNormalWorld(normal)
    vtk.vtkMath.Normalize(normal)
    return origin, normal

  def validateClipPlanes(self, surface, planeSpecifications):
    """Measure each output boundary loop against its intended clipping plane."""
    self.lastPlanarityResults = []
    self.lastPlanarityFailures = []
    if not planeSpecifications:
        return

    boundaryEdges = vtk.vtkFeatureEdges()
    boundaryEdges.SetInputData(surface)
    boundaryEdges.BoundaryEdgesOn()
    boundaryEdges.FeatureEdgesOff()
    boundaryEdges.ManifoldEdgesOff()
    boundaryEdges.NonManifoldEdgesOff()
    boundaryEdges.Update()

    connectivity = vtk.vtkPolyDataConnectivityFilter()
    connectivity.SetInputConnection(boundaryEdges.GetOutputPort())
    connectivity.SetExtractionModeToAllRegions()
    connectivity.ColorRegionsOn()
    connectivity.Update()
    boundaries = connectivity.GetOutput()
    regionArray = boundaries.GetPointData().GetArray("RegionId")
    if not regionArray or boundaries.GetNumberOfPoints() == 0:
        for specification in planeSpecifications:
            result = {**specification, "maximumErrorMm": float("inf"), "reason": "Missing boundary"}
            self.lastPlanarityResults.append(result)
            self.lastPlanarityFailures.append(result)
        return

    points = vtk_to_numpy(boundaries.GetPoints().GetData())
    regionIds = vtk_to_numpy(regionArray).astype(int)
    regions = []
    for regionId in np.unique(regionIds):
        regionPoints = points[regionIds == regionId]
        regions.append((int(regionId), regionPoints, np.mean(regionPoints, axis=0)))

    availableRegionIndices = set(range(len(regions)))
    for specification in planeSpecifications:
        if not availableRegionIndices:
            result = {**specification, "maximumErrorMm": float("inf"), "reason": "Missing boundary"}
        else:
            origin = np.asarray(specification["origin"])
            normal = np.asarray(specification["normal"])
            regionIndex = min(availableRegionIndices,
                              key=lambda index: np.linalg.norm(regions[index][2] - origin))
            availableRegionIndices.remove(regionIndex)
            regionPoints = regions[regionIndex][1]
            maximumError = float(np.max(np.abs((regionPoints - origin).dot(normal))))
            result = {**specification, "maximumErrorMm": maximumError, "reason": ""}
        self.lastPlanarityResults.append(result)
        if result["maximumErrorMm"] > self.planarityToleranceMm:
            self.lastPlanarityFailures.append(result)
    
    
  def resampleCenterline(self, polydata, spacing=0.5):
    """Resamples centerline with a spline filter to a desired spacing"""
    splineFilter = vtk.vtkSplineFilter()
    splineFilter.SetInputData(polydata)
    splineFilter.SetSubdivideToLength()
    splineFilter.SetLength(spacing)
    splineFilter.Update()
    polydata = splineFilter.GetOutput()
    return polydata
        
  def extendVessel(self, surfacePolyData, centerlinesPolyData, extensionRatio, extensionMode,
                   transitionRatio=None, interpolationMode=None, preserveCrossSectionShape=None,
                   extensionLengthScaleFactors=None):
    """Adds flow extensions to all boundaries.
    :param extensionRatio: length of each extension, as a multiple of the mean radius of the
      boundary that it is attached to. Defaults to self.ExtensionRatio.
    :param extensionMode: direction of the extension ("CENTERLINE_DIRECTION" or "BOUNDARY_NORMAL")
    :param transitionRatio: length of the transition from the original cross-section to the target
      one, as a fraction of the extension length (0..1). Defaults to self.TransitionRatio.
    :param interpolationMode: blending of the original cross-section into the target one
      ("LINEAR", "RAMP" or "THIN_PLATE_SPLINE"). Defaults to self.InterpolationMode.
    :param preserveCrossSectionShape: if enabled then the extension keeps the cross-sectional shape
      of the boundary that it grows from, instead of morphing it into a circle.
      Defaults to self.PreserveCrossSectionShape.
    :param extensionLengthScaleFactors: optional per-boundary multipliers applied to the extension
      length, indexed by boundary id; None leaves all extension lengths unscaled. A boundary's id
      is its label from the boundary labels this module writes (see labelClipBoundaries), which is
      the index of the clip point that opened it.
    :return: the extended surface. Growing an extension replaces the boundary it grew from with a
      new one at the tip, but the filter carries the boundary's label across to it, so a vessel end
      is still the same vessel end afterwards and nothing has to be renumbered.
    """
    if extensionRatio is None:
        extensionRatio = self.ExtensionRatio
    if transitionRatio is None:
        transitionRatio = self.TransitionRatio
    if interpolationMode is None:
        interpolationMode = self.InterpolationMode
    if preserveCrossSectionShape is None:
        preserveCrossSectionShape = self.PreserveCrossSectionShape
    transitionRatio = min(max(float(transitionRatio), 0.0), 1.0)
    
    extensionsFilter = vtkvmtkComputationalGeometry.vtkvmtkPolyDataFlowExtensionsFilter()
    extensionsFilter.SetInputData(surfacePolyData)
    # Read the boundaries from the labels, and carry each one across to the tip of its own
    # extension, so that a vessel end keeps its identity through the rebuild.
    extensionsFilter.SetBoundaryLabelsArrayName(self.boundaryLabelsArrayName)
    extensionsFilter.SetBoundaryPointOrderArrayName(self.boundaryPointOrderArrayName)
    extensionsFilter.SetCenterlines(centerlinesPolyData)
    extensionsFilter.SetAdaptiveExtensionLength(self.AdaptiveExtensionLength)
    extensionsFilter.SetAdaptiveExtensionRadius(self.AdaptiveExtensionRadius)
    extensionsFilter.SetAdaptiveNumberOfBoundaryPoints(self.AdaptiveNumberOfBoundaryPoints)
    extensionsFilter.SetExtensionLength(self.ExtensionLength)
    extensionsFilter.SetExtensionRatio(float(extensionRatio))
    if extensionLengthScaleFactors is not None:
        scaleFactorsArray = vtk.vtkDoubleArray()
        for scaleFactor in extensionLengthScaleFactors:
            scaleFactorsArray.InsertNextValue(float(scaleFactor))
        extensionsFilter.SetExtensionLengthScaleFactors(scaleFactorsArray)
    extensionsFilter.SetExtensionRadius(self.ExtensionRadius)
    extensionsFilter.SetTransitionRatio(transitionRatio)
    extensionsFilter.SetCenterlineNormalEstimationDistanceRatio(self.CenterlineNormalEstimationDistanceRatio)
    extensionsFilter.SetNumberOfBoundaryPoints(self.TargetNumberOfBoundaryPoints)
    extensionsFilter.SetPreserveCrossSectionShape(1 if preserveCrossSectionShape else 0)
    if extensionMode == "CENTERLINE_DIRECTION":
        extensionsFilter.SetExtensionModeToUseCenterlineDirection()
    elif extensionMode == "BOUNDARY_NORMAL":
        extensionsFilter.SetExtensionModeToUseNormalToBoundary()
    if interpolationMode == "LINEAR":
        extensionsFilter.SetInterpolationModeToLinear()
    elif interpolationMode == "THIN_PLATE_SPLINE":
        extensionsFilter.SetInterpolationModeToThinPlateSpline()
    elif interpolationMode == "RAMP":
        extensionsFilter.SetInterpolationModeToRamp()
    extensionsFilter.Update()
    return extensionsFilter.GetOutput()

  def clipVessel(self, surfacePolyData, centerlinesNode, clipPointsMarkupsNode, cap, addFlowExtensions,
                 extensionRatio, extensionMode, manualClipPlaneNormals=None, manualClipPlaneOrigins=None,
                 interactivePointIndex=-1, clippingMethod="PLANE_PATCH", sphereRadiusFactor=2.5,
                 transitionRatio=None, interpolationMode=None, preserveCrossSectionShape=None,
                 extensionScaleFactors=None,
                 labelModelFaces=False, modelFaceIdArrayName=_DEFAULT_MODEL_FACE_ID_ARRAY_NAME,
                 capMethod=_DEFAULT_CAP_METHOD,
                 capConstraintFactor=_DEFAULT_CAP_CONSTRAINT_FACTOR,
                 capNumberOfRings=_DEFAULT_CAP_NUMBER_OF_RINGS,
                 remeshCaps=False,
                 capTargetEdgeLength=_DEFAULT_CAP_TARGET_EDGE_LENGTH):
    """Clips the vessel.
    :param surfacePolyData: input surface
    :param centerlinesPolyData: input centerlines
    :param clipPointsMarkupsNode: markup node containing clip points
    :param cap: flag indicating whether to cap the model:
    :param addFlowExtensions: flag indicating whether to add flow extensions:
    :param extensionRatio: length of each flow extension, as a multiple of the radius of the
      vessel end that it is attached to; None uses the logic default
    :param extensionMode: string specifying the extension mode:
    :param transitionRatio: length of the flow extension transition (original cross-section to
      the target one) as a fraction of the extension length; None uses the logic default
    :param interpolationMode: string specifying how the original cross-section is blended into
      the target one ("LINEAR", "RAMP" or "THIN_PLATE_SPLINE"); None uses the logic default
    :param preserveCrossSectionShape: if enabled then the flow extensions keep the cross-sectional
      shape of the vessel ends instead of morphing it into a circle; None uses the logic default
    :param extensionScaleFactors: optional dict mapping clip point IDs (control point IDs of
      clipPointsMarkupsNode) to a multiplier applied to the length of the flow extension grown
      from that vessel end; ends without an entry keep the unscaled length
    :param labelModelFaces: if enabled then every output cell is tagged with an integer face id
      (wall vs. one id per cap) in the modelFaceIdArrayName cell array; see labelModelFaces()
    :param modelFaceIdArrayName: name of the cell array that holds the face ids
    :param capMethod: shape of the cap mesh, "CENTERPOINT", "SIMPLE" or "SMOOTH"; see capSurface()
    :param capConstraintFactor: how far a "SMOOTH" cap bulges out of the plane of the cut, 0 for
      a cap that stays in it
    :param capNumberOfRings: number of rings of cells a "SMOOTH" cap is made of
    :param remeshCaps: if enabled then the caps are retriangulated to a uniform point
      distribution, leaving the vessel wall untouched; see remeshCaps()
    :param capTargetEdgeLength: edge length a remeshed cap aims for, in mm; 0 sizes each cap
      after the surface around its own rim
    :return: polydata containing clipped vessel
    """

    # Say which input is missing. Without this the first thing to touch one of them raises an
    # AttributeError on None, which names neither the input nor the module that wanted it.
    if not centerlinesNode:
        raise ValueError(_("Valid input centerlines are required"))
    if centerlinesNode.GetPolyData() is None:
        raise ValueError(_("The input centerlines node holds no mesh"))
    if not clipPointsMarkupsNode:
        raise ValueError(_("Valid clip points are required"))

    centerlinesPolyData = self.getCachedCenterlineGeometry(centerlinesNode)

    numberOfControlPoints = clipPointsMarkupsNode.GetNumberOfControlPoints()
    if numberOfControlPoints == 0:
        raise ValueError(_("Failed to clip vessel (no output was generated)"))

    # identify closest point on centerline to clipPointsMarkups
    pointLocator = vtk.vtkPointLocator()
    pointLocator.SetDataSet(centerlinesPolyData)
    pointLocator.BuildLocator()
    
    clipPoints = []
    pos = [0.0, 0.0, 0.0]
    
    for controlPointIndex in range(numberOfControlPoints):
        clipPointsMarkupsNode.GetNthControlPointPositionWorld(controlPointIndex, pos)
        pointId = pointLocator.FindClosestPoint(pos)
        controlPointId = clipPointsMarkupsNode.GetNthControlPointID(controlPointIndex)
        if manualClipPlaneOrigins and controlPointId in manualClipPlaneOrigins:
            clipPoints.append(tuple(manualClipPlaneOrigins[controlPointId]))
        else:
            clipPoints.append(centerlinesPolyData.GetPoint(pointId))

    planeSpecifications = []
    self.lastUnclippedPoints = []
    radiusArray = centerlinesPolyData.GetPointData().GetArray(self.radiusArrayName)

    for controlPointIndex in range(numberOfControlPoints):
        pointId = pointLocator.FindClosestPoint(clipPoints[controlPointIndex])
        planeOrigin = clipPoints[controlPointIndex]
        planeNormal = list(centerlinesPolyData.GetPointData().GetArray("FrenetTangent").GetTuple3(pointId))
        controlPointId = clipPointsMarkupsNode.GetNthControlPointID(controlPointIndex)
        if manualClipPlaneNormals and controlPointId in manualClipPlaneNormals:
            planeNormal = list(manualClipPlaneNormals[controlPointId])
        else:
            planeNormal = self.orientNormalTowardBranchEnd(centerlinesPolyData, planeOrigin, planeNormal)
        vtk.vtkMath.Normalize(planeNormal)
        planeSpecifications.append({
            "index": controlPointIndex,
            "label": clipPointsMarkupsNode.GetNthControlPointLabel(controlPointIndex),
            "origin": tuple(planeOrigin),
            "normal": tuple(planeNormal),
            "radius": radiusArray.GetValue(pointId) if radiusArray else None,
        })

    def applyPlane(currentSurface, specification):
        clippedSurface, clipped, reason = self.clipModel(currentSurface, specification["origin"], specification["normal"],
                                                         specification.get("radius"), clippingMethod, sphereRadiusFactor)
        if clippedSurface.GetNumberOfPoints() == 0:
            logging.error("Plane removed the entire surface; skipping clip point %d.", specification["index"])
            return currentSurface
        if not clipped:
            self.lastUnclippedPoints.append(specification["label"])
            logging.warning("Clip point '%s' had no effect: it may be positioned exactly at, or beyond, the vessel end.",
                            specification["label"])
        return clippedSurface

    if 0 <= interactivePointIndex < numberOfControlPoints:
        # Cache the topology-safe prefix. Cuts after the edited endpoint must be replayed:
        # moving a plane can change the connected regions seen by downstream cuts.
        prefixPlaneKey = tuple(
            (specification["index"], specification["origin"], specification["normal"])
            for specification in planeSpecifications[:interactivePointIndex])
        incrementalCacheKey = (
            surfacePolyData.GetMTime(), centerlinesNode.GetPolyData().GetMTime(),
            clipPointsMarkupsNode.GetID(), interactivePointIndex, clippingMethod, prefixPlaneKey)
        if incrementalCacheKey != self._incrementalClipCacheKey or self._incrementalClipBaseSurface is None:
            fixedSurface = surfacePolyData
            for specification in planeSpecifications[:interactivePointIndex]:
                fixedSurface = applyPlane(fixedSurface, specification)
            self._incrementalClipBaseSurface = vtk.vtkPolyData()
            self._incrementalClipBaseSurface.DeepCopy(fixedSurface)
            self._incrementalClipCacheKey = incrementalCacheKey
        surface = self._incrementalClipBaseSurface
        for specification in planeSpecifications[interactivePointIndex:]:
            surface = applyPlane(surface, specification)
    else:
        surface = surfacePolyData
        for specification in planeSpecifications:
            surface = applyPlane(surface, specification)

    # Plane clipping does not require per-cut branch splitting, merging, or cleaning.
    # Clean once and retain the largest connected vessel component at the end.
    clean = vtk.vtkCleanPolyData()
    clean.SetInputData(surface)
    clean.Update()
    connectFilter = vtk.vtkPolyDataConnectivityFilter()
    connectFilter.SetInputConnection(clean.GetOutputPort())
    connectFilter.SetExtractionModeToLargestRegion()
    connectFilter.Update()
    surface = connectFilter.GetOutput()

    self.validateClipPlanes(surface, planeSpecifications)
    if self.lastPlanarityFailures:
        logging.warning("Clip Vessel found non-planar boundaries; flow extension and capping were skipped: %s",
                        ", ".join(result["label"] for result in self.lastPlanarityFailures))
        addFlowExtensions = False
        cap = False

    # Which cut opened which boundary, settled once here, while the boundaries still lie exactly
    # where the cuts left them, and written into the surface's own point data. From here on a
    # vessel end is referred to by its label, which is the index of the clip point that opened it,
    # and which the filters that rebuild the mesh carry with the points rather than renumber.
    surface, unmatchedClipPointIndices = self.labelClipBoundaries(surface, planeSpecifications)
    unidentifiedLabels = [specification["label"] for specification in planeSpecifications
                          if specification["index"] in unmatchedClipPointIndices]
    if unidentifiedLabels:
        # Without a boundary to point at, that vessel end gets neither its own face id nor its own
        # extension length; say so rather than let it quietly fall back to the capper's numbering.
        logging.warning("Clip Vessel could not tell which boundary belongs to %d clip point(s) (%s); "
                        "their caps take an id of the capping filter's own choosing and their flow "
                        "extensions are left unscaled.",
                        len(unidentifiedLabels), ", ".join(unidentifiedLabels))

    if addFlowExtensions:
        slicer.util.showStatusMessage(_("Adding extensions..."))
        slicer.app.processEvents()
        if labelModelFaces and surface.GetCellData().GetArray(modelFaceIdArrayName or "") is not None:
            # The extensions filter builds its cells from scratch and carries no cell data.
            logging.warning("Clip Vessel discarded the face labels the input surface carried: adding "
                            "flow extensions rebuilds the mesh and does not preserve cell data.")
        boundaryScaleFactors = None
        if extensionScaleFactors and any(abs(scaleFactor - 1.0) > 1e-6 for scaleFactor in extensionScaleFactors.values()):
            # One factor per boundary id, and a boundary id is a clip point index, so entry i
            # belongs to clip point i. A boundary no cut opened - a hole the input already had -
            # carries a label above the last clip point index, falls off the end of the list, and
            # is left unscaled rather than inheriting the factor of whichever clip point happens
            # to be nearest.
            # Written at the boundary id rather than appended, so that the list is indexed the
            # way the filter reads it however planeSpecifications happens to be ordered.
            boundaryScaleFactors = [1.0] * (max(specification["index"]
                                                for specification in planeSpecifications) + 1)
            for specification in planeSpecifications:
                clipPointId = clipPointsMarkupsNode.GetNthControlPointID(specification["index"])
                boundaryScaleFactors[specification["index"]] = extensionScaleFactors.get(clipPointId, 1.0)
        surface = self.extendVessel(
            surface, centerlinesPolyData, extensionRatio, extensionMode,
            transitionRatio, interpolationMode, preserveCrossSectionShape,
            boundaryScaleFactors)

    if cap and capMethod in _CAP_METHODS_NEEDING_TRIANGLES:
        # Ahead of the face ids being read, so that they still line up cell for cell with the
        # surface that gets capped (vtkTriangleFilter carries cell data over to every triangle
        # it splits a cell into).
        surface = self.triangulateSurface(surface)

    faceIdArrayName = (modelFaceIdArrayName or "").strip() if labelModelFaces else ""
    if labelModelFaces and not faceIdArrayName:
        logging.warning("Clip Vessel skipped labeling the faces: no face id array name was given.")

    # Read the labels while the cells still line up with the ones about to be capped: the
    # capping filter carries no other cell data through.
    existingFaceIds = None
    if faceIdArrayName:
        existingArray = surface.GetCellData().GetArray(faceIdArrayName)
        if existingArray is not None and existingArray.GetNumberOfTuples() == surface.GetNumberOfCells():
            existingFaceIds = vtk_to_numpy(existingArray).astype(np.int64).copy()
            if cap:
                # A vtkPolyData indexes cells verts, lines, polys, strips and the capping filter
                # copies only the polys, so take the poly cells' labels alone. One vert or line
                # cell - vtkCleanPolyData makes them from degenerate triangles - would otherwise
                # shift every label a cell out of step and scatter them over the surface.
                firstPolyCell = surface.GetNumberOfVerts() + surface.GetNumberOfLines()
                existingFaceIds = existingFaceIds[firstPolyCell:firstPolyCell + surface.GetNumberOfPolys()]

    # A cap takes the label of the boundary it closes, and every boundary has one: the clip point
    # index for a boundary a cut opened, and a fresh label above those for a hole no cut accounts
    # for. So the value the capper leaves on the cells it copied is the one thing that must not
    # be a label, and no label is negative.
    wallCellEntityId = -1

    # Cap all the holes that are in the surface
    if cap:
        slicer.util.showStatusMessage(_("Capping surface..."))
        slicer.app.processEvents() 
        # A private array, not the user's: on an input already carrying the user's array the
        # filter numbers the new caps on top of the existing ids (see capSurface). Remeshing the
        # caps needs it too, to tell a cap cell from a wall cell, even with no labeling asked for.
        surface = self.capSurface(surface,
                                  self.capBoundaryIdsArrayName if (faceIdArrayName or remeshCaps) else None,
                                  wallCellEntityId,
                                  capMethod=capMethod, constraintFactor=capConstraintFactor,
                                  numberOfRings=capNumberOfRings)

    # After capping and extensions: extensions drop cell data, and the caps only exist once the
    # capper has made them.
    self.lastFaceIdAssignments = []
    if faceIdArrayName:
        slicer.util.showStatusMessage(_("Labeling faces..."))
        slicer.app.processEvents()
        self.lastFaceIdAssignments = self.labelModelFaces(surface, planeSpecifications, faceIdArrayName,
                                                          existingFaceIds, wallCellEntityId)

    # Last of all: the remesher rebuilds the mesh and keeps only the one cell array it is given,
    # so anything that matches cells of the output up with cells of the input - the face labels
    # above do - has to have had its say by now.
    if cap and remeshCaps:
        slicer.util.showStatusMessage(_("Remeshing caps..."))
        slicer.app.processEvents()
        if faceIdArrayName:
            # The face ids are what the caps are told apart by, so the remesher carries the right
            # one onto every triangle it makes and the caps come out labeled without a second pass.
            capEntityIds = [faceId for faceId, _label in self.lastFaceIdAssignments]
            surface = self.remeshCaps(surface, faceIdArrayName, capEntityIds, capTargetEdgeLength)
            # The remesher rebuilds the cell data, which leaves nothing marked active.
            surface.GetCellData().SetActiveScalars(faceIdArrayName)
        else:
            # Nothing labeled the faces, so the capper's own per-boundary ids say which cells are
            # caps. They carry wallCellEntityId on the wall, which is negative and would read to
            # the remesher as "no entity", so they are shifted onto 0 for the wall and 1 up for
            # the caps (see remeshCaps).
            capBoundaryArray = surface.GetCellData().GetArray(self.capBoundaryIdsArrayName)
            if capBoundaryArray is not None:
                entityIds = vtk_to_numpy(capBoundaryArray).astype(np.int64) - wallCellEntityId
                entityIdsArray = numpy_to_vtk(entityIds.astype(np.int32), deep=True, array_type=vtk.VTK_INT)
                entityIdsArray.SetName(self.capBoundaryIdsArrayName)
                surface.GetCellData().RemoveArray(self.capBoundaryIdsArrayName)
                surface.GetCellData().AddArray(entityIdsArray)
                surface = self.remeshCaps(surface, self.capBoundaryIdsArrayName,
                                          [value for value in np.unique(entityIds) if value > 0],
                                          capTargetEdgeLength)
            surface.GetCellData().RemoveArray(self.capBoundaryIdsArrayName)   # internal bookkeeping

    surfacePolyData = vtk.vtkPolyData()
    surfacePolyData.DeepCopy(surface)
    if faceIdArrayName:
        # What labelModelFaces() labeled stays behind here; the copy is what the caller shows, so
        # it is the copy the run describes.
        self.rememberRunStateSurface(surfacePolyData)

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
    self.setUp()
    self.test_ClipVessel1()

  def test_ClipVessel1(self):
    """End-to-end test: download a vessel surface, extract its centerline (Extract Centerline
    module logic, with automatic endpoint detection), detect clip points from the centerline
    terminuses, and compute the clipped vessel with every clipping method."""
    self.delayDisplay("Starting the test")

    # Download and load the input vessel surface
    import SampleData
    inputSurfaceModelNode = SampleData.downloadFromURL(
        fileNames="aorta-surface.stl",
        nodeNames="aorta-surface",
        uris="https://raw.githubusercontent.com/vmtk/vmtk-test-data/master/input/aorta-surface.stl")[0]
    inputSurfacePolyData = inputSurfaceModelNode.GetPolyData()
    self.assertGreater(inputSurfacePolyData.GetNumberOfPoints(), 0)

    # Extract centerline using the Extract Centerline module logic
    import ExtractCenterline
    extractCenterlineLogic = ExtractCenterline.ExtractCenterlineLogic()

    self.delayDisplay("Preprocessing input surface")
    targetNumberOfPoints = 5000.0
    decimationAggressiveness = 4.0
    subdivideInputSurface = False
    preprocessedPolyData = extractCenterlineLogic.preprocess(inputSurfacePolyData, targetNumberOfPoints,
                                                             decimationAggressiveness, subdivideInputSurface)
    self.assertGreater(preprocessedPolyData.GetNumberOfPoints(), 0)

    self.delayDisplay("Detecting centerline endpoints")
    endPointsMarkupsNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "Centerline endpoints")
    networkPolyData = extractCenterlineLogic.extractNetwork(preprocessedPolyData, endPointsMarkupsNode)
    endpointPositions = extractCenterlineLogic.getEndPoints(networkPolyData, startPointPosition=None)
    # The aorta surface has one inlet and two iliac outlets
    self.assertGreaterEqual(len(endpointPositions), 3)
    for position in endpointPositions:
        endPointsMarkupsNode.AddControlPoint(vtk.vtkVector3d(position))

    self.delayDisplay("Extracting centerline")
    centerlinePolyData, voronoiDiagramPolyData = extractCenterlineLogic.extractCenterline(
        preprocessedPolyData, endPointsMarkupsNode)
    self.assertGreater(centerlinePolyData.GetNumberOfPoints(), 0)
    self.assertIsNotNone(centerlinePolyData.GetPointData().GetArray("Radius"))
    centerlineModelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Centerline model")
    centerlineModelNode.SetAndObserveMesh(centerlinePolyData)

    # Detect clip points from the centerline terminuses (inlet + one point per outlet).
    # The detected points lie on the centerline, pulled inward from each terminus by
    # insetFactor times the local vessel radius. The default inset (0.5x) leaves the clip
    # planes too close to the vessel ends on this coarsely decimated test surface (cuts can
    # miss the surface or come out non-planar), so a larger inset is used here.
    clipVesselLogic = ClipVesselLogic()
    self.delayDisplay("Detecting clip points")
    insetFactor = 1.5
    terminuses = clipVesselLogic.detectCenterlineTerminusClipPoints(centerlineModelNode, insetFactor)
    self.assertGreaterEqual(len(terminuses), 3)
    clipPointsMarkupsNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "Clip points")
    for terminus in terminuses:
        pointIndex = clipPointsMarkupsNode.AddControlPointWorld(vtk.vtkVector3d(terminus["position"]))
        clipPointsMarkupsNode.SetNthControlPointLabel(pointIndex, terminus["label"])

    # Compute the clipped vessel
    cap = True
    addFlowExtensions = False
    extensionRatio = 2.0
    extensionMode = "BOUNDARY_NORMAL"
    transitionRatio = 0.5

    # Clip with all clipping methods, each into its own output model node
    for clippingMethod in ["PLANE", "PLANE_SPHERE", "PLANE_PATCH", "BOX"]:
        self.delayDisplay("Clipping vessel (%s)" % clippingMethod)
        outputPolyData = clipVesselLogic.clipVessel(preprocessedPolyData, centerlineModelNode, clipPointsMarkupsNode,
                                                    cap, addFlowExtensions, extensionRatio, extensionMode,
                                                    clippingMethod=clippingMethod)
        self.assertIsNotNone(outputPolyData)
        self.assertGreater(outputPolyData.GetNumberOfCells(), 0)
        # Every clip point must have produced a cut
        self.assertEqual(clipVesselLogic.lastUnclippedPoints, [])
        if clippingMethod != "PLANE_SPHERE":
            # These methods cut with a plane, so every cut must be planar (planarity failures
            # would silently disable capping) and the capped output must be watertight.
            # PLANE_SPHERE is exempt: its cut may follow the sphere where the sphere is the
            # active constraint, which legitimately fails the planarity check.
            self.assertEqual(clipVesselLogic.lastPlanarityFailures, [])
            boundaryEdges = vtk.vtkFeatureEdges()
            boundaryEdges.SetInputData(outputPolyData)
            boundaryEdges.BoundaryEdgesOn()
            boundaryEdges.FeatureEdgesOff()
            boundaryEdges.NonManifoldEdgesOff()
            boundaryEdges.ManifoldEdgesOff()
            boundaryEdges.Update()
            self.assertEqual(boundaryEdges.GetOutput().GetNumberOfCells(), 0)
        outputModelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode",
            "Clipped vessel (%s)" % clippingMethod)
        outputModelNode.SetAndObserveMesh(outputPolyData)

    # Clip once per capping method. Each must close the surface with outward facing triangles.
    # A cap of zero roundness is flat, whichever method made it; only a smooth cap given enough
    # roundness domes out of the cut plane far enough to reach past the vessel itself.
    numberOfClipPointsForCaps = clipPointsMarkupsNode.GetNumberOfControlPoints()
    capMethodDiagonals = {}
    for capMethod, capRoundness in [("CENTERPOINT", 0.0), ("SIMPLE", 0.0), ("SMOOTH", 0.0), ("SMOOTH", 2.0)]:
        description = capMethod if capMethod != "SMOOTH" else "%s, roundness %g" % (capMethod, capRoundness)
        self.delayDisplay("Capping clipped vessel (%s)" % description)
        cappedPolyData = clipVesselLogic.clipVessel(preprocessedPolyData, centerlineModelNode, clipPointsMarkupsNode,
                                                    cap, addFlowExtensions, extensionRatio, extensionMode,
                                                    clippingMethod="PLANE_PATCH", labelModelFaces=True,
                                                    capMethod=capMethod, capConstraintFactor=capRoundness)
        self.assertIsNotNone(cappedPolyData)
        self.assertEqual(clipVesselLogic.lastUnclippedPoints, [])
        self.assertEqual(clipVesselLogic.lastPlanarityFailures, [])
        # Every cell must be a triangle, whichever capper made it
        self.assertEqual(cappedPolyData.GetPolys().IsHomogeneous(), 3)
        self.assertEqual(cappedPolyData.GetNumberOfCells(), cappedPolyData.GetNumberOfPolys())
        # The caps must face the same way as the vessel wall: re-orienting the output must find
        # nothing to re-wind. Two of the three cappers wind their caps inwards on their own, so
        # without the fix in capSurface the caps would render as though lit from inside.
        orientedCaps = vtk.vtkPolyDataNormals()
        orientedCaps.SetInputData(cappedPolyData)
        orientedCaps.ComputePointNormalsOff()
        orientedCaps.ComputeCellNormalsOn()
        orientedCaps.ConsistencyOn()
        orientedCaps.AutoOrientNormalsOn()
        orientedCaps.SplittingOff()
        orientedCaps.Update()
        self.assertTrue(np.array_equal(
            vtk_to_numpy(cappedPolyData.GetPolys().GetConnectivityArray()),
            vtk_to_numpy(orientedCaps.GetOutput().GetPolys().GetConnectivityArray())))
        # No normals may survive capping either: the simple capper hands its cap vertices the
        # normals the vessel wall left on them, which shades the cap as though it were wall.
        for attributes in [cappedPolyData.GetPointData(), cappedPolyData.GetCellData()]:
            self.assertIsNone(attributes.GetNormals())
            self.assertIsNone(attributes.GetArray("Normals"))
        # The caps must close the surface
        boundaryEdges = vtk.vtkFeatureEdges()
        boundaryEdges.SetInputData(cappedPolyData)
        boundaryEdges.BoundaryEdgesOn()
        boundaryEdges.FeatureEdgesOff()
        boundaryEdges.NonManifoldEdgesOff()
        boundaryEdges.ManifoldEdgesOff()
        boundaryEdges.Update()
        self.assertEqual(boundaryEdges.GetOutput().GetNumberOfCells(), 0)
        # ...and each of them must be labeled as its own face, as with the default capper
        capFaceIds = vtk_to_numpy(cappedPolyData.GetCellData().GetArray("ModelFaceID"))
        self.assertEqual(set(int(value) for value in np.unique(capFaceIds)),
                         set(range(1, numberOfClipPointsForCaps + 2)))
        if capRoundness == 0.0:
            # A cap of zero roundness is flat: every point of it lies in one plane, the plane of
            # the cut it closes. Measured as the spread of the cap's points along the normal of
            # their own best fit plane, against the width of the cap itself, so that it says
            # "flat" rather than "small".
            cappedPoints = vtk_to_numpy(cappedPolyData.GetPoints().GetData())
            for capFaceId in range(2, numberOfClipPointsForCaps + 2):
                capPointIds = set()
                for cellId in np.nonzero(capFaceIds == capFaceId)[0]:
                    cell = cappedPolyData.GetCell(int(cellId))
                    for pointIndex in range(cell.GetNumberOfPoints()):
                        capPointIds.add(cell.GetPointId(pointIndex))
                self.assertGreater(len(capPointIds), 3, "cap %d has no cells" % capFaceId)
                capPoints = cappedPoints[sorted(capPointIds)]
                centered = capPoints - capPoints.mean(axis=0)
                singularValues, rightVectors = np.linalg.svd(centered)[1:]
                outOfPlane = np.abs(centered @ rightVectors[-1]).max()
                capWidth = singularValues[0]
                self.assertLess(outOfPlane, 0.01 * capWidth,
                                "%s cap %d is %g out of plane across a width of %g"
                                % (description, capFaceId, outOfPlane, capWidth))
        capMethodDiagonals[description] = vtk.vtkBoundingBox(cappedPolyData.GetBounds()).GetDiagonalLength()
        cappedModelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode",
            "Clipped vessel (cap: %s)" % description)
        cappedModelNode.SetAndObserveMesh(cappedPolyData)
    # A flat cap adds nothing to the extent of the surface, whichever method made it, so all
    # three agree with the centre point capper. Roundness is what changes that, and it has to be
    # enough of it: a modest dome is still inside the bounding box of the vessel, which is set by
    # the vessel rather than by its ends, so the box only grows once the cap reaches past it.
    self.assertAlmostEqual(capMethodDiagonals["SIMPLE"], capMethodDiagonals["CENTERPOINT"], delta=0.01)
    self.assertAlmostEqual(capMethodDiagonals["SMOOTH, roundness 0"], capMethodDiagonals["CENTERPOINT"], delta=0.01)
    self.assertGreater(capMethodDiagonals["SMOOTH, roundness 2"], capMethodDiagonals["CENTERPOINT"])

    # Clip again with flow extensions added to the open vessel ends, once per interpolation mode,
    # and once more with the cross-section shape of the vessel ends preserved
    extensionOptions = [("LINEAR", False), ("THIN_PLATE_SPLINE", False), ("RAMP", False), ("RAMP", True)]
    for interpolationMode, preserveCrossSectionShape in extensionOptions:
        description = "%s%s" % (interpolationMode, ", preserved cross-section" if preserveCrossSectionShape else "")
        self.delayDisplay("Clipping vessel with flow extensions (%s)" % description)
        extendedPolyData = clipVesselLogic.clipVessel(preprocessedPolyData, centerlineModelNode, clipPointsMarkupsNode,
                                                      cap, True, extensionRatio, extensionMode,
                                                      transitionRatio=transitionRatio,
                                                      interpolationMode=interpolationMode,
                                                      preserveCrossSectionShape=preserveCrossSectionShape)
        self.assertIsNotNone(extendedPolyData)
        self.assertGreater(extendedPolyData.GetNumberOfCells(), 0)
        self.assertEqual(clipVesselLogic.lastUnclippedPoints, [])
        # The extensions must make the model larger than the plain clipped output
        extendedBounds = vtk.vtkBoundingBox(extendedPolyData.GetBounds())
        clippedBounds = vtk.vtkBoundingBox(outputPolyData.GetBounds())
        self.assertGreater(extendedBounds.GetDiagonalLength(), clippedBounds.GetDiagonalLength())
        extendedModelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode",
            "Clipped vessel (flow extensions, %s)" % description)
        extendedModelNode.SetAndObserveMesh(extendedPolyData)

    # Clip once more with a per-endpoint extension length scale factor: only the inlet
    # extension is scaled, the outlet extensions keep the common length.
    inletScaleFactor = 2.5
    inletPointId = clipPointsMarkupsNode.GetNthControlPointID(0)  # the first detected terminus is the inlet
    self.delayDisplay("Clipping vessel with the inlet flow extension scaled %gx" % inletScaleFactor)
    # The infinite-plane method is used so that each cut removes the entire end piece: the
    # localized methods can leave slivers of the original vessel end (outside their local
    # sphere) beyond the clip plane, which would corrupt the extension length measurement.
    unscaledPolyData = clipVesselLogic.clipVessel(preprocessedPolyData, centerlineModelNode, clipPointsMarkupsNode,
                                                  False, True, extensionRatio, extensionMode,
                                                  clippingMethod="PLANE",
                                                  transitionRatio=transitionRatio, interpolationMode="RAMP")
    scaledPolyData = clipVesselLogic.clipVessel(preprocessedPolyData, centerlineModelNode, clipPointsMarkupsNode,
                                                False, True, extensionRatio, extensionMode,
                                                clippingMethod="PLANE",
                                                transitionRatio=transitionRatio, interpolationMode="RAMP",
                                                extensionScaleFactors={inletPointId: inletScaleFactor})
    self.assertEqual(clipVesselLogic.lastUnclippedPoints, [])

    def extensionTipDistance(polyData, origin, normal, radius):
        """How far the surface reaches beyond a clip plane along its outward normal, within a
        cylinder of twice the local vessel radius around the extension axis. The default
        localized clipping method leaves distant parts of the vessel beyond the (infinite,
        oblique) clip plane, so the reach may only be measured near the extension itself."""
        offsets = vtk_to_numpy(polyData.GetPoints().GetData()) - np.asarray(origin)
        heights = offsets.dot(np.asarray(normal))
        lateralDistances = np.linalg.norm(offsets - np.outer(heights, np.asarray(normal)), axis=1)
        return float(np.max(heights[lateralDistances < 2.0 * radius]))

    # Each cut removed the local end region beyond its clip plane, so whatever reaches beyond
    # the plane near the extension axis is that end's flow extension; the farthest such point
    # measures its length.
    for controlPointIndex in range(clipPointsMarkupsNode.GetNumberOfControlPoints()):
        origin, normal, radius = clipVesselLogic.automaticClipPlane(centerlineModelNode, clipPointsMarkupsNode, controlPointIndex)
        unscaledLength = extensionTipDistance(unscaledPolyData, origin, normal, radius)
        scaledLength = extensionTipDistance(scaledPolyData, origin, normal, radius)
        if controlPointIndex == 0:
            # The inlet extension must be scaled by about the requested factor (extensions are
            # built in whole layers, so the length only matches to within a layer).
            self.assertGreater(scaledLength, 0.8 * inletScaleFactor * unscaledLength)
            self.assertLess(scaledLength, 1.2 * inletScaleFactor * unscaledLength)
        else:
            # The outlet extensions must be unaffected by the inlet's scale factor.
            self.assertAlmostEqual(scaledLength, unscaledLength, delta=0.01)
    unscaledModelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Clipped vessel (unscaled extensions)")
    unscaledModelNode.SetAndObserveMesh(unscaledPolyData)
    scaledModelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Clipped vessel (inlet extension scaled)")
    scaledModelNode.SetAndObserveMesh(scaledPolyData)
    # Face labeling: wall id 1, then one cap per clip point in clip point order. Run it with and
    # without flow extensions, since extensions move each cap several radii from the clip plane
    # it grew from, which is the case the cap-to-clip-point matching has to cope with.
    numberOfClipPoints = clipPointsMarkupsNode.GetNumberOfControlPoints()
    clipPlanes = [clipVesselLogic.automaticClipPlane(centerlineModelNode, clipPointsMarkupsNode, index)
                  for index in range(numberOfClipPoints)]
    for addExtensions in [False, True]:
        self.delayDisplay("Labeling model faces (%s flow extensions)" % ("with" if addExtensions else "without"))
        labeledPolyData = clipVesselLogic.clipVessel(preprocessedPolyData, centerlineModelNode, clipPointsMarkupsNode,
                                                     cap, addExtensions, extensionRatio, extensionMode,
                                                     transitionRatio=transitionRatio, labelModelFaces=True)
        faceIdArray = labeledPolyData.GetCellData().GetArray("ModelFaceID")
        self.assertIsNotNone(faceIdArray)
        self.assertTrue(faceIdArray.IsA("vtkIntArray"))
        self.assertEqual(faceIdArray.GetNumberOfTuples(), labeledPolyData.GetNumberOfCells())
        faceIds = vtk_to_numpy(faceIdArray)
        self.assertEqual(clipVesselLogic.lastWallFaceId, 1)
        self.assertEqual(clipVesselLogic.lastExistingFaceIdMap, {})
        self.assertEqual(set(int(value) for value in np.unique(faceIds)), set(range(1, numberOfClipPoints + 2)))
        self.assertGreater(np.count_nonzero(faceIds == 1), np.count_nonzero(faceIds != 1))
        self.assertEqual(len(clipVesselLogic.lastFaceIdAssignments), numberOfClipPoints)
        cellCenters = vtk.vtkCellCenters()
        cellCenters.SetInputData(labeledPolyData)
        cellCenters.Update()
        centers = vtk_to_numpy(cellCenters.GetOutput().GetPoints().GetData())
        for faceId, pointLabel in clipVesselLogic.lastFaceIdAssignments:
            index = faceId - 2
            self.assertEqual(pointLabel, clipPointsMarkupsNode.GetNthControlPointLabel(index))
            # Each cap must sit on its own clip plane's axis, and beyond the plane once an
            # extension has pushed it down the removed branch.
            origin, normal, radius = clipPlanes[index]
            offset = centers[faceIds == faceId].mean(axis=0) - np.array(origin)
            alongNormal = float(np.dot(offset, normal))
            self.assertLess(float(np.linalg.norm(offset - alongNormal * np.array(normal))), radius)
            if addExtensions:
                self.assertGreater(alongNormal, 0.0)

    # Uncapped: no caps to tell apart, so the whole surface is wall.
    self.delayDisplay("Labeling model faces (uncapped)")
    uncappedPolyData = clipVesselLogic.clipVessel(preprocessedPolyData, centerlineModelNode, clipPointsMarkupsNode,
                                                  False, False, extensionRatio, extensionMode, labelModelFaces=True)
    self.assertEqual(set(int(value) for value in np.unique(
        vtk_to_numpy(uncappedPolyData.GetCellData().GetArray("ModelFaceID")))), {1})
    self.assertEqual(clipVesselLogic.lastFaceIdAssignments, [])

    # An input that already carries labels: face 10 compacts to 1, the wall takes 2 and the caps
    # follow, and no cap is fused into the pre-existing face (which can only shrink as it is
    # clipped, never grow).
    self.delayDisplay("Labeling model faces (input already labeled)")
    prelabeledInput = vtk.vtkPolyData()
    prelabeledInput.DeepCopy(preprocessedPolyData)
    patchCellCount = prelabeledInput.GetNumberOfCells() // 10
    prelabeledValues = np.zeros(prelabeledInput.GetNumberOfCells(), dtype=np.int32)
    prelabeledValues[:patchCellCount] = 10
    prelabeledArray = numpy_to_vtk(prelabeledValues, deep=True, array_type=vtk.VTK_INT)
    prelabeledArray.SetName("ModelFaceID")
    prelabeledInput.GetCellData().AddArray(prelabeledArray)
    prelabeledPolyData = clipVesselLogic.clipVessel(prelabeledInput, centerlineModelNode, clipPointsMarkupsNode,
                                                    cap, False, extensionRatio, extensionMode, labelModelFaces=True)
    prelabeledFaceIds = vtk_to_numpy(prelabeledPolyData.GetCellData().GetArray("ModelFaceID"))
    self.assertEqual(clipVesselLogic.lastExistingFaceIdMap, {10: 1})
    self.assertEqual(clipVesselLogic.lastWallFaceId, 2)
    self.assertEqual(set(int(value) for value in np.unique(prelabeledFaceIds)),
                     set(range(1, numberOfClipPoints + 3)))
    self.assertGreater(np.count_nonzero(prelabeledFaceIds == 1), 0)
    self.assertLessEqual(np.count_nonzero(prelabeledFaceIds == 1), patchCellCount)
    # The internal cap bookkeeping array must not leak into the output
    self.assertIsNone(prelabeledPolyData.GetCellData().GetArray(clipVesselLogic.capBoundaryIdsArrayName))

    # Show all models as surface with edges
    for modelNode in slicer.util.getNodesByClass("vtkMRMLModelNode"):
        modelNode.CreateDefaultDisplayNodes()
        displayNode = modelNode.GetDisplayNode()
        displayNode.SetVisibility(True)
        displayNode.SetEdgeVisibility(True)

    self.delayDisplay("Test passed")
