import slicer, qt, traceback
import ClipVessel

failures = []
def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"  {detail}" if detail else ""))
    if not cond: failures.append(name)

try:
    # Must pass a parent: with parent=None the base class runs setup() from inside its own
    # __init__, before the subclass has initialized its attributes. Real Slicer passes a parent.
    parentWidget = slicer.qMRMLWidget()
    parentWidget.setLayout(qt.QVBoxLayout())
    parentWidget.setMRMLScene(slicer.mrmlScene)
    widget = ClipVessel.ClipVesselWidget(parentWidget)
    widget.setup()
    print("  PASS  widget setup() ran")
except Exception:
    print("  FAIL  widget setup() raised")
    traceback.print_exc()
    failures.append("setup")
    widget = None

if widget:
    pn = widget._parameterNode
    check("default LabelModelFaces is false", pn.GetParameter("LabelModelFaces") == "false",
          repr(pn.GetParameter("LabelModelFaces")))
    check("default array name", pn.GetParameter("ModelFaceIdArrayName") == "ModelFaceID",
          repr(pn.GetParameter("ModelFaceIdArrayName")))
    check("name field starts disabled", not widget.ui.modelFaceIdArrayNameLineEdit.enabled)

    # Checking the box must reach the parameter node and enable the name field
    widget.ui.labelModelFacesCheckBox.checked = True
    check("checkbox -> parameter node", pn.GetParameter("LabelModelFaces") == "true",
          repr(pn.GetParameter("LabelModelFaces")))
    check("name field enabled when checked", widget.ui.modelFaceIdArrayNameLineEdit.enabled)

    # Editing the name must reach the parameter node
    widget.ui.modelFaceIdArrayNameLineEdit.text = "CellEntityIds"
    widget.onModelFaceIdArrayNameEditingFinished()
    check("edited name -> parameter node", pn.GetParameter("ModelFaceIdArrayName") == "CellEntityIds",
          repr(pn.GetParameter("ModelFaceIdArrayName")))

    # Clearing it must fall back to the default rather than store an unusable empty name
    widget.ui.modelFaceIdArrayNameLineEdit.text = "   "
    widget.onModelFaceIdArrayNameEditingFinished()
    check("blank name falls back to default", pn.GetParameter("ModelFaceIdArrayName") == "ModelFaceID",
          repr(pn.GetParameter("ModelFaceIdArrayName")))
    check("field shows the fallback", widget.ui.modelFaceIdArrayNameLineEdit.text == "ModelFaceID",
          repr(widget.ui.modelFaceIdArrayNameLineEdit.text))

    # Parameter node -> GUI direction (as when a saved scene is restored)
    pn.SetParameter("LabelModelFaces", "false")
    pn.SetParameter("ModelFaceIdArrayName", "MyFaces")
    check("parameter node -> checkbox", not widget.ui.labelModelFacesCheckBox.checked)
    check("parameter node -> name field", widget.ui.modelFaceIdArrayNameLineEdit.text == "MyFaces",
          repr(widget.ui.modelFaceIdArrayNameLineEdit.text))
    check("name field disabled again", not widget.ui.modelFaceIdArrayNameLineEdit.enabled)

