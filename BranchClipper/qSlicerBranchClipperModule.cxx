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

// BranchClipper Logic includes
#include <vtkSlicerBranchClipperLogic.h>

// BranchClipper includes
#include "qSlicerBranchClipperModule.h"
#include "qSlicerBranchClipperModuleWidget.h"

//-----------------------------------------------------------------------------
/// \ingroup Slicer_QtModules_ExtensionTemplate
class qSlicerBranchClipperModulePrivate
{
public:
  qSlicerBranchClipperModulePrivate();
};

//-----------------------------------------------------------------------------
// qSlicerBranchClipperModulePrivate methods

//-----------------------------------------------------------------------------
qSlicerBranchClipperModulePrivate::qSlicerBranchClipperModulePrivate()
{
}

//-----------------------------------------------------------------------------
// qSlicerBranchClipperModule methods

//-----------------------------------------------------------------------------
qSlicerBranchClipperModule::qSlicerBranchClipperModule(QObject* _parent)
  : Superclass(_parent)
  , d_ptr(new qSlicerBranchClipperModulePrivate)
{
}

//-----------------------------------------------------------------------------
qSlicerBranchClipperModule::~qSlicerBranchClipperModule()
{
}

//-----------------------------------------------------------------------------
QString qSlicerBranchClipperModule::helpText() const
{
  return "This module splits a bifurcated vascular segment into individual branches, given its centerline model. <a href=\"https://github.com/chir-set/ToolX/tree/master/BranchClipper/\">Homepage</a>.";
}

//-----------------------------------------------------------------------------
QString qSlicerBranchClipperModule::acknowledgementText() const
{
  return "This work was partially funded by NIH grant NXNNXXNNNNNN-NNXN";
}

//-----------------------------------------------------------------------------
QStringList qSlicerBranchClipperModule::contributors() const
{
  QStringList moduleContributors;
  moduleContributors << QString("Saleem Edah-Tally [Surgeon] [Hobbyist developer]");
  return moduleContributors;
}

//-----------------------------------------------------------------------------
QIcon qSlicerBranchClipperModule::icon() const
{
  return QIcon(":/Icons/BranchClipper.png");
}

//-----------------------------------------------------------------------------
QStringList qSlicerBranchClipperModule::categories() const
{
  return QStringList() << "Vascular Modeling Toolkit";
}

//-----------------------------------------------------------------------------
QStringList qSlicerBranchClipperModule::dependencies() const
{
  return QStringList();
}

//-----------------------------------------------------------------------------
void qSlicerBranchClipperModule::setup()
{
  this->Superclass::setup();
}

//-----------------------------------------------------------------------------
qSlicerAbstractModuleRepresentation* qSlicerBranchClipperModule
::createWidgetRepresentation()
{
  return new qSlicerBranchClipperModuleWidget;
}

//-----------------------------------------------------------------------------
vtkMRMLAbstractLogic* qSlicerBranchClipperModule::createLogic()
{
  return vtkSlicerBranchClipperLogic::New();
}
