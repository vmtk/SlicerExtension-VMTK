/*==============================================================================

  Program: 3D Slicer

  Copyright (c) Kitware Inc.

  See COPYRIGHT.txt
  or http://www.slicer.org/copyright/copyright.txt for details.

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.

  This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc.
  and was partially funded by NIH grant 3P41RR013218-12S1

==============================================================================*/

#ifndef __qSlicerStenosisMeasurement3DWidget_h
#define __qSlicerStenosisMeasurement3DWidget_h

// Qt includes
#include <QWidget>

//  Widgets includes
#include "qSlicerStenosisMeasurement3DModuleWidgetsExport.h"

class qSlicerStenosisMeasurement3DWidgetPrivate;

/// \ingroup Slicer_QtModules_StenosisMeasurement3D
class Q_SLICER_MODULE_STENOSISMEASUREMENT3D_WIDGETS_EXPORT qSlicerStenosisMeasurement3DWidget
  : public QWidget
{
  Q_OBJECT
public:
  typedef QWidget Superclass;
  qSlicerStenosisMeasurement3DWidget(QWidget *parent=0);
  ~qSlicerStenosisMeasurement3DWidget() override;

protected slots:

protected:
  QScopedPointer<qSlicerStenosisMeasurement3DWidgetPrivate> d_ptr;

private:
  Q_DECLARE_PRIVATE(qSlicerStenosisMeasurement3DWidget);
  Q_DISABLE_COPY(qSlicerStenosisMeasurement3DWidget);
};

#endif
