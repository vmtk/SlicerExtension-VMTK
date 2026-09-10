import logging
import math
import time

import vtk
import qt
import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule, ScriptedLoadableModuleWidget,
    ScriptedLoadableModuleLogic, ScriptedLoadableModuleTest,
)
from slicer.util import VTKObservationMixin


class CenterlineJunctionAngles(ScriptedLoadableModule):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent.title = _("Centerline junction angles")
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Vascular Modeling Toolkit")]
        self.parent.dependencies = []
        self.parent.contributors = ["Aaron Brown"]
        self.parent.helpText = _("Measure angles between branches of a centerline model. "
            "Select a model from Extract Centerline and click Compute. "
            'See the <a href="https://github.com/vmtk/SlicerExtension-VMTK/blob/master/Docs/CenterlineJunctionAngles.md">documentation</a>.')
        self.parent.acknowledgementText = _("Uses VMTK bifurcation reference systems and bifurcation vectors.")


class CenterlineJunctionAnglesWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    def __init__(self, parent=None):
        VTKObservationMixin.__init__(self)
        self._parameterNode = None
        ScriptedLoadableModuleWidget.__init__(self, parent)

    def setup(self):
        super().setup()
        self.logic = CenterlineJunctionAnglesLogic()
        form = qt.QFormLayout()
        self.layout.addLayout(form)
        self.inputSelector = slicer.qMRMLNodeComboBox()
        self.inputSelector.nodeTypes = ["vtkMRMLModelNode"]
        self.inputSelector.addEnabled = False
        self.inputSelector.removeEnabled = False
        self.inputSelector.noneEnabled = True
        self.inputSelector.setMRMLScene(slicer.mrmlScene)
        self.inputSelector.toolTip = _("Centerline model created by Extract Centerline.")
        form.addRow(_("Input centerline:"), self.inputSelector)
        self.showVectorNames = qt.QCheckBox(_("Show vector names"))
        form.addRow(self.showVectorNames)
        self.applyButton = qt.QPushButton(_("Compute junction angles"))
        form.addRow(self.applyButton)
        self.highlightThresholdSpinBox = qt.QDoubleSpinBox()
        self.highlightThresholdSpinBox.setRange(0.0, 180.0)
        self.highlightThresholdSpinBox.setSingleStep(5.0)
        self.highlightThresholdSpinBox.setSuffix(_(" degrees"))
        self.highlightThresholdSpinBox.value = 60.0
        self.highlightThresholdSpinBox.toolTip = _("Angles greater than this threshold are highlighted in red.")
        form.addRow(_("Highlight above:"), self.highlightThresholdSpinBox)
        self.highlightButton = qt.QPushButton(_("Highlight angle annotations"))
        form.addRow(self.highlightButton)
        self.resetColorsButton = qt.QPushButton(_("Reset annotation colors"))
        form.addRow(self.resetColorsButton)
        self.layout.addStretch(1)
        self.inputSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
        self.showVectorNames.connect("toggled(bool)", self.updateParameterNodeFromGUI)
        self.highlightThresholdSpinBox.connect("valueChanged(double)", self.updateParameterNodeFromGUI)
        self.applyButton.connect("clicked(bool)", self.onApplyButton)
        self.highlightButton.connect("clicked(bool)", self.onHighlightButton)
        self.resetColorsButton.connect("clicked(bool)", self.onResetColorsButton)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
        self.initializeParameterNode()

    def cleanup(self):
        self.removeObservers()

    def enter(self):
        self.initializeParameterNode()

    def onSceneStartClose(self, caller, event):
        self.setParameterNode(None)
        self.logic.clearCache()

    def onSceneEndClose(self, caller, event):
        if self.parent.isEntered:
            self.initializeParameterNode()

    def initializeParameterNode(self):
        self.setParameterNode(self.logic.getParameterNode())

    def setParameterNode(self, node):
        if self._parameterNode:
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
        self._parameterNode = node
        if node:
            self.addObserver(node, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
        self.updateGUIFromParameterNode()

    def updateGUIFromParameterNode(self, caller=None, event=None):
        blocked = self.inputSelector.blockSignals(True)
        self.inputSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputCenterline") if self._parameterNode else None)
        self.inputSelector.blockSignals(blocked)
        blocked = self.showVectorNames.blockSignals(True)
        self.showVectorNames.checked = bool(self._parameterNode and self._parameterNode.GetParameter("ShowVectorNames") == "1")
        self.showVectorNames.blockSignals(blocked)
        blocked = self.highlightThresholdSpinBox.blockSignals(True)
        if self._parameterNode and self._parameterNode.GetParameter("HighlightThresholdDegrees"):
            self.highlightThresholdSpinBox.value = float(self._parameterNode.GetParameter("HighlightThresholdDegrees"))
        self.highlightThresholdSpinBox.blockSignals(blocked)
        self.applyButton.enabled = self.inputSelector.currentNode() is not None

    def updateParameterNodeFromGUI(self, *args):
        if not self._parameterNode:
            return
        with slicer.util.NodeModify(self._parameterNode):
            node = self.inputSelector.currentNode()
            self._parameterNode.SetNodeReferenceID("InputCenterline", node.GetID() if node else None)
            self._parameterNode.SetParameter("ShowVectorNames", "1" if self.showVectorNames.checked else "0")
            self._parameterNode.SetParameter("HighlightThresholdDegrees", str(self.highlightThresholdSpinBox.value))

    def onApplyButton(self):
        with slicer.util.tryWithErrorDisplay(_("Failed to compute junction angles."), waitCursor=True):
            inputCenterline = self.inputSelector.currentNode()
            if inputCenterline is None:
                raise ValueError(_("Please select a centerline model."))
            progressDialog = self.createProgressDialog()
            try:
                self.updateProgress(progressDialog, self.branchExtractionProgressMessage(inputCenterline.GetPolyData()), None)
                self.logic.splitCenterlines(inputCenterline.GetPolyData())
                self.updateProgress(progressDialog, _("Computing junction angles..."), 25)
                junctionAngles = self.logic.processJunctionAngles()
                if not junctionAngles:
                    slicer.util.infoDisplay(_("No junction angles were computed: the centerline has no measurable bifurcation."))
                    return
                self.updateProgress(progressDialog, _("Creating junction angle table..."), 50)
                slicer.mrmlScene.StartState(slicer.mrmlScene.BatchProcessState)
                try:
                    label = _("Centerline junction angles") + " - " + inputCenterline.GetName()
                    tableNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLTableNode", label)
                    self.logic.populateJunctionAnglesTable(tableNode, junctionAngles)
                    self.updateProgress(progressDialog, _("Creating bifurcation vectors..."), 65)
                    vectorFolder = self._createCurveSubjectHierarchyFolderNode(label + _(" vectors"))
                    self._createBifurcationVectorModel(self.logic.computeBifurcationVectors(), vectorFolder, self.showVectorNames.checked)
                    self.updateProgress(progressDialog, _("Creating junction angle annotations..."), 80)
                    angleFolder = self._createCurveSubjectHierarchyFolderNode(label + _(" annotations"))
                    self._createJunctionAngleGroupComponents(junctionAngles, angleFolder)
                finally:
                    slicer.mrmlScene.EndState(slicer.mrmlScene.BatchProcessState)
                self.updateProgress(progressDialog, _("Finished computing junction angles."), 100)
            finally:
                progressDialog.close()

    def createProgressDialog(self):
        progressDialog = qt.QProgressDialog(slicer.util.mainWindow())
        progressDialog.setWindowTitle(_("Centerline junction angles"))
        progressDialog.setLabelText(_("Starting computation..."))
        progressDialog.setCancelButton(None)
        progressDialog.setRange(0, 0)
        progressDialog.minimumDuration = 0
        progressDialog.windowModality = qt.Qt.WindowModal
        progressDialog.show()
        slicer.app.processEvents()
        return progressDialog

    def updateProgress(self, progressDialog, message, value) -> None:
        logging.info(message)
        progressDialog.setLabelText(message)
        if value is None:
            progressDialog.setRange(0, 0)
        else:
            progressDialog.setRange(0, 100)
            progressDialog.value = value
        slicer.util.showStatusMessage(message, 3000)
        slicer.app.processEvents()

    def branchExtractionProgressMessage(self, inputCenterline):
        if inputCenterline:
            return _("Analyzing centerline topology with VMTK ({points} points, {cells} cells). "
                     "Slicer may not respond during this step.").format(
                         points=inputCenterline.GetNumberOfPoints(),
                         cells=inputCenterline.GetNumberOfCells())
        return _("Analyzing centerline topology with VMTK. Slicer may not respond during this step.")

    def onHighlightButton(self):
        numberOfHighlightedNodes = self.highlightJunctionAngleAnnotations(self.highlightThresholdSpinBox.value)
        slicer.util.showStatusMessage(
            _("{count} junction angle annotations highlighted.").format(count=numberOfHighlightedNodes), 3000)

    def onResetColorsButton(self):
        numberOfResetNodes = self.resetJunctionAngleAnnotationColors()
        slicer.util.showStatusMessage(
            _("{count} junction angle annotation colors reset.").format(count=numberOfResetNodes), 3000)

    def highlightJunctionAngleAnnotations(self, thresholdDegrees, aboveColor=(1.0, 0.0, 0.0)):
        numberOfHighlightedNodes = 0
        for labelsNode in slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode"):
            if labelsNode.GetAttribute("CenterlineJunctionAngleLabels") != "1":
                continue
            labelsNode.GetDisplayNode().SetSelectedColor(aboveColor)
            for pointIndex in range(labelsNode.GetNumberOfControlPoints()):
                angleValue = labelsNode.GetNthControlPointDescription(pointIndex)
                if not angleValue:
                    continue
                highlighted = float(angleValue) > thresholdDegrees
                labelsNode.SetNthControlPointSelected(pointIndex, highlighted)
                if highlighted:
                    numberOfHighlightedNodes += 1
        return numberOfHighlightedNodes

    def resetJunctionAngleAnnotationColors(self):
        numberOfResetNodes = 0
        for labelsNode in slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode"):
            if labelsNode.GetAttribute("CenterlineJunctionAngleLabels") != "1":
                continue
            pairType = labelsNode.GetAttribute("PairType")
            if pairType not in junctionAnglePairTypeColors:
                continue
            labelsNode.GetDisplayNode().SetSelectedColor(junctionAnglePairTypeColors[pairType])
            for pointIndex in range(labelsNode.GetNumberOfControlPoints()):
                labelsNode.SetNthControlPointSelected(pointIndex, False)
                numberOfResetNodes += 1
        return numberOfResetNodes

    def _createCurveSubjectHierarchyFolderNode(self, label, parentFolderId=None):
        shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
        folderId = shNode.CreateFolderItem(shNode.GetSceneItemID() if parentFolderId is None else parentFolderId, label)
        shNode.SetItemExpanded(folderId, False)
        return folderId

    def _reparentNodeToSubjectHierarchyFolderNode(self, shFolderId, anyObject) -> None:
        if shFolderId < 0:
            return
        shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
        shObjectId = shNode.GetItemByDataNode(anyObject)
        shNode.SetItemParent(shObjectId, shFolderId)

    def _createPolylineModel(self, name, polylines, color, parentFolderId, lineWidth=2):
        if not polylines:
            return None
        points = vtk.vtkPoints()
        lines = vtk.vtkCellArray()
        polyData = vtk.vtkPolyData()
        for polyline in polylines:
            lines.InsertNextCell(len(polyline))
            for position in polyline:
                pointId = points.InsertNextPoint(position)
                lines.InsertCellPoint(pointId)
        polyData.SetPoints(points)
        polyData.SetLines(lines)
        modelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", name)
        modelNode.SetAndObservePolyData(polyData)
        modelNode.CreateDefaultDisplayNodes()
        displayNode = modelNode.GetDisplayNode()
        displayNode.SetColor(color)
        displayNode.SetLineWidth(lineWidth)
        displayNode.SetScalarVisibility(False)
        displayNode.SetVisibility2D(True)
        modelNode.SetAttribute("CenterlineJunctionAngles", "1")
        self._reparentNodeToSubjectHierarchyFolderNode(parentFolderId, modelNode)
        return modelNode

    def _createLabelsNode(self, name, labels, color, parentFolderId, attributes=None):
        if not labels:
            return None
        labelsNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", name)
        labelsNode.CreateDefaultDisplayNodes()
        displayNode = labelsNode.GetDisplayNode()
        displayNode.SetSelectedColor(color)
        displayNode.SetGlyphType(slicer.vtkMRMLMarkupsDisplayNode.Vertex2D)
        displayNode.SetGlyphScale(0.0)
        displayNode.SetTextScale(junctionAngleTextScale)
        displayNode.SetPointLabelsVisibility(True)
        displayNode.SetPropertiesLabelVisibility(False)
        displayNode.SetOccludedVisibility(True)
        displayNode.SetOccludedOpacity(occludedOpacity)
        for position, label, description in labels:
            pointIndex = labelsNode.AddControlPoint(vtk.vtkVector3d(position))
            labelsNode.SetNthControlPointLabel(pointIndex, label)
            labelsNode.SetNthControlPointDescription(pointIndex, description)
        labelsNode.SetLocked(True)
        labelsNode.SetAttribute("CenterlineJunctionAngles", "1")
        if attributes:
            for attributeName, attributeValue in attributes.items():
                labelsNode.SetAttribute(attributeName, str(attributeValue))
        self._reparentNodeToSubjectHierarchyFolderNode(parentFolderId, labelsNode)
        return labelsNode

    def _createBifurcationVectorModel(self, bifurcations, parentFolderId, showLabels):
        polylines = []
        labels = []
        for bifurcation in bifurcations:
            for groupId in sorted(bifurcation["branches"]):
                branch = bifurcation["branches"][groupId]
                if branch["vectorLength"] <= minimumVectorLength:
                    continue
                basePosition = branch["basePosition"]
                endPosition = [basePosition[i] + branch["vector"][i] for i in range(3)]
                polylines.append([basePosition, endPosition])
                if showLabels:
                    labels.append(([(basePosition[i] + endPosition[i]) / 2.0 for i in range(3)],
                                   _("Group {groupId}").format(groupId=branch["groupId"]),
                                   str(branch["groupId"])))
        self._createPolylineModel(_("Bifurcation vectors"), polylines, bifurcationVectorColor, parentFolderId, 3)
        self._createLabelsNode(_("Bifurcation vector labels"), labels, bifurcationVectorColor, parentFolderId)

    @staticmethod
    def _rayEndPosition(junctionAngle, positionKey):
        junctionPosition = junctionAngle["junctionPosition"]
        position = junctionAngle[positionKey]
        return [junctionPosition[i] + (position[i] - junctionPosition[i]) * junctionAngleRayScale
                for i in range(3)]

    @staticmethod
    def _angleArcPolyline(junctionAngle, numberOfSegments=12):
        junctionPosition = junctionAngle["junctionPosition"]
        ray1EndPosition = CenterlineJunctionAnglesWidget._rayEndPosition(junctionAngle, "branch1Position")
        ray2EndPosition = CenterlineJunctionAnglesWidget._rayEndPosition(junctionAngle, "branch2Position")
        vector1 = [ray1EndPosition[i] - junctionPosition[i] for i in range(3)]
        vector2 = [ray2EndPosition[i] - junctionPosition[i] for i in range(3)]
        length1 = vtk.vtkMath.Norm(vector1)
        length2 = vtk.vtkMath.Norm(vector2)
        if length1 <= minimumVectorLength or length2 <= minimumVectorLength:
            return [], junctionPosition
        for i in range(3):
            vector1[i] /= length1
            vector2[i] /= length2
        radius = min(length1, length2) * 0.35
        points = []
        for index in range(numberOfSegments + 1):
            ratio = index / numberOfSegments
            direction = [(1.0 - ratio) * vector1[i] + ratio * vector2[i] for i in range(3)]
            directionLength = vtk.vtkMath.Norm(direction)
            if directionLength <= minimumVectorLength:
                continue
            points.append([junctionPosition[i] + radius * direction[i] / directionLength for i in range(3)])
        labelPosition = points[len(points) // 2] if points else junctionPosition
        return points, labelPosition

    def _createJunctionAngleGroupComponents(self, junctionAngles, parentFolderId):
        labels = {"child-child": _("Child-child angles"), "parent-child": _("Parent-child angles"), "parent-parent": _("Parent-parent angles")}
        folders = {}
        groupedAnnotations = {}
        for junctionAngle in junctionAngles:
            if math.isnan(junctionAngle["angleDegrees"]):
                continue
            pairType = self.logic.junctionAnglePairType(junctionAngle["branch1Role"], junctionAngle["branch2Role"])
            if pairType not in folders:
                folders[pairType] = self._createCurveSubjectHierarchyFolderNode(labels[pairType], parentFolderId)
            branchOrder = junctionAngle["branchOrder"]
            groupKey = (pairType, branchOrder)
            if groupKey not in folders:
                folders[groupKey] = self._createCurveSubjectHierarchyFolderNode(
                    _("Branch order {order}").format(order=branchOrder), folders[pairType])
            groupedAnnotations.setdefault(groupKey, {"rays": [], "arcs": [], "labels": []})
            ray1EndPosition = self._rayEndPosition(junctionAngle, "branch1Position")
            ray2EndPosition = self._rayEndPosition(junctionAngle, "branch2Position")
            groupedAnnotations[groupKey]["rays"].append([ray1EndPosition, junctionAngle["junctionPosition"], ray2EndPosition])
            arcPolyline, labelPosition = self._angleArcPolyline(junctionAngle)
            if arcPolyline:
                groupedAnnotations[groupKey]["arcs"].append(arcPolyline)
            groupedAnnotations[groupKey]["labels"].append((labelPosition, _("{angle:.1f}°").format(
                angle=junctionAngle["angleDegrees"]), str(junctionAngle["angleDegrees"])))

        for groupKey, annotations in groupedAnnotations.items():
            pairType, branchOrder = groupKey
            folder = folders[groupKey]
            color = junctionAnglePairTypeColors[pairType]
            nameSuffix = _("branch order {order}").format(order=branchOrder)
            self._createPolylineModel(_("Junction angle rays - {suffix}").format(suffix=nameSuffix),
                                      annotations["rays"], color, folder, 2)
            self._createPolylineModel(_("Junction angle arcs - {suffix}").format(suffix=nameSuffix),
                                      annotations["arcs"], color, folder, 2)
            self._createLabelsNode(_("Junction angle labels - {suffix}").format(suffix=nameSuffix),
                                   annotations["labels"], color, folder,
                                   {"CenterlineJunctionAngleLabels": "1",
                                    "PairType": pairType,
                                    "BranchOrder": branchOrder})

    def _createBifurcationVectorComponent(self, branch, parentFolderId, showCurveName):
        """Create a curve for the segment over which the direction of a branch was measured.
        A branch whose vector has no length has no direction, it cannot be shown.
        """
        if branch["vectorLength"] <= minimumVectorLength:
            return None
        name = slicer.mrmlScene.GenerateUniqueName(_("Bifurcation_Vector"))
        curve = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsCurveNode", name)
        curve.CreateDefaultDisplayNodes()
        curve.GetDisplayNode().SetPropertiesLabelVisibility(showCurveName)
        curve.GetDisplayNode().SetSelectedColor([1.0, 0.5, 0.0])
        # A measured segment is inside the vessel, like the annotations
        curve.GetDisplayNode().SetOccludedVisibility(True)
        curve.GetDisplayNode().SetOccludedOpacity(occludedOpacity)
        curve.SetNumberOfPointsPerInterpolatingSegment(1)
        basePosition = branch["basePosition"]
        curve.AddControlPoint(vtk.vtkVector3d(basePosition))
        curve.AddControlPoint(vtk.vtkVector3d([basePosition[i] + branch["vector"][i] for i in range(3)]))
        curve.SetAttribute("GroupId", str(branch["groupId"]))
        # A measurement result, it must not be changed by moving a control point
        curve.SetLocked(True)
        self._reparentNodeToSubjectHierarchyFolderNode(parentFolderId, curve)
        return curve

    def _createJunctionAngleComponent(self, junctionAngle, parentFolderId):
        """Create an angle markup that shows a measured angle in 3D views.
        A pair with a branch that has no direction has no angle: its control points would be at the same
        position, which VTK cannot measure an angle from. Such a pair is in the table only.
        """
        if math.isnan(junctionAngle["angleDegrees"]):
            return None
        pairType = self.logic.junctionAnglePairType(junctionAngle["branch1Role"], junctionAngle["branch2Role"])
        angleNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsAngleNode", _("Junction_Angle"))
        angleNode.CreateDefaultDisplayNodes()

        # The rays are drawn several times longer than the measured segments, to be readable next to the
        # vessel. The angle depends on their directions only, and the bifurcation vector curves show over
        # what distance a direction was actually measured.
        junctionPosition = junctionAngle["junctionPosition"]

        def rayEndPosition(positionKey):
            position = junctionAngle[positionKey]
            return [junctionPosition[i] + (position[i] - junctionPosition[i]) * junctionAngleRayScale
                    for i in range(3)]

        # The angle is measured at the second control point, which is the bifurcation origin
        angleNode.AddControlPoint(vtk.vtkVector3d(rayEndPosition("branch1Position")))
        angleNode.AddControlPoint(vtk.vtkVector3d(junctionPosition))
        angleNode.AddControlPoint(vtk.vtkVector3d(rayEndPosition("branch2Position")))
        angleNode.SetAttribute("BifurcationGroupId", str(junctionAngle["bifurcationGroupId"]))
        angleNode.SetAttribute("Branch1GroupId", str(junctionAngle["branch1GroupId"]))
        angleNode.SetAttribute("Branch2GroupId", str(junctionAngle["branch2GroupId"]))
        angleNode.SetAttribute("BranchOrder", str(junctionAngle["branchOrder"]))
        angleNode.SetAttribute("PairType", pairType)

        # The label of an annotation is its name followed by its measurements. Only the angle value is
        # wanted, so the value becomes the name and the measurement is not printed after it. Which pair of
        # branches an annotation belongs to is told by its folder, its color and its attributes.
        angleNode.GetMeasurement("angle").SetPrintFormat("")
        angleNode.SetName(_("{angle:.1f}°").format(angle=junctionAngle["angleDegrees"]))

        displayNode = angleNode.GetDisplayNode()
        displayNode.SetSelectedColor(junctionAnglePairTypeColors[pairType])
        displayNode.SetPointLabelsVisibility(False)
        displayNode.SetPropertiesLabelVisibility(True)
        # A point glyph would only hide the vessel: the rays and the arc show where the angle is
        displayNode.SetGlyphType(slicer.vtkMRMLMarkupsDisplayNode.Vertex2D)
        displayNode.SetTextScale(junctionAngleTextScale)
        # An annotation is inside the vessel: without this it is hidden by an opaque surface
        displayNode.SetOccludedVisibility(True)
        displayNode.SetOccludedOpacity(occludedOpacity)
        # A measurement result, it must not be changed by moving a control point
        angleNode.SetLocked(True)
        self._reparentNodeToSubjectHierarchyFolderNode(parentFolderId, angleNode)
        return angleNode


class CenterlineJunctionAnglesLogic(ScriptedLoadableModuleLogic):
    def __init__(self) -> None:
        """
        Called when the logic class is instantiated. Can be used for initializing member variables.
        """
        ScriptedLoadableModuleLogic.__init__(self)
        self.clearCache()

    def clearCache(self):
        """Release cached input and measurements, including when the scene closes."""
        self._inputCenterline = None
        self._inputModificationTimes = None
        self._splitCenterlines = None
        self._bifurcationVectors = None

    @staticmethod
    def _modificationTimes(polyData):
        # Explicitly include connectivity: modifying a vtkCellArray does not necessarily
        # advance the polydata's own MTime. Point/cell data include their arrays' MTimes.
        objects = [polyData, polyData.GetPoints(), polyData.GetVerts(), polyData.GetLines(),
                   polyData.GetPolys(), polyData.GetStrips(), polyData.GetPointData(),
                   polyData.GetCellData(), polyData.GetFieldData()]
        return tuple(obj.GetMTime() if obj is not None else None for obj in objects)

    def splitCenterlines(self, inputCenterline: vtk.vtkPolyData):

        """Extract branches once per input revision, preserving VMTK's full-resolution result.

        Callers editing VTK arrays in place must mark those arrays Modified(), as required
        by the VTK pipeline. A different input or modified geometry/data invalidates both
        branch extraction and bifurcation-vector caches.
        """
        if not inputCenterline:
            self.clearCache()
            raise ValueError(_("Input centerline is invalid"))

        modificationTimes = self._modificationTimes(inputCenterline)
        if (self._inputCenterline is inputCenterline
                and self._inputModificationTimes == modificationTimes
                and self._splitCenterlines is not None):
            logging.info("Reusing cached centerline branch extraction")
            return self._splitCenterlines

        self.clearCache()
        startTime = time.perf_counter()
        logging.info("Centerline branch extraction started: %d points, %d cells",
                     inputCenterline.GetNumberOfPoints(), inputCenterline.GetNumberOfCells())
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
        self._inputCenterline = inputCenterline
        self._inputModificationTimes = self._modificationTimes(inputCenterline)
        logging.info("Centerline branch extraction completed in %.3f seconds", time.perf_counter() - startTime)
        return self._splitCenterlines

    def computeBifurcationVectors(self):
        """Compute the bifurcation reference systems and the bifurcation vectors of the centerline.
        This is the computation of the 'vmtkbifurcationreferencesystems' and 'vmtkbifurcationvectors'
        scripts of VMTK. For every branch that is adjacent to a bifurcation, the end of the branch group
        that is next to the bifurcation region is taken, and the branch is walked away from the
        bifurcation up to the center of the first maximum inscribed sphere that touches that end point.
        The bifurcation vector connects those two points, following the flow direction, therefore its
        length is of the order of the local vessel radius. Both ends are averages over the centerline
        tracts of the group, weighted by the square of the local radius.
        The result is cached until 'splitCenterlines()' is called again.
        :return: list of dicts, one for each bifurcation:
          {
            'bifurcationGroupId': the blanked group that represents the bifurcation,
            'position': origin of the bifurcation reference system, a radius weighted barycenter,
            'normal': normal of the bifurcation plane,
            'upNormal': direction from the parent branch towards the daughter branches,
            'branches': {groupId: {'groupId', 'role' ('Parent' or 'Child'), 'basePosition', 'vector',
                                   'outwardDirection', 'vectorLength', 'inPlaneAngleDegrees',
                                   'outOfPlaneAngleDegrees'}}
          }
          'outwardDirection' and the angles are given away from the bifurcation, which is the opposite of
          the stored vector for the parent branch. Angles are in degrees.
        """

        if self._bifurcationVectors is not None:
            return self._bifurcationVectors
        if not self._splitCenterlines:
            raise ValueError(_("Call 'splitCenterlines()' with an input centerline polydata first."))

        import time
        startTime = time.time()
        logging.info(_("Processing bifurcation vectors started: {points} points, {cells} cells").format(
                     points=self._splitCenterlines.GetNumberOfPoints(), cells=self._splitCenterlines.GetNumberOfCells()))

        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry

        referenceSystemsFilter = vtkvmtkComputationalGeometry.vtkvmtkCenterlineBifurcationReferenceSystems()
        referenceSystemsFilter.SetInputData(self._splitCenterlines)
        referenceSystemsFilter.SetRadiusArrayName(radiusArrayName)
        referenceSystemsFilter.SetGroupIdsArrayName(groupIdsArrayName)
        referenceSystemsFilter.SetBlankingArrayName(blankingArrayName)
        referenceSystemsFilter.SetNormalArrayName(normalArrayName)
        referenceSystemsFilter.SetUpNormalArrayName(upNormalArrayName)
        referenceSystemsFilter.Update()
        referenceSystems = referenceSystemsFilter.GetOutput()

        self._bifurcationVectors = []
        if (not referenceSystems) or (referenceSystems.GetNumberOfPoints() == 0):
            # The centerline does not have any bifurcation.
            return self._bifurcationVectors

        bifurcationVectorsFilter = vtkvmtkComputationalGeometry.vtkvmtkCenterlineBifurcationVectors()
        bifurcationVectorsFilter.SetInputData(self._splitCenterlines)
        bifurcationVectorsFilter.SetReferenceSystems(referenceSystems)
        bifurcationVectorsFilter.SetRadiusArrayName(radiusArrayName)
        bifurcationVectorsFilter.SetGroupIdsArrayName(groupIdsArrayName)
        bifurcationVectorsFilter.SetCenterlineIdsArrayName(centerlineIdsArrayName)
        bifurcationVectorsFilter.SetTractIdsArrayName(tractIdsArrayName)
        bifurcationVectorsFilter.SetBlankingArrayName(blankingArrayName)
        bifurcationVectorsFilter.SetReferenceSystemGroupIdsArrayName(groupIdsArrayName)
        bifurcationVectorsFilter.SetReferenceSystemNormalArrayName(normalArrayName)
        bifurcationVectorsFilter.SetReferenceSystemUpNormalArrayName(upNormalArrayName)
        bifurcationVectorsFilter.SetBifurcationVectorsArrayName(bifurcationVectorsArrayName)
        bifurcationVectorsFilter.SetInPlaneBifurcationVectorsArrayName(inPlaneBifurcationVectorsArrayName)
        bifurcationVectorsFilter.SetOutOfPlaneBifurcationVectorsArrayName(outOfPlaneBifurcationVectorsArrayName)
        bifurcationVectorsFilter.SetInPlaneBifurcationVectorAnglesArrayName(inPlaneBifurcationVectorAnglesArrayName)
        bifurcationVectorsFilter.SetOutOfPlaneBifurcationVectorAnglesArrayName(outOfPlaneBifurcationVectorAnglesArrayName)
        bifurcationVectorsFilter.SetBifurcationVectorsOrientationArrayName(bifurcationVectorsOrientationArrayName)
        bifurcationVectorsFilter.SetBifurcationGroupIdsArrayName(bifurcationGroupIdsArrayName)
        # The length of a vector tells over what distance the direction of a branch was determined.
        bifurcationVectorsFilter.SetNormalizeBifurcationVectors(0)
        bifurcationVectorsFilter.Update()
        bifurcationVectors = bifurcationVectorsFilter.GetOutput()
        if (not bifurcationVectors) or (bifurcationVectors.GetNumberOfPoints() == 0):
            return self._bifurcationVectors

        # One point of the reference systems for every bifurcation.
        bifurcationsByGroupId = {}
        referenceSystemPointData = referenceSystems.GetPointData()
        referenceSystemGroupIdsArray = referenceSystemPointData.GetArray(groupIdsArrayName)
        normalsArray = referenceSystemPointData.GetArray(normalArrayName)
        upNormalsArray = referenceSystemPointData.GetArray(upNormalArrayName)
        for pointId in range(referenceSystems.GetNumberOfPoints()):
            bifurcationGroupId = int(referenceSystemGroupIdsArray.GetTuple1(pointId))
            bifurcationsByGroupId[bifurcationGroupId] = {
                "bifurcationGroupId": bifurcationGroupId,
                "position": list(referenceSystems.GetPoint(pointId)),
                "normal": list(normalsArray.GetTuple3(pointId)) if normalsArray else [0.0, 0.0, 0.0],
                "upNormal": list(upNormalsArray.GetTuple3(pointId)) if upNormalsArray else [0.0, 0.0, 0.0],
                "branches": {},
                }

        # One point of the bifurcation vectors for every branch of every bifurcation.
        pointData = bifurcationVectors.GetPointData()
        groupIdsArray = pointData.GetArray(groupIdsArrayName)
        bifurcationGroupIdsArray = pointData.GetArray(bifurcationGroupIdsArrayName)
        orientationsArray = pointData.GetArray(bifurcationVectorsOrientationArrayName)
        vectorsArray = pointData.GetArray(bifurcationVectorsArrayName)
        inPlaneAnglesArray = pointData.GetArray(inPlaneBifurcationVectorAnglesArrayName)
        outOfPlaneAnglesArray = pointData.GetArray(outOfPlaneBifurcationVectorAnglesArrayName)
        if (not groupIdsArray) or (not bifurcationGroupIdsArray) or (not orientationsArray) or (not vectorsArray):
            raise ValueError(_("The bifurcation vectors are incomplete."))

        for pointId in range(bifurcationVectors.GetNumberOfPoints()):
            bifurcation = bifurcationsByGroupId.get(int(bifurcationGroupIdsArray.GetTuple1(pointId)))
            if bifurcation is None:
                continue
            # An upstream branch is the parent branch of the bifurcation.
            isUpstream = int(orientationsArray.GetTuple1(pointId)) == upstreamOrientation
            vector = list(vectorsArray.GetTuple3(pointId))
            vectorLength = vtk.vtkMath.Norm(vector)
            outwardDirection = [0.0, 0.0, 0.0]
            if vectorLength > minimumVectorLength:
                outwardDirection = [(-component if isUpstream else component) / vectorLength
                                    for component in vector]
            inPlaneAngleDegrees = math.degrees(inPlaneAnglesArray.GetTuple1(pointId)) if inPlaneAnglesArray else float("nan")
            outOfPlaneAngleDegrees = math.degrees(outOfPlaneAnglesArray.GetTuple1(pointId)) if outOfPlaneAnglesArray else float("nan")
            if isUpstream:
                inPlaneAngleDegrees = self.wrapAngleDegrees(inPlaneAngleDegrees + 180.0)
                outOfPlaneAngleDegrees = -outOfPlaneAngleDegrees
            groupId = int(groupIdsArray.GetTuple1(pointId))
            bifurcation["branches"][groupId] = {
                "groupId": groupId,
                "role": "Parent" if isUpstream else "Child",
                "basePosition": list(bifurcationVectors.GetPoint(pointId)),
                "vector": vector,
                "outwardDirection": outwardDirection,
                "vectorLength": vectorLength,
                "inPlaneAngleDegrees": inPlaneAngleDegrees,
                "outOfPlaneAngleDegrees": outOfPlaneAngleDegrees,
                "branchOrder": None,
                }

        self._bifurcationVectors = [bifurcationsByGroupId[bifurcationGroupId]
                                    for bifurcationGroupId in sorted(bifurcationsByGroupId.keys())
                                    if bifurcationsByGroupId[bifurcationGroupId]["branches"]]
        self.assignBranchOrders(self._bifurcationVectors)

        stopTime = time.time()
        durationValue = '%.2f' % (stopTime-startTime)
        logging.info(_("Processing bifurcation vectors completed in {duration} seconds").format(duration=durationValue))
        return self._bifurcationVectors

    @staticmethod
    def assignBranchOrders(bifurcations):
        """Assign branch orders from VMTK parent/child relationships.

        In each bifurcation, the children are one order distal to the parent.
        If a branch appears in several bifurcations, the lowest order found from
        the inlet side is used.
        """
        branchOrders = {}
        pendingEdges = []
        parentGroupIdsSet = set()
        childGroupIdsSet = set()
        for bifurcation in bifurcations:
            parentGroupIds = [branch["groupId"] for branch in bifurcation["branches"].values()
                              if branch["role"] == "Parent"]
            childGroupIds = [branch["groupId"] for branch in bifurcation["branches"].values()
                             if branch["role"] == "Child"]
            parentGroupIdsSet.update(parentGroupIds)
            childGroupIdsSet.update(childGroupIds)
            for parentGroupId in parentGroupIds:
                for childGroupId in childGroupIds:
                    pendingEdges.append((parentGroupId, childGroupId))

        for rootGroupId in parentGroupIdsSet - childGroupIdsSet:
            branchOrders[rootGroupId] = 0

        changed = True
        while changed:
            changed = False
            for parentGroupId, childGroupId in pendingEdges:
                if parentGroupId not in branchOrders:
                    continue
                childOrder = branchOrders[parentGroupId] + 1
                if childGroupId not in branchOrders or childOrder < branchOrders[childGroupId]:
                    branchOrders[childGroupId] = childOrder
                    changed = True

        for bifurcation in bifurcations:
            for branch in bifurcation["branches"].values():
                branch["branchOrder"] = branchOrders.get(branch["groupId"], 0)

    def processJunctionAngles(self):
        """Compute the angles between the branches that meet at each bifurcation.
        The direction of a branch is its bifurcation vector, oriented away from the bifurcation, so that
        the angle of a pair of branches is the angle between those two directions, in the [0, 180] range:
        180 degrees means that the two branches continue each other in a straight line. The angle
        projected onto the bifurcation plane and the angle of each branch with that plane are reported as
        well, as computed by VMTK. A bifurcation of degree n gives n*(n-1)/2 results, parent-child pairs
        first. A branch is identified by its GroupId, in the internally extracted branch groups.
        :return: list of dicts, one for each pair of branches of each bifurcation
        """

        junctionAngles = []
        bifurcations = self.computeBifurcationVectors()
        self.assignBranchOrders(bifurcations)
        for bifurcation in bifurcations:
            branches = [bifurcation["branches"][groupId] for groupId in sorted(bifurcation["branches"].keys())]
            # Parent branch first, so that a bifurcation gives parent-child, parent-child, child-child.
            branches.sort(key=lambda branch: (0 if branch["role"] == "Parent" else 1, branch["groupId"]))
            if len(branches) < 3:
                logging.warning(_("Skipping bifurcation {groupId}: it has {count} branches only.").format(
                                groupId=bifurcation["bifurcationGroupId"], count=len(branches)))
                continue
            for firstIndex in range(len(branches)):
                for secondIndex in range(firstIndex + 1, len(branches)):
                    branch1 = branches[firstIndex]
                    branch2 = branches[secondIndex]
                    junctionAngles.append({
                        "bifurcationGroupId": bifurcation["bifurcationGroupId"],
                        "junctionDegree": len(branches),
                        "junctionPosition": list(bifurcation["position"]),
                        "branch1GroupId": branch1["groupId"],
                        "branch2GroupId": branch2["groupId"],
                        "branch1Role": branch1["role"],
                        "branch2Role": branch2["role"],
                        "branch1Order": branch1["branchOrder"],
                        "branch2Order": branch2["branchOrder"],
                        "branchOrder": max(branch1["branchOrder"], branch2["branchOrder"]),
                        "angleDegrees": self.angleDegrees(branch1["outwardDirection"], branch2["outwardDirection"]),
                        "inPlaneAngleDegrees": abs(self.wrapAngleDegrees(
                            branch1["inPlaneAngleDegrees"] - branch2["inPlaneAngleDegrees"])),
                        "branch1OutOfPlaneAngleDegrees": branch1["outOfPlaneAngleDegrees"],
                        "branch2OutOfPlaneAngleDegrees": branch2["outOfPlaneAngleDegrees"],
                        # End points of the measured directions, for showing the angle in 3D views.
                        "branch1Position": [bifurcation["position"][i] + branch1["outwardDirection"][i] * branch1["vectorLength"]
                                            for i in range(3)],
                        "branch2Position": [bifurcation["position"][i] + branch2["outwardDirection"][i] * branch2["vectorLength"]
                                            for i in range(3)],
                        })
        return junctionAngles

    def populateJunctionAnglesTable(self, tableNode, junctionAngles):
        """Write junction angle results in a table node, one row for each pair of branches."""

        if not tableNode:
            raise ValueError(_("Output table node is invalid"))

        tableNode.RemoveAllColumns()
        results = junctionAngles if junctionAngles else []
        numberOfRows = len(results)

        def integerColumn(columnName):
            column = vtk.vtkIntArray()
            column.SetName(columnName)
            column.SetNumberOfValues(numberOfRows)
            return column

        def doubleColumn(columnName):
            column = vtk.vtkDoubleArray()
            column.SetName(columnName)
            column.SetNumberOfValues(numberOfRows)
            return column

        def stringColumn(columnName):
            column = vtk.vtkStringArray()
            column.SetName(columnName)
            column.SetNumberOfValues(numberOfRows)
            return column

        bifurcationGroupIds = integerColumn("BifurcationGroupId")
        junctionDegrees = integerColumn("JunctionDegree")
        branch1GroupIds = integerColumn("Branch1GroupId")
        branch2GroupIds = integerColumn("Branch2GroupId")
        branchOrders = integerColumn("BranchOrder")
        branch1Orders = integerColumn("Branch1Order")
        branch2Orders = integerColumn("Branch2Order")
        branch1Roles = stringColumn("Branch1Role")
        branch2Roles = stringColumn("Branch2Role")
        angles = doubleColumn("AngleDegrees")
        inPlaneAngles = doubleColumn("InPlaneAngleDegrees")
        branch1OutOfPlaneAngles = doubleColumn("Branch1OutOfPlaneAngleDegrees")
        branch2OutOfPlaneAngles = doubleColumn("Branch2OutOfPlaneAngleDegrees")

        junctionPositions = vtk.vtkDoubleArray()
        junctionPositions.SetName("JunctionPosition")
        junctionPositions.SetNumberOfComponents(3)
        junctionPositions.SetComponentName(0, "R")
        junctionPositions.SetComponentName(1, "A")
        junctionPositions.SetComponentName(2, "S")
        junctionPositions.SetNumberOfTuples(numberOfRows)

        for rowIndex in range(numberOfRows):
            junctionAngle = results[rowIndex]
            bifurcationGroupIds.SetValue(rowIndex, int(junctionAngle["bifurcationGroupId"]))
            junctionDegrees.SetValue(rowIndex, int(junctionAngle["junctionDegree"]))
            junctionPositions.SetTuple3(rowIndex, *junctionAngle["junctionPosition"])
            branch1GroupIds.SetValue(rowIndex, int(junctionAngle["branch1GroupId"]))
            branch2GroupIds.SetValue(rowIndex, int(junctionAngle["branch2GroupId"]))
            branchOrders.SetValue(rowIndex, int(junctionAngle["branchOrder"]))
            branch1Orders.SetValue(rowIndex, int(junctionAngle["branch1Order"]))
            branch2Orders.SetValue(rowIndex, int(junctionAngle["branch2Order"]))
            branch1Roles.SetValue(rowIndex, junctionAngle["branch1Role"])
            branch2Roles.SetValue(rowIndex, junctionAngle["branch2Role"])
            angles.SetValue(rowIndex, float(junctionAngle["angleDegrees"]))
            inPlaneAngles.SetValue(rowIndex, float(junctionAngle["inPlaneAngleDegrees"]))
            branch1OutOfPlaneAngles.SetValue(rowIndex, float(junctionAngle["branch1OutOfPlaneAngleDegrees"]))
            branch2OutOfPlaneAngles.SetValue(rowIndex, float(junctionAngle["branch2OutOfPlaneAngleDegrees"]))

        for column in [bifurcationGroupIds, junctionDegrees, junctionPositions,
                       branch1GroupIds, branch2GroupIds, branchOrders, branch1Orders, branch2Orders,
                       branch1Roles, branch2Roles,
                       angles, inPlaneAngles, branch1OutOfPlaneAngles, branch2OutOfPlaneAngles]:
            tableNode.GetTable().AddColumn(column)

        tableNode.SetColumnUnitLabel("JunctionPosition", "mm")
        for column in [angles, inPlaneAngles, branch1OutOfPlaneAngles, branch2OutOfPlaneAngles]:
            tableNode.SetColumnUnitLabel(column.GetName(), "deg")
        tableNode.SetColumnDescription("BifurcationGroupId", _("GroupId of the internally extracted bifurcation"))
        tableNode.SetColumnDescription("Branch1GroupId", _("GroupId of the first branch of the pair"))
        tableNode.SetColumnDescription("Branch2GroupId", _("GroupId of the second branch of the pair"))
        tableNode.SetColumnDescription("BranchOrder", _("Maximum branch order of the pair, used to group angle annotations"))
        tableNode.SetColumnDescription("Branch1Order", _("Branch order of the first branch of the pair"))
        tableNode.SetColumnDescription("Branch2Order", _("Branch order of the second branch of the pair"))
        tableNode.SetColumnDescription("AngleDegrees", _("Angle between the outward directions of the two"
                                                         " branches (180 degrees means that they continue"
                                                         " each other)"))
        tableNode.SetColumnDescription("InPlaneAngleDegrees", _("Angle of the pair projected onto the"
                                                                " bifurcation plane"))
        for columnName in ["Branch1OutOfPlaneAngleDegrees", "Branch2OutOfPlaneAngleDegrees"]:
            tableNode.SetColumnDescription(columnName, _("Angle between the branch and the bifurcation plane"))
        tableNode.GetTable().Modified()

    @staticmethod
    def junctionAnglePairType(branch1Role, branch2Role):
        """Type of a pair of branches: 'child-child', 'parent-child', or 'parent-parent'."""
        roles = [branch1Role, branch2Role]
        if roles == ["Child", "Child"]:
            return "child-child"
        if "Child" in roles:
            return "parent-child"
        return "parent-parent"

    @staticmethod
    def angleDegrees(vector1, vector2):
        """Angle between two vectors in degrees, in the [0, 180] range, nan for a vector of zero length."""
        norm1 = vtk.vtkMath.Norm(list(vector1))
        norm2 = vtk.vtkMath.Norm(list(vector2))
        if (norm1 <= 0.0) or (norm2 <= 0.0):
            return float("nan")
        # Clamp to compensate for numerical errors, acos fails outside [-1, 1].
        cosAngle = max(-1.0, min(1.0, vtk.vtkMath.Dot(list(vector1), list(vector2)) / (norm1 * norm2)))
        return math.degrees(math.acos(cosAngle))

    @staticmethod
    def wrapAngleDegrees(angleDegrees):
        """Wrap an angle to the (-180, 180] range."""
        if math.isnan(angleDegrees):
            return angleDegrees
        angleDegrees = math.fmod(angleDegrees, 360.0)
        if angleDegrees > 180.0:
            angleDegrees -= 360.0
        elif angleDegrees <= -180.0:
            angleDegrees += 360.0
        return angleDegrees


class CenterlineJunctionAnglesTest(ScriptedLoadableModuleTest):
    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        for test in [self.test_JunctionAngles, self.test_JunctionAnglesMultifurcation,
                     self.test_JunctionAnglesTable, self.test_JunctionAnglesOfAYShapedTube,
                     self.test_BranchExtractionCache, self.test_BranchOrderHierarchy]:
            self.setUp()
            test()

    def test_BranchExtractionCache(self):
        """Reuse unchanged input; invalidate on geometry, radius, connectivity, or input changes."""
        points = vtk.vtkPoints()
        lines = vtk.vtkCellArray()
        radius = vtk.vtkDoubleArray()
        radius.SetName(radiusArrayName)
        lines.InsertNextCell(5)
        for i in range(5):
            points.InsertNextPoint(0.0, float(i), 0.0)
            lines.InsertCellPoint(i)
            radius.InsertNextValue(0.5)
        polyData = vtk.vtkPolyData()
        polyData.SetPoints(points)
        polyData.SetLines(lines)
        polyData.GetPointData().AddArray(radius)
        logic = CenterlineJunctionAnglesLogic()
        split = logic.splitCenterlines(polyData)
        vectors = logic.computeBifurcationVectors()
        self.assertIs(logic.splitCenterlines(polyData), split)
        self.assertIs(logic.computeBifurcationVectors(), vectors)

        points.SetPoint(4, 0.0, 5.0, 0.0)
        points.Modified()
        changed = logic.splitCenterlines(polyData)
        self.assertIsNot(changed, split)
        self.assertIsNone(logic._bifurcationVectors)
        self.assertEqual(changed.GetPoint(changed.GetNumberOfPoints() - 1), (0.0, 5.0, 0.0))

        radius.SetValue(0, 0.75)
        radius.Modified()
        split = logic.splitCenterlines(polyData)
        self.assertIsNot(split, changed)
        self.assertEqual(split.GetPointData().GetArray(radiusArrayName).GetValue(0), 0.75)

        lines.Modified()
        changed = logic.splitCenterlines(polyData)
        self.assertIsNot(changed, split)
        otherInput = vtk.vtkPolyData()
        otherInput.DeepCopy(polyData)
        self.assertIsNot(logic.splitCenterlines(otherInput), changed)
        logic.clearCache()
        self.assertIsNone(logic._inputCenterline)
        self.assertIsNone(logic._splitCenterlines)
        self.assertIsNone(logic._bifurcationVectors)

    def test_BranchOrderHierarchy(self):
        """Branch orders follow parent-child relationships across bifurcations."""
        self.delayDisplay(_("Branch order hierarchy"))

        bifurcations = self.createBifurcationVectors()
        downstream = self.createBifurcationVectors(childAngles=(20.0, -20.0))
        downstream[0]["bifurcationGroupId"] = 5
        downstream[0]["branches"][2]["role"] = "Parent"
        downstream[0]["branches"][2]["inPlaneAngleDegrees"] = 180.0
        downstream[0]["branches"][4] = downstream[0]["branches"].pop(3)
        downstream[0]["branches"][4]["groupId"] = 4
        downstream[0]["branches"][5] = downstream[0]["branches"].pop(0)
        downstream[0]["branches"][5]["groupId"] = 5
        downstream[0]["branches"][5]["role"] = "Child"

        logic = CenterlineJunctionAnglesLogic()
        logic._bifurcationVectors = bifurcations + downstream
        junctionAngles = logic.processJunctionAngles()
        orderByPair = {(angle["bifurcationGroupId"], angle["branch1GroupId"], angle["branch2GroupId"]): angle["branchOrder"]
                       for angle in junctionAngles}
        self.assertEqual(orderByPair[(1, 0, 2)], 1)
        self.assertEqual(orderByPair[(5, 2, 4)], 2)
        self.assertEqual(orderByPair[(5, 2, 5)], 2)

        self.delayDisplay(_("Test passed"))

    @staticmethod
    def branchDirection(angleDegrees):
        """Unit direction in the RA plane, measured from the +A axis."""
        return [math.sin(math.radians(angleDegrees)), math.cos(math.radians(angleDegrees)), 0.0]

    @staticmethod
    def createBifurcationVectors(childAngles = (30.0, -40.0), vectorLength = 4.0):
        """Bifurcation vectors of a bifurcation whose branches have known directions.
        The parent branch points in the +A direction, the children leave at the given angles from it.
        The format is the one of CenterlineJunctionAnglesLogic.computeBifurcationVectors().
        """
        branches = {
            0: {
                "groupId": 0,
                "role": "Parent",
                "basePosition": [0.0, -vectorLength, 0.0],
                # VMTK stores the vector of the parent branch along the flow, towards the bifurcation
                "vector": [0.0, vectorLength, 0.0],
                "outwardDirection": [0.0, -1.0, 0.0],
                "vectorLength": vectorLength,
                "inPlaneAngleDegrees": 180.0,
                "outOfPlaneAngleDegrees": 0.0,
                },
            }
        for childIndex in range(len(childAngles)):
            groupId = childIndex + 2
            outwardDirection = CenterlineJunctionAnglesTest.branchDirection(childAngles[childIndex])
            branches[groupId] = {
                "groupId": groupId,
                "role": "Child",
                "basePosition": [0.0, 0.0, 0.0],
                "vector": [component * vectorLength for component in outwardDirection],
                "outwardDirection": outwardDirection,
                "vectorLength": vectorLength,
                "inPlaneAngleDegrees": childAngles[childIndex],
                "outOfPlaneAngleDegrees": 0.0,
                }
        return [{
            "bifurcationGroupId": 1,
            "position": [0.0, 0.0, 0.0],
            "normal": [0.0, 0.0, 1.0],
            "upNormal": [0.0, 1.0, 0.0],
            "branches": branches,
            }]

    @staticmethod
    def anglesByGroupIdPair(junctionAngles):
        return {(junctionAngle["branch1GroupId"], junctionAngle["branch2GroupId"]): junctionAngle["angleDegrees"]
                for junctionAngle in junctionAngles}

    def test_JunctionAngles(self):
        """Angles of a bifurcation whose branches have known directions."""
        self.delayDisplay(_("Junction angles of a bifurcation"))

        logic = CenterlineJunctionAnglesLogic()
        logic._bifurcationVectors = self.createBifurcationVectors()
        junctionAngles = logic.processJunctionAngles()

        # A bifurcation gives three pairs of branches, the parent-child pairs first
        self.assertEqual(len(junctionAngles), 3)
        self.assertEqual([(junctionAngle["branch1GroupId"], junctionAngle["branch2GroupId"])
                          for junctionAngle in junctionAngles], [(0, 2), (0, 3), (2, 3)])
        self.assertEqual([(junctionAngle["branch1Role"], junctionAngle["branch2Role"])
                          for junctionAngle in junctionAngles],
                         [("Parent", "Child"), ("Parent", "Child"), ("Child", "Child")])
        self.assertEqual([(junctionAngle["branch1Order"], junctionAngle["branch2Order"], junctionAngle["branchOrder"])
                          for junctionAngle in junctionAngles], [(0, 1, 1), (0, 1, 1), (1, 1, 1)])
        for junctionAngle in junctionAngles:
            self.assertEqual(junctionAngle["bifurcationGroupId"], 1)
            self.assertEqual(junctionAngle["junctionDegree"], 3)

        angles = self.anglesByGroupIdPair(junctionAngles)
        self.assertAlmostEqual(angles[(0, 2)], 150.0, delta=0.01)
        self.assertAlmostEqual(angles[(0, 3)], 140.0, delta=0.01)
        self.assertAlmostEqual(angles[(2, 3)], 70.0, delta=0.01)

        # The branches of this bifurcation are in one plane, so the in-plane angle is the same
        for junctionAngle in junctionAngles:
            self.assertAlmostEqual(junctionAngle["inPlaneAngleDegrees"], junctionAngle["angleDegrees"], delta=0.01)

        # The pair types drive the color and the name of the annotations
        self.assertEqual(logic.junctionAnglePairType("Parent", "Child"), "parent-child")
        self.assertEqual(logic.junctionAnglePairType("Child", "Child"), "child-child")
        # A direction cannot be determined from a vector of zero length
        self.assertTrue(math.isnan(logic.angleDegrees([0.0, 0.0, 0.0], [1.0, 0.0, 0.0])))

        self.delayDisplay(_("Test passed"))

    def test_JunctionAnglesMultifurcation(self):
        """A junction of degree n must give n*(n-1)/2 pairs of branches."""
        self.delayDisplay(_("Junction angles of a multifurcation"))

        logic = CenterlineJunctionAnglesLogic()
        logic._bifurcationVectors = self.createBifurcationVectors(childAngles = (45.0, 0.0, -45.0))
        junctionAngles = logic.processJunctionAngles()

        self.assertEqual(len(junctionAngles), 6)
        for junctionAngle in junctionAngles:
            self.assertEqual(junctionAngle["junctionDegree"], 4)
        pairTypes = [logic.junctionAnglePairType(junctionAngle["branch1Role"], junctionAngle["branch2Role"])
                     for junctionAngle in junctionAngles]
        self.assertEqual(pairTypes.count("parent-child"), 3)
        self.assertEqual(pairTypes.count("child-child"), 3)

        angles = self.anglesByGroupIdPair(junctionAngles)
        self.assertAlmostEqual(angles[(0, 2)], 135.0, delta=0.01)
        self.assertAlmostEqual(angles[(0, 3)], 180.0, delta=0.01)
        self.assertAlmostEqual(angles[(0, 4)], 135.0, delta=0.01)
        self.assertAlmostEqual(angles[(2, 3)], 45.0, delta=0.01)
        self.assertAlmostEqual(angles[(2, 4)], 90.0, delta=0.01)
        self.assertAlmostEqual(angles[(3, 4)], 45.0, delta=0.01)

        self.delayDisplay(_("Test passed"))

    def test_JunctionAnglesTable(self):
        """The results table must contain the results."""
        self.delayDisplay(_("Junction angles table"))

        logic = CenterlineJunctionAnglesLogic()
        logic._bifurcationVectors = self.createBifurcationVectors()
        junctionAngles = logic.processJunctionAngles()
        tableNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLTableNode", "Junction angles")
        logic.populateJunctionAnglesTable(tableNode, junctionAngles)

        table = tableNode.GetTable()
        self.assertEqual(table.GetNumberOfRows(), 3)
        self.assertEqual([table.GetColumnName(columnIndex) for columnIndex in range(table.GetNumberOfColumns())],
                         ["BifurcationGroupId", "JunctionDegree", "JunctionPosition",
                          "Branch1GroupId", "Branch2GroupId", "BranchOrder", "Branch1Order", "Branch2Order",
                          "Branch1Role", "Branch2Role",
                          "AngleDegrees", "InPlaneAngleDegrees",
                          "Branch1OutOfPlaneAngleDegrees", "Branch2OutOfPlaneAngleDegrees"])
        self.assertEqual(table.GetColumnByName("JunctionPosition").GetNumberOfComponents(), 3)
        for rowIndex in range(table.GetNumberOfRows()):
            junctionAngle = junctionAngles[rowIndex]
            self.assertEqual(table.GetValueByName(rowIndex, "BifurcationGroupId").ToInt(),
                             junctionAngle["bifurcationGroupId"])
            self.assertEqual(table.GetValueByName(rowIndex, "Branch1GroupId").ToInt(), junctionAngle["branch1GroupId"])
            self.assertEqual(table.GetValueByName(rowIndex, "Branch2GroupId").ToInt(), junctionAngle["branch2GroupId"])
            self.assertEqual(table.GetValueByName(rowIndex, "BranchOrder").ToInt(), junctionAngle["branchOrder"])
            self.assertEqual(table.GetValueByName(rowIndex, "Branch1Order").ToInt(), junctionAngle["branch1Order"])
            self.assertEqual(table.GetValueByName(rowIndex, "Branch2Order").ToInt(), junctionAngle["branch2Order"])
            self.assertEqual(table.GetValueByName(rowIndex, "Branch1Role").ToString(), junctionAngle["branch1Role"])
            self.assertAlmostEqual(table.GetValueByName(rowIndex, "AngleDegrees").ToDouble(),
                                   junctionAngle["angleDegrees"], places=9)

        # An empty result must clear the table
        logic.populateJunctionAnglesTable(tableNode, [])
        self.assertEqual(tableNode.GetTable().GetNumberOfRows(), 0)

        self.delayDisplay(_("Test passed"))

    @staticmethod
    def createTubeSurface(segments, spacing = 0.8, margin = 12.0):
        """Closed surface of a set of tubes, each segment given as (startPosition, endPosition, radius)."""
        import numpy as np
        from vtk.util import numpy_support

        def distanceToSegment(points, startPosition, endPosition):
            segmentVector = endPosition - startPosition
            ratios = np.clip(((points - startPosition) @ segmentVector) / (segmentVector @ segmentVector), 0.0, 1.0)
            return np.linalg.norm(points - (startPosition + ratios[:, None] * segmentVector), axis=1)

        segments = [(np.array(startPosition, dtype=float), np.array(endPosition, dtype=float), radius)
                    for startPosition, endPosition, radius in segments]
        endPositions = np.array([position for segment in segments for position in segment[:2]])
        maximumRadius = max(segment[2] for segment in segments)
        lowerBound = endPositions.min(axis=0) - maximumRadius - margin
        upperBound = endPositions.max(axis=0) + maximumRadius + margin
        dimensions = [int((upperBound[i] - lowerBound[i]) / spacing) for i in range(3)]
        grid = np.stack(np.meshgrid(*[lowerBound[i] + spacing * np.arange(dimensions[i]) for i in range(3)],
                                    indexing="ij"), axis=-1).reshape(-1, 3)
        values = np.full(grid.shape[0], 1e9)
        for startPosition, endPosition, radius in segments:
            values = np.minimum(values, distanceToSegment(grid, startPosition, endPosition) - radius)
        values = values.astype(np.float32).reshape(dimensions).transpose(2, 1, 0).ravel()

        imageData = vtk.vtkImageData()
        imageData.SetDimensions(*dimensions)
        imageData.SetOrigin(*lowerBound)
        imageData.SetSpacing(spacing, spacing, spacing)
        scalars = numpy_support.numpy_to_vtk(values, deep=True)
        scalars.SetName("Distance")
        imageData.GetPointData().SetScalars(scalars)
        marchingCubes = vtk.vtkMarchingCubes()
        marchingCubes.SetInputData(imageData)
        marchingCubes.SetValue(0, 0.0)
        smoother = vtk.vtkWindowedSincPolyDataFilter()
        smoother.SetInputConnection(marchingCubes.GetOutputPort())
        smoother.SetNumberOfIterations(20)
        smoother.NormalizeCoordinatesOn()
        smoother.Update()
        return smoother.GetOutput()

    def test_JunctionAnglesOfAYShapedTube(self):
        """The angles of a Y shaped tube must match the angles of the axes of the tubes."""
        self.delayDisplay(_("Junction angles of a Y shaped tube"))

        vesselRadius = 4.0
        junctionPosition = [0.0, 0.0, 0.0]
        inletPosition = [0.0, -40.0, 0.0]
        childEndPositions = [[component * 40.0 for component in self.branchDirection(angleDegrees)]
                             for angleDegrees in (30.0, -40.0)]
        surfacePolyData = self.createTubeSurface(
            [(inletPosition, junctionPosition, vesselRadius)]
            + [(junctionPosition, childEndPosition, vesselRadius) for childEndPosition in childEndPositions])

        # The input of this module is a centerline model of the 'Extract centerline' module
        import ExtractCenterline
        extractCenterlineLogic = ExtractCenterline.ExtractCenterlineLogic()
        endPointsMarkupsNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "Endpoints")
        endPointsMarkupsNode.AddControlPoint(vtk.vtkVector3d(inletPosition))
        for childEndPosition in childEndPositions:
            endPointsMarkupsNode.AddControlPoint(vtk.vtkVector3d(childEndPosition))
        # The inlet is the unselected control point, it gives the flow direction
        endPointsMarkupsNode.SetNthControlPointSelected(0, False)
        preprocessedPolyData = extractCenterlineLogic.preprocess(surfacePolyData, 8000, 4.0, False)
        centerlinePolyData = extractCenterlineLogic.extractCenterline(preprocessedPolyData,
                                                                      endPointsMarkupsNode, 1.0)[0]

        logic = CenterlineJunctionAnglesLogic()
        logic.splitCenterlines(centerlinePolyData)
        junctionAngles = logic.processJunctionAngles()

        self.assertEqual(len(junctionAngles), 3)
        self.assertEqual([(junctionAngle["branch1Role"], junctionAngle["branch2Role"])
                          for junctionAngle in junctionAngles],
                         [("Parent", "Child"), ("Parent", "Child"), ("Child", "Child")])

        # The bifurcation vectors follow each branch through the bifurcation, so the measured angles are
        # close to the angles of the axes of the tubes
        angles = self.anglesByGroupIdPair(junctionAngles)
        self.assertAlmostEqual(angles[(0, 2)], 150.0, delta=5.0)
        self.assertAlmostEqual(angles[(0, 3)], 140.0, delta=5.0)
        self.assertAlmostEqual(angles[(2, 3)], 70.0, delta=5.0)

        # The direction of a branch is determined over a distance of the order of the local vessel radius
        for bifurcation in logic.computeBifurcationVectors():
            for branch in bifurcation["branches"].values():
                self.assertAlmostEqual(branch["vectorLength"], vesselRadius, delta=0.5 * vesselRadius)

        # Reported IDs refer to the groups produced by internal branch extraction.
        groups = logic._splitCenterlines.GetCellData().GetArray(groupIdsArrayName)
        blanking = logic._splitCenterlines.GetCellData().GetArray(blankingArrayName)
        branchGroupIds = {int(groups.GetValue(i)) for i in range(groups.GetNumberOfTuples())
                          if not blanking.GetValue(i)}
        bifurcationGroupIds = {int(groups.GetValue(i)) for i in range(groups.GetNumberOfTuples())
                               if blanking.GetValue(i)}
        for angle in junctionAngles:
            self.assertIn(angle["branch1GroupId"], branchGroupIds)
            self.assertIn(angle["branch2GroupId"], branchGroupIds)
            self.assertIn(angle["bifurcationGroupId"], bifurcationGroupIds)

        self.delayDisplay(_("Test passed"))


blankingArrayName = 'Blanking'
radiusArrayName = 'Radius'  # maximum inscribed sphere radius
groupIdsArrayName = 'GroupIds'
centerlineIdsArrayName = 'CenterlineIds'
tractIdsArrayName = 'TractIds'
# Bifurcation reference systems and bifurcation vectors
normalArrayName = 'Normal'
upNormalArrayName = 'UpNormal'
bifurcationVectorsArrayName = 'BifurcationVectors'
inPlaneBifurcationVectorsArrayName = 'InPlaneBifurcationVectors'
outOfPlaneBifurcationVectorsArrayName = 'OutOfPlaneBifurcationVectors'
inPlaneBifurcationVectorAnglesArrayName = 'InPlaneBifurcationVectorAngles'
outOfPlaneBifurcationVectorAnglesArrayName = 'OutOfPlaneBifurcationVectorAngles'
bifurcationVectorsOrientationArrayName = 'BifurcationVectorsOrientation'
bifurcationGroupIdsArrayName = 'BifurcationGroupIds'
# A branch that is upstream of a bifurcation is its parent branch
upstreamOrientation = 0
# Vectors shorter than this, in mm, do not give a direction
minimumVectorLength = 1e-6
# Style of the junction angle annotations. The rays are drawn this many times longer than the measured
# segments, and the text is larger than the default scale of 3.0.
junctionAnglePairTypeColors = {"child-child": [1.0, 1.0, 0.0],
                               "parent-child": [0.0, 1.0, 1.0],
                               "parent-parent": [1.0, 1.0, 1.0]}
bifurcationVectorColor = [1.0, 0.5, 0.0]
junctionAngleRayScale = 3.0
junctionAngleTextScale = 5.0
# How much of an annotation is seen where the vessel surface hides it
occludedOpacity = 0.6
