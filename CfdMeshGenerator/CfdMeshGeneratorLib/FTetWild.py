"""fTetWild, in whichever Python can run it.

fTetWild arrives as the pytetwild package, and the Python it is installed into is usually
Slicer's own. Not always: a Slicer built for Intel running under Rosetta on an Apple silicon
Mac has an x86_64 Python, and pytetwild ships no wheel for that. The processor can run an arm64
Python, though, so on such a machine a virtual environment is made on one - the system Python,
run as arm64, the way SlicerSimVascular's SDFStent module does it, or one fetched by uv where
the system has none new enough - pytetwild is installed into it, and fTetWild is run there.

Everything the pipeline asks of fTetWild goes through tetrahedralize(), which either imports
pytetwild here or hands the arrays to a second interpreter by file and runs this very module
there as a script: `python -I FTetWild.py input.npz output.npz arguments.json`. So the script
half of this file must get by on numpy and pytetwild alone.
"""

import functools
import importlib
import json
import os
import platform
import subprocess
import sys
import types

# What to install when fTetWild is asked for. Pinned rather than floating: the mesh a version
# gives is the mesh it gives, and a solver run is worth being able to repeat.
REQUIREMENT = "pytetwild==0.4.2"

# The Pythons pytetwild can be installed into (its requires-python), as an inclusive lower and
# an exclusive upper bound. What a Python found on the machine is measured against.
SUPPORTED_PYTHON_VERSIONS = ((3, 10), (3, 15))

# The Python uv is asked for when none on the machine will do. pytetwild ships an abi3 wheel
# from 3.12 on, so this is the oldest version whose wheel will still be there when a newer one
# is released.
PYTHON_VERSION = "3.12"

# Where an arm64 Python may be found on a Mac, in the order they are tried: the one the Xcode
# Command Line Tools install, then python.org's framework builds, newest first, then Homebrew's.
# Every one of them is a universal binary or a native one, so `arch -arm64` runs it as arm64.
MACOS_PYTHON_CANDIDATES = (
    "/usr/bin/python3",
    "/Library/Frameworks/Python.framework/Versions/3.*/bin/python3",
    "/opt/homebrew/bin/python3",
)

# Names an interpreter that has pytetwild installed, to run fTetWild in instead of whatever the
# module would choose. For anyone keeping an environment of their own, and for the tests.
PYTHON_ENVIRONMENT_VARIABLE = "SLICER_CFDMESHGENERATOR_FTETWILD_PYTHON"


class TetrahedralizationError(RuntimeError):
    """fTetWild ran and could not mesh the surface it was given. Everything else that can go
    wrong - no pytetwild, an interpreter that will not start - is a plain RuntimeError, because
    it says nothing about the surface."""


#
# Running it here.
#


def importPyTetWild():
    """The pytetwild module. Raises ImportError if it is not installed.

    The import is worth a wrapper of its own because pytetwild 0.4.2 imports pyvista at the top
    of its package - for an accessor it registers on pyvista's own classes - without guarding it,
    so importing pytetwild alone fails on an installation that has no pyvista. Installing pyvista
    to answer that would bring a second VTK into a process that already has one, which is a worse
    thing to be wrong about than a missing accessor, so an empty module stands in its place for
    the length of the import and is taken out again after.
    """
    stub = "pyvista" not in sys.modules
    if stub:
        sys.modules["pyvista"] = types.ModuleType("pyvista")
    try:
        return importlib.import_module("pytetwild")
    except ImportError:
        # A failed import can leave the half-built package behind, and a later import would then
        # hand back what it got to instead of trying again.
        for name in [name for name in sys.modules if name.split(".")[0] == "pytetwild"]:
            del sys.modules[name]
        raise
    finally:
        if stub:
            del sys.modules["pyvista"]


def tetrahedralize(vertices, faces, python=None, **arguments):
    """Fill the surface with tetrahedra: pytetwild.tetrahedralize, run wherever it can be.

    :param vertices: the points of the surface, as an (n, 3) float array.
    :param faces: the triangles of the surface, as an (m, 3) index array.
    :param python: the interpreter to run fTetWild in, or None for this process.
    :param arguments: what pytetwild.tetrahedralize is given, as it takes them.
    :return: (points, tetrahedra) arrays.
    :raises TetrahedralizationError: if fTetWild could not mesh the surface.
    :raises RuntimeError: if fTetWild could not be run at all.
    """
    if python is None:
        try:
            pytetwild = importPyTetWild()
        except ImportError as error:
            raise RuntimeError("fTetWild is not installed (%s)" % REQUIREMENT) from error
        try:
            return pytetwild.tetrahedralize(vertices, faces, **arguments)
        except Exception as error:
            raise TetrahedralizationError(str(error)) from error
    return _tetrahedralizeIn(python, vertices, faces, arguments)


#
# Running it elsewhere.
#

