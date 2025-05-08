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
#include <QAction>
#include <QMenu>
#include <QStandardPaths>
#include <QDateTime>

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
#include <vtkMRMLStenosisMeasurement3DParameterNode.h>
#include <qSlicerExtensionsManagerModel.h>

//-----------------------------------------------------------------------------
/// \ingroup Slicer_QtModules_ExtensionTemplate
class qSlicerStenosisMeasurement3DModuleWidgetPrivate: public Ui_qSlicerStenosisMeasurement3DModuleWidget
{
public:
  qSlicerStenosisMeasurement3DModuleWidgetPrivate();
  void setLumenCache(vtkPolyData * clippedLumen);
  vtkSmartPointer<vtkMRMLStenosisMeasurement3DParameterNode> parameterNode = nullptr;

  vtkSmartPointer<vtkPolyData> lumenCache = nullptr;
  bool isLumenCacheValid = false;
};

//-----------------------------------------------------------------------------
// qSlicerStenosisMeasurement3DModuleWidgetPrivate methods

//-----------------------------------------------------------------------------
qSlicerStenosisMeasurement3DModuleWidgetPrivate::qSlicerStenosisMeasurement3DModuleWidgetPrivate()
{
  this->lumenCache = vtkSmartPointer<vtkPolyData>::New();
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidgetPrivate::setLumenCache(vtkPolyData * clippedLumen)
{
  this->lumenCache->Initialize();
  if (!clippedLumen) // Invalidate the cache by passing nullptr.
  {
    this->isLumenCacheValid = false;
    return;
  }
  this->lumenCache->DeepCopy(clippedLumen);
  this->isLumenCacheValid = true;
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
  QObject::connect(d->parameterSetSelector, SIGNAL(nodeAddedByUser(vtkMRMLNode*)),
                   this, SLOT(onParameterNodeAddedByUser(vtkMRMLNode*)));
  QObject::connect(d->parameterSetSelector, SIGNAL(currentNodeChanged(vtkMRMLNode*)),
                   this, SLOT(onParameterNodeChanged(vtkMRMLNode*)));

  // Put p1 and p2 ficucial points on the tube spline at nearest point when they are moved.
  this->fiducialObservation = vtkSmartPointer<vtkCallbackCommand>::New();
  this->fiducialObservation->SetClientData( reinterpret_cast<void *>(this) );
  this->fiducialObservation->SetCallback(qSlicerStenosisMeasurement3DModuleWidget::onFiducialPointEndInteraction);

  // Put p1 and p2 ficucial points on the tube spline at nearest point when the tube is updated.
  this->tubeObservation = vtkSmartPointer<vtkCallbackCommand>::New();
  this->tubeObservation->SetClientData( reinterpret_cast<void *>(this) );
  this->tubeObservation->SetCallback(qSlicerStenosisMeasurement3DModuleWidget::onTubePointEndInteraction);

  this->segmentationRepresentationObservation = vtkSmartPointer<vtkCallbackCommand>::New();
  this->segmentationRepresentationObservation->SetClientData( reinterpret_cast<void *>(this) );
  this->segmentationRepresentationObservation->SetCallback(qSlicerStenosisMeasurement3DModuleWidget::onSegmentationRepresentationModified);

  this->addMenu();

  // We won't check the structure of the table and assume it has been created in the module.
  const QString attributeName = QString(MODULE_TITLE) + QString(".Role");
  d->outputTableSelector->addAttribute("vtkMRMLTableNode", attributeName, MODULE_TITLE);
  d->parameterSetSelector->addAttribute("vtkMRMLStenosisMeasurement3DParameterNode", attributeName, MODULE_TITLE);
}

//-----------------------------------------------------------------------------

void qSlicerStenosisMeasurement3DModuleWidget::addMenu()
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);

  QMenu * applyButtonMenu = new QMenu(d->applyButton);
  d->applyButton->setMenu(applyButtonMenu);

  // Actions.
  QAction * actionClearCache = applyButtonMenu->addAction(qSlicerStenosisMeasurement3DModuleWidget::tr("Clear the enclosed lumen cache"));
  actionClearCache->setData(0);
  actionClearCache->setObjectName("ActionClearEnclosedLumenCache");

  applyButtonMenu->addSeparator();

  QAction * actionDumpVolumes = applyButtonMenu->addAction(qSlicerStenosisMeasurement3DModuleWidget::tr("Dump aggregate volumes to database"));
  actionDumpVolumes->setData(1);
  actionDumpVolumes->setObjectName("ActionDumpAggregateVolumesToDatabase");
  actionDumpVolumes->setToolTip(qSlicerStenosisMeasurement3DModuleWidget::tr("Attempt to save a database containing aggregate volumes of the study in your document directory."));
  
  QObject::connect(actionClearCache, SIGNAL(triggered()),
                   this, SLOT(clearLumenCache()));
  QObject::connect(actionDumpVolumes, SIGNAL(triggered()),
                   this, SLOT(dumpAggregateVolumes()));
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::enter()
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);

  if (this->logic)
  {
    this->logic->SetMRMLScene(this->mrmlScene());
  }
  if (d->parameterSetSelector->nodeCount() == 0)
  {
    vtkMRMLNode * nodeMrml = d->parameterSetSelector->addNode("vtkMRMLStenosisMeasurement3DParameterNode");
    d->parameterNode = vtkMRMLStenosisMeasurement3DParameterNode::SafeDownCast(nodeMrml);
  }
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onApply()
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  if (!d->parameterNode)
  {
    this->showStatusMessage(qSlicerStenosisMeasurement3DModuleWidget::tr("Invalid parameter node."), 5000);
    return;
  }
  vtkMRMLNode * shapeNode = d->parameterNode->GetInputShapeNode();
  vtkMRMLNode * fiducialNode = d->parameterNode->GetInputFiducialNode();
  vtkMRMLNode * segmentationNode = d->parameterNode->GetInputSegmentationNode();
  const std::string currentSegmentID = d->parameterNode->GetInputSegmentID();

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
  if (!this->getEnclosedSurface(shapeNodeReal, segmentationNodeReal, currentSegmentID, enclosedSurface, true))
  {
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
                            results, d->parameterNode ? d->parameterNode->GetName() : "Study",
                            d->parameterNode->GetOutputTableNode()))
  {
    this->showStatusMessage(qSlicerStenosisMeasurement3DModuleWidget::tr("Processing failed."), 5000);
    return;
  }
  // Finally show result.
  this->showResult(wallClosed, lumenClosed, results);
  // Optionally create models.
  this->createLesionModel(shapeNodeReal, enclosedSurface, fiducialNodeReal);

  // Cache the enclosed surface of the lumen if all is ok.
  d->setLumenCache(enclosedSurface);
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
  const double wallVolume = results->GetValue(1).ToDouble();
  const double lumenVolume = results->GetValue(2).ToDouble();
  const double lesionVolume =results->GetValue(3).ToDouble();
  const double degree =results->GetValue(4).ToDouble();
  const double length =results->GetValue(7).ToDouble();

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
   * in many scenarios.
   */
  QSignalBlocker blocker(d->inputSegmentSelector);
  d->inputSegmentSelector->setCurrentSegmentID("");
  if (d->parameterNode)
  {
    d->parameterNode->SetInputSegmentationNodeID(node ? node->GetID() : nullptr);
  }
  this->clearLumenCache();
  if (node)
  node->AddObserver(vtkSegmentation::RepresentationModified, this->segmentationRepresentationObservation);
}

