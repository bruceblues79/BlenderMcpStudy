# Blender MCP Study

面向 Blender MCP 的项目初始化技能（STARTER）：把每次口头交代的建模与渲染规范，固化成一份可复用的项目级 `AGENTS.md`。

## 解决的问题

- 每个新项目都要重复交代渲染引擎、比例尺、命名规则、风格倾向
- 规范散落在对话里，换会话就丢
- agent 对"场地多大、人物多高、文件存哪"理解不一致

STARTER 把这些变成一次性的向导问答，产出确定的 `AGENTS.md`，并按需给出一套面向非美术用户的建模协作流程建议。

## 使用方法

1. 安装依赖：`uvx mcp-for-blender setup`，并在 Blender 的 `Edit → Preferences → Add-ons` 启用 `Interface: MCP for Blender`
2. 把本仓库的 `.skill/` 整个目录复制到你的 Blender 项目根目录
3. 告诉 agent：读 `.skill/STARTER/SKILL.md` 并执行
4. 按向导逐项确认，每项都有默认值，可直接回"默认"

## 会产生什么效果

技能执行后会完成：

- 建立 `scenes/`、`previews/`、`render/` 三个工作目录
- 生成项目级 `AGENTS.md`，内容包含：
  - 固定不变的 `MUST DO FIRST` 工作协议（先提问、再声明假设、再动手）
  - 渲染规则（EEVEE、环境光、无额外灯光、Film 透明）
  - 比例尺参照（1.8m 人形参照物，按缩放比折算）
  - 文件命名规则（项目名 + 修改内容 + 时间戳）
  - 风格、倒角、破损、材质四类视觉规范
  - `SETUP`（建议性提醒，不写机器相关配置）与 `WORKSPACE` 说明
- 生成后自动通读一遍 `AGENTS.md` 做自检：无残留占位符、路径存在、口径一致、规则不冲突
- 问卷结束后回执一段推荐工作流（需求翻译 → 比例定锚 → 白模分块 → 视窗校验 → 破损风格 → 渲染交付），仅作建议，用户可随时换节奏

之后的每次建模任务，agent 都会按这份约定执行，不需要再重复交代。

`AGENTS.md` 属于项目本地配置，不进入版本库；仓库只维护技能本身。

## 目录结构

```
.skill/STARTER/
├── SKILL.md                       向导主流程
├── assets/
│   ├── ref_human.blend            1.8m 人形比例参照
│   └── je_gray_02_1k.exr          Poly Haven 森林环境 HDRI
└── references/
    ├── AGENTS_TEMPLATE.md         带占位符的模板与填写对照
    └── MCP_SETUP.md               前置依赖、开工自检与跨平台启动
```

## 前置条件

- Blender 5.2 LTS+
- uv
- [mcp-for-blender](https://github.com/ahujasid/mcp-for-blender)（原 `blender-mcp`）

## 许可证

MIT
