import os
import stat

def create_blockMeshDict():
    X = [-11.2, -0.282, -0.280, 0.280, 0.282, 11.2]
    Y = [-3.0, -0.075, -0.0741, -0.0025, 0.0025, 0.0741, 0.075, 3.0]
    Z = [0.0, 0.1]

    nx = [50, 3, 100, 3, 50]
    ny = [30, 3, 20, 5, 20, 3, 30]

    gx = [0.05, 1, 1, 1, 20]
    gy = [0.05, 1, 1, 1, 1, 1, 20]

    def V(i, j, k):
        return i + j*len(X) + k*len(X)*len(Y)

    def get_zone(i, j):
        if j == 3 and i in [1, 2, 3]:
            return "heater"
        if i in [1, 3] and j in [1, 2, 4, 5]:
            return "glass"
        if i == 2 and j in [1, 5]:
            return "cylinder"
        if i == 2 and j in [2, 4]:
            return "innerAir"
        return "outerAir"

    pts_str = ""
    for k, z in enumerate(Z):
        for j, y in enumerate(Y):
            for i, x in enumerate(X):
                pts_str += f"    ({x:.6f} {y:.6f} {z:.6f})\n"

    blocks_str = ""
    for i in range(len(X)-1):
        for j in range(len(Y)-1):
            zone = get_zone(i, j)
            v000 = V(i, j, 0)
            v100 = V(i+1, j, 0)
            v110 = V(i+1, j+1, 0)
            v010 = V(i, j+1, 0)
            v001 = V(i, j, 1)
            v101 = V(i+1, j, 1)
            v111 = V(i+1, j+1, 1)
            v011 = V(i, j+1, 1)

            blocks_str += f"    hex ({v000} {v100} {v110} {v010} {v001} {v101} {v111} {v011}) {zone} ({nx[i]} {ny[j]} 1) simpleGrading ({gx[i]} {gy[j]} 1)\n"

    inlet_faces = []
    outlet_faces = []
    top_bottom_faces = []

    for j in range(len(Y)-1):
        inlet_faces.append(f"({V(0, j, 0)} {V(0, j, 1)} {V(0, j+1, 1)} {V(0, j+1, 0)})")
        outlet_faces.append(f"({V(5, j, 0)} {V(5, j+1, 0)} {V(5, j+1, 1)} {V(5, j, 1)})")

    for i in range(len(X)-1):
        top_bottom_faces.append(f"({V(i, 0, 0)} {V(i+1, 0, 0)} {V(i+1, 0, 1)} {V(i, 0, 1)})")
        top_bottom_faces.append(f"({V(i, 7, 0)} {V(i, 7, 1)} {V(i+1, 7, 1)} {V(i+1, 7, 0)})")

    os.makedirs("system", exist_ok=True)
    with open("system/blockMeshDict", "w") as f:
        f.write(f"""/*--------------------------------*- C++ -*----------------------------------*\\
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
    class       dictionary;
    object      blockMeshDict;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

scale   1;

vertices
(
{pts_str}
);

blocks
(
{blocks_str}
);

edges
(
);

boundary
(
    inlet
    {{
        type patch;
        faces
        (
            {" ".join(inlet_faces)}
        );
    }}
    outlet
    {{
        type patch;
        faces
        (
            {" ".join(outlet_faces)}
        );
    }}
    topAndBottom
    {{
        type patch;
        faces
        (
            {" ".join(top_bottom_faces)}
        );
    }}
);

defaultPatch
{{
    name frontAndBack;
    type empty;
}}

// ************************************************************************* //
""")

def create_openfoam_dicts():
    os.makedirs("system", exist_ok=True)
    os.makedirs("constant", exist_ok=True)

    with open("system/controlDict", "w") as f:
        f.write("""/*--------------------------------*- C++ -*----------------------------------*\\
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
application     foamMultiRun;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         10;
deltaT          0.01;
writeControl    timeStep;
writeInterval   100;
purgeWrite      0;
writeFormat     ascii;
writePrecision  6;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;
""")

    with open("system/fvSchemes", "w") as f:
        f.write("""/*--------------------------------*- C++ -*----------------------------------*\\
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
    div(phi,e)      Gauss linearUpwind grad(e);
    div(phi,K)      Gauss linearUpwind grad(K);
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

    with open("system/fvSolution", "w") as f:
        f.write("""/*--------------------------------*- C++ -*----------------------------------*\\
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
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-7;
        relTol          0.01;
    }

    "U.*"
    {
        solver          PBiCGStab;
        preconditioner  DILU;
        tolerance       1e-7;
        relTol          0.1;
    }

    "e.*"
    {
        solver          PBiCGStab;
        preconditioner  DILU;
        tolerance       1e-7;
        relTol          0.1;
    }
}

PIMPLE
{
    nOuterCorrectors 1;
    nCorrectors      2;
    nNonOrthogonalCorrectors 0;
}
""")

def create_run_script():
    with open("run.sh", "w") as f:
        f.write("""#!/bin/bash
set -e
rm -rf 0 constant/polyMesh constant/*/polyMesh
blockMesh
splitMeshRegions -cellZones -overwrite
cp -r 0.orig 0
""")
    os.chmod("run.sh", 0o755)

if __name__ == "__main__":
    create_blockMeshDict()
    create_openfoam_dicts()
    create_run_script()
