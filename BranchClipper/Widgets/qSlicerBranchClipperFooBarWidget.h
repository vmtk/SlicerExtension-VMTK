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

#ifndef __qSlicerBranchClipperFooBarWidget_h
#define __qSlicerBranchClipperFooBarWidget_h

// Qt includes
#include <QWidget>

// FooBar Widgets includes
#include "qSlicerBranchClipperModuleWidgetsExport.h"

class qSlicerBranchClipperFooBarWidgetPrivate;

/// \ingroup Slicer_QtModules_BranchClipper
class Q_SLICER_MODULE_BRANCHCLIPPER_WIDGETS_EXPORT qSlicerBranchClipperFooBarWidget
  : public QWidget
{
  Q_OBJECT
public:
  typedef QWidget Superclass;
  qSlicerBranchClipperFooBarWidget(QWidget *parent=0);
  ~qSlicerBranchClipperFooBarWidget() override;

protected slots:

protected:
  QScopedPointer<qSlicerBranchClipperFooBarWidgetPrivate> d_ptr;

private:
  Q_DECLARE_PRIVATE(qSlicerBranchClipperFooBarWidget);
  Q_DISABLE_COPY(qSlicerBranchClipperFooBarWidget);
};

#endif
