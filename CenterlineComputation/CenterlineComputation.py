# slicer imports
import os
import unittest
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
import logging

# python includes
import math


#
# Centerline Computation using VMTK based Tools
#

class CenterlineComputation(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Centerline Computation"
        self.parent.categories = ["Vascular Modeling Toolkit"]
        self.parent.dependencies = []
        self.parent.contributors = ["Daniel Haehn (Boston Children's Hospital)", "Luca Antiga (Orobix)",
                                    "Steve Pieper (Isomics)", "Andras Lasso (PerkLab)"]
        self.parent.helpText = """
"""
        self.parent.acknowledgementText = """
"""  # replace with organization, grant and thanks.


class CenterlineComputationWidget(ScriptedLoadableModuleWidget):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None):
        ScriptedLoadableModuleWidget.__init__(self, parent)

        # the pointer to the logic
        self.logic = CenterlineComputationLogic()

        if not parent:
            # after setup, be ready for events
            self.parent.show()
        else:
            # register default slots
            self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)', self.onMRMLSceneChanged)

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)

        #
        # Inputs
        #

        inputsCollapsibleButton = ctk.ctkCollapsibleButton()
        inputsCollapsibleButton.text = "Inputs"
        self.layout.addWidget(inputsCollapsibleButton)
        inputsFormLayout = qt.QFormLayout(inputsCollapsibleButton)

        # inputVolume selector
        self.inputModelNodeSelector = slicer.qMRMLNodeComboBox()
        self.inputModelNodeSelector.objectName = 'inputModelNodeSelector'
        self.inputModelNodeSelector.toolTip = "Select the input model."
        self.inputModelNodeSelector.nodeTypes = ['vtkMRMLModelNode']
        self.inputModelNodeSelector.hideChildNodeTypes = ['vtkMRMLAnnotationNode']  # hide all annotation nodes
        self.inputModelNodeSelector.noneEnabled = False
        self.inputModelNodeSelector.addEnabled = False
        self.inputModelNodeSelector.removeEnabled = False
        inputsFormLayout.addRow("Vessel tree model:", self.inputModelNodeSelector)
        self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                            self.inputModelNodeSelector, 'setMRMLScene(vtkMRMLScene*)')

        # seed selector
        self.seedFiducialsNodeSelector = slicer.qSlicerSimpleMarkupsWidget()
        self.seedFiducialsNodeSelector.objectName = 'seedFiducialsNodeSelector'
        self.seedFiducialsNodeSelector = slicer.qSlicerSimpleMarkupsWidget()
        self.seedFiducialsNodeSelector.objectName = 'seedFiducialsNodeSelector'
        self.seedFiducialsNodeSelector.toolTip = "Select a fiducial to use as the origin of the Centerline."
        self.seedFiducialsNodeSelector.setNodeBaseName("OriginSeed")
        self.seedFiducialsNodeSelector.defaultNodeColor = qt.QColor(0, 255, 0)
        self.seedFiducialsNodeSelector.tableWidget().hide()
        self.seedFiducialsNodeSelector.markupsSelectorComboBox().noneEnabled = False
        self.seedFiducialsNodeSelector.markupsPlaceWidget().placeMultipleMarkups = slicer.qSlicerMarkupsPlaceWidget.ForcePlaceSingleMarkup
        inputsFormLayout.addRow("Start point:", self.seedFiducialsNodeSelector)
        self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                            self.seedFiducialsNodeSelector, 'setMRMLScene(vtkMRMLScene*)')

        #
        # Outputs
        #

        outputsCollapsibleButton = ctk.ctkCollapsibleButton()
        outputsCollapsibleButton.text = "Outputs"
        self.layout.addWidget(outputsCollapsibleButton)
        outputsFormLayout = qt.QFormLayout(outputsCollapsibleButton)

        # outputModel selector
        self.outputModelNodeSelector = slicer.qMRMLNodeComboBox()
        self.outputModelNodeSelector.objectName = 'outputModelNodeSelector'
        self.outputModelNodeSelector.toolTip = "Select the output model for the Centerlines."
        self.outputModelNodeSelector.nodeTypes = ['vtkMRMLModelNode']
        self.outputModelNodeSelector.baseName = "CenterlineComputationModel"
        self.outputModelNodeSelector.hideChildNodeTypes = ['vtkMRMLAnnotationNode']  # hide all annotation nodes
        self.outputModelNodeSelector.noneEnabled = True
        self.outputModelNodeSelector.noneDisplay = "Create new model"
        self.outputModelNodeSelector.addEnabled = True
        self.outputModelNodeSelector.renameEnabled = True
        self.outputModelNodeSelector.selectNodeUponCreation = True
        self.outputModelNodeSelector.removeEnabled = True
        outputsFormLayout.addRow("Centerline model:", self.outputModelNodeSelector)
        self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                            self.outputModelNodeSelector, 'setMRMLScene(vtkMRMLScene*)')

        self.outputEndPointsNodeSelector = slicer.qMRMLNodeComboBox()
        self.outputEndPointsNodeSelector.objectName = 'outputEndPointsNodeSelector'
        self.outputEndPointsNodeSelector.toolTip = "Select the output model for the Centerlines."
        self.outputEndPointsNodeSelector.nodeTypes = ['vtkMRMLMarkupsFiducialNode']
        self.outputEndPointsNodeSelector.baseName = "Centerline endpoints"
        self.outputEndPointsNodeSelector.noneEnabled = True
        self.outputEndPointsNodeSelector.noneDisplay = "Create new markups fiducial"
        self.outputEndPointsNodeSelector.addEnabled = True
        self.outputEndPointsNodeSelector.renameEnabled = True
        self.outputEndPointsNodeSelector.selectNodeUponCreation = True
        self.outputEndPointsNodeSelector.removeEnabled = True
        outputsFormLayout.addRow("Centerline endpoints:", self.outputEndPointsNodeSelector)
        self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                            self.outputEndPointsNodeSelector, 'setMRMLScene(vtkMRMLScene*)')

        if slicer.app.majorVersion * 100 + slicer.app.minorVersion >= 411:
            # curve node selector
            self.rootCurveNodeSelector = slicer.qMRMLNodeComboBox()
            self.rootCurveNodeSelector.objectName = 'rootCurveNodeSelector'
            self.rootCurveNodeSelector.toolTip = "Select a markups curve node to export results into a hierarchy of markups curves. CellId is added to the node name in parentheses."
            self.rootCurveNodeSelector.nodeTypes = ['vtkMRMLMarkupsCurveNode']
            self.rootCurveNodeSelector.baseName = "tree"
            self.rootCurveNodeSelector.noneEnabled = True
            self.rootCurveNodeSelector.addEnabled = True
            self.rootCurveNodeSelector.renameEnabled = True
            self.rootCurveNodeSelector.selectNodeUponCreation = True
            self.rootCurveNodeSelector.removeEnabled = True
            outputsFormLayout.addRow("Curve tree root:", self.rootCurveNodeSelector)
            self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                                self.rootCurveNodeSelector, 'setMRMLScene(vtkMRMLScene*)')

            # centerline properties table node selector
            self.centerlinePropertiesTableNodeSelector = slicer.qMRMLNodeComboBox()
            self.centerlinePropertiesTableNodeSelector.objectName = 'centerlinePropertiesTableNodeSelector'
            self.centerlinePropertiesTableNodeSelector.toolTip = "Select a table node that will store centerline quantification results."
            self.centerlinePropertiesTableNodeSelector.nodeTypes = ['vtkMRMLTableNode']
            self.centerlinePropertiesTableNodeSelector.baseName = "CenterlineProperties"
            self.centerlinePropertiesTableNodeSelector.noneEnabled = True
            self.centerlinePropertiesTableNodeSelector.addEnabled = True
            self.centerlinePropertiesTableNodeSelector.renameEnabled = True
            self.centerlinePropertiesTableNodeSelector.selectNodeUponCreation = True
            self.centerlinePropertiesTableNodeSelector.removeEnabled = True
            outputsFormLayout.addRow("Centerline properties:", self.centerlinePropertiesTableNodeSelector)
            self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                                self.centerlinePropertiesTableNodeSelector, 'setMRMLScene(vtkMRMLScene*)')

        #
        # Advanced outputs
        #
        advancedOutputsCollapsibleButton = ctk.ctkCollapsibleButton()
        advancedOutputsCollapsibleButton.text = "Advanced outputs"
        advancedOutputsCollapsibleButton.collapsed = True
        self.layout.addWidget(advancedOutputsCollapsibleButton)
        advancedOutputsFormLayout = qt.QFormLayout(advancedOutputsCollapsibleButton)


        # voronoiModel selector
        self.voronoiModelNodeSelector = slicer.qMRMLNodeComboBox()
        self.voronoiModelNodeSelector.objectName = 'voronoiModelNodeSelector'
        self.voronoiModelNodeSelector.toolTip = "Select the output model for the Voronoi Diagram."
        self.voronoiModelNodeSelector.nodeTypes = ['vtkMRMLModelNode']
        self.voronoiModelNodeSelector.baseName = "VoronoiModel"
        self.voronoiModelNodeSelector.hideChildNodeTypes = ['vtkMRMLAnnotationNode']  # hide all annotation nodes
        self.voronoiModelNodeSelector.noneEnabled = True
        self.voronoiModelNodeSelector.addEnabled = True
        self.voronoiModelNodeSelector.renameEnabled = True
        self.voronoiModelNodeSelector.selectNodeUponCreation = True
        self.voronoiModelNodeSelector.removeEnabled = True
        advancedOutputsFormLayout.addRow("Voronoi Model:", self.voronoiModelNodeSelector)
        self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                            self.voronoiModelNodeSelector, 'setMRMLScene(vtkMRMLScene*)')

        # non-manifold edges selector
        self.nonManifoldEdgesModelNodeSelector = slicer.qMRMLNodeComboBox()
        self.nonManifoldEdgesModelNodeSelector.objectName = 'nonManifoldEdgesModelNodeSelector'
        self.nonManifoldEdgesModelNodeSelector.toolTip = ("Select the output model for storing detected non-manifold edges."
                                                          + "Non-manifold edges indicate mesh errors, which may make centerline detection fail.")
        self.nonManifoldEdgesModelNodeSelector.nodeTypes = ['vtkMRMLModelNode']
        self.nonManifoldEdgesModelNodeSelector.baseName = "Non-manifold edges"
        #self.nonManifoldEdgesModelNodeSelector.hideChildNodeTypes = ['vtkMRMLAnnotationNode']  # hide all annotation nodes
        self.nonManifoldEdgesModelNodeSelector.noneEnabled = True
        self.nonManifoldEdgesModelNodeSelector.addEnabled = True
        self.nonManifoldEdgesModelNodeSelector.renameEnabled = True
        self.nonManifoldEdgesModelNodeSelector.selectNodeUponCreation = True
        self.nonManifoldEdgesModelNodeSelector.removeEnabled = True
        advancedOutputsFormLayout.addRow("Non-manifold edges:", self.nonManifoldEdgesModelNodeSelector)
        self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)',
                            self.nonManifoldEdgesModelNodeSelector, 'setMRMLScene(vtkMRMLScene*)')

        #
        # Reset, preview and apply buttons
        #

        self.buttonBox = qt.QDialogButtonBox()
        self.previewButton = self.buttonBox.addButton(self.buttonBox.Discard)
        self.previewButton.setIcon(qt.QIcon())
        self.previewButton.text = "Preview"
        self.previewButton.toolTip = "Click to refresh the preview."
        self.startButton = self.buttonBox.addButton(self.buttonBox.Apply)
        self.startButton.setIcon(qt.QIcon())
        self.startButton.text = "Start"
        self.startButton.enabled = False
        self.startButton.toolTip = "Click to start the filtering."
        self.layout.addWidget(self.buttonBox)
        self.previewButton.connect("clicked()", self.onPreviewButtonClicked)
        self.startButton.connect("clicked()", self.onStartButtonClicked)

        self.inputModelNodeSelector.setMRMLScene(slicer.mrmlScene)
        self.seedFiducialsNodeSelector.setMRMLScene(slicer.mrmlScene)
        self.outputModelNodeSelector.setMRMLScene(slicer.mrmlScene)
        self.outputEndPointsNodeSelector.setMRMLScene(slicer.mrmlScene)
        self.voronoiModelNodeSelector.setMRMLScene(slicer.mrmlScene)
        self.nonManifoldEdgesModelNodeSelector.setMRMLScene(slicer.mrmlScene)
        if slicer.app.majorVersion * 100 + slicer.app.minorVersion >= 411:
            self.rootCurveNodeSelector.setMRMLScene(slicer.mrmlScene)
            self.centerlinePropertiesTableNodeSelector.setMRMLScene(slicer.mrmlScene)

        # compress the layout
        self.layout.addStretch(1)

    def onMRMLSceneChanged(self):
        logging.debug("onMRMLSceneChanged")

    def onStartButtonClicked(self):
        self.start(False)

    def onPreviewButtonClicked(self):
        self.start(True)

    def start(self, preview):
        logging.debug("Starting Centerline Computation..")
        qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)
        try:
            # first we need the nodes
            currentModelNode = self.inputModelNodeSelector.currentNode()
            currentSeedsNode = self.seedFiducialsNodeSelector.currentNode()
            currentOutputModelNode = self.outputModelNodeSelector.currentNode()
            currentEndPointsMarkupsNode = self.outputEndPointsNodeSelector.currentNode()
            currentVoronoiModelNode = self.voronoiModelNodeSelector.currentNode()
            nonManifoldEdgesModelNode = self.nonManifoldEdgesModelNodeSelector.currentNode()
            if slicer.app.majorVersion * 100 + slicer.app.minorVersion >= 411:
                rootCurveNode = self.rootCurveNodeSelector.currentNode()
                centerlinePropertiesTableNode = self.centerlinePropertiesTableNodeSelector.currentNode()
            else:
                rootCurveNode = None
                centerlinePropertiesTableNode = None

            if not currentOutputModelNode or currentOutputModelNode.GetID() == currentModelNode.GetID():
                # we need a current model node, the display node is created later
                newModelNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLModelNode")
                newModelNode.UnRegister(None)
                newModelNode.SetName(slicer.mrmlScene.GetUniqueNameByString(self.outputModelNodeSelector.baseName))
                currentOutputModelNode = slicer.mrmlScene.AddNode(newModelNode)
                currentOutputModelNode.CreateDefaultDisplayNodes()
                currentOutputModelNode.GetDisplayNode().SetColor(0.0, 0.0, 1.0)
                self.outputModelNodeSelector.setCurrentNode(currentOutputModelNode)

            if not currentEndPointsMarkupsNode or currentEndPointsMarkupsNode.GetID() == currentSeedsNode.GetID():
                # we need a current seed node, the display node is created later
                currentEndPointsMarkupsNode = slicer.mrmlScene.GetNodeByID(
                    slicer.modules.markups.logic().AddNewFiducialNode("Centerline endpoints"))
                self.outputEndPointsNodeSelector.setCurrentNode(currentEndPointsMarkupsNode)

            self.logic.extractCenterline(currentModelNode, currentSeedsNode, currentOutputModelNode,
                              currentEndPointsMarkupsNode, currentVoronoiModelNode, nonManifoldEdgesModelNode,
                              rootCurveNode, centerlinePropertiesTableNode, preview)

            self.startButton.enabled = True
        except Exception as e:
            slicer.util.errorDisplay(str(e))
            import traceback
            traceback.print_exc()
        qt.QApplication.restoreOverrideCursor()


