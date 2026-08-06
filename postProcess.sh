#!/bin/sh
. ${WM_PROJECT_DIR:-/opt/openfoam13}/bin/tools/RunFunctions 2>/dev/null || true

echo "Running post-processing on existing simulation data..."
# Use -postProcess directly on the solver to execute the function objects defined in system/controlDict
# across all previously simulated time directories.
foamMultiRun -postProcess -func cylinder_probes
foamMultiRun -postProcess -func heater_probes
foamMultiRun -postProcess -func cylinderSurface

echo "Post-processing complete. You can find the data in the postProcessing/ directory."
