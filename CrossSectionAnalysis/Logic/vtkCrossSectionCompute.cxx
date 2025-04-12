/*
 * This file was created by SET [Surgeon] [Hobbyist developer].
 * Valuable input comes from Andras Lasso (Perklab) in many areas.
 */
#include "vtkCrossSectionCompute.h"
#include <iostream>
#include <thread>
#include <mutex>
#include <math.h> // sqrt
#include <vector>

#include <vtkMRMLSegmentationNode.h>
#include <vtkMRMLModelNode.h>
#include <vtkPlane.h>
#include <vtkCutter.h>
#include <vtkPolyDataConnectivityFilter.h>
#include <vtkContourTriangulator.h>
#include <vtkMassProperties.h>
#include <vtkMath.h> // Pi()
#include <vtkParallelTransportFrame.h>
#include <vtkPointData.h>
#include <vtkMRMLMarkupsShapeNode.h>

std::mutex mtx;

vtkStandardNewMacro(vtkCrossSectionCompute);

//------------------------------------------------------------------------------
/**
 * This class works with generated centerline polydata. Each thread has one instance of this class running.
 */
class CrossSectionComputeWorker
{
public:

  CrossSectionComputeWorker();
  virtual ~CrossSectionComputeWorker();

  void operator () (vtkPolyData* generatedPolyData,
    vtkDoubleArray* generatedTangents,
    vtkPolyData* closedSurfacePolyData,
    vtkDoubleArray* bufferArray,
    vtkIdType startPointIndex,
    vtkIdType endPointIndex);

private:
  /**
   * Generates the cross-section polydata as closest contour
   * around the generated centerline point.
   * The result is returned in contourPolyData.
   */
  void ComputeCrossSectionPolydata(vtkPolyData* generatedPolyData,
    vtkDoubleArray* generatedTangents,
    vtkPolyData* closedSurfacePolyData,
    vtkIdType pointIndex,
    vtkPolyData* contourPolyData);
};

//------------------------------------------------------------------------------
vtkCrossSectionCompute::vtkCrossSectionCompute()
{
  this->NumberOfThreads = 1;
  this->InputSurfaceNode = nullptr;
  this->ClosedSurfacePolyData = vtkSmartPointer<vtkPolyData>::New();
}

vtkCrossSectionCompute::~vtkCrossSectionCompute()
{
}

void vtkCrossSectionCompute::PrintSelf(ostream& os, vtkIndent indent)
{
    vtkObject::PrintSelf(os,indent);
    
    os << indent << "numberOfThreads: " << this->NumberOfThreads << "\n";
    os << indent << "inputSurfaceNode: " << this->InputSurfaceNode << "\n";
    os << indent << "inputSegmentID: " << this->InputSegmentID << "\n";
}

// The surface polydata is constant. Create it once only.
bool vtkCrossSectionCompute::SetInputSurfaceNode(vtkMRMLNode * inputSurface, const std::string& inputSegmentId)
{
  this->InputSurfaceNode = inputSurface;
  this->InputSegmentID = inputSegmentId;
  if (std::string(this->InputSurfaceNode->GetClassName()) == std::string("vtkMRMLSegmentationNode"))
  {
    vtkMRMLSegmentationNode * inputSegmentationNode = vtkMRMLSegmentationNode::SafeDownCast(this->InputSurfaceNode);
    if (inputSegmentationNode == NULL)
    {
        vtkErrorMacro("Invalid surface segmentation node.");
        this->ClosedSurfacePolyData = nullptr;
        return false;
    }
    inputSegmentationNode->CreateClosedSurfaceRepresentation();
    inputSegmentationNode->GetClosedSurfaceRepresentation(this->InputSegmentID, this->ClosedSurfacePolyData);
  }
  else if (std::string(this->InputSurfaceNode->GetClassName()) == std::string("vtkMRMLModelNode"))
  {
    vtkMRMLModelNode * inputModelNode = vtkMRMLModelNode::SafeDownCast(this->InputSurfaceNode);
    if (inputModelNode == NULL)
    {
        vtkErrorMacro("Invalid surface model node.");
        this->ClosedSurfacePolyData = nullptr;
        return false;
    }
    this->ClosedSurfacePolyData->DeepCopy(inputModelNode->GetPolyData());
  }
  else if (std::string(this->InputSurfaceNode->GetClassName()) == std::string("vtkMRMLMarkupsShapeNode"))
  {
      vtkMRMLMarkupsShapeNode * inputShapeNode = vtkMRMLMarkupsShapeNode::SafeDownCast(this->InputSurfaceNode);
      if (inputShapeNode == NULL)
      {
          std::cout << "Invalid surface shape node." << std::endl;
          this->ClosedSurfacePolyData = nullptr;
          return false;
      }
      if (inputShapeNode->GetShapeName() != vtkMRMLMarkupsShapeNode::Tube)
      {
          std::cout << "Surface shape node is not a Tube." << std::endl;
          this->ClosedSurfacePolyData = nullptr;
          return false;
      }
      if (inputShapeNode->GetNumberOfControlPoints() < 4)
      {
          std::cout << "The Tube surface shape node must have at least 4 control points." << std::endl;
          this->ClosedSurfacePolyData = nullptr;
          return false;
      }
      this->ClosedSurfacePolyData->DeepCopy(inputShapeNode->GetShapeWorld());
  }
  else
  {
    vtkErrorMacro("Invalid closed surface.");
    this->ClosedSurfacePolyData = nullptr;
    return false;
  }
  return true;
}

