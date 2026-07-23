import trimesh
import numpy as np
import os

# Create directory if it doesn't exist
os.makedirs('constant/triSurface', exist_ok=True)

# Cylinder specs
cyl_length = 560e-3 # 560 mm to m
cyl_outer_diam = 150e-3 # 150 mm to m
cyl_outer_radius = cyl_outer_diam / 2.0
cyl_thickness = 0.9e-3 # 0.9 mm to m
cyl_inner_radius = cyl_outer_radius - cyl_thickness

# Heater specs
heater_length = 600e-3 # 600 mm to m
heater_mass = 191e-3 # 191 g to kg
heater_density = 7.25 * 1000 # 7.25 g/cm^3 to kg/m^3
# Volume = mass / density
heater_volume = heater_mass / heater_density
# V = pi * r^2 * h => r = sqrt(V / (pi * h))
heater_radius = np.sqrt(heater_volume / (np.pi * heater_length))

# Generate Heater (solid cylinder at origin)
heater = trimesh.creation.cylinder(radius=heater_radius, height=heater_length, sections=100)
# Orient along X axis to match the long dimension of blockMesh
rot_matrix = trimesh.transformations.rotation_matrix(np.pi/2, [0, 1, 0])
heater.apply_transform(rot_matrix)
heater.export('constant/triSurface/heater.stl', file_type='stl_ascii')

# Generate Hollow Cylinder

# In trimesh >= 4.0, annulus directly creates a 3D volume if height is passed
cylinder = trimesh.creation.annulus(r_min=cyl_inner_radius, r_max=cyl_outer_radius, height=cyl_length)

cylinder.apply_transform(rot_matrix)
cylinder.export('constant/triSurface/cylinder.stl', file_type='stl_ascii')

# Generate Borosilicate glass disks
glass_thickness = 2e-3
glass1 = trimesh.creation.annulus(r_min=heater_radius, r_max=cyl_outer_radius, height=glass_thickness)
glass1.apply_translation([0, 0, -glass_thickness/2])
# Move glass1 to one end of the cylinder (along Z before rotation, so translate along Z then rotate)
glass1.apply_translation([0, 0, cyl_length/2 + glass_thickness/2])
glass1.apply_transform(rot_matrix)

glass2 = trimesh.creation.annulus(r_min=heater_radius, r_max=cyl_outer_radius, height=glass_thickness)
glass2.apply_translation([0, 0, -glass_thickness/2])
# Move glass2 to the other end
glass2.apply_translation([0, 0, -(cyl_length/2 + glass_thickness/2)])
glass2.apply_transform(rot_matrix)

# Combine both glasses into one STL for meshing simplicity, or keep separate
glass_combined = trimesh.util.concatenate([glass1, glass2])
glass_combined.export('constant/triSurface/glass.stl', file_type='stl_ascii')

print("STLs generated successfully in constant/triSurface/")
print(f"Heater radius calculated as: {heater_radius*1000:.2f} mm")
