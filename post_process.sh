#!/bin/bash
set -e

echo "Retroactively extracting probe and surface data from existing simulation..."

# Run postProcess on the specific regions pointing to the standalone dictionary files
postProcess -region cylinder -dict system/cylinder/probes
postProcess -region innerAir -dict system/innerAir/probes
postProcess -region cylinder -dict system/cylinder/surfaces

echo "Data extraction complete. Generating Gnuplot scripts and images..."

cat << 'GNUPLOT' > plot_temperatures.gnuplot
set terminal pngcairo size 1024,768 enhanced font 'Verdana,12'
set grid
set xlabel "Time (s)"
set ylabel "Temperature (K)"
set key outside right top

# Plot Cylinder Probes (1-8)
set title "Cylinder Temperature Probes (1-8)"
set output "cylinder_temperatures.png"
plot \
  "postProcessing/cylinder/probes/0/T" using 1:2 with lines title 'Sensor 1 (Bottom Inner)', \
  "postProcessing/cylinder/probes/0/T" using 1:3 with lines title 'Sensor 2', \
  "postProcessing/cylinder/probes/0/T" using 1:4 with lines title 'Sensor 3 (Top Inner)', \
  "postProcessing/cylinder/probes/0/T" using 1:5 with lines title 'Sensor 4', \
  "postProcessing/cylinder/probes/0/T" using 1:6 with lines title 'Sensor 5 (Top Outer)', \
  "postProcessing/cylinder/probes/0/T" using 1:7 with lines title 'Sensor 6', \
  "postProcessing/cylinder/probes/0/T" using 1:8 with lines title 'Sensor 7 (Bottom Outer)', \
  "postProcessing/cylinder/probes/0/T" using 1:9 with lines title 'Sensor 8'

# Plot Inner Air Probes (9-10)
set title "Inner Air Temperature Probes (9-10)"
set output "innerAir_temperatures.png"
plot \
  "postProcessing/innerAir/probes/0/T" using 1:2 with lines title 'Sensor 9', \
  "postProcessing/innerAir/probes/0/T" using 1:3 with lines title 'Sensor 10'
GNUPLOT

echo "Running Gnuplot..."
if command -v gnuplot &> /dev/null; then
    gnuplot plot_temperatures.gnuplot
    echo "Plots generated successfully: cylinder_temperatures.png and innerAir_temperatures.png"
else
    echo "Gnuplot is not installed on this system. The script 'plot_temperatures.gnuplot' has been generated for you to run elsewhere."
fi

echo "And you can visualize the VTK slices by opening them in ParaView."
