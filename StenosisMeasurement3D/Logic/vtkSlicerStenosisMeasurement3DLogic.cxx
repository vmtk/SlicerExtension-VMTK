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

// StenosisMeasurement3D Logic includes
#include "vtkSlicerStenosisMeasurement3DLogic.h"

// MRML includes
#include <vtkMRMLScene.h>

// VTK includes
#include <vtkIntArray.h>
#include <vtkNew.h>
#include <vtkObjectFactory.h>
#include <vtkPlane.h>
#include <vtkClipPolyData.h>
#include <vtkClipClosedSurface.h>
#include <vtkPlaneCollection.h>
#include <vtkTriangleFilter.h>
#include <vtkMRMLTableNode.h>
#include <vtkTable.h>
#include <vtkMRMLI18N.h>
#include <vtkMassProperties.h>

static const char* COLUMN_LABEL_STUDY = "Study";
static const char* COLUMN_LABEL_WALL = "Wall";
static const char* COLUMN_LABEL_LUMEN = "Lumen";
static const char* COLUMN_LABEL_LESION = "Lesion";
static const char* COLUMN_LABEL_STENOSIS = "Stenosis";
static const char* COLUMN_LABEL_LENGTH = "Length";
static const char* COLUMN_LABEL_NOTES = "Notes";

//----------------------------------------------------------------------------
vtkStandardNewMacro(vtkSlicerStenosisMeasurement3DLogic);

//----------------------------------------------------------------------------
vtkSlicerStenosisMeasurement3DLogic::vtkSlicerStenosisMeasurement3DLogic()
{
}

//----------------------------------------------------------------------------
vtkSlicerStenosisMeasurement3DLogic::~vtkSlicerStenosisMeasurement3DLogic()
{
}

//----------------------------------------------------------------------------
void vtkSlicerStenosisMeasurement3DLogic::PrintSelf(ostream& os, vtkIndent indent)
{
  this->Superclass::PrintSelf(os, indent);
}

//---------------------------------------------------------------------------
void vtkSlicerStenosisMeasurement3DLogic::SetMRMLSceneInternal(vtkMRMLScene * newScene)
{
  vtkNew<vtkIntArray> events;
  events->InsertNextValue(vtkMRMLScene::NodeAddedEvent);
  events->InsertNextValue(vtkMRMLScene::NodeRemovedEvent);
  events->InsertNextValue(vtkMRMLScene::EndBatchProcessEvent);
  this->SetAndObserveMRMLSceneEventsInternal(newScene, events.GetPointer());
}

//-----------------------------------------------------------------------------
void vtkSlicerStenosisMeasurement3DLogic::RegisterNodes()
{
  assert(this->GetMRMLScene() != 0);
  if (this->GetMRMLScene())
  {
    this->GetMRMLScene()->RegisterNodeClass(vtkSmartPointer<vtkMRMLStenosisMeasurement3DParameterNode>::New());
  }
}

//---------------------------------------------------------------------------
void vtkSlicerStenosisMeasurement3DLogic::UpdateFromMRMLScene()
{
  assert(this->GetMRMLScene() != 0);
}

//---------------------------------------------------------------------------
void vtkSlicerStenosisMeasurement3DLogic::OnMRMLSceneNodeAdded(vtkMRMLNode* node)
{
}

//---------------------------------------------------------------------------
void vtkSlicerStenosisMeasurement3DLogic::OnMRMLSceneNodeRemoved(vtkMRMLNode* vtkNotUsed(node))
{
}

