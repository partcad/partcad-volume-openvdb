#
# PartCAD, 2026
#
# Licensed under Apache License, Version 2.0.
#
"""What has to agree across the repository: the image the type names, the one built, and the copies of PartCAD."""

import hashlib
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def read(*path):
    with open(os.path.join(ROOT, *path)) as f:
        return f.read()


def test_the_type_names_the_image_this_repository_builds():
    version = read("VERSION").strip()
    images = re.findall(r"^\s+image:\s*(\S+)\s*$", read("partcad.yaml"), re.MULTILINE)

    assert images, "partcad.yaml names no image"
    # A part is cached against the tag: the package has to name the image
    # its own code went into, which is the one CI publishes as VERSION.
    assert set(images) == {"ghcr.io/partcad/partcad-volume-openvdb:%s" % version}


def test_the_copies_of_partcad_are_what_was_copied():
    lines = [line for line in read("image", "lib", "PARTCAD.sha256").splitlines() if not line.startswith("#")]
    recorded = dict(reversed(line.split()) for line in lines if line.strip())

    assert set(recorded) == {"part_voxels.py", "voxel_solid.py"}
    for name, digest in recorded.items():
        with open(os.path.join(ROOT, "image", "lib", name), "rb") as f:
            assert hashlib.sha256(f.read()).hexdigest() == digest, (
                "image/lib/%s is not what image/sync-partcad.sh copied from PartCAD: change it there, and copy it "
                "again" % name
            )


def test_the_image_installs_what_the_script_looks_for():
    dockerfile = read("image", "Dockerfile")

    assert "/opt/partcad-volume-openvdb" in read("vdb.py")
    assert re.search(r"^COPY .*lib/ /opt/partcad-volume-openvdb/?$", dockerfile, re.MULTILINE)
    assert "/opt/openvdb" in dockerfile
