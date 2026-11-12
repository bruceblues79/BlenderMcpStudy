"""默认直出：生成高原苔地地块 + 渲染预览，不保存 .blend，结束后退出 Blender。

用法：
    blender -b --factory-startup --python preview.py -- [--preset ground_plateau_moss] [--out previews/xxx.png]
"""
import sys, os, json, math, argparse
import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(SKILL))
sys.path.insert(0, HERE)
import groundgen

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--preset", default="ground_plateau_moss")
ap.add_argument("--out", default="")
ap.add_argument("--cam-y", type=float, default=-8.2)
ap.add_argument("--cam-z", type=float, default=8.2)
ap.add_argument("--target-z", type=float, default=0.4)
args = ap.parse_args(argv)

spec = groundgen.load_spec(os.path.join(SKILL, "presets", args.preset + ".json"))

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
objs, rep = groundgen.build(spec, name="Tile_Ground",
                            collection=groundgen.ensure_collection("Ground"), scene=scene)
print("REPORT", json.dumps(rep, ensure_ascii=False))

world = bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
nt = world.node_tree
bg = nt.nodes.get("Background")
env = nt.nodes.new("ShaderNodeTexEnvironment")
env.image = bpy.data.images.load(os.path.join(ROOT, ".skills", "STARTER", "assets", "qwantani_noon_puresky_1k.exr"))
nt.links.new(env.outputs["Color"], bg.inputs["Color"])

with bpy.data.libraries.load(os.path.join(ROOT, ".skills", "STARTER", "assets", "ref_human.blend"), link=False) as (src, dst):
    dst.collections = list(src.collections)
for coll in dst.collections:
    scene.collection.children.link(coll)
for obj in bpy.data.objects:
    if obj.name.startswith("ref_human"):
        obj.location = (2.4, -2.4, 0.0)

def gray_mat(name, value):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value = (value, value, value, 1.0)
    p.inputs["Roughness"].default_value = 0.95
    return m

bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 9.0, 4.0), rotation=(math.radians(90), 0, 0))
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
scene.render.resolution_x = 1600
scene.render.resolution_y = 900
scene.render.image_settings.file_format = 'PNG'

out = args.out or os.path.join(ROOT, "previews", f"TheFarField_{args.preset}.png")
scene.render.filepath = out
bpy.ops.render.render(write_still=True)
print("PREVIEW", out)
print("DONE")