//---------------------------------------------------------------------------
bool vtkSlicerStenosisMeasurement3DLogic::Process(vtkVariantArray * results)
{
  if (!results)
  {
    vtkErrorMacro("Please provide a vtkVariantArray to hold the results.");
    return false;
  }
  vtkMRMLStenosisMeasurement3DParameterNode * parameterNode = this->ParameterNode;
  if (!parameterNode)
  {
    vtkErrorMacro("Parameter node is NULL.");
    return false;
  }
  vtkMRMLMarkupsShapeNode * wallShapeNode = parameterNode->GetInputShapeNode();
  vtkMRMLSegmentationNode * lumenSegmentationNode = parameterNode->GetInputSegmentationNode();
  std::string segmentID = parameterNode->GetInputSegmentID();
  vtkMRMLMarkupsFiducialNode * boundaryFiducialNode = parameterNode->GetInputFiducialNode();
  vtkPolyData * outputWallOpenPolyData = parameterNode->GetOutputWallOpenPolyData();
  vtkPolyData * outputLumenOpenPolyData = parameterNode->GetOutputLumenOpenPolyData();
  vtkPolyData * outputWallClosedPolyData = parameterNode->GetOutputWallClosedPolyData();
  vtkPolyData * outputLumenClosedPolyData = parameterNode->GetOutputLumenClosedPolyData();
  
  // Note: we don't call ::UpdateBoundaryControlPointPosition here.
  if (wallShapeNode == nullptr || boundaryFiducialNode == nullptr
    || lumenSegmentationNode == nullptr || segmentID.empty()
    || wallShapeNode->GetNumberOfControlPoints() < 4 || boundaryFiducialNode->GetNumberOfControlPoints() < 2
    || wallShapeNode->GetShapeName() != vtkMRMLMarkupsShapeNode::Tube
  )
  {
    vtkErrorMacro("Invalid input.");
    return false;
  }

  if (outputWallOpenPolyData == nullptr || outputLumenOpenPolyData == nullptr
    || outputWallClosedPolyData == nullptr || outputLumenClosedPolyData == nullptr)
  {
    vtkErrorMacro("Invalid output: 4 polydata objects must be provided for open/closed lumen/wall output.");
    return false;
  }

  // Put a ficucial point on the nearest point of the wall spline.
  this->UpdateBoundaryControlPointPosition(0, boundaryFiducialNode, wallShapeNode);
  this->UpdateBoundaryControlPointPosition(1, boundaryFiducialNode, wallShapeNode);

  // Get wall polydata from shape markups node.
  vtkPolyData * wallOpenSurface = wallShapeNode->GetShapeWorld();
  vtkPolyData * wallClosedSurface = wallShapeNode->GetCappedTubeWorld();
  // Generate lumen polydata from lumen segment.
  vtkNew<vtkPolyData> lumenSurface;
  if (!lumenSegmentationNode->GetClosedSurfaceRepresentation(segmentID, lumenSurface))
  {
    if (!lumenSegmentationNode->CreateClosedSurfaceRepresentation())
    {
      vtkErrorMacro("Cannot create closed surface from segmentation.");
      return false;
    }
    lumenSegmentationNode->GetClosedSurfaceRepresentation(segmentID, lumenSurface);
  }
  
  // The first 2 fiducial points are used to cut through the lumen and wall polydata at arbitrary positions.
  double p1[3] = { 0.0 };
  double p2[3] = { 0.0 };
  boundaryFiducialNode->GetNthControlPointPositionWorld(0, p1);
  boundaryFiducialNode->GetNthControlPointPositionWorld(1, p2);
  
  // Get spline polydata from shape markups node.
  vtkSmartPointer<vtkPolyData> spline = vtkSmartPointer<vtkPolyData>::New();
  wallShapeNode->GetTrimmedSplineWorld(spline);
  vtkPoints * splinePoints = spline->GetPoints();
  // Get boundaries where polydatas will be cut.
  const vtkIdType p1IdType = spline->FindPoint(p1);
  const vtkIdType p2IdType = spline->FindPoint(p2);
  
  // Get adjacent points to boundaries to calculate normals.
  /*
   * N.B: GetPoint() has a nasty documented version,
   * when result is assigned to a pointer.
   * A first result takes the value of next ones !
   */
  double p1Neighbour[3] = { 0.0 };
  splinePoints->GetPoint(p1IdType + 1, p1Neighbour);
  double p2Neighbour[3] = { 0.0 };
  splinePoints->GetPoint(p2IdType - 1, p2Neighbour);
  // If p1 is nearer to the end of the spline than p2.
  if (p1IdType > p2IdType)
  {
    splinePoints->GetPoint(p1IdType - 1, p1Neighbour);
    splinePoints->GetPoint(p2IdType + 1, p2Neighbour);
  }
  // Use as normals.
  double startDirection[3] = { 0.0 };
  double endDirection[3] = { 0.0 };
  // The normal 'looks' at the first parameter.
  vtkMath::Subtract(p1Neighbour, p1, startDirection);
  vtkMath::Subtract(p2Neighbour, p2, endDirection);
  
  // Open surface: Clip wall and lumen at p1. Clip the result at p2.
  vtkNew<vtkPolyData> wallIntermediate;
  if (!this->Clip(wallOpenSurface, wallIntermediate, p1, startDirection, false))
  {
    return false;
  }
  if (!this->Clip(wallIntermediate, outputWallOpenPolyData, p2, endDirection, false))
  {
    return false;
  }
  
  vtkNew<vtkPolyData> lumenIntermediate;
  if (!this->Clip(lumenSurface, lumenIntermediate, p1, startDirection, false))
  {
    return false;
  }
   
  if (!this->Clip(lumenIntermediate, outputLumenOpenPolyData, p2, endDirection, false))
  {
    return false;
  }
  
  // Closed surface
  if (!this->ClipClosed(wallClosedSurface, outputWallClosedPolyData, p1, startDirection, p2, endDirection))
  {
    return false;
  }
  if (!this->ClipClosed(lumenSurface, outputLumenClosedPolyData, p1, startDirection, p2, endDirection))
  {
    return false;
  }

  if (!this->ComputeResults(results))
  {
    vtkErrorMacro("Failed to compute the results.");
    return false;
  }   
  vtkMRMLTableNode * outputTableNode = this->ParameterNode->GetOutputTableNode();
  if (results && outputTableNode)
  {
    if (this->DefineOutputTable())
    {
      outputTableNode->GetTable()->InsertNextRow(results);
      outputTableNode->Modified();
    }
  }

  return true;
}

