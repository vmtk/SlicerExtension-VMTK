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
    std::cout << "DTOR" << std::endl;
}

// Translated and adapted from the Python implementation.
vtkPolyData * vtkCrossSectionCompute::ComputeCrossSectionPolydata(unsigned int pointIndex)
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
    inputCurve->GetCurvePointToWorldTransformAtPointIndex(pointIndex, curvePointToWorld);
    for (unsigned int i = 0; i < 3; i++)
            normal[i] = curvePointToWorld->GetElement(i, 2);*/
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

/*
 * Static function.
 * Run by each thread.
 * The work horse is the worker instance.
 */
void vtkCrossSectionCompute::DoCompute(vtkDoubleArray * bufferArray,
				unsigned int startPointIndex,
	                        unsigned int endPointIndex,
				vtkCrossSectionCompute * worker)
{
#if DEVTIME != 0
  double startTime = worker->GetTimeOfDay();
#endif
  for (unsigned int i = startPointIndex; i <= endPointIndex; i++)
  {
    // Get the contout polydata
    vtkSmartPointer<vtkPolyData> polydata = worker->ComputeCrossSectionPolydata(i);
    // Get the surface area and circular equivalent diameter
    vtkNew<vtkMassProperties> crossSectionProperties;
    crossSectionProperties->SetInputData(polydata.Get());
    const double crossSectionSurfaceArea = crossSectionProperties->GetSurfaceArea();
    const double ceDiameter = (sqrt(crossSectionSurfaceArea / vtkMath::Pi())) * 2;
    
    bufferArray->InsertNextTuple3(i, crossSectionSurfaceArea, ceDiameter);;
    polydata->Delete();
  }

  // Manage last point for an input centerline model
  if (worker->inputCenterlineNode->IsA("vtkMRMLModelNode"))
  {
    // Cross-section area cannot be calculated at last point for a model.
    vtkMRMLModelNode * inputModel = vtkMRMLModelNode::SafeDownCast(worker->inputCenterlineNode);
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

  worker->inputCenterlineNode->Delete();
  delete worker;
#if DEVTIME != 0
  double endTime = worker->GetTimeOfDay();;
  cout << "This thread : " << (endTime - startTime) / 1000000 << " seconds" << endl;
#endif
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
     * This avoids crashes. VTK does not seem thread safe everywhere.
     */
    vtkSmartPointer<vtkPolyData> closedSurfacePolyDataCopy = vtkSmartPointer<vtkPolyData>::New();
    closedSurfacePolyDataCopy->DeepCopy(closedSurfacePolyData);
    
    // A new instance of this class passed in to each thread.
    vtkCrossSectionCompute * worker = new vtkCrossSectionCompute();
    
    // Let not the threads compute again the close surface.
    worker->SetClosedSurfacePolyData(closedSurfacePolyDataCopy);
    
    if (inputCenterlineNode->IsA("vtkMRMLModelNode"))
    {
        // Give each thread a copy of each centerline.
        vtkMRMLModelNode * inputModel = vtkMRMLModelNode::SafeDownCast(inputCenterlineNode);
        vtkMRMLModelNode * inputModelCopy = vtkMRMLModelNode::New();
        inputModelCopy->Copy(inputModel);
        worker->SetInputCenterlineNode(inputModelCopy);
    }
    else if (inputCenterlineNode->IsA("vtkMRMLMarkupsCurveNode"))
    {
        vtkMRMLMarkupsCurveNode * inputCurve = vtkMRMLMarkupsCurveNode::SafeDownCast(inputCenterlineNode);
        // Program dies here too.
        vtkMRMLMarkupsCurveNode * inputCurveCopy = vtkMRMLMarkupsCurveNode::New();
        inputCurveCopy->Copy(inputCurve);
        worker->SetInputCenterlineNode(inputCurveCopy);
    }
    else
    {
        std::cout << "Invalid centerline." << std::endl;
        return;
    }
    
    vtkSmartPointer<vtkDoubleArray> bufferArray = vtkSmartPointer<vtkDoubleArray>::New();
    bufferArray->SetNumberOfComponents(3);
    bufferArrays.push_back(bufferArray);
    
    /*
        * Notes for me :
        * Don't use :
    std::thread t(DoCompute, crossSectionAreaArray, ceDiameterArray, startPointIndex, endPointIndex, worker);
    t.join();
        * It will just be sequential !
        * Don't use :
    threads.push_back(t)
        * t is deleted at block loop; won't even build.
        * https://thispointer.com/c11-multithreading-part-2-joining-and-detaching-threads/
        * Create thread directly in the container; it never lived here.
    */
    threads.push_back(std::thread(worker->DoCompute, bufferArrays[i], startPointIndex, endPointIndex, worker));
  }
  for (unsigned int i = 0; i < threads.size(); i++)
  {
      //std::cout << threads[i].get_id() << std::endl;
      threads[i].join();
  }
  mtx.lock();
  for (unsigned int i = 0; i < numberOfThreads; i++)
  {
      vtkDoubleArray * bufferArray = (bufferArrays[i].Get());
      for (unsigned int r = 0; r < bufferArray->GetNumberOfTuples(); r++)
      {
          double tupleValues[3];
          tupleValues[0] = bufferArray->GetTuple3(r)[0]; // Output table row index
          tupleValues[1] = bufferArray->GetTuple3(r)[1]; // Cross-section area
          tupleValues[2] = bufferArray->GetTuple3(r)[2]; // CE diameter
          crossSectionAreaArray->SetValue(tupleValues[0], tupleValues[1]);
          ceDiameterArray->SetValue(tupleValues[0], tupleValues[2]);
      }
  }
  mtx.unlock();
}


