"""Drive the real widget's Apply path end to end, which is the one thing the other suites do
not touch: they call the logic directly, so a broken reference in onApplyButton goes unseen."""
import slicer, qt, vtk, traceback
import numpy as np
from vtk.util.numpy_support import vtk_to_numpy, numpy_to_vtk
import ClipVessel, SampleData, ExtractCenterline

failures = []
def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"  {detail}" if detail else ""), flush=True)
    if not cond:
        failures.append(name)

# --- scene: aorta surface, centerline, clip points -------------------------
inputNode = SampleData.downloadFromURL(
    fileNames="aorta-surface.stl", nodeNames="aorta-surface",
    uris="https://raw.githubusercontent.com/vmtk/vmtk-test-data/master/input/aorta-surface.stl")[0]
ecl = ExtractCenterlineLogic = ExtractCenterline.ExtractCenterlineLogic()
pre = ecl.preprocess(inputNode.GetPolyData(), 5000.0, 4.0, False)
ep = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "eps")
for p in ecl.getEndPoints(ecl.extractNetwork(pre, ep), startPointPosition=None):
    ep.AddControlPoint(vtk.vtkVector3d(p))
cl, _v = ecl.extractCenterline(pre, ep)
clNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Centerline model")
clNode.SetAndObserveMesh(cl)

# Feed the widget a model whose polydata is already preprocessed, and turn preprocessing off,
# so the input labels survive to the clipping stage.
surfaceNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Input surface")
surfaceNode.SetAndObserveMesh(pre)

logic = ClipVessel.ClipVesselLogic()
cpNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "Clip points")
for t in logic.detectCenterlineTerminusClipPoints(clNode, 1.5):
    i = cpNode.AddControlPointWorld(vtk.vtkVector3d(t["position"]))
    cpNode.SetNthControlPointLabel(i, t["label"])
numberOfClipPoints = cpNode.GetNumberOfControlPoints()

# --- widget -----------------------------------------------------------------
parent = slicer.qMRMLWidget(); parent.setLayout(qt.QVBoxLayout()); parent.setMRMLScene(slicer.mrmlScene)
widget = ClipVessel.ClipVesselWidget(parent)
widget.setup()
pn = widget._parameterNode
outNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Output surface model")
pn.SetNodeReferenceID("InputSurface", surfaceNode.GetID())
pn.SetNodeReferenceID("InputCenterlines", clNode.GetID())
pn.SetNodeReferenceID("ClipPoints", cpNode.GetID())
pn.SetNodeReferenceID("OutputSurfaceModel", outNode.GetID())
pn.SetParameter("PreprocessInputSurface", "false")
pn.SetParameter("CapOutputSurface", "true")
pn.SetParameter("ExtendOutputSurface", "false")
pn.SetParameter("LabelModelFaces", "true")
pn.SetParameter("ModelFaceIdArrayName", "ModelFaceID")

def apply(title):
    print(f"CASE: {title}", flush=True)
    try:
        widget.onApplyButton()
    except Exception:
        print("  FAIL  onApplyButton raised"); traceback.print_exc(); failures.append(title); return None
    print("  PASS  onApplyButton ran")
    print("    status: " + widget.ui.clipStatusLabel.text, flush=True)
    return outNode.GetPolyData()

# 1. clean input
out = apply("Apply through the widget, unlabeled input")
if out is not None:
    ids = vtk_to_numpy(out.GetCellData().GetArray("ModelFaceID"))
    check("wall=1, caps 2..N+1", set(int(v) for v in np.unique(ids)) == set(range(1, numberOfClipPoints + 2)),
          sorted(set(int(v) for v in np.unique(ids))))
    check("status names the array and the caps", "ModelFaceID" in widget.ui.clipStatusLabel.text
          and "wall=1" in widget.ui.clipStatusLabel.text)
    dn = outNode.GetDisplayNode()
    check("output auto-colored by face id", dn.GetScalarVisibility()
          and dn.GetActiveScalarName() == "ModelFaceID")

