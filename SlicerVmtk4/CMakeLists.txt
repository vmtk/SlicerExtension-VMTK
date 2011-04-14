
include( ExternalProject )

# Fetch the VMTK Package
#-----------------------------------------------------------------------------
# Sanity checks
if(DEFINED VMTK_DIR AND NOT EXISTS ${VMTK_DIR})
  message(FATAL_ERROR "VMTK_DIR variable is defined but corresponds to non-existing directory")
endif()

set(proj VMTK)

# re-define git protocol if necessary
if(NOT DEFINED git_protocol)
  set( git_protocol "git")
endif()

if(NOT DEFINED VMTK_DIR)
  message(STATUS "Adding external project: ${proj}")
  ExternalProject_Add(${proj}
    GIT_REPOSITORY "${git_protocol}://github.com/haehn/vmtk.git"
    GIT_TAG "origin/superbuild"
    SOURCE_DIR ${CMAKE_CURRENT_BINARY_DIR}/${proj}
    BINARY_DIR ${proj}-build
    CMAKE_GENERATOR ${gen}
    CMAKE_ARGS
      ${ep_common_args}
      -DBUILDNAME:STRING=${BUILDNAME}
      -DSITE:STRING=${SITE}
      -DMAKECOMMAND:STRING=${MAKECOMMAND}
      -DCMAKE_BUILD_TYPE:STRING=${build_type}
      -DBUILD_SHARED_LIBS:BOOL=ON
      -DBUILD_EXAMPLES:BOOL=OFF
      -DBUILD_TESTING:BOOL=OFF
      -DBUILD_DOCUMENTATION:BOOL=OFF
      -DCMAKE_CXX_FLAGS:STRING=${ep_common_cxx_flags}
      -DCMAKE_C_FLAGS:STRING=${ep_common_c_flags}
      -DCMAKE_INSTALL_PREFIX:PATH=${CMAKE_CURRENT_BINARY_DIR}/Install
      -DVTK_VMTK_WRAP_PYTHON:BOOL=ON
      # we don't want superbuild since it will override our CMake settings
      -DVMTK_USE_SUPERBUILD:BOOL=OFF
      -DVMTK_CONTRIB_SCRIPTS:BOOL=ON
      -DVMTK_VTK_CONTRIB:BOOL=ON
      -DVMTK_MINIMAL_INSTALL:BOOL=OFF
      -DVMTK_ENABLE_DISTRIBUTION:BOOL=OFF
      -DVMTK_WITH_LIBRARY_VERSION:BOOL=OFF
      -DVTK_VMTK_IN_SLICER4:BOOL=ON
      # we do not want tetgen..
      -DVMTK_BUILD_TETGEN:BOOL=OFF
      # we do not want the vmtk scripts even if they are great :)
      -DVMTK_SCRIPTS_ENABLED:BOOL=OFF
      # we do not want cocoa, go away :)
      -DVTK_VMTK_USE_COCOA:BOOL=OFF
      # we use Slicer's VTK and ITK
      -DUSE_SYSTEM_VTK:BOOL=ON
      -DUSE_SYSTEM_ITK:BOOL=ON
      -DITK_DIR:PATH=${ITK_DIR}
      -DVTK_DIR:PATH=${VTK_DIR}
      -DGIT_EXECUTABLE:FILEPATH=${GIT_EXECUTABLE}
    INSTALL_COMMAND ""
    DEPENDS 
      ${VMTK_DEPENDENCIES}
    )
  set(VMTK_DIR ${CMAKE_CURRENT_BINARY_DIR}/${proj}-build)
endif()
# End of VMTK External
#-----------------------------------------------------------------------------


# Module name (usually identique to the directory name)
SET(qt_module_name "SlicerVmtk4")

SET(qt_module_export_directive "Q_SLICER_QTMODULES_VMTK4_EXPORT")

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
  ${VMTK_DIR}/bin/
)

# Additional Target libraries
SET(qt_module_target_libraries
  vtkvmtkCommon vtkvmtkCommonPythonD
  vtkvmtkSegmentation vtkvmtkSegmentationPythonD
  vtkvmtkDifferentialGeometry vtkvmtkDifferentialGeometryPythonD
  vtkvmtkComputationalGeometry vtkvmtkComputationalGeometryPythonD
  vtkvmtkMisc vtkvmtkMiscPythonD
  vtkvmtkIO vtkvmtkIOPythonD
  vtkvmtkITK vtkvmtkITKPythonD    
  )

# Resources
SET(qt_module_resources
)

slicerMacroBuildQtModule(
  NAME ${qt_module_name}
  EXPORT_DIRECTIVE ${qt_module_export_directive}
  INCLUDE_DIRECTORIES ${qt_module_include_directories}
  SRCS ${qt_module_SRCS}
  MOC_SRCS ${qt_module_MOC_SRCS}
  UI_SRCS ${qt_module_UI_SRCS}
  TARGET_LIBRARIES ${qt_module_target_libraries}
  RESOURCES ${qt_module_resources}
  )


if(BUILD_TESTING)
  #add_subdirectory(Testing)
endif(BUILD_TESTING)
