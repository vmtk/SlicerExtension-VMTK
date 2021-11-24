/*
 * This file was created by SET [Surgeon] [Hobbyist developer].
 */

#ifndef __CrossSectionCompute_h
#define __CrossSectionCompute_h

// Created by cmake
#include "vtkSlicerCrossSectionAnalysisModuleLogicExport.h"
#include <thread>

#include <vtkDoubleArray.h>
#include <vtkMRMLNode.h>
#include <vtkPolyData.h>
#include <vtkSmartPointer.h>
#include <vtkObjectFactory.h>
#include <vtkMRMLModelNode.h>
#include <vtkMRMLMarkupsCurveNode.h>
#include <sys/time.h>

#define DEVTIME 1

/**
 * Abstract class to compute cross-section areas
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
   * This is the main purpose of this class.
   * The cross-section area and circular equivalent diameter
   * columns of the output table are updated in parallel.
   * Implement in derived classes.
   */
  virtual void UpdateTable(vtkDoubleArray * crossSectionAreaArray, vtkDoubleArray * ceDiameterArray) = 0;

protected:
  vtkCrossSectionCompute();
  virtual ~vtkCrossSectionCompute();

  unsigned int NumberOfThreads;
  vtkSmartPointer<vtkMRMLNode> InputSurfaceNode;
  // Created by ::SetInputSurfaceNode.
  vtkSmartPointer<vtkPolyData> ClosedSurfacePolyData;
  std::string InputSegmentID;
  
};

// -------------------------- vtkModelCrossSectionCompute ------------------
/**
 * This class works with centerline models.
 */
class VTK_SLICER_CROSSSECTION_COMPUTE_EXPORT vtkModelCrossSectionCompute
: public vtkCrossSectionCompute
{
public:
    
    static vtkModelCrossSectionCompute *New();
    vtkTypeMacro(vtkModelCrossSectionCompute, vtkCrossSectionCompute);
    void PrintSelf(ostream& os, vtkIndent indent) override;
    
    void SetInputCenterlineNode(vtkMRMLModelNode * centerline)
    {
        this->InputCenterlineNode = centerline;
    }
    
    virtual void UpdateTable(vtkDoubleArray * crossSectionAreaArray, vtkDoubleArray * ceDiameterArray) override;
protected:
    vtkModelCrossSectionCompute();
    virtual ~vtkModelCrossSectionCompute();
    
private:
    vtkSmartPointer<vtkMRMLModelNode> InputCenterlineNode;
};

/**
 * This class works with centerline models. Each thread has one instance of this class running.
 */
class vtkModelCrossSectionComputeWorker
{
public:
    
    vtkModelCrossSectionComputeWorker();
    virtual ~vtkModelCrossSectionComputeWorker();
    
    void operator () (vtkMRMLModelNode * inputCenterlineNode,
                    vtkPolyData * closedSurfacePolyData,
                    vtkDoubleArray * bufferArray,
                    vtkIdType startPointIndex,
                    vtkIdType endPointIndex);
    
private:
    /**
     * Generates the cross-section polydata as closest contour
     * around the input centerline point.
     * The result is returned in contourPolyData.
     */
    void ComputeCrossSectionPolydata(vtkMRMLModelNode * inputCenterlineNode,
                                    vtkPolyData * closedSurfacePolyData,
                                    vtkIdType pointIndex,
                                    vtkPolyData * contourPolyData);
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

// -------------------------- vtkCurveCrossSectionCompute ------------------

/**
 * This class works with centerline curves.
 */
class VTK_SLICER_CROSSSECTION_COMPUTE_EXPORT vtkCurveCrossSectionCompute
: public vtkCrossSectionCompute
{
public:
    
    static vtkCurveCrossSectionCompute *New();
    vtkTypeMacro(vtkCurveCrossSectionCompute, vtkCrossSectionCompute);
    void PrintSelf(ostream& os, vtkIndent indent) override;
    
    void SetInputCenterlineNode(vtkMRMLMarkupsCurveNode * centerline)
    {
        this->InputCenterlineNode = centerline;
    }
    
    virtual void UpdateTable(vtkDoubleArray * crossSectionAreaArray, vtkDoubleArray * ceDiameterArray) override;
protected:
    vtkCurveCrossSectionCompute();
    virtual ~vtkCurveCrossSectionCompute();
    
private:
    vtkSmartPointer<vtkMRMLMarkupsCurveNode> InputCenterlineNode;
};

/**
 * This class works with centerline curves. Each thread has one instance of this class running.
 */
class vtkCurveCrossSectionComputeWorker
{
public:
    
    vtkCurveCrossSectionComputeWorker();
    virtual ~vtkCurveCrossSectionComputeWorker();
    
    void operator () (vtkMRMLMarkupsCurveNode * inputCenterlineNode,
                      vtkPolyData * closedSurfacePolyData,
                      vtkDoubleArray * bufferArray,
                      vtkIdType startPointIndex,
                      vtkIdType endPointIndex);
    
private:
    /**
     * Generates the cross-section polydata as closest contour
     * around the input centerline point.
     * The result is returned in contourPolyData.
     */
    void ComputeCrossSectionPolydata(vtkMRMLMarkupsCurveNode * inputCenterlineNode,
                                    vtkPolyData * closedSurfacePolyData,
                                    vtkIdType pointIndex,
                                    vtkPolyData * contourPolyData);
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

