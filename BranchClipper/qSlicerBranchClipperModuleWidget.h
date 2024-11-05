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

#ifndef __qSlicerBranchClipperModuleWidget_h
#define __qSlicerBranchClipperModuleWidget_h

// Slicer includes
#include "qSlicerAbstractModuleWidget.h"

#include "qSlicerBranchClipperModuleExport.h"

class qSlicerBranchClipperModuleWidgetPrivate;
class vtkMRMLNode;

/// \ingroup Slicer_QtModules_ExtensionTemplate
class Q_SLICER_QTMODULES_BRANCHCLIPPER_EXPORT qSlicerBranchClipperModuleWidget :
  public qSlicerAbstractModuleWidget
{
  Q_OBJECT

public:

  typedef qSlicerAbstractModuleWidget Superclass;
  qSlicerBranchClipperModuleWidget(QWidget *parent=0);
  virtual ~qSlicerBranchClipperModuleWidget();

public slots:
  void onApply();
  void onSurfaceChanged(vtkMRMLNode* surface);

protected:
  QScopedPointer<qSlicerBranchClipperModuleWidgetPrivate> d_ptr;

  void setup() override;
  
  bool showStatusMessage(const QString& message, int duration = 0);

private:
  Q_DECLARE_PRIVATE(qSlicerBranchClipperModuleWidget);
  Q_DISABLE_COPY(qSlicerBranchClipperModuleWidget);
};

#endif
