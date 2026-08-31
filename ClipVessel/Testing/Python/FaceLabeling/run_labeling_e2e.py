import os
# The module lives three directories up from this file (ClipVessel/Testing/Python/FaceLabeling).
_MODULE_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
_MODULE_FILE = os.path.join(_MODULE_DIR, "ClipVessel.py")
import importlib.util, sys, traceback
import vtk, numpy as np
from vtk.util.numpy_support import vtk_to_numpy
import slicer

BRANCH_FILE = _MODULE_FILE
spec = importlib.util.spec_from_file_location("ClipVesselBranch", BRANCH_FILE)
mod = importlib.util.module_from_spec(spec)
sys.modules["ClipVesselBranch"] = mod
spec.loader.exec_module(mod)

failures = []
def check(name, condition, detail=""):
    print(("  PASS  " if condition else "  FAIL  ") + name + ("  " + str(detail) if detail else ""), flush=True)
    if not condition:
        failures.append(name)

# ---- Same setup as the module's own end-to-end test -----------------------
import SampleData, ExtractCenterline
inputSurfaceModelNode = SampleData.downloadFromURL(
    fileNames="aorta-surface.stl", nodeNames="aorta-surface",
    uris="https://raw.githubusercontent.com/vmtk/vmtk-test-data/master/input/aorta-surface.stl")[0]
extractCenterlineLogic = ExtractCenterline.ExtractCenterlineLogic()
preprocessedPolyData = extractCenterlineLogic.preprocess(inputSurfaceModelNode.GetPolyData(), 5000.0, 4.0, False)
endPointsMarkupsNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "Centerline endpoints")
networkPolyData = extractCenterlineLogic.extractNetwork(preprocessedPolyData, endPointsMarkupsNode)
for position in extractCenterlineLogic.getEndPoints(networkPolyData, startPointPosition=None):
    endPointsMarkupsNode.AddControlPoint(vtk.vtkVector3d(position))
centerlinePolyData, _voronoi = extractCenterlineLogic.extractCenterline(preprocessedPolyData, endPointsMarkupsNode)
centerlineModelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Centerline model")
centerlineModelNode.SetAndObserveMesh(centerlinePolyData)

logic = mod.ClipVesselLogic()
clipPointsMarkupsNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "Clip points")
for terminus in logic.detectCenterlineTerminusClipPoints(centerlineModelNode, 1.5):
    pointIndex = clipPointsMarkupsNode.AddControlPointWorld(vtk.vtkVector3d(terminus["position"]))
    clipPointsMarkupsNode.SetNthControlPointLabel(pointIndex, terminus["label"])
numberOfClipPoints = clipPointsMarkupsNode.GetNumberOfControlPoints()
print(f"SETUP: {numberOfClipPoints} clip points on the aorta surface", flush=True)

clipPlanes = [logic.automaticClipPlane(centerlineModelNode, clipPointsMarkupsNode, i) for i in range(numberOfClipPoints)]
clipPointPositions = np.array([plane[0] for plane in clipPlanes])

# An installed SlicerVMTK older than the version upstream master pins lacks the flow-extension
# setters it calls (SetPreserveCrossSectionShape, SetInterpolationModeToRamp,
# SetExtensionLengthScaleFactors), so stand in a version of extendVessel that skips just those.
# Everything else - the real extension filter, the real capper, and the labeling - is unchanged.
# *args keeps this working as upstream adds further extension options.
def patchedExtendVessel(surfacePolyData, centerlinesPolyData, extensionRatio, extensionMode,
                        transitionRatio=None, interpolationMode=None, preserveCrossSectionShape=None,
                        *args):
    f = mod.vtkvmtkComputationalGeometry.vtkvmtkPolyDataFlowExtensionsFilter()
    f.SetInputData(surfacePolyData)
    f.SetCenterlines(centerlinesPolyData)
    f.SetAdaptiveExtensionLength(logic.AdaptiveExtensionLength)
    f.SetAdaptiveExtensionRadius(logic.AdaptiveExtensionRadius)
    f.SetAdaptiveNumberOfBoundaryPoints(logic.AdaptiveNumberOfBoundaryPoints)
    f.SetExtensionLength(logic.ExtensionLength)
    f.SetExtensionRatio(float(extensionRatio if extensionRatio is not None else logic.ExtensionRatio))
    f.SetExtensionRadius(logic.ExtensionRadius)
    f.SetTransitionRatio(min(max(float(transitionRatio if transitionRatio is not None else logic.TransitionRatio), 0.0), 1.0))
    f.SetCenterlineNormalEstimationDistanceRatio(logic.CenterlineNormalEstimationDistanceRatio)
    f.SetNumberOfBoundaryPoints(logic.TargetNumberOfBoundaryPoints)
    f.SetExtensionModeToUseNormalToBoundary()
    f.SetInterpolationModeToLinear()
    f.Update()
    return f.GetOutput()
