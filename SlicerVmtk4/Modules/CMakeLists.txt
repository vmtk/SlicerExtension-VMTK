
# Common python classes for SlicerVmtk4 
ADD_SUBDIRECTORY(SlicerVmtk4CommonLib)

SET(SlicerVmtk4Modules_PYTHON_SCRIPTS
    LevelSetSegmentation.py
    VesselnessFiltering.py
    CenterlineComputation.py
    # here go other VMTK modules
  )
  
SET(KIT_PYTHON_RESOURCES
  )
  
ctkMacroCompilePythonScript(
  TARGET_NAME SlicerVmtk4Modules
  SCRIPTS "${SlicerVmtk4Modules_PYTHON_SCRIPTS}"
  RESOURCES "${SlicerVmtk4Modules_PYTHON_RESOURCES}"
  DESTINATION_DIR ${CMAKE_BINARY_DIR}/${Slicer_QTSCRIPTEDMODULES_LIB_DIR}
  INSTALL_DIR ${Slicer_INSTALL_ROOT}
  )
