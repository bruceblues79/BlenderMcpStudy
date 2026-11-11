"""崩积巨石程序化生成器。

纯 bpy / bmesh，无外部依赖，确定性：同一 spec 同一 seed 必得同一几何。

核心思路
--------
1. 斐波那契球面取点 + 半径扰动 → 凸包，作为"母岩"基底
2. 顶点抖动只作用在这一步（切口之前），切口之后不再动顶点
3. 断口按"目标切除体积比例"反解平面位置，保证每刀都是一整块大断面，
   而不是削掉一片薄皮（薄皮就是"挤出感"的来源）
4. 平面切割后取单边界的边做 holes_fill 封盖再三角化，断面严格共面
5. 归一化到目标包围盒 → 底面贴地 → 按 embed 沉入地表

语义层
------
prototype 可以只写 `form` + `bulk`，由 FORMS 表展开成尺寸与破损配置；
需要精确复刻时再写 `size` / `cuts` 覆盖。
"""

import json
import math
import os
import random

import bmesh
import bpy
from mathutils import Vector

# ---------------------------------------------------------------- 语义预设

# aspect: 高宽深相对比例（被 bulk 缩放）；fracture: 主断口数量；top: 默认平顶高度比
FORMS = {
    "slab": {"aspect": (1.00, 0.86, 0.42), "fracture": 1, "top": 0.88, "rough": 0.10},
    "block": {"aspect": (0.96, 0.88, 0.80), "fracture": 1, "top": None, "rough": 0.11},
    "column": {"aspect": (0.74, 0.68, 1.00), "fracture": 1, "top": None, "rough": 0.09},
    "wedge": {"aspect": (1.00, 0.82, 0.62), "fracture": 2, "top": None, "rough": 0.10},
    "shard": {"aspect": (0.86, 0.72, 0.66), "fracture": 2, "top": None, "rough": 0.11},
}

DEFAULTS = {
    "points": 30,
    "rough": 0.10,
    "jitter": 0.030,
    "top_tilt": (0.0, 0.0),
    "severity": 0.28,   # 主断口切除体积比例
    "chip": 0.09,       # 小崩角切除体积比例，0 表示不切
    "embed": 0.14,      # 沉入地表比例（按自身高度）
    "seed": 0,
}


# ---------------------------------------------------------------- 平面切割

def _measure_removed(bm, no, d):
    """法线正侧（dot > d）被切掉后损失的体积比例。"""
    tmp = bm.copy()
    v0 = abs(tmp.calc_volume(signed=True))
    bmesh.ops.bisect_plane(
        tmp, geom=tmp.verts[:] + tmp.edges[:] + tmp.faces[:], dist=1e-9,
        plane_co=no * d, plane_no=no, clear_outer=True, clear_inner=False,
    )
    border = [e for e in tmp.edges if len(e.link_faces) == 1]
    if border:
        bmesh.ops.holes_fill(tmp, edges=border, sides=0)
    v1 = abs(tmp.calc_volume(signed=True))
    tmp.free()
    return 1.0 - v1 / max(v0, 1e-9)


def _plane_for_fraction(bm, no, frac):
    """二分出平面偏移 d，使切掉的体积比例 = frac。

    注意：d 越大，切掉的越少（切除比例随 d 单调递减）。
    """
    vals = [v.co.dot(no) for v in bm.verts]
    lo, hi = min(vals), max(vals)
    for _ in range(18):
        mid = (lo + hi) * 0.5
        if _measure_removed(bm, no, mid) > frac:
            lo = mid
        else:
            hi = mid
    return (lo + hi) * 0.5


def _fill_caps(bm):
    border = [e for e in bm.edges if len(e.link_faces) == 1]
    if not border:
        return
    res = bmesh.ops.holes_fill(bm, edges=border, sides=0)
    bmesh.ops.triangulate(bm, faces=list(res["faces"]),
                          quad_method="BEAUTY", ngon_method="EAR_CLIP")


def cut_fraction(bm, direction, frac):
    """沿 direction 削掉 frac 比例的体量（一整块断面，不是薄皮）。"""
    no = Vector(direction).normalized()
    d = _plane_for_fraction(bm, no, frac)
    bmesh.ops.bisect_plane(
        bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-9,
        plane_co=no * d, plane_no=no, clear_outer=True, clear_inner=False,
    )
    _fill_caps(bm)
    return d


