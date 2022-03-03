
set(proj VMTK)

# Set dependency list
set(${proj}_DEPENDS
  ""
  )

# Include dependent projects if any
ExternalProject_Include_Dependencies(${proj} PROJECT_VAR proj)

if(${CMAKE_PROJECT_NAME}_USE_SYSTEM_${proj})
  message(FATAL_ERROR "Enabling ${CMAKE_PROJECT_NAME}_USE_SYSTEM_${proj} is not supported !")
endif()

# Sanity checks
if(DEFINED VMTK_DIR AND NOT EXISTS ${VMTK_DIR})
  message(FATAL_ERROR "VMTK_DIR [${VMTK_DIR}] variable is defined but corresponds to nonexistent directory")
endif()

if(NOT DEFINED ${proj}_DIR AND NOT ${CMAKE_PROJECT_NAME}_USE_SYSTEM_${proj})

  set(VMTK_USE_VTK9 ON)
  if(Slicer_VTK_VERSION_MAJOR VERSION_LESS "9")
    set(VMTK_USE_VTK9 OFF)
  endif()
  ExternalProject_Message(${proj} "VMTK_USE_VTK9:${VMTK_USE_VTK9}")

  set(EXTERNAL_PROJECT_OPTIONAL_CMAKE_CACHE_ARGS)
  if(VTK_WRAP_PYTHON)
    list(APPEND EXTERNAL_PROJECT_OPTIONAL_CMAKE_CACHE_ARGS
      -DPYTHON_EXECUTABLE:FILEPATH=${PYTHON_EXECUTABLE}
      -DPYTHON_INCLUDE_DIR:PATH=${PYTHON_INCLUDE_DIR}
      -DPYTHON_LIBRARY:FILEPATH=${PYTHON_LIBRARY}
      # Required by FindPython3 CMake module used by VTK
      -DPython3_ROOT_DIR:PATH=${Python3_ROOT_DIR}
      -DPython3_INCLUDE_DIR:PATH=${Python3_INCLUDE_DIR}
      -DPython3_LIBRARY:FILEPATH=${Python3_LIBRARY}
      -DPython3_LIBRARY_DEBUG:FILEPATH=${Python3_LIBRARY_DEBUG}
      -DPython3_LIBRARY_RELEASE:FILEPATH=${Python3_LIBRARY_RELEASE}
      -DPython3_EXECUTABLE:FILEPATH=${Python3_EXECUTABLE}
      )
  endif()

  ExternalProject_SetIfNotDefined(
    ${CMAKE_PROJECT_NAME}_${proj}_GIT_REPOSITORY
    "${EP_GIT_PROTOCOL}://github.com/vmtk/vmtk.git"
    QUIET
    )

  ExternalProject_SetIfNotDefined(
    ${CMAKE_PROJECT_NAME}_${proj}_GIT_TAG
    "27e3784dde5c2e8ad6a4ef21edfd50c72763fcdf"
    QUIET
    )

  set(EP_SOURCE_DIR ${CMAKE_BINARY_DIR}/${proj})
  set(EP_BINARY_DIR ${CMAKE_BINARY_DIR}/${proj}-build)

  ExternalProject_Add(${proj}
    ${${proj}_EP_ARGS}
    GIT_REPOSITORY "${${CMAKE_PROJECT_NAME}_${proj}_GIT_REPOSITORY}"
    GIT_TAG "${${CMAKE_PROJECT_NAME}_${proj}_GIT_TAG}"
    SOURCE_DIR ${EP_SOURCE_DIR}
    BINARY_DIR ${EP_BINARY_DIR}
    CMAKE_CACHE_ARGS
      -DCMAKE_RUNTIME_OUTPUT_DIRECTORY:PATH=${CMAKE_BINARY_DIR}/${EXTENSION_BUILD_SUBDIRECTORY}/${Slicer_THIRDPARTY_BIN_DIR}
      -DCMAKE_LIBRARY_OUTPUT_DIRECTORY:PATH=${CMAKE_BINARY_DIR}/${EXTENSION_BUILD_SUBDIRECTORY}/${Slicer_THIRDPARTY_LIB_DIR}
      -DCMAKE_ARCHIVE_OUTPUT_DIRECTORY:PATH=${CMAKE_ARCHIVE_OUTPUT_DIRECTORY}
      -DBUILD_SHARED_LIBS:BOOL=ON
      -DBUILD_DOCUMENTATION:BOOL=OFF
      -DCMAKE_CXX_COMPILER:FILEPATH=${CMAKE_CXX_COMPILER}
      -DCMAKE_CXX_FLAGS:STRING=${ep_common_cxx_flags}
      -DCMAKE_C_COMPILER:FILEPATH=${CMAKE_C_COMPILER}
      -DCMAKE_C_FLAGS:STRING=${ep_common_c_flags}
      -DCMAKE_INSTALL_PREFIX:PATH=${CMAKE_CURRENT_BINARY_DIR}/SlicerVmtk-build
      # installation location for the pypes/scripts
      -DVMTK_INSTALL_BIN_DIR:PATH=${Slicer_INSTALL_QTLOADABLEMODULES_PYTHON_LIB_DIR}/pypes
      -DVMTK_MODULE_INSTALL_LIB_DIR:PATH=${Slicer_INSTALL_QTLOADABLEMODULES_PYTHON_LIB_DIR}/pypes
      -DVMTK_SCRIPTS_INSTALL_BIN_DIR:PATH=${Slicer_INSTALL_QTLOADABLEMODULES_PYTHON_LIB_DIR}/pypes
      -DVMTK_SCRIPTS_INSTALL_LIB_DIR:PATH=${Slicer_INSTALL_QTLOADABLEMODULES_PYTHON_LIB_DIR}/pypes
      -DPYPES_INSTALL_BIN_DIR:PATH=${Slicer_INSTALL_QTLOADABLEMODULES_PYTHON_LIB_DIR}/pypes
      -DPYPES_MODULE_INSTALL_LIB_DIR:PATH=${Slicer_INSTALL_QTLOADABLEMODULES_PYTHON_LIB_DIR}/pypes
      -DVMTK_CONTRIB_SCRIPTS_INSTALL_LIB_DIR:PATH=${Slicer_INSTALL_QTLOADABLEMODULES_PYTHON_LIB_DIR}/pypes
      -DVMTK_CONTRIB_SCRIPTS_INSTALL_BIN_DIR:PATH=${Slicer_INSTALL_QTLOADABLEMODULES_PYTHON_LIB_DIR}/pypes
      # installation location for all vtkvmtk stuff
      -DVTK_VMTK_INSTALL_BIN_DIR:PATH=${Slicer_INSTALL_QTLOADABLEMODULES_BIN_DIR}
      -DVTK_VMTK_INSTALL_LIB_DIR:PATH=${Slicer_INSTALL_QTLOADABLEMODULES_LIB_DIR}
      -DVTK_VMTK_MODULE_INSTALL_LIB_DIR:PATH=${Slicer_INSTALL_QTLOADABLEMODULES_LIB_DIR}
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
      # macOS
      -DCMAKE_INSTALL_NAME_TOOL:FILEPATH=${CMAKE_INSTALL_NAME_TOOL}
      -DCMAKE_MACOSX_RPATH:BOOL=0
      # Options
      -DVMTK_USE_VTK9:BOOL=${VMTK_USE_VTK9}
      ${EXTERNAL_PROJECT_OPTIONAL_CMAKE_CACHE_ARGS}
    INSTALL_COMMAND ""
    DEPENDS
      ${${proj}_DEPENDS}
    )
  set(${proj}_DIR ${EP_BINARY_DIR})

  #-----------------------------------------------------------------------------
  # Launcher setting specific to build tree

  # NA

  #-----------------------------------------------------------------------------
  # Launcher setting specific to install tree

  # NA

else()
  ExternalProject_Add_Empty(${proj} DEPENDS ${${proj}_DEPENDS})
endif()

mark_as_superbuild(${proj}_DIR:PATH)

