#!/bin/bash
set -e

echo "Checking OpenFOAM environment..."
if ! command -v blockMesh &> /dev/null; then
    echo "Warning: OpenFOAM environment (v13) not found or not sourced."
    echo "Skipping execution test..."
else
    echo "Running meshing script..."
    blockMesh
    surfaceFeatures
    snappyHexMesh -overwrite

    echo "Copying 0.orig to 0..."
    rm -rf 0
    cp -r 0.orig 0

    echo "Splitting mesh regions..."
    splitMeshRegions -cellZones -overwrite

    echo "Running changeDictionary for all regions..."
    for region in air_outer air_inner heater cylinder glass_top glass_bottom; do
        changeDictionary -region $region
    done

    echo "Decomposing mesh for parallel execution..."
    decomposePar -allRegions -force

    echo "Running chtMultiRegionFoam in parallel on 8 processors..."
    mpirun -np 8 chtMultiRegionFoam -parallel

    echo "Reconstructing mesh and fields..."
    reconstructPar -allRegions

    echo "Simulation setup completed successfully!"
fi
