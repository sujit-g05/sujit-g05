#!/bin/bash
set -e
rm -rf constant/polyMesh constant/*/polyMesh
blockMesh
splitMeshRegions -cellZones -overwrite

rm -rf 0
cp -r 0.orig 0
