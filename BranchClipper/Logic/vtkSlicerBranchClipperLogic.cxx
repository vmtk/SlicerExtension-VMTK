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

// BranchClipper Logic includes
#include "vtkSlicerBranchClipperLogic.h"

// MRML includes
#include <vtkMRMLScene.h>

// VTK includes

#include <vtkNew.h>
#include <vtkObjectFactory.h>

// STD includes
#include <cassert>

#include <vtkvmtkPolyDataCenterlineGroupsClipper.h>
#include <vtkvmtkCenterlineBranchExtractor.h>
#include <vtkvmtkPolyDataBranchUtilities.h>

// This class is based on vmtkbranchclipper.py.
//----------------------------------------------------------------------------
vtkStandardNewMacro(vtkSlicerBranchClipperLogic);

//----------------------------------------------------------------------------
vtkSlicerBranchClipperLogic::vtkSlicerBranchClipperLogic()
{  
  this->Output = vtkSmartPointer<vtkPolyData>::New();
}

//----------------------------------------------------------------------------
vtkSlicerBranchClipperLogic::~vtkSlicerBranchClipperLogic()
{
}

//----------------------------------------------------------------------------
void vtkSlicerBranchClipperLogic::PrintSelf(ostream& os, vtkIndent indent)
{
  this->Superclass::PrintSelf(os, indent);
}

//---------------------------------------------------------------------------
void vtkSlicerBranchClipperLogic::SetMRMLSceneInternal(vtkMRMLScene * newScene)
{
  vtkNew<vtkIntArray> events;
  events->InsertNextValue(vtkMRMLScene::NodeAddedEvent);
  events->InsertNextValue(vtkMRMLScene::NodeRemovedEvent);
  events->InsertNextValue(vtkMRMLScene::EndBatchProcessEvent);
  this->SetAndObserveMRMLSceneEventsInternal(newScene, events.GetPointer());
}

//-----------------------------------------------------------------------------
void vtkSlicerBranchClipperLogic::RegisterNodes()
{
  assert(this->GetMRMLScene() != 0);
}

//---------------------------------------------------------------------------
void vtkSlicerBranchClipperLogic::UpdateFromMRMLScene()
{
  assert(this->GetMRMLScene() != 0);
}

//---------------------------------------------------------------------------
void vtkSlicerBranchClipperLogic
::OnMRMLSceneNodeAdded(vtkMRMLNode* vtkNotUsed(node))
{
}

//---------------------------------------------------------------------------
void vtkSlicerBranchClipperLogic
::OnMRMLSceneNodeRemoved(vtkMRMLNode* vtkNotUsed(node))
{
}

//---------------------------------------------------------------------------
void vtkSlicerBranchClipperLogic::Execute()
{
  vtkSmartPointer<vtkvmtkCenterlineBranchExtractor> extractor = vtkSmartPointer<vtkvmtkCenterlineBranchExtractor>::New();
  extractor->SetInputData(this->Centerlines);
  extractor->SetBlankingArrayName(this->BlankingArrayName.c_str());
  extractor->SetRadiusArrayName(this->CenterlineRadiusArrayName.c_str());
  extractor->SetGroupIdsArrayName(this->GroupIdsArrayName.c_str());
  extractor->SetCenterlineIdsArrayName(this->CenterlineIdsArrayName.c_str());
  extractor->SetTractIdsArrayName(this->TractIdsArrayName.c_str());
  extractor->Update();
  this->OutputCenterlines = extractor->GetOutput();
  
  vtkSmartPointer<vtkvmtkPolyDataCenterlineGroupsClipper> clipper = vtkSmartPointer<vtkvmtkPolyDataCenterlineGroupsClipper>::New();
  clipper->SetInputData(this->Surface);
  clipper->SetCenterlines(this->OutputCenterlines);
  clipper->SetCenterlineRadiusArrayName(this->CenterlineRadiusArrayName.c_str());
  clipper->SetCenterlineGroupIdsArrayName(this->CenterlineGroupIdsArrayName.c_str());
  clipper->SetGroupIdsArrayName(this->GroupIdsArrayName.c_str());
  clipper->SetCenterlineRadiusArrayName(this->CenterlineRadiusArrayName.c_str());
  clipper->SetBlankingArrayName(this->BlankingArrayName.c_str());
  clipper->SetCutoffRadiusFactor(this->CutoffRadiusFactor);
  clipper->SetClipValue(this->ClipValue);
  clipper->SetUseRadiusInformation(this->UseRadiusInformation);
  vtkSmartPointer<vtkIdList> centerlineGroupIds = vtkSmartPointer<vtkIdList>::New();
  if (this->CenterlineGroupIds)
  {
    for (vtkIdType i = 0; i < this->CenterlineGroupIds->GetNumberOfIds(); i++)
    {
      centerlineGroupIds->InsertNextId(this->CenterlineGroupIds->GetId(i));
    }
    clipper->SetCenterlineGroupIds(centerlineGroupIds);
    clipper->ClipAllCenterlineGroupIdsOff();
  }
  else
  {
    clipper->ClipAllCenterlineGroupIdsOn();
  }
  clipper->SetGenerateClippedOutput(this->InsideOut);
  clipper->Update();
  
  if (!this->InsideOut)
  {
    this->Output->DeepCopy(clipper->GetOutput());
  }
  else
  {
    this->Output->DeepCopy(clipper->GetClippedOutput());
  }
}

//---------------------------------------------------------------------------
vtkIdType vtkSlicerBranchClipperLogic::GetNumberOfBranches()
{
  vtkNew<vtkvmtkPolyDataBranchUtilities> groupCounter;
  vtkSmartPointer<vtkIdList> groupIds = vtkSmartPointer<vtkIdList>::New();
  groupCounter->GetGroupsIdList(this->Output, this->GroupIdsArrayName.c_str(), groupIds);
  return groupIds->GetNumberOfIds();
}

//---------------------------------------------------------------------------
/*
 * Don't provide the result of ExtractGroup as a return value.
 * Crash is guaranteed.
 * Let the caller provide a polydata.
 */
void vtkSlicerBranchClipperLogic::GetBranch(const vtkIdType index, vtkPolyData * surface)
{
  vtkNew<vtkvmtkPolyDataBranchUtilities> groupCounter;
  vtkSmartPointer<vtkIdList> groupIds = vtkSmartPointer<vtkIdList>::New();
  groupCounter->GetGroupsIdList(this->Output, this->GroupIdsArrayName.c_str(), groupIds);
  
  // ExtractGroup modifies its input.
  vtkNew<vtkPolyData> input;
  input->DeepCopy(this->Output);
  
  vtkSmartPointer<vtkvmtkPolyDataBranchUtilities> splitter = vtkSmartPointer<vtkvmtkPolyDataBranchUtilities>::New();
  splitter->ExtractGroup(input, this->GroupIdsArrayName.c_str(),
                         groupIds->GetId(index), true, surface);
}
