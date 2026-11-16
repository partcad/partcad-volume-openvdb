#
# PartCAD, 2026
#
# Licensed under Apache License, Version 2.0.
#
"""A stand-in for OpenVDB's Python bindings, for the tests that run where they are not.

Only what 'vdb_dense' calls, and only as OpenVDB documents it:
'readAllGridMetadata' (every grid of a file, without its voxels),
'readGridMetadata' (one, by name) and 'read'; a grid's 'name', 'gridClass', 'valueTypeName', 'background',
'evalActiveVoxelBoundingBox' (the inclusive index bounds of the voxels whose
value is not the background), 'copyToArray' (the values of a box of voxels
from a corner, the background where nothing is stored) and 'transform'
('voxelSize', 'indexToWorld').

A "VDB" here is an '.npz' that 'write' makes: each grid a dense array whose
first voxel is at index 'low', and its description as JSON.
"""

import json

import numpy


class GridClass:
    """How OpenVDB 12 on spells a class (an enum); before it, a string ('level set')."""

    def __init__(self, name):
        self.name = name

    def __str__(self):
        return "GridClass." + self.name


class Transform:
    def __init__(self, voxel, translation, turned):
        self.voxel = numpy.asarray(voxel, dtype=float)
        self.translation = numpy.asarray(translation, dtype=float)
        # A quarter turn about Z, for the test of a transform that turns.
        self.turn = numpy.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]) if turned else numpy.eye(3)

    def voxelSize(self):
        return tuple(self.voxel)

    def indexToWorld(self, xyz):
        return tuple(self.turn.dot(numpy.asarray(xyz, dtype=float) * self.voxel) + self.translation)


class Grid:
    def __init__(self, name, described, values=None):
        self.name = name
        if described.get("enum"):
            self.gridClass = GridClass(described["class"].upper().replace(" ", "_"))
        else:
            self.gridClass = described["class"]
        self.valueTypeName = described["type"]
        self.background = described["background"]
        self.low = numpy.asarray(described["low"], dtype=int)
        self.transform = Transform(described["voxel"], described["translation"], described.get("turned"))
        self.values = values

    def _stored(self):
        if self.values is None:
            raise RuntimeError("a grid read by readGridMetadata holds no voxels")
        return self.values

    def evalActiveVoxelBoundingBox(self):
        active = numpy.argwhere(self._stored() != self.background)
        if not len(active):
            return (0, 0, 0), (-1, -1, -1)
        low, high = active.min(axis=0) + self.low, active.max(axis=0) + self.low
        return tuple(int(v) for v in low), tuple(int(v) for v in high)

    def copyToArray(self, array, ijk):
        values = self._stored()
        array[...] = self.background
        start = numpy.asarray(ijk, dtype=int) - self.low
        lo = numpy.maximum(start, 0)
        hi = numpy.minimum(start + numpy.asarray(array.shape), numpy.asarray(values.shape))
        if (hi <= lo).any():
            return
        target = tuple(slice(lo[i] - start[i], hi[i] - start[i]) for i in range(3))
        array[target] = values[tuple(slice(lo[i], hi[i]) for i in range(3))]


def write(path, grids):
    """Write 'grids' -- '(name, values, described)' -- to 'path' as this stand-in reads them."""
    arrays = {}
    for name, values, described in grids:
        arrays["values:" + name] = numpy.asarray(values)
        arrays["described:" + name] = numpy.array(json.dumps(described))
    with open(path, "wb") as f:
        numpy.savez(f, **arrays)


def _load(path):
    try:
        found = numpy.load(path, allow_pickle=False)
    except Exception:
        raise RuntimeError("could not open file %s" % path)
    names = [key.split(":", 1)[1] for key in found.files if key.startswith("described:")]
    return found, names


def readAllGridMetadata(path):
    found, names = _load(path)
    return [Grid(name, json.loads(str(found["described:" + name]))) for name in names]


def readGridMetadata(path, name):
    found, names = _load(path)
    if name not in names:
        raise KeyError("no grid named %s" % name)
    return Grid(name, json.loads(str(found["described:" + name])))


def read(path, name):
    found, names = _load(path)
    if name not in names:
        raise KeyError("no grid named %s" % name)
    return Grid(name, json.loads(str(found["described:" + name])), found["values:" + name])