logic.extendVessel = patchedExtendVessel

def clip(cap, addExtensions, labelFaces=True):
    return logic.clipVessel(preprocessedPolyData, centerlineModelNode, clipPointsMarkupsNode,
                            cap, addExtensions, 2.0, "BOUNDARY_NORMAL", transitionRatio=0.5,
                            labelModelFaces=labelFaces)

for addExtensions in [False, True]:
    print(f"CASE: capped, {'with' if addExtensions else 'without'} flow extensions", flush=True)
    out = clip(True, addExtensions)
    faceIdArray = out.GetCellData().GetArray("ModelFaceID")
    check("ModelFaceID array exists", faceIdArray is not None)
    if faceIdArray is None:
        continue
    check("array is vtkIntArray", faceIdArray.IsA("vtkIntArray"), faceIdArray.GetClassName())
    check("one value per cell", faceIdArray.GetNumberOfTuples() == out.GetNumberOfCells(),
          f"{faceIdArray.GetNumberOfTuples()} vs {out.GetNumberOfCells()}")
    check("active scalars set", out.GetCellData().GetScalars() is not None
          and out.GetCellData().GetScalars().GetName() == "ModelFaceID")
    faceIds = vtk_to_numpy(faceIdArray)
    expected = set(range(1, numberOfClipPoints + 2))
    check("ids are exactly wall + one per clip point",
          set(int(v) for v in np.unique(faceIds)) == expected,
          f"got {sorted(set(int(v) for v in np.unique(faceIds)))}, expected {sorted(expected)}")
    check("wall is the largest face", np.count_nonzero(faceIds == 1) > np.count_nonzero(faceIds != 1),
          f"wall={np.count_nonzero(faceIds == 1)} caps={np.count_nonzero(faceIds != 1)}")
    check("one assignment per clip point", len(logic.lastFaceIdAssignments) == numberOfClipPoints,
          logic.lastFaceIdAssignments)
    cellCenters = vtk.vtkCellCenters()
    cellCenters.SetInputData(out)
    cellCenters.Update()
    centers = vtk_to_numpy(cellCenters.GetOutput().GetPoints().GetData())
    for faceId, pointLabel in logic.lastFaceIdAssignments:
        idx = faceId - 2
        check(f"id {faceId} label matches clip point {idx}",
              pointLabel == clipPointsMarkupsNode.GetNthControlPointLabel(idx),
              f"{pointLabel!r} vs {clipPointsMarkupsNode.GetNthControlPointLabel(idx)!r}")
        capCentroid = centers[faceIds == faceId].mean(axis=0)
        origin, normal, radius = clipPlanes[idx]
        offset = capCentroid - np.array(origin)
        alongNormal = float(np.dot(offset, normal))
        perpendicular = float(np.linalg.norm(offset - alongNormal * np.array(normal)))
        if not addExtensions:
            closest = int(np.argmin(np.linalg.norm(clipPointPositions - capCentroid, axis=1)))
            check(f"id {faceId} cap is nearest clip point {idx}", closest == idx, f"nearest was {closest}")
        else:
            check(f"id {faceId} cap is beyond its clip plane", alongNormal > 0.0, f"along={alongNormal:.3f}")
            check(f"id {faceId} cap stays on the plane axis", perpendicular < radius,
                  f"perp={perpendicular:.3f} radius={radius:.3f}")
    # Watertight: labeling must not perturb the geometry
    boundaryEdges = vtk.vtkFeatureEdges()
    boundaryEdges.SetInputData(out)
    boundaryEdges.BoundaryEdgesOn(); boundaryEdges.FeatureEdgesOff()
    boundaryEdges.NonManifoldEdgesOff(); boundaryEdges.ManifoldEdgesOff()
    boundaryEdges.Update()
    check("output is still watertight", boundaryEdges.GetOutput().GetNumberOfCells() == 0,
          boundaryEdges.GetOutput().GetNumberOfCells())
    # Labeling must not change the geometry compared to the unlabeled run
    plain = clip(True, addExtensions, labelFaces=False)
    check("same cell count as the unlabeled run", plain.GetNumberOfCells() == out.GetNumberOfCells(),
          f"{plain.GetNumberOfCells()} vs {out.GetNumberOfCells()}")
    check("unlabeled run has no ModelFaceID", plain.GetCellData().GetArray("ModelFaceID") is None)

