"""ROCKGEN — 确定性程序化石块生成器（Blender 为媒介）。

同一份 spec + 同一 seed 必然生成完全一致的石块。
几何只依赖整数 seed 与 preset 数值，不含任何随机时钟/哈希顺序依赖，便于移植到其他引擎。
"""
import bpy
import bmesh
import json
import math
import os
import random
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
TEX_DIR = os.path.join(os.path.dirname(HERE), "textures")

DEFAULTS = {
    "budget": {"max_tri": 75, "min_tri": 12},
    "bounds": {"max_m": 0.5, "min_m": 0.2},
    "embed": [0.14, 0.22],
    "uv_tile_m": 0.5,
    "material": {
        "name": "MAT_Rock_Granite",
        "roughness": 0.62,
        "metallic": 0.0,
        "albedo": "rock_granite_color.png",
        "normal": "rock_granite_normal.png",
        "normal_strength": 0.6,
    },
    "jitter": 0.010,
    "smooth_factor": 0.26,
    "smooth_angle_deg": 45.0,
}


def load_spec(path):
    with open(path, "r", encoding="utf-8") as fh:
        spec = json.load(fh)
    for key, value in DEFAULTS.items():
        spec.setdefault(key, value)
    return spec


def ensure_collection(name):
    scene = bpy.context.scene
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        scene.collection.children.link(coll)
    return coll


def _fib_points(n):
    ga = math.pi * (3 - math.sqrt(5))
    out = []
    for i in range(n):
        z = 1 - 2 * (i + 0.5) / n
        r = math.sqrt(max(0.0, 1 - z * z))
        th = ga * i
        out.append(Vector((r * math.cos(th), r * math.sin(th), z)))
    return out


def _unit_vec(rng):
    while True:
        v = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1)))
        if v.length > 1e-6:
            return v.normalized()


def _tri_total(bm):
    return sum(len(f.verts) - 2 for f in bm.faces)


def _hull_base(rng, points, squash, rough):
    bm = bmesh.new()
    for d in _fib_points(points):
        k = 1.0 + rng.uniform(-rough, rough)
        bm.verts.new(Vector((d.x * k, d.y * k, d.z * k * squash)))
    bmesh.ops.convex_hull(bm, input=list(bm.verts))
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    return bm


def _chip(bm, co, no):
    geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=no, clear_outer=True)
    bedges = [e for e in bm.edges if e.is_boundary]
    if bedges:
        bmesh.ops.holes_fill(bm, edges=bedges, sides=0)
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    return bm


def _limited_chip(bm, co, no, budget):
    backup = bm.copy()
    _chip(bm, co, no)
    if _tri_total(bm) > budget or len(bm.faces) == 0:
        bm.free()
        return backup
    backup.free()
    return bm


def _gen_angular(rng, proto, budget, jitter, smooth_factor):
    bm = _hull_base(rng, proto["points"], proto["squash"], proto["roughness"])
    top_ratio = proto.get("top_ratio")
    if top_ratio is not None:
        zs = [v.co.z for v in bm.verts]
        lo, hi = min(zs), max(zs)
        bm = _limited_chip(bm, Vector((0, 0, lo + (hi - lo) * top_ratio)), Vector((0, 0, 1)), budget)
    if proto.get("deep_cut"):
        d = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.4, 0.8))).normalized()
        bm = _limited_chip(bm, d * rng.uniform(0.52, 0.60), d, budget)
    for _ in range(proto.get("cuts", 0)):
        d = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.6, 1.0))).normalized()
        bm = _limited_chip(bm, d * rng.uniform(0.80, 0.94), d, budget)
    bmesh.ops.smooth_vert(
        bm,
        verts=list(bm.verts),
        factor=smooth_factor,
        use_axis_x=True,
        use_axis_y=True,
        use_axis_z=True,
    )
    for v in bm.verts:
        r = v.co.length
        v.co += Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))) * (jitter * r)
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    return bm


