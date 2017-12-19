cmake_minimum_required(VERSION 2.8.9)

#-----------------------------------------------------------------------------
project(SlicerVMTK)

#-----------------------------------------------------------------------------
set(EXTENSION_HOMEPAGE "https://github.com/vmtk/SlicerExtension-VMTK")
set(EXTENSION_CATEGORY "Vascular Modeling Toolkit")
set(EXTENSION_CONTRIBUTORS "Daniel Haehn (Boston Childrens Hospital), Luca Antiga (Orobix), Steve Pieper (Isomics), Jean-Christophe Fillion-Robin (Kitware)")
set(EXTENSION_DESCRIPTION "Vascular Modeling Toolkit for vessel tree segmentation and centerline extraction.")
set(EXTENSION_STATUS "Beta")
set(EXTENSION_ICONURL "http://www.nitrc.org/project/screenshot.php?group_id=196&screenshot_id=269")
set(EXTENSION_SCREENSHOTURLS "http://www.nitrc.org/project/screenshot.php?group_id=196&screenshot_id=126 http://www.nitrc.org/project/screenshot.php?group_id=196&screenshot_id=227 http://www.nitrc.org/project/screenshot.php?group_id=196&screenshot_id=228 http://www.nitrc.org/project/screenshot.php?group_id=196&screenshot_id=229")
set(EXTENSION_DEPENDS "NA")
set(EXTENSION_LICENSE_FILE ${Slicer_LICENSE_FILE})
set(EXTENSION_README_FILE ${Slicer_README_FILE})
set(EXTENSION_BUILD_SUBDIRECTORY inner-build)

set(SUPERBUILD_TOPLEVEL_PROJECT inner)

#-----------------------------------------------------------------------------
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})
mark_as_superbuild(Slicer_DIR)

find_package(Git REQUIRED)
mark_as_superbuild(GIT_EXECUTABLE)

#-----------------------------------------------------------------------------
option(${EXTENSION_NAME}_SUPERBUILD "Build ${EXTENSION_NAME} and the projects it depends on." ON)
mark_as_advanced(${EXTENSION_NAME}_SUPERBUILD)
if(${EXTENSION_NAME}_SUPERBUILD)
  include("${CMAKE_CURRENT_SOURCE_DIR}/SuperBuild.cmake")
  return()
endif()

#-----------------------------------------------------------------------------
add_subdirectory(VesselnessFiltering)
add_subdirectory(LevelSetSegmentation)
add_subdirectory(CenterlineComputation)

#-----------------------------------------------------------------------------
set(CPACK_INSTALL_CMAKE_PROJECTS "${CPACK_INSTALL_CMAKE_PROJECTS};${CMAKE_BINARY_DIR};${EXTENSION_NAME};ALL;/")
if(NOT APPLE)
  set(CPACK_INSTALL_CMAKE_PROJECTS "${CPACK_INSTALL_CMAKE_PROJECTS};${VMTK_DIR};VMTK;RuntimeLibraries;/")
endif()
set(CPACK_INSTALL_CMAKE_PROJECTS "${CPACK_INSTALL_CMAKE_PROJECTS};${VMTK_DIR};VMTK;PythonRuntimeLibraries;/")
set(CPACK_INSTALL_CMAKE_PROJECTS "${CPACK_INSTALL_CMAKE_PROJECTS};${VMTK_DIR};VMTK;RuntimeExecutables;/")
include(${Slicer_EXTENSION_CPACK})