//-----------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onSegmentIDChanged(QString segmentID)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  if (d->parameterNode)
  {
    d->parameterNode->SetInputSegmentID(segmentID.toStdString().c_str());
  }
  this->clearLumenCache();
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onLesionModelNodeChanged(vtkMRMLNode * node)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  if (d->parameterNode)
  {
    d->parameterNode->SetOutputLesionModelNodeID(node ? node->GetID() : nullptr);
  }
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onTableNodeChanged(vtkMRMLNode * node)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  if (!d->parameterNode)
  {
    return;
  }
  if (d->parameterNode->GetOutputTableNode())
  {
    qvtkDisconnect(d->parameterNode->GetOutputTableNode(), vtkCommand::ModifiedEvent, this , SLOT(onTableContentModified()));
  }
  d->updateBoundaryPointsSpinBox->setRange(0, 0);
  if (node)
  {
    vtkMRMLTableNode * tableNode = vtkMRMLTableNode::SafeDownCast(node);
    qvtkReconnect(tableNode, vtkCommand::ModifiedEvent, this , SLOT(onTableContentModified()));
    d->updateBoundaryPointsSpinBox->setRange(0, tableNode->GetNumberOfRows());
  }
  d->parameterNode->SetOutputTableNodeID(node ? node->GetID() : nullptr);
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onFiducialPointEndInteraction(vtkObject *caller,
                                                                             unsigned long event, void *clientData, void *callData)
{
  qSlicerStenosisMeasurement3DModuleWidget * client = reinterpret_cast<qSlicerStenosisMeasurement3DModuleWidget*>(clientData);
  if (!client || !client->d_ptr || !client->d_ptr->parameterNode)
  {
    return;
  }
  vtkMRMLMarkupsShapeNode * shapeNode = vtkMRMLMarkupsShapeNode::SafeDownCast(client->d_ptr->parameterNode->GetInputShapeNode());
  // React only if shape is a tube.
  if (!shapeNode || shapeNode->GetShapeName() != vtkMRMLMarkupsShapeNode::Tube)
  {
    return;
  }
  vtkMRMLMarkupsFiducialNode * fiducialNode = vtkMRMLMarkupsFiducialNode::SafeDownCast(client->d_ptr->parameterNode->GetInputFiducialNode());
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
  // Do not invalidate the cache.
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onTubePointEndInteraction(vtkObject *caller,
                                                                         unsigned long event, void *clientData, void *callData)
{
  qSlicerStenosisMeasurement3DModuleWidget * client = reinterpret_cast<qSlicerStenosisMeasurement3DModuleWidget*>(clientData);
  if (!client || !client->d_ptr || !client->d_ptr->parameterNode)
  {
    return;
  }
  vtkMRMLMarkupsShapeNode * shapeNode = vtkMRMLMarkupsShapeNode::SafeDownCast(client->d_ptr->parameterNode->GetInputShapeNode());
  if (!shapeNode || shapeNode->GetShapeName() != vtkMRMLMarkupsShapeNode::Tube)
  {
    return;
  }
  vtkMRMLMarkupsFiducialNode * fiducialNode = vtkMRMLMarkupsFiducialNode::SafeDownCast(client->d_ptr->parameterNode->GetInputFiducialNode());
  if (!fiducialNode)
  {
    return;
  }

  // Move control points to closest point on spline.
  client->logic->UpdateBoundaryControlPointPosition(0, fiducialNode, shapeNode);
  client->logic->UpdateBoundaryControlPointPosition(1, fiducialNode, shapeNode);
  // The cache is that of the enclosed lumen. If the tube is modified, we must update the enclosed part.
  client->d_ptr->setLumenCache(nullptr);
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onSegmentationRepresentationModified(vtkObject *caller,
                                                                unsigned long event, void *clientData, void *callData)
{
  qSlicerStenosisMeasurement3DModuleWidget * client = reinterpret_cast<qSlicerStenosisMeasurement3DModuleWidget*>(clientData);
  if (!client || !client->d_ptr || !client->d_ptr->parameterNode)
  {
    return;
  }
  const char * segmentID = client->d_ptr->parameterNode->GetInputSegmentID();
  const char * callValue =  static_cast<char*>(callData);
  if (std::string(callValue) == std::string(segmentID))
  {
    client->d_ptr->setLumenCache(nullptr);
  }
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onFiducialNodeChanged(vtkMRMLNode * node)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  if (!d->parameterNode || (d->parameterNode->GetInputFiducialNode() == node))
  {
    return;
  }
  if (d->parameterNode->GetInputFiducialNode())
  {
    // Disconnect the currently observed node.
    d->parameterNode->GetInputFiducialNode()->RemoveObserver(this->fiducialObservation);
  }
  d->parameterNode->SetInputFiducialNodeID(node ? node->GetID() : nullptr);
  vtkMRMLMarkupsFiducialNode * fiducialNode = vtkMRMLMarkupsFiducialNode::SafeDownCast(node);
  if (fiducialNode)
  {
    // Connect the current node.
    fiducialNode->AddObserver(vtkMRMLMarkupsNode::PointEndInteractionEvent, this->fiducialObservation);
  }
  // Move control points to closest point on spline.
  vtkMRMLMarkupsShapeNode * shapeNode = vtkMRMLMarkupsShapeNode::SafeDownCast(d->parameterNode->GetInputShapeNode());
  if (shapeNode && fiducialNode)
  {
    this->logic->UpdateBoundaryControlPointPosition(0, fiducialNode, shapeNode);
    this->logic->UpdateBoundaryControlPointPosition(1, fiducialNode, shapeNode);
  }
  if (d->parameterNode)
  {
    d->parameterNode->SetInputFiducialNodeID(node ? node->GetID() : nullptr);
  }
  this->clearLumenCache();
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onShapeNodeChanged(vtkMRMLNode * node)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  if (!d->parameterNode || (d->parameterNode->GetInputShapeNode() == node))
  {
    return;
  }
  if (d->parameterNode->GetInputShapeNode())
  {
    // Disconnect the currently observed node.
    d->parameterNode->GetInputShapeNode()->RemoveObserver(this->tubeObservation);
  }
  d->parameterNode->SetInputShapeNodeID(node ? node->GetID() : nullptr);
  vtkMRMLMarkupsShapeNode * shapeNode = vtkMRMLMarkupsShapeNode::SafeDownCast(node);
  if (shapeNode)
  {
    // Connect the current node.
    shapeNode->AddObserver(vtkMRMLMarkupsNode::PointEndInteractionEvent, this->tubeObservation);
  }
  // Move control points to closest point on spline.
  vtkMRMLMarkupsFiducialNode * fiducialNode = vtkMRMLMarkupsFiducialNode::SafeDownCast(d->parameterNode->GetInputFiducialNode());
  if (shapeNode && fiducialNode)
  {
    this->logic->UpdateBoundaryControlPointPosition(0, fiducialNode, shapeNode);
    this->logic->UpdateBoundaryControlPointPosition(1, fiducialNode, shapeNode);
  }
  if (d->parameterNode)
  {
    d->parameterNode->SetInputShapeNodeID(node ? node->GetID() : nullptr);
  }
  this->clearLumenCache();
}

//----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onTableContentModified()
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  if (!d->parameterNode)
  {
    return;
  }
  vtkMRMLTableNode * currentTableNode = d->parameterNode->GetOutputTableNode();
  if (!currentTableNode || currentTableNode->GetNumberOfRows() == 0)
  {
    return;
  }
  // Let 0 in the range, don't do anything at 0.
  d->updateBoundaryPointsSpinBox->setRange(0, currentTableNode->GetNumberOfRows());
}

//----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onUpdateBoundary(int index)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  if (!d->parameterNode)
  {
    return;
  }
  d->parameterNode->SetOutputTableRowId(index); // Always.
  vtkMRMLTableNode * currentTableNode = d->parameterNode->GetOutputTableNode();
  if (index == 0 || !currentTableNode)
  {
    return;
  }
  if (!currentTableNode || currentTableNode->GetNumberOfRows() == 0)
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

  const int startSplineId = currentTableNode->GetTable()->GetValueByName(index - 1, "StartSplineId").ToInt();
  const int endSplineId = currentTableNode->GetTable()->GetValueByName(index - 1, "EndSplineId").ToInt();
  double p1[3] = {0.0};
  double p2[3] = {0.0};
  spline->GetPoint(startSplineId, p1);
  spline->GetPoint(endSplineId, p2);
  boundaryNode->SetNthControlPointPositionWorld(0, p1);
  boundaryNode->SetNthControlPointPositionWorld(1, p2);
}

