import os

# Physical parameters
Lx = 22.4  # domain length
Ly = 6.0   # domain height
Lz = 0.1   # domain thickness (for 2D)

cyl_L = 0.56
cyl_OD = 0.15
cyl_thick = 0.0009
glass_thick = 0.002

heater_L = 0.564
heater_D = 0.005

# Derived parameters
x0 = -Lx / 2
x1 = -heater_L / 2
x2 = -cyl_L / 2
x3 = cyl_L / 2
x4 = heater_L / 2
x5 = Lx / 2

y0 = -Ly / 2
y1 = -cyl_OD / 2
y2 = -cyl_OD / 2 + cyl_thick
y3 = -heater_D / 2
y4 = heater_D / 2
y5 = cyl_OD / 2 - cyl_thick
y6 = cyl_OD / 2
y7 = Ly / 2

z0 = -Lz / 2
z1 = Lz / 2

xs = [x0, x1, x2, x3, x4, x5]
ys = [y0, y1, y2, y3, y4, y5, y6, y7]
zs = [z0, z1]

nx = [150, 5, 100, 5, 200]
ny = [80, 5, 40, 10, 40, 5, 80]

gx = [0.05, 1, 1, 1, 20]
gy = [0.05, 1, 1, 1, 1, 1, 20]

regions = [
    # j=0
    ['outerAir', 'outerAir', 'outerAir', 'outerAir', 'outerAir'],
    # j=1
    ['outerAir', 'glass', 'cylinder', 'glass', 'outerAir'],
    # j=2
    ['outerAir', 'glass', 'innerAir', 'glass', 'outerAir'],
    # j=3
    ['outerAir', 'heater', 'heater', 'heater', 'outerAir'],
    # j=4
    ['outerAir', 'glass', 'innerAir', 'glass', 'outerAir'],
    # j=5
    ['outerAir', 'glass', 'cylinder', 'glass', 'outerAir'],
    # j=6
    ['outerAir', 'outerAir', 'outerAir', 'outerAir', 'outerAir'],
]

def v_idx(i, j, k):
    return i + j * len(xs) + k * len(xs) * len(ys)

os.makedirs('system', exist_ok=True)
with open('system/blockMeshDict', 'w') as f:
    f.write('''/*--------------------------------*- C++ -*----------------------------------*\\
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
''')
    for k in range(len(zs)):
        for j in range(len(ys)):
            for i in range(len(xs)):
                f.write(f"    ({xs[i]:.6f} {ys[j]:.6f} {zs[k]:.6f})\n")

    f.write(''');

blocks
(
''')
    for j in range(len(ys) - 1):
        for i in range(len(xs) - 1):
            v0 = v_idx(i, j, 0)
            v1 = v_idx(i+1, j, 0)
            v2 = v_idx(i+1, j+1, 0)
            v3 = v_idx(i, j+1, 0)
            v4 = v_idx(i, j, 1)
            v5 = v_idx(i+1, j, 1)
            v6 = v_idx(i+1, j+1, 1)
            v7 = v_idx(i, j+1, 1)

            zone = regions[j][i]

            f.write(f"    hex ({v0} {v1} {v2} {v3} {v4} {v5} {v6} {v7}) {zone} ({nx[i]} {ny[j]} 1) simpleGrading ({gx[i]} {gy[j]} 1)\n")

    f.write(''');

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
''')
    for j in range(len(ys) - 1):
        i = 0
        v0 = v_idx(i, j, 0)
        v3 = v_idx(i, j+1, 0)
        v4 = v_idx(i, j, 1)
        v7 = v_idx(i, j+1, 1)
        f.write(f"            ({v0} {v4} {v7} {v3})\n")
    f.write('''        );
    }
    outlet
    {
        type patch;
        faces
        (
''')
    for j in range(len(ys) - 1):
        i = len(xs) - 1
        v1 = v_idx(i, j, 0)
        v2 = v_idx(i, j+1, 0)
        v5 = v_idx(i, j, 1)
        v6 = v_idx(i, j+1, 1)
        f.write(f"            ({v1} {v2} {v6} {v5})\n")
    f.write('''        );
    }
    bottom
    {
        type patch;
        faces
        (
''')
    for i in range(len(xs) - 1):
        j = 0
        v0 = v_idx(i, j, 0)
        v1 = v_idx(i+1, j, 0)
        v4 = v_idx(i, j, 1)
        v5 = v_idx(i+1, j, 1)
        f.write(f"            ({v0} {v1} {v5} {v4})\n")
    f.write('''        );
    }
    top
    {
        type patch;
        faces
        (
''')
    for i in range(len(xs) - 1):
        j = len(ys) - 1
        v3 = v_idx(i, j, 0)
        v2 = v_idx(i+1, j, 0)
        v7 = v_idx(i, j, 1)
        v6 = v_idx(i+1, j, 1)
        f.write(f"            ({v3} {v7} {v6} {v2})\n")
    f.write('''        );
    }
    frontAndBack
    {
        type empty;
        faces
        (
''')
    for j in range(len(ys) - 1):
        for i in range(len(xs) - 1):
            v0 = v_idx(i, j, 0)
            v1 = v_idx(i+1, j, 0)
            v2 = v_idx(i+1, j+1, 0)
            v3 = v_idx(i, j+1, 0)
            v4 = v_idx(i, j, 1)
            v5 = v_idx(i+1, j, 1)
            v6 = v_idx(i+1, j+1, 1)
            v7 = v_idx(i, j+1, 1)
            f.write(f"            ({v0} {v3} {v2} {v1})\n")
            f.write(f"            ({v4} {v5} {v6} {v7})\n")
    f.write('''        );
    }
);
''')

print("setup_mesh.py created.")
