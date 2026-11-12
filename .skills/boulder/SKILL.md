---
name: "boulder"
description: "语义巨石生成：用形态语义（扁平卧石/方块/竖高/楔形/碎块）+ 体量 + 断口强度，生成高海拔崩积巨石的低面数三角面原型。当用户要生成崩积巨石、崩裂块石、漂砾，或要调体量、断口数量与破损程度时调用。"
---

# 语义巨石生成 — 程序化生成器

## 触发条件

- 要生成高海拔 / 崩积 / 崩裂地质带来的大块石（不是河卵石、不是装饰小品石）
- 要用语义描述形态：`扁平卧石 / 方块 / 竖高块石 / 楔形 / 碎块`
- 要控单块体量、断口数量、破损强度、面数预算
- 要把一套确定的石头参数固化成可复现的 preset

不负责地形、植被、渲染风格；材质只到"程序化裸露花岗岩"这一层，不含贴图烘焙。

## 文件

| 文件 | 作用 |
|---|---|
| `scripts/bouldergen.py` | 生成器本体，纯 `bpy` / `bmesh`，确定性 |
| `scripts/viewshot.py` | 视窗截图助手（设机位 + 强制刷新 + 干净截图） |
| `presets/boulder.json` | 七块定版巨石参数 + 花岗岩材质配方（用户 2026-11-11 确认，preset 是唯一真源） |

技能内不含贴图、不含 `.blend` 依赖。

## 运行

在已连 MCP 的 Blender 里（推荐，符合项目预览规范）：

```python
import sys
SKILL = r"c:\Users\bruce\Documents\BlenderProjects\BlenderMcpStudy\.skills\boulder"
sys.path.insert(0, SKILL + r"\scripts")
import bouldergen

report = bouldergen.main(SKILL + r"\presets\boulder.json",
                         collection="Boulders_Prototype")
```

`main` 会：生成 → 沿 X 排开（净空取 preset 的 `layout.gap_m`）→ 打 `[BOULDERGEN] {json}` → 相交即抛错。

**禁止** `read_factory_settings` / `read_homefile`（会重置会话、断掉 MCP）。要新场景用 `bpy.data.scenes.new()`。

单独用几何接口：

```python
p = bouldergen.resolve({"form": "column", "bulk": 1.2, "seed": 42, "fracture": 1})
bm, points = bouldergen.build_one(p, budget={"min_tri": 90, "max_tri": 150})
```

## 语义参数

### 形态语义（`form`）

| form | 语义 | 默认比例 (X:Y:Z) | 默认平顶 | 默认断口数 |
|---|---|---|---|---|
| `slab` | 扁平卧石 | 1.00 : 0.86 : 0.42 | 0.88 | 1 |
| `block` | 方块 | 0.96 : 0.88 : 0.80 | 无 | 1 |
| `wedge` | 楔形 | 1.00 : 0.82 : 0.62 | 无 | 2 |
| `shard` | 碎块（嶙峋） | 0.86 : 0.72 : 0.66 | 无 | 2 |
| `column` | 竖高块石 | 0.74 : 0.68 : 1.00 | 无 | 1 |

### 字段

| 参数 | 位置 | 决定 |
|---|---|---|
| `form` | prototype | 形态语义，展开成默认比例 / 平顶 / 断口数 |
| `bulk` | prototype | 体量基准（米）；`size = bulk × form.aspect`；给了 `size` 就忽略 |
| `size` | prototype | 目标包围盒 `[x,y,z]`（米），生成后精确归一化到该尺寸 |
| `fracture` | prototype | 主断口数量，默认取 `form` 的值 |
| `severity` | prototype | 主断口切除体积比例，默认 0.28；第一刀用满值，后续刀用 0.55 倍 |
| `chip` | prototype | 小崩角切除体积比例，默认 0.09；`0` 表示不崩 |
| `top` | prototype | 平顶高度比（0=底 1=顶）；`null` 不截顶 |
| `top_tilt` | prototype | 平顶微倾 `[x,y]`，给平面法线加偏置，避免"机切"感 |
| `embed` | prototype | 沉地比例（按自身高度），实际露出高度 = `size.z × (1 − embed)` |
| `points` | prototype | 斐波那契球面取点数，决定母岩棱面数量（约 2n−4 面） |
| `rough` | prototype | 半径随机扰动，母岩嶙峋程度 |
| `jitter` | prototype | 顶点抖动幅度（相对体对角线），制造不规则边界 |
| `cuts` | prototype | 显式断口 `[{dir:[x,y,z], frac:0-1}]`，给了就不走语义自动布刀 |
| `seed` | prototype | 该块局部种子，改动只影响这一块 |
| `budget.min_tri` / `max_tri` | 顶层 | 单块三角面区间，越界自动调点数重试，6 次仍不达标抛错 |
| `layout.gap_m` | 顶层 | 排布净空（米），保证块间不粘连 |
| `material` | 顶层 | 见下方「材质」；`kind` 缺省时走纯色白模 |

