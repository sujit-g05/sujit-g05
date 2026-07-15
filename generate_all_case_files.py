import os

regions = ['air', 'innerAir', 'cylinder', 'heater', 'glass']
fluids = ['air', 'innerAir']
solids = ['cylinder', 'heater', 'glass']

for d in ['0.orig', 'constant', 'system']:
    os.makedirs(d, exist_ok=True)
    for r in regions:
        os.makedirs(f"{d}/{r}", exist_ok=True)

header = """/*--------------------------------*- C++ -*----------------------------------*\\
  =========                 |
  \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\\\    /   O peration     | Website:  https://openfoam.org
    \\\\  /    A nd           | Version:  13
     \\\\/     M anipulation  |
\\*---------------------------------------------------------------------------*/
"""

def write_solid_thermo(region, rho, cp, kappa):
    content = header + f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant/{region}";
    object      thermophysicalProperties;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

thermoType
{{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       constIso;
    thermo          hConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleEnthalpy;
}}

mixture
{{
    specie
    {{
        nMoles          1;
        molWeight       12;
    }}
    transport
    {{
        kappa           {kappa};
    }}
    thermodynamics
    {{
        Hf              0;
        Cp              {cp};
    }}
    equationOfState
    {{
        rho             {rho};
    }}
}}
"""
    with open(f"constant/{region}/thermophysicalProperties", "w") as f:
        f.write(content)

def write_fluid_thermo(region):
    content = header + f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant/{region}";
    object      thermophysicalProperties;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

thermoType
{{
    type            heRhoThermo;
    mixture         pureMixture;
    transport       const;
    thermo          hConst;
    equationOfState perfectGas;
    specie          specie;
    energy          sensibleEnthalpy;
}}

mixture
{{
    specie
    {{
        nMoles          1;
        molWeight       28.9;
    }}
    equationOfState
    {{
        Cp              1005;
        Hf              0;
    }}
    transport
    {{
        mu              1.8e-05;
        Pr              0.7;
    }}
}}
"""
    with open(f"constant/{region}/thermophysicalProperties", "w") as f:
        f.write(content)

write_solid_thermo("cylinder", 1570, 857.41, 0.84126)
write_solid_thermo("heater", 7250, 460, 11)
write_solid_thermo("glass", 2230, 750, 1.14)
write_fluid_thermo("air")
write_fluid_thermo("innerAir")

with open("system/heater/fvModels", "w") as f:
    f.write(header + """FoamFile
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
        h           (225 0);
    }
}
""")

with open("constant/regionProperties", "w") as f:
    f.write(header + """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant";
    object      regionProperties;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

regions
(
    fluid       (air innerAir)
    solid       (cylinder heater glass)
);
""")

with open("constant/g", "w") as f:
    f.write(header + """FoamFile
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

for r in regions:
    with open(f"constant/{r}/radiationProperties", "w") as f:
        f.write(header + f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "constant/{r}";
    object      radiationProperties;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

radiation       off;
radiationModel  none;
""")
