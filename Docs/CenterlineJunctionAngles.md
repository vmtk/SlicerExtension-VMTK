# Centerline junction angles

Select a centerline model produced by Extract Centerline, then click **Compute junction angles**. The module performs branch extraction internally and creates:

- a table with one row for every pair of branches of every bifurcation,
- native angle markup annotations for each pair of branches, grouped by pair type and branch order,
- one editable bifurcation vector markup for each branch of each bifurcation, in a 'Bifurcation vectors' folder grouped by branch order.

![Centerline junction angles](CenterlineJunctionAngles.png)

The measurement uses the bifurcation reference systems and the bifurcation vectors of VMTK, as the 'vmtkbifurcationreferencesystems' and 'vmtkbifurcationvectors' scripts do. For each bifurcation, VMTK computes a reference system: an origin, which is a radius weighted barycenter of the bifurcation, a bifurcation plane `Normal`, and an `UpNormal` that points from the parent branch towards the daughter branches. For each branch of the bifurcation, it computes a bifurcation vector: the end of the branch group that is next to the bifurcation region is taken, and the branch is walked away from the bifurcation up to the center of the first maximum inscribed sphere that touches that end point. The vector connects those two points, so its length is of the order of the local vessel radius.

Two properties of this definition are worth knowing. The vectors are computed on the branches, where each branch follows its own path through the bifurcation, and not on a merged centerline where the branches share a single trunk near the bifurcation: the measured angle is therefore the angle of the branches themselves. And the measurement distance follows the local vessel radius, so there is no scale to choose and the measurement behaves the same way in large and small vessels. On synthetic tubes whose axes meet at a known angle, it recovers the angle of the axes within about one degree, for vessel radii between 2 and 8 mm and independently of the branch lengths.

The vector of a branch is stored by VMTK along the flow direction, which means that the vector of the parent branch points towards the bifurcation. This module reverses it, so that all directions point away from the bifurcation and the angle of a pair of branches is directly the angle between the two directions, in the 0-180 degrees range: 180 degrees means that the two branches continue each other in a straight line. Note that the direction of a branch is measured just outside the bifurcation region, so for a branch that curves near the bifurcation it is not the same as the direction of the centerline at the bifurcation itself.

A branch is identified by its `GroupId`, from the internal branch extraction. The table stores the bifurcation and both branch IDs for each angle. Parent and child roles come from the upstream/downstream classification of VMTK, which follows the flow direction that was used for the centerline extraction. Parent-child angles use outward directions, so a straight continuation measures 180 degrees; the flow deflection is its supplement. Child-child angles describe the branching angle.

| Column | Description |
| --- | --- |
| `BifurcationGroupId` | `GroupId` of the internally extracted bifurcation |
| `JunctionDegree` | Number of branches that meet at the bifurcation |
| `JunctionPosition` | Origin of the bifurcation reference system (RAS) |
| `Branch1GroupId`, `Branch2GroupId` | `GroupId` of the two branches of the pair |
| `BranchOrder` | Generation of the bifurcation, which is the branch order of its parent branch. Every angle of a bifurcation carries the same value, so hiding a branch order hides whole junctions |
| `Branch1Order`, `Branch2Order` | Branch order of each branch in the pair |
| `Branch1Role`, `Branch2Role` | `Parent` or `Child` |
| `AngleDegrees` | Angle between the outward directions of the two branches |
| `InPlaneAngleDegrees` | Angle of the pair projected onto the bifurcation plane. For a bifurcation whose branches are in one plane it is the same as `AngleDegrees`; the difference between the two shows how much of the angle is out of the bifurcation plane |
| `Branch1OutOfPlaneAngleDegrees`, `Branch2OutOfPlaneAngleDegrees` | Angle between each branch and the bifurcation plane |

All the pairs of branches of the table are annotated with native angle markup nodes. The annotations are grouped in 'Child-child angles' and 'Parent-child angles' folders, then by branch order, so that pair types or distal annotations can be shown or hidden at once with the eye icon of the Data module. The bifurcation vectors sit in a 'Bifurcation vectors' folder of their own, also by branch order: a branch is shared by every pair of its bifurcation, so its vector exists once rather than once per pair type. Angle markups are colored by their measured `AngleDegrees` using the sequential Plasma color table (purple through orange to yellow), mapped linearly over the minimum and maximum measured angles shared by all groups in a computation; bifurcation vectors are orange and slightly transparent.

Branch order is calculated from the complete ordered centerline tracts. Every root branch is order 0 and each downstream branch is one order higher than its parent. A centerline containing multiple disconnected trees has one order-0 root in each tree. Invalid or unavailable angle vectors may omit an angle measurement, but they do not break the branch hierarchy or create a false downstream root. A branch is shown as **Unassigned branch order** only when it cannot be reached through the extracted centerline topology.

