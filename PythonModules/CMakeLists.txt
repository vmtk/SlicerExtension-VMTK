
#-----------------------------------------------------------------------------
set(MODULE_NAME ${EXTENSION_NAME})

#-----------------------------------------------------------------------------
set(MODULE_PYTHON_SCRIPTS
  LevelSetSegmentation.py
  VesselnessFiltering.py
  CenterlineComputation.py
  # here go other VMTK modules

  SlicerVmtkCommonLib/__init__.py
  SlicerVmtkCommonLib/Helper.py
  SlicerVmtkCommonLib/LevelSetSegmentationLogic.py
  SlicerVmtkCommonLib/VesselnessFilteringLogic.py
  SlicerVmtkCommonLib/CenterlineComputationLogic.py
  # here go other vmtk logic classes
  )
  
set(MODULE_PYTHON_RESOURCES
  Resources/Vesselness.png
  Resources/VesselnessVrPresets.mrml 
  )
  
#-----------------------------------------------------------------------------
slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  RESOURCES ${MODULE_PYTHON_RESOURCES}
  WITH_GENERIC_TESTS
  )
