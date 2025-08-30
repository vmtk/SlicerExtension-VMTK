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

class qSlicerStenosisMeasurement3DModuleWidgetPrivate;
class vtkMRMLNode;

/// \ingroup Slicer_QtModules_ExtensionTemplate
class Q_SLICER_QTMODULES_STENOSISMEASUREMENT3D_EXPORT qSlicerStenosisMeasurement3DModuleWidget :
  public qSlicerAbstractModuleWidget
{
  Q_OBJECT

public:

  typedef qSlicerAbstractModuleWidget Superclass;
  qSlicerStenosisMeasurement3DModuleWidget(QWidget *parent=0);
  virtual ~qSlicerStenosisMeasurement3DModuleWidget();

public slots:
  void onApply();
  void setup() override;
  void enter() override;
  bool setEditedNode(vtkMRMLNode * node, QString role, QString context) override;

protected slots:
  void onShapeNodeChanged(vtkMRMLNode * node);
  void onFiducialNodeChanged(vtkMRMLNode * node);
  void onSegmentationNodeChanged(vtkMRMLNode * node);
  void onSegmentIDChanged(QString segmentID);
  void onLesionModelNodeChanged(vtkMRMLNode * node);
  void onTableNodeChanged(vtkMRMLNode * node);
  void onTableContentModified();
  void onUpdateBoundary(int index);
  void onParameterNodeAddedByUser(vtkMRMLNode * node);
  void onParameterNodeChanged(vtkMRMLNode * node);
  void onSmoothingKernelSizeChanged(double value);
  void onPreProcessWallChanged(bool checked);
  void clearLumenCache();
  void dumpAggregateVolumes();
  void updateSegmentBySmoothClosing();

protected:
  QScopedPointer<qSlicerStenosisMeasurement3DModuleWidgetPrivate> d_ptr;

  bool showStatusMessage(const QString& message, int duration = 0);
  vtkSlicerStenosisMeasurement3DLogic::EnclosingType
  createEnclosedSurface(vtkMRMLMarkupsShapeNode * wallShapeNode,
                        vtkMRMLSegmentationNode * lumenSegmentationNode, std::string segmentID,
                        vtkPolyData * enclosedSurface,
                        bool preProcessWallSurface = false);
  bool getEnclosedSurface(vtkMRMLMarkupsShapeNode * wallShapeNode,
                          vtkMRMLSegmentationNode * lumenSegmentationNode, std::string segmentID,
                          vtkPolyData * enclosedSurface,
                          bool preProcessWallSurface = false); // From cache or create.

  void showResult(vtkPolyData * wall, vtkPolyData * lumen, vtkVariantArray * results);
  void createLesionModel(vtkMRMLMarkupsShapeNode * wallShapeNode, vtkPolyData * enclosedSurface,
                    vtkMRMLMarkupsFiducialNode * boundaryFiducialNode);

  vtkSmartPointer<vtkSlicerStenosisMeasurement3DLogic> logic;

  vtkSmartPointer<vtkCallbackCommand> fiducialObservation;
  static void onFiducialPointEndInteraction(vtkObject *caller,
                                            unsigned long event, void *clientData, void *callData);

  vtkSmartPointer<vtkCallbackCommand> tubePointEndInteractionObservation;
  vtkSmartPointer<vtkCallbackCommand> tubeModifiedObservation;
  static void onTubeModified(vtkObject *caller,
                                        unsigned long event, void *clientData, void *callData);

  vtkSmartPointer<vtkCallbackCommand> segmentationRepresentationObservation;
  static void onSegmentationRepresentationModified(vtkObject *caller,
                                        unsigned long event, void *clientData, void *callData);

  void setDefaultParameters(vtkMRMLNode * node);
  void updateGuiFromParameterNode();
  void addMenu();
  void updateRegionInfo();

private:
  Q_DECLARE_PRIVATE(qSlicerStenosisMeasurement3DModuleWidget);
  Q_DISABLE_COPY(qSlicerStenosisMeasurement3DModuleWidget);
};

#endif
