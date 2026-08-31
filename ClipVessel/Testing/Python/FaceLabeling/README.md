# Face labeling regression suites

Developer tests for the "Label mesh faces" option. Not registered with CTest: most need a Slicer
application with the module loaded and assert on MRML display state, not logic alone.

    ./run_all.sh [path/to/Slicer]

Each prints `  PASS` / `  FAIL` per check and a `*_RESULT:` summary.

| suite | pins down |
| --- | --- |
| `test_facelabels.py` | id layout, cap-to-clip-point matching, mis-sized input labels dropped |
| `test_cellorder.py` | vert/line cells take the low cell indices while capping copies only polys |
| `test_defect_holes.py` | a hole from a missing triangle joins the face around it |
| `test_preprocess_labels.py` | labels survive preprocessing, degenerate triangles and decimation |
| `test_legend_labels.py` | reproduces the renderer's label logic, so a "(none)" legend fails here |
| `test_widget.py` | GUI round trip, automatic colouring, colour table range and naming |
| `test_visible.py` | the mesh still draws when coloured by face id |
| `test_warning.py` | the preprocessing confirmation fires in one case and stays silent in five |
| `test_apply_widget.py` | the widget's Apply path end to end |
| `run_labeling_e2e.py` | the full pipeline on a real vessel surface, including a labeled input |

`diagnose_labels.py` and `diagnose_holes.py` are not tests. Run them inside a Slicer session that
has just applied Clip Vessel, to inspect a real case:

    exec(open('.../FaceLabeling/diagnose_labels.py').read())

The first reports where each face id came from and measures, against a cell locator, whether the
labels stayed on the geometry they started on. The second counts open boundaries at each stage,
to show where an unexpected hole is introduced.
