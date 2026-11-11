"""TREEGEN — 确定性程序化树木生成器（Blender 为媒介）。

输入：preset JSON（spec）
输出：Trunk / Branches / Twigs / Leaves 四个 mesh 对象，全部三角面

所有随机性只来自 spec["seed"]，同 spec 同 seed 必然同结果。
"""

import json
import math
import os
import random

import bpy
from mathutils import Matrix, Vector

TAU = math.pi * 2.0
TEX_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "assets", "textures")

# 叶原型：N 为轮廓边界点数，三角面数 = N - 2；lobes 为叶缘分裂数
LEAF_PROTOTYPES = {
    "P01": {"n": 4, "length": 0.13, "width": 0.062, "lobes": 1},
    "P02": {"n": 6, "length": 0.15, "width": 0.075, "lobes": 1},
    "P03": {"n": 8, "length": 0.18, "width": 0.062, "lobes": 1},
    "P04": {"n": 10, "length": 0.17, "width": 0.085, "lobes": 2},
    "P05": {"n": 12, "length": 0.19, "width": 0.100, "lobes": 3},
    "T3": {"n": 3, "length": 0.14, "width": 0.075, "lobes": 1},
    "C5": {"n": 5, "length": 0.22, "width": 0.100, "lobes": 2},
    "C7": {"n": 7, "length": 0.20, "width": 0.095, "lobes": 2},
}


