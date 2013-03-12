// Qt includes
#include <QtPlugin>

// Vmtk includes
#include "qSlicerVmtkModule.h"

extern  "C" void initlibvtkvmtkCommonPython();
extern  "C" void initlibvtkvmtkSegmentationPython();
extern  "C" void initlibvtkvmtkDifferentialGeometryPython();
extern  "C" void initlibvtkvmtkComputationalGeometryPython();
extern  "C" void initlibvtkvmtkIOPython();
extern  "C" void initlibvtkvmtkMiscPython();
extern  "C" void initlibvtkvmtkITKPython();

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

  initlibvtkvmtkCommonPython();
  initlibvtkvmtkSegmentationPython();
  initlibvtkvmtkDifferentialGeometryPython();
  initlibvtkvmtkComputationalGeometryPython();
  initlibvtkvmtkIOPython();
  initlibvtkvmtkMiscPython();
  initlibvtkvmtkITKPython();

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