The native annotation label is centered beyond its arc and shown as `Angle: 47.7°`. Slicer draws the label of a markup as the name of its node, a colon, and its enabled measurements, and offers no way to leave the name out, so every angle node is named `Angle`. One name for all of them keeps the label short and keeps Slicer from numbering it, at the cost of telling the annotations apart by name in the Data module. The pair of branches it belongs to is told by its folder and color, while the exact branch IDs are stored in the table and as markup-node attributes. The angle markup control points are drawn several times farther from the junction than the measured segments and staggered within each junction so that the arcs and labels remain readable next to the vessel. The angle depends on the directions of the rays only, and the bifurcation vector of each branch shows over what distance that direction was measured.

## Correcting a measurement

The bifurcation vectors are the editable end of the measurement and the angles follow them. Both ends of a vector are centerline positions, which is what makes them the right handles to drag: an angle ray is only the measured direction drawn out from the reference system origin, so its far end does not lie on a vessel. Angle markups are therefore locked and cannot be dragged. Keeping them out of picking also keeps a large tree responsive.

Drag either end of a bifurcation vector to correct the direction of a branch. Every angle of that bifurcation that uses the branch immediately follows: its ray, value, color, and label are recomputed from the new direction, while its vertex stays at the bifurcation reference system origin. An angle is a pair of directions, so only the directions are edited. The results table retains the originally computed centerline measurement.

With **Snap dragged vector endpoints to the centerline** enabled, the endpoint being dragged is held on the centerline of its own branch, so a corrected direction still runs along that branch instead of pointing anywhere in space. Only the dragged endpoint moves, so the end you are not holding keeps its measured position.

The snap offers one branch rather than the whole tree. Searching the whole tree pulls a handle onto whichever branch happens to lie nearest in space, which in a dense tree is often not the branch under the cursor. A bifurcation vector belongs to one branch, so only that branch is offered and the handle slides along it. The centerline of the branch is stored on the vector, so this still works in a scene that has been saved and reopened.

Which part of that branch is chosen is decided along the line of sight. A drag in a 3D view slides a handle across a plane facing the camera, so the handle sits under the cursor, and the part of the branch nearest that line of sight is the part being pointed at. Choosing the part nearest in space instead would pick whatever lies closest in depth, which is why the handle would otherwise appear to ignore the cursor. Where a branch doubles back and two of its parts are under the cursor, the nearer one is taken. In a view with several 3D panes the one under the pointer is used.

Depth therefore does not count against the snap: pulling a handle towards or away from the camera does not switch it off. Only a miss to the side does, and only beyond six vector lengths, after which the handle is left where it was put rather than pulled back. A vector is of the order of the local vessel radius and is well under a millimetre in a distal vessel, so the reach has to be a generous multiple of it. A handle can do nothing worse than slide along its own branch, so this is a comfort setting rather than a guard. Turn the option off to place an endpoint freely anywhere. **Reset selected vector** restores a vector's generated endpoints, and the angles measured from it with them.

Using the measured range increases contrast when angles cluster within a small interval. Filtering or hiding groups does not change this range. Separate computations may use different ranges; colors should therefore be compared within a computation. If all angles are equal, the range is padded by half a degree within 0–180° and all angles retain the same color. Native angle markup arcs and rays receive 3D lighting, so their apparent colors vary with surface orientation. Angle labels are unlit screen-facing text and share the angle markup color. Labels use contrasting text shadows for visibility: white for darker text and black for brighter text.

Each angle markup node stores `AngleDegrees`, `BifurcationGroupId`, `Branch1GroupId`, and `Branch2GroupId` as node attributes, and each vector markup stores `BifurcationGroupId`, `BranchGroupId`, `BranchRole`, and the centerline of its branch. The table remains the authoritative measurement record.

Set **Minimum angle** and click **Apply** to hide the angle annotations of the most recent computation below that value. Angles equal to the threshold remain visible, and colors are preserved. **Clear** removes the filter. Filtering changes only the display: the measurements and table remain intact, and bifurcation vectors are unaffected. Dragging a vector does not reapply the threshold while its endpoint is being held; click **Apply** to filter the edited values.

Every run creates its own nodes and folders. The bifurcation vector markups are editable; the angle markups are locked results.

Branch extraction is cached while the selected centerline is unchanged. Recomputing angles reuses that extraction and the bifurcation vectors; modifying the input or closing the scene clears the cache. The first calculation still performs full-resolution VMTK branch extraction, which can be slow for large trees. Each run creates fresh output nodes.

The module provides a snapping checkbox for vector dragging, visibility checkboxes for angle annotations and vectors, checkboxes for parent-child and child-child angle pairs, and one checkbox for each branch order in the most recent computation. If VMTK reports a component without any parent branch, its depth cannot be inferred and it appears as **Unassigned branch order** instead of being mislabeled order 0. The pair-type checkboxes apply to the angles only, since a vector belongs to a branch rather than to a pair. An element is visible only when its element, pair-type, and branch-order checkboxes are enabled; the angle threshold still applies. The vector color picker updates the active output and is used for new outputs. Scoping the controls to the latest result keeps older computations from adding unrelated branch-order controls. The settings are saved with the scene. Clearing the angle threshold does not override the visibility checkboxes.
