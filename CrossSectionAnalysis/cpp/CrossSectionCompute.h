/*
 * This file was created by SET [Surgeon] [Hobbyist developer].
 */

#ifndef __CrossSectionCompute_h
#define __CrossSectionCompute_h

/*
 * Notes for me :
 * Only class names must be 'vtk' prefixed.
 */

// Created by cmake
#include "vtkSlicerCrossSectionAnalysisModuleLogicExport.h"
#include <thread>

#include <vtkDoubleArray.h>
#include <vtkMRMLNode.h>
#include <vtkPolyData.h>
#include <vtkSmartPointer.h>
#include <sys/time.h>

#define DEVTIME 1

/**
 * This class computes cross-section areas along a centerline
 * in joinable threads running in parallel.
*/
class CROSSSECTION_COMPUTE_EXPORT vtkCrossSectionCompute
{
public:

  vtkCrossSectionCompute();
  virtual ~vtkCrossSectionCompute();

  void SetNumberOfThreads(unsigned int number)
  {
    numberOfThreads = number;
  }
  void SetInputCenterlineNode(vtkMRMLNode * inputCenterline)
  {
    inputCenterlineNode = inputCenterline;
  }
  /**
   * inputSurface may be a segmentation or a model.
   * inputSegmentId is ignored if inputSurface is a model.
   * A member closed surface polydata is derived from the input.
  */
  bool SetInputSurfaceNode(vtkMRMLNode * inputSurface, const std::string& inputSegmentId);

  /**
   * Generates the cross-section polydata as closest contour
   * around the input centerline point.
   * May be called directly from Python.
   */
  vtkPolyData * ComputeCrossSectionPolydata(unsigned int pointIndex);
  
  /**
   * This is the main purpose of this class.
   * The cross-section area and circular equivalent diameter
   * columns of the output table are updated in parallel.
   */
  void UpdateTable(vtkDoubleArray * crossSectionAreaArray, vtkDoubleArray * ceDiameterArray);
  
private:
  unsigned int numberOfThreads;
  vtkMRMLNode * inputCenterlineNode;
  vtkMRMLNode * inputSurfaceNode;
  // Created by ::SetInputSurfaceNode.
  vtkSmartPointer<vtkPolyData> closedSurfacePolyData;
  std::string inputSegmentID;

  /*
   * This function runs in a thread.
   * It takes ownership of worker, a new instance of this class,
   * and deletes it on completion.
   * Each thread receives a range of centerline points.
   */
  static void DoCompute(vtkDoubleArray * bufferArray,
			unsigned int startPointIndex,
			unsigned int endPointIndex,
			vtkCrossSectionCompute * worker);
  
  /*
   * This function expects a copy of closedSurfacePolyData.
   * It is called for every worker instance, such that
   * each instance does not need to calculate that polydata again.
   */
  void SetClosedSurfacePolyData(vtkPolyData * inputClosedSurfacePolyData)
  {
    closedSurfacePolyData = inputClosedSurfacePolyData;
  }
  
  /*
   * To calculate execution duration.
   */
#if DEVTIME != 0
  double GetTimeOfDay()
  {
      struct timeval atime;
      gettimeofday(&atime, NULL);
      return ((atime.tv_sec * 1000000) + atime.tv_usec);
  }
#endif
};

#endif

