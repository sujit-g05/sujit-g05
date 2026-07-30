import os
import trimesh
import trimesh.creation
import numpy as np

def create_geometry():
    os.makedirs('constant/triSurface', exist_ok=True)
    os.makedirs('system', exist_ok=True)

    heater = trimesh.creation.cylinder(radius=0.0037388, height=0.6)
    heater.export('constant/triSurface/heater.stl')
    print("Created heater.stl")

    cylinder = trimesh.creation.annulus(r_min=0.0741, r_max=0.075, height=0.56)
    cylinder.export('constant/triSurface/cylinder.stl')
    print("Created cylinder.stl")

    thickness_cap = 0.002
    glass_top = trimesh.creation.annulus(r_min=0.0037388, r_max=0.075, height=thickness_cap)
    matrix_top = np.eye(4)
    matrix_top[2, 3] = 0.28 + thickness_cap/2 - 0.0001
    glass_top.apply_transform(matrix_top)
    glass_top.export('constant/triSurface/glass_top.stl')
    print("Created glass_top.stl")

    glass_bottom = trimesh.creation.annulus(r_min=0.0037388, r_max=0.075, height=thickness_cap)
    matrix_bottom = np.eye(4)
    matrix_bottom[2, 3] = -0.28 - thickness_cap/2 + 0.0001
    glass_bottom.apply_transform(matrix_bottom)
    glass_bottom.export('constant/triSurface/glass_bottom.stl')
    print("Created glass_bottom.stl")

def write_meshing_dicts():
    block_mesh = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\    /   O peration     | Version:  13                                    |
|   \\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
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
    hex (0 1 2 3 4 5 6 7) (100 30 30) simpleGrading (1 1 1)
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
    sides
    {
        type patch;
        faces
        (
            (0 1 5 4)
            (3 7 6 2)
            (0 3 2 1)
            (4 5 6 7)
        );
    }
);

mergePatchPairs
(
);

// ************************************************************************* //
"""
    with open('system/blockMeshDict', 'w') as f:
        f.write(block_mesh)

    surface_features = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\    /   O peration     | Version:  13                                    |
|   \\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      surfaceFeaturesDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

heater.stl
{
    extractionMethod    extractFromSurface;
    extractFromSurfaceCoeffs
    {
        includedAngle   150;
    }
    writeObj            yes;
}

cylinder.stl
{
    extractionMethod    extractFromSurface;
    extractFromSurfaceCoeffs
    {
        includedAngle   150;
    }
    writeObj            yes;
}

glass_top.stl
{
    extractionMethod    extractFromSurface;
    extractFromSurfaceCoeffs
    {
        includedAngle   150;
    }
    writeObj            yes;
}

glass_bottom.stl
{
    extractionMethod    extractFromSurface;
    extractFromSurfaceCoeffs
    {
        includedAngle   150;
    }
    writeObj            yes;
}

// ************************************************************************* //
"""
    with open('system/surfaceFeaturesDict', 'w') as f:
        f.write(surface_features)

    snappy_hex_mesh = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\    /   O peration     | Version:  13                                    |
|   \\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
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
    heater
    {
        type triSurfaceMesh;
        file "heater.stl";
        regions
        {
            patch1 { name heater_boundary; }
        }
    }
    cylinder
    {
        type triSurfaceMesh;
        file "cylinder.stl";
        regions
        {
            patch1 { name cylinder_boundary; }
        }
    }
    glass_top
    {
        type triSurfaceMesh;
        file "glass_top.stl";
        regions
        {
            patch1 { name glass_top_boundary; }
        }
    }
    glass_bottom
    {
        type triSurfaceMesh;
        file "glass_bottom.stl";
        regions
        {
            patch1 { name glass_bottom_boundary; }
        }
    }
}