//-----------------------------------------------------------------------------
vtkSlicerStenosisMeasurement3DLogic::EnclosingType
qSlicerStenosisMeasurement3DModuleWidget::createEnclosedSurface(vtkMRMLMarkupsShapeNode * wallShapeNode,
                                                                vtkMRMLSegmentationNode * lumenSegmentationNode,
                                                                std::string segmentID, vtkPolyData * enclosedSurface,
                                                                bool updateMesh)
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
  enclosedSurface->Initialize();
  enclosedSurface->DeepCopy(inputLumenEnclosed);

  if (updateMesh)
  {
    // enclosedSurface is Initialize()d there and is not modified on abort.
    if (!this->logic->UpdateClosedSurfaceMesh(inputLumenEnclosed, enclosedSurface))
    {
      std::cerr << "Error updating the clipped lumen; continuing with the raw clipped surface." << endl;
    }
  }
  return enclosingType;
}

//-----------------------------------------------------------------------------
bool qSlicerStenosisMeasurement3DModuleWidget::getEnclosedSurface(vtkMRMLMarkupsShapeNode * wallShapeNode,
                                                                  vtkMRMLSegmentationNode * lumenSegmentationNode, std::string segmentID,
                                                                  vtkPolyData * enclosedSurface, bool updateMesh)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  if (d->isLumenCacheValid)
  {
    enclosedSurface->DeepCopy(d->lumenCache);
    return true;
  }
  else
  {
    vtkSlicerStenosisMeasurement3DLogic::EnclosingType enclosingType = this->createEnclosedSurface(
              wallShapeNode, lumenSegmentationNode, segmentID, enclosedSurface, updateMesh);
    if (enclosingType == vtkSlicerStenosisMeasurement3DLogic::EnclosingType_Last)
    {
      this->showStatusMessage(qSlicerStenosisMeasurement3DModuleWidget::tr("Error getting the enclosed lumen."), 5000);
      return false;
    }
    if (enclosingType == vtkSlicerStenosisMeasurement3DLogic::Distinct)
    {
      this->showStatusMessage(qSlicerStenosisMeasurement3DModuleWidget::tr("Input tube and input lumen do not intersect."), 5000);
      return false;
    }
    // The caller must cache the enclosed surface.
  }
  return true;
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::setDefaultParameters(vtkMRMLNode * node)
{
  if (!node)
  {
    return;
  }
  vtkMRMLStenosisMeasurement3DParameterNode * downcastNode = vtkMRMLStenosisMeasurement3DParameterNode::SafeDownCast(node);
  if (!downcastNode)
  {
    return;
  }
  downcastNode->SetOutputTableRowId(0);
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onParameterNodeAddedByUser(vtkMRMLNode * node)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  if (!node)
  {
    return;
  }
  vtkMRMLStenosisMeasurement3DParameterNode * downcastNode = vtkMRMLStenosisMeasurement3DParameterNode::SafeDownCast(node);
  if (!downcastNode)
  {
    return;
  }
  d->parameterNode = downcastNode;
  this->setDefaultParameters(d->parameterNode);
  this->clearLumenCache();
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::updateGuiFromParameterNode()
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  if (!d->parameterNode)
  {
    return;
  }

  d->inputShapeSelector->setCurrentNode(d->parameterNode->GetInputShapeNode());
  QSignalBlocker blocker(d->inputSegmentSelector);
  d->inputSegmentSelector->setCurrentNode(d->parameterNode->GetInputSegmentationNode());
  d->inputSegmentSelector->setCurrentSegmentID(d->parameterNode->GetInputSegmentID());
  d->inputFiducialSelector->setCurrentNode(d->parameterNode->GetInputFiducialNode());
  d->lesionModelSelector->setCurrentNode(d->parameterNode->GetOutputLesionModelNode());
  d->outputTableSelector->setCurrentNode(d->parameterNode->GetOutputTableNode());
  const int tableRowId = d->parameterNode->GetOutputTableRowId();
  d->updateBoundaryPointsSpinBox->setValue(tableRowId >= 0 ? tableRowId : 0);

  // Clear results.
  d->wallResultLabel->clear();
  d->lumenResultLabel->clear();
  d->lesionResultLabel->clear();
  d->stenosisResultLabel->clear();
  d->lengthResultLabel->clear();
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onParameterNodeChanged(vtkMRMLNode * node)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  vtkMRMLStenosisMeasurement3DParameterNode * downcastNode = vtkMRMLStenosisMeasurement3DParameterNode::SafeDownCast(node);
  if (!downcastNode)
  {
    return;
  }
  d->parameterNode = downcastNode;

  this->updateGuiFromParameterNode();
  this->clearLumenCache();
}

