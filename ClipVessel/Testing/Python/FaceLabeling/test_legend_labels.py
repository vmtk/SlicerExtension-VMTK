"""Reproduce what Slicer's renderer actually does to build legend label text, so the "(none)"
failure is caught without needing a 3D view.

vtkMRMLColorLegendDisplayableManager::CreateLookupTableCopyWithoutEmptyColors keeps only the
entries with GetColorDefined(i), then sets one annotation per kept entry from GetColorName(i).
vtkSlicerScalarBarActor::LayoutTicks then renders annotation text only if
  - UseAnnotationAsLabel is on (i.e. UseColorNamesForLabels), AND
  - GetNumberOfAnnotatedValues() > 1, AND
  - LabelFormat matches the regex "%.*s"
otherwise every label falls back to the literal "(none)".
"""
import re
import slicer, qt, vtk, numpy as np
from vtk.util.numpy_support import numpy_to_vtk
import ClipVessel

failures = []
def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"  {detail}" if detail else ""), flush=True)
    if not cond: failures.append(name)

def renderedLegendLabels(colorTableNode, legendDisplayNode):
    """The strings vtkSlicerScalarBarActor would draw."""
    validIndices = [i for i in range(colorTableNode.GetNumberOfColors())
                    if colorTableNode.GetColorDefined(i)]
    annotations = [colorTableNode.GetColorName(i) for i in validIndices]
    labelFormat = legendDisplayNode.GetLabelFormat()
    if not legendDisplayNode.GetUseColorNamesForLabels():
        return ["<numeric>"] * len(annotations)
    if len(annotations) <= 1 or not re.search(r"%.*s", labelFormat):
        return ["(none)"] * max(1, len(annotations))
    return annotations

parent = slicer.qMRMLWidget(); parent.setLayout(qt.QVBoxLayout()); parent.setMRMLScene(slicer.mrmlScene)
w = ClipVessel.ClipVesselWidget(parent); w.setup()
pn = w._parameterNode
out = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Output surface model")
cube = vtk.vtkCubeSource(); cube.Update()
pd = vtk.vtkPolyData(); pd.DeepCopy(cube.GetOutput())
vals = np.array([0, 0, 1, 1, 2, 3], dtype=np.int32)     # 2 input faces, 2 unlabeled -> a wall
arr = numpy_to_vtk(vals, deep=True, array_type=vtk.VTK_INT); arr.SetName("ModelFaceID")
pd.GetCellData().AddArray(arr); out.SetAndObserveMesh(pd); out.CreateDefaultDisplayNodes()
pn.SetNodeReferenceID("OutputSurfaceModel", out.GetID())
pn.SetParameter("ModelFaceIdArrayName", "ModelFaceID"); pn.SetParameter("LabelModelFaces", "true")

w.logic.labelModelFaces(pd, [], "ModelFaceID", vals.astype(np.int64))
table = w.updateFaceColorTable()
w.updateOutputFaceColoring()
legend = slicer.modules.colors.logic().GetColorLegendDisplayNode(out)

labels = renderedLegendLabels(table, legend)
print("    would render:", labels, flush=True)
check("no row renders as (none)", "(none)" not in labels, labels)
check("label format carries a string specifier", re.search(r"%.*s", legend.GetLabelFormat()) is not None,
      repr(legend.GetLabelFormat()))
check("uses colour names", legend.GetUseColorNamesForLabels())
check("every rendered label is non-empty", all(l for l in labels), labels)
# ids 1, 2 and 3 are three faces the input carried; the two id-0 cells are the wall, which
# therefore lands on 4. Four rows, and no row for colour-table entry 0.
check("one row per real face, entry 0 excluded", len(labels) == 4, labels)
check("the names are the face names",
      labels == ["Input face 1", "Input face 2", "Input face 3", "Wall"], labels)
check("entry 0 is hidden from the legend", not table.GetColorDefined(0))
check("entry 0 still opaque so the mesh is not translucent",
      table.GetLookupTable().GetTableValue(0)[3] == 1.0 and table.GetLookupTable().IsOpaque() == 1)

# A gap in the numbering (clip point that made no cut) must not add a blank row
w.logic.lastFaceIdAssignments = [(2, "First"), (4, "Third")]
w.logic.lastWallFaceId = 1
w.logic.lastExistingFaceIdMap = {}
table = w.updateFaceColorTable()
labels = renderedLegendLabels(table, legend)
print("    with a gap at id 3:", labels, flush=True)
check("gap adds no row", labels == ["Wall", "First", "Third"], labels)
check("gap entry hidden but opaque",
      not table.GetColorDefined(3) and table.GetLookupTable().GetTableValue(3)[3] == 1.0)

print()
print("LEGENDLABEL_RESULT:", "FAILED " + str(failures) if failures else "ALL CHECKS PASSED")
