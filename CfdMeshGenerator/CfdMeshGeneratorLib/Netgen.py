"""Netgen, in this process.

Netgen arrives as the netgen-mesher package, installed into Slicer's own Python the first time it
is asked for. Unlike pytetwild it ships a wheel for every Python Slicer runs on - Windows, Linux,
and a universal one for the Mac - so there is no machine on which it has to be run in an
interpreter of its own, and none of the machinery FTetWild keeps for that is needed here.

Everything the pipeline asks of Netgen goes through tetrahedralize(), which is written against
numpy and netgen alone: it is handed arrays and hands arrays back, so that the conversion to and
from VTK stays in the pipeline (see MeshingPipeline.runNetgen).
"""

import importlib
import logging
import sys

# What to install when Netgen is asked for. Pinned rather than floating: the mesh a version gives
# is the mesh it gives, and a solver run is worth being able to repeat.
REQUIREMENT = "netgen-mesher==6.2.2606"

# What Netgen makes of a size, on a mesh built from triangles rather than from a geometry.
#
# Meshing a geometry, Netgen installs maxh as a global cap on its size field. GenerateVolumeMesh
# on a hand-built surface never does: the cap stays at its initial 1e10, Python has no way to
# set it, and the one reader of maxh left is the step that seeds the inside with points
# (BlockFillLocalH), which lowers the field only where it is already above 1.5 x maxh. The
# field itself starts at the longest edge of each surface triangle and grows from there, so
# whatever maxh is passed, the inside comes out between maxh and 1.5 maxh, and the elements
# about a quarter larger than the field again. Handing over maxh / 1.5 puts that threshold at
# the size asked for, so every interior point whose field exceeds it is pulled down. Measured on
# tubes of three sizes at a target of 0.4: 0.52-0.57 mean edge as passed, 0.38-0.40 divided by
# 1.5, beside TetGen's 0.37 and fTetWild's 0.39 for the same target.
MAXH_SLACK = 1.5
# A size set at a point (RestrictLocalH) goes through the size field's own tolerance instead:
# LocalH::SetH leaves a cell alone when it is within 1.2 x of what is asked, and the elements
# come out about that much above the field. Divided by 1.5 as well, the per-point sizes came
# out finer than the other meshers (0.34); by 1.2, level with them.
LOCAL_H_SLACK = 1.2


class TetrahedralizationError(RuntimeError):
    """Netgen ran and could not mesh the surface it was given. Everything else that can go
    wrong - no netgen to import - is a plain RuntimeError, because it says nothing about the
    surface."""


def importNetgen():
    """The netgen.meshing module. Raises ImportError if it is not installed.

    A failed import can leave the half-built package behind, and a later import would then hand
    back what it got to instead of trying again, so what it left is taken out before the error
    is passed on.
    """
    try:
        return importlib.import_module("netgen.meshing")
    except ImportError:
        for name in [name for name in sys.modules
                     if name.split(".")[0] in ("netgen", "pyngcore")]:
            del sys.modules[name]
        raise


def isAvailable():
    """Whether Netgen can be run in this process. It is imported rather than looked for: a
    package that is installed but cannot be imported is not one to offer."""
    try:
        importNetgen()
    except ImportError:
        return False
    return True


