#
# PartCAD, 2026
#
# Licensed under Apache License, Version 2.0.
#
"""The reader with the real OpenVDB: the image's, which is where these run (see .github/workflows/test.yml).

Every volume is written here, by OpenVDB itself, so nothing is downloaded: a
level-set sphere, a fog volume from an array, and the two in one file.
"""

import math
import os
import subprocess
import textwrap

import numpy
import pytest
import vdb_volume

# Written in the OpenVDB environment's Python, through either module name and
# either spelling of the calls its versions have.
PRELUDE = textwrap.dedent("""
    import sys
    import numpy
    try:
        import openvdb as vdb
    except ImportError:
        import pyopenvdb as vdb

    def sphere(radius, voxel):
        make = getattr(vdb, "createLevelSetSphere", None) or vdb.FloatGrid.createLevelSetSphere
        grid = make(radius, center=(0.0, 0.0, 0.0), voxelSize=voxel, halfWidth=3.0)
        grid.name = "surface"
        return grid

    def fog(array, voxel, name="density"):
        grid = vdb.FloatGrid()
        grid.copyFromArray(array.astype(numpy.float32))
        grid.name = name
        grid.transform = vdb.createLinearTransform(voxelSize=voxel)
        try:
            grid.gridClass = vdb.GridClass.FOG_VOLUME
        except AttributeError:
            grid.gridClass = "fog volume"
        return grid
    """)


def make(python, code):
    subprocess.run([python, "-c", PRELUDE + textwrap.dedent(code)], check=True)


def volume(shape):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass()


def request(path, **parameters):
    return {"kind": "part", "name": "/test:volume", "path": str(path), "parameters": parameters, "config": {}}


def test_a_level_set_sphere(real_openvdb, tmp_path):
    path = tmp_path / "sphere.vdb"
    make(real_openvdb, "vdb.write(%r, grids=[sphere(0.5, 0.02)])" % str(path))

    output = vdb_volume.run(request(path, unit="m"))

    assert "exception" not in output, output
    # A sphere 500 mm in radius, in 20 mm voxels.
    assert volume(output["shape"]) == pytest.approx(4.0 / 3.0 * math.pi * 500.0**3, rel=0.05)


def test_a_fog_volume_is_the_cells_at_its_threshold(real_openvdb, tmp_path):
    path = tmp_path / "smoke.vdb"
    make(
        real_openvdb,
        """
        array = numpy.zeros((12, 12, 12))
        array[2:10, 3:9, 4:8] = 0.9
        array[0:2, 0:2, 0:2] = 0.1
        vdb.write(%r, grids=[fog(array, 0.01)])
        """ % str(path),
    )

    output = vdb_volume.run(request(path, unit="m", threshold=0.5))

    assert "exception" not in output, output
    assert volume(output["shape"]) == pytest.approx(8 * 6 * 4 * 1000.0, rel=1e-6)


def test_the_grid_is_chosen_and_named(real_openvdb, tmp_path):
    path = tmp_path / "scene.vdb"
    make(
        real_openvdb,
        """
        array = numpy.zeros((6, 6, 6))
        array[1:5, 1:5, 1:5] = 1.0
        vdb.write(%r, grids=[fog(array, 0.01), sphere(0.05, 0.01)])
        """ % str(path),
    )

    surface = vdb_volume.run(request(path, unit="m"))
    density = vdb_volume.run(request(path, unit="m", grid="density"))

    assert "exception" not in surface and "exception" not in density, (surface, density)
    assert volume(density["shape"]) == pytest.approx(64 * 1000.0, rel=1e-6)
    assert volume(surface["shape"]) == pytest.approx(4.0 / 3.0 * math.pi * 50.0**3, rel=0.25)


def test_what_openvdb_cannot_read_is_said(real_openvdb, tmp_path):
    path = tmp_path / "nothing.vdb"
    path.write_text("not a volume")

    output = vdb_volume.run(request(path))

    assert output["exception"].startswith("nothing.vdb: OpenVDB cannot read it")


def test_the_image_has_the_bindings_numpy_and_the_reader(real_openvdb):
    said = subprocess.run(
        [
            real_openvdb,
            "-I",
            "-c",
            'import numpy, openvdb; print(getattr(openvdb, "LIBRARY_VERSION", openvdb.__name__))',
        ],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout
    assert said.strip()
    assert os.path.isfile(os.path.join(os.environ["PC_VOLUME_OPENVDB_LIBRARY"], "vdb_dense.py"))
    assert numpy.__version__
