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
  
  vtkMRMLSegmentationNode * segmentation = nullptr;
  vtkMRMLNode * segmentationNode = d->segmentationSelector->currentNode();
  if (segmentationNode == nullptr)
  {
    this->showStatusMessage(qSlicerBranchClipperModuleWidget::tr("No segmentation selected."), 5000);
    return;
  }
  if ((d->bifurcationProfilesToolButton->isChecked() == false)
    && (d->branchSegmentsToolButton->isChecked() == false))
  {
    this->showStatusMessage(qSlicerBranchClipperModuleWidget::tr("No output selected."), 5000);
    return;
  }
  // Use controlled segment IDs. We can find and delete them precisely.
  std::string segmentID;
  std::string segmentName;
  
  if (segmentationNode && segmentationNode->IsA("vtkMRMLSegmentationNode")
    && (d->branchSegmentsToolButton->isChecked() || d->bifurcationProfilesToolButton->isChecked()) )
  {
    // Create a closed surface representation of the input segment.
    segmentation = vtkMRMLSegmentationNode::SafeDownCast(d->segmentationSelector->currentNode());
    if (segmentation->GetSegmentation() == nullptr) // Can it happen ?
    {
      const QString msg = qSlicerBranchClipperModuleWidget::tr("Segmentation is NULL in MRML node, aborting");
      cerr << msg.toStdString() << endl;
      this->showStatusMessage(msg, 5000);
      return;
    }
    if (segmentation && segmentation->CreateClosedSurfaceRepresentation())
    {
      // ID of input whole segment.
      segmentID = d->segmentSelector->currentSegmentID().toStdString();
      if (segmentID.empty())
      {
        const QString msg = qSlicerBranchClipperModuleWidget::tr("No segment selected.");
        this->showStatusMessage(msg, 5000);
        return;
      }
      // Name of the input whole segment.
      segmentName = segmentation->GetSegmentation()->GetSegment(segmentID)->GetName();
      // Input whole surface.
      segmentation->GetClosedSurfaceRepresentation(segmentID, surface);
    }
    else
    {
      const QString msg = qSlicerBranchClipperModuleWidget::tr("Could not create closed surface representation.");
      cerr << msg.toStdString() << endl;
      this->showStatusMessage(msg, 5000);
      return;
    }
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
  
  // Debranch now. Execute() can be a long process on heavy segmentations.
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
      if (segmentation)
      {
        // Control branch segment name, id and colour.
        std::string branchName = segmentName + std::string("_Branch_") + std::to_string((int) i);
        const std::string branchId = segmentID + std::string("_Branch_") + std::to_string((int) i);
        double colour[3] = {0.0};
        // Don't use a black segment on creation.
        bool segmentRemoved = false;
        // Don't duplicate on repeat apply.
        if (segmentation->GetSegmentation()->GetSegment(branchId))
        {
          // Keep the branch name if it has been changed in UI.
          branchName = segmentation->GetSegmentation()->GetSegment(branchId)->GetName();
          // Keep the colour of a segment with known id.
          segmentation->GetSegmentation()->GetSegment(branchId)->GetColor(colour);
          segmentation->GetSegmentation()->RemoveSegment(branchId);
          segmentRemoved = true;
        }
        /*
        * Don't use AddSegmentFromClosedSurfaceRepresentation().
        * Parameter segmentId is marked vtkNotUsed().
        */
        //segmentation->AddSegmentFromClosedSurfaceRepresentation(branchSurface, branchName, segmentRemoved ? colour : nullptr, branchId);
        vtkSmartPointer<vtkSegment> segment = vtkSmartPointer<vtkSegment>::New();
        if (segmentRemoved)
        {
          // Crash on nullptr. No crash with nullptr in other functions like AddSegmentFromClosedSurfaceRepresentation().
          segment->SetColor(colour);
        }
        segment->SetName(branchName.c_str());
        segment->SetTag("Segmentation.Status", "inprogress");
        if (segment->AddRepresentation(vtkSegmentationConverter::GetClosedSurfaceRepresentationName(), branchSurface))
        {
          segmentation->GetSegmentation()->AddSegment(segment, branchId);
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
    vtkMRMLSubjectHierarchyNode * shNode = mrmlScene()->GetSubjectHierarchyNode();
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
    // Seed with a constant for predictable random table and colours.
    vtkMath::RandomSeed(7);
    
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
