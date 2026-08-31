"""Where are the unmatched cap boundaries coming from? Counts the open boundaries of the input
surface, of the preprocessed surface, and of the clipped surface, so you can see at which stage
the extra holes appear. Run after an Apply."""
import slicer, vtk, numpy as np
from vtk.util.numpy_support import vtk_to_numpy
import vtkvmtkComputationalGeometryPython as vtkvmtkComputationalGeometry

def boundaries(pd, label):
    if pd is None:
        print(f"  {label:34s} (not available)"); return []
    extractor = vtkvmtkComputationalGeometry.vtkvmtkPolyDataBoundaryExtractor()
    extractor.SetInputData(pd)
    extractor.Update()
    out = extractor.GetOutput()
    loops = []
    for i in range(out.GetNumberOfCells()):
        cell = out.GetCell(i)
        pts = np.array([cell.GetPoints().GetPoint(j) for j in range(cell.GetNumberOfPoints())])
        loops.append((cell.GetNumberOfPoints(), pts.mean(axis=0),
                      float(np.linalg.norm(pts.max(0) - pts.min(0)))))
    print(f"  {label:34s} {pd.GetNumberOfCells():7d} cells, {len(loops):3d} open boundaries")
    small = [l for l in loops if l[0] <= 6]
    print(f"      boundary sizes (points): {sorted(l[0] for l in loops)}")
    if small:
        print(f"      TINY boundaries ({len(small)}), likely mesh defects rather than vessel ends:")
        for n, c, extent in small:
            print(f"        {n} points, extent {extent:.3f} mm, at "
                  f"({c[0]:.1f}, {c[1]:.1f}, {c[2]:.1f})")
    return loops

widget = slicer.modules.clipvessel.widgetRepresentation().self()
pn = widget._parameterNode
inputNode = pn.GetNodeReference("InputSurface")
inputPd = inputNode.GetPolyData() if inputNode and inputNode.IsA("vtkMRMLModelNode") else None
print("=" * 78)
print("Open boundaries at each stage (a vessel end is a big loop; a mesh defect is a tiny one)")
boundaries(inputPd, "1. input surface as loaded")
try:
    pre = widget.getPreprocessedPolyData()
except Exception as e:
    pre = None; print("  (preprocessing failed:", e, ")")
boundaries(pre, "2. after preprocessing")
print()
print(f"clip points placed: {pn.GetNodeReference('ClipPoints').GetNumberOfControlPoints() if pn.GetNodeReference('ClipPoints') else 0}")
print("Each clip point should account for exactly one boundary after clipping. Any boundary")
print("already present at stage 1 or 2 is an extra one that will be capped as its own face.")
print("=" * 78)
