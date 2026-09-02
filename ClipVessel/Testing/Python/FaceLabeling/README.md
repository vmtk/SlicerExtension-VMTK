# Face labeling tests

See how to run the tests in the
[developer notes](../../../../Docs/Developers.md#testing).

## Logic tests

No widget, no MRML display state.

| test | pins down |
| --- | --- |
| `test_ClipVesselFaceLabels.py` | id layout, cap-to-clip-point matching, mis-sized input labels dropped |
| `test_ClipVesselCellOrder.py` | vert/line cells take the low cell indices while capping copies only polys |
| `test_ClipVesselDefectHoles.py` | a hole from a missing triangle joins the face around it |

`test_ClipVesselDefectHoles` takes its fixtures from `test_ClipVesselCellOrder`, which works
because Slicer puts the script's own directory on `sys.path`.

## Tests that use the module widget

| test | pins down |
| --- | --- |
| `test_ClipVesselPreprocessingWarning.py` | the preprocessing confirmation fires in one case and stays silent in five |
| `test_ClipVesselPreprocessLabels.py` | labels survive preprocessing, degenerate triangles and decimation |
| `test_ClipVesselLegendLabels.py` | reproduces the renderer's label logic, so a "(none)" legend fails here |
| `test_ClipVesselWidget.py` | widget round trip, automatic colouring, colour table range and naming |
| `test_ClipVesselFaceColoringVisible.py` | the mesh still draws when coloured by face id |
| `test_ClipVesselApply.py` | the widget's Apply path end to end, on a downloaded vessel surface |

`test_ClipVesselPreprocessLabels` decimates through the CLI decimation module, and
`test_ClipVesselFaceColoringVisible` renders a 3D view, so neither is given
`--disable-cli-modules`.

These take the module's own widget from `clipVesselModuleWidget()` in
`ClipVesselTestFixture.py` rather than assembling one around a `qMRMLWidget`. Slicer owns that
widget and destroys it before the scene, so none of them has to hand the scene back, call
`cleanup()`, or pump the event loop to have the widget go away -- which a hand-built one does
need, since `setup()` gives the scene to the widgets loaded from the `.ui` file and a widget left
alive holds it, and every node the scene owns, to the end of the process. Only
`test_ClipVesselWidget` builds a second, independent widget, for the one case that needs a widget
which has not seen what the first one did, and that one it cleans up itself.

## Tests on a real vessel surface

These three build their case from `ClipVesselTestFixture.py`, which downloads a vessel surface,
extracts its centerline and places a clip point at each end. That module is deliberately not named
`test_*`, so a collector imports it rather than collecting it, and it builds the case once per
process and hands the same one to each test.

| test | pins down |
| --- | --- |
| `test_ClipVesselLabelingEndToEnd.py` | the whole pipeline capped, with and without flow extensions: every cap carries its own clip point's id and sits where that clip point is |
| `test_ClipVesselBoundaryStages.py` | only the cuts open boundaries: no mesh defect survives to be capped as a face nobody asked for |
| `test_ClipVesselLabelPlacement.py` | labels the input carried stay on the geometry they came from, measured with a cell locator rather than by cell index |

The last two were diagnostics to paste into a session after an Apply, which printed what they
found and left the reading to you. They now build their own case and check it.
`test_ClipVesselLabelPlacement` labels two patches well away from every clip point: a patch on a
vessel end is mostly cut away, and where the remnant's centre of mass ends up says nothing about
whether the labels stayed put.

