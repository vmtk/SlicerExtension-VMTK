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

#include <vtkPlane.h>
#include <vtkCutter.h>
#include <vtkPolyDataConnectivityFilter.h>
#include <vtkCleanPolyData.h>
#include <vtkContourTriangulator.h>
#include <vtkMassProperties.h>
#include <vtkMath.h> // Pi()
#include <vtkParallelTransportFrame.h>
#include <vtkPointData.h>
#include <vtkIdList.h>

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
    vtkIdType endPointIndex,
    vtkIdList* emptySectionIds = nullptr,
    vtkCrossSectionCompute::ExtractionMode extractionMode = vtkCrossSectionCompute::ExtractionMode::ClosestPoint);

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
    vtkPolyData* contourPolyData,
    vtkIdList* emptySectionIds = nullptr,
    vtkCrossSectionCompute::ExtractionMode extractionMode = vtkCrossSectionCompute::ExtractionMode::ClosestPoint);
};

//------------------------------------------------------------------------------
vtkCrossSectionCompute::vtkCrossSectionCompute()
{
  this->NumberOfThreads = 1;
  this->ClosedSurfacePolyData = vtkSmartPointer<vtkPolyData>::New();
}

//------------------------------------------------------------------------------
vtkCrossSectionCompute::~vtkCrossSectionCompute()
{
}

//------------------------------------------------------------------------------
void vtkCrossSectionCompute::PrintSelf(ostream& os, vtkIndent indent)
{
    vtkObject::PrintSelf(os,indent);

    os << indent << "numberOfThreads: " << this->NumberOfThreads << "\n";
    os << indent << "closedSurfacePolyData: " << this->ClosedSurfacePolyData << "\n";
}

//------------------------------------------------------------------------------
void vtkCrossSectionCompute::SetInputSurfacePolyData(vtkPolyData * inputSurface)
{
    if (!inputSurface)
    {
        vtkErrorMacro("Invalid input surface.");
        this->ClosedSurfacePolyData = nullptr;
        return;
    }

    this->ClosedSurfacePolyData->DeepCopy(inputSurface);
}

//------------------------------------------------------------------------------
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