//---------------------------------------------------------------------------
bool vtkSlicerStenosisMeasurement3DLogic::Clip(vtkPolyData * input, vtkPolyData * output,
                                               double * origin, double * normal, bool clipped)
{
  if (input == nullptr || origin == nullptr || normal == nullptr || output == nullptr)
  {
    vtkErrorMacro("Can't clip, invalid parameters.");
    return false;
  }
  vtkNew<vtkPlane> plane;
  plane->SetOrigin(origin);
  plane->SetNormal(normal);
  
  vtkNew<vtkClipPolyData> clipper;
  clipper->SetClipFunction(plane);
  clipper->SetInputData(input);
  clipper->GenerateClippedOutputOn();
  clipper->Update();
  
  output->Initialize();
  if (clipped)
  {
    output->DeepCopy(clipper->GetClippedOutput());
  }
  else
  {
    output->DeepCopy(clipper->GetOutput());
  }
  return true;
}

//-----------------------------------------------------------------------------
bool vtkSlicerStenosisMeasurement3DLogic::UpdateBoundaryControlPointPosition
  (int pointIndex, vtkMRMLMarkupsFiducialNode * fiducialNode, vtkMRMLMarkupsShapeNode * shapeNode)
{
  // Put a ficucial point on the nearest point of the wall spline.
  if (pointIndex < 0 || fiducialNode == nullptr || shapeNode == nullptr
    || pointIndex > (fiducialNode->GetNumberOfControlPoints() - 1)
    || (shapeNode && shapeNode->GetShapeName() != vtkMRMLMarkupsShapeNode::Tube))
  {
    vtkErrorMacro("Can't update control point position, invalid parameters.");
    return false;
  }
  vtkSmartPointer<vtkPolyData> spline = vtkSmartPointer<vtkPolyData>::New();
  shapeNode->GetTrimmedSplineWorld(spline);
  double controlPointCoordinate[3] = { 0.0 };
  fiducialNode->GetNthControlPointPositionWorld(pointIndex, controlPointCoordinate);
  vtkIdType targetPointId = spline->FindPoint(controlPointCoordinate);
  double * targetPointCoordinate = spline->GetPoint(targetPointId);
  if (controlPointCoordinate[0] != targetPointCoordinate[0]
    || controlPointCoordinate[1] != targetPointCoordinate[1]
    || controlPointCoordinate[2] != targetPointCoordinate[2])
  {
    fiducialNode->SetNthControlPointPositionWorld(pointIndex, targetPointCoordinate);
  }
  return true;
}