print("CASE: input surface already carries face labels (the reported bug)", flush=True)
# A pre-existing face on part of the wall, tagged 10 - well clear of the ids the module hands
# out, so a collision or a fusion would be unmistakable.
from vtk.util.numpy_support import numpy_to_vtk
prelabeled = vtk.vtkPolyData(); prelabeled.DeepCopy(preprocessedPolyData)
patchCellCount = prelabeled.GetNumberOfCells() // 10
vals = np.zeros(prelabeled.GetNumberOfCells(), dtype=np.int32)
vals[:patchCellCount] = 10
arr = numpy_to_vtk(vals, deep=True, array_type=vtk.VTK_INT); arr.SetName("ModelFaceID")
prelabeled.GetCellData().AddArray(arr)
out = logic.clipVessel(prelabeled, centerlineModelNode, clipPointsMarkupsNode, True, False,
                       2.0, "BOUNDARY_NORMAL", labelModelFaces=True)
faceIds = vtk_to_numpy(out.GetCellData().GetArray("ModelFaceID"))
check("existing face 10 compacted to 1", logic.lastExistingFaceIdMap == {10: 1}, logic.lastExistingFaceIdMap)
check("wall took the next id (2)", logic.lastWallFaceId == 2, logic.lastWallFaceId)
check("ids are 1..N+2 with nothing extra",
      set(int(v) for v in np.unique(faceIds)) == set(range(1, numberOfClipPoints + 3)),
      sorted(set(int(v) for v in np.unique(faceIds))))
check("caps start at 3, in clip point order",
      [f for f, _l in logic.lastFaceIdAssignments] == list(range(3, numberOfClipPoints + 3)),
      logic.lastFaceIdAssignments)
check("cap labels still match their clip points",
      [l for _f, l in logic.lastFaceIdAssignments] ==
      [clipPointsMarkupsNode.GetNthControlPointLabel(i) for i in range(numberOfClipPoints)],
      logic.lastFaceIdAssignments)
# The decisive check: the renumbered pre-existing face must not have absorbed any cap. Clipping
# can only remove patch cells, so its cell count can shrink but never grow.
patchCells = int(np.count_nonzero(faceIds == 1))
check("pre-existing face kept separate from every cap", 0 < patchCells <= patchCellCount,
      f"{patchCells} cells, input patch had {patchCellCount}")
capSizes = {int(f): int(np.count_nonzero(faceIds == f)) for f, _l in logic.lastFaceIdAssignments}
check("no cap is inflated by a fused face", all(n < patchCellCount for n in capSizes.values()), capSizes)
check("internal cap array does not leak",
      out.GetCellData().GetArray(logic.capBoundaryIdsArrayName) is None)
print("    cap sizes:", capSizes, " pre-existing face:", patchCells, "cells", flush=True)

print("CASE: uncapped", flush=True)
out = clip(False, False)
faceIds = vtk_to_numpy(out.GetCellData().GetArray("ModelFaceID"))
check("uncapped surface is all wall", set(int(v) for v in np.unique(faceIds)) == {1},
      sorted(set(int(v) for v in np.unique(faceIds))))
check("no cap assignments", logic.lastFaceIdAssignments == [], logic.lastFaceIdAssignments)

print()
print(f"E2E_LABELING: {'FAILED ' + str(failures) if failures else 'ALL CHECKS PASSED'}")
