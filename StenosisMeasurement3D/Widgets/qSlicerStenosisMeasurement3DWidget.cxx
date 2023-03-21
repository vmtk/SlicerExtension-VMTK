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

//  Widgets includes
#include "qSlicerStenosisMeasurement3DWidget.h"
#include "ui_qSlicerStenosisMeasurement3DWidget.h"

//-----------------------------------------------------------------------------
/// \ingroup Slicer_QtModules_StenosisMeasurement3D
class qSlicerStenosisMeasurement3DWidgetPrivate
  : public Ui_qSlicerStenosisMeasurement3DWidget
{
  Q_DECLARE_PUBLIC(qSlicerStenosisMeasurement3DWidget);
protected:
  qSlicerStenosisMeasurement3DWidget* const q_ptr;

public:
  qSlicerStenosisMeasurement3DWidgetPrivate(
    qSlicerStenosisMeasurement3DWidget& object);
  virtual void setupUi(qSlicerStenosisMeasurement3DWidget*);
};

// --------------------------------------------------------------------------
qSlicerStenosisMeasurement3DWidgetPrivate
::qSlicerStenosisMeasurement3DWidgetPrivate(
  qSlicerStenosisMeasurement3DWidget& object)
  : q_ptr(&object)
{
}

// --------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DWidgetPrivate
::setupUi(qSlicerStenosisMeasurement3DWidget* widget)
{
  this->Ui_qSlicerStenosisMeasurement3DWidget::setupUi(widget);
}

//-----------------------------------------------------------------------------
// qSlicerStenosisMeasurement3DWidget methods

//-----------------------------------------------------------------------------
qSlicerStenosisMeasurement3DWidget
::qSlicerStenosisMeasurement3DWidget(QWidget* parentWidget)
  : Superclass( parentWidget )
  , d_ptr( new qSlicerStenosisMeasurement3DWidgetPrivate(*this) )
{
  Q_D(qSlicerStenosisMeasurement3DWidget);
  d->setupUi(this);
}

//-----------------------------------------------------------------------------
qSlicerStenosisMeasurement3DWidget
::~qSlicerStenosisMeasurement3DWidget()
{
}
