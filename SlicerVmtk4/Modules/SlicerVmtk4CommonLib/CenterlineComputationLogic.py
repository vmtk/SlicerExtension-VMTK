# vtk includes
from __main__ import vtk

class CenterlineComputationLogic( object ):
    '''
    classdocs
    '''


    def __init__( self ):
        '''
        Constructor
        '''

    def importVmtk(self):
        '''
        '''
        # import the vmtk libraries
        try:
            from libvtkvmtkComputationalGeometryPython import *
            from libvtkvmtkMiscPython import *
        except ImportError:
            print "FAILURE: Unable to import the SlicerVmtk4 libraries!"        

    def prepareModel( self, polyData ):
        '''
        '''
        self.importVmtk()

        capDisplacement = 0.0

        surfaceCleaner = vtk.vtkCleanPolyData()
        surfaceCleaner.SetInput( polyData )
        surfaceCleaner.Update()

        surfaceTriangulator = vtk.vtkTriangleFilter()
        surfaceTriangulator.SetInput( surfaceCleaner.GetOutput() )
        surfaceTriangulator.PassLinesOff()
        surfaceTriangulator.PassVertsOff()
        surfaceTriangulator.Update()

        # new steps for preparation to avoid problems because of slim models (f.e. at stenosis)
        subdiv = vtk.vtkLinearSubdivisionFilter()
        subdiv.SetInput( surfaceTriangulator.GetOutput() )
        subdiv.SetNumberOfSubdivisions( 1 )
        subdiv.Update()

        smooth = vtk.vtkWindowedSincPolyDataFilter()
        smooth.SetInput( subdiv.GetOutput() )
        smooth.SetNumberOfIterations( 20 )
        smooth.SetPassBand( 0.1 )
        smooth.SetBoundarySmoothing( 1 )
        smooth.Update()

        normals = vtk.vtkPolyDataNormals()
        normals.SetInput( smooth.GetOutput() )
        normals.SetAutoOrientNormals( 1 )
        normals.SetFlipNormals( 0 )
        normals.SetConsistency( 1 )
        normals.SplittingOff()
        normals.Update()

        surfaceCapper = vtkvmtkCapPolyData()
        surfaceCapper.SetInput( normals.GetOutput() )
        surfaceCapper.SetDisplacement( capDisplacement )
        surfaceCapper.SetInPlaneDisplacement( capDisplacement )
        surfaceCapper.Update()

        outPolyData = vtk.vtkPolyData()
        outPolyData.DeepCopy( surfaceCapper.GetOutput() )
        outPolyData.Update()

        return outPolyData


    def decimateSurface( self, polyData ):
        '''
        '''      
        
        decimationFilter = vtk.vtkDecimatePro()
        decimationFilter.SetInput( polyData )
        decimationFilter.SetTargetReduction( 0.99 )
        decimationFilter.SetBoundaryVertexDeletion( 0 )
        decimationFilter.PreserveTopologyOn()
        decimationFilter.Update()

        cleaner = vtk.vtkCleanPolyData()
        cleaner.SetInput( decimationFilter.GetOutput() )
        cleaner.Update()

        triangleFilter = vtk.vtkTriangleFilter()
        triangleFilter.SetInput( cleaner.GetOutput() )
        triangleFilter.Update()

        outPolyData = vtk.vtkPolyData()
        outPolyData.DeepCopy( triangleFilter.GetOutput() )
        outPolyData.Update()

        return outPolyData


    def openSurfaceAtPoint( self, polyData, seed ):
        '''
        Returns a new surface with an opening at the given seed.
        '''

        someradius = 1.0

        pointLocator = vtk.vtkPointLocator()
        pointLocator.SetDataSet( polyData )
        pointLocator.BuildLocator()

        # find the closest point next to the seed on the surface
        #id = pointLocator.FindClosestPoint(int(seed[0]),int(seed[1]),int(seed[2]))
        id = pointLocator.FindClosestPoint( seed )

        # the seed is now guaranteed on the surface
        seed = polyData.GetPoint( id )

        sphere = vtk.vtkSphere()
        sphere.SetCenter( seed[0], seed[1], seed[2] )
        sphere.SetRadius( someradius )

        clip = vtk.vtkClipPolyData()
        clip.SetInput( polyData )
        clip.SetClipFunction( sphere )
        clip.Update()

        outPolyData = vtk.vtkPolyData()
        outPolyData.DeepCopy( clip.GetOutput() )
        outPolyData.Update()

        return outPolyData



    def extractNetwork( self, polyData ):
        '''
        Returns the network of the given surface.
        '''
        self.importVmtk()        

        radiusArrayName = 'Radius'
        topologyArrayName = 'Topology'
        marksArrayName = 'Marks'

        networkExtraction = vtkvmtkPolyDataNetworkExtraction()
        networkExtraction.SetInput( polyData )
        networkExtraction.SetAdvancementRatio( 1.05 )
        networkExtraction.SetRadiusArrayName( radiusArrayName )
        networkExtraction.SetTopologyArrayName( topologyArrayName )
        networkExtraction.SetMarksArrayName( marksArrayName )
        networkExtraction.Update()

        outPolyData = vtk.vtkPolyData()
        outPolyData.DeepCopy( networkExtraction.GetOutput() )
        outPolyData.Update()

        return outPolyData


    def clipSurfaceAtEndPoints( self, networkPolyData, surfacePolyData ):
        '''
        Clips the surfacePolyData on the endpoints identified using the networkPolyData.
        
        Returns a tupel of the form [clippedPolyData, endpointsPoints]
        '''
        self.importVmtk()

        cleaner = vtk.vtkCleanPolyData()
        cleaner.SetInput( networkPolyData )
        cleaner.Update()
        network = cleaner.GetOutput()
        network.BuildCells()
        network.BuildLinks( 0 )
        endpointIds = vtk.vtkIdList()

        radiusArray = network.GetPointData().GetArray( 'Radius' )

        endpoints = vtk.vtkPolyData()
        endpointsPoints = vtk.vtkPoints()
        endpointsRadius = vtk.vtkDoubleArray()
        endpointsRadius.SetName( 'Radius' )
        endpoints.SetPoints( endpointsPoints )
        endpoints.GetPointData().AddArray( endpointsRadius )

        radiusFactor = 1.2
        minRadius = 0.01

        for i in range( network.GetNumberOfCells() ):
            numberOfCellPoints = network.GetCell( i ).GetNumberOfPoints()
            pointId0 = network.GetCell( i ).GetPointId( 0 )
            pointId1 = network.GetCell( i ).GetPointId( numberOfCellPoints - 1 )

            pointCells = vtk.vtkIdList()
            network.GetPointCells( pointId0, pointCells )
            numberOfEndpoints = endpointIds.GetNumberOfIds()
            if pointCells.GetNumberOfIds() == 1:
                pointId = endpointIds.InsertUniqueId( pointId0 )
                if pointId == numberOfEndpoints:
                    point = network.GetPoint( pointId0 )
                    radius = radiusArray.GetValue( pointId0 )
                    radius = max( radius, minRadius )
                    endpointsPoints.InsertNextPoint( point )
                    endpointsRadius.InsertNextValue( radiusFactor * radius )

            pointCells = vtk.vtkIdList()
            network.GetPointCells( pointId1, pointCells )
            numberOfEndpoints = endpointIds.GetNumberOfIds()
            if pointCells.GetNumberOfIds() == 1:
                pointId = endpointIds.InsertUniqueId( pointId1 )
                if pointId == numberOfEndpoints:
                    point = network.GetPoint( pointId1 )
                    radius = radiusArray.GetValue( pointId1 )
                    radius = max( radius, minRadius )
                    endpointsPoints.InsertNextPoint( point )
                    endpointsRadius.InsertNextValue( radiusFactor * radius )

        polyBall = vtkvmtkPolyBall()
        polyBall.SetInput( endpoints )
        polyBall.SetPolyBallRadiusArrayName( 'Radius' )

        clipper = vtk.vtkClipPolyData()
        clipper.SetInput( surfacePolyData )
        clipper.SetClipFunction( polyBall )
        clipper.Update()

        connectivityFilter = vtk.vtkPolyDataConnectivityFilter()
        connectivityFilter.SetInput( clipper.GetOutput() )
        connectivityFilter.ColorRegionsOff()
        connectivityFilter.SetExtractionModeToLargestRegion()
        connectivityFilter.Update()

        clippedSurface = connectivityFilter.GetOutput()

        outPolyData = vtk.vtkPolyData()
        outPolyData.DeepCopy( clippedSurface )
        outPolyData.Update()

        return [outPolyData, endpointsPoints]


    def computeCenterlines( self, polyData, inletSeedIds, outletSeedIds ):
        '''
        Returns a tupel of two vtkPolyData objects. 
        The first are the centerlines, the second is the corresponding Voronoi diagram.
        '''
        self.importVmtk()        

        flipNormals = 0
        radiusArrayName = 'Radius'
        costFunction = '1/R'


        centerlineFilter = vtkvmtkPolyDataCenterlines()
        centerlineFilter.SetInput( polyData )
        centerlineFilter.SetSourceSeedIds( inletSeedIds )
        centerlineFilter.SetTargetSeedIds( outletSeedIds )
        centerlineFilter.SetRadiusArrayName( radiusArrayName )
        centerlineFilter.SetCostFunction( costFunction )
        centerlineFilter.SetFlipNormals( flipNormals )
        centerlineFilter.SetAppendEndPointsToCenterlines( 0 )
        centerlineFilter.SetSimplifyVoronoi( 0 )
        centerlineFilter.SetCenterlineResampling( 0 )
        centerlineFilter.SetResamplingStepLength( 1.0 )
        centerlineFilter.Update()

        outPolyData = vtk.vtkPolyData()
        outPolyData.DeepCopy( centerlineFilter.GetOutput() )
        outPolyData.Update()

        outPolyData2 = vtk.vtkPolyData()
        outPolyData2.DeepCopy( centerlineFilter.GetVoronoiDiagram() )
        outPolyData2.Update()

        return [outPolyData, outPolyData2]


