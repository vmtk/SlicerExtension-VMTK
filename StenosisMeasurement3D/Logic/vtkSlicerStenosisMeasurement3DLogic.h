/*==============================================================================

  Program: 3D Slicer

  Portions (c) Copyright Brigham and Women's Hospital (BWH) All Rights Reserved.

  See COPYRIGHT.txt
  or http://www.slicer.org/copyright/copyright.txt for details.

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.

==============================================================================*/

// .NAME vtkSlicerStenosisMeasurement3DLogic - slicer logic class for volumes manipulation
// .SECTION Description
// This class manages the logic associated with reading, saving,
// and changing propertied of the volumes


#ifndef __vtkSlicerStenosisMeasurement3DLogic_h
#define __vtkSlicerStenosisMeasurement3DLogic_h

// Slicer includes
#include "vtkSlicerModuleLogic.h"

// MRML includes

// STD includes
#include <cstdlib>

#include "vtkSlicerStenosisMeasurement3DModuleLogicExport.h"
#include <vtkMRMLMarkupsShapeNode.h>
#include <vtkMRMLMarkupsFiducialNode.h>
#include <vtkMRMLSegmentationNode.h>
#include <vtkVariantArray.h>
#include <vtkMRMLTableNode.h>

/// \ingroup Slicer_QtModules_ExtensionTemplate
class VTK_SLICER_STENOSISMEASUREMENT3D_MODULE_LOGIC_EXPORT vtkSlicerStenosisMeasurement3DLogic :
  public vtkSlicerModuleLogic
{
public:

  static vtkSlicerStenosisMeasurement3DLogic *New();
  vtkTypeMacro(vtkSlicerStenosisMeasurement3DLogic, vtkSlicerModuleLogic);
  void PrintSelf(ostream& os, vtkIndent indent) override;

  bool UpdateBoundaryControlPointPosition(int pointIndex, vtkMRMLMarkupsFiducialNode * fiducialNode,
                                          vtkMRMLMarkupsShapeNode * shapeNode);
  // The caller must pass in an enclosed surface.
  bool Process(vtkMRMLMarkupsShapeNode * wallShapeNode, vtkPolyData * enclosedSurface,
               vtkMRMLMarkupsFiducialNode * boundaryFiducialNode,
               vtkPolyData * outputWallOpenPolyData, vtkPolyData * outputLumenOpenPolyData,
               vtkPolyData * outputWallClosedPolyData, vtkPolyData * outputLumenClosedPolyData,
               vtkVariantArray * results, const std::string& studyName,
               vtkMRMLTableNode * outputTableNode = nullptr);
  // The caller must pass in an enclosed surface.
  bool CreateLesion(vtkMRMLMarkupsShapeNode * wallShapeNode, vtkPolyData * enclosedSurface,
                    vtkMRMLMarkupsFiducialNode * boundaryFiducialNode,
                    vtkPolyData * lesion);

  enum EnclosingType{Distinct = 0, Intersection, FirstIsEnclosed, SecondIsEnclosed, EnclosingType_Last};
  // Both input surfaces *must* be closed. This may be time consuming.
  EnclosingType GetClosedSurfaceEnclosingType(vtkPolyData * first, vtkPolyData * second, vtkPolyData * enclosed = nullptr);

  bool UpdateClosedSurfaceMesh(vtkPolyData * inMesh, vtkPolyData * outMesh);
  // Cut the input using a plane; either part may be in output. Create open polydata for display.
  bool ClipClosedSurface(vtkPolyData * input, vtkPolyData * output,
            double * origin, double * normal, bool clipped = false);
  // Create closed clipped polydata, suitable for vtkMassProperties.
  bool ClipClosedSurfaceWithClosedOutput(vtkPolyData * input, vtkPolyData * output,
                  double * startOrigin, double * startNormal, double * endOrigin, double * endNormal);

  bool DumpAggregateVolumes(vtkMRMLMarkupsShapeNode * wallShapeNode, vtkPolyData * enclosedSurface,
                           std::string filepath);

protected:
  vtkSlicerStenosisMeasurement3DLogic();
  ~vtkSlicerStenosisMeasurement3DLogic() override;

  void SetMRMLSceneInternal(vtkMRMLScene* newScene) override;
  /// Register MRML Node classes to Scene. Gets called automatically when the MRMLScene is attached to this logic class.
  void RegisterNodes() override;
  void UpdateFromMRMLScene() override;
  void OnMRMLSceneNodeAdded(vtkMRMLNode* node) override;
  void OnMRMLSceneNodeRemoved(vtkMRMLNode* node) override;

  bool CalculateClippedSplineLength(vtkMRMLMarkupsFiducialNode * fiducialNode,
                                    vtkMRMLMarkupsShapeNode * shapeNode,
                                    vtkDoubleArray * result);
  bool DefineOutputTable(vtkMRMLTableNode * outputTableNode);
  bool ComputeResults(vtkMRMLMarkupsShapeNode * inputShapeNode,
                      vtkMRMLMarkupsFiducialNode * inputFiducialNode,
                      vtkPolyData * wallClosedPolyData,
                      vtkPolyData * lumenClosedPolyData,
                      vtkVariantArray * results, const std::string& studyName);
private:

  vtkSlicerStenosisMeasurement3DLogic(const vtkSlicerStenosisMeasurement3DLogic&); // Not implemented
  void operator=(const vtkSlicerStenosisMeasurement3DLogic&); // Not implemented
};

#endif