/*
 * Sources of inspiration :
 * https://github.com/Slicer/Slicer/blob/19d2cbe4cfb5cd3d651f7cdfee1958d1f159d941/Modules/Loadable/Markups/MRML/vtkMRMLMarkupsCurveNode.cxx#L915
 * https://github.com/vmtk/SlicerExtension-VMTK/blob/81255c23d77e1549b82f4f21c2af7939282b020a/CrossSectionAnalysis/CrossSectionAnalysis.py#L1028
 * 
 */
void vtkCrossSectionCompute::SetInputCenterlinePolyData(vtkPolyData * inputCenterlinePolyData)
{    
    vtkSmartPointer<vtkParallelTransportFrame> curveCoordinateSystemGenerator = vtkSmartPointer<vtkParallelTransportFrame>::New();
    curveCoordinateSystemGenerator->SetInputData(inputCenterlinePolyData);
    curveCoordinateSystemGenerator->Update();
    
    this->GeneratedPolyData = curveCoordinateSystemGenerator->GetOutput();
    
    vtkPointData* pointData = this->GeneratedPolyData->GetPointData();
    this->GeneratedTangents = vtkDoubleArray::SafeDownCast(
        pointData->GetAbstractArray(curveCoordinateSystemGenerator->GetTangentsArrayName()));
}

bool vtkCrossSectionCompute::UpdateTable(vtkDoubleArray * crossSectionAreaArray, vtkDoubleArray * ceDiameterArray)
{
    if (this->InputSurfaceNode == nullptr)
    {     
        vtkErrorMacro("Input surface is NULL.");
        return false;
    }
    if (std::string(this->InputSurfaceNode->GetClassName()) == std::string("vtkMRMLSegmentationNode")
        && this->InputSegmentID.empty())
    {     
        vtkErrorMacro("Input segment ID is unknown.");
        return false;
    }
    /*
     * Divide the number of centerline points in equal blocks per thread.
     * The last block will include the residual points also.
     */
    const unsigned int numberOfValues = crossSectionAreaArray->GetNumberOfValues();
    unsigned int residual = numberOfValues % this->NumberOfThreads;
    unsigned int numberOfValuesPerBlock = (numberOfValues) / this->NumberOfThreads;
    
    std::vector<std::thread> threads;
    std::vector<vtkSmartPointer<vtkDoubleArray>> bufferArrays;
    
    for (unsigned int i = 0; i < this->NumberOfThreads; i++)
    {
        unsigned int startPointIndex = i * numberOfValuesPerBlock;
        unsigned int endPointIndex = ((i + 1) * numberOfValuesPerBlock) - 1;
        // The last block must include the residual points.
        if (i == (this->NumberOfThreads -1))
        {
            endPointIndex += residual;
        }
        
        /* 
         * Give each thread a copy of the closed surface.
         */
        vtkSmartPointer<vtkPolyData> closedSurfacePolyDataCopy = vtkSmartPointer<vtkPolyData>::New();
        closedSurfacePolyDataCopy->DeepCopy(this->ClosedSurfacePolyData.Get());
        
        // Each thread stores the results in this array.
        vtkSmartPointer<vtkDoubleArray> bufferArray = vtkSmartPointer<vtkDoubleArray>::New();
        bufferArray->SetNumberOfComponents(3);
        bufferArrays.push_back(bufferArray);
        
        threads.push_back(std::thread(CrossSectionComputeWorker(),
                                      this->GeneratedPolyData,
                                      this->GeneratedTangents,
                                      closedSurfacePolyDataCopy,
                                      bufferArrays[i],
                                      startPointIndex, endPointIndex));
    }
    for (unsigned int i = 0; i < threads.size(); i++)
    {
        threads[i].join();
    }
    // Update the output table columns.
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
    return true;
}

