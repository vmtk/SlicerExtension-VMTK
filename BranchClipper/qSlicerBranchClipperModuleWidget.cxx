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
    this->showStatusMessage("No centerline selected.", 5000);
    return;
  }
  centerlines->DeepCopy(centerlineModel->GetPolyData());
  
  vtkMRMLSegmentationNode * segmentation = nullptr;
  vtkMRMLNode * segmentationNode = d->segmentationSelector->currentNode();
  if (segmentationNode == nullptr)
  {
    this->showStatusMessage("No segmentation selected.", 5000);
    return;
  }
  // Use controlled segment IDs. We can find and delete them precisely.
  std::string segmentID;
  std::string segmentName;
  
  if (segmentationNode && segmentationNode->IsA("vtkMRMLSegmentationNode"))
  {
    segmentation = vtkMRMLSegmentationNode::SafeDownCast(d->segmentationSelector->currentNode());
    if (segmentation->GetSegmentation() == nullptr) // Can it happen ?
    {
      const char * msg = "Segmentation is NULL in MRML node, aborting";
      cerr << msg << endl;
      this->showStatusMessage(msg, 5000);
      return;
    }
    if (segmentation && segmentation->CreateClosedSurfaceRepresentation())
    {
      // ID of input whole segment.
      segmentID = d->segmentSelector->currentSegmentID().toStdString();
      if (segmentID.empty())
      {
        const char * msg = "No segment selected.";
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
      const char * msg = "Could not create closed surface representation.";
      cerr << msg << endl;
      this->showStatusMessage(msg, 5000);
      return;
    }
  }
  else
  {
    // Should not happen.
    const char * msg = "Unknown surface node";
    cerr << msg << endl;
    this->showStatusMessage(msg, 5000);
    return;
  }
  
  // Debranch now. Execute() can be a long process on heavy segmentations.
  this->showStatusMessage("Debranching, please wait...");
  vtkNew<vtkSlicerBranchClipperLogic> logic;
  logic->SetCenterlines(centerlines);
  logic->SetSurface(surface);
  logic->Execute();
  if (logic->GetOutput() == nullptr)
  {
    const char * msg = "Could not create a valid surface.";
    cerr << msg << endl;
    this->showStatusMessage(msg, 5000);
    return;
  }
  // Work on a copy of the debranched surface.
  vtkNew<vtkPolyData> output;
  output->DeepCopy(logic->GetOutput());
  
  // Create one segment per branch.
  const vtkIdType numberOfBranches = logic->GetNumberOfBranches();
  if (numberOfBranches == 0)
  {
    const char * msg = "No branches could be retrieved; the centerline may be invalid.";
    cerr << msg << endl;
    this->showStatusMessage(msg, 5000);
    return;
  }
  for (vtkIdType i = 0; i < numberOfBranches; i++)
  {
    std::string info("Processing branch: ");
    info += std::to_string(i + 1) + std::string("/") + std::to_string(numberOfBranches) + std::string(".");
    cout << info << endl;
    this->showStatusMessage(info.c_str());
    
    vtkNew<vtkPolyData> branchSurface;
    logic->GetBranch(i, branchSurface);
    if (branchSurface == nullptr)
    {
      const char * msg = "Could not retrieve branch surface ";
      cerr << msg << i << "." << endl;
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
  }
  this->showStatusMessage("Finished", 5000);
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