## 生成顺序（必须保持这个顺序）

```
斐波那契球面取点 → 凸包 → 顶点抖动（只在这一步） → 可选截顶 → 主断口 → 崩角
→ 三角化 → 法线重算 → 归一化到 size → 底面贴地 → 按 embed 下沉
```

三条硬性顺序契约：

1. **抖动必须在所有切割之前**。切口之后动顶点会把封盖面拉成非平面薄片，观感就是"挤出感"。
2. **断口位置由体积比例反解**，不是给个固定偏移。固定偏移容易只削掉薄皮，同样出挤出感。
3. **封盖必须封成单一平面**：`bisect_plane(clear_outer=True)` 后取 `len(e.link_faces)==1` 的边，`holes_fill` 再三角化。断面共面才有"断裂"而不是"折皱"。

## 七种定版原型

| ID | 形态 | 面数 | 尺寸 X×Y×Z (m) | 露出高度 (m) |
|---|---|---|---|---|
| B01 | slab 扁平卧石 + 微倾平顶 | 106 | 1.80×1.48×0.80 | 0.67 |
| B02 | block 方块 | 98 | 1.54×1.40×1.28 | 1.10 |
| B03 | slab 贴地大扁石 | 108 | 1.90×1.66×0.60 | 0.49 |
| B04 | column 竖高块石 | 92 | 1.22×1.14×1.60 | 1.54 |
| B05 | block 中块 | 98 | 1.66×1.38×1.10 | 0.95 |
| B06 | column 竖高 + 平顶 | 106 | 1.32×1.22×1.60 | 1.44 |
| B07 | shard 嶙峋碎块 | 108 | 1.60×1.50×1.26 | 1.07 |

合计 716 三角面。单块投影占地 1.2–1.9m，与小石（0.2–0.5m）拉开 3–4 倍体量差，撒点时不需要再靠物体缩放补尺寸。

## 材质：有裂痕的大块裸露花岗岩

两件事分开做，互不干扰：几何负责"崩裂成块"，材质负责"花岗岩 + 裂痕"。

### UV：盒式投影，真实米尺度

`uv_box_project(me, tile_m)`：按每个面的法线主导轴投影（|x| / |y| / |z| 取最大），`UV = 局部坐标米数 / tile_m`，默认 `tile_m = 0.5`。

- 单层 `UVMap`，不重叠、不旋转、不做智能展开，不依赖 UV 接缝
- UV 跨度 = 真实尺寸 / `tile_m`（如 1.80m 宽 → span_u ≈ 3.6）
- 只在矿粒与微观起伏上用 UV；大色斑和裂痕走 Object 坐标，避免 0.5m 平铺重复

### 节点结构（全程序化，零贴图）

