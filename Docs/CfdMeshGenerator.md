# CFD Mesh Generator

This module fills a vessel surface with tetrahedra, ready for a computational fluid dynamics solver. The input is a surface model - typically one that has come out of [Clip vessel](ClipVessel.md), with its ends cut normal to the centerline and its faces labeled. The output is a volumetric mesh, and optionally the remeshed surface the mesh was built on. This is the pipeline of VMTK's `vmtkmeshgenerator` script, with the same parameters.

![CFD Mesh Generator](CfdMeshGenerator.jpg)
**A volume mesh cut open with the clip button, to show the elements inside**

## What the module does
The surface goes through four steps, which the sections of the panel follow:

- *Cap surface* closes every open boundary with a cap of its own, each under its own id, so that a boundary condition can be assigned to it. A surface that is already closed does not need this; a surface left open cannot be filled with tetrahedra at all.
- *Remesh surface* retriangulates the surface into near equilateral cells of the target edge length. Turn it off only for a surface that is already meshed the way the solver wants it, because the size of the tetrahedra follows the size of the triangles they sit against. *Remesh wall* off remeshes the caps alone and leaves the wall exactly as it came in.
- *Add boundary layer* lines the wall on the inside with layers of prisms.
- The rest of the volume is filled with tetrahedra by the *Mesher* chosen, TetGen or fTetWild. *Tetrahedralize* splits the prisms of the boundary layer too, for a solver that takes nothing else.

## Mesher
Two meshers fill the surface, and they answer differently shaped questions.

*TetGen* is handed the surface as a boundary it may not touch, and hands back the same triangles with tetrahedra behind them. The mesh meets the surface exactly, which is what a mesh built on a carefully prepared surface wants. A surface it cannot fill it fails on.

*fTetWild* is handed the surface as a shape to stay within *Surface tolerance* of, and meshes what it makes of it. The boundary comes back retriangulated and moved by up to that tolerance, and each face keeps its id by being matched to the face of the input nearest it. In exchange it fills surfaces TetGen refuses, and it is the one that can size the elements by position: with *Element size mode* set to read an array, only fTetWild grades the volume to match, TetGen sizing it by one number throughout.

fTetWild is not built into the extension. It arrives as the `pytetwild` package, which the module offers to download from PyPI the first time fTetWild is chosen; this needs an internet connection and is done once. There is no package for Intel Macs. TetGen is not always there either: its licence makes building it a decision, and where it was not built its entry cannot be chosen.

The other three fTetWild settings trade time for quality. *Stop energy* is how good the worst element has to be before it stops improving the mesh, 3 being a regular tetrahedron; *Optimization passes* caps how long it spends trying; *Coarsen* asks for the fewest elements the tolerance allows rather than the size asked for.

With a boundary layer, fTetWild takes a different route to the same result: the layer is swept inwards to say how much room to leave, the space inside is filled, and the layer that ends up in the mesh is grown back outwards from the boundary of those tetrahedra, so that its inner face is made of the very cells they are bounded by. The wall then sits where the outside of the layer lands, within about the thickness of the layer of where the surface was.

## Element size
*Target edge length* is the one number that says how fine the whole mesh comes out. The surface triangles aim for it, the thickness of the boundary layer is a fraction of it (*Thickness factor*), and the tetrahedra follow the triangles they sit against, scaled by *Volume element scale factor* - below 1 the volume mesh is finer than the surface it fills.

Element count grows with the cube of the size, so halving the edge length is about eight times the mesh: on a clipped aorta, 3 mm gives some 39 thousand tetrahedra, 1.5 mm some 106 thousand, and 1 mm some 411 thousand. Start coarse.

Set *Element size mode* to take the size from an array instead, and the target edge length is read per point from an array carried on the input surface, so the mesh can be made finer where the vessel is narrow. *Edge length factor* then scales the whole array at once, without recomputing it. The surface follows such an array whichever mesher is used; the volume behind it follows the array only under fTetWild.

