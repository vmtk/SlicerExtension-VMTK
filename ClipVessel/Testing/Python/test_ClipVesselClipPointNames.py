"""Naming the clip points from the panel.

A clip point's label is the name its cap carries downstream, so this table is where the naming of
a case happens - during clipping rather than after meshing, which is the point of it: otherwise
it means waiting for a mesh to find out what has to be typed, and waiting again for another if
the meshing parameters change. It replaces right-click-rename on each point, and on a case with
two dozen vessel ends the thing an operator needs is the list, not a control for whichever point
happens to be selected.

What has to hold: the table says what the points say, editing a row names that point and no
other, and it never quietly unnames one.
"""

import unittest

import slicer

from ClipVessel import _CLIP_POINT_NAME_COLUMN, _CLIP_POINT_NAME_COLUMNS
from ClipVesselTestFixture import clipVesselModuleWidget


class ClipPointNamesTest(unittest.TestCase):

    def setUp(self):
        slicer.mrmlScene.Clear()
        self.widget = clipVesselModuleWidget()
        # Slicer owns one widget per module and hands back the same one every time, so state a
        # previous test left on it outlives the scene being cleared.
        self.widget._activeClipPointIndex = -1
        self.widget._activeClipPointId = None
        self.widget._planeEditing = False
        self.clipPoints = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode",
                                                             "Clip points")
        for label in ("Inlet", "Outlet 1", "Outlet 2"):
            index = self.clipPoints.AddControlPoint([0.0, 0.0, 0.0])
            self.clipPoints.SetNthControlPointLabel(index, label)
        self.widget._parameterNode.SetNodeReferenceID("ClipPoints", self.clipPoints.GetID())
        self.widget.rebuildClipPointNamesTable()
        self.table = self.widget.ui.clipPointNamesTable

    def shown(self):
        return [self.table.item(row, _CLIP_POINT_NAME_COLUMN).text()
                for row in range(self.table.rowCount)]

    def labels(self):
        return [self.clipPoints.GetNthControlPointLabel(i)
                for i in range(self.clipPoints.GetNumberOfControlPoints())]

    def setCell(self, row, text):
        """Type a name into a row, as editing the cell does."""
        self.table.item(row, _CLIP_POINT_NAME_COLUMN).setText(text)
        self.widget.onClipPointNameEdited(row, _CLIP_POINT_NAME_COLUMN)

    def test_the_table_lists_every_clip_point_in_order(self):
        """Row order is clip point order, which is also the order the caps are numbered in."""
        self.assertEqual(self.table.columnCount, len(_CLIP_POINT_NAME_COLUMNS))
        self.assertEqual(self.table.rowCount, 3)
        self.assertEqual([self.table.item(row, 0).text() for row in range(3)], ["1", "2", "3"])
        self.assertEqual(self.shown(), ["Inlet", "Outlet 1", "Outlet 2"])

    def test_only_the_name_column_can_be_edited(self):
        import qt
        self.assertTrue(self.table.item(0, _CLIP_POINT_NAME_COLUMN).flags() & qt.Qt.ItemIsEditable)
        self.assertFalse(self.table.item(0, 0).flags() & qt.Qt.ItemIsEditable)

    def test_editing_a_row_names_that_point_and_no_other(self):
        self.setCell(1, "RSVC")
        self.assertEqual(self.labels(), ["Inlet", "RSVC", "Outlet 2"])
        self.assertEqual(self.shown(), ["Inlet", "RSVC", "Outlet 2"])

    def test_an_empty_cell_does_not_unname_a_point(self):
        """Clearing a cell is too easy to do by accident, and a point with no label at all is one
        whose cap arrives unnamed downstream. The name it had goes back into the cell."""
        self.setCell(0, "")
        self.assertEqual(self.labels(), ["Inlet", "Outlet 1", "Outlet 2"])
        self.assertEqual(self.shown(), ["Inlet", "Outlet 1", "Outlet 2"])

    def test_a_rename_from_elsewhere_reaches_the_table(self):
        """The markups module, or a script, can rename a point while this panel is open.

        Renames arrive as modified events, and can arrive with no plane being edited, which is
        why the refresh sits ahead of the guard in onClipPointModified.
        """
        self.clipPoints.SetNthControlPointLabel(2, "azygous_vein")
        self.assertEqual(self.shown(), ["Inlet", "Outlet 1", "azygous_vein"])

    def test_the_table_follows_points_being_added_and_removed(self):
        self.clipPoints.RemoveNthControlPoint(0)
        self.assertEqual(self.table.rowCount, 2)
        self.assertEqual(self.shown(), ["Outlet 1", "Outlet 2"])

        index = self.clipPoints.AddControlPoint([1.0, 0.0, 0.0])
        self.clipPoints.SetNthControlPointLabel(index, "IVC")
        self.widget.rebuildClipPointNamesTable()
        self.assertEqual(self.table.rowCount, 3)
        self.assertEqual(self.shown(), ["Outlet 1", "Outlet 2", "IVC"])

    def test_selecting_a_row_selects_that_clip_point_in_the_views(self):
        """Reading a name off a row says nothing about where that vessel end is on the anatomy."""
        self.clipPoints.CreateDefaultDisplayNodes()
        self.table.setCurrentCell(2, _CLIP_POINT_NAME_COLUMN)
        self.widget.onClipPointNameRowSelected()
        self.assertEqual(self.clipPoints.GetDisplayNode().GetActiveControlPoint(), 2)

    def test_a_different_clip_points_node_rebuilds_the_table(self):
        other = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "Other points")
        other.SetNthControlPointLabel(other.AddControlPoint([0.0, 0.0, 0.0]), "aorta")
        self.widget._parameterNode.SetNodeReferenceID("ClipPoints", other.GetID())
        self.widget.observeClipPointsNode(other)
        self.assertEqual(self.shown(), ["aorta"])

    def test_capping_the_output_is_off_by_default(self):
        """The usual next step makes the caps itself, past a boundary layer, where they belong.

        Checked here because the checkbox and the parameter node used to disagree: the box was
        drawn unchecked and the default said true, so what the panel showed was not what a run
        would do.
        """
        self.assertEqual(self.widget._parameterNode.GetParameter("CapOutputSurface"), "false")
        self.assertFalse(self.widget.ui.capOutputSurfaceModelCheckBox.checked)


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
