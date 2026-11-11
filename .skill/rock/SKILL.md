---
name: "rock"
description: "石块生成器：按 preset 参数在 Blender 里生成低面数三角面石块原型，同一 seed 必然同结果。当用户要生成/调整野外石块、漂砾、崩积块石、改体量或破损程度时调用。"
---

# 石块生成 — 程序化生成器

## 触发条件

- 要生成一块或多块旷野石块（冰川漂砾 / 崩积块石一类）
- 要调整形态：体量、扁平度、棱角与破损、圆钝或嶙峋
- 要控制面数上限与包围盒尺寸
- 要把一套石块参数固化成可复现的 preset

不负责地形起伏、场景布景与渲染风格。

## 文件

| 文件 | 作用 |
|---|---|
| `scripts/rockgen.py` | 生成器本体，纯 `bpy`，确定性 |
| `scripts/preview.py` | 批处理直出：生成 + 环境光 + 参考人 + 渲染 |
| `presets/rock.json` | 七种石块标准参数 + 程序化花岗岩配方（定版默认） |

材质由节点实时计算，**技能内不含任何贴图文件**。

## 运行

### 默认直出（离线批处理）

在项目根目录执行：

```
blender -b --factory-startup --python ".skill/rock/scripts/preview.py" -- --preset rock
```

- 默认输出 `previews/TheFarField_rock_placement_rock.png`（脚本按自身位置推算项目根，不受 cwd 影响）
- `--layout row` 把七块按 0.65m 间距排成一排，输出 `previews/TheFarField_rock_row_rock.png`，用于逐个比对形态；参考人自动挪到队尾
- `--out` 必须给绝对路径：Blender 的 cwd 不等于项目根，相对路径会落到别处
- 可选机位：`--cam-y`、`--cam-z`、`--target-z`（不传则按 layout 取默认值）

### 在已打开的 Blender 里生成（MCP）

```python
import sys, os
SKILL = r"c:\Users\bruce\Documents\BlenderProjects\BlenderMcpStudy\.skill\rock"
sys.path.insert(0, os.path.join(SKILL, "scripts"))
import rockgen

scene = bpy.data.scenes.new("RockGen")
bpy.context.window.scene = scene

spec = rockgen.load_spec(os.path.join(SKILL, "presets", "rock.json"))
objs, report = rockgen.build(spec, name="Rock", collection=rockgen.ensure_collection("Rocks_Prototype"))
```

或直接用封装入口，会把同样的 report 打成 `[ROCKGEN] {...}`：

```python
report = rockgen.main(os.path.join(SKILL, "presets", "rock.json"), collection_name="Rocks_Prototype")
```

**禁止**在会话内用 `read_factory_settings` / `read_homefile`：会重置会话并断掉 MCP 连接。先 `scenes.new()` 建新场景再生成。

`report` 结构：`{"seed", "uv_tile_m", "rocks":[{"id","tri","dims","pos","embed"}], "total_tri"}`。

## 参数：输入决定什么结果

| 参数 | 位置 | 决定 |
|---|---|---|
| `seed` | 顶层 | 全局随机源；每块实际种子 = `seed + prototypes[].seed`，同 spec 同 seed 结果完全一致 |
| `budget.max_tri` | 顶层 | 单块三角面硬上限，越界抛 `RuntimeError` |
| `budget.min_tri` | 顶层 | 单块三角面下限，防止退化碎片 |
| `bounds.max_m` / `min_m` | 顶层 | 包围盒三轴允许区间（米），任一轴越界抛错 |
| `embed` | 顶层 | 沉入地表比例区间 `[0.14, 0.22]`，乘以自身高度得到下沉量 |
| `jitter` | 顶层 | 顶点扰幅（相对半径），制造不规则边界 |
| `smooth_factor` | 顶层 | 凸包后平滑强度，越大越圆钝 |
| `smooth_angle_deg` | 顶层 | 角度平滑阈值：面间夹角 ≤ 该值的边平滑过渡，超过则保持硬棱（默认 45°） |
| `uv_tile_m` | 顶层 | UV 密度：一张贴图覆盖的真实边长（米），默认 0.5 |
| `material` | 顶层 | 材质名与粗糙度、金属度常量 |
| `material.texture.kind` | 顶层 | 花岗岩配方名，目前只有 `granite_cool`（冷灰） |
| `material.texture.tile_m` | 顶层 | 配方对应的真实边长（米），与 `uv_tile_m` 一致 |
| `material.texture.mottle` | 顶层 | 大尺度色斑：`large_m` 斑块尺寸（米）、`contrast` 明暗幅度 |
| `material.texture.grain` | 顶层 | 矿粒：`size_mm` 晶粒直径（毫米）、`feldspar` 长石亮斑半径、`mica` 云母暗斑半径（Voronoi 距离） |
| `material.texture.albedo` | 顶层 | 线性 RGB 三色：`base` 底色 / `feldspar` 长石 / `mica` 云母 |
| `material.texture.bump` | 顶层 | 凹凸：`strength` 强度、`distance_m` 高度差（米）、`grain`/`mottle` 权重 |
| `prototypes[].id` | 数组 | 石块编号，同时决定网格与物体名 `Rock_<id>` |
| `prototypes[].form` | 数组 | `angular` 棱角型 / `rounded` 圆钝型，两条生成分支 |
| `prototypes[].points` | 数组 | 斐波那契球面取点数，决定原始凸包的棱面数量 |
| `prototypes[].squash` | 数组 | 竖向压扁系数，0.5 左右出扁平卧石 |
| `prototypes[].roughness` | 数组 | 半径随机扰动幅度，越大越嶙峋 |
| `prototypes[].top_ratio` | 数组 | 顶部水平截切高度（0=底 1=顶），出平坦顶面；`null` 不切 |
| `prototypes[].deep_cut` | 数组 | 是否加一刀深缺角（切掉约 1/3 体量） |
| `prototypes[].cuts` | 数组 | 浅切面数量，制造撞击面 |
| `prototypes[].dims` | 数组 | 目标包围盒 `[x,y,z]`（米），生成后精确归一化到该尺寸 |
| `prototypes[].seed` | 数组 | 该块局部种子偏移，改动只影响这一块 |
| `placement` | 顶层 | `[[x,y], ...]` 落地坐标；省略则全部落在原点 |

