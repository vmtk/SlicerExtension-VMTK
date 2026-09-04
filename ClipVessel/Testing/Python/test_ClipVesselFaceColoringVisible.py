"""The mesh must still be drawn when face colouring is switched on. Measured by comparing the
rendered frame against the same frame with the model hidden, so it cannot be fooled by the
background gradient."""
import unittest
import slicer, qt, vtk, numpy as np
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy
import ClipVessel
from ClipVesselTestFixture import clipVesselModuleWidget


class ClipVesselFaceColoringVisibleTest(unittest.TestCase):
    def setUp(self):
        slicer.mrmlScene.Clear()

    def test_FaceColoringVisible(self):
        failures = []
        def check(name, cond, detail=""):
            print(("  PASS  " if cond else "  FAIL  ") + name + (f"  {detail}" if detail else ""), flush=True)
            if not cond: failures.append(name)

        w = clipVesselModuleWidget()
        pn = w._parameterNode
        out = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Output surface model")
        sphere = vtk.vtkSphereSource(); sphere.SetThetaResolution(12); sphere.SetPhiResolution(12); sphere.Update()
        pd = vtk.vtkPolyData(); pd.DeepCopy(sphere.GetOutput())
        n = pd.GetNumberOfCells()
        # Two faces the input already carries, the rest left unlabeled so that a wall exists.
        vals = np.zeros(n, dtype=np.int32); vals[: n // 4] = 1; vals[n // 4 : n // 3] = 2
        arr = numpy_to_vtk(vals, deep=True, array_type=vtk.VTK_INT); arr.SetName("ModelFaceID")
        pd.GetCellData().AddArray(arr); pd.GetCellData().SetActiveScalars("ModelFaceID")
        out.SetAndObserveMesh(pd); out.CreateDefaultDisplayNodes()
        pn.SetNodeReferenceID("OutputSurfaceModel", out.GetID())
        pn.SetParameter("ModelFaceIdArrayName", "ModelFaceID")

        view = slicer.qMRMLThreeDWidget(); view.setMRMLScene(slicer.mrmlScene)
        vn = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLViewNode")
        vn.SetBoxVisible(False); vn.SetAxisLabelsVisible(False)
        view.setMRMLViewNode(vn); view.resize(400, 400); view.show()
        slicer.app.processEvents()
        t3d = view.threeDView(); t3d.resetFocalPoint()

        def frame():
            t3d.forceRender(); slicer.app.processEvents()
            f = vtk.vtkWindowToImageFilter(); f.SetInput(t3d.renderWindow()); f.ReadFrontBufferOff(); f.Update()
            img = f.GetOutput(); d = img.GetDimensions()
            return vtk_to_numpy(img.GetPointData().GetScalars()).reshape(d[1], d[0], -1)[:, :, :3].astype(int)

        def modelPixels():
            """Pixels that differ from the same scene with the model hidden."""
            out.GetDisplayNode().SetVisibility(False); empty = frame()
            out.GetDisplayNode().SetVisibility(True);  shown = frame()
            return int(np.count_nonzero(np.abs(shown - empty).sum(axis=2) > 12))

        pn.SetParameter("LabelModelFaces", "false")
        w.updateOutputFaceColoring()
        plain = modelPixels()
        check("model draws with labeling off", plain > 1000, f"{plain} px")

        pn.SetParameter("LabelModelFaces", "true")
        # A layout has to exist for a table to be built; label first, as Apply would.
        w.logic.labelModelFaces(pd, [], "ModelFaceID", vals)
        w.updateFaceColorTable()
        w.updateOutputFaceColoring()
        colored = modelPixels()
        check("model still draws with labeling on", colored > 1000, f"{colored} px")
        check("same coverage as uncoloured (not vanished, not translucent)",
              abs(colored - plain) < max(60, plain * 0.06), f"coloured {colored} vs plain {plain}")

        dn = out.GetDisplayNode()
        table = w.faceColorTable(create=False)
        lut = table.GetLookupTable()
        check("colour table is opaque", lut.IsOpaque() == 1, lut.IsOpaque())
        check("scalar range spans the table", tuple(dn.GetScalarRange()) == (0.0, float(table.GetNumberOfColors())),
              dn.GetScalarRange())
        rgb = [0.0, 0.0, 0.0]
        mapped = []
        for faceId in range(table.GetNumberOfColors()):
            lut.SetTableRange(*dn.GetScalarRange())
            lut.GetColor(float(faceId), rgb)
            mapped.append(tuple(round(c, 3) for c in rgb))
        expected = [tuple(round(c, 3) for c in lut.GetTableValue(i)[:3]) for i in range(table.GetNumberOfColors())]
        check("each face id maps to its own table entry", mapped == expected, f"{mapped} vs {expected}")
        # The sphere's ids are fed in as labels the input already carried, so 1/2/3 compact to 1/2/3
        # and the wall takes the next id.
        wallFaceId = w.logic.lastWallFaceId
        check("wall is the id after the input's own faces", wallFaceId == 3, wallFaceId)
        check("wall is the neutral grey", mapped[wallFaceId] == (0.78, 0.78, 0.812), mapped[wallFaceId])
        check("the two input faces and the wall are all distinct",
              len({mapped[1], mapped[2], mapped[wallFaceId]}) == 3, mapped[1:4])
        view.hide()
        print()

        # The widget belongs to the module manager, which destroys it before the scene, so it is
        # left alone here.
        slicer.mrmlScene.Clear()

        self.assertEqual(failures, [], "%d check(s) failed: %s" % (len(failures), failures))
if __name__ == "__main__":
    # Run by slicer_add_python_test as "Slicer --python-script", which reports the outcome through
    # the exit code: an exception fails the test, a clean return passes it. unittest.main() is not
    # used because it exits the interpreter itself, taking Slicer down before it can report.
    import sys
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise AssertionError("%d failure(s) and %d error(s) in %d test(s)"
                             % (len(result.failures), len(result.errors), result.testsRun))
