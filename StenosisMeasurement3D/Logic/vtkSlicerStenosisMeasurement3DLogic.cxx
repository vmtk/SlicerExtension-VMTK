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
#include "vtkMRMLStenosisMeasurement3DParameterNode.h"
#include <vtkMRMLStenosisMeasurement3DLesionModelDisplayNode.h>

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
#include <vtkTable.h>
#include <vtkMRMLI18N.h>
#include <vtkMassProperties.h>
#include <vtkPolyDataConnectivityFilter.h>
#include <vtkExtractEnclosedPoints.h>
#include <vtkBooleanOperationPolyDataFilter.h>
#include <vtkCleanPolyData.h>
#include <vtkMRMLSegmentationNode.h>
#include <vtkSegmentationConverter.h>
#include <vtkContourTriangulator.h>
#include <vtkAppendPolyData.h>
#include <vtkFeatureEdges.h>
#include <vtkPointData.h>
#include <vtkPolyDataNormals.h>
#include <vtkDataArray.h>
#include <vtkSQLiteDatabase.h>
#include <vtkTableToSQLiteWriter.h>
#include <vtkSQLiteQuery.h>

static const char* COLUMN_NAME_STUDY = "Study";
static const char* COLUMN_NAME_WALL = "WallVolume";
static const char* COLUMN_NAME_LUMEN = "LumenVolume";
static const char* COLUMN_NAME_LESION = "LesionVolume";
static const char* COLUMN_NAME_STENOSIS = "Stenosis";
static const char* COLUMN_NAME_START_SPLINE_ID = "StartSplineId";
static const char* COLUMN_NAME_END_SPLINE_ID = "EndSplineId";
static const char* COLUMN_NAME_LENGTH = "Length";
static const char* COLUMN_NAME_LESION_VOLUME_PER_CM = "LesionVolumePerCm";
static const char* COLUMN_NAME_STENOSIS_PER_CM = "StenosisPerCm";
static const char* COLUMN_NAME_NOTES = "Notes";

//------------------------------------------------------------------------------
#include <mutex>

std::mutex mtx;
//------------------------------------------------------------------------------
/**
 * Each thread has one instance of this class running.
 * It computes volumes and distances from startBlockId to endBlockId.
 */
class VolumeComputeWorker
{
public:

  VolumeComputeWorker();
  virtual ~VolumeComputeWorker();

  void operator () (vtkSlicerStenosisMeasurement3DLogic * logic,
                    int ID, vtkPolyData * wallSurface, // Closed
                    vtkPolyData * lumenSurface, // Clipped in tube and closed
                    vtkPolyData * spline, vtkDoubleArray* bufferArray,
                    vtkIdType startBlockId, vtkIdType endBlockId);

  int GetId() { return Id;}
  double CalculateSplineDistance(vtkPolyData * spline, vtkIdType startId, vtkIdType endId);

private:
  int Id = 0;
};

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
    this->GetMRMLScene()->RegisterNodeClass(vtkSmartPointer<vtkMRMLStenosisMeasurement3DLesionModelDisplayNode>::New());
  }
}

//---------------------------------------------------------------------------
void vtkSlicerStenosisMeasurement3DLogic::UpdateFromMRMLScene()
{
  assert(this->GetMRMLScene() != 0);
}

//---------------------------------------------------------------------------
void vtkSlicerStenosisMeasurement3DLogic
::OnMRMLSceneNodeAdded(vtkMRMLNode* vtkNotUsed(node))
{
}

//---------------------------------------------------------------------------
void vtkSlicerStenosisMeasurement3DLogic
::OnMRMLSceneNodeRemoved(vtkMRMLNode* vtkNotUsed(node))
{
}