//-----------------------------------------------------------------------------
bool vtkSlicerStenosisMeasurement3DLogic::ClipClosed(vtkPolyData * input, vtkPolyData * output,
            double * startOrigin, double * startNormal, double * endOrigin, double * endNormal)
{
  if (input == nullptr || startOrigin == nullptr || startNormal == nullptr
    || endOrigin == nullptr || endNormal == nullptr || output == nullptr
  )
  {
    vtkErrorMacro("Can't clip closed surface, invalid parameters.");
    return false;
  }
  vtkNew<vtkPlane> startPlane;
  startPlane->SetOrigin(startOrigin);
  startPlane->SetNormal(startNormal);
  vtkNew<vtkPlane> endPlane;
  endPlane->SetOrigin(endOrigin);
  endPlane->SetNormal(endNormal);
  vtkNew<vtkPlaneCollection> planes;
  planes->AddItem(startPlane);
  planes->AddItem(endPlane);
  planes->Modified();
  
  vtkNew<vtkClipClosedSurface> clipper;
  clipper->SetClippingPlanes(planes);
  clipper->SetInputData(input);
  clipper->Update();
  
  vtkNew<vtkTriangleFilter> triangleFilter;
  triangleFilter->SetInputData(clipper->GetOutput());
  triangleFilter->Update();
  output->Initialize();
  output->DeepCopy(triangleFilter->GetOutput());
  
  return true;
}

//-----------------------------------------------------------------------------
double vtkSlicerStenosisMeasurement3DLogic::CalculateClippedSplineLength(vtkMRMLMarkupsFiducialNode* fiducialNode, vtkMRMLMarkupsShapeNode* shapeNode)
{
  
  if (fiducialNode == nullptr || shapeNode == nullptr
    || (fiducialNode->GetNumberOfControlPoints() < 2) )
  {
    vtkErrorMacro("Can't compute the clipped spline length, invalid parameters.");
    return -1.0;
  }
  vtkSmartPointer<vtkPolyData> spline = vtkSmartPointer<vtkPolyData>::New();
  shapeNode->GetTrimmedSplineWorld(spline);
  double p1Fiducial[3] = { 0.0 };
  fiducialNode->GetNthControlPointPositionWorld(0, p1Fiducial);
  vtkIdType p1SplineId = spline->FindPoint(p1Fiducial);
  double p1Spline[3] = { 0.0 };
  spline->GetPoint(p1SplineId, p1Spline);
  
  double p2Fiducial[3] = { 0.0 };
  fiducialNode->GetNthControlPointPositionWorld(1, p2Fiducial);
  vtkIdType p2SplineId = spline->FindPoint(p2Fiducial);
  double p2Spline[3] = { 0.0 };
  spline->GetPoint(p2SplineId, p2Spline);
  
  if (p1SplineId == p2SplineId)
  {
    return 0.0;
  }
  
  vtkIdType startSplineId = vtkMath::Min(p1SplineId, p2SplineId);
  vtkIdType endSplineId = vtkMath::Max(p1SplineId, p2SplineId);
  
  double length = 0.0;
  for (vtkIdType splineId = startSplineId; splineId < endSplineId; splineId++)
  {
    double p1[3] = { 0.0 };
    double p2[3] = { 0.0 };
    spline->GetPoint(splineId, p1);
    spline->GetPoint(splineId + 1, p2);
    length += std::sqrt(vtkMath::Distance2BetweenPoints(p1, p2));
  }
  return length;
}