//-----------------------------------------------------------------------------
bool qSlicerStenosisMeasurement3DModuleWidget::setEditedNode(vtkMRMLNode* node,
                                                             QString role /* = QString()*/,
                                                             QString context /* = QString()*/)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  Q_UNUSED(role);
  Q_UNUSED(context);

  if (vtkMRMLStenosisMeasurement3DParameterNode::SafeDownCast(node))
  {
    d->parameterSetSelector->setCurrentNode(node);
    return true;
  }
  return false;
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::clearLumenCache()
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  d->setLumenCache(nullptr);
}

void qSlicerStenosisMeasurement3DModuleWidget::dumpAggregateVolumes()
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  if (!d->parameterNode)
  {
    this->showStatusMessage(qSlicerStenosisMeasurement3DModuleWidget::tr("Parameter node is invalid."), 5000);
    return;
  }
  QString documentPath = QStandardPaths::standardLocations(QStandardPaths::DocumentsLocation).at(0);
  QString timestamp = QDateTime::currentDateTime().toString("yyyyMMdd-hhmmss");
  QString dbName = d->parameterNode->GetName() + QString("-") + timestamp + QString(".db");
  QString dbPath = documentPath + QString("/") + dbName;
  vtkMRMLMarkupsShapeNode * wallShapeNode = vtkMRMLMarkupsShapeNode::SafeDownCast(d->parameterNode->GetInputShapeNode());
  vtkMRMLSegmentationNode * segmentationNode = vtkMRMLSegmentationNode::SafeDownCast(d->parameterNode->GetInputSegmentationNode());
  std::string segmentID = d->parameterNode->GetInputSegmentID();
  vtkNew<vtkPolyData> enclosedSurface;
  if (!this->getEnclosedSurface(wallShapeNode, segmentationNode, segmentID, enclosedSurface, true))
  {
    return;
  }

  // Cache the enclosed surface of the lumen if all is ok.
  d->setLumenCache(enclosedSurface);

  this->showStatusMessage(qSlicerStenosisMeasurement3DModuleWidget::tr("Processing, this can be long running, please wait..."));
  if (!this->logic->DumpAggregateVolumes(wallShapeNode, enclosedSurface, dbPath.toStdString()))
  {
    this->showStatusMessage(qSlicerStenosisMeasurement3DModuleWidget::tr("Error dumping aggregate volumes to database."), 10000);
    return;
  }
  QString successMessage = dbName + QString(qSlicerStenosisMeasurement3DModuleWidget::tr(" is saved in your document directory."));
  this->showStatusMessage(successMessage.toStdString().c_str(), 5000);
}
