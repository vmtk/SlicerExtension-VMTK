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
#include "qSlicerBranchClipperWidget.h"
#include "ui_qSlicerBranchClipperWidget.h"

//-----------------------------------------------------------------------------
/// \ingroup Slicer_QtModules_BranchClipper
class qSlicerBranchClipperWidgetPrivate
  : public Ui_qSlicerBranchClipperWidget
{
  Q_DECLARE_PUBLIC(qSlicerBranchClipperWidget);
protected:
  qSlicerBranchClipperWidget* const q_ptr;

public:
  qSlicerBranchClipperWidgetPrivate(
    qSlicerBranchClipperWidget& object);
  virtual void setupUi(qSlicerBranchClipperWidget*);
};

// --------------------------------------------------------------------------
qSlicerBranchClipperWidgetPrivate
::qSlicerBranchClipperWidgetPrivate(
  qSlicerBranchClipperWidget& object)
  : q_ptr(&object)
{
}

// --------------------------------------------------------------------------
void qSlicerBranchClipperWidgetPrivate
::setupUi(qSlicerBranchClipperWidget* widget)
{
  this->Ui_qSlicerBranchClipperWidget::setupUi(widget);
}

//-----------------------------------------------------------------------------
// qSlicerBranchClipperWidget methods

//-----------------------------------------------------------------------------
qSlicerBranchClipperWidget
::qSlicerBranchClipperWidget(QWidget* parentWidget)
  : Superclass( parentWidget )
  , d_ptr( new qSlicerBranchClipperWidgetPrivate(*this) )
{
  Q_D(qSlicerBranchClipperWidget);
  d->setupUi(this);
}

//-----------------------------------------------------------------------------
qSlicerBranchClipperWidget
::~qSlicerBranchClipperWidget()
{
}
