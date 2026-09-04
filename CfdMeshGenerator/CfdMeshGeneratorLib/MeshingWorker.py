"""Run the meshing pipeline in a process of its own.

    PythonSlicer -u MeshingWorker.py --input surface.vtp --parameters parameters.json
        --output-mesh mesh.vtu --output-surface surface.vtp --result result.json

The module runs its pipeline this way rather than in the application, for three reasons. A run
can be stopped: the application kills the process, where it could not interrupt a VTK filter.
A run that crashes - TetGen walks off the end of a surface it cannot fill and takes its process
with it - takes this process rather than the application, with everything in it. And fTetWild
can be run in a Python other than Slicer's where Slicer's cannot host it (see FTetWild).

What goes between the two is files: the surface and the parameters in, the mesh, the remeshed
surface and a result file out. The result file says whether the mesher managed to fill the
surface and, if the pipeline raised, what it raised; it is not written at all if the process
died, which is how the application tells a crash from a refusal. Progress goes up the pipe:
every step of the pipeline is announced on a line of its own under STEP_PREFIX, and everything
logged goes after it with its level in front, for the application to relay.
"""

import argparse
import json
import logging
import os
import sys
import traceback

# So that CfdMeshGeneratorLib can be imported wherever this is run from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vtk  # noqa: E402

from CfdMeshGeneratorLib.MeshingPipeline import MeshingPipeline  # noqa: E402

# What a line announcing a step of the pipeline starts with; see the module docstring.
STEP_PREFIX = "[step] "


def readSurface(path):
    reader = vtk.vtkXMLPolyDataReader()
    reader.SetFileName(path)
    reader.Update()
    return reader.GetOutput()


def write(path, dataObject):
    writer = (vtk.vtkXMLUnstructuredGridWriter() if dataObject.IsA("vtkUnstructuredGrid")
              else vtk.vtkXMLPolyDataWriter())
    writer.SetFileName(path)
    writer.SetInputData(dataObject)
    writer.SetDataModeToBinary()
    if not writer.Write():
        raise OSError("could not write %s" % path)


def writeResult(path, result):
    with open(path, "w") as resultFile:
        json.dump(result, resultFile)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--input", required=True, help="the surface to mesh, as a .vtp file")
    parser.add_argument("--parameters", required=True,
                        help="a JSON file holding the arguments of MeshingPipeline.generateMesh "
                             "under \"arguments\", and optionally the interpreter to run fTetWild "
                             "in under \"fTetWildPython\"")
    parser.add_argument("--output-mesh", required=True, help="where to write the mesh, as .vtu")
    parser.add_argument("--output-surface", required=True,
                        help="where to write the remeshed surface, as .vtp")
    parser.add_argument("--result", required=True, help="where to write the result JSON")
    options = parser.parse_args(argv)

    logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                        format="%(levelname)s: %(message)s")

    with open(options.parameters) as parametersFile:
        parameters = json.load(parametersFile)

    pipeline = MeshingPipeline()
    pipeline.fTetWildPython = parameters.get("fTetWildPython")
    pipeline.stepCallback = lambda step: print(STEP_PREFIX + step, flush=True)

    try:
        surface = readSurface(options.input)
        mesh, remeshedSurface = pipeline.generateMesh(surface, **parameters["arguments"])
        write(options.output_mesh, mesh)
        write(options.output_surface, remeshedSurface)
    except Exception as error:  # noqa: BLE001 - whatever it was, the application is told
        traceback.print_exc()
        writeResult(options.result, {
            "error": {"type": type(error).__name__, "message": str(error)}})
        return 1
    writeResult(options.result, {
        "tetrahedralizationFailed": pipeline.lastTetrahedralizationFailed})
    return 0


if __name__ == "__main__":
    sys.exit(main())
