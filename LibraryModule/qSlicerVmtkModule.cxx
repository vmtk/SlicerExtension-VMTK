// Qt includes
#include <QtPlugin>

// Vmtk includes
#include "qSlicerVmtkModule.h"

//-----------------------------------------------------------------------------
Q_EXPORT_PLUGIN2(qSlicerVmtkModule, qSlicerVmtkModule);

//-----------------------------------------------------------------------------
/// \ingroup Slicer_QtModules_Vmtk
class qSlicerVmtkModulePrivate
{
public:
  qSlicerVmtkModulePrivate();
};

//-----------------------------------------------------------------------------
// qSlicerVmtkModulePrivate methods

//-----------------------------------------------------------------------------
qSlicerVmtkModulePrivate::qSlicerVmtkModulePrivate()
{
}

//-----------------------------------------------------------------------------
// qSlicerVmtkModule methods

//-----------------------------------------------------------------------------
qSlicerVmtkModule::qSlicerVmtkModule(QObject* _parent)
  : Superclass(_parent)
  , d_ptr(new qSlicerVmtkModulePrivate)
{
}

//-----------------------------------------------------------------------------
qSlicerVmtkModule::~qSlicerVmtkModule()
{
}

//-----------------------------------------------------------------------------
QString qSlicerVmtkModule::helpText()const
{
  return QString();
}

//-----------------------------------------------------------------------------
QString qSlicerVmtkModule::acknowledgementText()const
{
  return "This work was supported by nothing but hot air :D";
}

//-----------------------------------------------------------------------------
QIcon qSlicerVmtkModule::icon()const
{
  return QIcon("");
}

//-----------------------------------------------------------------------------
void qSlicerVmtkModule::setup()
{
  this->Superclass::setup();
}

//-----------------------------------------------------------------------------
qSlicerAbstractModuleRepresentation * qSlicerVmtkModule::createWidgetRepresentation()
{
  return 0;
}

//-----------------------------------------------------------------------------
vtkMRMLAbstractLogic* qSlicerVmtkModule::createLogic()
{
  return 0;
}

//-----------------------------------------------------------------------------
bool qSlicerVmtkModule::isHidden()const
{
  return true;
}

//-----------------------------------------------------------------------------
QStringList qSlicerVmtkModule::categories()const
{
  return QStringList() << "Vascular Modeling Toolkit";
}