//------------------------------------------------------------------------------
bool vtkCrossSectionCompute::UpdateTable(vtkDoubleArray * crossSectionAreaArray, vtkDoubleArray * ceDiameterArray,
                                         vtkIdList* emptySectionIds, ExtractionMode extractionMode)
{
    if (this->ClosedSurfacePolyData == nullptr)
    {     
        vtkErrorMacro("Input surface is NULL.");
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
        closedSurfacePolyDataCopy->DeepCopy(this->ClosedSurfacePolyData);
        
        // Each thread stores the results in this array.
        vtkSmartPointer<vtkDoubleArray> bufferArray = vtkSmartPointer<vtkDoubleArray>::New();
        bufferArray->SetNumberOfComponents(3);
        bufferArrays.push_back(bufferArray);
        
        threads.push_back(std::thread(CrossSectionComputeWorker(),
                                      this->GeneratedPolyData,
                                      this->GeneratedTangents,
                                      closedSurfacePolyDataCopy,
                                      bufferArrays[i],
                                      startPointIndex, endPointIndex,
                                      emptySectionIds, extractionMode));
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

//------------------------------------------------------------------------------
vtkCrossSectionCompute::SectionCreationResult vtkCrossSectionCompute::CreateCrossSection(
                                vtkPolyData * result, vtkPolyData * input,
                                vtkPlane * plane, ExtractionMode extractionMode,
                                bool fromMainThread)
{
    auto consoleMessage = [&] (const std::string& message) {
        if (!fromMainThread)
        {
            mtx.lock();
        }
        std::cout << message << endl;
        if (!fromMainThread)
        {
            mtx.unlock();
        }
    };

    if (!input)
    {
        consoleMessage("Input polydata is NULL.");
        return SectionCreationResult::Abort;
    }
    if (!plane)
    {
        consoleMessage("Input cut plane is NULL.");
        return SectionCreationResult::Abort;
    }

    double * origin = plane->GetOrigin();
    double * normal = plane->GetNormal();
    if (normal[0] == 0.0 && normal[1] == 0.0 && normal[2] == 0.0)
    {
        std::string message("Invalid normal [0, 0, 0] at [");
        message += std::to_string(origin[0]) + std::string(", ");
        message += std::to_string(origin[1]) + std::string(", ");
        message += std::to_string(origin[2]) + std::string("].");
        consoleMessage(message);
        return SectionCreationResult::Abort;
    }
    // Do not copy nor clean the input. Let a caller do what seems appropriate.
    // Cut through the closed surface and get the points of the contour.
    vtkNew<vtkCutter> planeCut;
    planeCut->SetInputData(input);
    planeCut->SetCutFunction(plane);
    planeCut->Update();
    vtkPoints * planePoints = planeCut->GetOutput()->GetPoints();
    if (planePoints == NULL)
    {
        consoleMessage("Could not cut segment. Is it visible in 3D view?");
        return SectionCreationResult::Abort;
    }
    if (planePoints->GetNumberOfPoints() < 3)
    {
        consoleMessage("Not enough points to create surface");
        return SectionCreationResult::Abort;
    }

    vtkNew<vtkPolyDataConnectivityFilter> regionFilter;
    regionFilter->ColorRegionsOn();
    regionFilter->SetInputConnection(planeCut->GetOutputPort());
    regionFilter->SetExtractionModeToAllRegions();
    regionFilter->Update();
    const int numberOfRegions = regionFilter->GetNumberOfExtractedRegions();

    // Triangulate the contour points
    vtkNew<vtkContourTriangulator> contourTriangulator;
    contourTriangulator->SetInputConnection(regionFilter->GetOutputPort());
    contourTriangulator->Update();
    
    // Keep the closed surface around the centerline
    vtkNew<vtkPolyDataConnectivityFilter> connectivityFilter;
    connectivityFilter->SetInputConnection(contourTriangulator->GetOutputPort());
    switch (extractionMode)
    {
        case vtkCrossSectionCompute::ExtractionMode::LargestRegion:
            connectivityFilter->SetExtractionModeToLargestRegion();
            break;
        case vtkCrossSectionCompute::ExtractionMode::AllRegions:
            connectivityFilter->SetExtractionModeToAllRegions();
            break;
        default:
            connectivityFilter->SetClosestPoint(plane->GetOrigin());
            connectivityFilter->SetExtractionModeToClosestPointRegion();
    }
    connectivityFilter->Update();

    result->DeepCopy(connectivityFilter->GetOutput());
    if (result->GetNumberOfPoints() == 0)
    {
        return SectionCreationResult::Empty;
    }
    return SectionCreationResult::Success;
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
                                                vtkIdType endPointIndex,
                                                vtkIdList* emptySectionIds,
                                                vtkCrossSectionCompute::ExtractionMode extractionMode)
{
    for (vtkIdType i = startPointIndex; i <= endPointIndex; i++)
    {
        // Get the contour polydata
        vtkNew<vtkPolyData> contourPolyData;
        ComputeCrossSectionPolydata(generatedPolyData, generatedTangents,
                                    closedSurfacePolyData, i, contourPolyData,
                                    emptySectionIds, extractionMode);
        {
            // Get the surface area and circular equivalent diameter
            vtkNew<vtkMassProperties> crossSectionProperties;
            crossSectionProperties->SetInputData(contourPolyData);
            crossSectionProperties->Update();
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
    vtkPolyData * contourPolyData,
    vtkIdList* emptySectionIds,
    vtkCrossSectionCompute::ExtractionMode extractionMode)
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

    if (normal[0] == 0.0 &&  normal[1] == 0.0 &&  normal[2] == 0.0)
    {
        mtx.lock();
        std::cout << "Invalid normal [0, 0, 0] at point index " << pointIndex << "." << std::endl;
        mtx.unlock();
        return;
    }

    // Place a plane perpendicular to the centerline
    vtkNew<vtkPlane> plane;
    plane->SetOrigin(center);
    plane->SetNormal(normal);

    vtkCrossSectionCompute::SectionCreationResult
    result = vtkCrossSectionCompute::CreateCrossSection(contourPolyData,
                                                closedSurfacePolyData, plane,
                                                extractionMode, false);
    if (emptySectionIds && result == vtkCrossSectionCompute::SectionCreationResult::Empty)
    {
        mtx.lock();
        emptySectionIds->InsertNextId(pointIndex);
        mtx.unlock();
    }
}

