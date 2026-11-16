#
# PartCAD, 2026
#
# Licensed under Apache License, Version 2.0.
#
"""What the reader makes of a volume -- with a stand-in for OpenVDB's bindings (fake/openvdb.py).

The point of handing the grid to PartCAD's 'part_voxels' rather than building
the solid here is that the part is the solid PartCAD's 'voxels' type makes: so
the central test reads one grid both ways and compares the solids.
"""

import math
import os
import runpy

import numpy
import part_voxels
import pytest
import vdb_dense
import vdb_volume

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def volume(shape):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass()


def bounding_box(shape):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    return box.Get()


def solids(shape):
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer

    found, explorer = 0, TopExp_Explorer(shape, TopAbs_SOLID)
    while explorer.More():
        found += 1
        explorer.Next()
    return found


def ball(n=20, radius=None):
    """The signed distance to a sphere in an n-cube of voxels, centred in it, in voxels."""
    radius = radius or n * 0.35
    i, j, k = numpy.mgrid[0:n, 0:n, 0:n]
    centre = (n - 1) / 2.0
    return numpy.sqrt((i - centre) ** 2 + (j - centre) ** 2 + (k - centre) ** 2) - radius


def described(kind="fog volume", typed="float", background=0.0, low=(0, 0, 0), voxel=(0.01,) * 3, **more):
    found = {
        "class": kind,
        "type": typed,
        "background": background,
        "low": list(low),
        "voxel": list(voxel),
        "translation": [0.0, 0.0, 0.0],
    }
    found.update(more)
    return found


def request(path, **parameters):
    return {"kind": "part", "name": "/test:volume", "path": str(path), "parameters": parameters, "config": {}}


# -- The part ----------------------------------------------------------------------------------------------------


def test_a_volume_is_the_solid_the_builtin_type_makes_of_its_grid(fake_openvdb, tmp_path):
    density = (ball() < 0).astype(numpy.float32)
    vdb = tmp_path / "smoke.vdb"
    fake_openvdb.write(str(vdb), [("density", density, described())])
    array = tmp_path / "smoke.npy"
    numpy.save(array, density)

    ours = vdb_volume.run(request(vdb))
    # 0.01 m voxels, as the grid's transform says, are 10 mm.
    builtin = part_voxels.run(request(array, size=10))

    assert "exception" not in ours, ours
    assert "exception" not in builtin, builtin
    assert volume(ours["shape"]) == pytest.approx(volume(builtin["shape"]), rel=1e-9)
    assert volume(ours["shape"]) == pytest.approx(density.sum() * 1000.0, rel=1e-9)
    assert bounding_box(ours["shape"]) == pytest.approx(bounding_box(builtin["shape"]), abs=1e-6)


def test_a_level_set_is_filled_inside_its_surface(fake_openvdb, tmp_path):
    distance = ball(30) * 0.01  # in metres, as the transform's voxels are
    # Narrow-band: what is far from the surface is the background, inside and out.
    band = numpy.where(numpy.abs(distance) < 0.03, distance, numpy.where(distance < 0, -0.03, 0.03))
    vdb = tmp_path / "sphere.vdb"
    fake_openvdb.write(str(vdb), [("surface", band, described("level set", background=0.03))])

    output = vdb_volume.run(request(vdb, unit="m"))

    assert "exception" not in output, output
    radius = 30 * 0.35 * 10.0  # mm
    assert volume(output["shape"]) == pytest.approx(4.0 / 3.0 * math.pi * radius**3, rel=0.1)


def test_the_class_as_openvdb_12_spells_it(fake_openvdb, tmp_path):
    distance = ball(12)
    vdb = tmp_path / "sphere.vdb"
    fake_openvdb.write(str(vdb), [("surface", distance, described("level set", background=99.0, enum=True))])

    grid = fake_openvdb.read(str(vdb), "surface")
    output = vdb_volume.run(request(vdb))

    assert str(grid.gridClass) == "GridClass.LEVEL_SET"
    assert vdb_dense.grid_class(grid) == "level set"
    assert "exception" not in output, output
    assert volume(output["shape"]) == pytest.approx((distance < 0).sum() * 1000.0, rel=1e-9)


