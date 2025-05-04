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

// Qt includes
#include <QDebug>

// Slicer includes
#include "qSlicerStenosisMeasurement3DModuleWidget.h"
#include "ui_qSlicerStenosisMeasurement3DModuleWidget.h"
#include <qSlicerMainWindow.h>
#include <qSlicerCoreApplication.h>
#include <qstatusbar.h>
#include <QSettings>
#include <QMessageBox>

#include <vtkMRMLScene.h>
#include <vtkMRMLMarkupsFiducialNode.h>
#include <vtkMRMLMarkupsDisplayNode.h>
#include <vtkMRMLMarkupsShapeNode.h>
#include <vtkMRMLModelNode.h>
#include <vtkMassProperties.h>
#include <vtkMRMLTableNode.h>
#include <vtkMRMLMeasurementLength.h>
#include <vtkMRMLMeasurementVolume.h>
#include <vtkMRMLStaticMeasurement.h>
#include <vtkVariantArray.h>
#include <vtkTable.h>
#include <vtkMRMLSelectionNode.h>
#include <vtkMRMLUnitNode.h>
#include <qSlicerExtensionsManagerModel.h>

//-----------------------------------------------------------------------------
/// \ingroup Slicer_QtModules_ExtensionTemplate
class qSlicerStenosisMeasurement3DModuleWidgetPrivate: public Ui_qSlicerStenosisMeasurement3DModuleWidget
{
public:
  qSlicerStenosisMeasurement3DModuleWidgetPrivate();
  vtkSmartPointer<vtkMRMLTableNode> currentTableNode = nullptr;
};

//-----------------------------------------------------------------------------
// qSlicerStenosisMeasurement3DModuleWidgetPrivate methods

//-----------------------------------------------------------------------------
qSlicerStenosisMeasurement3DModuleWidgetPrivate::qSlicerStenosisMeasurement3DModuleWidgetPrivate()
{
}

//-----------------------------------------------------------------------------
// qSlicerStenosisMeasurement3DModuleWidget methods

//-----------------------------------------------------------------------------
qSlicerStenosisMeasurement3DModuleWidget::qSlicerStenosisMeasurement3DModuleWidget(QWidget* _parent)
  : Superclass( _parent )
  , d_ptr( new qSlicerStenosisMeasurement3DModuleWidgetPrivate )
{
  this->logic = vtkSmartPointer<vtkSlicerStenosisMeasurement3DLogic>::New();
}

