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
#include "qSlicerBranchClipperModuleWidget.h"
#include "ui_qSlicerBranchClipperModuleWidget.h"
#include <vtkSlicerBranchClipperLogic.h>

#include <vtkMRMLModelNode.h>
#include <vtkMRMLSegmentationNode.h>
#include <vtkSegmentationConverter.h>
#include <vtkMRMLSubjectHierarchyNode.h>
#include <vtkMRMLScene.h>
#include <vtkMRMLDisplayNode.h>
#include <vtkSlicerSegmentationsModuleLogic.h>
#include <vtkPolyDataCollection.h>
#include <vtkTimerLog.h>

#include <qSlicerMainWindow.h>
#include <qSlicerCoreApplication.h>
#include <qstatusbar.h>

//-----------------------------------------------------------------------------
/// \ingroup Slicer_QtModules_ExtensionTemplate
class qSlicerBranchClipperModuleWidgetPrivate: public Ui_qSlicerBranchClipperModuleWidget
{
public:
  qSlicerBranchClipperModuleWidgetPrivate();
};

//-----------------------------------------------------------------------------
// qSlicerBranchClipperModuleWidgetPrivate methods

//-----------------------------------------------------------------------------
qSlicerBranchClipperModuleWidgetPrivate::qSlicerBranchClipperModuleWidgetPrivate()
{
}

//-----------------------------------------------------------------------------
// qSlicerBranchClipperModuleWidget methods

//-----------------------------------------------------------------------------
qSlicerBranchClipperModuleWidget::qSlicerBranchClipperModuleWidget(QWidget* _parent)
  : Superclass( _parent )
  , d_ptr( new qSlicerBranchClipperModuleWidgetPrivate )
{
}

//-----------------------------------------------------------------------------
qSlicerBranchClipperModuleWidget::~qSlicerBranchClipperModuleWidget()
{
}

//-----------------------------------------------------------------------------
void qSlicerBranchClipperModuleWidget::setup()
{
  Q_D(qSlicerBranchClipperModuleWidget);
  d->setupUi(this);
  this->Superclass::setup();
  
  QObject::connect(d->applyButton, SIGNAL(clicked()),
                   this, SLOT(onApply()));
  QObject::connect(d->surfaceSelector, SIGNAL(currentNodeChanged(vtkMRMLNode*)),
                   this, SLOT(onSurfaceChanged(vtkMRMLNode*)));

  d->segmentSelector->setVisible(false);
  /*
   * Seed with a constant for predictable random table and colours.
   * Not using vtkMRMLColorTableNode because we may have more than 256 branches
   * or bifurcation profiles.
  */
  vtkMath::RandomSeed(7);
}

//-----------------------------------------------------------------------------
void qSlicerBranchClipperModuleWidget::onSurfaceChanged(vtkMRMLNode* surface)
{
  Q_D(qSlicerBranchClipperModuleWidget);
  // Will be set to None if surface is a model.
  d->segmentSelector->setCurrentNode(surface);
  vtkMRMLSegmentationNode * segmentation = vtkMRMLSegmentationNode::SafeDownCast(surface);
  d->segmentSelector->setVisible(segmentation != nullptr);
}

