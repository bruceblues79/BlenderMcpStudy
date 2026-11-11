"""高原苔地地块生成器：16m 单四边面地块 + 纯程序化地表材质。

约束：
- 地块为单一四边面（2 三角面），不做细分与起伏；
- 材质全部为节点，无 TEX_IMAGE、无外部贴图；
- 纹理尺度按真实米制，坐标由世界位置驱动，相邻地块拼接无缝；
- seed 为唯一随机源，相同 seed 生成结果完全一致。
"""
import json
import math
import os
import random

import bpy


def load_spec(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_collection(name, scene=None):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        (scene or bpy.context.scene).collection.children.link(coll)
    return coll


def _srgb_to_linear(hexstr):
    h = hexstr.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (out[0], out[1], out[2], 1.0)


def _noise(nt, name, p, loc, rng, dim="3D"):
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.name = n.label = name
    n.location = loc
    n.noise_dimensions = dim
    n.inputs["Scale"].default_value = p["scale"]
    n.inputs["Detail"].default_value = p.get("detail", 4.0)
    n.inputs["Roughness"].default_value = p.get("roughness", 0.55)
    n.inputs["Distortion"].default_value = p.get("distortion", 0.0)
    if dim == "4D":
        n.inputs["W"].default_value = rng.uniform(0.0, 10.0)
    return n


def _ramp(nt, name, stops, loc, interp="EASE"):
    r = nt.nodes.new("ShaderNodeValToRGB")
    r.name = r.label = name
    r.location = loc
    cr = r.color_ramp
    cr.interpolation = interp
    while len(cr.elements) > len(stops):
        cr.elements.remove(cr.elements[-1])
    while len(cr.elements) < len(stops):
        cr.elements.new(0.5)
    for el, (pos, color) in zip(cr.elements, stops):
        el.position = pos
        el.color = _srgb_to_linear(color) if isinstance(color, str) else color
    return r


def _math(nt, name, op, a=None, b=None, loc=(0, 0)):
    n = nt.nodes.new("ShaderNodeMath")
    n.name = n.label = name
    n.location = loc
    n.operation = op
    if a is not None:
        n.inputs[0].default_value = a
    if b is not None:
        n.inputs[1].default_value = b
    return n


def _mix(nt, name, loc, blend="MIX"):
    n = nt.nodes.new("ShaderNodeMix")
    n.name = n.label = name
    n.location = loc
    n.data_type = "RGBA"
    n.blend_type = blend
    n.clamp_factor = True
    return n


def _voronoi(nt, name, scale, vec, loc, rng):
    v = nt.nodes.new("ShaderNodeTexVoronoi")
    v.name = v.label = name
    v.location = loc
    v.feature = "F1"
    v.inputs["Scale"].default_value = scale
    v.inputs["Randomness"].default_value = 1.0
    nt.links.new(vec, v.inputs["Vector"])
    return v


def _offset_mapping(nt, name, vec, loc, rng):
    m = nt.nodes.new("ShaderNodeMapping")
    m.name = m.label = name
    m.location = loc
    m.inputs["Location"].default_value = (
        rng.uniform(0.0, 40.0), rng.uniform(0.0, 40.0), rng.uniform(0.0, 40.0))
    nt.links.new(vec, m.inputs["Vector"])
    return m


def _litter_layer(nt, tag, mp, sc, radius, edge_scale, gain, colors, rng, loc_y):
    v = _voronoi(nt, "Voronoi_" + tag, sc["scale"], mp.outputs["Vector"], (-2200, loc_y - 60), rng)
    shape = _ramp(nt, "Ramp_" + tag + "Shape",
                  [(0.03, (1, 1, 1, 1)), (radius, (0, 0, 0, 1))], (-2000, loc_y - 40))
    nt.links.new(v.outputs["Distance"], shape.inputs["Fac"])
    edge_n = _noise(nt, "Noise_" + tag + "Edge",
                    {"scale": edge_scale, "detail": 3.0, "roughness": 0.55, "distortion": 0.5},
                    (-2200, loc_y - 300), rng, "4D")
    edge_r = _ramp(nt, "Ramp_" + tag + "Edge",
                   [(0.30, (0, 0, 0, 1)), (0.64, (1, 1, 1, 1))], (-2000, loc_y - 300))
    nt.links.new(edge_n.outputs["Fac"], edge_r.inputs["Fac"])
    mul1 = _math(nt, "Mul_" + tag + "Shape", "MULTIPLY", loc=(-1780, loc_y - 60))
    nt.links.new(shape.outputs["Color"], mul1.inputs[0])
    nt.links.new(edge_r.outputs["Color"], mul1.inputs[1])
    mul2 = _math(nt, "Mul_" + tag + "Gain", "MULTIPLY", b=gain, loc=(-1620, loc_y - 60))
    nt.links.new(mul1.outputs[0], mul2.inputs[0])
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    sep.name = sep.label = "Sep_" + tag
    sep.location = (-2000, loc_y - 180)
    nt.links.new(v.outputs["Color"], sep.inputs["Color"])
    col = _ramp(nt, "Ramp_" + tag + "Color",
                [(0.05, colors[0]), (0.95, colors[1])], (-1780, loc_y - 220))
    nt.links.new(sep.outputs["Red"], col.inputs["Fac"])
    return mul2, col, shape


def build_material(spec):
    """按 preset 构建地表材质，返回 bpy.types.Material。"""
    msp = spec["material"]
    seed = int(spec.get("seed", 0))
    rng = random.Random(seed)

    mat = bpy.data.materials.new(msp["name"])
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    N = nt.nodes.new

    geo = N("ShaderNodeNewGeometry")
    geo.location = (-2800, 200)
    pos = geo.outputs["Position"]

    # ---------- 腐殖土 ----------
    soil = msp["soil"]
    n_soil = _noise(nt, "Noise_Soil", soil, (-2400, 900), rng, "4D")
    nt.links.new(pos, n_soil.inputs["Vector"])
    r_soil = _ramp(nt, "Ramp_Soil",
                   [(0.24, soil["dark"]), (0.52, soil["mid"]), (0.80, soil["light"])],
                   (-2200, 900))
    nt.links.new(n_soil.outputs["Fac"], r_soil.inputs["Fac"])

    # ---------- 苔藓（weight 直接控制覆盖度） ----------
    mo = msp["moss"]
    w = float(mo["weight"])
    moss_low = 0.5 - 0.21 * w
    n_mreg = _noise(nt, "Noise_MossRegion", mo["region"], (-2400, 600), rng, "4D")
    nt.links.new(pos, n_mreg.inputs["Vector"])
    r_mreg = _ramp(nt, "Ramp_MossRegion",
                   [(moss_low, (0, 0, 0, 1)), (moss_low + 0.14, (1, 1, 1, 1))], (-2200, 600))
    nt.links.new(n_mreg.outputs["Fac"], r_mreg.inputs["Fac"])

    n_medge = _noise(nt, "Noise_MossEdge", mo["edge"], (-2400, 360), rng, "4D")
    nt.links.new(pos, n_medge.inputs["Vector"])
    r_medge = _ramp(nt, "Ramp_MossEdge",
                    [(0.30, (0, 0, 0, 1)), (0.68, (1, 1, 1, 1))], (-2200, 360))
    nt.links.new(n_medge.outputs["Fac"], r_medge.inputs["Fac"])

    mul_m1 = _math(nt, "Mul_Moss1", "MULTIPLY", loc=(-1900, 520))
    nt.links.new(r_mreg.outputs["Color"], mul_m1.inputs[0])
    nt.links.new(r_medge.outputs["Color"], mul_m1.inputs[1])
    mul_m2 = _math(nt, "Mul_Moss2", "MULTIPLY", b=1.3, loc=(-1750, 520))
    nt.links.new(mul_m1.outputs[0], mul_m2.inputs[0])
    clamp_m = _math(nt, "Clamp_Moss", "MINIMUM", b=1.0, loc=(-1600, 520))
    nt.links.new(mul_m2.outputs[0], clamp_m.inputs[0])
    moss_on = _math(nt, "Mul_MossEnable", "MULTIPLY",
                    b=1.0 if w > 0.0 else 0.0, loc=(-1470, 520))
    nt.links.new(clamp_m.outputs[0], moss_on.inputs[0])

    n_mcol = _noise(nt, "Noise_MossColor", mo["color"], (-2400, 120), rng, "4D")
    nt.links.new(pos, n_mcol.inputs["Vector"])
    r_mcol = _ramp(nt, "Ramp_MossColor",
                   [(0.28, mo["deep"]), (0.58, mo["mid"]), (0.82, mo["light"])], (-2200, 120))
    nt.links.new(n_mcol.outputs["Fac"], r_mcol.inputs["Fac"])

    n_mfine = _noise(nt, "Noise_MossFine",
                     {"scale": 20.0, "detail": 3.0, "roughness": 0.6}, (-2100, -100), rng, "4D")
    nt.links.new(pos, n_mfine.inputs["Vector"])
    r_mfine = _ramp(nt, "Ramp_MossFine",
                    [(0.32, (0.78, 0.78, 0.78, 1)), (0.68, (1, 1, 1, 1))], (-1920, -100))
    nt.links.new(n_mfine.outputs["Fac"], r_mfine.inputs["Fac"])
    mix_mfine = _mix(nt, "Mix_MossFine", (-1750, 120), "MULTIPLY")
    mix_mfine.inputs[0].default_value = 1.0
    nt.links.new(r_mcol.outputs["Color"], mix_mfine.inputs[6])
    nt.links.new(r_mfine.outputs["Color"], mix_mfine.inputs[7])

    mix_moss = _mix(nt, "Mix_Moss", (-1400, 700))
    nt.links.new(r_soil.outputs["Color"], mix_moss.inputs[6])
    nt.links.new(mix_mfine.outputs[2], mix_moss.inputs[7])
    nt.links.new(moss_on.outputs[0], mix_moss.inputs[0])
    cur = mix_moss

    # ---------- 枯叶碎屑 ----------
    lit = msp["litter"]
    lw = float(lit["weight"])

    map_big = N("ShaderNodeMapping")
    map_big.name = map_big.label = "Map_Litter"
    map_big.location = (-2400, -200)
    map_big.inputs["Scale"].default_value = (1.0, lit["big"]["stretch"], 1.0)
    nt.links.new(pos, map_big.inputs["Vector"])

    lb, lcb, lshp = _litter_layer(nt, "Litter", map_big, lit["big"], lit["big"]["radius"],
                                  lit["big"]["edge_scale"], lit["big"]["gain"],
                                  (lit["big"]["dark"], lit["big"]["light"]), rng, -200)

    cl_low = 0.5 - 0.28 * lw
    n_cl = _noise(nt, "Noise_LitterCluster", lit["cluster"], (-2400, -700), rng, "4D")
    nt.links.new(pos, n_cl.inputs["Vector"])
    r_cl = _ramp(nt, "Ramp_LitterCluster",
                 [(cl_low, (0, 0, 0, 1)), (cl_low + 0.18, (1, 1, 1, 1))], (-2200, -700))
    nt.links.new(n_cl.outputs["Fac"], r_cl.inputs["Fac"])
    lf = _math(nt, "Mul_LitterFac", "MULTIPLY", loc=(-1500, -620))
    nt.links.new(lb.outputs[0], lf.inputs[0])
    nt.links.new(r_cl.outputs["Color"], lf.inputs[1])
    lf2 = _math(nt, "Mul_LitterFacGain", "MULTIPLY", b=0.95, loc=(-1350, -620))
    nt.links.new(lf.outputs[0], lf2.inputs[0])
    lit_on = _math(nt, "Mul_LitterEnable", "MULTIPLY",
                   b=1.0 if lw > 0.0 else 0.0, loc=(-1220, -620))
    nt.links.new(lf2.outputs[0], lit_on.inputs[0])

    mix_lit = _mix(nt, "Mix_Litter", (-1150, 600))
    nt.links.new(cur.outputs[2], mix_lit.inputs[6])
    nt.links.new(lcb.outputs["Color"], mix_lit.inputs[7])
    nt.links.new(lit_on.outputs[0], mix_lit.inputs[0])
    cur = mix_lit

    map_f = N("ShaderNodeMapping")
    map_f.name = map_f.label = "Map_Frag"
    map_f.location = (-2400, -1000)
    map_f.inputs["Scale"].default_value = (1.0, lit["frag"]["stretch"], 1.0)
    nt.links.new(pos, map_f.inputs["Vector"])
    fb, fcb, fshp = _litter_layer(nt, "Frag", map_f, lit["frag"], lit["frag"]["radius"],
                                  lit["frag"]["edge_scale"], lit["frag"]["gain"],
                                  (lit["frag"]["dark"], lit["frag"]["light"]), rng, -1000)
    ff = _math(nt, "Mul_FragFac", "MULTIPLY", loc=(-1500, -950))
    nt.links.new(fb.outputs[0], ff.inputs[0])
    nt.links.new(r_cl.outputs["Color"], ff.inputs[1])
    ff2 = _math(nt, "Mul_FragFacGain", "MULTIPLY", b=0.55, loc=(-1350, -950))
    nt.links.new(ff.outputs[0], ff2.inputs[0])
    frag_on = _math(nt, "Mul_FragEnable", "MULTIPLY",
                    b=1.0 if lw > 0.0 else 0.0, loc=(-1220, -950))
    nt.links.new(ff2.outputs[0], frag_on.inputs[0])

    mix_frag = _mix(nt, "Mix_Frag", (-950, 600))
    nt.links.new(cur.outputs[2], mix_frag.inputs[6])
    nt.links.new(fcb.outputs["Color"], mix_frag.inputs[7])
    nt.links.new(frag_on.outputs[0], mix_frag.inputs[0])
    cur = mix_frag

    # ---------- 碎砾 ----------
    gv = msp["gravel"]
    gw = float(gv["weight"])
    map_g = _offset_mapping(nt, "Map_Gravel", pos, (-2400, -1400), rng)
    v_peb = _voronoi(nt, "Voronoi_Pebble", gv["scale"], map_g.outputs["Vector"], (-2200, -1400), rng)
    r_pshape = _ramp(nt, "Ramp_PebbleShape",
                     [(0.02, (1, 1, 1, 1)), (gv["radius"], (0, 0, 0, 1))], (-2000, -1380))
    nt.links.new(v_peb.outputs["Distance"], r_pshape.inputs["Fac"])

    g_low = 0.66 - 0.64 * gw
    n_pmask = _noise(nt, "Noise_PebbleMask", gv["mask"], (-2400, -1650), rng, "4D")
    nt.links.new(pos, n_pmask.inputs["Vector"])
    r_pmask = _ramp(nt, "Ramp_PebbleMask",
                    [(g_low, (0, 0, 0, 1)), (g_low + 0.12, (1, 1, 1, 1))], (-2200, -1650))
    nt.links.new(n_pmask.outputs["Fac"], r_pmask.inputs["Fac"])

    n_pedge = _noise(nt, "Noise_PebbleEdge",
                     {"scale": gv["edge_scale"], "detail": 3.0, "roughness": 0.55, "distortion": 0.4},
                     (-2400, -1880), rng, "4D")
    nt.links.new(pos, n_pedge.inputs["Vector"])
    r_pedge = _ramp(nt, "Ramp_PebbleEdge",
                    [(0.30, (0, 0, 0, 1)), (0.62, (1, 1, 1, 1))], (-2200, -1880))
    nt.links.new(n_pedge.outputs["Fac"], r_pedge.inputs["Fac"])

    p1 = _math(nt, "Mul_Peb1", "MULTIPLY", loc=(-1750, -1450))
    nt.links.new(r_pshape.outputs["Color"], p1.inputs[0])
    nt.links.new(r_pmask.outputs["Color"], p1.inputs[1])
    p2 = _math(nt, "Mul_Peb2", "MULTIPLY", loc=(-1600, -1450))
    nt.links.new(p1.outputs[0], p2.inputs[0])
    nt.links.new(r_pedge.outputs["Color"], p2.inputs[1])
    peb_on = _math(nt, "Mul_PebbleEnable", "MULTIPLY",
                   b=1.0 if gw > 0.0 else 0.0, loc=(-1450, -1450))
    nt.links.new(p2.outputs[0], peb_on.inputs[0])

    sep_p = N("ShaderNodeSeparateColor")
    sep_p.name = sep_p.label = "Sep_Pebble"
    sep_p.location = (-2200, -1560)
    nt.links.new(v_peb.outputs["Color"], sep_p.inputs["Color"])
    r_pcol = _ramp(nt, "Ramp_PebbleColor",
                   [(0.05, gv["dark"]), (0.95, gv["light"])], (-2000, -1600))
    nt.links.new(sep_p.outputs["Red"], r_pcol.inputs["Fac"])

    mix_peb = _mix(nt, "Mix_Pebble", (-700, 600))
    nt.links.new(cur.outputs[2], mix_peb.inputs[6])
    nt.links.new(r_pcol.outputs["Color"], mix_peb.inputs[7])
    nt.links.new(peb_on.outputs[0], mix_peb.inputs[0])
    cur = mix_peb

    # ---------- 地衣 / 干草色斑 ----------
    li = msp["lichen"]
    lw_li = float(li["weight"])
    li_low = 0.68 - 0.32 * lw_li
    n_li = _noise(nt, "Noise_Lichen", li["patch"], (-1150, -1400), rng, "4D")
    nt.links.new(pos, n_li.inputs["Vector"])
    r_li = _ramp(nt, "Ramp_Lichen",
                 [(li_low, (0, 0, 0, 1)), (li_low + 0.09, (1, 1, 1, 1))], (-950, -1400))
    nt.links.new(n_li.outputs["Fac"], r_li.inputs["Fac"])
    n_lie = _noise(nt, "Noise_LichenEdge", li["edge"], (-1150, -1650), rng, "4D")
    nt.links.new(pos, n_lie.inputs["Vector"])
    r_lie = _ramp(nt, "Ramp_LichenEdge",
                  [(0.34, (0, 0, 0, 1)), (0.64, (1, 1, 1, 1))], (-950, -1650))
    nt.links.new(n_lie.outputs["Fac"], r_lie.inputs["Fac"])
    li_f = _math(nt, "Mul_LichenFac", "MULTIPLY", loc=(-780, -1480))
    nt.links.new(r_li.outputs["Color"], li_f.inputs[0])
    nt.links.new(r_lie.outputs["Color"], li_f.inputs[1])
    li_f2 = _math(nt, "Mul_LichenGain", "MULTIPLY", b=li["gain"], loc=(-640, -1480))
    nt.links.new(li_f.outputs[0], li_f2.inputs[0])
    lich_on = _math(nt, "Mul_LichenEnable", "MULTIPLY",
                    b=1.0 if lw_li > 0.0 else 0.0, loc=(-500, -1480))
    nt.links.new(li_f2.outputs[0], lich_on.inputs[0])
    n_lic = _noise(nt, "Noise_LichenColor", li["color"], (-950, -1850), rng, "4D")
    nt.links.new(pos, n_lic.inputs["Vector"])
    r_lic = _ramp(nt, "Ramp_LichenColor",
                  [(0.30, li["dark"]), (0.72, li["light"])], (-780, -1850))
    nt.links.new(n_lic.outputs["Fac"], r_lic.inputs["Fac"])

    mix_li = _mix(nt, "Mix_Lichen", (-480, 320))
    nt.links.new(cur.outputs[2], mix_li.inputs[6])
    nt.links.new(r_lic.outputs["Color"], mix_li.inputs[7])
    nt.links.new(lich_on.outputs[0], mix_li.inputs[0])
    cur = mix_li

    # ---------- 细颗粒色噪 ----------
    gr = msp["grain"]
    n_grain = _noise(nt, "Noise_Grain",
                     {"scale": gr["scale"], "detail": 4.0, "roughness": 0.6, "distortion": 0.3},
                     (-1150, 900), rng, "4D")
    nt.links.new(pos, n_grain.inputs["Vector"])
    gv_ = gr["dark"]
    r_grain = _ramp(nt, "Ramp_Grain",
                    [(0.30, (gv_, gv_, gv_, 1)), (0.70, (1, 1, 1, 1))], (-950, 900))
    nt.links.new(n_grain.outputs["Fac"], r_grain.inputs["Fac"])
    mix_grain = _mix(nt, "Mix_Grain", (-400, 600), "MULTIPLY")
    mix_grain.inputs[0].default_value = 1.0
    mix_grain.inputs[6].default_value = (1, 1, 1, 1)
    nt.links.new(r_grain.outputs["Color"], mix_grain.inputs[7])
    nt.links.new(cur.outputs[2], mix_grain.inputs[6])

    # ---------- 法线 ----------
    bp = msp["bump"]
    n_mid = _noise(nt, "Noise_SoilMid", bp["mid"], (-1600, -2350), rng, "4D")
    nt.links.new(pos, n_mid.inputs["Vector"])
    n_micro = _noise(nt, "Noise_Micro", bp["micro"], (-1600, -2100), rng, "4D")
    nt.links.new(pos, n_micro.inputs["Vector"])
    n_fine = _noise(nt, "Noise_FineGrain", bp["fine"], (-1150, -2100), rng, "4D")
    nt.links.new(pos, n_fine.inputs["Vector"])

    b1 = N("ShaderNodeBump")
    b1.name = b1.label = "Bump_Mid"
    b1.location = (-900, -1500)
    b1.inputs["Strength"].default_value = bp["mid"]["strength"]
    b1.inputs["Distance"].default_value = bp["mid"]["distance"]
    nt.links.new(n_mid.outputs["Fac"], b1.inputs["Height"])

    b2 = N("ShaderNodeBump")
    b2.name = b2.label = "Bump_Micro"
    b2.location = (-750, -1500)
    b2.inputs["Strength"].default_value = bp["micro"]["strength"]
    b2.inputs["Distance"].default_value = bp["micro"]["distance"]
    nt.links.new(n_micro.outputs["Fac"], b2.inputs["Height"])
    nt.links.new(b1.outputs["Normal"], b2.inputs["Normal"])

    b3 = N("ShaderNodeBump")
    b3.name = b3.label = "Bump_Litter"
    b3.location = (-600, -1500)
    b3.inputs["Strength"].default_value = bp["litter"]["strength"]
    b3.inputs["Distance"].default_value = bp["litter"]["distance"]
    nt.links.new(lshp.outputs["Color"], b3.inputs["Height"])
    nt.links.new(b2.outputs["Normal"], b3.inputs["Normal"])

    b4 = N("ShaderNodeBump")
    b4.name = b4.label = "Bump_Pebble"
    b4.location = (-450, -1500)
    b4.inputs["Strength"].default_value = bp["gravel"]["strength"]
    b4.inputs["Distance"].default_value = bp["gravel"]["distance"]
    nt.links.new(r_pshape.outputs["Color"], b4.inputs["Height"])
    nt.links.new(b3.outputs["Normal"], b4.inputs["Normal"])

    b5 = N("ShaderNodeBump")
    b5.name = b5.label = "Bump_Fine"
    b5.location = (-300, -1500)
    b5.inputs["Strength"].default_value = bp["fine"]["strength"]
    b5.inputs["Distance"].default_value = bp["fine"]["distance"]
    nt.links.new(n_fine.outputs["Fac"], b5.inputs["Height"])
    nt.links.new(b4.outputs["Normal"], b5.inputs["Normal"])

    bsdf = N("ShaderNodeBsdfPrincipled")
    bsdf.name = bsdf.label = "Ground_BSDF"
    bsdf.location = (-150, 600)
    bsdf.inputs["Roughness"].default_value = msp["roughness"]
    nt.links.new(mix_grain.outputs[2], bsdf.inputs["Base Color"])
    nt.links.new(b5.outputs["Normal"], bsdf.inputs["Normal"])

    out = N("ShaderNodeOutputMaterial")
    out.location = (120, 600)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    return mat


def build(spec, name="Tile_Ground", collection=None, scene=None, location=(0.0, 0.0, 0.0),
          rebuild_material=True):
    """创建地块板体：顶面平坦 z=0，按 grid 分段，向下挤出厚度并封闭底面。"""
    import bmesh

    scene = scene or bpy.context.scene
    tile = spec["tile"]
    size = float(tile["size_m"])
    thickness = float(tile.get("thickness_m", 0.2))
    uv_per_m = float(tile.get("uv_per_m", 1.0))
    grid = max(1, int(tile.get("grid", 1)))
    half = size * 0.5
    step = size / grid

    verts = []
    top = {}
    bot = {}
    for j in range(grid + 1):
        for i in range(grid + 1):
            x = -half + step * i
            y = -half + step * j
            top[(i, j)] = len(verts)
            verts.append((x, y, 0.0))
    for j in range(grid + 1):
        for i in range(grid + 1):
            x = -half + step * i
            y = -half + step * j
            bot[(i, j)] = len(verts)
            verts.append((x, y, -thickness))

    faces = []
    for j in range(grid):
        for i in range(grid):
            faces.append((top[(i, j)], top[(i + 1, j)], top[(i + 1, j + 1)]))
            faces.append((top[(i, j)], top[(i + 1, j + 1)], top[(i, j + 1)]))
            faces.append((bot[(i, j)], bot[(i + 1, j + 1)], bot[(i + 1, j)]))
            faces.append((bot[(i, j)], bot[(i, j + 1)], bot[(i + 1, j + 1)]))
    for i in range(grid):
        faces.append((top[(i, 0)], bot[(i, 0)], bot[(i + 1, 0)]))
        faces.append((top[(i, 0)], bot[(i + 1, 0)], top[(i + 1, 0)]))
        faces.append((top[(i, grid)], top[(i + 1, grid)], bot[(i + 1, grid)]))
        faces.append((top[(i, grid)], bot[(i + 1, grid)], bot[(i, grid)]))
    for j in range(grid):
        faces.append((top[(0, j)], top[(0, j + 1)], bot[(0, j + 1)]))
        faces.append((top[(0, j)], bot[(0, j + 1)], bot[(0, j)]))
        faces.append((top[(grid, j)], bot[(grid, j)], bot[(grid, j + 1)]))
        faces.append((top[(grid, j)], bot[(grid, j + 1)], top[(grid, j + 1)]))

    me = bpy.data.meshes.new(name + "_Mesh")
    me.from_pydata(verts, [], faces)
    me.update()

    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(me)
    bm.free()

    uv = me.uv_layers.new(name="UVMap")
    for loop in me.loops:
        v = me.vertices[loop.vertex_index].co
        uv.data[loop.index].uv = ((v.x + half) * uv_per_m, (v.y + half) * uv_per_m)

    obj = bpy.data.objects.new(name, me)
    obj.location = location
    (collection or ensure_collection("Ground", scene)).objects.link(obj)

    mat_name = spec["material"]["name"]
    mat = None if rebuild_material else bpy.data.materials.get(mat_name)
    if mat is None:
        existing = bpy.data.materials.get(mat_name)
        if existing is not None:
            bpy.data.materials.remove(existing)
        mat = build_material(spec)
    me.materials.append(mat)

    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    report = {
        "name": obj.name,
        "size_m": size,
        "grid": grid,
        "faces": len(me.polygons),
        "tris": tris,
        "uv_span_m": (size * uv_per_m, size * uv_per_m),
        "material": mat.name,
    }
    return [obj], report
