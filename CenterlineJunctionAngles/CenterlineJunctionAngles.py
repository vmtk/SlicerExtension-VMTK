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
        self._branchOrderCheckboxes = {}
        ScriptedLoadableModuleWidget.__init__(self, parent)

    def setup(self):
        super().setup()
        self.logic = CenterlineJunctionAnglesLogic()
        uiWidget = slicer.util.loadUI(self.resourcePath("UI/CenterlineJunctionAngles.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)
        uiWidget.setMRMLScene(slicer.mrmlScene)
        self.ui.inputSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
        self.ui.showVectorNames.connect("toggled(bool)", self.updateParameterNodeFromGUI)
        self.ui.minimumAngleSpinBox.connect("valueChanged(double)", self.updateParameterNodeFromGUI)
        self.ui.applyButton.connect("clicked(bool)", self.onApplyButton)
        self.ui.filterButton.connect("clicked(bool)", self.onFilterButton)
        self.ui.showAllButton.connect("clicked(bool)", self.onShowAllButton)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
        for name in ("showArcs", "showAnnotations", "showRays", "showVectors", "showParentChild", "showChildChild"):
            getattr(self.ui, name).connect("toggled(bool)", self.onDisplayControlsChanged)
        for name in ("rayColorButton", "vectorColorButton"):
            getattr(self.ui, name).connect("colorChanged(QColor)", self.onDisplayControlsChanged)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndBatchProcessEvent, self.refreshBranchOrderControls)
        self.initializeParameterNode()
        self.refreshBranchOrderControls()

    def cleanup(self):
        self.removeObservers()

    def enter(self):
        self.initializeParameterNode()
        self.refreshBranchOrderControls()

    def onSceneStartClose(self, caller, event):
        self.setParameterNode(None)
        self.logic.clearCache()

    def onSceneEndClose(self, caller, event):
        if getattr(self.parent, "isEntered", False):
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
        blocked = self.ui.inputSelector.blockSignals(True)
        self.ui.inputSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputCenterline") if self._parameterNode else None)
        self.ui.inputSelector.blockSignals(blocked)
        blocked = self.ui.showVectorNames.blockSignals(True)
        self.ui.showVectorNames.checked = bool(self._parameterNode and self._parameterNode.GetParameter("ShowVectorNames") == "1")
        self.ui.showVectorNames.blockSignals(blocked)
        blocked = self.ui.minimumAngleSpinBox.blockSignals(True)
        if self._parameterNode and self._parameterNode.GetParameter("MinimumAngleDegrees"):
            self.ui.minimumAngleSpinBox.value = float(self._parameterNode.GetParameter("MinimumAngleDegrees"))
        self.ui.minimumAngleSpinBox.blockSignals(blocked)
        for name in ("showArcs", "showAnnotations", "showRays", "showVectors", "showParentChild", "showChildChild"):
            control = getattr(self.ui, name)
            blocked = control.blockSignals(True)
            control.checked = not self._parameterNode or self._parameterNode.GetParameter(name) != "0"
            control.blockSignals(blocked)
        for name, default in (("rayColorButton", junctionAngleGeometryColor), ("vectorColorButton", bifurcationVectorColor)):
            value = self._parameterNode.GetParameter(name) if self._parameterNode else ""
            color = [float(component) for component in value.split()] if value else default
            control = getattr(self.ui, name)
            blocked = control.blockSignals(True)
            control.color = qt.QColor.fromRgbF(*color)
            control.blockSignals(blocked)
        self.ui.applyButton.enabled = self.ui.inputSelector.currentNode() is not None

    def updateParameterNodeFromGUI(self, *args):
        if not self._parameterNode:
            return
        with slicer.util.NodeModify(self._parameterNode):
            node = self.ui.inputSelector.currentNode()
            self._parameterNode.SetNodeReferenceID("InputCenterline", node.GetID() if node else None)
            self._parameterNode.SetParameter("ShowVectorNames", "1" if self.ui.showVectorNames.checked else "0")
            self._parameterNode.SetParameter("MinimumAngleDegrees", str(self.ui.minimumAngleSpinBox.value))

    def annotationDisplayNodes(self):
        elements = {"CenterlineJunctionAngleArcs": "showArcs",
                    "CenterlineJunctionAngleLabels": "showAnnotations",
                    "CenterlineJunctionAngleRays": "showRays",
                    "CenterlineJunctionAngleVectors": "showVectors",
                    "CenterlineJunctionAngleVectorLabels": "showVectors"}
        for node in slicer.util.getNodesByClass("vtkMRMLDisplayableNode"):
            for attribute, control in elements.items():
                if node.GetAttribute(attribute) == "1":
                    yield node, control
                    break

    def refreshBranchOrderControls(self, caller=None, event=None):
        orders = sorted({int(node.GetAttribute("BranchOrder")) for node, _ in self.annotationDisplayNodes()
                         if node.GetAttribute("BranchOrder") is not None})
        for order in list(self._branchOrderCheckboxes):
            if order not in orders:
                checkbox = self._branchOrderCheckboxes.pop(order)
                self.ui.branchOrdersWidget.layout().removeWidget(checkbox)
                checkbox.deleteLater()
        hiddenOrders = self._parameterNode.GetParameter("HiddenBranchOrders").split() if self._parameterNode else []
        for order in orders:
            if order not in self._branchOrderCheckboxes:
                checkbox = qt.QCheckBox(_("Branch order {order}").format(order=order))
                self.ui.branchOrdersWidget.layout().insertWidget(orders.index(order), checkbox)
                self._branchOrderCheckboxes[order] = checkbox
                checkbox.connect("toggled(bool)", self.onDisplayControlsChanged)
            checkbox = self._branchOrderCheckboxes[order]
            blocked = checkbox.blockSignals(True)
            checkbox.checked = str(order) not in hiddenOrders
            checkbox.blockSignals(blocked)

    def onDisplayControlsChanged(self, *args):
        if self._parameterNode:
            with slicer.util.NodeModify(self._parameterNode):
                for name in ("showArcs", "showAnnotations", "showRays", "showVectors", "showParentChild", "showChildChild"):
                    self._parameterNode.SetParameter(name, "1" if getattr(self.ui, name).checked else "0")
                for name in ("rayColorButton", "vectorColorButton"):
                    color = getattr(self.ui, name).color
                    self._parameterNode.SetParameter(name, " ".join(str(value) for value in
                                                     (color.redF(), color.greenF(), color.blueF())))
                self._parameterNode.SetParameter("HiddenBranchOrders", " ".join(
                    str(order) for order, checkbox in self._branchOrderCheckboxes.items() if not checkbox.checked))
        self.applyDisplayControls()

    def applyDisplayControls(self):
        for node, control in self.annotationDisplayNodes():
            order = node.GetAttribute("BranchOrder")
            checkbox = self._branchOrderCheckboxes.get(int(order)) if order is not None else None
            pairControl = {"parent-child": "showParentChild", "child-child": "showChildChild"}.get(node.GetAttribute("PairType"))
            pairVisible = pairControl is None or getattr(self.ui, pairControl).checked
            node.GetDisplayNode().SetVisibility(
                getattr(self.ui, control).checked and (checkbox is None or checkbox.checked) and pairVisible)
            if control not in ("showRays", "showVectors"):
                continue
            qcolor = self.ui.rayColorButton.color if control == "showRays" else self.ui.vectorColorButton.color
            color = (qcolor.redF(), qcolor.greenF(), qcolor.blueF())
            display = node.GetDisplayNode()
            display.SetColor(color)
            if node.IsA("vtkMRMLMarkupsNode"):
                display.SetSelectedColor(color)
            if control == "showRays" and display.GetColorNode():
                colorNode = display.GetColorNode()
                for index in range(colorNode.GetNumberOfColors()):
                    colorNode.SetColor(index, "Ray", *color, 1.0)

    def onApplyButton(self):
        with slicer.util.tryWithErrorDisplay(_("Failed to compute junction angles."), waitCursor=True):
            inputCenterline = self.ui.inputSelector.currentNode()
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
                    self.updateProgress(progressDialog, _("Creating junction angle annotations..."), 80)
                    angleFolder = self._createCurveSubjectHierarchyFolderNode(label + _(" annotations"))
                    self._createJunctionAngleGroupComponents(
                        junctionAngles, self.logic.computeBifurcationVectors(), angleFolder, self.ui.showVectorNames.checked)
                finally:
                    slicer.mrmlScene.EndState(slicer.mrmlScene.BatchProcessState)
                self.refreshBranchOrderControls()
                self.applyDisplayControls()
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

    def onFilterButton(self):
        count = self.filterJunctionAngleAnnotations(self.ui.minimumAngleSpinBox.value)
        slicer.util.showStatusMessage(
            _("{count} junction angle annotations meet the threshold.").format(count=count), 3000)

    def onShowAllButton(self):
        count = self.filterJunctionAngleAnnotations(0.0)
        slicer.util.showStatusMessage(
            _("{count} junction angle annotations restored.").format(count=count), 3000)

    def filterJunctionAngleAnnotations(self, minimumAngleDegrees):
        """Hide labels, arcs, and rays below the threshold without changing colors or data."""
        count = 0
        for labelsNode in slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode"):
            if labelsNode.GetAttribute("CenterlineJunctionAngleLabels") != "1":
                continue
            for pointIndex in range(labelsNode.GetNumberOfControlPoints()):
                angleValue = labelsNode.GetNthControlPointDescription(pointIndex)
                if not angleValue:
                    continue
                visible = float(angleValue) >= minimumAngleDegrees
                labelsNode.SetNthControlPointVisibility(pointIndex, visible)
                count += int(visible)
        for model in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if (model.GetAttribute("CenterlineJunctionAngleArcs") != "1"
                    and model.GetAttribute("CenterlineJunctionAngleRays") != "1"):
                continue
            if model.GetPolyData().GetPointData().GetArray("AngleDegrees") is None:
                continue
            display = model.GetDisplayNode()
            display.SetThresholdRange(minimumAngleDegrees, 180.0)
            display.SetThresholdEnabled(minimumAngleDegrees > 0.0)
        return count

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

    def _createPolylineModel(self, name, polylines, color, parentFolderId, lineWidth=2, attributes=None, pointsToShow=None, pointSize=1):
        if not polylines:
            return None
        points = vtk.vtkPoints()
        lines = vtk.vtkCellArray()
        vertices = vtk.vtkCellArray()
        polyData = vtk.vtkPolyData()
        for polyline in polylines:
            lines.InsertNextCell(len(polyline))
            for position in polyline:
                pointId = points.InsertNextPoint(position)
                lines.InsertCellPoint(pointId)
        for position in pointsToShow or []:
            pointId = points.InsertNextPoint(position)
            vertices.InsertNextCell(1)
            vertices.InsertCellPoint(pointId)
        polyData.SetPoints(points)
        polyData.SetLines(lines)
        if pointsToShow:
            polyData.SetVerts(vertices)
        modelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", name)
        modelNode.SetAndObservePolyData(polyData)
        modelNode.CreateDefaultDisplayNodes()
        displayNode = modelNode.GetDisplayNode()
        displayNode.SetColor(color)
        displayNode.SetLineWidth(lineWidth)
        displayNode.SetPointSize(pointSize)
        displayNode.SetScalarVisibility(False)
        displayNode.SetVisibility2D(True)
        modelNode.SetAttribute("CenterlineJunctionAngles", "1")
        if attributes:
            for attributeName, attributeValue in attributes.items():
                modelNode.SetAttribute(attributeName, str(attributeValue))
        self._reparentNodeToSubjectHierarchyFolderNode(parentFolderId, modelNode)
        return modelNode

    def _createTubeModel(self, name, polylines, sphereCenters, color, parentFolderId, tubeRadius, sphereRadius, attributes=None, opacity=1.0, angleDegrees=None, colorByAngle=True, scalarRange=(0.0, 180.0)):
        if not polylines:
            return None

        points = vtk.vtkPoints()
        lines = vtk.vtkCellArray()
        centerlines = vtk.vtkPolyData()
        angleScalars = None
        if angleDegrees is not None:
            if len(angleDegrees) != len(polylines) or sphereCenters:
                raise ValueError("Angle scalars require one value per polyline and no spheres")
            angleScalars = vtk.vtkDoubleArray()
            angleScalars.SetName("AngleDegrees")
        for polylineIndex, polyline in enumerate(polylines):
            lines.InsertNextCell(len(polyline))
            for position in polyline:
                pointId = points.InsertNextPoint(position)
                lines.InsertCellPoint(pointId)
                if angleScalars is not None:
                    angleScalars.InsertNextValue(angleDegrees[polylineIndex])
        if angleScalars is not None:
            centerlines.GetPointData().SetScalars(angleScalars)
        centerlines.SetPoints(points)
        centerlines.SetLines(lines)

        tube = vtk.vtkTubeFilter()
        tube.SetInputData(centerlines)
        tube.SetRadius(tubeRadius)
        tube.SetVaryRadiusToVaryRadiusOff()
        tube.SetNumberOfSides(12)
        tube.CappingOn()
        tube.Update()

        append = vtk.vtkAppendPolyData()
        append.AddInputData(tube.GetOutput())
        for center in sphereCenters:
            sphere = vtk.vtkSphereSource()
            sphere.SetCenter(center)
            sphere.SetRadius(sphereRadius)
            sphere.SetThetaResolution(12)
            sphere.SetPhiResolution(12)
            sphere.Update()
            append.AddInputData(sphere.GetOutput())
        append.Update()

        modelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", name)
        modelNode.SetAndObservePolyData(append.GetOutput())
        modelNode.CreateDefaultDisplayNodes()
        displayNode = modelNode.GetDisplayNode()
        displayNode.SetColor(color)
        displayNode.SetOpacity(opacity)
        displayNode.SetScalarVisibility(angleScalars is not None)
        if angleScalars is not None:
            displayNode.SetActiveScalar("AngleDegrees", vtk.vtkAssignAttribute.POINT_DATA)
            if colorByAngle:
                displayNode.SetLighting(True)
                displayNode.SetAndObserveColorNodeID("vtkMRMLColorTableNodeFilePlasma.txt")
            else:
                # Slicer model thresholding requires scalar visibility. A constant
                # lookup table keeps the rays yellow while allowing them to be filtered.
                colorNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLColorTableNode", "Junction angle ray color")
                colorNode.SetTypeToUser()
                colorNode.SetNumberOfColors(2)
                colorNode.SetColor(0, "Ray", *color, 1.0)
                colorNode.SetColor(1, "Ray", *color, 1.0)
                colorNode.SetHideFromEditors(True)
                displayNode.SetAndObserveColorNodeID(colorNode.GetID())
            displayNode.SetScalarRangeFlag(displayNode.UseManualScalarRange)
            displayNode.SetScalarRange(*scalarRange)
        displayNode.SetVisibility2D(True)
        modelNode.SetAttribute("CenterlineJunctionAngles", "1")
        if attributes:
            for attributeName, attributeValue in attributes.items():
                modelNode.SetAttribute(attributeName, str(attributeValue))
        self._reparentNodeToSubjectHierarchyFolderNode(parentFolderId, modelNode)
        return modelNode

    def _createLabelsNode(self, name, labels, color, parentFolderId, attributes=None):
        if not labels:
            return None
        labelsNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", name)
        labelsNode.CreateDefaultDisplayNodes()
        displayNode = labelsNode.GetDisplayNode()
        displayNode.SetColor(color)
        displayNode.SetSelectedColor(color)
        displayNode.SetGlyphType(slicer.vtkMRMLMarkupsDisplayNode.Vertex2D)
        displayNode.SetGlyphScale(0.0)
        displayNode.SetTextScale(junctionAngleTextScale)
        displayNode.GetTextProperty().ShadowOn()
        displayNode.SetPointLabelsVisibility(True)
        displayNode.SetPropertiesLabelVisibility(False)
        displayNode.SetOccludedVisibility(True)
        displayNode.SetOccludedOpacity(occludedOpacity)
        for position, label, description in labels:
            pointIndex = labelsNode.AddControlPoint(vtk.vtkVector3d(position))
            labelsNode.SetNthControlPointLabel(pointIndex, label)
            labelsNode.SetNthControlPointDescription(pointIndex, description)
            labelsNode.SetNthControlPointSelected(pointIndex, False)
        labelsNode.SetLocked(True)
        labelsNode.SetAttribute("CenterlineJunctionAngles", "1")
        if attributes:
            for attributeName, attributeValue in attributes.items():
                labelsNode.SetAttribute(attributeName, str(attributeValue))
        self._reparentNodeToSubjectHierarchyFolderNode(parentFolderId, labelsNode)
        return labelsNode

    def _createBifurcationVectorModel(self, branches, parentFolderId, showLabels, branchOrder, pairType):
        polylines = []
        vectorPoints = []
        labels = []
        for branch in branches:
            if branch["vectorLength"] <= minimumVectorLength:
                continue
            basePosition = branch["basePosition"]
            endPosition = [basePosition[i] + branch["vector"][i] for i in range(3)]
            polylines.append([basePosition, endPosition])
            vectorPoints.extend([basePosition, endPosition])
            if showLabels:
                labels.append(([(basePosition[i] + endPosition[i]) / 2.0 for i in range(3)],
                               _("Group {groupId}").format(groupId=branch["groupId"]),
                               str(branch["groupId"])))
        self._createTubeModel(_("Bifurcation vectors"), polylines, vectorPoints, bifurcationVectorColor, parentFolderId,
                              bifurcationVectorTubeRadius, bifurcationVectorEndpointRadius,
                              {"CenterlineJunctionAngleVectors": "1", "BranchOrder": branchOrder, "PairType": pairType}, bifurcationVectorOpacity)
        self._createLabelsNode(_("Bifurcation vector labels"), labels, bifurcationVectorColor, parentFolderId,
                               {"CenterlineJunctionAngleVectorLabels": "1", "BranchOrder": branchOrder, "PairType": pairType})

    @staticmethod
    def _rayEndPosition(junctionAngle, positionKey, minimumLength=0.0):
        junctionPosition = junctionAngle["junctionPosition"]
        position = junctionAngle[positionKey]
        direction = [position[i] - junctionPosition[i] for i in range(3)]
        length = vtk.vtkMath.Norm(direction)
        scale = max(junctionAngleRayScale, minimumLength / length) if length > minimumVectorLength else junctionAngleRayScale
        return [junctionPosition[i] + direction[i] * scale for i in range(3)]

    @staticmethod
    def _angleArcPolyline(junctionAngle, numberOfSegments=24, radius=None):
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
        if radius is None:
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

    @staticmethod
    def _bifurcationBranchesByGroupId(bifurcations):
        branchesByGroupId = {}
        for bifurcation in bifurcations:
            for branch in bifurcation["branches"].values():
                branchesByGroupId[(bifurcation["bifurcationGroupId"], branch["groupId"])] = branch
        return branchesByGroupId

    def _junctionArcRadii(self, junctionAngles):
        """Assign stable, distinct radii across all pairs at each junction."""
        anglesByJunction = {}
        for angle in junctionAngles:
            if not math.isfinite(angle["angleDegrees"]):
                raise ValueError(_("Cannot display a non-finite junction angle."))
            anglesByJunction.setdefault(angle["bifurcationGroupId"], []).append(angle)
        radii = {}
        for junctionId, angles in anglesByJunction.items():
            angles = sorted(angles, key=lambda angle: (angle["branch1GroupId"], angle["branch2GroupId"]))
            rayLengths = [math.dist(angle["junctionPosition"], self._rayEndPosition(angle, positionKey))
                          for angle in angles for positionKey in ("branch1Position", "branch2Position")]
            positiveLengths = [length for length in rayLengths if length > minimumVectorLength]
            if not positiveLengths:
                continue
            # Use one length for the whole junction: unequal branch lengths must
            # not bring arcs assigned to different radial levels together again.
            referenceLength = min(positiveLengths)
            for index, angle in enumerate(angles):
                fraction = 0.35 + 0.30 * index
                radii[(junctionId, angle["branch1GroupId"], angle["branch2GroupId"])] = referenceLength * fraction
        return radii

    def _createJunctionAngleGroupComponents(self, junctionAngles, bifurcations, parentFolderId, showVectorLabels):
        labels = {"child-child": _("Child-child angles"), "parent-child": _("Parent-child angles"), "parent-parent": _("Parent-parent angles")}
        folders = {}
        groupedAnnotations = {}
        angleValues = [angle["angleDegrees"] for angle in junctionAngles]
        if not angleValues:
            return
        if not all(math.isfinite(value) for value in angleValues):
            raise ValueError(_("Cannot display a non-finite junction angle."))
        scalarRange = (min(angleValues), max(angleValues))
        if scalarRange[0] == scalarRange[1]:
            # Keep the lookup table well-defined when every measurement is equal.
            scalarRange = (max(0.0, scalarRange[0] - 0.5), min(180.0, scalarRange[1] + 0.5))
        branchesByGroupId = self._bifurcationBranchesByGroupId(bifurcations)
        arcRadii = self._junctionArcRadii(junctionAngles)
        for junctionAngle in junctionAngles:
            pairType = self.logic.junctionAnglePairType(junctionAngle["branch1Role"], junctionAngle["branch2Role"])
            if pairType not in folders:
                folders[pairType] = self._createCurveSubjectHierarchyFolderNode(labels[pairType], parentFolderId)
            branchOrder = junctionAngle["branchOrder"]
            groupKey = (pairType, branchOrder)
            if groupKey not in folders:
                folders[groupKey] = self._createCurveSubjectHierarchyFolderNode(
                    _("Branch order {order}").format(order=branchOrder), folders[pairType])
            groupedAnnotations.setdefault(groupKey, {"rays": [], "arcs": [], "angleDegrees": [], "rayAngleDegrees": [], "labels": [], "vectorGroupIds": set()})
            arcKey = (junctionAngle["bifurcationGroupId"], junctionAngle["branch1GroupId"], junctionAngle["branch2GroupId"])
            arcRadius = arcRadii.get(arcKey)
            minimumRayLength = 1.1 * arcRadius if arcRadius is not None else 0.0
            ray1EndPosition = self._rayEndPosition(junctionAngle, "branch1Position", minimumRayLength)
            ray2EndPosition = self._rayEndPosition(junctionAngle, "branch2Position", minimumRayLength)
            groupedAnnotations[groupKey]["rays"].append([ray1EndPosition, junctionAngle["junctionPosition"], ray2EndPosition])
            groupedAnnotations[groupKey]["rayAngleDegrees"].append(junctionAngle["angleDegrees"])
            arcPolyline, labelPosition = self._angleArcPolyline(junctionAngle, radius=arcRadius)
            if arcPolyline:
                groupedAnnotations[groupKey]["arcs"].append(arcPolyline)
                groupedAnnotations[groupKey]["angleDegrees"].append(junctionAngle["angleDegrees"])
            groupedAnnotations[groupKey]["labels"].append((labelPosition, _("{angle:.1f}°").format(
                angle=junctionAngle["angleDegrees"]), str(junctionAngle["angleDegrees"])))
            bifurcationGroupId = junctionAngle["bifurcationGroupId"]
            groupedAnnotations[groupKey]["vectorGroupIds"].add((bifurcationGroupId, junctionAngle["branch1GroupId"]))
            groupedAnnotations[groupKey]["vectorGroupIds"].add((bifurcationGroupId, junctionAngle["branch2GroupId"]))

        for groupKey, annotations in groupedAnnotations.items():
            pairType, branchOrder = groupKey
            folder = folders[groupKey]
            nameSuffix = _("branch order {order}").format(order=branchOrder)
            self._createTubeModel(_("Junction angle rays - {suffix}").format(suffix=nameSuffix),
                                  annotations["rays"], [], junctionAngleGeometryColor, folder, junctionAngleTubeRadius, 0.0,
                                  {"CenterlineJunctionAngleRays": "1",
                                   "PairType": pairType,
                                   "BranchOrder": branchOrder},
                                  angleDegrees=annotations["rayAngleDegrees"], colorByAngle=False)
            self._createTubeModel(_("Junction angle arcs - {suffix}").format(suffix=nameSuffix),
                                  annotations["arcs"], [], junctionAngleGeometryColor, folder, junctionAngleTubeRadius, 0.0,
                                  {"CenterlineJunctionAngleArcs": "1",
                                   "PairType": pairType,
                                   "BranchOrder": branchOrder}, angleDegrees=annotations["angleDegrees"], scalarRange=scalarRange)
            # Markups colors apply to a whole node. Group labels by lookup-table
            # color to match the arcs without creating a node for every measurement.
            lookupTable = vtk.vtkLookupTable()
            lookupTable.DeepCopy(slicer.mrmlScene.GetNodeByID("vtkMRMLColorTableNodeFilePlasma.txt").GetLookupTable())
            lookupTable.SetRange(*scalarRange)
            labelsByColor = {}
            for label in annotations["labels"]:
                color = [0.0, 0.0, 0.0]
                lookupTable.GetColor(float(label[2]), color)
                labelsByColor.setdefault(tuple(color), []).append(label)
            for color, colorLabels in labelsByColor.items():
                self._createLabelsNode(_("Junction angle labels - {suffix}").format(suffix=nameSuffix),
                                       colorLabels, color, folder,
                                       {"CenterlineJunctionAngleLabels": "1",
                                        "PairType": pairType,
                                        "BranchOrder": branchOrder})
            vectorBranches = [branchesByGroupId[groupId] for groupId in sorted(annotations["vectorGroupIds"])
                              if groupId in branchesByGroupId]
            self._createBifurcationVectorModel(vectorBranches, folder, showVectorLabels, branchOrder, pairType)


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
        if inputCenterline.GetNumberOfPoints() == 0 or inputCenterline.GetNumberOfCells() == 0:
            self.clearCache()
            raise ValueError(_("Input centerline is empty."))
        radiusArray = inputCenterline.GetPointData().GetArray(radiusArrayName)
        if radiusArray is None or radiusArray.GetNumberOfTuples() != inputCenterline.GetNumberOfPoints():
            self.clearCache()
            raise ValueError(_("Input centerline is missing the required '{name}' point data array.").format(name=radiusArrayName))
        for pointIndex in range(inputCenterline.GetNumberOfPoints()):
            position = inputCenterline.GetPoint(pointIndex)
            radius = radiusArray.GetTuple1(pointIndex)
            if (not all(math.isfinite(value) for value in position)
                    or not math.isfinite(radius) or radius <= 0.0):
                self.clearCache()
                raise ValueError(_("Input centerline contains invalid geometry or radius values."))

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

        if referenceSystems is None:
            raise ValueError(_("VMTK did not produce bifurcation reference systems."))
        if referenceSystems.GetNumberOfPoints() == 0:
            # A valid centerline may have no bifurcations.
            self._bifurcationVectors = []
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
        if bifurcationVectors is None or bifurcationVectors.GetNumberOfPoints() == 0:
            raise ValueError(_("VMTK found bifurcations but did not produce their branch vectors."))

        bifurcations = self._readBifurcationVectors(referenceSystems, bifurcationVectors)
        self.assignBranchOrders(bifurcations)
        self._bifurcationVectors = bifurcations
        logging.info("Processing bifurcation vectors completed in %.2f seconds", time.time() - startTime)
        return self._bifurcationVectors

    def _readBifurcationVectors(self, referenceSystems, bifurcationVectors):
        """Validate VMTK outputs before publishing or caching measurement results."""
        def requiredArray(polyData, name, components):
            array = polyData.GetPointData().GetArray(name)
            if (array is None or array.GetNumberOfComponents() != components
                    or array.GetNumberOfTuples() != polyData.GetNumberOfPoints()):
                raise ValueError(_("Missing or invalid VMTK array '{name}'.").format(name=name))
            return array

        # One point of the reference systems for every bifurcation.
        bifurcationsByGroupId = {}
        referenceSystemGroupIdsArray = requiredArray(referenceSystems, groupIdsArrayName, 1)
        normalsArray = requiredArray(referenceSystems, normalArrayName, 3)
        upNormalsArray = requiredArray(referenceSystems, upNormalArrayName, 3)
        for pointId in range(referenceSystems.GetNumberOfPoints()):
            bifurcationGroupId = int(referenceSystemGroupIdsArray.GetTuple1(pointId))
            position = list(referenceSystems.GetPoint(pointId))
            normal = list(normalsArray.GetTuple3(pointId))
            upNormal = list(upNormalsArray.GetTuple3(pointId))
            if (not all(math.isfinite(value) for value in position + normal + upNormal)
                    or vtk.vtkMath.Norm(normal) <= minimumVectorLength
                    or vtk.vtkMath.Norm(upNormal) <= minimumVectorLength):
                raise ValueError(_("Invalid reference system at bifurcation {groupId}.").format(groupId=bifurcationGroupId))
            bifurcationsByGroupId[bifurcationGroupId] = {
                "bifurcationGroupId": bifurcationGroupId,
                "position": position,
                "normal": normal,
                "upNormal": upNormal,
                "branches": {},
                }

        # One point of the bifurcation vectors for every branch of every bifurcation.
        groupIdsArray = requiredArray(bifurcationVectors, groupIdsArrayName, 1)
        bifurcationGroupIdsArray = requiredArray(bifurcationVectors, bifurcationGroupIdsArrayName, 1)
        orientationsArray = requiredArray(bifurcationVectors, bifurcationVectorsOrientationArrayName, 1)
        vectorsArray = requiredArray(bifurcationVectors, bifurcationVectorsArrayName, 3)
        inPlaneAnglesArray = requiredArray(bifurcationVectors, inPlaneBifurcationVectorAnglesArrayName, 1)
        outOfPlaneAnglesArray = requiredArray(bifurcationVectors, outOfPlaneBifurcationVectorAnglesArrayName, 1)

        for pointId in range(bifurcationVectors.GetNumberOfPoints()):
            bifurcation = bifurcationsByGroupId.get(int(bifurcationGroupIdsArray.GetTuple1(pointId)))
            if bifurcation is None:
                raise ValueError(_("A bifurcation vector has no matching reference system."))
            # An upstream branch is the parent branch of the bifurcation.
            isUpstream = int(orientationsArray.GetTuple1(pointId)) == upstreamOrientation
            vector = list(vectorsArray.GetTuple3(pointId))
            vectorLength = vtk.vtkMath.Norm(vector)
            groupId = int(groupIdsArray.GetTuple1(pointId))
            if not all(math.isfinite(value) for value in vector) or not math.isfinite(vectorLength) or vectorLength <= minimumVectorLength:
                logging.warning(_("Skipping branch {branchId} at bifurcation {bifurcationId}: VMTK did not produce a valid direction.").format(
                    branchId=groupId, bifurcationId=bifurcation["bifurcationGroupId"]))
                continue
            outwardDirection = [(-component if isUpstream else component) / vectorLength for component in vector]
            inPlaneAngleDegrees = math.degrees(inPlaneAnglesArray.GetTuple1(pointId))
            outOfPlaneAngleDegrees = math.degrees(outOfPlaneAnglesArray.GetTuple1(pointId))
            basePosition = list(bifurcationVectors.GetPoint(pointId))
            if not all(math.isfinite(value) for value in basePosition + [inPlaneAngleDegrees, outOfPlaneAngleDegrees]):
                logging.warning(_("Skipping branch {branchId} at bifurcation {bifurcationId}: VMTK did not produce a valid position or projected angle.").format(
                    branchId=groupId, bifurcationId=bifurcation["bifurcationGroupId"]))
                continue
            if isUpstream:
                inPlaneAngleDegrees = self.wrapAngleDegrees(inPlaneAngleDegrees + 180.0)
                outOfPlaneAngleDegrees = -outOfPlaneAngleDegrees
            bifurcation["branches"][groupId] = {
                "groupId": groupId,
                "role": "Parent" if isUpstream else "Child",
                "basePosition": basePosition,
                "vector": vector,
                "outwardDirection": outwardDirection,
                "vectorLength": vectorLength,
                "inPlaneAngleDegrees": inPlaneAngleDegrees,
                "outOfPlaneAngleDegrees": outOfPlaneAngleDegrees,
                "branchOrder": None,
                }

        for bifurcation in bifurcationsByGroupId.values():
            if len(bifurcation["branches"]) < 3:
                logging.warning(_("Skipping bifurcation {groupId}: it has fewer than three valid branch vectors.").format(
                    groupId=bifurcation["bifurcationGroupId"]))
        return [bifurcationsByGroupId[groupId] for groupId in sorted(bifurcationsByGroupId)
                if len(bifurcationsByGroupId[groupId]["branches"]) >= 3]

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
                logging.warning(_("Skipping bifurcation {groupId}: it has fewer than three valid branches.").format(
                    groupId=bifurcation["bifurcationGroupId"]))
                continue
            if not all(math.isfinite(value) for value in bifurcation["position"]):
                raise ValueError(_("Invalid position at bifurcation {groupId}.").format(groupId=bifurcation["bifurcationGroupId"]))
            for branch in branches:
                direction = branch["outwardDirection"]
                values = list(direction) + [branch["vectorLength"], branch["inPlaneAngleDegrees"], branch["outOfPlaneAngleDegrees"]]
                if (not all(math.isfinite(value) for value in values)
                        or vtk.vtkMath.Norm(direction) <= minimumVectorLength
                        or branch["vectorLength"] <= minimumVectorLength):
                    raise ValueError(_("Invalid cached direction or projected angle for branch {branchId} at bifurcation {bifurcationId}.").format(
                        branchId=branch["groupId"], bifurcationId=bifurcation["bifurcationGroupId"]))
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
                        "angleDegrees": math.degrees(vtk.vtkMath.AngleBetweenVectors(branch1["outwardDirection"], branch2["outwardDirection"])),
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
    def wrapAngleDegrees(angleDegrees):
        """Wrap an angle to the (-180, 180] range."""
        if not math.isfinite(angleDegrees):
            raise ValueError(_("Cannot wrap a non-finite angle."))
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
                     self.test_BifurcationVectorValidation,
                     self.test_BranchExtractionCache, self.test_BranchOrderHierarchy,
                     self.test_ArcScalars, self.test_DisplayControls, self.test_AngleColorRange, self.test_StaggeredArcs]:
            self.setUp()
            test()

    def test_DisplayControls(self):
        """Element/order visibility composes with thresholding, and colors update in place."""
        import os
        widget = CenterlineJunctionAnglesWidget()
        widget.resourcePath = lambda name: os.path.join(os.path.dirname(__file__), "Resources", name)
        widget.setup()
        try:
            self.assertTrue(widget.ui.displayOptionsCollapsibleButton.collapsed)
            bifurcations = self.createBifurcationVectors()
            widget.logic._bifurcationVectors = bifurcations
            angles = widget.logic.processJunctionAngles()
            angles[0]["branchOrder"] = 2
            folder = widget._createCurveSubjectHierarchyFolderNode("Display controls test")
            widget._createJunctionAngleGroupComponents(angles, bifurcations, folder, True)
            widget.refreshBranchOrderControls()
            widget.applyDisplayControls()
            self.assertEqual(set(widget._branchOrderCheckboxes), {1, 2})
            nodes = list(widget.annotationDisplayNodes())
            self.assertTrue(nodes)
            for control in ("showArcs", "showAnnotations", "showRays", "showVectors"):
                getattr(widget.ui, control).checked = False
                for node, element in nodes:
                    self.assertEqual(bool(node.GetDisplayNode().GetVisibility()), element != control)
                getattr(widget.ui, control).checked = True
            self.assertEqual({node.GetAttribute("PairType") for node, _ in nodes}, {"parent-child", "child-child"})
            for pairType, pairControl in (("parent-child", "showParentChild"), ("child-child", "showChildChild")):
                getattr(widget.ui, pairControl).checked = False
                for node, _ in nodes:
                    self.assertEqual(bool(node.GetDisplayNode().GetVisibility()), node.GetAttribute("PairType") != pairType)
                self.assertEqual(widget._parameterNode.GetParameter(pairControl), "0")
                widget.updateGUIFromParameterNode()
                self.assertFalse(getattr(widget.ui, pairControl).checked)
                getattr(widget.ui, pairControl).checked = True
            widget._branchOrderCheckboxes[1].checked = False
            for node, _ in nodes:
                self.assertEqual(bool(node.GetDisplayNode().GetVisibility()), node.GetAttribute("BranchOrder") == "2")
            widget.filterJunctionAngleAnnotations(100.0)
            widget.ui.showArcs.checked = False
            widget._branchOrderCheckboxes[1].checked = True
            for node, control in nodes:
                self.assertEqual(bool(node.GetDisplayNode().GetVisibility()), control != "showArcs")
                if control in ("showArcs", "showRays"):
                    self.assertTrue(node.GetDisplayNode().GetThresholdEnabled())
            widget.ui.showChildChild.checked = False
            for node, control in nodes:
                self.assertEqual(bool(node.GetDisplayNode().GetVisibility()),
                                 control != "showArcs" and node.GetAttribute("PairType") != "child-child")
                if control in ("showArcs", "showRays"):
                    self.assertTrue(node.GetDisplayNode().GetThresholdEnabled())
            widget.ui.showChildChild.checked = True
            widget.ui.rayColorButton.color = qt.QColor.fromRgbF(0.2, 0.4, 0.6)
            widget.ui.vectorColorButton.color = qt.QColor.fromRgbF(0.6, 0.4, 0.2)
            for node, control in nodes:
                if control not in ("showRays", "showVectors"):
                    continue
                expected = (0.2, 0.4, 0.6) if control == "showRays" else (0.6, 0.4, 0.2)
                for actual, value in zip(node.GetDisplayNode().GetColor(), expected):
                    self.assertAlmostEqual(actual, value, places=4)
                if control == "showRays":
                    color = [0.0] * 4
                    node.GetDisplayNode().GetColorNode().GetColor(0, color)
                    for actual, value in zip(color, expected):
                        self.assertAlmostEqual(actual, value, places=4)
            widget.onShowAllButton()
            for node, control in nodes:
                self.assertEqual(bool(node.GetDisplayNode().GetVisibility()), control != "showArcs")
            widget._branchOrderCheckboxes[2].checked = False
            widget.refreshBranchOrderControls()
            self.assertFalse(widget._branchOrderCheckboxes[2].checked)
            self.assertEqual(widget._parameterNode.GetParameter("showArcs"), "0")
            self.assertEqual(widget._parameterNode.GetParameter("HiddenBranchOrders"), "2")
        finally:
            widget.cleanup()

    def test_StaggeredArcs(self):
        """A trifurcation uses distinct radial levels, independent of input ordering."""
        import copy
        widget = CenterlineJunctionAnglesWidget()
        widget.logic = CenterlineJunctionAnglesLogic()
        bifurcations = self.createBifurcationVectors(childAngles=(20.0, -40.0, 80.0))
        widget.logic._bifurcationVectors = bifurcations
        angles = widget.logic.processJunctionAngles()
        originalAngles = copy.deepcopy(angles)
        radii = widget._junctionArcRadii(angles)
        self.assertEqual(len(radii), 6)
        self.assertEqual(len(set(radii.values())), 6)
        originalRayLength = math.dist(angles[0]["junctionPosition"], widget._rayEndPosition(angles[0], "branch1Position"))
        self.assertAlmostEqual(min(radii.values()), 0.35 * originalRayLength)
        self.assertGreater(max(radii.values()), originalRayLength)
        self.assertEqual(radii, widget._junctionArcRadii(list(reversed(angles))))
        expectedLabels = []
        for angle in angles:
            key = (angle["bifurcationGroupId"], angle["branch1GroupId"], angle["branch2GroupId"])
            points, label = widget._angleArcPolyline(angle, radius=radii[key])
            self.assertTrue(points)
            for position in points:
                self.assertAlmostEqual(math.dist(position, angle["junctionPosition"]), radii[key])
            self.assertEqual(label, points[len(points) // 2])
            expectedLabels.append(tuple(label))
            for positionKey in ("branch1Position", "branch2Position"):
                self.assertLess(radii[key], math.dist(angle["junctionPosition"], widget._rayEndPosition(angle, positionKey, 1.1 * radii[key])))
        folder = widget._createCurveSubjectHierarchyFolderNode("Staggered arcs test")
        widget._createJunctionAngleGroupComponents(angles, bifurcations, folder, False)
        actualLabels = []
        for node in slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode"):
            if node.GetAttribute("CenterlineJunctionAngleLabels") != "1":
                continue
            for index in range(node.GetNumberOfControlPoints()):
                position = [0.0, 0.0, 0.0]
                node.GetNthControlPointPosition(index, position)
                actualLabels.append(tuple(position))
        self.assertCountEqual(actualLabels, expectedLabels)
        self.assertEqual(angles, originalAngles)

    def test_AngleColorRange(self):
        """Close measurements use the full scale; equal measurements remain well-defined."""
        widget = CenterlineJunctionAnglesWidget()
        widget.logic = CenterlineJunctionAnglesLogic()
        bifurcations = self.createBifurcationVectors()
        widget.logic._bifurcationVectors = bifurcations
        angles = widget.logic.processJunctionAngles()
        for values in ((60.0, 60.5, 61.0), (60.0, 60.0, 60.0), (0.0, 0.0, 0.0), (180.0, 180.0, 180.0)):
            slicer.mrmlScene.Clear()
            for angle, value in zip(angles, values):
                angle["angleDegrees"] = value
            folder = widget._createCurveSubjectHierarchyFolderNode("Color range test")
            widget._createJunctionAngleGroupComponents(angles, bifurcations, folder, False)
            models = [node for node in slicer.util.getNodesByClass("vtkMRMLModelNode")
                      if node.GetAttribute("CenterlineJunctionAngleArcs") == "1"]
            self.assertTrue(models)
            ranges = {model.GetDisplayNode().GetScalarRange() for model in models}
            self.assertEqual(len(ranges), 1)
            lower, upper = ranges.pop()
            self.assertLess(lower, upper)
            if min(values) != max(values):
                self.assertEqual((lower, upper), (min(values), max(values)))
            lookupTable = vtk.vtkLookupTable()
            lookupTable.DeepCopy(models[0].GetDisplayNode().GetColorNode().GetLookupTable())
            lookupTable.SetRange(lower, upper)
            colors = set()
            for node in slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode"):
                if node.GetAttribute("CenterlineJunctionAngleLabels") != "1":
                    continue
                colors.add(node.GetDisplayNode().GetColor())
                for index in range(node.GetNumberOfControlPoints()):
                    expected = [0.0, 0.0, 0.0]
                    lookupTable.GetColor(float(node.GetNthControlPointDescription(index)), expected)
                    self.assertEqual(node.GetDisplayNode().GetColor(), tuple(expected))
            self.assertEqual(len(colors), len(set(values)))
            widget.filterJunctionAngleAnnotations(60.5)
            self.assertEqual({model.GetDisplayNode().GetScalarRange() for model in models}, {(lower, upper)})

    def test_ArcScalars(self):
        """Grouped arc tubes retain each measurement and use a shared color scale."""
        widget = CenterlineJunctionAnglesWidget()
        widget.logic = CenterlineJunctionAnglesLogic()
        bifurcations = self.createBifurcationVectors(childAngles=(20.0, -40.0, 80.0))
        widget.logic._bifurcationVectors = bifurcations
        angles = widget.logic.processJunctionAngles()
        folder = widget._createCurveSubjectHierarchyFolderNode("Test angles")
        widget._createJunctionAngleGroupComponents(angles, bifurcations, folder, False)
        arcModels = [node for node in slicer.util.getNodesByClass("vtkMRMLModelNode")
                     if node.GetAttribute("CenterlineJunctionAngleArcs") == "1"]
        self.assertEqual(len(arcModels), 2)
        for model in arcModels:
            polyData = model.GetPolyData()
            scalars = polyData.GetPointData().GetArray("AngleDegrees")
            self.assertIsNotNone(scalars)
            self.assertEqual(scalars.GetNumberOfTuples(), polyData.GetNumberOfPoints())
            expected = {round(angle["angleDegrees"], 6) for angle in angles
                        if widget.logic.junctionAnglePairType(angle["branch1Role"], angle["branch2Role"])
                        == model.GetAttribute("PairType")}
            self.assertEqual({round(scalars.GetValue(i), 6) for i in range(scalars.GetNumberOfTuples())}, expected)
            for cellIndex in range(polyData.GetNumberOfCells()):
                pointIds = polyData.GetCell(cellIndex).GetPointIds()
                self.assertEqual(len({scalars.GetValue(pointIds.GetId(i))
                                      for i in range(pointIds.GetNumberOfIds())}), 1)
            display = model.GetDisplayNode()
            self.assertTrue(display.GetScalarVisibility())
            self.assertEqual(display.GetActiveScalarName(), "AngleDegrees")
            self.assertEqual(display.GetScalarRange(),
                             (min(angle["angleDegrees"] for angle in angles), max(angle["angleDegrees"] for angle in angles)))
            self.assertIsNotNone(display.GetColorNode())
            self.assertEqual(display.GetColorNode().GetName(), "Plasma")
            self.assertTrue(display.GetLighting())
        lookupTable = vtk.vtkLookupTable()
        lookupTable.DeepCopy(arcModels[0].GetDisplayNode().GetColorNode().GetLookupTable())
        lookupTable.SetRange(*arcModels[0].GetDisplayNode().GetScalarRange())
        labels = [node for node in slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode")
                  if node.GetAttribute("CenterlineJunctionAngleLabels") == "1"]
        self.assertEqual(sum(node.GetNumberOfControlPoints() for node in labels), len(angles))
        for node in labels:
            self.assertTrue(node.GetDisplayNode().GetTextProperty().GetShadow())
            for index in range(node.GetNumberOfControlPoints()):
                expectedColor = [0.0, 0.0, 0.0]
                lookupTable.GetColor(float(node.GetNthControlPointDescription(index)), expectedColor)
                for actual, expected in zip(node.GetDisplayNode().GetColor(), expectedColor):
                    self.assertAlmostEqual(actual, expected)
        originalColors = {node.GetID(): node.GetDisplayNode().GetColor() for node in labels}
        models = [node for node in slicer.util.getNodesByClass("vtkMRMLModelNode")
                  if node.GetAttribute("CenterlineJunctionAngleArcs") == "1"
                  or node.GetAttribute("CenterlineJunctionAngleRays") == "1"]
        originalPointCounts = {node.GetID(): node.GetPolyData().GetNumberOfPoints() for node in models}
        # Include an exact measurement to check that the threshold is inclusive,
        # then raise and lower it before restoring every annotation.
        for threshold in (angles[0]["angleDegrees"], 180.0, 100.0, 0.0):
            self.assertEqual(widget.filterJunctionAngleAnnotations(threshold),
                             sum(angle["angleDegrees"] >= threshold for angle in angles))
            for node in labels:
                self.assertEqual(node.GetDisplayNode().GetColor(), originalColors[node.GetID()])
                for index in range(node.GetNumberOfControlPoints()):
                    self.assertEqual(node.GetNthControlPointVisibility(index),
                                     float(node.GetNthControlPointDescription(index)) >= threshold)
            for model in models:
                display = model.GetDisplayNode()
                self.assertEqual(display.GetThresholdEnabled(), threshold > 0.0)
                self.assertEqual(model.GetPolyData().GetNumberOfPoints(), originalPointCounts[model.GetID()])
                output = display.GetOutputPolyData()
                if output.GetNumberOfPoints():
                    self.assertGreaterEqual(output.GetPointData().GetArray("AngleDegrees").GetRange()[0], threshold)
                if threshold == 0.0:
                    self.assertEqual(output.GetNumberOfPoints(), originalPointCounts[model.GetID()])
                if model.GetAttribute("CenterlineJunctionAngleRays") == "1":
                    rayColor = [0.0, 0.0, 0.0, 0.0]
                    display.GetColorNode().GetColor(0, rayColor)
                    self.assertEqual(rayColor[:3], junctionAngleGeometryColor)

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
    def addArray(polyData, name, components, tuples):
        array = vtk.vtkDoubleArray()
        array.SetName(name)
        array.SetNumberOfComponents(components)
        for values in tuples:
            if components == 1:
                array.InsertNextValue(values)
            else:
                array.InsertNextTuple(values)
        polyData.GetPointData().AddArray(array)
        return array

    def createBifurcationVectorFilterOutputs(self, childAngles = (30.0, -40.0), vectorLength = 4.0):
        bifurcation = self.createBifurcationVectors(childAngles, vectorLength)[0]

        referencePoints = vtk.vtkPoints()
        referencePoints.InsertNextPoint(bifurcation["position"])
        referenceSystems = vtk.vtkPolyData()
        referenceSystems.SetPoints(referencePoints)
        self.addArray(referenceSystems, groupIdsArrayName, 1, [bifurcation["bifurcationGroupId"]])
        self.addArray(referenceSystems, normalArrayName, 3, [bifurcation["normal"]])
        self.addArray(referenceSystems, upNormalArrayName, 3, [bifurcation["upNormal"]])

        vectorPoints = vtk.vtkPoints()
        groupIds = []
        bifurcationGroupIds = []
        orientations = []
        vectors = []
        inPlaneAngles = []
        outOfPlaneAngles = []
        for branch in bifurcation["branches"].values():
            vectorPoints.InsertNextPoint(branch["basePosition"])
            groupIds.append(branch["groupId"])
            bifurcationGroupIds.append(bifurcation["bifurcationGroupId"])
            isUpstream = branch["role"] == "Parent"
            orientations.append(upstreamOrientation if isUpstream else 1)
            vectors.append(branch["vector"])
            inPlaneAngles.append(math.radians(0.0 if isUpstream else branch["inPlaneAngleDegrees"]))
            outOfPlaneAngles.append(math.radians(-branch["outOfPlaneAngleDegrees"] if isUpstream else branch["outOfPlaneAngleDegrees"]))
        bifurcationVectors = vtk.vtkPolyData()
        bifurcationVectors.SetPoints(vectorPoints)
        self.addArray(bifurcationVectors, groupIdsArrayName, 1, groupIds)
        self.addArray(bifurcationVectors, bifurcationGroupIdsArrayName, 1, bifurcationGroupIds)
        self.addArray(bifurcationVectors, bifurcationVectorsOrientationArrayName, 1, orientations)
        self.addArray(bifurcationVectors, bifurcationVectorsArrayName, 3, vectors)
        self.addArray(bifurcationVectors, inPlaneBifurcationVectorAnglesArrayName, 1, inPlaneAngles)
        self.addArray(bifurcationVectors, outOfPlaneBifurcationVectorAnglesArrayName, 1, outOfPlaneAngles)
        return referenceSystems, bifurcationVectors

    @staticmethod
    def anglesByGroupIdPair(junctionAngles):
        return {(junctionAngle["branch1GroupId"], junctionAngle["branch2GroupId"]): junctionAngle["angleDegrees"]
                for junctionAngle in junctionAngles}

    def test_BifurcationVectorValidation(self):
        """Malformed VMTK outputs raise exceptions instead of becoming NaN measurements."""
        self.delayDisplay(_("Bifurcation vector validation"))

        logic = CenterlineJunctionAnglesLogic()
        referenceSystems, bifurcationVectors = self.createBifurcationVectorFilterOutputs()
        bifurcations = logic._readBifurcationVectors(referenceSystems, bifurcationVectors)
        logic.assignBranchOrders(bifurcations)
        logic._bifurcationVectors = bifurcations
        angles = self.anglesByGroupIdPair(logic.processJunctionAngles())
        self.assertAlmostEqual(angles[(0, 2)], 150.0, delta=0.01)
        self.assertAlmostEqual(angles[(0, 3)], 140.0, delta=0.01)
        self.assertAlmostEqual(angles[(2, 3)], 70.0, delta=0.01)

        referenceSystems, bifurcationVectors = self.createBifurcationVectorFilterOutputs()
        referenceSystems.GetPointData().RemoveArray(upNormalArrayName)
        with self.assertRaisesRegex(ValueError, upNormalArrayName):
            logic._readBifurcationVectors(referenceSystems, bifurcationVectors)

        referenceSystems, bifurcationVectors = self.createBifurcationVectorFilterOutputs()
        bifurcationVectors.GetPointData().GetArray(bifurcationVectorsArrayName).SetTuple3(0, 0.0, 0.0, 0.0)
        self.assertEqual(logic._readBifurcationVectors(referenceSystems, bifurcationVectors), [])

        referenceSystems, bifurcationVectors = self.createBifurcationVectorFilterOutputs()
        bifurcationVectors.GetPointData().GetArray(inPlaneBifurcationVectorAnglesArrayName).SetTuple1(1, float("nan"))
        self.assertEqual(logic._readBifurcationVectors(referenceSystems, bifurcationVectors), [])

        referenceSystems, bifurcationVectors = self.createBifurcationVectorFilterOutputs(childAngles=(30.0, -40.0, 80.0))
        bifurcationVectors.GetPointData().GetArray(bifurcationVectorsArrayName).SetTuple3(1, 0.0, 0.0, 0.0)
        bifurcations = logic._readBifurcationVectors(referenceSystems, bifurcationVectors)
        self.assertEqual(len(bifurcations), 1)
        self.assertNotIn(2, bifurcations[0]["branches"])

        emptyCenterline = vtk.vtkPolyData()
        with self.assertRaisesRegex(ValueError, "empty"):
            logic.splitCenterlines(emptyCenterline)

        self.delayDisplay(_("Test passed"))

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
        logic._bifurcationVectors[0]["branches"][0]["outwardDirection"] = [0.0, 0.0, 0.0]
        with self.assertRaisesRegex(ValueError, "cached direction"):
            logic.processJunctionAngles()

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
junctionAngleLabelColor = [1.0, 1.0, 0.0]
junctionAngleGeometryColor = [1.0, 1.0, 0.0]
bifurcationVectorColor = [1.0, 0.5, 0.0]
bifurcationVectorTubeRadius = 0.16
bifurcationVectorEndpointRadius = 0.32
bifurcationVectorOpacity = 0.8
junctionAngleTubeRadius = 0.14
junctionAngleRayScale = 3.0
junctionAngleTextScale = 5.0
# How much of an annotation is seen where the vessel surface hides it
occludedOpacity = 0.6