def load_spec(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _basis(direction, roll=0.0):
    d = direction.normalized()
    up = Vector((0.0, 0.0, 1.0))
    if abs(d.dot(up)) > 0.95:
        up = Vector((1.0, 0.0, 0.0))
    u = d.cross(up).normalized()
    v = d.cross(u).normalized()
    if roll:
        rot = Matrix.Rotation(roll, 3, d)
        u = rot @ u
        v = rot @ v
    return u, v


def _tube(verts, faces, uvs, p0, p1, r0, r1, sides, v0=0.0, v1=1.0, roll=0.0,
          uv_scale=1.0):
    if r0 <= 1e-5 or r1 <= 1e-5:
        return
    u, v = _basis(p1 - p0, roll)
    base = len(verts)
    v0 *= uv_scale
    v1 *= uv_scale
    for i in range(sides):
        a = TAU * i / sides
        verts.append(p0 + (u * math.cos(a) + v * math.sin(a)) * r0)
    for i in range(sides):
        a = TAU * i / sides
        verts.append(p1 + (u * math.cos(a) + v * math.sin(a)) * r1)
    # 树皮 UV：U 为环向弧长、V 为沿管长度，乘以 uv_scale 归一贴图尺寸
    us0 = [TAU * r0 * i / sides * uv_scale for i in range(sides)] + [TAU * r0 * uv_scale]
    us1 = [TAU * r1 * i / sides * uv_scale for i in range(sides)] + [TAU * r1 * uv_scale]
    for i in range(sides):
        j = (i + 1) % sides
        faces.append((base + i, base + j, base + sides + j))
        uvs.extend([(us0[i], v0), (us0[i + 1], v0), (us1[i + 1], v1)])
        faces.append((base + i, base + sides + j, base + sides + i))
        uvs.extend([(us0[i], v0), (us1[i + 1], v1), (us1[i], v1)])
    # 端口封口
    top = base + sides
    for i in range(1, sides - 1):
        faces.append((top, top + i, top + i + 1))
        uvs.extend([(us1[0], v1), (us1[i], v1), (us1[i + 1], v1)])


def _trunk_spine(spec, rng):
    tr = spec["trunk"]
    seg = tr["segments"]
    height = spec["height_m"]
    lean_dir = rng.uniform(0.0, TAU)
    phase = rng.uniform(0.0, TAU)
    lean = math.radians(tr["lean_deg"]) * height
    bend = tr["bend"] * 0.10 * height
    spine = []
    for i in range(seg + 1):
        t = i / seg
        drift = lean * (t ** 2.2)
        wob = bend * math.sin(t * math.pi * 1.6 + phase) * t
        x = math.cos(lean_dir) * drift + math.cos(lean_dir + 1.4) * wob
        y = math.sin(lean_dir) * drift + math.sin(lean_dir + 1.4) * wob
        radius = tr["base_radius"] * (1.0 - t) ** 0.9 + tr["top_radius"]
        spine.append((Vector((x, y, height * t)), radius))
    return spine


def _trunk_mesh(spine, origin, sides, uv_scale=1.0):
    """连续环次主干：一条管，无段间接缝。"""
    pts = [origin + p for p, _ in spine]
    radii = [r for _, r in spine]
    tangents = []
    for i in range(len(pts)):
        if i == 0:
            t = pts[1] - pts[0]
        elif i == len(pts) - 1:
            t = pts[-1] - pts[-2]
        else:
            t = pts[i + 1] - pts[i - 1]
        tangents.append(t.normalized())
    u = _basis(tangents[0])[0]
    rings = []
    for i, tangent in enumerate(tangents):
        if i > 0:
            axis = tangents[i - 1].cross(tangent)
            if axis.length > 1e-6:
                angle = tangents[i - 1].angle(tangent)
                u = (Matrix.Rotation(angle, 3, axis.normalized()) @ u).normalized()
        v = tangent.cross(u).normalized()
        ring = []
        for k in range(sides):
            a = TAU * k / sides
            ring.append(pts[i] + (u * math.cos(a) + v * math.sin(a)) * radii[i])
        rings.append(ring)

    # 树皮 UV：V 为沿主干累计长度，U 为各环实际周长的弧长，统一乘 uv_scale
    vs = [0.0]
    for i in range(1, len(pts)):
        vs.append(vs[-1] + (pts[i] - pts[i - 1]).length)
    vs = [v * uv_scale for v in vs]
    us = [[TAU * r * k / sides * uv_scale for k in range(sides)] + [TAU * r * uv_scale]
          for r in radii]

    verts, faces, uvs = [], [], []
    for ring in rings:
        verts.extend(ring)
    for i in range(len(rings) - 1):
        b0 = i * sides
        b1 = (i + 1) * sides
        u0, u1 = us[i], us[i + 1]
        v0, v1 = vs[i], vs[i + 1]
        for k in range(sides):
            j = (k + 1) % sides
            faces.append((b0 + k, b0 + j, b1 + j))
            uvs.extend([(u0[k], v0), (u0[k + 1], v0), (u1[k + 1], v1)])
            faces.append((b0 + k, b1 + j, b1 + k))
            uvs.extend([(u0[k], v0), (u1[k + 1], v1), (u1[k], v1)])
    top = (len(rings) - 1) * sides
    for k in range(1, sides - 1):
        faces.append((top, top + k, top + k + 1))
        uvs.extend([(us[-1][0], vs[-1]), (us[-1][k], vs[-1]), (us[-1][k + 1], vs[-1])])
    for k in range(1, sides - 1):
        faces.append((0, k + 1, k))
        uvs.extend([(us[0][0], vs[0]), (us[0][k + 1], vs[0]), (us[0][k], vs[0])])
    return verts, faces, uvs


def _grow_branch(start, base_dir, length, radius, sides, segments, rng, curl=0.0,
                 tip_droop=0.0, uv_scale=1.0):
    """从 start 沿 base_dir 生长，返回 (verts, faces, uvs, points)。"""
    verts, faces, uvs, pts = [], [], [], []
    pos = start.copy()
    direction = base_dir.normalized()
    roll = rng.uniform(0, TAU)  # 整根枝共用相位，保证分段间 UV 不错位
    v_acc = 0.0
    pts.append(pos.copy())
    for i in range(segments):
        t0 = i / segments
        step = length / segments
        # 中段向上抬，随 t 平滑转入重力下垂（旋转而非矢量叠加，避免接缝折角）
        curl_step = curl * (0.35 - t0)
        axis = direction.cross(Vector((0.0, 0.0, 1.0)))
        if axis.length < 1e-4:
            axis = Vector((1.0, 0.0, 0.0))
        axis = axis.normalized()
        direction = (Matrix.Rotation(curl_step, 3, axis) @ direction).normalized()
        if tip_droop > 0.0:
            bend = tip_droop * 1.05 * (t0 ** 1.2) / max(1, segments)
            direction = (Matrix.Rotation(-bend, 3, axis) @ direction).normalized()
        r0 = radius * (1.0 - t0) ** 0.85 + 0.0035
        r1 = radius * (1.0 - (t0 + 1.0 / segments)) ** 0.85 + 0.0035
        nxt = pos + direction * step
        rng.uniform(0, TAU)  # 保留原有随机消耗次数，避免改变下游叶片分布
        _tube(verts, faces, uvs, pos, nxt, r0, r1, sides,
              v0=v_acc, v1=v_acc + (nxt - pos).length, roll=roll, uv_scale=uv_scale)
        v_acc += (nxt - pos).length
        pos = nxt
        pts.append(pos.copy())
    return verts, faces, uvs, pts


def _twig_card(verts, faces, uvs, start, direction, length, width, rng, uv_scale=1.0):
    d = direction.normalized()
    side = d.cross(Vector((0.0, 0.0, 1.0)))
    if side.length < 1e-4:
        side = Vector((1.0, 0.0, 0.0))
    side = (Matrix.Rotation(rng.uniform(-0.5, 0.5), 3, d) @ side.normalized()).normalized()
    tip = start + d * length
    a = start - side * width * 0.5
    b = start + side * width * 0.5
    c = tip + side * width * 0.18
    e = tip - side * width * 0.18
    i = len(verts)
    verts.extend([a, b, c, e])
    faces.append((i, i + 1, i + 2))
    faces.append((i, i + 2, i + 3))
    # 细枝 UV：与树皮同密度，U 跨宽度、V 沿长度；按 loop 顺序写入
    v_end = length * uv_scale
    uw = width * uv_scale
    uv_a = (0.0, 0.0)
    uv_b = (uw, 0.0)
    uv_c = (uw * 0.82, v_end)
    uv_e = (uw * 0.18, v_end)
    uvs.extend([uv_a, uv_b, uv_c, uv_a, uv_c, uv_e])
    return tip


def _leaf_outline(proto_key, scale, single_tri=False):
    proto = LEAF_PROTOTYPES[proto_key]
    n = proto["n"]
    length = proto["length"] * scale
    width = proto["width"] * scale
    lobes = proto["lobes"]
    if single_tri or n == 3:
        # 单三角叶片：叶柄、左肩、右侧偏上的叶尖，略带偏斜避免机械感
        pts = [Vector((0.0, 0.0, 0.0)),
               Vector((-width * 0.60, length * 0.45, 0.0)),
               Vector((width * 0.60, length * 0.90, 0.0))]
        uvs = [(0.5, 0.0), (0.0, 0.45), (1.0, 0.90)]
        return pts, [(0, 1, 2)], uvs, 1
    side_count = (n - 2) // 2
    pts = [Vector((0.0, 0.0, 0.0))]

    def half(u, sign):
        w = width * (math.sin(math.pi * u) ** 0.65)
        if lobes > 1:
            w *= 0.72 + 0.28 * abs(math.cos(math.pi * lobes * u))
        return Vector((sign * w, length * u, 0.0))

    for i in range(side_count):
        u = (i + 1) / (side_count + 1)
        pts.append(half(u, -1.0))
    pts.append(Vector((0.0, length, 0.0)))
    for i in range(side_count - 1, -1, -1):
        u = (i + 1) / (side_count + 1)
        pts.append(half(u, 1.0))
    faces = [(0, 2 + i, 1 + i) for i in range(len(pts) - 2)]
    # 叶片 UV：所有原型共用一张 0–1 叶面图，U 按半宽归一、V 沿叶轴
    uvs = [(0.5 + 0.5 * p.x / width, p.y / length) for p in pts]
    return pts, faces, uvs, n - 2


def _place_leaf(verts, faces, uvs, anchor, out_dir, proto_key, scale, droop, rng,
                single_tri=False):
    pts, faces_local, pt_uvs, _ = _leaf_outline(proto_key, scale, single_tri)
    if not pts:
        return 0

    o = out_dir.normalized()
    azim = rng.uniform(-1.15, 1.15)
    flat = Matrix.Rotation(azim, 3, Vector((0.0, 0.0, 1.0))) @ Vector((o.x, o.y, 0.0))
    o = Vector((flat.x, flat.y, -droop * (0.55 + 0.45 * rng.random())))
    if o.length < 1e-5:
        o = Vector((0.0, 1.0, -0.3))
    o.normalize()
    side = o.cross(Vector((0.0, 0.0, 1.0)))
    if side.length < 1e-4:
        side = Vector((1.0, 0.0, 0.0))
    side.normalize()
    normal = side.cross(o).normalized()
    if normal.z > 0.45:
        normal = -normal
        side = -side
    rot = Matrix.Rotation(rng.uniform(-0.45, 0.45), 3, normal)
    o2 = rot @ o
    side2 = rot @ side
    roll = Matrix.Rotation(rng.uniform(-0.45, 0.45), 3, o2)
    side2 = (roll @ side2).normalized()
    if side2.cross(o2).z > 0.25:
        side2 = -side2

    base = len(verts)
    for p in pts:
        verts.append(anchor + o2 * p.y + side2 * p.x)
    for f in faces_local:
        faces.append((base + f[0], base + f[1], base + f[2]))
        uvs.extend([pt_uvs[f[0]], pt_uvs[f[1]], pt_uvs[f[2]]])
    return len(faces_local)


def _attach_points(spec, branch_pts, twig_pts, rng, l1_count=0):
    """收集叶片挂载点：只挂次级枝与细枝，主干与一级枝根部不放叶。"""
    leaves = spec["leaf"]
    attach = leaves["attach"]
    min_u_l1 = leaves.get("min_u_l1", 0.5)
    min_u_l2 = leaves.get("min_u_l2", 0.25)
    points = []
    for pts, per in ((branch_pts, attach["branch"]), (twig_pts, attach["twig"])):
        for ci, chain in enumerate(pts):
            if len(chain) < 2:
                continue
            lo = 0.0
            if pts is branch_pts:
                lo = min_u_l1 if ci < l1_count else min_u_l2
            for k in range(per):
                # 起始段留空（主干/一级枝根部无叶），其余沿枝略带相位抖动，避免等距死板
                u = lo + (k + rng.uniform(0.15, 0.85)) / per * (1.0 - lo)
                idx = min(len(chain) - 2, int(u * (len(chain) - 1)))
                frac = u * (len(chain) - 1) - idx
                pos = chain[idx].lerp(chain[idx + 1], frac)
                out = (chain[idx + 1] - chain[idx])
                if out.length < 1e-5:
                    continue
                out = Vector((out.x, out.y, out.z * 0.25)).normalized()
                points.append((pos, out, idx == len(chain) - 2))
    rng.shuffle(points)
    return points


def _new_object(name, verts, faces, uvs, collection, material):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in verts], [], faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(material)
    layer = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        for li in poly.loop_indices:
            layer.data[li].uv = uvs[li]
    collection.objects.link(obj)
    return obj


