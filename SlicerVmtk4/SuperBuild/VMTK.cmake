
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
      -DVTK_VMTK_BUILD_TETGEN:BOOL=OFF
      # we not want stellar..
      -DVTK_VMTK_BUILD_STELLAR:BOOL=OFF
      # we want the vmtk scripts :)
      -DVMTK_SCRIPTS_ENABLED:BOOL=ON
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
