# slicer imports
from __main__ import vtk, slicer

# python includes
import sys
from time import strftime

class Helper(object):
    '''
    classdocs
    '''

    @staticmethod    
    def Info(message):
        '''
        
        '''

        print "[VMTK " + strftime("%m/%d/%Y %H:%M:%S") + "]: " + str(message)
        sys.stdout.flush()

        
    @staticmethod    
    def Debug(message):
        '''
        
        '''

        showDebugOutput = 1
        
        if showDebugOutput:
            print "[VMTK " + strftime("%m/%d/%Y %H:%M:%S") + "] DEBUG: " + str(message)
            sys.stdout.flush()

    @staticmethod
    def CreateSpace(n):
        '''
        '''
        spacer = ""
        for s in range(n):
          spacer += " "
          
        return spacer
    
    @staticmethod
    def CheckIfVmtkIsInstalled():
        '''
        '''
        vmtkInstalled = True
        try:
            fastMarching = vtkvmtkFastMarchingUpwindGradientImageFilter()
            fastMarching = None
        except Exception:
            vmtkInstalled = False
            
        return vmtkInstalled
    
    @staticmethod
    def convertFiducialHierarchyToVtkIdList(hierarchyNode,volumeNode):
        '''
        '''
        outputIds = vtk.vtkIdList()
        
        if not hierarchyNode or not volumeNode:
            return outputIds
        
        if isinstance(hierarchyNode,slicer.vtkMRMLAnnotationHierarchyNode) and isinstance(volumeNode,slicer.vtkMRMLScalarVolumeNode):
            
            childrenNodes = vtk.vtkCollection()
            
            image = volumeNode.GetImageData()
            hierarchyNode.GetChildrenDisplayableNodes(childrenNodes)
            
            rasToIjkMatrix = vtk.vtkMatrix4x4()
            volumeNode.GetRASToIJKMatrix(rasToIjkMatrix)        
            
            # now we have the childrens which are fiducialNodes - let's loop!
            for n in range(childrenNodes.GetNumberOfItems()):
                
                currentFiducial = childrenNodes.GetItemAsObject(n)
                currentCoordinatesRAS = [0,0,0]
                
                # grab the current coordinates
                currentFiducial.GetFiducialCoordinates(currentCoordinatesRAS)
                currentCoordinatesRAS.append(1)
                
                # convert to IJK
                currentCoordinatesIJK = rasToIjkMatrix.MultiplyPoint(currentCoordinatesRAS)
                # strip the last element since we need a 3based tupel
                currentCoordinatesIJKlist = (currentCoordinatesIJK[0],currentCoordinatesIJK[1],currentCoordinatesIJK[2])
                print currentCoordinatesIJKlist
                outputIds.InsertNextId(image.ComputePointId(currentCoordinatesIJKlist))
        
    
    
        # IdList was created, return it even if it might be empty
        return outputIds    
                    
