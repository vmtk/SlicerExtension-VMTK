# vtk includes
from __main__ import vtk

# import the vmtk libraries
from libvtkvmtkSegmentationPython import *

class LevelSetSegmentationLogic(object):
    '''
    classdocs
    '''


    def __init__(self):
        '''
        Constructor
        '''
        
    def performInitialization(self, image, lowerThreshold, upperThreshold, sourceSeedIds, targetSeedIds, ignoreSideBranches=0):
        '''
        '''
        cast = vtk.vtkImageCast()
        cast.SetInput(image)
        cast.SetOutputScalarTypeToFloat()
        cast.Update()
        image = cast.GetOutput()

        scalarRange = image.GetScalarRange()

        imageDimensions = image.GetDimensions()
        maxImageDimensions = max(imageDimensions)

        threshold = vtk.vtkImageThreshold()
        threshold.SetInput(image)
        threshold.ThresholdBetween(lowerThreshold, upperThreshold)
        threshold.ReplaceInOff()
        threshold.ReplaceOutOn()
        threshold.SetOutValue(scalarRange[0] - scalarRange[1])
        threshold.Update()

        thresholdedImage = threshold.GetOutput()

        scalarRange = thresholdedImage.GetScalarRange()

        shiftScale = vtk.vtkImageShiftScale()
        shiftScale.SetInput(thresholdedImage)
        shiftScale.SetShift(-scalarRange[0])
        shiftScale.SetScale(1 / (scalarRange[1] - scalarRange[0]))
        shiftScale.Update()

        speedImage = shiftScale.GetOutput()
        
        if ignoreSideBranches:
            # ignore sidebranches, use colliding fronts
            fastMarching = vtkvmtkCollidingFrontsImageFilter()
            fastMarching.SetInput(speedImage)
            fastMarching.SetSeeds1(sourceSeedIds)
            fastMarching.SetSeeds2(targetSeedIds)
            fastMarching.ApplyConnectivityOn()
            fastMarching.StopOnTargetsOn()            
            fastMarching.Update()
        
            subtract = vtk.vtkImageMathematics()
            subtract.SetInput(fastMarching.GetOutput())
            subtract.SetOperationToAddConstant()
            subtract.SetConstantC(-10 * fastMarching.GetNegativeEpsilon())
            subtract.Update()
        
        else:
            fastMarching = vtkvmtkFastMarchingUpwindGradientImageFilter()
            fastMarching.SetInput(speedImage)
            fastMarching.SetSeeds(sourceSeedIds)
            fastMarching.GenerateGradientImageOn()
            fastMarching.SetTargetOffset(0.0)
            fastMarching.SetTargets(targetSeedIds)
            if targetSeedIds.GetNumberOfIds() > 0:
                fastMarching.SetTargetReachedModeToOneTarget()
            else:
                fastMarching.SetTargetReachedModeToNoTargets()
            fastMarching.Update()
        
            if targetSeedIds.GetNumberOfIds() > 0:
                subtract = vtk.vtkImageMathematics()
                subtract.SetInput(fastMarching.GetOutput())
                subtract.SetOperationToAddConstant()
                subtract.SetConstantC(-fastMarching.GetTargetValue())
                subtract.Update()
        
            else:
                subtract = vtk.vtkImageThreshold()
                subtract.SetInput(fastMarching.GetOutput())
                subtract.ThresholdByLower(2000) # TODO find robuste value
                subtract.ReplaceInOff()
                subtract.ReplaceOutOn()
                subtract.SetOutValue(-1)
                subtract.Update()
        
        outImageData = vtk.vtkImageData()
        outImageData.DeepCopy(subtract.GetOutput())
        outImageData.Update()
        
        
        return outImageData


    
    def performEvolution(self,originalImage,segmentationImage,numberOfIterations,inflation,curvature,attraction,method='geodesic'):
        '''
        
        '''

        featureDerivativeSigma = 0.0
        maximumRMSError = 1E-20
        isoSurfaceValue = 0.0

        if method=='curves':
            levelSets = vtkvmtkCurvesLevelSetImageFilter()
        else:
            levelSets = vtkvmtkGeodesicActiveContourLevelSetImageFilter()

        levelSets.SetFeatureImage(self.buildGradientBasedFeatureImage(originalImage))
        levelSets.SetDerivativeSigma(featureDerivativeSigma)
        levelSets.SetAutoGenerateSpeedAdvection(1)
        levelSets.SetPropagationScaling(inflation*(-1))
        levelSets.SetCurvatureScaling(curvature)
        levelSets.SetAdvectionScaling(attraction*(-1))
        levelSets.SetInput(segmentationImage)
        levelSets.SetNumberOfIterations(numberOfIterations)
        levelSets.SetIsoSurfaceValue(isoSurfaceValue)
        levelSets.SetMaximumRMSError(maximumRMSError)
        levelSets.SetInterpolateSurfaceLocation(1)
        levelSets.SetUseImageSpacing(1)
        levelSets.Update()

        outImageData = vtk.vtkImageData()
        outImageData.DeepCopy(levelSets.GetOutput())
        outImageData.Update()
        
        return outImageData
        
                
    def buildGradientBasedFeatureImage(self,imageData):

        derivativeSigma = 0.0
        sigmoidRemapping = 1

        cast = vtk.vtkImageCast()
        cast.SetInput(imageData)
        cast.SetOutputScalarTypeToFloat()
        cast.Update()

        if (derivativeSigma > 0.0):
            gradientMagnitude = vtkvmtkGradientMagnitudeRecursiveGaussianImageFilter()
            gradientMagnitude.SetInput(cast.GetOutput())
            gradientMagnitude.SetSigma(derivativeSigma)
            gradientMagnitude.SetNormalizeAcrossScale(0)
            gradientMagnitude.Update()
        else:
            gradientMagnitude = vtkvmtkGradientMagnitudeImageFilter()
            gradientMagnitude.SetInput(cast.GetOutput())
            gradientMagnitude.Update()

        featureImage = None
        if sigmoidRemapping==1:
            scalarRange = gradientMagnitude.GetOutput().GetPointData().GetScalars().GetRange()
            inputMinimum = scalarRange[0]
            inputMaximum = scalarRange[1]
            alpha = - (inputMaximum - inputMinimum) / 6.0
            beta = (inputMaximum + inputMinimum) / 2.0
            
            sigmoid = vtkvmtkSigmoidImageFilter()
            sigmoid.SetInput(gradientMagnitude.GetOutput())
            sigmoid.SetAlpha(alpha)
            sigmoid.SetBeta(beta)
            sigmoid.SetOutputMinimum(0.0)
            sigmoid.SetOutputMaximum(1.0)
            sigmoid.Update()
            featureImage = sigmoid.GetOutput()
        else:
            boundedReciprocal = vtkvmtkBoundedReciprocalImageFilter()
            boundedReciprocal.SetInput(gradientMagnitude.GetOutput())
            boundedReciprocal.Update()
            featureImage = boundedReciprocal.GetOutput()

        outImageData = vtk.vtkImageData()
        outImageData.DeepCopy(featureImage)
        outImageData.Update()

        return outImageData    
    
    def buildSimpleLabelMap(self,image,inValue,outValue):

        threshold = vtk.vtkImageThreshold()
        threshold.SetInput(image)
        threshold.ThresholdByLower(0)
        threshold.ReplaceInOn()
        threshold.ReplaceOutOn()
        threshold.SetOutValue(outValue)
        threshold.SetInValue(inValue)
        threshold.Update()

        outVolumeData = vtk.vtkImageData()
        outVolumeData.DeepCopy(threshold.GetOutput())
        outVolumeData.Update()

        return outVolumeData
        
    def marchingCubes(self,image,ijkToRasMatrix,threshold):
        
        
        transformIJKtoRAS = vtk.vtkTransform()
        transformIJKtoRAS.SetMatrix(ijkToRasMatrix)
        
        marchingCubes = vtk.vtkMarchingCubes()
        marchingCubes.SetInput(image)
        marchingCubes.SetValue(0,threshold)
        marchingCubes.ComputeScalarsOn()
        marchingCubes.ComputeGradientsOn()
        marchingCubes.ComputeNormalsOn()
        marchingCubes.GetOutput().ReleaseDataFlagOn()
        marchingCubes.Update()
        
        
        if transformIJKtoRAS.GetMatrix().Determinant() < 0:
            reverser = vtk.vtkReverseSense()
            reverser.SetInput(marchingCubes.GetOutput())
            reverser.ReverseNormalsOn()
            reverser.GetOutput().ReleaseDataFlagOn()
            reverser.Update()
            correctedOutput = reverser.GetOutput()
        else:
            correctedOutput = marchingCubes.GetOutput()
        
        transformer = vtk.vtkTransformPolyDataFilter()
        transformer.SetInput(correctedOutput)
        transformer.SetTransform(transformIJKtoRAS)
        transformer.GetOutput().ReleaseDataFlagOn()
        transformer.Update()
        
        normals = vtk.vtkPolyDataNormals()
        normals.ComputePointNormalsOn()
        normals.SetInput(transformer.GetOutput())
        normals.SetFeatureAngle(60)
        normals.SetSplitting(1)
        normals.GetOutput().ReleaseDataFlagOn()
        normals.Update()
        
        stripper = vtk.vtkStripper()
        stripper.SetInput(normals.GetOutput())
        stripper.GetOutput().ReleaseDataFlagOff()
        stripper.Update()
        stripper.GetOutput().Update()
        
        result = vtk.vtkPolyData()
        result.DeepCopy(stripper.GetOutput())
        result.Update()
        
        return result