| 层 | 坐标 | 做法 |
|---|---|---|
| 大色斑 | Object | Noise 0.45m → ColorRamp，在 `base` / `light` 间混合 |
| 长石颗粒 | UV | Voronoi F1 5mm，`Distance` 经 ColorRamp 取稀疏白点 → `feldspar` |
| 云母黑点 | UV | Voronoi F1 2.5mm，更小阈值 → `mica` |
| 主裂痕 | Object | Voronoi `DISTANCE_TO_EDGE` 1.15m，宽 32mm，深度 0.90 |
| 细裂痕 | Object | Voronoi `DISTANCE_TO_EDGE` 0.38m，宽 7.7mm，深度 0.55 |
| 裂痕打断 | Object | Noise 0.55m → ColorRamp（0.42–0.66）乘进裂痕遮罩，避免闭合网格感 |
| 土垢 | Object | Noise 0.32m → ColorRamp（0.40–0.62），`amount` 0.55，压向暖灰褐 |
| 垂直水痕 | Object | Mapping 把 Z 压成 1/7 → Noise 0.22m，形成竖向流痕 |
| 铁锈斑 | Object | Voronoi F1 0.28m 芯部 → 赭褐 `stain` 色，稀疏分布 |
| 地衣 | Object | Noise 0.10m（detail 6）取高阈值 0.56–0.64 × Noise 0.40m 稀疏遮罩 → 不规则灰绿斑 |
| 近地积尘 | Generated | Generated Z（Map Range 0→0.42）→ 底部变脏，破掉"整块干净" |
| 固有色 | — | 上述层依次 Mix 到 `crack` 色，接 Principled `Base Color` |
| 法线 | UV + Object | 5mm 微粒 Noise + 45mm 起伏 Noise − 裂痕凹陷 → Bump（strength 0.85 / distance 1.8mm）→ `Normal` |
| 粗糙度 | — | 常量 0.74（风化面更哑，不接任何纹理） |
| 金属度 / 高光 | — | 常量 0.0 / 0.5 |

### 配方字段（`material`）

| 字段 | 默认 | 说明 |
|---|---|---|
| `kind` | — | 给了才走程序化花岗岩；缺省 = 纯色白模 |
| `name` | `MAT_Boulder_Granite` | 材质名，同名会原地重建节点 |
| `uv_tile_m` | 0.5 | UV 一格代表的真实米数 |
| `colors.base / light` | 见 preset | 大色斑两端色 |
| `colors.feldspar / mica / crack` | 见 preset | 长石、云母、裂痕色 |
| `grain.size_mm` | 5.0 | 长石颗粒尺寸（毫米），云母取 0.5 倍 |
| `grain.feldspar / mica` | 0.26 / 0.09 | 颗粒遮罩阈值，越小越密 |
| `crack.major_m / minor_m` | 1.15 / 0.38 | 两级裂痕网格尺度（米） |
| `crack.width / depth` | 0.032 / 0.90 | 主裂宽（米）与变暗强度 |
| `crack.break_m / break_lo / break_hi` | 0.55 / 0.36 / 0.60 | 裂痕打断噪声的尺度与阈值 |
| `weather.grime` | 0.32m / 0.55 | 土垢：尺度、混合量、ColorRamp 阈值 `lo/hi` |
| `weather.streak` | 0.22m / 0.55 | 垂直水痕：尺度、混合量、`stretch` 拉长倍率 |
| `weather.stain` | 0.28m / 0.50 | 铁锈斑：尺度、芯部阈值 `edge`、混合量 |
| `weather.lichen` | 0.10m / 0.70 | 地衣：噪声尺度、阈值 `lo/hi`、混合量、`sparse_*` 稀疏遮罩 |
| `weather.dirt` | 0.45 / 0.85 | 近地积尘：高度比例（Generated Z）、混合量 |
| `bump.grain / coarse / crack` | 0.45 / 0.55 / 1.6 | 三路高度权重 |
| `bump.strength / distance_m` | 0.85 / 0.0018 | Bump 强度与起伏距离 |
| `roughness / metallic / specular` | 0.74 / 0.0 / 0.5 | 全部为常量 |

配色注意：本项目预览世界 `W_FarField` 是蓝调天空、不加灯，背光面会明显偏冷偏暗。
固有色按"受光面读作中灰花岗岩、并且带风化脏感"来定（当前 base ≈ 0.26, 0.245, 0.226 线性）。
早先版本曾用 0.62 级别的高反照率，结果在开阔天空下像新切的白石，已否。
不要再往物理反照率压 —— 0.24~0.30 是这版世界下的可用区间。