//---------------------------------------------------------------------------
bool vtkSlicerStenosisMeasurement3DLogic::Process(vtkMRMLMarkupsShapeNode * wallShapeNode, vtkPolyData * enclosedSurface,
                                                  vtkMRMLMarkupsFiducialNode * boundaryFiducialNode,
                                                  vtkPolyData * outputWallOpenPolyData, vtkPolyData * outputLumenOpenPolyData,
                                                  vtkPolyData * outputWallClosedPolyData, vtkPolyData * outputLumenClosedPolyData,
                                                  vtkVariantArray * results, const std::string& studyName,
                                                  vtkMRMLTableNode * outputTableNode)
{
  if (!results)
  {
    vtkErrorMacro("Please provide a vtkVariantArray to hold the results.");
    return false;
  }
  // Note: we don't call ::UpdateBoundaryControlPointPosition here.
  if (wallShapeNode == nullptr || boundaryFiducialNode == nullptr || enclosedSurface == nullptr
    || wallShapeNode->GetNumberOfControlPoints() < 4 || boundaryFiducialNode->GetNumberOfControlPoints() < 2
    || wallShapeNode->GetShapeName() != vtkMRMLMarkupsShapeNode::Tube
  )
  {
    vtkErrorMacro("Invalid input, cannot process.");
    return false;
  }

  // Get the spline polydata from the shape markups node.
  vtkSmartPointer<vtkPolyData> spline = vtkSmartPointer<vtkPolyData>::New();
  if (!wallShapeNode->GetTrimmedSplineWorld(spline))
  {
    vtkErrorMacro("The tube does not have a valid spline."); // < 4 points for example.
    return false;
  }

  // Get wall polydata from shape markups node.
  vtkPolyData * wallOpenSurface = wallShapeNode->GetShapeWorld();
  vtkPolyData * wallClosedSurface = wallShapeNode->GetCappedTubeWorld();

  // The first 2 fiducial points are used to cut through the lumen and wall polydata at arbitrary positions.
  double p1[3] = { 0.0 };
  double p2[3] = { 0.0 };
  boundaryFiducialNode->GetNthControlPointPositionWorld(0, p1);
  boundaryFiducialNode->GetNthControlPointPositionWorld(1, p2);

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
  if (!this->ClipClosedSurface(wallOpenSurface, wallIntermediate, p1, startDirection, false))
  {
    return false;
  }
  if (!this->ClipClosedSurface(wallIntermediate, outputWallOpenPolyData, p2, endDirection, false))
  {
    return false;
  }

  vtkNew<vtkPolyData> lumenIntermediate;
  if (!this->ClipClosedSurface(enclosedSurface, lumenIntermediate, p1, startDirection, false))
  {
    return false;
  }

  if (!this->ClipClosedSurface(lumenIntermediate, outputLumenOpenPolyData, p2, endDirection, false))
  {
    return false;
  }

  // Closed surface
  if (!this->ClipClosedSurfaceWithClosedOutput(wallClosedSurface, outputWallClosedPolyData, p1, startDirection, p2, endDirection))
  {
    return false;
  }
  if (!this->ClipClosedSurfaceWithClosedOutput(enclosedSurface, outputLumenClosedPolyData, p1, startDirection, p2, endDirection))
  {
    return false;
  }

  if (!this->ComputeResults(wallShapeNode, boundaryFiducialNode,
        outputWallClosedPolyData, outputLumenClosedPolyData,
        results, studyName))
  {
    vtkErrorMacro("Failed to compute the results.");
    return false;
  }   
  if (results && outputTableNode)
  {
    if (this->DefineOutputTable(outputTableNode))
    {
      outputTableNode->GetTable()->InsertNextRow(results);
      outputTableNode->Modified();
    }
  }

  return true;
}

