#-----------------------------------------------------------------------------
# Tests for Clip Vessel.
#
# Every one of these is a plain test file, not a scripted module. Building them as modules would
# put them in Slicer's module list, and would also stop SlicerPythonTestRunner collecting them:
# Slicer imports a scripted module at startup, so pytest finds the name already bound to the copy
# in the build tree and refuses the source file with an import file mismatch.
#
# They are named test_*.py so that pytest finds them with its own default pattern, which also
# keeps it away from the diagnostic scripts in this directory that are not tests and that do real
# work when imported.
#
# Each ends by running its own unittest suite and raising if anything failed, which is what
# slicer_add_python_test reports through the exit code. The same file is collected directly by
# pytest, so the two ways of running them agree.
#-----------------------------------------------------------------------------

# Logic only: no widget, no MRML display state
slicer_add_python_test(SCRIPT test_ClipVesselFaceLabels.py
                       SLICER_ARGS --disable-cli-modules)
slicer_add_python_test(SCRIPT test_ClipVesselCellOrder.py
                       SLICER_ARGS --disable-cli-modules)
slicer_add_python_test(SCRIPT test_ClipVesselCapMethods.py)
slicer_add_python_test(SCRIPT test_ClipVesselCapRemeshing.py)
slicer_add_python_test(SCRIPT test_ClipVesselDefectHoles.py
                       SLICER_ARGS --disable-cli-modules)

# These build the module widget
slicer_add_python_test(SCRIPT test_ClipVesselPreprocessingWarning.py
                       SLICER_ARGS --disable-cli-modules)
slicer_add_python_test(SCRIPT test_ClipVesselLegendLabels.py
                       SLICER_ARGS --disable-cli-modules)
slicer_add_python_test(SCRIPT test_ClipVesselWidget.py
                       SLICER_ARGS --disable-cli-modules)
slicer_add_python_test(SCRIPT test_ClipVesselPlaneEditingExit.py)
slicer_add_python_test(SCRIPT test_ClipVesselOutputNode.py)

# Preprocessing decimates through the CLI decimation module, so the CLI modules stay enabled
slicer_add_python_test(SCRIPT test_ClipVesselPreprocessLabels.py)

# Renders a 3D view, so every module stays enabled
slicer_add_python_test(SCRIPT test_ClipVesselFaceColoringVisible.py)

# Drives Apply end to end on a downloaded sample surface
slicer_add_python_test(SCRIPT test_ClipVesselApply.py)

# These work on a real vessel surface, built once each by ClipVesselTestFixture.py, which is
# deliberately not named test_*: it is imported by them rather than collected as a test itself.
slicer_add_python_test(SCRIPT test_ClipVesselLabelingEndToEnd.py)
slicer_add_python_test(SCRIPT test_ClipVesselBoundaryStages.py)
slicer_add_python_test(SCRIPT test_ClipVesselLabelPlacement.py)
slicer_add_python_test(SCRIPT test_ClipVesselClippingMethods.py)
slicer_add_python_test(SCRIPT test_ClipVesselCappingOnAVessel.py)
slicer_add_python_test(SCRIPT test_ClipVesselFlowExtensions.py)