def _gen_rounded(rng, proto, budget):
    bm = bmesh.new()
    squash = proto.get("squash", 0.8)
    try:
        bmesh.ops.create_uvsphere(bm, u_segments=8, v_segments=5, radius=1.0)
    except TypeError:
        bmesh.ops.create_uvsphere(bm, u_segments=8, v_segments=5, diameter=1.0)
    for v in bm.verts:
        n = (
            1.0
            + 0.14 * math.sin(3.1 * v.co.x + 1.2) * math.cos(2.6 * v.co.y - 0.6)
            + 0.04 * rng.uniform(-1, 1)
        )
        v.co = v.co.normalized() * n
        v.co.z *= squash
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    d = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(0.4, 1.0))).normalized()
    bm = _limited_chip(bm, d * 0.93, d, budget)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    return bm


def _fit(bm, dims, yaw):
    mat = Matrix.Rotation(yaw, 3, "Z")
    for v in bm.verts:
        v.co = mat @ v.co
    for axis in range(3):
        vals = [v.co[axis] for v in bm.verts]
        lo, hi = min(vals), max(vals)
        cur = hi - lo
        scale = dims[axis] / cur if cur > 1e-9 else 1.0
        center = (lo + hi) * 0.5
        for v in bm.verts:
            v.co[axis] = (v.co[axis] - center) * scale
    zmin = min(v.co.z for v in bm.verts)
    for v in bm.verts:
        v.co.z -= zmin
    return bm


def _uv_box(bm, tile_m):
    """盒式投影：每面按法线主导轴投影，UV 直接取真实米数 / tile_m，密度与尺寸无关。"""
    uv_layer = bm.loops.layers.uv.verify()
    inv = 1.0 / max(tile_m, 1e-6)
    plane_axes = ((1, 2), (0, 2), (0, 1))
    for f in bm.faces:
        n = f.normal
        axis = max(range(3), key=lambda i: abs(n[i]))
        a, b = plane_axes[axis]
        for loop in f.loops:
            co = loop.vert.co
            loop[uv_layer].uv = (co[a] * inv, co[b] * inv)
    return bm


def _shade_by_angle(bm, angle_deg):
    """所有面设平滑，面间夹角超过阈值的边标为锐边（自动平滑）。"""
    bm.normal_update()
    limit = math.radians(angle_deg)
    for f in bm.faces:
        f.smooth = True
    for e in bm.edges:
        if len(e.link_faces) == 2:
            e.smooth = e.calc_face_angle(0.0) <= limit
    return bm


