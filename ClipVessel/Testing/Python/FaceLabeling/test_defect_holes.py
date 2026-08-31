import os
# The module lives three directories up from this file (ClipVessel/Testing/Python/FaceLabeling).
_MODULE_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
_MODULE_FILE = os.path.join(_MODULE_DIR, "ClipVessel.py")
"""A hole from a missing triangle must be filled into the face around it, not turned into a
face of its own. Mirrors the real case: two 3-cell caps that no clip point accounts for."""
import importlib.util, sys
import vtk, numpy as np
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy

spec = importlib.util.spec_from_file_location("CV", _MODULE_FILE)
mod = importlib.util.module_from_spec(spec); sys.modules["CV"] = mod; spec.loader.exec_module(mod)
logic = mod.ClipVesselLogic()

failures = []
def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"  {detail}" if detail else ""), flush=True)
    if not cond: failures.append(name)

def tube(nz=10, nTheta=20, drop=()):
    pts, polys = vtk.vtkPoints(), vtk.vtkCellArray()
    for k in range(nz):
        for t in range(nTheta):
            a = 2 * np.pi * t / nTheta
            pts.InsertNextPoint(np.cos(a), np.sin(a), 10.0 * k / (nz - 1))
    idx = 0
    for k in range(nz - 1):
        for t in range(nTheta):
            a0 = k * nTheta + t; a1 = k * nTheta + (t + 1) % nTheta
            for tri in ([a0, a1, a1 + nTheta], [a0, a1 + nTheta, a0 + nTheta]):
                if idx not in drop:
                    polys.InsertNextCell(3, tri)
                idx += 1
    pd = vtk.vtkPolyData(); pd.SetPoints(pts); pd.SetPolys(polys); return pd

specs = [{"index": 0, "label": "Inlet", "origin": (0.0, 0.0, 0.0), "normal": (0.0, 0.0, -1.0), "radius": 1.0},
         {"index": 1, "label": "Outlet", "origin": (0.0, 0.0, 10.0), "normal": (0.0, 0.0, 1.0), "radius": 1.0}]

def run(label, drop, existingValues=None):
    surface = tube(drop=drop)
    n = surface.GetNumberOfCells()
    existing = None
    if existingValues is not None:
        vals = existingValues(surface, n)
        arr = numpy_to_vtk(vals, deep=True, array_type=vtk.VTK_INT); arr.SetName("ModelFaceID")
        surface.GetCellData().AddArray(arr)
        existing = vals.astype(np.int64)
    capped = logic.capSurface(surface, logic.capBoundaryIdsArrayName)
    assignments = logic.labelModelFaces(capped, specs, "ModelFaceID", existing)
    ids = vtk_to_numpy(capped.GetCellData().GetArray("ModelFaceID"))
    hist = {int(k): int(v) for k, v in zip(*np.unique(ids, return_counts=True))}
    print(f"  [{label}] ids={hist} assignments={assignments} wall={logic.lastWallFaceId}", flush=True)
    return assignments, hist

print("1. clean tube: two caps, one per clip point")
a, hist = run("clean", ())
check("exactly two cap faces", len(a) == 2, a)
check("ids are wall + 2 caps", sorted(hist) == [1, 2, 3], sorted(hist))

print("2. one missing triangle: the fill joins the wall, no extra face")
a, hist = run("1 hole", (100,))
check("still exactly two cap faces", len(a) == 2, a)
check("no third face invented", sorted(hist) == [1, 2, 3], sorted(hist))
check("caps are the clip points", [l for _f, l in a] == ["Inlet", "Outlet"], a)

print("3. two missing triangles far apart, matching the real case")
a, hist = run("2 holes", (60, 300))
check("still exactly two cap faces", len(a) == 2, a)
check("no extra faces invented", sorted(hist) == [1, 2, 3], sorted(hist))

print("4. hole inside a pre-existing labelled patch: the fill joins THAT patch, not the wall")
def patchValues(surface, n):
    cc = vtk.vtkCellCenters(); cc.SetInputData(surface); cc.Update()
    z = vtk_to_numpy(cc.GetOutput().GetPoints().GetData())[:, 2]
    return np.where(z > 4.0, 7, 0).astype(np.int32)     # id 7 patch over the upper half
a, hist = run("hole in patch", (300,), patchValues)     # cell 300 lies in the upper half
check("patch 7 compacted to 1, wall 2, caps 3 and 4",
      logic.lastExistingFaceIdMap == {7: 1} and logic.lastWallFaceId == 2,
      (logic.lastExistingFaceIdMap, logic.lastWallFaceId))
check("still exactly two cap faces", len(a) == 2, a)
check("no extra face invented", sorted(hist) == [1, 2, 3, 4], sorted(hist))

print()
print("DEFECT_RESULT:", "FAILED " + str(failures) if failures else "ALL CHECKS PASSED")
