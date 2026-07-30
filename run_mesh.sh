#!/bin/bash
set -e

# Sourcing OpenFOAM environment if necessary
# source /opt/openfoam13/etc/bashrc

echo "Checking OpenFOAM environment..."
if ! command -v blockMesh &> /dev/null; then
    echo "Warning: OpenFOAM environment (v13) not found or not sourced."
    echo "Please ensure you have OpenFOAM v13 installed and sourced, e.g.:"
    echo "  source /opt/openfoam13/etc/bashrc"
    echo "Skipping meshing test..."
else
    echo "Running blockMesh..."
    blockMesh

    echo "Extracting surface features..."
    surfaceFeatures

    echo "Running snappyHexMesh..."
    snappyHexMesh -overwrite

    echo "Splitting mesh regions..."
    splitMeshRegions -cellZones -overwrite

    echo "Meshing completed successfully!"
fi
