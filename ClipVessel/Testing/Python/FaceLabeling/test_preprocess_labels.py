"""Labels must survive preprocessing on meshes that break it: degenerate triangles (which make
vtkTriangleFilter leave the cell array double length and misaligned) and decimation (which drops
it). Measured geometrically, so misplacement is visible."""
import slicer, qt, vtk, numpy as np
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy
import ClipVessel

failures = []
def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"  {detail}" if detail else ""), flush=True)
    if not cond: failures.append(name)

def tube(nz=12, nTheta=24, height=10.0, radius=1.0, degenerate=0):
    pts, polys = vtk.vtkPoints(), vtk.vtkCellArray()
    def P(k, t):
        a = 2 * np.pi * t / nTheta
        return (radius * np.cos(a), radius * np.sin(a), height * k / (nz - 1))
    for k in range(nz - 1):
        for t in range(nTheta):
            for tri in ((P(k, t), P(k, t + 1), P(k + 1, t + 1)),
                        (P(k, t), P(k + 1, t + 1), P(k + 1, t))):
                polys.InsertNextCell(3, [pts.InsertNextPoint(*p) for p in tri])
    for _ in range(degenerate):
        i = pts.InsertNextPoint(0.0, 0.0, 0.0)
        polys.InsertNextCell(3, [i, i, i])
    pd = vtk.vtkPolyData(); pd.SetPoints(pts); pd.SetPolys(polys)
    return pd

def centroids(pd):
    cc = vtk.vtkCellCenters(); cc.SetInputData(pd); cc.Update()
    return vtk_to_numpy(cc.GetOutput().GetPoints().GetData())

parent = slicer.qMRMLWidget(); parent.setLayout(qt.QVBoxLayout()); parent.setMRMLScene(slicer.mrmlScene)
widget = ClipVessel.ClipVesselWidget(parent); widget.setup()
pn = widget._parameterNode
inputNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Input surface")
pn.SetNodeReferenceID("InputSurface", inputNode.GetID())
pn.SetParameter("LabelModelFaces", "true")
pn.SetParameter("ModelFaceIdArrayName", "ModelFaceID")
pn.SetParameter("PreprocessInputSurface", "true")
pn.SetParameter("SubdivideInputSurface", "false")

for degenerate, target, label in [(0, 500000.0, "clean mesh, no decimation"),
                                  (5, 500000.0, "5 degenerate triangles, no decimation"),
                                  (40, 500000.0, "40 degenerate triangles, no decimation"),
                                  (5, 200.0, "5 degenerate triangles + decimation")]:
    pd = tube(degenerate=degenerate)
    cent = centroids(pd)
    vals = np.where(cent[:, 2] < 1.0, 3, 1).astype(np.int32)      # an inlet patch at the low-z end
    arr = numpy_to_vtk(vals, deep=True, array_type=vtk.VTK_INT); arr.SetName("ModelFaceID")
    pd.GetCellData().AddArray(arr)
    inputNode.SetAndObserveMesh(pd)
    pn.SetParameter("TargetNumberOfPoints", str(target))
    widget._preprocessedCacheKey = None                            # force recompute
    out = widget.getPreprocessedPolyData()
    a = out.GetCellData().GetArray("ModelFaceID")
    if a is None:
        check(label, False, "ModelFaceID absent after preprocessing"); continue
    lengthOk = a.GetNumberOfTuples() == out.GetNumberOfCells()
    ids = vtk_to_numpy(a)
    oc = centroids(out)
    # allow a one-cell-wide band at the patch edge, where decimation legitimately shifts it
    cellSize = float(np.linalg.norm(oc.max(0) - oc.min(0))) / max(1.0, out.GetNumberOfCells() ** 0.5)
    clear = np.abs(oc[:, 2] - 1.0) > 2.0 * cellSize
    wrong = int(np.count_nonzero(((ids == 3) != (oc[:, 2] < 1.0)) & clear))
    check(f"{label}: array length matches cell count", lengthOk,
          f"{a.GetNumberOfTuples()} tuples for {out.GetNumberOfCells()} cells")
    check(f"{label}: labels on the right geometry", wrong == 0,
          f"{wrong}/{int(clear.sum())} misplaced")

print()
print("PREPROCESS_RESULT:", "FAILED " + str(failures) if failures else "ALL CHECKS PASSED")
