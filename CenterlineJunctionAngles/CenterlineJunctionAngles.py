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
        self._updatingAnnotation = False
        self._vectorMarkupModifiedCallback = self.onVectorMarkupModified
        self._observedVectorMarkupIds = set()
        self._annotationIndex = None
        self._annotationIndexKey = None
        self._angleLookupTable = None
        self._branchPolyline = None
        self._branchPolylineKey = None
        ScriptedLoadableModuleWidget.__init__(self, parent)

    def setup(self):
        super().setup()
        self.logic = CenterlineJunctionAnglesLogic()
        uiWidget = slicer.util.loadUI(self.resourcePath("UI/CenterlineJunctionAngles.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)
        uiWidget.setMRMLScene(slicer.mrmlScene)
        self.ui.inputSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
        self.ui.minimumAngleSpinBox.connect("valueChanged(double)", self.updateParameterNodeFromGUI)
        self.ui.applyButton.connect("clicked(bool)", self.onApplyButton)
        self.ui.filterButton.connect("clicked(bool)", self.onFilterButton)
        self.ui.showAllButton.connect("clicked(bool)", self.onShowAllButton)
        self.ui.resetSelectedVectorButton.connect("clicked(bool)", self.onResetSelectedVector)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
        for name in savedCheckBoxNames:
            getattr(self.ui, name).connect("toggled(bool)", self.onDisplayControlsChanged)
        self.ui.vectorColorButton.connect("colorChanged(QColor)", self.onDisplayControlsChanged)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndBatchProcessEvent, self.refreshBranchOrderControls)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.NodeRemovedEvent, self.onNodeRemoved)
        self.initializeParameterNode()
        self.refreshBranchOrderControls()

    def cleanup(self):
        self.removeObservers()

    def enter(self):
        self.initializeParameterNode()
        self.refreshBranchOrderControls()

    def onSceneStartClose(self, caller, event):
        self.setParameterNode(None)
        self.releaseVectorObservations()
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
        blocked = self.ui.minimumAngleSpinBox.blockSignals(True)
        if self._parameterNode and self._parameterNode.GetParameter("MinimumAngleDegrees"):
            self.ui.minimumAngleSpinBox.value = float(self._parameterNode.GetParameter("MinimumAngleDegrees"))
        self.ui.minimumAngleSpinBox.blockSignals(blocked)
        for name in savedCheckBoxNames:
            control = getattr(self.ui, name)
            blocked = control.blockSignals(True)
            control.checked = not self._parameterNode or self._parameterNode.GetParameter(name) != "0"
            control.blockSignals(blocked)
        value = self._parameterNode.GetParameter("vectorColorButton") if self._parameterNode else ""
        color = [float(component) for component in value.split()] if value else bifurcationVectorColor
        blocked = self.ui.vectorColorButton.blockSignals(True)
        self.ui.vectorColorButton.color = qt.QColor.fromRgbF(*color)
        self.ui.vectorColorButton.blockSignals(blocked)
        self.ui.applyButton.enabled = self.ui.inputSelector.currentNode() is not None

    def updateParameterNodeFromGUI(self, *args):
        if not self._parameterNode:
            return
        with slicer.util.NodeModify(self._parameterNode):
            node = self.ui.inputSelector.currentNode()
            self._parameterNode.SetNodeReferenceID("InputCenterline", node.GetID() if node else None)
            self._parameterNode.SetParameter("MinimumAngleDegrees", str(self.ui.minimumAngleSpinBox.value))

    def annotationDisplayNodes(self):
        elements = {"CenterlineJunctionAngleMarkup": None,
                    "CenterlineJunctionAngleVectors": "showVectors"}
        activeOutputSetId = self._parameterNode.GetParameter("ActiveOutputSetId") if self._parameterNode else ""
        for node in slicer.util.getNodesByClass("vtkMRMLDisplayableNode"):
            if activeOutputSetId and node.GetAttribute("OutputSetId") != activeOutputSetId:
                continue
            for attribute, control in elements.items():
                if node.GetAttribute(attribute) == "1":
                    if attribute == "CenterlineJunctionAngleVectors":
                        self.observeVectorMarkup(node)
                    yield node, control
                    break

    @staticmethod
    def restoreVectorControlPoints(vectorNode):
        """Put a vector back on its generated ends, adding any that are missing.

        A vector whose control points were deleted has nothing left to grab, so it cannot
        be repaired by hand; its generated ends are recorded and are put back here.
        """
        values = [float(value) for value in (vectorNode.GetAttribute("GeneratedControlPointPositions") or "").split()]
        if len(values) != 6:
            raise ValueError(_("The selected vector does not contain its generated control-point positions."))
        wasFixed = vectorNode.GetFixedNumberOfControlPoints()
        vectorNode.SetFixedNumberOfControlPoints(False)
        try:
            while vectorNode.GetNumberOfControlPoints() < 2:
                pointIndex = vectorNode.AddControlPoint(vtk.vtkVector3d(values[0:3]))
                vectorNode.SetNthControlPointSelected(pointIndex, False)
                vectorNode.SetNthControlPointLabel(pointIndex, "")
            for pointIndex in range(2):
                vectorNode.SetNthControlPointPositionWorld(pointIndex, values[3 * pointIndex:3 * pointIndex + 3])
        finally:
            vectorNode.SetFixedNumberOfControlPoints(wasFixed)

    def observeVectorMarkup(self, vectorNode):
        """A branch vector is the editable end of the measurement, so its moves are followed."""
        if vectorNode.GetID() in self._observedVectorMarkupIds or not vectorNode.IsA("vtkMRMLMarkupsNode"):
            return
        if vectorNode.GetNumberOfControlPoints() < 2 and vectorNode.GetAttribute("GeneratedControlPointPositions"):
            logging.warning(_("Restoring the generated ends of bifurcation vector '{name}'.").format(
                name=vectorNode.GetName()))
            self.restoreVectorControlPoints(vectorNode)
        self.addObserver(vectorNode, slicer.vtkMRMLMarkupsNode.PointModifiedEvent, self._vectorMarkupModifiedCallback)
        self._observedVectorMarkupIds.add(vectorNode.GetID())

    @vtk.calldata_type(vtk.VTK_OBJECT)
    def onNodeRemoved(self, caller, event, removedNode):
        """Release the observation of a vector markup that has left the scene.

        The observation holds a reference to the node, so a removed annotation would
        otherwise stay alive for as long as this widget does.
        """
        self._annotationIndex = None
        if removedNode is None or removedNode.GetID() not in self._observedVectorMarkupIds:
            return
        self.removeObserver(removedNode, slicer.vtkMRMLMarkupsNode.PointModifiedEvent,
                            self._vectorMarkupModifiedCallback)
        self._observedVectorMarkupIds.discard(removedNode.GetID())

    def releaseVectorObservations(self):
        """Stop following vectors that are no longer the ones the panel drives."""
        self.removeObservers(self._vectorMarkupModifiedCallback)
        self._observedVectorMarkupIds.clear()
        self._annotationIndex = None
        self._branchPolyline = None
        self._branchPolylineKey = None

    def annotationIndex(self):
        """Annotations of the active output, keyed by the branch of a bifurcation they measure.

        A vector drag has to reach the angles of its branch on every move of a handle, so
        the lookup is built once and kept until the output or the scene changes.
        """
        activeOutputSetId = self._parameterNode.GetParameter("ActiveOutputSetId") if self._parameterNode else ""
        if self._annotationIndex is not None and self._annotationIndexKey == activeOutputSetId:
            return self._annotationIndex
        angleNodesByBranch = {}
        vectorNodeByBranch = {}
        for node, control in self.annotationDisplayNodes():
            bifurcationGroupId = node.GetAttribute("BifurcationGroupId")
            if bifurcationGroupId is None:
                continue
            if node.GetAttribute("CenterlineJunctionAngleVectors") == "1":
                vectorNodeByBranch[(bifurcationGroupId, node.GetAttribute("BranchGroupId"))] = node
            elif node.GetAttribute("CenterlineJunctionAngleMarkup") == "1":
                for branchAttribute in ("Branch1GroupId", "Branch2GroupId"):
                    angleNodesByBranch.setdefault(
                        (bifurcationGroupId, node.GetAttribute(branchAttribute)), []).append(node)
        self._annotationIndex = (angleNodesByBranch, vectorNodeByBranch)
        self._annotationIndexKey = activeOutputSetId
        return self._annotationIndex

    def angleLookupTable(self, scalarMinimum, scalarMaximum):
        """Plasma color table of an angle range, copied from the scene once and then reused."""
        if self._angleLookupTable is None:
            colorNode = slicer.mrmlScene.GetNodeByID("vtkMRMLColorTableNodeFilePlasma.txt")
            if colorNode is None:
                raise ValueError(_("The Plasma color table is not available."))
            self._angleLookupTable = vtk.vtkLookupTable()
            self._angleLookupTable.DeepCopy(colorNode.GetLookupTable())
        self._angleLookupTable.SetRange(scalarMinimum, scalarMaximum)
        return self._angleLookupTable

    def branchCenterlinePositions(self, vectorNode):
        """Centerline of the branch a vector measures, parsed once per vector."""
        serializedPositions = vectorNode.GetAttribute("BranchCenterlinePositions") or ""
        if not serializedPositions:
            return None
        polylineKey = (vectorNode.GetID(), len(serializedPositions))
        if self._branchPolylineKey != polylineKey:
            values = [float(value) for value in serializedPositions.split()]
            self._branchPolyline = [values[index:index + 3] for index in range(0, len(values) - 2, 3)]
            self._branchPolylineKey = polylineKey
        return self._branchPolyline if len(self._branchPolyline) >= 2 else None

    @staticmethod
    def interactingSightDirection(position):
        """Direction the user is looking along at a position, in the view being used."""
        layoutManager = slicer.app.layoutManager()
        if layoutManager is None:
            return None
        views = [layoutManager.threeDWidget(index).threeDView()
                 for index in range(layoutManager.threeDViewCount)]
        views = [view for view in views if view is not None]
        view = next((candidate for candidate in views if candidate.underMouse()),
                    views[0] if len(views) == 1 else None)
        if view is None:
            return None
        renderer = view.renderWindow().GetRenderers().GetFirstRenderer()
        camera = renderer.GetActiveCamera() if renderer else None
        if camera is None:
            return None
        if camera.GetParallelProjection():
            direction = list(camera.GetDirectionOfProjection())
        else:
            direction = [position[index] - camera.GetPosition()[index] for index in range(3)]
        length = vtk.vtkMath.Norm(direction)
        if length <= minimumVectorLength:
            return None
        return [component / length for component in direction]

    @staticmethod
    def closestPositionOnPolyline(polyline, position):
        """Position on a polyline nearest a point in space, and how far away it is."""
        closest = (None, None)
        for start, end in zip(polyline, polyline[1:]):
            segment = [end[index] - start[index] for index in range(3)]
            segmentLength2 = vtk.vtkMath.Dot(segment, segment)
            if segmentLength2 <= minimumVectorLength:
                continue
            ratio = sum((position[index] - start[index]) * segment[index] for index in range(3)) / segmentLength2
            ratio = min(1.0, max(0.0, ratio))
            candidate = [start[index] + segment[index] * ratio for index in range(3)]
            distance = math.dist(candidate, position)
            if closest[1] is None or distance < closest[1]:
                closest = (candidate, distance)
        return closest

    @staticmethod
    def closestPositionAlongSight(polyline, position, sightDirection):
        """Position on a polyline nearest the line of sight through a handle.

        Dragging in a 3D view slides a handle across a plane facing the camera, so the
        handle sits under the cursor and the line of sight through it is the line the user
        is pointing along. Measuring across that line instead of through space picks the
        part of the branch that is under the cursor rather than the part that happens to be
        nearest in depth, which is what makes the snap follow the cursor.
        """
        candidates = []
        for start, end in zip(polyline, polyline[1:]):
            segment = [end[index] - start[index] for index in range(3)]
            segmentLength2 = vtk.vtkMath.Dot(segment, segment)
            if segmentLength2 <= minimumVectorLength:
                continue
            toStart = [start[index] - position[index] for index in range(3)]
            alongSight = vtk.vtkMath.Dot(segment, sightDirection)
            denominator = segmentLength2 - alongSight * alongSight
            if denominator <= minimumVectorLength:
                # The segment runs along the line of sight, so every point of it is aimed
                # at equally well and its near end is the one to take.
                ratio = 0.0
            else:
                ratio = (alongSight * vtk.vtkMath.Dot(sightDirection, toStart)
                         - vtk.vtkMath.Dot(segment, toStart)) / denominator
            ratio = min(1.0, max(0.0, ratio))
            candidate = [start[index] + segment[index] * ratio for index in range(3)]
            toCandidate = [candidate[index] - position[index] for index in range(3)]
            depth = vtk.vtkMath.Dot(toCandidate, sightDirection)
            across = [toCandidate[index] - depth * sightDirection[index] for index in range(3)]
            candidates.append((vtk.vtkMath.Norm(across), vtk.vtkMath.Norm(toCandidate), candidate))
        if not candidates:
            return None, None
        # Where a branch doubles back, two places are under the cursor; take the nearer of
        # them so that the handle does not travel along the branch in depth.
        smallestOffset = min(candidate[0] for candidate in candidates)
        aimedAt = [candidate for candidate in candidates if candidate[0] <= smallestOffset + sightTieTolerance]
        offset, distance, closestPosition = min(aimedAt, key=lambda candidate: candidate[1])
        return closestPosition, offset

    def snapDraggedHandleToCenterline(self, vectorNode):
        """Hold the handle that is being dragged on the centerline of its own branch.

        Only the dragged handle is moved: snapping the other end as well would change a
        direction that the user did not touch. A handle carried farther than the reach of
        the snap is left where it was put, so the branch does not drag it back.
        """
        displayNode = vectorNode.GetDisplayNode()
        if displayNode.GetActiveComponentType() != slicer.vtkMRMLMarkupsDisplayNode.ComponentControlPoint:
            return
        pointIndex = displayNode.GetActiveComponentIndex()
        if not 0 <= pointIndex < vectorNode.GetNumberOfControlPoints():
            return
        polyline = self.branchCenterlinePositions(vectorNode)
        if polyline is None:
            return
        position = list(vectorNode.GetNthControlPointPositionWorld(pointIndex))
        sightDirection = self.interactingSightDirection(position)
        if sightDirection is None:
            closestPosition, offset = self.closestPositionOnPolyline(polyline, position)
        else:
            closestPosition, offset = self.closestPositionAlongSight(polyline, position, sightDirection)
        if closestPosition is None:
            return
        # How far the aim misses the branch. Depth does not count against it, so pulling a
        # handle towards or away from the camera does not switch the snap off. A vector is
        # of the order of the local vessel radius, so its length gives a reach that is
        # generous in a large vessel and tight in a small one.
        generatedLength = float(vectorNode.GetAttribute("GeneratedVectorLength") or 0.0)
        if generatedLength > minimumVectorLength and offset > maximumSnapDistanceInVectorLengths * generatedLength:
            return
        # Moving a control point costs a full markup update, so a handle that is already on
        # the branch is left alone instead of being written back onto itself.
        if math.dist(closestPosition, position) > snapTolerance:
            vectorNode.SetNthControlPointPositionWorld(pointIndex, closestPosition)

    @staticmethod
    def branchDirectionOfVector(vectorNode):
        """Outward direction and length of a branch, from the two ends of its vector markup.

        'OutwardPointIndex' is the end away from the bifurcation, which is the base of the
        vector for a parent branch and its tip for a child branch.
        """
        outwardPointIndex = int(vectorNode.GetAttribute("OutwardPointIndex") or 0)
        outwardPosition = vectorNode.GetNthControlPointPositionWorld(outwardPointIndex)
        junctionPosition = vectorNode.GetNthControlPointPositionWorld(1 - outwardPointIndex)
        direction = [outwardPosition[i] - junctionPosition[i] for i in range(3)]
        length = vtk.vtkMath.Norm(direction)
        if not math.isfinite(length) or length <= minimumVectorLength:
            return None, 0.0
        return [component / length for component in direction], length

    def updateAngleFromVectors(self, angleNode, vectorNodeByBranch):
        """Lay the rays of an angle along the current directions of its two branch vectors.

        The vertex stays at the bifurcation reference system origin: an angle is a pair of
        directions, and only those directions are edited.
        """
        bifurcationGroupId = angleNode.GetAttribute("BifurcationGroupId")
        rayScale = float(angleNode.GetAttribute("RayScale") or junctionAngleRayScale)
        junctionPosition = angleNode.GetNthControlPointPositionWorld(1)
        # Both rays move together, so the annotation is redrawn once instead of twice.
        with slicer.util.NodeModify(angleNode):
            for pointIndex, branchAttribute in ((0, "Branch1GroupId"), (2, "Branch2GroupId")):
                vectorNode = vectorNodeByBranch.get((bifurcationGroupId, angleNode.GetAttribute(branchAttribute)))
                if vectorNode is None:
                    continue
                direction, length = self.branchDirectionOfVector(vectorNode)
                if direction is None:
                    continue
                angleNode.SetNthControlPointPositionWorld(
                    pointIndex, [junctionPosition[i] + direction[i] * length * rayScale for i in range(3)])
        self.refreshAngleValue(angleNode)

    def refreshAngleValue(self, angleNode):
        """Store and recolor the measurement an angle annotation now shows."""
        angleDegrees = angleNode.GetAngleDegrees()
        if not math.isfinite(angleDegrees):
            return
        angleNode.SetAttribute("AngleDegrees", str(angleDegrees))
        lookupTable = self.angleLookupTable(float(angleNode.GetAttribute("ColorRangeMinimum") or 0.0),
                                            float(angleNode.GetAttribute("ColorRangeMaximum") or 180.0))
        color = [0.0, 0.0, 0.0]
        lookupTable.GetColor(angleDegrees, color)
        angleNode.GetDisplayNode().SetColor(color)
        angleNode.GetDisplayNode().SetSelectedColor(color)

    def onVectorMarkupModified(self, vectorNode, event=None):
        """Follow a dragged branch vector into every angle measured from that branch.

        This runs for every move of a handle. The threshold is not reapplied here, so an
        annotation does not disappear from under the cursor while it is being edited.
        """
        if self._updatingAnnotation or vectorNode.GetNumberOfDefinedControlPoints(True) != 2:
            return
        self._updatingAnnotation = True
        try:
            if hasattr(self, "ui") and self.ui.snapToCenterline.checked:
                self.snapDraggedHandleToCenterline(vectorNode)
            angleNodesByBranch, vectorNodeByBranch = self.annotationIndex()
            branchKey = (vectorNode.GetAttribute("BifurcationGroupId"), vectorNode.GetAttribute("BranchGroupId"))
            for angleNode in angleNodesByBranch.get(branchKey, ()):
                self.updateAngleFromVectors(angleNode, vectorNodeByBranch)
        finally:
            self._updatingAnnotation = False

    def onResetSelectedVector(self):
        """Put an edited branch vector back where the centerline put it, angles included."""
        selectedNode = None
        for node, control in self.annotationDisplayNodes():
            if node.GetAttribute("CenterlineJunctionAngleVectors") != "1":
                continue
            displayNode = node.GetDisplayNode()
            if (displayNode.GetActiveComponentType() != slicer.vtkMRMLMarkupsDisplayNode.ComponentNone
                    or any(node.GetNthControlPointSelected(index) for index in range(node.GetNumberOfControlPoints()))):
                selectedNode = node
                break
        if selectedNode is None:
            slicer.util.infoDisplay(_("Select a bifurcation vector or one of its handles, then click Reset selected vector."))
            return
        self._updatingAnnotation = True
        try:
            self.restoreVectorControlPoints(selectedNode)
        finally:
            self._updatingAnnotation = False
        self.onVectorMarkupModified(selectedNode)
        minimumAngle = self.ui.minimumAngleSpinBox.value
        angleNodesByBranch, vectorNodeByBranch = self.annotationIndex()
        branchKey = (selectedNode.GetAttribute("BifurcationGroupId"), selectedNode.GetAttribute("BranchGroupId"))
        for angleNode in angleNodesByBranch.get(branchKey, ()):
            angleNode.SetAttribute("ThresholdVisible", "1" if angleNode.GetAngleDegrees() >= minimumAngle else "0")
        self.applyDisplayControls()

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
                checkbox = qt.QCheckBox(_("Unassigned branch order") if order < 0
                                        else _("Branch order {order}").format(order=order))
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
                for name in savedCheckBoxNames:
                    self._parameterNode.SetParameter(name, "1" if getattr(self.ui, name).checked else "0")
                color = self.ui.vectorColorButton.color
                self._parameterNode.SetParameter("vectorColorButton", " ".join(str(value) for value in
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
            thresholdVisible = node.GetAttribute("ThresholdVisible") != "0"
            if node.GetAttribute("CenterlineJunctionAngleMarkup") == "1":
                visible = self.ui.showAnnotations.checked and (checkbox is None or checkbox.checked) and pairVisible and thresholdVisible
                node.GetDisplayNode().SetVisibility(visible)
                continue
            node.GetDisplayNode().SetVisibility(
                getattr(self.ui, control).checked and (checkbox is None or checkbox.checked) and pairVisible)
            if control != "showVectors":
                continue
            qcolor = self.ui.vectorColorButton.color
            color = (qcolor.redF(), qcolor.greenF(), qcolor.blueF())
            display = node.GetDisplayNode()
            display.SetColor(color)
            if node.IsA("vtkMRMLMarkupsNode"):
                display.SetSelectedColor(color)

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
                    outputSetId = tableNode.GetID()
                    tableNode.SetAttribute("CenterlineJunctionAngles", "1")
                    tableNode.SetAttribute("OutputSetId", outputSetId)
                    # The panel follows one output at a time, so the vectors of the previous
                    # one stop being observed as soon as this one takes over.
                    self.releaseVectorObservations()
                    self._parameterNode.SetParameter("ActiveOutputSetId", outputSetId)
                    self.logic.populateJunctionAnglesTable(tableNode, junctionAngles)
                    self.updateProgress(progressDialog, _("Creating junction angle annotations..."), 80)
                    angleFolder = self._createSubjectHierarchyFolderNode(label + _(" annotations"))
                    self._createJunctionAngleGroupComponents(
                        junctionAngles, self.logic.computeBifurcationVectors(), angleFolder, outputSetId)
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
        """Hide angle annotations below the threshold without changing colors or data."""
        count = 0
        for angleNode, control in self.annotationDisplayNodes():
            if angleNode.GetAttribute("CenterlineJunctionAngleMarkup") != "1":
                continue
            angleValue = angleNode.GetAttribute("AngleDegrees")
            if not angleValue:
                continue
            visible = float(angleValue) >= minimumAngleDegrees
            angleNode.SetAttribute("ThresholdVisible", "1" if visible else "0")
            count += int(visible)
        self.applyDisplayControls()
        return count

    def _createSubjectHierarchyFolderNode(self, label, parentFolderId=None):
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

    def _createBifurcationVectorMarkup(self, bifurcation, branch, parentFolderId, branchOrder,
                                       outputSetId, branchPolyline=None):
        """One editable line markup for the bifurcation vector of a branch.

        Both ends come from the centerline, so this is the handle to drag when a measured
        direction has to be corrected; the angles of the branch follow it.
        """
        if branch["vectorLength"] <= minimumVectorLength:
            return None
        basePosition = branch["basePosition"]
        endPosition = [basePosition[i] + branch["vector"][i] for i in range(3)]
        vectorNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsLineNode", _("Vector {bifurcation}: branch {branch}").format(
            bifurcation=bifurcation["bifurcationGroupId"], branch=branch["groupId"]))
        vectorNode.CreateDefaultDisplayNodes()
        for position in (basePosition, endPosition):
            pointIndex = vectorNode.AddControlPoint(vtk.vtkVector3d(position))
            vectorNode.SetNthControlPointSelected(pointIndex, False)
            vectorNode.SetNthControlPointLabel(pointIndex, "")
        vectorNode.SetLocked(False)
        # The two ends are the measurement, so they can be dragged but not deleted.
        vectorNode.SetFixedNumberOfControlPoints(True)
        vectorNode.SetAttribute("CenterlineJunctionAngles", "1")
        vectorNode.SetAttribute("CenterlineJunctionAngleVectors", "1")
        vectorNode.SetAttribute("BranchOrder", str(branchOrder))
        vectorNode.SetAttribute("OutputSetId", outputSetId)
        vectorNode.SetAttribute("BifurcationGroupId", str(bifurcation["bifurcationGroupId"]))
        vectorNode.SetAttribute("BranchGroupId", str(branch["groupId"]))
        vectorNode.SetAttribute("BranchRole", branch["role"])
        # VMTK stores a parent vector along the flow, so its base is the end away from the
        # bifurcation; a child vector starts at the bifurcation and its tip is that end.
        vectorNode.SetAttribute("OutwardPointIndex", "0" if branch["role"] == "Parent" else "1")
        vectorNode.SetAttribute("GeneratedControlPointPositions", " ".join(
            str(coordinate) for position in (basePosition, endPosition) for coordinate in position))
        vectorNode.SetAttribute("GeneratedVectorLength", str(branch["vectorLength"]))
        # The curve of the branch travels with the annotation, so a handle can be held on
        # its own branch after the scene has been saved and reopened.
        if branchPolyline:
            stride = max(1, (len(branchPolyline) + maximumStoredBranchPoints - 1) // maximumStoredBranchPoints)
            storedPolyline = branchPolyline[::stride]
            if storedPolyline[-1] != branchPolyline[-1]:
                storedPolyline.append(branchPolyline[-1])
            vectorNode.SetAttribute("BranchCenterlinePositions", " ".join(
                str(coordinate) for position in storedPolyline for coordinate in position))
        displayNode = vectorNode.GetDisplayNode()
        displayNode.SetColor(bifurcationVectorColor)
        displayNode.SetSelectedColor(bifurcationVectorColor)
        displayNode.SetOpacity(bifurcationVectorOpacity)
        displayNode.SetGlyphScale(bifurcationVectorGlyphScale)
        displayNode.SetLineThickness(bifurcationVectorLineThickness)
        displayNode.SetPointLabelsVisibility(False)
        displayNode.SetPropertiesLabelVisibility(False)
        displayNode.SetOccludedVisibility(True)
        displayNode.SetOccludedOpacity(occludedOpacity)
        self._reparentNodeToSubjectHierarchyFolderNode(parentFolderId, vectorNode)
        return vectorNode

    @staticmethod
    def _rayEndPosition(junctionAngle, positionKey, rayScale=None):
        """End of an annotation ray: the measured direction, drawn 'rayScale' times longer."""
        junctionPosition = junctionAngle["junctionPosition"]
        position = junctionAngle[positionKey]
        scale = junctionAngleRayScale if rayScale is None else rayScale
        return [junctionPosition[i] + (position[i] - junctionPosition[i]) * scale for i in range(3)]

    @staticmethod
    def _junctionMarkupRayScales(junctionAngles):
        """Stagger native angle arcs by increasing both ray lengths for successive pairs."""
        anglesByJunction = {}
        for angle in junctionAngles:
            anglesByJunction.setdefault(angle["bifurcationGroupId"], []).append(angle)
        scales = {}
        for junctionId, angles in anglesByJunction.items():
            angles.sort(key=lambda angle: (angle["branch1GroupId"], angle["branch2GroupId"]))
            for index, angle in enumerate(angles):
                scales[(junctionId, angle["branch1GroupId"], angle["branch2GroupId"])] = (
                    junctionAngleRayScale + junctionAngleRayScaleStep * index)
        return scales

    @staticmethod
    def _bifurcationBranchesByGroupId(bifurcations):
        branchesByGroupId = {}
        for bifurcation in bifurcations:
            for branch in bifurcation["branches"].values():
                branchesByGroupId[(bifurcation["bifurcationGroupId"], branch["groupId"])] = branch
        return branchesByGroupId

    def _createJunctionAngleGroupComponents(self, junctionAngles, bifurcations, parentFolderId, outputSetId=""):
        labels = {"child-child": _("Child-child angles"), "parent-child": _("Parent-child angles"), "parent-parent": _("Parent-parent angles")}
        folders = {}
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
        branchPolylines = self.logic.branchPolylines()
        lookupTable = self.angleLookupTable(*scalarRange)
        rayScales = self._junctionMarkupRayScales(junctionAngles)
        vectorBranchOrders = {}
        for junctionAngle in junctionAngles:
            pairType = self.logic.junctionAnglePairType(junctionAngle["branch1Role"], junctionAngle["branch2Role"])
            if pairType not in folders:
                folders[pairType] = self._createSubjectHierarchyFolderNode(labels[pairType], parentFolderId)
            branchOrder = junctionAngle["branchOrder"]
            groupKey = (pairType, branchOrder)
            if groupKey not in folders:
                folders[groupKey] = self._createSubjectHierarchyFolderNode(
                    _("Unassigned branch order") if branchOrder < 0
                    else _("Branch order {order}").format(order=branchOrder), folders[pairType])
            angleKey = (junctionAngle["bifurcationGroupId"], junctionAngle["branch1GroupId"],
                        junctionAngle["branch2GroupId"])
            rayScale = rayScales[angleKey]
            ray1EndPosition = self._rayEndPosition(junctionAngle, "branch1Position", rayScale=rayScale)
            ray2EndPosition = self._rayEndPosition(junctionAngle, "branch2Position", rayScale=rayScale)
            # Slicer draws the label of an angle as the name of the node, a colon, and the
            # measurement, and offers no way to leave the name out, so the label reads
            # 'Angle: 47.7'. Every node is given the same concise name once it is in the
            # scene, which keeps that label short and keeps Slicer from numbering it. The
            # node description is not used for the branch identity of a pair: Slicer
            # rewrites it from the measurements. The identity is in the attributes below.
            angleNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsAngleNode", " ")
            angleNode.SetName(_("Angle"))
            angleNode.CreateDefaultDisplayNodes()
            pointPositions = (ray1EndPosition, junctionAngle["junctionPosition"], ray2EndPosition)
            for position in pointPositions:
                pointIndex = angleNode.AddControlPoint(vtk.vtkVector3d(position))
                angleNode.SetNthControlPointSelected(pointIndex, False)
            for pointIndex in range(3):
                angleNode.SetNthControlPointLabel(pointIndex, "")
            # The vectors carry the editing, so an angle is a read-only result. Locking it
            # also keeps it out of picking, which keeps a large tree responsive.
            angleNode.SetLocked(True)
            angleNode.SetAttribute("CenterlineJunctionAngles", "1")
            angleNode.SetAttribute("CenterlineJunctionAngleMarkup", "1")
            angleNode.SetAttribute("PairType", pairType)
            angleNode.SetAttribute("BranchOrder", str(branchOrder))
            angleNode.SetAttribute("OutputSetId", outputSetId)
            angleNode.SetAttribute("ThresholdVisible", "1")
            angleNode.SetAttribute("AngleDegrees", str(junctionAngle["angleDegrees"]))
            angleNode.SetAttribute("ColorRangeMinimum", str(scalarRange[0]))
            angleNode.SetAttribute("ColorRangeMaximum", str(scalarRange[1]))
            angleNode.SetAttribute("BifurcationGroupId", str(junctionAngle["bifurcationGroupId"]))
            angleNode.SetAttribute("Branch1GroupId", str(junctionAngle["branch1GroupId"]))
            angleNode.SetAttribute("Branch2GroupId", str(junctionAngle["branch2GroupId"]))
            angleNode.SetAttribute("GeneratedControlPointPositions", " ".join(
                str(coordinate) for position in pointPositions for coordinate in position))
            angleNode.SetAttribute("GeneratedAngleDegrees", str(junctionAngle["angleDegrees"]))
            angleNode.SetAttribute("RayScale", str(rayScale))
            measurement = angleNode.GetMeasurement("angle")
            if measurement:
                measurement.SetPrintFormat("%3.1f°")
            displayNode = angleNode.GetDisplayNode()
            color = [0.0, 0.0, 0.0]
            lookupTable.GetColor(junctionAngle["angleDegrees"], color)
            displayNode.SetColor(color)
            displayNode.SetSelectedColor(color)
            displayNode.SetGlyphScale(0.7)
            displayNode.SetLineThickness(0.8)
            displayNode.SetPointLabelsVisibility(False)
            displayNode.SetPropertiesLabelVisibility(True)
            displayNode.SetTextScale(junctionAngleTextScale)
            displayNode.GetTextProperty().ShadowOn()
            displayNode.SetOccludedVisibility(True)
            displayNode.SetOccludedOpacity(occludedOpacity)
            self._reparentNodeToSubjectHierarchyFolderNode(folders[groupKey], angleNode)
            bifurcationGroupId = junctionAngle["bifurcationGroupId"]
            # A branch is shared by the pairs of its bifurcation, so its vector is created
            # once, in a folder of its own, instead of once per pair type.
            vectorBranchOrders[(bifurcationGroupId, junctionAngle["branch1GroupId"])] = branchOrder
            vectorBranchOrders[(bifurcationGroupId, junctionAngle["branch2GroupId"])] = branchOrder

        bifurcationsByGroupId = {bifurcation["bifurcationGroupId"]: bifurcation for bifurcation in bifurcations}
        for branchKey in sorted(vectorBranchOrders):
            branch = branchesByGroupId.get(branchKey)
            bifurcation = bifurcationsByGroupId.get(branchKey[0])
            if branch is None or bifurcation is None:
                continue
            branchOrder = vectorBranchOrders[branchKey]
            if "vectors" not in folders:
                folders["vectors"] = self._createSubjectHierarchyFolderNode(
                    _("Bifurcation vectors"), parentFolderId)
            orderKey = ("vectors", branchOrder)
            if orderKey not in folders:
                folders[orderKey] = self._createSubjectHierarchyFolderNode(
                    _("Unassigned branch order") if branchOrder < 0
                    else _("Branch order {order}").format(order=branchOrder), folders["vectors"])
            self._createBifurcationVectorMarkup(bifurcation, branch, folders[orderKey], branchOrder,
                                                outputSetId, branchPolylines.get(branch["groupId"]))


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
        self._branchOrders = None
        self._branchPolylines = None

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
        self._branchOrders = self.computeBranchOrders(self._splitCenterlines)
        self._branchPolylines = self.computeBranchPolylines(self._splitCenterlines)
        self.assignBranchOrders(bifurcations, self._branchOrders)
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

    def branchPolylines(self):
        """Centerline of every branch group of the last computation, by GroupId."""
        return self._branchPolylines or {}

    @staticmethod
    def computeBranchPolylines(splitCenterlines):
        """The centerline of every branch group, as the curve that its vector runs along.

        Each centerline that passes through a group traces the same branch there, so one
        tract describes it; the longest one covers the whole branch.
        """
        if splitCenterlines is None:
            return {}
        groupIds = splitCenterlines.GetCellData().GetArray(groupIdsArrayName)
        blanking = splitCenterlines.GetCellData().GetArray(blankingArrayName)
        if groupIds is None or blanking is None:
            return {}
        polylines = {}
        for cellId in range(splitCenterlines.GetNumberOfCells()):
            if int(blanking.GetTuple1(cellId)):
                continue
            cell = splitCenterlines.GetCell(cellId)
            numberOfPoints = cell.GetNumberOfPoints()
            groupId = int(groupIds.GetTuple1(cellId))
            if numberOfPoints < 2 or len(polylines.get(groupId, ())) >= numberOfPoints:
                continue
            polylines[groupId] = [list(cell.GetPoints().GetPoint(index)) for index in range(numberOfPoints)]
        return polylines

    @staticmethod
    def computeBranchOrders(splitCenterlines):
        """Compute branch depth from complete ordered centerline tracts.

        Branch extraction stores each input centerline as an ordered sequence of
        tracts. Non-blanked groups are vessel branches and blanked groups are
        bifurcation regions. Consecutive vessel groups along each centerline
        therefore define the parent-child graph even when a bifurcation vector
        is invalid and cannot be used for an angle measurement.
        """
        if splitCenterlines is None:
            return {}
        cellData = splitCenterlines.GetCellData()
        groupIds = cellData.GetArray(groupIdsArrayName)
        centerlineIds = cellData.GetArray(centerlineIdsArrayName)
        tractIds = cellData.GetArray(tractIdsArrayName)
        blanking = cellData.GetArray(blankingArrayName)
        numberOfCells = splitCenterlines.GetNumberOfCells()
        for array, name in ((groupIds, groupIdsArrayName), (centerlineIds, centerlineIdsArrayName),
                            (tractIds, tractIdsArrayName), (blanking, blankingArrayName)):
            if array is None or array.GetNumberOfTuples() != numberOfCells:
                raise ValueError(_("Missing or invalid extracted centerline array '{name}'.").format(name=name))

        tractsByCenterline = {}
        for cellId in range(numberOfCells):
            centerlineId = int(centerlineIds.GetTuple1(cellId))
            tractsByCenterline.setdefault(centerlineId, []).append((
                int(tractIds.GetTuple1(cellId)), cellId,
                int(groupIds.GetTuple1(cellId)), int(blanking.GetTuple1(cellId))))

        adjacency = {}
        indegree = {}
        allBranches = set()
        for tracts in tractsByCenterline.values():
            # Cell ID makes ordering deterministic if malformed input contains
            # duplicate tract IDs.
            tracts.sort(key=lambda tract: (tract[0], tract[1]))
            branchSequence = []
            for tractId, cellId, groupId, isBlanked in tracts:
                if isBlanked:
                    continue
                if not branchSequence or branchSequence[-1] != groupId:
                    branchSequence.append(groupId)
                    allBranches.add(groupId)
            for parentGroupId, childGroupId in zip(branchSequence, branchSequence[1:]):
                if parentGroupId == childGroupId:
                    continue
                children = adjacency.setdefault(parentGroupId, set())
                if childGroupId not in children:
                    children.add(childGroupId)
                    indegree[childGroupId] = indegree.get(childGroupId, 0) + 1
                indegree.setdefault(parentGroupId, indegree.get(parentGroupId, 0))

        # Each real connected component has one root. Multiple roots here mean
        # that the input actually contains multiple centerline trees, not that
        # an angle-producing junction was skipped.
        branchOrders = {groupId: 0 for groupId in allBranches if indegree.get(groupId, 0) == 0}
        pending = list(branchOrders)
        while pending:
            parentGroupId = pending.pop(0)
            childOrder = branchOrders[parentGroupId] + 1
            for childGroupId in adjacency.get(parentGroupId, ()):
                if childGroupId not in branchOrders or childOrder < branchOrders[childGroupId]:
                    branchOrders[childGroupId] = childOrder
                    pending.append(childGroupId)
        return branchOrders

    @staticmethod
    def assignBranchOrders(bifurcations, completeBranchOrders=None):
        """Assign branch orders from VMTK parent/child relationships.

        In each bifurcation, the children are one order distal to the parent.
        If a branch appears in several bifurcations, the lowest order found from
        the inlet side is used.
        """
        if completeBranchOrders is not None:
            for bifurcation in bifurcations:
                for branch in bifurcation["branches"].values():
                    branch["branchOrder"] = completeBranchOrders.get(branch["groupId"], -1)
            return

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

        rootGroupIds = parentGroupIdsSet - childGroupIdsSet
        for rootGroupId in rootGroupIds:
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
                # If VMTK reports a component without any parent branch then its
                # depth cannot be inferred. Do not mislabel those distal branches
                # as order zero.
                branch["branchOrder"] = branchOrders.get(branch["groupId"], -1)

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
        self.assignBranchOrders(bifurcations, self._branchOrders)
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
            # The generation of a bifurcation is the order of the branch that reaches it from
            # the inlet, its parent. Every angle of the bifurcation is reported in that
            # generation, so that hiding a branch order hides a whole junction at a time.
            parentOrders = [branch["branchOrder"] for branch in branches if branch["role"] == "Parent"]
            if parentOrders:
                junctionOrder = min(parentOrders)
            else:
                # VMTK reported no upstream branch here, so the branch closest to the inlet is
                # the shallowest one. An unassigned order cannot stand in for a generation.
                assignedOrders = [branch["branchOrder"] for branch in branches if branch["branchOrder"] >= 0]
                junctionOrder = min(assignedOrders) if assignedOrders else -1
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
                        "branchOrder": junctionOrder,
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
        tableNode.SetColumnDescription("BranchOrder", _("Generation of the bifurcation, the branch order of its parent branch, shared by every angle of that bifurcation"))
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
                     self.test_BranchOrderUsesCompleteTopology,
                     self.test_MarkupAngleAnnotations, self.test_VectorDrivesAngle,
                     self.test_ResetSelectedVector, self.test_SnapToCenterline,
                     self.test_SnapAlongSight, self.test_BranchPolylines,
                     self.test_VectorControlPointsSurviveDeletion,
                     self.test_VectorMarkupObservationLifetime,
                     self.test_DisplayControls, self.test_AngleColorRange]:
            self.setUp()
            test()

    def test_DisplayControls(self):
        """Element/order visibility composes with thresholding, and colors update in place."""
        # A widget without a parent sets itself up, so setup() must not be called again:
        # a second one would load the panel twice and connect every control twice.
        widget = CenterlineJunctionAnglesWidget()
        try:
            self.assertTrue(widget.ui.displayOptionsCollapsibleButton.collapsed)
            bifurcations = self.createBifurcationVectors()
            widget.logic._bifurcationVectors = bifurcations
            angles = widget.logic.processJunctionAngles()
            for angle in angles:
                angle["branchOrder"] = 1
            angles[0]["branchOrder"] = 2
            folder = widget._createSubjectHierarchyFolderNode("Display controls test")
            widget._createJunctionAngleGroupComponents(angles, bifurcations, folder)
            widget.refreshBranchOrderControls()
            widget.applyDisplayControls()
            self.assertEqual(set(widget._branchOrderCheckboxes), {1, 2})
            nodes = list(widget.annotationDisplayNodes())
            self.assertTrue(nodes)
            for control in ("showAnnotations", "showVectors"):
                getattr(widget.ui, control).checked = False
                for node, element in nodes:
                    if node.GetAttribute("CenterlineJunctionAngleMarkup") == "1":
                        self.assertEqual(bool(node.GetDisplayNode().GetVisibility()), control != "showAnnotations")
                        self.assertTrue(node.GetDisplayNode().GetPropertiesLabelVisibility())
                        self.assertFalse(node.GetDisplayNode().GetPointLabelsVisibility())
                    else:
                        self.assertEqual(bool(node.GetDisplayNode().GetVisibility()), element != control)
                getattr(widget.ui, control).checked = True
            self.assertEqual({node.GetAttribute("PairType") for node, _ in nodes
                              if node.GetAttribute("CenterlineJunctionAngleMarkup") == "1"},
                             {"parent-child", "child-child"})
            self.assertTrue(all(node.GetAttribute("PairType") is None for node, _ in nodes
                                if node.GetAttribute("CenterlineJunctionAngleVectors") == "1"))
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
            widget._branchOrderCheckboxes[1].checked = True
            for node, control in nodes:
                expectedVisible = (node.GetAttribute("CenterlineJunctionAngleMarkup") != "1"
                                   or float(node.GetAttribute("AngleDegrees")) >= 100.0)
                self.assertEqual(bool(node.GetDisplayNode().GetVisibility()), expectedVisible)
            widget.ui.showChildChild.checked = False
            for node, control in nodes:
                self.assertEqual(bool(node.GetDisplayNode().GetVisibility()),
                                 node.GetAttribute("PairType") != "child-child"
                                 and (node.GetAttribute("CenterlineJunctionAngleMarkup") != "1"
                                      or float(node.GetAttribute("AngleDegrees")) >= 100.0))
            widget.ui.showChildChild.checked = True
            widget.ui.vectorColorButton.color = qt.QColor.fromRgbF(0.6, 0.4, 0.2)
            for node, control in nodes:
                if control != "showVectors":
                    continue
                expected = (0.6, 0.4, 0.2)
                for actual, value in zip(node.GetDisplayNode().GetColor(), expected):
                    self.assertAlmostEqual(actual, value, places=4)
            widget.onShowAllButton()
            for node, _ in nodes:
                self.assertTrue(node.GetDisplayNode().GetVisibility())
            widget._branchOrderCheckboxes[2].checked = False
            widget.refreshBranchOrderControls()
            self.assertFalse(widget._branchOrderCheckboxes[2].checked)
            self.assertEqual(widget._parameterNode.GetParameter("HiddenBranchOrders"), "2")
        finally:
            widget.cleanup()

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
            folder = widget._createSubjectHierarchyFolderNode("Color range test")
            widget._createJunctionAngleGroupComponents(angles, bifurcations, folder)
            lower, upper = (min(values), max(values))
            if lower == upper:
                lower, upper = (max(0.0, lower - 0.5), min(180.0, upper + 0.5))
            self.assertLess(lower, upper)
            if min(values) != max(values):
                self.assertEqual((lower, upper), (min(values), max(values)))
            lookupTable = vtk.vtkLookupTable()
            lookupTable.DeepCopy(slicer.mrmlScene.GetNodeByID("vtkMRMLColorTableNodeFilePlasma.txt").GetLookupTable())
            lookupTable.SetRange(lower, upper)
            colors = set()
            for node in slicer.util.getNodesByClass("vtkMRMLMarkupsAngleNode"):
                if node.GetAttribute("CenterlineJunctionAngleMarkup") != "1":
                    continue
                colors.add(node.GetDisplayNode().GetColor())
                expected = [0.0, 0.0, 0.0]
                lookupTable.GetColor(float(node.GetAttribute("AngleDegrees")), expected)
                self.assertEqual(node.GetDisplayNode().GetColor(), tuple(expected))
            self.assertEqual(len(colors), len(set(values)))
            widget.filterJunctionAngleAnnotations(60.5)
            for node in slicer.util.getNodesByClass("vtkMRMLMarkupsAngleNode"):
                if node.GetAttribute("CenterlineJunctionAngleMarkup") == "1":
                    self.assertEqual(bool(node.GetDisplayNode().GetVisibility()),
                                     float(node.GetAttribute("AngleDegrees")) >= 60.5)

    def test_MarkupAngleAnnotations(self):
        """Native markup angle nodes store each measurement and remain interactable."""
        widget = CenterlineJunctionAnglesWidget()
        widget.logic = CenterlineJunctionAnglesLogic()
        bifurcations = self.createBifurcationVectors(childAngles=(20.0, -40.0, 80.0))
        widget.logic._bifurcationVectors = bifurcations
        angles = widget.logic.processJunctionAngles()
        folder = widget._createSubjectHierarchyFolderNode("Test angles")
        widget._createJunctionAngleGroupComponents(angles, bifurcations, folder)
        lookupTable = vtk.vtkLookupTable()
        lookupTable.DeepCopy(slicer.mrmlScene.GetNodeByID("vtkMRMLColorTableNodeFilePlasma.txt").GetLookupTable())
        lookupTable.SetRange(min(angle["angleDegrees"] for angle in angles), max(angle["angleDegrees"] for angle in angles))
        angleNodes = [node for node in slicer.util.getNodesByClass("vtkMRMLMarkupsAngleNode")
                      if node.GetAttribute("CenterlineJunctionAngleMarkup") == "1"]
        self.assertEqual(len(angleNodes), len(angles))
        for node in angleNodes:
            self.assertEqual(node.GetNumberOfControlPoints(), 3)
            # An angle is a result of the vectors, so it is not edited directly.
            self.assertTrue(node.GetLocked())
            self.assertTrue(node.GetDisplayNode().GetPropertiesLabelVisibility())
            self.assertFalse(node.GetDisplayNode().GetPointLabelsVisibility())
            self.assertEqual(node.GetName(), _("Angle"))
            self.assertEqual(node.GetMeasurement("angle").GetPrintFormat(), "%3.1f°")
            expectedColor = [0.0, 0.0, 0.0]
            lookupTable.GetColor(float(node.GetAttribute("AngleDegrees")), expectedColor)
            for actual, expected in zip(node.GetDisplayNode().GetColor(), expectedColor):
                self.assertAlmostEqual(actual, expected)
        # Include an exact measurement to check that the threshold is inclusive,
        # then raise and lower it before restoring every annotation.
        for threshold in (angles[0]["angleDegrees"], 180.0, 100.0, 0.0):
            self.assertEqual(widget.filterJunctionAngleAnnotations(threshold),
                             sum(angle["angleDegrees"] >= threshold for angle in angles))
            for node in angleNodes:
                self.assertEqual(bool(node.GetDisplayNode().GetVisibility()),
                                 float(node.GetAttribute("AngleDegrees")) >= threshold)

    @staticmethod
    def vectorNodesByBranchGroupId(widget):
        return {node.GetAttribute("BranchGroupId"): node for node, control in widget.annotationDisplayNodes()
                if node.GetAttribute("CenterlineJunctionAngleVectors") == "1"}

    @staticmethod
    def angleNodesByBranchGroupIdPair(widget):
        return {(node.GetAttribute("Branch1GroupId"), node.GetAttribute("Branch2GroupId")): node
                for node, control in widget.annotationDisplayNodes()
                if node.GetAttribute("CenterlineJunctionAngleMarkup") == "1"}

    def bifurcationAnnotationWidget(self, childAngles=(30.0, -40.0), branchPolylines=None):
        widget = CenterlineJunctionAnglesWidget()
        widget.logic = CenterlineJunctionAnglesLogic()
        widget.logic._bifurcationVectors = self.createBifurcationVectors(childAngles=childAngles)
        widget.logic._branchPolylines = branchPolylines
        junctionAngles = widget.logic.processJunctionAngles()
        folder = widget._createSubjectHierarchyFolderNode("Annotations")
        widget._createJunctionAngleGroupComponents(junctionAngles, widget.logic._bifurcationVectors, folder)
        return widget

    def test_VectorDrivesAngle(self):
        """Dragging a branch vector must move every angle measured from that branch."""
        widget = self.bifurcationAnnotationWidget()
        try:
            vectorNodes = self.vectorNodesByBranchGroupId(widget)
            angleNodes = self.angleNodesByBranchGroupIdPair(widget)
            self.assertEqual(set(vectorNodes), {"0", "2", "3"})
            self.assertEqual(set(angleNodes), {("0", "2"), ("0", "3"), ("2", "3")})
            self.assertAlmostEqual(angleNodes[("0", "2")].GetAngleDegrees(), 150.0, delta=0.01)

            # Branch 2 leaves the junction at its tip, so point 1 is its outward end.
            self.assertEqual(vectorNodes["2"].GetAttribute("OutwardPointIndex"), "1")
            self.assertEqual(vectorNodes["0"].GetAttribute("OutwardPointIndex"), "0")
            vectorNodes["2"].SetNthControlPointPosition(1, 4.0, 0.0, 0.0)

            # Branch 2 now runs along +R: 90 degrees from the parent, 130 from branch 3.
            self.assertAlmostEqual(angleNodes[("0", "2")].GetAngleDegrees(), 90.0, delta=0.01)
            self.assertAlmostEqual(angleNodes[("2", "3")].GetAngleDegrees(), 130.0, delta=0.01)
            # The pair that does not contain branch 2 must not have moved.
            self.assertAlmostEqual(angleNodes[("0", "3")].GetAngleDegrees(), 140.0, delta=0.01)
            for pair in (("0", "2"), ("2", "3")):
                self.assertAlmostEqual(float(angleNodes[pair].GetAttribute("AngleDegrees")),
                                       angleNodes[pair].GetAngleDegrees())
            # The vertex of an angle stays at the bifurcation reference system origin.
            for angleNode in angleNodes.values():
                for coordinate in angleNode.GetNthControlPointPositionWorld(1):
                    self.assertAlmostEqual(coordinate, 0.0)
        finally:
            widget.cleanup()

    def test_ResetSelectedVector(self):
        """Reset restores a vector and its angles, and asks for a selection when there is none."""
        widget = self.bifurcationAnnotationWidget()
        try:
            requests = []
            infoDisplay = slicer.util.infoDisplay
            slicer.util.infoDisplay = lambda text, *args, **keywordArguments: requests.append(text)
            try:
                widget.onResetSelectedVector()
                self.assertEqual(len(requests), 1)

                vectorNode = self.vectorNodesByBranchGroupId(widget)["2"]
                angleNode = self.angleNodesByBranchGroupIdPair(widget)[("0", "2")]
                generatedPositions = [float(value) for value
                                      in vectorNode.GetAttribute("GeneratedControlPointPositions").split()]
                self.assertEqual(len(generatedPositions), 6)
                vectorNode.SetNthControlPointSelected(1, True)
                vectorNode.SetNthControlPointPosition(1, 4.0, 0.0, 0.0)
                self.assertAlmostEqual(angleNode.GetAngleDegrees(), 90.0, delta=0.01)

                widget.onResetSelectedVector()
                self.assertEqual(len(requests), 1)
                for pointIndex in range(2):
                    position = vectorNode.GetNthControlPointPositionWorld(pointIndex)
                    for actual, expected in zip(position, generatedPositions[3 * pointIndex:3 * pointIndex + 3]):
                        self.assertAlmostEqual(actual, expected)
                self.assertAlmostEqual(angleNode.GetAngleDegrees(),
                                       float(angleNode.GetAttribute("GeneratedAngleDegrees")), delta=0.01)
            finally:
                slicer.util.infoDisplay = infoDisplay
        finally:
            widget.cleanup()

    def test_SnapToCenterline(self):
        """A dragged vector endpoint is held on its own branch, within the reach of the snap."""
        # Branch 2 runs along +A through the junction. Branch 3 is laid right next to the
        # position dragged to below, so a snap that searched the whole tree would take it.
        branch2Polyline = [[0.0, float(index) - 5.0, 0.0] for index in range(11)]
        branch3Polyline = [[5.9, 2.0, 3.0 + 0.5 * index] for index in range(-4, 5)]
        widget = self.bifurcationAnnotationWidget(
            branchPolylines={0: [[0.0, -9.0, 0.0], [0.0, 0.0, 0.0]], 2: branch2Polyline, 3: branch3Polyline})
        try:
            vectorNode = self.vectorNodesByBranchGroupId(widget)["2"]
            self.assertEqual(float(vectorNode.GetAttribute("GeneratedVectorLength")), 4.0)
            untouched = list(vectorNode.GetNthControlPointPositionWorld(0))
            vectorNode.GetDisplayNode().SetActiveComponent(
                slicer.vtkMRMLMarkupsDisplayNode.ComponentControlPoint, 1)
            widget.ui.snapToCenterline.checked = True

            # 6.7 mm from branch 2 and 0.1 mm from branch 3: it must land on branch 2.
            vectorNode.SetNthControlPointPosition(1, 6.0, 2.0, 3.0)
            snapped = list(vectorNode.GetNthControlPointPositionWorld(1))
            self.assertAlmostEqual(snapped[0], 0.0)
            self.assertAlmostEqual(snapped[1], 2.0)
            self.assertAlmostEqual(snapped[2], 0.0)
            # The end that was not dragged must not have moved.
            for actual, expected in zip(vectorNode.GetNthControlPointPositionWorld(0), untouched):
                self.assertAlmostEqual(actual, expected)
            # The angles of the branch follow the snapped direction: +A from the junction
            # is straight on from the parent branch.
            angleNode = self.angleNodesByBranchGroupIdPair(widget)[("0", "2")]
            self.assertAlmostEqual(angleNode.GetAngleDegrees(), 180.0, delta=0.01)

            # A miss larger than the reach of the snap is deliberate and is left alone.
            outOfReach = maximumSnapDistanceInVectorLengths * 4.0 + 10.0
            vectorNode.SetNthControlPointPosition(1, outOfReach, 2.0, 0.0)
            for actual, expected in zip(vectorNode.GetNthControlPointPositionWorld(1), (outOfReach, 2.0, 0.0)):
                self.assertAlmostEqual(actual, expected)

            # With snapping off the endpoint stays where it was put, in reach or not.
            widget.ui.snapToCenterline.checked = False
            vectorNode.SetNthControlPointPosition(1, 6.0, 2.0, 3.0)
            for actual, expected in zip(vectorNode.GetNthControlPointPositionWorld(1), (6.0, 2.0, 3.0)):
                self.assertAlmostEqual(actual, expected)

            # A vector that carries no branch centerline is left alone.
            widget.ui.snapToCenterline.checked = True
            vectorNode.SetAttribute("BranchCenterlinePositions", "")
            vectorNode.SetNthControlPointPosition(1, 1.0, 1.0, 4.0)
            for actual, expected in zip(vectorNode.GetNthControlPointPositionWorld(1), (1.0, 1.0, 4.0)):
                self.assertAlmostEqual(actual, expected)
        finally:
            widget.cleanup()

    def test_SnapAlongSight(self):
        """Aiming picks the part of a branch under the cursor, not the part nearest in space."""
        # A branch that runs away from the camera at x = 2 and then crosses to the line of
        # sight far away, with the viewer looking along +S from the handle at the origin.
        polyline = [[2.0, 0.0, 0.0], [2.0, 0.0, 30.0], [0.0, 0.0, 30.0]]
        handle = [0.0, 0.0, 0.0]
        sightDirection = [0.0, 0.0, 1.0]

        # Nearest in space is the near limb, 2 mm to the side of where the user is pointing.
        inSpace, distance = CenterlineJunctionAnglesWidget.closestPositionOnPolyline(polyline, handle)
        self.assertAlmostEqual(distance, 2.0)
        self.assertAlmostEqual(inSpace[0], 2.0)

        # Along the line of sight it is the far limb, which is the one under the cursor.
        alongSight, offset = CenterlineJunctionAnglesWidget.closestPositionAlongSight(
            polyline, handle, sightDirection)
        self.assertAlmostEqual(offset, 0.0)
        self.assertAlmostEqual(alongSight[0], 0.0)
        self.assertAlmostEqual(alongSight[2], 30.0)

        # A branch lying along the line of sight is aimed at everywhere, so the near end wins.
        alongSight, offset = CenterlineJunctionAnglesWidget.closestPositionAlongSight(
            [[0.0, 0.0, 5.0], [0.0, 0.0, 50.0]], handle, sightDirection)
        self.assertAlmostEqual(offset, 0.0)
        self.assertAlmostEqual(alongSight[2], 5.0)

        self.assertEqual(CenterlineJunctionAnglesWidget.closestPositionAlongSight(
            [[0.0, 0.0, 0.0]], handle, sightDirection), (None, None))
        self.assertEqual(CenterlineJunctionAnglesWidget.closestPositionOnPolyline([[0.0, 0.0, 0.0]], handle),
                         (None, None))

    def test_BranchPolylines(self):
        """Each branch group gives one curve, its longest tract; bifurcation regions give none."""
        splitCenterlines = vtk.vtkPolyData()
        points = vtk.vtkPoints()
        lines = vtk.vtkCellArray()
        # Group 0 twice, the second tract longer; group 1 blanked; group 2 once.
        for tract in ([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)],
                      [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)],
                      [(2.0, 0.0, 0.0), (3.0, 0.0, 0.0)],
                      [(3.0, 0.0, 0.0), (4.0, 0.0, 0.0)]):
            lines.InsertNextCell(len(tract))
            for position in tract:
                lines.InsertCellPoint(points.InsertNextPoint(position))
        splitCenterlines.SetPoints(points)
        splitCenterlines.SetLines(lines)
        for name, values in ((groupIdsArrayName, [0, 0, 1, 2]), (blankingArrayName, [0, 0, 1, 0])):
            array = vtk.vtkIntArray()
            array.SetName(name)
            for value in values:
                array.InsertNextValue(value)
            splitCenterlines.GetCellData().AddArray(array)

        polylines = CenterlineJunctionAnglesLogic.computeBranchPolylines(splitCenterlines)
        self.assertEqual(sorted(polylines), [0, 2])
        self.assertEqual(len(polylines[0]), 3)
        self.assertEqual(len(polylines[2]), 2)
        self.assertEqual(CenterlineJunctionAnglesLogic.computeBranchPolylines(None), {})

    def test_VectorControlPointsSurviveDeletion(self):
        """A vector keeps its two ends, and a stripped one is put back together."""
        widget = self.bifurcationAnnotationWidget()
        try:
            vectorNode = self.vectorNodesByBranchGroupId(widget)["2"]
            self.assertTrue(vectorNode.GetFixedNumberOfControlPoints())
            generated = [float(value) for value
                         in vectorNode.GetAttribute("GeneratedControlPointPositions").split()]
            # Deleting an end of the measurement must not be possible.
            vectorNode.RemoveNthControlPoint(0)
            self.assertEqual(vectorNode.GetNumberOfControlPoints(), 2)

            # A vector stripped by an older version is repaired when it is seen again.
            vectorNode.SetFixedNumberOfControlPoints(False)
            vectorNode.RemoveAllControlPoints()
            self.assertEqual(vectorNode.GetNumberOfControlPoints(), 0)
            widget.releaseVectorObservations()
            list(widget.annotationDisplayNodes())
            self.assertEqual(vectorNode.GetNumberOfControlPoints(), 2)
            for pointIndex in range(2):
                for actual, expected in zip(vectorNode.GetNthControlPointPositionWorld(pointIndex),
                                            generated[3 * pointIndex:3 * pointIndex + 3]):
                    self.assertAlmostEqual(actual, expected)
        finally:
            widget.cleanup()

    def test_VectorMarkupObservationLifetime(self):
        """A vector that leaves the scene must not stay observed, and alive, in the widget."""
        widget = self.bifurcationAnnotationWidget()
        try:
            vectorNodes = list(self.vectorNodesByBranchGroupId(widget).values())
            self.assertEqual(len(widget._observedVectorMarkupIds), len(vectorNodes))
            slicer.mrmlScene.RemoveNode(vectorNodes[0])
            self.assertEqual(len(widget._observedVectorMarkupIds), len(vectorNodes) - 1)
            slicer.mrmlScene.Clear()
            self.assertFalse(widget._observedVectorMarkupIds)
            self.assertFalse([observation for observation in widget.Observations
                              if observation[2] == widget._vectorMarkupModifiedCallback])
        finally:
            widget.cleanup()

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
        # Both bifurcations report all of their angles in their own generation.
        self.assertEqual(orderByPair[(1, 0, 2)], 0)
        self.assertEqual(orderByPair[(1, 0, 3)], 0)
        self.assertEqual(orderByPair[(1, 2, 3)], 0)
        self.assertEqual(orderByPair[(5, 2, 4)], 1)
        self.assertEqual(orderByPair[(5, 2, 5)], 1)
        self.assertEqual(orderByPair[(5, 4, 5)], 1)

        self.delayDisplay(_("Test passed"))

    def test_BranchOrderUsesCompleteTopology(self):
        """A missing angle junction must not create a false downstream root."""
        splitCenterlines = vtk.vtkPolyData()
        lines = vtk.vtkCellArray()
        points = vtk.vtkPoints()
        for cellId in range(9):
            pointId = points.InsertNextPoint(float(cellId), 0.0, 0.0)
            lines.InsertNextCell(1)
            lines.InsertCellPoint(pointId)
        splitCenterlines.SetPoints(points)
        splitCenterlines.SetVerts(lines)

        def addCellArray(name, values):
            array = vtk.vtkIntArray()
            array.SetName(name)
            for value in values:
                array.InsertNextValue(value)
            splitCenterlines.GetCellData().AddArray(array)

        # Two source-to-target paths share branch 0. The first passes through
        # branches 2 and 4; the second passes through branches 3 and 5. Blanked
        # groups represent their intervening bifurcation regions.
        addCellArray(centerlineIdsArrayName, [0, 0, 0, 0, 0, 1, 1, 1, 1])
        addCellArray(tractIdsArrayName, [0, 1, 2, 3, 4, 0, 1, 2, 3])
        addCellArray(groupIdsArrayName, [0, 1, 2, 6, 4, 0, 1, 3, 5])
        addCellArray(blankingArrayName, [0, 1, 0, 1, 0, 0, 1, 0, 0])

        orders = CenterlineJunctionAnglesLogic.computeBranchOrders(splitCenterlines)
        self.assertEqual(orders, {0: 0, 2: 1, 3: 1, 4: 2, 5: 2})

        # Simulate angle-vector output that omitted the junction between groups
        # 2 and 4. Group 4 still retains order 2 from the complete topology.
        bifurcations = self.createBifurcationVectors()
        downstream = self.createBifurcationVectors()
        downstream[0]["bifurcationGroupId"] = 6
        downstream[0]["branches"][4] = downstream[0]["branches"].pop(0)
        downstream[0]["branches"][4]["groupId"] = 4
        downstream[0]["branches"][4]["role"] = "Parent"
        downstream[0]["branches"][5] = downstream[0]["branches"].pop(2)
        downstream[0]["branches"][5]["groupId"] = 5
        downstream[0]["branches"][6] = downstream[0]["branches"].pop(3)
        downstream[0]["branches"][6]["groupId"] = 6
        CenterlineJunctionAnglesLogic.assignBranchOrders(bifurcations + downstream, orders)
        self.assertEqual(downstream[0]["branches"][4]["branchOrder"], 2)
        self.assertEqual(downstream[0]["branches"][5]["branchOrder"], 2)

        # Branch extraction output that is missing an array must be reported as such.
        splitCenterlines.GetCellData().RemoveArray(tractIdsArrayName)
        with self.assertRaisesRegex(ValueError, tractIdsArrayName):
            CenterlineJunctionAnglesLogic.computeBranchOrders(splitCenterlines)

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
                          for junctionAngle in junctionAngles], [(0, 1, 0), (0, 1, 0), (1, 1, 0)])
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