class CenterlineComputationLogic(object):
    '''
    classdocs
    '''

    def __init__(self):
        '''
        Constructor
        '''
        self.blankingArrayName = 'Blanking'
        self.radiusArrayName = 'Radius'  # maximum inscribed sphere radius
        self.groupIdsArrayName = 'GroupIds'
        self.centerlineIdsArrayName = 'CenterlineIds'
        self.tractIdsArrayName = 'TractIds'
        self.topologyArrayName = 'Topology'
        self.marksArrayName = 'Marks'
        self.lengthArrayName = 'Length'
        self.curvatureArrayName = 'Curvature'
        self.torsionArrayName = 'Torsion'
        self.tortuosityArrayName = 'Tortuosity'

    def extractCenterline(self, currentModelNode, currentSeedsNode, currentOutputModelNode, currentEndPointsMarkupsNode,
                          currentVoronoiModelNode, nonManifoldEdgesModelNode, rootCurveNode, centerlinePropertiesTableNode, preview=False):
        logging.debug("Starting Centerline Computation..")

        if not currentModelNode:
            # we need a input volume node
            raise ValueError("Input model node required")

        if not currentSeedsNode:
            # we need a seeds node
            raise ValueError("Input seeds node required")

        # the output models
        preparedModel = vtk.vtkPolyData()
        model = vtk.vtkPolyData()
        network = vtk.vtkPolyData()
        voronoi = vtk.vtkPolyData()

        nonManifoldEdges = None
        if nonManifoldEdgesModelNode:
            if not nonManifoldEdgesModelNode.GetPolyData():
                nonManifoldEdgesModelNode.SetAndObservePolyData(vtk.vtkPolyData())
            if not nonManifoldEdgesModelNode.GetDisplayNode():
                nonManifoldEdgesModelNode.CreateDefaultDisplayNodes()
                nonManifoldEdgesModelNode.GetDisplayNode().SetColor(1.0,0.0,0.0)
                nonManifoldEdgesModelNode.GetDisplayNode().SetLineWidth(10)
            nonManifoldEdges = nonManifoldEdgesModelNode.GetPolyData()

        currentCoordinatesRAS = [0, 0, 0]

        # grab the current coordinates
        currentSeedsNode.GetNthFiducialPosition(0, currentCoordinatesRAS)

        # prepare the model
        preparedModel.DeepCopy(self.prepareModel(currentModelNode.GetPolyData(), subdivide=True, nonManifoldEdges=nonManifoldEdges))
        if nonManifoldEdgesModelNode:
            numberOfNonManifoldEdges = nonManifoldEdgesModelNode.GetPolyData().GetNumberOfCells()
            if numberOfNonManifoldEdges>0:
                logging.error("Found {0} non-manifold edges. Centerline computation may fail.".format(numberOfNonManifoldEdges))

        if preparedModel.GetNumberOfPoints() == 0:
            raise ValueError("Input model preparation failed. It probably has surface errors.")

        # decimate the model (only for network extraction)
        model.DeepCopy(self.decimateSurface(preparedModel))

        # open the model at the seed (only for network extraction)
        self.openSurfaceAtPoint(model, currentCoordinatesRAS)

        # extract Network
        network.DeepCopy(self.extractNetwork(model))

        #
        #
        # not preview mode: real computation!
        if not preview:
            # here we start the actual centerline computation which is mathematically more robust and accurate but takes longer than the network extraction

            # clip surface at endpoints identified by the network extraction
            clippedSurface, endpoints = self.clipSurfaceAtEndPoints(network, preparedModel) # old: currentModelNode.GetPolyData()

            # now find the one endpoint which is closest to the seed and use it as the source point for centerline computation
            # all other endpoints are the target points
            sourcePoint = [0, 0, 0]

            # the following arrays have the same indexes and are synchronized at all times
            distancesToSeed = []
            targetPoints = []

            # Get distances of points from source point
            for i in range(endpoints.GetNumberOfPoints()):
                currentPoint = endpoints.GetPoint(i)
                # get the euclidean distance
                currentDistanceToSeed = math.sqrt(math.pow((currentPoint[0] - currentCoordinatesRAS[0]), 2) +
                                                  math.pow((currentPoint[1] - currentCoordinatesRAS[1]), 2) +
                                                  math.pow((currentPoint[2] - currentCoordinatesRAS[2]), 2))

                targetPoints.append(currentPoint)
                distancesToSeed.append(currentDistanceToSeed)

            # For some reason, closest endpoint was ignored in the original implementation, as it was some kind of
            # "hole point", but in closed surfaces created by segmentation we don't have such hole points, so
            # by default we don't ignore it.
            ignoreClosestEndPoint = False

            if ignoreClosestEndPoint:
                # endpoint resulting in the tiny hole we poked in the surface
                # this is very close to our seed but not the correct sourcePoint,
                # ignore it
                holePointIndex = distancesToSeed.index(min(distancesToSeed))
                # .. and remove it
                distancesToSeed.pop(holePointIndex)
                targetPoints.pop(holePointIndex)

            # the index with minimal distance is the point closest to the seed, we want to set it as sourcepoint
            # all other points are the targetpoints
            sourcePointIndex = distancesToSeed.index(min(distancesToSeed))
            # .. and remove it after saving it as the sourcePoint
            sourcePoint = targetPoints[sourcePointIndex]
            distancesToSeed.pop(sourcePointIndex)
            targetPoints.pop(sourcePointIndex)

            # at this point we have the sourcePoint and a list of real targetPoints

            # now create the sourceIdList and targetIdList for the actual centerline computation
            sourceIdList = vtk.vtkIdList()
            targetIdList = vtk.vtkIdList()

            pointLocator = vtk.vtkPointLocator()
            pointLocator.SetDataSet(clippedSurface)
            pointLocator.BuildLocator()

            # locate the source on the surface
            sourceId = pointLocator.FindClosestPoint(sourcePoint)
            sourceIdList.InsertNextId(sourceId)

            currentEndPointsMarkupsNode.GetDisplayNode().SetTextScale(0)
            currentEndPointsMarkupsNode.RemoveAllMarkups()

            currentEndPointsMarkupsNode.AddFiducialFromArray(sourcePoint)

            # locate the endpoints on the surface
            for p in targetPoints:
                fid = currentEndPointsMarkupsNode.AddFiducialFromArray(p)
                currentEndPointsMarkupsNode.SetNthFiducialSelected(fid, False)
                id = pointLocator.FindClosestPoint(p)
                targetIdList.InsertNextId(id)

            newNetwork, newVoronoi = self.computeCenterlines(clippedSurface, sourceIdList, targetIdList)

            network.DeepCopy(newNetwork)
            voronoi.DeepCopy(newVoronoi)

        currentOutputModelNode.SetAndObservePolyData(network)

        # Make model node semi-transparent to make centerline inside visible
        currentModelNode.CreateDefaultDisplayNodes()
        currentModelDisplayNode = currentModelNode.GetDisplayNode()
        currentModelDisplayNode.SetOpacity(0.4)

        if currentVoronoiModelNode:
            # Configure the displayNode to show the centerline and Voronoi model
            currentOutputModelNode.CreateDefaultDisplayNodes()
            currentOutputModelDisplayNode = currentOutputModelNode.GetDisplayNode()
            currentOutputModelDisplayNode.SetColor(0.0, 0.0, 0.4)  # red
            currentOutputModelDisplayNode.SetBackfaceCulling(0)
            currentOutputModelDisplayNode.SetSliceIntersectionVisibility(0)
            currentOutputModelDisplayNode.SetVisibility(1)
            currentOutputModelDisplayNode.SetOpacity(1.0)

        # only update the voronoi node if we are not in preview mode

        if currentVoronoiModelNode and not preview:
            currentVoronoiModelNode.SetAndObservePolyData(voronoi)
            currentVoronoiModelNode.CreateDefaultDisplayNodes()
            currentVoronoiModelDisplayNode = currentVoronoiModelNode.GetDisplayNode()

            # always configure the displayNode to show the model
            currentVoronoiModelDisplayNode.SetScalarVisibility(1)
            currentVoronoiModelDisplayNode.SetBackfaceCulling(0)
            currentVoronoiModelDisplayNode.SetActiveScalarName(self.radiusArrayName)
            currentVoronoiModelDisplayNode.SetAndObserveColorNodeID(
                slicer.mrmlScene.GetNodesByName("Labels").GetItemAsObject(0).GetID())
            currentVoronoiModelDisplayNode.SetSliceIntersectionVisibility(0)
            currentVoronoiModelDisplayNode.SetVisibility(1)
            currentVoronoiModelDisplayNode.SetOpacity(0.5)

        if (rootCurveNode or centerlinePropertiesTableNode) and not preview:
            self.createCurveTreeFromCenterline(currentOutputModelNode, rootCurveNode, centerlinePropertiesTableNode)

        logging.debug("End of Centerline Computation..")

        return True


    def prepareModel(self, polyData, subdivide=True, nonManifoldEdges=None):
        '''
        '''
        # import the vmtk libraries
        try:
            import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
            import vtkvmtkMiscPython as vtkvmtkMisc
        except ImportError:
            logging.error("Unable to import the SlicerVmtk libraries")

        capDisplacement = 0.0

        surfaceCleaner = vtk.vtkCleanPolyData()
        surfaceCleaner.SetInputData(polyData)
        surfaceCleaner.Update()

        surfaceTriangulator = vtk.vtkTriangleFilter()
        surfaceTriangulator.SetInputData(surfaceCleaner.GetOutput())
        surfaceTriangulator.PassLinesOff()
        surfaceTriangulator.PassVertsOff()
        surfaceTriangulator.Update()

        # new steps for preparation to avoid problems because of slim models (f.e. at stenosis)
        if subdivide:
            subdiv = vtk.vtkLinearSubdivisionFilter()
            subdiv.SetInputData(surfaceTriangulator.GetOutput())
            subdiv.SetNumberOfSubdivisions(1)
            subdiv.Update()
            if subdiv.GetOutput().GetNumberOfPoints() == 0:
                logging.warning("Mesh subdivision failed. Skip subdivision step.")
                subdivide = False

        smooth = vtk.vtkWindowedSincPolyDataFilter()
        if subdivide:
            smooth.SetInputData(subdiv.GetOutput())
        else:
            smooth.SetInputData(surfaceTriangulator.GetOutput())
        smooth.SetNumberOfIterations(20)
        smooth.SetPassBand(0.1)
        smooth.SetBoundarySmoothing(1)
        smooth.Update()

        normals = vtk.vtkPolyDataNormals()
        normals.SetInputData(smooth.GetOutput())
        normals.SetAutoOrientNormals(1)
        normals.SetFlipNormals(0)
        normals.SetConsistency(1)
        normals.SplittingOff()
        normals.Update()

        surfaceCapper = vtkvmtkComputationalGeometry.vtkvmtkCapPolyData()
        surfaceCapper.SetInputData(normals.GetOutput())
        surfaceCapper.SetDisplacement(capDisplacement)
        surfaceCapper.SetInPlaneDisplacement(capDisplacement)
        surfaceCapper.Update()

        outPolyData = vtk.vtkPolyData()
        outPolyData.DeepCopy(surfaceCapper.GetOutput())

        if nonManifoldEdges:
            self.checkNonManifoldSurface(outPolyData, nonManifoldEdges)

        return outPolyData


    def checkNonManifoldSurface(self, polyData, nonManifoldEdges):
        '''
        Returns pairs of point IDs with endpoints of non-manifold edgesin nonManifoldEdges.
        '''
        import vtkvmtkDifferentialGeometryPython as vtkvmtkDifferentialGeometry
        neighborhoods = vtkvmtkDifferentialGeometry.vtkvmtkNeighborhoods()
        neighborhoods.SetNeighborhoodTypeToPolyDataManifoldNeighborhood()
        neighborhoods.SetDataSet(polyData)
        neighborhoods.Build()

        polyData.BuildCells()
        polyData.BuildLinks(0)

        neighborCellIds = vtk.vtkIdList()
        nonManifoldEdgeLines = vtk.vtkCellArray()
        for i in range(neighborhoods.GetNumberOfNeighborhoods()):
            neighborhood = neighborhoods.GetNeighborhood(i)
            for j in range(neighborhood.GetNumberOfPoints()):
                neighborId = neighborhood.GetPointId(j)
                if i < neighborId:
                    neighborCellIds.Initialize()
                    polyData.GetCellEdgeNeighbors(-1,i,neighborId,neighborCellIds)
                    if neighborCellIds.GetNumberOfIds() > 2:
                        nonManifoldEdgeLines.InsertNextCell(2)
                        nonManifoldEdgeLines.InsertCellPoint(i)
                        nonManifoldEdgeLines.InsertCellPoint(neighborId)

        nonManifoldEdges.Initialize()
        points = vtk.vtkPoints()
        points.DeepCopy(polyData.GetPoints())
        nonManifoldEdges.SetPoints(points)
        nonManifoldEdges.SetLines(nonManifoldEdgeLines)


    def decimateSurface(self, polyData):
        '''
        '''

        decimationFilter = vtk.vtkDecimatePro()
        decimationFilter.SetInputData(polyData)
        decimationFilter.SetTargetReduction(0.99)
        decimationFilter.SetBoundaryVertexDeletion(0)
        decimationFilter.PreserveTopologyOn()
        decimationFilter.Update()

        cleaner = vtk.vtkCleanPolyData()
        cleaner.SetInputData(decimationFilter.GetOutput())
        cleaner.Update()

        triangleFilter = vtk.vtkTriangleFilter()
        triangleFilter.SetInputData(cleaner.GetOutput())
        triangleFilter.Update()

        outPolyData = vtk.vtkPolyData()
        outPolyData.DeepCopy(triangleFilter.GetOutput())

        return outPolyData

    def openSurfaceAtPoint(self, polyData, seed):
        '''
        Returns a new surface with an opening at the given seed.
        '''

        someradius = 1.0

        pointLocator = vtk.vtkPointLocator()
        pointLocator.SetDataSet(polyData)
        pointLocator.BuildLocator()

        # find the closest point next to the seed on the surface
        id = pointLocator.FindClosestPoint(seed)

        if id<0:
            # Calling GetPoint(-1) would crash the application
            raise ValueError("openSurfaceAtPoint failed: empty input polydata")

        # Tell the polydata to build 'upward' links from points to cells
        polyData.BuildLinks()
        # Mark cells as deleted
        cellIds = vtk.vtkIdList()
        polyData.GetPointCells(id, cellIds)
        for cellIdIndex in range(cellIds.GetNumberOfIds()):
            polyData.DeleteCell(cellIds.GetId(cellIdIndex))
        # Remove the marked cells
        polyData.RemoveDeletedCells()

    def extractNetwork(self, polyData):
        '''
        Returns the network of the given surface.
        '''
        # import the vmtk libraries
        try:
            import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
            import vtkvmtkMiscPython as vtkvmtkMisc
        except ImportError:
            logging.error("Unable to import the SlicerVmtk libraries")

        networkExtraction = vtkvmtkMisc.vtkvmtkPolyDataNetworkExtraction()
        networkExtraction.SetInputData(polyData)
        networkExtraction.SetAdvancementRatio(1.05)
        networkExtraction.SetRadiusArrayName(self.radiusArrayName)
        networkExtraction.SetTopologyArrayName(self.topologyArrayName)
        networkExtraction.SetMarksArrayName(self.marksArrayName)
        networkExtraction.Update()

        outPolyData = vtk.vtkPolyData()
        outPolyData.DeepCopy(networkExtraction.GetOutput())

        return outPolyData

    def clipSurfaceAtEndPoints(self, networkPolyData, surfacePolyData):
        '''
        Clips the surfacePolyData on the endpoints identified using the networkPolyData.

        Returns a tupel of the form [clippedPolyData, endpointsPoints]
        '''
        # import the vmtk libraries
        try:
            import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
            import vtkvmtkMiscPython as vtkvmtkMisc
        except ImportError:
            logging.error("Unable to import the SlicerVmtk libraries")

        cleaner = vtk.vtkCleanPolyData()
        cleaner.SetInputData(networkPolyData)
        cleaner.Update()
        network = cleaner.GetOutput()
        network.BuildCells()
        network.BuildLinks(0)
        endpointIds = vtk.vtkIdList()

        radiusArray = network.GetPointData().GetArray(self.radiusArrayName)

        endpoints = vtk.vtkPolyData()
        endpointsPoints = vtk.vtkPoints()
        endpointsRadius = vtk.vtkDoubleArray()
        endpointsRadius.SetName(self.radiusArrayName)
        endpoints.SetPoints(endpointsPoints)
        endpoints.GetPointData().AddArray(endpointsRadius)

        radiusFactor = 1.2
        minRadius = 0.01
        for i in range(network.GetNumberOfCells()):
            numberOfCellPoints = network.GetCell(i).GetNumberOfPoints()
            pointId0 = network.GetCell(i).GetPointId(0)
            pointId1 = network.GetCell(i).GetPointId(numberOfCellPoints - 1)

            pointCells = vtk.vtkIdList()
            network.GetPointCells(pointId0, pointCells)
            numberOfEndpoints = endpointIds.GetNumberOfIds()
            if pointCells.GetNumberOfIds() == 1:
                pointId = endpointIds.InsertUniqueId(pointId0)
                if pointId == numberOfEndpoints:
                    point = network.GetPoint(pointId0)
                    radius = radiusArray.GetValue(pointId0)
                    radius = max(radius, minRadius)
                    endpointsPoints.InsertNextPoint(point)
                    endpointsRadius.InsertNextValue(radiusFactor * radius)

            pointCells = vtk.vtkIdList()
            network.GetPointCells(pointId1, pointCells)
            numberOfEndpoints = endpointIds.GetNumberOfIds()
            if pointCells.GetNumberOfIds() == 1:
                pointId = endpointIds.InsertUniqueId(pointId1)
                if pointId == numberOfEndpoints:
                    point = network.GetPoint(pointId1)
                    radius = radiusArray.GetValue(pointId1)
                    radius = max(radius, minRadius)
                    endpointsPoints.InsertNextPoint(point)
                    endpointsRadius.InsertNextValue(radiusFactor * radius)

        outPolyData = vtk.vtkPolyData()
        outPolyData.DeepCopy(surfacePolyData)
        numberOfEndpoints = endpointsPoints.GetNumberOfPoints()
        for pointIndex in range(numberOfEndpoints):
            self.openSurfaceAtPoint(outPolyData, endpointsPoints.GetPoint(pointIndex))

        return [outPolyData, endpointsPoints]

    def computeCenterlines(self, polyData, inletSeedIds, outletSeedIds):
        '''
        Returns a tupel of two vtkPolyData objects.
        The first are the centerlines, the second is the corresponding Voronoi diagram.
        '''
        # import the vmtk libraries
        try:
            import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry
            import vtkvmtkMiscPython as vtkvmtkMisc
        except ImportError:
            logging.error("Unable to import the SlicerVmtk libraries")

        centerlineFilter = vtkvmtkComputationalGeometry.vtkvmtkPolyDataCenterlines()
        centerlineFilter.SetInputData(polyData)
        centerlineFilter.SetSourceSeedIds(inletSeedIds)
        centerlineFilter.SetTargetSeedIds(outletSeedIds)
        centerlineFilter.SetRadiusArrayName(self.radiusArrayName)
        centerlineFilter.SetCostFunction('1/R')
        centerlineFilter.SetFlipNormals(False)
        centerlineFilter.SetAppendEndPointsToCenterlines(0)
        centerlineFilter.SetSimplifyVoronoi(0)
        centerlineFilter.SetCenterlineResampling(0)
        centerlineFilter.SetResamplingStepLength(1.0)
        centerlineFilter.Update()

        outPolyData = vtk.vtkPolyData()
        outPolyData.DeepCopy(centerlineFilter.GetOutput())

        outPolyData2 = vtk.vtkPolyData()
        outPolyData2.DeepCopy(centerlineFilter.GetVoronoiDiagram())

        return [outPolyData, outPolyData2]

    def createCurveTreeFromCenterline(self, centerlineModel, rootCurve=None, centerlinePropertiesTableNode=None):

        import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry

        branchExtractor = vtkvmtkComputationalGeometry.vtkvmtkCenterlineBranchExtractor()
        branchExtractor.SetInputData(centerlineModel.GetPolyData())
        branchExtractor.SetBlankingArrayName(self.blankingArrayName)
        branchExtractor.SetRadiusArrayName(self.radiusArrayName)
        branchExtractor.SetGroupIdsArrayName(self.groupIdsArrayName)
        branchExtractor.SetCenterlineIdsArrayName(self.centerlineIdsArrayName)
        branchExtractor.SetTractIdsArrayName(self.tractIdsArrayName)
        branchExtractor.Update()
        centerlines = branchExtractor.GetOutput()

        mergeCenterlines = vtkvmtkComputationalGeometry.vtkvmtkMergeCenterlines()
        mergeCenterlines.SetInputData(centerlines)
        mergeCenterlines.SetRadiusArrayName(self.radiusArrayName)
        mergeCenterlines.SetGroupIdsArrayName(self.groupIdsArrayName)
        mergeCenterlines.SetCenterlineIdsArrayName(self.centerlineIdsArrayName)
        mergeCenterlines.SetTractIdsArrayName(self.tractIdsArrayName)
        mergeCenterlines.SetBlankingArrayName(self.blankingArrayName)
        mergeCenterlines.SetResamplingStepLength(1.0)
        mergeCenterlines.SetMergeBlanked(True)
        mergeCenterlines.Update()
        mergedCenterlines = mergeCenterlines.GetOutput()

        if centerlinePropertiesTableNode:
            centerlinePropertiesTableNode.RemoveAllColumns()

            # Cell index column
            numberOfCells = mergedCenterlines.GetNumberOfCells()
            cellIndexArray = vtk.vtkIntArray()
            cellIndexArray.SetName("CellId")
            cellIndexArray.SetNumberOfValues(numberOfCells)
            for cellIndex in range(numberOfCells):
                cellIndexArray.SetValue(cellIndex, cellIndex)
            centerlinePropertiesTableNode.GetTable().AddColumn(cellIndexArray)

            # Get average radius
            pointDataToCellData = vtk.vtkPointDataToCellData()
            pointDataToCellData.SetInputData(mergedCenterlines)
            pointDataToCellData.ProcessAllArraysOff()
            pointDataToCellData.AddPointDataArray(self.radiusArrayName)
            pointDataToCellData.Update()
            averageRadiusArray = pointDataToCellData.GetOutput().GetCellData().GetArray(self.radiusArrayName)
            centerlinePropertiesTableNode.GetTable().AddColumn(averageRadiusArray)

            # Get length, curvature, torsion, tortuosity
            centerlineBranchGeometry = vtkvmtkComputationalGeometry.vtkvmtkCenterlineBranchGeometry()
            centerlineBranchGeometry.SetInputData(mergedCenterlines)
            centerlineBranchGeometry.SetRadiusArrayName(self.radiusArrayName)
            centerlineBranchGeometry.SetGroupIdsArrayName(self.groupIdsArrayName)
            centerlineBranchGeometry.SetBlankingArrayName(self.blankingArrayName)
            centerlineBranchGeometry.SetLengthArrayName(self.lengthArrayName)
            centerlineBranchGeometry.SetCurvatureArrayName(self.curvatureArrayName)
            centerlineBranchGeometry.SetTorsionArrayName(self.torsionArrayName)
            centerlineBranchGeometry.SetTortuosityArrayName(self.tortuosityArrayName)
            centerlineBranchGeometry.SetLineSmoothing(False)
            #centerlineBranchGeometry.SetNumberOfSmoothingIterations(100)
            #centerlineBranchGeometry.SetSmoothingFactor(0.1)
            centerlineBranchGeometry.Update()
            centerlineProperties = centerlineBranchGeometry.GetOutput()
            for columnName in [self.lengthArrayName, self.curvatureArrayName, self.torsionArrayName, self.tortuosityArrayName]:
                centerlinePropertiesTableNode.GetTable().AddColumn(centerlineProperties.GetPointData().GetArray(columnName))

            # Get branch start and end positions
            startPointPositions = vtk.vtkDoubleArray()
            startPointPositions.SetName("StartPointPosition")
            endPointPositions = vtk.vtkDoubleArray()
            endPointPositions.SetName("EndPointPosition")
            for positions in [startPointPositions, endPointPositions]:
                positions.SetNumberOfComponents(3)
                positions.SetComponentName(0, "R")
                positions.SetComponentName(1, "A")
                positions.SetComponentName(2, "S")
                positions.SetNumberOfTuples(numberOfCells)
            for cellIndex in range(numberOfCells):
                pointIds = mergedCenterlines.GetCell(cellIndex).GetPointIds()
                startPointPosition = [0, 0, 0]
                if pointIds.GetNumberOfIds() > 0:
                    mergedCenterlines.GetPoint(pointIds.GetId(0), startPointPosition)
                if pointIds.GetNumberOfIds() > 1:
                    endPointPosition = [0, 0, 0]
                    mergedCenterlines.GetPoint(pointIds.GetId(pointIds.GetNumberOfIds()-1), endPointPosition)
                else:
                    endPointPosition = startPointPosition
                startPointPositions.SetTuple3(cellIndex, *startPointPosition)
                endPointPositions.SetTuple3(cellIndex, *endPointPosition)
            centerlinePropertiesTableNode.GetTable().AddColumn(startPointPositions)
            centerlinePropertiesTableNode.GetTable().AddColumn(endPointPositions)

            centerlinePropertiesTableNode.GetTable().Modified()

        if rootCurve:
            # Delete existing children of the output markups curve
            shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
            curveItem = shNode.GetItemByDataNode(rootCurve)
            shNode.RemoveItemChildren(curveItem)
            # Add centerline widgets
            self.processedCellIds = []
            self._addCenterline(mergedCenterlines, replaceCurve=rootCurve)

    def _addCenterline(self, mergedCenterlines, baseName=None, cellId=0, parentItem=None, replaceCurve=None):
        # Add current cell as a curve node
        assignAttribute = vtk.vtkAssignAttribute()
        assignAttribute.SetInputData(mergedCenterlines)
        assignAttribute.Assign(self.groupIdsArrayName, vtk.vtkDataSetAttributes.SCALARS,
                               vtk.vtkAssignAttribute.CELL_DATA)
        thresholder = vtk.vtkThreshold()
        thresholder.SetInputConnection(assignAttribute.GetOutputPort())
        groupId = mergedCenterlines.GetCellData().GetArray(self.groupIdsArrayName).GetValue(cellId)
        thresholder.ThresholdBetween(groupId - 0.5, groupId + 0.5)
        thresholder.Update()

        if replaceCurve:
            # update existing curve widget
            curveNode = replaceCurve
            if baseName is None:
                baseName = curveNode.GetName()
                # Parse name, if it ends with a number in a parenthesis ("branch (1)") then assume it contains
                # the cell index and remove it to get the base name
                import re
                matched = re.match("(.+) \([0-9]+\)", baseName)
                if matched:
                    baseName = matched[1]
            curveNode.SetName("{0} ({1})".format(baseName, cellId))
        else:
            if baseName is None:
                baseName = "branch"
            curveNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsCurveNode", "{0} ({1})".format(baseName, cellId))

        curveNode.SetAttribute("CellId", str(cellId))
        curveNode.SetAttribute("GroupId", str(groupId))
        curveNode.SetControlPointPositionsWorld(thresholder.GetOutput().GetPoints())
        slicer.modules.markups.logic().SetAllMarkupsVisibility(curveNode, False)
        slicer.app.processEvents()
        shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
        curveItem = shNode.GetItemByDataNode(curveNode)
        if parentItem is not None:
            shNode.SetItemParent(curveItem, parentItem)
        # Add connecting cells
        self.processedCellIds.append(cellId)
        cellPoints = mergedCenterlines.GetCell(cellId).GetPointIds()
        endPointIndex = cellPoints.GetId(cellPoints.GetNumberOfIds() - 1)
        numberOfCells = mergedCenterlines.GetNumberOfCells()
        branchIndex = 0
        for neighborCellIndex in range(numberOfCells):
            if neighborCellIndex in self.processedCellIds:
                continue
            if endPointIndex != mergedCenterlines.GetCell(neighborCellIndex).GetPointIds().GetId(0):
                continue
            branchIndex += 1
            self._addCenterline(mergedCenterlines, baseName, neighborCellIndex, curveItem)


