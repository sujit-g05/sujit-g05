import os

def get_header(cls, obj):
    return f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\    /   O peration     | Version:  13                                    |
|   \\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       {cls};
    object      {obj};
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
"""

def write_file(filepath, content):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        f.write(content)

import math
angles = [0, 90, 180, 270]
r_in = 0.0741
r_out = 0.075
z = 0.05

cyl_probes = ""
probe_id = 1
for angle in angles:
    rad = math.radians(angle)
    x = r_in * math.cos(rad)
    y = r_in * math.sin(rad)
    cyl_probes += f"    ({x:8.5f} {y:8.5f} {z}) // {probe_id} (inner)\n"
    probe_id += 1

for angle in angles:
    rad = math.radians(angle)
    x = r_out * math.cos(rad)
    y = r_out * math.sin(rad)
    cyl_probes += f"    ({x:8.5f} {y:8.5f} {z}) // {probe_id} (outer)\n"
    probe_id += 1

air_probes = ""
r_air = 0.0383
for angle in [90, 270]:
    rad = math.radians(angle)
    x = r_air * math.cos(rad)
    y = r_air * math.sin(rad)
    air_probes += f"    ({x:8.5f} {y:8.5f} {z}) // {probe_id} (air)\n"
    probe_id += 1

write_file("system/cylinder/probes", get_header("dictionary", "probes") + f"""
type            probes;
libs            ("libsampling.so");
region          cylinder;
fields          (T);
probeLocations
(
{cyl_probes});
""")

write_file("system/innerAir/probes", get_header("dictionary", "probes") + f"""
type            probes;
libs            ("libsampling.so");
region          innerAir;
fields          (T);
probeLocations
(
{air_probes});
""")

write_file("system/cylinder/surfaces", get_header("dictionary", "surfaces") + """
type            surfaces;
libs            ("libsampling.so");
region          cylinder;
surfaceFormat   vtk;
fields          (T);
interpolationScheme cellPoint;
surfaces
(
    upper_surface
    {
        type            plane;
        planeType       pointAndNormal;
        pointAndNormalDict
        {
            point   (0 0.075 0.05);
            normal  (0 1 0);
        }
    }
    lower_surface
    {
        type            plane;
        planeType       pointAndNormal;
        pointAndNormalDict
        {
            point   (0 -0.075 0.05);
            normal  (0 -1 0);
        }
    }
);
""")