# Check boxes whose state is saved in the parameter node, and so with the scene
savedCheckBoxNames = ("showAnnotations", "showVectors", "showParentChild", "showChildChild", "snapToCenterline")
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
# How far the aim may miss the branch of a dragged handle and still snap to it, in vector
# lengths. A vector is of the order of the local vessel radius, which is well under a
# millimetre in a distal vessel, so the reach has to be a generous multiple of it to be
# usable. A miss larger than this is taken to be a deliberate move off the centerline.
# Nothing worse than sliding along its own branch can happen to a handle, so this is a
# comfort setting rather than a guard.
maximumSnapDistanceInVectorLengths = 6.0
# Two places of a branch aimed at within this distance of each other, in mm, are taken
# to be aimed at equally well, and the nearer of them is the one snapped to
sightTieTolerance = 0.5
# A handle already this close to its branch, in mm, is not written back onto itself
snapTolerance = 1e-4
# Points of a branch centerline stored on a vector, enough to snap to a long branch
maximumStoredBranchPoints = 400
# Style of the junction angle annotations. The markup control points are drawn this many times longer
# than the measured segments, and the text is larger than the default scale of 3.0.
bifurcationVectorColor = [1.0, 0.5, 0.0]
bifurcationVectorLineThickness = 0.5
bifurcationVectorGlyphScale = 1.2
bifurcationVectorOpacity = 0.8
junctionAngleRayScale = 2.0
junctionAngleRayScaleStep = 0.4
junctionAngleTextScale = 5.0
# How much of an annotation is seen where the vessel surface hides it
occludedOpacity = 0.6