def cut_top(bm, tilt, ratio):
    """水平（可微倾）截顶，ratio 为保留高度比例。"""
    no = Vector((tilt[0], tilt[1], 1.0)).normalized()
    vals = [v.co.dot(no) for v in bm.verts]
    d = min(vals) + (max(vals) - min(vals)) * ratio
    bmesh.ops.bisect_plane(
        bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-9,
        plane_co=no * d, plane_no=no, clear_outer=True, clear_inner=False,
    )
    _fill_caps(bm)


# ---------------------------------------------------------------- 几何构建

def _bbox(bm):
    xs = [v.co.x for v in bm.verts]
    ys = [v.co.y for v in bm.verts]
    zs = [v.co.z for v in bm.verts]
    return Vector((min(xs), min(ys), min(zs))), Vector((max(xs), max(ys), max(zs)))


def _tri_n(bm):
    return sum(len(f.verts) - 2 for f in bm.faces)


def _hull(points, rough, rnd):
    """斐波那契球面取点 → 凸包。"""
    golden = math.pi * (3.0 - math.sqrt(5.0))
    bm = bmesh.new()
    for i in range(points):
        z = 1.0 - 2.0 * (i + 0.5) / points
        r = math.sqrt(max(0.0, 1.0 - z * z))
        th = golden * i + rnd.uniform(-0.18, 0.18)
        rad = 1.0 + rnd.uniform(-1.0, 1.0) * rough
        bm.verts.new(Vector((math.cos(th) * r, math.sin(th) * r, z)) * rad)
    bmesh.ops.convex_hull(bm, input=bm.verts[:], use_existing_faces=False)
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
    return bm


def _auto_cuts(rnd, count, severity, chip):
    """按语义生成断口方向：方位均匀打散 + 仰角随机。"""
    cuts = []
    base = rnd.uniform(0.0, 2.0 * math.pi)
    for i in range(max(0, count)):
        az = base + i * (2.0 * math.pi / max(1, count)) + rnd.uniform(-0.5, 0.5)
        el = rnd.uniform(-0.15, 0.55)
        cuts.append({
            "dir": [math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)],
            "frac": severity if i == 0 else severity * 0.55,
        })
    if chip:
        az = base + math.pi * 0.5 + rnd.uniform(-0.6, 0.6)
        el = rnd.uniform(-0.25, 0.25)
        cuts.append({
            "dir": [math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)],
            "frac": chip,
        })
    return cuts


def resolve(proto):
    """把语义字段展开成完整参数。"""
    p = dict(DEFAULTS)
    form = FORMS.get(proto.get("form"))
    if form:
        for k in ("rough",):
            p[k] = form[k]
    p.update({k: v for k, v in proto.items() if k != "form"})

    rnd = random.Random(p["seed"] * 7919 + 13)
    if "size" not in proto:
        bulk = float(proto.get("bulk", 1.2))
        aspect = form["aspect"] if form else (1.0, 0.87, 0.62)
        p["size"] = [bulk * a for a in aspect]
    if "top" not in proto and form:
        p["top"] = form["top"]
    if "cuts" not in proto:
        count = proto.get("fracture", form["fracture"] if form else 1)
        p["cuts"] = _auto_cuts(rnd, count, p["severity"], p["chip"])
    return p


def build_bm(p):
    """按参数建一块巨石的 bmesh，返回 (bm, 实际点数)。"""
    rnd = random.Random(p["seed"])
    points = int(p["points"])
    bm = _hull(points, p["rough"], rnd)

    # 抖动：只作用于基底，切口之后禁止再动顶点
    bm.normal_update()
    lo, hi = _bbox(bm)
    amp = (hi - lo).length * p["jitter"]
    for v in bm.verts:
        v.co += v.normal * (rnd.uniform(-1.0, 1.0) * amp)

    if p.get("top") is not None:
        cut_top(bm, p.get("top_tilt", (0.0, 0.0)), p["top"])
    for c in p["cuts"]:
        cut_fraction(bm, c["dir"], c["frac"])

    bmesh.ops.triangulate(bm, faces=bm.faces[:],
                          quad_method="BEAUTY", ngon_method="EAR_CLIP")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

    # 归一化到目标包围盒
    lo, hi = _bbox(bm)
    span = hi - lo
    target = p["size"]
    for v in bm.verts:
        v.co.x = (v.co.x - lo.x) * (target[0] / span.x)
        v.co.y = (v.co.y - lo.y) * (target[1] / span.y)
        v.co.z = (v.co.z - lo.z) * (target[2] / span.z)
    return bm, points


