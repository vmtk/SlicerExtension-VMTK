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

#ifndef __qSlicerBranchClipperWidget_h
#define __qSlicerBranchClipperWidget_h

// Qt includes
#include <QWidget>

//  Widgets includes
#include "qSlicerBranchClipperModuleWidgetsExport.h"

class qSlicerBranchClipperWidgetPrivate;

/// \ingroup Slicer_QtModules_BranchClipper
class Q_SLICER_MODULE_BRANCHCLIPPER_WIDGETS_EXPORT qSlicerBranchClipperWidget
  : public QWidget
{
  Q_OBJECT
public:
  typedef QWidget Superclass;
  qSlicerBranchClipperWidget(QWidget *parent=0);
  ~qSlicerBranchClipperWidget() override;

protected slots:

protected:
  QScopedPointer<qSlicerBranchClipperWidgetPrivate> d_ptr;

private:
  Q_DECLARE_PRIVATE(qSlicerBranchClipperWidget);
  Q_DISABLE_COPY(qSlicerBranchClipperWidget);
};

#endif
