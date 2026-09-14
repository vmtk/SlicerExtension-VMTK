"""What the output surface records about where the names of its faces are.

The face ids are in the output's cell data and the names are control point labels on the clip
points markups node; between them sits an offset that is written down nowhere on the output
(faceIdLayout decides it from what the input carried). So a face id cannot be turned back into a
name by anything holding only the surface. This is the record that makes it possible - the node,
and which control point each cap's face id came from - and it is the whole of what Mesh Prep and
a case setup downstream have to go on.
"""

import json
import unittest

import slicer

from ClipVessel import (CLIP_POINTS_NODE_REFERENCE_ROLE, FACE_ID_TO_CLIP_POINT_ID_ATTRIBUTE,
                        WALL_FACE_ID_ATTRIBUTE)
from ClipVesselTestFixture import aortaCase


def resolveNames(modelNode):
    """Face id -> vessel name, read the way a downstream module reads it.

    None for a face whose clip point is gone: the caller asked for a name and there is not one,
    which is a different answer from there being no record at all.
    """
    stored = modelNode.GetAttribute(FACE_ID_TO_CLIP_POINT_ID_ATTRIBUTE)
    markups = modelNode.GetNodeReference(CLIP_POINTS_NODE_REFERENCE_ROLE)
    if not stored or markups is None:
        return {}
    names = {}
    for faceId, controlPointId in json.loads(stored).items():
        index = markups.GetNthControlPointIndexByID(controlPointId)
        names[int(faceId)] = markups.GetNthControlPointLabel(index) if index >= 0 else None
    return names


