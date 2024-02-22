# Centerline disassembly

This module can split a bifurcated centerline model into multiple components. It can create centerline models and centerline curves.

The input centerline must have been created with the 'Extract centerline' module.

![CenterlineDisassembly](CenterlineDisassembly_0.png)

### Usage

Select a centerline model node, the components to extract, the output type and apply. The result can be browsed in the 'Models' and 'Markups' modules' widgets.

The components of a centerline can be:

      - bifurcations,
      - branches, i.e,  centerline parts that exclude the bifurcations,
      - centerlines, i.e, one complete centerline from the first endpoint to every other endpoint.