castellatedMeshControls
{
    maxLocalCells 100000;
    maxGlobalCells 2000000;
    minRefinementCells 10;
    maxLoadUnbalance 0.10;
    nCellsBetweenLevels 1;

    features
    (
        {
            file "heater.eMesh";
            level 6;
        }
        {
            file "cylinder.eMesh";
            level 6;
        }
        {
            file "glass_top.eMesh";
            level 6;
        }
        {
            file "glass_bottom.eMesh";
            level 6;
        }
    );

    refinementSurfaces
    {
        heater
        {
            level (5 6);
            faceZone heater;
            cellZone heater;
            cellZoneInside inside;
        }
        cylinder
        {
            level (5 6);
            faceZone cylinder;
            cellZone cylinder;
            cellZoneInside inside;
        }
        glass_top
        {
            level (5 6);
            faceZone glass_top;
            cellZone glass_top;
            cellZoneInside inside;
        }
        glass_bottom
        {
            level (5 6);
            faceZone glass_bottom;
            cellZone glass_bottom;
            cellZoneInside inside;
        }
    }

    resolveFeatureAngle 30;

    refinementRegions
    {
    }

    locationsInMesh
    (
        ((-10.0 0.0 0.0) air_outer)
        ((0.035 0.0 0.0) air_inner)
    );

    allowFreeStandingZoneFaces true;
}

snapControls
{
    nSmoothPatch 3;
    tolerance 2.0;
    nSolveIter 30;
    nRelaxIter 5;
    nFeatureSnapIter 10;
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
    slipFeatureAngle 30;
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
}

mergeTolerance 1e-6;

// ************************************************************************* //
"""
    with open('system/snappyHexMeshDict', 'w') as f:
        f.write(snappy_hex_mesh)

    mesh_quality = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\    /   O peration     | Version:  13                                    |
|   \\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
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

// ************************************************************************* //
"""
    with open('system/meshQualityDict', 'w') as f:
        f.write(mesh_quality)


def write_solver_dicts():
    control_dict = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\    /   O peration     | Version:  13                                    |
|   \\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      controlDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

application     chtMultiRegionFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         100;
deltaT          0.001;
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
{
    air_outer       fluid;
    air_inner       fluid;
    heater          solid;
    cylinder        solid;
    glass_top       solid;
    glass_bottom    solid;
}

// ************************************************************************* //
"""
    with open('system/controlDict', 'w') as f:
        f.write(control_dict)

    fv_schemes = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\    /   O peration     | Version:  13                                    |
|   \\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
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
    div(phi,U)      Gauss linearUpwind grad(U);
    div(phi,h)      Gauss linearUpwind grad(h);
    div(phi,k)      Gauss upwind;
    div(phi,K)      Gauss linearUpwind grad(U);
    div(phi,epsilon) Gauss upwind;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}

laplacianSchemes
{
    default         Gauss linear corrected;
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         corrected;
}

// ************************************************************************* //
"""
    with open('system/fvSchemes', 'w') as f:
        f.write(fv_schemes)

    fv_solution = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\    /   O peration     | Version:  13                                    |
|   \\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      fvSolution;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

solvers
{
    "rho.*"
    {
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-7;
        relTol          0;
    }

    "p_rgh.*"
    {
        solver          GAMG;
        tolerance       1e-7;
        relTol          0.01;
        smoother        GaussSeidel;
    }

    "U.*"
    {
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-8;
        relTol          0.1;
    }

    "h.*"
    {
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-8;
        relTol          0.1;
    }

    "(k|epsilon).*"
    {
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-8;
        relTol          0.1;
    }
}

PIMPLE
{
    nOuterCorrectors 1;
    nCorrectors      2;
    nNonOrthogonalCorrectors 0;
}

