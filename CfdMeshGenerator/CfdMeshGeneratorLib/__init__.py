"""What the CFD Mesh Generator module runs outside the application.

MeshingPipeline is the pipeline itself, FTetWild is the one mesher that is not built into the
extension, and MeshingWorker is the script that runs the pipeline in a process of its own. None
of them needs the application, which is what lets them be run in a plain PythonSlicer.
"""
