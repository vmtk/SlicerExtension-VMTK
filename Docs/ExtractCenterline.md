# Extract centerline

## Preprocessing

The module requires a surface mesh as input (specified in either model or segmentation node). The mesh is typically created by segmenting images and therefore very dense, containing very high number of points. Using all the points in the centerline extraction would make the computation time very long (several minutes to tens of minutes). Preprocessing steps built into the module simplify the input mesh by replacing many small mesh elements with larger ones in regions where the curvature of the surface is low. This simplification reduces number of points and thus computation time, without significant changes in the computation result.

Preprocessing is enabled by default and it aims for reducing the number of mesh points to 5k (=5000). For larger, more complex networks, this `Target point count` parameter values can be increased (up to about 100k should be enough for most cases). Simplification is not performed in high-curvature areas, as it could remove significant features from the mesh and/or may introduce mesh errors (such as non-manifold edges). `Aggressiveness` parameter controls how much change in the mesh is acceptable during simplification. If aggressiveness value is low then all features of the mesh are preserved and no mesh errors are introduced but it may prevent the simplification method to reach the desired target point reduction. Any positive value can be used for aggressiveness, but values between 3.5-4.5 work best for typical inputs.

`Subdivide` can be enabled to increase the number of input points. This may make computation more robust for input meshes that has very coarse resolution

If a node is specified in `Output preprocessed surface` then preprocessing result is saved in that node. This is useful for quality checks: to ensure that all important details of the mesh are preserved. Saving preprocessed surface can be used to reduce computation time for repeated centerline extractions: once the preprocessed mesh is computed, choose it as input `Surface` and disable `Preprocess input surface`.

## Network extraction

Network extraction can be used for quick, approximate extraction of a complete centerline network. It is invoked automatically when Endpoints "Auto-detect" button is clicked or a node is selected as "Network model" output.

Computation requires `Surface` input and an optional starting point. If no starting point is defined then closest point to one of the corners of the model is chosen. A centerline segment may appear between the starting point and the centerline network. To avoid this small extra branch, a starting point can be defined manually by placing an `Endpoint` markup point at end of any of the branches.

## Centerline tree extraction

Accurate, Voronoi model based centerline tree extraction can be performed by specifying an input `Surface` and `Endpoints`.

`Endpoints` are a list of branch endpoints that will be connected by centerlines. An endpoint can be inlet or outlet type by making the corresponding markup point "unselected" or "selected", respectively. Typically one inlet point is enough, but if the network consists of several independent trees then an inlet point should be defined in each tree. If no inlet point is designated then the first endpoint will be used as inlet. If an endpoint is not reachable then it may be connected to other points via a straight line. Remove or reposition these endpoints to create a complete, valid centerline network.

Extracted centerlines are saved into a model node if a model node is selected as `Centerline model`.

If a markups curve node is selected as `Centerline curve` then branches are split into separate curve nodes. Geometrical properties (length, average radius, curvature, torsion, tortuosity) are computed if a table node is chosen as `Quantification results`. Tortuosity is computed as the ratio between the centerline length and the distance of the line endpoints. Important: make sure that all endpoints are reachable (none of them are connected with a straight line to some other points in the tree), as unreachable endpoints may make computation run endlessly.

`Voronoi diagram` is a surface similar to medial surface, which is used for searching path between branch endpoints. This model can be saved for quality checks and for getting a surface where branch endpoints can be robustly placed on.

## Mesh error check

Mesh errors, such as non-manifold edges may cause errors during centerline computation. Non-manifold edges can be marked on the image by choosing a markups node as `Mesh error check results`.
