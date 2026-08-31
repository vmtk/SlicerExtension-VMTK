import os
# The module lives three directories up from this file (ClipVessel/Testing/Python/FaceLabeling).
_MODULE_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
_MODULE_FILE = os.path.join(_MODULE_DIR, "ClipVessel.py")
import sys, types
sys.modules.setdefault("vtkvmtkComputationalGeometryPython",
                       types.ModuleType("vtkvmtkComputationalGeometryPython"))
sys.path.insert(0, _MODULE_DIR)

import vtk
import numpy as np
from vtk.util.numpy_support import vtk_to_numpy, numpy_to_vtk
import ClipVessel

logic = ClipVessel.ClipVesselLogic()
failures = []

def check(name, condition, detail=""):
    print(("  PASS  " if condition else "  FAIL  ") + name + (f"  {detail}" if detail else ""))
    if not condition:
        failures.append(name)

def makeSurface(cellCentroids, capBoundaryIds=None, existingFaceIds=None):
    """One small independent triangle per requested centroid, mimicking a capped surface:
    capBoundaryIds is what capSurface writes into the private array (0 = came from the input,
    i+1 = the cap that closed boundary i).

    Returns (surface, existingForCall). existingForCall is existingFaceIds trimmed to the cells
    that came from the input, which is what clipVessel passes: it reads those values off the
    surface *before* capping, so the array it hands over is shorter than the capped output. The
    capper drops all other cell data, so on a capped surface the face id array is genuinely
    absent - only the uncapped case still carries it.
    """
    points, polys = vtk.vtkPoints(), vtk.vtkCellArray()
    for centroid in cellCentroids:
        centroid = np.asarray(centroid, dtype=float)
        offsets = np.array([[0.02, 0.0, 0.0], [-0.01, 0.02, 0.0], [-0.01, -0.02, 0.0]])
        polys.InsertNextCell(3, [points.InsertNextPoint(*(centroid + o)) for o in offsets])
    surface = vtk.vtkPolyData(); surface.SetPoints(points); surface.SetPolys(polys)
    existingForCall = None if existingFaceIds is None else np.asarray(existingFaceIds, dtype=np.int64)
    if capBoundaryIds is not None:
        arr = numpy_to_vtk(np.asarray(capBoundaryIds, dtype=np.int64), deep=True, array_type=vtk.VTK_ID_TYPE)
        arr.SetName(logic.capBoundaryIdsArrayName)
        surface.GetCellData().AddArray(arr)
        if existingForCall is not None:
            inputCellCount = int(np.count_nonzero(np.asarray(capBoundaryIds) == 0))
            existingForCall = existingForCall[:inputCellCount]
    elif existingForCall is not None:
        # Uncapped: the array is still on the surface, so exercise the read-it-back path.
        arr = numpy_to_vtk(np.asarray(existingFaceIds, dtype=np.int32), deep=True, array_type=vtk.VTK_INT)
        arr.SetName("ModelFaceID")
        surface.GetCellData().AddArray(arr)
        existingForCall = None
    return surface, existingForCall

def spec(index, label, origin, normal):
    return {"index": index, "label": label, "origin": tuple(origin), "normal": tuple(normal), "radius": 1.0}

def ids(surface, name="ModelFaceID"):
    return list(vtk_to_numpy(surface.GetCellData().GetArray(name)))

INLET_OUTLET = [spec(0, "Inlet", (0, 0, 0), (0, 0, -1)), spec(1, "Outlet", (0, 0, 10), (0, 0, 1))]

print("1. _distanceToRay")
d = ClipVessel._distanceToRay
check("on the ray, far along it", abs(d((0, 0, -6), (0, 0, 0), (0, 0, -1))) < 1e-12)
check("off to the side", abs(d((3, 0, -6), (0, 0, 0), (0, 0, -1)) - 3.0) < 1e-12)
check("behind the ray start", abs(d((0, 0, 4), (0, 0, 0), (0, 0, -1)) - 4.0) < 1e-12)

