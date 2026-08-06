#!/bin/bash
set -e

echo "Retroactively extracting probe and surface data from existing simulation..."

# Run postProcess on the specific regions pointing to the standalone dictionary files
postProcess -region cylinder -dict system/cylinder/probes || echo "Warning: Cylinder probes failed, maybe already extracted?"
postProcess -region innerAir -dict system/innerAir/probes || echo "Warning: InnerAir probes failed, maybe already extracted?"
postProcess -region cylinder -dict system/cylinder/surfaces || echo "Warning: Cylinder surfaces failed."

echo "Data extraction complete. Locating data for Gnuplot..."

CYL_FILE=$(find postProcessing/cylinder -path "*/0/T" | head -n 1)
AIR_FILE=$(find postProcessing/innerAir -path "*/0/T" | head -n 1)

if [ -z "$CYL_FILE" ]; then
    echo "Error: Could not find cylinder probe data file 'T'."
else
    echo "Found cylinder data at: $CYL_FILE"
fi

if [ -z "$AIR_FILE" ]; then
    echo "Error: Could not find innerAir probe data file 'T'."
else
    echo "Found inner air data at: $AIR_FILE"
fi

cat << GNUPLOT > plot_temperatures.gnuplot
set terminal pngcairo size 1024,768 enhanced font 'Verdana,12'
set grid
set xlabel "Time (s)"
set ylabel "Temperature (K)"
set key outside right top

# Plot Cylinder Probes (1-8)
set title "Cylinder Temperature Probes (1-8)"
set output "cylinder_temperatures.png"
plot \\
  "$CYL_FILE" using 1:2 with lines title 'Sensor 1 (Bottom Inner)', \\
  "$CYL_FILE" using 1:3 with lines title 'Sensor 2', \\
  "$CYL_FILE" using 1:4 with lines title 'Sensor 3 (Top Inner)', \\
  "$CYL_FILE" using 1:5 with lines title 'Sensor 4', \\
  "$CYL_FILE" using 1:6 with lines title 'Sensor 5 (Top Outer)', \\
  "$CYL_FILE" using 1:7 with lines title 'Sensor 6', \\
  "$CYL_FILE" using 1:8 with lines title 'Sensor 7 (Bottom Outer)', \\
  "$CYL_FILE" using 1:9 with lines title 'Sensor 8'

# Plot Inner Air Probes (9-10)
set title "Inner Air Temperature Probes (9-10)"
set output "innerAir_temperatures.png"
plot \\
  "$AIR_FILE" using 1:2 with lines title 'Sensor 9', \\
  "$AIR_FILE" using 1:3 with lines title 'Sensor 10'
GNUPLOT

echo "Running Gnuplot..."
if command -v gnuplot &> /dev/null; then
    gnuplot plot_temperatures.gnuplot
    echo "Plots generated successfully: cylinder_temperatures.png and innerAir_temperatures.png"
else
    echo "Gnuplot is not installed on this system. The script 'plot_temperatures.gnuplot' has been generated for you to run elsewhere."
fi

echo "And you can visualize the VTK slices by opening them in ParaView."
