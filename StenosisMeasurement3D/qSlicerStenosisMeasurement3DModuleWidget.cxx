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
#include "vtkMRMLStenosisMeasurement3DParameterNode.h"
#include <qSlicerMainWindow.h>
#include <qSlicerCoreApplication.h>
#include <qstatusbar.h>
#include <QSettings>
#include <QMessageBox>

#include <vtkMRMLMarkupsFiducialNode.h>
#include <vtkMRMLMarkupsDisplayNode.h>
#include <vtkMRMLMarkupsShapeNode.h>
#include <vtkMRMLModelNode.h>
#include <vtkMRMLTableNode.h>
#include <vtkMRMLMeasurementLength.h>
#include <vtkMRMLMeasurementVolume.h>
#include <vtkMRMLStaticMeasurement.h>
#include <vtkVariantArray.h>
#include <qSlicerExtensionsManagerModel.h>

//-----------------------------------------------------------------------------
/// \ingroup Slicer_QtModules_ExtensionTemplate
class qSlicerStenosisMeasurement3DModuleWidgetPrivate: public Ui_qSlicerStenosisMeasurement3DModuleWidget
{
public:
  qSlicerStenosisMeasurement3DModuleWidgetPrivate();
  void EnableWorkspace();
  
  // It is observed to update the logic only, not to update the widgets.
  vtkWeakPointer<vtkMRMLStenosisMeasurement3DParameterNode> ParameterNode;
};

//-----------------------------------------------------------------------------
// qSlicerStenosisMeasurement3DModuleWidgetPrivate methods

//-----------------------------------------------------------------------------
qSlicerStenosisMeasurement3DModuleWidgetPrivate::qSlicerStenosisMeasurement3DModuleWidgetPrivate()
{
}

void qSlicerStenosisMeasurement3DModuleWidgetPrivate::EnableWorkspace()
{
  bool enabled = this->ParameterNode != nullptr;
  this->inputsCollapsibleButton->setEnabled(enabled);
  this->outputCollapsibleButton->setEnabled(enabled);
  this->applyButton->setEnabled(enabled);
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
  d->EnableWorkspace();
  
  d->outputCollapsibleButton->setCollapsed(true);
  
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
  QObject::connect(d->wallModelSelector, SIGNAL(currentNodeChanged(vtkMRMLNode*)),
                   this, SLOT(onWallModelNodeChanged(vtkMRMLNode*)));
  QObject::connect(d->lumenModelSelector, SIGNAL(currentNodeChanged(vtkMRMLNode*)),
                   this, SLOT(onLumenModelNodeChanged(vtkMRMLNode*)));
  QObject::connect(d->outputTableSelector, SIGNAL(currentNodeChanged(vtkMRMLNode*)),
                   this, SLOT(onTableNodeChanged(vtkMRMLNode*)));

  QObject::connect(d->parameterSetSelector, SIGNAL(currentNodeChanged(vtkMRMLNode*)),
          this, SLOT(setParameterNode(vtkMRMLNode*)));

  // We won't check the structure of the table and assume it has been created in the module.
  const QString attributeName = QString(MODULE_TITLE) + QString(".Role");
  d->outputTableSelector->addAttribute("vtkMRMLTableNode", attributeName, "OutputTable");
  d->parameterSetSelector->addAttribute("vtkMRMLStenosisMeasurement3DParameterNode", attributeName, MODULE_TITLE);
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::enter()
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);

  if (d->parameterSetSelector->nodeCount() == 0)
  {
    d->parameterSetSelector->addNode("vtkMRMLStenosisMeasurement3DParameterNode");
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
  
  // Create output data.
  vtkSmartPointer<vtkPolyData> wallOpen = vtkSmartPointer<vtkPolyData>::New();
  vtkSmartPointer<vtkPolyData> lumenOpen = vtkSmartPointer<vtkPolyData>::New();
  vtkSmartPointer<vtkPolyData> wallClosed = vtkSmartPointer<vtkPolyData>::New();
  vtkSmartPointer<vtkPolyData> lumenClosed = vtkSmartPointer<vtkPolyData>::New();
  d->ParameterNode->SetOutputWallOpenPolyData(wallOpen);
  d->ParameterNode->SetOutputLumenOpenPolyData(lumenOpen);
  d->ParameterNode->SetOutputWallClosedPolyData(wallClosed);
  d->ParameterNode->SetOutputLumenClosedPolyData(lumenClosed);
  // Do the job.
  // ParameterNode is set in logic by onParameterNodeModified().
  vtkNew<vtkVariantArray> results;
  if (!this->logic->Process(results))
  {
    this->showStatusMessage(qSlicerStenosisMeasurement3DModuleWidget::tr("Processing failed."), 5000);
    return;
  }
  // Finally show result. An optional table is updated at the same time.
  this->showResult(results);
  // Optionally create models.
  this->createModels(wallOpen, lumenOpen);
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::showResult(vtkVariantArray * results)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  if (!results)
  {
    this->showStatusMessage(qSlicerStenosisMeasurement3DModuleWidget::tr("Unexpected NULL result array."), 5000);
    return;
  }
  // Get the volumes.
  const double wallVolume = results->GetValue(1).ToDouble();
  const double lumenVolume = results->GetValue(2).ToDouble();
  const double lesionVolume =results->GetValue(3).ToDouble();
  const double degree =results->GetValue(4).ToDouble();
  const double length =results->GetValue(5).ToDouble();

  // Use the facilities of MRML measurement classes to format the volumes.
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
  
  d->outputCollapsibleButton->setCollapsed(false);
  show(wallVolume, d->wallResultLabel);
  show(lumenVolume, d->lumenResultLabel);
  show(lesionVolume, d->lesionResultLabel);
  
  // Show the stenosis degree.
  std::string stenosisDegree = "#ERR";
  if (wallVolume > 0)
  {
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
void qSlicerStenosisMeasurement3DModuleWidget::onFiducialNodeChanged(vtkMRMLNode * node)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  if (d->ParameterNode)
  {
    d->ParameterNode->SetInputFiducialNodeID(node ? node->GetID() : nullptr);
  }
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onShapeNodeChanged(vtkMRMLNode * node)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  if (d->ParameterNode)
  {
    d->ParameterNode->SetInputShapeNodeID(node ? node->GetID() : nullptr);
  }
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onSegmentationNodeChanged(vtkMRMLNode * node)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  if (d->ParameterNode)
  {
    d->ParameterNode->SetInputSegmentationNodeID(node ? node->GetID() : nullptr);
  }
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
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  if (d->ParameterNode)
  {
    d->ParameterNode->SetInputSegmentID(segmentID.toStdString().c_str());
  }
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onWallModelNodeChanged(vtkMRMLNode * node)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  if (d->ParameterNode)
  {
    d->ParameterNode->SetOutputWallModelNodeID(node ? node->GetID() : nullptr);
  }
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onLumenModelNodeChanged(vtkMRMLNode * node)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  if (d->ParameterNode)
  {
    d->ParameterNode->SetOutputLumenModelNodeID(node ? node->GetID() : nullptr);
  }
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onTableNodeChanged(vtkMRMLNode * node)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  if (d->ParameterNode)
  {
    d->ParameterNode->SetOutputTableNodeID(node ? node->GetID() : nullptr);
  }
}

//-----------------------------------------------------------
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

//------------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::setParameterNode(vtkMRMLNode* node)
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  vtkMRMLStenosisMeasurement3DParameterNode* parameterNode = vtkMRMLStenosisMeasurement3DParameterNode::SafeDownCast(node);
  qvtkReconnect(d->ParameterNode, parameterNode, vtkCommand::ModifiedEvent, this, SLOT(onParameterNodeModified()));
  d->ParameterNode = parameterNode;
  d->EnableWorkspace();
  this->updateWidgetFromMRML();
  this->onParameterNodeModified();
}

