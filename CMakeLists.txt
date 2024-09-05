cmake_minimum_required(VERSION 3.13.4)

project(SlicerVMTK)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://github.com/vmtk/SlicerExtension-VMTK")
set(EXTENSION_CATEGORY "Vascular Modeling Toolkit")
set(EXTENSION_CONTRIBUTORS "Daniel Haehn (Boston Childrens Hospital), Luca Antiga (Orobix), Steve Pieper (Isomics), Jean-Christophe Fillion-Robin (Kitware)")
set(EXTENSION_DESCRIPTION "Vascular Modeling Toolkit for vessel tree segmentation and centerline extraction.")
set(EXTENSION_STATUS "Beta")
set(EXTENSION_ICONURL "https://www.nitrc.org/project/screenshot.php?group_id=196&screenshot_id=269")
set(EXTENSION_SCREENSHOTURLS "https://www.nitrc.org/project/screenshot.php?group_id=196&screenshot_id=126 https://www.nitrc.org/project/screenshot.php?group_id=196&screenshot_id=227 https://www.nitrc.org/project/screenshot.php?group_id=196&screenshot_id=228 https://www.nitrc.org/project/screenshot.php?group_id=196&screenshot_id=229")
set(EXTENSION_DEPENDS "ExtraMarkups")
set(EXTENSION_LICENSE_FILE ${Slicer_LICENSE_FILE})
set(EXTENSION_README_FILE ${Slicer_README_FILE})
set(EXTENSION_BUILD_SUBDIRECTORY inner-build)

set(SUPERBUILD_TOPLEVEL_PROJECT inner)

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})
mark_as_superbuild(Slicer_DIR)

find_package(Git REQUIRED)
mark_as_superbuild(GIT_EXECUTABLE)

option(SlicerVMTK_USE_ExtraMarkups
  "This needs to be disabled when this extension is bundled with Slicer" ON)

if(SlicerVMTK_USE_ExtraMarkups)
  find_package(ExtraMarkups REQUIRED)
  mark_as_superbuild(ExtraMarkups_DIR)
endif()

#-----------------------------------------------------------------------------
# SuperBuild setup
option(${EXTENSION_NAME}_SUPERBUILD "Build ${EXTENSION_NAME} and the projects it depends on." ON)
mark_as_advanced(${EXTENSION_NAME}_SUPERBUILD)
if(${EXTENSION_NAME}_SUPERBUILD)
  include("${CMAKE_CURRENT_SOURCE_DIR}/SuperBuild.cmake")
  return()
endif()

find_package(VMTK REQUIRED)

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(VesselnessFiltering)
add_subdirectory(LevelSetSegmentation)
if(${Slicer_VERSION_MAJOR}.${Slicer_VERSION_MINOR} VERSION_GREATER_EQUAL 4.11)
  # New-generation centerline computation - only available for recent Slicer versions
  add_subdirectory(ExtractCenterline)
else()
  add_subdirectory(CenterlineComputation)
endif()
add_subdirectory(CrossSectionAnalysis)
add_subdirectory(QuickArterySegmentation)
add_subdirectory(GuidedArterySegmentation)
add_subdirectory(GuidedVeinSegmentation)
add_subdirectory(StenosisMeasurement1D)
add_subdirectory(StenosisMeasurement2D)
if(SlicerVMTK_USE_ExtraMarkups)
  add_subdirectory(StenosisMeasurement3D)
endif()
add_subdirectory(BranchClipper)
add_subdirectory(ArterialCalcificationPreProcessor)
add_subdirectory(CenterlineDisassembly)

#-----------------------------------------------------------------------------
set(EXTENSION_CPACK_INSTALL_CMAKE_PROJECTS)
if(NOT APPLE)
  list(APPEND EXTENSION_CPACK_INSTALL_CMAKE_PROJECTS "${VMTK_DIR};VMTK;RuntimeLibraries;/")
endif()
list(APPEND EXTENSION_CPACK_INSTALL_CMAKE_PROJECTS "${VMTK_DIR};VMTK;PythonRuntimeLibraries;/")
list(APPEND EXTENSION_CPACK_INSTALL_CMAKE_PROJECTS "${VMTK_DIR};VMTK;RuntimeExecutables;/")
set(${EXTENSION_NAME}_CPACK_INSTALL_CMAKE_PROJECTS "${EXTENSION_CPACK_INSTALL_CMAKE_PROJECTS}" CACHE STRING "List of external projects to install" FORCE)

#-----------------------------------------------------------------------------
list(APPEND CPACK_INSTALL_CMAKE_PROJECTS "${CMAKE_BINARY_DIR};${EXTENSION_NAME};ALL;/")
list(APPEND CPACK_INSTALL_CMAKE_PROJECTS "${${EXTENSION_NAME}_CPACK_INSTALL_CMAKE_PROJECTS}")
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})

