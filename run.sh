#!/bin/bash
set -e
rm -rf 0 constant/polyMesh constant/*/polyMesh
blockMesh
splitMeshRegions -cellZones -overwrite

# Initialize boundary fields required for agglomeration and view factors
cp -r 0.orig 0

faceAgglomerate -region innerAir -dict system/innerAir/viewFactorsDict
faceAgglomerate -region outerAir -dict system/outerAir/viewFactorsDict
viewFactorsGen -region innerAir
viewFactorsGen -region outerAir

# Create ParaView files
paraFoam -touchAll