def _tetrahedralizeIn(python, vertices, faces, arguments):
    """tetrahedralize(), in another interpreter, by way of files in a directory of their own.

    The interpreter is a child of this process, so whoever stops this process - the module
    kills the worker's whole process tree - stops it too.
    """
    import tempfile

    import numpy as np

    with tempfile.TemporaryDirectory(prefix="CfdMeshGenerator-fTetWild-") as directory:
        inputPath = os.path.join(directory, "input.npz")
        outputPath = os.path.join(directory, "output.npz")
        argumentsPath = os.path.join(directory, "arguments.json")
        arrays = dict(vertices=vertices, faces=faces)
        for name in ("bg_vertices", "bg_tets", "bg_values"):
            if name in arguments:
                arrays[name] = np.asarray(arguments.pop(name))
        np.savez(inputPath, **arrays)
        with open(argumentsPath, "w") as argumentsFile:
            json.dump(arguments, argumentsFile)

        # -I: the interpreter is to see its own packages and nothing of this process's - not the
        # PYTHONPATH and PYTHONHOME Slicer's launcher sets, which point at the Python this process
        # runs on, and which the other one may not even be able to load.
        command = interpreterCommand(python) + [
            "-I", os.path.abspath(__file__), inputPath, outputPath, argumentsPath]
        process = subprocess.Popen(
            command, env=_cleanEnvironment(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            universal_newlines=True, **hiddenWindowArguments())
        output, _ = process.communicate()
        returnCode = process.returncode
        if output.strip():
            print(output.strip(), flush=True)
        if returnCode != 0 or not os.path.isfile(outputPath):
            raise RuntimeError("fTetWild could not be run in %s (exit code %s):\n%s"
                               % (python, returnCode, _tail(output)))
        with np.load(outputPath) as result:
            if "error" in result:
                raise TetrahedralizationError(str(result["error"]))
            return result["points"], result["tetrahedra"]


def _cleanEnvironment():
    """This process's environment without the variables that bind a Python to this one."""
    environment = dict(os.environ)
    for name in list(environment):
        if name.startswith("PYTHON") or name in (
                "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH", "QT_PLUGIN_PATH"):
            del environment[name]
    return environment


def hiddenWindowArguments():
    """Popen arguments that keep a console window from opening on Windows."""
    if os.name != "nt":
        return {}
    startupInfo = subprocess.STARTUPINFO()
    startupInfo.dwFlags = subprocess.STARTF_USESHOWWINDOW
    startupInfo.wShowWindow = subprocess.SW_HIDE
    return dict(startupinfo=startupInfo)


def _tail(output, lines=20):
    return "\n".join(output.strip().splitlines()[-lines:])


#
# Which interpreter, and how to get one.
#

# Interpreters found to have pytetwild, so that a probe - which starts a process - is not run
# again on every press of a button. An interpreter that has it keeps it; one that does not may
# be given it, so only the answer "yes" is kept.
_knownToHaveIt = set()


def isAvailable(python=None):
    """Whether fTetWild can be run in the given interpreter, or in this process for None."""
    if python is None:
        try:
            importPyTetWild()
        except ImportError:
            return False
        return True
    if python in _knownToHaveIt:
        return True
    if not os.path.isfile(python):
        return False
    try:
        completed = subprocess.run(
            interpreterCommand(python) + ["-I", "-c", "import pytetwild"], env=_cleanEnvironment(),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True,
            timeout=120, **hiddenWindowArguments())
    except (OSError, subprocess.SubprocessError):
        return False
    # pytetwild imports pyvista on its way in (see importPyTetWild) and a separate environment
    # has it; one made by hand may not, and is still able to run the script half of this file.
    available = completed.returncode == 0 or "No module named 'pyvista'" in completed.stdout
    if available:
        _knownToHaveIt.add(python)
    return available


def needsSeparateEnvironment():
    """Whether this process's Python cannot host pytetwild, so that fTetWild has to be run in
    another: an Intel build running under Rosetta on an Apple silicon Mac, for which there is
    no wheel. The kernel is asked whether this process is being translated, as SDFStent asks."""
    return sys.platform == "darwin" and _runningUnderRosetta()


@functools.lru_cache(maxsize=None)
def _runningUnderRosetta():
    # Asked once: the answer does not change while the process runs, and it is asked for every
    # command that runs the interpreter.
    try:
        completed = subprocess.run(["sysctl", "-n", "sysctl.proc_translated"],
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   universal_newlines=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.stdout.strip() == "1"


def interpreterCommand(python):
    """The command that runs the given interpreter as the processor's own architecture.

    On a Mac under Rosetta, `arch -arm64` in front: a universal binary run from a translated
    process would otherwise come up as x86_64 like its parent, and a venv made on one is a
    symlink to it. Elsewhere the interpreter is run as it is.
    """
    if needsSeparateEnvironment():
        return ["arch", "-arm64", python]
    return [python]


def findSystemPython():
    """An arm64 Python on this Mac that pytetwild can be installed into, or None.

    The candidates are tried in order (MACOS_PYTHON_CANDIDATES), each run as arm64 and asked
    what it is; the first that runs, is arm64, and is of a version pytetwild supports is the
    one. The Command Line Tools Python is asked first because it is the one most Macs have,
    and passed over where it is too old, which at 3.9 it has been for some years.
    """
    import glob

    if sys.platform != "darwin":
        return None
    candidates = []
    for pattern in MACOS_PYTHON_CANDIDATES:
        if any(character in pattern for character in "*?["):
            candidates.extend(sorted(glob.glob(pattern), reverse=True))
        else:
            candidates.append(pattern)
    for candidate in candidates:
        if _isSupportedArm64Python(candidate):
            return candidate
    return None


def _isSupportedArm64Python(python):
    if not os.path.isfile(python):
        return False
    try:
        completed = subprocess.run(
            ["arch", "-arm64", python, "-I", "-c",
             "import platform, sys; print(platform.machine(), *sys.version_info[:2])"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True,
            timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    parts = completed.stdout.split()
    if completed.returncode != 0 or len(parts) != 3 or parts[0] != "arm64":
        return False
    version = (int(parts[1]), int(parts[2]))
    lowest, tooHigh = SUPPORTED_PYTHON_VERSIONS
    return lowest <= version < tooHigh


def hardwareArchitecture():
    """The processor's architecture as uv names it: aarch64 or x86_64."""
    if needsSeparateEnvironment():
        return "aarch64"
    machine = platform.machine().lower()
    return "aarch64" if machine in ("arm64", "aarch64") else "x86_64"


def pythonRequest():
    """The Python uv is asked for: the pinned version, for this operating system and the
    processor - which is not necessarily what this process runs as."""
    operatingSystem = {"darwin": "macos", "win32": "windows"}.get(sys.platform, "linux")
    return "cpython-%s-%s-%s-none" % (PYTHON_VERSION, operatingSystem, hardwareArchitecture())


def environmentPython(directory):
    """The interpreter of the environment kept in the given directory, whether or not it has
    been made yet."""
    if os.name == "nt":
        return os.path.join(directory, "venv", "Scripts", "python.exe")
    return os.path.join(directory, "venv", "bin", "python")


def venvCommands(directory, basePython):
    """The commands that make the environment on a Python already on the machine: the venv
    module of that Python, run as arm64, then pip in the venv it made. (arguments, environment
    variables) pairs, to be run in order."""
    venv = os.path.join(directory, "venv")
    return [
        (interpreterCommand(basePython) + ["-m", "venv", venv], {}),
        (interpreterCommand(environmentPython(directory)) + ["-m", "pip", "install", REQUIREMENT],
         {}),
    ]


def uvCommands(directory, uvExecutable):
    """The commands that make the environment where no Python on the machine will do: uv
    fetches one and makes the venv on it, then installs into that. (arguments, environment
    variables) pairs, to be run in order with the given uv.

    uv puts the CPython it fetches under the directory too, rather than wherever it keeps its
    own, so that the whole of what was installed is in one place to be deleted. It is told not
    to keep a cache for the same reason. The uv binary is run as itself rather than as
    `python -m uv`: run from inside a Python, uv counts that Python among the interpreters it
    may build on, whatever it is told to prefer, and Slicer's is the one this is getting away
    from.
    """
    environment = {
        "UV_PYTHON_INSTALL_DIR": os.path.join(directory, "python"),
        "UV_NO_CACHE": "1",
        # Not to be talked out of the interpreter asked for by one it finds on the machine.
        "UV_PYTHON_PREFERENCE": "only-managed",
    }
    venv = os.path.join(directory, "venv")
    return [
        ([uvExecutable, "venv", "--python", pythonRequest(), venv], environment),
        ([uvExecutable, "pip", "install", "--python", environmentPython(directory), REQUIREMENT],
         environment),
    ]


#
# The script half: fTetWild in an interpreter of its own.
#


def main(argv):
    """Read the surface, mesh it, write the result - or why there is none."""
    import numpy as np

    inputPath, outputPath, argumentsPath = argv[1:4]
    with open(argumentsPath) as argumentsFile:
        arguments = json.load(argumentsFile)
    with np.load(inputPath) as arrays:
        vertices = arrays["vertices"]
        faces = arrays["faces"]
        for name in ("bg_vertices", "bg_tets", "bg_values"):
            if name in arrays:
                arguments[name] = arrays[name]
    try:
        points, tetrahedra = tetrahedralize(vertices, faces, **arguments)
    except TetrahedralizationError as error:
        import traceback

        traceback.print_exc()
        np.savez(outputPath, error=np.array(str(error)))
        return 0
    np.savez(outputPath, points=points, tetrahedra=tetrahedra)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
