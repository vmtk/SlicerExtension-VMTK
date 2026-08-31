import os
# The module lives three directories up from this file (ClipVessel/Testing/Python/FaceLabeling).
_MODULE_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
_MODULE_FILE = os.path.join(_MODULE_DIR, "ClipVessel.py")
"""Hypothesis: if the pre-cap surface holds any vert/line cells, they occupy the LOW cell
indices (polydata order is verts, lines, polys, strips) while vtkvmtkCapPolyData copies only
GetPolys(). Index-based alignment of the captured labels then shifts by that count."""
import importlib.util, sys
import vtk, numpy as np
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy

spec = importlib.util.spec_from_file_location("CV", _MODULE_FILE)
mod = importlib.util.module_from_spec(spec); sys.modules["CV"] = mod; spec.loader.exec_module(mod)
logic = mod.ClipVesselLogic()
failures = []

def openTube(nz=8, nTheta=20, height=10.0, radius=1.0, nVerts=0, nLines=0):
    pts, polys = vtk.vtkPoints(), vtk.vtkCellArray()
    verts, lines = vtk.vtkCellArray(), vtk.vtkCellArray()
    for k in range(nz):
        z = height * k / (nz - 1)
        for t in range(nTheta):
            a = 2 * np.pi * t / nTheta
            pts.InsertNextPoint(radius * np.cos(a), radius * np.sin(a), z)
    for k in range(nz - 1):
        for t in range(nTheta):
            a0 = k * nTheta + t; a1 = k * nTheta + (t + 1) % nTheta
            polys.InsertNextCell(3, [a0, a1, a1 + nTheta]); polys.InsertNextCell(3, [a0, a1 + nTheta, a0 + nTheta])
    pd = vtk.vtkPolyData(); pd.SetPoints(pts); pd.SetPolys(polys)
    for i in range(nVerts):
        verts.InsertNextCell(1, [i])
    for i in range(nLines):
        lines.InsertNextCell(2, [i, i + 1])
    if nVerts: pd.SetVerts(verts)
    if nLines: pd.SetLines(lines)
    return pd

specs = [{"index": 0, "label": "Inlet", "origin": (0.0, 0.0, 0.0), "normal": (0.0, 0.0, -1.0), "radius": 1.0},
         {"index": 1, "label": "Outlet", "origin": (0.0, 0.0, 10.0), "normal": (0.0, 0.0, 1.0), "radius": 1.0}]

def centroids(pd):
    cc = vtk.vtkCellCenters(); cc.SetInputData(pd); cc.Update()
    return vtk_to_numpy(cc.GetOutput().GetPoints().GetData())

for nVerts, nLines in [(0, 0), (1, 0), (0, 1), (3, 2)]:
    surface = openTube(nVerts=nVerts, nLines=nLines)
    nCells = surface.GetNumberOfCells()
    nPolys = surface.GetPolys().GetNumberOfCells()
    # Label a localised patch geometrically: the poly cells with z above the midpoint.
    cent = centroids(surface)
    patch = cent[:, 2] > 7.0
    vals = np.where(patch, 3, 1).astype(np.int32)
    arr = numpy_to_vtk(vals, deep=True, array_type=vtk.VTK_INT); arr.SetName("ModelFaceID")
    surface.GetCellData().AddArray(arr)

    existing = vtk_to_numpy(surface.GetCellData().GetArray("ModelFaceID")).astype(np.int64).copy()
    firstPoly = surface.GetNumberOfVerts() + surface.GetNumberOfLines()
    existing = existing[firstPoly:firstPoly + surface.GetNumberOfPolys()]
    capped = logic.capSurface(surface, logic.capBoundaryIdsArrayName)
    assignments = logic.labelModelFaces(capped, specs, "ModelFaceID", existing)
    outIds = vtk_to_numpy(capped.GetCellData().GetArray("ModelFaceID"))
    outCent = centroids(capped)
    capIds = {f for f, _l in assignments}
    # face 2 is the compacted former id 3; it must still be the z>7 cells
    isFace2 = outIds == 2
    shouldBe = outCent[:, 2] > 7.0
    notCap = ~np.isin(outIds, list(capIds))
    wrong = int(np.count_nonzero((isFace2 != shouldBe) & notCap))
    tot = int(notCap.sum())
    ok = (wrong == 0 and logic.lastExistingFaceIdMap == {1: 1, 3: 2} and logic.lastWallFaceId is None)
    print(("  PASS  " if ok else "  FAIL  ") +
          f"verts={nVerts} lines={nLines}: misplaced {wrong}/{tot} "
          f"remap={logic.lastExistingFaceIdMap} wall={logic.lastWallFaceId}", flush=True)
    if not ok:
        failures.append(f"verts={nVerts} lines={nLines}")

print()
print("CELLORDER_RESULT:", "FAILED " + str(failures) if failures else "ALL CHECKS PASSED")