class Slicelet(object):
    """A slicer slicelet is a module widget that comes up in stand alone mode
    implemented as a python class.
    This class provides common wrapper functionality used by all slicer modlets.
    """

    # TODO: put this in a SliceletLib
    # TODO: parse command line arge

    def __init__(self, widgetClass=None):
        self.parent = qt.QFrame()
        self.parent.setLayout(qt.QVBoxLayout())

        # TODO: should have way to pop up python interactor
        self.buttons = qt.QFrame()
        self.buttons.setLayout(qt.QHBoxLayout())
        self.parent.layout().addWidget(self.buttons)
        self.addDataButton = qt.QPushButton("Add Data")
        self.buttons.layout().addWidget(self.addDataButton)
        self.addDataButton.connect("clicked()", slicer.app.ioManager().openAddDataDialog)
        self.loadSceneButton = qt.QPushButton("Load Scene")
        self.buttons.layout().addWidget(self.loadSceneButton)
        self.loadSceneButton.connect("clicked()", slicer.app.ioManager().openLoadSceneDialog)

        if widgetClass:
            self.widget = widgetClass(self.parent)
            self.widget.setup()
        self.parent.show()


class CenterlineComputationSlicelet(Slicelet):
    """ Creates the interface when module is run as a stand alone gui app.
    """

    def __init__(self):
        super(CenterlineComputationSlicelet, self).__init__(CenterlineComputationWidget)


if __name__ == "__main__":
    # TODO: need a way to access and parse command line arguments
    # TODO: ideally command line args should handle --xml

    import sys

    print(sys.argv)

    slicelet = CenterlineComputationSlicelet()
