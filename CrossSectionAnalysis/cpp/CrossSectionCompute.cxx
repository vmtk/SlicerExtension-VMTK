/*
 * This file was created by SET [Surgeon] [Hobbyist developer].
 */
#include "CrossSectionCompute.h"
#include <iostream>
#include <thread>
#include <mutex>
#include <math.h> // sqrt
#include <vector>

#include <vtkMRMLModelNode.h>
#include <vtkMRMLMarkupsCurveNode.h>
#include <vtkMRMLSegmentationNode.h>
#include <vtkPlane.h>
#include <vtkCutter.h>
#include <vtkConnectivityFilter.h>
#include <vtkContourTriangulator.h>
#include <vtkMatrix4x4.h> // Should not be required.
#include <vtkMassProperties.h>
#include <vtkMath.h> // Pi()

std::mutex mtx;

vtkCrossSectionCompute::vtkCrossSectionCompute()
{
  numberOfThreads = 1;
  inputCenterlineNode = NULL;
  inputSurfaceNode = NULL;
  inputSegmentID = "";
  closedSurfacePolyData = vtkSmartPointer<vtkPolyData>::New();
}

vtkCrossSectionCompute::~vtkCrossSectionCompute()
{
}

// The surface polydata is constant. Create it once only.
bool vtkCrossSectionCompute::SetInputSurfaceNode(vtkMRMLNode * inputSurface, const std::string& inputSegmentId)
{
  inputSurfaceNode = inputSurface;
  inputSegmentID = inputSegmentId;
  if (inputSurfaceNode->IsA("vtkMRMLSegmentationNode"))
  {
    vtkMRMLSegmentationNode * inputSegmentationNode = vtkMRMLSegmentationNode::SafeDownCast(inputSurfaceNode);
    inputSegmentationNode->CreateClosedSurfaceRepresentation();
    inputSegmentationNode->GetClosedSurfaceRepresentation(inputSegmentID, closedSurfacePolyData);
  }
  else if (inputSurfaceNode->IsA("vtkMRMLModelNode"))
  {
    vtkMRMLModelNode * inputModelNode = vtkMRMLModelNode::SafeDownCast(inputSurfaceNode);
    closedSurfacePolyData->DeepCopy(inputModelNode->GetPolyData());
  }
  else
  {
    std::cout << "Invalid closed surface." << std::endl;
    return false;
  }
  return true;
}

