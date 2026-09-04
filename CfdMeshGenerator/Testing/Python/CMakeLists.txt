#-----------------------------------------------------------------------------
# Tests for the meshing pipeline.
#
# Every one of these is a plain test file, not a scripted module. Building them as modules would
# put them in Slicer's module list, and would also stop SlicerPythonTestRunner collecting them:
# Slicer imports a scripted module at startup, so pytest finds the name already bound to the copy
# in the build tree and refuses the source file with an import file mismatch.
#
# They are named test_*.py so that pytest finds them with its own default pattern, which also
# keeps it away from CfdMeshGeneratorTestFixture.py - imported by them rather than collected.
#
# Each ends by running its own unittest suite and raising if anything failed, which is what
# slicer_add_python_test reports through the exit code. The same file is collected directly by
# pytest, so the two ways of running them agree.
#-----------------------------------------------------------------------------

# Logic only: no widget, no MRML display state
slicer_add_python_test(SCRIPT test_CfdMeshGeneratorMeshing.py
                       SLICER_ARGS --disable-cli-modules)
slicer_add_python_test(SCRIPT test_CfdMeshGeneratorBoundaryLayer.py
                       SLICER_ARGS --disable-cli-modules)
slicer_add_python_test(SCRIPT test_CfdMeshGeneratorFaceIds.py
                       SLICER_ARGS --disable-cli-modules)
slicer_add_python_test(SCRIPT test_CfdMeshGeneratorFTetWild.py
                       SLICER_ARGS --disable-cli-modules)

# Works on the clipped aorta of VMTK's test data, which lives in the build tree; the test says so
# and skips where it is not there.
slicer_add_python_test(SCRIPT test_CfdMeshGeneratorClippedAorta.py
                       SLICER_ARGS --disable-cli-modules)

# Runs the pipeline in a process of its own, the way Apply does
slicer_add_python_test(SCRIPT test_CfdMeshGeneratorSeparateProcess.py
                       SLICER_ARGS --disable-cli-modules)

# Builds the module widget
slicer_add_python_test(SCRIPT test_CfdMeshGeneratorWidget.py
                       SLICER_ARGS --disable-cli-modules)
