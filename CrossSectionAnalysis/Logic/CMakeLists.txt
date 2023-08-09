# This work is templated on commit 88673aa16b5
# of https://github.com/lassoan/SlicerSegmentEditorExtraEffects/

project(vtkSlicer${MODULE_NAME}ModuleLogic)

set(KIT ${PROJECT_NAME})

set(${KIT}_EXPORT_DIRECTIVE "VTK_SLICER_CROSSSECTION_COMPUTE_EXPORT")

set(${KIT}_INCLUDE_DIRECTORIES
  ${vtkSlicerShapeModuleMRML_INCLUDE_DIRS}
  )

set(${KIT}_SRCS
  vtkCrossSectionCompute.cxx
  vtkCrossSectionCompute.h
  )

set(${KIT}_TARGET_LIBRARIES
  ${VTK_LIBRARIES}
  vtkSlicerShapeModuleMRML
  )

#-----------------------------------------------------------------------------
SlicerMacroBuildModuleLogic(
  NAME ${KIT}
  EXPORT_DIRECTIVE ${${KIT}_EXPORT_DIRECTIVE}
  INCLUDE_DIRECTORIES ${${KIT}_INCLUDE_DIRECTORIES}
  SRCS ${${KIT}_SRCS}
  TARGET_LIBRARIES ${${KIT}_TARGET_LIBRARIES}
  )