def tetrahedralize(vertices, faces, faceIds, maxh, grading, optimizationSteps,
                   sizingPoints=None, sizingLengths=None):
    """Fill the surface with tetrahedra, keeping its triangles as they are.

    Netgen is handed the triangles as the boundary of one domain and meshes the inside of it. It
    neither splits nor moves them: what it adds is points inside, and tetrahedra on both. So the
    points of the surface come back first, unmoved and in their order, and the boundary comes
    back as the very triangles that went in, over the same point ids.

    :param vertices: the points of the surface, as an (n, 3) float array.
    :param faces: the triangles of the surface, as an (m, 3) index array, wound so that they face
      outwards. A surface that faces inwards as a whole is turned round; one that faces both
      ways is not one Netgen can fill.
    :param faceIds: the id of the face of the surface each triangle stands on, as an (m,) int
      array. The boundary comes back labelled with them.
    :param maxh: the edge length the tetrahedra are to come out at. What Netgen is handed is
      smaller than this by MAXH_SLACK, which is what it takes for them to come out at it; see
      the note on that constant.
    :param grading: how fast the size may change from one element to the next, 0 to 1.
    :param optimizationSteps: passes Netgen spends improving the mesh once it has filled it.
    :param sizingPoints: points at which a target edge length is known, as a (k, 3) array, or
      None for one size throughout. The size field Netgen reads is lowered to sizingLengths at
      each of them; it is never raised, so a point asking for a coarser mesh than the surface
      around it has no effect.
    :param sizingLengths: the edge length the tetrahedra are to come out at, at each of those
      points, as a (k,) array. Scaled by LOCAL_H_SLACK on the way in, as maxh is.
    :return: (points, tetrahedra, boundaryTriangles, boundaryFaceIds) as arrays. The tetrahedra
      are wound the way VTK winds them.
    :raises TetrahedralizationError: if Netgen could not fill the surface.
    :raises RuntimeError: if Netgen is not installed.
    """
    import numpy as np

    try:
        meshing = importNetgen()
    except ImportError as error:
        raise RuntimeError("Netgen is not installed (%s)" % REQUIREMENT) from error

    vertices = np.ascontiguousarray(vertices, dtype=np.float64).reshape(-1, 3)
    faces = np.ascontiguousarray(faces, dtype=np.int32).reshape(-1, 3)
    faceIds = np.asarray(faceIds, dtype=np.int32).ravel()
    if len(faceIds) != len(faces):
        raise ValueError("%d triangles were given %d face ids" % (len(faces), len(faceIds)))

    # Netgen meshes the side of the surface its triangles face away from. Handed a surface that
    # faces inwards it fills nothing and says so on stderr, which is a poor answer to a question
    # that can be settled here from the sign of the volume the surface encloses.
    corners = vertices[faces]
    enclosed = np.einsum("ij,ij->i", corners[:, 0],
                         np.cross(corners[:, 1], corners[:, 2])).sum() / 6.0
    if enclosed < 0.0:
        logging.debug("The surface faces inwards; its triangles are turned round for Netgen")
        faces = np.ascontiguousarray(faces[:, [0, 2, 1]])

    # Netgen reports every step of its work on stdout; the pipeline reports the steps of its own.
    meshing.SetMessageImportance(0)

    mesh = meshing.Mesh(dim=3)
    mesh.AddPoints(vertices)
    # One face descriptor per face of the input, so that the boundary can be read back labelled:
    # each surface element of the result names its descriptor, and the descriptor is numbered
    # from 1 in the order they are added. Netgen fills domain 1, which is what domin says the
    # triangles bound; 0 outside is nothing.
    faceIdOfDescriptor = [0]
    for faceId in np.unique(faceIds):
        number = len(faceIdOfDescriptor)
        descriptor = mesh.Add(meshing.FaceDescriptor(surfnr=number, domin=1, domout=0, bc=number))
        if descriptor != number:
            raise RuntimeError("Netgen numbered a face descriptor %d where %d was expected"
                               % (descriptor, number))
        faceIdOfDescriptor.append(int(faceId))
        mesh.AddElements(dim=2, index=descriptor,
                         data=np.ascontiguousarray(faces[faceIds == faceId]), base=0)
    faceIdOfDescriptor = np.array(faceIdOfDescriptor, dtype=np.int32)

    # The size field is built before anything lowers it: RestrictLocalH builds one itself where
    # there is none, at a grading of its own choosing rather than the one asked for. Built from
    # the surface, the field already holds the size of every triangle, and the volume mesher
    # keeps a field it finds rather than building another.
    mesh.CalcLocalH(float(grading), 1)
    if sizingPoints is not None and sizingLengths is not None:
        sizingPoints = np.asarray(sizingPoints, dtype=np.float64).reshape(-1, 3)
        sizingLengths = np.asarray(sizingLengths, dtype=np.float64).ravel()
        for point, length in zip(sizingPoints.tolist(), sizingLengths.tolist()):
            mesh.RestrictLocalH((point[0], point[1], point[2]), length / LOCAL_H_SLACK)

    # A surface Netgen cannot fill is not an exception: the run gives up, writes why to stderr,
    # and leaves the mesh with no volume elements in it. An exception out of here is something
    # else - an argument it does not take, say - and is passed on as a failure all the same,
    # since the surface was not filled.
    try:
        mesh.GenerateVolumeMesh(maxh=float(maxh) / MAXH_SLACK, grading=float(grading),
                                optsteps3d=int(optimizationSteps))
    except Exception as error:
        raise TetrahedralizationError(str(error)) from error

    # Copied out at once: what the accessors hand back are views of memory the mesh owns.
    points = np.array(mesh.Coordinates(), dtype=np.float64)
    elements = mesh.Elements3D().NumPy()
    if len(elements) == 0:
        raise TetrahedralizationError(
            "Netgen could not fill the surface with tetrahedra; it will have said why above")
    if (elements["np"] != 4).any():
        raise TetrahedralizationError("Netgen answered with elements that are not tetrahedra")
    # Netgen numbers its points from 1.
    tetrahedra = elements["nodes"][:, :4].astype(np.int64) - 1
    boundary = mesh.Elements2D().NumPy()
    boundaryTriangles = boundary["nodes"][:, :3].astype(np.int64) - 1
    boundaryFaceIds = faceIdOfDescriptor[boundary["index"]]
    for name, indices in (("tetrahedra", tetrahedra), ("boundary triangles", boundaryTriangles)):
        if len(indices) and (indices.min() < 0 or indices.max() >= len(points)):
            raise TetrahedralizationError(
                "Netgen's %s refer to points it did not hand back" % name)

    # Netgen numbers the corners of a tetrahedron the other way round from VTK. Each is turned
    # by its own volume rather than all of them on trust, which costs nothing and asks nothing.
    corners = points[tetrahedra]
    inverted = np.einsum(
        "ij,ij->i",
        np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]),
        corners[:, 3] - corners[:, 0]) < 0.0
    tetrahedra[inverted] = tetrahedra[inverted][:, [0, 2, 1, 3]]

    return points, tetrahedra, boundaryTriangles, boundaryFaceIds
