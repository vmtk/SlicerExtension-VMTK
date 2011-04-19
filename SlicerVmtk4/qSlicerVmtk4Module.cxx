
// Qt includes
#include <QtPlugin>

// Vmtk4 includes
#include "qSlicerVmtk4Module.h"

extern  "C" void initlibvtkvmtkCommonPython();
extern  "C" void initlibvtkvmtkSegmentationPython();
extern  "C" void initlibvtkvmtkDifferentialGeometryPython();
extern  "C" void initlibvtkvmtkComputationalGeometryPython();
extern  "C" void initlibvtkvmtkIOPython();
extern  "C" void initlibvtkvmtkMiscPython();
extern  "C" void initlibvtkvmtkITKPython();

//-----------------------------------------------------------------------------
Q_EXPORT_PLUGIN2(qSlicerVmtk4Module, qSlicerVmtk4Module);

//-----------------------------------------------------------------------------
/// \ingroup Slicer_QtModules_Vmtk4
class qSlicerVmtk4ModulePrivate
{
public:
  qSlicerVmtk4ModulePrivate();
};

//-----------------------------------------------------------------------------
// qSlicerVmtk4ModulePrivate methods

//-----------------------------------------------------------------------------
qSlicerVmtk4ModulePrivate::qSlicerVmtk4ModulePrivate()
{
}

//-----------------------------------------------------------------------------
// qSlicerVmtk4Module methods

//-----------------------------------------------------------------------------
qSlicerVmtk4Module::qSlicerVmtk4Module(QObject* _parent)
  : Superclass(_parent)
  , d_ptr(new qSlicerVmtk4ModulePrivate)
{
}

//-----------------------------------------------------------------------------
qSlicerVmtk4Module::~qSlicerVmtk4Module()
{
}

//-----------------------------------------------------------------------------
QString qSlicerVmtk4Module::helpText()const
{
  return QString();
}

//-----------------------------------------------------------------------------
QString qSlicerVmtk4Module::acknowledgementText()const
{
  return "This work was supported by nothing but hot air :D";
}

//-----------------------------------------------------------------------------
QIcon qSlicerVmtk4Module::icon()const
{
  return QIcon("");
}

//-----------------------------------------------------------------------------
void qSlicerVmtk4Module::setup()
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
qSlicerAbstractModuleRepresentation * qSlicerVmtk4Module::createWidgetRepresentation()
{
  return 0;
}

//-----------------------------------------------------------------------------
vtkMRMLAbstractLogic* qSlicerVmtk4Module::createLogic()
{
  return 0;
}

//-----------------------------------------------------------------------------
bool qSlicerVmtk4Module::isHidden()const
{
  return true;
}