//-----------------------------------------------------------------------------
qSlicerStenosisMeasurement3DModuleWidget::~qSlicerStenosisMeasurement3DModuleWidget()
{
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::setup()
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  d->setupUi(this);
  this->Superclass::setup();
  
  d->outputCollapsibleButton->setCollapsed(true);
  d->modelCollapsibleButton->setCollapsed(true);
  
  QObject::connect(d->applyButton, SIGNAL(clicked()),
                   this, SLOT(onApply()));
  QObject::connect(d->inputShapeSelector, SIGNAL(currentNodeChanged(vtkMRMLNode*)),
                   this, SLOT(onShapeNodeChanged(vtkMRMLNode*)));
  QObject::connect(d->inputFiducialSelector, SIGNAL(currentNodeChanged(vtkMRMLNode*)),
                   this, SLOT(onFiducialNodeChanged(vtkMRMLNode*)));
  QObject::connect(d->inputFiducialSelector, SIGNAL(nodeAddedByUser(vtkMRMLNode*)),
                   this, SLOT(onFiducialNodeChanged(vtkMRMLNode*)));
  QObject::connect(d->inputSegmentSelector, SIGNAL(currentNodeChanged(vtkMRMLNode*)),
                   this, SLOT(onSegmentationNodeChanged(vtkMRMLNode*)));
  QObject::connect(d->inputSegmentSelector, SIGNAL(currentSegmentChanged(QString)),
                   this, SLOT(onSegmentIDChanged(QString)));
  QObject::connect(d->lesionModelSelector, SIGNAL(currentNodeChanged(vtkMRMLNode*)),
                   this, SLOT(onLesionModelNodeChanged(vtkMRMLNode*)));
  QObject::connect(d->outputTableSelector, SIGNAL(currentNodeChanged(vtkMRMLNode*)),
                   this, SLOT(onTableNodeChanged(vtkMRMLNode*)));
  QObject::connect(d->updateBoundaryPointsSpinBox, SIGNAL(valueChanged(int)),
                   this, SLOT(onUpdateBoundary(int)));

  // Put p1 and p2 ficucial points on the tube spline at nearest point when they are moved.
  this->fiducialObservation = vtkSmartPointer<vtkCallbackCommand>::New();
  this->fiducialObservation->SetClientData( reinterpret_cast<void *>(this) );
  this->fiducialObservation->SetCallback(qSlicerStenosisMeasurement3DModuleWidget::onFiducialPointEndInteraction);
  
  // Put p1 and p2 ficucial points on the tube spline at nearest point when the tube is updated.
  this->tubeObservation = vtkSmartPointer<vtkCallbackCommand>::New();
  this->tubeObservation->SetClientData( reinterpret_cast<void *>(this) );
  this->tubeObservation->SetCallback(qSlicerStenosisMeasurement3DModuleWidget::onTubePointEndInteraction);

  // We won't check the structure of the table and assume it has been created in the module.
  const QString attributeName = QString(MODULE_TITLE) + QString(".Role");
  d->outputTableSelector->addAttribute("vtkMRMLTableNode", attributeName, MODULE_TITLE);
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::enter()
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);

  if (this->logic)
  {
    this->logic->SetMRMLScene(this->mrmlScene());
  }
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onApply()
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  
  vtkMRMLNode * shapeNode = d->inputShapeSelector->currentNode();
  vtkMRMLNode * fiducialNode = d->inputFiducialSelector->currentNode();
  vtkMRMLNode * segmentationNode = d->inputSegmentSelector->currentNode();
  const std::string currentSegmentID = d->inputSegmentSelector->currentSegmentID().toStdString();
  
  if (!shapeNode || !fiducialNode || !segmentationNode || currentSegmentID.empty())
  {
    this->showStatusMessage(qSlicerStenosisMeasurement3DModuleWidget::tr("Insufficient input."), 5000);
    return;
  }
  vtkMRMLMarkupsShapeNode * shapeNodeReal = vtkMRMLMarkupsShapeNode::SafeDownCast(shapeNode);
  if (!shapeNodeReal || shapeNodeReal->GetShapeName() != vtkMRMLMarkupsShapeNode::Tube)
  {
    this->showStatusMessage(qSlicerStenosisMeasurement3DModuleWidget::tr("Wrong shape node."), 5000);
    return;
  }
  vtkMRMLMarkupsFiducialNode * fiducialNodeReal = vtkMRMLMarkupsFiducialNode::SafeDownCast(fiducialNode);
  if (!fiducialNodeReal)
  {
    this->showStatusMessage(qSlicerStenosisMeasurement3DModuleWidget::tr("Inconsistent fiducial input."), 5000);
    return;
  }
  if (fiducialNodeReal->GetNumberOfControlPoints() < 2)
  {
    this->showStatusMessage(qSlicerStenosisMeasurement3DModuleWidget::tr("Two fiducial input points are mandatory."), 5000);
    return;
  }
  vtkMRMLSegmentationNode * segmentationNodeReal = vtkMRMLSegmentationNode::SafeDownCast(segmentationNode);
  if (!segmentationNodeReal)
  {
    this->showStatusMessage(qSlicerStenosisMeasurement3DModuleWidget::tr("Inconsistent segmentation input."), 5000);
    return;
  }

  // Get the lumen enclosed in the tube once only, it may be time consuming.
  vtkNew<vtkPolyData> enclosedSurface;
  vtkSlicerStenosisMeasurement3DLogic::EnclosingType enclosingType = this->getEnclosedSurface(
                          shapeNodeReal, segmentationNodeReal, currentSegmentID,enclosedSurface);
  if (enclosingType == vtkSlicerStenosisMeasurement3DLogic::EnclosingType_Last)
  {
    this->showStatusMessage(qSlicerStenosisMeasurement3DModuleWidget::tr("Error getting the enclosed lumen."), 5000);
    return;
  }
  if (enclosingType == vtkSlicerStenosisMeasurement3DLogic::Distinct)
  {
    this->showStatusMessage(qSlicerStenosisMeasurement3DModuleWidget::tr("Input tube and input lumen do not intersect."), 5000);
    return;
  }

  // Create output data.
  vtkSmartPointer<vtkPolyData> wallOpen = vtkSmartPointer<vtkPolyData>::New();
  vtkSmartPointer<vtkPolyData> lumenOpen = vtkSmartPointer<vtkPolyData>::New();
  vtkSmartPointer<vtkPolyData> wallClosed = vtkSmartPointer<vtkPolyData>::New();
  vtkSmartPointer<vtkPolyData> lumenClosed = vtkSmartPointer<vtkPolyData>::New();
  // Do the job.
  vtkNew<vtkVariantArray> results;
  if (!this->logic->Process(shapeNodeReal, enclosedSurface, fiducialNodeReal,
                            wallOpen, lumenOpen, wallClosed, lumenClosed,
                            results, d->currentTableNode))
  {
    this->showStatusMessage(qSlicerStenosisMeasurement3DModuleWidget::tr("Processing failed."), 5000);
    return;
  }
  // Finally show result.
  this->showResult(wallClosed, lumenClosed, results);
  // Optionally create models.
  this->createLesionModel(shapeNodeReal, enclosedSurface, fiducialNodeReal);
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::showResult(vtkPolyData * wall, vtkPolyData * lumen,
                                                          vtkVariantArray * results)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  
  vtkNew<vtkMassProperties> wallMassProperties;
  wallMassProperties->SetInputData(wall);
  wallMassProperties->Update();
  vtkNew<vtkMassProperties> lumenMassProperties;
  lumenMassProperties->SetInputData(lumen);
  lumenMassProperties->Update();

  if (wall == nullptr)
  {
    d->wallResultLabel->clear();
    d->lesionResultLabel->clear();
    d->stenosisResultLabel->clear();
  }
  if (lumen == nullptr)
  {
    d->lumenResultLabel->clear();
    d->lesionResultLabel->clear();
    d->stenosisResultLabel->clear();
  }
  if (wall == nullptr && lumen == nullptr)
  {
    return;
  }
  vtkMRMLScene * scene = this->mrmlScene();
  if (!scene)
  {
    return;
  }
  vtkMRMLNode * selectionNodeMrml = scene->GetNodeByID("vtkMRMLSelectionNodeSingleton");
  if (!selectionNodeMrml)
  {
    return;
  }
  vtkMRMLSelectionNode * mrmlSelectionNode = vtkMRMLSelectionNode::SafeDownCast(selectionNodeMrml);

  // Get the volumes.
  const double wallVolume = results->GetValue(0).ToDouble();
  const double lumenVolume = results->GetValue(1).ToDouble();
  const double lesionVolume =results->GetValue(2).ToDouble();
  const double degree =results->GetValue(3).ToDouble();
  const double length =results->GetValue(6).ToDouble();

  // Use the facilities of MRML measurement classes to format the volumes.
  auto show = [&] (const double& value, const std::string& category, QLabel * widget)
  {
    const char * idUnitNode = mrmlSelectionNode->GetUnitNodeID(category.c_str());
    vtkMRMLNode * unitNodeMrml = scene->GetNodeByID(idUnitNode);
    if (!unitNodeMrml)
    {
      return;
    }
    vtkMRMLUnitNode * unitNode = vtkMRMLUnitNode::SafeDownCast(unitNodeMrml);
    const char * displayString = unitNode->GetDisplayStringFromValue(value);
    
    widget->setText(displayString);
    widget->setToolTip(std::to_string(value).c_str());
  };
  
  d->outputCollapsibleButton->setCollapsed(false);
  show(wallVolume, "volume", d->wallResultLabel);
  show(lumenVolume, "volume", d->lumenResultLabel);
  show(lesionVolume, "volume", d->lesionResultLabel);
  
  std::string stenosisDegree = "#ERR";
  if (wallVolume > 0)
  {
    const double degree = (lesionVolume / wallVolume);
    vtkNew<vtkMRMLStaticMeasurement> measurement;
    measurement->SetValue(degree);
    measurement->SetDisplayCoefficient(100);
    measurement->SetPrintFormat("%-#4.3g %s");
    measurement->SetUnits(" %");
    measurement->Modified();
    stenosisDegree = measurement->GetValueWithUnitsAsPrintableString();
    
    std::string tip = std::to_string(degree); // 0.xyz, raw ratio, no units needed.
    d->stenosisResultLabel->setToolTip(tip.c_str());
  }
  d->stenosisResultLabel->setText(stenosisDegree.c_str());

  // Show the length of the spline between boundary points.
  if (length >= 0)
  {
    show(length, "length", d->lengthResultLabel);
  }
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::createLesionModel(vtkMRMLMarkupsShapeNode * wallShapeNode,
                                                            vtkPolyData * enclosedSurface,
                                                            vtkMRMLMarkupsFiducialNode * boundaryFiducialNode)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);

  vtkMRMLNode * modelMrml = d->lesionModelSelector->currentNode();
  if (!modelMrml)
  {
    return;
  }
  vtkMRMLModelNode * model = vtkMRMLModelNode::SafeDownCast(modelMrml);
  vtkNew<vtkPolyData> lesion;
  this->logic->CreateLesion(wallShapeNode, enclosedSurface, boundaryFiducialNode,
                          lesion);
  model->CreateDefaultDisplayNodes();
  model->SetAndObserveMesh(lesion);
}

