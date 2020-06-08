The VMTK Extension for 3D Slicer
--------------------------------

This extension makes the Vascular Modeling Toolkit (VMTK, http://www.vmtk.org/) available in 3D Slicer (www.slicer.org). Features include vessel tree segmentation and centerline extraction. Short demo video of vessel segmentation and centerline extraction is available here: https://youtu.be/caEuwJ7pCWs

[![](https://img.youtube.com/vi/caEuwJ7pCWs/0.jpg)](https://www.youtube.com/watch?v=caEuwJ7pCWs "VMTK demo")

# Installation

VMTK extension is available for recent 3D Slicer versions (Slicer-4.10 and above). Install 3D Slicer, start 3D Slicer, and in the extension manager install SlicerVMTK extension.

# Usage

SlicerVMTK extension provides the following modules - listed in in Vascular Modeling Toolkit category in the module list.

## Vesselness Filtering

Image processing operation that increases brightness of tubular structures and suppresses other shapes (plates and blobs). This module can be used to pre-process image data to make vessel segmentation easier.


## Level Set Segmentation

This module can segment a *single vessel branch* of a vessel tree from an image (either unprocessed or vesselness-filtered can be used).

## Centerline Computation

Determine centerlines in a vessel tree from an input model node. Click "Preview" button for a quick validation of the input model and approximate centerline computation. Click "Start" button for full network analysis and computation of all outputs.

Required inputs:
- Vessel tree model: this can be any tree structure (not just vascular tree but airways, etc.), either created in Segment Editor module or using Level Set Segmentation module. If Segment Editor is used then segmentation node must be exported to model node by right-clicking on the segmentation in Data module and selecting "Export visible segments to models".
- Start point: a markups fiducial node containing a single point, this should be placed at the branch of the tree

Outputs:
- Centerline model: network extraction results (without branch extraction and merging). Points contain centerline points, and "Radius" point data contains maximum inscribed sphere radius at each point.
- Centerline endpoints: Coordinates of found start point and all detected branch endpoints.
- Voronoi model (optional): medial surface of the input model (medial surface contains points that are qat equal distance from nearest surface points)
- Curve tree rool (optional): if a markups curve node is selected then a hierarchy of curve nodes are created from extracted and merged branches. CellId of each branch is saved into the node's name (and also as node attribute), which can be used for cross-referencing with CellId column of centerline properties table.
- Centerline properties (optional): if a table node is selected then branch length, average radius, curvature, torsion, and tortuosity is computed for all the extracted and merged branches.

![](CenterlineComputationOutput1.png)

# Advanced analysis

Results can quantitatively analyzed in Slicer's Python interactor (or by implementing custom Slicer modules).

## Examples

Get centerline point coordinates and radii as numpy array and print them:

```python
c = getNode('CenterlineComputationModel')
points = slicer.util.arrayFromModelPoints(c)
radii = slicer.util.arrayFromModelPointData(c, 'Radius')
for i, radius in enumerate(radii):
  print("Point {0}: position={1}, radius={2}".format(i, points[i], radius))
```

Get centerline points and lines as VTK object:

```python
centerlineModel = getNode('CenterlineComputationModel')
centerlinePoly = centerlineModel.GetPolyData()

# Get first point position:
print(centerlinePoly.GetPoints().GetPoint(0))

# Get point IDs of the first line segment
pointIds = vtk.vtkIdList()
centerlinePoly.GetLines().GetCell(0, pointIds)
```

# For developers

## Compilation

```
SLICER_BUILD_DIR=/path/to/Slicer-SuperBuild
```

```
git clone git://github.com/vmtk/SlicerVMTK.git
mkdir SlicerVMTK-build/ && cd $_

EXTENSION_BUILD_DIR=`pwd`

cmake -DSlicer_DIR:PATH=$SLICER_BUILD_DIR/Slicer-build ../SlicerVMTK
make -j5
make package
```

## Start Slicer and detect the VMTK extension

```
$SLICER_BUILD_DIR/Slicer \
  --launcher-additional-settings \
  $EXTENSION_BUILD_DIR\inner-build\AdditionalLauncherSettings.ini \
  --additional-module-paths \
  $EXTENSION_BUILD_DIR/inner-build/lib/Slicer-4.3/qt-loadable-modules \
  $EXTENSION_BUILD_DIR/inner-build/lib/Slicer-4.3/qt-scripted-modules
```

