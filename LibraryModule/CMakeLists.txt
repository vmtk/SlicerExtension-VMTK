
#-----------------------------------------------------------------------------
set(MODULE_NAME Vmtk)
set(MODULE_TITLE ${MODULE_NAME})

string(TOUPPER ${MODULE_NAME} MODULE_NAME_UPPER)

#-----------------------------------------------------------------------------
#add_subdirectory(Logic)
#add_subdirectory(Widgets)

#-----------------------------------------------------------------------------
set(MODULE_EXPORT_DIRECTIVE "Q_SLICER_QTMODULES_${MODULE_NAME_UPPER}_EXPORT")

# Current_{source,binary} and Slicer_{Libs,Base} already included
set(MODULE_INCLUDE_DIRECTORIES
  #${CMAKE_CURRENT_SOURCE_DIR}/Logic
  #${CMAKE_CURRENT_BINARY_DIR}/Logic
  #${CMAKE_CURRENT_SOURCE_DIR}/Widgets
  #${CMAKE_CURRENT_BINARY_DIR}/Widgets
  )

set(MODULE_SRCS
  qSlicer${MODULE_NAME}Module.cxx
  qSlicer${MODULE_NAME}Module.h
  #qSlicer${MODULE_NAME}ModuleWidget.cxx
  #qSlicer${MODULE_NAME}ModuleWidget.h
  )

set(MODULE_MOC_SRCS
  qSlicer${MODULE_NAME}Module.h
  #qSlicer${MODULE_NAME}ModuleWidget.h
  )

set(MODULE_UI_SRCS
  #Resources/UI/qSlicer${MODULE_NAME}ModuleWidget.ui
  )

set(MODULE_TARGET_LIBRARIES
  #vtkSlicer${MODULE_NAME}ModuleLogic
  #qSlicer${MODULE_NAME}ModuleWidgets
  )

set(MODULE_RESOURCES
  #Resources/qSlicer${MODULE_NAME}Module.qrc
  )
  
#-----------------------------------------------------------------------------
# Avoid error when building on mac (Xcode 4.6, cmake 2.8.10)
# ld: framework not found QtSvg
# clang: error: linker command failed with exit code 1 (use -v to see invocation)
# TODO: this should be fixed either in CMake or in the Slicer extension build system
if(APPLE)
  set(CMAKE_SHARED_LINKER_FLAGS "-F /Library/Frameworks")
  set(CMAKE_EXE_LINKER_FLAGS "-F /Library/Frameworks")
endif()
#-----------------------------------------------------------------------------
  
# Link against VMTK lib
link_directories(
  ${CMAKE_BINARY_DIR}/${Slicer_QTLOADABLEMODULES_LIB_DIR}
)

# configure VMTK targets
set(VMTK_LIBRARIES
  vtkvmtkCommon
  vtkvmtkSegmentation
  vtkvmtkDifferentialGeometry
  vtkvmtkComputationalGeometry
  vtkvmtkMisc
  vtkvmtkIO
  vtkvmtkITK
  )

set(VMTK_PYTHON_LIBRARIES)
foreach(lib ${VMTK_LIBRARIES})
  list(APPEND VMTK_PYTHON_LIBRARIES ${lib}PythonD)
endforeach()

# Additional Target libraries
set(MODULE_TARGET_LIBRARIES
  ${VMTK_LIBRARIES}
  ${VMTK_PYTHON_LIBRARIES}
  )  

#-----------------------------------------------------------------------------
slicerMacroBuildQtModule(
  NAME ${MODULE_NAME}
  TITLE ${MODULE_TITLE}
  EXPORT_DIRECTIVE ${MODULE_EXPORT_DIRECTIVE}
  INCLUDE_DIRECTORIES ${MODULE_INCLUDE_DIRECTORIES}
  SRCS ${MODULE_SRCS}
  MOC_SRCS ${MODULE_MOC_SRCS}
  UI_SRCS ${MODULE_UI_SRCS}
  TARGET_LIBRARIES ${MODULE_TARGET_LIBRARIES}
  RESOURCES ${MODULE_RESOURCES}
  WITH_GENERIC_TESTS
  )

#-----------------------------------------------------------------------------
if(BUILD_TESTING)
  add_subdirectory(Testing)
endif()