// ************************************************************************* //
"""
    with open('system/fvSolution', 'w') as f:
        f.write(fv_solution)


def write_0_orig_dicts():
    os.makedirs('0.orig', exist_ok=True)

    header = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\    /   O peration     | Version:  13                                    |
|   \\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    object      <OBJECT>;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
"""
    header_vec = header.replace("volScalarField", "volVectorField")

    t_content = header.replace("<OBJECT>", "T") + """
dimensions      [0 0 0 1 0 0 0];
internalField   uniform 293.15;
boundaryField
{
    ".*"
    {
        type            zeroGradient;
    }
}
"""
    with open('0.orig/T', 'w') as f: f.write(t_content)

    u_content = header_vec.replace("<OBJECT>", "U") + """
dimensions      [0 1 -1 0 0 0 0];
internalField   uniform (0 0 0);
boundaryField
{
    ".*"
    {
        type            uniformFixedValue;
        uniformValue    constant (0 0 0);
    }
}
"""
    with open('0.orig/U', 'w') as f: f.write(u_content)

    prgh_content = header.replace("<OBJECT>", "p_rgh") + """
dimensions      [1 -1 -2 0 0 0 0];
internalField   uniform 101325;
boundaryField
{
    ".*"
    {
        type            calculated;
        value           uniform 101325;
    }
}
"""
    with open('0.orig/p_rgh', 'w') as f: f.write(prgh_content)

    p_content = header.replace("<OBJECT>", "p") + """
dimensions      [1 -1 -2 0 0 0 0];
internalField   uniform 101325;
boundaryField
{
    ".*"
    {
        type            calculated;
        value           uniform 101325;
    }
}
"""
    with open('0.orig/p', 'w') as f: f.write(p_content)

    k_content = header.replace("<OBJECT>", "k") + """
dimensions      [0 2 -2 0 0 0 0];
internalField   uniform 0.1;
boundaryField
{
    ".*"
    {
        type            zeroGradient;
    }
}
"""
    with open('0.orig/k', 'w') as f: f.write(k_content)

    eps_content = header.replace("<OBJECT>", "epsilon") + """
dimensions      [0 2 -3 0 0 0 0];
internalField   uniform 0.1;
boundaryField
{
    ".*"
    {
        type            zeroGradient;
    }
}
"""
    with open('0.orig/epsilon', 'w') as f: f.write(eps_content)

    nut_content = header.replace("<OBJECT>", "nut") + """
dimensions      [0 2 -1 0 0 0 0];
internalField   uniform 0;
boundaryField
{
    ".*"
    {
        type            calculated;
        value           uniform 0;
    }
}
"""
    with open('0.orig/nut', 'w') as f: f.write(nut_content)

    alphat_content = header.replace("<OBJECT>", "alphat") + """
dimensions      [1 -1 -1 0 0 0 0];
internalField   uniform 0;
boundaryField
{
    ".*"
    {
        type            calculated;
        value           uniform 0;
    }
}
"""
    with open('0.orig/alphat', 'w') as f: f.write(alphat_content)
    # G
    g_content = header.replace("<OBJECT>", "G") + """
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
"""
    with open('0.orig/G', 'w') as f: f.write(g_content)

    # qr
    qr_content = header_vec.replace("<OBJECT>", "qr") + """
dimensions      [1 0 -3 0 0 0 0];
internalField   uniform (0 0 0);
boundaryField
{
    ".*"
    {
        type            calculated;
        value           uniform (0 0 0);
    }
}
"""
    with open('0.orig/qr', 'w') as f: f.write(qr_content)



def write_constant_dicts():
    os.makedirs('constant/air_outer', exist_ok=True)
    os.makedirs('constant/air_inner', exist_ok=True)
    os.makedirs('constant/heater', exist_ok=True)
    os.makedirs('constant/cylinder', exist_ok=True)
    os.makedirs('constant/glass_top', exist_ok=True)
    os.makedirs('constant/glass_bottom', exist_ok=True)

    header = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\    /   O peration     | Version:  13                                    |
|   \\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      <OBJECT>;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
"""

    g = header.replace("<OBJECT>", "g") + """
dimensions      [0 1 -2 0 0 0 0];
value           (0 0 -9.81);
"""
    with open('constant/g', 'w') as f: f.write(g)

    air_thermo = header.replace("<OBJECT>", "thermophysicalProperties") + """
thermoType
{
    type            heRhoThermo;
    mixture         pureMixture;
    transport       const;
    thermo          hConst;
    equationOfState perfectGas;
    specie          specie;
    energy          sensibleEnthalpy;
}

mixture
{
    specie
    {
        nMoles      1;
        molWeight   28.96;
    }
    thermodynamics
    {
        Cp          1004.4;
        Hf          0;
    }
    transport
    {
        mu          1.831e-05;
        Pr          0.705;
    }
}
"""
    air_turb = header.replace("<OBJECT>", "turbulenceProperties") + """