def build_one(p, budget=None):
    """建一块，自动调点数把面数收进 [min_tri, max_tri]。"""
    min_tri = budget["min_tri"] if budget else 0
    max_tri = budget["max_tri"] if budget else 10 ** 6
    tuned = dict(p)
    bm = None
    for _ in range(6):
        bm, _points = build_bm(tuned)
        tri = _tri_n(bm)
        if min_tri <= tri <= max_tri:
            return bm, tuned
        tuned["points"] = min(40, tuned["points"] + 4) if tri < min_tri \
            else max(16, tuned["points"] - 3)
        bm.free()
        bm = None
    raise RuntimeError("无法把 %s 的面数收进 [%d, %d]" % (p.get("id"), min_tri, max_tri))


# ---------------------------------------------------------------- 场景装配

def ensure_collection(name):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
    return col


def ensure_material(name, roughness=0.55, metallic=0.0):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF") if mat.use_nodes else None
    if bsdf:
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
    return mat


# ---------------------------------------------------------------- UV（盒式投影）

def uv_box_project(me, tile_m=0.5):
    """按面法线主导轴投影，UV 用真实米数除以 tile_m，无智能展开、无外部贴图。"""
    layer = me.uv_layers.get("UVMap") or me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        n = poly.normal
        ax = abs(n.x)
        ay = abs(n.y)
        az = abs(n.z)
        axis = 0 if (ax >= ay and ax >= az) else (1 if ay >= az else 2)
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            if axis == 0:
                u, v = co.y, co.z
            elif axis == 1:
                u, v = co.x, co.z
            else:
                u, v = co.x, co.y
            layer.data[li].uv = (u / tile_m, v / tile_m)
    return layer


# ---------------------------------------------------------------- 程序化材质

def _node(nt, kind, loc=(0, 0)):
    n = nt.nodes.new(kind)
    n.location = loc
    return n


def _ramp(nt, stops, loc=(0, 0)):
    n = _node(nt, "ShaderNodeValToRGB", loc)
    ramp = n.color_ramp
    ramp.interpolation = "LINEAR"
    while len(ramp.elements) > 1:
        ramp.elements.remove(ramp.elements[-1])
    ramp.elements[0].position = stops[0][0]
    ramp.elements[0].color = stops[0][1]
    for pos, col in stops[1:]:
        e = ramp.elements.new(pos)
        e.color = col
    return n


def _mix(nt, fac, a, b, loc=(0, 0), blend="MIX"):
    n = _node(nt, "ShaderNodeMix", loc)
    n.data_type = "RGBA"
    n.blend_type = blend
    if isinstance(fac, (int, float)):
        n.inputs[0].default_value = fac
    else:
        nt.links.new(fac, n.inputs[0])
    for socket, src in ((n.inputs[6], a), (n.inputs[7], b)):
        if isinstance(src, (tuple, list)):
            socket.default_value = tuple(src) + (1.0,) if len(src) == 3 else tuple(src)
        else:
            nt.links.new(src, socket)
    return n.outputs[2]


def _math(nt, op, a, b=None, loc=(0, 0), clamp=False):
    n = _node(nt, "ShaderNodeMath", loc)
    n.operation = op
    n.use_clamp = clamp
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    return n.outputs[0]


def _noise(nt, vec, size_m, unit, detail=6, rough=0.55, loc=(0, 0)):
    n = _node(nt, "ShaderNodeTexNoise", loc)
    n.inputs["Scale"].default_value = unit / size_m
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = rough
    nt.links.new(vec, n.inputs["Vector"])
    return n.outputs["Fac"]