def build(spec, name="Tree_Birch", origin=(0.0, 0.0, 0.0), collection=None):
    rng = random.Random(spec["seed"])
    if collection is None:
        collection = bpy.context.scene.collection
    mat_bark, mat_leaf = _ensure_materials()

    origin_v = Vector(origin)
    spine = _trunk_spine(spec, rng)
    tr = spec["trunk"]
    gravity = spec.get("droop", 1.0)
    # 树皮 UV 归一：主干基部的环向周长正好占满贴图 U 0–1，枝干沿用同一密度（可重叠）
    bark_uv = 1.0 / (TAU * (tr["base_radius"] + tr["top_radius"]))

    trunk_v, trunk_f, trunk_uv = _trunk_mesh(spine, origin_v, tr["sides"], bark_uv)

    branch_v, branch_f, branch_uv = [], [], []
    branch_chains = []
    branch_spec = spec["branch"]
    l1 = branch_spec["level1"]
    l2 = branch_spec["level2"]
    golden = math.radians(137.5)

    def sample_spine(t):
        raw = t * (len(spine) - 1)
        idx = min(len(spine) - 2, int(raw))
        frac = raw - idx
        p = spine[idx][0].lerp(spine[idx + 1][0], frac)
        r = spine[idx][1] * (1 - frac) + spine[idx + 1][1] * frac
        return p, r

    for i in range(l1["count"]):
        t = branch_spec["start"] + (branch_spec["end"] - branch_spec["start"]) * (i + 0.5) / l1["count"]
        t += rng.uniform(-0.02, 0.02)
        anchor, trunk_r = sample_spine(t)
        azim = golden * i + rng.uniform(-0.25, 0.25)
        pitch = math.radians(rng.uniform(*l1["pitch_deg"]))
        outward = Vector((math.cos(azim), math.sin(azim), 0.0))
        direction = (outward * math.cos(pitch) + Vector((0, 0, math.sin(pitch)))).normalized()
        length = spec["height_m"] * l1["len_ratio"] * (1.12 - 0.55 * t)
        radius = max(0.004, trunk_r * l1["radius_ratio"])
        bv, bf, buv, pts = _grow_branch(origin_v + anchor, direction, length, radius,
                                        l1["sides"], l1["segments"], rng, curl=0.55,
                                        tip_droop=gravity * 0.6, uv_scale=bark_uv)
        off = len(branch_v)
        branch_v.extend(bv)
        branch_f.extend(tuple(i + off for i in f) for f in bf)
        branch_uv.extend(buv)
        branch_chains.append(pts)

        for k in range(l2["per_parent"]):
            u = l2["at"][0] + (l2["at"][1] - l2["at"][0]) * (k + 0.5) / l2["per_parent"]
            idx = min(len(pts) - 2, int(u * (len(pts) - 1)))
            start = pts[idx]
            seg_dir = (pts[idx + 1] - pts[idx]).normalized()
            twist = Vector((seg_dir.x, seg_dir.y, 0.0))
            if twist.length < 1e-4:
                twist = outward
            twist.normalize()
            twist = (Matrix.Rotation(rng.uniform(0.5, 1.4) * rng.choice((-1, 1)), 3,
                                     Vector((0, 0, 1))) @ twist)
            p2 = math.radians(rng.uniform(*l2["pitch_deg"]))
            d2 = (twist * math.cos(p2) + Vector((0, 0, math.sin(p2)))).normalized()
            l2_len = length * l2["len_ratio"] * rng.uniform(0.8, 1.15)
            sv, sf, suv, spts = _grow_branch(start, d2, l2_len, max(0.0035, radius * l2["radius_ratio"]),
                                             l2["sides"], l2["segments"], rng, curl=0.45,
                                             tip_droop=gravity * 0.9, uv_scale=bark_uv)
            off = len(branch_v)
            branch_v.extend(sv)
            branch_f.extend(tuple(i + off for i in f) for f in sf)
            branch_uv.extend(suv)
            branch_chains.append(spts)

    # 细枝：双面材质的面片，同时作为叶片挂点
    twig_v, twig_f, twig_uv = [], [], []
    twig_chains = []
    tw = spec["twig"]
    for chain in branch_chains:
        if len(chain) < 2:
            continue
        tip = chain[-1]
        direction = (chain[-1] - chain[-2]).normalized()
        for _ in range(tw["per_tip"]):
            d = (Matrix.Rotation(rng.uniform(-0.9, 0.9), 3, Vector((0, 0, 1))) @ direction)
            d = Vector((d.x, d.y, d.z - gravity * 0.55)).normalized()
            end = _twig_card(twig_v, twig_f, twig_uv, tip, d, tw["len"] * rng.uniform(0.7, 1.2),
                             tw["width"], rng, bark_uv)
            twig_chains.append([tip.copy(), end.copy()])

    attach = _attach_points(spec, branch_chains, twig_chains, rng, l1_count=l1["count"])

    leaf_v, leaf_f, leaf_uv = [], [], []
    leaf = spec["leaf"]
    proto_cycle = list(leaf["prototypes"])
    season_factor = spec["season"]["leaf_factor"]
    target_tri = int(spec["budget"]["leaf_max_tri"] * spec["canopy"] * season_factor)
    per_cluster = max(1, int(leaf["per_cluster"]))
    single_tri = bool(leaf.get("single_tri", True))
    min_gap = leaf["cluster_spread"] * 1.7  # 叶簇最小间距，避免局部扎堆
    ci = 0
    leaf_total = 0
    placed = []
    for pos, out, is_tip in attach:
        proto = proto_cycle[ci % len(proto_cycle)]
        cluster_tri = (1 if single_tri else LEAF_PROTOTYPES[proto]["n"] - 2) * per_cluster
        if len(leaf_f) + cluster_tri > target_tri:
            break
        # 与前序叶簇过近时沿背离方向推开，保持数量不变只错开位置
        p = pos.copy()
        for q in placed:
            d = p - q
            if d.length < min_gap:
                if d.length < 1e-4:
                    d = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1),
                                rng.uniform(-0.3, 0.3)))
                p = q + d.normalized() * min_gap
        placed.append(p)
        for _ in range(per_cluster):
            jitter = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
            jitter *= leaf["cluster_spread"] * rng.random()
            droop = gravity * (1.25 if is_tip else 1.0)
            _place_leaf(leaf_v, leaf_f, leaf_uv, p + jitter, out, proto,
                        leaf["scale"] * rng.uniform(0.85, 1.15), droop, rng, single_tri)
            leaf_total += 1
        ci += 1

    objs = {
        "trunk": _new_object(f"{name}_Trunk", trunk_v, trunk_f, trunk_uv, collection, mat_bark),
        "branches": _new_object(f"{name}_Branches", branch_v, branch_f, branch_uv, collection, mat_bark),
        "twigs": _new_object(f"{name}_Twigs", twig_v, twig_f, twig_uv, collection, mat_bark),
        "leaves": _new_object(f"{name}_Leaves", leaf_v, leaf_f, leaf_uv, collection, mat_leaf),
    }
    report = {
        "trunk_tri": len(trunk_f),
        "branch_tri": len(branch_f),
        "twig_tri": len(twig_f),
        "leaf_tri": len(leaf_f),
        "leaf_count": leaf_total,
        "branch_budget": spec["budget"]["branch_max_tri"],
        "leaf_budget": target_tri,
    }
    if report["branch_tri"] > spec["budget"]["branch_max_tri"]:
        raise RuntimeError(
            f"枝干面数 {report['branch_tri']} 超出预算 {spec['budget']['branch_max_tri']}；"
            f"降低 branch.level1.count 或 branch.level2.per_parent"
        )
    return objs, report