//-------------------------- From util.py -------------------------------------
bool qSlicerStenosisMeasurement3DModuleWidget::showStatusMessage(const QString& message, int duration)
{
  QWidgetList widgets = qSlicerCoreApplication::application()->topLevelWidgets();
  QWidget * mainWidget = nullptr;
  for (int i = 0; i < widgets.count(); i++)
  {
    if (widgets.at(i)->objectName() == QString("qSlicerMainWindow"))
    {
      mainWidget = widgets.at(i);
      break;
    }
  }
  if (!mainWidget)
  {
    return false;
  }
  qSlicerMainWindow * mainWindow = static_cast<qSlicerMainWindow*> (mainWidget);
  if (!mainWindow /*?*/ || !mainWindow->statusBar())
  {
    return false;
  }
  mainWindow->statusBar()->showMessage(message, duration);
  qSlicerCoreApplication::application()->processEvents();
  return true;
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onSegmentationNodeChanged(vtkMRMLNode * node)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  /*
   * The segmentation selector is special.
   * If we don't clear it explicitly, the last segment is selected
   * in many scenarios, and Apply fails nevertheless.
   * Despite this clearing, the right segment ID in the parameter node
   * is selected.
   */
  QSignalBlocker blocker(d->inputSegmentSelector);
  d->inputSegmentSelector->setCurrentSegmentID("");
}