def _voronoi(nt, vec, size_m, unit, loc=(0, 0), feature="F1", randomness=1.0):
    n = _node(nt, "ShaderNodeTexVoronoi", loc)
    n.feature = feature
    n.inputs["Scale"].default_value = unit / size_m
    n.inputs["Randomness"].default_value = randomness
    nt.links.new(vec, n.inputs["Vector"])
    return n


def build_material(recipe):
    """大块裸露花岗岩：裂痕网络 + 长石/云母矿粒 + 风化 + 常量粗糙度，全程序化。

    - 裂痕、大色斑、风化层走 Object 坐标（真实米，每块石头独一无二，不会像 UV 那样平铺）
    - 矿粒走 UV 坐标（细碎高频，平铺不明显）
    - 风化 = 土垢 + 垂直水痕 + 地衣斑 + 近地积尘，压掉"刚切开的白净感"
    - 法线只来自 Bump 节点，不读任何图片
    """
    name = recipe.get("name", "MAT_Boulder_Granite")
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    unit_uv = float(recipe.get("uv_tile_m", 0.5))
    col = recipe.get("colors", {})
    base = tuple(col.get("base", (0.300, 0.292, 0.278)))
    light = tuple(col.get("light", (0.430, 0.418, 0.398)))
    feldspar = tuple(col.get("feldspar", (0.580, 0.565, 0.530)))
    mica = tuple(col.get("mica", (0.045, 0.043, 0.042)))
    crack_col = tuple(col.get("crack", (0.075, 0.070, 0.064)))

    mottle = recipe.get("mottle", {})
    grain = recipe.get("grain", {})
    crack = recipe.get("crack", {})
    bump = recipe.get("bump", {})

    coord = _node(nt, "ShaderNodeTexCoord", (0, 0))
    uv_vec = coord.outputs["UV"]
    obj_vec = coord.outputs["Object"]

    # --- 大色斑：Object 坐标，真实米
    mottle_noise = _noise(nt, obj_vec, float(mottle.get("size_m", 0.45)), 1.0,
                          detail=int(mottle.get("detail", 5)), loc=(-1400, 220))
    mottle_fac = _ramp(nt, [(0.36, (0, 0, 0, 1)), (0.72, (1, 1, 1, 1))], (-1200, 220))
    nt.links.new(mottle_noise, mottle_fac.inputs[0])
    albedo = _mix(nt, mottle_fac.outputs[0], base, light, (-980, 240))

    # --- 矿粒：UV 坐标，毫米级
    feld = _voronoi(nt, uv_vec, float(grain.get("size_mm", 5.0)) / 1000.0, unit_uv,
                    (-1400, -60), "F1")
    feld_mask = _ramp(nt, [(0.0, (1, 1, 1, 1)),
                           (float(grain.get("feldspar", 0.26)), (0, 0, 0, 1))], (-1200, -60))
    nt.links.new(feld.outputs["Distance"], feld_mask.inputs[0])
    albedo = _mix(nt, feld_mask.outputs[0], albedo, feldspar, (-800, 220))

    mica_v = _voronoi(nt, uv_vec, float(grain.get("size_mm", 5.0)) / 1000.0 * 0.5, unit_uv,
                      (-1400, -290), "F1")
    mica_mask = _ramp(nt, [(0.0, (1, 1, 1, 1)),
                           (float(grain.get("mica", 0.09)), (0, 0, 0, 1))], (-1200, -290))
    nt.links.new(mica_v.outputs["Distance"], mica_mask.inputs[0])
    albedo = _mix(nt, mica_mask.outputs[0], albedo, mica, (-640, 220))

    # --- 风化：土垢 / 垂直水痕 / 地衣 / 近地积尘，全部 Object 坐标（真实米）
    weather = recipe.get("weather", {})
    if weather:
        grime = weather.get("grime", {})
        g_noise = _noise(nt, obj_vec, float(grime.get("size_m", 0.85)), 1.0,
                         detail=5, rough=0.55, loc=(-1400, 520))
        g_mask = _ramp(nt, [(float(grime.get("lo", 0.40)), (0, 0, 0, 1)),
                            (float(grime.get("hi", 0.68)), (1, 1, 1, 1))], (-1200, 520))
        nt.links.new(g_noise, g_mask.inputs[0])
        g_amt = _math(nt, "MULTIPLY", g_mask.outputs[0], float(grime.get("amount", 0.55)),
                      (-1000, 520), clamp=True)
        albedo = _mix(nt, g_amt, albedo,
                      tuple(grime.get("color", (0.185, 0.170, 0.140))), (-860, 520))

        streak = weather.get("streak", {})
        mp = _node(nt, "ShaderNodeMapping", (-1700, 780))
        mp.inputs["Scale"].default_value = (1.0, 1.0, 1.0 / float(streak.get("stretch", 7.0)))
        nt.links.new(obj_vec, mp.inputs["Vector"])
        s_noise = _noise(nt, mp.outputs["Vector"], float(streak.get("size_m", 0.30)), 1.0,
                         detail=4, rough=0.6, loc=(-1480, 780))
        s_mask = _ramp(nt, [(float(streak.get("lo", 0.42)), (0, 0, 0, 1)),
                            (float(streak.get("hi", 0.62)), (1, 1, 1, 1))], (-1280, 780))
        nt.links.new(s_noise, s_mask.inputs[0])
        s_amt = _math(nt, "MULTIPLY", s_mask.outputs[0], float(streak.get("amount", 0.38)),
                      (-1100, 780), clamp=True)
        albedo = _mix(nt, s_amt, albedo,
                      tuple(streak.get("color", (0.135, 0.125, 0.105))), (-700, 560))

        stain = weather.get("stain", {})
        if stain:
            st_v = _voronoi(nt, obj_vec, float(stain.get("size_m", 0.45)), 1.0,
                            (-1500, 1810), "F1")
            st_mask = _ramp(nt, [(0.0, (1, 1, 1, 1)),
                                 (float(stain.get("edge", 0.32)), (0, 0, 0, 1))], (-1300, 1810))
            nt.links.new(st_v.outputs["Distance"], st_mask.inputs[0])
            st_amt = _math(nt, "MULTIPLY", st_mask.outputs[0], float(stain.get("amount", 0.30)),
                           (-1100, 1810), clamp=True)
            albedo = _mix(nt, st_amt, albedo,
                          tuple(stain.get("color", (0.300, 0.190, 0.100))), (-620, 660))

        lichen = weather.get("lichen", {})
        l_v = _noise(nt, obj_vec, float(lichen.get("size_m", 0.10)), 1.0,
                     detail=6, rough=0.62, loc=(-1500, 1040))
        l_mask = _ramp(nt, [(float(lichen.get("lo", 0.56)), (0, 0, 0, 1)),
                            (float(lichen.get("hi", 0.64)), (1, 1, 1, 1))], (-1300, 1040))
        nt.links.new(l_v, l_mask.inputs[0])
        l_sp = _noise(nt, obj_vec, float(lichen.get("sparse_m", 0.40)), 1.0, detail=3,
                      loc=(-1500, 1240))
        l_spm = _ramp(nt, [(float(lichen.get("sparse_lo", 0.36)), (0, 0, 0, 1)),
                           (float(lichen.get("sparse_hi", 0.52)), (1, 1, 1, 1))], (-1300, 1240))
        nt.links.new(l_sp, l_spm.inputs[0])
        l_amt = _math(nt, "MULTIPLY", l_mask.outputs[0], l_spm.outputs[0], (-1100, 1100))
        l_amt = _math(nt, "MULTIPLY", l_amt, float(lichen.get("amount", 0.34)),
                      (-950, 1100), clamp=True)
        albedo = _mix(nt, l_amt, albedo,
                      tuple(lichen.get("color", (0.300, 0.325, 0.255))), (-540, 560))

        dirt = weather.get("dirt", {})
        sep = _node(nt, "ShaderNodeSeparateXYZ", (-1700, 1480))
        nt.links.new(coord.outputs["Generated"], sep.inputs["Vector"])
        mr = _node(nt, "ShaderNodeMapRange", (-1500, 1480))
        mr.inputs["From Min"].default_value = 0.0
        mr.inputs["From Max"].default_value = float(dirt.get("height", 0.34))
        mr.inputs["To Min"].default_value = 1.0
        mr.inputs["To Max"].default_value = 0.0
        mr.clamp = True
        nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
        d_amt = _math(nt, "MULTIPLY", mr.outputs[0], float(dirt.get("amount", 0.65)),
                      (-1250, 1480), clamp=True)
        albedo = _mix(nt, d_amt, albedo,
                      tuple(dirt.get("color", (0.115, 0.100, 0.078))), (-400, 600))

    # --- 裂痕：Object 坐标两级 Voronoi 到边距离；再用噪声打断，避免规则网格感
    break_noise = _noise(nt, obj_vec, float(crack.get("break_m", 0.55)), 1.0,
                         detail=3, rough=0.5, loc=(-1400, -520))
    break_mask = _ramp(nt, [(float(crack.get("break_lo", 0.34)), (0, 0, 0, 1)),
                            (float(crack.get("break_hi", 0.58)), (1, 1, 1, 1))], (-1200, -520))
    nt.links.new(break_noise, break_mask.inputs[0])

    width = float(crack.get("width", 0.014))
    major = _voronoi(nt, obj_vec, float(crack.get("major_m", 1.15)), 1.0,
                     (-1400, -720), "DISTANCE_TO_EDGE", 1.0)
    major_mask = _ramp(nt, [(0.0, (1, 1, 1, 1)), (width, (0, 0, 0, 1))], (-1200, -720))
    nt.links.new(major.outputs["Distance"], major_mask.inputs[0])

    minor = _voronoi(nt, obj_vec, float(crack.get("minor_m", 0.38)), 1.0,
                     (-1400, -950), "DISTANCE_TO_EDGE", 1.0)
    minor_mask = _ramp(nt, [(0.0, (1, 1, 1, 1)), (width * 0.55, (0, 0, 0, 1))], (-1200, -950))
    nt.links.new(minor.outputs["Distance"], minor_mask.inputs[0])

    major_dark = _math(nt, "MULTIPLY", major_mask.outputs[0], float(crack.get("depth", 0.55)),
                       (-980, -720), clamp=True)
    minor_dark = _math(nt, "MULTIPLY", minor_mask.outputs[0], float(crack.get("minor_depth", 0.30)),
                       (-980, -950), clamp=True)
    crack_raw = _math(nt, "MAXIMUM", major_dark, minor_dark, (-820, -800))
    crack_amt = _math(nt, "MULTIPLY", crack_raw, break_mask.outputs[0], (-660, -800), clamp=True)

    albedo = _mix(nt, crack_amt, albedo, crack_col, (-480, 220))

    # --- 法线：矿粒微起伏 + 起伏面 - 裂痕凹陷
    micro = _noise(nt, uv_vec, float(grain.get("size_mm", 5.0)) / 1000.0, unit_uv,
                   detail=8, rough=0.62, loc=(-1400, -1180))
    coarse = _noise(nt, obj_vec, float(bump.get("coarse_m", 0.045)), 1.0,
                    detail=4, rough=0.5, loc=(-1400, -1400))
    h_micro = _math(nt, "MULTIPLY", micro, float(bump.get("grain", 0.45)), (-1200, -1180))
    h_coarse = _math(nt, "MULTIPLY", coarse, float(bump.get("coarse", 0.55)), (-1200, -1400))
    height = _math(nt, "ADD", h_micro, h_coarse, (-1050, -1290))
    crack_h = _math(nt, "MULTIPLY", crack_amt, float(bump.get("crack", 1.6)), (-1000, -800))
    height = _math(nt, "SUBTRACT", height, crack_h, (-900, -1240))
    bump_node = _node(nt, "ShaderNodeBump", (-760, -700))
    bump_node.inputs["Strength"].default_value = float(bump.get("strength", 0.85))
    bump_node.inputs["Distance"].default_value = float(bump.get("distance_m", 0.0018))
    nt.links.new(height, bump_node.inputs["Height"])

    bsdf = _node(nt, "ShaderNodeBsdfPrincipled", (-300, 220))
    bsdf.inputs["Roughness"].default_value = float(recipe.get("roughness", 0.62))
    bsdf.inputs["Metallic"].default_value = float(recipe.get("metallic", 0.0))
    bsdf.inputs["Specular IOR Level"].default_value = float(recipe.get("specular", 0.5))
    nt.links.new(albedo, bsdf.inputs["Base Color"])
    nt.links.new(bump_node.outputs["Normal"], bsdf.inputs["Normal"])

    out = _node(nt, "ShaderNodeOutputMaterial", (40, 220))
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def material_for(recipe):
    if not recipe:
        return ensure_material("MAT_Boulder_White")
    if recipe.get("kind"):
        return build_material(recipe)
    return ensure_material(**recipe)


