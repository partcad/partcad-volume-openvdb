#
# PartCAD, 2026
#
# Licensed under Apache License, Version 2.0.
#
"""One grid of an OpenVDB file, as a dense grid of what it fills: run by the OpenVDB environment's Python.

    python vdb_dense.py <file.vdb> <out.npz> '<options as JSON>'

OpenVDB's Python bindings are built for conda-forge's Python and its numpy, so
this runs there (/opt/openvdb in the image) rather than in the Python that
builds the part, and hands its answer over as a file: an '.npz' of

  * 'values' - what each cell holds: the fraction of it that is filled (0 to
    1, float32), or, for an integer grid read as labels, the label;
  * 'kind' - 'fraction' or 'labels';
  * 'voxel' - a cell's size along X, Y and Z, in the grid's world units;
  * 'corner' - where the cell [0, 0, 0]'s low corner is, in world units;
  * 'what' - a line for the log.

What a grid fills is what its class says: a level set is filled inside its
surface (where its distance is below nought), anything else of numbers at and
above 'threshold' (0.5 unless the part says), a grid of booleans where true,
and a grid of integers is read as the labels of a segmentation, unless a
'threshold' says they are densities.

A VDB is sparse, and its bounds can be thousands of voxels a side, so it is
read a tile at a time, and when its active voxels' bounding box holds more
than 'maxVoxels' (16.8 million: 256 cubed) it is coarsened by a whole factor:
each cell is then a block of voxels, and its value the share of them filled.
Labels coarsened that way are no longer labels, and are read as occupancy.

Plain numpy and the bindings, for any Python they are built for; both the
'openvdb' (OpenVDB 12 on) and the 'pyopenvdb' module names, and both the
spellings of a grid's class those two have.
"""

import json
import math
import sys

DEFAULT_MAX_VOXELS = 256**3
# A tile's edge, in voxels, at most: 256 cubed float32 is 64 MB.
TILE = 256
# What a grid is read as, by its value type.
SCALARS = {"float": "float32", "double": "float64", "half": "float32"}
INTEGERS = {"int32": "int32", "int64": "int64", "uint32": "uint32", "int8": "int8", "uint8": "uint8"}
# Which grid is read when the part names none: the first of these classes, by name, else the first scalar grid.
PREFERRED = ("level set", "fog volume")


def bindings():
    try:
        import openvdb
    except ImportError:
        try:
            import pyopenvdb as openvdb
        except ImportError:
            raise ValueError("this Python has no OpenVDB bindings (neither 'openvdb' nor 'pyopenvdb')")
    return openvdb


def grid_class(grid):
    """'level set', 'fog volume', 'staggered' or 'unknown', however the bindings spell it."""
    found = str(getattr(grid, "gridClass", "") or "").strip().lower()
    found = found.rsplit(".", 1)[-1].replace("_", " ").replace("grid ", "")
    return found or "unknown"


def value_type(grid):
    return str(getattr(grid, "valueTypeName", "") or "").strip().lower()


def coord(value):
    try:
        return tuple(int(v) for v in value)
    except TypeError:
        return (int(value.x()), int(value.y()), int(value.z()))


def choose(grids, wanted):
    """The grid the part reads out of the file's: the one named 'wanted', or the best one there is."""
    names = [str(grid.name) for grid in grids]
    if not grids:
        raise ValueError("it holds no grid")
    if wanted:
        if str(wanted) not in names:
            raise ValueError("it holds no grid named '%s'; it holds %s" % (wanted, ", ".join(repr(n) for n in names)))
        return str(wanted)
    for wanted_class in PREFERRED:
        for grid in grids:
            if grid_class(grid) == wanted_class:
                return str(grid.name)
    for grid in grids:
        if value_type(grid) in SCALARS or value_type(grid) in INTEGERS or value_type(grid) == "bool":
            return str(grid.name)
    return names[0]


def placement(grid, low):
    """'(voxel, corner, said)': a voxel's size and the low corner of voxel 'low', in world units, and a warning or None."""
    transform = grid.transform
    origin = [float(v) for v in transform.indexToWorld(tuple(float(v) for v in low))]
    steps = [
        [float(v) for v in transform.indexToWorld(tuple(float(low[i] + (i == axis)) for i in range(3)))]
        for axis in range(3)
    ]
    axes = [[steps[axis][i] - origin[i] for i in range(3)] for axis in range(3)]
    voxel = [math.sqrt(sum(c * c for c in axes[axis])) for axis in range(3)]
    said = None
    if any(abs(axes[axis][i]) > 1e-9 * max(voxel) for axis in range(3) for i in range(3) if i != axis):
        said = "its transform turns the grid, and the solid is not turned: it is axis-aligned, at its voxels' size"
    # A voxel is centred on its index: the cell starts half a voxel before it.
    corner = [origin[i] - 0.5 * voxel[i] for i in range(3)]
    return voxel, corner, said


