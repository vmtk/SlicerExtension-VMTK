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

#ifndef __qSlicerStenosisMeasurement3DModuleWidget_h
#define __qSlicerStenosisMeasurement3DModuleWidget_h

// Slicer includes
#include "qSlicerAbstractModuleWidget.h"

#include "qSlicerStenosisMeasurement3DModuleExport.h"

#include <vtkSmartPointer.h>
#include <vtkWeakPointer.h>
#include <vtkCallbackCommand.h>
#include <vtkPolyData.h>
#include <vtkMRMLMarkupsNode.h>
#include <vtkSlicerStenosisMeasurement3DLogic.h>
#include <vtkMRMLStenosisMeasurement3DParameterNode.h>

class qSlicerStenosisMeasurement3DModuleWidgetPrivate;

/// \ingroup Slicer_QtModules_ExtensionTemplate
class Q_SLICER_QTMODULES_STENOSISMEASUREMENT3D_EXPORT qSlicerStenosisMeasurement3DModuleWidget :
  public qSlicerAbstractModuleWidget
{
  Q_OBJECT

public:

  typedef qSlicerAbstractModuleWidget Superclass;
  qSlicerStenosisMeasurement3DModuleWidget(QWidget *parent=0);
  virtual ~qSlicerStenosisMeasurement3DModuleWidget();

  bool setEditedNode(vtkMRMLNode* node, QString role = QString(), QString context = QString()) override;
  void enter() override;

public slots:
  void onApply();
  void setParameterNode(vtkMRMLNode* node);

protected slots:
  void onShapeNodeChanged(vtkMRMLNode * node);
  void onFiducialNodeChanged(vtkMRMLNode * node);
  void onSegmentationNodeChanged(vtkMRMLNode * node);
  void onSegmentIDChanged(QString segmentID);
  void onWallModelNodeChanged(vtkMRMLNode * node);
  void onLumenModelNodeChanged(vtkMRMLNode * node);
  void onTableNodeChanged(vtkMRMLNode * node);
  void onParameterNodeModified(); // Update the parameter node in the logic only.

protected:
  QScopedPointer<qSlicerStenosisMeasurement3DModuleWidgetPrivate> d_ptr;

  void setup() override;
  bool showStatusMessage(const QString& message, int duration = 0);
  void showResult(vtkVariantArray * results);
  void createModels(vtkPolyData * wall, vtkPolyData * lumen);
  void updateWidgetFromMRML();

  vtkSmartPointer<vtkSlicerStenosisMeasurement3DLogic> logic;

private:
  Q_DECLARE_PRIVATE(qSlicerStenosisMeasurement3DModuleWidget);
  Q_DISABLE_COPY(qSlicerStenosisMeasurement3DModuleWidget);
};

#endif