/////////////////////////////////////////////////////////////////////////
CrossSectionComputeWorker::CrossSectionComputeWorker()
{
}

CrossSectionComputeWorker::~CrossSectionComputeWorker()
{
}

void CrossSectionComputeWorker::operator () (vtkPolyData * generatedPolyData,
                                                vtkDoubleArray * generatedTangents,
                                                vtkPolyData * closedSurfacePolyData,
                                                vtkDoubleArray * bufferArray,
                                                vtkIdType startPointIndex,
                                                vtkIdType endPointIndex)
{
    for (vtkIdType i = startPointIndex; i <= endPointIndex; i++)
    {
        // Get the contour polydata
        vtkNew<vtkPolyData> contourPolyData;
        ComputeCrossSectionPolydata(generatedPolyData, generatedTangents,
                                    closedSurfacePolyData, i, contourPolyData);
        {
            // Get the surface area and circular equivalent diameter
            vtkNew<vtkMassProperties> crossSectionProperties;
            crossSectionProperties->SetInputData(contourPolyData);
            const double crossSectionSurfaceArea = crossSectionProperties->GetSurfaceArea();
            const double ceDiameter = (sqrt(crossSectionSurfaceArea / vtkMath::Pi())) * 2;
            
            bufferArray->InsertNextTuple3((double) i, crossSectionSurfaceArea, ceDiameter);
        }
    }
}

// Translated and adapted from the Python implementation.
void CrossSectionComputeWorker::ComputeCrossSectionPolydata(
    vtkPolyData * generatedPolyData,
    vtkDoubleArray * generatedTangents,
    vtkPolyData * closedSurfacePolyData,
    vtkIdType pointIndex,
    vtkPolyData * contourPolyData)
{
    if (generatedPolyData == nullptr)
    {
        mtx.lock();
        std::cout << "Generated centerline polydata is NULL." << std::endl;
        mtx.unlock();
        return;
    }
    if (generatedTangents == nullptr)
    {
        mtx.lock();
        std::cout << "Generated centerline tangents is NULL." << std::endl;
        mtx.unlock();
        return;
    }
    if (closedSurfacePolyData == nullptr)
    {
        mtx.lock();
        std::cout << "Closed  surface polydata is NULL." << std::endl;
        mtx.unlock();
        return;
    }
    
    double center[3] = {0.0, 0.0, 0.0};
    generatedPolyData->GetPoint(pointIndex, center);
    
    double normal[3] = {0.0, 0.0, 0.0};
    for (unsigned int i = 0; i < 3; i++)
    {
        normal[i] = generatedTangents->GetTuple3(pointIndex)[i];
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
        mtx.lock();
        std::cout << "Could not cut segment. Is it visible in 3D view?" << std::endl;
        mtx.unlock();
        return;
    }
    if (planePoints->GetNumberOfPoints() < 3)
    {
        mtx.lock();
        std::cout << "Not enough points to create surface" << std::endl;
        mtx.unlock();
        return;
    }

    /*
     * There may be holes in the cross-section although there are none in the
     * segment itself, or branches around it. The latter will be eliminated
     * below. If a hole is the closest region to the reference point, it will be
     * the selected region with an inversed result.
     * TODO: handle this case.
    */
    vtkNew<vtkPolyDataConnectivityFilter> regionFilter;
    regionFilter->SetInputConnection(planeCut->GetOutputPort());
    regionFilter->SetExtractionModeToAllRegions();
    regionFilter->Update();
    const int numberOfRegions = regionFilter->GetNumberOfExtractedRegions();
    if (regionFilter->GetNumberOfExtractedRegions() != 1)
    {
        std:cout << "Point index: " << pointIndex << " - the number of extracted regions(" << numberOfRegions << ") in the cross-section is not exactly 1; the surface area *may* be unexpected." << endl;
    }

    // Keep the closed surface around the centerline
    vtkNew<vtkPolyDataConnectivityFilter> connectivityFilter;
    connectivityFilter->SetInputData(planeCut->GetOutput());
    connectivityFilter->SetClosestPoint(center);
    connectivityFilter->SetExtractionModeToClosestPointRegion();
    connectivityFilter->Update();

    // Triangulate the contour points
    vtkNew<vtkContourTriangulator> contourTriangulator;
    contourTriangulator->SetInputData(connectivityFilter->GetOutput());
    contourTriangulator->Update();

    contourPolyData->DeepCopy(contourTriangulator->GetOutput());
}