棱角型的生成顺序：凸包基底 → 顶部水平截切 → 深缺角 → 若干浅切面 → 平滑 → 顶点扰动 → 三角化 → 归一化到 `dims` → 底面贴地 → 按 `embed` 下沉。

每次切口前会备份网格，切完若超 `max_tri` 就回滚，所以面数上限是硬保证而不是事后裁剪。

## 七种原型定位

| ID | 形态 | 面数 | 尺寸 (m) | 用途 |
|---|---|---|---|---|
| P01 | 棱角 + 深缺角 + 平顶 | 70 | 0.46×0.39×0.36 | 主视觉块石 |
| P02 | 棱角 + 三浅切面 | 46 | 0.34×0.30×0.27 | 中块填充 |
| P03 | 扁平卧石（squash 0.52） | 68 | 0.50×0.41×0.24 | 贴地大扁石 |
| P04 | 圆钝（smooth） | 64 | 0.40×0.35×0.32 | 冰川漂砾 |
| P05 | 小块嶙峋 | 48 | 0.29×0.25×0.23 | 碎石点缀 |
| P06 | 圆钝扁球（squash 0.70） | 64 | 0.32×0.28×0.25 | 半埋卵石 |
| P07 | 棱角 + 深缺角 + 陡顶 | 70 | 0.50×0.38×0.35 | 端景块石 |

合计 430 三角面。

## 默认直出

`presets/rock.json` 就是定版默认值（用户 2026-11-11 认可的七种石块），用户说“生成石块”时直接跑，不再逐项确认：

```
blender -b --factory-startup --python .skill/rock/scripts/preview.py -- --preset rock
```

默认行为：生成 → 打环境光 → 摆参考人 → 渲染 `previews/TheFarField_rock_placement_<preset>.png` → 退出 Blender。

基线（改动后需重新对照）：7 块 / 430 三角面（每块 46–70）、尺寸 0.20–0.50m、角度平滑 45°、`uv_tile_m` 0.5、粗糙度常量 0.62、程序化花岗岩配方一套。

规则：
- 不保存 `.blend`，脚本生成的场景一律视为试验产物
- 用 `--out` 指定别的输出路径时才覆盖默认命名
- 只有当生成算法需要变（新形态分支、新破损方式）才改 `rockgen.py`；观感诉求只改 preset

## 多块派生

```python
objs, report = rockgen.spawn_variants(spec, count=7, spacing=0.75, x0=-2.1, y=-6.5)
```

同一 preset 派生 N 块并按固定间距排开，方便逐个比对。几何仍由各自 `seed` 决定，所以与单独生成完全一致；只有坐标不同。

## UV 与材质

- UV 在生成器内写入，与 `.skill/birch` 的做法一致：不依赖智能展开，不事后补 UV
- 盒式投影：每个面按法线主导轴（X/Y/Z 中绝对值最大者）投影到平面，UV 直接取该面顶点的真实米数除以 `uv_tile_m`
- 结果：配方固定覆盖 0.5m×0.5m，块石越大纹理重复次数越多，不同尺寸石块矿粒密度一致
- 材质 `MAT_Rock_Granite` 全程序化，**不读任何图片**：`ShaderNodeTexCoord` 取 UV → 噪声/Voronoi → 颜色混合 → `Bump`
- 配方三层：
  - 大斑：`Noise(large_m)` 经 ColorRamp 重塑 → 在 `base` 上下按 `contrast` 混合，避免平铺感
  - 长石亮斑：`Voronoi F1`（晶粒 `size_mm`）距离 < `feldspar` 的胞心区域 → 混向长石色
  - 云母暗斑：另一组 4D Voronoi（`W` 偏移打散）距离 < `mica` 处 → 混向近黑
