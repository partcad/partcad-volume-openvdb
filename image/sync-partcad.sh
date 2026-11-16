#!/bin/sh
# Copy PartCAD's voxel modules into image/lib, and record where from.
#
#   image/sync-partcad.sh <a PartCAD checkout>
#
# The image makes a grid a solid with PartCAD's own code -- the 'voxels'
# part type of //builtin/import and the builder it uses -- so that a part
# read here is the solid the built-in type would make of the same grid. They
# are copies rather than an import because the image has no PartCAD in it: the
# script runs there as the image has it (see "Running in a container" in
# PartCAD's part type documentation), and what it builds is cached against the
# image's tag, so what builds it has to be in the image.
#
# Edit them in PartCAD, then run this. A test fails when a copy differs from
# what PARTCAD.sha256 says was copied, which is what keeps a local edit from
# drifting away from PartCAD unnoticed. A new copy is a new image: bump VERSION.
set -eu

checkout=${1:?usage: $0 <a PartCAD checkout>}
source_dir="$checkout/src/partcad/builtin/import"
here=$(cd "$(dirname "$0")" && pwd)
lib="$here/lib"
files="part_voxels.py voxel_solid.py"

for file in $files; do
  cp "$source_dir/$file" "$lib/$file"
done

commit=$(git -C "$checkout" rev-parse HEAD)
{
  echo "# Copied from partcad/partcad at $commit, src/partcad/builtin/import/."
  echo "# Written by image/sync-partcad.sh: do not edit by hand."
  (cd "$lib" && sha256sum $files)
} >"$lib/PARTCAD.sha256"

echo "Copied $files from $commit"
