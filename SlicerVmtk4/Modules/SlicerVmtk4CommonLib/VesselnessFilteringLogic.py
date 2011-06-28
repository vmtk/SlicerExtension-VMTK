# vtk includes
from __main__ import vtk

class VesselnessFilteringLogic(object):
    '''
    classdocs
    '''


    def __init__(self):
        '''
        Constructor
        '''

    def importVmtk(self):
        '''
        '''
        # import the vmtk libraries
        try:
            from libvtkvmtkSegmentationPython import *
        except ImportError:
            print "FAILURE: Unable to import the SlicerVmtk4 libraries!"
        
        
    def performFrangiVesselness(self, image, minimumDiameter, maximumDiameter, discretizationSteps, alpha, beta, gamma):
        '''
        '''
        self.importVmtk()

        cast = vtk.vtkImageCast()
        cast.SetInput(image)
        cast.SetOutputScalarTypeToFloat()
        cast.Update()
        image = cast.GetOutput()

        v = vtkvmtkVesselnessMeasureImageFilter()
        v.SetInput(image)
        v.SetSigmaMin(minimumDiameter)
        v.SetSigmaMax(maximumDiameter)
        v.SetNumberOfSigmaSteps(discretizationSteps)
        v.SetAlpha(alpha)
        v.SetBeta(beta)
        v.SetGamma(gamma)
        v.Update()

        outImageData = vtk.vtkImageData()
        outImageData.DeepCopy(v.GetOutput())
        outImageData.Update()
        outImageData.GetPointData().GetScalars().Modified()

        return outImageData        


    def getDiameter(self, image, x, y, z):
        '''
        '''
        
        edgeImage = self.performLaplaceOfGaussian(image)
        
        foundDiameter = False
        
        edgeImageSeedValue = edgeImage.GetScalarComponentAsFloat(x, y, z, 0)
        seedValueSign = cmp(edgeImageSeedValue, 0) # returns 1 if >0 or -1 if <0
        
        # the list of hits
        # [left, right, top, bottom, front, back]
        hits = [False, False, False, False, False, False]
        
        distanceFromSeed = 1
        
        while not foundDiameter:
            
            if (distanceFromSeed >= edgeImage.GetDimensions()[0]
                or distanceFromSeed >= edgeImage.GetDimensions()[1]
                or distanceFromSeed >= edgeImage.GetDimensions()[2]):
                # we are out of bounds
                break
                        
            # get the values for the lookahead directions in the edgeImage
            edgeValues = [edgeImage.GetScalarComponentAsFloat(x - distanceFromSeed, y, z, 0), # left
                          edgeImage.GetScalarComponentAsFloat(x + distanceFromSeed, y, z, 0), # right
                          edgeImage.GetScalarComponentAsFloat(x, y + distanceFromSeed, z, 0), # top
                          edgeImage.GetScalarComponentAsFloat(x, y - distanceFromSeed, z, 0), # bottom
                          edgeImage.GetScalarComponentAsFloat(x, y, z + distanceFromSeed, 0), # front
                          edgeImage.GetScalarComponentAsFloat(x, y, z - distanceFromSeed, 0)] # back
            
            # first loop, check if we have hits
            for v in range(len(edgeValues)):
                
                if not hits[v] and cmp(edgeValues[v],0) != seedValueSign:
                    # hit
                    hits[v] = True
                
            # now check if we have two hits in opposite directions
            if hits[0] and hits[1]:
                # we have the diameter!
                foundDiameter = True
                break
                
            if hits[2] and hits[3]:
                foundDiameter = True
                break
            
            if hits[4] and hits[5]:
                foundDiameter = True
                break    
                            
            # increase distance from seed for next iteration
            distanceFromSeed += 1
        
        # we now just return the distanceFromSeed
        # if the diameter was not detected properly, this can equal one of the image dimensions
        return distanceFromSeed
    
        
        
    def performLaplaceOfGaussian(self, image):
        '''
        '''
        
        gaussian = vtk.vtkImageGaussianSmooth()
        gaussian.SetInput(image)
        gaussian.Update()
        
        laplacian = vtk.vtkImageLaplacian()
        laplacian.SetInput(gaussian.GetOutput())
        laplacian.Update()
        
        outImageData = vtk.vtkImageData()
        outImageData.DeepCopy(laplacian.GetOutput())
        outImageData.Update()        

        return outImageData
    
    
    def calculateContrastMeasure(self,image,x,y,z,diameter):
        '''
        '''
        seedValue = image.GetScalarComponentAsFloat(x,y,z,0)
        
        outsideValues = [seedValue - image.GetScalarComponentAsFloat(x+(2*diameter),y,z,0), # right
                         seedValue - image.GetScalarComponentAsFloat(x-(2*diameter),y,z,0), # left
                         seedValue - image.GetScalarComponentAsFloat(x,y+(2*diameter),z,0), # top
                         seedValue - image.GetScalarComponentAsFloat(x,y-(2*diameter),z,0), # bottom
                         seedValue - image.GetScalarComponentAsFloat(x,y,z+(2*diameter),0), # front
                         seedValue - image.GetScalarComponentAsFloat(x,y,z-(2*diameter),0)] # back
        
        differenceValue = max(outsideValues)
        
        contrastMeasure = differenceValue / 10 # get 1/10 of it
        
        return 2 * contrastMeasure
    