def _new_material(name, roughness, stem):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nt = mat.node_tree
        bsdf = nt.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.8, 0.8, 0.8, 1.0)
            bsdf.inputs["Roughness"].default_value = roughness
            bsdf.inputs["Metallic"].default_value = 0.0
            color = os.path.join(TEX_DIR, "birch_%s_color.png" % stem)
            normal = os.path.join(TEX_DIR, "birch_%s_normal.png" % stem)
            if os.path.exists(color):
                tex = nt.nodes.new("ShaderNodeTexImage")
                tex.image = bpy.data.images.load(color, check_existing=True)
                nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
            if os.path.exists(normal):
                ntex = nt.nodes.new("ShaderNodeTexImage")
                img = bpy.data.images.load(normal, check_existing=True)
                img.colorspace_settings.name = 'Non-Color'
                ntex.image = img
                nmap = nt.nodes.new("ShaderNodeNormalMap")
                nt.links.new(ntex.outputs["Color"], nmap.inputs["Color"])
                nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _ensure_materials():
    """树皮与叶片两套材质：贴图由 gen_tex.py 生成，粗糙度走常数。"""
    return (_new_material("MAT_Birch_Bark", 0.9, "bark"),
            _new_material("MAT_Birch_Leaf", 0.6, "leaf"))