//-----------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onSegmentIDChanged(QString segmentID)
{
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onLesionModelNodeChanged(vtkMRMLNode * node)
{
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onTableNodeChanged(vtkMRMLNode * node)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  if (d->currentTableNode)
  {
    qvtkDisconnect(d->currentTableNode, vtkCommand::ModifiedEvent, this , SLOT(onTableContentModified()));
  }
  d->updateBoundaryPointsSpinBox->setRange(0, 0);
  if (node)
  {
    vtkMRMLTableNode * tableNode = vtkMRMLTableNode::SafeDownCast(node);
    qvtkReconnect(tableNode, vtkCommand::ModifiedEvent, this , SLOT(onTableContentModified()));
    d->updateBoundaryPointsSpinBox->setRange(0, tableNode->GetNumberOfRows());
    d->currentTableNode = tableNode;
  }
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onFiducialPointEndInteraction(vtkObject *caller,
                                                                             unsigned long event, void *clientData, void *callData)
{
  qSlicerStenosisMeasurement3DModuleWidget * client = reinterpret_cast<qSlicerStenosisMeasurement3DModuleWidget*>(clientData);
  if (!client || !client->currentShapeNode)
  {
    return;
  }
  vtkMRMLMarkupsShapeNode * shapeNode = vtkMRMLMarkupsShapeNode::SafeDownCast(client->currentShapeNode);
  // React only if shape is a tube.
  if (!shapeNode || shapeNode->GetShapeName() != vtkMRMLMarkupsShapeNode::Tube)
  {
    return;
  }
  vtkMRMLMarkupsFiducialNode * fiducialNode = vtkMRMLMarkupsFiducialNode::SafeDownCast(client->currentFiducialNode);
  if (!fiducialNode)
  {
    return;
  }
  
  vtkMRMLMarkupsDisplayNode * fiducialDisplayNode = fiducialNode->GetMarkupsDisplayNode();
  const int activeControlPoint = fiducialDisplayNode->GetActiveControlPoint();
  if (activeControlPoint > 1)
  {
    return;
  }
  // Move the control point to closest point on spline.
  client->logic->UpdateBoundaryControlPointPosition(activeControlPoint, fiducialNode, shapeNode);
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onTubePointEndInteraction(vtkObject *caller,
                                                                         unsigned long event, void *clientData, void *callData)
{
  qSlicerStenosisMeasurement3DModuleWidget * client = reinterpret_cast<qSlicerStenosisMeasurement3DModuleWidget*>(clientData);
  if (!client || !client->currentShapeNode)
  {
    return;
  }
  vtkMRMLMarkupsShapeNode * shapeNode = vtkMRMLMarkupsShapeNode::SafeDownCast(client->currentShapeNode);
  if (!shapeNode || shapeNode->GetShapeName() != vtkMRMLMarkupsShapeNode::Tube)
  {
    return;
  }
  vtkMRMLMarkupsFiducialNode * fiducialNode = vtkMRMLMarkupsFiducialNode::SafeDownCast(client->currentFiducialNode);
  if (!fiducialNode)
  {
    return;
  }
  
  // Move control points to closest point on spline.
  client->logic->UpdateBoundaryControlPointPosition(0, fiducialNode, shapeNode);
  client->logic->UpdateBoundaryControlPointPosition(1, fiducialNode, shapeNode);
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onFiducialNodeChanged(vtkMRMLNode * node)
{
  if (this->currentFiducialNode == node)
  {
    return;
  }
  if (this->currentFiducialNode)
  {
    // Disconnect the currently observed node.
    this->currentFiducialNode->RemoveObserver(this->fiducialObservation);
  }
  this->currentFiducialNode = node;
  if (this->currentFiducialNode)
  {
    // Connect the current node.
    this->currentFiducialNode->AddObserver(vtkMRMLMarkupsNode::PointEndInteractionEvent, this->fiducialObservation);
  }
  // Move control points to closest point on spline.
  if (this->currentShapeNode && this->currentFiducialNode)
  {
    vtkMRMLMarkupsFiducialNode * fiducialNode = vtkMRMLMarkupsFiducialNode::SafeDownCast(this->currentFiducialNode);
    vtkMRMLMarkupsShapeNode * shapeNode = vtkMRMLMarkupsShapeNode::SafeDownCast(this->currentShapeNode);
    this->logic->UpdateBoundaryControlPointPosition(0, fiducialNode, shapeNode);
    this->logic->UpdateBoundaryControlPointPosition(1, fiducialNode, shapeNode);
  }
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onShapeNodeChanged(vtkMRMLNode * node)
{
  if (this->currentShapeNode == node)
  {
    return;
  }
  if (this->currentShapeNode)
  {
    // Disconnect the currently observed node.
    this->currentShapeNode->RemoveObserver(this->tubeObservation);
  }
  this->currentShapeNode = node;
  if (currentShapeNode)
  {
    // Connect the current node.
    this->currentShapeNode->AddObserver(vtkMRMLMarkupsNode::PointEndInteractionEvent, this->tubeObservation);
  }
  // Move control points to closest point on spline.
  if (this->currentShapeNode && this->currentFiducialNode)
  {
    vtkMRMLMarkupsFiducialNode * fiducialNode = vtkMRMLMarkupsFiducialNode::SafeDownCast(this->currentFiducialNode);
    vtkMRMLMarkupsShapeNode * shapeNode = vtkMRMLMarkupsShapeNode::SafeDownCast(this->currentShapeNode);
    this->logic->UpdateBoundaryControlPointPosition(0, fiducialNode, shapeNode);
    this->logic->UpdateBoundaryControlPointPosition(1, fiducialNode, shapeNode);
  }
}

//----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onTableContentModified()
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);

  if (!d->currentTableNode || d->currentTableNode->GetNumberOfRows() == 0)
  {
    return;
  }
  // Let 0 in the range, don't do anything at 0.
  d->updateBoundaryPointsSpinBox->setRange(0, d->currentTableNode->GetNumberOfRows());
}

//----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onUpdateBoundary(int index)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);

  if (index == 0 || !d->currentTableNode)
  {
    return;
  }

  if (!d->currentTableNode || d->currentTableNode->GetNumberOfRows() == 0)
  {
    this->showStatusMessage(qSlicerStenosisMeasurement3DModuleWidget::tr("Invalid or empty table."), 5000);
    return;
  }
  vtkMRMLNode * tubeNodeMrml = d->inputShapeSelector->currentNode();
  vtkMRMLMarkupsShapeNode * tubeNode = vtkMRMLMarkupsShapeNode::SafeDownCast(tubeNodeMrml);
  vtkMRMLNode * boundaryNodeMrml = d->inputFiducialSelector->currentNode();
  vtkMRMLMarkupsFiducialNode * boundaryNode = vtkMRMLMarkupsFiducialNode::SafeDownCast(boundaryNodeMrml);

  vtkNew<vtkPolyData> spline;
  if (!tubeNode->GetTrimmedSplineWorld(spline))
  {
    this->showStatusMessage(qSlicerStenosisMeasurement3DModuleWidget::tr("The tube does not have a valid spline."), 5000);
    return;
  }
  if (!tubeNode || !boundaryNode || boundaryNode->GetNumberOfControlPoints() < 2)
  {
    this->showStatusMessage(qSlicerStenosisMeasurement3DModuleWidget::tr("Invalid tube or boundary node."), 5000);
    return;
  }

  const int startSplineId = d->currentTableNode->GetTable()->GetValueByName(index - 1, "StartSplineId").ToInt();
  const int endSplineId = d->currentTableNode->GetTable()->GetValueByName(index - 1, "EndSplineId").ToInt();
  double p1[3] = {0.0};
  double p2[3] = {0.0};
  spline->GetPoint(startSplineId, p1);
  spline->GetPoint(endSplineId, p2);
  boundaryNode->SetNthControlPointPositionWorld(0, p1);
  boundaryNode->SetNthControlPointPositionWorld(1, p2);
}

//-----------------------------------------------------------------------------
vtkSlicerStenosisMeasurement3DLogic::EnclosingType qSlicerStenosisMeasurement3DModuleWidget::getEnclosedSurface(
                                                                vtkMRMLMarkupsShapeNode * wallShapeNode,
                                                                vtkMRMLSegmentationNode * lumenSegmentationNode,
                                                                std::string segmentID, vtkPolyData * enclosedSurface
                                                                )
{
  if (!wallShapeNode || !lumenSegmentationNode || !enclosedSurface)
  {
    std::cerr << "Invalid input, cannot get the enclosed lumen surface." << std::endl;
    return vtkSlicerStenosisMeasurement3DLogic::EnclosingType_Last;
  }
  // Get wall polydata from shape markups node.
  vtkPolyData * wallClosedSurface = wallShapeNode->GetCappedTubeWorld();
  // Generate lumen polydata from lumen segment.
  vtkNew<vtkPolyData> inputLumenSurface;
  if (!lumenSegmentationNode->GetClosedSurfaceRepresentation(segmentID, inputLumenSurface))
  {
    if (!lumenSegmentationNode->CreateClosedSurfaceRepresentation())
    {
      std::cerr << "Cannot create closed surface from segmentation." << std::endl;
      return vtkSlicerStenosisMeasurement3DLogic::EnclosingType_Last;
    }
    if (!lumenSegmentationNode->GetClosedSurfaceRepresentation(segmentID, inputLumenSurface))
    {
      std::cerr << "Cannot get closed surface from segmentation." << std::endl;
      return vtkSlicerStenosisMeasurement3DLogic::EnclosingType_Last;
    }
  }
  
  vtkNew<vtkPolyData> inputLumenEnclosed;
  vtkSlicerStenosisMeasurement3DLogic::EnclosingType enclosingType =
                  this->logic->GetClosedSurfaceEnclosingType(wallClosedSurface, inputLumenSurface, inputLumenEnclosed);
  if (enclosingType == vtkSlicerStenosisMeasurement3DLogic::EnclosingType_Last)
  {
    return vtkSlicerStenosisMeasurement3DLogic::EnclosingType_Last; // Logging has been done.
  }
  if (enclosingType == vtkSlicerStenosisMeasurement3DLogic::Distinct)
  {
    std::cerr << "Input tube and input lumen do not intersect." << std::endl;
    return enclosingType;
  }
  
  if (!this->logic->UpdateClosedSurfaceMesh(inputLumenEnclosed, enclosedSurface))
  {
    std::cerr << "Error updating the clipped lumen; continuing with the raw clipped surface." << endl;
    enclosedSurface->Initialize();
    enclosedSurface->DeepCopy(inputLumenEnclosed);
  }
  return enclosingType;
}
