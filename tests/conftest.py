#
# PartCAD, 2026
#
# Licensed under Apache License, Version 2.0.
#
"""Where the tests find what the part type runs with.

* The reader: the image's copy where these tests run in the image
  (/opt/partcad-volume-openvdb), which is the copy a user's parts are built
  with; this checkout's image/lib anywhere else.
* PartCAD's wrappers directory, which is on the path when PartCAD runs the
  script, for 'ocp_serialize' (the voxel builder compounds its solids with it):
  from an installed PartCAD, which needs none of its dependencies for that.
* OpenVDB: a stand-in module (fake/openvdb.py), run by this Python as if it
  were OpenVDB's, for the tests of what this code does with what OpenVDB
  says; and the real one -- the image's -- for 'test_live.py', which is
  skipped where there is none.
"""

import importlib.util
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FAKE = os.path.join(HERE, "fake")
IMAGE_LIBRARY = "/opt/partcad-volume-openvdb"
LIBRARY = (
    IMAGE_LIBRARY
    if os.path.isfile(os.path.join(IMAGE_LIBRARY, "vdb_volume.py"))
    else os.path.join(ROOT, "image", "lib")
)
REAL_PYTHON = os.environ.get("PC_OPENVDB_PYTHON_REAL") or (
    "/opt/openvdb/bin/python" if os.path.exists("/opt/openvdb/bin/python") else None
)

os.environ["PC_VOLUME_OPENVDB_LIBRARY"] = LIBRARY
sys.path.insert(0, LIBRARY)

spec = importlib.util.find_spec("partcad")
if spec is not None and spec.submodule_search_locations:
    sys.path.append(os.path.join(list(spec.submodule_search_locations)[0], "wrappers"))


@pytest.fixture
def fake_openvdb(tmp_path, monkeypatch):
    """A "Python with OpenVDB" that is this one with the stand-in on its path: the module, to write volumes with."""
    program = tmp_path / "python-with-openvdb"
    program.write_text(
        "#!%s\n"
        "import runpy, sys\n"
        "sys.path.insert(0, %r)\n"
        "arguments = [a for a in sys.argv[1:] if a != '-I']\n"
        "sys.argv = arguments\n"
        "runpy.run_path(arguments[0], run_name='__main__')\n" % (sys.executable, FAKE)
    )
    program.chmod(0o755)
    monkeypatch.setenv("PC_OPENVDB_PYTHON", str(program))
    sys.path.insert(0, FAKE)
    try:
        import openvdb

        yield openvdb
    finally:
        sys.path.remove(FAKE)
        sys.modules.pop("openvdb", None)


@pytest.fixture
def real_openvdb(monkeypatch):
    if not REAL_PYTHON:
        pytest.skip("there is no OpenVDB here: these run in the image (see .github/workflows/test.yml)")
    monkeypatch.setenv("PC_OPENVDB_PYTHON", REAL_PYTHON)
    return REAL_PYTHON
