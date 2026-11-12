# 高原苔地地块（ground）

在 Blender 内程序化生成“高原白桦林林下苔地”地块：16m 平板地块 + 纯节点材质。
不依赖任何外部贴图或中间格式，所有形态与材质参数固化在 `presets/*.json` 中，preset 是唯一真源。

## 语义

- 地貌：近寒带高原 / 白桦林林下，苔藓为主、腐殖土与枯叶碎屑交织、局部裸砾石与地衣色斑。
- 风格：荒野、少人工痕迹；色彩低饱和，明度偏暗，不用鲜艳绿。
- 适用范围：可随湿度/踩踏/海拔退化为稀疏植被地表，甚至无苔藓，但不脱离高原白桦林苔地的色相与物质构成（腐殖土 + 枯叶 + 砾石）。

## 产出

`groundgen.build(spec)` 返回一个地块对象：

- 几何：16m × 16m 板体（三角面数随 `tile.grid` 变化），顶面严格位于 z=0，向下挤出 `tile.thickness_m` 并封底；无起伏；
- UV：米制平铺，`uv_per_m=1` 时 U/V 跨度为 0–16 m，供导出/引擎侧使用；
- 材质：`M_Ground_<type>`，全部为 ShaderNode，无 `TEX_IMAGE`；
- 坐标：材质以 `Geometry > Position`（世界空间）驱动，纹理按真实米制分布，相邻地块拼接无缝、无重复。

## 参数（preset）

```
seed                      唯一随机源：相同 seed 结果完全一致
tile.size_m               地块边长（默认 16）
tile.thickness_m          向下挤出的板厚（默认 0.2，顶面恒在 z=0）
tile.grid                 顶面分段数（默认 6，1 为单面）
tile.uv_per_m             UV 每米重复数（默认 1）
material.roughness        粗糙度常量（默认 0.93）
material.soil.*           腐殖土三段色 + 噪声尺度
material.moss.weight      苔藓覆盖度 0–1
material.litter.weight    枯叶聚簇覆盖度 0–1
material.lichen.weight    地衣/干草色斑覆盖度 0–1
material.gravel.weight    碎砾覆盖度 0–1
material.grain.*          细颗粒色噪
material.bump.*           五层法线：中尺度隆起 / 微观颗粒 / 叶片 / 卵石 / 极细颗粒
```

权重到阈值的映射（保证任意中间档都成立）：

```
苔藓区噪声阈值      low = 0.5 - 0.21 * moss.weight
枯叶聚簇阈值        low = 0.5 - 0.28 * litter.weight
地衣斑块阈值        low = 0.68 - 0.32 * lichen.weight
碎砾聚簇阈值        low = 0.66 - 0.64 * gravel.weight
```

任一 weight 设为 0 时，该层由 `Mul_<Layer>Enable` 节点整体关闭（因子乘 0），用于无苔藓、无落叶等退化档；0 以上按上式线性收缩。

## 退化轴

单轴衰减，而不是并列多套材质：

- 苔藓减少时腐殖土、枯叶、砾石自然显出，色相保持不变；
- 任何中间状态都成立，适合按世界坐标混档或流式地块边缘过渡。

已提供档位：

| preset | 说明 |
| --- | --- |
| `ground_plateau_moss` | 标准档，高原苔地（当前基线） |

后续可派生（只需复制 preset 改权重，不改代码）：

- 稀疏档：`moss 0.15 / litter 0.9 / lichen 0.2 / gravel 0.5`
- 无苔藓档：`moss 0 / litter 1.0 / lichen 0.1 / gravel 0.7`

## 约束

- 禁止置换、起伏或额外厚度；
- 禁止 `TEX_IMAGE` 与外部贴图，材质参数只写在 preset；
- 禁止倒角；
- 地块对象命名 `Tile_Ground`，材质命名 `M_Ground_<type>`；
- 同 seed 必须完全一致，随机只允许来自 seed。

## 用法

在 Blender 内：

```python
import sys
sys.path.insert(0, ".skills/ground/scripts")
import groundgen

spec = groundgen.load_spec(".skills/ground/presets/ground_plateau_moss.json")
objs, report = groundgen.build(spec, collection=groundgen.ensure_collection("Ground"))
```

命令行出预览（不保存 .blend）：

```
blender -b --factory-startup --python .skills/ground/scripts/preview.py -- --preset ground_plateau_moss
```

预览规格：EEVEE、24mm、45° 俯视、`qwantani_noon_puresky_1k.exr` 环境、Film Transparent、含 `ref_human` 与灰色背板。

## 文件

```
.skills/ground/
├── SKILL.md
├── presets/ground_plateau_moss.json
└── scripts/
    ├── groundgen.py   地块与材质构建
    └── preview.py     预览出图
```
