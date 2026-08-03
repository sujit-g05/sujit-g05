import gmsh
import os

def create_mesh():
    gmsh.initialize()
    gmsh.model.add("multiregion")

    # Dimensions
    L = 22.4
    H = 6.0
    R_out = 150e-3 / 2          # 0.075
    R_in = R_out - 0.9e-3       # 0.0741
    R_heater = 5e-3 / 2         # 0.0025
    dz = 0.1 # Z-thickness for 2D

    # Create 2D geometry
    box = gmsh.model.occ.addRectangle(-L/2, -H/2, 0, L, H)

    cyl_outer = gmsh.model.occ.addDisk(0, 0, 0, R_out, R_out)
    cyl_inner = gmsh.model.occ.addDisk(0, 0, 0, R_in, R_in)
    heater = gmsh.model.occ.addDisk(0, 0, 0, R_heater, R_heater)

    # Fragment to get distinct non-overlapping regions
    gmsh.model.occ.fragment([(2, box)], [(2, cyl_outer), (2, cyl_inner), (2, heater)])
    gmsh.model.occ.synchronize()

    # Identify the 2D regions by their areas
    surfaces = gmsh.model.getEntities(2)
    areas = []
    for dim, tag in surfaces:
        mass = gmsh.model.occ.getMass(dim, tag)
        cm = gmsh.model.occ.getCenterOfMass(dim, tag)
        areas.append((tag, mass, cm))

    # Sort by area
    areas.sort(key=lambda x: x[1])

    vols = {}
    surf_to_name = {
        areas[0][0]: "heater",
        areas[1][0]: "cylinder",
        areas[2][0]: "innerAir",
        areas[3][0]: "outerAir"
    }

    front_back_surfs = []
    for tag, name in surf_to_name.items():
        ext = gmsh.model.occ.extrude([(2, tag)], 0, 0, dz, numElements=[1], recombine=True)
        top_surf = ext[0][1]
        vol = ext[1][1]
        vols[name] = vol
        front_back_surfs.extend([tag, top_surf])

    gmsh.model.occ.synchronize()
    gmsh.model.occ.removeAllDuplicates()
    gmsh.model.occ.synchronize()

    inlet_surfs = []
    outlet_surfs = []
    top_bottom_surfs = []

    surfaces = gmsh.model.getEntities(2)
    final_front_back = []

    for dim, tag in surfaces:
        bbox = gmsh.model.getBoundingBox(dim, tag)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox

        # Front and back
        if abs(zmax - zmin) < 1e-6:
            final_front_back.append(tag)
            continue

        # Left (inlet)
        if abs(xmin - (-L/2)) < 1e-6 and abs(xmax - (-L/2)) < 1e-6:
            inlet_surfs.append(tag)
            continue

        # Right (outlet)
        if abs(xmin - (L/2)) < 1e-6 and abs(xmax - (L/2)) < 1e-6:
            outlet_surfs.append(tag)
            continue

        # Top and bottom
        if (abs(ymin - (-H/2)) < 1e-6 and abs(ymax - (-H/2)) < 1e-6) or \
           (abs(ymin - (H/2)) < 1e-6 and abs(ymax - (H/2)) < 1e-6):
            top_bottom_surfs.append(tag)
            continue

    for name, tag in vols.items():
        gmsh.model.addPhysicalGroup(3, [tag], name=name)

    if inlet_surfs: gmsh.model.addPhysicalGroup(2, inlet_surfs, name="inlet")
    if outlet_surfs: gmsh.model.addPhysicalGroup(2, outlet_surfs, name="outlet")
    if top_bottom_surfs: gmsh.model.addPhysicalGroup(2, top_bottom_surfs, name="topAndBottom")
    if final_front_back: gmsh.model.addPhysicalGroup(2, final_front_back, name="frontAndBack")

    # Meshing - MAKE COARSER FOR SPEED
    gmsh.model.mesh.field.add("Distance", 1)
    gmsh.model.mesh.field.setNumbers(1, "CurvesList", [c for d, c in gmsh.model.getEntities(1) if d==1])
    gmsh.model.mesh.field.setNumber(1, "Sampling", 20)

    gmsh.model.mesh.field.add("Threshold", 2)
    gmsh.model.mesh.field.setNumber(2, "InField", 1)
    gmsh.model.mesh.field.setNumber(2, "SizeMin", 0.005) # coarser
    gmsh.model.mesh.field.setNumber(2, "SizeMax", 1.0)   # coarser
    gmsh.model.mesh.field.setNumber(2, "DistMin", 0.1)
    gmsh.model.mesh.field.setNumber(2, "DistMax", 2.0)

    gmsh.model.mesh.field.setAsBackgroundMesh(2)
    gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
    gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)

    gmsh.model.mesh.generate(3)
    gmsh.write("mesh.msh")
    gmsh.finalize()

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
""")

def create_run_script():
    with open("run.sh", "w") as f:
        f.write("""#!/bin/bash
set -e
gmshToFoam mesh.msh

# Update boundary type for frontAndBack to empty
sed -i '/frontAndBack/,/}/ s/type.*patch;/type empty;/' constant/polyMesh/boundary
sed -i '/frontAndBack/,/}/ s/type.*wall;/type empty;/' constant/polyMesh/boundary

splitMeshRegions -cellZones -overwrite
""")
    os.chmod("run.sh", 0o755)

if __name__ == "__main__":
    create_mesh()
    create_openfoam_dicts()
    create_run_script()
