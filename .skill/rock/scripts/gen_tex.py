"""ROCK 贴图生成：像素级程序化冷灰花岗岩，四边严格无缝，输出 PNG。

用法：
    blender -b --factory-startup --python .skill/rock/scripts/gen_tex.py

输出（512²，0.5m 对应 1 张图）：
    rock_granite_color.png / rock_granite_normal.png

噪声由 FFT 频域随机相位生成，天然周期，平铺无缝。
法线由高度场中心差分得到切线空间法线；粗糙度不生成贴图，走材质常数。
"""

import os
import struct
import zlib

import numpy as np

SIZE = 512
SEED = 20261111
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), "textures")


def _noise(rng, size, sx, sy, slope=1.6):
    """周期噪声：频域高斯带限 + 随机相位，IFFT 结果四边无缝。"""
    f = np.fft.fftfreq(size)
    fy = f[:, None]
    fx = f[None, :]
    amp = np.exp(-((fx / sx) ** 2 + (fy / sy) ** 2)) / (np.sqrt(fx ** 2 + fy ** 2) ** slope + 1e-4)
    amp[0, 0] = 0.0
    spec = amp * np.exp(2j * np.pi * rng.random((size, size)))
    n = np.real(np.fft.ifft2(spec))
    n -= n.min()
    return n / max(n.max(), 1e-9)


def _fbm(rng, size, layers):
    out = np.zeros((size, size))
    weight = 0.0
    for sx, sy, w in layers:
        out += _noise(rng, size, sx, sy) * w
        weight += w
    out /= weight
    n = out - out.mean()
    return n / (n.std() + 1e-6)


def _white_blur(rng, size, cutoff):
    """白噪声低通：只在 cutoff 以内保留能量，得到几像素级的均匀矿粒。"""
    f = np.fft.fftfreq(size)
    fy = f[:, None]
    fx = f[None, :]
    amp = np.exp(-((fx / cutoff) ** 2 + (fy / cutoff) ** 2))
    n = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((size, size))) * amp))
    n -= n.mean()
    return n / (n.std() + 1e-6)


def _normal(height, strength):
    gx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * 0.5
    gy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * 0.5
    n = np.stack([-gx * strength, -gy * strength, np.ones_like(height)], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n * 0.5 + 0.5


def _srgb(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def _write_png(path, rgb):
    h, w, _ = rgb.shape
    rows = b"".join(b"\x00" + rgb[y].tobytes() for y in range(h))

    def chunk(tag, data):
        tag = tag.encode("ascii")
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk("IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk("IDAT", zlib.compress(rows, 9))
    png += chunk("IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)


def granite(size, seed):
    rng = np.random.default_rng(seed)
    # 中低频色斑：整体灰调起伏，避免平铺感
    mottle = _fbm(rng, size, [(0.016, 0.016, 0.55), (0.045, 0.045, 0.30), (0.110, 0.110, 0.15)])
    # 毫米级矿粒：白噪声低通，得到 2–4px 的碎粒而不是大斑块
    fine = _white_blur(rng, size, 0.26)
    fine2 = _white_blur(rng, size, 0.38)
    light = np.clip((fine - 1.10) / 0.45, 0.0, 1.0) ** 0.85
    dark = np.clip((fine2 - 1.20) / 0.45, 0.0, 1.0) ** 0.85

    # 底色：冷灰花岗岩（线性空间），蓝灰倾向
    grey = 0.230 + 0.032 * mottle + 0.022 * fine
    col = np.stack([grey * 0.950, grey * 0.985, grey * 1.045], axis=-1)
    # 长石亮斑偏冷白，云母暗斑近炭黑
    lite = np.array([0.480, 0.500, 0.530])
    darkc = np.array([0.014, 0.016, 0.020])
    a_l = np.clip(light * 0.90, 0.0, 1.0)[..., None]
    a_d = np.clip(dark * 0.90, 0.0, 1.0)[..., None]
    col = col * (1.0 - a_l) + lite * a_l
    col = col * (1.0 - a_d) + darkc * a_d

    height = 0.30 * fine + 0.35 * fine2 + 0.30 * light - 0.30 * dark
    nrm = _normal(height, 0.9)
    return col, nrm


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    col, nrm = granite(SIZE, SEED)
    cpath = os.path.join(OUT_DIR, "rock_granite_color.png")
    npath = os.path.join(OUT_DIR, "rock_granite_normal.png")
    _write_png(cpath, np.round(_srgb(col) * 255).astype(np.uint8))
    _write_png(npath, np.round(np.clip(nrm, 0.0, 1.0) * 255).astype(np.uint8))
    print("TEX", cpath)
    print("TEX", npath)


if __name__ == "__main__":
    main()
