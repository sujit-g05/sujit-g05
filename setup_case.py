import os
import math

def create_blockMeshDict():
    # Helper to calculate points
    pts = []
    def add_pt(x, y):
        pts.append((x, y))
        return len(pts) - 1

    # Heater square core (a)
    a = 0.0012
    L0_0 = add_pt(-a, -a)
    L0_1 = add_pt( a, -a)
    L0_2 = add_pt( a,  a)
    L0_3 = add_pt(-a,  a)

    # Heater boundary (r = 0.0025)
    b1 = 0.0025 / 1.41421356
    L1_0 = add_pt(-b1, -b1)
    L1_1 = add_pt( b1, -b1)
    L1_2 = add_pt( b1,  b1)
    L1_3 = add_pt(-b1,  b1)

    # Inner Air boundary (r = 0.0741)
    b2 = 0.0741 / 1.41421356
    L2_0 = add_pt(-b2, -b2)
    L2_1 = add_pt( b2, -b2)
    L2_2 = add_pt( b2,  b2)
    L2_3 = add_pt(-b2,  b2)

    # Cylinder boundary (r = 0.075)
    b3 = 0.075 / 1.41421356
    L3_0 = add_pt(-b3, -b3)
    L3_1 = add_pt( b3, -b3)
    L3_2 = add_pt( b3,  b3)
    L3_3 = add_pt(-b3,  b3)

    # Outer Air boundary (rectangular box, user domain 6x6, so X +/- 3.0, Y +/- 3.0)
    # The previous setup used an O-grid mapping to a rectangular boundary.
    s = 0.15 # intermediate square for grading
    P = {}
    X_vals = [-3.0, -s, s, 3.0]
    Y_vals = [-3.0, -s, s, 3.0]

    for i in range(4):
        for j in range(4):
            P[(i,j)] = add_pt(X_vals[i], Y_vals[j])

    L4_0 = P[(1,1)]
    L4_1 = P[(2,1)]
    L4_2 = P[(2,2)]
    L4_3 = P[(1,2)]

    N = len(pts)
    pts_str = ""
    for p in pts:
        pts_str += f"    ({p[0]:.6f} {p[1]:.6f} 0)\n"
    for p in pts:
        pts_str += f"    ({p[0]:.6f} {p[1]:.6f} 0.1)\n"

    blocks = []
    n_tan = 30
    n_rad_h = 10
    n_rad_ia = 40
    n_rad_cyl = 5
    n_rad_oa = 20

    # Heater core
    blocks.append(f"    hex ({L0_0} {L0_1} {L0_2} {L0_3} {L0_0+N} {L0_1+N} {L0_2+N} {L0_3+N}) heater ({n_tan} {n_tan} 1) simpleGrading (1 1 1)")

    # O-grid Rings (Anti-Clockwise right-hand rule)
    def add_ring(inner, outer, n_r, zone):
        blocks.append(f"    hex ({inner[0]} {outer[0]} {outer[1]} {inner[1]} {inner[0]+N} {outer[0]+N} {outer[1]+N} {inner[1]+N}) {zone} ({n_r} {n_tan} 1) simpleGrading (1 1 1)")
        blocks.append(f"    hex ({inner[1]} {outer[1]} {outer[2]} {inner[2]} {inner[1]+N} {outer[1]+N} {outer[2]+N} {inner[2]+N}) {zone} ({n_r} {n_tan} 1) simpleGrading (1 1 1)")
        blocks.append(f"    hex ({inner[2]} {outer[2]} {outer[3]} {inner[3]} {inner[2]+N} {outer[2]+N} {outer[3]+N} {inner[3]+N}) {zone} ({n_r} {n_tan} 1) simpleGrading (1 1 1)")
        blocks.append(f"    hex ({inner[3]} {outer[3]} {outer[0]} {inner[0]} {inner[3]+N} {outer[3]+N} {outer[0]+N} {inner[0]+N}) {zone} ({n_r} {n_tan} 1) simpleGrading (1 1 1)")

    add_ring([L0_0, L0_1, L0_2, L0_3], [L1_0, L1_1, L1_2, L1_3], n_rad_h, "heater")
    add_ring([L1_0, L1_1, L1_2, L1_3], [L2_0, L2_1, L2_2, L2_3], n_rad_ia, "innerAir")
    add_ring([L2_0, L2_1, L2_2, L2_3], [L3_0, L3_1, L3_2, L3_3], n_rad_cyl, "cylinder")
    add_ring([L3_0, L3_1, L3_2, L3_3], [L4_0, L4_1, L4_2, L4_3], n_rad_oa, "outerAir")

    nx_list = [50, n_tan, 50]
    ny_list = [30, n_tan, 30]

    # Outer rectangular domain blocks
    for i in range(3):
        for j in range(3):
            if i == 1 and j == 1:
                continue
            p0 = P[(i, j)]
            p1 = P[(i+1, j)]
            p2 = P[(i+1, j+1)]
            p3 = P[(i, j+1)]

            gx = 1
            if i == 0: gx = 0.05
            elif i == 2: gx = 20

            gy = 1
            if j == 0: gy = 0.05
            elif j == 2: gy = 20

            blocks.append(f"    hex ({p0} {p1} {p2} {p3} {p0+N} {p1+N} {p2+N} {p3+N}) outerAir ({nx_list[i]} {ny_list[j]} 1) simpleGrading ({gx} {gy} 1)")

    arcs = []
    def add_arcs(level_pts, R, z):
        arcs.append(f"    arc {level_pts[0]} {level_pts[1]} (0 {-R} {z})")
        arcs.append(f"    arc {level_pts[1]} {level_pts[2]} ({R} 0 {z})")
        arcs.append(f"    arc {level_pts[2]} {level_pts[3]} (0 {R} {z})")
        arcs.append(f"    arc {level_pts[3]} {level_pts[0]} ({-R} 0 {z})")

    add_arcs([L1_0, L1_1, L1_2, L1_3], 0.0025, 0)
    add_arcs([L1_0+N, L1_1+N, L1_2+N, L1_3+N], 0.0025, 0.1)

    add_arcs([L2_0, L2_1, L2_2, L2_3], 0.0741, 0)
    add_arcs([L2_0+N, L2_1+N, L2_2+N, L2_3+N], 0.0741, 0.1)

    add_arcs([L3_0, L3_1, L3_2, L3_3], 0.075, 0)
    add_arcs([L3_0+N, L3_1+N, L3_2+N, L3_3+N], 0.075, 0.1)

    def get_face(p0, p1):
        return f"({p0} {p1} {p1+N} {p0+N})"

    inlet_faces = []
    outlet_faces = []
    top_bottom_faces = []

    for j in range(3):
        inlet_faces.append(get_face(P[(0, j+1)], P[(0, j)]))
        outlet_faces.append(get_face(P[(3, j)], P[(3, j+1)]))

    for i in range(3):
        top_bottom_faces.append(get_face(P[(i+1, 3)], P[(i, 3)]))
        top_bottom_faces.append(get_face(P[(i, 0)], P[(i+1, 0)]))

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
{chr(10).join(blocks)}
);

edges
(
{chr(10).join(arcs)}
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
    outerBoundary
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

if __name__ == "__main__":
    create_blockMeshDict()
