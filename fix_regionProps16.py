import os

path = "generate_all_case_files.py"
with open(path, "r") as f:
    content = f.read()

bad_syntax = """regions
{
    fluid       (air innerAir);
    solid       (cylinder heater glass);
}"""

good_syntax = """regions
(
    fluid       (air innerAir)
    solid       (cylinder heater glass)
);"""

content = content.replace(bad_syntax, good_syntax)
with open(path, "w") as f:
    f.write(content)