//-----------------------------------------------------------------------------
void vtkSlicerStenosisMeasurement3DLogic::ProcessMRMLNodesEvents(vtkObject* caller, unsigned long event, void* callData)
{
  if (!this->ParameterNode)
  {
    return;
  }
  vtkMRMLMarkupsFiducialNode * inputFiducialNode = vtkMRMLMarkupsFiducialNode::SafeDownCast(this->ParameterNode->GetInputFiducialNode());
  vtkMRMLMarkupsShapeNode * inputShapeNode = vtkMRMLMarkupsShapeNode::SafeDownCast(this->ParameterNode->GetInputShapeNode());
  if (inputFiducialNode && inputShapeNode)
  {
    vtkMRMLMarkupsDisplayNode * fiducialDisplayNode = inputFiducialNode->GetMarkupsDisplayNode();
    if (!fiducialDisplayNode)
    {
      return;
    }
    this->UpdateBoundaryControlPointPosition(0, inputFiducialNode, inputShapeNode);
    this->UpdateBoundaryControlPointPosition(1, inputFiducialNode, inputShapeNode);
  }
}

//-----------------------------------------------------------------------------
void vtkSlicerStenosisMeasurement3DLogic::SetParameterNode(vtkMRMLStenosisMeasurement3DParameterNode* parameterNode)
{
  if (this->ParameterNode)
  {
    vtkUnObserveMRMLNodeMacro(this->ParameterNode->GetInputFiducialNode());
    vtkUnObserveMRMLNodeMacro(this->ParameterNode->GetInputShapeNode());
  }
  this->ParameterNode = parameterNode;
  if (!this->ParameterNode)
  {
    return;
  }
  // Needed for python scripting.
  if (!this->ParameterNode->GetScene())
  {
    this->ParameterNode->SetScene(this->GetMRMLScene());
  }
  // Put p1 and p2 ficucial points on the tube spline at nearest point when the fiducial or tube nodes are updated.
  vtkNew<vtkIntArray> events;
  events->InsertNextValue(vtkMRMLMarkupsFiducialNode::PointEndInteractionEvent);
  vtkObserveMRMLNodeEventsMacro(this->ParameterNode->GetInputFiducialNode(), events.GetPointer());
  vtkObserveMRMLNodeEventsMacro(this->ParameterNode->GetInputShapeNode(), events.GetPointer());
  // Move p1 and p2 now.
  vtkMRMLMarkupsFiducialNode * inputFiducialNode = this->ParameterNode->GetInputFiducialNode();
  vtkMRMLMarkupsShapeNode * inputShapeNode = this->ParameterNode->GetInputShapeNode();
  if (inputFiducialNode && inputShapeNode && inputShapeNode->GetShapeName() == vtkMRMLMarkupsShapeNode::Tube)
  {
    this->UpdateBoundaryControlPointPosition(0, inputFiducialNode, inputShapeNode);
    this->UpdateBoundaryControlPointPosition(1, inputFiducialNode, inputShapeNode);
  }
}

