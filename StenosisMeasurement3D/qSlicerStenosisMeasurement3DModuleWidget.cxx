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

#include <vtkMRMLMarkupsFiducialNode.h>
#include <vtkMRMLMarkupsDisplayNode.h>
#include <vtkMRMLMarkupsShapeNode.h>
#include <vtkMRMLModelNode.h>
#include <vtkMassProperties.h>
#include <vtkMRMLMeasurementLength.h>
#include <vtkMRMLMeasurementVolume.h>
#include <vtkMRMLStaticMeasurement.h>
#include <qSlicerExtensionsManagerModel.h>

//-----------------------------------------------------------------------------
/// \ingroup Slicer_QtModules_ExtensionTemplate
class qSlicerStenosisMeasurement3DModuleWidgetPrivate: public Ui_qSlicerStenosisMeasurement3DModuleWidget
{
public:
  qSlicerStenosisMeasurement3DModuleWidgetPrivate();
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
  
  d->resultCollapsibleButton->setCollapsed(true);
  d->modelCollapsibleButton->setCollapsed(true);
  
  QObject::connect(d->applyButton, SIGNAL(clicked()),
                   this, SLOT(onApply()));
  QObject::connect(d->inputShapeSelector, SIGNAL(currentNodeChanged(vtkMRMLNode*)),
                   this, SLOT(onShapeNodeChanged(vtkMRMLNode*)));
  QObject::connect(d->inputFiducialSelector, SIGNAL(currentNodeChanged(vtkMRMLNode*)),
                   this, SLOT(onFiducialNodeChanged(vtkMRMLNode*)));
  QObject::connect(d->inputFiducialSelector, SIGNAL(nodeAddedByUser(vtkMRMLNode*)),
                   this, SLOT(onFiducialNodeChanged(vtkMRMLNode*)));
  
  // Put p1 and p2 ficucial points on the tube spline at nearest point when they are moved.
  this->fiducialObservation = vtkSmartPointer<vtkCallbackCommand>::New();
  this->fiducialObservation->SetClientData( reinterpret_cast<void *>(this) );
  this->fiducialObservation->SetCallback(qSlicerStenosisMeasurement3DModuleWidget::onFiducialPointEndInteraction);
  
  // Put p1 and p2 ficucial points on the tube spline at nearest point when the tube is updated.
  this->tubeObservation = vtkSmartPointer<vtkCallbackCommand>::New();
  this->tubeObservation->SetClientData( reinterpret_cast<void *>(this) );
  this->tubeObservation->SetCallback(qSlicerStenosisMeasurement3DModuleWidget::onTubePointEndInteraction);
  
