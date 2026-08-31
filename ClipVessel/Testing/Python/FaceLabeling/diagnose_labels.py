"""Paste-and-run diagnostic: where do the input's ModelFaceID labels actually go?
Reads the live Clip Vessel module state, so run it after an Apply."""
import slicer, vtk, numpy as np
from vtk.util.numpy_support import vtk_to_numpy

def arrayInfo(pd, name):
    out = []
    for where, data in (("cell", pd.GetCellData()), ("point", pd.GetPointData())):
        a = data.GetArray(name)
        if a is not None:
            v = vtk_to_numpy(a)
            counts = {int(k): int(c) for k, c in zip(*np.unique(v, return_counts=True))}
            out.append(f"{where} data, {a.GetClassName()}, {a.GetNumberOfTuples()} tuples, {counts}")
    return out or ["ABSENT"]

widget = slicer.modules.clipvessel.widgetRepresentation().self()
pn = widget._parameterNode
logic = widget.logic
arrayName = pn.GetParameter("ModelFaceIdArrayName") or "ModelFaceID"
print("=" * 78)
print("array name in use          :", arrayName)
print("Label mesh faces           :", pn.GetParameter("LabelModelFaces"))
print("Preprocess input surface   :", pn.GetParameter("PreprocessInputSurface"))
print("Subdivide input surface    :", pn.GetParameter("SubdivideInputSurface"))
target = float(pn.GetParameter("TargetNumberOfPoints"))
print("Target number of points    :", int(target))

inputNode = pn.GetNodeReference("InputSurface")
print("\ninput node                 :", inputNode.GetClassName() if inputNode else None,
      repr(inputNode.GetName()) if inputNode else "")
inputPd = inputNode.GetPolyData() if inputNode and inputNode.IsA("vtkMRMLModelNode") else None
if inputPd is None:
    print("  !! not a model node - the surface is regenerated from the segmentation, so any")
    print("     face labels on it are not visible to the module at all.")
else:
    print(f"  {inputPd.GetNumberOfPoints()} points, {inputPd.GetNumberOfCells()} cells")
    for line in arrayInfo(inputPd, arrayName):
        print("  ", arrayName, ":", line)
    willDecimate = target < inputPd.GetNumberOfPoints()
    print(f"  decimation will run        : {willDecimate}"
          f"  ({int(target)} target vs {inputPd.GetNumberOfPoints()} input points)")
    if willDecimate:
        print("     -> preprocessing DISCARDS the labels; the output is labeled from scratch.")

print("\nwhat the last run recorded :")
print("  existing id remap        :", logic.lastExistingFaceIdMap)
print("  wall face id             :", logic.lastWallFaceId)
print("  cap assignments          :", logic.lastFaceIdAssignments)

outputNode = pn.GetNodeReference("OutputSurfaceModel")
outputPd = outputNode.GetPolyData() if outputNode else None
print("\noutput node                :", repr(outputNode.GetName()) if outputNode else None)
if outputPd is not None:
    print(f"  {outputPd.GetNumberOfPoints()} points, {outputPd.GetNumberOfCells()} cells")
    for line in arrayInfo(outputPd, arrayName):
        print("  ", arrayName, ":", line)

# --- did each output cell keep the label of the input geometry it sits on? -----------------
if inputPd is not None and outputPd is not None and logic.lastExistingFaceIdMap:
    inArr = inputPd.GetCellData().GetArray(arrayName)
    outArr = outputPd.GetCellData().GetArray(arrayName)
    if inArr is None or outArr is None:
        print("\nspatial check: skipped (array missing on one side)")
    else:
        def centroids(pd):
            cc = vtk.vtkCellCenters(); cc.SetInputData(pd); cc.Update()
            return vtk_to_numpy(cc.GetOutput().GetPoints().GetData())
        inIds, outIds = vtk_to_numpy(inArr), vtk_to_numpy(outArr)
        outCent = centroids(outputPd)
        # A CELL locator, not nearest-centroid: clipping splits triangles, so a cut cell's
        # centroid can sit nearer a neighbour's centroid than its own parent's.
        loc = vtk.vtkCellLocator(); loc.SetDataSet(inputPd); loc.BuildLocator()
        remap = dict(logic.lastExistingFaceIdMap)
        capIds = {f for f, _l in logic.lastFaceIdAssignments}
        wallId = logic.lastWallFaceId
        closest = [0.0, 0.0, 0.0]
        cellId, subId, dist2 = vtk.mutable(0), vtk.mutable(0), vtk.mutable(0.0)
        agree = disagree = 0
        disagreeDist, agreeDist, examples = [], [], []
        for i, centroid in enumerate(outCent):
            faceId = int(outIds[i])
            if faceId in capIds:
                continue                      # caps are new geometry
            loc.FindClosestPoint(list(centroid), closest, cellId, subId, dist2)
            expected = remap.get(int(inIds[int(cellId)]), wallId)
            if faceId == expected:
                agree += 1; agreeDist.append(float(dist2) ** 0.5)
            else:
                disagree += 1; disagreeDist.append(float(dist2) ** 0.5)
                if len(examples) < 5:
                    examples.append(f"cell {i}: got {faceId}, input surface says {expected}, "
                                    f"{float(dist2) ** 0.5:.4f} mm away")
        total = agree + disagree
        print(f"\nSPATIAL CHECK (cell locator): {disagree}/{total} non-cap cells disagree "
              f"({100.0 * disagree / max(1, total):.2f}%)")
        for e in examples:
            print("   ", e)
        if disagreeDist:
            import statistics
            print(f"    distance to the input surface - agreeing cells: median "
                  f"{statistics.median(agreeDist):.4f} mm; disagreeing: median "
                  f"{statistics.median(disagreeDist):.4f} mm")
            print("    (disagreeing cells sitting much further off the input surface = they are")
            print("     cut/new cells at a clip, i.e. a measurement artefact, not scattering)")

        # Is the patch where it should be? Compare its extent, not just its cell count.
        for originalId, newId in sorted(remap.items()):
            inMask, outMask = inIds == originalId, outIds == newId
            if not inMask.any() or not outMask.any():
                continue
            inC, outC = centroids(inputPd)[inMask], outCent[outMask]
            shift = np.linalg.norm(inC.mean(axis=0) - outC.mean(axis=0))
            print(f"    input face {originalId} -> output face {newId}: "
                  f"{int(inMask.sum())} -> {int(outMask.sum())} cells, "
                  f"centre of mass moved {shift:.3f} mm, "
                  f"bbox in  {np.round(inC.min(0), 1)}..{np.round(inC.max(0), 1)}  "
                  f"out {np.round(outC.min(0), 1)}..{np.round(outC.max(0), 1)}")
print("=" * 78)
