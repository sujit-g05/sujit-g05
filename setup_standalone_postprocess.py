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

write_file("system/cylinder/probes", get_header("dictionary", "probes") + """
type            probes;
libs            ("libsampling.so");
region          cylinder;
fields          (T);
probeLocations
(
    (-0.14 -0.0745 0.05) // 1
    ( 0.14 -0.0745 0.05) // 2
    (-0.14  0.0745 0.05) // 3
    ( 0.14  0.0745 0.05) // 4
    (-0.14  0.0749 0.05) // 5
    ( 0.14  0.0749 0.05) // 6
    (-0.14 -0.0749 0.05) // 7
    ( 0.14 -0.0749 0.05) // 8
);
""")

write_file("system/innerAir/probes", get_header("dictionary", "probes") + """
type            probes;
libs            ("libsampling.so");
region          innerAir;
fields          (T);
probeLocations
(
    (0  0.0383 0.05) // 9
    (0 -0.0383 0.05) // 10
);
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
