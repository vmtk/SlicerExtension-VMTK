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

// FooBar Widgets includes
#include "qSlicerBranchClipperFooBarWidget.h"
#include "ui_qSlicerBranchClipperFooBarWidget.h"

//-----------------------------------------------------------------------------
/// \ingroup Slicer_QtModules_BranchClipper
class qSlicerBranchClipperFooBarWidgetPrivate
  : public Ui_qSlicerBranchClipperFooBarWidget
{
  Q_DECLARE_PUBLIC(qSlicerBranchClipperFooBarWidget);
protected:
  qSlicerBranchClipperFooBarWidget* const q_ptr;

public:
  qSlicerBranchClipperFooBarWidgetPrivate(
    qSlicerBranchClipperFooBarWidget& object);
  virtual void setupUi(qSlicerBranchClipperFooBarWidget*);
};

// --------------------------------------------------------------------------
qSlicerBranchClipperFooBarWidgetPrivate
::qSlicerBranchClipperFooBarWidgetPrivate(
  qSlicerBranchClipperFooBarWidget& object)
  : q_ptr(&object)
{
}

// --------------------------------------------------------------------------
void qSlicerBranchClipperFooBarWidgetPrivate
::setupUi(qSlicerBranchClipperFooBarWidget* widget)
{
  this->Ui_qSlicerBranchClipperFooBarWidget::setupUi(widget);
}

//-----------------------------------------------------------------------------
// qSlicerBranchClipperFooBarWidget methods

//-----------------------------------------------------------------------------
qSlicerBranchClipperFooBarWidget
::qSlicerBranchClipperFooBarWidget(QWidget* parentWidget)
  : Superclass( parentWidget )
  , d_ptr( new qSlicerBranchClipperFooBarWidgetPrivate(*this) )
{
  Q_D(qSlicerBranchClipperFooBarWidget);
  d->setupUi(this);
}

//-----------------------------------------------------------------------------
qSlicerBranchClipperFooBarWidget
::~qSlicerBranchClipperFooBarWidget()
{
}
