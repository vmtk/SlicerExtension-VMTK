/*
 * This file was created by SET [Surgeon] [Hobbyist developer].
 * Valuable input comes from Andras Lasso (Perklab) in many areas.
 */

#ifndef __vtkCrossSectionCompute_h
#define __vtkCrossSectionCompute_h

// Created by cmake
#include "vtkSlicerCrossSectionAnalysisModuleLogicExport.h"
#include <thread>

#include <vtkDoubleArray.h>
#include <vtkMRMLNode.h>
#include <vtkPolyData.h>
#include <vtkSmartPointer.h>
#include <vtkObjectFactory.h>
#include <vtkPlane.h>

/**
 * This class computes cross-section areas
 * of a surface along a centerline.
*/
class VTK_SLICER_CROSSSECTION_COMPUTE_EXPORT vtkCrossSectionCompute
: public vtkObject
{
public:

  static vtkCrossSectionCompute *New();
  vtkTypeMacro(vtkCrossSectionCompute, vtkObject);
  void PrintSelf(ostream& os, vtkIndent indent) override;

  void SetNumberOfThreads(unsigned int number)
  {
    this->NumberOfThreads = number;
  }
  
  void SetInputSurfacePolyData(vtkPolyData * inputSurface);
  
  /**
   * Also computes GeneratedPolyData and GeneratedTangents once only.
   */ 
  void SetInputCenterlinePolyData(vtkPolyData * inputCenterlinePolyData);
  
  /**
   * This is the main purpose of this class.
   * The cross-section area and circular equivalent diameter
   * columns of the output table are updated in parallel.
   */
  bool UpdateTable(vtkDoubleArray * crossSectionAreaArray, vtkDoubleArray * ceDiameterArray,
                   vtkIdList* emptySectionIds  = nullptr);

  /**
   * Create a cross-section polydata of the input polydata with a given plane.
   * In ClosestPoint mode, holes nearby to the reference point are rightly
   * excluded.
   */
  enum ExtractionMode{LargestRegion = 0, AllRegions, ClosestPoint};
  enum SectionCreationResult {Success = 0, Abort, Empty};
  static SectionCreationResult CreateCrossSection(vtkPolyData * result, vtkPolyData * input,
                                          vtkPlane * plane,
                                          ExtractionMode extractionMode = ExtractionMode::ClosestPoint,
                                          bool fromMainThread = true);

protected:
  vtkCrossSectionCompute();
  virtual ~vtkCrossSectionCompute();

private:
  unsigned int NumberOfThreads;
  vtkSmartPointer<vtkPolyData> ClosedSurfacePolyData;
  
  /**
   * We don't need normals and binormals.
   * And we don't want to recompute the 4x4 matrix at each point.
   */ 
  vtkSmartPointer<vtkPolyData> GeneratedPolyData;
  vtkSmartPointer<vtkDoubleArray> GeneratedTangents;
  
};

#endif // __vtkCrossSectionCompute_h