void vtkCrossSectionCompute::UpdateTable(vtkDoubleArray * crossSectionAreaArray, vtkDoubleArray * ceDiameterArray)
{
  if (inputCenterlineNode == NULL)
  {     
    std::cout << "Input centerline is NULL." << std::endl;
    return;
  }
  if (inputSurfaceNode == NULL)
  {     
    std::cout << "Input surface is NULL." << std::endl;
    return;
  }
  if (inputSegmentID.empty())
  {     
    std::cout << "Input segment ID is unknown." << std::endl;
    return;
  }
  /*
   * Divide the number of centerline points in equal blocks per thread.
   * The last block will include the residual points also.
   */
  const unsigned int numberOfValues = crossSectionAreaArray->GetNumberOfValues();
  unsigned int residual = numberOfValues % numberOfThreads;
  unsigned int numberOfValuesPerBlock = (numberOfValues - residual) / numberOfThreads;
  
  std::vector<std::thread> threads;
  std::vector<vtkSmartPointer<vtkDoubleArray>> bufferArrays;
  
  for (unsigned int i = 0; i < numberOfThreads; i++)
  {
    unsigned int startPointIndex = i * numberOfValuesPerBlock;
    unsigned int endPointIndex = ((i + 1) * numberOfValuesPerBlock) - 1;
    if (i == (numberOfThreads -1))
    {
        endPointIndex += residual;
    }

    /* 
     * Give each thread a copy of the closed surface.
     */
    vtkSmartPointer<vtkPolyData> closedSurfacePolyDataCopy = vtkSmartPointer<vtkPolyData>::New();
    closedSurfacePolyDataCopy->DeepCopy(closedSurfacePolyData.Get());
    
    /* 
     * Give each thread a copy of the centerline.
     */
    vtkMRMLNode * inputCenterlineNodeCopy;
    
    if (inputCenterlineNode->IsA("vtkMRMLModelNode"))
    {
        // Give each thread a copy of each centerline.
        vtkMRMLModelNode * inputModel = vtkMRMLModelNode::SafeDownCast(inputCenterlineNode);
        inputCenterlineNodeCopy = vtkMRMLModelNode::New();
        inputCenterlineNodeCopy->Copy(inputModel);
    }
    else if (inputCenterlineNode->IsA("vtkMRMLMarkupsCurveNode"))
    {
        vtkMRMLMarkupsCurveNode * inputCurve = vtkMRMLMarkupsCurveNode::SafeDownCast(inputCenterlineNode);
        // Program dies here too.
        inputCenterlineNodeCopy = vtkMRMLMarkupsCurveNode::New();
        inputCenterlineNodeCopy->Copy(inputCurve);
    }
    else
    {
        std::cout << "Invalid centerline." << std::endl;
        return;
    }
    
    // Each thread stores the results in this array.
    vtkSmartPointer<vtkDoubleArray> bufferArray = vtkSmartPointer<vtkDoubleArray>::New();
    bufferArray->SetNumberOfComponents(3);
    bufferArrays.push_back(bufferArray);
    
    threads.push_back(std::thread(vtkCrossSectionComputeWorker(),
                                  inputCenterlineNodeCopy,
                                  closedSurfacePolyDataCopy,
                                  bufferArrays[i],
                                  startPointIndex, endPointIndex));
  }
  for (unsigned int i = 0; i < threads.size(); i++)
  {
      threads[i].join();
  }
  // Update the output table columns.
  mtx.lock();
  for (unsigned int i = 0; i < numberOfThreads; i++)
  {
      vtkDoubleArray * bufferArray = (bufferArrays[i].Get());
      for (unsigned int r = 0; r < bufferArray->GetNumberOfTuples(); r++)
      {
          double tupleValues[3] = {0.0, 0.0, 0.0};
          tupleValues[0] = bufferArray->GetTuple3(r)[0]; // Output table row index
          tupleValues[1] = bufferArray->GetTuple3(r)[1]; // Cross-section area
          tupleValues[2] = bufferArray->GetTuple3(r)[2]; // CE diameter
          crossSectionAreaArray->SetValue((int) tupleValues[0], tupleValues[1]);
          ceDiameterArray->SetValue((int) tupleValues[0], tupleValues[2]);
      }
  }
  mtx.unlock();
}

/////////////////////////////////////////////////////////////////////////

vtkCrossSectionComputeWorker::vtkCrossSectionComputeWorker()
{
}

vtkCrossSectionComputeWorker::~vtkCrossSectionComputeWorker()
{
}

void vtkCrossSectionComputeWorker::operator () (vtkMRMLNode * inputCenterlineNode,
                             vtkPolyData * closedSurfacePolyData,
                             vtkDoubleArray * bufferArray,
                             unsigned int startPointIndex,
                             unsigned int endPointIndex)
{
#if DEVTIME != 0
    double startTime = GetTimeOfDay();
#endif
    for (unsigned int i = startPointIndex; i <= endPointIndex; i++)
    {
        // Get the contout polydata
        vtkPolyData * polydata = ComputeCrossSectionPolydata(inputCenterlineNode, closedSurfacePolyData, i);
        {
            // Get the surface area and circular equivalent diameter
            vtkNew<vtkMassProperties> crossSectionProperties;
            crossSectionProperties->SetInputData(polydata);
            const double crossSectionSurfaceArea = crossSectionProperties->GetSurfaceArea();
            const double ceDiameter = (sqrt(crossSectionSurfaceArea / vtkMath::Pi())) * 2;
            
            bufferArray->InsertNextTuple3((double) i, crossSectionSurfaceArea, ceDiameter);
        }
        polydata->Delete();
    }
    
    // Manage last point for an input centerline model
    if (inputCenterlineNode->IsA("vtkMRMLModelNode"))
    {
        // Cross-section area cannot be calculated at last point for a model.
        vtkMRMLModelNode * inputModel = vtkMRMLModelNode::SafeDownCast(inputCenterlineNode);
        vtkPoints * modelPoints = inputModel->GetMesh()->GetPoints();
        const unsigned int numberOfPoints = modelPoints->GetNumberOfPoints();
        if (endPointIndex == (numberOfPoints - 1))
        {
            const unsigned int beforeLastPointIndex = endPointIndex - 1;
            bufferArray->SetTuple3(endPointIndex,
                                   bufferArray->GetTuple3(beforeLastPointIndex)[0],
                                   bufferArray->GetTuple3(beforeLastPointIndex)[1],
                                   bufferArray->GetTuple3(beforeLastPointIndex)[2]);
        }
    }
    
    inputCenterlineNode->Delete();
    
    #if DEVTIME != 0
    double endTime = GetTimeOfDay();;
    cout << "This thread : " << std::this_thread::get_id() << " "
        << (endTime - startTime) / 1000000 << " seconds" << endl;
    #endif
}

