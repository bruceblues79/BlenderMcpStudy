"""默认直出：生成石块 + 渲染预览，不保存 .blend，结束后退出 Blender。

用法：
    blender -b --factory-startup --python preview.py -- [--preset rock] [--out previews/xxx.png]
"""
import sys, os, json, math, argparse
import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(SKILL))
sys.path.insert(0, HERE)
import rockgen

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--preset", default="rock")
ap.add_argument("--out", default="")
ap.add_argument("--layout", choices=["placement", "row"], default="placement")
ap.add_argument("--cam-y", type=float, default=None)
ap.add_argument("--cam-z", type=float, default=None)
ap.add_argument("--target-z", type=float, default=None)
args = ap.parse_args(argv)

if args.layout == "row":
    args.cam_y = -10.2 if args.cam_y is None else args.cam_y
    args.cam_z = 1.5 if args.cam_z is None else args.cam_z
    args.target_z = 0.30 if args.target_z is None else args.target_z
else:
    args.cam_y = -7.6 if args.cam_y is None else args.cam_y
    args.cam_z = 1.8 if args.cam_z is None else args.cam_z
    args.target_z = 0.40 if args.target_z is None else args.target_z

spec = rockgen.load_spec(os.path.join(SKILL, "presets", args.preset + ".json"))

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
placement = None
if args.layout == "row":
    placement = [(-1.95 + i * 0.65, -6.6) for i in range(len(spec["prototypes"]))]
objs, rep = rockgen.build(spec, name="Rock", collection=rockgen.ensure_collection("Rocks_Prototype"), placement=placement)
print("REPORT", json.dumps(rep, ensure_ascii=False))

world = bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
nt = world.node_tree
bg = nt.nodes.get("Background")
env = nt.nodes.new("ShaderNodeTexEnvironment")
env.image = bpy.data.images.load(os.path.join(ROOT, ".skill", "STARTER", "assets", "qwantani_noon_puresky_1k.exr"))
nt.links.new(env.outputs["Color"], bg.inputs["Color"])

with bpy.data.libraries.load(os.path.join(ROOT, ".skill", "STARTER", "assets", "ref_human.blend"), link=False) as (src, dst):
    dst.collections = list(src.collections)
for coll in dst.collections:
    scene.collection.children.link(coll)
human_xy = (2.35, -6.6) if args.layout == "row" else (0.0, 0.0)
for obj in bpy.data.objects:
    if obj.name.startswith("ref_human"):
        obj.location = (human_xy[0], human_xy[1], 0.0)

def gray_mat(name, value):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value = (value, value, value, 1.0)
    p.inputs["Roughness"].default_value = 0.95
    return m

bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
bpy.context.active_object.name = "Preview_Floor"
bpy.context.active_object.data.materials.append(gray_mat("MAT_Preview_Floor", 0.62))

bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 9.0, 4.0), rotation=(math.radians(90), 0, 0))
bpy.context.active_object.name = "Preview_Backdrop"
bpy.context.active_object.data.materials.append(gray_mat("MAT_Preview_Backdrop", 0.45))

cam_data = bpy.data.cameras.new("Camera")
cam_data.lens = 24.0
cam = bpy.data.objects.new("Camera", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
cam.location = (0.0, args.cam_y, args.cam_z)
cam.rotation_euler = (Vector((0.0, 0.0, args.target_z)) - cam.location).to_track_quat('-Z', 'Y').to_euler()

scene.render.engine = 'BLENDER_EEVEE'
scene.render.film_transparent = True
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.image_settings.file_format = 'PNG'

out = args.out or os.path.join(ROOT, "previews", f"TheFarField_rock_{args.layout}_{args.preset}.png")
scene.render.filepath = out
bpy.ops.render.render(write_still=True)
print("PREVIEW", out)
print("DONE")
