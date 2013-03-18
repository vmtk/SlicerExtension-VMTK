cmake_minimum_required(VERSION 2.8.9)

#-----------------------------------------------------------------------------
set(EXTENSION_NAME VMTKSlicerExtension)

#-----------------------------------------------------------------------------
set(EXTENSION_HOMEPAGE "http://slicer.vmtk.org/")
set(EXTENSION_CATEGORY "Vascular Modeling Toolkit")
set(EXTENSION_CONTRIBUTORS "Daniel Haehn (Boston Childrens Hospital), Luca Antiga (Orobix), Steve Pieper (Isomics)")
set(EXTENSION_DESCRIPTION "The Vascular Modeling Toolkit as a 3D Slicer4 extension.")
set(EXTENSION_STATUS "Beta")
set(EXTENSION_ICONURL "http://www.nitrc.org/project/screenshot.php?group_id=196&screenshot_id=269")
set(EXTENSION_SCREENSHOTURLS "http://www.nitrc.org/project/screenshot.php?group_id=196&screenshot_id=126 http://www.nitrc.org/project/screenshot.php?group_id=196&screenshot_id=227 http://www.nitrc.org/project/screenshot.php?group_id=196&screenshot_id=228 http://www.nitrc.org/project/screenshot.php?group_id=196&screenshot_id=229")
set(EXTENSION_DEPENDS "NA")
set(EXTENSION_BUILD_SUBDIRECTORY SlicerVmtk-build)
set(EXTENSION_LICENSE_FILE ${Slicer_LICENSE_FILE})
set(EXTENSION_README_FILE ${Slicer_README_FILE})

#-----------------------------------------------------------------------------
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

find_package(Git REQUIRED)

#-----------------------------------------------------------------------------
option(${EXTENSION_NAME}_SUPERBUILD "Build ${EXTENSION_NAME} and the projects it depends on via SuperBuild.cmake." ON)
mark_as_advanced(${EXTENSION_NAME}_SUPERBUILD)
if(${EXTENSION_NAME}_SUPERBUILD)
  include("${CMAKE_CURRENT_SOURCE_DIR}/SuperBuild.cmake")
  return()
endif()

#-----------------------------------------------------------------------------
add_subdirectory(LibraryModule)
add_subdirectory(PythonModules)

#-----------------------------------------------------------------------------
set(CPACK_INSTALL_CMAKE_PROJECTS "${CPACK_INSTALL_CMAKE_PROJECTS};${CMAKE_BINARY_DIR};${EXTENSION_NAME};ALL;/")
#set(CPACK_INSTALL_CMAKE_PROJECTS "${CPACK_INSTALL_CMAKE_PROJECTS};${VMTK_DIR};VMTK;RuntimeLibraries;/")
INCLUDE(${Slicer_EXTENSION_CPACK})
