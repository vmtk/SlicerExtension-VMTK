SET(SlicerVmtkCommonLib_PYTHON_SCRIPTS
  __init__.py
  Helper.py
  LevelSetSegmentationLogic.py
  VesselnessFilteringLogic.py
  CenterlineComputationLogic.py
  # here go other vmtk logic classes
  )

SET(SlicerVmtkCommonLib_PYTHON_RESOURCES
  )
  
ctkMacroCompilePythonScript(
  TARGET_NAME SlicerVmtkCommonLib
  SCRIPTS "${SlicerVmtkCommonLib_PYTHON_SCRIPTS}"
  RESOURCES "${SlicerVmtkCommonLib_PYTHON_RESOURCES}"
  DESTINATION_DIR ${CMAKE_BINARY_DIR}/${Slicer_QTSCRIPTEDMODULES_LIB_DIR}/SlicerVmtkCommonLib
  INSTALL_DIR ${Slicer_INSTALL_ROOT}
  )

#-----------------------------------------------------------------------------
# Testing
#
if(BUILD_TESTING)
endif(BUILD_TESTING)