def build(spec, collection="Boulders_Prototype", material=None):
    """生成 spec 里全部 prototype，摆在原点，返回 (objects, report)。"""
    col = ensure_collection(collection)
    mat = material_for(material)
    tile = float((material or {}).get("uv_tile_m", 0.5))
    budget = spec.get("budget")
    objs, rows = [], []

    for proto in spec["prototypes"]:
        p = resolve(proto)
        bm, tuned = build_one(p, budget)
        me = bpy.data.meshes.new("M_" + proto["id"])
        bm.to_mesh(me)
        bm.free()
        for poly in me.polygons:
            poly.use_smooth = False          # 平直着色，保留硬棱
        uv_box_project(me, tile)
        me.materials.append(mat)
        ob = bpy.data.objects.new("Boulder_" + proto["id"], me)
        col.objects.link(ob)
        ob.location = (0.0, 0.0, -p["size"][2] * p["embed"])
        objs.append(ob)
        rows.append({
            "id": proto["id"],
            "form": proto.get("form"),
            "tri": sum(len(poly.vertices) - 2 for poly in me.polygons),
            "dims": [round(v, 2) for v in p["size"]],
            "embed": round(p["embed"], 3),
            "points": tuned["points"],
            "seed": p["seed"],
        })
    return objs, rows


