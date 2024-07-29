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
  /**
   * inputSurface may be a segmentation or a model.
   * inputSegmentId is ignored if inputSurface is a model.
   * A member closed surface polydata is derived from the input.
  */
  bool SetInputSurfaceNode(vtkMRMLNode * inputSurface, const std::string& inputSegmentId);
  
  /**
   * Also computes GeneratedPolyData and GeneratedTangents once only.
   */ 
  void SetInputCenterlinePolyData(vtkPolyData * inputCenterlinePolyData);
  
  /**
   * This is the main purpose of this class.
   * The cross-section area and circular equivalent diameter
   * columns of the output table are updated in parallel.
   */
  void UpdateTable(vtkDoubleArray * crossSectionAreaArray, vtkDoubleArray * ceDiameterArray);

protected:
  vtkCrossSectionCompute();
  virtual ~vtkCrossSectionCompute();
  
  void ExcludeHolesFromSurface(vtkPolyData * inPolyData, vtkPolyData * outPolyData);

private:
  unsigned int NumberOfThreads;
  vtkSmartPointer<vtkMRMLNode> InputSurfaceNode;
  // Created by ::SetInputSurfaceNode.
  vtkSmartPointer<vtkPolyData> ClosedSurfacePolyData;
  std::string InputSegmentID;
  
  /**
   * We don't need normals and binormals.
   * And we don't want to recompute the 4x4 matrix at each point.
   */ 
  vtkSmartPointer<vtkPolyData> GeneratedPolyData;
  vtkSmartPointer<vtkDoubleArray> GeneratedTangents;
  
};

#endif // __vtkCrossSectionCompute_h
