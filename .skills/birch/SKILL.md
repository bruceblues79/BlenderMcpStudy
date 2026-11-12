---
name: "birch"
description: "白桦树生成器：按 preset 参数在 Blender 里生成枝干与叶簇，同一 seed 必然同结果。当用户要生成/调整白桦树、改形态、调茂密度、切换季相时调用。"
---

# 白桦树生成 — 程序化生成器

## 触发条件

- 要生成一棵或多棵树木（白桦为首个树种）
- 要调整形态：高度、分枝数、分枝角、叶簇
- 要调整茂密度（`canopy`）或季相（`season`）
- 要把一套树木参数固化成可复现的 preset

不负责地形摆放与渲染风格；材质由生成器内置的程序化节点自动挂载。

## 文件

| 文件 | 作用 |
|---|---|
| `scripts/treegen.py` | 生成器本体 + 程序化树皮/叶片材质，纯 `bpy`，确定性 |
| `scripts/preview.py` | 批处理直出：生成 + 环境光 + 参考人 + 渲染 |
| `presets/birch.json` | 白桦标准参数 + 材质配方（定版默认） |
| `presets/birch_winter.json` | 冬季季相（叶量 0.6） |

材质由节点实时计算，**技能内不含任何贴图文件**。

## 运行

### 默认直出（离线批处理）

在项目根目录执行：

```
blender -b --factory-startup --python ".skills/birch/scripts/preview.py" -- --preset birch
```

- 默认输出 `previews/TheFarField_birch_default_birch.png`（脚本按自身位置推算项目根，不受 cwd 影响）
- 换 preset：`--preset birch_winter`
- `--out` 必须给绝对路径：Blender 的 cwd 不等于项目根，相对路径会落到别处
- 可选机位：`--cam-y`（默认 -11.0）、`--cam-z`（默认 3.6）、`--target-z`（默认 2.8）

### 在已打开的 Blender 里生成（MCP）

```python
import sys, os
SKILL = r"c:\Users\bruce\Documents\BlenderProjects\BlenderMcpStudy\.skills\birch"
sys.path.insert(0, os.path.join(SKILL, "scripts"))
import treegen

scene = bpy.data.scenes.new("BirchGen")
bpy.context.window.scene = scene

spec = treegen.load_spec(os.path.join(SKILL, "presets", "birch.json"))
objs, report = treegen.build(spec, name="Tree_Birch", collection=treegen.ensure_collection("Birch"))
```

**禁止**在会话内用 `read_factory_settings` / `read_homefile`：会重置会话并断掉 MCP 连接。先 `scenes.new()` 建新场景再生成。

`report` 含各部件面数与预算；`main()` 包装版会把同样的 report 打成 `[TREEGEN] {...}`。

## 参数：输入决定什么结果

| 参数 | 位置 | 决定 |
|---|---|---|
| `seed` | 顶层 | 唯一随机源；同 spec 同 seed 结果完全一致 |
| `height_m` | 顶层 | 主干高度，同时缩放枝长与树冠尺度 |
| `trunk.sides` | 顶层 | 主干径向边数（白桦 5） |
| `trunk.segments` | 顶层 | 主干分段，直接影响主干三角面 |
| `trunk.base_radius` / `top_radius` | 顶层 | 根径与梢径，锥化程度 |
| `trunk.lean_deg` / `bend` | 顶层 | 整体倾斜与弯曲幅度 |
| `branch.start` / `end` | 顶层 | 分枝在树干上的纵向区间（0=根 1=梢） |
| `branch.level1.count` | 顶层 | 一级分枝数量，主轴决定树冠疏密骨架 |
| `branch.level1.pitch_deg` | 顶层 | 分枝仰角区间，越小越平展 |
| `branch.level1.len_ratio` | 顶层 | 一级枝长占树高比例，决定横向铺开宽度 |
| `branch.level2.*` | 顶层 | 二级分枝数量、角度、长度衰减 |
| `canopy` | 顶层 | 0–1 茂密度；直接乘出叶片三角面预算 |
| `twig.per_tip` / `len` | 顶层 | 细枝挂点数量与长度；细枝不生成几何，只决定叶片往枝梢外延伸的距离 |
| `droop` | 顶层 | 全局重力强度，默认 1.0；内部按 一级枝 0.6 / 二级枝 0.9 / 叶片 1.0（枝梢 1.25）递增，越靠梢越垂 |
| `leaf.prototypes` | 顶层 | 叶原型序列，循环取用；决定平均面数与叶数 |
| `leaf.scale` | 顶层 | 叶片缩放，越大叶越少但仍占满预算 |
| `leaf.per_cluster` | 顶层 | 每簇叶数，簇越大越成团 |
| `leaf.cluster_spread` | 顶层 | 簇内散开半径，越小越紧密 |
| `leaf.attach.branch` / `.twig` | 顶层 | 沿枝条 / 沿细枝挂点的叶片簇数量；主干不挂叶 |
| `season.leaf_factor` | 顶层 | 叶量系数：春 0.6 / 夏 1.0 / 秋 0.7 / 冬 0.0 |
| `budget.branch_max_tri` | 顶层 | 枝干面数硬上限，超出直接抛错 |
| `budget.leaf_max_tri` | 顶层 | 满 `canopy` 时的叶片面数上限 |
| `variation.seed_stride` | 顶层 | 多棵生成时每棵的 seed 步长 |
| `variation.height` | 顶层 | 每棵高度随机浮动比例（0.10 = ±10%） |
| `variation.branch_count` | 顶层 | 每棵一级枝数量向下抖动幅度，保证不破 1000 面 |
| `material.bark.*` | 顶层 | 树皮配方：底色 `base`、浓淡 `mottle`/`grain`、皮孔 `lenticels`、裂纹 `cracks`、`bump` |
| `material.leaf.*` | 顶层 | 叶片配方：`deep`/`pale` 双绿、主脉压暗 `midrib`、逐叶随机强度 `per_leaf` |

