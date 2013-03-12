#ifndef __qSlicerVmtkModule_h
#define __qSlicerVmtkModule_h

// SlicerQt includes
#include "qSlicerLoadableModule.h"

#include "qSlicerVmtkModuleExport.h"

class qSlicerVmtkModulePrivate;

/// \ingroup Slicer_QtModules_Vmtk
class Q_SLICER_QTMODULES_VMTK_EXPORT qSlicerVmtkModule :
  public qSlicerLoadableModule
{
  Q_OBJECT
  Q_INTERFACES(qSlicerLoadableModule);

public:

  typedef qSlicerLoadableModule Superclass;
  explicit qSlicerVmtkModule(QObject *parent=0);
  virtual ~qSlicerVmtkModule();

  qSlicerGetTitleMacro(QTMODULE_TITLE);
  
  /// Activate hidden mode for this module.
  virtual bool isHidden()const;

  /// Help to use the module
  virtual QString helpText()const;

  /// Return acknowledgements
  virtual QString acknowledgementText()const;
  
  /// Return a custom icon for the module
  virtual QIcon icon()const;

protected:

  /// Initialize the module. Register the volumes reader/writer
  virtual void setup();

  /// Create and return the widget representation associated to this module
  virtual qSlicerAbstractModuleRepresentation * createWidgetRepresentation();

  /// Create and return the logic associated to this module
  virtual vtkMRMLAbstractLogic* createLogic();

protected:
  QScopedPointer<qSlicerVmtkModulePrivate> d_ptr;

private:
  Q_DECLARE_PRIVATE(qSlicerVmtkModule);
  Q_DISABLE_COPY(qSlicerVmtkModule);

};

#endif
