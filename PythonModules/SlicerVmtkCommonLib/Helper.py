# slicer imports
from __main__ import vtk, slicer

# python includes
import sys
import time

class Helper(object):
    '''
    classdocs
    '''

    @staticmethod
    def Info(message):
        '''

        '''

        print "[VMTK " + time.strftime("%m/%d/%Y %H:%M:%S") + "]: " + str(message)
        sys.stdout.flush()


    @staticmethod
    def Debug(message):
        '''

        '''

        showDebugOutput = 1
        from time import strftime
        if showDebugOutput:
            print "[VMTK " + time.strftime("%m/%d/%Y %H:%M:%S") + "] DEBUG: " + str(message)
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

        if isinstance(hierarchyNode,slicer.vtkMRMLMarkupsFiducialNode) and isinstance(volumeNode,slicer.vtkMRMLScalarVolumeNode):

            image = volumeNode.GetImageData()


            # now we have the children which are fiducialNodes - let's loop!
            for n in range(hierarchyNode.GetNumberOfFiducials()):

                currentCoordinatesRAS = [0,0,0]

                # grab the current coordinates
                hierarchyNode.GetNthFiducialPosition(n,currentCoordinatesRAS)

                # convert the RAS to IJK
                currentCoordinatesIJK = Helper.ConvertRAStoIJK(volumeNode,currentCoordinatesRAS)

                # strip the last element since we need a 3based tupel
                currentCoordinatesIJKlist = (int(currentCoordinatesIJK[0]),int(currentCoordinatesIJK[1]),int(currentCoordinatesIJK[2]))
                outputIds.InsertNextId(int(image.ComputePointId(currentCoordinatesIJKlist)))



        # IdList was created, return it even if it might be empty
        return outputIds

    @staticmethod
    def ConvertRAStoIJK(volumeNode,rasCoordinates):
        '''
        '''
        rasToIjkMatrix = vtk.vtkMatrix4x4()
        volumeNode.GetRASToIJKMatrix(rasToIjkMatrix)

        # the RAS coordinates need to be 4
        if len(rasCoordinates) < 4:
            rasCoordinates.append(1)

        ijkCoordinates = rasToIjkMatrix.MultiplyPoint(rasCoordinates)

        return ijkCoordinates


    @staticmethod
    def extractROI(originalVolumeID,newVolumeID,rasCoordinates,diameter):
        '''
        '''

        originalVolume = slicer.mrmlScene.GetNodeByID(originalVolumeID)
        newVolume = slicer.mrmlScene.GetNodeByID(newVolumeID)

        # code below converted from cropVolume module by A. Fedorov
        # optimized after that :)

        inputRASToIJK = vtk.vtkMatrix4x4()
        inputIJKToRAS = vtk.vtkMatrix4x4()
        outputIJKToRAS = vtk.vtkMatrix4x4()
        outputRASToIJK = vtk.vtkMatrix4x4()
        volumeXform = vtk.vtkMatrix4x4()
        T = vtk.vtkMatrix4x4()

        originalVolume.GetRASToIJKMatrix(inputRASToIJK)
        originalVolume.GetIJKToRASMatrix(inputIJKToRAS)

        outputIJKToRAS.Identity()
        outputRASToIJK.Identity()

        volumeXform.Identity()

        T.Identity()

        # if the originalVolume is under a transform
        volumeTransformNode = originalVolume.GetParentTransformNode()
        if volumeTransformNode:
            volumeTransformNode.GetMatrixTransformToWorld(volumeXform)
            volumeXform.Invert()

        maxSpacing = max(originalVolume.GetSpacing())

        # build our box
        rX = diameter*4*maxSpacing
        rY = diameter*4*maxSpacing
        rZ = diameter*4*maxSpacing
        cX = rasCoordinates[0]
        cY = rasCoordinates[1]
        cZ = rasCoordinates[2]

        inputSpacingX = originalVolume.GetSpacing()[0]
        inputSpacingY = originalVolume.GetSpacing()[1]
        inputSpacingZ = originalVolume.GetSpacing()[2]

        outputExtentX = int(2.0*rX/inputSpacingX)
        outputExtentY = int(2.0*rY/inputSpacingY)
        outputExtentZ = int(2.0*rZ/inputSpacingZ)

        # configure spacing
        outputIJKToRAS.SetElement(0,0,inputSpacingX)
        outputIJKToRAS.SetElement(1,1,inputSpacingY)
        outputIJKToRAS.SetElement(2,2,inputSpacingZ)

        # configure origin
        outputIJKToRAS.SetElement(0,3,(cX-rX+inputSpacingX*0.5))
        outputIJKToRAS.SetElement(1,3,(cY-rY+inputSpacingY*0.5))
        outputIJKToRAS.SetElement(2,3,(cZ-rZ+inputSpacingZ*0.5))

        outputRASToIJK.DeepCopy(outputIJKToRAS)
        outputRASToIJK.Invert()

        T.DeepCopy(outputIJKToRAS)
        T.Multiply4x4(volumeXform,T,T)
        T.Multiply4x4(inputRASToIJK,T,T)

        resliceT = vtk.vtkTransform()
        resliceT.SetMatrix(T)

        reslicer = vtk.vtkImageReslice()
        reslicer.SetInterpolationModeToLinear()
        reslicer.SetInputData(originalVolume.GetImageData())
        reslicer.SetOutputExtent(0,int(outputExtentX),0,int(outputExtentY),0,int(outputExtentZ))
        reslicer.SetOutputOrigin(0,0,0)
        reslicer.SetOutputSpacing(1,1,1)
        #reslicer.SetOutputOrigin(image.GetOrigin())
        #reslicer.SetOutputSpacing(image.GetSpacing())
        reslicer.SetResliceTransform(resliceT)
        reslicer.UpdateWholeExtent()

        changer = vtk.vtkImageChangeInformation()
        changer.SetInputData(reslicer.GetOutput())
        changer.SetOutputOrigin(0,0,0)
        changer.SetOutputSpacing(1,1,1)
        #changer.SetOutputOrigin(image.GetOrigin())
        # changer.SetOutputSpacing(image.GetSpacing())
        changer.Update()

        outImageData = vtk.vtkImageData()
        outImageData.DeepCopy(changer.GetOutput())

        newVolume.SetAndObserveImageData(outImageData)
        newVolume.SetIJKToRASMatrix(outputIJKToRAS)
        newVolume.SetRASToIJKMatrix(outputRASToIJK)

        newVolume.Modified()
