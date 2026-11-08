# MUST DO FIRST

- 这是一个`blender mcp`项目
- 执行我的任务前，请先不要急着输出结果。
- 请你先识别我这个需求里所有模糊、缺失、可能影响结果的信息，并列出问题向我确认；等我补充完关键信息之后，你再正式开始执行。
- 如果你必须先做假设，请明确告诉我你做了哪些假设，不要自己硬补充。
- 执行任务时，请打开blender制作。

# RULES

- 渲染方式：用`{{渲染引擎}}`;环境`world`使用`{{环境光}}`;{{灯光策略}};`Render`设置`Film`的`Transparent`{{透明设置}}。
- 视窗预览：为`{{目标平台}}`平台制作素材，`View`的`Focal Length`使用`{{焦距}}`进行模拟。
- 比例尺参照：{{比例参照}}。{{比例折算}}
- 文档命名：`{{项目名}}_<本次修改内容>_YYMMDDHHMM.blend`。`{{项目名}}`为项目总名称，下划线后的字段说明该文件改了什么，末尾10位为时间纪要（年月日时分）。
- 建模面规则：请使用{{建模面}}建模。

# STYLE

- 风格：{{风格关键词}}。
- 建模倒角：{{倒角策略}}。
- 不规则与随机性：{{破损模式}}。
- 材质：{{材质策略}}

# SETUP

- 依赖：Blender 3.0+、uv、`mcp-for-blender`（原 `blender-mcp`）：https://github.com/ahujasid/mcp-for-blender 。
- 安装：`uvx mcp-for-blender setup` 自动配置客户端与 addon；手动为 `uvx mcp-for-blender install-addon`，再到 `Edit → Preferences → Add-ons` 启用 `Interface: MCP for Blender`。
- 连接：开启 Blender 后 addon 自动启动 socket 服务，默认 `localhost:9876`；N 面板 → `MCP for Blender` → `Start MCP Server` 可手动启动。
- 验证：任务开始前先确认连接（`get_addon_status`、`get_scene_info`），再读取当前文件与对象列表。
- 约束：同时只运行一个 MCP 服务实例；socket 无鉴权，仅限 localhost。

# WORKSPACE

- `scenes/`：所有 `.blend` 场景的读写目录，文件读写方式与子目录管理由用户控制，git 不负责追踪管理。
- `previews/`：视窗预览截图，用于快速确认形态与比例，git 不负责追踪管理。
- `render/`：最终渲染成图，用于交付确认，git 不负责追踪管理。
- `.screenshots/`：工具自动截图，仅本地保留，git 不负责追踪管理。
- `.skill/STARTER/assets/`：参照资产原件（`ref_human.blend`、`je_gray_02_1k.exr`），场景直接引用，不复制到项目根目录。

---

## 填写对照

| 占位符 | 默认值 | 说明 |
|---|---|---|
| `{{项目名}}` | `theme` | 同时用于文件命名，可自定义 |
| `{{建模面}}` | 四边面 | 或三角面 |
| `{{比例参照}}` | Append `.skill/STARTER/assets/ref_human.blend` 中的 `ref_human` 合集到场景内 | 可选 1m 立方体 / 无 |
| `{{比例折算}}` | 1:1 时写"真人高`1.8`米，按原尺寸放置" | 1:10 时写"真人高`1.8`米，按`1:10`折算为场景内`0.18`米" |
| `{{渲染引擎}}` | eevee | 或 cycles |
| `{{环境光}}` | `.\.skill\STARTER\assets\je_gray_02_1k.exr` | 纯色 / 无 |
| `{{灯光策略}}` | 不要加任何的灯光 | |
| `{{透明设置}}` | 开启 | |
| `{{焦距}}` | 24mm | |
| `{{目标平台}}` | pico-spatial-sdk | 或通用 |
| `{{风格关键词}}` | 由 LLM 根据用户的描述归纳 3–5 个 | 参考图时先解读再确认 |
| `{{倒角策略}}` | 允许自由发挥，不规定尺寸；人工制品的边角本就不统一 | 也可选统一倒角 |
| `{{破损模式}}` | 主动制作严重侵蚀，缺角与形体缺失并用，面数集中在破损处，边界做不规则抖动 | 轻微磨损 / 完好 |
| `{{材质策略}}` | 白模阶段只用默认 pbr 素模，颜色默认，粗糙度与金属度可调；白模验证通过后再做材质整体调整。 | 或改为白模验证后从 Poly Haven 取贴图 |
