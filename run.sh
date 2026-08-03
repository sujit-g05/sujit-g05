#!/bin/bash
set -e
rm -rf constant/polyMesh constant/*/polyMesh
blockMesh
splitMeshRegions -cellZones -overwrite
