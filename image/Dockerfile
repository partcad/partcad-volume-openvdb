# The image the 'vdb' part type runs in: PartCAD's Python base, with OCP
# (which a part type hands its shapes back in), OpenVDB's Python bindings, and
# the code that reads with them.
#
# Built FROM PartCAD's own base image, as PartCAD's part type documentation asks
# of an image a 'container:' names ("What the image needs"): it carries the
# Python and the JSON-RPC service PartCAD runs commands through, and its
# 'verify.py' checks that contract at the end of this build.
#
#   docker build -t ghcr.io/partcad/partcad-volume-openvdb:$(cat VERSION) image
#
# A new image is a new tag (VERSION), never a new build under an old one: a
# part is cached against the tag it was built with.

# The PartCAD release whose base image this is built on, and the Python in it.
ARG PARTCAD_VERSION=0.10.26
ARG PYTHON_VERSION=3.12
# Set by BuildKit to the architecture being built ('amd64', 'arm64'): PartCAD
# publishes its base image per architecture.
ARG TARGETARCH

# OpenVDB's Python bindings are built by conda-forge for conda-forge's Python
# and numpy (Debian's are for Debian's Python, and PyPI has none), so they come
# from there -- into an environment of their own, at /opt/openvdb, with its own
# interpreter. The part's script runs on the image's Python (with OCP) and runs
# 'vdb_dense.py' on this one, which hands the grid back as a file.
FROM mambaorg/micromamba:2.10.0-debian13-slim AS openvdb
ARG OPENVDB_VERSION=14.0.0
USER root
RUN micromamba create --yes --prefix /opt/openvdb --channel conda-forge --override-channels \
      "python=3.12" "numpy>=2,<3" "openvdb=${OPENVDB_VERSION}" \
  && micromamba clean --all --yes \
  && rm -rf /opt/openvdb/include \
  && /opt/openvdb/bin/python -I -c "import openvdb; print('OpenVDB', getattr(openvdb, 'LIBRARY_VERSION', '?'))"


FROM ghcr.io/partcad/partcad-container-python:${PARTCAD_VERSION}-py${PYTHON_VERSION}-${TARGETARCH}
ARG PARTCAD_VERSION
ARG OPENVDB_VERSION=14.0.0

USER root

# OCP at the version PartCAD's sandboxes have it (sandbox_versions.BUILD123D
# and .OCP), which brings numpy.
RUN pip install --no-cache-dir "build123d==0.11.1" "cadquery-ocp-novtk==7.9.3.1.1"

COPY --from=openvdb /opt/openvdb /opt/openvdb
ENV PC_OPENVDB_PYTHON=/opt/openvdb/bin/python

COPY lib/ /opt/partcad-volume-openvdb/
RUN python3 -c "import sys; sys.path.insert(0, '/opt/partcad-volume-openvdb'); import vdb_volume, part_voxels, voxel_solid; import OCP" \
  && /opt/openvdb/bin/python -I -c "import sys; sys.path.insert(0, '/opt/partcad-volume-openvdb'); import vdb_dense; vdb_dense.bindings()" \
  && python3 /pc/verify.py

LABEL partcad.image="1"
LABEL partcad.partcad="${PARTCAD_VERSION}"
LABEL partcad.openvdb="${OPENVDB_VERSION}"
LABEL org.opencontainers.image.source="https://github.com/partcad/partcad-volume-openvdb"
LABEL org.opencontainers.image.description="OpenVDB for PartCAD's 'vdb' part type"
LABEL org.opencontainers.image.licenses="Apache-2.0"

USER pc