- 凹凸：`Noise` 高频 + 大斑噪声按 `bump.grain` / `bump.mottle` 加权 → `Bump`（Distance 用米，默认 1.8mm）
- 粗糙度 0.62 / 金属度 0 为常量，不出粗糙度贴图
- 所有尺寸参数都是物理单位（米 / 毫米），与 `uv_tile_m` 解耦，换分辨率或换引擎不会改变观感尺度

## 固化产物与移植

这个技能本身就是资产：**preset 是内容，脚本是算法**。两者都不含 `.blend` 依赖，换成任何引擎都能重放同一套石块。

| 产物 | 可移植性 |
|---|---|
| `presets/rock.json` | 纯 JSON、单位为米、种子为整数，几何与材质配方都在里面，可直接当作运行时配置 |
| `scripts/rockgen.py` | 算法描述；随机只走 `random.Random(seed)`，顺序固定，无时钟/哈希依赖 |
| 本文件 | 参数语义与验收口径；换引擎时照着它对齐 |

材质没有任何二进制资产：`rock.json` 的 `material.texture` 就是配方，Blender 用节点实现，游戏端用 shader 实现，两边吃同一份 JSON。

移植到 Three.js 时的算子对照：

| 现用 bpy / bmesh | Three.js 对应 |
|---|---|
| `random.Random(seed)` | 自带 seeded PRNG（mulberry32 / xorshift），禁止用 `Math.random` |
| `convex_hull` | `examples/jsm/math/ConvexHull` + `ConvexGeometry` |
| `bisect_plane` + `holes_fill` | 需自写平面切割与切口封盖三角扇，或退而用 `three-bvh-csg` |
| `smooth_vert` | 一轮拉普拉斯平滑 |
| `_shade_by_angle` | `BufferGeometryUtils.toCreasedNormals(geo, 45°)` |
| `_uv_box` | 直接照搬（面法线主轴 → 平面投影，米数 ÷ `uv_tile_m`） |
| `_fit` / 下沉 | 直接照搬（包围盒缩放 + 底面贴地） |
| `Noise` / `Voronoi` 节点 | 片元着色器里的 value-noise / Worley（3D 噪声，按米取尺度），或 CPU 烘进 `DataTexture` |
| `Bump` 节点 | 片元里对高度求导扰动法线，或 `normalMap` 由烘出的高度场生成 |

移植时必须一并带走的三条契约：
- 种子全表集中，任何一处引入非确定性都会让同一 preset 在不同平台产出不同石块
- 生成时保留凸包顶点，可直接当 `cannon-es` / `rapier` 的凸多面体碰撞体
- 单位固定为米，`uv_tile_m` 是真实尺度参数，不要改成按单块包围盒归一化

## 硬约束

- 全部三角面
- 单块 `min_tri ≤ tri ≤ max_tri`，越界抛 `RuntimeError`，不静默截断
- 包围盒三轴都落在 `[bounds.min_m, bounds.max_m]`，任一轴越界抛错
- 着色统一按角度平滑：所有面 `smooth`，面间夹角 > `smooth_angle_deg` 的边标锐边，所以大面保持硬棱、弧面过渡柔和；不使用 `shade_auto_smooth` 修改器，锐边直接写进网格数据
- 不做倒角，破损靠切面与顶点扰动
- 所有石块共用同一个材质与配方，不逐块出图
- UV 必须真实尺度：配方边长 = `uv_tile_m` 米，禁止按单块包围盒归一化（会让大小块的矿粒密度不一致）

## 验收

1. 打印 report，逐块核对 `tri` / `dims` / `embed`
2. 三轴尺寸全部在 0.2–0.5m，面数全部 ≤ 75
3. 每块网格有 1 层 UV，UV 跨度 = 真实尺寸 / `uv_tile_m`（如 0.46m 块 → 约 0.92）
4. 材质槽是 `MAT_Rock_Granite`，节点树里没有 `TEX_IMAGE`，Base Color 与 Normal 都来自节点，Roughness = 0.62 常量
5. 出图看：七块形态是否可辨、是否过于碎片化、顶面是否平整、参考人比例是否正确、矿粒密度是否一致
6. 命名 `TheFarField_<内容>_YYMMDDHHMM.blend`，存 `scenes/`，预览存 `previews/`

## 已知限制

- 只有棱角 / 圆钝两条生成分支；层状板岩、蜂窝风化石需新增分支
- 圆钝型固定 8×5 段 UV 球基底，形状变化只靠噪声与一刀浅切，重复度高
- 切口是平面切，产生的是直棱直角的撞击面，没有真实的贝壳状断口
- 盒式投影在主导轴切换的边上有 UV 接缝；矿粒在各块上的朝向不统一（无整体纹理方向约定）
- 程序化噪声不带 mipmap：远距离或 VR 斜视角下矿粒会闪烁，需要时在引擎侧配各向异性过滤或距离淡出
- 晶粒用 Voronoi 胞心做，形状是圆斑而非真实花岗岩的自形晶，凑近看偏“点状”
