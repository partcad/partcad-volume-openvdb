#
# PartCAD, 2026
#
# Licensed under Apache License, Version 2.0.
#
"""An OpenVDB volume, as the solids PartCAD's 'voxels' part type makes of a grid.

OpenVDB is how film, simulation and 3D printing software keeps a volume: a
sparse grid of voxels -- the signed distance to a surface (a level set: what
Houdini, Blender's remesher and many slicers write), a density (a fog volume:
smoke, a CT scan, a simulation's field), occupancy or labels. PartCAD's
'voxels' type reads NumPy, NRRD and NIfTI grids; this reads a '.vdb' by
OpenVDB itself and hands the grid to the same code, a copy of PartCAD's own
'part_voxels' beside this module (see 'sync-partcad.sh'): the filled voxels,
taken into boxes and fused, a solid per label.

The bindings are in an OpenVDB environment of their own (/opt/openvdb in the
image), so the grid is read by 'vdb_dense.py' run there, and handed over as a
file. Parameters, beside the 'voxels' type's own ('size', 'up', 'origin',
'maxBoxes'):

  * 'grid' - which of the file's grids: by default its first level set, else
    its first fog volume, else its first grid of numbers;
  * 'threshold' - the density a fog volume, or any grid of numbers that is not
    a level set, is filled at (0.5); for a grid of integers, that they are
    densities rather than labels;
  * 'unit' - what the grid's world unit is (metres, unless the part says):
    a voxel is its transform's size in it, unless 'size' says otherwise;
  * 'maxVoxels' - the most cells the grid is read into (256 cubed): a larger
    one is coarsened by a whole factor, each cell the share of its voxels
    filled.

With 'origin: file' the solid is where the grid's transform puts it, in
'unit'; a transform that turns the grid is not applied, only its scale and
offset, and a warning says so.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# The OpenVDB environment's interpreter, as the image has it (see image/Dockerfile).
DEFAULT_PYTHON = "/opt/openvdb/bin/python"
CONVERTER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vdb_dense.py")

UNITS = {"m": 1000.0, "cm": 10.0, "mm": 1.0, "um": 0.001, "in": 25.4, "ft": 304.8}


def python():
    found = os.environ.get("PC_OPENVDB_PYTHON") or (DEFAULT_PYTHON if os.path.exists(DEFAULT_PYTHON) else None)
    if not found:
        raise ValueError(
            "there is no OpenVDB here: this part type runs in the image its package names, which carries it "
            "(set PC_OPENVDB_PYTHON to a Python with its bindings to run it elsewhere)"
        )
    return found


def unit_scale(unit):
    key = str(unit or "m").strip().lower()
    if key not in UNITS:
        raise ValueError("'unit' is one of %s, not '%s'" % (", ".join(UNITS), unit))
    return UNITS[key]


def dense(path, parameters):
    """What 'vdb_dense.py' makes of the file: the arrays and values it writes, as a dict."""
    import numpy

    options = {
        key: parameters.get(key) for key in ("grid", "threshold", "maxVoxels") if parameters.get(key) not in (None, "")
    }
    # The environment's own Python, with nothing of this one's on its path:
    # its numpy is the one the bindings were built against.
    env = {key: value for key, value in os.environ.items() if not key.startswith("PYTHON")}
    env["PYTHONNOUSERSITE"] = "1"
    scratch = tempfile.mkdtemp(prefix="pc-openvdb-")
    try:
        out = os.path.join(scratch, "grid.npz")
        try:
            done = subprocess.run(
                [python(), "-I", CONVERTER, path, out, json.dumps(options)],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except OSError as e:
            raise ValueError("OpenVDB's Python could not be run: %s" % e)
        if done.returncode != 0:
            said = [line for line in (done.stderr or "").strip().splitlines() if line.strip()]
            raise ValueError(said[-1] if said else "OpenVDB's Python failed with exit %d" % done.returncode)
        with numpy.load(out, allow_pickle=False) as found:
            return {key: found[key] for key in found.files}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def read(path, parameters):
    """The 'part_voxels.Grid' of the part's '.vdb'."""
    import numpy
    import part_voxels

    found = dense(path, parameters)
    scale = unit_scale(parameters.get("unit"))
    voxel = numpy.asarray(found["voxel"], dtype=float)
    if not (numpy.isfinite(voxel).all() and (voxel > 0.0).all()):
        raise ValueError("its transform gives its voxels no size")
    labels = str(found["kind"]) == "labels"
    grid = part_voxels.grid_of(
        found["values"],
        None if labels else 0.5,
        os.path.basename(path),
        tuple(float(v) * scale for v in voxel),
        what=str(found["what"]),
    )
    # In voxels, as every grid's corner is.
    grid.corner = tuple(float(c) / float(v) for c, v in zip(found["corner"], voxel))
    if str(found.get("warning", "")):
        print("vdb: %s: %s" % (os.path.basename(path), found["warning"]), file=sys.stderr)
    return grid


def run(request):
    """The part 'request' asks for, as the 'output' PartCAD's 'wrapper_part_type' reads."""
    import part_voxels

    parameters = dict(request.get("parameters") or {})
    # 'part_voxels.run' reads its file by the extension; here OpenVDB reads
    # it, and the grid is handed over instead. Put back afterwards.
    builtin = part_voxels.read
    part_voxels.read = lambda path, given: read(path, parameters)
    try:
        return part_voxels.run(request)
    finally:
        part_voxels.read = builtin