simulationType  RAS;

RAS
{
    RASModel        kEpsilon;
    turbulence      on;
    printCoeffs     on;
}
"""
    air_rad = header.replace("<OBJECT>", "radiationProperties") + """
radiation       on;
radiationModel  fvDOM;

fvDOMCoeffs
{
    nPhi        2;
    nTheta      2;
    tolerance   1e-3;
    maxIter     10;
}

absorptionEmissionModel constantAbsorptionEmission;

constantAbsorptionEmissionCoeffs
{
    a           ( 0 );
    e           ( 0 );
    E           ( 0 );
}

scatterModel    none;
sootModel       none;
"""

    for region in ['air_outer', 'air_inner']:
        with open(f'constant/{region}/thermophysicalProperties', 'w') as f: f.write(air_thermo)
        with open(f'constant/{region}/turbulenceProperties', 'w') as f: f.write(air_turb)
        with open(f'constant/{region}/radiationProperties', 'w') as f: f.write(air_rad)


    solid_thermo_template = header.replace("<OBJECT>", "thermophysicalProperties") + """
thermoType
{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       constIso;
    thermo          hConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleEnthalpy;
}

mixture
{
    specie
    {
        nMoles      1;
        molWeight   1;
    }
    transport
    {
        kappa       <KAPPA>;
    }
    thermodynamics
    {
        Hf          0;
        Cp          <CP>;
    }
    equationOfState
    {
        rho         <RHO>;
    }
}
"""
    solid_rad = header.replace("<OBJECT>", "radiationProperties") + """
