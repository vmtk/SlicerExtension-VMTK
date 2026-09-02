"""Applies to every test collected from this directory, however it is collected.

SlicerPythonTestRunner spawns an instance of the application binary per test file, which inherits
the launcher's environment but not the module paths the launcher was given, so the ClipVessel
module is importable there but not registered. The tests that build the module's widget need it
registered. Doing it here covers every test in one place; the tests that need it ask for it
themselves as well, so that they also work when run one at a time outside pytest.
"""

from ClipVesselTestFixture import ensureClipVesselModuleRegistered

ensureClipVesselModuleRegistered()
