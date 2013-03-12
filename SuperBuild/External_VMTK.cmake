# Fetch the VMTK Package
#-----------------------------------------------------------------------------

# Make sure this file is included only once
get_filename_component(CMAKE_CURRENT_LIST_FILENAME ${CMAKE_CURRENT_LIST_FILE} NAME_WE)
if(${CMAKE_CURRENT_LIST_FILENAME}_FILE_INCLUDED)
  return()
endif()
set(${CMAKE_CURRENT_LIST_FILENAME}_FILE_INCLUDED 1)

# Sanity checks
if(DEFINED VMTK_DIR AND NOT EXISTS ${VMTK_DIR})
  message(FATAL_ERROR "VMTK_DIR variable is defined but corresponds to non-existing directory")
endif()

# Set dependency list
set(VMTK_DEPENDENCIES "")

SlicerMacroCheckExternalProjectDependency(VMTK)
set(proj VMTK)

if(NOT DEFINED ${proj}_DIR)
  #message(STATUS "Adding external project: ${proj}")
  
  # Set CMake OSX variable to pass down the external project
  set(CMAKE_OSX_EXTERNAL_PROJECT_ARGS)
  if(APPLE)
    list(APPEND CMAKE_OSX_EXTERNAL_PROJECT_ARGS
      -DCMAKE_OSX_ARCHITECTURES=${CMAKE_OSX_ARCHITECTURES}
      -DCMAKE_OSX_SYSROOT=${CMAKE_OSX_SYSROOT}
      -DCMAKE_OSX_DEPLOYMENT_TARGET=${CMAKE_OSX_DEPLOYMENT_TARGET})
  endif()  

  if(NOT DEFINED git_protocol)
    set(git_protocol "git")
  endif()  
  
  ExternalProject_Add(${proj}
    GIT_REPOSITORY "${git_protocol}://github.com/lantiga/vmtk.git"
    GIT_TAG "origin/itk4"
    SOURCE_DIR ${CMAKE_CURRENT_BINARY_DIR}/${proj}
    BINARY_DIR ${proj}-build
    CMAKE_GENERATOR ${gen}
    CMAKE_ARGS
      ${ep_common_args}
      -DCMAKE_BUILD_TYPE:STRING=${build_type}
      -DCMAKE_RUNTIME_OUTPUT_DIRECTORY:PATH=${CMAKE_CURRENT_BINARY_DIR}/SlicerVmtk4-build/${Slicer_QTLOADABLEMODULES_LIB_DIR}
      -DCMAKE_LIBRARY_OUTPUT_DIRECTORY:PATH=${CMAKE_CURRENT_BINARY_DIR}/SlicerVmtk4-build/${Slicer_QTLOADABLEMODULES_LIB_DIR}
      -DCMAKE_ARCHIVE_OUTPUT_DIRECTORY:PATH=${CMAKE_CURRENT_BINARY_DIR}/SlicerVmtk4-build/${Slicer_QTLOADABLEMODULES_LIB_DIR}
      -DBUILD_SHARED_LIBS:BOOL=ON
      -DBUILD_DOCUMENTATION:BOOL=OFF
      -DCMAKE_CXX_FLAGS:STRING=${ep_common_cxx_flags}
      -DCMAKE_C_FLAGS:STRING=${ep_common_c_flags}
      -DCMAKE_INSTALL_PREFIX:PATH=${CMAKE_CURRENT_BINARY_DIR}/SlicerVmtk4-build
      # installation location for the pypes/scripts
      -DVMTK_INSTALL_BIN_DIR:PATH=${Slicer_QTLOADABLEMODULES_LIB_DIR}/pypes
      -DVMTK_MODULE_INSTALL_LIB_DIR:PATH=${Slicer_QTLOADABLEMODULES_LIB_DIR}/pypes
      -DVMTK_SCRIPTS_INSTALL_BIN_DIR:PATH=${Slicer_QTLOADABLEMODULES_LIB_DIR}/pypes
      -DVMTK_SCRIPTS_INSTALL_LIB_DIR:PATH=${Slicer_QTLOADABLEMODULES_LIB_DIR}/pypes
      -DPYPES_INSTALL_BIN_DIR:PATH=${Slicer_QTLOADABLEMODULES_LIB_DIR}/pypes
      -DPYPES_MODULE_INSTALL_LIB_DIR:PATH=${Slicer_QTLOADABLEMODULES_LIB_DIR}/pypes
      -DVMTK_CONTRIB_SCRIPTS_INSTALL_LIB_DIR:PATH=${Slicer_QTLOADABLEMODULES_LIB_DIR}/pypes
      -DVMTK_CONTRIB_SCRIPTS_INSTALL_BIN_DIR:PATH=${Slicer_QTLOADABLEMODULES_LIB_DIR}/pypes
      # installation location for all vtkvmtk stuff
      -DVTK_VMTK_INSTALL_BIN_DIR:PATH=${Slicer_QTLOADABLEMODULES_LIB_DIR}
      -DVTK_VMTK_INSTALL_LIB_DIR:PATH=${Slicer_QTLOADABLEMODULES_LIB_DIR}
      -DVTK_VMTK_MODULE_INSTALL_LIB_DIR:PATH=${Slicer_QTLOADABLEMODULES_LIB_DIR}
      -DVTK_VMTK_WRAP_PYTHON:BOOL=ON
      # we don't want superbuild since it will override our CMake settings
      -DVMTK_USE_SUPERBUILD:BOOL=OFF
      -DVMTK_CONTRIB_SCRIPTS:BOOL=ON
      -DVMTK_MINIMAL_INSTALL:BOOL=OFF
      -DVMTK_ENABLE_DISTRIBUTION:BOOL=OFF
      -DVMTK_WITH_LIBRARY_VERSION:BOOL=OFF
      # we want the vmtk scripts :)
      -DVMTK_SCRIPTS_ENABLED:BOOL=ON
      # we do not want cocoa, go away :)
      -DVTK_VMTK_USE_COCOA:BOOL=OFF
      # we use Slicer's VTK and ITK
      -DUSE_SYSTEM_VTK:BOOL=ON
      -DUSE_SYSTEM_ITK:BOOL=ON
      -DITK_DIR:PATH=${ITK_DIR}
      -DVTK_DIR:PATH=${VTK_DIR}
    INSTALL_COMMAND ""
    DEPENDS 
      ${VMTK_DEPENDENCIES}
    )
  set(${proj}_DIR ${CMAKE_BINARY_DIR}/${proj}-build)

else()
  # The project is provided using <proj>_DIR, nevertheless since other project may depend on <proj>,
  # let's add an 'empty' one
  SlicerMacroEmptyExternalProject(${proj} "${${proj}_DEPENDENCIES}")
endif()
# End of VMTK External
#-----------------------------------------------------------------------------
