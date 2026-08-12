#!/bin/sh

rm -rf 0
rm -rf constant/*/polyMesh
rm -rf constant/polyMesh

if ! command -v blockMesh >/dev/null 2>&1; then
    echo "OpenFOAM not found in PATH. Skipping execution."
else
    # Mesh generation
    blockMesh
    splitMeshRegions -cellZones -overwrite

    # Setup initial fields
    cp -r 0.orig 0

    # Radiation setup for innerAir
    faceAgglomerate -region innerAir -dict system/innerAir/viewFactorsDict
    viewFactorsGen -region innerAir

    # Run solver
    foamMultiRun
fi