def layout_row(objs, gap=0.62, axis="x"):
    """沿 axis 排开，块间留固定净空；坐标按世界包围盒递推。"""
    bpy.context.view_layer.update()
    cursor = 0.0
    for ob in objs:
        corners = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
        width = max(c.x for c in corners) - min(c.x for c in corners)
        depth = max(c.y for c in corners) - min(c.y for c in corners)
        min_x = min(c.x for c in corners)
        min_y = min(c.y for c in corners)
        if axis == "x":
            ob.location.x += cursor - min_x
            ob.location.y += -min_y
            cursor += width + gap
        else:
            ob.location.y += cursor - min_y
            ob.location.x += -min_x
            cursor += depth + gap
    bpy.context.view_layer.update()
    return cursor - gap if objs else 0.0


def world_bounds(objs):
    out = []
    for ob in objs:
        pts = [ob.matrix_world @ v.co for v in ob.data.vertices]
        out.append({
            "id": ob.name,
            "x": [round(min(p.x for p in pts), 2), round(max(p.x for p in pts), 2)],
            "y": [round(min(p.y for p in pts), 2), round(max(p.y for p in pts), 2)],
            "top": round(max(p.z for p in pts), 2),
        })
    return out


def overlaps(objs, eps=1e-4):
    """两两 AABB 相交检查，返回冲突对。"""
    rows = world_bounds(objs)
    bad = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a, b = rows[i], rows[j]
            if (a["x"][0] < b["x"][1] - eps and b["x"][0] < a["x"][1] - eps and
                    a["y"][0] < b["y"][1] - eps and b["y"][0] < a["y"][1] - eps):
                bad.append([a["id"], b["id"]])
    return bad


def load_spec(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main(preset_path, collection="Boulders_Prototype", gap=None, save_blend=None):
    spec = load_spec(preset_path)
    objs, rows = build(spec, collection, spec.get("material"))
    gap = gap if gap is not None else spec.get("layout", {}).get("gap_m", 0.62)
    layout_row(objs, gap, spec.get("layout", {}).get("axis", "x"))
    bad = overlaps(objs)
    report = {
        "preset": os.path.basename(preset_path),
        "gap_m": gap,
        "boulders": rows,
        "total_tri": sum(r["tri"] for r in rows),
        "overlap": bad,
        "bounds": world_bounds(objs),
    }
    if bad:
        raise RuntimeError("巨石包围盒相交: %s" % bad)
    print("[BOULDERGEN]", json.dumps(report, ensure_ascii=False))
    if save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=save_blend, copy=True, compress=True)
    return report