//---------------------------------------------------------------------------
bool vtkSlicerStenosisMeasurement3DLogic::ClipClosedSurface(vtkPolyData * input, vtkPolyData * output,
                                               double * origin, double * normal, bool clipped)
{
  if (input == nullptr || origin == NULL || normal == NULL)
  {
    vtkErrorMacro("Can't clip, invalid parameters.");
    return false;
  }
  if (normal[0] == 0 && normal[1] == 0 && normal[2] == 0)
  {
    vtkErrorMacro("Invalid normal, all values are zero.");
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
    || pointIndex > (fiducialNode->GetNumberOfControlPoints() - 1) )
  {
    vtkErrorMacro("Can't update control point position, invalid parameters.");
    return false;
  }
  // Get the spline polydata from the shape markups node.
  vtkSmartPointer<vtkPolyData> spline = vtkSmartPointer<vtkPolyData>::New();
  if (!shapeNode->GetTrimmedSplineWorld(spline))
  {
    vtkErrorMacro("The tube does not have a valid spline.");
    return false;
  }
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
bool vtkSlicerStenosisMeasurement3DLogic::ClipClosedSurfaceWithClosedOutput(vtkPolyData * input, vtkPolyData * output,
            double * startOrigin, double * startNormal, double * endOrigin, double * endNormal)
{
  if (input == nullptr || startOrigin == NULL || startNormal == NULL
    || endOrigin == NULL || endNormal == NULL
  )
  {
    vtkErrorMacro("Can't clip, invalid parameters.");
    return false;
  }
  if (startNormal[0] == 0 && startNormal[1] == 0 && startNormal[2] == 0)
  {
    vtkErrorMacro("Invalid start normal, all values are zero.");
    return false;
  }
  if (endNormal[0] == 0 && endNormal[1] == 0 && endNormal[2] == 0)
  {
    vtkErrorMacro("Invalid end normal, all values are zero.");
    return false;
  }
  if ((startOrigin[0] == endOrigin[0])
    && (startOrigin[1] == endOrigin[1])
    && (startOrigin[2] == endOrigin[2]))
  {
    vtkErrorMacro("Start and end points are identical.");
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
  output->DeepCopy(triangleFilter->GetOutput());

  return true;
}

//-----------------------------------------------------------------------------
bool vtkSlicerStenosisMeasurement3DLogic::CalculateClippedSplineLength(vtkMRMLMarkupsFiducialNode* fiducialNode,
                                                                         vtkMRMLMarkupsShapeNode* shapeNode,
                                                                         vtkDoubleArray * result)
{

  if (fiducialNode == nullptr || shapeNode == nullptr
    || (fiducialNode->GetNumberOfControlPoints() < 2) || !result)
  {
    vtkErrorMacro("Can't compute the clipped spline length, invalid parameters.");
    return false;
  }
  // Get the spline polydata from the shape markups node.
  vtkSmartPointer<vtkPolyData> spline = vtkSmartPointer<vtkPolyData>::New();
  if (!shapeNode->GetTrimmedSplineWorld(spline))
  {
    vtkErrorMacro("The tube does not have a valid spline.");
    return false;
  }
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
    vtkErrorMacro("Identical spline ids.");
    return false;
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
  result->InsertNextValue(startSplineId);
  result->InsertNextValue(endSplineId);
  result->InsertNextValue(length);
  return true;
}

//-----------------------------------------------------------------------------
bool vtkSlicerStenosisMeasurement3DLogic::DefineOutputTable(vtkMRMLTableNode * outputTableNode)
{
  /*
   * Define an input table structure to store the results in append mode only.
   */
  if (!outputTableNode)
  {
    return false;
  }
  if (outputTableNode->GetNumberOfColumns() == 0)
  {
    vtkNew<vtkStringArray> studyColumn;
    vtkNew<vtkDoubleArray> wallVolumeColumn;
    vtkNew<vtkDoubleArray> lumenVolumeColumn;
    vtkNew<vtkDoubleArray> lesionVolumeColumn;
    vtkNew<vtkDoubleArray> stenosisColumn;
    vtkNew<vtkDoubleArray> startSplineIdColumn;
    vtkNew<vtkDoubleArray> endSplineIdColumn;
    vtkNew<vtkDoubleArray> lengthColumn;
    vtkNew<vtkDoubleArray> lesionVolumePerCmColumn;
    vtkNew<vtkDoubleArray> stenosisPerCmColumn;
    vtkNew<vtkStringArray> notesColumn;

    studyColumn->SetName(COLUMN_NAME_STUDY);
    wallVolumeColumn->SetName(COLUMN_NAME_WALL);
    lumenVolumeColumn->SetName(COLUMN_NAME_LUMEN);
    lesionVolumeColumn->SetName(COLUMN_NAME_LESION);
    stenosisColumn->SetName(COLUMN_NAME_STENOSIS);
    startSplineIdColumn->SetName(COLUMN_NAME_START_SPLINE_ID);
    endSplineIdColumn->SetName(COLUMN_NAME_END_SPLINE_ID);
    lengthColumn->SetName(COLUMN_NAME_LENGTH);
    lesionVolumePerCmColumn->SetName(COLUMN_NAME_LESION_VOLUME_PER_CM);
    stenosisPerCmColumn->SetName(COLUMN_NAME_STENOSIS_PER_CM);
    notesColumn->SetName(COLUMN_NAME_NOTES);

    outputTableNode->AddColumn(studyColumn);
    outputTableNode->AddColumn(wallVolumeColumn);
    outputTableNode->AddColumn(lumenVolumeColumn);
    outputTableNode->AddColumn(lesionVolumeColumn);
    outputTableNode->AddColumn(stenosisColumn);
    outputTableNode->AddColumn(startSplineIdColumn);
    outputTableNode->AddColumn(endSplineIdColumn);
    outputTableNode->AddColumn(lengthColumn);
    outputTableNode->AddColumn(lesionVolumePerCmColumn);
    outputTableNode->AddColumn(stenosisPerCmColumn);
    outputTableNode->AddColumn(notesColumn);

    outputTableNode->SetColumnTitle(COLUMN_NAME_STUDY, vtkMRMLTr("vtkSlicerStenosisMeasurement3DLogic", "Study"));
    outputTableNode->SetColumnTitle(COLUMN_NAME_WALL, vtkMRMLTr("vtkSlicerStenosisMeasurement3DLogic", "Wall volume"));
    outputTableNode->SetColumnTitle(COLUMN_NAME_LUMEN, vtkMRMLTr("vtkSlicerStenosisMeasurement3DLogic", "Lumen volume"));
    outputTableNode->SetColumnTitle(COLUMN_NAME_LESION, vtkMRMLTr("vtkSlicerStenosisMeasurement3DLogic", "Lesion"));
    outputTableNode->SetColumnTitle(COLUMN_NAME_STENOSIS, vtkMRMLTr("vtkSlicerStenosisMeasurement3DLogic", "Stenosis"));
    outputTableNode->SetColumnTitle(COLUMN_NAME_START_SPLINE_ID, vtkMRMLTr("vtkSlicerStenosisMeasurement3DLogic", "From spline id"));
    outputTableNode->SetColumnTitle(COLUMN_NAME_END_SPLINE_ID, vtkMRMLTr("vtkSlicerStenosisMeasurement3DLogic", "To spline id"));
    outputTableNode->SetColumnTitle(COLUMN_NAME_LENGTH, vtkMRMLTr("vtkSlicerStenosisMeasurement3DLogic", "Length"));
    outputTableNode->SetColumnTitle(COLUMN_NAME_LESION_VOLUME_PER_CM, vtkMRMLTr("vtkSlicerStenosisMeasurement3DLogic", "Lesion volume per cm"));
    outputTableNode->SetColumnTitle(COLUMN_NAME_STENOSIS_PER_CM, vtkMRMLTr("vtkSlicerStenosisMeasurement3DLogic", "Stenosis per cm"));
    outputTableNode->SetColumnTitle(COLUMN_NAME_NOTES, vtkMRMLTr("vtkSlicerStenosisMeasurement3DLogic", "Notes"));

    outputTableNode->SetUseColumnTitleAsColumnHeader(true);
    outputTableNode->Modified();
  }
  return true;
}

//-----------------------------------------------------------------------------
bool vtkSlicerStenosisMeasurement3DLogic::ComputeResults(vtkMRMLMarkupsShapeNode * inputShapeNode,
                                                         vtkMRMLMarkupsFiducialNode * inputFiducialNode,
                                                         vtkPolyData * wallClosedPolyData,
                                                         vtkPolyData * lumenClosedPolyData,
                                                         vtkVariantArray * results, const std::string& studyName)
{
  if (!inputShapeNode || !inputFiducialNode || !results)
  {
    return false;
  }
  results->Initialize();
  if (!wallClosedPolyData)
  {
    vtkErrorMacro("Unexpected empty wall closed surface.");
    return false;
  }
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
  // Get the spline length and ids of boundary points.
  vtkNew<vtkDoubleArray> splineBounds;
  if (inputShapeNode && inputFiducialNode)
  {
    if (!this->CalculateClippedSplineLength(inputFiducialNode, inputShapeNode, splineBounds))
    {
      return false; // Logging done.
    }
  }
  // Return the result in a variant array.
  const double length = splineBounds->GetValue(2);
  results->InsertNextValue(studyName.c_str());
  results->InsertNextValue(wallVolume);
  results->InsertNextValue(lumenVolume);
  results->InsertNextValue(lesionVolume);
  results->InsertNextValue(degree);
  results->InsertNextValue(splineBounds->GetValue(0)); // id1
  results->InsertNextValue(splineBounds->GetValue(1)); // id2
  results->InsertNextValue(length);
  results->InsertNextValue(length ? (lesionVolume / length) * 10.0 : -1.0); // Lesion volume per cm
  results->InsertNextValue(length ? (degree / length) * 10.0 : -1.0); // Degree stenosis per cm
  results->InsertNextValue(""); // Notes.

  return true;
}

//-----------------------------------------------------------------------------
// Both input surfaces *must* be closed.
vtkSlicerStenosisMeasurement3DLogic::EnclosingType
vtkSlicerStenosisMeasurement3DLogic::GetClosedSurfaceEnclosingType(vtkPolyData* first, vtkPolyData* second,
                                                                   vtkPolyData * enclosed)
{
  // vtkIntersectionPolyDataFilter on its own is not bullet proof.
  // It is nevertheless used in vtkBooleanOperationPolyDataFilter.
  if (!first || !second)
  {
    vtkErrorMacro("Parameter 'first' or 'second' is NULL.");
    return EnclosingType::EnclosingType_Last;
  }
  if (first->GetNumberOfPoints() == 0 || second->GetNumberOfPoints() == 0)
  {
    vtkErrorMacro("Parameter 'first' or 'second' has zero point.");
    return EnclosingType::EnclosingType_Last;
  }

  const int firstPointCount = first->GetNumberOfPoints();
  const int secondPointCount = second->GetNumberOfPoints();
  int firstInSecondPointCount = 0;
  int secondInFirstPointCount = 0;
  int intersectionPointCount = 0;

  vtkNew<vtkTriangleFilter> triangulatorFirst;
  triangulatorFirst->SetInputData(first);
  triangulatorFirst->Update();

  /*
   * Using the largest region prevents crashes when there are holes in the
   * segment. A segment with a detached largest region outside of the tube is
   * considered out of purpose for the module.
   */
  vtkNew<vtkPolyDataConnectivityFilter> regionExtractorFirst;
  regionExtractorFirst->SetExtractionModeToLargestRegion();
  regionExtractorFirst->SetInputConnection(triangulatorFirst->GetOutputPort());
  regionExtractorFirst->Update();

  vtkNew<vtkTriangleFilter> triangulatorSecond;
  triangulatorSecond->SetInputData(second);
  triangulatorSecond->Update();

  vtkNew<vtkPolyDataConnectivityFilter> regionExtractorSecond;
  regionExtractorSecond->SetExtractionModeToLargestRegion();
  regionExtractorSecond->SetInputConnection(triangulatorSecond->GetOutputPort());
  regionExtractorSecond->Update();

  vtkNew<vtkCleanPolyData> cleanerFirst;
  cleanerFirst->SetInputConnection(regionExtractorFirst->GetOutputPort());
  cleanerFirst->Update();

  vtkNew<vtkCleanPolyData> cleanerSecond;
  cleanerSecond->SetInputConnection(regionExtractorSecond->GetOutputPort());
  cleanerSecond->Update();

  {
    vtkNew<vtkExtractEnclosedPoints> pointExtractor;
    pointExtractor->SetInputConnection(cleanerFirst->GetOutputPort());
    pointExtractor->SetSurfaceConnection(cleanerSecond->GetOutputPort());
    pointExtractor->Update();
    firstInSecondPointCount = pointExtractor->GetOutput()->GetNumberOfPoints();
  }

  {
    vtkNew<vtkExtractEnclosedPoints> pointExtractor;
    pointExtractor->SetInputConnection(cleanerSecond->GetOutputPort());
    pointExtractor->SetSurfaceConnection(cleanerFirst->GetOutputPort());
    pointExtractor->Update();
    secondInFirstPointCount = pointExtractor->GetOutput()->GetNumberOfPoints();
  }

  /*
   * NOTE: Below may fail. In one scene, it fails with a tube resolution at 45,
   * and succeeds at 44, 46 and even 15. In another scene, 45 is OK. The input
   * segment is a regular one.
   * Both outputs of the boolFilter have zero point on failure. It's not
   * possible to detect a processing failure.
   */
  vtkNew<vtkBooleanOperationPolyDataFilter> boolFilter;
  boolFilter->SetOperationToIntersection();
  boolFilter->SetInputConnection(cleanerFirst->GetOutputPort());
  boolFilter->AddInputConnection(1, cleanerSecond->GetOutputPort());
  boolFilter->Update();
  // 0 means completely distinct or one is completely enclosed in the other.
  intersectionPointCount = boolFilter->GetOutput()->GetNumberOfPoints();

  if (intersectionPointCount != 0)
  {
    if (enclosed)
    {
      // There may be triangles and/or strips beyond each end.
      // Further processing must be done by the caller.
      enclosed->Initialize();
      enclosed->DeepCopy(boolFilter->GetOutput());
    }
    return EnclosingType::Intersection;
  }
  if (firstInSecondPointCount == firstPointCount)
  {
    if (enclosed)
    {
      enclosed->Initialize();
      enclosed->DeepCopy(first);
    }
    return EnclosingType::FirstIsEnclosed;
  }
  if (secondInFirstPointCount == secondPointCount)
  {
    if (enclosed)
    {
      enclosed->Initialize();
      enclosed->DeepCopy(second);
    }
    return EnclosingType::SecondIsEnclosed;
  }

  return EnclosingType::Distinct;
}

//-----------------------------------------------------------------------------
// Obtain a very nice mesh as seen in WireFrame representation.
bool vtkSlicerStenosisMeasurement3DLogic::UpdateClosedSurfaceMesh(vtkPolyData* inMesh, vtkPolyData* outMesh)
{
  if (!inMesh || !outMesh)
  {
    vtkErrorMacro("Parameter 'inMesh' or 'outMesh' is NULL.");
    return false;
  }
  if (!this->GetMRMLScene())
  {
    vtkErrorMacro("MRML scene is NULL.");
    return false;
  }

  vtkNew<vtkMRMLSegmentationNode> segmentationNode;
  segmentationNode->CreateClosedSurfaceRepresentation();

  const std::string preferred3DRepresentationName = vtkSegmentationConverter::GetSegmentationClosedSurfaceRepresentationName();

  const std::string segmentId = segmentationNode->AddSegmentFromClosedSurfaceRepresentation(inMesh, this->GetMRMLScene()->GenerateUniqueName("MeshInput"));
  // The mesh is recreated here.
  outMesh->Initialize();
  segmentationNode->GetSegmentation()->RemoveRepresentation(preferred3DRepresentationName);
  segmentationNode->GetSegmentation()->CreateRepresentation(preferred3DRepresentationName);
  segmentationNode->GetClosedSurfaceRepresentation(segmentId, outMesh);

  return true;
}

//---------------------------------------------------------------------------
bool vtkSlicerStenosisMeasurement3DLogic::CreateLesion(vtkMRMLMarkupsShapeNode * wallShapeNode,
                                                       vtkPolyData * enclosedSurface,
                                                       vtkMRMLMarkupsFiducialNode * boundaryFiducialNode,
                                                       vtkPolyData * lesion)
{
  if (!lesion)
  {
    vtkErrorMacro("Please provide a polydata object to hold the results.");
    return false;
  }
  // Note: we don't call ::UpdateBoundaryControlPointPosition here.
  if (wallShapeNode == nullptr || boundaryFiducialNode == nullptr
    || enclosedSurface == nullptr
    || wallShapeNode->GetNumberOfControlPoints() < 4 || boundaryFiducialNode->GetNumberOfControlPoints() < 2
    || wallShapeNode->GetShapeName() != vtkMRMLMarkupsShapeNode::Tube
  )
  {
    vtkErrorMacro("Invalid input, cannot create lesion.");
    return false;
  }

  // Get the spline polydata from the shape markups node.
  vtkSmartPointer<vtkPolyData> spline = vtkSmartPointer<vtkPolyData>::New();
  if (!wallShapeNode->GetTrimmedSplineWorld(spline))
  {
    vtkErrorMacro("The tube does not have a valid spline.");
    return false;
  }

  // Put a ficucial point on the nearest point of the wall spline.
  this->UpdateBoundaryControlPointPosition(0, boundaryFiducialNode, wallShapeNode);
  this->UpdateBoundaryControlPointPosition(1, boundaryFiducialNode, wallShapeNode);

  // Get wall polydata from shape markups node.
  vtkPolyData * wallOpenSurface = wallShapeNode->GetShapeWorld();
  vtkPolyData * wallClosedSurface = wallShapeNode->GetCappedTubeWorld();

  // The first 2 fiducial points are used to cut through the lumen and wall polydata at arbitrary positions.
  double p1[3] = { 0.0 };
  double p2[3] = { 0.0 };
  boundaryFiducialNode->GetNthControlPointPositionWorld(0, p1);
  boundaryFiducialNode->GetNthControlPointPositionWorld(1, p2);

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
  vtkNew<vtkPolyData> wallOpenInBounds;
  if (!this->ClipClosedSurface(wallOpenSurface, wallIntermediate, p1, startDirection, false))
  {
    return false;
  }
  if (!this->ClipClosedSurface(wallIntermediate, wallOpenInBounds, p2, endDirection, false))
  {
    return false;
  }

  vtkNew<vtkPolyData> lumenIntermediate;
  vtkNew<vtkPolyData> lumenOpenInBounds;
  if (!this->ClipClosedSurface(enclosedSurface, lumenIntermediate, p1, startDirection, false))
  {
    return false;
  }

  if (!this->ClipClosedSurface(lumenIntermediate, lumenOpenInBounds, p2, endDirection, false))
  {
    return false;
  }

  vtkNew<vtkIntArray> array;
  array->SetName("PartId");
  array->SetNumberOfValues(wallOpenInBounds->GetNumberOfPoints());
  array->Fill(0);
  for (int i = 0; i < lumenOpenInBounds->GetNumberOfPoints(); i++)
  {
    array->InsertNextValue(1);
  }
  vtkNew<vtkAppendPolyData> appender;
  appender->AddInputData(wallOpenInBounds);
  appender->AddInputData(lumenOpenInBounds);
  appender->Update();
  vtkNew<vtkFeatureEdges> edgeExtractor;
  edgeExtractor->SetInputConnection(appender->GetOutputPort());
  edgeExtractor->BoundaryEdgesOn();
  edgeExtractor->FeatureEdgesOff();
  edgeExtractor->ManifoldEdgesOff();
  edgeExtractor->NonManifoldEdgesOff();
  edgeExtractor->Update();
  vtkNew<vtkContourTriangulator> contourFill;
  contourFill->SetInputConnection(edgeExtractor->GetOutputPort());
  contourFill->Update();
  vtkPolyData * contours = contourFill->GetOutput();
  for (int i = 0; i < contours->GetNumberOfPoints(); i++)
  {
    array->InsertNextValue(2);
  }
  appender->AddInputData(contours);
  appender->Update();
  appender->GetOutput()->GetPointData()->AddArray(array);
  vtkNew<vtkPolyDataNormals> normals;
  normals->SetInputConnection(appender->GetOutputPort());
  normals->Update();

  lesion->Initialize();
  lesion->DeepCopy(normals->GetOutput());

  return true;
}
//------------------------------------------------------------------------------
bool vtkSlicerStenosisMeasurement3DLogic::DumpAggregateVolumes(vtkMRMLMarkupsShapeNode* wallShapeNode,
                                                              vtkPolyData* enclosedSurface,
                                                              std::string filepath)
{
  /* 
   * There may be marginal differences with the result from ::Process(), mainly
   * with the lumen volume. These are inversely proportional to the spline
   * resolution. The surface resolution influences less.
   * 
   * Chop the surfaces in blocks, one thread for each block.
   * Calculate volumes from the first spline id of a block to the next until the last id.
   * Append the array from each thread in the 'result' table.
   * Cross join the table in SQLite and create a new aggregate table.
   * Each row is crossed with the entire table.
   */
  if (wallShapeNode == nullptr || enclosedSurface == nullptr || filepath.empty()
    || wallShapeNode->GetShapeName() != vtkMRMLMarkupsShapeNode::Tube
    || wallShapeNode->GetNumberOfControlPoints() < 4
  )
  {
    vtkErrorMacro("Invalid input, cannot continue.");
    return false;
  }

  vtkNew<vtkPolyData> trimmedSpline;
  if (!wallShapeNode->GetTrimmedSplineWorld(trimmedSpline))
  {
    vtkErrorMacro("The tube does not have a valid spline.");
    return false;
  }

  vtkNew<vtkMRMLTableNode> result;

  // Exclude the last point to remain within bounds. 851 spline points -> 850 measurements.
  const int numberOfPoints = trimmedSpline->GetNumberOfPoints() - 1;
  int numberOfThreads = std::thread::hardware_concurrency(); // Does not mean number of cores/cpus.
  if (numberOfThreads < 1 || numberOfPoints < numberOfThreads)
  {
    numberOfThreads = 1;
  }
  const int residual = numberOfPoints % numberOfThreads;
  const int numberOfPointsPerBlock = numberOfPoints / numberOfThreads;
  std::vector<std::thread> threads;
  std::vector<vtkSmartPointer<vtkDoubleArray>> bufferArrays;

  for (int i = 0; i < numberOfThreads; i++)
  {
    const vtkIdType startBlockId = i * numberOfPointsPerBlock;
    vtkIdType endBlockId = ((i + 1) * numberOfPointsPerBlock) - 1;
    if (i == (numberOfThreads - 1))
    {
      endBlockId += residual;
    }
    vtkSmartPointer<vtkDoubleArray> bufferArray = vtkSmartPointer<vtkDoubleArray> ::New();
    bufferArray->SetNumberOfComponents(5);
    bufferArrays.push_back(bufferArray);

    vtkSmartPointer<vtkPolyData> wallSurfaceCopy = vtkSmartPointer<vtkPolyData>::New();
    vtkSmartPointer<vtkPolyData> lumenSurfaceCopy = vtkSmartPointer<vtkPolyData>::New();
    vtkSmartPointer<vtkPolyData> trimmedSplineCopy = vtkSmartPointer<vtkPolyData>::New();
    wallSurfaceCopy->DeepCopy(wallShapeNode->GetCappedTubeWorld());
    lumenSurfaceCopy->DeepCopy(enclosedSurface);
    vtkNew<vtkPolyData> threadTrimmedSpline;
    wallShapeNode->GetTrimmedSplineWorld(threadTrimmedSpline);
    trimmedSplineCopy->DeepCopy(threadTrimmedSpline);
    threads.push_back(std::thread(
                        VolumeComputeWorker(),
                        this, i,
                        wallSurfaceCopy, lumenSurfaceCopy, trimmedSplineCopy,
                        bufferArray, startBlockId, endBlockId
                          ) // std::thread
                      );    // threads

  }
  for (int i = 0; i < numberOfThreads; i++)
  {
    threads[i].join();
  }

  vtkTable * table = result->GetTable();
  vtkNew<vtkDoubleArray> splineIdColumn;
  vtkNew<vtkDoubleArray> distanceColumn;
  vtkNew<vtkDoubleArray> wallVolumeColumn;
  vtkNew<vtkDoubleArray> lumenVolumeColumn;
  splineIdColumn->SetName("SplineId");
  distanceColumn->SetName("Distance");
  wallVolumeColumn->SetName("WallVolume");
  lumenVolumeColumn->SetName("LumenVolume");
  table->AddColumn(splineIdColumn);
  table->AddColumn(distanceColumn);
  table->AddColumn(wallVolumeColumn);
  table->AddColumn(lumenVolumeColumn);
  table->InsertNextBlankRow();

  double totalCumulated[3] = {0.0};
  for (int i = 0; i < numberOfThreads; i++)
  {
    vtkDoubleArray * bufferArray = bufferArrays[i];
    for (int t = 0; t < bufferArray->GetNumberOfTuples(); t++)
    {
      double * currentTuple = bufferArray->GetTuple(t);
      vtkNew<vtkVariantArray> cumulated;
      cumulated->InsertNextValue(currentTuple[1]); // endBlockId, startBlockId is always 0
      cumulated->InsertNextValue(currentTuple[2] + totalCumulated[0]); // distance
      cumulated->InsertNextValue(currentTuple[3] + totalCumulated[1]); // wallVolume
      cumulated->InsertNextValue(currentTuple[4] + totalCumulated[2]); // lumenVolume
      table->InsertNextRow(cumulated);
    }

    vtkVariantArray * lastCumulatedTuple = table->GetRow(table->GetNumberOfRows() - 1);
    totalCumulated[0] = lastCumulatedTuple->GetValue(1).ToDouble(); // distance
    totalCumulated[1] = lastCumulatedTuple->GetValue(2).ToDouble(); // wallVolume
    totalCumulated[2] = lastCumulatedTuple->GetValue(3).ToDouble(); // lumenVolume
  }

  vtkNew<vtkSQLiteDatabase> db;
  db->SetDatabaseFileName(filepath.c_str());
  if (!db->Open(nullptr, vtkSQLiteDatabase::CREATE)) // CREATE - Create new, fail if file exists.
  {
    vtkErrorMacro("File exists, aborting.");
    return false;
  }
  vtkNew<vtkTableToSQLiteWriter> dbWriter;
  // Cumulative volumes from spline id 0 to the last one.
  dbWriter->SetTableName("CumulativeVolumes");
  dbWriter->SetDatabase(db);
  dbWriter->SetInputData(result->GetTable());
  dbWriter->Update();

  // Using an intermediate for easier read/write of SQL expressions.
  // Volumes between spline points, from id1 to id2.
  std::string sql = "CREATE TABLE Intermediate AS" 
  " SELECT V1.SplineId StartId, V2.SplineId EndId,"
  " CAST((V2.Distance - V1.Distance) AS REAL) Distance,"
  " CAST((V2.WallVolume - V1.WallVolume) AS REAL ) WallVolume,"
  " CAST((V2.LumenVolume - V1.LumenVolume) AS REAL ) LumenVolume,"
  " CAST(((V2.WallVolume - V1.WallVolume) - (V2.LumenVolume - V1.LumenVolume)) AS REAL) LesionVolume"
  " FROM CumulativeVolumes V1 CROSS JOIN CumulativeVolumes V2"
  " WHERE V1.SplineId < V2.SplineId"
  " ORDER BY V1.SplineId, V2.SplineId";
  // query must be explicitly deleted.
  vtkSQLiteQuery * query = static_cast<vtkSQLiteQuery*> (db->GetQueryInstance());
  query->SetQuery(sql.c_str());
  if (!query->Execute())
  {
    vtkErrorMacro("Error creating 'Intermediate' table, aborting.");
    return false;
  }
  /*
   * Final table for volumes between spline points, from id 'p' to id 'p + n'.
   */

  sql = "CREATE TABLE BoundVolumes AS"
  " SELECT *,"
  " CAST((LesionVolume / WallVolume)  * 100 AS REAL) Stenosis,"
  " CAST((LesionVolume / Distance) * 10 AS REAL) LesionVolumePerCm,"
  " CAST(((LesionVolume / WallVolume) / Distance) * 10 AS REAL) StenosisPerCm"
  " FROM Intermediate";
  query->SetQuery(sql.c_str());
  if (!query->Execute())
  {
    vtkErrorMacro("Error creating 'BoundVolumes' table, aborting.");
    return false;
  }
  sql = "DROP TABLE Intermediate";
  query->SetQuery(sql.c_str());
  if (!query->Execute())
  {
    vtkErrorMacro("Error deleting 'Intermediate' table."); // Don't return.
  }
  query->Delete();

  auto createIndices = [&] (vtkStringArray * queries)
  {
    if (!queries)
    {
      vtkErrorMacro("Invalid queries array, aborting.");
      return false;
    }
    bool noError = true;
    vtkSQLiteQuery * indexQuery = static_cast<vtkSQLiteQuery*> (db->GetQueryInstance());
    for (int i = 0; i < queries->GetNumberOfValues(); i++)
    {
      vtkStdString indexSql = queries->GetValue(i);
      indexQuery->SetQuery(indexSql.c_str());
      if (!indexQuery->Execute())
      {
        noError = false;
      }
    }
    indexQuery->Delete();
    return noError;
  };

  vtkNew<vtkStringArray> indexSql;
  indexSql->InsertNextValue("CREATE INDEX CumulativeVolumes_SplineId ON CumulativeVolumes(SplineId)");
  indexSql->InsertNextValue("CREATE INDEX CumulativeVolumes_Distance ON CumulativeVolumes(Distance)");
  indexSql->InsertNextValue("CREATE INDEX CumulativeVolumes_WallVolume ON CumulativeVolumes(WallVolume)");
  indexSql->InsertNextValue("CREATE INDEX CumulativeVolumes_LumenVolume ON CumulativeVolumes(LumenVolume)");
  if (!createIndices(indexSql))
  {
    vtkErrorMacro("Error creating indices on CumulativeVolumes table.");
  }

  indexSql->Initialize();
  indexSql->InsertNextValue("CREATE INDEX BoundVolumes_StartId ON BoundVolumes(StartId)");
  indexSql->InsertNextValue("CREATE INDEX BoundVolumes_EndId ON BoundVolumes(EndId)");
  indexSql->InsertNextValue("CREATE INDEX BoundVolumes_StartId_EndId ON BoundVolumes(StartId, EndId)");
  indexSql->InsertNextValue("CREATE INDEX BoundVolumes_Distance ON BoundVolumes(Distance)");
  indexSql->InsertNextValue("CREATE INDEX BoundVolumes_WallVolume ON BoundVolumes(WallVolume)");
  indexSql->InsertNextValue("CREATE INDEX BoundVolumes_LumenVolume ON BoundVolumes(LumenVolume)");
  indexSql->InsertNextValue("CREATE INDEX BoundVolumes_LesionVolume ON BoundVolumes(LesionVolume)");
  indexSql->InsertNextValue("CREATE INDEX BoundVolumes_Stenosis ON BoundVolumes(Stenosis)");
  indexSql->InsertNextValue("CREATE INDEX BoundVolumes_LesionVolumePerCm ON BoundVolumes(LesionVolumePerCm)");
  indexSql->InsertNextValue("CREATE INDEX BoundVolumes_StenosisPerCm ON BoundVolumes(StenosisPerCm)");
  if (!createIndices(indexSql))
  {
    vtkErrorMacro("Error creating indices on BoundVolumes table.");
  }

  // Proceed with specialised statistical software for further analysis.
  // It's not even possible to get a standard deviation from <cmath>.
  db->Close();

  return true;
}

//------------------------------------------------------------------------------
VolumeComputeWorker::VolumeComputeWorker()
{
}

//------------------------------------------------------------------------------
VolumeComputeWorker::~VolumeComputeWorker()
{
}

//------------------------------------------------------------------------------
void VolumeComputeWorker::operator()(vtkSlicerStenosisMeasurement3DLogic * logic,
                                     int ID, vtkPolyData* wallSurface,
                                     vtkPolyData* lumenSurface,
                                     vtkPolyData* spline,
                                     vtkDoubleArray* bufferArray,
                                     vtkIdType startBlockId,
                                     vtkIdType endBlockId)
{
  this->Id = ID;
  double startPoint[3] = { 0.0 };
  double startPointNeighbour[3] = { 0.0 };
  double startNormal[3] = { 0.0 };
  spline->GetPoint(startBlockId, startPoint);
  spline->GetPoint(startBlockId + 1, startPointNeighbour);
  vtkMath::Subtract(startPointNeighbour, startPoint, startNormal);

  for (vtkIdType i = startBlockId + 1; i <= endBlockId + 1; i++) // +1, +1
  {
    double p2[3] = { 0.0 };
    double p2Neighbour[3] = { 0.0 };
    double endNormal[3] = { 0.0 };
    spline->GetPoint(i, p2);
    spline->GetPoint(i - 1, p2Neighbour);
    vtkMath::Subtract(p2Neighbour, p2, endNormal);

    vtkNew<vtkPolyData> clippedWall;
    if (!logic->ClipClosedSurfaceWithClosedOutput(wallSurface, clippedWall,
                                             startPoint, startNormal,
                                             p2, endNormal))
    {
      std::cerr << "Error clipping wall surface from id " << startBlockId
              << " to " << i << "." << std::endl;
      continue;
    }
    vtkNew<vtkPolyData> clippedLumen;
    if (!logic->ClipClosedSurfaceWithClosedOutput(lumenSurface, clippedLumen,
                                              startPoint, startNormal,
                                              p2, endNormal))
    {
      std::cerr << "Error clipping lumen surface from id " << startBlockId
      << " to " << i << "." << std::endl;
      continue;
    }
    double distance = this->CalculateSplineDistance(spline, startBlockId, i);

    vtkNew<vtkMassProperties> wallProperties;
    wallProperties->SetInputData(clippedWall);
    wallProperties->Update();
    vtkNew<vtkMassProperties> lumenProperties;
    lumenProperties->SetInputData(clippedLumen);
    lumenProperties->Update();
    double tuple[5] = {(double) startBlockId, (double) i, distance,
                wallProperties->GetVolume(), lumenProperties->GetVolume()};
    bufferArray->InsertNextTuple(tuple);
  }
}

//------------------------------------------------------------------------------
double VolumeComputeWorker::CalculateSplineDistance(vtkPolyData* spline, vtkIdType startId, vtkIdType endId)
{
  if (!spline || startId < 0 || endId < 0 || startId > endId)
  {
    mtx.lock();
    std::cerr << "Invalid input, cannot calculate spline distance." << std::endl;
    mtx.unlock();
    return -1.0;
  }
  double length = 0.0;
  for (vtkIdType splineId = startId; splineId < endId; splineId++)
  {
    double p1[3] = { 0.0 };
    double p2[3] = { 0.0 };
    spline->GetPoint(splineId, p1);
    spline->GetPoint(splineId + 1, p2);
    length += std::sqrt(vtkMath::Distance2BetweenPoints(p1, p2));
  }
  return length;
}