  // Check and install ExtraMarkups extension for Shape::Tube node.
  this->installExtensionFromServer("ExtraMarkups");
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
    this->showStatusMessage("Insufficient input.", 5000);
    return;
  }
  vtkMRMLMarkupsShapeNode * shapeNodeReal = vtkMRMLMarkupsShapeNode::SafeDownCast(shapeNode);
  if (!shapeNodeReal || shapeNodeReal->GetShapeName() != vtkMRMLMarkupsShapeNode::Tube)
  {
    this->showStatusMessage("Bad shape node.", 5000);
    return;
  }
  vtkMRMLMarkupsFiducialNode * fiducialNodeReal = vtkMRMLMarkupsFiducialNode::SafeDownCast(fiducialNode);
  if (!fiducialNodeReal)
  {
    this->showStatusMessage("Inconsistent fiducial input.", 5000);
    return;
  }
  if (fiducialNodeReal->GetNumberOfControlPoints() < 2)
  {
    this->showStatusMessage("Two fiducial input points are mandatory.", 5000);
    return;
  }
  vtkMRMLSegmentationNode * segmentationNodeReal = vtkMRMLSegmentationNode::SafeDownCast(segmentationNode);
  if (!segmentationNodeReal)
  {
    this->showStatusMessage("Inconsistent segmentation input.", 5000);
    return;
  }
  
  // Create output data.
  vtkSmartPointer<vtkPolyData> wallOpen = vtkSmartPointer<vtkPolyData>::New();
  vtkSmartPointer<vtkPolyData> lumenOpen = vtkSmartPointer<vtkPolyData>::New();
  vtkSmartPointer<vtkPolyData> wallClosed = vtkSmartPointer<vtkPolyData>::New();
  vtkSmartPointer<vtkPolyData> lumenClosed = vtkSmartPointer<vtkPolyData>::New();
  // Do the job.
  double length = this->logic->Process(shapeNodeReal, segmentationNodeReal, currentSegmentID,
                                     fiducialNodeReal, wallOpen, lumenOpen, wallClosed, lumenClosed);
  if (length < 0.0)
  {
    this->showStatusMessage("Processing failed.", 5000);
    return;
  }
  // Finally show result.
  this->showResult(wallClosed, lumenClosed, length);
  // Optionally create models.
  this->createModels(wallOpen, lumenOpen);
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::showResult(vtkPolyData * wall, vtkPolyData * lumen,
                                                          double length)
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
  const double wallVolume = wallMassProperties->GetVolume();
  const double lumenVolume = lumenMassProperties->GetVolume();
  const double lesionVolume = wallVolume - lumenVolume;
  
  // Use the facilities of MRML measurement classes.
  auto show = [&] (const double& volume, QLabel * widget)
  {
    vtkNew<vtkMRMLMeasurementVolume> volumeMeasurement;
    volumeMeasurement->SetValue(volume);
    volumeMeasurement->SetDisplayCoefficient(0.001);
    volumeMeasurement->SetPrintFormat("%-#4.4g %s");
    volumeMeasurement->Modified();
    
    widget->setText(volumeMeasurement->GetValueWithUnitsAsPrintableString().c_str());
    std::string tip = std::to_string(volume) + std::string(" mm3");
    widget->setToolTip(tip.c_str());
  };
  
  d->resultCollapsibleButton->setCollapsed(false);
  show(wallVolume, d->wallResultLabel);
  show(lumenVolume, d->lumenResultLabel);
  show(lesionVolume, d->lesionResultLabel);
  
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
  
  std::string lengthMeasured = "#ERR";
  if (length > 0)
  {
    vtkNew<vtkMRMLMeasurementLength> lengthMeasurement;
    lengthMeasurement->SetValue(length);
    lengthMeasurement->SetPrintFormat("%-#4.4g %s");
    lengthMeasurement->SetUnits(" mm");
    lengthMeasurement->Modified();
    lengthMeasured = lengthMeasurement->GetValueWithUnitsAsPrintableString();
    
    std::string tip = std::to_string(length) + std::string(" mm");
    d->lengthResultLabel->setToolTip(tip.c_str());
  }
  d->lengthResultLabel->setText(lengthMeasured.c_str());
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::createModels(vtkPolyData * wall, vtkPolyData * lumen)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  
  auto createModel = [&](vtkPolyData * polydata, vtkMRMLNode * modelNodeBase)
  {
    if (polydata && modelNodeBase)
    {
      vtkMRMLModelNode * modelNodeReal = vtkMRMLModelNode::SafeDownCast(modelNodeBase);
      if (modelNodeReal)
      {
        modelNodeReal->SetAndObservePolyData(polydata);
        modelNodeReal->Modified();
        if (!modelNodeReal->GetDisplayNode())
        {
          // If model is freshly created from selector.
          modelNodeReal->CreateDefaultDisplayNodes();
        }
      }
    }
  };
  
  createModel(wall, d->wallModelSelector->currentNode());
  createModel(lumen, d->lumenModelSelector->currentNode());
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


//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::installExtensionFromServer(const QString& extensionName)
{
  bool developerModeEnabled = QSettings().value("Developer/DeveloperMode").toBool();
  
  qSlicerExtensionsManagerModel * em = qSlicerCoreApplication::application()->extensionsManagerModel();
  if (!em || em->isExtensionInstalled(extensionName))
  {
    return;
  }
  if (developerModeEnabled)
  {
    QString message("Aborting installation of ");
    message += extensionName;
    message += QString(" in developer mode.");
    this->showStatusMessage(message, 5000);
    std::cout << message.toStdString() << std::endl;
    return;
  }
  bool result = em->updateExtensionsMetadataFromServer(true, true);
  if (!result)
  {
    QString message("Could not update metadata from server to install ");
    message += extensionName + QString(".");
    this->showStatusMessage(message, 5000);
    std::cout << message.toStdString() << std::endl;
    return;
  }
  QString message = extensionName + QString(" must be installed. Do you want to install it now ?");
  QMessageBox::StandardButton reply = QMessageBox::question(nullptr, "Install extension ?",message);
  if (reply != QMessageBox::StandardButton::Yes)
  {
    message = QString("This module cannot be used without ") + extensionName + QString(".");
    this->showStatusMessage(message, 5000);
    std::cout << message.toStdString() << std::endl;
    return;
  }
  if (!em->downloadAndInstallExtensionByName(extensionName, true, true))
  {
    message = QString("Failed to install ") + extensionName + QString(" extension.");
    this->showStatusMessage(message, 5000);
    std::cout << message.toStdString() << std::endl;
    return;
  }
  message = extensionName + QString(" has been installed from server.");
  message += QString("\n\nSlicer must be restarted. Do you want to restart now ?");
  reply = QMessageBox::question(nullptr, "Restart slicer ?",message);
  if (reply == QMessageBox::StandardButton::Yes)
  {
    qSlicerCoreApplication::application()->restart();
  }
}