def test_a_fog_volume_is_filled_at_its_threshold(fake_openvdb, tmp_path):
    # A density falling off from the middle: the higher the threshold, the less is filled.
    density = numpy.clip(1.0 - (ball(16) + 16 * 0.35) / 8.0, 0.0, 1.0).astype(numpy.float32)
    vdb = tmp_path / "smoke.vdb"
    fake_openvdb.write(str(vdb), [("density", density, described())])

    low = vdb_volume.run(request(vdb, threshold=0.2))
    high = vdb_volume.run(request(vdb, threshold=0.8))

    assert volume(low["shape"]) == pytest.approx((density >= 0.2).sum() * 1000.0, rel=1e-9)
    assert volume(high["shape"]) == pytest.approx((density >= 0.8).sum() * 1000.0, rel=1e-9)
    assert volume(high["shape"]) < volume(low["shape"])


def test_a_grid_of_integers_is_a_solid_per_label(fake_openvdb, tmp_path):
    labels = numpy.zeros((10, 10, 10), dtype=numpy.int32)
    labels[1:4, 1:4, 1:4] = 7
    labels[6:9, 6:9, 6:9] = 3
    vdb = tmp_path / "segments.vdb"
    fake_openvdb.write(str(vdb), [("labels", labels, described(typed="int32"))])

    output = vdb_volume.run(request(vdb))

    assert "exception" not in output, output
    assert solids(output["shape"]) == 2
    assert volume(output["shape"]) == pytest.approx(2 * 27 * 1000.0, rel=1e-9)


def test_a_large_grid_is_coarsened_into_shares_of_its_voxels(fake_openvdb, tmp_path):
    distance = ball(40)
    vdb = tmp_path / "sphere.vdb"
    fake_openvdb.write(str(vdb), [("surface", distance, described("level set", background=99.0))])

    fine = vdb_volume.run(request(vdb))
    coarse = vdb_volume.run(request(vdb, maxVoxels=20**3))
    found = vdb_dense.convert(str(vdb), {"maxVoxels": 20**3}, fake_openvdb)

    assert "exception" not in coarse, coarse
    assert found["values"].shape == (20, 20, 20)
    assert list(found["voxel"]) == pytest.approx([0.02] * 3)
    assert "coarsened 2 times" in str(found["what"])
    assert volume(coarse["shape"]) == pytest.approx(volume(fine["shape"]), rel=0.1)


def test_a_coarsened_edge_is_shared_by_the_voxels_it_has(fake_openvdb, tmp_path):
    # 5 voxels along X coarsened by 2: the last cell is one voxel, and full.
    occupied = numpy.ones((5, 2, 2), dtype=bool)
    vdb = tmp_path / "bar.vdb"
    fake_openvdb.write(str(vdb), [("mask", occupied, described(typed="bool", background=False))])

    found = vdb_dense.convert(str(vdb), {"maxVoxels": 5}, fake_openvdb)

    assert found["values"].shape == (3, 1, 1)
    assert list(found["values"].ravel()) == [1.0, 1.0, 1.0]


def test_tiles_meet_where_a_grid_is_larger_than_one(fake_openvdb, tmp_path, monkeypatch):
    distance = ball(30)
    vdb = tmp_path / "sphere.vdb"
    fake_openvdb.write(str(vdb), [("surface", distance, described("level set", background=99.0))])
    whole = vdb_dense.convert(str(vdb), {}, fake_openvdb)
    coarse = vdb_dense.convert(str(vdb), {"maxVoxels": 15**3}, fake_openvdb)

    monkeypatch.setattr(vdb_dense, "TILE", 7)

    assert numpy.array_equal(vdb_dense.convert(str(vdb), {}, fake_openvdb)["values"], whole["values"])
    assert numpy.allclose(vdb_dense.convert(str(vdb), {"maxVoxels": 15**3}, fake_openvdb)["values"], coarse["values"])
    assert whole["values"].sum() == (distance < 0).sum()


def test_with_origin_file_the_transform_places_it(fake_openvdb, tmp_path):
    occupied = numpy.zeros((4, 4, 4), dtype=bool)
    occupied[1:3, 1:3, 1:3] = True
    vdb = tmp_path / "cube.vdb"
    fake_openvdb.write(
        str(vdb), [("mask", occupied, described(typed="bool", background=False, low=(10, 0, 0), translation=[1, 2, 3]))]
    )

    output = vdb_volume.run(request(vdb, origin="file", unit="m"))

    xmin, ymin, zmin, xmax, ymax, zmax = bounding_box(output["shape"])
    # Index 11 to 12 along X, each voxel 10 mm and centred on its index, moved 1 m: 1105 to 1125 mm.
    assert (xmin, xmax) == pytest.approx((1105.0, 1125.0), abs=1e-6)
    assert (ymin, ymax) == pytest.approx((2005.0, 2025.0), abs=1e-6)
    assert (zmin, zmax) == pytest.approx((3005.0, 3025.0), abs=1e-6)