def filled(values, kind, threshold):
    """Where a tile of 'values' is filled, by what the grid is."""
    import numpy

    if kind == "level set":
        return values < 0.0
    if values.dtype == bool:
        return values
    if numpy.issubdtype(values.dtype, numpy.integer) and threshold is None:
        return values != 0
    return values >= (0.5 if threshold is None else float(threshold))


def convert(path, options, openvdb=None):
    """What the module docstring says is written, as a dict of arrays and values."""
    import numpy

    openvdb = openvdb or bindings()
    try:
        grids = openvdb.readGridMetadata(path)
    except Exception as e:
        raise ValueError("OpenVDB cannot read it: %s" % e)
    name = choose(list(grids), options.get("grid"))
    try:
        grid = openvdb.read(path, name)
    except Exception as e:
        raise ValueError("OpenVDB cannot read its grid '%s': %s" % (name, e))
    kind = grid_class(grid)
    typed = value_type(grid)
    threshold = options.get("threshold")
    threshold = None if threshold in (None, "") else float(threshold)
    if typed in SCALARS:
        dtype = SCALARS[typed]
    elif typed in INTEGERS:
        dtype = INTEGERS[typed]
    elif typed == "bool":
        dtype = "bool"
    else:
        raise ValueError(
            "its grid '%s' holds %s values, and only a grid of numbers bounds something: name one in 'grid'"
            % (name, typed or "unknown")
        )
    labels = dtype in INTEGERS.values() and threshold is None and kind != "level set"

    low, high = (coord(c) for c in grid.evalActiveVoxelBoundingBox())
    dims = [high[i] - low[i] + 1 for i in range(3)]
    if min(dims) < 1:
        raise ValueError("its grid '%s' has no active voxel" % name)
    limit = int(float(options.get("maxVoxels") or DEFAULT_MAX_VOXELS))
    total = dims[0] * dims[1] * dims[2]
    factor = 1
    while total / float(factor**3) > limit:
        factor += 1
    out = [int(math.ceil(d / float(factor))) for d in dims]
    if labels and factor > 1:
        labels = False
    values = numpy.zeros(out, dtype=numpy.int32 if labels else numpy.float32)
    # A tile's edge, a whole number of blocks.
    edge = max(factor, (TILE // factor) * factor)
    for x in range(0, dims[0], edge):
        for y in range(0, dims[1], edge):
            for z in range(0, dims[2], edge):
                shape = (min(edge, dims[0] - x), min(edge, dims[1] - y), min(edge, dims[2] - z))
                tile = numpy.zeros(shape, dtype=dtype)
                grid.copyToArray(tile, (low[0] + x, low[1] + y, low[2] + z))
                if labels:
                    values[x : x + shape[0], y : y + shape[1], z : z + shape[2]] = tile
                    continue
                inside = filled(tile, kind, threshold).astype(numpy.float32)
                if factor == 1:
                    values[x : x + shape[0], y : y + shape[1], z : z + shape[2]] = inside
                    continue
                # Each block's share filled: summed over the block and divided
                # by how many voxels it has, which is fewer at the far edges.
                blocks = [int(math.ceil(s / float(factor))) for s in shape]
                padded = [b * factor for b in blocks]
                sums = numpy.zeros(padded, dtype=numpy.float32)
                counts = numpy.zeros(padded, dtype=numpy.float32)
                sums[: shape[0], : shape[1], : shape[2]] = inside
                counts[: shape[0], : shape[1], : shape[2]] = 1.0
                folded = (blocks[0], factor, blocks[1], factor, blocks[2], factor)
                share = sums.reshape(folded).sum(axis=(1, 3, 5)) / counts.reshape(folded).sum(axis=(1, 3, 5))
                bx, by, bz = x // factor, y // factor, z // factor
                values[bx : bx + blocks[0], by : by + blocks[1], bz : bz + blocks[2]] = share
    voxel, corner, warning = placement(grid, low)
    what = "OpenVDB grid '%s' (%s, %s), %d x %d x %d" % (name, kind, typed, dims[0], dims[1], dims[2])
    if factor > 1:
        what += " coarsened %d times to %d x %d x %d" % (factor, out[0], out[1], out[2])
    return {
        "values": values,
        "kind": "labels" if labels else "fraction",
        "voxel": numpy.array(voxel) * factor,
        "corner": numpy.array(corner),
        "what": what,
        "warning": warning or "",
    }


def main(arguments):
    import numpy

    path, out, options = arguments[0], arguments[1], json.loads(arguments[2]) if len(arguments) > 2 else {}
    try:
        found = convert(path, options)
    except ValueError as e:
        sys.stderr.write("%s\n" % e)
        return 2
    numpy.savez(out, **found)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
