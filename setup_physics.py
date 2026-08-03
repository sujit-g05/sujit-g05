import os
import shutil

# Properties
rho_heater = 7250
Cp_heater = 460
kappa_heater = 11

rho_cyl = 1570
Cp_cyl = 857.41
kappa_cyl = 0.84126

rho_glass = 2230
Cp_glass = 830
kappa_glass = 1.14

# Heat Source
# 15% of 1500W = 225W.
# Volume = pi * r^2 * L = pi * (0.0025)^2 * 0.564 = 1.1074e-5 m^3
# q = 225 / 1.1074e-5 = 20317861.6 W/m^3
heat_source = 20317862.0

solids = ["heater", "cylinder", "glass"]
fluids = ["innerAir", "outerAir"]
all_regions = solids + fluids

def write_file(filepath, content):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
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

def setup_constant():
    # Gravity
    write_file("constant/g", get_header("uniformDimensionedVectorField", "g") + "\ndimensions      [0 1 -2 0 0 0 0];\nvalue           (0 -9.81 0);\n")

    # Solid thermophysical properties
    def get_solid_thermo(rho, cp, kappa):
        return get_header("dictionary", "thermophysicalProperties") + f"""
thermoType
{{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       constIso;
    thermo          eConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleInternalEnergy;
}}

mixture
{{
    specie
    {{
        nMoles          1;
        molWeight       12;
    }}
    equationOfState
    {{
        rho             {rho};
    }}
    thermo
    {{
        Cv              {cp};
        Hf              0;
    }}
    transport
    {{
        kappa           {kappa};
    }}
}}
"""

    write_file("constant/heater/thermophysicalProperties", get_solid_thermo(rho_heater, Cp_heater, kappa_heater))
    write_file("constant/cylinder/thermophysicalProperties", get_solid_thermo(rho_cyl, Cp_cyl, kappa_cyl))
    write_file("constant/glass/thermophysicalProperties", get_solid_thermo(rho_glass, Cp_glass, kappa_glass))

    for solid in solids:
        write_file(f"constant/{solid}/radiationProperties", get_header("dictionary", "radiationProperties") + "\nradiation off;\n")

    # Fluid thermophysical properties
    fluid_thermo = get_header("dictionary", "thermophysicalProperties") + """
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
        nMoles          1;
        molWeight       28.96;
    }
    equationOfState
    {
        pRef            101325;
    }
    thermo
    {
        Cp              1004.4;
        Hf              0;
    }
    transport
    {
        mu              1.831e-05;
        Pr              0.705;
    }
}
"""
    for fluid in fluids:
        write_file(f"constant/{fluid}/thermophysicalProperties", fluid_thermo)
        write_file(f"constant/{fluid}/turbulenceProperties", get_header("dictionary", "turbulenceProperties") + "\nsimulationType laminar;\n")
        write_file(f"constant/{fluid}/radiationProperties", get_header("dictionary", "radiationProperties") + "\nradiation off;\n")


def setup_system():
    # ControlDict
    write_file("system/controlDict", get_header("dictionary", "controlDict") + """
application     foamMultiRun;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         10;
deltaT          0.001;
writeControl    timeStep;
writeInterval   1000;
purgeWrite      0;
writeFormat     ascii;
writePrecision  6;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;

modules
(
    {
        name fluid;
        type fluidMultiRegion;
        regions (innerAir outerAir);
    }
    {
        name solid;
        type solidMultiRegion;
        regions (heater cylinder glass);
    }
);
""")

    # fvModels for heater
    write_file("system/heater/fvModels", get_header("dictionary", "fvModels") + f"""
heater_source
{{
    type            scalarSemiImplicitSource;
    volumeMode      specific;
    selectionMode   all;
    sources
    {{
        e           ({heat_source} 0);
    }}
}}
""")

    # fvSchemes & fvSolution per region
    solid_schemes = get_header("dictionary", "fvSchemes") + """
ddtSchemes { default Euler; }
gradSchemes { default Gauss linear; }
divSchemes { default none; }
laplacianSchemes { default Gauss linear orthogonal; }
interpolationSchemes { default linear; }
snGradSchemes { default orthogonal; }
"""

    fluid_schemes = get_header("dictionary", "fvSchemes") + """
ddtSchemes { default Euler; }
gradSchemes { default Gauss linear; }
divSchemes {
    default none;
    div(phi,U) Gauss upwind;
    div(phi,h) Gauss upwind;
    div(phi,K) Gauss upwind;
    div(phid,p) Gauss upwind;
    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear orthogonal; }
interpolationSchemes { default linear; }
snGradSchemes { default orthogonal; }
"""

    solid_solution = get_header("dictionary", "fvSolution") + """
solvers {
    "e.*" { solver PCG; preconditioner DIC; tolerance 1e-7; relTol 0; }
}
PIMPLE {
    nOuterCorrectors 1;
    nCorrectors      2;
    nNonOrthogonalCorrectors 0;
}
"""

    fluid_solution = get_header("dictionary", "fvSolution") + """
solvers {
    "p_rgh.*" { solver PCG; preconditioner DIC; tolerance 1e-7; relTol 0.05; }
    "p_rghFinal" { solver PCG; preconditioner DIC; tolerance 1e-7; relTol 0; }
    "U.*" { solver PBiCGStab; preconditioner DILU; tolerance 1e-7; relTol 0.1; }
    "h.*" { solver PBiCGStab; preconditioner DILU; tolerance 1e-7; relTol 0.1; }
}
PIMPLE {
    nOuterCorrectors 1;
    nCorrectors      2;
    nNonOrthogonalCorrectors 0;
    pRefCell         0;
    pRefValue        101325;
}
"""

    for solid in solids:
        write_file(f"system/{solid}/fvSchemes", solid_schemes)
        write_file(f"system/{solid}/fvSolution", solid_solution)

    for fluid in fluids:
        write_file(f"system/{fluid}/fvSchemes", fluid_schemes)
        write_file(f"system/{fluid}/fvSolution", fluid_solution)


