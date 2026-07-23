import os

def write_file(path, content):
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    with open(path, "w") as f:
        f.write(content)

write_file("Allrun", """#!/bin/sh
. ${WM_PROJECT_DIR:-/opt/openfoam13}/bin/tools/RunFunctions 2>/dev/null || true

echo "Cleaning up..."
rm -rf 0
rm -rf constant/polyMesh system/polyMesh
rm -rf constant/air/polyMesh constant/cylinder/polyMesh constant/heater/polyMesh constant/glass/polyMesh


echo "Checking Python dependencies for geometry generation..."
python3 -c "import trimesh; import numpy" 2>/dev/null || { echo "Installing required Python packages..."; pip install trimesh numpy; }

echo "Generating geometry..."
python generate_stls.py

echo "Running blockMesh..."
blockMesh

echo "Extracting surface features..."
surfaceFeatures

echo "Running snappyHexMesh..."
snappyHexMesh -overwrite

echo "Defining fluid cell zones..."
topoSet

echo "Setting up initial conditions..."
cp -r 0.orig 0

echo "Splitting mesh by regions..."
splitMeshRegions -cellZones -overwrite

# OpenFOAM v13 splitMeshRegions automatically configures the coupled mapped boundary conditions in the 0/ region directories.


echo "Applying changeDictionary to setup coupled multi-region boundaries..."
for region in air cylinder heater glass; do
    changeDictionary -region $region
done

echo "Decomposing mesh for parallel execution..."
runApplication decomposePar -allRegions

echo "Running foamMultiRun in parallel..."
runParallel foamMultiRun

echo "Reconstructing mesh and fields..."
runApplication reconstructPar -allRegions

echo "Case simulation complete."

echo "Setting up post-processing..."
# Create dummy files for ParaView to easily open the regions
paraFoam -touchAll
echo "Post-processing files created. After running the simulation, open the .OpenFOAM files in ParaView."
echo "To view residual graphs while running, you can use: foamMonitor -l postProcessing/residuals/0/residuals.dat"
""")

write_file("generate_stls.py", """import trimesh
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
""")

write_file("constant/g", """/*--------------------------------*- C++ -*----------------------------------*\\
  =========                 |
  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\\\    /   O peration     | Website:  https://openfoam.org
    \\\\  /    A nd           | Version:  13
     \\\\/     M anipulation  |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       uniformDimensionedVectorField;
    location    "constant";
    object      g;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 1 -2 0 0 0 0];
value           (0 -9.81 0);
""")

write_file("constant/glass/thermophysicalProperties", """/*--------------------------------*- C++ -*----------------------------------*\\
  =========                 |
  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\\\    /   O peration     | Website:  https://openfoam.org
    \\\\  /    A nd           | Version:  13
     \\\\/     M anipulation  |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant/glass";
    object      thermophysicalProperties;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

thermoType
{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       constIsoSolid;
    thermo          eConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleInternalEnergy;
}

mixture
{
    specie
    {
        nMoles          1;
        molWeight       12;
    }
    transport
    {
        kappa           1.14;
    }
    thermodynamics
    {
        Hf              0;
        Cv              750;
    }
    equationOfState
    {
        rho             2230;
    }
}
""")

write_file("constant/glass/radiationProperties", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant/glass";
    object      radiationProperties;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

radiation       on;
radiationModel  opaqueSolid;
emissivity      0.9;
""")

write_file("constant/heater/thermophysicalProperties", """/*--------------------------------*- C++ -*----------------------------------*\\
  =========                 |
  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\\\    /   O peration     | Website:  https://openfoam.org
    \\\\  /    A nd           | Version:  13
     \\\\/     M anipulation  |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant/heater";
    object      thermophysicalProperties;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

thermoType
{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       constIsoSolid;
    thermo          eConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleInternalEnergy;
}

mixture
{
    specie
    {
        nMoles          1;
        molWeight       12;
    }
    transport
    {
        kappa           11;
    }
    thermodynamics
    {
        Hf              0;
        Cv              460;
    }
    equationOfState
    {
        rho             7250;
    }
}
""")

write_file("constant/heater/radiationProperties", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant/heater";
    object      radiationProperties;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

radiation       on;
radiationModel  opaqueSolid;
emissivity      0.7;
""")

write_file("constant/air/thermophysicalProperties", """/*--------------------------------*- C++ -*----------------------------------*\\
  =========                 |
  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\\\    /   O peration     | Website:  https://openfoam.org
    \\\\  /    A nd           | Version:  13
     \\\\/     M anipulation  |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant/air";
    object      thermophysicalProperties;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

thermoType
{
    type            heRhoThermo;
    mixture         pureMixture;
    transport       const;
    thermo          eConst;
    equationOfState perfectGas;
    specie          specie;
    energy          sensibleInternalEnergy;
}

mixture
{
    specie
    {
        nMoles          1;
        molWeight       28.9;
    }
    equationOfState
    {
        Cv              1005;
        Hf              0;
    }
    transport
    {
        mu              1.8e-05;
        Pr              0.7;
    }
}
""")

write_file("constant/air/radiationProperties", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      radiationProperties;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

radiation       on;
radiationModel  fvDOM;

fvDOMCoeffs
{
    nPhi        2;
    nTheta      2;
    tolerance   1e-3;
    maxIter     10;
}
""")

write_file("constant/triSurface/cylinder.stl", """solid
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28 0.0 -0.07410000000000001
vertex -0.28 0.014456192861395102 -0.07267618927787939
vertex -0.28 0.0 -0.07500000000000001
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28 0.0 -0.07500000000000001
vertex -0.28 0.014456192861395102 -0.07267618927787939
vertex -0.28 0.014631774151209618 -0.0735588960302423
endloop
endfacet
facet normal 4.93810394156627e-17 0.09801714032956073 -0.9951847266721969
outer loop
vertex -0.28 0.0 -0.07500000000000001
vertex -0.28 0.014631774151209618 -0.0735588960302423
vertex 0.28 0.0 -0.07499999999999998
endloop
endfacet
facet normal 4.932486595119492e-17 0.09801714032956073 -0.9951847266721969
outer loop
vertex 0.28 0.0 -0.07499999999999998
vertex -0.28 0.014631774151209618 -0.0735588960302423
vertex 0.28 0.014631774151209618 -0.07355889603024227
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.28 0.0 -0.07499999999999998
vertex 0.28 0.014631774151209618 -0.07355889603024227
vertex 0.28 0.0 -0.07409999999999999
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.28 0.0 -0.07409999999999999
vertex 0.28 0.014631774151209618 -0.07355889603024227
vertex 0.28 0.014456192861395102 -0.07267618927787936
endloop
endfacet
facet normal -4.956430238245496e-17 -0.09801714032956069 0.9951847266721968
outer loop
vertex 0.28 0.0 -0.07409999999999999
vertex 0.28 0.014456192861395102 -0.07267618927787936
vertex -0.28 0.0 -0.07410000000000001
endloop
endfacet
facet normal -4.932486595119491e-17 -0.0980171403295607 0.9951847266721968
outer loop
vertex -0.28 0.0 -0.07410000000000001
vertex 0.28 0.014456192861395102 -0.07267618927787936
vertex -0.28 0.014456192861395102 -0.07267618927787939
endloop
endfacet
facet normal -0.9999999999999999 0.0 -0.0
outer loop
vertex -0.28 0.014456192861395102 -0.07267618927787939
vertex -0.28 0.02835684233825315 -0.06845947335908636
vertex -0.28 0.014631774151209618 -0.0735588960302423
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28 0.014631774151209618 -0.0735588960302423
vertex -0.28 0.02835684233825315 -0.06845947335908636
vertex -0.28 0.02870125742738173 -0.06929096493834652
endloop
endfacet
facet normal 4.7735004768473934e-17 0.290284677254462 -0.9569403357322089
outer loop
vertex -0.28 0.014631774151209618 -0.0735588960302423
vertex -0.28 0.02870125742738173 -0.06929096493834652
vertex 0.28 0.014631774151209618 -0.07355889603024227
endloop
endfacet
facet normal 4.742933901439401e-17 0.29028467725446205 -0.9569403357322089
outer loop
vertex 0.28 0.014631774151209618 -0.07355889603024227
vertex -0.28 0.02870125742738173 -0.06929096493834652
vertex 0.28 0.02870125742738173 -0.0692909649383465
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.28 0.014631774151209618 -0.07355889603024227
vertex 0.28 0.02870125742738173 -0.0692909649383465
vertex 0.28 0.014456192861395102 -0.07267618927787936
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.28 0.014456192861395102 -0.07267618927787936
vertex 0.28 0.02870125742738173 -0.0692909649383465
vertex 0.28 0.02835684233825315 -0.06845947335908634
endloop
endfacet
facet normal -4.748176866890642e-17 -0.29028467725446205 0.9569403357322089
outer loop
vertex 0.28 0.014456192861395102 -0.07267618927787936
vertex 0.28 0.02835684233825315 -0.06845947335908634
vertex -0.28 0.014456192861395102 -0.07267618927787939
endloop
endfacet
facet normal -4.7429339014394e-17 -0.29028467725446205 0.9569403357322089
outer loop
vertex -0.28 0.014456192861395102 -0.07267618927787939
vertex 0.28 0.02835684233825315 -0.06845947335908634
vertex -0.28 0.02835684233825315 -0.06845947335908636
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28 0.02835684233825315 -0.06845947335908636
vertex -0.28 0.041167754266752524 -0.061611898271618615
vertex -0.28 0.02870125742738173 -0.06929096493834652
endloop
endfacet
facet normal -0.9999999999999999 0.0 0.0
outer loop
vertex -0.28 0.02870125742738173 -0.06929096493834652
vertex -0.28 0.041167754266752524 -0.061611898271618615
vertex -0.28 0.04166776747647016 -0.062360220922690904
endloop
endfacet
facet normal 4.444293547409642e-17 0.471396736825998 -0.8819212643483549
outer loop
vertex -0.28 0.02870125742738173 -0.06929096493834652
vertex -0.28 0.04166776747647016 -0.062360220922690904
vertex 0.28 0.02870125742738173 -0.0692909649383465
endloop
endfacet
facet normal 4.3711129177949676e-17 0.471396736825998 -0.8819212643483549
outer loop
vertex 0.28 0.02870125742738173 -0.0692909649383465
vertex -0.28 0.04166776747647016 -0.062360220922690904
vertex 0.28 0.04166776747647016 -0.062360220922690876
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.28 0.02870125742738173 -0.0692909649383465
vertex 0.28 0.04166776747647016 -0.062360220922690876
vertex 0.28 0.02835684233825315 -0.06845947335908634
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.28 0.02835684233825315 -0.06845947335908634
vertex 0.28 0.04166776747647016 -0.062360220922690876
vertex 0.28 0.041167754266752524 -0.06161189827161859
endloop
endfacet
facet normal -4.331670124180937e-17 -0.4713967368259978 0.8819212643483549
outer loop
vertex 0.28 0.02835684233825315 -0.06845947335908634
vertex 0.28 0.041167754266752524 -0.06161189827161859
vertex -0.28 0.02835684233825315 -0.06845947335908636
endloop
endfacet
facet normal -4.3711129177949676e-17 -0.4713967368259978 0.8819212643483549
outer loop
vertex -0.28 0.02835684233825315 -0.06845947335908636
vertex 0.28 0.041167754266752524 -0.06161189827161859
vertex -0.28 0.041167754266752524 -0.061611898271618615
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28 0.041167754266752524 -0.061611898271618615
vertex -0.28 0.052396612485923165 -0.052396612485923186
vertex -0.28 0.04166776747647016 -0.062360220922690904
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28 0.04166776747647016 -0.062360220922690904
vertex -0.28 0.052396612485923165 -0.052396612485923186
vertex -0.28 0.05303300858899106 -0.05303300858899108
endloop
endfacet
facet normal 3.785879688534141e-17 0.6343932841636455 -0.773010453362737
outer loop
vertex -0.28 0.04166776747647016 -0.062360220922690904
vertex -0.28 0.05303300858899106 -0.05303300858899108
vertex 0.28 0.04166776747647016 -0.062360220922690876
endloop
endfacet
facet normal 3.8313125160680414e-17 0.6343932841636455 -0.773010453362737
outer loop
vertex 0.28 0.04166776747647016 -0.062360220922690876
vertex -0.28 0.05303300858899106 -0.05303300858899108
vertex 0.28 0.05303300858899106 -0.05303300858899105
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.28 0.04166776747647016 -0.062360220922690876
vertex 0.28 0.05303300858899106 -0.05303300858899105
vertex 0.28 0.041167754266752524 -0.06161189827161859
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.28 0.041167754266752524 -0.06161189827161859
vertex 0.28 0.05303300858899106 -0.05303300858899105
vertex 0.28 0.052396612485923165 -0.05239661248592316
endloop
endfacet
facet normal -3.8318620329292915e-17 -0.6343932841636455 0.7730104533627368
outer loop
vertex 0.28 0.041167754266752524 -0.06161189827161859
vertex 0.28 0.052396612485923165 -0.05239661248592316
vertex -0.28 0.041167754266752524 -0.061611898271618615
endloop
endfacet
facet normal -3.83131251606804e-17 -0.6343932841636455 0.7730104533627368
outer loop
vertex -0.28 0.041167754266752524 -0.061611898271618615
vertex 0.28 0.052396612485923165 -0.05239661248592316
vertex -0.28 0.052396612485923165 -0.052396612485923186
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28 0.052396612485923165 -0.052396612485923186
vertex -0.28 0.0616118982716186 -0.041167754266752545
vertex -0.28 0.05303300858899106 -0.05303300858899108
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28 0.05303300858899106 -0.05303300858899108
vertex -0.28 0.0616118982716186 -0.041167754266752545
vertex -0.28 0.06236022092269089 -0.041667767476470184
endloop
endfacet
facet normal 3.127465829658636e-17 0.7730104533627365 -0.6343932841636457
outer loop
vertex -0.28 0.05303300858899106 -0.05303300858899108
vertex -0.28 0.06236022092269089 -0.041667767476470184
vertex 0.28 0.05303300858899106 -0.05303300858899105
endloop
endfacet
facet normal 3.1442769229734333e-17 0.7730104533627365 -0.6343932841636457
outer loop
vertex 0.28 0.05303300858899106 -0.05303300858899105
vertex -0.28 0.06236022092269089 -0.041667767476470184
vertex 0.28 0.06236022092269089 -0.041667767476470156
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.28 0.05303300858899106 -0.05303300858899105
vertex 0.28 0.06236022092269089 -0.041667767476470156
vertex 0.28 0.052396612485923165 -0.05239661248592316
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.28 0.052396612485923165 -0.05239661248592316
vertex 0.28 0.06236022092269089 -0.041667767476470156
vertex 0.28 0.0616118982716186 -0.04116775426675252
endloop
endfacet
facet normal -3.1654512445937626e-17 -0.7730104533627367 0.6343932841636459
outer loop
vertex 0.28 0.052396612485923165 -0.05239661248592316
vertex 0.28 0.0616118982716186 -0.04116775426675252
vertex -0.28 0.052396612485923165 -0.052396612485923186
endloop
endfacet
facet normal -3.1442769229734345e-17 -0.7730104533627367 0.6343932841636459
outer loop
vertex -0.28 0.052396612485923165 -0.052396612485923186
vertex 0.28 0.0616118982716186 -0.04116775426675252
vertex -0.28 0.0616118982716186 -0.041167754266752545
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28 0.0616118982716186 -0.041167754266752545
vertex -0.28 0.06845947335908635 -0.028356842338253176
vertex -0.28 0.06236022092269089 -0.041667767476470184
endloop
endfacet
facet normal -0.9999999999999999 0.0 0.0
outer loop
vertex -0.28 0.06236022092269089 -0.041667767476470184
vertex -0.28 0.06845947335908635 -0.028356842338253176
vertex -0.28 0.06929096493834651 -0.028701257427381752
endloop
endfacet
facet normal 2.4690519707831345e-17 0.8819212643483549 -0.471396736825998
outer loop
vertex -0.28 0.06236022092269089 -0.041667767476470184
vertex -0.28 0.06929096493834651 -0.028701257427381752
vertex 0.28 0.06236022092269089 -0.041667767476470156
endloop
endfacet
facet normal 2.9205106638247106e-17 0.8819212643483549 -0.47139673682599775
outer loop
vertex 0.28 0.06236022092269089 -0.041667767476470156
vertex -0.28 0.06929096493834651 -0.028701257427381752
vertex 0.28 0.06929096493834651 -0.028701257427381718
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.28 0.06236022092269089 -0.041667767476470156
vertex 0.28 0.06929096493834651 -0.028701257427381718
vertex 0.28 0.0616118982716186 -0.04116775426675252
endloop
endfacet
facet normal 0.9999999999999999 0.0 -0.0
outer loop
vertex 0.28 0.0616118982716186 -0.04116775426675252
vertex 0.28 0.06929096493834651 -0.028701257427381718
vertex 0.28 0.06845947335908635 -0.02835684233825314
endloop
endfacet
facet normal -2.3324377591743506e-17 -0.8819212643483552 0.4713967368259978
outer loop
vertex 0.28 0.0616118982716186 -0.04116775426675252
vertex 0.28 0.06845947335908635 -0.02835684233825314
vertex -0.28 0.0616118982716186 -0.041167754266752545
endloop
endfacet
facet normal -2.920510663824711e-17 -0.8819212643483549 0.4713967368259979
outer loop
vertex -0.28 0.0616118982716186 -0.041167754266752545
vertex 0.28 0.06845947335908635 -0.02835684233825314
vertex -0.28 0.06845947335908635 -0.028356842338253176
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28 0.06845947335908635 -0.028356842338253176
vertex -0.28 0.07267618927787937 -0.014456192861395127
vertex -0.28 0.06929096493834651 -0.028701257427381752
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28 0.06929096493834651 -0.028701257427381752
vertex -0.28 0.07267618927787937 -0.014456192861395127
vertex -0.28 0.07355889603024228 -0.014631774151209642
endloop
endfacet
facet normal 1.8106381119076325e-17 0.9569403357322089 -0.29028467725446205
outer loop
vertex -0.28 0.06929096493834651 -0.028701257427381752
vertex -0.28 0.07355889603024228 -0.014631774151209642
vertex 0.28 0.06929096493834651 -0.028701257427381718
endloop
endfacet
facet normal 1.798441586963093e-17 0.9569403357322089 -0.29028467725446205
outer loop
vertex 0.28 0.06929096493834651 -0.028701257427381718
vertex -0.28 0.07355889603024228 -0.014631774151209642
vertex 0.28 0.07355889603024228 -0.014631774151209608
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.28 0.06929096493834651 -0.028701257427381718
vertex 0.28 0.07355889603024228 -0.014631774151209608
vertex 0.28 0.06845947335908635 -0.02835684233825314
endloop
endfacet
facet normal 0.9999999999999999 0.0 -0.0
outer loop
vertex 0.28 0.06845947335908635 -0.02835684233825314
vertex 0.28 0.07355889603024228 -0.014631774151209608
vertex 0.28 0.07267618927787937 -0.014456192861395092
endloop
endfacet
facet normal -1.832629667922704e-17 -0.9569403357322089 0.29028467725446205
outer loop
vertex 0.28 0.06845947335908635 -0.02835684233825314
vertex 0.28 0.07267618927787937 -0.014456192861395092
vertex -0.28 0.06845947335908635 -0.028356842338253176
endloop
endfacet
facet normal -1.7984415869630927e-17 -0.9569403357322089 0.29028467725446205
outer loop
vertex -0.28 0.06845947335908635 -0.028356842338253176
vertex 0.28 0.07267618927787937 -0.014456192861395092
vertex -0.28 0.07267618927787937 -0.014456192861395127
endloop
endfacet
facet normal -0.9999999999999999 0.0 -0.0
outer loop
vertex -0.28 0.07267618927787937 -0.014456192861395127
vertex -0.28 0.0741 -2.168237157890389e-17
vertex -0.28 0.07355889603024228 -0.014631774151209642
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28 0.07355889603024228 -0.014631774151209642
vertex -0.28 0.0741 -2.168237157890389e-17
vertex -0.28 0.075 -2.173748068486552e-17
endloop
endfacet
facet normal 5.761121265160647e-18 0.9951847266721969 -0.0980171403295607
outer loop
vertex -0.28 0.07355889603024228 -0.014631774151209642
vertex -0.28 0.075 -2.173748068486552e-17
vertex 0.28 0.07355889603024228 -0.014631774151209608
endloop
endfacet
facet normal 6.001818858308673e-18 0.9951847266721969 -0.0980171403295607
outer loop
vertex 0.28 0.07355889603024228 -0.014631774151209608
vertex -0.28 0.075 -2.173748068486552e-17
vertex 0.28 0.075 1.2552629691260372e-17
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.28 0.07355889603024228 -0.014631774151209608
vertex 0.28 0.075 1.2552629691260372e-17
vertex 0.28 0.07267618927787937 -0.014456192861395092
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.28 0.07267618927787937 -0.014456192861395092
vertex 0.28 0.075 1.2552629691260372e-17
vertex 0.28 0.0741 1.2607738797222003e-17
endloop
endfacet
facet normal -6.2476011406455825e-18 -0.9951847266721968 0.09801714032956066
outer loop
vertex 0.28 0.07267618927787937 -0.014456192861395092
vertex 0.28 0.0741 1.2607738797222003e-17
vertex -0.28 0.07267618927787937 -0.014456192861395127
endloop
endfacet
facet normal -6.0018188583086706e-18 -0.9951847266721968 0.09801714032956066
outer loop
vertex -0.28 0.07267618927787937 -0.014456192861395127
vertex 0.28 0.0741 1.2607738797222003e-17
vertex -0.28 0.0741 -2.168237157890389e-17
endloop
endfacet
facet normal -0.9999999999999999 0.0 0.0
outer loop
vertex -0.28 0.0741 -2.168237157890389e-17
vertex -0.28 0.07267618927787937 0.014456192861395082
vertex -0.28 0.075 -2.173748068486552e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28 0.075 -2.173748068486552e-17
vertex -0.28 0.07267618927787937 0.014456192861395082
vertex -0.28 0.07355889603024228 0.014631774151209597
endloop
endfacet
facet normal -5.761121265160647e-18 0.9951847266721969 0.0980171403295607
outer loop
vertex -0.28 0.075 -2.173748068486552e-17
vertex -0.28 0.07355889603024228 0.014631774151209597
vertex 0.28 0.075 1.2552629691260372e-17
endloop
endfacet
facet normal -6.072594084921501e-18 0.9951847266721969 0.0980171403295607
outer loop
vertex 0.28 0.075 1.2552629691260372e-17
vertex -0.28 0.07355889603024228 0.014631774151209597
vertex 0.28 0.07355889603024228 0.014631774151209632
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.28 0.075 1.2552629691260372e-17
vertex 0.28 0.07355889603024228 0.014631774151209632
vertex 0.28 0.0741 1.2607738797222003e-17
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.28 0.0741 1.2607738797222003e-17
vertex 0.28 0.07355889603024228 0.014631774151209632
vertex 0.28 0.07267618927787937 0.014456192861395116
endloop
endfacet
facet normal 5.8310943979358766e-18 -0.9951847266721968 -0.09801714032956066
outer loop
vertex 0.28 0.0741 1.2607738797222003e-17
vertex 0.28 0.07267618927787937 0.014456192861395116
vertex -0.28 0.0741 -2.168237157890389e-17
endloop
endfacet
facet normal 6.072594084921499e-18 -0.9951847266721968 -0.09801714032956069
outer loop
vertex -0.28 0.0741 -2.168237157890389e-17
vertex 0.28 0.07267618927787937 0.014456192861395116
vertex -0.28 0.07267618927787937 0.014456192861395082
endloop
endfacet
facet normal -0.9999999999999999 0.0 0.0
outer loop
vertex -0.28 0.07267618927787937 0.014456192861395082
vertex -0.28 0.06845947335908635 0.02835684233825313
vertex -0.28 0.07355889603024228 0.014631774151209597
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28 0.07355889603024228 0.014631774151209597
vertex -0.28 0.06845947335908635 0.02835684233825313
vertex -0.28 0.06929096493834651 0.02870125742738171
endloop
endfacet
facet normal -1.810638111907632e-17 0.9569403357322089 0.290284677254462
outer loop
vertex -0.28 0.07355889603024228 0.014631774151209597
vertex -0.28 0.06929096493834651 0.02870125742738171
vertex 0.28 0.07355889603024228 0.014631774151209632
endloop
endfacet
facet normal -1.7984415869630923e-17 0.9569403357322089 0.290284677254462
outer loop
vertex 0.28 0.07355889603024228 0.014631774151209632
vertex -0.28 0.06929096493834651 0.02870125742738171
vertex 0.28 0.06929096493834651 0.028701257427381745
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.28 0.07355889603024228 0.014631774151209632
vertex 0.28 0.06929096493834651 0.028701257427381745
vertex 0.28 0.07267618927787937 0.014456192861395116
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.28 0.07267618927787937 0.014456192861395116
vertex 0.28 0.06929096493834651 0.028701257427381745
vertex 0.28 0.06845947335908635 0.028356842338253165
endloop
endfacet
facet normal 1.832629667922704e-17 -0.9569403357322089 -0.29028467725446205
outer loop
vertex 0.28 0.07267618927787937 0.014456192861395116
vertex 0.28 0.06845947335908635 0.028356842338253165
vertex -0.28 0.07267618927787937 0.014456192861395082
endloop
endfacet
facet normal 1.7984415869630927e-17 -0.9569403357322089 -0.29028467725446205
outer loop
vertex -0.28 0.07267618927787937 0.014456192861395082
vertex 0.28 0.06845947335908635 0.028356842338253165
vertex -0.28 0.06845947335908635 0.02835684233825313
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28 0.06845947335908635 0.02835684233825313
vertex -0.28 0.061611898271618615 0.04116775426675249
vertex -0.28 0.06929096493834651 0.02870125742738171
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28 0.06929096493834651 0.02870125742738171
vertex -0.28 0.061611898271618615 0.04116775426675249
vertex -0.28 0.062360220922690904 0.04166776747647013
endloop
endfacet
facet normal -2.798258900220889e-17 0.8819212643483552 0.47139673682599764
outer loop
vertex -0.28 0.06929096493834651 0.02870125742738171
vertex -0.28 0.062360220922690904 0.04166776747647013
vertex 0.28 0.06929096493834651 0.028701257427381745
endloop
endfacet
facet normal -2.3364085310597686e-17 0.881921264348355 0.4713967368259978
outer loop
vertex 0.28 0.06929096493834651 0.028701257427381745
vertex -0.28 0.062360220922690904 0.04166776747647013
vertex 0.28 0.062360220922690904 0.041667767476470156
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.28 0.06929096493834651 0.028701257427381745
vertex 0.28 0.062360220922690904 0.041667767476470156
vertex 0.28 0.06845947335908635 0.028356842338253165
endloop
endfacet
facet normal 0.9999999999999999 0.0 0.0
outer loop
vertex 0.28 0.06845947335908635 0.028356842338253165
vertex 0.28 0.062360220922690904 0.041667767476470156
vertex 0.28 0.061611898271618615 0.04116775426675252
endloop
endfacet
facet normal 2.832245850426002e-17 -0.8819212643483549 -0.4713967368259977
outer loop
vertex 0.28 0.06845947335908635 0.028356842338253165
vertex 0.28 0.061611898271618615 0.04116775426675252
vertex -0.28 0.06845947335908635 0.02835684233825313
endloop
endfacet
facet normal 2.3364085310597668e-17 -0.881921264348355 -0.4713967368259975
outer loop
vertex -0.28 0.06845947335908635 0.02835684233825313
vertex 0.28 0.061611898271618615 0.04116775426675252
vertex -0.28 0.061611898271618615 0.04116775426675249
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28 0.061611898271618615 0.04116775426675249
vertex -0.28 0.05239661248592317 0.05239661248592315
vertex -0.28 0.062360220922690904 0.04166776747647013
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28 0.062360220922690904 0.04166776747647013
vertex -0.28 0.05239661248592317 0.05239661248592315
vertex -0.28 0.053033008588991064 0.05303300858899104
endloop
endfacet
facet normal -3.1274658296586325e-17 0.773010453362737 0.6343932841636454
outer loop
vertex -0.28 0.062360220922690904 0.04166776747647013
vertex -0.28 0.053033008588991064 0.05303300858899104
vertex 0.28 0.062360220922690904 0.041667767476470156
endloop
endfacet
facet normal -3.1442769229734315e-17 0.773010453362737 0.6343932841636454
outer loop
vertex 0.28 0.062360220922690904 0.041667767476470156
vertex -0.28 0.053033008588991064 0.05303300858899104
vertex 0.28 0.053033008588991064 0.05303300858899107
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.28 0.062360220922690904 0.041667767476470156
vertex 0.28 0.053033008588991064 0.05303300858899107
vertex 0.28 0.061611898271618615 0.04116775426675252
endloop
endfacet
facet normal 0.9999999999999999 0.0 0.0
outer loop
vertex 0.28 0.061611898271618615 0.04116775426675252
vertex 0.28 0.053033008588991064 0.05303300858899107
vertex 0.28 0.05239661248592317 0.05239661248592318
endloop
endfacet
facet normal 2.9988485475098756e-17 -0.773010453362737 -0.6343932841636455
outer loop
vertex 0.28 0.061611898271618615 0.04116775426675252
vertex 0.28 0.05239661248592317 0.05239661248592318
vertex -0.28 0.061611898271618615 0.04116775426675249
endloop
endfacet
facet normal 3.144276922973432e-17 -0.773010453362737 -0.6343932841636455
outer loop
vertex -0.28 0.061611898271618615 0.04116775426675249
vertex 0.28 0.05239661248592317 0.05239661248592318
vertex -0.28 0.05239661248592317 0.05239661248592315
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28 0.05239661248592317 0.05239661248592315
vertex -0.28 0.041167754266752524 0.061611898271618594
vertex -0.28 0.053033008588991064 0.05303300858899104
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28 0.053033008588991064 0.05303300858899104
vertex -0.28 0.041167754266752524 0.061611898271618594
vertex -0.28 0.04166776747647016 0.06236022092269088
endloop
endfacet
facet normal -3.785879688534137e-17 0.6343932841636458 0.7730104533627367
outer loop
vertex -0.28 0.053033008588991064 0.05303300858899104
vertex -0.28 0.04166776747647016 0.06236022092269088
vertex 0.28 0.053033008588991064 0.05303300858899107
endloop
endfacet
facet normal -3.83131251606804e-17 0.6343932841636458 0.7730104533627367
outer loop
vertex 0.28 0.053033008588991064 0.05303300858899107
vertex -0.28 0.04166776747647016 0.06236022092269088
vertex 0.28 0.04166776747647016 0.06236022092269091
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.28 0.053033008588991064 0.05303300858899107
vertex 0.28 0.04166776747647016 0.06236022092269091
vertex 0.28 0.05239661248592317 0.05239661248592318
endloop
endfacet
facet normal 0.9999999999999999 0.0 0.0
outer loop
vertex 0.28 0.05239661248592317 0.05239661248592318
vertex 0.28 0.04166776747647016 0.06236022092269091
vertex 0.28 0.041167754266752524 0.06161189827161862
endloop
endfacet
facet normal 3.8318620329292884e-17 -0.6343932841636459 -0.7730104533627367
outer loop
vertex 0.28 0.05239661248592317 0.05239661248592318
vertex 0.28 0.041167754266752524 0.06161189827161862
vertex -0.28 0.05239661248592317 0.05239661248592315
endloop
endfacet
facet normal 3.8313125160680395e-17 -0.6343932841636459 -0.7730104533627367
outer loop
vertex -0.28 0.05239661248592317 0.05239661248592315
vertex 0.28 0.041167754266752524 0.06161189827161862
vertex -0.28 0.041167754266752524 0.061611898271618594
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28 0.041167754266752524 0.061611898271618594
vertex -0.28 0.028356842338253162 0.06845947335908634
vertex -0.28 0.04166776747647016 0.06236022092269088
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28 0.04166776747647016 0.06236022092269088
vertex -0.28 0.028356842338253162 0.06845947335908634
vertex -0.28 0.028701257427381742 0.0692909649383465
endloop
endfacet
facet normal -4.444293547409646e-17 0.47139673682599786 0.8819212643483549
outer loop
vertex -0.28 0.04166776747647016 0.06236022092269088
vertex -0.28 0.028701257427381742 0.0692909649383465
vertex 0.28 0.04166776747647016 0.06236022092269091
endloop
endfacet
facet normal -4.3711129177949676e-17 0.47139673682599786 0.8819212643483549
outer loop
vertex 0.28 0.04166776747647016 0.06236022092269091
vertex -0.28 0.028701257427381742 0.0692909649383465
vertex 0.28 0.028701257427381742 0.06929096493834652
endloop
endfacet
facet normal 0.9999999999999999 0.0 0.0
outer loop
vertex 0.28 0.04166776747647016 0.06236022092269091
vertex 0.28 0.028701257427381742 0.06929096493834652
vertex 0.28 0.041167754266752524 0.06161189827161862
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.28 0.041167754266752524 0.06161189827161862
vertex 0.28 0.028701257427381742 0.06929096493834652
vertex 0.28 0.028356842338253162 0.06845947335908636
endloop
endfacet
facet normal 4.331670124180941e-17 -0.4713967368259977 -0.8819212643483549
outer loop
vertex 0.28 0.041167754266752524 0.06161189827161862
vertex 0.28 0.028356842338253162 0.06845947335908636
vertex -0.28 0.041167754266752524 0.061611898271618594
endloop
endfacet
facet normal 4.3711129177949676e-17 -0.4713967368259977 -0.8819212643483549
outer loop
vertex -0.28 0.041167754266752524 0.061611898271618594
vertex 0.28 0.028356842338253162 0.06845947335908636
vertex -0.28 0.028356842338253162 0.06845947335908634
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28 0.028356842338253162 0.06845947335908634
vertex -0.28 0.01445619286139513 0.07267618927787936
vertex -0.28 0.028701257427381742 0.0692909649383465
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28 0.028701257427381742 0.0692909649383465
vertex -0.28 0.01445619286139513 0.07267618927787936
vertex -0.28 0.014631774151209646 0.07355889603024227
endloop
endfacet
facet normal -4.7735004768473983e-17 0.2902846772544623 0.9569403357322089
outer loop
vertex -0.28 0.028701257427381742 0.0692909649383465
vertex -0.28 0.014631774151209646 0.07355889603024227
vertex 0.28 0.028701257427381742 0.06929096493834652
endloop
endfacet
facet normal -4.7429339014393995e-17 0.29028467725446233 0.9569403357322089
outer loop
vertex 0.28 0.028701257427381742 0.06929096493834652
vertex -0.28 0.014631774151209646 0.07355889603024227
vertex 0.28 0.014631774151209646 0.0735588960302423
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.28 0.028701257427381742 0.06929096493834652
vertex 0.28 0.014631774151209646 0.0735588960302423
vertex 0.28 0.028356842338253162 0.06845947335908636
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.28 0.028356842338253162 0.06845947335908636
vertex 0.28 0.014631774151209646 0.0735588960302423
vertex 0.28 0.01445619286139513 0.07267618927787939
endloop
endfacet
facet normal 4.7481768668906485e-17 -0.29028467725446244 -0.9569403357322088
outer loop
vertex 0.28 0.028356842338253162 0.06845947335908636
vertex 0.28 0.01445619286139513 0.07267618927787939
vertex -0.28 0.028356842338253162 0.06845947335908634
endloop
endfacet
facet normal 4.7429339014394e-17 -0.29028467725446244 -0.9569403357322088
outer loop
vertex -0.28 0.028356842338253162 0.06845947335908634
vertex 0.28 0.01445619286139513 0.07267618927787939
vertex -0.28 0.01445619286139513 0.07267618927787936
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28 0.01445619286139513 0.07267618927787936
vertex -0.28 9.074632781681887e-18 0.07409999999999999
vertex -0.28 0.014631774151209646 0.07355889603024227
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28 0.014631774151209646 0.07355889603024227
vertex -0.28 9.074632781681887e-18 0.07409999999999999
vertex -0.28 9.184850993605149e-18 0.07499999999999998
endloop
endfacet
facet normal -4.938103941566263e-17 0.09801714032956058 0.9951847266721969
outer loop
vertex -0.28 0.014631774151209646 0.07355889603024227
vertex -0.28 9.184850993605149e-18 0.07499999999999998
vertex 0.28 0.014631774151209646 0.0735588960302423
endloop
endfacet
facet normal -4.932486595119491e-17 0.09801714032956058 0.9951847266721969
outer loop
vertex 0.28 0.014631774151209646 0.0735588960302423
vertex -0.28 9.184850993605149e-18 0.07499999999999998
vertex 0.28 9.184850993605149e-18 0.07500000000000001
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.28 0.014631774151209646 0.0735588960302423
vertex 0.28 9.184850993605149e-18 0.07500000000000001
vertex 0.28 0.01445619286139513 0.07267618927787939
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.28 0.01445619286139513 0.07267618927787939
vertex 0.28 9.184850993605149e-18 0.07500000000000001
vertex 0.28 9.074632781681887e-18 0.07410000000000001
endloop
endfacet
facet normal 4.95643023824549e-17 -0.09801714032956056 -0.9951847266721968
outer loop
vertex 0.28 0.01445619286139513 0.07267618927787939
vertex 0.28 9.074632781681887e-18 0.07410000000000001
vertex -0.28 0.01445619286139513 0.07267618927787936
endloop
endfacet
facet normal 4.9324865951194914e-17 -0.09801714032956058 -0.9951847266721968
outer loop
vertex -0.28 0.01445619286139513 0.07267618927787936
vertex 0.28 9.074632781681887e-18 0.07410000000000001
vertex -0.28 9.074632781681887e-18 0.07409999999999999
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28 9.074632781681887e-18 0.07409999999999999
vertex -0.28 -0.014456192861395111 0.07267618927787936
vertex -0.28 9.184850993605149e-18 0.07499999999999998
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28 9.184850993605149e-18 0.07499999999999998
vertex -0.28 -0.014456192861395111 0.07267618927787936
vertex -0.28 -0.014631774151209627 0.07355889603024227
endloop
endfacet
facet normal -4.938103941566264e-17 -0.09801714032956059 0.9951847266721969
outer loop
vertex -0.28 9.184850993605149e-18 0.07499999999999998
vertex -0.28 -0.014631774151209627 0.07355889603024227
vertex 0.28 9.184850993605149e-18 0.07500000000000001
endloop
endfacet
facet normal -4.9324865951194914e-17 -0.0980171403295606 0.9951847266721969
outer loop
vertex 0.28 9.184850993605149e-18 0.07500000000000001
vertex -0.28 -0.014631774151209627 0.07355889603024227
vertex 0.28 -0.014631774151209627 0.0735588960302423
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.28 9.184850993605149e-18 0.07500000000000001
vertex 0.28 -0.014631774151209627 0.0735588960302423
vertex 0.28 9.074632781681887e-18 0.07410000000000001
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.28 9.074632781681887e-18 0.07410000000000001
vertex 0.28 -0.014631774151209627 0.0735588960302423
vertex 0.28 -0.014456192861395111 0.07267618927787939
endloop
endfacet
facet normal 4.95643023824549e-17 0.09801714032956056 -0.9951847266721968
outer loop
vertex 0.28 9.074632781681887e-18 0.07410000000000001
vertex 0.28 -0.014456192861395111 0.07267618927787939
vertex -0.28 9.074632781681887e-18 0.07409999999999999
endloop
endfacet
facet normal 4.932486595119491e-17 0.09801714032956056 -0.9951847266721968
outer loop
vertex -0.28 9.074632781681887e-18 0.07409999999999999
vertex 0.28 -0.014456192861395111 0.07267618927787939
vertex -0.28 -0.014456192861395111 0.07267618927787936
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28 -0.014456192861395111 0.07267618927787936
vertex -0.28 -0.028356842338253144 0.06845947335908634
vertex -0.28 -0.014631774151209627 0.07355889603024227
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28 -0.014631774151209627 0.07355889603024227
vertex -0.28 -0.028356842338253144 0.06845947335908634
vertex -0.28 -0.028701257427381725 0.0692909649383465
endloop
endfacet
facet normal -4.7735004768473983e-17 -0.2902846772544623 0.9569403357322089
outer loop
vertex -0.28 -0.014631774151209627 0.07355889603024227
vertex -0.28 -0.028701257427381725 0.0692909649383465
vertex 0.28 -0.014631774151209627 0.0735588960302423
endloop
endfacet
facet normal -4.7429339014394e-17 -0.2902846772544623 0.9569403357322089
outer loop
vertex 0.28 -0.014631774151209627 0.0735588960302423
vertex -0.28 -0.028701257427381725 0.0692909649383465
vertex 0.28 -0.028701257427381725 0.06929096493834652
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.28 -0.014631774151209627 0.0735588960302423
vertex 0.28 -0.028701257427381725 0.06929096493834652
vertex 0.28 -0.014456192861395111 0.07267618927787939
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.28 -0.014456192861395111 0.07267618927787939
vertex 0.28 -0.028701257427381725 0.06929096493834652
vertex 0.28 -0.028356842338253144 0.06845947335908636
endloop
endfacet
facet normal 4.7481768668906485e-17 0.29028467725446244 -0.9569403357322089
outer loop
vertex 0.28 -0.014456192861395111 0.07267618927787939
vertex 0.28 -0.028356842338253144 0.06845947335908636
vertex -0.28 -0.014456192861395111 0.07267618927787936
endloop
endfacet
facet normal 4.742933901439401e-17 0.29028467725446244 -0.9569403357322089
outer loop
vertex -0.28 -0.014456192861395111 0.07267618927787936
vertex 0.28 -0.028356842338253144 0.06845947335908636
vertex -0.28 -0.028356842338253144 0.06845947335908634
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28 -0.028356842338253144 0.06845947335908634
vertex -0.28 -0.0411677542667525 0.0616118982716186
vertex -0.28 -0.028701257427381725 0.0692909649383465
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28 -0.028701257427381725 0.0692909649383465
vertex -0.28 -0.0411677542667525 0.0616118982716186
vertex -0.28 -0.04166776747647014 0.06236022092269089
endloop
endfacet
facet normal -4.4442935474096476e-17 -0.47139673682599764 0.8819212643483552
outer loop
vertex -0.28 -0.028701257427381725 0.0692909649383465
vertex -0.28 -0.04166776747647014 0.06236022092269089
vertex 0.28 -0.028701257427381725 0.06929096493834652
endloop
endfacet
facet normal -4.371112917794969e-17 -0.47139673682599764 0.8819212643483552
outer loop
vertex 0.28 -0.028701257427381725 0.06929096493834652
vertex -0.28 -0.04166776747647014 0.06236022092269089
vertex 0.28 -0.04166776747647014 0.06236022092269092
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.28 -0.028701257427381725 0.06929096493834652
vertex 0.28 -0.04166776747647014 0.06236022092269092
vertex 0.28 -0.028356842338253144 0.06845947335908636
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.28 -0.028356842338253144 0.06845947335908636
vertex 0.28 -0.04166776747647014 0.06236022092269092
vertex 0.28 -0.0411677542667525 0.06161189827161863
endloop
endfacet
facet normal 4.3316701241809426e-17 0.4713967368259975 -0.881921264348355
outer loop
vertex 0.28 -0.028356842338253144 0.06845947335908636
vertex 0.28 -0.0411677542667525 0.06161189827161863
vertex -0.28 -0.028356842338253144 0.06845947335908634
endloop
endfacet
facet normal 4.371112917794968e-17 0.4713967368259975 -0.881921264348355
outer loop
vertex -0.28 -0.028356842338253144 0.06845947335908634
vertex 0.28 -0.0411677542667525 0.06161189827161863
vertex -0.28 -0.0411677542667525 0.0616118982716186
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28 -0.0411677542667525 0.0616118982716186
vertex -0.28 -0.052396612485923165 0.05239661248592317
vertex -0.28 -0.04166776747647014 0.06236022092269089
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28 -0.04166776747647014 0.06236022092269089
vertex -0.28 -0.052396612485923165 0.05239661248592317
vertex -0.28 -0.05303300858899106 0.053033008588991064
endloop
endfacet
facet normal -3.950483153253012e-17 -0.6343932841636448 0.7730104533627375
outer loop
vertex -0.28 -0.04166776747647014 0.06236022092269089
vertex -0.28 -0.05303300858899106 0.053033008588991064
vertex 0.28 -0.04166776747647014 0.06236022092269092
endloop
endfacet
facet normal -3.831312516068044e-17 -0.6343932841636448 0.7730104533627375
outer loop
vertex 0.28 -0.04166776747647014 0.06236022092269092
vertex -0.28 -0.05303300858899106 0.053033008588991064
vertex 0.28 -0.05303300858899106 0.05303300858899109
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.28 -0.04166776747647014 0.06236022092269092
vertex 0.28 -0.05303300858899106 0.05303300858899109
vertex 0.28 -0.0411677542667525 0.06161189827161863
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.28 -0.0411677542667525 0.06161189827161863
vertex 0.28 -0.05303300858899106 0.05303300858899109
vertex 0.28 -0.052396612485923165 0.0523966124859232
endloop
endfacet
facet normal 3.831862032929288e-17 0.6343932841636448 -0.7730104533627374
outer loop
vertex 0.28 -0.0411677542667525 0.06161189827161863
vertex 0.28 -0.052396612485923165 0.0523966124859232
vertex -0.28 -0.0411677542667525 0.0616118982716186
endloop
endfacet
facet normal 3.831312516068043e-17 0.6343932841636448 -0.7730104533627374
outer loop
vertex -0.28 -0.0411677542667525 0.0616118982716186
vertex 0.28 -0.052396612485923165 0.0523966124859232
vertex -0.28 -0.052396612485923165 0.05239661248592317
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28 -0.052396612485923165 0.05239661248592317
vertex -0.28 -0.0616118982716186 0.04116775426675251
vertex -0.28 -0.05303300858899106 0.053033008588991064
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28 -0.05303300858899106 0.053033008588991064
vertex -0.28 -0.0616118982716186 0.04116775426675251
vertex -0.28 -0.06236022092269089 0.04166776747647015
endloop
endfacet
facet normal -3.127465829658634e-17 -0.7730104533627373 0.6343932841636453
outer loop
vertex -0.28 -0.05303300858899106 0.053033008588991064
vertex -0.28 -0.06236022092269089 0.04166776747647015
vertex 0.28 -0.05303300858899106 0.05303300858899109
endloop
endfacet
facet normal -3.144276922973431e-17 -0.7730104533627373 0.6343932841636453
outer loop
vertex 0.28 -0.05303300858899106 0.05303300858899109
vertex -0.28 -0.06236022092269089 0.04166776747647015
vertex 0.28 -0.06236022092269089 0.04166776747647018
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.28 -0.05303300858899106 0.05303300858899109
vertex 0.28 -0.06236022092269089 0.04166776747647018
vertex 0.28 -0.052396612485923165 0.0523966124859232
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.28 -0.052396612485923165 0.0523966124859232
vertex 0.28 -0.06236022092269089 0.04166776747647018
vertex 0.28 -0.0616118982716186 0.04116775426675254
endloop
endfacet
facet normal 3.165451244593759e-17 0.7730104533627372 -0.6343932841636453
outer loop
vertex 0.28 -0.052396612485923165 0.0523966124859232
vertex 0.28 -0.0616118982716186 0.04116775426675254
vertex -0.28 -0.052396612485923165 0.05239661248592317
endloop
endfacet
facet normal 3.144276922973431e-17 0.7730104533627372 -0.6343932841636453
outer loop
vertex -0.28 -0.052396612485923165 0.05239661248592317
vertex 0.28 -0.0616118982716186 0.04116775426675254
vertex -0.28 -0.0616118982716186 0.04116775426675251
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28 -0.0616118982716186 0.04116775426675251
vertex -0.28 -0.06845947335908634 0.028356842338253176
vertex -0.28 -0.06236022092269089 0.04166776747647015
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28 -0.06236022092269089 0.04166776747647015
vertex -0.28 -0.06845947335908634 0.028356842338253176
vertex -0.28 -0.06929096493834648 0.028701257427381756
endloop
endfacet
facet normal -2.3044485060642663e-17 -0.881921264348355 0.4713967368259976
outer loop
vertex -0.28 -0.06236022092269089 0.04166776747647015
vertex -0.28 -0.06929096493834648 0.028701257427381756
vertex 0.28 -0.06236022092269089 0.04166776747647018
endloop
endfacet
facet normal -2.92051066382471e-17 -0.8819212643483549 0.47139673682599775
outer loop
vertex 0.28 -0.06236022092269089 0.04166776747647018
vertex -0.28 -0.06929096493834648 0.028701257427381756
vertex 0.28 -0.06929096493834648 0.02870125742738179
endloop
endfacet
facet normal 0.9999999999999999 -0.0 0.0
outer loop
vertex 0.28 -0.06236022092269089 0.04166776747647018
vertex 0.28 -0.06929096493834648 0.02870125742738179
vertex 0.28 -0.0616118982716186 0.04116775426675254
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.28 -0.0616118982716186 0.04116775426675254
vertex 0.28 -0.06929096493834648 0.02870125742738179
vertex 0.28 -0.06845947335908634 0.02835684233825321
endloop
endfacet
facet normal 2.332437759174358e-17 0.8819212643483546 -0.47139673682599836
outer loop
vertex 0.28 -0.0616118982716186 0.04116775426675254
vertex 0.28 -0.06845947335908634 0.02835684233825321
vertex -0.28 -0.0616118982716186 0.04116775426675251
endloop
endfacet
facet normal 2.920510663824713e-17 0.8819212643483547 -0.4713967368259982
outer loop
vertex -0.28 -0.0616118982716186 0.04116775426675251
vertex 0.28 -0.06845947335908634 0.02835684233825321
vertex -0.28 -0.06845947335908634 0.028356842338253176
endloop
endfacet
facet normal -0.9999999999999999 -0.0 0.0
outer loop
vertex -0.28 -0.06845947335908634 0.028356842338253176
vertex -0.28 -0.07267618927787936 0.014456192861395116
vertex -0.28 -0.06929096493834648 0.028701257427381756
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28 -0.06929096493834648 0.028701257427381756
vertex -0.28 -0.07267618927787936 0.014456192861395116
vertex -0.28 -0.07355889603024227 0.014631774151209632
endloop
endfacet
facet normal -1.81063811190763e-17 -0.9569403357322088 0.2902846772544626
outer loop
vertex -0.28 -0.06929096493834648 0.028701257427381756
vertex -0.28 -0.07355889603024227 0.014631774151209632
vertex 0.28 -0.06929096493834648 0.02870125742738179
endloop
endfacet
facet normal -1.7984415869630964e-17 -0.9569403357322088 0.2902846772544626
outer loop
vertex 0.28 -0.06929096493834648 0.02870125742738179
vertex -0.28 -0.07355889603024227 0.014631774151209632
vertex 0.28 -0.07355889603024227 0.014631774151209666
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.28 -0.06929096493834648 0.02870125742738179
vertex 0.28 -0.07355889603024227 0.014631774151209666
vertex 0.28 -0.06845947335908634 0.02835684233825321
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.28 -0.06845947335908634 0.02835684233825321
vertex 0.28 -0.07355889603024227 0.014631774151209666
vertex 0.28 -0.07267618927787936 0.014456192861395151
endloop
endfacet
facet normal 1.8326296679227032e-17 0.9569403357322092 -0.29028467725446194
outer loop
vertex 0.28 -0.06845947335908634 0.02835684233825321
vertex 0.28 -0.07267618927787936 0.014456192861395151
vertex -0.28 -0.06845947335908634 0.028356842338253176
endloop
endfacet
facet normal 1.798441586963092e-17 0.9569403357322092 -0.29028467725446194
outer loop
vertex -0.28 -0.06845947335908634 0.028356842338253176
vertex 0.28 -0.07267618927787936 0.014456192861395151
vertex -0.28 -0.07267618927787936 0.014456192861395116
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28 -0.07267618927787936 0.014456192861395116
vertex -0.28 -0.0741 -3.533106015540117e-18
vertex -0.28 -0.07355889603024227 0.014631774151209632
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28 -0.07355889603024227 0.014631774151209632
vertex -0.28 -0.0741 -3.533106015540117e-18
vertex -0.28 -0.075 -3.3677786976552243e-18
endloop
endfacet
facet normal -6.1726299269578286e-18 -0.9951847266721967 0.09801714032956152
outer loop
vertex -0.28 -0.07355889603024227 0.014631774151209632
vertex -0.28 -0.075 -3.3677786976552243e-18
vertex 0.28 -0.07355889603024227 0.014631774151209666
endloop
endfacet
facet normal -6.001818858308723e-18 -0.9951847266721967 0.09801714032956152
outer loop
vertex 0.28 -0.07355889603024227 0.014631774151209666
vertex -0.28 -0.075 -3.3677786976552243e-18
vertex 0.28 -0.075 3.092233167847067e-17
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.28 -0.07355889603024227 0.014631774151209666
vertex 0.28 -0.075 3.092233167847067e-17
vertex 0.28 -0.07267618927787936 0.014456192861395151
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.28 -0.07267618927787936 0.014456192861395151
vertex 0.28 -0.075 3.092233167847067e-17
vertex 0.28 -0.0741 3.0757004360585776e-17
endloop
endfacet
facet normal 6.2476011406455756e-18 0.9951847266721968 -0.09801714032956152
outer loop
vertex 0.28 -0.07267618927787936 0.014456192861395151
vertex 0.28 -0.0741 3.0757004360585776e-17
vertex -0.28 -0.07267618927787936 0.014456192861395116
endloop
endfacet
facet normal 6.001818858308723e-18 0.9951847266721968 -0.09801714032956153
outer loop
vertex -0.28 -0.07267618927787936 0.014456192861395116
vertex 0.28 -0.0741 3.0757004360585776e-17
vertex -0.28 -0.0741 -3.533106015540117e-18
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.28 -0.0741 -3.533106015540117e-18
vertex -0.28 -0.07267618927787937 -0.014456192861395125
vertex -0.28 -0.075 -3.3677786976552243e-18
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28 -0.075 -3.3677786976552243e-18
vertex -0.28 -0.07267618927787937 -0.014456192861395125
vertex -0.28 -0.07355889603024228 -0.014631774151209639
endloop
endfacet
facet normal 6.17262992695783e-18 -0.9951847266721969 -0.09801714032956059
outer loop
vertex -0.28 -0.075 -3.3677786976552243e-18
vertex -0.28 -0.07355889603024228 -0.014631774151209639
vertex 0.28 -0.075 3.092233167847067e-17
endloop
endfacet
facet normal 6.072594084921494e-18 -0.9951847266721969 -0.09801714032956059
outer loop
vertex 0.28 -0.075 3.092233167847067e-17
vertex -0.28 -0.07355889603024228 -0.014631774151209639
vertex 0.28 -0.07355889603024228 -0.014631774151209604
endloop
endfacet
facet normal 1.0 -0.0 -0.0
outer loop
vertex 0.28 -0.075 3.092233167847067e-17
vertex 0.28 -0.07355889603024228 -0.014631774151209604
vertex 0.28 -0.0741 3.0757004360585776e-17
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.28 -0.0741 3.0757004360585776e-17
vertex 0.28 -0.07355889603024228 -0.014631774151209604
vertex 0.28 -0.07267618927787937 -0.01445619286139509
endloop
endfacet
facet normal -5.8310943979358704e-18 0.9951847266721968 0.09801714032956056
outer loop
vertex 0.28 -0.0741 3.0757004360585776e-17
vertex 0.28 -0.07267618927787937 -0.01445619286139509
vertex -0.28 -0.0741 -3.533106015540117e-18
endloop
endfacet
facet normal -6.0725940849214914e-18 0.9951847266721968 0.09801714032956056
outer loop
vertex -0.28 -0.0741 -3.533106015540117e-18
vertex 0.28 -0.07267618927787937 -0.01445619286139509
vertex -0.28 -0.07267618927787937 -0.014456192861395125
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.28 -0.07267618927787937 -0.014456192861395125
vertex -0.28 -0.06845947335908634 -0.028356842338253186
vertex -0.28 -0.07355889603024228 -0.014631774151209639
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28 -0.07355889603024228 -0.014631774151209639
vertex -0.28 -0.06845947335908634 -0.028356842338253186
vertex -0.28 -0.0692909649383465 -0.028701257427381766
endloop
endfacet
facet normal 1.8106381119076297e-17 -0.9569403357322088 -0.29028467725446255
outer loop
vertex -0.28 -0.07355889603024228 -0.014631774151209639
vertex -0.28 -0.0692909649383465 -0.028701257427381766
vertex 0.28 -0.07355889603024228 -0.014631774151209604
endloop
endfacet
facet normal 1.798441586963096e-17 -0.9569403357322088 -0.29028467725446255
outer loop
vertex 0.28 -0.07355889603024228 -0.014631774151209604
vertex -0.28 -0.0692909649383465 -0.028701257427381766
vertex 0.28 -0.0692909649383465 -0.02870125742738173
endloop
endfacet
facet normal 1.0 -0.0 -0.0
outer loop
vertex 0.28 -0.07355889603024228 -0.014631774151209604
vertex 0.28 -0.0692909649383465 -0.02870125742738173
vertex 0.28 -0.07267618927787937 -0.01445619286139509
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.28 -0.07267618927787937 -0.01445619286139509
vertex 0.28 -0.0692909649383465 -0.02870125742738173
vertex 0.28 -0.06845947335908634 -0.02835684233825315
endloop
endfacet
facet normal -1.7493283193807615e-17 0.9569403357322087 0.2902846772544628
outer loop
vertex 0.28 -0.07267618927787937 -0.01445619286139509
vertex 0.28 -0.06845947335908634 -0.02835684233825315
vertex -0.28 -0.07267618927787937 -0.014456192861395125
endloop
endfacet
facet normal -1.798441586963097e-17 0.9569403357322087 0.2902846772544628
outer loop
vertex -0.28 -0.07267618927787937 -0.014456192861395125
vertex 0.28 -0.06845947335908634 -0.02835684233825315
vertex -0.28 -0.06845947335908634 -0.028356842338253186
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.28 -0.06845947335908634 -0.028356842338253186
vertex -0.28 -0.061611898271618615 -0.04116775426675251
vertex -0.28 -0.0692909649383465 -0.028701257427381766
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28 -0.0692909649383465 -0.028701257427381766
vertex -0.28 -0.061611898271618615 -0.04116775426675251
vertex -0.28 -0.062360220922690904 -0.04166776747647015
endloop
endfacet
facet normal 2.9628623649397717e-17 -0.8819212643483548 -0.47139673682599775
outer loop
vertex -0.28 -0.0692909649383465 -0.028701257427381766
vertex -0.28 -0.062360220922690904 -0.04166776747647015
vertex 0.28 -0.0692909649383465 -0.02870125742738173
endloop
endfacet
facet normal 2.336408531059768e-17 -0.881921264348355 -0.4713967368259977
outer loop
vertex 0.28 -0.0692909649383465 -0.02870125742738173
vertex -0.28 -0.062360220922690904 -0.04166776747647015
vertex 0.28 -0.062360220922690904 -0.04166776747647012
endloop
endfacet
facet normal 1.0 -0.0 -0.0
outer loop
vertex 0.28 -0.0692909649383465 -0.02870125742738173
vertex 0.28 -0.062360220922690904 -0.04166776747647012
vertex 0.28 -0.06845947335908634 -0.02835684233825315
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.28 -0.06845947335908634 -0.02835684233825315
vertex 0.28 -0.062360220922690904 -0.04166776747647012
vertex 0.28 -0.061611898271618615 -0.04116775426675248
endloop
endfacet
facet normal -2.832245850426007e-17 0.881921264348355 0.47139673682599753
outer loop
vertex 0.28 -0.06845947335908634 -0.02835684233825315
vertex 0.28 -0.061611898271618615 -0.04116775426675248
vertex -0.28 -0.06845947335908634 -0.028356842338253186
endloop
endfacet
facet normal -2.336408531059768e-17 0.8819212643483549 0.47139673682599775
outer loop
vertex -0.28 -0.06845947335908634 -0.028356842338253186
vertex 0.28 -0.061611898271618615 -0.04116775426675248
vertex -0.28 -0.061611898271618615 -0.04116775426675251
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.28 -0.061611898271618615 -0.04116775426675251
vertex -0.28 -0.052396612485923186 -0.05239661248592317
vertex -0.28 -0.062360220922690904 -0.04166776747647015
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28 -0.062360220922690904 -0.04166776747647015
vertex -0.28 -0.052396612485923186 -0.05239661248592317
vertex -0.28 -0.05303300858899108 -0.053033008588991064
endloop
endfacet
facet normal 3.1274658296586344e-17 -0.7730104533627375 -0.6343932841636448
outer loop
vertex -0.28 -0.062360220922690904 -0.04166776747647015
vertex -0.28 -0.05303300858899108 -0.053033008588991064
vertex 0.28 -0.062360220922690904 -0.04166776747647012
endloop
endfacet
facet normal 3.144276922973429e-17 -0.7730104533627375 -0.6343932841636448
outer loop
vertex 0.28 -0.062360220922690904 -0.04166776747647012
vertex -0.28 -0.05303300858899108 -0.053033008588991064
vertex 0.28 -0.05303300858899108 -0.053033008588991036
endloop
endfacet
facet normal 1.0 -0.0 -0.0
outer loop
vertex 0.28 -0.062360220922690904 -0.04166776747647012
vertex 0.28 -0.05303300858899108 -0.053033008588991036
vertex 0.28 -0.061611898271618615 -0.04116775426675248
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.28 -0.061611898271618615 -0.04116775426675248
vertex 0.28 -0.05303300858899108 -0.053033008588991036
vertex 0.28 -0.052396612485923186 -0.052396612485923144
endloop
endfacet
facet normal -3.1654512445937595e-17 0.7730104533627374 0.6343932841636448
outer loop
vertex 0.28 -0.061611898271618615 -0.04116775426675248
vertex 0.28 -0.052396612485923186 -0.052396612485923144
vertex -0.28 -0.061611898271618615 -0.04116775426675251
endloop
endfacet
facet normal -3.1442769229734296e-17 0.7730104533627374 0.6343932841636448
outer loop
vertex -0.28 -0.061611898271618615 -0.04116775426675251
vertex 0.28 -0.052396612485923186 -0.052396612485923144
vertex -0.28 -0.052396612485923186 -0.05239661248592317
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.28 -0.052396612485923186 -0.05239661248592317
vertex -0.28 -0.041167754266752524 -0.061611898271618615
vertex -0.28 -0.05303300858899108 -0.053033008588991064
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28 -0.05303300858899108 -0.053033008588991064
vertex -0.28 -0.041167754266752524 -0.061611898271618615
vertex -0.28 -0.04166776747647016 -0.062360220922690904
endloop
endfacet
facet normal 3.785879688534134e-17 -0.6343932841636454 -0.773010453362737
outer loop
vertex -0.28 -0.05303300858899108 -0.053033008588991064
vertex -0.28 -0.04166776747647016 -0.062360220922690904
vertex 0.28 -0.05303300858899108 -0.053033008588991036
endloop
endfacet
facet normal 3.8313125160680414e-17 -0.6343932841636454 -0.773010453362737
outer loop
vertex 0.28 -0.05303300858899108 -0.053033008588991036
vertex -0.28 -0.04166776747647016 -0.062360220922690904
vertex 0.28 -0.04166776747647016 -0.062360220922690876
endloop
endfacet
facet normal 1.0 -0.0 -0.0
outer loop
vertex 0.28 -0.05303300858899108 -0.053033008588991036
vertex 0.28 -0.04166776747647016 -0.062360220922690876
vertex 0.28 -0.052396612485923186 -0.052396612485923144
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.28 -0.052396612485923186 -0.052396612485923144
vertex 0.28 -0.04166776747647016 -0.062360220922690876
vertex 0.28 -0.041167754266752524 -0.06161189827161859
endloop
endfacet
facet normal -3.8318620329292853e-17 0.6343932841636455 0.773010453362737
outer loop
vertex 0.28 -0.052396612485923186 -0.052396612485923144
vertex 0.28 -0.041167754266752524 -0.06161189827161859
vertex -0.28 -0.052396612485923186 -0.05239661248592317
endloop
endfacet
facet normal -3.8313125160680414e-17 0.6343932841636455 0.773010453362737
outer loop
vertex -0.28 -0.052396612485923186 -0.05239661248592317
vertex 0.28 -0.041167754266752524 -0.06161189827161859
vertex -0.28 -0.041167754266752524 -0.061611898271618615
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.28 -0.041167754266752524 -0.061611898271618615
vertex -0.28 -0.028356842338253196 -0.06845947335908635
vertex -0.28 -0.04166776747647016 -0.062360220922690904
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28 -0.04166776747647016 -0.062360220922690904
vertex -0.28 -0.028356842338253196 -0.06845947335908635
vertex -0.28 -0.028701257427381777 -0.0692909649383465
endloop
endfacet
facet normal 4.4442935474096575e-17 -0.47139673682599775 -0.8819212643483549
outer loop
vertex -0.28 -0.04166776747647016 -0.062360220922690904
vertex -0.28 -0.028701257427381777 -0.0692909649383465
vertex 0.28 -0.04166776747647016 -0.062360220922690876
endloop
endfacet
facet normal 4.3711129177949676e-17 -0.47139673682599775 -0.8819212643483549
outer loop
vertex 0.28 -0.04166776747647016 -0.062360220922690876
vertex -0.28 -0.028701257427381777 -0.0692909649383465
vertex 0.28 -0.028701257427381777 -0.06929096493834647
endloop
endfacet
facet normal 0.9999999999999999 -0.0 -0.0
outer loop
vertex 0.28 -0.04166776747647016 -0.062360220922690876
vertex 0.28 -0.028701257427381777 -0.06929096493834647
vertex 0.28 -0.041167754266752524 -0.06161189827161859
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.28 -0.041167754266752524 -0.06161189827161859
vertex 0.28 -0.028701257427381777 -0.06929096493834647
vertex 0.28 -0.028356842338253196 -0.06845947335908632
endloop
endfacet
facet normal -4.4982728212648334e-17 0.47139673682599836 0.8819212643483546
outer loop
vertex 0.28 -0.041167754266752524 -0.06161189827161859
vertex 0.28 -0.028356842338253196 -0.06845947335908632
vertex -0.28 -0.041167754266752524 -0.061611898271618615
endloop
endfacet
facet normal -4.371112917794966e-17 0.47139673682599836 0.8819212643483546
outer loop
vertex -0.28 -0.041167754266752524 -0.061611898271618615
vertex 0.28 -0.028356842338253196 -0.06845947335908632
vertex -0.28 -0.028356842338253196 -0.06845947335908635
endloop
endfacet
facet normal -0.9999999999999999 -0.0 -0.0
outer loop
vertex -0.28 -0.028356842338253196 -0.06845947335908635
vertex -0.28 -0.014456192861395137 -0.07267618927787937
vertex -0.28 -0.028701257427381777 -0.0692909649383465
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28 -0.028701257427381777 -0.0692909649383465
vertex -0.28 -0.014456192861395137 -0.07267618927787937
vertex -0.28 -0.014631774151209653 -0.07355889603024228
endloop
endfacet
facet normal 4.7735004768473885e-17 -0.2902846772544626 -0.9569403357322088
outer loop
vertex -0.28 -0.028701257427381777 -0.0692909649383465
vertex -0.28 -0.014631774151209653 -0.07355889603024228
vertex 0.28 -0.028701257427381777 -0.06929096493834647
endloop
endfacet
facet normal 4.742933901439399e-17 -0.2902846772544626 -0.9569403357322088
outer loop
vertex 0.28 -0.028701257427381777 -0.06929096493834647
vertex -0.28 -0.014631774151209653 -0.07355889603024228
vertex 0.28 -0.014631774151209653 -0.07355889603024225
endloop
endfacet
facet normal 1.0 -0.0 -0.0
outer loop
vertex 0.28 -0.028701257427381777 -0.06929096493834647
vertex 0.28 -0.014631774151209653 -0.07355889603024225
vertex 0.28 -0.028356842338253196 -0.06845947335908632
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.28 -0.028356842338253196 -0.06845947335908632
vertex 0.28 -0.014631774151209653 -0.07355889603024225
vertex 0.28 -0.014456192861395137 -0.07267618927787935
endloop
endfacet
facet normal -4.7481768668906404e-17 0.29028467725446194 0.9569403357322092
outer loop
vertex 0.28 -0.028356842338253196 -0.06845947335908632
vertex 0.28 -0.014456192861395137 -0.07267618927787935
vertex -0.28 -0.028356842338253196 -0.06845947335908635
endloop
endfacet
facet normal -4.7429339014394014e-17 0.29028467725446194 0.9569403357322092
outer loop
vertex -0.28 -0.028356842338253196 -0.06845947335908635
vertex 0.28 -0.014456192861395137 -0.07267618927787935
vertex -0.28 -0.014456192861395137 -0.07267618927787937
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.28 -0.014456192861395137 -0.07267618927787937
vertex -0.28 0.0 -0.07410000000000001
vertex -0.28 -0.014631774151209653 -0.07355889603024228
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28 -0.014631774151209653 -0.07355889603024228
vertex -0.28 0.0 -0.07410000000000001
vertex -0.28 0.0 -0.07500000000000001
endloop
endfacet
facet normal 4.9381039415662573e-17 -0.09801714032956142 -0.9951847266721969
outer loop
vertex -0.28 -0.014631774151209653 -0.07355889603024228
vertex -0.28 0.0 -0.07500000000000001
vertex 0.28 -0.014631774151209653 -0.07355889603024225
endloop
endfacet
facet normal 4.932486595119491e-17 -0.09801714032956142 -0.9951847266721969
outer loop
vertex 0.28 -0.014631774151209653 -0.07355889603024225
vertex -0.28 0.0 -0.07500000000000001
vertex 0.28 0.0 -0.07499999999999998
endloop
endfacet
facet normal 1.0 -0.0 -0.0
outer loop
vertex 0.28 -0.014631774151209653 -0.07355889603024225
vertex 0.28 0.0 -0.07499999999999998
vertex 0.28 -0.014456192861395137 -0.07267618927787935
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.28 -0.014456192861395137 -0.07267618927787935
vertex 0.28 0.0 -0.07499999999999998
vertex 0.28 0.0 -0.07409999999999999
endloop
endfacet
facet normal -4.914779563974514e-17 0.09801714032956141 0.9951847266721968
outer loop
vertex 0.28 -0.014456192861395137 -0.07267618927787935
vertex 0.28 0.0 -0.07409999999999999
vertex -0.28 -0.014456192861395137 -0.07267618927787937
endloop
endfacet
facet normal -4.932486595119491e-17 0.09801714032956141 0.9951847266721968
outer loop
vertex -0.28 -0.014456192861395137 -0.07267618927787937
vertex 0.28 0.0 -0.07409999999999999
vertex -0.28 0.0 -0.07410000000000001
endloop
endfacet

endsolid
""")

write_file("constant/triSurface/heater.stl", """solid
facet normal -1.0 0.0 0.0
outer loop
vertex -0.3 0.0 -0.0037384977086385
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.00023474221338455788 -0.0037311206373890717
endloop
endfacet
facet normal 6.068628891616964e-17 0.03141075907812757 -0.9995065603657315
outer loop
vertex -0.3 0.0 -0.0037384977086385
vertex -0.3 0.00023474221338455788 -0.0037311206373890717
vertex 0.3 0.0 -0.0037384977086384634
endloop
endfacet
facet normal 6.068536231307425e-17 0.03141075907812757 -0.9995065603657315
outer loop
vertex 0.3 0.0 -0.0037384977086384634
vertex -0.3 0.00023474221338455788 -0.0037311206373890717
vertex 0.3 0.00023474221338455788 -0.0037311206373890353
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.3 0.0 -0.0037384977086384634
vertex 0.3 0.00023474221338455788 -0.0037311206373890353
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -0.9999999999999999 0.0 0.0
outer loop
vertex -0.3 0.00023474221338455788 -0.0037311206373890717
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0004685580064964031 -0.0037090185375707454
endloop
endfacet
facet normal 6.044414837809094e-17 0.0941083133185138 -0.9955619646030801
outer loop
vertex -0.3 0.00023474221338455788 -0.0037311206373890717
vertex -0.3 0.0004685580064964031 -0.0037090185375707454
vertex 0.3 0.00023474221338455788 -0.0037311206373890353
endloop
endfacet
facet normal 6.044586491252938e-17 0.0941083133185138 -0.9955619646030801
outer loop
vertex 0.3 0.00023474221338455788 -0.0037311206373890353
vertex -0.3 0.0004685580064964031 -0.0037090185375707454
vertex 0.3 0.0004685580064964031 -0.003709018537570709
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.3 0.00023474221338455788 -0.0037311206373890353
vertex 0.3 0.0004685580064964031 -0.003709018537570709
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -0.9999999999999999 0.0 0.0
outer loop
vertex -0.3 0.0004685580064964031 -0.0037090185375707454
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.000700524615220398 -0.003672278636074015
endloop
endfacet
facet normal 5.996867241240918e-17 0.15643446504023079 -0.9876883405951378
outer loop
vertex -0.3 0.0004685580064964031 -0.0037090185375707454
vertex -0.3 0.000700524615220398 -0.003672278636074015
vertex 0.3 0.0004685580064964031 -0.003709018537570709
endloop
endfacet
facet normal 5.996781529826368e-17 0.15643446504023076 -0.9876883405951378
outer loop
vertex 0.3 0.0004685580064964031 -0.003709018537570709
vertex -0.3 0.000700524615220398 -0.003672278636074015
vertex 0.3 0.000700524615220398 -0.0036722786360739784
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.3 0.0004685580064964031 -0.003709018537570709
vertex 0.3 0.000700524615220398 -0.0036722786360739784
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -0.9999999999999999 0.0 0.0
outer loop
vertex -0.3 0.000700524615220398 -0.003672278636074015
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0009297265733273722 -0.0036210459285052226
endloop
endfacet
facet normal 5.925252342706123e-17 0.21814324139654473 -0.9759167619387469
outer loop
vertex -0.3 0.000700524615220398 -0.003672278636074015
vertex -0.3 0.0009297265733273722 -0.0036210459285052226
vertex 0.3 0.000700524615220398 -0.0036722786360739784
endloop
endfacet
facet normal 5.925310011370446e-17 0.21814324139654476 -0.9759167619387469
outer loop
vertex 0.3 0.000700524615220398 -0.0036722786360739784
vertex -0.3 0.0009297265733273722 -0.0036210459285052226
vertex 0.3 0.0009297265733273722 -0.003621045928505186
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.3 0.000700524615220398 -0.0036722786360739784
vertex 0.3 0.0009297265733273722 -0.003621045928505186
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.3 0.0009297265733273722 -0.0036210459285052226
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0011552593254010913 -0.0035555226069551465
endloop
endfacet
facet normal 5.831331164299855e-17 0.2789911060392288 -0.9602936856769432
outer loop
vertex -0.3 0.0009297265733273722 -0.0036210459285052226
vertex -0.3 0.0011552593254010913 -0.0035555226069551465
vertex 0.3 0.0009297265733273722 -0.003621045928505186
endloop
endfacet
facet normal 5.830454001316302e-17 0.27899110603922883 -0.9602936856769432
outer loop
vertex 0.3 0.0009297265733273722 -0.003621045928505186
vertex -0.3 0.0011552593254010913 -0.0035555226069551465
vertex 0.3 0.0011552593254010913 -0.00355552260695511
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.3 0.0009297265733273722 -0.003621045928505186
vertex 0.3 0.0011552593254010913 -0.00355552260695511
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.3 0.0011552593254010913 -0.0035555226069551465
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0013762327967052346 -0.0034759672620391854
endloop
endfacet
facet normal 5.712755676561917e-17 0.3387379202452915 -0.9408807689542256
outer loop
vertex -0.3 0.0011552593254010913 -0.0035555226069551465
vertex -0.3 0.0013762327967052346 -0.0034759672620391854
vertex 0.3 0.0011552593254010913 -0.00355552260695511
endloop
endfacet
facet normal 5.712587853000018e-17 0.3387379202452915 -0.9408807689542256
outer loop
vertex 0.3 0.0011552593254010913 -0.00355552260695511
vertex -0.3 0.0013762327967052346 -0.0034759672620391854
vertex 0.3 0.0013762327967052346 -0.003475967262039149
endloop
endfacet
facet normal 0.9999999999999999 0.0 -0.0
outer loop
vertex 0.3 0.0011552593254010913 -0.00355552260695511
vertex 0.3 0.0013762327967052346 -0.003475967262039149
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.3 0.0013762327967052346 -0.0034759672620391854
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0015917749059017404 -0.003382693862358343
endloop
endfacet
facet normal 5.571873908952497e-17 0.3971478906347805 -0.9177546256839811
outer loop
vertex -0.3 0.0013762327967052346 -0.0034759672620391854
vertex -0.3 0.0015917749059017404 -0.003382693862358343
vertex 0.3 0.0013762327967052346 -0.003475967262039149
endloop
endfacet
facet normal 5.572176730261083e-17 0.3971478906347805 -0.9177546256839811
outer loop
vertex 0.3 0.0013762327967052346 -0.003475967262039149
vertex -0.3 0.0015917749059017404 -0.003382693862358343
vertex 0.3 0.0015917749059017404 -0.0033826938623583067
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.3 0.0013762327967052346 -0.003475967262039149
vertex 0.3 0.0015917749059017404 -0.0033826938623583067
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.3 0.0015917749059017404 -0.003382693862358343
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0018010350067574326 -0.003276070515408597
endloop
endfacet
facet normal 5.409859876201674e-17 0.4539904997395463 -0.891006524188368
outer loop
vertex -0.3 0.0015917749059017404 -0.003382693862358343
vertex -0.3 0.0018010350067574326 -0.003276070515408597
vertex 0.3 0.0015917749059017404 -0.0033826938623583067
endloop
endfacet
facet normal 5.4097747716532056e-17 0.45399049973954636 -0.891006524188368
outer loop
vertex 0.3 0.0015917749059017404 -0.0033826938623583067
vertex -0.3 0.0018010350067574326 -0.003276070515408597
vertex 0.3 0.0018010350067574326 -0.0032760705154085607
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.3 0.0015917749059017404 -0.0033826938623583067
vertex 0.3 0.0018010350067574326 -0.0032760705154085607
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.3 0.0018010350067574326 -0.003276070515408597
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0020031872452560807 -0.003156518014828784
endloop
endfacet
facet normal 5.224365548849269e-17 0.5090414157503709 -0.8607420270039438
outer loop
vertex -0.3 0.0018010350067574326 -0.003276070515408597
vertex -0.3 0.0020031872452560807 -0.003156518014828784
vertex 0.3 0.0018010350067574326 -0.0032760705154085607
endloop
endfacet
facet normal 5.226022903512615e-17 0.509041415750371 -0.8607420270039438
outer loop
vertex 0.3 0.0018010350067574326 -0.0032760705154085607
vertex -0.3 0.0020031872452560807 -0.003156518014828784
vertex 0.3 0.0020031872452560807 -0.0031565180148287477
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.3 0.0018010350067574326 -0.0032760705154085607
vertex 0.3 0.0020031872452560807 -0.0031565180148287477
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.3 0.0020031872452560807 -0.003156518014828784
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0021974338188669026 -0.0030245081797203506
endloop
endfacet
facet normal 5.022435015275778e-17 0.562083377852131 -0.8270805742745615
outer loop
vertex -0.3 0.0020031872452560807 -0.003156518014828784
vertex -0.3 0.0021974338188669026 -0.0030245081797203506
vertex 0.3 0.0020031872452560807 -0.0031565180148287477
endloop
endfacet
facet normal 5.021646310514615e-17 0.562083377852131 -0.8270805742745615
outer loop
vertex 0.3 0.0020031872452560807 -0.0031565180148287477
vertex -0.3 0.0021974338188669026 -0.0030245081797203506
vertex 0.3 0.0021974338188669026 -0.003024508179720314
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.3 0.0020031872452560807 -0.0031565180148287477
vertex 0.3 0.0021974338188669026 -0.003024508179720314
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.3 0.0021974338188669026 -0.0030245081797203506
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0023830081251066757 -0.002880561992592912
endloop
endfacet
facet normal 4.7993722165608524e-17 0.6129070536529766 -0.7901550123756904
outer loop
vertex -0.3 0.0021974338188669026 -0.0030245081797203506
vertex -0.3 0.0023830081251066757 -0.002880561992592912
vertex 0.3 0.0021974338188669026 -0.003024508179720314
endloop
endfacet
facet normal 4.7974515737009916e-17 0.6129070536529766 -0.7901550123756904
outer loop
vertex 0.3 0.0021974338188669026 -0.003024508179720314
vertex -0.3 0.0023830081251066757 -0.002880561992592912
vertex 0.3 0.0023830081251066757 -0.0028805619925928757
endloop
endfacet
facet normal 0.9999999999999999 0.0 -0.0
outer loop
vertex 0.3 0.0021974338188669026 -0.003024508179720314
vertex 0.3 0.0023830081251066757 -0.0028805619925928757
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.3 0.0023830081251066757 -0.002880561992592912
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0025591777869695066 -0.0027252475432843043
endloop
endfacet
facet normal 4.5528291232443823e-17 0.6613118653236514 -0.7501110696304599
outer loop
vertex -0.3 0.0023830081251066757 -0.002880561992592912
vertex -0.3 0.0025591777869695066 -0.0027252475432843043
vertex 0.3 0.0023830081251066757 -0.0028805619925928757
endloop
endfacet
facet normal 4.554323487273113e-17 0.6613118653236515 -0.7501110696304599
outer loop
vertex 0.3 0.0023830081251066757 -0.0028805619925928757
vertex -0.3 0.0025591777869695066 -0.0027252475432843043
vertex 0.3 0.0025591777869695066 -0.002725247543284268
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.3 0.0023830081251066757 -0.0028805619925928757
vertex 0.3 0.0025591777869695066 -0.002725247543284268
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.3 0.0025591777869695066 -0.0027252475432843043
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.002725247543284286 -0.0025591777869695244
endloop
endfacet
facet normal 4.2945458826271015e-17 0.7071067811865485 -0.7071067811865466
outer loop
vertex -0.3 0.0025591777869695066 -0.0027252475432843043
vertex -0.3 0.002725247543284286 -0.0025591777869695244
vertex 0.3 0.0025591777869695066 -0.002725247543284268
endloop
endfacet
facet normal 4.293221566713442e-17 0.7071067811865485 -0.7071067811865466
outer loop
vertex 0.3 0.0025591777869695066 -0.002725247543284268
vertex -0.3 0.002725247543284286 -0.0025591777869695244
vertex 0.3 0.002725247543284286 -0.002559177786969488
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.3 0.0025591777869695066 -0.002725247543284268
vertex 0.3 0.002725247543284286 -0.002559177786969488
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.3 0.002725247543284286 -0.0025591777869695244
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0028805619925928944 -0.0023830081251066935
endloop
endfacet
facet normal 4.0151303768684284e-17 0.7501110696304589 -0.6613118653236524
outer loop
vertex -0.3 0.002725247543284286 -0.0025591777869695244
vertex -0.3 0.0028805619925928944 -0.0023830081251066935
vertex 0.3 0.002725247543284286 -0.002559177786969488
endloop
endfacet
facet normal 4.0151762620163336e-17 0.7501110696304589 -0.6613118653236524
outer loop
vertex 0.3 0.002725247543284286 -0.002559177786969488
vertex -0.3 0.0028805619925928944 -0.0023830081251066935
vertex 0.3 0.0028805619925928944 -0.002383008125106657
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.3 0.002725247543284286 -0.002559177786969488
vertex 0.3 0.0028805619925928944 -0.002383008125106657
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.3 0.0028805619925928944 -0.0023830081251066935
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0030245081797203323 -0.0021974338188669204
endloop
endfacet
facet normal 3.721626694348806e-17 0.7901550123756913 -0.6129070536529755
outer loop
vertex -0.3 0.0028805619925928944 -0.0023830081251066935
vertex -0.3 0.0030245081797203323 -0.0021974338188669204
vertex 0.3 0.0028805619925928944 -0.002383008125106657
endloop
endfacet
facet normal 3.7212848909725755e-17 0.7901550123756913 -0.6129070536529755
outer loop
vertex 0.3 0.0028805619925928944 -0.002383008125106657
vertex -0.3 0.0030245081797203323 -0.0021974338188669204
vertex 0.3 0.0030245081797203323 -0.002197433818866884
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.3 0.0028805619925928944 -0.002383008125106657
vertex 0.3 0.0030245081797203323 -0.002197433818866884
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.3 0.0030245081797203323 -0.0021974338188669204
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.003156518014828766 -0.0020031872452560984
endloop
endfacet
facet normal 3.414034835068248e-17 0.8270805742745615 -0.562083377852131
outer loop
vertex -0.3 0.0030245081797203323 -0.0021974338188669204
vertex -0.3 0.003156518014828766 -0.0020031872452560984
vertex 0.3 0.0030245081797203323 -0.002197433818866884
endloop
endfacet
facet normal 3.412707308557518e-17 0.8270805742745615 -0.562083377852131
outer loop
vertex 0.3 0.0030245081797203323 -0.002197433818866884
vertex -0.3 0.003156518014828766 -0.0020031872452560984
vertex 0.3 0.003156518014828766 -0.002003187245256062
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.3 0.0030245081797203323 -0.002197433818866884
vertex 0.3 0.003156518014828766 -0.002003187245256062
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -0.9999999999999999 0.0 0.0
outer loop
vertex -0.3 0.003156518014828766 -0.0020031872452560984
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0032760705154085794 -0.0018010350067574504
endloop
endfacet
facet normal 3.092354799026733e-17 0.860742027003943 -0.5090414157503723
outer loop
vertex -0.3 0.003156518014828766 -0.0020031872452560984
vertex -0.3 0.0032760705154085794 -0.0018010350067574504
vertex 0.3 0.003156518014828766 -0.002003187245256062
endloop
endfacet
facet normal 3.127454916769348e-17 0.8607420270039435 -0.5090414157503715
outer loop
vertex 0.3 0.003156518014828766 -0.002003187245256062
vertex -0.3 0.0032760705154085794 -0.0018010350067574504
vertex 0.3 0.0032760705154085794 -0.0018010350067574135
endloop
endfacet
facet normal 0.9999999999999999 0.0 -0.0
outer loop
vertex 0.3 0.003156518014828766 -0.002003187245256062
vertex 0.3 0.0032760705154085794 -0.0018010350067574135
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.3 0.0032760705154085794 -0.0018010350067574504
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0033826938623583254 -0.0015917749059017586
endloop
endfacet
facet normal 2.789458998666493e-17 0.8910065241883677 -0.4539904997395471
outer loop
vertex -0.3 0.0032760705154085794 -0.0018010350067574504
vertex -0.3 0.0033826938623583254 -0.0015917749059017586
vertex 0.3 0.0032760705154085794 -0.0018010350067574135
endloop
endfacet
facet normal 2.789232421263916e-17 0.8910065241883677 -0.4539904997395471
outer loop
vertex 0.3 0.0032760705154085794 -0.0018010350067574135
vertex -0.3 0.0033826938623583254 -0.0015917749059017586
vertex 0.3 0.0033826938623583254 -0.0015917749059017217
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.3 0.0032760705154085794 -0.0018010350067574135
vertex 0.3 0.0033826938623583254 -0.0015917749059017217
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -0.9999999999999999 0.0 0.0
outer loop
vertex -0.3 0.0033826938623583254 -0.0015917749059017586
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0034759672620391677 -0.0013762327967052526
endloop
endfacet
facet normal 2.4396026091030932e-17 0.9177546256839815 -0.3971478906347802
outer loop
vertex -0.3 0.0033826938623583254 -0.0015917749059017586
vertex -0.3 0.0034759672620391677 -0.0013762327967052526
vertex 0.3 0.0033826938623583254 -0.0015917749059017217
endloop
endfacet
facet normal 2.4400020996708302e-17 0.9177546256839815 -0.3971478906347802
outer loop
vertex 0.3 0.0033826938623583254 -0.0015917749059017217
vertex -0.3 0.0034759672620391677 -0.0013762327967052526
vertex 0.3 0.0034759672620391677 -0.0013762327967052157
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.3 0.0033826938623583254 -0.0015917749059017217
vertex 0.3 0.0034759672620391677 -0.0013762327967052157
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.3 0.0034759672620391677 -0.0013762327967052526
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0035555226069551283 -0.00115525932540111
endloop
endfacet
facet normal 2.0803541016990852e-17 0.9408807689542257 -0.3387379202452907
outer loop
vertex -0.3 0.0034759672620391677 -0.0013762327967052526
vertex -0.3 0.0035555226069551283 -0.00115525932540111
vertex 0.3 0.0034759672620391677 -0.0013762327967052157
endloop
endfacet
facet normal 2.0811422045212723e-17 0.9408807689542257 -0.3387379202452907
outer loop
vertex 0.3 0.0034759672620391677 -0.0013762327967052157
vertex -0.3 0.0035555226069551283 -0.00115525932540111
vertex 0.3 0.0035555226069551283 -0.0011552593254010731
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.3 0.0034759672620391677 -0.0013762327967052157
vertex 0.3 0.0035555226069551283 -0.0011552593254010731
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.3 0.0035555226069551283 -0.00115525932540111
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0036210459285052044 -0.0009297265733273903
endloop
endfacet
facet normal 1.7140615059145903e-17 0.9602936856769434 -0.27899110603922816
outer loop
vertex -0.3 0.0035555226069551283 -0.00115525932540111
vertex -0.3 0.0036210459285052044 -0.0009297265733273903
vertex 0.3 0.0035555226069551283 -0.0011552593254010731
endloop
endfacet
facet normal 1.7039862330981743e-17 0.9602936856769435 -0.27899110603922844
outer loop
vertex 0.3 0.0035555226069551283 -0.0011552593254010731
vertex -0.3 0.0036210459285052044 -0.0009297265733273903
vertex 0.3 0.0036210459285052044 -0.0009297265733273537
endloop
endfacet
facet normal 0.9999999999999999 0.0 -0.0
outer loop
vertex 0.3 0.0035555226069551283 -0.0011552593254010731
vertex 0.3 0.0036210459285052044 -0.0009297265733273537
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.3 0.0036210459285052044 -0.0009297265733273903
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0036722786360739966 -0.000700524615220416
endloop
endfacet
facet normal 1.332506718639082e-17 0.9759167619387471 -0.21814324139654462
outer loop
vertex -0.3 0.0036210459285052044 -0.0009297265733273903
vertex -0.3 0.0036722786360739966 -0.000700524615220416
vertex 0.3 0.0036210459285052044 -0.0009297265733273537
endloop
endfacet
facet normal 1.332347419458088e-17 0.9759167619387469 -0.21814324139654462
outer loop
vertex 0.3 0.0036210459285052044 -0.0009297265733273537
vertex -0.3 0.0036722786360739966 -0.000700524615220416
vertex 0.3 0.0036722786360739966 -0.0007005246152203793
endloop
endfacet
facet normal 0.9999999999999999 0.0 -0.0
outer loop
vertex 0.3 0.0036210459285052044 -0.0009297265733273537
vertex 0.3 0.0036722786360739966 -0.0007005246152203793
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -0.9999999999999999 0.0 0.0
outer loop
vertex -0.3 0.0036722786360739966 -0.000700524615220416
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.003709018537570727 -0.00046855800649642145
endloop
endfacet
facet normal 9.55647990283891e-18 0.9876883405951375 -0.15643446504023104
outer loop
vertex -0.3 0.0036722786360739966 -0.000700524615220416
vertex -0.3 0.003709018537570727 -0.00046855800649642145
vertex 0.3 0.0036722786360739966 -0.0007005246152203793
endloop
endfacet
facet normal 9.582772156924774e-18 0.9876883405951377 -0.15643446504023095
outer loop
vertex 0.3 0.0036722786360739966 -0.0007005246152203793
vertex -0.3 0.003709018537570727 -0.00046855800649642145
vertex 0.3 0.003709018537570727 -0.0004685580064963847
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.3 0.0036722786360739966 -0.0007005246152203793
vertex 0.3 0.003709018537570727 -0.0004685580064963847
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.3 0.003709018537570727 -0.00046855800649642145
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0037311206373890535 -0.00023474221338457598
endloop
endfacet
facet normal 5.7702823983357605e-18 0.9955619646030801 -0.09410831331851369
outer loop
vertex -0.3 0.003709018537570727 -0.00046855800649642145
vertex -0.3 0.0037311206373890535 -0.00023474221338457598
vertex 0.3 0.003709018537570727 -0.0004685580064963847
endloop
endfacet
facet normal 5.764832732811668e-18 0.9955619646030801 -0.09410831331851369
outer loop
vertex 0.3 0.003709018537570727 -0.0004685580064963847
vertex -0.3 0.0037311206373890535 -0.00023474221338457598
vertex 0.3 0.0037311206373890535 -0.00023474221338453923
endloop
endfacet
facet normal 0.9999999999999999 0.0 -0.0
outer loop
vertex 0.3 0.003709018537570727 -0.0004685580064963847
vertex 0.3 0.0037311206373890535 -0.00023474221338453923
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.3 0.0037311206373890535 -0.00023474221338457598
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0037384977086384816 -1.7768505703107723e-17
endloop
endfacet
facet normal 1.9239166389161196e-18 0.9995065603657316 -0.03141075907812753
outer loop
vertex -0.3 0.0037311206373890535 -0.00023474221338457598
vertex -0.3 0.0037384977086384816 -1.7768505703107723e-17
vertex 0.3 0.0037311206373890535 -0.00023474221338453923
endloop
endfacet
facet normal 1.923354278190877e-18 0.9995065603657316 -0.03141075907812753
outer loop
vertex 0.3 0.0037311206373890535 -0.00023474221338453923
vertex -0.3 0.0037384977086384816 -1.7768505703107723e-17
vertex 0.3 0.0037384977086384816 1.8970898271312872e-17
endloop
endfacet
facet normal 0.9999999999999999 0.0 -0.0
outer loop
vertex 0.3 0.0037311206373890535 -0.00023474221338453923
vertex 0.3 0.0037384977086384816 1.8970898271312872e-17
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.3 0.0037384977086384816 -1.7768505703107723e-17
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0037311206373890535 0.0002347422133845396
endloop
endfacet
facet normal -1.923916638916126e-18 0.9995065603657316 0.03141075907812763
outer loop
vertex -0.3 0.0037384977086384816 -1.7768505703107723e-17
vertex -0.3 0.0037311206373890535 0.0002347422133845396
vertex 0.3 0.0037384977086384816 1.8970898271312872e-17
endloop
endfacet
facet normal -1.9241421476037485e-18 0.9995065603657315 0.031410759078127626
outer loop
vertex 0.3 0.0037384977086384816 1.8970898271312872e-17
vertex -0.3 0.0037311206373890535 0.0002347422133845396
vertex 0.3 0.0037311206373890535 0.00023474221338457636
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 0.0037384977086384816 1.8970898271312872e-17
vertex 0.3 0.0037311206373890535 0.00023474221338457636
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.3 0.0037311206373890535 0.0002347422133845396
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0037090185375707268 0.00046855800649638513
endloop
endfacet
facet normal -5.770282398335758e-18 0.9955619646030799 0.0941083133185155
outer loop
vertex -0.3 0.0037311206373890535 0.0002347422133845396
vertex -0.3 0.0037090185375707268 0.00046855800649638513
vertex 0.3 0.0037311206373890535 0.00023474221338457636
endloop
endfacet
facet normal -5.764832732811779e-18 0.9955619646030799 0.0941083133185155
outer loop
vertex 0.3 0.0037311206373890535 0.00023474221338457636
vertex -0.3 0.0037090185375707268 0.00046855800649638513
vertex 0.3 0.0037090185375707268 0.0004685580064964219
endloop
endfacet
facet normal 0.9999999999999999 0.0 0.0
outer loop
vertex 0.3 0.0037311206373890535 0.00023474221338457636
vertex 0.3 0.0037090185375707268 0.0004685580064964219
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -0.9999999999999999 -0.0 0.0
outer loop
vertex -0.3 0.0037090185375707268 0.00046855800649638513
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.003672278636073996 0.0007005246152203804
endloop
endfacet
facet normal -9.57996019744045e-18 0.9876883405951378 0.15643446504023056
outer loop
vertex -0.3 0.0037090185375707268 0.00046855800649638513
vertex -0.3 0.003672278636073996 0.0007005246152203804
vertex 0.3 0.0037090185375707268 0.0004685580064964219
endloop
endfacet
facet normal -9.554504392450049e-18 0.9876883405951378 0.15643446504023062
outer loop
vertex 0.3 0.0037090185375707268 0.0004685580064964219
vertex -0.3 0.003672278636073996 0.0007005246152203804
vertex 0.3 0.003672278636073996 0.000700524615220417
endloop
endfacet
facet normal 0.9999999999999999 0.0 0.0
outer loop
vertex 0.3 0.0037090185375707268 0.0004685580064964219
vertex 0.3 0.003672278636073996 0.000700524615220417
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.3 0.003672278636073996 0.0007005246152203804
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0036210459285052044 0.0009297265733273541
endloop
endfacet
facet normal -1.3325067186390861e-17 0.9759167619387472 0.21814324139654348
outer loop
vertex -0.3 0.003672278636073996 0.0007005246152203804
vertex -0.3 0.0036210459285052044 0.0009297265733273541
vertex 0.3 0.003672278636073996 0.000700524615220417
endloop
endfacet
facet normal -1.3323474194580807e-17 0.9759167619387472 0.21814324139654348
outer loop
vertex 0.3 0.003672278636073996 0.000700524615220417
vertex -0.3 0.0036210459285052044 0.0009297265733273541
vertex 0.3 0.0036210459285052044 0.0009297265733273907
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 0.003672278636073996 0.000700524615220417
vertex 0.3 0.0036210459285052044 0.0009297265733273907
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.3 0.0036210459285052044 0.0009297265733273541
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0035555226069551283 0.0011552593254010736
endloop
endfacet
facet normal -1.7046693880739642e-17 0.9602936856769435 0.27899110603922844
outer loop
vertex -0.3 0.0036210459285052044 0.0009297265733273541
vertex -0.3 0.0035555226069551283 0.0011552593254010736
vertex 0.3 0.0036210459285052044 0.0009297265733273907
endloop
endfacet
facet normal -1.7140689918739015e-17 0.9602936856769434 0.27899110603922816
outer loop
vertex 0.3 0.0036210459285052044 0.0009297265733273907
vertex -0.3 0.0035555226069551283 0.0011552593254010736
vertex 0.3 0.0035555226069551283 0.0011552593254011104
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 0.0036210459285052044 0.0009297265733273907
vertex 0.3 0.0035555226069551283 0.0011552593254011104
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.3 0.0035555226069551283 0.0011552593254010736
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0034759672620391672 0.0013762327967052161
endloop
endfacet
facet normal -2.0803541016990842e-17 0.9408807689542252 0.33873792024529237
outer loop
vertex -0.3 0.0035555226069551283 0.0011552593254010736
vertex -0.3 0.0034759672620391672 0.0013762327967052161
vertex 0.3 0.0035555226069551283 0.0011552593254011104
endloop
endfacet
facet normal -2.0811422045212825e-17 0.9408807689542252 0.33873792024529237
outer loop
vertex 0.3 0.0035555226069551283 0.0011552593254011104
vertex -0.3 0.0034759672620391672 0.0013762327967052161
vertex 0.3 0.0034759672620391672 0.001376232796705253
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 0.0035555226069551283 0.0011552593254011104
vertex 0.3 0.0034759672620391672 0.001376232796705253
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.3 0.0034759672620391672 0.0013762327967052161
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.003382693862358325 0.001591774905901722
endloop
endfacet
facet normal -2.439602609103095e-17 0.9177546256839811 0.3971478906347805
outer loop
vertex -0.3 0.0034759672620391672 0.0013762327967052161
vertex -0.3 0.003382693862358325 0.001591774905901722
vertex 0.3 0.0034759672620391672 0.001376232796705253
endloop
endfacet
facet normal -2.440002099670832e-17 0.9177546256839811 0.3971478906347805
outer loop
vertex 0.3 0.0034759672620391672 0.001376232796705253
vertex -0.3 0.003382693862358325 0.001591774905901722
vertex 0.3 0.003382693862358325 0.0015917749059017588
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 0.0034759672620391672 0.001376232796705253
vertex 0.3 0.003382693862358325 0.0015917749059017588
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -0.9999999999999999 -0.0 0.0
outer loop
vertex -0.3 0.003382693862358325 0.001591774905901722
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0032760705154085785 0.0018010350067574146
endloop
endfacet
facet normal -2.789458998666482e-17 0.8910065241883677 0.45399049973954714
outer loop
vertex -0.3 0.003382693862358325 0.001591774905901722
vertex -0.3 0.0032760705154085785 0.0018010350067574146
vertex 0.3 0.003382693862358325 0.0015917749059017588
endloop
endfacet
facet normal -2.789232421263916e-17 0.8910065241883677 0.45399049973954714
outer loop
vertex 0.3 0.003382693862358325 0.0015917749059017588
vertex -0.3 0.0032760705154085785 0.0018010350067574146
vertex 0.3 0.0032760705154085785 0.0018010350067574515
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 0.003382693862358325 0.0015917749059017588
vertex 0.3 0.0032760705154085785 0.0018010350067574515
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.3 0.0032760705154085785 0.0018010350067574146
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0031565180148287655 0.002003187245256063
endloop
endfacet
facet normal -3.127575240929088e-17 0.8607420270039441 0.5090414157503704
outer loop
vertex -0.3 0.0032760705154085785 0.0018010350067574146
vertex -0.3 0.0031565180148287655 0.002003187245256063
vertex 0.3 0.0032760705154085785 0.0018010350067574515
endloop
endfacet
facet normal -3.090661329513237e-17 0.8607420270039435 0.5090414157503713
outer loop
vertex 0.3 0.0032760705154085785 0.0018010350067574515
vertex -0.3 0.0031565180148287655 0.002003187245256063
vertex 0.3 0.0031565180148287655 0.0020031872452560993
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 0.0032760705154085785 0.0018010350067574515
vertex 0.3 0.0031565180148287655 0.0020031872452560993
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.3 0.0031565180148287655 0.002003187245256063
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0030245081797203323 0.002197433818866884
endloop
endfacet
facet normal -3.411686805608105e-17 0.8270805742745614 0.5620833778521315
outer loop
vertex -0.3 0.0031565180148287655 0.002003187245256063
vertex -0.3 0.0030245081797203323 0.002197433818866884
vertex 0.3 0.0031565180148287655 0.0020031872452560993
endloop
endfacet
facet normal -3.412707308557521e-17 0.8270805742745614 0.5620833778521315
outer loop
vertex 0.3 0.0031565180148287655 0.0020031872452560993
vertex -0.3 0.0030245081797203323 0.002197433818866884
vertex 0.3 0.0030245081797203323 0.0021974338188669204
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 0.0031565180148287655 0.0020031872452560993
vertex 0.3 0.0030245081797203323 0.0021974338188669204
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.3 0.0030245081797203323 0.002197433818866884
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0028805619925928944 0.0023830081251066575
endloop
endfacet
facet normal -3.7216266943488e-17 0.7901550123756919 0.6129070536529745
outer loop
vertex -0.3 0.0030245081797203323 0.002197433818866884
vertex -0.3 0.0028805619925928944 0.0023830081251066575
vertex 0.3 0.0030245081797203323 0.0021974338188669204
endloop
endfacet
facet normal -3.7212848909725694e-17 0.7901550123756919 0.6129070536529745
outer loop
vertex 0.3 0.0030245081797203323 0.0021974338188669204
vertex -0.3 0.0028805619925928944 0.0023830081251066575
vertex 0.3 0.0028805619925928944 0.002383008125106694
endloop
endfacet
facet normal 0.9999999999999999 0.0 0.0
outer loop
vertex 0.3 0.0030245081797203323 0.0021974338188669204
vertex 0.3 0.0028805619925928944 0.002383008125106694
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.3 0.0028805619925928944 0.0023830081251066575
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0027252475432842857 0.0025591777869694884
endloop
endfacet
facet normal -4.015130376868424e-17 0.750111069630458 0.6613118653236535
outer loop
vertex -0.3 0.0028805619925928944 0.0023830081251066575
vertex -0.3 0.0027252475432842857 0.0025591777869694884
vertex 0.3 0.0028805619925928944 0.002383008125106694
endloop
endfacet
facet normal -4.01517626201634e-17 0.750111069630458 0.6613118653236535
outer loop
vertex 0.3 0.0028805619925928944 0.002383008125106694
vertex -0.3 0.0027252475432842857 0.0025591777869694884
vertex 0.3 0.0027252475432842857 0.002559177786969525
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 0.0028805619925928944 0.002383008125106694
vertex 0.3 0.0027252475432842857 0.002559177786969525
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -0.9999999999999999 -0.0 0.0
outer loop
vertex -0.3 0.0027252475432842857 0.0025591777869694884
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0025591777869695058 0.0027252475432842684
endloop
endfacet
facet normal -4.2945458826270966e-17 0.7071067811865476 0.7071067811865476
outer loop
vertex -0.3 0.0027252475432842857 0.0025591777869694884
vertex -0.3 0.0025591777869695058 0.0027252475432842684
vertex 0.3 0.0027252475432842857 0.002559177786969525
endloop
endfacet
facet normal -4.293221566713448e-17 0.7071067811865476 0.7071067811865476
outer loop
vertex 0.3 0.0027252475432842857 0.002559177786969525
vertex -0.3 0.0025591777869695058 0.0027252475432842684
vertex 0.3 0.0025591777869695058 0.0027252475432843048
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 0.0027252475432842857 0.002559177786969525
vertex 0.3 0.0025591777869695058 0.0027252475432843048
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.3 0.0025591777869695058 0.0027252475432842684
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.002383008125106675 0.002880561992592876
endloop
endfacet
facet normal -4.5528291232443823e-17 0.6613118653236514 0.7501110696304599
outer loop
vertex -0.3 0.0025591777869695058 0.0027252475432842684
vertex -0.3 0.002383008125106675 0.002880561992592876
vertex 0.3 0.0025591777869695058 0.0027252475432843048
endloop
endfacet
facet normal -4.554323487273113e-17 0.6613118653236515 0.7501110696304599
outer loop
vertex 0.3 0.0025591777869695058 0.0027252475432843048
vertex -0.3 0.002383008125106675 0.002880561992592876
vertex 0.3 0.002383008125106675 0.0028805619925929126
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 0.0025591777869695058 0.0027252475432843048
vertex 0.3 0.002383008125106675 0.0028805619925929126
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.3 0.002383008125106675 0.002880561992592876
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.002197433818866903 0.0030245081797203137
endloop
endfacet
facet normal -4.797024187100727e-17 0.6129070536529769 0.7901550123756901
outer loop
vertex -0.3 0.002383008125106675 0.002880561992592876
vertex -0.3 0.002197433818866903 0.0030245081797203137
vertex 0.3 0.002383008125106675 0.0028805619925929126
endloop
endfacet
facet normal -4.797451573700989e-17 0.6129070536529769 0.79015501237569
outer loop
vertex 0.3 0.002383008125106675 0.0028805619925929126
vertex -0.3 0.002197433818866903 0.0030245081797203137
vertex 0.3 0.002197433818866903 0.00302450817972035
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 0.002383008125106675 0.0028805619925929126
vertex 0.3 0.002197433818866903 0.00302450817972035
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.3 0.002197433818866903 0.0030245081797203137
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0020031872452560807 0.0031565180148287477
endloop
endfacet
facet normal -5.0200869858156084e-17 0.5620833778521314 0.8270805742745613
outer loop
vertex -0.3 0.002197433818866903 0.0030245081797203137
vertex -0.3 0.0020031872452560807 0.0031565180148287477
vertex 0.3 0.002197433818866903 0.00302450817972035
endloop
endfacet
facet normal -5.021646310514612e-17 0.5620833778521314 0.8270805742745613
outer loop
vertex 0.3 0.002197433818866903 0.00302450817972035
vertex -0.3 0.0020031872452560807 0.0031565180148287477
vertex 0.3 0.0020031872452560807 0.003156518014828784
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 0.002197433818866903 0.00302450817972035
vertex 0.3 0.0020031872452560807 0.003156518014828784
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.3 0.0020031872452560807 0.0031565180148287477
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0018010350067574322 0.0032760705154085607
endloop
endfacet
facet normal -5.226713578309418e-17 0.5090414157503701 0.8607420270039443
outer loop
vertex -0.3 0.0020031872452560807 0.0031565180148287477
vertex -0.3 0.0018010350067574322 0.0032760705154085607
vertex 0.3 0.0020031872452560807 0.003156518014828784
endloop
endfacet
facet normal -5.226022903512618e-17 0.5090414157503702 0.8607420270039443
outer loop
vertex 0.3 0.0020031872452560807 0.003156518014828784
vertex -0.3 0.0018010350067574322 0.0032760705154085607
vertex 0.3 0.0018010350067574322 0.003276070515408597
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 0.0020031872452560807 0.003156518014828784
vertex 0.3 0.0018010350067574322 0.003276070515408597
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.3 0.0018010350067574322 0.0032760705154085607
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0015917749059017395 0.003382693862358307
endloop
endfacet
facet normal -5.409859876201662e-17 0.45399049973954714 0.8910065241883677
outer loop
vertex -0.3 0.0018010350067574322 0.0032760705154085607
vertex -0.3 0.0015917749059017395 0.003382693862358307
vertex 0.3 0.0018010350067574322 0.003276070515408597
endloop
endfacet
facet normal -5.409774771653205e-17 0.45399049973954714 0.8910065241883677
outer loop
vertex 0.3 0.0018010350067574322 0.003276070515408597
vertex -0.3 0.0015917749059017395 0.003382693862358307
vertex 0.3 0.0015917749059017395 0.0033826938623583436
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 0.0018010350067574322 0.003276070515408597
vertex 0.3 0.0015917749059017395 0.0033826938623583436
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.3 0.0015917749059017395 0.003382693862358307
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0013762327967052337 0.0034759672620391494
endloop
endfacet
facet normal -5.571873908952497e-17 0.3971478906347805 0.9177546256839811
outer loop
vertex -0.3 0.0015917749059017395 0.003382693862358307
vertex -0.3 0.0013762327967052337 0.0034759672620391494
vertex 0.3 0.0015917749059017395 0.0033826938623583436
endloop
endfacet
facet normal -5.572176730261083e-17 0.3971478906347805 0.9177546256839811
outer loop
vertex 0.3 0.0015917749059017395 0.0033826938623583436
vertex -0.3 0.0013762327967052337 0.0034759672620391494
vertex 0.3 0.0013762327967052337 0.003475967262039186
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 0.0015917749059017395 0.0033826938623583436
vertex 0.3 0.0013762327967052337 0.003475967262039186
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -0.9999999999999999 -0.0 0.0
outer loop
vertex -0.3 0.0013762327967052337 0.0034759672620391494
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0011552593254010902 0.0035555226069551105
endloop
endfacet
facet normal -5.712755676561912e-17 0.3387379202452912 0.9408807689542257
outer loop
vertex -0.3 0.0013762327967052337 0.0034759672620391494
vertex -0.3 0.0011552593254010902 0.0035555226069551105
vertex 0.3 0.0013762327967052337 0.003475967262039186
endloop
endfacet
facet normal -5.71258785300002e-17 0.3387379202452912 0.9408807689542257
outer loop
vertex 0.3 0.0013762327967052337 0.003475967262039186
vertex -0.3 0.0011552593254010902 0.0035555226069551105
vertex 0.3 0.0011552593254010902 0.003555522606955147
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 0.0013762327967052337 0.003475967262039186
vertex 0.3 0.0011552593254010902 0.003555522606955147
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.3 0.0011552593254010902 0.0035555226069551105
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0009297265733273723 0.003621045928505186
endloop
endfacet
facet normal -5.830157149569809e-17 0.2789911060392285 0.9602936856769433
outer loop
vertex -0.3 0.0011552593254010902 0.0035555226069551105
vertex -0.3 0.0009297265733273723 0.003621045928505186
vertex 0.3 0.0011552593254010902 0.003555522606955147
endloop
endfacet
facet normal -5.830454001316303e-17 0.2789911060392285 0.9602936856769433
outer loop
vertex 0.3 0.0011552593254010902 0.003555522606955147
vertex -0.3 0.0009297265733273723 0.003621045928505186
vertex 0.3 0.0009297265733273723 0.0036210459285052226
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 0.0011552593254010902 0.003555522606955147
vertex 0.3 0.0009297265733273723 0.0036210459285052226
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.3 0.0009297265733273723 0.003621045928505186
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0007005246152203978 0.0036722786360739784
endloop
endfacet
facet normal -5.925252342706117e-17 0.21814324139654448 0.9759167619387469
outer loop
vertex -0.3 0.0009297265733273723 0.003621045928505186
vertex -0.3 0.0007005246152203978 0.0036722786360739784
vertex 0.3 0.0009297265733273723 0.0036210459285052226
endloop
endfacet
facet normal -5.925310011370446e-17 0.21814324139654453 0.9759167619387469
outer loop
vertex 0.3 0.0009297265733273723 0.0036210459285052226
vertex -0.3 0.0007005246152203978 0.0036722786360739784
vertex 0.3 0.0007005246152203978 0.003672278636074015
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 0.0009297265733273723 0.0036210459285052226
vertex 0.3 0.0007005246152203978 0.003672278636074015
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.3 0.0007005246152203978 0.0036722786360739784
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0004685580064964025 0.003709018537570709
endloop
endfacet
facet normal -5.996867241240906e-17 0.15643446504023048 0.9876883405951379
outer loop
vertex -0.3 0.0007005246152203978 0.0036722786360739784
vertex -0.3 0.0004685580064964025 0.003709018537570709
vertex 0.3 0.0007005246152203978 0.003672278636074015
endloop
endfacet
facet normal -5.996781529826366e-17 0.15643446504023045 0.9876883405951379
outer loop
vertex 0.3 0.0007005246152203978 0.003672278636074015
vertex -0.3 0.0004685580064964025 0.003709018537570709
vertex 0.3 0.0004685580064964025 0.0037090185375707454
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 0.0007005246152203978 0.003672278636074015
vertex 0.3 0.0004685580064964025 0.0037090185375707454
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.3 0.0004685580064964025 0.003709018537570709
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.00023474221338455698 0.0037311206373890353
endloop
endfacet
facet normal -6.044414837809087e-17 0.09410831331851369 0.9955619646030801
outer loop
vertex -0.3 0.0004685580064964025 0.003709018537570709
vertex -0.3 0.00023474221338455698 0.0037311206373890353
vertex 0.3 0.0004685580064964025 0.0037090185375707454
endloop
endfacet
facet normal -6.04458649125294e-17 0.09410831331851369 0.9955619646030801
outer loop
vertex 0.3 0.0004685580064964025 0.0037090185375707454
vertex -0.3 0.00023474221338455698 0.0037311206373890353
vertex 0.3 0.00023474221338455698 0.0037311206373890717
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 0.0004685580064964025 0.0037090185375707454
vertex 0.3 0.00023474221338455698 0.0037311206373890717
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.3 0.00023474221338455698 0.0037311206373890353
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -1.2023925682051498e-18 0.0037384977086384634
endloop
endfacet
facet normal -6.068482139775696e-17 0.03141075907812753 0.9995065603657316
outer loop
vertex -0.3 0.00023474221338455698 0.0037311206373890353
vertex -0.3 -1.2023925682051498e-18 0.0037384977086384634
vertex 0.3 0.00023474221338455698 0.0037311206373890717
endloop
endfacet
facet normal -6.068536231307425e-17 0.03141075907812753 0.9995065603657316
outer loop
vertex 0.3 0.00023474221338455698 0.0037311206373890717
vertex -0.3 -1.2023925682051498e-18 0.0037384977086384634
vertex 0.3 -1.2023925682051498e-18 0.0037384977086385
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 0.00023474221338455698 0.0037311206373890717
vertex 0.3 -1.2023925682051498e-18 0.0037384977086385
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.3 -1.2023925682051498e-18 0.0037384977086384634
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.00023474221338455777 0.0037311206373890353
endloop
endfacet
facet normal -6.068628891616997e-17 -0.031410759078127744 0.9995065603657316
outer loop
vertex -0.3 -1.2023925682051498e-18 0.0037384977086384634
vertex -0.3 -0.00023474221338455777 0.0037311206373890353
vertex 0.3 -1.2023925682051498e-18 0.0037384977086385
endloop
endfacet
facet normal -6.068536231307425e-17 -0.031410759078127744 0.9995065603657316
outer loop
vertex 0.3 -1.2023925682051498e-18 0.0037384977086385
vertex -0.3 -0.00023474221338455777 0.0037311206373890353
vertex 0.3 -0.00023474221338455777 0.0037311206373890717
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -1.2023925682051498e-18 0.0037384977086385
vertex 0.3 -0.00023474221338455777 0.0037311206373890717
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.3 -0.00023474221338455777 0.0037311206373890353
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0004685580064964032 0.003709018537570709
endloop
endfacet
facet normal -6.044414837809089e-17 -0.09410831331851373 0.9955619646030801
outer loop
vertex -0.3 -0.00023474221338455777 0.0037311206373890353
vertex -0.3 -0.0004685580064964032 0.003709018537570709
vertex 0.3 -0.00023474221338455777 0.0037311206373890717
endloop
endfacet
facet normal -6.04458649125294e-17 -0.09410831331851373 0.9955619646030801
outer loop
vertex 0.3 -0.00023474221338455777 0.0037311206373890717
vertex -0.3 -0.0004685580064964032 0.003709018537570709
vertex 0.3 -0.0004685580064964032 0.0037090185375707454
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.00023474221338455777 0.0037311206373890717
vertex 0.3 -0.0004685580064964032 0.0037090185375707454
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.3 -0.0004685580064964032 0.003709018537570709
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0007005246152203985 0.003672278636073978
endloop
endfacet
facet normal -5.996867241240906e-17 -0.15643446504023228 0.9876883405951374
outer loop
vertex -0.3 -0.0004685580064964032 0.003709018537570709
vertex -0.3 -0.0007005246152203985 0.003672278636073978
vertex 0.3 -0.0004685580064964032 0.0037090185375707454
endloop
endfacet
facet normal -5.996781529826365e-17 -0.1564344650402323 0.9876883405951374
outer loop
vertex 0.3 -0.0004685580064964032 0.0037090185375707454
vertex -0.3 -0.0007005246152203985 0.003672278636073978
vertex 0.3 -0.0007005246152203985 0.0036722786360740144
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.0004685580064964032 0.0037090185375707454
vertex 0.3 -0.0007005246152203985 0.0036722786360740144
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.3 -0.0007005246152203985 0.003672278636073978
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.000929726573327373 0.003621045928505186
endloop
endfacet
facet normal -5.925252342706119e-17 -0.21814324139654276 0.9759167619387472
outer loop
vertex -0.3 -0.0007005246152203985 0.003672278636073978
vertex -0.3 -0.000929726573327373 0.003621045928505186
vertex 0.3 -0.0007005246152203985 0.0036722786360740144
endloop
endfacet
facet normal -5.925310011370447e-17 -0.21814324139654276 0.9759167619387472
outer loop
vertex 0.3 -0.0007005246152203985 0.0036722786360740144
vertex -0.3 -0.000929726573327373 0.003621045928505186
vertex 0.3 -0.000929726573327373 0.0036210459285052226
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.0007005246152203985 0.0036722786360740144
vertex 0.3 -0.000929726573327373 0.0036210459285052226
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -0.9999999999999999 -0.0 -0.0
outer loop
vertex -0.3 -0.000929726573327373 0.003621045928505186
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0011552593254010926 0.00355552260695511
endloop
endfacet
facet normal -5.830157149569764e-17 -0.27899110603922816 0.9602936856769434
outer loop
vertex -0.3 -0.000929726573327373 0.003621045928505186
vertex -0.3 -0.0011552593254010926 0.00355552260695511
vertex 0.3 -0.000929726573327373 0.0036210459285052226
endloop
endfacet
facet normal -5.830454001316303e-17 -0.27899110603922816 0.9602936856769434
outer loop
vertex 0.3 -0.000929726573327373 0.0036210459285052226
vertex -0.3 -0.0011552593254010926 0.00355552260695511
vertex 0.3 -0.0011552593254010926 0.0035555226069551465
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.000929726573327373 0.0036210459285052226
vertex 0.3 -0.0011552593254010926 0.0035555226069551465
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.3 -0.0011552593254010926 0.00355552260695511
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0013762327967052359 0.0034759672620391486
endloop
endfacet
facet normal -5.712755676561913e-17 -0.33873792024529303 0.9408807689542248
outer loop
vertex -0.3 -0.0011552593254010926 0.00355552260695511
vertex -0.3 -0.0013762327967052359 0.0034759672620391486
vertex 0.3 -0.0011552593254010926 0.0035555226069551465
endloop
endfacet
facet normal -5.712587853000015e-17 -0.33873792024529303 0.9408807689542248
outer loop
vertex 0.3 -0.0011552593254010926 0.0035555226069551465
vertex -0.3 -0.0013762327967052359 0.0034759672620391486
vertex 0.3 -0.0013762327967052359 0.003475967262039185
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.0011552593254010926 0.0035555226069551465
vertex 0.3 -0.0013762327967052359 0.003475967262039185
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.3 -0.0013762327967052359 0.0034759672620391486
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0015917749059017401 0.0033826938623583067
endloop
endfacet
facet normal -5.571873908952535e-17 -0.3971478906347813 0.9177546256839809
outer loop
vertex -0.3 -0.0013762327967052359 0.0034759672620391486
vertex -0.3 -0.0015917749059017401 0.0033826938623583067
vertex 0.3 -0.0013762327967052359 0.003475967262039185
endloop
endfacet
facet normal -5.572176730261082e-17 -0.3971478906347813 0.9177546256839809
outer loop
vertex 0.3 -0.0013762327967052359 0.003475967262039185
vertex -0.3 -0.0015917749059017401 0.0033826938623583067
vertex 0.3 -0.0015917749059017401 0.003382693862358343
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.0013762327967052359 0.003475967262039185
vertex 0.3 -0.0015917749059017401 0.003382693862358343
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -0.9999999999999999 -0.0 -0.0
outer loop
vertex -0.3 -0.0015917749059017401 0.0033826938623583067
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0018010350067574328 0.0032760705154085603
endloop
endfacet
facet normal -5.409859876201662e-17 -0.45399049973954714 0.8910065241883677
outer loop
vertex -0.3 -0.0015917749059017401 0.0033826938623583067
vertex -0.3 -0.0018010350067574328 0.0032760705154085603
vertex 0.3 -0.0015917749059017401 0.003382693862358343
endloop
endfacet
facet normal -5.409774771653205e-17 -0.4539904997395471 0.8910065241883677
outer loop
vertex 0.3 -0.0015917749059017401 0.003382693862358343
vertex -0.3 -0.0018010350067574328 0.0032760705154085603
vertex 0.3 -0.0018010350067574328 0.0032760705154085967
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.0015917749059017401 0.003382693862358343
vertex 0.3 -0.0018010350067574328 0.0032760705154085967
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.3 -0.0018010350067574328 0.0032760705154085603
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0020031872452560807 0.0031565180148287473
endloop
endfacet
facet normal -5.2267135783094315e-17 -0.5090414157503714 0.8607420270039438
outer loop
vertex -0.3 -0.0018010350067574328 0.0032760705154085603
vertex -0.3 -0.0020031872452560807 0.0031565180148287473
vertex 0.3 -0.0018010350067574328 0.0032760705154085967
endloop
endfacet
facet normal -5.2260229035126144e-17 -0.5090414157503714 0.8607420270039438
outer loop
vertex 0.3 -0.0018010350067574328 0.0032760705154085967
vertex -0.3 -0.0020031872452560807 0.0031565180148287473
vertex 0.3 -0.0020031872452560807 0.0031565180148287837
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.0018010350067574328 0.0032760705154085967
vertex 0.3 -0.0020031872452560807 0.0031565180148287837
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.3 -0.0020031872452560807 0.0031565180148287473
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0021974338188669035 0.0030245081797203133
endloop
endfacet
facet normal -5.0200869858156004e-17 -0.5620833778521306 0.8270805742745618
outer loop
vertex -0.3 -0.0020031872452560807 0.0031565180148287473
vertex -0.3 -0.0021974338188669035 0.0030245081797203133
vertex 0.3 -0.0020031872452560807 0.0031565180148287837
endloop
endfacet
facet normal -5.0216463105146153e-17 -0.5620833778521306 0.8270805742745618
outer loop
vertex 0.3 -0.0020031872452560807 0.0031565180148287837
vertex -0.3 -0.0021974338188669035 0.0030245081797203133
vertex 0.3 -0.0021974338188669035 0.0030245081797203497
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.0020031872452560807 0.0031565180148287837
vertex 0.3 -0.0021974338188669035 0.0030245081797203497
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.3 -0.0021974338188669035 0.0030245081797203133
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0023830081251066766 0.0028805619925928753
endloop
endfacet
facet normal -4.797024187100701e-17 -0.6129070536529755 0.7901550123756913
outer loop
vertex -0.3 -0.0021974338188669035 0.0030245081797203133
vertex -0.3 -0.0023830081251066766 0.0028805619925928753
vertex 0.3 -0.0021974338188669035 0.0030245081797203497
endloop
endfacet
facet normal -4.797451573700997e-17 -0.6129070536529754 0.7901550123756913
outer loop
vertex 0.3 -0.0021974338188669035 0.0030245081797203497
vertex -0.3 -0.0023830081251066766 0.0028805619925928753
vertex 0.3 -0.0023830081251066766 0.0028805619925929117
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.0021974338188669035 0.0030245081797203497
vertex 0.3 -0.0023830081251066766 0.0028805619925929117
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.3 -0.0023830081251066766 0.0028805619925928753
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0025591777869695066 0.002725247543284268
endloop
endfacet
facet normal -4.5528291232444e-17 -0.6613118653236523 0.7501110696304591
outer loop
vertex -0.3 -0.0023830081251066766 0.0028805619925928753
vertex -0.3 -0.0025591777869695066 0.002725247543284268
vertex 0.3 -0.0023830081251066766 0.0028805619925929117
endloop
endfacet
facet normal -4.5543234872731085e-17 -0.6613118653236523 0.7501110696304591
outer loop
vertex 0.3 -0.0023830081251066766 0.0028805619925929117
vertex -0.3 -0.0025591777869695066 0.002725247543284268
vertex 0.3 -0.0025591777869695066 0.0027252475432843043
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.0023830081251066766 0.0028805619925929117
vertex 0.3 -0.0025591777869695066 0.0027252475432843043
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.3 -0.0025591777869695066 0.002725247543284268
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.002725247543284286 0.002559177786969488
endloop
endfacet
facet normal -4.292197853166944e-17 -0.7071067811865485 0.7071067811865466
outer loop
vertex -0.3 -0.0025591777869695066 0.002725247543284268
vertex -0.3 -0.002725247543284286 0.002559177786969488
vertex 0.3 -0.0025591777869695066 0.0027252475432843043
endloop
endfacet
facet normal -4.293221566713442e-17 -0.7071067811865485 0.7071067811865466
outer loop
vertex 0.3 -0.0025591777869695066 0.0027252475432843043
vertex -0.3 -0.002725247543284286 0.002559177786969488
vertex 0.3 -0.002725247543284286 0.0025591777869695244
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.0025591777869695066 0.0027252475432843043
vertex 0.3 -0.002725247543284286 0.0025591777869695244
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.3 -0.002725247543284286 0.002559177786969488
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0028805619925928944 0.0023830081251066566
endloop
endfacet
facet normal -4.0151303768684234e-17 -0.7501110696304598 0.6613118653236516
outer loop
vertex -0.3 -0.002725247543284286 0.002559177786969488
vertex -0.3 -0.0028805619925928944 0.0023830081251066566
vertex 0.3 -0.002725247543284286 0.0025591777869695244
endloop
endfacet
facet normal -4.015176262016328e-17 -0.7501110696304598 0.6613118653236516
outer loop
vertex 0.3 -0.002725247543284286 0.0025591777869695244
vertex -0.3 -0.0028805619925928944 0.0023830081251066566
vertex 0.3 -0.0028805619925928944 0.002383008125106693
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.002725247543284286 0.0025591777869695244
vertex 0.3 -0.0028805619925928944 0.002383008125106693
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.3 -0.0028805619925928944 0.0023830081251066566
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.003024508179720332 0.002197433818866885
endloop
endfacet
facet normal -3.721626694348827e-17 -0.7901550123756901 0.6129070536529769
outer loop
vertex -0.3 -0.0028805619925928944 0.0023830081251066566
vertex -0.3 -0.003024508179720332 0.002197433818866885
vertex 0.3 -0.0028805619925928944 0.002383008125106693
endloop
endfacet
facet normal -3.721284890972585e-17 -0.7901550123756901 0.6129070536529769
outer loop
vertex 0.3 -0.0028805619925928944 0.002383008125106693
vertex -0.3 -0.003024508179720332 0.002197433818866885
vertex 0.3 -0.003024508179720332 0.0021974338188669213
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.0028805619925928944 0.002383008125106693
vertex 0.3 -0.003024508179720332 0.0021974338188669213
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.3 -0.003024508179720332 0.002197433818866885
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0031565180148287668 0.002003187245256061
endloop
endfacet
facet normal -3.414034835068216e-17 -0.8270805742745613 0.5620833778521314
outer loop
vertex -0.3 -0.003024508179720332 0.002197433818866885
vertex -0.3 -0.0031565180148287668 0.002003187245256061
vertex 0.3 -0.003024508179720332 0.0021974338188669213
endloop
endfacet
facet normal -3.41270730855752e-17 -0.8270805742745613 0.5620833778521314
outer loop
vertex 0.3 -0.003024508179720332 0.0021974338188669213
vertex -0.3 -0.0031565180148287668 0.002003187245256061
vertex 0.3 -0.0031565180148287668 0.0020031872452560976
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.003024508179720332 0.0021974338188669213
vertex 0.3 -0.0031565180148287668 0.0020031872452560976
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.3 -0.0031565180148287668 0.002003187245256061
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.003276070515408579 0.001801035006757414
endloop
endfacet
facet normal -3.090006769566594e-17 -0.8607420270039444 0.5090414157503698
outer loop
vertex -0.3 -0.0031565180148287668 0.002003187245256061
vertex -0.3 -0.003276070515408579 0.001801035006757414
vertex 0.3 -0.0031565180148287668 0.0020031872452560976
endloop
endfacet
facet normal -3.127454916769343e-17 -0.8607420270039441 0.5090414157503707
outer loop
vertex 0.3 -0.0031565180148287668 0.0020031872452560976
vertex -0.3 -0.003276070515408579 0.001801035006757414
vertex 0.3 -0.003276070515408579 0.0018010350067574508
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.0031565180148287668 0.0020031872452560976
vertex 0.3 -0.003276070515408579 0.0018010350067574508
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.3 -0.003276070515408579 0.001801035006757414
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0033826938623583262 0.0015917749059017198
endloop
endfacet
facet normal -2.7871109692063044e-17 -0.8910065241883677 0.45399049973954747
outer loop
vertex -0.3 -0.003276070515408579 0.001801035006757414
vertex -0.3 -0.0033826938623583262 0.0015917749059017198
vertex 0.3 -0.003276070515408579 0.0018010350067574508
endloop
endfacet
facet normal -2.789232421263917e-17 -0.8910065241883677 0.45399049973954747
outer loop
vertex 0.3 -0.003276070515408579 0.0018010350067574508
vertex -0.3 -0.0033826938623583262 0.0015917749059017198
vertex 0.3 -0.0033826938623583262 0.0015917749059017566
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.003276070515408579 0.0018010350067574508
vertex 0.3 -0.0033826938623583262 0.0015917749059017566
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.3 -0.0033826938623583262 0.0015917749059017198
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0034759672620391677 0.0013762327967052155
endloop
endfacet
facet normal -2.4396026091031126e-17 -0.9177546256839814 0.3971478906347797
outer loop
vertex -0.3 -0.0033826938623583262 0.0015917749059017198
vertex -0.3 -0.0034759672620391677 0.0013762327967052155
vertex 0.3 -0.0033826938623583262 0.0015917749059017566
endloop
endfacet
facet normal -2.4400020996708275e-17 -0.9177546256839814 0.3971478906347797
outer loop
vertex 0.3 -0.0033826938623583262 0.0015917749059017566
vertex -0.3 -0.0034759672620391677 0.0013762327967052155
vertex 0.3 -0.0034759672620391677 0.0013762327967052524
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.0033826938623583262 0.0015917749059017566
vertex 0.3 -0.0034759672620391677 0.0013762327967052524
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -0.9999999999999999 -0.0 -0.0
outer loop
vertex -0.3 -0.0034759672620391677 0.0013762327967052155
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0035555226069551283 0.0011552593254010736
endloop
endfacet
facet normal -2.080354101699091e-17 -0.9408807689542253 0.33873792024529165
outer loop
vertex -0.3 -0.0034759672620391677 0.0013762327967052155
vertex -0.3 -0.0035555226069551283 0.0011552593254010736
vertex 0.3 -0.0034759672620391677 0.0013762327967052524
endloop
endfacet
facet normal -2.081142204521278e-17 -0.9408807689542253 0.33873792024529165
outer loop
vertex 0.3 -0.0034759672620391677 0.0013762327967052524
vertex -0.3 -0.0035555226069551283 0.0011552593254010736
vertex 0.3 -0.0035555226069551283 0.0011552593254011104
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.0034759672620391677 0.0013762327967052524
vertex 0.3 -0.0035555226069551283 0.0011552593254011104
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.3 -0.0035555226069551283 0.0011552593254010736
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.003621045928505205 0.0009297265733273525
endloop
endfacet
facet normal -1.7140615059145795e-17 -0.9602936856769434 0.2789911060392283
outer loop
vertex -0.3 -0.0035555226069551283 0.0011552593254010736
vertex -0.3 -0.003621045928505205 0.0009297265733273525
vertex 0.3 -0.0035555226069551283 0.0011552593254011104
endloop
endfacet
facet normal -1.7039862330981712e-17 -0.9602936856769434 0.278991106039228
outer loop
vertex 0.3 -0.0035555226069551283 0.0011552593254011104
vertex -0.3 -0.003621045928505205 0.0009297265733273525
vertex 0.3 -0.003621045928505205 0.0009297265733273891
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.0035555226069551283 0.0011552593254011104
vertex 0.3 -0.003621045928505205 0.0009297265733273891
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.3 -0.003621045928505205 0.0009297265733273525
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0036722786360739966 0.0007005246152203796
endloop
endfacet
facet normal -1.3325067186390909e-17 -0.9759167619387471 0.21814324139654426
outer loop
vertex -0.3 -0.003621045928505205 0.0009297265733273525
vertex -0.3 -0.0036722786360739966 0.0007005246152203796
vertex 0.3 -0.003621045928505205 0.0009297265733273891
endloop
endfacet
facet normal -1.3323474194580857e-17 -0.9759167619387471 0.21814324139654426
outer loop
vertex 0.3 -0.003621045928505205 0.0009297265733273891
vertex -0.3 -0.0036722786360739966 0.0007005246152203796
vertex 0.3 -0.0036722786360739966 0.0007005246152204163
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.003621045928505205 0.0009297265733273891
vertex 0.3 -0.0036722786360739966 0.0007005246152204163
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.3 -0.0036722786360739966 0.0007005246152203796
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.003709018537570727 0.00046855800649638275
endloop
endfacet
facet normal -9.556479902838815e-18 -0.9876883405951379 0.15643446504022945
outer loop
vertex -0.3 -0.0036722786360739966 0.0007005246152203796
vertex -0.3 -0.003709018537570727 0.00046855800649638275
vertex 0.3 -0.0036722786360739966 0.0007005246152204163
endloop
endfacet
facet normal -9.58277215692469e-18 -0.9876883405951379 0.15643446504022956
outer loop
vertex 0.3 -0.0036722786360739966 0.0007005246152204163
vertex -0.3 -0.003709018537570727 0.00046855800649638275
vertex 0.3 -0.003709018537570727 0.0004685580064964195
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.0036722786360739966 0.0007005246152204163
vertex 0.3 -0.003709018537570727 0.0004685580064964195
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.3 -0.003709018537570727 0.00046855800649638275
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0037311206373890535 0.00023474221338453888
endloop
endfacet
facet normal -5.764412324685408e-18 -0.99556196460308 0.09410831331851434
outer loop
vertex -0.3 -0.003709018537570727 0.00046855800649638275
vertex -0.3 -0.0037311206373890535 0.00023474221338453888
vertex 0.3 -0.003709018537570727 0.0004685580064964195
endloop
endfacet
facet normal -5.764832732811708e-18 -0.99556196460308 0.09410831331851434
outer loop
vertex 0.3 -0.003709018537570727 0.0004685580064964195
vertex -0.3 -0.0037311206373890535 0.00023474221338453888
vertex 0.3 -0.0037311206373890535 0.00023474221338457563
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.003709018537570727 0.0004685580064964195
vertex 0.3 -0.0037311206373890535 0.00023474221338457563
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.3 -0.0037311206373890535 0.00023474221338453888
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0037384977086384816 -1.7682951099334722e-17
endloop
endfacet
facet normal -1.9239166389161327e-18 -0.9995065603657316 0.031410759078127744
outer loop
vertex -0.3 -0.0037311206373890535 0.00023474221338453888
vertex -0.3 -0.0037384977086384816 -1.7682951099334722e-17
vertex 0.3 -0.0037311206373890535 0.00023474221338457563
endloop
endfacet
facet normal -1.9233542781908906e-18 -0.9995065603657316 0.031410759078127744
outer loop
vertex 0.3 -0.0037311206373890535 0.00023474221338457563
vertex -0.3 -0.0037384977086384816 -1.7682951099334722e-17
vertex 0.3 -0.0037384977086384816 1.9056452875085873e-17
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.3 -0.0037311206373890535 0.00023474221338457563
vertex 0.3 -0.0037384977086384816 1.9056452875085873e-17
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.3 -0.0037384977086384816 -1.7682951099334722e-17
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0037311206373890535 -0.00023474221338457756
endloop
endfacet
facet normal 1.9224491205035074e-18 -0.9995065603657315 -0.0314107590781273
outer loop
vertex -0.3 -0.0037384977086384816 -1.7682951099334722e-17
vertex -0.3 -0.0037311206373890535 -0.00023474221338457756
vertex 0.3 -0.0037384977086384816 1.9056452875085873e-17
endloop
endfacet
facet normal 1.9241421476037293e-18 -0.9995065603657316 -0.03141075907812731
outer loop
vertex 0.3 -0.0037384977086384816 1.9056452875085873e-17
vertex -0.3 -0.0037311206373890535 -0.00023474221338457756
vertex 0.3 -0.0037311206373890535 -0.0002347422133845408
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.0037384977086384816 1.9056452875085873e-17
vertex 0.3 -0.0037311206373890535 -0.0002347422133845408
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.3 -0.0037311206373890535 -0.00023474221338457756
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.003709018537570727 -0.0004685580064964214
endloop
endfacet
facet normal 5.764412324685408e-18 -0.99556196460308 -0.09410831331851434
outer loop
vertex -0.3 -0.0037311206373890535 -0.00023474221338457756
vertex -0.3 -0.003709018537570727 -0.0004685580064964214
vertex 0.3 -0.0037311206373890535 -0.0002347422133845408
endloop
endfacet
facet normal 5.764832732811708e-18 -0.99556196460308 -0.09410831331851435
outer loop
vertex 0.3 -0.0037311206373890535 -0.0002347422133845408
vertex -0.3 -0.003709018537570727 -0.0004685580064964214
vertex 0.3 -0.003709018537570727 -0.00046855800649638464
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.0037311206373890535 -0.0002347422133845408
vertex 0.3 -0.003709018537570727 -0.00046855800649638464
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.3 -0.003709018537570727 -0.0004685580064964214
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.003672278636073996 -0.0007005246152204182
endloop
endfacet
facet normal 9.579960197440384e-18 -0.9876883405951377 -0.15643446504023129
outer loop
vertex -0.3 -0.003709018537570727 -0.0004685580064964214
vertex -0.3 -0.003672278636073996 -0.0007005246152204182
vertex 0.3 -0.003709018537570727 -0.00046855800649638464
endloop
endfacet
facet normal 9.554504392450086e-18 -0.9876883405951378 -0.1564344650402312
outer loop
vertex 0.3 -0.003709018537570727 -0.00046855800649638464
vertex -0.3 -0.003672278636073996 -0.0007005246152204182
vertex 0.3 -0.003672278636073996 -0.0007005246152203816
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.003709018537570727 -0.00046855800649638464
vertex 0.3 -0.003672278636073996 -0.0007005246152203816
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.3 -0.003672278636073996 -0.0007005246152204182
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0036210459285052044 -0.0009297265733273911
endloop
endfacet
facet normal 1.3325067186390909e-17 -0.9759167619387471 -0.21814324139654426
outer loop
vertex -0.3 -0.003672278636073996 -0.0007005246152204182
vertex -0.3 -0.0036210459285052044 -0.0009297265733273911
vertex 0.3 -0.003672278636073996 -0.0007005246152203816
endloop
endfacet
facet normal 1.3323474194580857e-17 -0.9759167619387471 -0.21814324139654426
outer loop
vertex 0.3 -0.003672278636073996 -0.0007005246152203816
vertex -0.3 -0.0036210459285052044 -0.0009297265733273911
vertex 0.3 -0.0036210459285052044 -0.0009297265733273544
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.003672278636073996 -0.0007005246152203816
vertex 0.3 -0.0036210459285052044 -0.0009297265733273544
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.3 -0.0036210459285052044 -0.0009297265733273911
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0035555226069551287 -0.0011552593254011091
endloop
endfacet
facet normal 1.703495373343896e-17 -0.9602936856769434 -0.27899110603922833
outer loop
vertex -0.3 -0.0036210459285052044 -0.0009297265733273911
vertex -0.3 -0.0035555226069551287 -0.0011552593254011091
vertex 0.3 -0.0036210459285052044 -0.0009297265733273544
endloop
endfacet
facet normal 1.7140689918739036e-17 -0.9602936856769432 -0.27899110603922855
outer loop
vertex 0.3 -0.0036210459285052044 -0.0009297265733273544
vertex -0.3 -0.0035555226069551287 -0.0011552593254011091
vertex 0.3 -0.0035555226069551287 -0.0011552593254010723
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.0036210459285052044 -0.0009297265733273544
vertex 0.3 -0.0035555226069551287 -0.0011552593254010723
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -0.9999999999999999 0.0 -0.0
outer loop
vertex -0.3 -0.0035555226069551287 -0.0011552593254011091
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.003475967262039167 -0.001376232796705254
endloop
endfacet
facet normal 2.0827021311592184e-17 -0.940880768954225 -0.3387379202452923
outer loop
vertex -0.3 -0.0035555226069551287 -0.0011552593254011091
vertex -0.3 -0.003475967262039167 -0.001376232796705254
vertex 0.3 -0.0035555226069551287 -0.0011552593254010723
endloop
endfacet
facet normal 2.0811422045212825e-17 -0.940880768954225 -0.3387379202452923
outer loop
vertex 0.3 -0.0035555226069551287 -0.0011552593254010723
vertex -0.3 -0.003475967262039167 -0.001376232796705254
vertex 0.3 -0.003475967262039167 -0.0013762327967052172
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.0035555226069551287 -0.0011552593254010723
vertex 0.3 -0.003475967262039167 -0.0013762327967052172
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.3 -0.003475967262039167 -0.001376232796705254
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0033826938623583254 -0.0015917749059017583
endloop
endfacet
facet normal 2.4396026091031126e-17 -0.9177546256839814 -0.3971478906347797
outer loop
vertex -0.3 -0.003475967262039167 -0.001376232796705254
vertex -0.3 -0.0033826938623583254 -0.0015917749059017583
vertex 0.3 -0.003475967262039167 -0.0013762327967052172
endloop
endfacet
facet normal 2.4400020996708275e-17 -0.9177546256839814 -0.3971478906347797
outer loop
vertex 0.3 -0.003475967262039167 -0.0013762327967052172
vertex -0.3 -0.0033826938623583254 -0.0015917749059017583
vertex 0.3 -0.0033826938623583254 -0.0015917749059017215
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.003475967262039167 -0.0013762327967052172
vertex 0.3 -0.0033826938623583254 -0.0015917749059017215
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.3 -0.0033826938623583254 -0.0015917749059017583
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.003276070515408578 -0.0018010350067574523
endloop
endfacet
facet normal 2.787110969206306e-17 -0.8910065241883673 -0.4539904997395478
outer loop
vertex -0.3 -0.0033826938623583254 -0.0015917749059017583
vertex -0.3 -0.003276070515408578 -0.0018010350067574523
vertex 0.3 -0.0033826938623583254 -0.0015917749059017215
endloop
endfacet
facet normal 2.7892324212639196e-17 -0.8910065241883673 -0.4539904997395478
outer loop
vertex 0.3 -0.0033826938623583254 -0.0015917749059017215
vertex -0.3 -0.003276070515408578 -0.0018010350067574523
vertex 0.3 -0.003276070515408578 -0.0018010350067574155
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.0033826938623583254 -0.0015917749059017215
vertex 0.3 -0.003276070515408578 -0.0018010350067574155
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.3 -0.003276070515408578 -0.0018010350067574523
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0031565180148287655 -0.002003187245256099
endloop
endfacet
facet normal 3.127575240929111e-17 -0.860742027003943 -0.5090414157503724
outer loop
vertex -0.3 -0.003276070515408578 -0.0018010350067574523
vertex -0.3 -0.0031565180148287655 -0.002003187245256099
vertex 0.3 -0.003276070515408578 -0.0018010350067574155
endloop
endfacet
facet normal 3.0906613295132386e-17 -0.8607420270039434 -0.5090414157503715
outer loop
vertex 0.3 -0.003276070515408578 -0.0018010350067574155
vertex -0.3 -0.0031565180148287655 -0.002003187245256099
vertex 0.3 -0.0031565180148287655 -0.0020031872452560624
endloop
endfacet
facet normal 0.9999999999999999 -0.0 0.0
outer loop
vertex 0.3 -0.003276070515408578 -0.0018010350067574155
vertex 0.3 -0.0031565180148287655 -0.0020031872452560624
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -0.9999999999999999 0.0 -0.0
outer loop
vertex -0.3 -0.0031565180148287655 -0.002003187245256099
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0030245081797203306 -0.002197433818866923
endloop
endfacet
facet normal 3.414034835068211e-17 -0.8270805742745618 -0.5620833778521305
outer loop
vertex -0.3 -0.0031565180148287655 -0.002003187245256099
vertex -0.3 -0.0030245081797203306 -0.002197433818866923
vertex 0.3 -0.0031565180148287655 -0.0020031872452560624
endloop
endfacet
facet normal 3.412707308557515e-17 -0.8270805742745618 -0.5620833778521305
outer loop
vertex 0.3 -0.0031565180148287655 -0.0020031872452560624
vertex -0.3 -0.0030245081797203306 -0.002197433818866923
vertex 0.3 -0.0030245081797203306 -0.0021974338188668866
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.0031565180148287655 -0.0020031872452560624
vertex 0.3 -0.0030245081797203306 -0.0021974338188668866
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.3 -0.0030245081797203306 -0.002197433818866923
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0028805619925928935 -0.002383008125106695
endloop
endfacet
facet normal 3.721626694348831e-17 -0.790155012375691 -0.6129070536529758
outer loop
vertex -0.3 -0.0030245081797203306 -0.002197433818866923
vertex -0.3 -0.0028805619925928935 -0.002383008125106695
vertex 0.3 -0.0030245081797203306 -0.0021974338188668866
endloop
endfacet
facet normal 3.7212848909725774e-17 -0.790155012375691 -0.6129070536529758
outer loop
vertex 0.3 -0.0030245081797203306 -0.0021974338188668866
vertex -0.3 -0.0028805619925928935 -0.002383008125106695
vertex 0.3 -0.0028805619925928935 -0.0023830081251066584
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.0030245081797203306 -0.0021974338188668866
vertex 0.3 -0.0028805619925928935 -0.0023830081251066584
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.3 -0.0028805619925928935 -0.002383008125106695
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.002725247543284286 -0.0025591777869695244
endloop
endfacet
facet normal 4.0151303768684555e-17 -0.7501110696304584 -0.6613118653236532
outer loop
vertex -0.3 -0.0028805619925928935 -0.002383008125106695
vertex -0.3 -0.002725247543284286 -0.0025591777869695244
vertex 0.3 -0.0028805619925928935 -0.0023830081251066584
endloop
endfacet
facet normal 4.0151762620163385e-17 -0.7501110696304584 -0.6613118653236532
outer loop
vertex 0.3 -0.0028805619925928935 -0.0023830081251066584
vertex -0.3 -0.002725247543284286 -0.0025591777869695244
vertex 0.3 -0.002725247543284286 -0.002559177786969488
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.0028805619925928935 -0.0023830081251066584
vertex 0.3 -0.002725247543284286 -0.002559177786969488
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.3 -0.002725247543284286 -0.0025591777869695244
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.002559177786969505 -0.0027252475432843056
endloop
endfacet
facet normal 4.294545882627062e-17 -0.7071067811865476 -0.7071067811865476
outer loop
vertex -0.3 -0.002725247543284286 -0.0025591777869695244
vertex -0.3 -0.002559177786969505 -0.0027252475432843056
vertex 0.3 -0.002725247543284286 -0.002559177786969488
endloop
endfacet
facet normal 4.2932215667134476e-17 -0.7071067811865476 -0.7071067811865476
outer loop
vertex 0.3 -0.002725247543284286 -0.002559177786969488
vertex -0.3 -0.002559177786969505 -0.0027252475432843056
vertex 0.3 -0.002559177786969505 -0.0027252475432842692
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.002725247543284286 -0.002559177786969488
vertex 0.3 -0.002559177786969505 -0.0027252475432842692
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -0.9999999999999999 0.0 -0.0
outer loop
vertex -0.3 -0.002559177786969505 -0.0027252475432843056
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0023830081251066753 -0.0028805619925929126
endloop
endfacet
facet normal 4.55517715270457e-17 -0.6613118653236522 -0.7501110696304594
outer loop
vertex -0.3 -0.002559177786969505 -0.0027252475432843056
vertex -0.3 -0.0023830081251066753 -0.0028805619925929126
vertex 0.3 -0.002559177786969505 -0.0027252475432842692
endloop
endfacet
facet normal 4.55432348727311e-17 -0.6613118653236522 -0.7501110696304594
outer loop
vertex 0.3 -0.002559177786969505 -0.0027252475432842692
vertex -0.3 -0.0023830081251066753 -0.0028805619925929126
vertex 0.3 -0.0023830081251066753 -0.002880561992592876
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.002559177786969505 -0.0027252475432842692
vertex 0.3 -0.0023830081251066753 -0.002880561992592876
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -0.9999999999999999 0.0 -0.0
outer loop
vertex -0.3 -0.0023830081251066753 -0.0028805619925929126
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0021974338188669004 -0.003024508179720352
endloop
endfacet
facet normal 4.7970241871006564e-17 -0.6129070536529753 -0.7901550123756914
outer loop
vertex -0.3 -0.0023830081251066753 -0.0028805619925929126
vertex -0.3 -0.0021974338188669004 -0.003024508179720352
vertex 0.3 -0.0023830081251066753 -0.002880561992592876
endloop
endfacet
facet normal 4.797451573700998e-17 -0.6129070536529753 -0.7901550123756914
outer loop
vertex 0.3 -0.0023830081251066753 -0.002880561992592876
vertex -0.3 -0.0021974338188669004 -0.003024508179720352
vertex 0.3 -0.0021974338188669004 -0.0030245081797203154
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.0023830081251066753 -0.002880561992592876
vertex 0.3 -0.0021974338188669004 -0.0030245081797203154
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.3 -0.0021974338188669004 -0.003024508179720352
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0020031872452560794 -0.003156518014828785
endloop
endfacet
facet normal 5.0224350152757995e-17 -0.5620833778521315 -0.8270805742745614
outer loop
vertex -0.3 -0.0021974338188669004 -0.003024508179720352
vertex -0.3 -0.0020031872452560794 -0.003156518014828785
vertex 0.3 -0.0021974338188669004 -0.0030245081797203154
endloop
endfacet
facet normal 5.021646310514612e-17 -0.5620833778521315 -0.8270805742745614
outer loop
vertex 0.3 -0.0021974338188669004 -0.0030245081797203154
vertex -0.3 -0.0020031872452560794 -0.003156518014828785
vertex 0.3 -0.0020031872452560794 -0.0031565180148287486
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.0021974338188669004 -0.0030245081797203154
vertex 0.3 -0.0020031872452560794 -0.0031565180148287486
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.3 -0.0020031872452560794 -0.003156518014828785
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0018010350067574326 -0.003276070515408597
endloop
endfacet
facet normal 5.2267135783094617e-17 -0.5090414157503707 -0.8607420270039441
outer loop
vertex -0.3 -0.0020031872452560794 -0.003156518014828785
vertex -0.3 -0.0018010350067574326 -0.003276070515408597
vertex 0.3 -0.0020031872452560794 -0.0031565180148287486
endloop
endfacet
facet normal 5.226022903512616e-17 -0.5090414157503707 -0.8607420270039441
outer loop
vertex 0.3 -0.0020031872452560794 -0.0031565180148287486
vertex -0.3 -0.0018010350067574326 -0.003276070515408597
vertex 0.3 -0.0018010350067574326 -0.0032760705154085607
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.0020031872452560794 -0.0031565180148287486
vertex 0.3 -0.0018010350067574326 -0.0032760705154085607
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -0.9999999999999999 0.0 -0.0
outer loop
vertex -0.3 -0.0018010350067574326 -0.003276070515408597
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0015917749059017384 -0.003382693862358344
endloop
endfacet
facet normal 5.4098598762016256e-17 -0.45399049973954597 -0.8910065241883683
outer loop
vertex -0.3 -0.0018010350067574326 -0.003276070515408597
vertex -0.3 -0.0015917749059017384 -0.003382693862358344
vertex 0.3 -0.0018010350067574326 -0.0032760705154085607
endloop
endfacet
facet normal 5.409774771653208e-17 -0.45399049973954597 -0.8910065241883683
outer loop
vertex 0.3 -0.0018010350067574326 -0.0032760705154085607
vertex -0.3 -0.0015917749059017384 -0.003382693862358344
vertex 0.3 -0.0015917749059017384 -0.0033826938623583076
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.0018010350067574326 -0.0032760705154085607
vertex 0.3 -0.0015917749059017384 -0.0033826938623583076
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.3 -0.0015917749059017384 -0.003382693862358344
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0013762327967052341 -0.003475967262039186
endloop
endfacet
facet normal 5.571873908952535e-17 -0.3971478906347813 -0.9177546256839809
outer loop
vertex -0.3 -0.0015917749059017384 -0.003382693862358344
vertex -0.3 -0.0013762327967052341 -0.003475967262039186
vertex 0.3 -0.0015917749059017384 -0.0033826938623583076
endloop
endfacet
facet normal 5.572176730261082e-17 -0.3971478906347813 -0.9177546256839809
outer loop
vertex 0.3 -0.0015917749059017384 -0.0033826938623583076
vertex -0.3 -0.0013762327967052341 -0.003475967262039186
vertex 0.3 -0.0013762327967052341 -0.0034759672620391494
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.0015917749059017384 -0.0033826938623583076
vertex 0.3 -0.0013762327967052341 -0.0034759672620391494
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.3 -0.0013762327967052341 -0.003475967262039186
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0011552593254010892 -0.0035555226069551474
endloop
endfacet
facet normal 5.710407647101717e-17 -0.3387379202452907 -0.9408807689542258
outer loop
vertex -0.3 -0.0013762327967052341 -0.003475967262039186
vertex -0.3 -0.0011552593254010892 -0.0035555226069551474
vertex 0.3 -0.0013762327967052341 -0.0034759672620391494
endloop
endfacet
facet normal 5.71258785300002e-17 -0.3387379202452907 -0.9408807689542258
outer loop
vertex 0.3 -0.0013762327967052341 -0.0034759672620391494
vertex -0.3 -0.0011552593254010892 -0.0035555226069551474
vertex 0.3 -0.0011552593254010892 -0.003555522606955111
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.0013762327967052341 -0.0034759672620391494
vertex 0.3 -0.0011552593254010892 -0.003555522606955111
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.3 -0.0011552593254010892 -0.0035555226069551474
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.000929726573327371 -0.003621045928505223
endloop
endfacet
facet normal 5.830157149569803e-17 -0.2789911060392282 -0.9602936856769434
outer loop
vertex -0.3 -0.0011552593254010892 -0.0035555226069551474
vertex -0.3 -0.000929726573327371 -0.003621045928505223
vertex 0.3 -0.0011552593254010892 -0.003555522606955111
endloop
endfacet
facet normal 5.830454001316305e-17 -0.2789911060392282 -0.9602936856769434
outer loop
vertex 0.3 -0.0011552593254010892 -0.003555522606955111
vertex -0.3 -0.000929726573327371 -0.003621045928505223
vertex 0.3 -0.000929726573327371 -0.0036210459285051866
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.0011552593254010892 -0.003555522606955111
vertex 0.3 -0.000929726573327371 -0.0036210459285051866
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.3 -0.000929726573327371 -0.003621045928505223
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.0007005246152203982 -0.003672278636074015
endloop
endfacet
facet normal 5.926426357436238e-17 -0.21814324139654426 -0.9759167619387471
outer loop
vertex -0.3 -0.000929726573327371 -0.003621045928505223
vertex -0.3 -0.0007005246152203982 -0.003672278636074015
vertex 0.3 -0.000929726573327371 -0.0036210459285051866
endloop
endfacet
facet normal 5.925310011370447e-17 -0.21814324139654426 -0.9759167619387471
outer loop
vertex 0.3 -0.000929726573327371 -0.0036210459285051866
vertex -0.3 -0.0007005246152203982 -0.003672278636074015
vertex 0.3 -0.0007005246152203982 -0.0036722786360739784
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.000929726573327371 -0.0036210459285051866
vertex 0.3 -0.0007005246152203982 -0.0036722786360739784
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.3 -0.0007005246152203982 -0.003672278636074015
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.00046855800649640134 -0.0037090185375707454
endloop
endfacet
facet normal 5.996867241240869e-17 -0.1564344650402295 -0.987688340595138
outer loop
vertex -0.3 -0.0007005246152203982 -0.003672278636074015
vertex -0.3 -0.00046855800649640134 -0.0037090185375707454
vertex 0.3 -0.0007005246152203982 -0.0036722786360739784
endloop
endfacet
facet normal 5.996781529826368e-17 -0.1564344650402295 -0.987688340595138
outer loop
vertex 0.3 -0.0007005246152203982 -0.0036722786360739784
vertex -0.3 -0.00046855800649640134 -0.0037090185375707454
vertex 0.3 -0.00046855800649640134 -0.003709018537570709
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.0007005246152203982 -0.0036722786360739784
vertex 0.3 -0.00046855800649640134 -0.003709018537570709
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.3 -0.00046855800649640134 -0.0037090185375707454
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 -0.00023474221338455747 -0.0037311206373890717
endloop
endfacet
facet normal 6.044414837809129e-17 -0.09410831331851434 -0.99556196460308
outer loop
vertex -0.3 -0.00046855800649640134 -0.0037090185375707454
vertex -0.3 -0.00023474221338455747 -0.0037311206373890717
vertex 0.3 -0.00046855800649640134 -0.003709018537570709
endloop
endfacet
facet normal 6.04458649125294e-17 -0.09410831331851435 -0.99556196460308
outer loop
vertex 0.3 -0.00046855800649640134 -0.003709018537570709
vertex -0.3 -0.00023474221338455747 -0.0037311206373890717
vertex 0.3 -0.00023474221338455747 -0.0037311206373890353
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.00046855800649640134 -0.003709018537570709
vertex 0.3 -0.00023474221338455747 -0.0037311206373890353
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.3 -0.00023474221338455747 -0.0037311206373890717
vertex -0.3 0.0 -1.8369701987210297e-17
vertex -0.3 0.0 -0.0037384977086385
endloop
endfacet
facet normal 6.068482139775715e-17 -0.031410759078127626 -0.9995065603657316
outer loop
vertex -0.3 -0.00023474221338455747 -0.0037311206373890717
vertex -0.3 0.0 -0.0037384977086385
vertex 0.3 -0.00023474221338455747 -0.0037311206373890353
endloop
endfacet
facet normal 6.068536231307425e-17 -0.031410759078127626 -0.9995065603657316
outer loop
vertex 0.3 -0.00023474221338455747 -0.0037311206373890353
vertex -0.3 0.0 -0.0037384977086385
vertex 0.3 0.0 -0.0037384977086384634
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.3 -0.00023474221338455747 -0.0037311206373890353
vertex 0.3 0.0 -0.0037384977086384634
vertex 0.3 0.0 1.8369701987210297e-17
endloop
endfacet

endsolid
""")

write_file("constant/triSurface/glass.stl", """solid
facet normal -1.0 0.0 -0.0
outer loop
vertex 0.279 0.0 -0.0037384977086384647
vertex 0.279 0.000729344721834839 -0.003666663523453811
vertex 0.279 0.0 -0.07499999999999998
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex 0.279 0.0 -0.07499999999999998
vertex 0.279 0.000729344721834839 -0.003666663523453811
vertex 0.279 0.014631774151209618 -0.07355889603024227
endloop
endfacet
facet normal 0.0 0.09801714032956071 -0.995184726672197
outer loop
vertex 0.279 0.0 -0.07499999999999998
vertex 0.279 0.014631774151209618 -0.07355889603024227
vertex 0.281 0.0 -0.07499999999999998
endloop
endfacet
facet normal 0.0 0.09801714032956071 -0.995184726672197
outer loop
vertex 0.281 0.0 -0.07499999999999998
vertex 0.279 0.014631774151209618 -0.07355889603024227
vertex 0.281 0.014631774151209618 -0.07355889603024227
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.281 0.0 -0.07499999999999998
vertex 0.281 0.014631774151209618 -0.07355889603024227
vertex 0.281 0.0 -0.0037384977086384642
endloop
endfacet
facet normal 1.0 -0.0 -0.0
outer loop
vertex 0.281 0.0 -0.0037384977086384642
vertex 0.281 0.014631774151209618 -0.07355889603024227
vertex 0.281 0.000729344721834839 -0.0036666635234538104
endloop
endfacet
facet normal -2.1670674721591997e-16 -0.09801714032956056 0.9951847266721969
outer loop
vertex 0.281 0.0 -0.0037384977086384642
vertex 0.281 0.000729344721834839 -0.0036666635234538104
vertex 0.279 0.0 -0.0037384977086384647
endloop
endfacet
facet normal -2.1579628853647757e-16 -0.09801714032956055 0.9951847266721969
outer loop
vertex 0.279 0.0 -0.0037384977086384647
vertex 0.281 0.000729344721834839 -0.0036666635234538104
vertex 0.279 0.000729344721834839 -0.003666663523453811
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex 0.279 0.000729344721834839 -0.003666663523453811
vertex 0.279 0.0014306611350307975 -0.00345392151535142
vertex 0.279 0.014631774151209618 -0.07355889603024227
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex 0.279 0.014631774151209618 -0.07355889603024227
vertex 0.279 0.0014306611350307975 -0.00345392151535142
vertex 0.279 0.02870125742738173 -0.0692909649383465
endloop
endfacet
facet normal 0.0 0.290284677254462 -0.9569403357322089
outer loop
vertex 0.279 0.014631774151209618 -0.07355889603024227
vertex 0.279 0.02870125742738173 -0.0692909649383465
vertex 0.281 0.014631774151209618 -0.07355889603024227
endloop
endfacet
facet normal 0.0 0.290284677254462 -0.9569403357322089
outer loop
vertex 0.281 0.014631774151209618 -0.07355889603024227
vertex 0.279 0.02870125742738173 -0.0692909649383465
vertex 0.281 0.02870125742738173 -0.0692909649383465
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.281 0.014631774151209618 -0.07355889603024227
vertex 0.281 0.02870125742738173 -0.0692909649383465
vertex 0.281 0.000729344721834839 -0.0036666635234538104
endloop
endfacet
facet normal 0.9999999999999999 -0.0 -0.0
outer loop
vertex 0.281 0.000729344721834839 -0.0036666635234538104
vertex 0.281 0.02870125742738173 -0.0692909649383465
vertex 0.281 0.0014306611350307975 -0.0034539215153514195
endloop
endfacet
facet normal -1.9864785161459324e-16 -0.2902846772544627 0.9569403357322088
outer loop
vertex 0.281 0.000729344721834839 -0.0036666635234538104
vertex 0.281 0.0014306611350307975 -0.0034539215153514195
vertex 0.279 0.000729344721834839 -0.003666663523453811
endloop
endfacet
facet normal -2.075033581879736e-16 -0.2902846772544627 0.9569403357322088
outer loop
vertex 0.279 0.000729344721834839 -0.003666663523453811
vertex 0.281 0.0014306611350307975 -0.0034539215153514195
vertex 0.279 0.0014306611350307975 -0.00345392151535142
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex 0.279 0.0014306611350307975 -0.00345392151535142
vertex 0.279 0.00207699804313153 -0.0031084472403955753
vertex 0.279 0.02870125742738173 -0.0692909649383465
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex 0.279 0.02870125742738173 -0.0692909649383465
vertex 0.279 0.00207699804313153 -0.0031084472403955753
vertex 0.279 0.04166776747647016 -0.062360220922690876
endloop
endfacet
facet normal 0.0 0.4713967368259979 -0.8819212643483549
outer loop
vertex 0.279 0.02870125742738173 -0.0692909649383465
vertex 0.279 0.04166776747647016 -0.062360220922690876
vertex 0.281 0.02870125742738173 -0.0692909649383465
endloop
endfacet
facet normal 0.0 0.4713967368259979 -0.8819212643483549
outer loop
vertex 0.281 0.02870125742738173 -0.0692909649383465
vertex 0.279 0.04166776747647016 -0.062360220922690876
vertex 0.281 0.04166776747647016 -0.062360220922690876
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.281 0.02870125742738173 -0.0692909649383465
vertex 0.281 0.04166776747647016 -0.062360220922690876
vertex 0.281 0.0014306611350307975 -0.0034539215153514195
endloop
endfacet
facet normal 1.0 -0.0 -0.0
outer loop
vertex 0.281 0.0014306611350307975 -0.0034539215153514195
vertex 0.281 0.04166776747647016 -0.062360220922690876
vertex 0.281 0.00207699804313153 -0.003108447240395575
endloop
endfacet
facet normal -1.805889560132667e-16 -0.4713967368259973 0.8819212643483553
outer loop
vertex 0.281 0.0014306611350307975 -0.0034539215153514195
vertex 0.281 0.00207699804313153 -0.003108447240395575
vertex 0.279 0.0014306611350307975 -0.00345392151535142
endloop
endfacet
facet normal -1.9123619015352973e-16 -0.4713967368259973 0.8819212643483553
outer loop
vertex 0.279 0.0014306611350307975 -0.00345392151535142
vertex 0.281 0.00207699804313153 -0.003108447240395575
vertex 0.279 0.00207699804313153 -0.0031084472403955753
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex 0.279 0.00207699804313153 -0.0031084472403955753
vertex 0.279 0.00264351708122864 -0.0026435170812286234
vertex 0.279 0.04166776747647016 -0.062360220922690876
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex 0.279 0.04166776747647016 -0.062360220922690876
vertex 0.279 0.00264351708122864 -0.0026435170812286234
vertex 0.279 0.05303300858899106 -0.05303300858899105
endloop
endfacet
facet normal 0.0 0.6343932841636455 -0.7730104533627369
outer loop
vertex 0.279 0.04166776747647016 -0.062360220922690876
vertex 0.279 0.05303300858899106 -0.05303300858899105
vertex 0.281 0.04166776747647016 -0.062360220922690876
endloop
endfacet
facet normal 0.0 0.6343932841636455 -0.7730104533627369
outer loop
vertex 0.281 0.04166776747647016 -0.062360220922690876
vertex 0.279 0.05303300858899106 -0.05303300858899105
vertex 0.281 0.05303300858899106 -0.05303300858899105
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.281 0.04166776747647016 -0.062360220922690876
vertex 0.281 0.05303300858899106 -0.05303300858899105
vertex 0.281 0.00207699804313153 -0.003108447240395575
endloop
endfacet
facet normal 1.0 -0.0 -0.0
outer loop
vertex 0.281 0.00207699804313153 -0.003108447240395575
vertex 0.281 0.05303300858899106 -0.05303300858899105
vertex 0.281 0.00264351708122864 -0.002643517081228623
endloop
endfacet
facet normal -1.444711648106133e-16 -0.6343932841636455 0.773010453362737
outer loop
vertex 0.281 0.00207699804313153 -0.003108447240395575
vertex 0.281 0.00264351708122864 -0.002643517081228623
vertex 0.279 0.00207699804313153 -0.0031084472403955753
endloop
endfacet
facet normal -1.6761992257797667e-16 -0.6343932841636455 0.773010453362737
outer loop
vertex 0.279 0.00207699804313153 -0.0031084472403955753
vertex 0.281 0.00264351708122864 -0.002643517081228623
vertex 0.279 0.00264351708122864 -0.0026435170812286234
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex 0.279 0.00264351708122864 -0.0026435170812286234
vertex 0.279 0.003108447240395592 -0.0020769980431315136
vertex 0.279 0.05303300858899106 -0.05303300858899105
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex 0.279 0.05303300858899106 -0.05303300858899105
vertex 0.279 0.003108447240395592 -0.0020769980431315136
vertex 0.279 0.06236022092269089 -0.041667767476470156
endloop
endfacet
facet normal 0.0 0.7730104533627367 -0.6343932841636458
outer loop
vertex 0.279 0.05303300858899106 -0.05303300858899105
vertex 0.279 0.06236022092269089 -0.041667767476470156
vertex 0.281 0.05303300858899106 -0.05303300858899105
endloop
endfacet
facet normal 0.0 0.7730104533627367 -0.6343932841636458
outer loop
vertex 0.281 0.05303300858899106 -0.05303300858899105
vertex 0.279 0.06236022092269089 -0.041667767476470156
vertex 0.281 0.06236022092269089 -0.041667767476470156
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.281 0.05303300858899106 -0.05303300858899105
vertex 0.281 0.06236022092269089 -0.041667767476470156
vertex 0.281 0.00264351708122864 -0.002643517081228623
endloop
endfacet
facet normal 0.9999999999999999 -0.0 -0.0
outer loop
vertex 0.281 0.00264351708122864 -0.002643517081228623
vertex 0.281 0.06236022092269089 -0.041667767476470156
vertex 0.281 0.003108447240395592 -0.002076998043131513
endloop
endfacet
facet normal -1.4447116481061325e-16 -0.7730104533627367 0.6343932841636458
outer loop
vertex 0.281 0.00264351708122864 -0.002643517081228623
vertex 0.281 0.003108447240395592 -0.002076998043131513
vertex 0.279 0.00264351708122864 -0.0026435170812286234
endloop
endfacet
facet normal -1.3756211538008763e-16 -0.7730104533627367 0.6343932841636458
outer loop
vertex 0.279 0.00264351708122864 -0.0026435170812286234
vertex 0.281 0.003108447240395592 -0.002076998043131513
vertex 0.279 0.003108447240395592 -0.0020769980431315136
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex 0.279 0.003108447240395592 -0.0020769980431315136
vertex 0.279 0.003453921515351437 -0.0014306611350307806
vertex 0.279 0.06236022092269089 -0.041667767476470156
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex 0.279 0.06236022092269089 -0.041667767476470156
vertex 0.279 0.003453921515351437 -0.0014306611350307806
vertex 0.279 0.06929096493834651 -0.028701257427381718
endloop
endfacet
facet normal 0.0 0.881921264348355 -0.47139673682599775
outer loop
vertex 0.279 0.06236022092269089 -0.041667767476470156
vertex 0.279 0.06929096493834651 -0.028701257427381718
vertex 0.281 0.06236022092269089 -0.041667767476470156
endloop
endfacet
facet normal 0.0 0.881921264348355 -0.47139673682599775
outer loop
vertex 0.281 0.06236022092269089 -0.041667767476470156
vertex 0.279 0.06929096493834651 -0.028701257427381718
vertex 0.281 0.06929096493834651 -0.028701257427381718
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.281 0.06236022092269089 -0.041667767476470156
vertex 0.281 0.06929096493834651 -0.028701257427381718
vertex 0.281 0.003108447240395592 -0.002076998043131513
endloop
endfacet
facet normal 0.9999999999999999 -0.0 -0.0
outer loop
vertex 0.281 0.003108447240395592 -0.002076998043131513
vertex 0.281 0.06929096493834651 -0.028701257427381718
vertex 0.281 0.003453921515351437 -0.0014306611350307806
endloop
endfacet
facet normal -9.029447800663335e-17 -0.8819212643483553 0.4713967368259973
outer loop
vertex 0.281 0.003108447240395592 -0.002076998043131513
vertex 0.281 0.003453921515351437 -0.0014306611350307806
vertex 0.279 0.003108447240395592 -0.0020769980431315136
endloop
endfacet
facet normal 0.0 -0.8819212643483554 0.4713967368259971
outer loop
vertex 0.279 0.003108447240395592 -0.0020769980431315136
vertex 0.281 0.003453921515351437 -0.0014306611350307806
vertex 0.279 0.003453921515351437 -0.0014306611350307806
endloop
endfacet
facet normal -0.9999999999999999 0.0 0.0
outer loop
vertex 0.279 0.003453921515351437 -0.0014306611350307806
vertex 0.279 0.0036666635234538277 -0.0007293447218348221
vertex 0.279 0.06929096493834651 -0.028701257427381718
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex 0.279 0.06929096493834651 -0.028701257427381718
vertex 0.279 0.0036666635234538277 -0.0007293447218348221
vertex 0.279 0.07355889603024228 -0.014631774151209608
endloop
endfacet
facet normal 0.0 0.9569403357322089 -0.29028467725446205
outer loop
vertex 0.279 0.06929096493834651 -0.028701257427381718
vertex 0.279 0.07355889603024228 -0.014631774151209608
vertex 0.281 0.06929096493834651 -0.028701257427381718
endloop
endfacet
facet normal 0.0 0.9569403357322089 -0.29028467725446205
outer loop
vertex 0.281 0.06929096493834651 -0.028701257427381718
vertex 0.279 0.07355889603024228 -0.014631774151209608
vertex 0.281 0.07355889603024228 -0.014631774151209608
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.281 0.06929096493834651 -0.028701257427381718
vertex 0.281 0.07355889603024228 -0.014631774151209608
vertex 0.281 0.003453921515351437 -0.0014306611350307806
endloop
endfacet
facet normal 1.0 -0.0 -0.0
outer loop
vertex 0.281 0.003453921515351437 -0.0014306611350307806
vertex 0.281 0.07355889603024228 -0.014631774151209608
vertex 0.281 0.0036666635234538277 -0.000729344721834822
endloop
endfacet
facet normal 0.0 -0.9569403357322088 0.29028467725446266
outer loop
vertex 0.281 0.003453921515351437 -0.0014306611350307806
vertex 0.281 0.0036666635234538277 -0.000729344721834822
vertex 0.279 0.003453921515351437 -0.0014306611350307806
endloop
endfacet
facet normal -1.5736363885927084e-17 -0.9569403357322088 0.2902846772544627
outer loop
vertex 0.279 0.003453921515351437 -0.0014306611350307806
vertex 0.281 0.0036666635234538277 -0.000729344721834822
vertex 0.279 0.0036666635234538277 -0.0007293447218348221
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex 0.279 0.0036666635234538277 -0.0007293447218348221
vertex 0.279 0.0037384977086384816 1.685490588548039e-17
vertex 0.279 0.07355889603024228 -0.014631774151209608
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex 0.279 0.07355889603024228 -0.014631774151209608
vertex 0.279 0.0037384977086384816 1.685490588548039e-17
vertex 0.279 0.075 1.2491397351303004e-17
endloop
endfacet
facet normal 0.0 0.9951847266721969 -0.0980171403295607
outer loop
vertex 0.279 0.07355889603024228 -0.014631774151209608
vertex 0.279 0.075 1.2491397351303004e-17
vertex 0.281 0.07355889603024228 -0.014631774151209608
endloop
endfacet
facet normal 6.001818858308654e-18 0.9951847266721969 -0.0980171403295607
outer loop
vertex 0.281 0.07355889603024228 -0.014631774151209608
vertex 0.279 0.075 1.2491397351303004e-17
vertex 0.281 0.075 1.261386203121774e-17
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.281 0.07355889603024228 -0.014631774151209608
vertex 0.281 0.075 1.261386203121774e-17
vertex 0.281 0.0036666635234538277 -0.000729344721834822
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.281 0.0036666635234538277 -0.000729344721834822
vertex 0.281 0.075 1.261386203121774e-17
vertex 0.281 0.0037384977086384816 1.6977370565395124e-17
endloop
endfacet
facet normal -4.514723900331666e-18 -0.9951847266721969 0.09801714032956056
outer loop
vertex 0.281 0.0036666635234538277 -0.000729344721834822
vertex 0.281 0.0037384977086384816 1.6977370565395124e-17
vertex 0.279 0.0036666635234538277 -0.0007293447218348221
endloop
endfacet
facet normal -6.001818858308646e-18 -0.9951847266721969 0.09801714032956056
outer loop
vertex 0.279 0.0036666635234538277 -0.0007293447218348221
vertex 0.281 0.0037384977086384816 1.6977370565395124e-17
vertex 0.279 0.0037384977086384816 1.685490588548039e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex 0.279 0.0037384977086384816 1.685490588548039e-17
vertex 0.279 0.0036666635234538277 0.0007293447218348559
vertex 0.279 0.075 1.2491397351303004e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex 0.279 0.075 1.2491397351303004e-17
vertex 0.279 0.0036666635234538277 0.0007293447218348559
vertex 0.279 0.07355889603024228 0.014631774151209632
endloop
endfacet
facet normal 0.0 0.9951847266721969 0.0980171403295607
outer loop
vertex 0.279 0.075 1.2491397351303004e-17
vertex 0.279 0.07355889603024228 0.014631774151209632
vertex 0.281 0.075 1.261386203121774e-17
endloop
endfacet
facet normal -0.0 0.9951847266721969 0.0980171403295607
outer loop
vertex 0.281 0.075 1.261386203121774e-17
vertex 0.279 0.07355889603024228 0.014631774151209632
vertex 0.281 0.07355889603024228 0.014631774151209632
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.281 0.075 1.261386203121774e-17
vertex 0.281 0.07355889603024228 0.014631774151209632
vertex 0.281 0.0037384977086384816 1.6977370565395124e-17
endloop
endfacet
facet normal 0.9999999999999999 0.0 -0.0
outer loop
vertex 0.281 0.0037384977086384816 1.6977370565395124e-17
vertex 0.281 0.07355889603024228 0.014631774151209632
vertex 0.281 0.0036666635234538277 0.000729344721834856
endloop
endfacet
facet normal 1.3544171700994998e-17 -0.9951847266721969 -0.09801714032956056
outer loop
vertex 0.281 0.0037384977086384816 1.6977370565395124e-17
vertex 0.281 0.0036666635234538277 0.000729344721834856
vertex 0.279 0.0037384977086384816 1.685490588548039e-17
endloop
endfacet
facet normal 5.3135198243062995e-18 -0.9951847266721969 -0.09801714032956055
outer loop
vertex 0.279 0.0037384977086384816 1.685490588548039e-17
vertex 0.281 0.0036666635234538277 0.000729344721834856
vertex 0.279 0.0036666635234538277 0.0007293447218348559
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex 0.279 0.0036666635234538277 0.0007293447218348559
vertex 0.279 0.003453921515351437 0.0014306611350308144
vertex 0.279 0.07355889603024228 0.014631774151209632
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex 0.279 0.07355889603024228 0.014631774151209632
vertex 0.279 0.003453921515351437 0.0014306611350308144
vertex 0.279 0.06929096493834651 0.028701257427381745
endloop
endfacet
facet normal 0.0 0.9569403357322089 0.290284677254462
outer loop
vertex 0.279 0.07355889603024228 0.014631774151209632
vertex 0.279 0.06929096493834651 0.028701257427381745
vertex 0.281 0.07355889603024228 0.014631774151209632
endloop
endfacet
facet normal -0.0 0.9569403357322089 0.290284677254462
outer loop
vertex 0.281 0.07355889603024228 0.014631774151209632
vertex 0.279 0.06929096493834651 0.028701257427381745
vertex 0.281 0.06929096493834651 0.028701257427381745
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.281 0.07355889603024228 0.014631774151209632
vertex 0.281 0.06929096493834651 0.028701257427381745
vertex 0.281 0.0036666635234538277 0.000729344721834856
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.281 0.0036666635234538277 0.000729344721834856
vertex 0.281 0.06929096493834651 0.028701257427381745
vertex 0.281 0.003453921515351437 0.0014306611350308144
endloop
endfacet
facet normal 1.8058895601326663e-17 -0.9569403357322088 -0.2902846772544628
outer loop
vertex 0.281 0.0036666635234538277 0.000729344721834856
vertex 0.281 0.003453921515351437 0.0014306611350308144
vertex 0.279 0.0036666635234538277 0.0007293447218348559
endloop
endfacet
facet normal -0.0 -0.9569403357322088 -0.2902846772544627
outer loop
vertex 0.279 0.0036666635234538277 0.0007293447218348559
vertex 0.281 0.003453921515351437 0.0014306611350308144
vertex 0.279 0.003453921515351437 0.0014306611350308144
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex 0.279 0.003453921515351437 0.0014306611350308144
vertex 0.279 0.0031084472403955926 0.002076998043131546
vertex 0.279 0.06929096493834651 0.028701257427381745
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex 0.279 0.06929096493834651 0.028701257427381745
vertex 0.279 0.0031084472403955926 0.002076998043131546
vertex 0.279 0.062360220922690904 0.041667767476470156
endloop
endfacet
facet normal 0.0 0.881921264348355 0.4713967368259978
outer loop
vertex 0.279 0.06929096493834651 0.028701257427381745
vertex 0.279 0.062360220922690904 0.041667767476470156
vertex 0.281 0.06929096493834651 0.028701257427381745
endloop
endfacet
facet normal -0.0 0.881921264348355 0.4713967368259978
outer loop
vertex 0.281 0.06929096493834651 0.028701257427381745
vertex 0.279 0.062360220922690904 0.041667767476470156
vertex 0.281 0.062360220922690904 0.041667767476470156
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.281 0.06929096493834651 0.028701257427381745
vertex 0.281 0.062360220922690904 0.041667767476470156
vertex 0.281 0.003453921515351437 0.0014306611350308144
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.281 0.003453921515351437 0.0014306611350308144
vertex 0.281 0.062360220922690904 0.041667767476470156
vertex 0.281 0.0031084472403955926 0.0020769980431315466
endloop
endfacet
facet normal 0.0 -0.8819212643483553 -0.4713967368259971
outer loop
vertex 0.281 0.003453921515351437 0.0014306611350308144
vertex 0.281 0.0031084472403955926 0.0020769980431315466
vertex 0.279 0.003453921515351437 0.0014306611350308144
endloop
endfacet
facet normal 1.0221787323386469e-16 -0.8819212643483553 -0.47139673682599736
outer loop
vertex 0.279 0.003453921515351437 0.0014306611350308144
vertex 0.281 0.0031084472403955926 0.0020769980431315466
vertex 0.279 0.0031084472403955926 0.002076998043131546
endloop
endfacet
facet normal -0.9999999999999999 0.0 0.0
outer loop
vertex 0.279 0.0031084472403955926 0.002076998043131546
vertex 0.279 0.0026435170812286403 0.002643517081228657
vertex 0.279 0.062360220922690904 0.041667767476470156
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex 0.279 0.062360220922690904 0.041667767476470156
vertex 0.279 0.0026435170812286403 0.002643517081228657
vertex 0.279 0.053033008588991064 0.05303300858899107
endloop
endfacet
facet normal 0.0 0.7730104533627371 0.6343932841636455
outer loop
vertex 0.279 0.062360220922690904 0.041667767476470156
vertex 0.279 0.053033008588991064 0.05303300858899107
vertex 0.281 0.062360220922690904 0.041667767476470156
endloop
endfacet
facet normal -0.0 0.7730104533627371 0.6343932841636455
outer loop
vertex 0.281 0.062360220922690904 0.041667767476470156
vertex 0.279 0.053033008588991064 0.05303300858899107
vertex 0.281 0.053033008588991064 0.05303300858899107
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.281 0.062360220922690904 0.041667767476470156
vertex 0.281 0.053033008588991064 0.05303300858899107
vertex 0.281 0.0031084472403955926 0.0020769980431315466
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex 0.281 0.0031084472403955926 0.0020769980431315466
vertex 0.281 0.053033008588991064 0.05303300858899107
vertex 0.281 0.0026435170812286403 0.0026435170812286572
endloop
endfacet
facet normal 1.4447116481061313e-16 -0.7730104533627372 -0.6343932841636453
outer loop
vertex 0.281 0.0031084472403955926 0.0020769980431315466
vertex 0.281 0.0026435170812286403 0.0026435170812286572
vertex 0.279 0.0031084472403955926 0.002076998043131546
endloop
endfacet
facet normal 1.3756211538008753e-16 -0.7730104533627372 -0.6343932841636453
outer loop
vertex 0.279 0.0031084472403955926 0.002076998043131546
vertex 0.281 0.0026435170812286403 0.0026435170812286572
vertex 0.279 0.0026435170812286403 0.002643517081228657
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex 0.279 0.0026435170812286403 0.002643517081228657
vertex 0.279 0.00207699804313153 0.0031084472403956095
vertex 0.279 0.053033008588991064 0.05303300858899107
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex 0.279 0.053033008588991064 0.05303300858899107
vertex 0.279 0.00207699804313153 0.0031084472403956095
vertex 0.279 0.04166776747647016 0.06236022092269091
endloop
endfacet
facet normal 0.0 0.6343932841636459 0.7730104533627367
outer loop
vertex 0.279 0.053033008588991064 0.05303300858899107
vertex 0.279 0.04166776747647016 0.06236022092269091
vertex 0.281 0.053033008588991064 0.05303300858899107
endloop
endfacet
facet normal -0.0 0.6343932841636459 0.7730104533627367
outer loop
vertex 0.281 0.053033008588991064 0.05303300858899107
vertex 0.279 0.04166776747647016 0.06236022092269091
vertex 0.281 0.04166776747647016 0.06236022092269091
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.281 0.053033008588991064 0.05303300858899107
vertex 0.281 0.04166776747647016 0.06236022092269091
vertex 0.281 0.0026435170812286403 0.0026435170812286572
endloop
endfacet
facet normal 0.9999999999999999 0.0 -0.0
outer loop
vertex 0.281 0.0026435170812286403 0.0026435170812286572
vertex 0.281 0.04166776747647016 0.06236022092269091
vertex 0.281 0.00207699804313153 0.00310844724039561
endloop
endfacet
facet normal 1.4447116481061313e-16 -0.6343932841636459 -0.7730104533627365
outer loop
vertex 0.281 0.0026435170812286403 0.0026435170812286572
vertex 0.281 0.00207699804313153 0.00310844724039561
vertex 0.279 0.0026435170812286403 0.002643517081228657
endloop
endfacet
facet normal 1.676199225779766e-16 -0.6343932841636459 -0.7730104533627365
outer loop
vertex 0.279 0.0026435170812286403 0.002643517081228657
vertex 0.281 0.00207699804313153 0.00310844724039561
vertex 0.279 0.00207699804313153 0.0031084472403956095
endloop
endfacet
facet normal -0.9999999999999999 0.0 0.0
outer loop
vertex 0.279 0.00207699804313153 0.0031084472403956095
vertex 0.279 0.001430661135030798 0.0034539215153514538
vertex 0.279 0.04166776747647016 0.06236022092269091
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex 0.279 0.04166776747647016 0.06236022092269091
vertex 0.279 0.001430661135030798 0.0034539215153514538
vertex 0.279 0.028701257427381742 0.06929096493834652
endloop
endfacet
facet normal 0.0 0.4713967368259978 0.8819212643483548
outer loop
vertex 0.279 0.04166776747647016 0.06236022092269091
vertex 0.279 0.028701257427381742 0.06929096493834652
vertex 0.281 0.04166776747647016 0.06236022092269091
endloop
endfacet
facet normal -0.0 0.4713967368259978 0.8819212643483548
outer loop
vertex 0.281 0.04166776747647016 0.06236022092269091
vertex 0.279 0.028701257427381742 0.06929096493834652
vertex 0.281 0.028701257427381742 0.06929096493834652
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.281 0.04166776747647016 0.06236022092269091
vertex 0.281 0.028701257427381742 0.06929096493834652
vertex 0.281 0.00207699804313153 0.00310844724039561
endloop
endfacet
facet normal 0.9999999999999999 0.0 -0.0
outer loop
vertex 0.281 0.00207699804313153 0.00310844724039561
vertex 0.281 0.028701257427381742 0.06929096493834652
vertex 0.281 0.001430661135030798 0.003453921515351454
endloop
endfacet
facet normal 1.8058895601326682e-16 -0.4713967368259971 -0.8819212643483553
outer loop
vertex 0.281 0.00207699804313153 0.00310844724039561
vertex 0.281 0.001430661135030798 0.003453921515351454
vertex 0.279 0.00207699804313153 0.0031084472403956095
endloop
endfacet
facet normal 1.9123619015352973e-16 -0.4713967368259971 -0.8819212643483553
outer loop
vertex 0.279 0.00207699804313153 0.0031084472403956095
vertex 0.281 0.001430661135030798 0.003453921515351454
vertex 0.279 0.001430661135030798 0.0034539215153514538
endloop
endfacet
facet normal -0.9999999999999999 0.0 0.0
outer loop
vertex 0.279 0.001430661135030798 0.0034539215153514538
vertex 0.279 0.0007293447218348403 0.0036666635234538446
vertex 0.279 0.028701257427381742 0.06929096493834652
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex 0.279 0.028701257427381742 0.06929096493834652
vertex 0.279 0.0007293447218348403 0.0036666635234538446
vertex 0.279 0.014631774151209646 0.0735588960302423
endloop
endfacet
facet normal 0.0 0.2902846772544624 0.956940335732209
outer loop
vertex 0.279 0.028701257427381742 0.06929096493834652
vertex 0.279 0.014631774151209646 0.0735588960302423
vertex 0.281 0.028701257427381742 0.06929096493834652
endloop
endfacet
facet normal -0.0 0.2902846772544624 0.956940335732209
outer loop
vertex 0.281 0.028701257427381742 0.06929096493834652
vertex 0.279 0.014631774151209646 0.0735588960302423
vertex 0.281 0.014631774151209646 0.0735588960302423
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.281 0.028701257427381742 0.06929096493834652
vertex 0.281 0.014631774151209646 0.0735588960302423
vertex 0.281 0.001430661135030798 0.003453921515351454
endloop
endfacet
facet normal 0.9999999999999999 0.0 -0.0
outer loop
vertex 0.281 0.001430661135030798 0.003453921515351454
vertex 0.281 0.014631774151209646 0.0735588960302423
vertex 0.281 0.0007293447218348403 0.003666663523453845
endloop
endfacet
facet normal 1.986478516145935e-16 -0.29028467725446305 -0.9569403357322088
outer loop
vertex 0.281 0.001430661135030798 0.003453921515351454
vertex 0.281 0.0007293447218348403 0.003666663523453845
vertex 0.279 0.001430661135030798 0.0034539215153514538
endloop
endfacet
facet normal 2.0750335818797356e-16 -0.29028467725446305 -0.9569403357322088
outer loop
vertex 0.279 0.001430661135030798 0.0034539215153514538
vertex 0.281 0.0007293447218348403 0.003666663523453845
vertex 0.279 0.0007293447218348403 0.0036666635234538446
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex 0.279 0.0007293447218348403 0.0036666635234538446
vertex 0.279 4.5783392525038305e-19 0.0037384977086384985
vertex 0.279 0.014631774151209646 0.0735588960302423
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex 0.279 0.014631774151209646 0.0735588960302423
vertex 0.279 4.5783392525038305e-19 0.0037384977086384985
vertex 0.279 9.184850993605149e-18 0.07500000000000001
endloop
endfacet
facet normal 0.0 0.09801714032956059 0.995184726672197
outer loop
vertex 0.279 0.014631774151209646 0.0735588960302423
vertex 0.279 9.184850993605149e-18 0.07500000000000001
vertex 0.281 0.014631774151209646 0.0735588960302423
endloop
endfacet
facet normal -0.0 0.09801714032956059 0.995184726672197
outer loop
vertex 0.281 0.014631774151209646 0.0735588960302423
vertex 0.279 9.184850993605149e-18 0.07500000000000001
vertex 0.281 9.184850993605149e-18 0.07500000000000001
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.281 0.014631774151209646 0.0735588960302423
vertex 0.281 9.184850993605149e-18 0.07500000000000001
vertex 0.281 0.0007293447218348403 0.003666663523453845
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.281 0.0007293447218348403 0.003666663523453845
vertex 0.281 9.184850993605149e-18 0.07500000000000001
vertex 0.281 4.5783392525038305e-19 0.003738497708638499
endloop
endfacet
facet normal 2.1219202331558804e-16 -0.09801714032956045 -0.9951847266721969
outer loop
vertex 0.281 0.0007293447218348403 0.003666663523453845
vertex 0.281 4.5783392525038305e-19 0.003738497708638499
vertex 0.279 0.0007293447218348403 0.0036666635234538446
endloop
endfacet
facet normal 2.1579628853647757e-16 -0.09801714032956044 -0.9951847266721969
outer loop
vertex 0.279 0.0007293447218348403 0.0036666635234538446
vertex 0.281 4.5783392525038305e-19 0.003738497708638499
vertex 0.279 4.5783392525038305e-19 0.0037384977086384985
endloop
endfacet
facet normal -0.9999999999999999 -0.0 0.0
outer loop
vertex 0.279 4.5783392525038305e-19 0.0037384977086384985
vertex 0.279 -0.0007293447218348393 0.0036666635234538446
vertex 0.279 9.184850993605149e-18 0.07500000000000001
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex 0.279 9.184850993605149e-18 0.07500000000000001
vertex 0.279 -0.0007293447218348393 0.0036666635234538446
vertex 0.279 -0.014631774151209627 0.0735588960302423
endloop
endfacet
facet normal 0.0 -0.09801714032956059 0.9951847266721969
outer loop
vertex 0.279 9.184850993605149e-18 0.07500000000000001
vertex 0.279 -0.014631774151209627 0.0735588960302423
vertex 0.281 9.184850993605149e-18 0.07500000000000001
endloop
endfacet
facet normal 0.0 -0.09801714032956059 0.9951847266721969
outer loop
vertex 0.281 9.184850993605149e-18 0.07500000000000001
vertex 0.279 -0.014631774151209627 0.0735588960302423
vertex 0.281 -0.014631774151209627 0.0735588960302423
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.281 9.184850993605149e-18 0.07500000000000001
vertex 0.281 -0.014631774151209627 0.0735588960302423
vertex 0.281 4.5783392525038305e-19 0.003738497708638499
endloop
endfacet
facet normal 0.9999999999999999 0.0 0.0
outer loop
vertex 0.281 4.5783392525038305e-19 0.003738497708638499
vertex 0.281 -0.014631774151209627 0.0735588960302423
vertex 0.281 -0.0007293447218348393 0.003666663523453845
endloop
endfacet
facet normal 2.1670674721591977e-16 0.09801714032956048 -0.995184726672197
outer loop
vertex 0.281 4.5783392525038305e-19 0.003738497708638499
vertex 0.281 -0.0007293447218348393 0.003666663523453845
vertex 0.279 4.5783392525038305e-19 0.0037384977086384985
endloop
endfacet
facet normal 2.1579628853647762e-16 0.09801714032956048 -0.995184726672197
outer loop
vertex 0.279 4.5783392525038305e-19 0.0037384977086384985
vertex 0.281 -0.0007293447218348393 0.003666663523453845
vertex 0.279 -0.0007293447218348393 0.0036666635234538446
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex 0.279 -0.0007293447218348393 0.0036666635234538446
vertex 0.279 -0.001430661135030797 0.003453921515351454
vertex 0.279 -0.014631774151209627 0.0735588960302423
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex 0.279 -0.014631774151209627 0.0735588960302423
vertex 0.279 -0.001430661135030797 0.003453921515351454
vertex 0.279 -0.028701257427381725 0.06929096493834652
endloop
endfacet
facet normal 0.0 -0.2902846772544622 0.9569403357322087
outer loop
vertex 0.279 -0.014631774151209627 0.0735588960302423
vertex 0.279 -0.028701257427381725 0.06929096493834652
vertex 0.281 -0.014631774151209627 0.0735588960302423
endloop
endfacet
facet normal 0.0 -0.2902846772544622 0.9569403357322087
outer loop
vertex 0.281 -0.014631774151209627 0.0735588960302423
vertex 0.279 -0.028701257427381725 0.06929096493834652
vertex 0.281 -0.028701257427381725 0.06929096493834652
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.281 -0.014631774151209627 0.0735588960302423
vertex 0.281 -0.028701257427381725 0.06929096493834652
vertex 0.281 -0.0007293447218348393 0.003666663523453845
endloop
endfacet
facet normal 0.9999999999999999 0.0 0.0
outer loop
vertex 0.281 -0.0007293447218348393 0.003666663523453845
vertex 0.281 -0.028701257427381725 0.06929096493834652
vertex 0.281 -0.001430661135030797 0.0034539215153514546
endloop
endfacet
facet normal 2.1670674721592016e-16 0.29028467725446244 -0.9569403357322089
outer loop
vertex 0.281 -0.0007293447218348393 0.003666663523453845
vertex 0.281 -0.001430661135030797 0.0034539215153514546
vertex 0.279 -0.0007293447218348393 0.0036666635234538446
endloop
endfacet
facet normal 2.0750335818797361e-16 0.29028467725446244 -0.9569403357322089
outer loop
vertex 0.279 -0.0007293447218348393 0.0036666635234538446
vertex 0.281 -0.001430661135030797 0.0034539215153514546
vertex 0.279 -0.001430661135030797 0.003453921515351454
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex 0.279 -0.001430661135030797 0.003453921515351454
vertex 0.279 -0.002076998043131529 0.0031084472403956095
vertex 0.279 -0.028701257427381725 0.06929096493834652
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex 0.279 -0.028701257427381725 0.06929096493834652
vertex 0.279 -0.002076998043131529 0.0031084472403956095
vertex 0.279 -0.04166776747647014 0.06236022092269092
endloop
endfacet
facet normal 0.0 -0.47139673682599764 0.8819212643483552
outer loop
vertex 0.279 -0.028701257427381725 0.06929096493834652
vertex 0.279 -0.04166776747647014 0.06236022092269092
vertex 0.281 -0.028701257427381725 0.06929096493834652
endloop
endfacet
facet normal 0.0 -0.47139673682599764 0.8819212643483552
outer loop
vertex 0.281 -0.028701257427381725 0.06929096493834652
vertex 0.279 -0.04166776747647014 0.06236022092269092
vertex 0.281 -0.04166776747647014 0.06236022092269092
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.281 -0.028701257427381725 0.06929096493834652
vertex 0.281 -0.04166776747647014 0.06236022092269092
vertex 0.281 -0.001430661135030797 0.0034539215153514546
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.281 -0.001430661135030797 0.0034539215153514546
vertex 0.281 -0.04166776747647014 0.06236022092269092
vertex 0.281 -0.002076998043131529 0.00310844724039561
endloop
endfacet
facet normal 1.8058895601326677e-16 0.47139673682599753 -0.8819212643483552
outer loop
vertex 0.281 -0.001430661135030797 0.0034539215153514546
vertex 0.281 -0.002076998043131529 0.00310844724039561
vertex 0.279 -0.001430661135030797 0.003453921515351454
endloop
endfacet
facet normal 1.912361901535297e-16 0.47139673682599753 -0.8819212643483552
outer loop
vertex 0.279 -0.001430661135030797 0.003453921515351454
vertex 0.281 -0.002076998043131529 0.00310844724039561
vertex 0.279 -0.002076998043131529 0.0031084472403956095
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex 0.279 -0.002076998043131529 0.0031084472403956095
vertex 0.279 -0.00264351708122864 0.0026435170812286577
vertex 0.279 -0.04166776747647014 0.06236022092269092
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex 0.279 -0.04166776747647014 0.06236022092269092
vertex 0.279 -0.00264351708122864 0.0026435170812286577
vertex 0.279 -0.05303300858899106 0.05303300858899109
endloop
endfacet
facet normal 0.0 -0.6343932841636448 0.7730104533627374
outer loop
vertex 0.279 -0.04166776747647014 0.06236022092269092
vertex 0.279 -0.05303300858899106 0.05303300858899109
vertex 0.281 -0.04166776747647014 0.06236022092269092
endloop
endfacet
facet normal 0.0 -0.6343932841636448 0.7730104533627374
outer loop
vertex 0.281 -0.04166776747647014 0.06236022092269092
vertex 0.279 -0.05303300858899106 0.05303300858899109
vertex 0.281 -0.05303300858899106 0.05303300858899109
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.281 -0.04166776747647014 0.06236022092269092
vertex 0.281 -0.05303300858899106 0.05303300858899109
vertex 0.281 -0.002076998043131529 0.00310844724039561
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.281 -0.002076998043131529 0.00310844724039561
vertex 0.281 -0.05303300858899106 0.05303300858899109
vertex 0.281 -0.00264351708122864 0.002643517081228658
endloop
endfacet
facet normal 1.4447116481061318e-16 0.6343932841636449 -0.7730104533627374
outer loop
vertex 0.281 -0.002076998043131529 0.00310844724039561
vertex 0.281 -0.00264351708122864 0.002643517081228658
vertex 0.279 -0.002076998043131529 0.0031084472403956095
endloop
endfacet
facet normal 1.6761992257797677e-16 0.6343932841636449 -0.7730104533627374
outer loop
vertex 0.279 -0.002076998043131529 0.0031084472403956095
vertex 0.281 -0.00264351708122864 0.002643517081228658
vertex 0.279 -0.00264351708122864 0.0026435170812286577
endloop
endfacet
facet normal -0.9999999999999999 -0.0 0.0
outer loop
vertex 0.279 -0.00264351708122864 0.0026435170812286577
vertex 0.279 -0.003108447240395592 0.002076998043131547
vertex 0.279 -0.05303300858899106 0.05303300858899109
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex 0.279 -0.05303300858899106 0.05303300858899109
vertex 0.279 -0.003108447240395592 0.002076998043131547
vertex 0.279 -0.06236022092269089 0.04166776747647018
endloop
endfacet
facet normal 0.0 -0.7730104533627372 0.6343932841636452
outer loop
vertex 0.279 -0.05303300858899106 0.05303300858899109
vertex 0.279 -0.06236022092269089 0.04166776747647018
vertex 0.281 -0.05303300858899106 0.05303300858899109
endloop
endfacet
facet normal 0.0 -0.7730104533627372 0.6343932841636452
outer loop
vertex 0.281 -0.05303300858899106 0.05303300858899109
vertex 0.279 -0.06236022092269089 0.04166776747647018
vertex 0.281 -0.06236022092269089 0.04166776747647018
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.281 -0.05303300858899106 0.05303300858899109
vertex 0.281 -0.06236022092269089 0.04166776747647018
vertex 0.281 -0.00264351708122864 0.002643517081228658
endloop
endfacet
facet normal 0.9999999999999999 0.0 0.0
outer loop
vertex 0.281 -0.00264351708122864 0.002643517081228658
vertex 0.281 -0.06236022092269089 0.04166776747647018
vertex 0.281 -0.003108447240395592 0.0020769980431315474
endloop
endfacet
facet normal 1.4447116481061313e-16 0.7730104533627372 -0.6343932841636453
outer loop
vertex 0.281 -0.00264351708122864 0.002643517081228658
vertex 0.281 -0.003108447240395592 0.0020769980431315474
vertex 0.279 -0.00264351708122864 0.0026435170812286577
endloop
endfacet
facet normal 1.3756211538008753e-16 0.7730104533627372 -0.6343932841636453
outer loop
vertex 0.279 -0.00264351708122864 0.0026435170812286577
vertex 0.281 -0.003108447240395592 0.0020769980431315474
vertex 0.279 -0.003108447240395592 0.002076998043131547
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex 0.279 -0.003108447240395592 0.002076998043131547
vertex 0.279 -0.003453921515351436 0.0014306611350308168
vertex 0.279 -0.06236022092269089 0.04166776747647018
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex 0.279 -0.06236022092269089 0.04166776747647018
vertex 0.279 -0.003453921515351436 0.0014306611350308168
vertex 0.279 -0.06929096493834648 0.02870125742738179
endloop
endfacet
facet normal 0.0 -0.881921264348355 0.47139673682599775
outer loop
vertex 0.279 -0.06236022092269089 0.04166776747647018
vertex 0.279 -0.06929096493834648 0.02870125742738179
vertex 0.281 -0.06236022092269089 0.04166776747647018
endloop
endfacet
facet normal 0.0 -0.881921264348355 0.47139673682599775
outer loop
vertex 0.281 -0.06236022092269089 0.04166776747647018
vertex 0.279 -0.06929096493834648 0.02870125742738179
vertex 0.281 -0.06929096493834648 0.02870125742738179
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.281 -0.06236022092269089 0.04166776747647018
vertex 0.281 -0.06929096493834648 0.02870125742738179
vertex 0.281 -0.003108447240395592 0.0020769980431315474
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.281 -0.003108447240395592 0.0020769980431315474
vertex 0.281 -0.06929096493834648 0.02870125742738179
vertex 0.281 -0.003453921515351436 0.0014306611350308168
endloop
endfacet
facet normal 1.0835337360796033e-16 0.881921264348355 -0.4713967368259975
outer loop
vertex 0.281 -0.003108447240395592 0.0020769980431315474
vertex 0.281 -0.003453921515351436 0.0014306611350308168
vertex 0.279 -0.003108447240395592 0.002076998043131547
endloop
endfacet
facet normal 0.0 0.881921264348355 -0.47139673682599775
outer loop
vertex 0.279 -0.003108447240395592 0.002076998043131547
vertex 0.281 -0.003453921515351436 0.0014306611350308168
vertex 0.279 -0.003453921515351436 0.0014306611350308168
endloop
endfacet
facet normal -0.9999999999999999 -0.0 0.0
outer loop
vertex 0.279 -0.003453921515351436 0.0014306611350308168
vertex 0.279 -0.0036666635234538273 0.0007293447218348577
vertex 0.279 -0.06929096493834648 0.02870125742738179
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex 0.279 -0.06929096493834648 0.02870125742738179
vertex 0.279 -0.0036666635234538273 0.0007293447218348577
vertex 0.279 -0.07355889603024227 0.014631774151209666
endloop
endfacet
facet normal 0.0 -0.9569403357322088 0.29028467725446266
outer loop
vertex 0.279 -0.06929096493834648 0.02870125742738179
vertex 0.279 -0.07355889603024227 0.014631774151209666
vertex 0.281 -0.06929096493834648 0.02870125742738179
endloop
endfacet
facet normal 0.0 -0.9569403357322088 0.29028467725446266
outer loop
vertex 0.281 -0.06929096493834648 0.02870125742738179
vertex 0.279 -0.07355889603024227 0.014631774151209666
vertex 0.281 -0.07355889603024227 0.014631774151209666
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.281 -0.06929096493834648 0.02870125742738179
vertex 0.281 -0.07355889603024227 0.014631774151209666
vertex 0.281 -0.003453921515351436 0.0014306611350308168
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex 0.281 -0.003453921515351436 0.0014306611350308168
vertex 0.281 -0.07355889603024227 0.014631774151209666
vertex 0.281 -0.0036666635234538273 0.0007293447218348578
endloop
endfacet
facet normal 0.0 0.9569403357322087 -0.29028467725446305
outer loop
vertex 0.281 -0.003453921515351436 0.0014306611350308168
vertex 0.281 -0.0036666635234538273 0.0007293447218348578
vertex 0.279 -0.003453921515351436 0.0014306611350308168
endloop
endfacet
facet normal 1.57363638859271e-17 0.9569403357322087 -0.290284677254463
outer loop
vertex 0.279 -0.003453921515351436 0.0014306611350308168
vertex 0.281 -0.0036666635234538273 0.0007293447218348578
vertex 0.279 -0.0036666635234538273 0.0007293447218348577
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex 0.279 -0.0036666635234538273 0.0007293447218348577
vertex 0.279 -0.0037384977086384816 1.7770573735981155e-17
vertex 0.279 -0.07355889603024227 0.014631774151209666
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex 0.279 -0.07355889603024227 0.014631774151209666
vertex 0.279 -0.0037384977086384816 1.7770573735981155e-17
vertex 0.279 -0.075 3.08610993385133e-17
endloop
endfacet
facet normal 0.0 -0.9951847266721969 0.09801714032956155
outer loop
vertex 0.279 -0.07355889603024227 0.014631774151209666
vertex 0.279 -0.075 3.08610993385133e-17
vertex 0.281 -0.07355889603024227 0.014631774151209666
endloop
endfacet
facet normal -6.001818858308706e-18 -0.9951847266721969 0.09801714032956155
outer loop
vertex 0.281 -0.07355889603024227 0.014631774151209666
vertex 0.279 -0.075 3.08610993385133e-17
vertex 0.281 -0.075 3.0983564018428035e-17
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.281 -0.07355889603024227 0.014631774151209666
vertex 0.281 -0.075 3.0983564018428035e-17
vertex 0.281 -0.0036666635234538273 0.0007293447218348578
endloop
endfacet
facet normal 0.9999999999999999 0.0 0.0
outer loop
vertex 0.281 -0.0036666635234538273 0.0007293447218348578
vertex 0.281 -0.075 3.0983564018428035e-17
vertex 0.281 -0.0037384977086384816 1.789303841589589e-17
endloop
endfacet
facet normal 4.51472390033166e-18 0.9951847266721969 -0.09801714032956103
outer loop
vertex 0.281 -0.0036666635234538273 0.0007293447218348578
vertex 0.281 -0.0037384977086384816 1.789303841589589e-17
vertex 0.279 -0.0036666635234538273 0.0007293447218348577
endloop
endfacet
facet normal 6.001818858308675e-18 0.9951847266721969 -0.09801714032956103
outer loop
vertex 0.279 -0.0036666635234538273 0.0007293447218348577
vertex 0.281 -0.0037384977086384816 1.789303841589589e-17
vertex 0.279 -0.0037384977086384816 1.7770573735981155e-17
endloop
endfacet
facet normal -0.9999999999999999 -0.0 -0.0
outer loop
vertex 0.279 -0.0037384977086384816 1.7770573735981155e-17
vertex 0.279 -0.0036666635234538277 -0.0007293447218348221
vertex 0.279 -0.075 3.08610993385133e-17
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex 0.279 -0.075 3.08610993385133e-17
vertex 0.279 -0.0036666635234538277 -0.0007293447218348221
vertex 0.279 -0.07355889603024228 -0.014631774151209604
endloop
endfacet
facet normal 0.0 -0.9951847266721969 -0.09801714032956059
outer loop
vertex 0.279 -0.075 3.08610993385133e-17
vertex 0.279 -0.07355889603024228 -0.014631774151209604
vertex 0.281 -0.075 3.0983564018428035e-17
endloop
endfacet
facet normal 0.0 -0.9951847266721969 -0.09801714032956059
outer loop
vertex 0.281 -0.075 3.0983564018428035e-17
vertex 0.279 -0.07355889603024228 -0.014631774151209604
vertex 0.281 -0.07355889603024228 -0.014631774151209604
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.281 -0.075 3.0983564018428035e-17
vertex 0.281 -0.07355889603024228 -0.014631774151209604
vertex 0.281 -0.0037384977086384816 1.789303841589589e-17
endloop
endfacet
facet normal 0.9999999999999999 -0.0 0.0
outer loop
vertex 0.281 -0.0037384977086384816 1.789303841589589e-17
vertex 0.281 -0.07355889603024228 -0.014631774151209604
vertex 0.281 -0.0036666635234538277 -0.000729344721834822
endloop
endfacet
facet normal -4.51472390033166e-18 0.9951847266721969 0.09801714032956045
outer loop
vertex 0.281 -0.0037384977086384816 1.789303841589589e-17
vertex 0.281 -0.0036666635234538277 -0.000729344721834822
vertex 0.279 -0.0037384977086384816 1.7770573735981155e-17
endloop
endfacet
facet normal -5.313519824306294e-18 0.9951847266721969 0.09801714032956045
outer loop
vertex 0.279 -0.0037384977086384816 1.7770573735981155e-17
vertex 0.281 -0.0036666635234538277 -0.000729344721834822
vertex 0.279 -0.0036666635234538277 -0.0007293447218348221
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex 0.279 -0.0036666635234538277 -0.0007293447218348221
vertex 0.279 -0.0034539215153514364 -0.0014306611350307812
vertex 0.279 -0.07355889603024228 -0.014631774151209604
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex 0.279 -0.07355889603024228 -0.014631774151209604
vertex 0.279 -0.0034539215153514364 -0.0014306611350307812
vertex 0.279 -0.0692909649383465 -0.02870125742738173
endloop
endfacet
facet normal 0.0 -0.9569403357322088 -0.2902846772544626
outer loop
vertex 0.279 -0.07355889603024228 -0.014631774151209604
vertex 0.279 -0.0692909649383465 -0.02870125742738173
vertex 0.281 -0.07355889603024228 -0.014631774151209604
endloop
endfacet
facet normal 0.0 -0.9569403357322088 -0.2902846772544626
outer loop
vertex 0.281 -0.07355889603024228 -0.014631774151209604
vertex 0.279 -0.0692909649383465 -0.02870125742738173
vertex 0.281 -0.0692909649383465 -0.02870125742738173
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.281 -0.07355889603024228 -0.014631774151209604
vertex 0.281 -0.0692909649383465 -0.02870125742738173
vertex 0.281 -0.0036666635234538277 -0.000729344721834822
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.281 -0.0036666635234538277 -0.000729344721834822
vertex 0.281 -0.0692909649383465 -0.02870125742738173
vertex 0.281 -0.0034539215153514364 -0.0014306611350307812
endloop
endfacet
facet normal -1.8058895601326638e-17 0.9569403357322087 0.29028467725446294
outer loop
vertex 0.281 -0.0036666635234538277 -0.000729344721834822
vertex 0.281 -0.0034539215153514364 -0.0014306611350307812
vertex 0.279 -0.0036666635234538277 -0.0007293447218348221
endloop
endfacet
facet normal 0.0 0.9569403357322087 0.290284677254463
outer loop
vertex 0.279 -0.0036666635234538277 -0.0007293447218348221
vertex 0.281 -0.0034539215153514364 -0.0014306611350307812
vertex 0.279 -0.0034539215153514364 -0.0014306611350307812
endloop
endfacet
facet normal -0.9999999999999999 0.0 -0.0
outer loop
vertex 0.279 -0.0034539215153514364 -0.0014306611350307812
vertex 0.279 -0.0031084472403955926 -0.002076998043131512
vertex 0.279 -0.0692909649383465 -0.02870125742738173
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex 0.279 -0.0692909649383465 -0.02870125742738173
vertex 0.279 -0.0031084472403955926 -0.002076998043131512
vertex 0.279 -0.062360220922690904 -0.04166776747647012
endloop
endfacet
facet normal 0.0 -0.881921264348355 -0.47139673682599764
outer loop
vertex 0.279 -0.0692909649383465 -0.02870125742738173
vertex 0.279 -0.062360220922690904 -0.04166776747647012
vertex 0.281 -0.0692909649383465 -0.02870125742738173
endloop
endfacet
facet normal 0.0 -0.881921264348355 -0.47139673682599764
outer loop
vertex 0.281 -0.0692909649383465 -0.02870125742738173
vertex 0.279 -0.062360220922690904 -0.04166776747647012
vertex 0.281 -0.062360220922690904 -0.04166776747647012
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.281 -0.0692909649383465 -0.02870125742738173
vertex 0.281 -0.062360220922690904 -0.04166776747647012
vertex 0.281 -0.0034539215153514364 -0.0014306611350307812
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.281 -0.0034539215153514364 -0.0014306611350307812
vertex 0.281 -0.062360220922690904 -0.04166776747647012
vertex 0.281 -0.0031084472403955926 -0.0020769980431315114
endloop
endfacet
facet normal 0.0 0.881921264348355 0.47139673682599775
outer loop
vertex 0.281 -0.0034539215153514364 -0.0014306611350307812
vertex 0.281 -0.0031084472403955926 -0.0020769980431315114
vertex 0.279 -0.0034539215153514364 -0.0014306611350307812
endloop
endfacet
facet normal -1.0221787323386472e-16 0.881921264348355 0.4713967368259975
outer loop
vertex 0.279 -0.0034539215153514364 -0.0014306611350307812
vertex 0.281 -0.0031084472403955926 -0.0020769980431315114
vertex 0.279 -0.0031084472403955926 -0.002076998043131512
endloop
endfacet
facet normal -0.9999999999999999 0.0 -0.0
outer loop
vertex 0.279 -0.0031084472403955926 -0.002076998043131512
vertex 0.279 -0.0026435170812286407 -0.0026435170812286225
vertex 0.279 -0.062360220922690904 -0.04166776747647012
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex 0.279 -0.062360220922690904 -0.04166776747647012
vertex 0.279 -0.0026435170812286407 -0.0026435170812286225
vertex 0.279 -0.05303300858899108 -0.053033008588991036
endloop
endfacet
facet normal 0.0 -0.7730104533627374 -0.6343932841636448
outer loop
vertex 0.279 -0.062360220922690904 -0.04166776747647012
vertex 0.279 -0.05303300858899108 -0.053033008588991036
vertex 0.281 -0.062360220922690904 -0.04166776747647012
endloop
endfacet
facet normal 0.0 -0.7730104533627374 -0.6343932841636448
outer loop
vertex 0.281 -0.062360220922690904 -0.04166776747647012
vertex 0.279 -0.05303300858899108 -0.053033008588991036
vertex 0.281 -0.05303300858899108 -0.053033008588991036
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.281 -0.062360220922690904 -0.04166776747647012
vertex 0.281 -0.05303300858899108 -0.053033008588991036
vertex 0.281 -0.0031084472403955926 -0.0020769980431315114
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.281 -0.0031084472403955926 -0.0020769980431315114
vertex 0.281 -0.05303300858899108 -0.053033008588991036
vertex 0.281 -0.0026435170812286407 -0.002643517081228622
endloop
endfacet
facet normal -1.4447116481061318e-16 0.7730104533627374 0.6343932841636449
outer loop
vertex 0.281 -0.0031084472403955926 -0.0020769980431315114
vertex 0.281 -0.0026435170812286407 -0.002643517081228622
vertex 0.279 -0.0031084472403955926 -0.002076998043131512
endloop
endfacet
facet normal -1.3756211538008743e-16 0.7730104533627374 0.6343932841636449
outer loop
vertex 0.279 -0.0031084472403955926 -0.002076998043131512
vertex 0.281 -0.0026435170812286407 -0.002643517081228622
vertex 0.279 -0.0026435170812286407 -0.0026435170812286225
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex 0.279 -0.0026435170812286407 -0.0026435170812286225
vertex 0.279 -0.00207699804313153 -0.0031084472403955753
vertex 0.279 -0.05303300858899108 -0.053033008588991036
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex 0.279 -0.05303300858899108 -0.053033008588991036
vertex 0.279 -0.00207699804313153 -0.0031084472403955753
vertex 0.279 -0.04166776747647016 -0.062360220922690876
endloop
endfacet
facet normal 0.0 -0.6343932841636455 -0.7730104533627371
outer loop
vertex 0.279 -0.05303300858899108 -0.053033008588991036
vertex 0.279 -0.04166776747647016 -0.062360220922690876
vertex 0.281 -0.05303300858899108 -0.053033008588991036
endloop
endfacet
facet normal 0.0 -0.6343932841636455 -0.7730104533627371
outer loop
vertex 0.281 -0.05303300858899108 -0.053033008588991036
vertex 0.279 -0.04166776747647016 -0.062360220922690876
vertex 0.281 -0.04166776747647016 -0.062360220922690876
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.281 -0.05303300858899108 -0.053033008588991036
vertex 0.281 -0.04166776747647016 -0.062360220922690876
vertex 0.281 -0.0026435170812286407 -0.002643517081228622
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.281 -0.0026435170812286407 -0.002643517081228622
vertex 0.281 -0.04166776747647016 -0.062360220922690876
vertex 0.281 -0.00207699804313153 -0.003108447240395575
endloop
endfacet
facet normal -1.4447116481061306e-16 0.6343932841636456 0.7730104533627368
outer loop
vertex 0.281 -0.0026435170812286407 -0.002643517081228622
vertex 0.281 -0.00207699804313153 -0.003108447240395575
vertex 0.279 -0.0026435170812286407 -0.0026435170812286225
endloop
endfacet
facet normal -1.6761992257797662e-16 0.6343932841636456 0.7730104533627368
outer loop
vertex 0.279 -0.0026435170812286407 -0.0026435170812286225
vertex 0.281 -0.00207699804313153 -0.003108447240395575
vertex 0.279 -0.00207699804313153 -0.0031084472403955753
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex 0.279 -0.00207699804313153 -0.0031084472403955753
vertex 0.279 -0.0014306611350307999 -0.003453921515351419
vertex 0.279 -0.04166776747647016 -0.062360220922690876
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex 0.279 -0.04166776747647016 -0.062360220922690876
vertex 0.279 -0.0014306611350307999 -0.003453921515351419
vertex 0.279 -0.028701257427381777 -0.06929096493834647
endloop
endfacet
facet normal 0.0 -0.47139673682599775 -0.881921264348355
outer loop
vertex 0.279 -0.04166776747647016 -0.062360220922690876
vertex 0.279 -0.028701257427381777 -0.06929096493834647
vertex 0.281 -0.04166776747647016 -0.062360220922690876
endloop
endfacet
facet normal 0.0 -0.47139673682599775 -0.881921264348355
outer loop
vertex 0.281 -0.04166776747647016 -0.062360220922690876
vertex 0.279 -0.028701257427381777 -0.06929096493834647
vertex 0.281 -0.028701257427381777 -0.06929096493834647
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.281 -0.04166776747647016 -0.062360220922690876
vertex 0.281 -0.028701257427381777 -0.06929096493834647
vertex 0.281 -0.00207699804313153 -0.003108447240395575
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.281 -0.00207699804313153 -0.003108447240395575
vertex 0.281 -0.028701257427381777 -0.06929096493834647
vertex 0.281 -0.0014306611350307999 -0.0034539215153514186
endloop
endfacet
facet normal -1.8058895601326734e-16 0.47139673682599775 0.881921264348355
outer loop
vertex 0.281 -0.00207699804313153 -0.003108447240395575
vertex 0.281 -0.0014306611350307999 -0.0034539215153514186
vertex 0.279 -0.00207699804313153 -0.0031084472403955753
endloop
endfacet
facet normal -1.912361901535297e-16 0.47139673682599775 0.881921264348355
outer loop
vertex 0.279 -0.00207699804313153 -0.0031084472403955753
vertex 0.281 -0.0014306611350307999 -0.0034539215153514186
vertex 0.279 -0.0014306611350307999 -0.003453921515351419
endloop
endfacet
facet normal -0.9999999999999999 0.0 -0.0
outer loop
vertex 0.279 -0.0014306611350307999 -0.003453921515351419
vertex 0.279 -0.0007293447218348407 -0.0036666635234538104
vertex 0.279 -0.028701257427381777 -0.06929096493834647
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex 0.279 -0.028701257427381777 -0.06929096493834647
vertex 0.279 -0.0007293447218348407 -0.0036666635234538104
vertex 0.279 -0.014631774151209653 -0.07355889603024225
endloop
endfacet
facet normal 0.0 -0.29028467725446266 -0.9569403357322088
outer loop
vertex 0.279 -0.028701257427381777 -0.06929096493834647
vertex 0.279 -0.014631774151209653 -0.07355889603024225
vertex 0.281 -0.028701257427381777 -0.06929096493834647
endloop
endfacet
facet normal 0.0 -0.29028467725446266 -0.9569403357322088
outer loop
vertex 0.281 -0.028701257427381777 -0.06929096493834647
vertex 0.279 -0.014631774151209653 -0.07355889603024225
vertex 0.281 -0.014631774151209653 -0.07355889603024225
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.281 -0.028701257427381777 -0.06929096493834647
vertex 0.281 -0.014631774151209653 -0.07355889603024225
vertex 0.281 -0.0014306611350307999 -0.0034539215153514186
endloop
endfacet
facet normal 0.9999999999999999 -0.0 0.0
outer loop
vertex 0.281 -0.0014306611350307999 -0.0034539215153514186
vertex 0.281 -0.014631774151209653 -0.07355889603024225
vertex 0.281 -0.0007293447218348407 -0.00366666352345381
endloop
endfacet
facet normal -1.9864785161459305e-16 0.290284677254463 0.9569403357322087
outer loop
vertex 0.281 -0.0014306611350307999 -0.0034539215153514186
vertex 0.281 -0.0007293447218348407 -0.00366666352345381
vertex 0.279 -0.0014306611350307999 -0.003453921515351419
endloop
endfacet
facet normal -2.0750335818797356e-16 0.290284677254463 0.9569403357322087
outer loop
vertex 0.279 -0.0014306611350307999 -0.003453921515351419
vertex 0.281 -0.0007293447218348407 -0.00366666352345381
vertex 0.279 -0.0007293447218348407 -0.0036666635234538104
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex 0.279 -0.0007293447218348407 -0.0036666635234538104
vertex 0.279 0.0 -0.0037384977086384647
vertex 0.279 -0.014631774151209653 -0.07355889603024225
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex 0.279 -0.014631774151209653 -0.07355889603024225
vertex 0.279 0.0 -0.0037384977086384647
vertex 0.279 0.0 -0.07499999999999998
endloop
endfacet
facet normal 0.0 -0.09801714032956142 -0.9951847266721967
outer loop
vertex 0.279 -0.014631774151209653 -0.07355889603024225
vertex 0.279 0.0 -0.07499999999999998
vertex 0.281 -0.014631774151209653 -0.07355889603024225
endloop
endfacet
facet normal 0.0 -0.09801714032956142 -0.9951847266721967
outer loop
vertex 0.281 -0.014631774151209653 -0.07355889603024225
vertex 0.279 0.0 -0.07499999999999998
vertex 0.281 0.0 -0.07499999999999998
endloop
endfacet
facet normal 1.0 -0.0 -0.0
outer loop
vertex 0.281 -0.014631774151209653 -0.07355889603024225
vertex 0.281 0.0 -0.07499999999999998
vertex 0.281 -0.0007293447218348407 -0.00366666352345381
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex 0.281 -0.0007293447218348407 -0.00366666352345381
vertex 0.281 0.0 -0.07499999999999998
vertex 0.281 0.0 -0.0037384977086384642
endloop
endfacet
facet normal -2.1670674721591942e-16 0.09801714032956091 0.9951847266721968
outer loop
vertex 0.281 -0.0007293447218348407 -0.00366666352345381
vertex 0.281 0.0 -0.0037384977086384642
vertex 0.279 -0.0007293447218348407 -0.0036666635234538104
endloop
endfacet
facet normal -2.1579628853647757e-16 0.09801714032956092 0.9951847266721968
outer loop
vertex 0.279 -0.0007293447218348407 -0.0036666635234538104
vertex 0.281 0.0 -0.0037384977086384642
vertex 0.279 0.0 -0.0037384977086384647
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28300000000000003 0.0 -0.003738497708638499
vertex -0.28300000000000003 0.000729344721834839 -0.003666663523453845
vertex -0.28300000000000003 0.0 -0.07500000000000001
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28300000000000003 0.0 -0.07500000000000001
vertex -0.28300000000000003 0.000729344721834839 -0.003666663523453845
vertex -0.28300000000000003 0.014631774151209618 -0.0735588960302423
endloop
endfacet
facet normal 0.0 0.09801714032956071 -0.995184726672197
outer loop
vertex -0.28300000000000003 0.0 -0.07500000000000001
vertex -0.28300000000000003 0.014631774151209618 -0.0735588960302423
vertex -0.281 0.0 -0.07500000000000001
endloop
endfacet
facet normal 0.0 0.09801714032956071 -0.995184726672197
outer loop
vertex -0.281 0.0 -0.07500000000000001
vertex -0.28300000000000003 0.014631774151209618 -0.0735588960302423
vertex -0.281 0.014631774151209618 -0.0735588960302423
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex -0.281 0.0 -0.07500000000000001
vertex -0.281 0.014631774151209618 -0.0735588960302423
vertex -0.281 0.0 -0.003738497708638499
endloop
endfacet
facet normal 1.0 -0.0 -0.0
outer loop
vertex -0.281 0.0 -0.003738497708638499
vertex -0.281 0.014631774151209618 -0.0735588960302423
vertex -0.281 0.000729344721834839 -0.003666663523453845
endloop
endfacet
facet normal 0.0 -0.09801714032956056 0.9951847266721969
outer loop
vertex -0.281 0.0 -0.003738497708638499
vertex -0.281 0.000729344721834839 -0.003666663523453845
vertex -0.28300000000000003 0.0 -0.003738497708638499
endloop
endfacet
facet normal 0.0 -0.09801714032956056 0.9951847266721969
outer loop
vertex -0.28300000000000003 0.0 -0.003738497708638499
vertex -0.281 0.000729344721834839 -0.003666663523453845
vertex -0.28300000000000003 0.000729344721834839 -0.003666663523453845
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28300000000000003 0.000729344721834839 -0.003666663523453845
vertex -0.28300000000000003 0.0014306611350307975 -0.003453921515351454
vertex -0.28300000000000003 0.014631774151209618 -0.0735588960302423
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28300000000000003 0.014631774151209618 -0.0735588960302423
vertex -0.28300000000000003 0.0014306611350307975 -0.003453921515351454
vertex -0.28300000000000003 0.02870125742738173 -0.06929096493834652
endloop
endfacet
facet normal 0.0 0.290284677254462 -0.9569403357322089
outer loop
vertex -0.28300000000000003 0.014631774151209618 -0.0735588960302423
vertex -0.28300000000000003 0.02870125742738173 -0.06929096493834652
vertex -0.281 0.014631774151209618 -0.0735588960302423
endloop
endfacet
facet normal 0.0 0.290284677254462 -0.9569403357322089
outer loop
vertex -0.281 0.014631774151209618 -0.0735588960302423
vertex -0.28300000000000003 0.02870125742738173 -0.06929096493834652
vertex -0.281 0.02870125742738173 -0.06929096493834652
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex -0.281 0.014631774151209618 -0.0735588960302423
vertex -0.281 0.02870125742738173 -0.06929096493834652
vertex -0.281 0.000729344721834839 -0.003666663523453845
endloop
endfacet
facet normal 0.9999999999999999 -0.0 -0.0
outer loop
vertex -0.281 0.000729344721834839 -0.003666663523453845
vertex -0.281 0.02870125742738173 -0.06929096493834652
vertex -0.281 0.0014306611350307975 -0.003453921515351454
endloop
endfacet
facet normal 0.0 -0.2902846772544627 0.9569403357322088
outer loop
vertex -0.281 0.000729344721834839 -0.003666663523453845
vertex -0.281 0.0014306611350307975 -0.003453921515351454
vertex -0.28300000000000003 0.000729344721834839 -0.003666663523453845
endloop
endfacet
facet normal 0.0 -0.2902846772544627 0.9569403357322088
outer loop
vertex -0.28300000000000003 0.000729344721834839 -0.003666663523453845
vertex -0.281 0.0014306611350307975 -0.003453921515351454
vertex -0.28300000000000003 0.0014306611350307975 -0.003453921515351454
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28300000000000003 0.0014306611350307975 -0.003453921515351454
vertex -0.28300000000000003 0.00207699804313153 -0.0031084472403956095
vertex -0.28300000000000003 0.02870125742738173 -0.06929096493834652
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28300000000000003 0.02870125742738173 -0.06929096493834652
vertex -0.28300000000000003 0.00207699804313153 -0.0031084472403956095
vertex -0.28300000000000003 0.04166776747647016 -0.062360220922690904
endloop
endfacet
facet normal 0.0 0.4713967368259979 -0.8819212643483549
outer loop
vertex -0.28300000000000003 0.02870125742738173 -0.06929096493834652
vertex -0.28300000000000003 0.04166776747647016 -0.062360220922690904
vertex -0.281 0.02870125742738173 -0.06929096493834652
endloop
endfacet
facet normal 0.0 0.4713967368259979 -0.8819212643483549
outer loop
vertex -0.281 0.02870125742738173 -0.06929096493834652
vertex -0.28300000000000003 0.04166776747647016 -0.062360220922690904
vertex -0.281 0.04166776747647016 -0.062360220922690904
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex -0.281 0.02870125742738173 -0.06929096493834652
vertex -0.281 0.04166776747647016 -0.062360220922690904
vertex -0.281 0.0014306611350307975 -0.003453921515351454
endloop
endfacet
facet normal 1.0 -0.0 -0.0
outer loop
vertex -0.281 0.0014306611350307975 -0.003453921515351454
vertex -0.281 0.04166776747647016 -0.062360220922690904
vertex -0.281 0.00207699804313153 -0.0031084472403956095
endloop
endfacet
facet normal 0.0 -0.4713967368259973 0.8819212643483553
outer loop
vertex -0.281 0.0014306611350307975 -0.003453921515351454
vertex -0.281 0.00207699804313153 -0.0031084472403956095
vertex -0.28300000000000003 0.0014306611350307975 -0.003453921515351454
endloop
endfacet
facet normal 0.0 -0.4713967368259973 0.8819212643483553
outer loop
vertex -0.28300000000000003 0.0014306611350307975 -0.003453921515351454
vertex -0.281 0.00207699804313153 -0.0031084472403956095
vertex -0.28300000000000003 0.00207699804313153 -0.0031084472403956095
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28300000000000003 0.00207699804313153 -0.0031084472403956095
vertex -0.28300000000000003 0.00264351708122864 -0.0026435170812286577
vertex -0.28300000000000003 0.04166776747647016 -0.062360220922690904
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28300000000000003 0.04166776747647016 -0.062360220922690904
vertex -0.28300000000000003 0.00264351708122864 -0.0026435170812286577
vertex -0.28300000000000003 0.05303300858899106 -0.05303300858899108
endloop
endfacet
facet normal 0.0 0.6343932841636455 -0.7730104533627369
outer loop
vertex -0.28300000000000003 0.04166776747647016 -0.062360220922690904
vertex -0.28300000000000003 0.05303300858899106 -0.05303300858899108
vertex -0.281 0.04166776747647016 -0.062360220922690904
endloop
endfacet
facet normal 0.0 0.6343932841636455 -0.7730104533627369
outer loop
vertex -0.281 0.04166776747647016 -0.062360220922690904
vertex -0.28300000000000003 0.05303300858899106 -0.05303300858899108
vertex -0.281 0.05303300858899106 -0.05303300858899108
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex -0.281 0.04166776747647016 -0.062360220922690904
vertex -0.281 0.05303300858899106 -0.05303300858899108
vertex -0.281 0.00207699804313153 -0.0031084472403956095
endloop
endfacet
facet normal 1.0 -0.0 -0.0
outer loop
vertex -0.281 0.00207699804313153 -0.0031084472403956095
vertex -0.281 0.05303300858899106 -0.05303300858899108
vertex -0.281 0.00264351708122864 -0.0026435170812286577
endloop
endfacet
facet normal 0.0 -0.6343932841636455 0.773010453362737
outer loop
vertex -0.281 0.00207699804313153 -0.0031084472403956095
vertex -0.281 0.00264351708122864 -0.0026435170812286577
vertex -0.28300000000000003 0.00207699804313153 -0.0031084472403956095
endloop
endfacet
facet normal 0.0 -0.6343932841636455 0.773010453362737
outer loop
vertex -0.28300000000000003 0.00207699804313153 -0.0031084472403956095
vertex -0.281 0.00264351708122864 -0.0026435170812286577
vertex -0.28300000000000003 0.00264351708122864 -0.0026435170812286577
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28300000000000003 0.00264351708122864 -0.0026435170812286577
vertex -0.28300000000000003 0.003108447240395592 -0.002076998043131548
vertex -0.28300000000000003 0.05303300858899106 -0.05303300858899108
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28300000000000003 0.05303300858899106 -0.05303300858899108
vertex -0.28300000000000003 0.003108447240395592 -0.002076998043131548
vertex -0.28300000000000003 0.06236022092269089 -0.041667767476470184
endloop
endfacet
facet normal 0.0 0.7730104533627367 -0.6343932841636458
outer loop
vertex -0.28300000000000003 0.05303300858899106 -0.05303300858899108
vertex -0.28300000000000003 0.06236022092269089 -0.041667767476470184
vertex -0.281 0.05303300858899106 -0.05303300858899108
endloop
endfacet
facet normal 0.0 0.7730104533627367 -0.6343932841636458
outer loop
vertex -0.281 0.05303300858899106 -0.05303300858899108
vertex -0.28300000000000003 0.06236022092269089 -0.041667767476470184
vertex -0.281 0.06236022092269089 -0.041667767476470184
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex -0.281 0.05303300858899106 -0.05303300858899108
vertex -0.281 0.06236022092269089 -0.041667767476470184
vertex -0.281 0.00264351708122864 -0.0026435170812286577
endloop
endfacet
facet normal 0.9999999999999999 -0.0 -0.0
outer loop
vertex -0.281 0.00264351708122864 -0.0026435170812286577
vertex -0.281 0.06236022092269089 -0.041667767476470184
vertex -0.281 0.003108447240395592 -0.002076998043131548
endloop
endfacet
facet normal 0.0 -0.7730104533627367 0.6343932841636458
outer loop
vertex -0.281 0.00264351708122864 -0.0026435170812286577
vertex -0.281 0.003108447240395592 -0.002076998043131548
vertex -0.28300000000000003 0.00264351708122864 -0.0026435170812286577
endloop
endfacet
facet normal 0.0 -0.7730104533627367 0.6343932841636458
outer loop
vertex -0.28300000000000003 0.00264351708122864 -0.0026435170812286577
vertex -0.281 0.003108447240395592 -0.002076998043131548
vertex -0.28300000000000003 0.003108447240395592 -0.002076998043131548
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28300000000000003 0.003108447240395592 -0.002076998043131548
vertex -0.28300000000000003 0.003453921515351437 -0.001430661135030815
vertex -0.28300000000000003 0.06236022092269089 -0.041667767476470184
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28300000000000003 0.06236022092269089 -0.041667767476470184
vertex -0.28300000000000003 0.003453921515351437 -0.001430661135030815
vertex -0.28300000000000003 0.06929096493834651 -0.028701257427381752
endloop
endfacet
facet normal 0.0 0.8819212643483549 -0.4713967368259979
outer loop
vertex -0.28300000000000003 0.06236022092269089 -0.041667767476470184
vertex -0.28300000000000003 0.06929096493834651 -0.028701257427381752
vertex -0.281 0.06236022092269089 -0.041667767476470184
endloop
endfacet
facet normal 0.0 0.8819212643483549 -0.4713967368259979
outer loop
vertex -0.281 0.06236022092269089 -0.041667767476470184
vertex -0.28300000000000003 0.06929096493834651 -0.028701257427381752
vertex -0.281 0.06929096493834651 -0.028701257427381752
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex -0.281 0.06236022092269089 -0.041667767476470184
vertex -0.281 0.06929096493834651 -0.028701257427381752
vertex -0.281 0.003108447240395592 -0.002076998043131548
endloop
endfacet
facet normal 0.9999999999999999 -0.0 -0.0
outer loop
vertex -0.281 0.003108447240395592 -0.002076998043131548
vertex -0.281 0.06929096493834651 -0.028701257427381752
vertex -0.281 0.003453921515351437 -0.0014306611350308148
endloop
endfacet
facet normal 0.0 -0.8819212643483554 0.4713967368259971
outer loop
vertex -0.281 0.003108447240395592 -0.002076998043131548
vertex -0.281 0.003453921515351437 -0.0014306611350308148
vertex -0.28300000000000003 0.003108447240395592 -0.002076998043131548
endloop
endfacet
facet normal -5.110893661693232e-17 -0.8819212643483553 0.47139673682599714
outer loop
vertex -0.28300000000000003 0.003108447240395592 -0.002076998043131548
vertex -0.281 0.003453921515351437 -0.0014306611350308148
vertex -0.28300000000000003 0.003453921515351437 -0.001430661135030815
endloop
endfacet
facet normal -0.9999999999999999 0.0 0.0
outer loop
vertex -0.28300000000000003 0.003453921515351437 -0.001430661135030815
vertex -0.28300000000000003 0.0036666635234538277 -0.0007293447218348566
vertex -0.28300000000000003 0.06929096493834651 -0.028701257427381752
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28300000000000003 0.06929096493834651 -0.028701257427381752
vertex -0.28300000000000003 0.0036666635234538277 -0.0007293447218348566
vertex -0.28300000000000003 0.07355889603024228 -0.014631774151209642
endloop
endfacet
facet normal 0.0 0.9569403357322089 -0.29028467725446205
outer loop
vertex -0.28300000000000003 0.06929096493834651 -0.028701257427381752
vertex -0.28300000000000003 0.07355889603024228 -0.014631774151209642
vertex -0.281 0.06929096493834651 -0.028701257427381752
endloop
endfacet
facet normal 0.0 0.9569403357322089 -0.29028467725446205
outer loop
vertex -0.281 0.06929096493834651 -0.028701257427381752
vertex -0.28300000000000003 0.07355889603024228 -0.014631774151209642
vertex -0.281 0.07355889603024228 -0.014631774151209642
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex -0.281 0.06929096493834651 -0.028701257427381752
vertex -0.281 0.07355889603024228 -0.014631774151209642
vertex -0.281 0.003453921515351437 -0.0014306611350308148
endloop
endfacet
facet normal 1.0 -0.0 -0.0
outer loop
vertex -0.281 0.003453921515351437 -0.0014306611350308148
vertex -0.281 0.07355889603024228 -0.014631774151209642
vertex -0.281 0.0036666635234538277 -0.0007293447218348565
endloop
endfacet
facet normal -1.8058895601326663e-17 -0.9569403357322088 0.2902846772544628
outer loop
vertex -0.281 0.003453921515351437 -0.0014306611350308148
vertex -0.281 0.0036666635234538277 -0.0007293447218348565
vertex -0.28300000000000003 0.003453921515351437 -0.001430661135030815
endloop
endfacet
facet normal -1.5736363885927084e-17 -0.9569403357322088 0.2902846772544627
outer loop
vertex -0.28300000000000003 0.003453921515351437 -0.001430661135030815
vertex -0.281 0.0036666635234538277 -0.0007293447218348565
vertex -0.28300000000000003 0.0036666635234538277 -0.0007293447218348566
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28300000000000003 0.0036666635234538277 -0.0007293447218348566
vertex -0.28300000000000003 0.0037384977086384816 -1.755766917056024e-17
vertex -0.28300000000000003 0.07355889603024228 -0.014631774151209642
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28300000000000003 0.07355889603024228 -0.014631774151209642
vertex -0.28300000000000003 0.0037384977086384816 -1.755766917056024e-17
vertex -0.28300000000000003 0.075 -2.1921177704737623e-17
endloop
endfacet
facet normal 0.0 0.9951847266721969 -0.0980171403295607
outer loop
vertex -0.28300000000000003 0.07355889603024228 -0.014631774151209642
vertex -0.28300000000000003 0.075 -2.1921177704737623e-17
vertex -0.281 0.07355889603024228 -0.014631774151209642
endloop
endfacet
facet normal 6.001818858308654e-18 0.9951847266721969 -0.0980171403295607
outer loop
vertex -0.281 0.07355889603024228 -0.014631774151209642
vertex -0.28300000000000003 0.075 -2.1921177704737623e-17
vertex -0.281 0.075 -2.1798713024822888e-17
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex -0.281 0.07355889603024228 -0.014631774151209642
vertex -0.281 0.075 -2.1798713024822888e-17
vertex -0.281 0.0036666635234538277 -0.0007293447218348565
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex -0.281 0.0036666635234538277 -0.0007293447218348565
vertex -0.281 0.075 -2.1798713024822888e-17
vertex -0.281 0.0037384977086384816 -1.7435204490645505e-17
endloop
endfacet
facet normal -4.514723900331666e-18 -0.9951847266721969 0.09801714032956056
outer loop
vertex -0.281 0.0036666635234538277 -0.0007293447218348565
vertex -0.281 0.0037384977086384816 -1.7435204490645505e-17
vertex -0.28300000000000003 0.0036666635234538277 -0.0007293447218348566
endloop
endfacet
facet normal -6.001818858308646e-18 -0.9951847266721969 0.09801714032956056
outer loop
vertex -0.28300000000000003 0.0036666635234538277 -0.0007293447218348566
vertex -0.281 0.0037384977086384816 -1.7435204490645505e-17
vertex -0.28300000000000003 0.0037384977086384816 -1.755766917056024e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28300000000000003 0.0037384977086384816 -1.755766917056024e-17
vertex -0.28300000000000003 0.0036666635234538277 0.0007293447218348215
vertex -0.28300000000000003 0.075 -2.1921177704737623e-17
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28300000000000003 0.075 -2.1921177704737623e-17
vertex -0.28300000000000003 0.0036666635234538277 0.0007293447218348215
vertex -0.28300000000000003 0.07355889603024228 0.014631774151209597
endloop
endfacet
facet normal 0.0 0.9951847266721969 0.0980171403295607
outer loop
vertex -0.28300000000000003 0.075 -2.1921177704737623e-17
vertex -0.28300000000000003 0.07355889603024228 0.014631774151209597
vertex -0.281 0.075 -2.1798713024822888e-17
endloop
endfacet
facet normal -0.0 0.9951847266721969 0.0980171403295607
outer loop
vertex -0.281 0.075 -2.1798713024822888e-17
vertex -0.28300000000000003 0.07355889603024228 0.014631774151209597
vertex -0.281 0.07355889603024228 0.014631774151209597
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex -0.281 0.075 -2.1798713024822888e-17
vertex -0.281 0.07355889603024228 0.014631774151209597
vertex -0.281 0.0037384977086384816 -1.7435204490645505e-17
endloop
endfacet
facet normal 0.9999999999999999 0.0 -0.0
outer loop
vertex -0.281 0.0037384977086384816 -1.7435204490645505e-17
vertex -0.281 0.07355889603024228 0.014631774151209597
vertex -0.281 0.0036666635234538277 0.0007293447218348216
endloop
endfacet
facet normal 4.514723900331666e-18 -0.9951847266721969 -0.09801714032956056
outer loop
vertex -0.281 0.0037384977086384816 -1.7435204490645505e-17
vertex -0.281 0.0036666635234538277 0.0007293447218348216
vertex -0.28300000000000003 0.0037384977086384816 -1.755766917056024e-17
endloop
endfacet
facet normal 5.313519824306301e-18 -0.9951847266721969 -0.09801714032956056
outer loop
vertex -0.28300000000000003 0.0037384977086384816 -1.755766917056024e-17
vertex -0.281 0.0036666635234538277 0.0007293447218348216
vertex -0.28300000000000003 0.0036666635234538277 0.0007293447218348215
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28300000000000003 0.0036666635234538277 0.0007293447218348215
vertex -0.28300000000000003 0.003453921515351437 0.00143066113503078
vertex -0.28300000000000003 0.07355889603024228 0.014631774151209597
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28300000000000003 0.07355889603024228 0.014631774151209597
vertex -0.28300000000000003 0.003453921515351437 0.00143066113503078
vertex -0.28300000000000003 0.06929096493834651 0.02870125742738171
endloop
endfacet
facet normal 0.0 0.9569403357322089 0.290284677254462
outer loop
vertex -0.28300000000000003 0.07355889603024228 0.014631774151209597
vertex -0.28300000000000003 0.06929096493834651 0.02870125742738171
vertex -0.281 0.07355889603024228 0.014631774151209597
endloop
endfacet
facet normal -0.0 0.9569403357322089 0.290284677254462
outer loop
vertex -0.281 0.07355889603024228 0.014631774151209597
vertex -0.28300000000000003 0.06929096493834651 0.02870125742738171
vertex -0.281 0.06929096493834651 0.02870125742738171
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex -0.281 0.07355889603024228 0.014631774151209597
vertex -0.281 0.06929096493834651 0.02870125742738171
vertex -0.281 0.0036666635234538277 0.0007293447218348216
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex -0.281 0.0036666635234538277 0.0007293447218348216
vertex -0.281 0.06929096493834651 0.02870125742738171
vertex -0.281 0.003453921515351437 0.0014306611350307801
endloop
endfacet
facet normal 1.8058895601326657e-17 -0.9569403357322088 -0.29028467725446266
outer loop
vertex -0.281 0.0036666635234538277 0.0007293447218348216
vertex -0.281 0.003453921515351437 0.0014306611350307801
vertex -0.28300000000000003 0.0036666635234538277 0.0007293447218348215
endloop
endfacet
facet normal 3.147272777185417e-17 -0.9569403357322088 -0.2902846772544627
outer loop
vertex -0.28300000000000003 0.0036666635234538277 0.0007293447218348215
vertex -0.281 0.003453921515351437 0.0014306611350307801
vertex -0.28300000000000003 0.003453921515351437 0.00143066113503078
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28300000000000003 0.003453921515351437 0.00143066113503078
vertex -0.28300000000000003 0.0031084472403955926 0.002076998043131512
vertex -0.28300000000000003 0.06929096493834651 0.02870125742738171
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28300000000000003 0.06929096493834651 0.02870125742738171
vertex -0.28300000000000003 0.0031084472403955926 0.002076998043131512
vertex -0.28300000000000003 0.062360220922690904 0.04166776747647013
endloop
endfacet
facet normal 0.0 0.8819212643483552 0.47139673682599764
outer loop
vertex -0.28300000000000003 0.06929096493834651 0.02870125742738171
vertex -0.28300000000000003 0.062360220922690904 0.04166776747647013
vertex -0.281 0.06929096493834651 0.02870125742738171
endloop
endfacet
facet normal -0.0 0.8819212643483552 0.47139673682599764
outer loop
vertex -0.281 0.06929096493834651 0.02870125742738171
vertex -0.28300000000000003 0.062360220922690904 0.04166776747647013
vertex -0.281 0.062360220922690904 0.04166776747647013
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex -0.281 0.06929096493834651 0.02870125742738171
vertex -0.281 0.062360220922690904 0.04166776747647013
vertex -0.281 0.003453921515351437 0.0014306611350307801
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex -0.281 0.003453921515351437 0.0014306611350307801
vertex -0.281 0.062360220922690904 0.04166776747647013
vertex -0.281 0.0031084472403955926 0.002076998043131512
endloop
endfacet
facet normal 5.417668680398008e-17 -0.8819212643483553 -0.47139673682599736
outer loop
vertex -0.281 0.003453921515351437 0.0014306611350307801
vertex -0.281 0.0031084472403955926 0.002076998043131512
vertex -0.28300000000000003 0.003453921515351437 0.00143066113503078
endloop
endfacet
facet normal -0.0 -0.8819212643483553 -0.4713967368259972
outer loop
vertex -0.28300000000000003 0.003453921515351437 0.00143066113503078
vertex -0.281 0.0031084472403955926 0.002076998043131512
vertex -0.28300000000000003 0.0031084472403955926 0.002076998043131512
endloop
endfacet
facet normal -0.9999999999999999 0.0 0.0
outer loop
vertex -0.28300000000000003 0.0031084472403955926 0.002076998043131512
vertex -0.28300000000000003 0.0026435170812286403 0.0026435170812286225
vertex -0.28300000000000003 0.062360220922690904 0.04166776747647013
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28300000000000003 0.062360220922690904 0.04166776747647013
vertex -0.28300000000000003 0.0026435170812286403 0.0026435170812286225
vertex -0.28300000000000003 0.053033008588991064 0.05303300858899104
endloop
endfacet
facet normal 0.0 0.7730104533627371 0.6343932841636455
outer loop
vertex -0.28300000000000003 0.062360220922690904 0.04166776747647013
vertex -0.28300000000000003 0.053033008588991064 0.05303300858899104
vertex -0.281 0.062360220922690904 0.04166776747647013
endloop
endfacet
facet normal -0.0 0.7730104533627371 0.6343932841636455
outer loop
vertex -0.281 0.062360220922690904 0.04166776747647013
vertex -0.28300000000000003 0.053033008588991064 0.05303300858899104
vertex -0.281 0.053033008588991064 0.05303300858899104
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex -0.281 0.062360220922690904 0.04166776747647013
vertex -0.281 0.053033008588991064 0.05303300858899104
vertex -0.281 0.0031084472403955926 0.002076998043131512
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex -0.281 0.0031084472403955926 0.002076998043131512
vertex -0.281 0.053033008588991064 0.05303300858899104
vertex -0.281 0.0026435170812286403 0.0026435170812286225
endloop
endfacet
facet normal 0.0 -0.7730104533627372 -0.6343932841636453
outer loop
vertex -0.281 0.0031084472403955926 0.002076998043131512
vertex -0.281 0.0026435170812286403 0.0026435170812286225
vertex -0.28300000000000003 0.0031084472403955926 0.002076998043131512
endloop
endfacet
facet normal -0.0 -0.7730104533627372 -0.6343932841636453
outer loop
vertex -0.28300000000000003 0.0031084472403955926 0.002076998043131512
vertex -0.281 0.0026435170812286403 0.0026435170812286225
vertex -0.28300000000000003 0.0026435170812286403 0.0026435170812286225
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28300000000000003 0.0026435170812286403 0.0026435170812286225
vertex -0.28300000000000003 0.00207699804313153 0.0031084472403955753
vertex -0.28300000000000003 0.053033008588991064 0.05303300858899104
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28300000000000003 0.053033008588991064 0.05303300858899104
vertex -0.28300000000000003 0.00207699804313153 0.0031084472403955753
vertex -0.28300000000000003 0.04166776747647016 0.06236022092269088
endloop
endfacet
facet normal 0.0 0.6343932841636459 0.7730104533627367
outer loop
vertex -0.28300000000000003 0.053033008588991064 0.05303300858899104
vertex -0.28300000000000003 0.04166776747647016 0.06236022092269088
vertex -0.281 0.053033008588991064 0.05303300858899104
endloop
endfacet
facet normal -0.0 0.6343932841636459 0.7730104533627367
outer loop
vertex -0.281 0.053033008588991064 0.05303300858899104
vertex -0.28300000000000003 0.04166776747647016 0.06236022092269088
vertex -0.281 0.04166776747647016 0.06236022092269088
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex -0.281 0.053033008588991064 0.05303300858899104
vertex -0.281 0.04166776747647016 0.06236022092269088
vertex -0.281 0.0026435170812286403 0.0026435170812286225
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex -0.281 0.0026435170812286403 0.0026435170812286225
vertex -0.281 0.04166776747647016 0.06236022092269088
vertex -0.281 0.00207699804313153 0.0031084472403955753
endloop
endfacet
facet normal 0.0 -0.6343932841636459 -0.7730104533627365
outer loop
vertex -0.281 0.0026435170812286403 0.0026435170812286225
vertex -0.281 0.00207699804313153 0.0031084472403955753
vertex -0.28300000000000003 0.0026435170812286403 0.0026435170812286225
endloop
endfacet
facet normal -0.0 -0.6343932841636459 -0.7730104533627365
outer loop
vertex -0.28300000000000003 0.0026435170812286403 0.0026435170812286225
vertex -0.281 0.00207699804313153 0.0031084472403955753
vertex -0.28300000000000003 0.00207699804313153 0.0031084472403955753
endloop
endfacet
facet normal -0.9999999999999999 0.0 0.0
outer loop
vertex -0.28300000000000003 0.00207699804313153 0.0031084472403955753
vertex -0.28300000000000003 0.001430661135030798 0.0034539215153514195
vertex -0.28300000000000003 0.04166776747647016 0.06236022092269088
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28300000000000003 0.04166776747647016 0.06236022092269088
vertex -0.28300000000000003 0.001430661135030798 0.0034539215153514195
vertex -0.28300000000000003 0.028701257427381742 0.0692909649383465
endloop
endfacet
facet normal 0.0 0.4713967368259978 0.8819212643483548
outer loop
vertex -0.28300000000000003 0.04166776747647016 0.06236022092269088
vertex -0.28300000000000003 0.028701257427381742 0.0692909649383465
vertex -0.281 0.04166776747647016 0.06236022092269088
endloop
endfacet
facet normal -0.0 0.4713967368259978 0.8819212643483548
outer loop
vertex -0.281 0.04166776747647016 0.06236022092269088
vertex -0.28300000000000003 0.028701257427381742 0.0692909649383465
vertex -0.281 0.028701257427381742 0.0692909649383465
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex -0.281 0.04166776747647016 0.06236022092269088
vertex -0.281 0.028701257427381742 0.0692909649383465
vertex -0.281 0.00207699804313153 0.0031084472403955753
endloop
endfacet
facet normal 1.0 0.0 -0.0
outer loop
vertex -0.281 0.00207699804313153 0.0031084472403955753
vertex -0.281 0.028701257427381742 0.0692909649383465
vertex -0.281 0.001430661135030798 0.0034539215153514195
endloop
endfacet
facet normal 0.0 -0.4713967368259971 -0.8819212643483553
outer loop
vertex -0.281 0.00207699804313153 0.0031084472403955753
vertex -0.281 0.001430661135030798 0.0034539215153514195
vertex -0.28300000000000003 0.00207699804313153 0.0031084472403955753
endloop
endfacet
facet normal -0.0 -0.4713967368259971 -0.8819212643483553
outer loop
vertex -0.28300000000000003 0.00207699804313153 0.0031084472403955753
vertex -0.281 0.001430661135030798 0.0034539215153514195
vertex -0.28300000000000003 0.001430661135030798 0.0034539215153514195
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28300000000000003 0.001430661135030798 0.0034539215153514195
vertex -0.28300000000000003 0.0007293447218348403 0.0036666635234538104
vertex -0.28300000000000003 0.028701257427381742 0.0692909649383465
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28300000000000003 0.028701257427381742 0.0692909649383465
vertex -0.28300000000000003 0.0007293447218348403 0.0036666635234538104
vertex -0.28300000000000003 0.014631774151209646 0.07355889603024227
endloop
endfacet
facet normal 0.0 0.2902846772544624 0.956940335732209
outer loop
vertex -0.28300000000000003 0.028701257427381742 0.0692909649383465
vertex -0.28300000000000003 0.014631774151209646 0.07355889603024227
vertex -0.281 0.028701257427381742 0.0692909649383465
endloop
endfacet
facet normal -0.0 0.2902846772544624 0.956940335732209
outer loop
vertex -0.281 0.028701257427381742 0.0692909649383465
vertex -0.28300000000000003 0.014631774151209646 0.07355889603024227
vertex -0.281 0.014631774151209646 0.07355889603024227
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex -0.281 0.028701257427381742 0.0692909649383465
vertex -0.281 0.014631774151209646 0.07355889603024227
vertex -0.281 0.001430661135030798 0.0034539215153514195
endloop
endfacet
facet normal 0.9999999999999999 0.0 -0.0
outer loop
vertex -0.281 0.001430661135030798 0.0034539215153514195
vertex -0.281 0.014631774151209646 0.07355889603024227
vertex -0.281 0.0007293447218348403 0.0036666635234538104
endloop
endfacet
facet normal 0.0 -0.29028467725446305 -0.9569403357322088
outer loop
vertex -0.281 0.001430661135030798 0.0034539215153514195
vertex -0.281 0.0007293447218348403 0.0036666635234538104
vertex -0.28300000000000003 0.001430661135030798 0.0034539215153514195
endloop
endfacet
facet normal -0.0 -0.29028467725446305 -0.9569403357322088
outer loop
vertex -0.28300000000000003 0.001430661135030798 0.0034539215153514195
vertex -0.281 0.0007293447218348403 0.0036666635234538104
vertex -0.28300000000000003 0.0007293447218348403 0.0036666635234538104
endloop
endfacet
facet normal -0.9999999999999999 0.0 0.0
outer loop
vertex -0.28300000000000003 0.0007293447218348403 0.0036666635234538104
vertex -0.28300000000000003 4.5783392525038305e-19 0.0037384977086384642
vertex -0.28300000000000003 0.014631774151209646 0.07355889603024227
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28300000000000003 0.014631774151209646 0.07355889603024227
vertex -0.28300000000000003 4.5783392525038305e-19 0.0037384977086384642
vertex -0.28300000000000003 9.184850993605149e-18 0.07499999999999998
endloop
endfacet
facet normal 0.0 0.09801714032956059 0.995184726672197
outer loop
vertex -0.28300000000000003 0.014631774151209646 0.07355889603024227
vertex -0.28300000000000003 9.184850993605149e-18 0.07499999999999998
vertex -0.281 0.014631774151209646 0.07355889603024227
endloop
endfacet
facet normal -0.0 0.09801714032956059 0.995184726672197
outer loop
vertex -0.281 0.014631774151209646 0.07355889603024227
vertex -0.28300000000000003 9.184850993605149e-18 0.07499999999999998
vertex -0.281 9.184850993605149e-18 0.07499999999999998
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex -0.281 0.014631774151209646 0.07355889603024227
vertex -0.281 9.184850993605149e-18 0.07499999999999998
vertex -0.281 0.0007293447218348403 0.0036666635234538104
endloop
endfacet
facet normal 0.9999999999999999 0.0 0.0
outer loop
vertex -0.281 0.0007293447218348403 0.0036666635234538104
vertex -0.281 9.184850993605149e-18 0.07499999999999998
vertex -0.281 4.5783392525038305e-19 0.0037384977086384642
endloop
endfacet
facet normal 0.0 -0.09801714032956045 -0.9951847266721969
outer loop
vertex -0.281 0.0007293447218348403 0.0036666635234538104
vertex -0.281 4.5783392525038305e-19 0.0037384977086384642
vertex -0.28300000000000003 0.0007293447218348403 0.0036666635234538104
endloop
endfacet
facet normal -0.0 -0.09801714032956045 -0.9951847266721969
outer loop
vertex -0.28300000000000003 0.0007293447218348403 0.0036666635234538104
vertex -0.281 4.5783392525038305e-19 0.0037384977086384642
vertex -0.28300000000000003 4.5783392525038305e-19 0.0037384977086384642
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28300000000000003 4.5783392525038305e-19 0.0037384977086384642
vertex -0.28300000000000003 -0.0007293447218348393 0.0036666635234538104
vertex -0.28300000000000003 9.184850993605149e-18 0.07499999999999998
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28300000000000003 9.184850993605149e-18 0.07499999999999998
vertex -0.28300000000000003 -0.0007293447218348393 0.0036666635234538104
vertex -0.28300000000000003 -0.014631774151209627 0.07355889603024227
endloop
endfacet
facet normal 0.0 -0.09801714032956059 0.9951847266721969
outer loop
vertex -0.28300000000000003 9.184850993605149e-18 0.07499999999999998
vertex -0.28300000000000003 -0.014631774151209627 0.07355889603024227
vertex -0.281 9.184850993605149e-18 0.07499999999999998
endloop
endfacet
facet normal 0.0 -0.09801714032956059 0.9951847266721969
outer loop
vertex -0.281 9.184850993605149e-18 0.07499999999999998
vertex -0.28300000000000003 -0.014631774151209627 0.07355889603024227
vertex -0.281 -0.014631774151209627 0.07355889603024227
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex -0.281 9.184850993605149e-18 0.07499999999999998
vertex -0.281 -0.014631774151209627 0.07355889603024227
vertex -0.281 4.5783392525038305e-19 0.0037384977086384642
endloop
endfacet
facet normal 0.9999999999999999 0.0 0.0
outer loop
vertex -0.281 4.5783392525038305e-19 0.0037384977086384642
vertex -0.281 -0.014631774151209627 0.07355889603024227
vertex -0.281 -0.0007293447218348393 0.0036666635234538104
endloop
endfacet
facet normal 0.0 0.09801714032956048 -0.995184726672197
outer loop
vertex -0.281 4.5783392525038305e-19 0.0037384977086384642
vertex -0.281 -0.0007293447218348393 0.0036666635234538104
vertex -0.28300000000000003 4.5783392525038305e-19 0.0037384977086384642
endloop
endfacet
facet normal 0.0 0.09801714032956048 -0.995184726672197
outer loop
vertex -0.28300000000000003 4.5783392525038305e-19 0.0037384977086384642
vertex -0.281 -0.0007293447218348393 0.0036666635234538104
vertex -0.28300000000000003 -0.0007293447218348393 0.0036666635234538104
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28300000000000003 -0.0007293447218348393 0.0036666635234538104
vertex -0.28300000000000003 -0.001430661135030797 0.00345392151535142
vertex -0.28300000000000003 -0.014631774151209627 0.07355889603024227
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.28300000000000003 -0.014631774151209627 0.07355889603024227
vertex -0.28300000000000003 -0.001430661135030797 0.00345392151535142
vertex -0.28300000000000003 -0.028701257427381725 0.0692909649383465
endloop
endfacet
facet normal 0.0 -0.2902846772544622 0.9569403357322087
outer loop
vertex -0.28300000000000003 -0.014631774151209627 0.07355889603024227
vertex -0.28300000000000003 -0.028701257427381725 0.0692909649383465
vertex -0.281 -0.014631774151209627 0.07355889603024227
endloop
endfacet
facet normal 0.0 -0.2902846772544622 0.9569403357322087
outer loop
vertex -0.281 -0.014631774151209627 0.07355889603024227
vertex -0.28300000000000003 -0.028701257427381725 0.0692909649383465
vertex -0.281 -0.028701257427381725 0.0692909649383465
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex -0.281 -0.014631774151209627 0.07355889603024227
vertex -0.281 -0.028701257427381725 0.0692909649383465
vertex -0.281 -0.0007293447218348393 0.0036666635234538104
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex -0.281 -0.0007293447218348393 0.0036666635234538104
vertex -0.281 -0.028701257427381725 0.0692909649383465
vertex -0.281 -0.001430661135030797 0.00345392151535142
endloop
endfacet
facet normal 0.0 0.29028467725446244 -0.9569403357322089
outer loop
vertex -0.281 -0.0007293447218348393 0.0036666635234538104
vertex -0.281 -0.001430661135030797 0.00345392151535142
vertex -0.28300000000000003 -0.0007293447218348393 0.0036666635234538104
endloop
endfacet
facet normal 0.0 0.29028467725446244 -0.9569403357322089
outer loop
vertex -0.28300000000000003 -0.0007293447218348393 0.0036666635234538104
vertex -0.281 -0.001430661135030797 0.00345392151535142
vertex -0.28300000000000003 -0.001430661135030797 0.00345392151535142
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28300000000000003 -0.001430661135030797 0.00345392151535142
vertex -0.28300000000000003 -0.002076998043131529 0.0031084472403955753
vertex -0.28300000000000003 -0.028701257427381725 0.0692909649383465
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.28300000000000003 -0.028701257427381725 0.0692909649383465
vertex -0.28300000000000003 -0.002076998043131529 0.0031084472403955753
vertex -0.28300000000000003 -0.04166776747647014 0.06236022092269089
endloop
endfacet
facet normal 0.0 -0.47139673682599764 0.8819212643483552
outer loop
vertex -0.28300000000000003 -0.028701257427381725 0.0692909649383465
vertex -0.28300000000000003 -0.04166776747647014 0.06236022092269089
vertex -0.281 -0.028701257427381725 0.0692909649383465
endloop
endfacet
facet normal 0.0 -0.47139673682599764 0.8819212643483552
outer loop
vertex -0.281 -0.028701257427381725 0.0692909649383465
vertex -0.28300000000000003 -0.04166776747647014 0.06236022092269089
vertex -0.281 -0.04166776747647014 0.06236022092269089
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex -0.281 -0.028701257427381725 0.0692909649383465
vertex -0.281 -0.04166776747647014 0.06236022092269089
vertex -0.281 -0.001430661135030797 0.00345392151535142
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex -0.281 -0.001430661135030797 0.00345392151535142
vertex -0.281 -0.04166776747647014 0.06236022092269089
vertex -0.281 -0.002076998043131529 0.0031084472403955753
endloop
endfacet
facet normal 0.0 0.47139673682599753 -0.8819212643483552
outer loop
vertex -0.281 -0.001430661135030797 0.00345392151535142
vertex -0.281 -0.002076998043131529 0.0031084472403955753
vertex -0.28300000000000003 -0.001430661135030797 0.00345392151535142
endloop
endfacet
facet normal 0.0 0.47139673682599753 -0.8819212643483552
outer loop
vertex -0.28300000000000003 -0.001430661135030797 0.00345392151535142
vertex -0.281 -0.002076998043131529 0.0031084472403955753
vertex -0.28300000000000003 -0.002076998043131529 0.0031084472403955753
endloop
endfacet
facet normal -0.9999999999999999 -0.0 0.0
outer loop
vertex -0.28300000000000003 -0.002076998043131529 0.0031084472403955753
vertex -0.28300000000000003 -0.00264351708122864 0.0026435170812286234
vertex -0.28300000000000003 -0.04166776747647014 0.06236022092269089
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.28300000000000003 -0.04166776747647014 0.06236022092269089
vertex -0.28300000000000003 -0.00264351708122864 0.0026435170812286234
vertex -0.28300000000000003 -0.05303300858899106 0.053033008588991064
endloop
endfacet
facet normal 0.0 -0.6343932841636448 0.7730104533627374
outer loop
vertex -0.28300000000000003 -0.04166776747647014 0.06236022092269089
vertex -0.28300000000000003 -0.05303300858899106 0.053033008588991064
vertex -0.281 -0.04166776747647014 0.06236022092269089
endloop
endfacet
facet normal 0.0 -0.6343932841636448 0.7730104533627374
outer loop
vertex -0.281 -0.04166776747647014 0.06236022092269089
vertex -0.28300000000000003 -0.05303300858899106 0.053033008588991064
vertex -0.281 -0.05303300858899106 0.053033008588991064
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex -0.281 -0.04166776747647014 0.06236022092269089
vertex -0.281 -0.05303300858899106 0.053033008588991064
vertex -0.281 -0.002076998043131529 0.0031084472403955753
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex -0.281 -0.002076998043131529 0.0031084472403955753
vertex -0.281 -0.05303300858899106 0.053033008588991064
vertex -0.281 -0.00264351708122864 0.0026435170812286234
endloop
endfacet
facet normal 0.0 0.6343932841636449 -0.7730104533627374
outer loop
vertex -0.281 -0.002076998043131529 0.0031084472403955753
vertex -0.281 -0.00264351708122864 0.0026435170812286234
vertex -0.28300000000000003 -0.002076998043131529 0.0031084472403955753
endloop
endfacet
facet normal 0.0 0.6343932841636449 -0.7730104533627374
outer loop
vertex -0.28300000000000003 -0.002076998043131529 0.0031084472403955753
vertex -0.281 -0.00264351708122864 0.0026435170812286234
vertex -0.28300000000000003 -0.00264351708122864 0.0026435170812286234
endloop
endfacet
facet normal -0.9999999999999999 -0.0 0.0
outer loop
vertex -0.28300000000000003 -0.00264351708122864 0.0026435170812286234
vertex -0.28300000000000003 -0.003108447240395592 0.0020769980431315127
vertex -0.28300000000000003 -0.05303300858899106 0.053033008588991064
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.28300000000000003 -0.05303300858899106 0.053033008588991064
vertex -0.28300000000000003 -0.003108447240395592 0.0020769980431315127
vertex -0.28300000000000003 -0.06236022092269089 0.04166776747647015
endloop
endfacet
facet normal 0.0 -0.7730104533627372 0.6343932841636452
outer loop
vertex -0.28300000000000003 -0.05303300858899106 0.053033008588991064
vertex -0.28300000000000003 -0.06236022092269089 0.04166776747647015
vertex -0.281 -0.05303300858899106 0.053033008588991064
endloop
endfacet
facet normal 0.0 -0.7730104533627372 0.6343932841636452
outer loop
vertex -0.281 -0.05303300858899106 0.053033008588991064
vertex -0.28300000000000003 -0.06236022092269089 0.04166776747647015
vertex -0.281 -0.06236022092269089 0.04166776747647015
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex -0.281 -0.05303300858899106 0.053033008588991064
vertex -0.281 -0.06236022092269089 0.04166776747647015
vertex -0.281 -0.00264351708122864 0.0026435170812286234
endloop
endfacet
facet normal 0.9999999999999999 0.0 0.0
outer loop
vertex -0.281 -0.00264351708122864 0.0026435170812286234
vertex -0.281 -0.06236022092269089 0.04166776747647015
vertex -0.281 -0.003108447240395592 0.0020769980431315127
endloop
endfacet
facet normal 0.0 0.7730104533627372 -0.6343932841636453
outer loop
vertex -0.281 -0.00264351708122864 0.0026435170812286234
vertex -0.281 -0.003108447240395592 0.0020769980431315127
vertex -0.28300000000000003 -0.00264351708122864 0.0026435170812286234
endloop
endfacet
facet normal 0.0 0.7730104533627372 -0.6343932841636453
outer loop
vertex -0.28300000000000003 -0.00264351708122864 0.0026435170812286234
vertex -0.281 -0.003108447240395592 0.0020769980431315127
vertex -0.28300000000000003 -0.003108447240395592 0.0020769980431315127
endloop
endfacet
facet normal -1.0 -0.0 0.0
outer loop
vertex -0.28300000000000003 -0.003108447240395592 0.0020769980431315127
vertex -0.28300000000000003 -0.003453921515351436 0.0014306611350307823
vertex -0.28300000000000003 -0.06236022092269089 0.04166776747647015
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.28300000000000003 -0.06236022092269089 0.04166776747647015
vertex -0.28300000000000003 -0.003453921515351436 0.0014306611350307823
vertex -0.28300000000000003 -0.06929096493834648 0.028701257427381756
endloop
endfacet
facet normal 0.0 -0.881921264348355 0.47139673682599753
outer loop
vertex -0.28300000000000003 -0.06236022092269089 0.04166776747647015
vertex -0.28300000000000003 -0.06929096493834648 0.028701257427381756
vertex -0.281 -0.06236022092269089 0.04166776747647015
endloop
endfacet
facet normal 0.0 -0.881921264348355 0.47139673682599753
outer loop
vertex -0.281 -0.06236022092269089 0.04166776747647015
vertex -0.28300000000000003 -0.06929096493834648 0.028701257427381756
vertex -0.281 -0.06929096493834648 0.028701257427381756
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex -0.281 -0.06236022092269089 0.04166776747647015
vertex -0.281 -0.06929096493834648 0.028701257427381756
vertex -0.281 -0.003108447240395592 0.0020769980431315127
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex -0.281 -0.003108447240395592 0.0020769980431315127
vertex -0.281 -0.06929096493834648 0.028701257427381756
vertex -0.281 -0.003453921515351436 0.0014306611350307825
endloop
endfacet
facet normal 0.0 0.881921264348355 -0.47139673682599775
outer loop
vertex -0.281 -0.003108447240395592 0.0020769980431315127
vertex -0.281 -0.003453921515351436 0.0014306611350307825
vertex -0.28300000000000003 -0.003108447240395592 0.0020769980431315127
endloop
endfacet
facet normal 5.1108936616932377e-17 0.881921264348355 -0.47139673682599764
outer loop
vertex -0.28300000000000003 -0.003108447240395592 0.0020769980431315127
vertex -0.281 -0.003453921515351436 0.0014306611350307825
vertex -0.28300000000000003 -0.003453921515351436 0.0014306611350307823
endloop
endfacet
facet normal -0.9999999999999999 -0.0 0.0
outer loop
vertex -0.28300000000000003 -0.003453921515351436 0.0014306611350307823
vertex -0.28300000000000003 -0.0036666635234538273 0.0007293447218348232
vertex -0.28300000000000003 -0.06929096493834648 0.028701257427381756
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.28300000000000003 -0.06929096493834648 0.028701257427381756
vertex -0.28300000000000003 -0.0036666635234538273 0.0007293447218348232
vertex -0.28300000000000003 -0.07355889603024227 0.014631774151209632
endloop
endfacet
facet normal 0.0 -0.9569403357322088 0.29028467725446266
outer loop
vertex -0.28300000000000003 -0.06929096493834648 0.028701257427381756
vertex -0.28300000000000003 -0.07355889603024227 0.014631774151209632
vertex -0.281 -0.06929096493834648 0.028701257427381756
endloop
endfacet
facet normal 0.0 -0.9569403357322088 0.29028467725446266
outer loop
vertex -0.281 -0.06929096493834648 0.028701257427381756
vertex -0.28300000000000003 -0.07355889603024227 0.014631774151209632
vertex -0.281 -0.07355889603024227 0.014631774151209632
endloop
endfacet
facet normal 1.0 0.0 0.0
outer loop
vertex -0.281 -0.06929096493834648 0.028701257427381756
vertex -0.281 -0.07355889603024227 0.014631774151209632
vertex -0.281 -0.003453921515351436 0.0014306611350307825
endloop
endfacet
facet normal 0.9999999999999999 0.0 0.0
outer loop
vertex -0.281 -0.003453921515351436 0.0014306611350307825
vertex -0.281 -0.07355889603024227 0.014631774151209632
vertex -0.281 -0.0036666635234538273 0.0007293447218348233
endloop
endfacet
facet normal 3.6117791202653276e-17 0.9569403357322087 -0.29028467725446294
outer loop
vertex -0.281 -0.003453921515351436 0.0014306611350307825
vertex -0.281 -0.0036666635234538273 0.0007293447218348233
vertex -0.28300000000000003 -0.003453921515351436 0.0014306611350307823
endloop
endfacet
facet normal 1.57363638859271e-17 0.9569403357322087 -0.290284677254463
outer loop
vertex -0.28300000000000003 -0.003453921515351436 0.0014306611350307823
vertex -0.281 -0.0036666635234538273 0.0007293447218348233
vertex -0.28300000000000003 -0.0036666635234538273 0.0007293447218348232
endloop
endfacet
facet normal -0.9999999999999999 -0.0 0.0
outer loop
vertex -0.28300000000000003 -0.0036666635234538273 0.0007293447218348232
vertex -0.28300000000000003 -0.0037384977086384816 -1.6642001320059475e-17
vertex -0.28300000000000003 -0.07355889603024227 0.014631774151209632
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.28300000000000003 -0.07355889603024227 0.014631774151209632
vertex -0.28300000000000003 -0.0037384977086384816 -1.6642001320059475e-17
vertex -0.28300000000000003 -0.075 -3.551475717527327e-18
endloop
endfacet
facet normal 0.0 -0.9951847266721969 0.09801714032956155
outer loop
vertex -0.28300000000000003 -0.07355889603024227 0.014631774151209632
vertex -0.28300000000000003 -0.075 -3.551475717527327e-18
vertex -0.281 -0.07355889603024227 0.014631774151209632
endloop
endfacet
facet normal -6.0018188583087245e-18 -0.9951847266721969 0.09801714032956155
outer loop
vertex -0.281 -0.07355889603024227 0.014631774151209632
vertex -0.28300000000000003 -0.075 -3.551475717527327e-18
vertex -0.281 -0.075 -3.4290110376125918e-18
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex -0.281 -0.07355889603024227 0.014631774151209632
vertex -0.281 -0.075 -3.4290110376125918e-18
vertex -0.281 -0.0036666635234538273 0.0007293447218348233
endloop
endfacet
facet normal 0.9999999999999999 0.0 0.0
outer loop
vertex -0.281 -0.0036666635234538273 0.0007293447218348233
vertex -0.281 -0.075 -3.4290110376125918e-18
vertex -0.281 -0.0037384977086384816 -1.651953664014474e-17
endloop
endfacet
facet normal 4.514723900331661e-18 0.9951847266721969 -0.09801714032956105
outer loop
vertex -0.281 -0.0036666635234538273 0.0007293447218348233
vertex -0.281 -0.0037384977086384816 -1.651953664014474e-17
vertex -0.28300000000000003 -0.0036666635234538273 0.0007293447218348232
endloop
endfacet
facet normal 6.001818858308676e-18 0.9951847266721969 -0.09801714032956105
outer loop
vertex -0.28300000000000003 -0.0036666635234538273 0.0007293447218348232
vertex -0.281 -0.0037384977086384816 -1.651953664014474e-17
vertex -0.28300000000000003 -0.0037384977086384816 -1.6642001320059475e-17
endloop
endfacet
facet normal -1.0 -0.0 -0.0
outer loop
vertex -0.28300000000000003 -0.0037384977086384816 -1.6642001320059475e-17
vertex -0.28300000000000003 -0.0036666635234538277 -0.0007293447218348566
vertex -0.28300000000000003 -0.075 -3.551475717527327e-18
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28300000000000003 -0.075 -3.551475717527327e-18
vertex -0.28300000000000003 -0.0036666635234538277 -0.0007293447218348566
vertex -0.28300000000000003 -0.07355889603024228 -0.014631774151209639
endloop
endfacet
facet normal 0.0 -0.9951847266721969 -0.09801714032956059
outer loop
vertex -0.28300000000000003 -0.075 -3.551475717527327e-18
vertex -0.28300000000000003 -0.07355889603024228 -0.014631774151209639
vertex -0.281 -0.075 -3.4290110376125918e-18
endloop
endfacet
facet normal 0.0 -0.9951847266721969 -0.09801714032956059
outer loop
vertex -0.281 -0.075 -3.4290110376125918e-18
vertex -0.28300000000000003 -0.07355889603024228 -0.014631774151209639
vertex -0.281 -0.07355889603024228 -0.014631774151209639
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex -0.281 -0.075 -3.4290110376125918e-18
vertex -0.281 -0.07355889603024228 -0.014631774151209639
vertex -0.281 -0.0037384977086384816 -1.651953664014474e-17
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex -0.281 -0.0037384977086384816 -1.651953664014474e-17
vertex -0.281 -0.07355889603024228 -0.014631774151209639
vertex -0.281 -0.0036666635234538277 -0.0007293447218348565
endloop
endfacet
facet normal -4.51472390033166e-18 0.995184726672197 0.09801714032956045
outer loop
vertex -0.281 -0.0037384977086384816 -1.651953664014474e-17
vertex -0.281 -0.0036666635234538277 -0.0007293447218348565
vertex -0.28300000000000003 -0.0037384977086384816 -1.6642001320059475e-17
endloop
endfacet
facet normal -5.313519824306294e-18 0.995184726672197 0.09801714032956045
outer loop
vertex -0.28300000000000003 -0.0037384977086384816 -1.6642001320059475e-17
vertex -0.281 -0.0036666635234538277 -0.0007293447218348565
vertex -0.28300000000000003 -0.0036666635234538277 -0.0007293447218348566
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28300000000000003 -0.0036666635234538277 -0.0007293447218348566
vertex -0.28300000000000003 -0.0034539215153514364 -0.0014306611350308157
vertex -0.28300000000000003 -0.07355889603024228 -0.014631774151209639
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28300000000000003 -0.07355889603024228 -0.014631774151209639
vertex -0.28300000000000003 -0.0034539215153514364 -0.0014306611350308157
vertex -0.28300000000000003 -0.0692909649383465 -0.028701257427381766
endloop
endfacet
facet normal 0.0 -0.9569403357322088 -0.2902846772544626
outer loop
vertex -0.28300000000000003 -0.07355889603024228 -0.014631774151209639
vertex -0.28300000000000003 -0.0692909649383465 -0.028701257427381766
vertex -0.281 -0.07355889603024228 -0.014631774151209639
endloop
endfacet
facet normal 0.0 -0.9569403357322088 -0.2902846772544626
outer loop
vertex -0.281 -0.07355889603024228 -0.014631774151209639
vertex -0.28300000000000003 -0.0692909649383465 -0.028701257427381766
vertex -0.281 -0.0692909649383465 -0.028701257427381766
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex -0.281 -0.07355889603024228 -0.014631774151209639
vertex -0.281 -0.0692909649383465 -0.028701257427381766
vertex -0.281 -0.0036666635234538277 -0.0007293447218348565
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex -0.281 -0.0036666635234538277 -0.0007293447218348565
vertex -0.281 -0.0692909649383465 -0.028701257427381766
vertex -0.281 -0.0034539215153514364 -0.0014306611350308155
endloop
endfacet
facet normal 0.0 0.9569403357322087 0.29028467725446305
outer loop
vertex -0.281 -0.0036666635234538277 -0.0007293447218348565
vertex -0.281 -0.0034539215153514364 -0.0014306611350308155
vertex -0.28300000000000003 -0.0036666635234538277 -0.0007293447218348566
endloop
endfacet
facet normal -3.14727277718542e-17 0.9569403357322087 0.290284677254463
outer loop
vertex -0.28300000000000003 -0.0036666635234538277 -0.0007293447218348566
vertex -0.281 -0.0034539215153514364 -0.0014306611350308155
vertex -0.28300000000000003 -0.0034539215153514364 -0.0014306611350308157
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28300000000000003 -0.0034539215153514364 -0.0014306611350308157
vertex -0.28300000000000003 -0.0031084472403955926 -0.002076998043131546
vertex -0.28300000000000003 -0.0692909649383465 -0.028701257427381766
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28300000000000003 -0.0692909649383465 -0.028701257427381766
vertex -0.28300000000000003 -0.0031084472403955926 -0.002076998043131546
vertex -0.28300000000000003 -0.062360220922690904 -0.04166776747647015
endloop
endfacet
facet normal 0.0 -0.8819212643483549 -0.47139673682599786
outer loop
vertex -0.28300000000000003 -0.0692909649383465 -0.028701257427381766
vertex -0.28300000000000003 -0.062360220922690904 -0.04166776747647015
vertex -0.281 -0.0692909649383465 -0.028701257427381766
endloop
endfacet
facet normal 0.0 -0.8819212643483549 -0.47139673682599786
outer loop
vertex -0.281 -0.0692909649383465 -0.028701257427381766
vertex -0.28300000000000003 -0.062360220922690904 -0.04166776747647015
vertex -0.281 -0.062360220922690904 -0.04166776747647015
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex -0.281 -0.0692909649383465 -0.028701257427381766
vertex -0.281 -0.062360220922690904 -0.04166776747647015
vertex -0.281 -0.0034539215153514364 -0.0014306611350308155
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex -0.281 -0.0034539215153514364 -0.0014306611350308155
vertex -0.281 -0.062360220922690904 -0.04166776747647015
vertex -0.281 -0.0031084472403955926 -0.002076998043131546
endloop
endfacet
facet normal -5.4176686803980164e-17 0.881921264348355 0.4713967368259975
outer loop
vertex -0.281 -0.0034539215153514364 -0.0014306611350308155
vertex -0.281 -0.0031084472403955926 -0.002076998043131546
vertex -0.28300000000000003 -0.0034539215153514364 -0.0014306611350308157
endloop
endfacet
facet normal 0.0 0.881921264348355 0.47139673682599764
outer loop
vertex -0.28300000000000003 -0.0034539215153514364 -0.0014306611350308157
vertex -0.281 -0.0031084472403955926 -0.002076998043131546
vertex -0.28300000000000003 -0.0031084472403955926 -0.002076998043131546
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28300000000000003 -0.0031084472403955926 -0.002076998043131546
vertex -0.28300000000000003 -0.0026435170812286407 -0.002643517081228657
vertex -0.28300000000000003 -0.062360220922690904 -0.04166776747647015
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28300000000000003 -0.062360220922690904 -0.04166776747647015
vertex -0.28300000000000003 -0.0026435170812286407 -0.002643517081228657
vertex -0.28300000000000003 -0.05303300858899108 -0.053033008588991064
endloop
endfacet
facet normal 0.0 -0.7730104533627374 -0.6343932841636448
outer loop
vertex -0.28300000000000003 -0.062360220922690904 -0.04166776747647015
vertex -0.28300000000000003 -0.05303300858899108 -0.053033008588991064
vertex -0.281 -0.062360220922690904 -0.04166776747647015
endloop
endfacet
facet normal 0.0 -0.7730104533627374 -0.6343932841636448
outer loop
vertex -0.281 -0.062360220922690904 -0.04166776747647015
vertex -0.28300000000000003 -0.05303300858899108 -0.053033008588991064
vertex -0.281 -0.05303300858899108 -0.053033008588991064
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex -0.281 -0.062360220922690904 -0.04166776747647015
vertex -0.281 -0.05303300858899108 -0.053033008588991064
vertex -0.281 -0.0031084472403955926 -0.002076998043131546
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex -0.281 -0.0031084472403955926 -0.002076998043131546
vertex -0.281 -0.05303300858899108 -0.053033008588991064
vertex -0.281 -0.0026435170812286407 -0.002643517081228657
endloop
endfacet
facet normal 0.0 0.7730104533627374 0.6343932841636449
outer loop
vertex -0.281 -0.0031084472403955926 -0.002076998043131546
vertex -0.281 -0.0026435170812286407 -0.002643517081228657
vertex -0.28300000000000003 -0.0031084472403955926 -0.002076998043131546
endloop
endfacet
facet normal 0.0 0.7730104533627374 0.6343932841636449
outer loop
vertex -0.28300000000000003 -0.0031084472403955926 -0.002076998043131546
vertex -0.281 -0.0026435170812286407 -0.002643517081228657
vertex -0.28300000000000003 -0.0026435170812286407 -0.002643517081228657
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28300000000000003 -0.0026435170812286407 -0.002643517081228657
vertex -0.28300000000000003 -0.00207699804313153 -0.0031084472403956095
vertex -0.28300000000000003 -0.05303300858899108 -0.053033008588991064
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28300000000000003 -0.05303300858899108 -0.053033008588991064
vertex -0.28300000000000003 -0.00207699804313153 -0.0031084472403956095
vertex -0.28300000000000003 -0.04166776747647016 -0.062360220922690904
endloop
endfacet
facet normal 0.0 -0.6343932841636455 -0.7730104533627371
outer loop
vertex -0.28300000000000003 -0.05303300858899108 -0.053033008588991064
vertex -0.28300000000000003 -0.04166776747647016 -0.062360220922690904
vertex -0.281 -0.05303300858899108 -0.053033008588991064
endloop
endfacet
facet normal 0.0 -0.6343932841636455 -0.7730104533627371
outer loop
vertex -0.281 -0.05303300858899108 -0.053033008588991064
vertex -0.28300000000000003 -0.04166776747647016 -0.062360220922690904
vertex -0.281 -0.04166776747647016 -0.062360220922690904
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex -0.281 -0.05303300858899108 -0.053033008588991064
vertex -0.281 -0.04166776747647016 -0.062360220922690904
vertex -0.281 -0.0026435170812286407 -0.002643517081228657
endloop
endfacet
facet normal 0.9999999999999999 -0.0 0.0
outer loop
vertex -0.281 -0.0026435170812286407 -0.002643517081228657
vertex -0.281 -0.04166776747647016 -0.062360220922690904
vertex -0.281 -0.00207699804313153 -0.0031084472403956095
endloop
endfacet
facet normal 0.0 0.6343932841636456 0.7730104533627368
outer loop
vertex -0.281 -0.0026435170812286407 -0.002643517081228657
vertex -0.281 -0.00207699804313153 -0.0031084472403956095
vertex -0.28300000000000003 -0.0026435170812286407 -0.002643517081228657
endloop
endfacet
facet normal 0.0 0.6343932841636456 0.7730104533627368
outer loop
vertex -0.28300000000000003 -0.0026435170812286407 -0.002643517081228657
vertex -0.281 -0.00207699804313153 -0.0031084472403956095
vertex -0.28300000000000003 -0.00207699804313153 -0.0031084472403956095
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28300000000000003 -0.00207699804313153 -0.0031084472403956095
vertex -0.28300000000000003 -0.0014306611350307999 -0.0034539215153514533
vertex -0.28300000000000003 -0.04166776747647016 -0.062360220922690904
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28300000000000003 -0.04166776747647016 -0.062360220922690904
vertex -0.28300000000000003 -0.0014306611350307999 -0.0034539215153514533
vertex -0.28300000000000003 -0.028701257427381777 -0.0692909649383465
endloop
endfacet
facet normal 0.0 -0.47139673682599775 -0.881921264348355
outer loop
vertex -0.28300000000000003 -0.04166776747647016 -0.062360220922690904
vertex -0.28300000000000003 -0.028701257427381777 -0.0692909649383465
vertex -0.281 -0.04166776747647016 -0.062360220922690904
endloop
endfacet
facet normal 0.0 -0.47139673682599775 -0.881921264348355
outer loop
vertex -0.281 -0.04166776747647016 -0.062360220922690904
vertex -0.28300000000000003 -0.028701257427381777 -0.0692909649383465
vertex -0.281 -0.028701257427381777 -0.0692909649383465
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex -0.281 -0.04166776747647016 -0.062360220922690904
vertex -0.281 -0.028701257427381777 -0.0692909649383465
vertex -0.281 -0.00207699804313153 -0.0031084472403956095
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex -0.281 -0.00207699804313153 -0.0031084472403956095
vertex -0.281 -0.028701257427381777 -0.0692909649383465
vertex -0.281 -0.0014306611350307999 -0.0034539215153514533
endloop
endfacet
facet normal 0.0 0.47139673682599775 0.881921264348355
outer loop
vertex -0.281 -0.00207699804313153 -0.0031084472403956095
vertex -0.281 -0.0014306611350307999 -0.0034539215153514533
vertex -0.28300000000000003 -0.00207699804313153 -0.0031084472403956095
endloop
endfacet
facet normal 0.0 0.47139673682599775 0.881921264348355
outer loop
vertex -0.28300000000000003 -0.00207699804313153 -0.0031084472403956095
vertex -0.281 -0.0014306611350307999 -0.0034539215153514533
vertex -0.28300000000000003 -0.0014306611350307999 -0.0034539215153514533
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28300000000000003 -0.0014306611350307999 -0.0034539215153514533
vertex -0.28300000000000003 -0.0007293447218348407 -0.0036666635234538446
vertex -0.28300000000000003 -0.028701257427381777 -0.0692909649383465
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28300000000000003 -0.028701257427381777 -0.0692909649383465
vertex -0.28300000000000003 -0.0007293447218348407 -0.0036666635234538446
vertex -0.28300000000000003 -0.014631774151209653 -0.07355889603024228
endloop
endfacet
facet normal 0.0 -0.29028467725446266 -0.9569403357322088
outer loop
vertex -0.28300000000000003 -0.028701257427381777 -0.0692909649383465
vertex -0.28300000000000003 -0.014631774151209653 -0.07355889603024228
vertex -0.281 -0.028701257427381777 -0.0692909649383465
endloop
endfacet
facet normal 0.0 -0.29028467725446266 -0.9569403357322088
outer loop
vertex -0.281 -0.028701257427381777 -0.0692909649383465
vertex -0.28300000000000003 -0.014631774151209653 -0.07355889603024228
vertex -0.281 -0.014631774151209653 -0.07355889603024228
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex -0.281 -0.028701257427381777 -0.0692909649383465
vertex -0.281 -0.014631774151209653 -0.07355889603024228
vertex -0.281 -0.0014306611350307999 -0.0034539215153514533
endloop
endfacet
facet normal 0.9999999999999999 -0.0 0.0
outer loop
vertex -0.281 -0.0014306611350307999 -0.0034539215153514533
vertex -0.281 -0.014631774151209653 -0.07355889603024228
vertex -0.281 -0.0007293447218348407 -0.0036666635234538446
endloop
endfacet
facet normal 0.0 0.290284677254463 0.9569403357322087
outer loop
vertex -0.281 -0.0014306611350307999 -0.0034539215153514533
vertex -0.281 -0.0007293447218348407 -0.0036666635234538446
vertex -0.28300000000000003 -0.0014306611350307999 -0.0034539215153514533
endloop
endfacet
facet normal 0.0 0.290284677254463 0.9569403357322087
outer loop
vertex -0.28300000000000003 -0.0014306611350307999 -0.0034539215153514533
vertex -0.281 -0.0007293447218348407 -0.0036666635234538446
vertex -0.28300000000000003 -0.0007293447218348407 -0.0036666635234538446
endloop
endfacet
facet normal -1.0 0.0 -0.0
outer loop
vertex -0.28300000000000003 -0.0007293447218348407 -0.0036666635234538446
vertex -0.28300000000000003 0.0 -0.003738497708638499
vertex -0.28300000000000003 -0.014631774151209653 -0.07355889603024228
endloop
endfacet
facet normal -1.0 0.0 0.0
outer loop
vertex -0.28300000000000003 -0.014631774151209653 -0.07355889603024228
vertex -0.28300000000000003 0.0 -0.003738497708638499
vertex -0.28300000000000003 0.0 -0.07500000000000001
endloop
endfacet
facet normal 0.0 -0.09801714032956142 -0.9951847266721967
outer loop
vertex -0.28300000000000003 -0.014631774151209653 -0.07355889603024228
vertex -0.28300000000000003 0.0 -0.07500000000000001
vertex -0.281 -0.014631774151209653 -0.07355889603024228
endloop
endfacet
facet normal 0.0 -0.09801714032956142 -0.9951847266721967
outer loop
vertex -0.281 -0.014631774151209653 -0.07355889603024228
vertex -0.28300000000000003 0.0 -0.07500000000000001
vertex -0.281 0.0 -0.07500000000000001
endloop
endfacet
facet normal 1.0 -0.0 -0.0
outer loop
vertex -0.281 -0.014631774151209653 -0.07355889603024228
vertex -0.281 0.0 -0.07500000000000001
vertex -0.281 -0.0007293447218348407 -0.0036666635234538446
endloop
endfacet
facet normal 1.0 -0.0 0.0
outer loop
vertex -0.281 -0.0007293447218348407 -0.0036666635234538446
vertex -0.281 0.0 -0.07500000000000001
vertex -0.281 0.0 -0.003738497708638499
endloop
endfacet
facet normal 0.0 0.09801714032956091 0.9951847266721968
outer loop
vertex -0.281 -0.0007293447218348407 -0.0036666635234538446
vertex -0.281 0.0 -0.003738497708638499
vertex -0.28300000000000003 -0.0007293447218348407 -0.0036666635234538446
endloop
endfacet
facet normal 0.0 0.09801714032956091 0.9951847266721968
outer loop
vertex -0.28300000000000003 -0.0007293447218348407 -0.0036666635234538446
vertex -0.281 0.0 -0.003738497708638499
vertex -0.28300000000000003 0.0 -0.003738497708638499
endloop
endfacet

endsolid
""")

write_file("constant/cylinder/thermophysicalProperties", """/*--------------------------------*- C++ -*----------------------------------*\\
  =========                 |
  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\\\    /   O peration     | Website:  https://openfoam.org
    \\\\  /    A nd           | Version:  13
     \\\\/     M anipulation  |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant/cylinder";
    object      thermophysicalProperties;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

thermoType
{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       constIsoSolid;
    thermo          eConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleInternalEnergy;
}

mixture
{
    specie
    {
        nMoles          1;
        molWeight       12;
    }
    transport
    {
        kappa           0.84126;
    }
    thermodynamics
    {
        Hf              0;
        Cv              857.41;
    }
    equationOfState
    {
        rho             1570;
    }
}
""")

write_file("constant/cylinder/radiationProperties", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant/cylinder";
    object      radiationProperties;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

radiation       on;
radiationModel  opaqueSolid;
emissivity      0.1;
""")

write_file("system/controlDict", """/*--------------------------------*- C++ -*----------------------------------*\\
  =========                 |
  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\\\    /   O peration     | Website:  https://openfoam.org
    \\\\  /    A nd           | Version:  13
     \\\\/     M anipulation  |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    format      ascii;
    class       dictionary;
    location    "system";
    object      controlDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

application     foamMultiRun;

startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         10;
deltaT          0.0001;
adjustTimeStep  yes;
maxCo           1.0;
maxDi           1.0;
writeControl    timeStep;
writeInterval   10;
purgeWrite      0;
writeFormat     ascii;
writePrecision  6;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;

modules
(
    fluid
    {
        regions (air);
    }
    solid
    {
        regions (cylinder heater glass);
    }
);

functions
{
    // Monitor maximum temperature in the heater
    maxT_heater
    {
        type            volFieldValue;
        libs            ("libfieldFunctionObjects.so");
        log             true;
        writeControl    timeStep;
        writeInterval   1;
        region          heater;
        operation       max;
        fields          (T);
    }



    // Add residual plotting data (so the user can plot graphs using foamMonitor)

    // Extract the cylinder surface temperature for detailed analysis
    cylinderSurface
    {
        type            surfaces;
        libs            ("libsampling.so");
        writeControl    timeStep;
        writeInterval   10;
        region          air;

        surfaceFormat   vtk;

        fields          (T);

        surfaces
        {
            cylinder_surface
            {
                type        patch;
                patches     (".*_to_cylinder");
                interpolate true;
            }
        }
    }

    residuals
    {
        type            residuals;
        libs            ("libutilityFunctionObjects.so");
        writeControl    timeStep;
        writeInterval   1;
        fields          (U p T k epsilon);
    }
}
// ************************************************************************* //
""")

write_file("system/fvSchemes", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvSchemes;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

ddtSchemes
{
    default         Euler;
}

gradSchemes
{
    default         Gauss linear;
}

divSchemes
{
    default         none;
}

laplacianSchemes
{
    default         Gauss linear orthogonal;
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         orthogonal;
}

// ************************************************************************* //
""")

write_file("system/topoSetDict", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      topoSetDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

actions
(
    {
        name    air;
        type    cellSet;
        action  new;
        source  boxToCell;
        box     (-20 -20 -20) (20 20 20);
    }
    {
        name    air;
        type    cellSet;
        action  delete;
        source  zoneToCell;
        zone    heater;
    }
    {
        name    air;
        type    cellSet;
        action  delete;
        source  zoneToCell;
        zone    cylinder;
    }
    {
        name    air;
        type    cellSet;
        action  delete;
        source  zoneToCell;
        zone    glass;
    }
    {
        name    air;
        type    cellZoneSet;
        action  new;
        source  setToCellZone;
        set     air;
    }
);

// ************************************************************************* //
""")

write_file("system/decomposeParDict", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      decomposeParDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

numberOfSubdomains 4;

method          scotch;

// ************************************************************************* //
""")

write_file("system/surfaceFeaturesDict", """/*--------------------------------*- C++ -*----------------------------------*\\
  =========                 |
  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\\\    /   O peration     | Website:  https://openfoam.org
    \\\\  /    A nd           | Version:  13
     \\\\/     M anipulation  |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    format      ascii;
    class       dictionary;
    object      surfaceFeaturesDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

cylinder.stl
{
    includedAngle   150;
}

heater.stl
{
    includedAngle   150;
}

glass.stl
{
    includedAngle   150;
}

// ************************************************************************* //
""")

write_file("system/snappyHexMeshDict", """/*--------------------------------*- C++ -*----------------------------------*\\
  =========                 |
  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\\\    /   O peration     | Website:  https://openfoam.org
    \\\\  /    A nd           | Version:  13
     \\\\/     M anipulation  |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    format      ascii;
    class       dictionary;
    object      snappyHexMeshDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

castellatedMesh true;
snap            true;
addLayers       false;

geometry
{
    cylinder.stl
    {
        type triSurfaceMesh;
        file "cylinder.stl";
        name cylinder;
    }
    heater.stl
    {
        type triSurfaceMesh;
        file "heater.stl";
        name heater;
    }
    glass.stl
    {
        type triSurfaceMesh;
        file "glass.stl";
        name glass;
    }
    # innerAir is enclosed by cylinder and glass. We don't necessarily need a separate STL
    # if we seed it properly, but OpenFOAM's splitMeshRegions with -cellZones uses the cellZones from sHM.
    # To zone innerAir, let's use the cylinder and glass to define a closed volume if possible.
    # Wait, if we use the same surface for two zones, it's tricky.
    # A cleaner way is to let splitMeshRegions detect disconnected regions.
    # But sHM assigns all unassigned cells to the 'air' region by default (since no cellZone is specified for the background mesh, it becomes domain0, then renamed).
}

castellatedMeshControls
{
    maxLocalCells 1000000;
    maxGlobalCells 2000000;
    minRefinementCells 10;
    maxLoadUnbalance 0.10;
    nCellsBetweenLevels 1;

    features
    (
        { file "cylinder.eMesh"; level 2; }
        { file "heater.eMesh"; level 2; }
        { file "glass.eMesh"; level 2; }
    );

    refinementSurfaces
    {
        cylinder
        {
            level (7 8);
            regions { ".*" { level (7 8); } }
            faceZone cylinder;
            cellZone cylinder;
            cellZoneInside inside;
            insidePoint (0.0 0.0745 0.0);
        }
        heater
        {
            level (5 6);
            regions { ".*" { level (5 6); } }
            faceZone heater;
            cellZone heater;
            cellZoneInside inside;
            insidePoint (0.0 0.0 0.0);
        }
        glass
        {
            level (5 6);
            regions { ".*" { level (5 6); } }
            faceZone glass;
            cellZone glass;
            cellZoneInside inside;
            insidePoints ((0.281 0.05 0.0) (-0.281 0.05 0.0));
        }
    }

    resolveFeatureAngle 30;

    refinementRegions
    {
        cylinder
        {
            mode inside;
            level 8;
        }
        heater
        {
            mode inside;
            level 6;
        }
        glass
        {
            mode inside;
            level 6;
        }
    }

    insidePoints
    (
        (0.0 2.0 2.0)   // External air (outside cylinder)

    );
    allowFreeStandingZoneFaces true;
}

snapControls
{
    nSmoothPatch 3;
    tolerance 2.0;
    nSolveIter 300;
    nRelaxIter 5;
    nFeatureSnapIter 10;
    implicitFeatureSnap false;
    explicitFeatureSnap true;
    multiRegionFeatureSnap true;
}

addLayersControls
{
    relativeSizes true;
    layers
    {
    }
    expansionRatio 1.0;
    finalLayerThickness 0.3;
    minThickness 0.1;
    nGrow 0;
    featureAngle 30;
    nRelaxIter 3;
    nSmoothSurfaceNormals 1;
    nSmoothNormals 3;
    nSmoothThickness 10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedianAxisAngle 90;
    nBufferCellsNoExtrude 0;
    nLayerIter 50;
}

meshQualityControls
{
    #include "meshQualityDict"
}

writeFlags
(
    scalarLevels
    layerSets
    layerFields
);

mergeTolerance 1e-6;

// ************************************************************************* //
""")

write_file("system/meshQualityDict", """/*--------------------------------*- C++ -*----------------------------------*\\
  =========                 |
  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\\\    /   O peration     | Website:  https://openfoam.org
    \\\\  /    A nd           | Version:  13
     \\\\/     M anipulation  |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    format      ascii;
    class       dictionary;
    object      meshQualityDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

maxNonOrtho 65;
maxBoundarySkewness 20;
maxInternalSkewness 4;
maxConcave 80;
minVol 1e-13;
minTetQuality 1e-30;
minArea -1;
minTwist 0.01;
minDeterminant 0.001;
minFaceWeight 0.02;
minVolRatio 0.01;
triangleTwist -1;
nSmoothScale 4;
errorReduction 0.75;
relaxed
{
    maxNonOrtho 75;
}

// ************************************************************************* //
""")

write_file("system/fvSolution", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      fvSolution;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

solvers
{
    p
    {
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-06;
        relTol          0;
    }
}

// ************************************************************************* //
""")

write_file("system/blockMeshDict", """/*--------------------------------*- C++ -*----------------------------------*\\
  =========                 |
  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\\\    /   O peration     | Website:  https://openfoam.org
    \\\\  /    A nd           | Version:  13
     \\\\/     M anipulation  |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    format      ascii;
    class       dictionary;
    object      blockMeshDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

scale   1;

vertices
(
    (-11.2 -3 -3)
    ( 11.2 -3 -3)
    ( 11.2  3 -3)
    (-11.2  3 -3)
    (-11.2 -3  3)
    ( 11.2 -3  3)
    ( 11.2  3  3)
    (-11.2  3  3)
);

blocks
(
    hex (0 1 2 3 4 5 6 7) (200 60 60) simpleGrading (1 1 1)
);

edges
(
);

boundary
(
    inlet
    {
        type patch;
        faces
        (
            (0 4 7 3)
        );
    }
    outlet
    {
        type patch;
        faces
        (
            (1 2 6 5)
        );
    }
    topAndBottom
    {
        type patch;
        faces
        (
            (3 7 6 2)
            (0 1 5 4)
        );
    }
    frontAndBack
    {
        type patch;
        faces
        (
            (4 5 6 7)
            (0 3 2 1)
        );
    }
);

mergePatchPairs
(
);

// ************************************************************************* //
""")

write_file("system/glass/fvSchemes", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system/glass";
    object      fvSchemes;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

ddtSchemes
{
    default         Euler;
}

gradSchemes
{
    default         Gauss linear;
}

divSchemes
{
    default         none;
}

laplacianSchemes
{
    default         Gauss linear orthogonal;
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         orthogonal;
}
// ************************************************************************* //
""")

write_file("system/glass/changeDictionaryDict", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system/glass";
    object      changeDictionaryDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dictionaryReplacement
{






    T
    {
        boundaryField
        {
            ".*_to_.*"
            {
                type            coupledTemperature;
                Tnbr            T;
                kappaMethod     solidThermo;
                value           uniform 300;
            }
        }
    }



}
// ************************************************************************* //
""")

write_file("system/glass/fvSolution", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system/glass";
    object      fvSolution;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

solvers
{
    e
    {
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-7;
        relTol          0.01;
    }
}

SIMPLE
{
    nNonOrthogonalCorrectors 0;
}

PIMPLE
{
    nOuterCorrectors 2;
    nCorrectors      2;
    nNonOrthogonalCorrectors 0;
    pRefCell         0;
    pRefValue        0;
}
""")

write_file("system/heater/fvSchemes", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system/heater";
    object      fvSchemes;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

ddtSchemes
{
    default         Euler;
}

gradSchemes
{
    default         Gauss linear;
}

divSchemes
{
    default         none;
}

laplacianSchemes
{
    default         Gauss linear orthogonal;
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         orthogonal;
}
// ************************************************************************* //
""")

write_file("system/heater/changeDictionaryDict", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system/heater";
    object      changeDictionaryDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dictionaryReplacement
{






    T
    {
        boundaryField
        {
            ".*_to_.*"
            {
                type            coupledTemperature;
                Tnbr            T;
                kappaMethod     solidThermo;
                value           uniform 300;
            }
        }
    }



}
// ************************************************************************* //
""")

write_file("system/heater/fvModels", """/*--------------------------------*- C++ -*----------------------------------*\\
  =========                 |
  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\\\    /   O peration     | Website:  https://openfoam.org
    \\\\  /    A nd           | Version:  13
     \\\\/     M anipulation  |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system/heater";
    object      fvModels;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

heaterSource
{
    type            scalarSemiImplicitSource;
    active          true;
    selectionMode   all;
    volumeMode      absolute;
    sources
    {
        e           (225 0);
    }
}
""")

write_file("system/heater/fvSolution", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system/heater";
    object      fvSolution;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

solvers
{
    e
    {
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-7;
        relTol          0.01;
    }
}

SIMPLE
{
    nNonOrthogonalCorrectors 0;
}

PIMPLE
{
    nOuterCorrectors 2;
    nCorrectors      2;
    nNonOrthogonalCorrectors 0;
    pRefCell         0;
    pRefValue        0;
}
""")

write_file("system/air/fvSchemes", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system/air";
    object      fvSchemes;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

ddtSchemes
{
    default         Euler;
}

gradSchemes
{
    default         Gauss linear;
}

divSchemes
{
    div(I)          Gauss upwind;
    default         none;
    div(phi,U)      Gauss upwind;
    div(phi,K)      Gauss upwind;
    div(phi,e)      Gauss upwind;
    div(phi,h)      Gauss upwind;
    div(phi,k)      Gauss upwind;
    div(phi,epsilon) Gauss upwind;
    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;
}

laplacianSchemes
{
    default         Gauss linear orthogonal;
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         orthogonal;
}
""")

write_file("system/air/changeDictionaryDict", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system/air";
    object      changeDictionaryDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dictionaryReplacement
{






    T
    {
        boundaryField
        {
            ".*_to_.*"
            {
                type            coupledTemperature;
                Tnbr            T;
                kappaMethod     fluidThermo;
                value           uniform 300;
            }
        }
    }

    U
    {
        boundaryField
        {
            ".*_to_.*"
            {
                type            noSlip;
            }
        }
    }
    p_rgh
    {
        boundaryField
        {
            ".*_to_.*"
            {
                type            fixedFluxPressure;
                value           uniform 100000;
            }
        }
    }
    k
    {
        boundaryField
        {
            ".*_to_.*"
            {
                type            kqRWallFunction;
                value           uniform 0.1;
            }
        }
    }
    epsilon
    {
        boundaryField
        {
            ".*_to_.*"
            {
                type            epsilonWallFunction;
                value           uniform 0.01;
            }
        }
    }
    nut
    {
        boundaryField
        {
            ".*_to_.*"
            {
                type            nutkWallFunction;
                value           uniform 0;
            }
        }
    }
    alphat
    {
        boundaryField
        {
            ".*_to_.*"
            {
                type            alphatJayatillekeWallFunction;
                value           uniform 0;
            }
        }
    }



}
// ************************************************************************* //
""")

write_file("system/air/fvSolution", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system/air";
    object      fvSolution;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

solvers
{
    I
    {
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-05;
        relTol          0.1;
    }

    p_rgh
    {
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-7;
        relTol          0.01;
    }

    "(U|e|k|epsilon)"
    {
        solver          PBiCGStab;
        preconditioner  DILU;
        tolerance       1e-7;
        relTol          0.1;
    }
}

SIMPLE
{
    nNonOrthogonalCorrectors 0;
    pRefCell        0;
    pRefValue       0;
}

relaxationFactors
{
    equations
    {
        U               0.9;
        e               0.9;
        k               0.9;
        epsilon         0.9;
    }
}

PIMPLE
{
    nOuterCorrectors 2;
    nCorrectors      2;
    nNonOrthogonalCorrectors 0;
    pRefCell         0;
    pRefValue        0;
}
""")

write_file("system/cylinder/fvSchemes", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system/cylinder";
    object      fvSchemes;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

ddtSchemes
{
    default         Euler;
}

gradSchemes
{
    default         Gauss linear;
}

divSchemes
{
    default         none;
}

laplacianSchemes
{
    default         Gauss linear orthogonal;
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         orthogonal;
}
// ************************************************************************* //
""")

write_file("system/cylinder/changeDictionaryDict", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system/cylinder";
    object      changeDictionaryDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dictionaryReplacement
{






    T
    {
        boundaryField
        {
            ".*_to_.*"
            {
                type            coupledTemperature;
                Tnbr            T;
                kappaMethod     solidThermo;
                value           uniform 300;
            }
        }
    }



}
// ************************************************************************* //
""")

write_file("system/cylinder/fvSolution", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system/cylinder";
    object      fvSolution;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

solvers
{
    e
    {
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-7;
        relTol          0.01;
    }
}

SIMPLE
{
    nNonOrthogonalCorrectors 0;
}

PIMPLE
{
    nOuterCorrectors 2;
    nCorrectors      2;
    nNonOrthogonalCorrectors 0;
    pRefCell         0;
    pRefValue        0;
}
""")

write_file("0.orig/glass/T", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0/glass";
    object      T;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 0 0 1 0 0 0];
internalField   uniform 300;

boundaryField
{
    ".*"
    {
        type            zeroGradient;
    }
}
// ************************************************************************* //
""")

write_file("0.orig/heater/T", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0/heater";
    object      T;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 0 0 1 0 0 0];
internalField   uniform 300;

boundaryField
{
    ".*"
    {
        type            zeroGradient;
    }
}
// ************************************************************************* //
""")

write_file("0.orig/air/T", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0/air";
    object      T;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 0 0 1 0 0 0];
internalField   uniform 300;

boundaryField
{

    inlet
    {
        type            fixedValue;
        value           uniform 300;
    }
    outlet
    {
        type            zeroGradient;
    }
    topAndBottom
    {
        type            zeroGradient;
    }
    frontAndBack
    {
        type            zeroGradient;
    }

}
// ************************************************************************* //
""")

write_file("0.orig/air/G", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0/air";
    object      G;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [1 0 -3 0 0 0 0];
internalField   uniform 0;

boundaryField
{
    ".*"
    {
        type            calculated;
        value           uniform 0;
    }
}
""")

write_file("0.orig/air/alphat", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0/air";
    object      alphat;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [1 -1 -1 0 0 0 0];
internalField   uniform 0;

boundaryField
{

    inlet
    {
        type            calculated;
        value           uniform 0;
    }
    outlet
    {
        type            calculated;
        value           uniform 0;
    }
    topAndBottom
    {
        type            slip;
    }
    frontAndBack
    {
        type            slip;
    }

}
// ************************************************************************* //
""")

write_file("0.orig/air/U", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volVectorField;
    location    "0/air";
    object      U;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 1 -1 0 0 0 0];
internalField   uniform (1 0 0);

boundaryField
{

    inlet
    {
        type            fixedValue;
        value           uniform (1 0 0);
    }
    outlet
    {
        type            zeroGradient;
    }
    topAndBottom
    {
        type            slip;
    }
    frontAndBack
    {
        type            slip;
    }

}
// ************************************************************************* //
""")

write_file("0.orig/air/k", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0/air";
    object      k;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 2 -2 0 0 0 0];
internalField   uniform 0.1;

boundaryField
{

    inlet
    {
        type            fixedValue;
        value           uniform 0.1;
    }
    outlet
    {
        type            zeroGradient;
    }
    topAndBottom
    {
        type            slip;
    }
    frontAndBack
    {
        type            slip;
    }

}
// ************************************************************************* //
""")

write_file("0.orig/air/p", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0/air";
    object      p;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [1 -1 -2 0 0 0 0];
internalField   uniform 100000;

boundaryField
{
    ".*"
    {
        type            calculated;
        value           uniform 100000;
    }
}
// ************************************************************************* //
""")

write_file("0.orig/air/p_rgh", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0/air";
    object      p_rgh;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [1 -1 -2 0 0 0 0];
internalField   uniform 100000;

boundaryField
{

    inlet
    {
        type            fixedFluxPressure;
        value           uniform 100000;
    }
    outlet
    {
        type            fixedValue;
        value           uniform 100000;
    }
    topAndBottom
    {
        type            zeroGradient;
    }
    frontAndBack
    {
        type            zeroGradient;
    }

}
// ************************************************************************* //
""")

write_file("0.orig/air/IDefault", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0/air";
    object      IDefault;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [1 0 -3 0 0 0 0];
internalField   uniform 0;

boundaryField
{
    inlet
    {
        type            greyDiffusiveRadiation;
        value           uniform 0;
        emissivityMode  lookup;
        emissivity      1;
    }
    outlet
    {
        type            greyDiffusiveRadiation;
        value           uniform 0;
        emissivityMode  lookup;
        emissivity      1;
    }
    topAndBottom
    {
        type            greyDiffusiveRadiation;
        value           uniform 0;
        emissivityMode  lookup;
        emissivity      1;
    }
    frontAndBack
    {
        type            greyDiffusiveRadiation;
        value           uniform 0;
        emissivityMode  lookup;
        emissivity      1;
    }
    ".*"
    {
        type            greyDiffusiveRadiation;
        value           uniform 0;
        emissivityMode  solidRadiation;
    }
}
""")

write_file("0.orig/air/nut", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0/air";
    object      nut;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 2 -1 0 0 0 0];
internalField   uniform 0;

boundaryField
{

    inlet
    {
        type            calculated;
        value           uniform 0;
    }
    outlet
    {
        type            calculated;
        value           uniform 0;
    }
    topAndBottom
    {
        type            slip;
    }
    frontAndBack
    {
        type            slip;
    }

}
// ************************************************************************* //
""")

write_file("0.orig/air/epsilon", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0/air";
    object      epsilon;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 2 -3 0 0 0 0];
internalField   uniform 0.01;

boundaryField
{

    inlet
    {
        type            fixedValue;
        value           uniform 0.01;
    }
    outlet
    {
        type            zeroGradient;
    }
    topAndBottom
    {
        type            slip;
    }
    frontAndBack
    {
        type            slip;
    }

}
// ************************************************************************* //
""")

write_file("0.orig/cylinder/T", """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  13                                    |
|   \\\\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0/cylinder";
    object      T;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 0 0 1 0 0 0];
internalField   uniform 300;

boundaryField
{
    ".*"
    {
        type            zeroGradient;
    }
}
// ************************************************************************* //
""")

print("OpenFOAM case files generated successfully.")