def ensure_collection(name):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def spawn_variants(spec, count=5, spacing=2.2, x0=0.0, name_prefix="Birch_V"):
    """同一 preset 派生 N 棵不同树：seed 派生 + 轻量形态抖动。"""
    var = spec.get("variation", {})
    stride = var.get("seed_stride", 977)
    height_jitter = var.get("height", 0.0)
    branch_jitter = var.get("branch_count", 0)
    results = []
    for i in range(count):
        s = json.loads(json.dumps(spec))
        s["seed"] = spec["seed"] + i * stride
        r = random.Random(s["seed"])
        s["height_m"] = round(spec["height_m"] * (1.0 + r.uniform(-height_jitter, height_jitter)), 4)
        s["branch"]["level1"]["count"] = max(6, spec["branch"]["level1"]["count"]
                                             - r.randint(0, branch_jitter))
        s["branch"]["level2"]["per_parent"] = 2 if r.random() > 0.35 else 1
        name = f"{name_prefix}{i + 1:02d}"
        objs, report = build(s, name=name, origin=(x0 + i * spacing, 0.0, 0.0),
                             collection=ensure_collection(name))
        report["variant"] = i + 1
        report["seed"] = s["seed"]
        report["height_m"] = s["height_m"]
        results.append((objs, report))
    return results


def main(preset_path, name="Tree_Birch", origin=(0.0, 0.0, 0.0), collection_name=None):
    spec = load_spec(preset_path)
    coll = ensure_collection(collection_name or name)
    objs, report = build(spec, name=name, origin=origin, collection=coll)
    report["objects"] = [o.name for o in objs.values()]
    report["spec"] = {
        "height_m": spec["height_m"],
        "canopy": spec["canopy"],
        "seed": spec["seed"],
        "season": spec["season"],
    }
    print("[TREEGEN] " + json.dumps(report, ensure_ascii=False))
    return report