print("2. no pre-existing labels: wall=1, caps follow clip point order")
# Cap boundary ids deliberately in the opposite order to the clip points.
s, existing = makeSurface([(0, 0, 5), (0, 0, 5), (0, 0, 5), (0, 0, 0), (0, 0, 10)], [0, 0, 0, 2, 1])
a = logic.labelModelFaces(s, INLET_OUTLET, "ModelFaceID", existing)
check("wall cells are 1", ids(s)[:3] == [1, 1, 1], ids(s)[:3])
check("inlet cap (boundary 2) -> 2", ids(s)[3] == 2, ids(s)[3])
check("outlet cap (boundary 1) -> 3", ids(s)[4] == 3, ids(s)[4])
check("wall id reported", logic.lastWallFaceId == 1, logic.lastWallFaceId)
check("no existing remap", logic.lastExistingFaceIdMap == {}, logic.lastExistingFaceIdMap)
check("assignments", a == [(2, "Inlet"), (3, "Outlet")], a)
check("array is vtkIntArray", s.GetCellData().GetArray("ModelFaceID").IsA("vtkIntArray"))
check("active scalars set", s.GetCellData().GetScalars().GetName() == "ModelFaceID")
check("private array removed", s.GetCellData().GetArray(logic.capBoundaryIdsArrayName) is None)

print("3. THE BUG: a pre-existing face whose id collides with a cap id")
# Patch at id 2 on part of the wall; the inlet cap would previously have been fused into it.
s, existing = makeSurface([(0, 0, 5), (0, 0, 5), (0, 0, 5), (0, 0, 0), (0, 0, 10)],
                [0, 0, 0, 1, 2], [2, 2, 0, 0, 0])
a = logic.labelModelFaces(s, INLET_OUTLET, "ModelFaceID", existing)
check("existing face 2 compacted to 1", logic.lastExistingFaceIdMap == {2: 1}, logic.lastExistingFaceIdMap)
check("patch cells are 1", ids(s)[:2] == [1, 1], ids(s)[:2])
check("wall is 2", ids(s)[2] == 2 and logic.lastWallFaceId == 2, (ids(s)[2], logic.lastWallFaceId))
check("inlet cap is 3, not fused", ids(s)[3] == 3, ids(s)[3])
check("outlet cap is 4", ids(s)[4] == 4, ids(s)[4])
check("assignments", a == [(3, "Inlet"), (4, "Outlet")], a)
check("every face is distinct", len(set(ids(s))) == 4, sorted(set(ids(s))))

print("4. the user's case: a lone patch at id 10 -> 1, wall 2, first cap 3")
s, existing = makeSurface([(0, 0, 5), (0, 0, 5), (0, 0, 0), (0, 0, 10)], [0, 0, 1, 2], [10, 0, 0, 0])
a = logic.labelModelFaces(s, INLET_OUTLET, "ModelFaceID", existing)
check("10 -> 1", logic.lastExistingFaceIdMap == {10: 1}, logic.lastExistingFaceIdMap)
check("wall = 2", logic.lastWallFaceId == 2, logic.lastWallFaceId)
check("layout is [1, 2, 3, 4]", ids(s) == [1, 2, 3, 4], ids(s))
check("first cap = 3", a[0] == (3, "Inlet"), a)

print("5. several pre-existing faces compact in ascending order of original id")
s, existing = makeSurface([(0, 0, 5), (0, 0, 5), (0, 0, 5), (0, 0, 5), (0, 0, 0), (0, 0, 10)],
                [0, 0, 0, 0, 1, 2], [50, 7, 22, 0, 0, 0])
a = logic.labelModelFaces(s, INLET_OUTLET, "ModelFaceID", existing)
check("7->1, 22->2, 50->3", logic.lastExistingFaceIdMap == {7: 1, 22: 2, 50: 3}, logic.lastExistingFaceIdMap)
check("cells remapped correctly", ids(s)[:4] == [3, 1, 2, 4], ids(s)[:4])
check("wall = 4", logic.lastWallFaceId == 4, logic.lastWallFaceId)
check("caps = 5, 6", a == [(5, "Inlet"), (6, "Outlet")], a)

print("6. input already labels every cell: no wall id set aside, caps follow immediately")
s, existing = makeSurface([(0, 0, 5), (0, 0, 5), (0, 0, 0)], [0, 0, 1], [1, 4, 0])
a = logic.labelModelFaces(s, [spec(0, "Inlet", (0, 0, 0), (0, 0, -1))], "ModelFaceID", existing)
check("1->1, 4->2", logic.lastExistingFaceIdMap == {1: 1, 4: 2}, logic.lastExistingFaceIdMap)
check("no wall face", logic.lastWallFaceId is None, logic.lastWallFaceId)
check("cap takes the next id, 3 not 4", a == [(3, "Inlet")], a)
check("ids contiguous, no phantom face", sorted(set(ids(s))) == [1, 2, 3], sorted(set(ids(s))))