//----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::updateWidgetFromMRML()
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  if (!d->ParameterNode)
  {
    // Reset all UI widgets.
    d->inputShapeSelector->setCurrentNode(nullptr);
    d->inputFiducialSelector->setCurrentNode(nullptr);
    d->inputSegmentSelector->setCurrentNode(nullptr);
    d->inputSegmentSelector->setCurrentSegmentID(nullptr);
    d->wallModelSelector->setCurrentNode(nullptr);
    d->lumenModelSelector->setCurrentNode(nullptr);
    d->outputTableSelector->setCurrentNode(nullptr);
    d->wallResultLabel->clear();
    d->lumenResultLabel->clear();
    d->lesionResultLabel->clear();
    d->stenosisResultLabel->clear();
    d->lengthResultLabel->clear();
    return;
  }
  
  /*
   * The parameter node will get in turn updated.
   * Since we do not update widgets when it changes because it's private,
   * we will not end in infinite recursion.
   * 
   */
  d->inputShapeSelector->setCurrentNode(d->ParameterNode->GetInputShapeNode());
  d->inputFiducialSelector->setCurrentNode(d->ParameterNode->GetInputFiducialNode());
  /*
   * The segmentation selector is special. The segmentID must be explicitly
   * cleared if the segmentation is null.
   */
  {
    QSignalBlocker blocker(d->inputSegmentSelector);
    d->inputSegmentSelector->setCurrentNode(d->ParameterNode->GetInputSegmentationNode());
    d->inputSegmentSelector->setCurrentSegmentID(d->ParameterNode->GetInputSegmentationNode()
                                      ? QString(d->ParameterNode->GetInputSegmentID())
                                      : nullptr);
  }
  
  d->wallModelSelector->setCurrentNode(d->ParameterNode->GetOutputWallModelNode());
  d->lumenModelSelector->setCurrentNode(d->ParameterNode->GetOutputLumenModelNode());
  d->outputTableSelector->setCurrentNode(d->ParameterNode->GetOutputTableNode());
  
  /*
   * Despite the MRML table, recompute is unavoidable since it stores
   * results from one or many parameter sets.
  */
  d->wallResultLabel->clear();
  d->lumenResultLabel->clear();
  d->lesionResultLabel->clear();
  d->stenosisResultLabel->clear();
  d->lengthResultLabel->clear();
}

//----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModuleWidget::onParameterNodeModified()
{
  Q_D(qSlicerStenosisMeasurement3DModuleWidget);
  if (this->logic)
  {
    this->logic->SetParameterNode(d->ParameterNode);
  }
}
