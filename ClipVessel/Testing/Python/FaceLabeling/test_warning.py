"""The popup must fire exactly when preprocessing would discard the input's own face labels,
and never otherwise. slicer.util.confirmOkCancelDisplay is stubbed so nothing blocks."""
import slicer, qt, vtk, numpy as np
from vtk.util.numpy_support import numpy_to_vtk
import ClipVessel

failures = []
def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"  {detail}" if detail else ""), flush=True)
    if not cond: failures.append(name)

shown = []
answer = [True]
realConfirm = slicer.util.confirmOkCancelDisplay
def stubConfirm(text, windowTitle=None, parent=None, **kwargs):
    shown.append(text)
    return answer[0]
slicer.util.confirmOkCancelDisplay = stubConfirm

parent = slicer.qMRMLWidget(); parent.setLayout(qt.QVBoxLayout()); parent.setMRMLScene(slicer.mrmlScene)
w = ClipVessel.ClipVesselWidget(parent); w.setup()
pn = w._parameterNode

sphere = vtk.vtkSphereSource(); sphere.SetThetaResolution(30); sphere.SetPhiResolution(30); sphere.Update()
labeled = vtk.vtkPolyData(); labeled.DeepCopy(sphere.GetOutput())
vals = np.zeros(labeled.GetNumberOfCells(), dtype=np.int32); vals[:50] = 10
arr = numpy_to_vtk(vals, deep=True, array_type=vtk.VTK_INT); arr.SetName("ModelFaceID")
labeled.GetCellData().AddArray(arr)
plain = vtk.vtkPolyData(); plain.DeepCopy(sphere.GetOutput())
inputNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Input surface")
inputNode.SetAndObserveMesh(labeled)
pointCount = labeled.GetNumberOfPoints()
print(f"  (input surface has {pointCount} points)", flush=True)
pn.SetNodeReferenceID("InputSurface", inputNode.GetID())
pn.SetParameter("LabelModelFaces", "true")
pn.SetParameter("PreprocessInputSurface", "true")
pn.SetParameter("ModelFaceIdArrayName", "ModelFaceID")
pn.SetParameter("TargetNumberOfPoints", str(pointCount // 2))    # below -> decimates

def ask():
    del shown[:]
    return w.confirmPreprocessingDiscardsFaceLabels(), len(shown)

proceed, count = ask()
check("warns when preprocessing will decimate a labeled input", count == 1, f"{count} popups")
check("proceeds when the user clicks OK", proceed is True, proceed)
if shown:
    text = shown[0]
    check("names the array", "ModelFaceID" in text)
    check("says the boundaries can shift", "shift" in text)
    check("says the faces survive rather than being discarded",
          "no face is lost" in text and "discard" not in text)
    check("tells the user how to keep them", "Preprocess input surface" in text and str(pointCount) in text,
          text.replace("\n", " ")[:150])

answer[0] = False
proceed, _ = ask()
check("cancel aborts the run", proceed is False, proceed)
answer[0] = True

pn.SetParameter("TargetNumberOfPoints", str(pointCount * 2))      # above -> no decimation
_p, count = ask()
check("silent when the target is above the input point count", count == 0, f"{count} popups")

pn.SetParameter("TargetNumberOfPoints", str(pointCount // 2))
pn.SetParameter("PreprocessInputSurface", "false")
_p, count = ask()
check("silent when preprocessing is off", count == 0, f"{count} popups")

pn.SetParameter("PreprocessInputSurface", "true")
pn.SetParameter("LabelModelFaces", "false")
_p, count = ask()
check("silent when face labeling is off", count == 0, f"{count} popups")

pn.SetParameter("LabelModelFaces", "true")
inputNode.SetAndObserveMesh(plain)
_p, count = ask()
check("silent when the input carries no face labels", count == 0, f"{count} popups")

inputNode.SetAndObserveMesh(labeled)
pn.SetParameter("ModelFaceIdArrayName", "SomeOtherName")
_p, count = ask()
check("silent when the configured array name is absent", count == 0, f"{count} popups")

# Auto-apply must never pop a modal dialog mid-drag: it does not go through the click path.
pn.SetParameter("ModelFaceIdArrayName", "ModelFaceID")
del shown[:]
try:
    w.onAutoApplyTimeout()
except Exception:
    pass   # it will fail for want of centerlines; only the popup count matters
check("auto-apply never shows the popup", len(shown) == 0, f"{len(shown)} popups")

slicer.util.confirmOkCancelDisplay = realConfirm
print()
print("WARNING_RESULT:", "FAILED " + str(failures) if failures else "ALL CHECKS PASSED")
