# MUST DO FIRST
- 这是一个`blender mcp`项目
- 执行我的任务前，请先不要急着输出结果。
- 请你先识别我这个需求里所有模糊、缺失、可能影响结果的信息，并列出问题向我确认；等我补充完关键信息之后，你再正式开始执行。
- 如果你必须先做假设，请明确告诉我你做了哪些假设，不要自己硬补充。
- 执行任务时，请打开blender制作。

# RULES
- 渲染方式：用`eevee`;环境`world`使用`.\je_gray_02_1k.exr`;不要加任何的灯光;`Render`设置`Film`的`Transparent`开启。
- 视窗预览：为`pico-spatial-sdk`平台制作素材，`View`的`Focal Length`使用`24mm`进行模拟。
- 比例尺参照：Append `ref_human.blend` 中的 `ref_human` 合集到场景内，作为人形参照物。真人高 `1.8` 米，按 `1:10` 折算为场景内 `0.18` 米。
- 文档命名：`sanctuary_<本次修改内容>_YYMMDDHHMM.blend`。`sanctuary`为项目总名称，下划线后的字段说明该文件改了什么，末尾10位为时间纪要（年月日时分）。
- 建模面规则：请使用四边面建模。

# STYLE
- 风格：这是一个上古神庙探险的奇幻写实风格。
- 建模倒角：倾向自然，禁止对物体边界添加倒角，除非用户需求。
- 不规则与随机性：物品均都有严重的历史侵蚀，意味着要主动制作破损，面数要对破损做集中的体现； 物品可以有形体上的部分缺失，体现残破感。需要边界有不规则的抖动，来体现斑驳。
- 材质：模型制作时先不考虑材质贴图，均使用默认pbr的素模，且颜色默认，粗糙度，金属度可以调整。先做白模验证，再做材质整体调整。

# SETUP
- 依赖：Blender 3.0+、uv、`mcp-for-blender`（原 `blender-mcp`）：https://github.com/ahujasid/mcp-for-blender 。
- 安装：`uvx mcp-for-blender setup` 自动配置客户端与 addon；手动为 `uvx mcp-for-blender install-addon`，再到 `Edit → Preferences → Add-ons` 启用 `Interface: MCP for Blender`。
- 连接：开启 Blender 后 addon 自动启动 socket 服务，默认 `localhost:9876`；N 面板 → `MCP for Blender` → `Start MCP Server` 可手动启动。
- 验证：任务开始前先确认连接（`get_addon_status`、`get_scene_info`），再读取当前文件与对象列表。
- 约束：同时只运行一个 MCP 服务实例；socket 无鉴权，仅限 localhost。

# WORKSPACE
- `scenes/`：所有 `.blend` 场景的读写目录，改动后另存为新文件，不覆盖已有文件。
- `previews/`：视窗预览截图，用于快速确认形态与比例。
- `render/`：EEVEE 渲染成图，用于最终交付确认。
- `.screenshots/`：工具自动截图，仅本地保留。
- `.skill/STARTER/assets/`：参照资产原件（`ref_human.blend`、`je_gray_02_1k.exr`），首次使用时复制到项目根目录。