//-----------------------------------------------------------------------------
void qSlicerBranchClipperModuleWidget::onApply()
{
  Q_D(qSlicerBranchClipperModuleWidget);
  // Work on copies.
  vtkNew<vtkPolyData> centerlines;
  vtkNew<vtkPolyData> surface;
  
  vtkMRMLModelNode * centerlineModel = vtkMRMLModelNode::SafeDownCast( d->inputCenterlineSelector->currentNode());
  if (centerlineModel == nullptr)
  {
    this->showStatusMessage(qSlicerBranchClipperModuleWidget::tr("No centerline selected."), 5000);
    return;
  }
  centerlines->DeepCopy(centerlineModel->GetPolyData());
  
  vtkMRMLSegmentationNode * inputSegmentationNode = nullptr;
  vtkMRMLModelNode * inputModelNode = nullptr;
  vtkMRMLNode * surfaceNode = d->surfaceSelector->currentNode();
  if (surfaceNode == nullptr)
  {
    this->showStatusMessage(qSlicerBranchClipperModuleWidget::tr("No surface selected."), 5000);
    return;
  }
  if ((d->bifurcationProfilesToolButton->isChecked() == false)
    && (d->branchSegmentsToolButton->isChecked() == false))
  {
    this->showStatusMessage(qSlicerBranchClipperModuleWidget::tr("No output selected."), 5000);
    return;
  }
  // Control segment and model names.
  std::string inputSegmentName;
  std::string inputModelName;
  std::string inputSegmentID;
  vtkMRMLSubjectHierarchyNode * shNode = mrmlScene()->GetSubjectHierarchyNode();
  vtkIdType shBranchesModelFolderId = 0;
  
  if (surfaceNode && surfaceNode->IsA("vtkMRMLSegmentationNode")
    && (d->branchSegmentsToolButton->isChecked() || d->bifurcationProfilesToolButton->isChecked()) )
  {
    // Create a closed surface representation of the input segment.
    inputSegmentationNode = vtkMRMLSegmentationNode::SafeDownCast(d->surfaceSelector->currentNode());
    if (inputSegmentationNode->GetSegmentation() == nullptr) // Can it happen ?
    {
      const QString msg = qSlicerBranchClipperModuleWidget::tr("Segmentation is NULL in MRML node, aborting");
      cerr << msg.toStdString() << endl;
      this->showStatusMessage(msg, 5000);
      return;
    }
    if (inputSegmentationNode->GetSegmentation()->GetNumberOfSegments() == 0)
    {
      const QString msg = qSlicerBranchClipperModuleWidget::tr("No segment found in the segmentation, aborting");
      cerr << msg.toStdString() << endl;
      this->showStatusMessage(msg, 5000);
      return;
    }
    if (inputSegmentationNode && inputSegmentationNode->CreateClosedSurfaceRepresentation())
    {
      // ID of input whole segment.
      inputSegmentID = d->segmentSelector->currentSegmentID().toStdString();
      if (inputSegmentID.empty())
      {
        const QString msg = qSlicerBranchClipperModuleWidget::tr("No segment selected.");
        this->showStatusMessage(msg, 5000);
        return;
      }
      // Name of the input whole segment.
      inputSegmentName = inputSegmentationNode->GetSegmentation()->GetSegment(inputSegmentID)->GetName();
      // Input whole surface.
      inputSegmentationNode->GetClosedSurfaceRepresentation(inputSegmentID, surface);
    }
    else
    {
      const QString msg = qSlicerBranchClipperModuleWidget::tr("Could not create closed surface representation.");
      cerr << msg.toStdString() << endl;
      this->showStatusMessage(msg, 5000);
      return;
    }
  }
  else if (surfaceNode && surfaceNode->IsA("vtkMRMLModelNode")
    && (d->branchSegmentsToolButton->isChecked() || d->bifurcationProfilesToolButton->isChecked()) )
  {
    inputModelNode = vtkMRMLModelNode::SafeDownCast(d->surfaceSelector->currentNode());
    surface->DeepCopy(inputModelNode->GetPolyData());
    inputModelName = inputModelNode->GetName();
  }
  else
  {
    // Should not happen.
    const QString msg = qSlicerBranchClipperModuleWidget::tr("Unknown surface node");
    cerr << msg.toStdString() << endl;
    this->showStatusMessage(msg, 5000);
    return;
  }
  
  vtkNew<vtkTimerLog> timer;
  
  // Split now. Execute() can be a long process on heavy segmentations.
  timer->StartTimer();
  this->showStatusMessage(qSlicerBranchClipperModuleWidget::tr("Splitting, please wait..."));

  vtkNew<vtkSlicerBranchClipperLogic> logic;
  logic->SetCenterlines(centerlines);
  logic->SetSurface(surface);
  logic->Execute();
  if (logic->GetOutput() == nullptr)
  {
    const QString msg = qSlicerBranchClipperModuleWidget::tr("Could not create a valid surface.");
    cerr << msg.toStdString() << endl;
    this->showStatusMessage(msg, 5000);
    return;
  }
  timer->StopTimer();
  QString centerlineElapsedTime = QString::asprintf("%.4f", timer->GetElapsedTime());
  const std::string elapsedMessage = "Input centerline processed in " + centerlineElapsedTime.toStdString() + "s.";
  cout << elapsedMessage << endl;
  
  mrmlScene()->StartState(vtkMRMLScene::BatchProcessState);
  
  // Create branch segments on demand; this can be a lengthy process too.
  if (d->branchSegmentsToolButton->isChecked())
  {
    // Create one segment per branch.
    const vtkIdType numberOfBranches = logic->GetNumberOfBranches();
    if (numberOfBranches == 0)
    {
      mrmlScene()->EndState(vtkMRMLScene::BatchProcessState);
      const QString msg = qSlicerBranchClipperModuleWidget::tr("No branches could be retrieved; the centerline may be invalid.");
      cerr << msg.toStdString() << endl;
      this->showStatusMessage(msg, 5000);
      return;
    }
    if (inputModelNode)
    {
      // Create a child folder of the input centerline to contain all created models; only for a input model surface.
      vtkIdType shMasterCenterlineId = shNode->GetItemByDataNode(centerlineModel);
      shBranchesModelFolderId = shNode->CreateFolderItem(shMasterCenterlineId, qSlicerBranchClipperModuleWidget::tr("Branches").toStdString());
      shNode->SetItemExpanded(shBranchesModelFolderId, false);
    }
    for (vtkIdType i = 0; i < numberOfBranches; i++)
    {
      timer->StartTimer();
      std::string info(qSlicerBranchClipperModuleWidget::tr("Processing branch ").toStdString());
      info += std::to_string(i + 1) + std::string("/") + std::to_string(numberOfBranches);
      this->showStatusMessage(info.c_str());
      
      std::string consoleInfo("Processing branch ");
      consoleInfo += std::to_string(i + 1) + std::string("/") + std::to_string(numberOfBranches);
      cout << consoleInfo; // no endl
      
      vtkNew<vtkPolyData> branchSurface;
      logic->GetBranch(i, branchSurface);
      if (branchSurface == nullptr)
      {
        cout << endl;
        const QString msg = qSlicerBranchClipperModuleWidget::tr("Could not retrieve branch surface ");
        cerr << msg.toStdString() << i << "." << endl;
        this->showStatusMessage(msg, 5000);
        continue;
      }
      if (inputSegmentationNode)
      {
        // Control branch segment name.
        std::string branchName = inputSegmentName + std::string("_Branch_") + std::to_string((int) i);
        std::string branchId = inputSegmentationNode->AddSegmentFromClosedSurfaceRepresentation(branchSurface, branchName);
        vtkSegment * segment = inputSegmentationNode->GetSegmentation()->GetSegment(branchId);
        if (segment)
        {
          vtkSlicerSegmentationsModuleLogic::SetSegmentStatus(segment, vtkSlicerSegmentationsModuleLogic::InProgress);
          // Don't call Modified().
        }
      }
      else if(inputModelNode)
      {
        // Control branch model name.
        std::string branchName = inputModelName + std::string("_Branch_") + std::to_string((int) i);
        vtkMRMLNode * branchNode = this->mrmlScene()->AddNewNodeByClass("vtkMRMLModelNode");
        if (!branchNode)
        {
          cerr <<  "Could not add branch model: " << i << endl;
        }
        else
        {
          vtkMRMLModelNode * branchModelNode = vtkMRMLModelNode::SafeDownCast(branchNode);
          branchModelNode->CreateDefaultDisplayNodes();
          branchModelNode->SetName(branchName.c_str());
          double colour[3] = {vtkMath::Random(), vtkMath::Random(), vtkMath::Random()};
          branchModelNode->GetDisplayNode()->SetColor(colour);
          branchModelNode->SetAndObservePolyData(branchSurface);
          // Reparent in subject hierarchy.
          vtkIdType shBranchModelId = shNode->GetItemByDataNode(branchModelNode);
          shNode->SetItemParent(shBranchModelId, shBranchesModelFolderId);
        }
      }
      
      timer->StopTimer();
      QString elapsedTime = QString::asprintf("%.4f", timer->GetElapsedTime());
      const std::string elapsedMessage = ": created in " + elapsedTime.toStdString() + "s.";
      cout << elapsedMessage << endl;
    }
  }
  
  // Create bifurcation profiles on demand; though it's usually faster than creating branch segments.
  if (d->bifurcationProfilesToolButton->isChecked())
  {
    vtkPolyDataCollection * profiledPolyDatas = logic->GetOutputBifurcationProfilesCollection();
    if (!profiledPolyDatas)
    {
      mrmlScene()->EndState(vtkMRMLScene::BatchProcessState);
      const QString msg = qSlicerBranchClipperModuleWidget::tr("Could not get a valid collection of bifurcation profiles.");
      cerr << msg.toStdString() << endl;
      this->showStatusMessage(msg, 5000);
      return;
    }
    if (shNode == nullptr) // ?
    {
      mrmlScene()->EndState(vtkMRMLScene::BatchProcessState);
      const QString msg = qSlicerBranchClipperModuleWidget::tr("Could not get a valid subject hierarchy node.");
      cerr << msg.toStdString() << endl;
      this->showStatusMessage(msg, 5000);
      return;
    }
    
    timer->StartTimer();
    
    // Create a child folder of the input centerline to contain all created models.
    vtkIdType shMasterCenterlineId = shNode->GetItemByDataNode(centerlineModel);
    vtkIdType shFolderId = shNode->CreateFolderItem(shMasterCenterlineId, qSlicerBranchClipperModuleWidget::tr("Bifurcation profiles").toStdString());
    shNode->SetItemExpanded(shFolderId, false);
    
    for (int i = 0; i < profiledPolyDatas->GetNumberOfItems(); i++)
    {
      // Create model and set colour.
      vtkPolyData * profilePolyData = vtkPolyData::SafeDownCast(profiledPolyDatas->GetItemAsObject(i));
      double colour[3] = {vtkMath::Random(), vtkMath::Random(), vtkMath::Random()};
      vtkSmartPointer<vtkMRMLModelNode> profileModel = vtkMRMLModelNode::SafeDownCast(mrmlScene()->AddNewNodeByClass("vtkMRMLModelNode"));
      profileModel->CreateDefaultDisplayNodes();
      profileModel->SetAndObservePolyData(profilePolyData);
      profileModel->GetDisplayNode()->SetColor(colour);
      // Reparent in subject hierarchy.
      vtkIdType shModelId = shNode->GetItemByDataNode(profileModel);
      shNode->SetItemParent(shModelId, shFolderId);
    }
    
    timer->StopTimer();
    QString elapsedTime = QString::asprintf("%.4f", timer->GetElapsedTime());
    const std::string elapsedMessage = "All bifurcation profiles created in " + elapsedTime.toStdString() + "s.";
    cout << elapsedMessage << endl;
  }
  
  mrmlScene()->EndState(vtkMRMLScene::BatchProcessState);
  this->showStatusMessage(qSlicerBranchClipperModuleWidget::tr("Finished"), 5000);
}

//-------------------------- From util.py -------------------------------------
bool qSlicerBranchClipperModuleWidget::showStatusMessage(const QString& message, int duration)
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
  if (mainWindow->statusBar() == nullptr) // ?
  {
    return false;
  }
  mainWindow->statusBar()->showMessage(message, duration);
  qSlicerCoreApplication::application()->processEvents();
  return true;
}
