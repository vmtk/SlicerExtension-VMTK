"""How a meshing run is carried out, away from the application.

The pipeline runs outside the application so that a run can be stopped and a mesher that crashes
takes nothing with it (see MeshingWorker). Where it runs depends on what the application is:

- in 3D Slicer, a PythonSlicer process of its own, which the event loop keeps turning around -
  the window stays alive, the log fills as the run talks, and Cancel can be pressed;
- in a web browser (SlicerWeb), a worker with a Python of its own, since a page cannot start
  programs; the page keeps drawing while the worker computes.

Both are started, say what they are doing, and end with a callback. Neither blocks the caller: what
the run leaves behind is read from its files when the callback says it has finished.
"""

import logging
import os
import sys

__all__ = ["MeshingRunner", "ProcessRunner", "WorkerJobRunner", "makeRunner"]


class MeshingRunner:
    """A run of the meshing worker: started, listened to, and stopped if it takes too long.

    :param argv: the worker and its arguments, as a command line.
    :param onLine: called with each line the run prints.
    :param onFinished: called with (returnCode, lastLines) when it ends; a returnCode other than 0
        means the run died, which is what a mesher that crashed on its input leaves behind.
    """

    #: Lines kept to show if the run dies without saying why.
    LAST_LINES = 30

    def __init__(self, argv, onLine=None, onFinished=None):
        self.argv = list(argv)
        self.onLine = onLine
        self.onFinished = onFinished
        self.cancelled = False
        self._lastLines = []

    def start(self):
        raise NotImplementedError

    def cancel(self):
        raise NotImplementedError

    @property
    def running(self):
        raise NotImplementedError

    # --- for subclasses
    def _line(self, line):
        self._lastLines.append(line)
        del self._lastLines[: max(0, len(self._lastLines) - self.LAST_LINES)]
        if self.onLine:
            self.onLine(line)

    def _finished(self, returnCode):
        if self.onFinished:
            self.onFinished(returnCode, "\n".join(self._lastLines))


class ProcessRunner(MeshingRunner):
    """The run in a process of its own (3D Slicer).

    slicer.util.launchConsoleProcess starts it and relays what it prints, line by line, in the
    thread the application runs in, where it is safe to touch the user interface. Nothing here
    waits for the process: the application is left to do what it likes meanwhile, which is what
    makes the run interruptible and the progress visible.
    """

    def __init__(self, argv, onLine=None, onFinished=None):
        super().__init__(argv, onLine, onFinished)
        self._process = None

    @property
    def running(self):
        return self._process is not None and self._process.poll() is None

    def start(self):
        import slicer
        import slicer.packaging

        # What stops the run (see cancel); asked for now, so that a press of Cancel does not have
        # to wait for an installation.
        slicer.packaging.pip_ensure("psutil", requester="CfdMeshGenerator")
        environment = {
            # The worker imports the wrapped VMTK classes and this module's own package from
            # wherever this process found them, which an extension built rather than installed
            # passes to the application on its command line and not in the environment.
            "PYTHONPATH": os.pathsep.join(
                [path for path in sys.path if path and os.path.isdir(path)]
                + [path for path in os.environ.get("PYTHONPATH", "").split(os.pathsep) if path]),
            # VTK, built to report leaks, reports them at exit in a dialog on Windows, and a dialog
            # in a process with no window to show it in is a process that never exits. This is the
            # switch that has it write them to stderr instead, where they are relayed like the rest.
            "DASHBOARD_TEST_FROM_CTEST": "1",
        }
        self._process = slicer.util.launchConsoleProcess(
            self.argv, useStartupEnvironment=False, updateEnvironment=environment,
            blocking=False, logCallback=self._line, completedCallback=self._onCompleted)

    def _onCompleted(self, returnCode):
        self._process = None
        self._finished(returnCode)

    def cancel(self):
        import psutil

        process = self._process
        if process is None or process.poll() is not None:
            return
        self.cancelled = True
        # PythonSlicer is a launcher that runs the worker's Python as a process of its own, and
        # the worker may have an interpreter of its own running fTetWild under it: the whole tree
        # is stopped, the processes under the launcher first, so that none is left running
        # without the one that started it. process.kill() would only stop the launcher.
        try:
            launcher = psutil.Process(process.pid)
            processes = launcher.children(recursive=True) + [launcher]
        except psutil.NoSuchProcess:
            return
        for running in processes:
            try:
                running.kill()
            except psutil.NoSuchProcess:
                pass


class WorkerJobRunner(MeshingRunner):
    """The run in a worker of the page (SlicerWeb).

    A web page cannot start a program, but it can start a worker with a Python of its own and the
    same packages; the files of the run are handed over and what it writes comes back. What the
    worker prints arrives line by line, as it does from a process.
    """

    def __init__(self, argv, onLine=None, onFinished=None, files=None, outputs=None):
        super().__init__(argv, onLine, onFinished)
        self.files = dict(files or {})     # path -> bytes, written before the run
        self.outputs = list(outputs or [])  # paths read back after it
        self.returnedFiles = {}
        self._running = False

    @property
    def running(self):
        return self._running

    def start(self):
        from slicerweb import jobs

        # The worker runs the same script the process would, with the same command line.
        code = (
            "import runpy, sys\n"
            "import slicerweb_job as job\n"
            "class _Out:\n"
            "    def write(self, text):\n"
            "        for line in text.splitlines():\n"
            "            if line:\n"
            "                job.log('INFO', line)\n"
            "        return len(text)\n"
            "    def flush(self):\n"
            "        pass\n"
            "sys.argv = list(argv)\n"
            "sys.stdout = sys.stderr = _Out()\n"
            "try:\n"
            "    runpy.run_path(argv[0], run_name='__main__')\n"
            "except SystemExit as exit:\n"
            "    result = int(exit.code or 0)\n"
            "else:\n"
            "    result = 0\n"
        )
        # The command line of the process form is [python, -u, script, ...]: the worker is already
        # a Python, so it runs the script with the arguments that follow it.
        argv = [argument for argument in self.argv if argument != "-u"][1:]
        self._running = True
        jobs.run(
            code,
            globals={"argv": argv},
            files=self.files,
            outputs=self.outputs,
            onDone=self._onDone,
            onFailed=self._onFailed,
            onProgress=lambda message, fraction: self._line(message),
            onLog=lambda level, message: self._line(message),
        )

    def _onDone(self, result, files):
        self._running = False
        self.returnedFiles = files
        self._finished(int(result or 0))

    def _onFailed(self, message):
        self._running = False
        self._line(str(message))
        self._finished(1)

    def cancel(self):
        from slicerweb import jobs

        self.cancelled = True
        self._running = False
        jobs.cancel()
        self._finished(1)


def inBrowser():
    """Whether this application is a web page (SlicerWeb) rather than desktop 3D Slicer."""
    try:
        from slicerweb import jobs
    except ImportError:
        return False
    return jobs.available()


def makeRunner(argv, onLine=None, onFinished=None, files=None, outputs=None):
    """The runner this application can use: a process, or a worker in a browser."""
    if inBrowser():
        return WorkerJobRunner(argv, onLine, onFinished, files=files, outputs=outputs)
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug("Meshing runs in a process: %s", " ".join(argv))
    return ProcessRunner(argv, onLine, onFinished)