def _material(spec):
    """共享材质：固有色 + 法线贴图，粗糙度/金属度走常量。"""
    conf = spec["material"]
    mat = bpy.data.materials.get(conf["name"])
    if mat is None:
        mat = bpy.data.materials.new(conf["name"])
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = conf["roughness"]
    bsdf.inputs["Metallic"].default_value = conf["metallic"]

    color = os.path.join(TEX_DIR, conf["albedo"])
    normal = os.path.join(TEX_DIR, conf["normal"])
    if os.path.exists(color) and not bsdf.inputs["Base Color"].is_linked:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.name = "Rock_Albedo"
        tex.image = bpy.data.images.load(color, check_existing=True)
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if os.path.exists(normal) and not bsdf.inputs["Normal"].is_linked:
        img = bpy.data.images.load(normal, check_existing=True)
        img.colorspace_settings.name = 'Non-Color'
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.name = "Rock_Normal"
        tex.image = img
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nmap.inputs["Strength"].default_value = conf.get("normal_strength", 1.0)
        nt.links.new(tex.outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def build(spec, name="Rock", collection=None, placement=None):
    """按 spec 生成全部原型石块，返回 (objects, report)。"""
    coll = collection or ensure_collection("Rocks")
    mat = _material(spec)
    max_tri = spec["budget"]["max_tri"]
    min_tri = spec["budget"]["min_tri"]
    lo_m = spec["bounds"]["min_m"]
    hi_m = spec["bounds"]["max_m"]
    embed_lo, embed_hi = spec["embed"]
    jitter = spec["jitter"]
    smooth_factor = spec["smooth_factor"]
    smooth_angle = spec["smooth_angle_deg"]
    slots = placement if placement is not None else spec.get("placement") or []
    base_seed = spec.get("seed", 0)

    objs = []
    report = {"seed": base_seed, "uv_tile_m": spec["uv_tile_m"], "rocks": [], "total_tri": 0}

    for index, proto in enumerate(spec["prototypes"]):
        seed = (base_seed + proto.get("seed", index)) & 0x7FFFFFFF
        rng = random.Random(seed)
        yaw = rng.uniform(0, math.tau)
        if proto.get("form") == "rounded":
            bm = _gen_rounded(rng, proto, max_tri)
        else:
            bm = _gen_angular(rng, proto, max_tri, jitter, smooth_factor)
        _fit(bm, proto["dims"], yaw)
        _uv_box(bm, spec["uv_tile_m"])
        _shade_by_angle(bm, smooth_angle)

        tris = _tri_total(bm)
        if tris > max_tri:
            bm.free()
            raise RuntimeError("%s 超出三角面预算：%d > %d" % (proto["id"], tris, max_tri))
        if tris < min_tri:
            bm.free()
            raise RuntimeError("%s 低于三角面下限：%d < %d" % (proto["id"], tris, min_tri))

        mesh_name = "%s_%s" % (name, proto["id"])
        me = bpy.data.meshes.new(mesh_name)
        bm.to_mesh(me)
        bm.free()

        widths = [
            max(v.co.x for v in me.vertices) - min(v.co.x for v in me.vertices),
            max(v.co.y for v in me.vertices) - min(v.co.y for v in me.vertices),
            max(v.co.z for v in me.vertices) - min(v.co.z for v in me.vertices),
        ]
        for w in widths:
            if w > hi_m + 1e-4 or w < lo_m - 1e-4:
                raise RuntimeError("%s 包围盒越界：%.3f m 不在 [%.2f, %.2f]" % (proto["id"], w, lo_m, hi_m))

        me.materials.append(mat)

        sx, sy = slots[index] if index < len(slots) else (0.0, 0.0)
        sink = rng.uniform(embed_lo, embed_hi) * widths[2]
        ob = bpy.data.objects.new(mesh_name, me)
        ob.location = (sx, sy, -sink)
        coll.objects.link(ob)
        objs.append(ob)

        report["rocks"].append(
            {
                "id": proto["id"],
                "tri": tris,
                "dims": [round(w, 3) for w in widths],
                "pos": [round(sx, 2), round(sy, 2)],
                "embed": round(sink, 3),
            }
        )
        report["total_tri"] += tris

    return objs, report


def spawn_variants(spec, count=7, spacing=0.75, x0=-2.1, y=-6.5):
    """把同一套原型按固定间距排成一排，方便逐个比对形态。"""
    slots = [(x0 + i * spacing, y) for i in range(count)]
    return build(spec, name="Rock", placement=slots)


def main(preset_path, name="Rock", collection_name=None, placement=None):
    """会话内入口：读 preset → 生成 → 打印 [ROCKGEN] 报告。"""
    spec = load_spec(preset_path)
    coll = ensure_collection(collection_name or name)
    objs, report = build(spec, name=name, collection=coll, placement=placement)
    report["objects"] = [o.name for o in objs]
    report["spec"] = {
        "seed": spec["seed"],
        "uv_tile_m": spec["uv_tile_m"],
        "smooth_angle_deg": spec["smooth_angle_deg"],
        "material": spec["material"]["name"],
        "prototypes": [p["id"] for p in spec["prototypes"]],
    }
    print("[ROCKGEN] " + json.dumps(report, ensure_ascii=False))
    return report
