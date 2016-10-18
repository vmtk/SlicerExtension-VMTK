# vtk includes
from __main__ import vtk
import logging


class LevelSetSegmentationLogic( object ):
    '''
    classdocs
    '''


    def __init__( self ):
        '''
        Constructor
        '''


    def performInitialization( self, image, lowerThreshold, upperThreshold, sourceSeedIds, targetSeedIds, method="collidingfronts" ):
        '''
        '''
        # import the vmtk libraries
        try:
            import vtkvmtkSegmentationPython as vtkvmtkSegmentation
        except ImportError:
            logging.error("Unable to import the SlicerVmtk libraries")

        cast = vtk.vtkImageCast()
        cast.SetInputData( image )
        cast.SetOutputScalarTypeToFloat()
        cast.Update()
        image = cast.GetOutput()

        scalarRange = image.GetScalarRange()

        imageDimensions = image.GetDimensions()
        maxImageDimensions = max( imageDimensions )

        threshold = vtk.vtkImageThreshold()
        threshold.SetInputData( image )
        threshold.ThresholdBetween( lowerThreshold, upperThreshold )
        threshold.ReplaceInOff()
        threshold.ReplaceOutOn()
        threshold.SetOutValue( scalarRange[0] - scalarRange[1] )
        threshold.Update()

        thresholdedImage = threshold.GetOutput()

        scalarRange = thresholdedImage.GetScalarRange()

        shiftScale = vtk.vtkImageShiftScale()
        shiftScale.SetInputData( thresholdedImage )
        shiftScale.SetShift( -scalarRange[0] )
        shiftScale.SetScale( 1.0 / ( scalarRange[1] - scalarRange[0] ) )
        shiftScale.Update()

        speedImage = shiftScale.GetOutput()

        if method == "collidingfronts":
            # ignore sidebranches, use colliding fronts
            logging.debug("Using Colliding fronts")
            logging.debug("number of vtk ids: " + str(sourceSeedIds.GetNumberOfIds()))
            logging.debug("SourceSeedIds:")
            logging.debug(sourceSeedIds)
            collidingFronts = vtkvmtkSegmentation.vtkvmtkCollidingFrontsImageFilter()
            collidingFronts.SetInputData( speedImage )
            sourceSeedId1 = vtk.vtkIdList()
            sourceSeedId1.InsertNextId( sourceSeedIds.GetId(0) )
            sourceSeedId2 = vtk.vtkIdList()
            sourceSeedId2.InsertNextId( sourceSeedIds.GetId(1) )
            collidingFronts.SetSeeds1( sourceSeedId1 )
            collidingFronts.SetSeeds2( sourceSeedId2 )
            collidingFronts.ApplyConnectivityOn()
            collidingFronts.StopOnTargetsOn()
            collidingFronts.Update()

            subtract = vtk.vtkImageMathematics()
            subtract.SetInputData( collidingFronts.GetOutput() )
            subtract.SetOperationToAddConstant()
            subtract.SetConstantC( -10 * collidingFronts.GetNegativeEpsilon() )
            subtract.Update()

        elif method == "fastmarching":
            fastMarching = vtkvmtkSegmentation.vtkvmtkFastMarchingUpwindGradientImageFilter()
            fastMarching.SetInputData( speedImage )
            fastMarching.SetSeeds( sourceSeedIds )
            fastMarching.GenerateGradientImageOn()
            fastMarching.SetTargetOffset( 0.0 )
            fastMarching.SetTargets( targetSeedIds )
            if targetSeedIds.GetNumberOfIds() > 0:
                fastMarching.SetTargetReachedModeToOneTarget()
            else:
                fastMarching.SetTargetReachedModeToNoTargets()
            fastMarching.Update()

            if targetSeedIds.GetNumberOfIds() > 0:
                subtract = vtk.vtkImageMathematics()
                subtract.SetInputData( fastMarching.GetOutput() )
                subtract.SetOperationToAddConstant()
                subtract.SetConstantC( -fastMarching.GetTargetValue() )
                subtract.Update()

            else:
                subtract = vtk.vtkImageThreshold()
                subtract.SetInputData( fastMarching.GetOutput() )
                subtract.ThresholdByLower( 2000 )  # TODO find robuste value
                subtract.ReplaceInOff()
                subtract.ReplaceOutOn()
                subtract.SetOutValue( -1 )
                subtract.Update()
        
        elif method == "threshold":
            raise NotImplementedError()
        elif method == "isosurface":
            raise NotImplementedError()
        elif method == "seeds":
            raise NotImplementedError()
        else:
            raise NameError()

        outImageData = vtk.vtkImageData()
        outImageData.DeepCopy( subtract.GetOutput() )

        return outImageData



    def performEvolution( self, originalImage, segmentationImage, numberOfIterations, inflation, curvature, attraction, method='geodesic' ):
        '''

        '''
        # import the vmtk libraries
        try:
            import vtkvmtkSegmentationPython as vtkvmtkSegmentation
        except ImportError:
            logging.error("Unable to import the SlicerVmtk libraries")

        featureDerivativeSigma = 0.0
        maximumRMSError = 1E-20
        isoSurfaceValue = 0.0

        logging.debug("NumberOfIterations: " + str(numberOfIterations))
        logging.debug("inflation: " + str(inflation))
        logging.debug("curvature: " + str(curvature))
        logging.debug("attraction: " + str(attraction))

        if method == 'curves':
            levelSets = vtkvmtkSegmentation.vtkvmtkCurvesLevelSetImageFilter()
        else:
            logging.debug("using vtkvmtkGeodesicActiveContourLevelSetImageFilter")
            levelSets = vtkvmtkSegmentation.vtkvmtkGeodesicActiveContourLevelSetImageFilter()

        levelSets.SetFeatureImage( self.buildGradientBasedFeatureImage( originalImage ) )
        levelSets.SetDerivativeSigma( featureDerivativeSigma )
        levelSets.SetAutoGenerateSpeedAdvection( 1 )
        levelSets.SetPropagationScaling( inflation * ( -1 ) )
        levelSets.SetCurvatureScaling( curvature )
        levelSets.SetAdvectionScaling( attraction * ( -1 ) )
        levelSets.SetInputData( segmentationImage )
        levelSets.SetNumberOfIterations( numberOfIterations )
        levelSets.SetIsoSurfaceValue( isoSurfaceValue )
        levelSets.SetMaximumRMSError( maximumRMSError )
        levelSets.SetInterpolateSurfaceLocation( 1 )
        levelSets.SetUseImageSpacing( 1 )
        levelSets.Update()

        outImageData = vtk.vtkImageData()
        outImageData.DeepCopy( levelSets.GetOutput() )

        return outImageData


    def buildGradientBasedFeatureImage( self, imageData ):
        '''
        '''
        # import the vmtk libraries
        try:
            import vtkvmtkSegmentationPython as vtkvmtkSegmentation
        except ImportError:
            logging.error("Unable to import the SlicerVmtk libraries")

        derivativeSigma = 0.0
        sigmoidRemapping = 1

        cast = vtk.vtkImageCast()
        cast.SetInputData( imageData )
        cast.SetOutputScalarTypeToFloat()
        cast.Update()

        if ( derivativeSigma > 0.0 ):
            gradientMagnitude = vtkvmtkSegmentation.vtkvmtkGradientMagnitudeRecursiveGaussianImageFilter()
            gradientMagnitude.SetInputData( cast.GetOutput() )
            gradientMagnitude.SetSigma( derivativeSigma )
            gradientMagnitude.SetNormalizeAcrossScale( 0 )
            gradientMagnitude.Update()
        else:
            gradientMagnitude = vtkvmtkSegmentation.vtkvmtkGradientMagnitudeImageFilter()
            gradientMagnitude.SetInputData( cast.GetOutput() )
            gradientMagnitude.Update()

        featureImage = None
        if sigmoidRemapping == 1:
            scalarRange = gradientMagnitude.GetOutput().GetPointData().GetScalars().GetRange()
            inputMinimum = scalarRange[0]
            inputMaximum = scalarRange[1]
            alpha = -( inputMaximum - inputMinimum ) / 6.0
            beta = ( inputMaximum + inputMinimum ) / 2.0

            sigmoid = vtkvmtkSegmentation.vtkvmtkSigmoidImageFilter()
            sigmoid.SetInputData( gradientMagnitude.GetOutput() )
            sigmoid.SetAlpha( alpha )
            sigmoid.SetBeta( beta )
            sigmoid.SetOutputMinimum( 0.0 )
            sigmoid.SetOutputMaximum( 1.0 )
            sigmoid.Update()
            featureImage = sigmoid.GetOutput()
        else:
            boundedReciprocal = vtkvmtkSegmentation.vtkvmtkBoundedReciprocalImageFilter()
            boundedReciprocal.SetInputData( gradientMagnitude.GetOutput() )
            boundedReciprocal.Update()
            featureImage = boundedReciprocal.GetOutput()

        outImageData = vtk.vtkImageData()
        outImageData.DeepCopy( featureImage )

        return outImageData

    def buildSimpleLabelMap( self, image, inValue, outValue ):

        threshold = vtk.vtkImageThreshold()
        threshold.SetInputData( image )
        threshold.ThresholdByLower( 0 )
        threshold.ReplaceInOn()
        threshold.ReplaceOutOn()
        threshold.SetOutValue( outValue )
        threshold.SetInValue( inValue )
        threshold.Update()

        outVolumeData = vtk.vtkImageData()
        outVolumeData.DeepCopy( threshold.GetOutput() )

        return outVolumeData

    def marchingCubes( self, image, ijkToRasMatrix, threshold ):


        transformIJKtoRAS = vtk.vtkTransform()
        transformIJKtoRAS.SetMatrix( ijkToRasMatrix )

        marchingCubes = vtk.vtkMarchingCubes()
        marchingCubes.SetInputData( image )
        marchingCubes.SetValue( 0, threshold )
        marchingCubes.ComputeScalarsOn()
        marchingCubes.ComputeGradientsOn()
        marchingCubes.ComputeNormalsOn()
        marchingCubes.ReleaseDataFlagOn()
        marchingCubes.Update()


        if transformIJKtoRAS.GetMatrix().Determinant() < 0:
            reverser = vtk.vtkReverseSense()
            reverser.SetInputData( marchingCubes.GetOutput() )
            reverser.ReverseNormalsOn()
            reverser.ReleaseDataFlagOn()
            reverser.Update()
            correctedOutput = reverser.GetOutput()
        else:
            correctedOutput = marchingCubes.GetOutput()

        transformer = vtk.vtkTransformPolyDataFilter()
        transformer.SetInputData( correctedOutput )
        transformer.SetTransform( transformIJKtoRAS )
        transformer.ReleaseDataFlagOn()
        transformer.Update()

        normals = vtk.vtkPolyDataNormals()
        normals.ComputePointNormalsOn()
        normals.SetInputData( transformer.GetOutput() )
        normals.SetFeatureAngle( 60 )
        normals.SetSplitting( 1 )
        normals.ReleaseDataFlagOn()
        normals.Update()

        stripper = vtk.vtkStripper()
        stripper.SetInputData( normals.GetOutput() )
        stripper.ReleaseDataFlagOff()
        stripper.Update()
        stripper.GetOutput()

        result = vtk.vtkPolyData()
        result.DeepCopy( stripper.GetOutput() )

        return result
