#!/bin/bash
set -e

echo "Retroactively extracting probe and surface data from existing simulation..."

# Run postProcess on the specific regions pointing to the standalone dictionary files
postProcess -region cylinder -dict system/cylinder/probes
postProcess -region innerAir -dict system/innerAir/probes
postProcess -region cylinder -dict system/cylinder/surfaces

echo "Data extraction complete. You can view the extracted probe data in the 'postProcessing' folder."
echo "And you can visualize the VTK slices by opening them in ParaView."
