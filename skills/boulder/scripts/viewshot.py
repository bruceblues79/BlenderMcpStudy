"""视窗截图助手（走 MCP addon 的 GPUOffScreen，出图不含 UI）。

坑位记录：region_3d 的 view_location / view_rotation / view_distance 是惰性更新，
不先 redraw_timer 就截图，拿到的是上一帧的机位矩阵。这里固定先刷新再截。
"""

import bpy
from mathutils import Vector


def find_view3d():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    return space
    raise RuntimeError("当前窗口里找不到 3D 视窗")


def setup(lens=24.0):
    """按项目预览规范设置视窗：24mm、Material Preview、Scene World、叠加层开。"""
    space = find_view3d()
    space.lens = lens
    space.shading.type = "MATERIAL"
    space.shading.use_scene_world = True
    space.overlay.show_overlays = True
    return space


def aim(target, direction, distance, perspective="PERSP"):
    """direction 是视线方向（从机位指向目标），会归一化。"""
    space = find_view3d()
    region = space.region_3d
    region.view_perspective = perspective
    region.view_location = Vector(target)
    region.view_rotation = Vector(direction).normalized().to_track_quat("-Z", "Y")
    region.view_distance = distance
    return space


def shot(filepath, max_size=1600):
    """先强制重绘刷新视图矩阵，再截取干净视窗图。"""
    server = getattr(bpy.types, "blendermcp_server", None)
    if server is None:
        raise RuntimeError("MCP addon 未运行，无法用 GPUOffScreen 截图")
    bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
    return server.get_viewport_screenshot(max_size=max_size, filepath=filepath)
