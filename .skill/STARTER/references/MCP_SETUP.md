# mcp-for-blender 前置与自检

## 依赖

- Blender 5.2 LTS+
- uv
- `mcp-for-blender`（原 `blender-mcp`）：https://github.com/ahujasid/mcp-for-blender

## 安装

```
uvx mcp-for-blender setup
```

自动写入客户端配置并安装 addon；装完在 Blender 的 `Edit → Preferences → Add-ons` 启用 `Interface: MCP for Blender`。已有 uv 的机器走到这一步就够了，不需要手写客户端 JSON。

## 开工自检

1. `get_addon_status` —— addon 是否在线
2. `get_scene_info` —— 当前文件与对象列表

连不上按顺序排查：Blender 是否在运行 → addon 是否启用 → 客户端改完配置后是否完全退出并重启。

## 由 Agent 启动 Blender

先探测 Blender 可执行文件位置，不要写死路径；再以**脱离当前命令生命周期**的方式启动，否则进程会随命令结束被回收：

- Windows：`Invoke-CimMethod -ClassName Win32_Process -MethodName Create`（`Start-Process` 启动的进程会随命令结束被回收）
- macOS：`open -a Blender --args <file.blend>` 或 `nohup <blender> <file.blend> &`
- Linux：`nohup <blender> <file.blend> >/dev/null 2>&1 &`

启动后等待 10–20 秒，再用 `get_addon_status` 确认。

## 边界

- socket 无鉴权与加密，能连上即可在 Blender 内执行 Python。保持本机使用，不要暴露到公网。
- 同时只运行一个 MCP 服务实例。
- 安装位置、端口、客户端配置因机器而异，由用户掌握，不写进项目文档。
