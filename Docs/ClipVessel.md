# Clip Vessel
This module serves to clip or truncate a vessel based on user provider points. The user must provide a surface as input (in either model or segmentation format) as well as vessel centerlines created by the VMTK module [**ExtractCenterline**.](https://github.com/vmtk/SlicerExtension-VMTK/blob/master/Docs/ExtractCenterline.md). All branches/vessels should contain a centerline otherwise the clipping may produce undesired geometries in regions without a centerline.  Finally, the user must provide a list of fiducial points that represent where the model will be clipped. The first point is assumed to be the vessel inlet and will clip accordingly. If the output model needs to be capped this can be triggered by the checkbox. The module outputs the clipped surface.

![Clip points](ClipVessel_0.png)
**Placement of markup points to define clipping locations**

![Clipped vessel](ClipVessel_1.png)
**Clipped vessel**


## Advanced
Advanced options include preprocessing of the input surface and the addition of flow extensions.
Refer to [here](https://github.com/vmtk/SlicerExtension-VMTK/blob/master/Docs/ExtractCenterline.md#:~:text=Extract%20centerline-,Preprocessing,-The%20module%20requires) for preprocessing options related to the input surface. When creating flow extensions the user can control the extension length ratio, the extension mode, and the interpolation mode. The extension length ratio sets the length of each extension as a multiple of the radius of the vessel end that it is attached to (for example, 2 adds an extension that is twice as long as the radius of that clipped end, default 2). The extension mode selects the direction of the extension: along the direction of the centerline at the vessel end, or along the normal of the clipped boundary. The interpolation mode selects how the original outlet is transitioned to the outlet of the extension: ramp fades the original cross-section into the target one along a smooth curve that is flat at both ends, so the extension leaves the clipped boundary and settles into the uniform tube without a crease (default); linear fades them at a constant rate; thin plate spline warps the transition instead, which loses the finer features of a non-circular outlet within the first few layers of the extension. The transition length ratio sets how much of the extension length is used for the transition (0 = the target cross-section is reached immediately at the clipped boundary, 1 = the whole extension, default 0.25). By default the target cross-section is a circle; enable *preserve cross-section shape* to keep the outline of the clipped vessel end along the whole extension instead, so that the area distribution of a non-circular outlet is not altered (note that a strongly concave outline may be hard to cap).

The length of an individual flow extension can also be adjusted: click a clip point to select the vessel endpoint, then use the *extension length scale* slider (in the Inputs section, next to the clip plane adjustment buttons) to scale the length of the extension grown from that endpoint relative to the common length set by the extension length ratio. Endpoints left at 1.0x keep the common length.

![Clipped vessel extended](ClipVessel_2.png)
**Clipped vessel with flow extensions**


## Acknowledgement
This module has been contributed by David Molony and is heavily based on the ExtractCenterline module.