调参教训：1m 级石头身上，风化层的特征尺度超过 0.4m 就只剩一两个斑，
参数再大也"看不见变化"。土垢/地衣这类要压在 0.1~0.35m 才读得出来；
同时 ColorRamp 的 `lo/hi` 间距不能太宽，宽了就变成半透明蒙版，等于没加。

## 硬约束

- 全部三角面，单块 `min_tri ≤ tri ≤ max_tri`，越界抛错不静默截断
- 平直着色（所有 polygon `use_smooth=False`），大断面保持硬棱；不做角度平滑、不做倒角
- 每块最多 1 个主断口 + 1 个小崩角，不允许叠加多层浅切（会出"多结构折皱"）
- 排布后必须做 AABB 两两相交检查，`overlap` 非空直接失败
- 埋地量 `embed` 默认 0.14–0.18；要精确露出高度时按 `size.z × (1−embed)` 反算

## 验收

1. 打印 `[BOULDERGEN]` report，逐块核对 `tri` / `dims` / `points`
2. `total_tri` 与每块面数落在预算区间
3. 断口数量 = 1 主 + 最多 1 崩角，近景看不到薄片状挤出
4. `bounds` 里相邻块 X 间隙等于 `gap_m`，`overlap` 为空
5. 要比例参照时 append `.skills/STARTER/assets/ref_human.blend` 的 `ref_human`（1.8m）
6. 预览按项目规范：EEVEE + `W_FarField` 环境、不加灯、Film Transparent 开；视窗 24mm / Material Preview / Scene World / 叠加层开；截图用 `viewshot.py`
7. 命名 `TheFarField_<内容>_YYMMDDHHMM.blend` 存 `scenes/`，预览存 `previews/`
8. 材质验收：每块都有 `uv_layers["UVMap"]`，UV 跨度 = 尺寸 / `uv_tile_m`；节点里没有 `ShaderNodeTexImage`；`Base Color` 与 `Normal` 有连线；`Roughness` 是常量且未连线

## 已知限制

- 断口是平面切割，出的是直棱直角的撞击面，没有真实的贝壳状断口与阶步
- 面数上限 150 卡死，无法在同一块上既做多级再破裂又做大断面
- 圆钝风化形态没有分支（当前全部是棱角型）
- 只有 X / Y 单轴排布，环形或簇状摆位需自己在外部写
- 抖动是各向同性的，没有按层理方向做各向异性侵蚀
- 裂痕是 Object 空间里 Voronoi 的切面线，和几何断口不对齐，也不沿断口延伸
- 材质全程序化、无贴图烘焙，没有 mipmap / 各向异性过滤，远距细颗粒会闪
- `Object` 坐标依赖物体 scale = 1；被缩放的石头要把纹理坐标对象指到自身，否则纹理跟着缩放
- 背光面偏冷是场景世界（蓝调天空 + 不加灯）决定的，不是材质问题；要中性灰得另配环境

## 移植契约

preset 是内容、脚本是算法，两者都不含二进制资产。换引擎时照着下表对齐：

| bpy / bmesh | Three.js |
|---|---|
| `random.Random(seed)` | 自带 seeded PRNG（mulberry32 / xorshift），禁止 `Math.random` |
| `convex_hull` | `ConvexHull` + `ConvexGeometry` |
| `bisect_plane` + `holes_fill` | 自写平面切割与封盖三角扇，或 `three-bvh-csg` |
| 体积比例反解平面 | 二分 + 体积计算（凸体可用解析式） |
| `_fill` 后三角化 | `BufferGeometryUtils` 的 ear-clipping |
| 归一化 / 贴地 / 下沉 | 直接照搬（包围盒缩放 + 底面贴地） |

必须一并带走的三条契约：

- 种子全表集中，任何一处引入非确定性都会让同一 preset 在不同平台产出不同石头
- 单位固定为米，`size` 是真实尺度，不要按单块包围盒归一化
- 保留凸包顶点，可直接当 `cannon-es` / `rapier` 的凸多面体碰撞体
