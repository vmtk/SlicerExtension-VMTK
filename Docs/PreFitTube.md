# Pre-fit tube

This module pre-fits a Shape::Tube markups node along an input markups curve that represents the axis of a non-aneurysmal artery. The control points of the tube must be further repositioned to represent the best *estimate* of the arterial wall.

![Example](PreFitTube_0.png)

### Usage

Select a markups curve node, a scalar volume of a CT angiogram and a target dimension profile. Select an output Shape::Tube node, and optionally a segmentation node to keep the segment mask. After applying, the resulting Shape::Tube node may be post-processed to position the control points on the arterial wall.

### Notes
 - This extension is a requirement: [ExtraMarkups](https://github.com/chir-set/SlicerExtraMarkups).
 - Use cropped volumes to save time.
 - For tiny targets, resampling the volume to increase the resolution may help.
 - The input curve should represent the axis of the artery.
 - For diseased arteries, the more the curve passes through calcifications and soft lesions, the better for the segment mask.
 - An output segmentation node can be specified to view the segment mask.

