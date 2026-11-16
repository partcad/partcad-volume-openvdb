# partcad-volume-openvdb

[OpenVDB](https://www.openvdb.org) volumes as [PartCAD](https://github.com/partcad/partcad) parts: the exact solid a
`.vdb`'s voxels fill.

OpenVDB is how film, simulation and 3D printing software keeps a volume: a sparse grid of voxels holding the signed
distance to a surface (a *level set*: Houdini, Blender's remesher, many slicers), a density (a *fog volume*: smoke,
a CT scan, a simulation's field), occupancy, or labels. The `vdb` part type reads one with OpenVDB itself and hands
the grid to PartCAD's own `voxels` code: the filled voxels, taken into boxes and fused, a solid per label.

| The grid | Is filled |
|---|---|
| a level set | inside its surface, where the distance is below nought |
| a fog volume, or any grid of numbers | at `threshold` (0.5) and above |
| booleans | where true |
| integers | by label, a solid per value -- or at `threshold`, which says they are densities |

## What it needs

A container runtime -- Docker, running -- and nothing else. The type runs in
`ghcr.io/partcad/partcad-volume-openvdb`, which carries OpenVDB's Python bindings (conda-forge's build), OCP, and the
reader; PartCAD pulls it the first time a part needs it. A machine with no container runtime cannot build these
parts, and says so, naming the image.

Requires PartCAD 0.10.24 or later, the first to run a part type in a `container:`.

## Using it

```yaml
dependencies:
  openvdb:
    type: git
    url: https://github.com/partcad/partcad-volume-openvdb

parts:
  lattice:
    type: openvdb:vdb
    path: volumes/lattice.vdb
    parameters:
      unit: mm          # the grid's world unit
  plume:
    type: openvdb:vdb
    path: volumes/explosion.vdb
    parameters:
      grid: density
      threshold: 0.2
      maxVoxels: 2097152   # 128 cubed: coarser, and quicker
```

## Parameters

Everything PartCAD's `voxels` type takes -- `size`, `up`, `origin`, `maxBoxes`: see "Height maps, point clouds and
voxels" in PartCAD's part documentation -- and:

| | |
|---|---|
| `grid` | which of the file's grids: by default its first level set, else its first fog volume, else its first grid of numbers |
| `threshold` | the value a fog volume or a grid of numbers is filled at (0.5); for integers, that they are densities rather than labels |
| `unit` | the grid's world unit (`m`, `cm`, `mm`, `um`, `in`, `ft`; metres by default): a voxel is its transform's size in it, unless `size` says otherwise |
| `maxVoxels` | the most cells the grid is read into (16,777,216: 256 cubed). A larger grid is coarsened by a whole factor, each cell then filled where most of its voxels are; labels are then read as occupancy |

With `origin: file` the solid is where the grid's transform puts it. A transform that turns the grid is not applied
-- only its scale and its offset -- and a warning says so.

## How it works

`vdb.py`, the script the type names, hands the request to the reader the image installed at
`/opt/partcad-volume-openvdb` (`image/lib`). OpenVDB's bindings are built for conda-forge's Python and numpy, so they
live in an environment of their own at `/opt/openvdb`, and `vdb_dense.py` runs there: it reads the grid a tile at a
time and writes what it fills to an `.npz`. `vdb_volume.py`, on the image's Python, hands that to `part_voxels`: a copy
of PartCAD's own, beside it.

The copies of PartCAD's `part_voxels.py` and `voxel_solid.py` are kept by `image/sync-partcad.sh`, which records where
they came from in `image/lib/PARTCAD.sha256`; a test fails when a copy differs from what was copied. They are in the
image rather than taken from the PartCAD that runs the part, because a part is cached against the image's tag:
whatever builds it has to be in the image.

## Developing

```bash
pip install pytest "build123d==0.11.1" "cadquery-ocp-novtk==7.9.3.1.1"
pip install --no-deps "partcad @ git+https://github.com/partcad/partcad@devel"   # its wrappers, for 'ocp_serialize'
pytest                                                                           # with a stand-in for OpenVDB

docker build -t ghcr.io/partcad/partcad-volume-openvdb:$(cat VERSION) image     # the image, tagged as partcad.yaml names it
docker run --rm --user root -v "$PWD:/src" -w /src ghcr.io/partcad/partcad-volume-openvdb:$(cat VERSION) \
  sh -c 'pip install pytest && pip install --no-deps "partcad @ git+https://github.com/partcad/partcad@devel" && python3 -m pytest'
```

The tests in `tests/test_live.py` run only where the real bindings are -- in the image -- and write every volume they
read with OpenVDB itself.

**A change to the image is a new `VERSION`**, and the same tag in `partcad.yaml` (a test holds the two together). CI
publishes the image for amd64 and arm64 when `main` moves to a version that is not published yet, and never rebuilds
a published one: parts are cached against the tag, so a rebuilt tag is a change nobody's cache notices.

## License

Apache 2.0: see [LICENSE](LICENSE) and [NOTICE](NOTICE).
