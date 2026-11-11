"""BIRCH 贴图生成：像素级程序化假纹理，四边严格无缝，输出 PNG。

用法：
    blender -b --factory-startup --python .skill/birch/scripts/gen_tex.py

输出（512²，1m 对应 1 张图）：
    birch_bark_color.png / birch_bark_normal.png
    birch_leaf_color.png / birch_leaf_normal.png

所有噪声由 FFT 频域随机相位生成，天然周期，平铺无缝。
法线由高度场做中心差分得到切线空间法线；粗糙度不生成贴图，走常数。
"""

import os
import struct
import zlib

import numpy as np

SIZE = 512
SEED = 20261110
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), "assets", "textures")


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


def _lenticels(rng, size, rows=62):
    """横向皮孔：每行若干短横条，x 方向环绕，保证左右无缝。"""
    m = np.zeros((size, size), dtype=np.float64)
    for i in range(rows):
        y0 = (i + rng.uniform(-0.35, 1.35)) / rows * size
        for _ in range(int(rng.integers(1, 3))):
            length = rng.uniform(0.030, 0.100) * size
            x0 = rng.uniform(0, size)
            bow = rng.uniform(-0.8, 0.8)
            strength = rng.uniform(0.55, 1.0)
            xs = np.arange(max(2, int(length)))
            ys_line = y0 + np.sin(xs / max(length - 1, 1) * np.pi) * bow
            xi = np.round(x0 + xs).astype(int) % size
            for thick in (0, 1):
                yi = np.clip(np.round(ys_line).astype(int) + thick, 0, size - 1)
                np.add.at(m, (yi, xi), strength)
    m = np.clip(m, 0.0, 1.0)
    # 只软化一次，保留约 3px 的锐利皮孔
    return (m + np.roll(m, 1, axis=0) + np.roll(m, -1, axis=0)) / 3.0


def _wobble(rng, size, amp, harmonics=6):
    """周期正弦叠加的横向抖动曲线，首尾自然接上。"""
    y = np.arange(size) / size
    out = np.zeros(size)
    for k in range(1, harmonics + 1):
        out += np.sin(2 * np.pi * k * y + rng.uniform(0, 2 * np.pi)) / k
    out /= np.abs(out).max() + 1e-6
    return out * amp


def _cracks(rng, size, count=13):
    """纵向裂纹：带抖动、沿 V 断续的竖线，U/V 两向无缝。"""
    m = np.zeros((size, size), dtype=np.float64)
    x = np.arange(size)[None, :]
    for i in range(count):
        x0 = (i + rng.uniform(0.2, 0.8)) / count * size
        center = (x0 + _wobble(rng, size, rng.uniform(4.0, 9.0)))[:, None]
        dist = np.abs(((x - center + size / 2.0) % size) - size / 2.0)
        line = np.exp(-(dist / rng.uniform(1.0, 2.0)) ** 2)
        # 短段化：低频遮罩把裂纹切成断续的伤口
        fade = _noise(rng, size, 0.015, 0.045)
        fade = np.clip((fade - 0.52) / 0.30, 0.0, 1.0) ** 0.85
        m += line * fade * rng.uniform(0.70, 1.0)
    return np.clip(m, 0.0, 1.0)


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
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(rows, 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)


def bark(size, seed):
    rng = np.random.default_rng(seed)
    # 中低频斑驳 + 细颗粒：树皮灰白浓淡，绝不出现大块污斑
    mottle = _fbm(rng, size, [(0.030, 0.070, 0.6), (0.120, 0.180, 0.4)])
    grain = _fbm(rng, size, [(0.280, 0.380, 1.0)])
    lent = _lenticels(rng, size)
    crack = _cracks(rng, size)

    # 底色：白桦灰白（线性空间），保留中频浓淡以免成片死白
    grey = 0.680 + 0.075 * mottle + 0.020 * grain
    col = np.stack([grey, grey * 0.988, grey * 0.960], axis=-1)
    # 纵向裂纹压暗
    col *= (1.0 - 0.88 * crack[..., None])
    # 皮孔近黑褐
    dark = np.array([0.032, 0.028, 0.024])
    a = np.clip(lent * 1.45, 0.0, 1.0)[..., None]
    col = col * (1.0 - a) + dark * a

    height = (0.25 * grain - 0.75 * crack - 0.55 * lent + 0.06 * mottle)
    nrm = _normal(height, 2.2)
    return col, nrm


def leaf(size, seed):
    rng = np.random.default_rng(seed)
    mott = _fbm(rng, size, [(0.018, 0.018, 0.55), (0.060, 0.060, 0.30), (0.160, 0.160, 0.15)])
    # 夏季白桦叶：深绿到偏黄绿之间随色斑过渡（线性空间）
    deep = np.array([0.105, 0.245, 0.034])
    pale = np.array([0.195, 0.365, 0.058])
    t = np.clip(0.5 + 0.38 * mott, 0.0, 1.0)[..., None]
    col = deep * (1.0 - t) + pale * t
    # 主脉：U≈0.5 轻微压暗（叶 UV 的 V 沿叶轴）
    x = (np.arange(size)[None, :] + 0.5) / size
    midrib = np.exp(-((x - 0.5) / 0.016) ** 2)
    col *= (1.0 - 0.20 * midrib)[..., None]

    height = 0.55 * mott - 0.35 * midrib
    nrm = _normal(height, 0.9)
    return col, nrm


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for tag, fn, s in (("bark", bark, SEED), ("leaf", leaf, SEED + 7)):
        col, nrm = fn(SIZE, s)
        cpath = os.path.join(OUT_DIR, "birch_%s_color.png" % tag)
        npath = os.path.join(OUT_DIR, "birch_%s_normal.png" % tag)
        _write_png(cpath, np.round(_srgb(col) * 255).astype(np.uint8))
        _write_png(npath, np.round(np.clip(nrm, 0.0, 1.0) * 255).astype(np.uint8))
        print("TEX", cpath)
        print("TEX", npath)


if __name__ == "__main__":
    main()