# 2. input that already carries labels
vals = np.zeros(pre.GetNumberOfCells(), dtype=np.int32)
vals[: pre.GetNumberOfCells() // 10] = 10
labeled = vtk.vtkPolyData(); labeled.DeepCopy(pre)
arr = numpy_to_vtk(vals, deep=True, array_type=vtk.VTK_INT); arr.SetName("ModelFaceID")
labeled.GetCellData().AddArray(arr)
surfaceNode.SetAndObserveMesh(labeled)
out = apply("Apply through the widget, input already labeled (10 -> 1, wall 2, caps 3+)")
if out is not None:
    ids = vtk_to_numpy(out.GetCellData().GetArray("ModelFaceID"))
    check("existing 10 -> 1", widget.logic.lastExistingFaceIdMap == {10: 1}, widget.logic.lastExistingFaceIdMap)
    check("wall = 2", widget.logic.lastWallFaceId == 2, widget.logic.lastWallFaceId)
    check("ids are 1..N+2", set(int(v) for v in np.unique(ids)) == set(range(1, numberOfClipPoints + 3)),
          sorted(set(int(v) for v in np.unique(ids))))
    check("status reports the renumbering", "10" in widget.ui.clipStatusLabel.text
          and "wall=2" in widget.ui.clipStatusLabel.text, widget.ui.clipStatusLabel.text)

# 3. Preprocessing on, over the raw (un-decimated) surface so decimation really runs and
# destroys the labels. Note the surface above was already preprocessed, so turning
# preprocessing on for it is a no-op and the labels legitimately survive - the flag reports
# what actually happened to the array, it does not assume preprocessing always drops it.
rawLabeled = vtk.vtkPolyData(); rawLabeled.DeepCopy(inputNode.GetPolyData())
rawVals = np.zeros(rawLabeled.GetNumberOfCells(), dtype=np.int32)
rawVals[: rawLabeled.GetNumberOfCells() // 10] = 10
rawArr = numpy_to_vtk(rawVals, deep=True, array_type=vtk.VTK_INT); rawArr.SetName("ModelFaceID")
rawLabeled.GetCellData().AddArray(rawArr)
surfaceNode.SetAndObserveMesh(rawLabeled)
pn.SetParameter("PreprocessInputSurface", "true")
# ExtractCenterline.preprocess only decimates when the point target is below the input's point
# count (reductionFactor > 0). The module default is 50000, well above this surface, so it has
# to be lowered or preprocessing is a no-op and there is nothing to drop.
pn.SetParameter("TargetNumberOfPoints", "3000")
print(f"  (raw surface has {rawLabeled.GetNumberOfPoints()} points vs a 3000 point target, "
      f"so decimation will run)", flush=True)
pn.SetParameter("LabelModelFaces", "true")
print("  DIAG PreprocessInputSurface param =", repr(pn.GetParameter("PreprocessInputSurface")),
      " checkbox =", widget.ui.preprocessInputSurfaceModelCheckBox.checked, flush=True)
_pp = widget.getPreprocessedPolyData()
print("  DIAG preprocessed:", _pp.GetNumberOfPoints(), "points; has ModelFaceID =",
      _pp.GetCellData().GetArray("ModelFaceID") is not None, flush=True)
out = apply("Apply with preprocessing on over the raw surface, decimation and all")
if out is not None:
    # Decimation used to destroy the labels; they are now re-derived from the original surface
    # by position, so the patch survives being decimated.
    check("input face 10 survives decimation", widget.logic.lastExistingFaceIdMap == {10: 1},
          widget.logic.lastExistingFaceIdMap)
    check("wall still follows it", widget.logic.lastWallFaceId == 2, widget.logic.lastWallFaceId)
    ids = vtk_to_numpy(out.GetCellData().GetArray("ModelFaceID"))
    check("the transferred patch is a sensible fraction of the decimated mesh",
          0 < int(np.count_nonzero(ids == 1)) < out.GetNumberOfCells() // 2,
          f"{int(np.count_nonzero(ids == 1))} of {out.GetNumberOfCells()} cells")

# 4. labeling off -> no array, no scalar coloring
pn.SetParameter("PreprocessInputSurface", "false")
pn.SetParameter("LabelModelFaces", "false")
out = apply("Apply with labeling off")
if out is not None:
    check("no face id array", out.GetCellData().GetArray("ModelFaceID") is None)
    check("scalar coloring off", not outNode.GetDisplayNode().GetScalarVisibility())

# 5. the colour legend
pn.SetParameter("LabelModelFaces", "true")
pn.SetParameter("TargetNumberOfPoints", "50000")
surfaceNode.SetAndObserveMesh(labeled)      # patch at 10 -> 1, wall 2, caps 3..5
pn.SetParameter("PreprocessInputSurface", "false")
out = apply("Apply, then inspect the colour legend")
if out is not None:
    table = widget.faceColorTable(create=False)
    legend = slicer.modules.colors.logic().GetColorLegendDisplayNode(outNode)
    check("a colour table was built", table is not None)
    check("a legend node exists", legend is not None)
    if table and legend:
        names = [table.GetColorName(i) for i in range(table.GetNumberOfColors())]
        print("    legend entries:", list(enumerate(names)), flush=True)
        # Entry 0 is not a face, but it must still be opaque: a single transparent entry makes
        # VTK classify the whole model as translucent, which is what made the mesh vanish.
        check("entry 0 unnamed but opaque",
              names[0] == "" and table.GetLookupTable().GetTableValue(0)[3] == 1.0,
              (names[0], table.GetLookupTable().GetTableValue(0)[3]))
        check("whole table opaque", table.GetLookupTable().IsOpaque() == 1)
        check("pre-existing face named by its original id", names[1] == "Input face 10", names[1])
        check("wall named", names[2] == "Wall", names[2])
        check("caps named after their clip points",
              names[3:6] == ["Inlet", "Outlet 1", "Outlet 2"], names[3:6])
        check("no anatomical names leaked in",
              not any(n in names for n in ["Brain", "Ventricles", "Tumor"]), names)
        rgbs = [tuple(round(c, 3) for c in table.GetLookupTable().GetTableValue(i)[:3])
                for i in range(1, table.GetNumberOfColors())]
        check("every face has a distinct colour", len(set(rgbs)) == len(rgbs), rgbs)
        import itertools, math
        worst = min(math.dist(a, b) for a, b in itertools.combinations(rgbs, 2))
        check("colours are well separated", worst > 0.25, f"min pairwise distance {worst:.3f}")
        check("legend visible", legend.GetVisibility())
        check("legend uses the face names", legend.GetUseColorNamesForLabels())
        check("legend titled with the array", legend.GetTitleText() == "ModelFaceID", legend.GetTitleText())
        # Entry 0 is kept out of the legend by being marked undefined, not by a scalar range.
        check("legend skips entry 0", not table.GetColorDefined(0))
        check("legend label format carries a string specifier, else every row reads '(none)'",
              "%s" in legend.GetLabelFormat(), repr(legend.GetLabelFormat()))
        # The legend deliberately does NOT carry its own colour node: the displayable manager
        # reads the model display node's, "and not the color node and range that is set in the
        # colorLegendDisplayNode" (vtkMRMLColorLegendDisplayableManager.cxx:423-426).
        check("legend reads the model's colour table",
              outNode.GetDisplayNode().GetColorNodeID() == table.GetID())
        check("model bound to the face table",
              outNode.GetDisplayNode().GetColorNodeID() == table.GetID())

    # Unchecking must hide the legend too, not just the scalar colouring
    widget.ui.labelModelFacesCheckBox.checked = False
    check("legend hidden when labeling is off", not legend.GetVisibility())
    widget.ui.labelModelFacesCheckBox.checked = True
    check("legend shown again on re-check", legend.GetVisibility())

print()
print("APPLY_RESULT:", "FAILED " + str(failures) if failures else "ALL CHECKS PASSED")
