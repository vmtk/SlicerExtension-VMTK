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

#define WORKER_MESSAGE(msg) mtx.lock();\
                            std::cout << msg << std::endl;\
                            mtx.unlock();

vtkStandardNewMacro(vtkCrossSectionCompute);

void vtkCrossSectionCompute::PrintSelf(ostream& os, vtkIndent indent)
{
    vtkObject::PrintSelf(os,indent);
    
    os << indent << "numberOfThreads: " << this->NumberOfThreads << "\n";
    os << indent << "inputCenterlineNode: " << this->InputCenterlineNode << "\n";
    os << indent << "inputSurfaceNode: " << this->InputSurfaceNode << "\n";
    os << indent << "inputSegmentID: " << this->InputSegmentID << "\n";
}

// The surface polydata is constant. Create it once only.
bool vtkCrossSectionCompute::SetInputSurfaceNode(vtkMRMLNode * inputSurface, const std::string& inputSegmentId)
{
  this->InputSurfaceNode = inputSurface;
  this->InputSegmentID = inputSegmentId;
  if (this->InputSurfaceNode->IsA("vtkMRMLSegmentationNode"))
  {
    vtkMRMLSegmentationNode * inputSegmentationNode = vtkMRMLSegmentationNode::SafeDownCast(this->InputSurfaceNode);
    inputSegmentationNode->CreateClosedSurfaceRepresentation();
    inputSegmentationNode->GetClosedSurfaceRepresentation(this->InputSegmentID, this->ClosedSurfacePolyData);
  }
  else if (this->InputSurfaceNode->IsA("vtkMRMLModelNode"))
  {
    vtkMRMLModelNode * inputModelNode = vtkMRMLModelNode::SafeDownCast(this->InputSurfaceNode);
    this->ClosedSurfacePolyData->DeepCopy(inputModelNode->GetPolyData());
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
  if (this->InputCenterlineNode == NULL)
  {     
    std::cout << "Input centerline is NULL." << std::endl;
    return;
  }
  if (this->InputSurfaceNode == NULL)
  {     
    std::cout << "Input surface is NULL." << std::endl;
    return;
  }
  if (this->InputSegmentID.empty())
  {     
    std::cout << "Input segment ID is unknown." << std::endl;
    return;
  }
  /*
   * Divide the number of centerline points in equal blocks per thread.
   * The last block will include the residual points also.
   */
  const unsigned int numberOfValues = crossSectionAreaArray->GetNumberOfValues();
  unsigned int residual = numberOfValues % this->NumberOfThreads;
  unsigned int numberOfValuesPerBlock = (numberOfValues - residual) / this->NumberOfThreads;
  
  std::vector<std::thread> threads;
  std::vector<vtkSmartPointer<vtkDoubleArray>> bufferArrays;
  
  for (unsigned int i = 0; i < this->NumberOfThreads; i++)
  {
    unsigned int startPointIndex = i * numberOfValuesPerBlock;
    unsigned int endPointIndex = ((i + 1) * numberOfValuesPerBlock) - 1;
    if (i == (this->NumberOfThreads -1))
    {
        endPointIndex += residual;
    }

    /* 
     * Give each thread a copy of the closed surface.
     */
    vtkSmartPointer<vtkPolyData> closedSurfacePolyDataCopy = vtkSmartPointer<vtkPolyData>::New();
    closedSurfacePolyDataCopy->DeepCopy(this->ClosedSurfacePolyData.Get());
    
    /* 
     * Give each thread a copy of the centerline.
     */
    vtkMRMLNode * inputCenterlineNodeCopy;
    
    if (this->InputCenterlineNode->IsA("vtkMRMLModelNode"))
    {
        // Give each thread a copy of each centerline.
        vtkMRMLModelNode * inputModel = vtkMRMLModelNode::SafeDownCast(this->InputCenterlineNode);
        inputCenterlineNodeCopy = vtkMRMLModelNode::New();
        inputCenterlineNodeCopy->Copy(inputModel);
    }
    else if (this->InputCenterlineNode->IsA("vtkMRMLMarkupsCurveNode"))
    {
        vtkMRMLMarkupsCurveNode * inputCurve = vtkMRMLMarkupsCurveNode::SafeDownCast(this->InputCenterlineNode);
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
  for (unsigned int i = 0; i < this->NumberOfThreads; i++)
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
        // Cross-section area is not calculated at last point for a model.
        vtkMRMLModelNode * inputModel = vtkMRMLModelNode::SafeDownCast(inputCenterlineNode);
        vtkPoints * modelPoints = inputModel->GetMesh()->GetPoints();
        const unsigned int numberOfPoints = modelPoints->GetNumberOfPoints();
        if (endPointIndex == (numberOfPoints - 1))
        {
            const unsigned int blockLastPointIndex = bufferArray->GetNumberOfTuples() - 1;
            const unsigned int blockBeforeLastPointIndex = bufferArray->GetNumberOfTuples() - 1 - 1;
            bufferArray->SetTuple3(blockLastPointIndex,
                                   bufferArray->GetTuple3(blockLastPointIndex)[0],
                                   bufferArray->GetTuple3(blockBeforeLastPointIndex)[1],
                                   bufferArray->GetTuple3(blockBeforeLastPointIndex)[2]);
        }
    }
    
    // The centerline copy is not needed anymore.
    inputCenterlineNode->Delete();
    
    #if DEVTIME != 0
    mtx.lock();
    double endTime = GetTimeOfDay();;
    cout << "This thread : " << std::this_thread::get_id() << " "
        << (endTime - startTime) / 1000000 << " seconds" << endl;
    mtx.unlock();
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
        WORKER_MESSAGE("Input centerline is NULL.");
        return NULL;
    }
    if (closedSurfacePolyData == NULL)
    {
        WORKER_MESSAGE("Closed  surface polydata is NULL.");
        return NULL;
    }
    
    double center[3] = {0.0, 0.0, 0.0};
    double normal[3] = {0.0, 0.0, 0.0};
    if (inputCenterlineNode->IsA("vtkMRMLModelNode"))
    {
        vtkMRMLModelNode * inputModel = vtkMRMLModelNode::SafeDownCast(inputCenterlineNode);
        vtkPoints * modelPoints = inputModel->GetMesh()->GetPoints();
        const unsigned int numberOfPoints = modelPoints->GetNumberOfPoints();
        double centerLocal[3] = {0.0, 0.0, 0.0};
        modelPoints->GetPoint(pointIndex, centerLocal);
        inputModel->TransformPointToWorld(centerLocal, center);
        // Exclude the last centerline point
        if (pointIndex < (numberOfPoints - 1))
        {
            double centerInc[3] = {0.0, 0.0, 0.0};
            // note that this +1 does not work for the last point
            double centerLocalInc[3] = {0.0, 0.0, 0.0};
            modelPoints->GetPoint(pointIndex + 1, centerLocalInc);
            inputModel->TransformPointToWorld(centerLocalInc, centerInc);
            for (unsigned int i = 0; i < 3; i++)
                normal[i] = centerInc[i] - center[i];
        }
        else
        // Return an empty polydata at the last centerline point
        {
            return vtkPolyData::New();
            /*
             * Sample output at last point
             * 337 : pointIndex
             * centerInc    center      normal
             * 4.49817e-43  -10.7484    10.7484337
             * 0            17.932     -17.932337
             * 7.21367e+25  -84.3496    7.21367e+25
             * 
             */
        }
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
        WORKER_MESSAGE("Wrong input centerline node.");
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
        WORKER_MESSAGE("Could not cut segment. Is it visible in 3D view?");
        return NULL;
    }
    if (planePoints->GetNumberOfPoints() < 3)
    {
        WORKER_MESSAGE("Not enough points to create surface");
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