//-----------------------------------------------------------------------------
bool vtkSlicerStenosisMeasurement3DLogic::DefineOutputTable()
{
  /*
   * Define an input table structure to store the results in append mode only.
   */
  if (!this->ParameterNode or (this->ParameterNode && !this->ParameterNode->GetOutputTableNode()))
  {
    return false;
  }
  
  vtkMRMLTableNode * outputTableNode = this->ParameterNode->GetOutputTableNode();
  
  if (outputTableNode->GetNumberOfColumns() == 0)
  {
    vtkNew<vtkStringArray> studyColumn;
    vtkNew<vtkDoubleArray> wallColumn;
    vtkNew<vtkDoubleArray> lumenColumn;
    vtkNew<vtkDoubleArray> lesionColumn;
    vtkNew<vtkDoubleArray> stenosisColumn;
    vtkNew<vtkDoubleArray> lengthColumn;
    vtkNew<vtkStringArray> notesColumn;

    studyColumn->SetName(COLUMN_LABEL_STUDY);
    wallColumn->SetName(COLUMN_LABEL_WALL);
    lumenColumn->SetName(COLUMN_LABEL_LUMEN);
    lesionColumn->SetName(COLUMN_LABEL_LESION);
    stenosisColumn->SetName(COLUMN_LABEL_STENOSIS);
    lengthColumn->SetName(COLUMN_LABEL_LENGTH);
    notesColumn->SetName(COLUMN_LABEL_NOTES);

    outputTableNode->AddColumn(studyColumn);
    outputTableNode->AddColumn(wallColumn);
    outputTableNode->AddColumn(lumenColumn);
    outputTableNode->AddColumn(lesionColumn);
    outputTableNode->AddColumn(stenosisColumn);
    outputTableNode->AddColumn(lengthColumn);
    outputTableNode->AddColumn(notesColumn);

    outputTableNode->SetColumnTitle(COLUMN_LABEL_STUDY, vtkMRMLTr("vtkSlicerStenosisMeasurement3DLogic", "Study"));
    outputTableNode->SetColumnTitle(COLUMN_LABEL_WALL, vtkMRMLTr("vtkSlicerStenosisMeasurement3DLogic", "Wall"));
    outputTableNode->SetColumnTitle(COLUMN_LABEL_LUMEN, vtkMRMLTr("vtkSlicerStenosisMeasurement3DLogic", "Lumen"));
    outputTableNode->SetColumnTitle(COLUMN_LABEL_LESION, vtkMRMLTr("vtkSlicerStenosisMeasurement3DLogic", "Lesion"));
    outputTableNode->SetColumnTitle(COLUMN_LABEL_STENOSIS, vtkMRMLTr("vtkSlicerStenosisMeasurement3DLogic", "Stenosis"));
    outputTableNode->SetColumnTitle(COLUMN_LABEL_LENGTH, vtkMRMLTr("vtkSlicerStenosisMeasurement3DLogic", "Length"));
    outputTableNode->SetColumnTitle(COLUMN_LABEL_NOTES, vtkMRMLTr("vtkSlicerStenosisMeasurement3DLogic", "Notes"));

    outputTableNode->SetUseColumnTitleAsColumnHeader(true);
    outputTableNode->Modified();
  }
  return true;
}

//-----------------------------------------------------------------------------
bool vtkSlicerStenosisMeasurement3DLogic::ComputeResults(vtkVariantArray * results)
{
  if (!this->ParameterNode || !results)
  {
    return false;
  }
  results->Initialize();
  vtkPolyData * wallClosedPolyData = this->ParameterNode->GetOutputWallClosedPolyData();
  if (!wallClosedPolyData)
  {
    vtkErrorMacro("Unexpected empty wall closed surface.");
    return false;
  }
  vtkPolyData * lumenClosedPolyData = this->ParameterNode->GetOutputLumenClosedPolyData();
  if (!lumenClosedPolyData)
  {
    vtkErrorMacro("Unexpected empty lumen closed surface.");
    return false;
  }
  vtkNew<vtkMassProperties> wallMassProperties;
  wallMassProperties->SetInputData(wallClosedPolyData);
  wallMassProperties->Update();
  vtkNew<vtkMassProperties> lumenMassProperties;
  lumenMassProperties->SetInputData(lumenClosedPolyData);
  lumenMassProperties->Update();
  // Get the volumes.
  const double wallVolume = wallMassProperties->GetVolume();
  const double lumenVolume = lumenMassProperties->GetVolume();
  const double lesionVolume = wallVolume - lumenVolume;
  // Calculate stenosis degree.
  double degree = -1.0;
  if (wallVolume)
  {
    degree = (lesionVolume / wallVolume);
  }
  // Get the spline length between boundary points.
  double length = -1.0;
  vtkMRMLMarkupsShapeNode * inputShapeNode = this->ParameterNode->GetInputShapeNode();
  vtkMRMLMarkupsFiducialNode * inputFiducialNode = this->ParameterNode->GetInputFiducialNode();
  if (inputShapeNode && inputFiducialNode)
  {
    length = this->CalculateClippedSplineLength(inputFiducialNode, inputShapeNode);
  }
  // Return the result in a variant array.
  results->InsertNextValue(this->ParameterNode->GetName());
  results->InsertNextValue(wallVolume);
  results->InsertNextValue(lumenVolume);
  results->InsertNextValue(lesionVolume);
  results->InsertNextValue(degree);
  results->InsertNextValue(length);
  results->InsertNextValue(""); // Notes.

  return true;
}
