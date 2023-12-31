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

// .NAME vtkSlicerBranchClipperLogic - slicer logic class for volumes manipulation
// .SECTION Description
// This class manages the logic associated with reading, saving,
// and changing propertied of the volumes


#ifndef __vtkSlicerBranchClipperLogic_h
#define __vtkSlicerBranchClipperLogic_h

// Slicer includes
#include "vtkSlicerModuleLogic.h"

// MRML includes

// STD includes
#include <cstdlib>

#include "vtkSlicerBranchClipperModuleLogicExport.h"

#include <vtkPolyData.h>
#include <vtkSetGet.h>
#include <vtkPolyDataCollection.h>

/// \ingroup Slicer_QtModules_ExtensionTemplate
class VTK_SLICER_BRANCHCLIPPER_MODULE_LOGIC_EXPORT vtkSlicerBranchClipperLogic :
  public vtkSlicerModuleLogic
{
public:

  static vtkSlicerBranchClipperLogic *New();
  vtkTypeMacro(vtkSlicerBranchClipperLogic, vtkSlicerModuleLogic);
  void PrintSelf(ostream& os, vtkIndent indent) override;
  
  vtkGetObjectMacro( Surface, vtkPolyData);
  vtkSetObjectMacro( Surface, vtkPolyData);
  vtkGetObjectMacro(Centerlines, vtkPolyData);
  vtkSetObjectMacro(Centerlines, vtkPolyData);
  vtkSetMacro(CenterlineGroupIdsArrayName, std::string);
  vtkGetMacro(CenterlineGroupIdsArrayName, std::string);
  vtkSetMacro(GroupIdsArrayName, std::string);
  vtkGetMacro(GroupIdsArrayName, std::string);
  vtkSetMacro(CenterlineRadiusArrayName, std::string);
  vtkGetMacro(CenterlineRadiusArrayName, std::string);
  vtkSetMacro(BlankingArrayName, std::string);
  vtkGetMacro(BlankingArrayName, std::string);
  vtkGetMacro(CenterlineIdsArrayName, std::string);
  vtkSetMacro(CenterlineIdsArrayName, std::string);
  vtkGetMacro(TractIdsArrayName, std::string);
  vtkSetMacro(TractIdsArrayName, std::string);
  vtkSetMacro(CutoffRadiusFactor,double);
  vtkGetMacro(CutoffRadiusFactor,double);
  vtkSetMacro(ClipValue,double);
  vtkGetMacro(ClipValue,double);
  vtkSetMacro(UseRadiusInformation,int);
  vtkGetMacro(UseRadiusInformation,int);
  vtkBooleanMacro(UseRadiusInformation,int);
  vtkSetObjectMacro(CenterlineGroupIds,vtkIdList);
  vtkGetObjectMacro(CenterlineGroupIds,vtkIdList);
  vtkSetMacro(GenerateClippedOutput,int);
  vtkGetMacro(GenerateClippedOutput,int);
  vtkBooleanMacro(GenerateClippedOutput,int);
  vtkSetMacro(ClipAllCenterlineGroupIds,int);
  vtkGetMacro(ClipAllCenterlineGroupIds,int);
  vtkBooleanMacro(ClipAllCenterlineGroupIds,int);
  vtkSetMacro(InsideOut,int);
  vtkGetMacro(InsideOut,int);
  vtkBooleanMacro(InsideOut,int);
  vtkGetObjectMacro(Output, vtkPolyData);
  vtkGetObjectMacro(OutputCenterlines, vtkPolyData);
  
  vtkIdType GetNumberOfBranches();
  void GetBranch(const vtkIdType index, vtkPolyData * surface);

  void Execute();
  
  // For bifurcation profiles.
  vtkSetMacro(BifurcationProfileGroupIdsArrayName, std::string);
  vtkGetMacro(BifurcationProfileGroupIdsArrayName, std::string);
  vtkSetMacro(BifurcationProfileBifurcationGroupIdsArrayName, std::string);
  vtkGetMacro(BifurcationProfileBifurcationGroupIdsArrayName, std::string);
  vtkSetMacro(BifurcationProfileOrientationArrayName, std::string);
  vtkGetMacro(BifurcationProfileOrientationArrayName, std::string);
  
  vtkPolyDataCollection * GetOutputBifurcationProfilesCollection()
  {
    return BifurcationProfilesCollection;
  }

protected:
  vtkSlicerBranchClipperLogic();
  ~vtkSlicerBranchClipperLogic() override;

  void SetMRMLSceneInternal(vtkMRMLScene* newScene) override;
  /// Register MRML Node classes to Scene. Gets called automatically when the MRMLScene is attached to this logic class.
  void RegisterNodes() override;
  void UpdateFromMRMLScene() override;
  void OnMRMLSceneNodeAdded(vtkMRMLNode* node) override;
  void OnMRMLSceneNodeRemoved(vtkMRMLNode* node) override;
  
  vtkPolyData * Surface = nullptr;
  vtkPolyData * Centerlines = nullptr;
  std::string CenterlineGroupIdsArrayName = "GroupIds";
  std::string GroupIdsArrayName = "GroupIds";
  std::string CenterlineRadiusArrayName = "Radius";
  std::string BlankingArrayName = "Blanking";
  std::string CenterlineIdsArrayName = "CenterlineIds";
  std::string TractIdsArrayName = "TractIds";
  double CutoffRadiusFactor = 0x1E16;
  double ClipValue = 0.0;
  int UseRadiusInformation = 1;
  vtkIdList * CenterlineGroupIds = nullptr;
  int GenerateClippedOutput = 0;
  int ClipAllCenterlineGroupIds = 0;
  int InsideOut = 0;
  
  vtkSmartPointer<vtkPolyData> Output = nullptr;
  vtkSmartPointer<vtkPolyData> OutputCenterlines = nullptr;
  
  // For bifurcation profiles.
  bool CreatePolyDataFromCell(vtkIdType cellId, vtkPolyData * profiledOutput, vtkPolyData * cellPolyData);
  
  std::string BifurcationProfileGroupIdsArrayName = "BifurcationProfileGroupIds";
  std::string BifurcationProfileBifurcationGroupIdsArrayName = "BifurcationProfileBifurcationGroupIds";
  std::string BifurcationProfileOrientationArrayName = "BifurcationProfileOrientation";
  
  vtkPolyDataCollection * BifurcationProfilesCollection = nullptr;
  
private:

  vtkSlicerBranchClipperLogic(const vtkSlicerBranchClipperLogic&); // Not implemented
  void operator=(const vtkSlicerBranchClipperLogic&); // Not implemented
};

#endif
