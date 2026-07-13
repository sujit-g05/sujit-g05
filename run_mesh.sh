#!/bin/bash
set -e

echo "Generating base mesh with blockMesh..."
blockMesh

echo "Extracting surface features..."
surfaceFeatureExtract

echo "Running snappyHexMesh for multi-region..."
snappyHexMesh -overwrite

echo "Splitting mesh regions..."
splitMeshRegions -cellZones -overwrite

echo "Mesh generation complete!"