def setup_0_orig():
    os.makedirs("0.orig", exist_ok=True)

    for solid in solids:
        os.makedirs(f"0.orig/{solid}", exist_ok=True)
        # T
        write_file(f"0.orig/{solid}/T", get_header("volScalarField", "T") + """
dimensions      [0 0 0 1 0 0 0];
internalField   uniform 300;
boundaryField
{
    frontAndBack { type empty; }
    ".*"         { type compressible::turbulentTemperatureRadCoupledMixed; Tnbr T; kappaMethod solidThermo; value uniform 300; }
}
""")

    for fluid in fluids:
        os.makedirs(f"0.orig/{fluid}", exist_ok=True)
        # T
        write_file(f"0.orig/{fluid}/T", get_header("volScalarField", "T") + """
dimensions      [0 0 0 1 0 0 0];
internalField   uniform 300;
boundaryField
{
    inlet        { type fixedValue; value uniform 300; }
    outlet       { type inletOutlet; inletValue uniform 300; value uniform 300; }
    topAndBottom { type zeroGradient; }
    frontAndBack { type empty; }
    ".*"         { type compressible::turbulentTemperatureRadCoupledMixed; Tnbr T; kappaMethod fluidThermo; value uniform 300; }
}
""")
        # U
        u_val = "(1 0 0)" if fluid == "outerAir" else "(0 0 0)"
        write_file(f"0.orig/{fluid}/U", get_header("volVectorField", "U") + f"""
dimensions      [0 1 -1 0 0 0 0];
internalField   uniform {u_val};
boundaryField
{{
    inlet        {{ type fixedValue; value uniform {u_val}; }}
    outlet       {{ type inletOutlet; inletValue uniform (0 0 0); value uniform {u_val}; }}
    topAndBottom {{ type symmetry; }}
    frontAndBack {{ type empty; }}
    ".*"         {{ type noSlip; }}
}}
""")
        # p_rgh
        write_file(f"0.orig/{fluid}/p_rgh", get_header("volScalarField", "p_rgh") + """
dimensions      [1 -1 -2 0 0 0 0];
internalField   uniform 101325;
boundaryField
{
    inlet        { type zeroGradient; }
    outlet       { type fixedValue; value uniform 101325; }
    topAndBottom { type symmetry; }
    frontAndBack { type empty; }
    ".*"         { type fixedFluxPressure; value uniform 101325; }
}
""")
        # p
        write_file(f"0.orig/{fluid}/p", get_header("volScalarField", "p") + """
dimensions      [1 -1 -2 0 0 0 0];
internalField   uniform 101325;
boundaryField
{
    inlet        { type calculated; value uniform 101325; }
    outlet       { type calculated; value uniform 101325; }
    topAndBottom { type symmetry; }
    frontAndBack { type empty; }
    ".*"         { type calculated; value uniform 101325; }
}
""")


if __name__ == "__main__":
    setup_constant()
    setup_system()
    setup_0_orig()

    # Update run script
    with open("run.sh", "a") as f:
        f.write("\nrm -rf 0\ncp -r 0.orig 0\n")