# ---- automatic coloring of the output by face id -------------------------
if widget:
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk
    import numpy as np

    # A stand-in output model carrying a ModelFaceID array, as clipVessel would have produced
    out = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Output surface model")
    cube = vtk.vtkCubeSource(); cube.Update()
    pd = vtk.vtkPolyData(); pd.DeepCopy(cube.GetOutput())
    arr = numpy_to_vtk(np.array([0, 1, 1, 2, 3, 4], dtype=np.int32), deep=True, array_type=vtk.VTK_INT)
    arr.SetName("ModelFaceID")
    pd.GetCellData().AddArray(arr)
    pd.GetCellData().SetActiveScalars("ModelFaceID")
    out.SetAndObserveMesh(pd)
    out.CreateDefaultDisplayNodes()
    pn = widget._parameterNode
    pn.SetNodeReferenceID("OutputSurfaceModel", out.GetID())
    pn.SetParameter("ModelFaceIdArrayName", "ModelFaceID")

    dn = out.GetDisplayNode()
    pn.SetParameter("LabelModelFaces", "true")
    # The colour table is built from what a labeling run recorded, so run one.
    widget.logic.labelModelFaces(pd, [], "ModelFaceID", np.array([0, 1, 1, 2, 3, 4], dtype=np.int64))
    widget.updateFaceColorTable()
    widget.updateOutputFaceColoring()
    check("scalar visibility on when labeling", dn.GetScalarVisibility())
    check("active scalar is ModelFaceID", dn.GetActiveScalarName() == "ModelFaceID",
          repr(dn.GetActiveScalarName()))
    check("attribute location is cell data",
          dn.GetActiveAttributeLocation() == vtk.vtkAssignAttribute.CELL_DATA,
          dn.GetActiveAttributeLocation())
    table = slicer.mrmlScene.GetNodeByID(dn.GetColorNodeID())
    check("a face color table was built", table is not None
          and table.IsA("vtkMRMLColorTableNode"), dn.GetColorNodeID())
    # Ids 1..4 compact to 1..4 and cell 0 is unlabeled, so the wall lands on 5 (no clip points).
    check("input faces named by their original id",
          [table.GetColorName(i) for i in (1, 2, 3, 4)] ==
          ["Input face 1", "Input face 2", "Input face 3", "Input face 4"],
          [table.GetColorName(i) for i in (1, 2, 3, 4)])
    check("wall named", table.GetColorName(5) == "Wall", table.GetColorName(5))
    # Face id N must land on table entry N. The colour node's own range is 0-255 whatever the
    # table size, which would put every id on entry 0 and draw the model in one flat colour.
    check("scalar range spans the table, so ids map 1:1",
          tuple(dn.GetScalarRange()) == (0.0, float(table.GetNumberOfColors())),
          f"{dn.GetScalarRange()} for {table.GetNumberOfColors()} colours")
    check("colour table is opaque (a transparent entry would make the mesh translucent)",
          table.GetLookupTable().IsOpaque() == 1)
    # The legend resolves a name by mapping the face id through the colour node's own range. If
    # that range is left at the default 0-255 every id lands on entry 0, which has no name, and
    # the legend reads "(none)" for every face.
    lo, hi = table.GetLookupTable().GetRange()
    count = table.GetNumberOfColors()
    check("colour node range spans the table", (lo, hi) == (0.0, float(count)), (lo, hi))
    unnamed = [v for v in range(1, count)
               if not table.GetColorName(int((v - lo) / (hi - lo) * count))]
    check("every face id resolves to a name, never '(none)'", not unnamed, unnamed)

    # Turning the checkbox off must put the model back to its plain color right away
    widget.ui.labelModelFacesCheckBox.checked = False
    check("scalar visibility off when unchecked", not dn.GetScalarVisibility())

    # Turning it back on with the array present must recolor without an Apply
    widget.ui.labelModelFacesCheckBox.checked = True
    check("recolors on re-check", dn.GetScalarVisibility())

    # Checking it when the output has no such array must NOT switch to scalar coloring
    pn.SetParameter("ModelFaceIdArrayName", "NoSuchArray")
    widget.updateOutputFaceColoring()
    check("no coloring when the array is absent", not dn.GetScalarVisibility())

    # And with no labeling run recorded there is nothing to name, so no coloring either.
    pn.SetParameter("ModelFaceIdArrayName", "ModelFaceID")
    freshWidget = ClipVessel.ClipVesselWidget(parentWidget)
    freshWidget.setup()
    freshWidget._parameterNode.SetNodeReferenceID("OutputSurfaceModel", out.GetID())
    freshWidget._parameterNode.SetParameter("LabelModelFaces", "true")
    freshWidget._parameterNode.SetParameter("ModelFaceIdArrayName", "ModelFaceID")
    freshWidget._parameterNode.RemoveNodeReferenceIDs("FaceColorTable")
    freshWidget.updateOutputFaceColoring()
    check("no coloring before any labeling run", not dn.GetScalarVisibility())

print("WIDGET_RESULT:", "FAILED " + str(failures) if failures else "ALL CHECKS PASSED")
