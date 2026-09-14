# Centerline junction angles

Select a centerline model produced by Extract Centerline, then click **Compute junction angles**. The module performs branch extraction internally and creates:

- a table with one row for every pair of branches of every bifurcation,
- compact tube-style 3D angle annotations for each pair of branches, grouped by pair type and branch order,
- compact tube-style bifurcation vector displays with start and end dots inside the same folders as the angle annotations they support.

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
| `BranchOrder` | Maximum branch order of the pair |
| `Branch1Order`, `Branch2Order` | Branch order of each branch in the pair |
| `Branch1Role`, `Branch2Role` | `Parent` or `Child` |
| `AngleDegrees` | Angle between the outward directions of the two branches |
| `InPlaneAngleDegrees` | Angle of the pair projected onto the bifurcation plane. For a bifurcation whose branches are in one plane it is the same as `AngleDegrees`; the difference between the two shows how much of the angle is out of the bifurcation plane |
| `Branch1OutOfPlaneAngleDegrees`, `Branch2OutOfPlaneAngleDegrees` | Angle between each branch and the bifurcation plane |

All the pairs of branches of the table are annotated. Arcs at each junction use staggered radii, with each label at its own arc midpoint, to reduce overlap at trifurcations and other junctions. Staggering expands outward from the original inner radius, extending annotation rays as needed without changing measured bifurcation vectors. Radial levels are assigned by branch IDs across pair types and remain fixed when filtering or hiding groups. View-dependent overlap can still occur. The annotations are therefore grouped in 'Child-child angles' and 'Parent-child angles' folders, then by branch order, so that pair types or distal annotations can be shown or hidden at once with the eye icon of the Data module. Each branch-order folder contains the angle rays, arcs, labels, and the corresponding tube-style bifurcation vectors with start and end dots for that pair type and order. Angle rays are yellow by default; arcs and their corresponding angle labels are colored by their measured `AngleDegrees` using the sequential Plasma color table (purple through orange to yellow), mapped linearly over the minimum and maximum measured angles shared by all groups in a computation; bifurcation vectors are orange and slightly transparent. The 3D tube rays, tube arcs, labels, and vector tubes are stored in grouped nodes instead of one markup node per measurement, which keeps large trees much smaller in the scene.

An annotation label shows the angle value only; the pair of branches it belongs to is told by its folder and color, while the exact branch IDs are stored in the table. Its rays are drawn several times longer than the measured segments so that they are readable next to the vessel: the angle depends on the directions of the rays only, and the bifurcation vector display in the same folder shows over what distance each direction was measured.

Labels that share a color are stored together in a markup node within their pair-type and branch-order folder. Label colors match the default arc color scale at creation time. Using the measured range increases contrast when angles cluster within a small interval. Filtering or hiding groups does not change this range. Separate computations may use different ranges; colors should therefore be compared within a computation. If all angles are equal, the range is padded by half a degree within 0–180° and all angles retain the same color. Arc tubes receive 3D lighting, so their apparent colors vary with surface orientation. Angle labels are unlit screen-facing text and share the arcs’ base colors. Labels use contrasting text shadows for visibility: white for darker text and black for brighter text.

Each arc model stores `AngleDegrees` as point scalars, with a constant value along each arc, including its tube caps. You can change the color table or scalar range in the Models module.

Native angle markup nodes were considered for the 3D measurements. They work well for a small number of interactable angles, but one node per angle becomes expensive for large centerline trees and does not provide all display controls used here. In Slicer 5.12.3, a synthetic 900-angle scene took about 456 ms per rendered frame, 85 s to save, and 7.3 s to delete when represented by native angle markups; the grouped tube display took about 96 ms per frame, 0.95 s to save, and 0.5 s to delete. Native angle markups also render their arcs and rays as tubes, so they have the same lighting/color mismatch with unlit text labels, and their arc radius is derived from the shorter ray length rather than stored as an independently controlled staggered radius. The grouped representation is therefore used for generated results, while the table remains the self-contained measurement record.

Set **Minimum angle** and click **Apply angle threshold** to hide labels, arcs, and rays below that value. Angles equal to the threshold remain visible, and colors are preserved. **Clear angle threshold** removes the filter. Filtering changes only the display: the measurements and table remain intact, and bifurcation vectors are unaffected.

The generated display nodes are locked, since they are measurement results. Every run creates its own nodes and folders.

Branch extraction is cached while the selected centerline is unchanged. Recomputing angles reuses that extraction and the bifurcation vectors; modifying the input or closing the scene clears the cache. The first calculation still performs full-resolution VMTK branch extraction, which can be slow for large trees. Each run creates fresh output nodes.

The module provides separate visibility checkboxes for arcs, angle annotations, rays, and vectors, checkboxes for parent-child and child-child angle pairs, and one checkbox for each branch order present in the scene. The pair-type checkboxes also control the corresponding vectors and vector names. An element is visible only when its element, pair-type, and branch-order checkboxes are enabled; the angle threshold still applies. Vector visibility also controls vector names when those were generated. Ray and vector color pickers update existing outputs and are used for new outputs. These controls apply to all junction-angle outputs in the scene, and their settings are saved with the scene. Clearing the angle threshold does not override the visibility checkboxes.