radiation off;
"""
    for region in ['heater', 'cylinder', 'glass_top', 'glass_bottom']:
        with open(f'constant/{region}/radiationProperties', 'w') as f: f.write(solid_rad)

    heater_thermo = solid_thermo_template.replace("<KAPPA>", "11").replace("<CP>", "460").replace("<RHO>", "7250")
    with open('constant/heater/thermophysicalProperties', 'w') as f: f.write(heater_thermo)

    cyl_thermo = solid_thermo_template.replace("<KAPPA>", "0.84126").replace("<CP>", "857.41").replace("<RHO>", "1570")
    with open('constant/cylinder/thermophysicalProperties', 'w') as f: f.write(cyl_thermo)

    glass_thermo = solid_thermo_template.replace("<KAPPA>", "1.2").replace("<CP>", "750").replace("<RHO>", "2230")
    with open('constant/glass_top/thermophysicalProperties', 'w') as f: f.write(glass_thermo)
    with open('constant/glass_bottom/thermophysicalProperties', 'w') as f: f.write(glass_thermo)


def write_system_dicts():
    os.makedirs('system/air_outer', exist_ok=True)
    os.makedirs('system/air_inner', exist_ok=True)
    os.makedirs('system/heater', exist_ok=True)
    os.makedirs('system/cylinder', exist_ok=True)
    os.makedirs('system/glass_top', exist_ok=True)
    os.makedirs('system/glass_bottom', exist_ok=True)

    header = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\    /   O peration     | Version:  13                                    |
|   \\  /    A nd           | Web:      www.OpenFOAM.org                      |
|    \\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      <OBJECT>;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
"""

    cd_fluid = header.replace("<OBJECT>", "changeDictionaryDict") + """
U
{
    boundaryField
    {
        inlet
        {
            type            fixedValue;
            value           uniform (1 0 0);
        }
        outlet
        {
            type            inletOutlet;
            inletValue      uniform (0 0 0);
            value           uniform (0 0 0);
        }
        sides
        {
            type            slip;
        }
        ".*_to_.*"
        {
            type            fixedValue;
            value           uniform (0 0 0);
        }
    }
}
T
{
    boundaryField
    {
        inlet
        {
            type            fixedValue;
            value           uniform 293.15;
        }
        outlet
        {
            type            inletOutlet;
            inletValue      uniform 293.15;
            value           uniform 293.15;
        }
        sides
        {
            type            zeroGradient;
        }
        ".*_to_.*"
        {
            type            compressible::turbulentTemperatureCoupledBaffleMixed;
            Tnbr            T;
            kappaMethod     fluidThermo;
            value           uniform 293.15;
        }
    }
}
p_rgh
{
    boundaryField
    {
        inlet
        {
            type            fixedFluxPressure;
            value           uniform 101325;
        }
        outlet
        {
            type            fixedValue;
            value           uniform 101325;
        }
        sides
        {
            type            zeroGradient;
        }
        ".*_to_.*"
        {
            type            fixedFluxPressure;
            value           uniform 101325;
        }
    }
}
qr
{
    boundaryField
    {
        ".*_to_.*"
        {
            type            greyDiffusiveRadiation;
            emissivityMode  lookup;
            emissivity      uniform 1.0; // Air boundary
            value           uniform (0 0 0);
        }
    }
}
"""
    with open('system/air_outer/changeDictionaryDict', 'w') as f: f.write(cd_fluid)

    cd_inner = header.replace("<OBJECT>", "changeDictionaryDict") + """
U
{
    boundaryField
    {
        ".*_to_.*"
        {
            type            fixedValue;
            value           uniform (0 0 0);
        }
    }
}
T
{
    boundaryField
    {
        ".*_to_.*"
        {
            type            compressible::turbulentTemperatureCoupledBaffleMixed;
            Tnbr            T;
            kappaMethod     fluidThermo;
            value           uniform 293.15;
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
            value           uniform 101325;
        }
    }
}
qr
{
    boundaryField
    {
        ".*_to_.*"
        {
            type            greyDiffusiveRadiation;
            emissivityMode  lookup;
            emissivity      uniform 1.0; // Air boundary
            value           uniform (0 0 0);
        }
    }
}
"""
    with open('system/air_inner/changeDictionaryDict', 'w') as f: f.write(cd_inner)

    cd_solid = header.replace("<OBJECT>", "changeDictionaryDict") + """
T
{
    boundaryField
    {
        ".*_to_.*"
        {
            type            compressible::turbulentTemperatureCoupledBaffleMixed;
            Tnbr            T;
            kappaMethod     solidThermo;
            value           uniform 293.15;
        }
    }
}
qr
{
    boundaryField
    {
        ".*_to_.*"
        {
            type            greyDiffusiveRadiation;
            emissivityMode  lookup;
            emissivity      uniform 0.7; // Applying user specified emissivity
            value           uniform (0 0 0);
        }
    }
}
"""
    for region in ['heater', 'cylinder', 'glass_top', 'glass_bottom']:
        with open(f'system/{region}/changeDictionaryDict', 'w') as f: f.write(cd_solid)

    decompose_par = header.replace("<OBJECT>", "decomposeParDict") + """
numberOfSubdomains 8;

method          scotch;
"""
    with open('system/decomposeParDict', 'w') as f: f.write(decompose_par)

    fv_models = header.replace("<OBJECT>", "fvModels") + """
heatSource
{
    type            scalarSemiImplicitSource;
    volumeMode      absolute;
    selectionMode   all;

    sources
    {
        h           (225 0); // Absolute power in W
    }
}
"""
    with open('system/heater/fvModels', 'w') as f: f.write(fv_models)

    with open('system/fvSchemes', 'r') as f: fv_schemes = f.read()
    with open('system/fvSolution', 'r') as f: fv_solution = f.read()

    for region in ['air_outer', 'air_inner', 'heater', 'cylinder', 'glass_top', 'glass_bottom']:
        with open(f'system/{region}/fvSchemes', 'w') as f: f.write(fv_schemes)
        with open(f'system/{region}/fvSolution', 'w') as f: f.write(fv_solution)

    with open('system/air_inner/fvSolution', 'r') as f:
        inner_sol = f.read()
    inner_sol = inner_sol.replace('"p_rgh.*"\n    {', '"p_rgh.*"\n    {\n        pRefCell        0;\n        pRefValue       101325;')
    with open('system/air_inner/fvSolution', 'w') as f:
        f.write(inner_sol)


if __name__ == '__main__':
    create_geometry()
    write_meshing_dicts()
    write_solver_dicts()
    write_0_orig_dicts()
    write_constant_dicts()
    write_system_dicts()
