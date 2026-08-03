#!/bin/bash
set -e
gmshToFoam mesh.msh

# Update boundary type for frontAndBack to empty
sed -i '/frontAndBack/,/}/ s/type.*patch;/type empty;/' constant/polyMesh/boundary
sed -i '/frontAndBack/,/}/ s/type.*wall;/type empty;/' constant/polyMesh/boundary

splitMeshRegions -cellZones -overwrite