// Translated and adapted from the Python implementation.
vtkPolyData * vtkCrossSectionComputeWorker::ComputeCrossSectionPolydata(
                                vtkMRMLNode * inputCenterlineNode,
                                vtkPolyData * closedSurfacePolyData,
                                unsigned int pointIndex)
{
    if (inputCenterlineNode == NULL)
    {
        std::cout << "Input centerline is NULL." << std::endl;
        return NULL;
    }
    if (closedSurfacePolyData == NULL)
    {
        std::cout << "Closed  surface polydata is NULL." << std::endl;
        return NULL;
    }
    
    double center[3] = {0.0, 0.0, 0.0};
    double normal[3] = {0.0, 0.0, 0.0};
    if (inputCenterlineNode->IsA("vtkMRMLModelNode"))
    {
        vtkMRMLModelNode * inputModel = vtkMRMLModelNode::SafeDownCast(inputCenterlineNode);
        vtkPoints * modelPoints = inputModel->GetMesh()->GetPoints();
        double centerLocal[3] = {0.0, 0.0, 0.0};
        modelPoints->GetPoint(pointIndex, centerLocal);
        inputModel->TransformPointToWorld(centerLocal, center);
        double centerInc[3] = {0.0, 0.0, 0.0};
        // note that this +1 does not work for the last point
        double centerLocalInc[3] = {0.0, 0.0, 0.0};
        modelPoints->GetPoint(pointIndex + 1, centerLocalInc);
        inputModel->TransformPointToWorld(centerLocalInc, centerInc);
        for (unsigned int i = 0; i < 3; i++)
            normal[i] = centerInc[i] - center[i];
    }
    else if (inputCenterlineNode->IsA("vtkMRMLMarkupsCurveNode"))
    {
        vtkMRMLMarkupsCurveNode * inputCurve = vtkMRMLMarkupsCurveNode::SafeDownCast(inputCenterlineNode);
        // Calls to *any* function of markups curve always crash Slicer
        vtkPoints * curvePoints = inputCurve->GetCurvePointsWorld();
        curvePoints->GetPoint(pointIndex, center);
        // This seems to have been fixed of a previous bug.
        inputCurve->GetCurveDirectionAtPointIndexWorld(pointIndex, normal);
        /*vtkNew<vtkMatrix4x4> curvePointToWorld;
         *   inputCurve->GetCurvePointToWorldTransformAtPointIndex(pointIndex, curvePointToWorld);
         *   for (unsigned int i = 0; i < 3; i++)
         *           normal[i] = curvePointToWorld->GetElement(i, 2);*/
    }
    else
    {
        std::cout << "Wrong input centerline node." << std::endl;
        return NULL;
    }
    
    // Place a plane perpendicular to the centerline
    vtkNew<vtkPlane> plane;
    plane->SetOrigin(center);
    plane->SetNormal(normal);
    
    // Cut through the closed surface and get the points of the contour.
    vtkNew<vtkCutter> planeCut;
    planeCut->SetInputData(closedSurfacePolyData);
    planeCut->SetCutFunction(plane);
    planeCut->Update();
    vtkPoints * planePoints = planeCut->GetOutput()->GetPoints();
    if (planePoints == NULL)
    {
        std::cout << "Could not cut segment. Is it visible in 3D view?" << std::endl;
        return NULL;
    }
    if (planePoints->GetNumberOfPoints() < 3)
    {
        std::cout << "Not enough points to create surface" << std::endl;
        return NULL;
    }
    
    // Keep the closed surface around the centerline
    vtkNew<vtkConnectivityFilter> connectivityFilter;
    connectivityFilter->SetInputData(planeCut->GetOutput());
    connectivityFilter->SetClosestPoint(center);
    connectivityFilter->SetExtractionModeToClosestPointRegion();
    connectivityFilter->Update();
    
    // Triangulate the contour points
    vtkNew<vtkContourTriangulator> contourTriangulator;
    contourTriangulator->SetInputData(connectivityFilter->GetPolyDataOutput());
    contourTriangulator->Update();
    
    vtkPolyData * contourPolyData = vtkPolyData::New();
    contourPolyData->DeepCopy(contourTriangulator->GetOutput());
    
    return contourPolyData;
}