class ClipVesselNameSourceTest(unittest.TestCase):
    """Built once and shared: building the case clips a real aorta.

    So no test here may leave the clip points changed. The one that has to delete a point works
    on a copy of the node.
    """

    @classmethod
    def setUpClass(cls):
        cls.case = aortaCase()

    def recordedCase(self, **clipArguments):
        """Clip the aorta and record the name source on a model node, as Apply does."""
        case = self.case
        case.clip(**clipArguments)
        outputModelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Clipped")
        case.logic.recordNameSource(outputModelNode, case.clipPointsMarkupsNode)
        return case, outputModelNode

    def test_every_cap_records_the_clip_point_that_named_it(self):
        """The recorded names are the clip point labels, cap for cap.

        Checked against lastFaceIdAssignments, which is what the status line and the face colour
        table already show: the record has to say the same thing they do, or the panel downstream
        and the panel the operator typed the labels into disagree about the same mesh.
        """
        case, outputModelNode = self.recordedCase(cap=True)

        self.assertEqual(outputModelNode.GetNodeReference(CLIP_POINTS_NODE_REFERENCE_ROLE),
                         case.clipPointsMarkupsNode)
        self.assertEqual(outputModelNode.GetAttribute(WALL_FACE_ID_ATTRIBUTE), "1")
        self.assertEqual(resolveNames(outputModelNode), dict(case.logic.lastFaceIdAssignments))
        self.assertEqual(len(resolveNames(outputModelNode)), case.numberOfClipPoints)

    def test_the_names_survive_flow_extensions(self):
        """Growing a flow extension does not cost the names.

        Worth its own test: an extension rebuilds the mesh and keeps no cell data, which is why
        faceIdLayout has to be told whether the input's ids will still be there. The record is
        built from the clip points rather than from the surface, so it comes through - but that is
        the kind of thing that holds until somebody moves one line.
        """
        case, outputModelNode = self.recordedCase(cap=True, addFlowExtensions=True)
        self.assertEqual(resolveNames(outputModelNode), dict(case.logic.lastFaceIdAssignments))

    def test_renaming_a_clip_point_renames_its_face(self):
        """The name follows the control point, with nothing re-clipped and nothing re-recorded.

        This is the point of recording the node rather than the labels: the labels are not copied
        anywhere, so there is no second copy to go stale. Fixing a typo upstream fixes the face.
        """
        case, outputModelNode = self.recordedCase(cap=True)
        faceId = min(resolveNames(outputModelNode))
        originalLabel = case.clipPointsMarkupsNode.GetNthControlPointLabel(faceId - 2)
        try:
            case.clipPointsMarkupsNode.SetNthControlPointLabel(faceId - 2, "RSVC")
            self.assertEqual(resolveNames(outputModelNode)[faceId], "RSVC")
        finally:
            case.clipPointsMarkupsNode.SetNthControlPointLabel(faceId - 2, originalLabel)

    def test_deleting_a_clip_point_unnames_its_face_and_no_other(self):
        """A deleted clip point leaves its own face unnamed and every other name where it was.

        The reason the map is keyed by control point ID. A cap's face id is
        firstCapFaceId + clip point index, so deleting a clip point shifts every later index down
        one: keyed by index, each of those vessels' names would move onto the face of the vessel
        before it - quietly, since both are valid names for valid faces. Downstream that is a
        boundary condition on the wrong vessel, which nothing further along can catch. Keyed by ID
        the deleted point simply fails the lookup.

        Done on a copy of the clip points node so that the shared case survives. CopyContent
        carries the control point IDs across, which is what lets the copy answer for the original.
        """
        case, outputModelNode = self.recordedCase(cap=True)
        before = resolveNames(outputModelNode)
        self.assertGreaterEqual(len(before), 3, "needs three caps for a deletion to shift one")

        clipPointsCopy = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode",
                                                            "Clip points (copy)")
        clipPointsCopy.CopyContent(case.clipPointsMarkupsNode)
        outputModelNode.SetNodeReferenceID(CLIP_POINTS_NODE_REFERENCE_ROLE, clipPointsCopy.GetID())
        self.assertEqual(resolveNames(outputModelNode), before, "the copy should answer the same")

        faceIds = sorted(before)
        deletedFaceId = faceIds[len(faceIds) // 2]
        clipPointsCopy.RemoveNthControlPoint(deletedFaceId - 2)

        after = resolveNames(outputModelNode)
        self.assertIsNone(after[deletedFaceId])
        self.assertEqual(after, {faceId: (None if faceId == deletedFaceId else name)
                                 for faceId, name in before.items()})

        # Control point IDs come from a counter that does not go back, so the face of a deleted
        # clip point stays unnamed rather than being taken over by the next point placed.
        clipPointsCopy.AddControlPoint([0.0, 0.0, 0.0])
        self.assertIsNone(resolveNames(outputModelNode)[deletedFaceId])

    def test_the_names_are_recorded_with_capping_and_labeling_both_off(self):
        """The case the whole thing has to serve, and the one that nearly did not work.

        A workflow that meshes in CFD Mesh Generator clips with *Cap output surface* off - the
        mesher makes the caps, past the boundary layer, where they belong - and then labeling
        the faces does nothing, because there are no caps yet to label. So the run that most
        needs the names carries neither a cap nor a face id array, and the face ids its mesh
        ends up with come from the BoundaryLabels point data instead.

        The mapping is recorded where the boundaries are labelled for exactly this reason. Were
        it taken from the face labeling, the names would be there in every run that does not
        need them and missing from the one that does.
        """
        case = self.case
        case.clip(cap=False, labelModelFaces=False)
        outputModelNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Clipped")
        case.logic.recordNameSource(outputModelNode, case.clipPointsMarkupsNode)

        # No face id array on the surface at all, and the record is there all the same.
        self.assertIsNone(case.clip(cap=False, labelModelFaces=False)
                          .GetCellData().GetArray("ModelFaceID"))
        case.logic.recordNameSource(outputModelNode, case.clipPointsMarkupsNode)
        self.assertEqual(outputModelNode.GetAttribute(WALL_FACE_ID_ATTRIBUTE), "1")
        self.assertEqual(
            resolveNames(outputModelNode),
            {faceId: case.clipPointsMarkupsNode.GetNthControlPointLabel(faceId - 2)
             for faceId in range(2, 2 + case.numberOfClipPoints)})

    def test_a_run_that_matched_no_boundary_records_nothing(self):
        """And clears what the run before left, rather than describing a surface that is gone.

        The output node is reused across runs, so what is on it is the previous run's. There is
        no cheap way to make every cut fail on the real aorta, so the run state is emptied
        directly - what is being checked is that recordNameSource believes it rather than
        leaving the attributes it wrote last time.
        """
        case, outputModelNode = self.recordedCase(cap=True)
        self.assertIsNotNone(outputModelNode.GetAttribute(FACE_ID_TO_CLIP_POINT_ID_ATTRIBUTE))

        case.logic.lastFaceIdControlPointIds = {}
        case.logic.recordNameSource(outputModelNode, case.clipPointsMarkupsNode)

        self.assertIsNone(outputModelNode.GetAttribute(FACE_ID_TO_CLIP_POINT_ID_ATTRIBUTE))
        self.assertIsNone(outputModelNode.GetAttribute(WALL_FACE_ID_ATTRIBUTE))
        self.assertIsNone(outputModelNode.GetNodeReference(CLIP_POINTS_NODE_REFERENCE_ROLE))


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
