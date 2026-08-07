#!/bin/bash
set -e
rm -rf 0 constant/polyMesh constant/*/polyMesh
blockMesh
splitMeshRegions -cellZones -overwrite

viewFactorsGen -region innerAir
viewFactorsGen -region outerAir

cp -r 0.orig 0

# Create ParaView files
paraFoam -touchAll
