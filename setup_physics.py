import os
import shutil

regions = ['heater', 'cylinder', 'innerAir', 'outerAir']
fluids = ['innerAir', 'outerAir']
solids = ['heater', 'cylinder']

def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)

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

# -----------------
# System directory
# -----------------

controlDict = get_header("dictionary", "controlDict") + """
application     foamMultiRun;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         10; // short for testing
deltaT          0.01;
writeControl    adjustableRunTime;
writeInterval   1;
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
        type fluid;
        regions (innerAir outerAir);
    }
    solid
    {
        type solid;
        regions (heater cylinder);
    }
);

functions
{
}
"""
write_file("system/controlDict", controlDict)

fvSchemes = get_header("dictionary", "fvSchemes") + """
ddtSchemes { default Euler; }
gradSchemes { default Gauss linear; }
divSchemes {
    default none;
    div(phi,U) Gauss upwind;
    div(phi,K) Gauss upwind;
    div(phi,h) Gauss upwind;
    div(phi,e) Gauss upwind;
    div(phi,k) Gauss upwind;
    div(phi,epsilon) Gauss upwind;
    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;
    div(I) Gauss upwind;
    div(ji,I) Gauss upwind;
}
laplacianSchemes { default Gauss linear orthogonal; }
interpolationSchemes { default linear; }
snGradSchemes { default orthogonal; }
wallDist { method meshWave; }
"""
write_file("system/fvSchemes", fvSchemes)

fvSolution = get_header("dictionary", "fvSolution") + """
solvers
{
    "rho.*"
    {
        solver          diagonal;
    }
    "p_rgh.*"
    {
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-7;
        relTol          0.01;
    }
    "(U|h|e|k|epsilon).*"
    {
        solver          PBiCGStab;
        preconditioner  DILU;
        tolerance       1e-7;
        relTol          0.1;
    }
    "(G|I.*)"
    {
        solver          PBiCGStab;
        preconditioner  DILU;
        tolerance       1e-7;
        relTol          0.1;
    }
}
PIMPLE
{
    nOuterCorrectors 2;
    nCorrectors      2;
    nNonOrthogonalCorrectors 0;
}
"""
write_file("system/fvSolution", fvSolution)

for region in regions:
    write_file(f"system/{region}/fvSchemes", fvSchemes)
    write_file(f"system/{region}/fvSolution", fvSolution)

# View factors dict for innerAir
vfd = get_header("dictionary", "viewFactorsDict") + """
writeViewFactorMatrix true;
writeFacesByRays    true;
nFacesInCoarsestLevel 10;
featureAngle        180;
"""
for region in fluids:
    write_file(f"system/{region}/viewFactorsDict", vfd)


# -----------------
# Constant directory
# -----------------

write_file("constant/g", get_header("uniformDimensionedVectorField", "g") + "dimensions [0 1 -2 0 0 0 0];\nvalue (0 0 0);\n")

for region in regions:
    if region in fluids:
        thermo = """
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
        Cp          1004;
        Hf          0;
    }
    transport
    {
        mu          1.8e-05;
        Pr          0.7;
    }
}
"""
        turb = """
simulationType  RAS;
RAS
{
    RASModel        kEpsilon;
    turbulence      on;
    printCoeffs     on;
}
"""
        rad = 'radiation on;\nradiationModel fvDOM;\n\nfvDOMCoeffs\n{\n    nPhi        2;\n    nTheta      2;\n    tolerance   1e-3;\n    maxIter     10;\n}\n\nabsorptionEmissionModel constantAbsorptionEmission;\nconstantAbsorptionEmissionCoeffs\n{\n    a       0;\n    e       0;\n    E       0;\n}\nscatterModel none;\n'
    else:
        # solids
        if region == 'heater':
            rho, cp, k = 7250, 460, 11
        else: # cylinder
            rho, cp, k = 1570, 857.41, 0.84126
        thermo = f"""
thermoType
{{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       const;
    thermo          hConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleEnthalpy;
}}
mixture
{{
    specie
    {{
        nMoles      1;
        molWeight   12; // dummy
    }}
    transport
    {{
        kappa       {k};
    }}
    thermodynamics
    {{
        Hf          0;
        Cp          {cp};
        rho         {rho};
    }}
}}
"""
        turb = ""
        rad = "radiation off;\n"

    write_file(f"constant/{region}/thermophysicalProperties", get_header("dictionary", "thermophysicalProperties") + thermo)
    write_file(f"constant/{region}/radiationProperties", get_header("dictionary", "radiationProperties") + rad)
    if turb:
        write_file(f"constant/{region}/turbulenceProperties", get_header("dictionary", "turbulenceProperties") + turb)

# Heater power source: 225W in total over 0.564m length 3D cylinder.
# Volume of 3D heater = pi * (0.0025)^2 * 0.564 = 1.1074e-5 m^3
# Power density = 225 / 1.1074e-5 = 20317665 W/m^3
fvModels = get_header("dictionary", "fvModels") + """
heaterSource
{
    type            scalarSemiImplicitSource;
    volumeMode      specific;
    selectionMode   all;
    sources
    {
        h           (20317665 0);
    }
}
"""
write_file("constant/heater/fvModels", fvModels)


# -----------------
# 0.orig directory
# -----------------

def create_field(name, dim, int_val, boundary_str):
    content = get_header("volScalarField" if type(int_val) != tuple else "volVectorField", name) + f"""
dimensions      {dim};
internalField   uniform {int_val};
boundaryField
{{
{boundary_str}
}}
"""
    return content

