#!/bin/bash
set -e

echo "Retroactively extracting probe and surface data from existing simulation..."

# Run postProcess on the specific regions and functions defined in system/controlDict
postProcess -region cylinder -func probes_cylinder
postProcess -region innerAir -func probes_innerAir
postProcess -region cylinder -func surfaces_cylinder

echo "Data extraction complete. You can view the extracted probe data in the 'postProcessing' folder."
