PROJECT(SlicerVmtk4)
#-----------------------------------------------------------------------------
cmake_minimum_required(VERSION 2.8.2)
#-----------------------------------------------------------------------------

if(POLICY CMP0016)
  CMAKE_POLICY(SET CMP0016 NEW)
endif()
if(POLICY CMP0017)
  CMAKE_POLICY(SET CMP0017 OLD)
endif()

#-----------------------------------------------------------------------------
# Prerequisites
#-----------------------------------------------------------------------------
IF(NOT Slicer_SOURCE_DIR)
  FIND_PACKAGE(Slicer REQUIRED)
  INCLUDE(${Slicer_USE_FILE})
ENDIF()

#-----------------------------------------------------------------------------
# Module name (usually identique to the directory name)
#-----------------------------------------------------------------------------
SET(EXTENSION_NAME SlicerVmtk4)

#-----------------------------------------------------------------------------
# Superbuild Option - Enabled by default
#-----------------------------------------------------------------------------
OPTION(SlicerVmtk4_SUPERBUILD "Build SlicerVmtk4 and the projects it depends on via SuperBuild.cmake." ON)
MARK_AS_ADVANCED(SlicerVmtk4_SUPERBUILD)

#-----------------------------------------------------------------------------
# Additional C/CXX flags
#-----------------------------------------------------------------------------
SET(ADDITIONAL_C_FLAGS "" CACHE STRING "Additional ${EXTENSION_NAME} C Flags")
SET(ADDITIONAL_CXX_FLAGS "" CACHE STRING "Additional ${EXTENSION_NAME} CXX Flags")

#-----------------------------------------------------------------------------
# CPack for SlicerVmtk4
#-----------------------------------------------------------------------------
set(CPACK_INSTALL_CMAKE_PROJECTS "${CPACK_INSTALL_CMAKE_PROJECTS};${CMAKE_BINARY_DIR};SlicerVmtk4;ALL;/")

#-----------------------------------------------------------------------------
# CPack for VMTK, has to be before superbuild call
#-----------------------------------------------------------------------------
set(CPACK_INSTALL_CMAKE_PROJECTS "${CPACK_INSTALL_CMAKE_PROJECTS};${VMTK_DIR};VMTK;RuntimeLibraries;/")

INCLUDE(SlicerEnableExtensionTesting)

#-----------------------------------------------------------------------------
# Superbuild script
#-----------------------------------------------------------------------------
IF(SlicerVmtk4_SUPERBUILD)
  INCLUDE("${CMAKE_CURRENT_SOURCE_DIR}/SuperBuild.cmake")
  RETURN()
ENDIF()

#-----------------------------------------------------------------------------
# Extension description
#-----------------------------------------------------------------------------
SET(EXTENSION_HOMEPAGE "http://slicer.vmtk.org/")
SET(EXTENSION_CATEGORY "Vascular Modeling Toolkit")
SET(EXTENSION_STATUS "Beta")
SET(EXTENSION_DESCRIPTION "The Vascular Modeling Toolkit as a 3D Slicer4 extension.")

SET(EXTENSION_LICENSE_FILE ${Slicer_LICENSE_FILE})
SET(EXTENSION_README_FILE ${Slicer_README_FILE})

SET(qt_module_export_directive "Q_SLICER_QTMODULES_VMTK4_EXPORT")

#-----------------------------------------------------------------------------
# Sources
#-----------------------------------------------------------------------------

# Additional includes - Current_{source,binary} and Slicer_{Libs,Base} already included
SET(qt_module_include_directories
  )

# Source files
SET(qt_module_SRCS
  qSlicerVmtk4Module.cxx
  qSlicerVmtk4Module.h
  )

# Headers that should run through moc
SET(qt_module_MOC_SRCS
  qSlicerVmtk4Module.h
  )

# UI files
SET(qt_module_UI_SRCS
)

# Link against VMTK
LINK_DIRECTORIES(
  ${CMAKE_BINARY_DIR}/${Slicer_QTLOADABLEMODULES_LIB_DIR}
)

# TODO VMTK should expose a VMTK_LIBRARIES variable
SET(VMTK_LIBRARIES
  vtkvmtkCommon
  vtkvmtkSegmentation
  vtkvmtkDifferentialGeometry
  vtkvmtkComputationalGeometry
  vtkvmtkMisc
  vtkvmtkIO
  vtkvmtkITK
  )

SET(VMTK_PYTHON_LIBRARIES)
FOREACH(lib ${VMTK_LIBRARIES})
  LIST(APPEND VMTK_PYTHON_LIBRARIES ${lib}PythonD)
ENDFOREACH()

# Additional Target libraries
SET(qt_module_target_libraries
  ${VMTK_LIBRARIES}
  ${VMTK_PYTHON_LIBRARIES}
  )

# Resources
SET(qt_module_resources
  )

#-----------------------------------------------------------------------------
# Include Python Modules
#-----------------------------------------------------------------------------
ADD_SUBDIRECTORY(Modules)


#-----------------------------------------------------------------------------
# Build
#-----------------------------------------------------------------------------

# patch until JC fixes the macro :)
set(Slicer_INSTALL_QTLOADABLEMODULES_BIN_DIR ${Slicer_QTLOADABLEMODULES_BIN_DIR})
set(Slicer_INSTALL_QTLOADABLEMODULES_LIB_DIR ${Slicer_QTLOADABLEMODULES_LIB_DIR})

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

set(EXTENSION_BINARY_DIR ${CMAKE_CURRENT_BINARY_DIR}/SlicerVmtk4-build)
message(XX ${EXTENSION_BINARY_DIR})

#-----------------------------------------------------------------------------
# Generate extension description file '<EXTENSION_NAME>.s4ext'
#-----------------------------------------------------------------------------
IF(NOT Slicer_SOURCE_DIR)
  INCLUDE(SlicerFunctionGenerateExtensionDescription)
  slicerFunctionGenerateExtensionDescription(
    EXTENSION_NAME ${EXTENSION_NAME}
    EXTENSION_CATEGORY ${EXTENSION_CATEGORY} 
    EXTENSION_STATUS ${EXTENSION_STATUS}
    EXTENSION_HOMEPAGE ${EXTENSION_HOMEPAGE}
    EXTENSION_DESCRIPTION ${EXTENSION_DESCRIPTION}
    DESTINATION_DIR ${CMAKE_CURRENT_BINARY_DIR}
    SLICER_WC_REVISION ${Slicer_WC_REVISION}
    SLICER_WC_ROOT ${Slicer_WC_ROOT}
    )
  INCLUDE(${Slicer_EXTENSION_CPACK})
ENDIF()

#-----------------------------------------------------------------------------
# Testing
#-----------------------------------------------------------------------------
if(BUILD_TESTING)
  #add_subdirectory(Testing)
endif()