实际叶面数 = `leaf_max_tri × canopy × season.leaf_factor`，脚本按此预算逐簇累加，超出前停止。

## 材质（程序化，无贴图）

- `MAT_Birch_Bark` / `MAT_Birch_Leaf` 由 `_ensure_materials(spec, bark_uv)` 现场构建，节点树里没有 `TEX_IMAGE`
- 树皮三层，全部按物理尺度换算（`bark_uv` 把环向周长归一，配方里的 `rows_per_m` / `per_m` / `dash_m` 是米制）：
  - 横向皮孔：`Wave(BANDS, Y)` 造行距 → `Noise` 高频在 U 上切断成短横条 → 混向近黑
  - 纵向裂纹：`Noise` 经 `Mapping` 在 U 上放大、V 上压扁 → `abs(f-0.5) < width` 取脊线，再乘低频遮罩做成断续
  - 灰白浓淡：中频 `Noise` 调制底色，`base` 为线性 RGB
- 叶片：4D `Noise` 取深浅绿过渡，`UV.x` 距 0.5 的距离出主脉并压暗
- 逐叶片随机：生成时给叶片网格写入面属性 `leaf_rand`（每片一个 0–1 随机数），材质用 `Attribute` 节点同时驱动噪声 W 与明度抖动，避免每片叶子一模一样
- 粗糙度走常量（树皮 0.9 / 叶 0.6），凹凸由 `Bump` 从同一套高度场生成


## 茂密度五档

| canopy | 观感 | 白桦叶面数（默认预算 2200） |
|---|---|---|
| 1.00 | 极密 | 2200 / 880 片 |
| 0.75 | 密 | 1650 / 660 片 |
| 0.50 | 中 | 1100 / 440 片 |
| 0.25 | 疏 | 550 / 220 片 |
| 0.10 | 极疏 | 220 / 88 片 |

同一份 preset 只改 `canopy` 即可，不要复制脚本。

## 默认直出

`presets/birch.json` 就是定版默认值（用户 2026-11-10 认可的「标准白桦树」），用户说“生成一棵树”时直接跑，不再逐项确认：

```
blender -b --factory-startup --python .skills/birch/scripts/preview.py -- --preset birch
```

标准形态基线（改动后需重新对照）：主干 76 / 枝干 630 / 叶片 2200，合计 2906 三角面（总预算 3200）；一级枝 10 条，叶 880 片，树高约 5.7m。

默认行为：生成 → 打环境光 → 摆参考人 → 渲染 `previews/TheFarField_birch_default_<preset>.png` → 退出 Blender。

规则：
- 不保存 `.blend`，脚本生成的场景一律视为试验产物
- 用 `--out` 指定别的输出路径时才覆盖默认命名
- 只有当几何结构需要变（新树种、新分级）才改 `treegen.py`；观感诉求只改 preset

## 多棵不同树

```python
results = treegen.spawn_variants(spec, count=5, spacing=2.4, x0=-4.8)
```

同一 preset 派生 N 棵：seed 按 `variation.seed_stride` 递推，高度浮动 `±variation.height`，一级枝数量只向下抖动（避免破 1000 面预算）。返回 `[(objs, report), ...]`。

## 硬约束

- 全部三角面
- 主干 5 边、次枝 3 边
- 材质必须程序化：不得引入 `TEX_IMAGE`，不得依赖 `textures/` 里的文件
- 叶片禁止朝天：生成后法线 `z > 0.25` 会被翻转，隔离校验口径是 `normal.z > 0.3` 的面数应为 0
- 主干不挂叶，叶片只挂次级枝与细枝挂点；细枝仅参与挂点计算，不生成几何
- 枝干面数超 `branch_max_tri` 抛 `RuntimeError`，不静默截断

## 验收

1. 打印 report，核对 `trunk_tri` / `branch_tri` / `leaf_tri` / `leaf_count`
2. 校验朝天叶面数为 0
3. 视窗或渲染出图，重点看：枝干是否穿透树冠、叶簇是否悬空脱离枝条、五档梯度是否可辨
4. 命名 `TheFarField_<内容>_YYMMDDHHMM.blend`，存 `scenes/`，预览存 `previews/`

## 已知限制

- 目前只有白桦一个树种；其他树种需新增 preset 并在 `treegen.py` 里加形态特化
- 叶片为单层面片，渲染背面偏暗，属白模阶段预期
- 树冠密度由预算驱动，不看真实叶面积
- 树皮 U 为环向弧长，程序化噪声在 U 回环处有一条竖缝（已确认可接受，未做 mirror UV）
- 程序化噪声不带 mipmap，远距离或 VR 斜视角下细皮孔可能闪烁
- 旧树（本改动之前生成的）没有 `leaf_rand` 面属性，材质会把逐叶随机退化成常量，需要重新生成或补写属性
