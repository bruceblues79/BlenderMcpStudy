# mcp-for-blender 配置参考

## 项目信息

- 仓库：https://github.com/ahujasid/mcp-for-blender （原 `blender-mcp`）
- PyPI 包：`mcp-for-blender`（原 `blender-mcp`，旧命令 `uvx blender-mcp` 仍可用）
- 依赖：Blender 5.2 LTS+、Python 3.10+、uv
- 默认端口：`9876`

## 安装

自动（推荐）：

```
uvx mcp-for-blender setup
```

Windows 也可用一行脚本：

```
powershell -ExecutionPolicy ByPass -c "irm https://www.mcp-for-blender.com/install.ps1 | iex"
```

手动：

```
uvx mcp-for-blender install-addon
```

然后在 Blender 中 `Edit → Preferences → Add-ons` 启用 `Interface: MCP for Blender`。

## 客户端配置

```json
{
  "mcpServers": {
    "blender": {
      "command": "uvx",
      "args": ["mcp-for-blender"]
    }
  }
}
```

机器上有 conda / pyenv 时固定解释器：

```json
{
  "mcpServers": {
    "blender": {
      "command": "uvx",
      "args": ["--python", "3.11", "mcp-for-blender"],
      "env": { "UV_PYTHON_PREFERENCE": "only-managed" }
    }
  }
}
```

## 连接与验证

1. 打开 Blender，addon 自动启动 socket 服务
2. 3D 视口按 `N` → `MCP for Blender` 标签 → 未运行时点 `Start MCP Server`
3. 客户端调用 `get_addon_status`，再调用 `get_scene_info` 确认能读到场景

## 由 Agent 启动 Blender（Windows）

Agent 自己拉起 Blender 时，必须用脱离当前命令生命周期的方式，否则进程会在命令结束后被回收，表现为「启动后十几秒自动消失」：

```powershell
$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
  CommandLine = '"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" "scenes\xxx.blend"'
}
$r.ReturnValue   # 0 = 启动成功
```

启动后等 10–20 秒，再依次确认：`Get-NetTCPConnection -LocalPort 9876`、`get_addon_status`、`get_scene_info`。

不要用 `Start-Process` 启动 Blender（进程会随命令结束被回收）。`Get-Process blender` 没有输出说明进程已退出。

## 环境变量

| 变量 | 默认 | 用途 |
|---|---|---|
| `BLENDER_HOST` | `localhost` | Blender 地址 |
| `BLENDER_PORT` | `9876` | 端口，多开 Blender 时逐个指定 |
| `BLENDER_MCP_SAFE_MODE` | 关 | 设为 `1` 时执行前校验脚本 |

## 常见故障

| 现象 | 处理 |
|---|---|
| `spawn uvx ENOENT` | 用 `where uvx` 查绝对路径填入 `command`，或改用 `cmd /c uvx mcp-for-blender` |
| 客户端连不上 | 确认 Blender 已开、addon 已启用、端口一致；改完配置需完全退出并重启客户端 |
| 多个客户端抢连接 | 同时只运行一个 MCP 服务实例 |
| 脚本被拒 | 检查是否开启了 `BLENDER_MCP_SAFE_MODE` |
| 安装反复失败 | `uv cache clean mcp-for-blender blender-mcp` 后重试 |

## 安全

socket 无鉴权与加密，能访问该端口即可在 Blender 内执行 Python。保持 `localhost`，不要直接暴露到外网。
