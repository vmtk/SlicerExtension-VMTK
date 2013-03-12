
# Common python classes for SlicerVmtk 
ADD_SUBDIRECTORY(SlicerVmtkCommonLib)

SET(SlicerVmtkModules_PYTHON_SCRIPTS
    LevelSetSegmentation.py
    VesselnessFiltering.py
    CenterlineComputation.py
    # here go other VMTK modules
  )
  
SET(KIT_PYTHON_RESOURCES
  )
  
ctkMacroCompilePythonScript(
  TARGET_NAME SlicerVmtkModules
  SCRIPTS "${SlicerVmtkModules_PYTHON_SCRIPTS}"
  RESOURCES "${SlicerVmtkModules_PYTHON_RESOURCES}"
  DESTINATION_DIR ${CMAKE_BINARY_DIR}/${Slicer_QTSCRIPTEDMODULES_LIB_DIR}
  INSTALL_DIR ${Slicer_INSTALL_ROOT}
  )
