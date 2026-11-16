#
# PartCAD, 2026
#
# Licensed under Apache License, Version 2.0.
#
"""The 'vdb' part type: an OpenVDB volume, as a solid.

This runs in the image the type names ('container:' in partcad.yaml), which
carries OpenVDB and the code that reads with it (image/lib, installed at
/opt/partcad-volume-openvdb): this script only hands the request over, so that
what reads a volume is the image, and a part is keyed on the image's tag.

'PC_VOLUME_OPENVDB_LIBRARY' names another copy of that code, for running it
outside the image (the tests do).
"""

import os
import sys

CACHE_VERSION = 1

LIBRARY = os.environ.get("PC_VOLUME_OPENVDB_LIBRARY") or "/opt/partcad-volume-openvdb"

if __name__ == "__partcad_part__":
    if not os.path.isfile(os.path.join(LIBRARY, "vdb_volume.py")):
        output = {
            "exception": "%s holds no OpenVDB reader: this part type runs in the image its package names "
            "(partcad-volume-openvdb), and this is not it" % LIBRARY
        }
    else:
        sys.path.insert(0, LIBRARY)
        import vdb_volume

        output = vdb_volume.run(request)  # noqa: F821
