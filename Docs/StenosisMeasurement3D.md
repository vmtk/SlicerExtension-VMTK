# Three dimensional stenosis measurement

This [Slicer](https://www.slicer.org/) module calculates arterial stenosis degree in 3D. It requires the custom [Shape](https://github.com/chir-set/ExtraMarkups/) markups as a tube.

**Usage**

Segment a diseased arterial lumen using the segment editor. Draw a best fit arterial wall around the lumen using the Tube (Shape) markups. This is not a computed step, but totally observer dependent. It is more accurately done in slice views in these ways:

 - proceed with many manual reformatting so as to be perpendicular to the arterial axis prior to placing a pair of points in one slice view (activate 'Slice intersections', use 'Ctrl+Alt+LeftClickDrag' and/or 'Interaction'),
 
 - use a temporary open curve markups node: place each point of the curve at best estimates of the artery's anatomical axis; use 'Cross-section analysis' module to browse a resliced view along the curve; place pairs of control points of the Shape::Tube node at significant intervals during browsing; the open curve node can then be hidden or removed;
 
 - place pairs of control points of the Shape::Tube in a 'Volume rendering' view along the artery, click on successive control points and reslice to the active control point each time in the Markups module widget; this will reslice the selected view such that both elements of a pair of control points of the Shape::Tube node can be repositioned accurately to the best estimate of the artery's walls.

The lumen should be manually cut to the zone of study. Otherwise, the result may be meaningless, if surrounding far away parts of the segment are included in the calculation. There should remain the drawn Tube surrounding a lumen that extends a little beyond the Tube.

Place 2 points of a fidicial node to further limit the extent of the study.

**Options**

Show models of the surfaces being cut down and measured.


![Usage](StenosisMeasurement3D_0.png)

**Notes**

 - A small part of the drawn tube is excluded at each end during processing; the boundary points do not extend in the excluded parts.
 - The usefulness of evaluating arterial stenosis by volume in clinical practice is yet to be determined.

**Disclaimer**

Use at your own risks.



