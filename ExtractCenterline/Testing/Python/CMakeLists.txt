#-----------------------------------------------------------------------------
# Tests for centerline extraction.
#
# Every one of these is a plain test file, not a scripted module. Building them as modules would
# put them in Slicer's module list, and would also stop SlicerPythonTestRunner collecting them:
# Slicer imports a scripted module at startup, so pytest finds the name already bound to the copy
# in the build tree and refuses the source file with an import file mismatch.
#
# They are named test_*.py so that pytest finds them with its own default pattern, which also
# keeps it away from ExtractCenterlineTestFixture.py - imported by them rather than collected.
#
# Each ends by running its own unittest suite and raising if anything failed, which is what
# slicer_add_python_test reports through the exit code. The same file is collected directly by
# pytest, so the two ways of running them agree.
#
# All three work on the sample vessel, decimated once per process by ExtractCenterlineTestFixture.
# Preprocessing decimates through the CLI decimation module, so the CLI modules stay enabled.
#-----------------------------------------------------------------------------

slicer_add_python_test(SCRIPT test_ExtractCenterlinePreprocessing.py)
slicer_add_python_test(SCRIPT test_ExtractCenterlineNetwork.py)
slicer_add_python_test(SCRIPT test_ExtractCenterlineCenterline.py)
