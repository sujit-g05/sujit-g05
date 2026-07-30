import os
import trimesh
import trimesh.creation
import numpy as np

def create_geometry():
    # Create directories
    os.makedirs('constant/triSurface', exist_ok=True)
    os.makedirs('system', exist_ok=True)

    # 1. Heater (FeCrAl alloy)
    # mass = 191g = 0.191 kg, density = 7.25 g/cm^3 = 7250 kg/m^3
    # volume = mass / density = 0.191 / 7250 = 2.63448e-5 m^3
    # V = pi * r^2 * h => r = sqrt(V / (pi * h))
    # h = 600 mm = 0.6 m
    # r = sqrt(2.63448e-5 / (pi * 0.6)) = 0.0037388 m = 3.7388 mm
    heater = trimesh.creation.cylinder(radius=0.0037388, height=0.6)
    heater.export('constant/triSurface/heater.stl')
    print("Created heater.stl")

    # 2. Hollow cylinder (borosilicate glass disk later)
    # length = 560 mm = 0.56 m, D = 150 mm => R = 75 mm = 0.075 m, thickness = 0.9 mm = 0.0009 m
    # Inner radius = 0.075 - 0.0009 = 0.0741 m
    cylinder = trimesh.creation.annulus(r_min=0.0741, r_max=0.075, height=0.56)
    cylinder.export('constant/triSurface/cylinder.stl')
    print("Created cylinder.stl")

    # 3. Glass Top
    # Caps the cylinder. R_max = 0.075 m, R_min = 0.0037388 m (hole for heater)
    # Assuming standard thickness for glass, let's use 0.9 mm as well for the caps for simplicity, or 2mm?
    # No thickness specified for caps, let's assume 2mm
    thickness_cap = 0.002
    glass_top = trimesh.creation.annulus(r_min=0.0037388, r_max=0.075, height=thickness_cap)
    # Translate to top of cylinder
    # Cylinder is centered at z=0, height 0.56 => top is at z=0.28
    # Glass top is centered at z=0, so move it to z=0.28 + thickness_cap/2
    matrix_top = np.eye(4)
    matrix_top[2, 3] = 0.28 + thickness_cap/2
    glass_top.apply_transform(matrix_top)
    glass_top.export('constant/triSurface/glass_top.stl')
    print("Created glass_top.stl")

    # 4. Glass Bottom
    glass_bottom = trimesh.creation.annulus(r_min=0.0037388, r_max=0.075, height=thickness_cap)
    matrix_bottom = np.eye(4)
    matrix_bottom[2, 3] = -0.28 - thickness_cap/2
    glass_bottom.apply_transform(matrix_bottom)
    glass_bottom.export('constant/triSurface/glass_bottom.stl')
    print("Created glass_bottom.stl")


def write_meshing_dicts():
    # blockMeshDict
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

    # surfaceFeaturesDict
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

    # snappyHexMeshDict
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
            level 2;
        }
        {
            file "cylinder.eMesh";
            level 2;
        }
        {
            file "glass_top.eMesh";
            level 2;
        }
        {
            file "glass_bottom.eMesh";
            level 2;
        }
    );

    refinementSurfaces
    {
        heater
        {
            level (2 2);
            faceZone heater;
            cellZone heater;
            cellZoneInside inside;
        }
        cylinder
        {
            level (2 2);
            faceZone cylinder;
            cellZone cylinder;
            cellZoneInside inside;
        }
        glass_top
        {
            level (2 2);
            faceZone glass_top;
            cellZone glass_top;
            cellZoneInside inside;
        }
        glass_bottom
        {
            level (2 2);
            faceZone glass_bottom;
            cellZone glass_bottom;
            cellZoneInside inside;
        }
    }

    resolveFeatureAngle 30;

    refinementRegions
    {
    }

    insidePoint (-10.0 0.0 0.0);

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

    # meshQualityDict
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
    # controlDict
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
endTime         10;
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

// ************************************************************************* //
"""
    with open('system/controlDict', 'w') as f:
        f.write(control_dict)

    # fvSchemes
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

    # fvSolution
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


if __name__ == '__main__':
    create_geometry()
    write_meshing_dicts()
    write_solver_dicts()