def test_a_transform_that_turns_the_grid_is_said_not_to(fake_openvdb, tmp_path, capfd):
    occupied = numpy.ones((2, 3, 4), dtype=bool)
    vdb = tmp_path / "turned.vdb"
    fake_openvdb.write(str(vdb), [("mask", occupied, described(typed="bool", background=False, turned=True))])

    output = vdb_volume.run(request(vdb))

    assert "exception" not in output, output
    assert "is not turned" in capfd.readouterr().err


def test_the_grid_is_chosen_by_its_class_or_by_name(fake_openvdb, tmp_path):
    vdb = tmp_path / "scene.vdb"
    fake_openvdb.write(
        str(vdb),
        [
            ("velocity", numpy.zeros((2, 2, 2)), described(typed="vec3s")),
            ("density", numpy.ones((2, 2, 2)), described()),
            ("surface", ball(6), described("level set", background=99.0)),
        ],
    )

    assert "OpenVDB grid 'surface'" in str(vdb_dense.convert(str(vdb), {}, fake_openvdb)["what"])
    assert "OpenVDB grid 'density'" in str(vdb_dense.convert(str(vdb), {"grid": "density"}, fake_openvdb)["what"])
    with pytest.raises(ValueError, match="only a grid of numbers bounds something"):
        vdb_dense.convert(str(vdb), {"grid": "velocity"}, fake_openvdb)
    output = vdb_volume.run(request(vdb, grid="smoke"))
    assert output["exception"] == (
        "scene.vdb: it holds no grid named 'smoke'; it holds 'velocity', 'density', 'surface'"
    )


def test_what_openvdb_cannot_read_is_said(fake_openvdb, tmp_path):
    vdb = tmp_path / "nothing.vdb"
    vdb.write_text("not a volume")

    output = vdb_volume.run(request(vdb))

    assert output["exception"].startswith("nothing.vdb: OpenVDB cannot read it: ")


def test_an_empty_grid_is_said_to_be(fake_openvdb, tmp_path):
    vdb = tmp_path / "empty.vdb"
    fake_openvdb.write(str(vdb), [("density", numpy.zeros((3, 3, 3)), described())])

    assert "has no active voxel" in vdb_volume.run(request(vdb))["exception"]


def test_with_no_openvdb_the_failure_says_where_it_is(tmp_path, monkeypatch):
    monkeypatch.delenv("PC_OPENVDB_PYTHON", raising=False)
    monkeypatch.setattr(vdb_volume, "DEFAULT_PYTHON", str(tmp_path / "none"))

    output = vdb_volume.run(request(tmp_path / "a.vdb"))

    assert "there is no OpenVDB here" in output["exception"]


def test_the_builtin_reader_is_put_back(fake_openvdb, tmp_path):
    vdb = tmp_path / "smoke.vdb"
    fake_openvdb.write(str(vdb), [("density", numpy.ones((2, 2, 2)), described())])
    vdb_volume.run(request(vdb))

    assert part_voxels.read.__module__ == "part_voxels"


def test_the_unit(fake_openvdb, tmp_path):
    vdb = tmp_path / "cube.vdb"
    fake_openvdb.write(
        str(vdb), [("mask", numpy.ones((2, 2, 2), dtype=bool), described(typed="bool", voxel=[1, 1, 1]))]
    )

    assert volume(vdb_volume.run(request(vdb, unit="mm"))["shape"]) == pytest.approx(8.0)
    assert volume(vdb_volume.run(request(vdb, unit="cm"))["shape"]) == pytest.approx(8000.0)
    assert "'unit' is one of" in vdb_volume.run(request(vdb, unit="furlong"))["exception"]


# -- The script --------------------------------------------------------------------------------------------------


def test_the_package_script_hands_the_request_to_the_library(fake_openvdb, tmp_path):
    vdb = tmp_path / "smoke.vdb"
    fake_openvdb.write(str(vdb), [("density", (ball(8) < 0).astype(numpy.float32), described())])

    found = runpy.run_path(
        os.path.join(ROOT, "vdb.py"), init_globals={"request": request(vdb)}, run_name="__partcad_part__"
    )

    assert "exception" not in found["output"], found["output"]
    assert volume(found["output"]["shape"]) > 0


def test_the_package_script_outside_the_image_says_so(tmp_path, monkeypatch):
    monkeypatch.setenv("PC_VOLUME_OPENVDB_LIBRARY", str(tmp_path))

    found = runpy.run_path(
        os.path.join(ROOT, "vdb.py"), init_globals={"request": request("a.vdb")}, run_name="__partcad_part__"
    )

    assert "runs in the image its package names" in found["output"]["exception"]
