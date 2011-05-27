SET(SlicerVmtk4CommonLib_PYTHON_SCRIPTS
  __init__.py
  Helper.py
  LevelSetSegmentationLogic.py
  VesselnessFilteringLogic.py
  CenterlineComputationLogic.py
  # here go other vmtk logic classes
  )

SET(SlicerVmtk4CommonLib_PYTHON_RESOURCES
  )
  
ctkMacroCompilePythonScript(
  TARGET_NAME SlicerVmtk4CommonLib
  SCRIPTS "${SlicerVmtk4CommonLib_PYTHON_SCRIPTS}"
  RESOURCES "${SlicerVmtk4CommonLib_PYTHON_RESOURCES}"
  DESTINATION_DIR ${Slicer_BINARY_DIR}/bin/Python/SlicerVmtk4CommonLib
  INSTALL_DIR ${Slicer_INSTALL_BIN_DIR}
  )

#-----------------------------------------------------------------------------
# Testing
#
if(BUILD_TESTING)
endif(BUILD_TESTING)
