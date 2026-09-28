"""What the CFD Mesh Generator module runs outside the application.

MeshingPipeline is the pipeline itself, FTetWild is the one mesher that is not built into the
extension, and MeshingWorker is the script that runs the pipeline outside the application. None of
them needs the application, which is what lets them be run in a plain PythonSlicer.

MeshingRunner is the one that does need it: it is what the module starts a run with, and what tells
it when the run has finished - a process of its own in 3D Slicer, a worker of the page in a web
browser.
"""