Asking the remesher for triangles far from the size of the ones the surface arrived with can leave it with holes, which no mesher can fill. fTetWild says so and stops rather than handing back a mesh of the part of the surface that was closed.

## Face ids
Every cell of the output carries an integer in the cell array named by *Face ids array* (`ModelFaceID` by default, the name SimVascular and its meshing tools read the faces of a model by): one id for the wall, one for each cap, and 0 for the volume elements. This is what a solver reads the boundary conditions off - a different condition per inlet, outlet and wall.

If the input surface already carries an array of that name, its ids are kept and any new caps are numbered above them, so a surface labeled by Clip Vessel arrives in the solver with the numbering it left Clip Vessel with. Under any other name the faces of the input are renumbered from scratch. The array is also what holds the faces apart while the surface is remeshed: the boundary between wall and cap stays where it is instead of being smoothed away.

## Boundary label arrays
*Boundary labels array* and *Point order array* name two point data arrays that say which vessel end each boundary point belongs to (`BoundaryLabels` and `BoundaryPointOrder` by default, the names the VMTK filters use and the ones [Clip vessel](ClipVessel.md) writes). A boundary's label is the face id of the cap that closes it: the two arrays and the face id array are one numbering, so the end labelled 3 in the point data is the face numbered 3 in the cell data, here and in Clip Vessel. Where the input surface carries them, each cap therefore comes out under the id its own end is known by - the same id every run, and the id Clip Vessel gave it. A point on no boundary carries -1, which is no face id at all. Where it does not, the caps are numbered in the order the boundaries happen to be found in, which can differ from one run to the next. The arrays are carried through the whole pipeline and are still on the output, so a mesh can be re-meshed with its ends identified the same way. Change the names only to match a surface whose arrays are called something else, or to keep out of the way of arrays of that name meaning something else.

## Boundary layer
The prisms along the wall are what resolve the velocity gradient there, and with it the wall shear stress; a mesh of tetrahedra alone needs to be far finer everywhere to say the same thing. *Number of sublayers*, *Sublayer ratio* and *Thickness factor* shape the layer - how many prisms, how their thickness grows away from the wall, and how thick the whole layer is relative to the target edge length.

*Layer on caps* is normally what an inlet or outlet boundary condition wants: turned off, the layer stops at the wall and each cap stays a single flat face with the flow meeting it directly, the caps being made past the layer, on the inner surface. A surface that arrives already capped has its caps taken off first and their ids put back on the ones made in their place, so the setting means the same thing whether or not the ends were closed before.

## Looking at the result
Each node selector has buttons beside it that show or hide the node and turn its edges on and off, so a mesh can be checked without a trip to the Models module. The volume mesh has a third button that cuts it open: the first press puts a box through the middle of the mesh and clips to it, keeping whole elements, and the box can then be dragged and resized in the views. Pressing again turns the clipping off and on.

## Acknowledgement
This module wraps the mesh generation pipeline of the [Vascular Modeling Toolkit](http://www.vmtk.org), developed by Luca Antiga and David Steinman.

The volume mesh is generated by TetGen, by Hang Si, or by fTetWild.

TetGen is licensed under the terms of the MIT license with exceptions, one of which is that distribution of it for any commercial purpose is permissible only by direct arrangement with the copyright owner; for private, research and educational purposes it can be used at no cost and without further arrangements. Anyone putting this module to commercial use should read TetGen's license first.

fTetWild is ["Fast Tetrahedral Meshing in the Wild"](https://github.com/wildmeshing/fTetWild), by Yixin Hu, Teseo Schneider, Bolun Wang, Denis Zorin and Daniele Panozzo (ACM Transactions on Graphics 39(4), SIGGRAPH 2020), under the Mozilla Public License 2.0. It is used through the [pytetwild](https://github.com/pyvista/pytetwild) package of the PyVista project.
