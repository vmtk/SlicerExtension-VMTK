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

// StenosisMeasurement3D Logic includes
#include <vtkSlicerStenosisMeasurement3DLogic.h>

// StenosisMeasurement3D includes
#include "qSlicerStenosisMeasurement3DModule.h"
#include "qSlicerStenosisMeasurement3DModuleWidget.h"

//-----------------------------------------------------------------------------
/// \ingroup Slicer_QtModules_ExtensionTemplate
class qSlicerStenosisMeasurement3DModulePrivate
{
public:
  qSlicerStenosisMeasurement3DModulePrivate();
};

//-----------------------------------------------------------------------------
// qSlicerStenosisMeasurement3DModulePrivate methods

//-----------------------------------------------------------------------------
qSlicerStenosisMeasurement3DModulePrivate::qSlicerStenosisMeasurement3DModulePrivate()
{
}

//-----------------------------------------------------------------------------
// qSlicerStenosisMeasurement3DModule methods

//-----------------------------------------------------------------------------
qSlicerStenosisMeasurement3DModule::qSlicerStenosisMeasurement3DModule(QObject* _parent)
  : Superclass(_parent)
  , d_ptr(new qSlicerStenosisMeasurement3DModulePrivate)
{
}

//-----------------------------------------------------------------------------
qSlicerStenosisMeasurement3DModule::~qSlicerStenosisMeasurement3DModule()
{
}

//-----------------------------------------------------------------------------
QString qSlicerStenosisMeasurement3DModule::helpText() const
{
  return "This <a href=\"https://github.com/vmtk/SlicerExtension-VMTK/\">module</a> evaluates an arterial stenosis by relating the lumen and wall volumes.";
}

//-----------------------------------------------------------------------------
QString qSlicerStenosisMeasurement3DModule::acknowledgementText() const
{
  return "This work was partially funded by NIH grant NXNNXXNNNNNN-NNXN";
}

//-----------------------------------------------------------------------------
QStringList qSlicerStenosisMeasurement3DModule::contributors() const
{
  QStringList moduleContributors;
  moduleContributors << QString("Saleem Edah-Tally [Surgeon] [Hobbyist developer]");
  moduleContributors << QString("Andras Lasso, PerkLab");
  return moduleContributors;
}

//-----------------------------------------------------------------------------
QIcon qSlicerStenosisMeasurement3DModule::icon() const
{
  return QIcon(":/Icons/StenosisMeasurement3D.png");
}

//-----------------------------------------------------------------------------
QStringList qSlicerStenosisMeasurement3DModule::categories() const
{
  return QStringList() << "Vascular Modeling Toolkit";
}

//-----------------------------------------------------------------------------
QStringList qSlicerStenosisMeasurement3DModule::dependencies() const
{
  return QStringList();
}

//-----------------------------------------------------------------------------
void qSlicerStenosisMeasurement3DModule::setup()
{
  this->Superclass::setup();
}

//-----------------------------------------------------------------------------
qSlicerAbstractModuleRepresentation* qSlicerStenosisMeasurement3DModule
::createWidgetRepresentation()
{
  return new qSlicerStenosisMeasurement3DModuleWidget;
}

//-----------------------------------------------------------------------------
vtkMRMLAbstractLogic* qSlicerStenosisMeasurement3DModule::createLogic()
{
  return vtkSlicerStenosisMeasurement3DLogic::New();
}