for region in regions:
    is_fluid = region in fluids

    b_T = f"""
    frontAndBack {{ type empty; }}
    ".*_to_.*"
    {{
        type            turbulentTemperatureRadCoupledMixed;
        Tnbr            T;
        kappaMethod     {'fluidThermo' if is_fluid else 'solidThermo'};
        value           uniform 300;
    }}
    inlet {{ type fixedValue; value uniform 300; }}
    outlet {{ type inletOutlet; inletValue uniform 300; value uniform 300; }}
    outerBoundary {{ type zeroGradient; }}
    ".*" {{ type zeroGradient; }}
"""
    write_file(f"0.orig/{region}/T", create_field("T", "[0 0 0 1 0 0 0]", 300, b_T))

    b_alphat = f"""
    frontAndBack {{ type empty; }}
    ".*_to_.*"
    {{
        type            alphatWallFunction;
        Prt             0.85;
        value           uniform 0;
    }}
    inlet {{ type calculated; value uniform 0; }}
    outlet {{ type calculated; value uniform 0; }}
    outerBoundary {{ type calculated; value uniform 0; }}
    ".*" {{ type calculated; value uniform 0; }}
"""
    write_file(f"0.orig/{region}/alphat", create_field("alphat", "[1 -1 -1 0 0 0 0]", 0, b_alphat))

    if is_fluid:
        b_p = f"""
    frontAndBack {{ type empty; }}
    inlet {{ type zeroGradient; }}
    outlet {{ type fixedValue; value uniform 100000; }}
    outerBoundary {{ type zeroGradient; }}
    ".*" {{ type zeroGradient; }}
"""
        write_file(f"0.orig/{region}/p", create_field("p", "[1 -1 -2 0 0 0 0]", 100000, b_p))
        write_file(f"0.orig/{region}/p_rgh", create_field("p_rgh", "[1 -1 -2 0 0 0 0]", 100000, b_p))

        b_U = f"""
    frontAndBack {{ type empty; }}
    inlet {{ type fixedValue; value uniform (1 0 0); }}
    outlet {{ type inletOutlet; inletValue uniform (0 0 0); value uniform (1 0 0); }}
    outerBoundary {{ type slip; }}
    ".*" {{ type noSlip; }}
"""
        write_file(f"0.orig/{region}/U", create_field("U", "[0 1 -1 0 0 0 0]", "(0 0 0)", b_U))

        b_k = f"""
    frontAndBack {{ type empty; }}
    inlet {{ type fixedValue; value uniform 0.00375; }}
    outlet {{ type inletOutlet; inletValue uniform 0.00375; value uniform 0.00375; }}
    outerBoundary {{ type zeroGradient; }}
    ".*" {{ type kqRWallFunction; value uniform 0.00375; }}
"""
        write_file(f"0.orig/{region}/k", create_field("k", "[0 2 -2 0 0 0 0]", 0.00375, b_k))

        b_eps = f"""
    frontAndBack {{ type empty; }}
    inlet {{ type fixedValue; value uniform 0.01; }}
    outlet {{ type inletOutlet; inletValue uniform 0.01; value uniform 0.01; }}
    outerBoundary {{ type zeroGradient; }}
    ".*" {{ type epsilonWallFunction; value uniform 0.01; }}
"""
        write_file(f"0.orig/{region}/epsilon", create_field("epsilon", "[0 2 -3 0 0 0 0]", 0.01, b_eps))

        b_nut = f"""
    frontAndBack {{ type empty; }}
    inlet {{ type calculated; value uniform 0; }}
    outlet {{ type calculated; value uniform 0; }}
    outerBoundary {{ type calculated; value uniform 0; }}
    ".*" {{ type nutkWallFunction; value uniform 0; }}
"""
        write_file(f"0.orig/{region}/nut", create_field("nut", "[0 2 -1 0 0 0 0]", 0, b_nut))
        write_file(f"0.orig/{region}/mut", create_field("mut", "[1 -1 -1 0 0 0 0]", 0, b_nut))


        # fvDOM fields: G, q, qr (calculated) and IDefault
        b_G = f"""
    frontAndBack {{ type empty; }}
    ".*" {{ type calculated; value uniform 0; }}
"""
        write_file(f"0.orig/{region}/G", create_field("G", "[1 0 -3 0 0 0 0]", 0, b_G))

        b_IDefault = f"""
    frontAndBack {{ type empty; }}
    ".*heater.*"
    {{
        type            greyDiffusiveRadiation;
        emissivityMode  lookup;
        emissivity      uniform 0.7;
        value           uniform 0;
    }}
    ".*cylinder.*"
    {{
        type            greyDiffusiveRadiation;
        emissivityMode  lookup;
        emissivity      uniform 0.8;
        value           uniform 0;
    }}
    ".*"
    {{
        type            greyDiffusiveRadiation;
        emissivityMode  lookup;
        emissivity      uniform 1.0;
        value           uniform 0;
    }}
"""
        write_file(f"0.orig/{region}/IDefault", create_field("IDefault", "[1 0 -3 0 0 0 0]", 0, b_IDefault))

        b_q = f"""
    frontAndBack {{ type empty; }}
    ".*" {{ type calculated; value uniform 0; }}
"""
        write_file(f"0.orig/{region}/q", create_field("q", "[1 0 -3 0 0 0 0]", 0, b_q))
        write_file(f"0.orig/{region}/qr", create_field("qr", "[1 0 -3 0 0 0 0]", 0, b_q))

print("setup_physics.py complete.")
