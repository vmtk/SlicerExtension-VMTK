# This work is templated on commit 88673aa16b5
# of https://github.com/lassoan/SlicerSegmentEditorExtraEffects/

# Should we keep the same naming scheme ?
project(vtkSlicer${MODULE_NAME}ModuleLogic)

set(KIT ${PROJECT_NAME})

set(${KIT}_EXPORT_DIRECTIVE "CROSSSECTION_COMPUTE_EXPORT")

set(${KIT}_INCLUDE_DIRECTORIES
  )

set(${KIT}_SRCS
  CrossSectionCompute.cxx
  CrossSectionCompute.h
  )

set(${KIT}_TARGET_LIBRARIES
  ${VTK_LIBRARIES}
  )

#-----------------------------------------------------------------------------
SlicerMacroBuildModuleLogic(
  NAME ${KIT}
  EXPORT_DIRECTIVE ${${KIT}_EXPORT_DIRECTIVE}
  INCLUDE_DIRECTORIES ${${KIT}_INCLUDE_DIRECTORIES}
  SRCS ${${KIT}_SRCS}
  TARGET_LIBRARIES ${${KIT}_TARGET_LIBRARIES}
  )

