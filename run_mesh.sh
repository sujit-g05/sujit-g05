#!/bin/sh

if ! command -v blockMesh >/dev/null 2>&1; then
    echo "OpenFOAM not found in PATH. Skipping mesh generation."
else
    blockMesh
    splitMeshRegions -cellZones -overwrite
fi