print("6b. mis-sized existing labels are dropped, never smeared onto the wrong cells")
s, _ignored = makeSurface([(0, 0, 5), (0, 0, 5), (0, 0, 0)], [0, 0, 1])
a = logic.labelModelFaces(s, [spec(0, "Inlet", (0, 0, 0), (0, 0, -1))], "ModelFaceID",
                          np.array([7, 7, 7, 7, 7], dtype=np.int64))   # 5 values, 2 non-cap cells
check("dropped, not applied", logic.lastExistingFaceIdMap == {}, logic.lastExistingFaceIdMap)
check("still labels wall and cap", ids(s) == [1, 1, 2], ids(s))
check("cap assignment intact", a == [(2, "Inlet")], a)

print("7. non-positive ids count as unlabeled")
s, existing = makeSurface([(0, 0, 5), (0, 0, 5), (0, 0, 0)], [0, 0, 1], [0, -3, 0])
logic.labelModelFaces(s, [spec(0, "Inlet", (0, 0, 0), (0, 0, -1))], "ModelFaceID", existing)
check("0 and -3 both treated as wall", ids(s)[:2] == [1, 1], ids(s)[:2])
check("no existing remap", logic.lastExistingFaceIdMap == {}, logic.lastExistingFaceIdMap)

print("8. flow extensions: cap far from its plane, with pre-existing labels too")
# Trunk cap 6 down from its plane; side branch origin only 1 away from that cap.
s, existing = makeSurface([(0, 0, 5), (0, 0, 4), (0, 0, -6), (6, 0, -5)], [0, 0, 1, 2], [9, 0, 0, 0])
a = logic.labelModelFaces(s, [spec(0, "Trunk", (0, 0, 0), (0, 0, -1)),
                              spec(1, "Branch", (0, 0, -5), (1, 0, 0))], "ModelFaceID", existing)
check("9 -> 1", logic.lastExistingFaceIdMap == {9: 1}, logic.lastExistingFaceIdMap)
check("wall = 2", logic.lastWallFaceId == 2, logic.lastWallFaceId)
check("trunk cap = 3 (not claimed by Branch)", ids(s)[2] == 3, ids(s)[2])
check("branch cap = 4", ids(s)[3] == 4, ids(s)[3])
check("assignments", a == [(3, "Trunk"), (4, "Branch")], a)

print("9. uncapped surface (no private array)")
s, existing = makeSurface([(0, 0, 0), (0, 0, 1)], None, [10, 0])
a = logic.labelModelFaces(s, [spec(0, "Inlet", (0, 0, 0), (0, 0, -1))], "ModelFaceID", existing)
check("existing still compacted", logic.lastExistingFaceIdMap == {10: 1}, logic.lastExistingFaceIdMap)
check("layout is [1, 2]", ids(s) == [1, 2], ids(s))
check("no cap assignments", a == [], a)

print("10. clip point with no cap leaves its id unused")
s, existing = makeSurface([(0, 0, 5), (0, 0, 0), (0, 0, 20)], [0, 1, 2])
a = logic.labelModelFaces(s, [spec(0, "First", (0, 0, 0), (0, 0, -1)),
                              spec(1, "NoCut", (0, 0, 10), (1, 0, 0)),
                              spec(2, "Third", (0, 0, 20), (0, 0, 1))], "ModelFaceID", existing)
check("first cap = 2, third cap = 4 (3 unused)", ids(s)[1:] == [2, 4], ids(s)[1:])
check("assignments", a == [(2, "First"), (4, "Third")], a)

print("11. custom array name")
s, existing = makeSurface([(0, 0, 5), (0, 0, 0)], [0, 1], None)
logic.labelModelFaces(s, [spec(0, "Inlet", (0, 0, 0), (0, 0, -1))], "CellEntityIds", existing)
check("written under the given name", ids(s, "CellEntityIds") == [1, 2], ids(s, "CellEntityIds"))
check("no ModelFaceID created", s.GetCellData().GetArray("ModelFaceID") is None)

print()
print(f"FAILED: {len(failures)} check(s): {failures}" if failures else "ALL CHECKS PASSED")
