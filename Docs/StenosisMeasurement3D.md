# Three dimensional stenosis measurement

This [Slicer](https://www.slicer.org/) module calculates arterial stenosis degree in 3D. It requires the custom [Shape](https://github.com/chir-set/ExtraMarkups/) markups as a tube.

**Usage**

Segment an diseased arterial lumen using the segment editor. Draw a best fit arterial wall around the lumen using the Tube (Shape) markups. This is not a computed step, but totally observer dependent. It is more accurately done in slice views, with many reformating so as to be perpendicular to the arterial axis prior to placing a pair of points in one slice view.

The lumen should be manually cut to the zone of study. Otherwise, the result may be meaningless, if surrounding far away parts of the segment are included in the calculation. There should remain the drawn Tube surrounding a lumen that extends a little beyond the Tube.

Place 2 points of a fidicial node to further limit the extent of the study.

**Options**

Show models of the surfaces being cut down and measured.


![Usage](StenosisMeasurement3D_0.png)

**Notes**

 - If the first boundary point is at the begining or at the end of the wall's axis, the calculated volume is incorrect. This is yet unexplained. Draw a wall slightly beyond the zone of interest.
 - 
 - The usefulness of evaluating arterial stenosis by volume in clinical practice is yet to be determined.

**Disclaimer**

Use at your own risks.



