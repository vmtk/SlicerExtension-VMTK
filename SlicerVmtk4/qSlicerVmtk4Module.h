#ifndef __qSlicerVmtk4Module_h
#define __qSlicerVmtk4Module_h

// CTK includes
#include <ctkPimpl.h>

// SlicerQt includes
#include "qSlicerLoadableModule.h"

#include "qSlicerSlicerVmtk4ModuleExport.h"

class qSlicerVmtk4ModulePrivate;

/// \ingroup Slicer_QtModules_Vmtk4
class Q_SLICER_QTMODULES_VMTK4_EXPORT qSlicerVmtk4Module :
  public qSlicerLoadableModule
{
  Q_OBJECT
  Q_INTERFACES(qSlicerLoadableModule);

public:

  typedef qSlicerLoadableModule Superclass;
  explicit qSlicerVmtk4Module(QObject *parent=0);
  virtual ~qSlicerVmtk4Module();

  qSlicerGetTitleMacro(QTMODULE_TITLE);
  
  ///
  /// Help to use the module
  virtual QString helpText()const;

  ///
  /// Return acknowledgements
  virtual QString acknowledgementText()const;
  
  ///
  /// Return a custom icon for the module
  virtual QIcon icon()const;

protected:
  ///
  /// Initialize the module. Register the volumes reader/writer
  virtual void setup();

  ///
  /// Create and return the widget representation associated to this module
  virtual qSlicerAbstractModuleRepresentation * createWidgetRepresentation();

  ///
  /// Create and return the logic associated to this module
  virtual vtkMRMLAbstractLogic* createLogic();

protected:
  QScopedPointer<qSlicerVmtk4ModulePrivate> d_ptr;

private:
  Q_DECLARE_PRIVATE(qSlicerVmtk4Module);
  Q_DISABLE_COPY(qSlicerVmtk4Module);

};

#endif
