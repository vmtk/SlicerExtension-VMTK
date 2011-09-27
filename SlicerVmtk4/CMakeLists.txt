#
# SlicerVmtk4: The Vascular Modeling Toolkit in 3D Slicer 4
#
# http://slicer.vmtk.org
#

#-----------------------------------------------------------------------------
cmake_minimum_required(VERSION 2.8.2)
#-----------------------------------------------------------------------------

#-----------------------------------------------------------------------------
# See http://cmake.org/cmake/help/cmake-2-8-docs.html#section_Policies for details
#-----------------------------------------------------------------------------
if(POLICY CMP0016)
  CMAKE_POLICY(SET CMP0016 NEW)
endif()
if(POLICY CMP0017)
  CMAKE_POLICY(SET CMP0017 OLD)
endif()

#-----------------------------------------------------------------------------
# Module name (usually identique to the directory name)
#-----------------------------------------------------------------------------
set(EXTENSION_NAME SlicerVmtk4)
set(EXTENSION_BUILD_SUBDIRECTORY ${EXTENSION_NAME}-build)

#-----------------------------------------------------------------------------
# Prerequisites
#-----------------------------------------------------------------------------
if(NOT Slicer_SOURCE_DIR)
  find_package(Slicer REQUIRED)

  # Additional C/CXX flags - Should be defined before including Slicer_USE_FILE
  set(ADDITIONAL_C_FLAGS "" CACHE STRING "Additional ${EXTENSION_NAME} C Flags")
  set(ADDITIONAL_CXX_FLAGS "" CACHE STRING "Additional ${EXTENSION_NAME} CXX Flags")

  include(${Slicer_USE_FILE})

  include(SlicerEnableExtensionTesting)

  find_package(Git REQUIRED)
endif()

#-----------------------------------------------------------------------------
# Superbuild
#-----------------------------------------------------------------------------
option(${EXTENSION_NAME}_SUPERBUILD "Build ${EXTENSION_NAME} and the projects it depends on via SuperBuild.cmake." ON)
mark_as_advanced(${EXTENSION_NAME}_SUPERBUILD)
if(${EXTENSION_NAME}_SUPERBUILD)
  include("${CMAKE_CURRENT_SOURCE_DIR}/SuperBuild.cmake")
  return()
endif()

#-----------------------------------------------------------------------------
# Include Python Modules
#-----------------------------------------------------------------------------
add_subdirectory(Modules)

#-----------------------------------------------------------------------------
# Extension description
#-----------------------------------------------------------------------------
set(EXTENSION_HOMEPAGE "http://slicer.vmtk.org/")
set(EXTENSION_CATEGORY "Vascular Modeling Toolkit")
set(EXTENSION_STATUS "Beta")
set(EXTENSION_DESCRIPTION "The Vascular Modeling Toolkit as a 3D Slicer4 extension.")
set(EXTENSION_DEPENDS "NA")

set(EXTENSION_LICENSE_FILE ${Slicer_LICENSE_FILE})
set(EXTENSION_README_FILE ${Slicer_README_FILE})

#-----------------------------------------------------------------------------
# Sources
#-----------------------------------------------------------------------------
set(qt_module_export_directive "Q_SLICER_QTMODULES_VMTK4_EXPORT")

# Additional includes - Current_{source,binary} and Slicer_{Libs,Base} already included
set(qt_module_include_directories
  )

# Source files
set(qt_module_SRCS
  qSlicerVmtk4Module.cxx
  qSlicerVmtk4Module.h
  )

# Headers that should run through moc
set(qt_module_MOC_SRCS
  qSlicerVmtk4Module.h
  )

# UI files
set(qt_module_UI_SRCS
)

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
set(qt_module_target_libraries
  ${VMTK_LIBRARIES}
  ${VMTK_PYTHON_LIBRARIES}
  )

# Resources
set(qt_module_resources
  )

#-----------------------------------------------------------------------------
# Build
#-----------------------------------------------------------------------------
slicerMacroBuildQtModule(
  NAME ${EXTENSION_NAME}
  EXPORT_DIRECTIVE ${qt_module_export_directive}
  INCLUDE_DIRECTORIES ${qt_module_include_directories}
  SRCS ${qt_module_SRCS}
  MOC_SRCS ${qt_module_MOC_SRCS}
  UI_SRCS ${qt_module_UI_SRCS}
  TARGET_LIBRARIES ${qt_module_target_libraries}
  RESOURCES ${qt_module_resources}
  )

#-----------------------------------------------------------------------------
# Testing
#-----------------------------------------------------------------------------
if(BUILD_TESTING)
  #add_subdirectory(Testing)
endif()

#-----------------------------------------------------------------------------
# Generate extension description file '<EXTENSION_NAME>.s4ext'
#-----------------------------------------------------------------------------
include(SlicerFunctionGenerateExtensionDescription)
slicerFunctionGenerateExtensionDescription(
  EXTENSION_NAME ${EXTENSION_NAME}
  EXTENSION_BUILD_SUBDIRECTORY ${EXTENSION_BUILD_SUBDIRECTORY}
  EXTENSION_CATEGORY ${EXTENSION_CATEGORY}
  EXTENSION_STATUS ${EXTENSION_STATUS}
  EXTENSION_HOMEPAGE ${EXTENSION_HOMEPAGE}
  EXTENSION_DESCRIPTION ${EXTENSION_DESCRIPTION}
  EXTENSION_DEPENDS ${EXTENSION_DEPENDS}
  DESTINATION_DIR ${CMAKE_CURRENT_BINARY_DIR}
  SLICER_WC_REVISION ${Slicer_WC_REVISION}
  SLICER_WC_ROOT ${Slicer_WC_ROOT}
  )

#-----------------------------------------------------------------------------
# Packaging
#-----------------------------------------------------------------------------
# Current project
set(CPACK_INSTALL_CMAKE_PROJECTS "${CPACK_INSTALL_CMAKE_PROJECTS};${CMAKE_BINARY_DIR};${EXTENSION_NAME};ALL;/")
# External projects
#set(CPACK_INSTALL_CMAKE_PROJECTS "${CPACK_INSTALL_CMAKE_PROJECTS};${<EP>_DIR};<EP>;RuntimeLibraries;/")
INCLUDE(${Slicer_EXTENSION_CPACK})

