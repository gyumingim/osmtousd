"""
Procedural facade texture generator.
Each texture = one window bay (3m wide) x one floor (3m tall), 1024x1024.
UV tiling handles repeated windows across building width and height.
"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

RES = 1024
TEXTURE_DIR = os.path.join(os.path.dirname(__file__), "textures")

# Bay and floor dimensions (meters) — affects UV tiling scale
BAY_WIDTH = 3.0
FLOOR_HEIGHT = 3.0


def _fbm(h, w, scale=6, octaves=4, seed=0):
    """Fractal Brownian Motion noise for surface texture."""
    rng = np.random.RandomState(seed)
    result = np.zeros((h, w), dtype=np.float32)
    amp = 1.0
    total = 0.0
    for octave in range(octaves):
        freq = 2 ** octave
        sh = max(2, h // (scale // freq + 1))
        sw = max(2, w // (scale // freq + 1))
        n = rng.rand(sh, sw).astype(np.float32)
        n_img = Image.fromarray((n * 255).astype(np.uint8))
        n_big = np.array(n_img.resize((w, h), Image.BILINEAR)) / 255.0
        result += n_big * amp
        total += amp
        amp *= 0.5
    return result / total


def _apply_noise(base_rgb, noise, strength):
    arr = np.full((RES, RES, 3), base_rgb, dtype=np.float32)
    arr += (noise[:, :, np.newaxis] * 2 - 1) * strength
    return np.clip(arr, 0, 255).astype(np.uint8)


def _draw_window(draw, x0, y0, x1, y1, glass_color, frame_color,
                 blind_prob=0.4, rng=None):
    if rng is None:
        rng = np.random.RandomState()
    fw = max(2, (x1 - x0) // 12)  # frame width
    draw.rectangle([x0, y0, x1, y1], fill=frame_color)
    gx0, gy0, gx1, gy1 = x0 + fw, y0 + fw, x1 - fw, y1 - fw
    if rng.rand() < blind_prob:
        # Partially closed blind — lighter tint
        blind_h = rng.randint(int((gy1 - gy0) * 0.2), int((gy1 - gy0) * 0.8))
        draw.rectangle([gx0, gy0, gx1, gy0 + blind_h],
                       fill=tuple(min(255, c + 60) for c in glass_color))
        draw.rectangle([gx0, gy0 + blind_h, gx1, gy1], fill=glass_color)
    else:
        draw.rectangle([gx0, gy0, gx1, gy1], fill=glass_color)


# ── Type-specific generators ─────────────────────────────────────────────────

def _residential(seed=0):
    """Concrete facade with window grid. Color varies by seed."""
    rng = np.random.RandomState(seed)
    palette = [
        (195, 188, 178),  # warm gray
        (185, 195, 200),  # cool gray
        (200, 190, 175),  # beige
    ]
    base_color = palette[seed % len(palette)]
    noise = _fbm(RES, RES, scale=8, seed=seed)
    base = _apply_noise(base_color, noise, strength=18)
    img = Image.fromarray(base)
    draw = ImageDraw.Draw(img)

    # Floor separator line (bottom edge)
    draw.rectangle([0, RES - 8, RES, RES], fill=(60, 60, 60))

    # Window: centered, ~55% width, ~55% height of cell
    margin_x = int(RES * 0.22)
    margin_y = int(RES * 0.20)
    glass = (
        rng.randint(80, 120), rng.randint(120, 160), rng.randint(160, 210)
    )
    frame = (80, 80, 80)
    _draw_window(draw, margin_x, margin_y, RES - margin_x, RES - margin_y - 8,
                 glass_color=glass, frame_color=frame,
                 blind_prob=0.45, rng=rng)

    # Air conditioner box on some cells
    if rng.rand() < 0.3:
        ax = rng.randint(margin_x, RES - margin_x - 60)
        draw.rectangle([ax, RES - margin_y - 8, ax + 55, RES - 8],
                       fill=(150, 150, 155))

    return img.filter(ImageFilter.GaussianBlur(0.5))


def _commercial(seed=0):
    """Glass curtain wall — large panes, steel frame."""
    rng = np.random.RandomState(seed)
    frame_color = (70, 75, 80)
    frame_w = 14

    img = Image.new("RGB", (RES, RES), frame_color)
    draw = ImageDraw.Draw(img)

    # Glass pane (nearly full cell minus frame)
    gx0, gy0 = frame_w, frame_w
    gx1, gy1 = RES - frame_w, RES - frame_w

    # Reflection gradient: brighter at top
    base_blue = rng.randint(90, 130)
    for y in range(gy0, gy1):
        t = (y - gy0) / (gy1 - gy0)
        r = int((base_blue + 30) * (1 - t * 0.3))
        g = int((base_blue + 50) * (1 - t * 0.2))
        b = int((base_blue + 90) * (1 - t * 0.1))
        draw.line([(gx0, y), (gx1, y)], fill=(
            min(255, r), min(255, g), min(255, b)
        ))

    # Reflection highlight streak
    if rng.rand() < 0.5:
        sx = rng.randint(gx0, gx1 - 40)
        for i in range(30):
            draw.line([(sx + i, gy0), (sx + i, gy1)],
                      fill=(255, 255, 255))

    # Mullion cross
    mid_x, mid_y = RES // 2, RES // 2
    draw.rectangle([mid_x - 3, gy0, mid_x + 3, gy1], fill=frame_color)
    draw.rectangle([gx0, mid_y - 3, gx1, mid_y + 3], fill=frame_color)

    return img


def _industrial(seed=0):
    """Corrugated metal panel with few small windows."""
    rng = np.random.RandomState(seed)
    palette = [(130, 130, 135), (120, 115, 110), (115, 120, 125)]
    base_color = palette[seed % len(palette)]

    # Corrugated effect via vertical sin stripes
    arr = np.zeros((RES, RES, 3), dtype=np.uint8)
    noise = _fbm(RES, RES, scale=4, seed=seed)
    for x in range(RES):
        t = (np.sin(x / RES * np.pi * 24) + 1) / 2
        shade = int(base_color[0] + t * 22 - 11)
        col = np.clip(
            shade + (noise[:, x] * 2 - 1) * 12, 0, 255
        ).astype(np.uint8)
        arr[:, x, 0] = col
        arr[:, x, 1] = np.clip(
            base_color[1] + t * 18 - 9 + (noise[:, x] * 2 - 1) * 12,
            0, 255).astype(np.uint8)
        arr[:, x, 2] = np.clip(
            base_color[2] + t * 18 - 9 + (noise[:, x] * 2 - 1) * 12,
            0, 255).astype(np.uint8)

    # Rust spots
    rust_noise = _fbm(RES, RES, scale=3, seed=seed + 50)
    rust_mask = rust_noise > 0.78
    arr[rust_mask, 0] = np.clip(
        arr[rust_mask, 0].astype(int) + 40, 0, 255).astype(np.uint8)
    arr[rust_mask, 1] = np.clip(
        arr[rust_mask, 1].astype(int) - 15, 0, 255).astype(np.uint8)
    arr[rust_mask, 2] = np.clip(
        arr[rust_mask, 2].astype(int) - 20, 0, 255).astype(np.uint8)

    img = Image.fromarray(arr)
    draw = ImageDraw.Draw(img)

    # Rare small windows near top (~20% chance per cell)
    if rng.rand() < 0.20:
        wx = rng.randint(int(RES * 0.25), int(RES * 0.65))
        draw.rectangle([wx, int(RES * 0.12), wx + 80, int(RES * 0.32)],
                       fill=(40, 50, 60))

    # Horizontal panel joints
    for fy in [RES // 3, 2 * RES // 3]:
        draw.line([(0, fy), (RES, fy)], fill=(50, 50, 50), width=3)

    return img.filter(ImageFilter.GaussianBlur(0.4))


def _educational(seed=0):
    """Brick facade with regular windows."""
    rng = np.random.RandomState(seed)
    brick_colors = [
        (165, 80, 60),   # red brick
        (175, 140, 100),  # tan brick
        (130, 110, 90),   # brown brick
    ]
    brick_c = brick_colors[seed % len(brick_colors)]
    arr = np.zeros((RES, RES, 3), dtype=np.uint8)
    noise = _fbm(RES, RES, scale=5, seed=seed)

    brick_h = RES // 14
    brick_w = int(brick_h * 2.2)
    for row in range(RES // brick_h + 1):
        y0 = row * brick_h
        offset = (brick_w // 2) if row % 2 else 0
        for col in range(-1, RES // brick_w + 2):
            x0 = col * brick_w + offset
            x1 = x0 + brick_w - 3
            y1 = y0 + brick_h - 2
            x0c = max(0, x0)
            x1c = min(RES, x1)
            y0c = max(0, y0)
            y1c = min(RES, y1)
            if x0c < x1c and y0c < y1c:
                n_val = noise[y0c:y1c, x0c:x1c]
                r = np.clip(brick_c[0] + (n_val * 2 - 1) * 20, 0, 255)
                g = np.clip(brick_c[1] + (n_val * 2 - 1) * 15, 0, 255)
                b = np.clip(brick_c[2] + (n_val * 2 - 1) * 15, 0, 255)
                arr[y0c:y1c, x0c:x1c, 0] = r.astype(np.uint8)
                arr[y0c:y1c, x0c:x1c, 1] = g.astype(np.uint8)
                arr[y0c:y1c, x0c:x1c, 2] = b.astype(np.uint8)

    img = Image.fromarray(arr)
    draw = ImageDraw.Draw(img)

    margin_x = int(RES * 0.20)
    margin_y = int(RES * 0.20)
    glass = (
        rng.randint(100, 130), rng.randint(140, 170), rng.randint(170, 210)
    )
    _draw_window(draw, margin_x, margin_y, RES - margin_x, RES - margin_y,
                 glass_color=glass, frame_color=(60, 55, 50), rng=rng)

    return img.filter(ImageFilter.GaussianBlur(0.4))


def _medical(seed=0):
    """Clean white tile facade."""
    rng = np.random.RandomState(seed)
    noise = _fbm(RES, RES, scale=6, seed=seed)
    base = _apply_noise((238, 236, 232), noise, strength=8)
    img = Image.fromarray(base)
    draw = ImageDraw.Draw(img)

    tile_size = RES // 8
    for x in range(0, RES, tile_size):
        draw.line([(x, 0), (x, RES)], fill=(200, 200, 200), width=2)
    for y in range(0, RES, tile_size):
        draw.line([(0, y), (RES, y)], fill=(200, 200, 200), width=2)

    margin_x = int(RES * 0.18)
    margin_y = int(RES * 0.18)
    glass = (140, 175, 210)
    _draw_window(draw, margin_x, margin_y, RES - margin_x, RES - margin_y,
                 glass_color=glass, frame_color=(160, 160, 165), rng=rng)

    return img


def _asphalt(seed=0):
    """Dark asphalt road surface with aggregate noise and faint wear marks."""
    rng = np.random.RandomState(seed)
    palette = [(55, 55, 58), (50, 50, 54), (60, 58, 55)]
    base_color = palette[seed % len(palette)]
    noise = _fbm(RES, RES, scale=3, octaves=5, seed=seed)
    arr = _apply_noise(base_color, noise, strength=12)

    # Coarse aggregate speckling
    img = Image.fromarray(arr)
    draw = ImageDraw.Draw(img)
    agg_noise = _fbm(RES, RES, scale=2, seed=seed + 10)
    for _ in range(400):
        x = rng.randint(0, RES)
        y = rng.randint(0, RES)
        v = int(agg_noise[y % RES, x % RES] * 30)
        r = rng.randint(1, 3)
        c = base_color[0] + v + rng.randint(-5, 5)
        draw.ellipse([x - r, y - r, x + r, y + r],
                     fill=(min(255, max(0, c)),) * 3)

    # Faint wear track (lighter strip down center)
    cx = RES // 2
    wear_w = int(RES * 0.15)
    for x in range(cx - wear_w, cx + wear_w):
        t = 1.0 - abs(x - cx) / wear_w
        for y in range(RES):
            px = img.getpixel((x, y))
            worn = tuple(min(255, int(c + t * 8)) for c in px)
            draw.point((x, y), fill=worn)

    return img.filter(ImageFilter.GaussianBlur(0.3))


def _generic(seed=0):
    rng = np.random.RandomState(seed)
    noise = _fbm(RES, RES, scale=6, seed=seed)
    base = _apply_noise((178, 172, 165), noise, strength=15)
    img = Image.fromarray(base)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, RES - 6, RES, RES], fill=(50, 50, 50))
    margin_x = int(RES * 0.22)
    margin_y = int(RES * 0.22)
    glass = (90, 130, 170)
    _draw_window(draw, margin_x, margin_y, RES - margin_x, RES - margin_y - 6,
                 glass_color=glass, frame_color=(80, 80, 80), rng=rng)
    return img.filter(ImageFilter.GaussianBlur(0.4))


# Public API

_GENERATORS = {
    "residential": _residential,
    "commercial":  _commercial,
    "industrial":  _industrial,
    "educational": _educational,
    "medical":     _medical,
    "generic":     _generic,
    "asphalt":     _asphalt,
}

_VARIATIONS = 4  # texture variations per type

# Map OSM building tag → style
OSM_STYLE = {
    "apartments": "residential", "residential": "residential",
    "house": "residential",      "dormitory": "residential",
    "commercial": "commercial",  "retail": "commercial",
    "office": "commercial",      "hotel": "commercial",
    "motel": "commercial",
    "university": "educational", "school": "educational",
    "kindergarten": "educational",
    "hospital": "medical",       "clinic": "medical",
    "industrial": "industrial",  "warehouse": "industrial",
    "public": "generic",         "government": "generic",
    "train_station": "generic",  "yes": "generic",
}

# Map Vworld usability code prefix → style
VWORLD_STYLE = {
    "01": "residential", "02": "commercial", "03": "commercial",
    "04": "industrial",  "05": "educational", "06": "medical",
    "08": "generic",     "10": "generic",
}


def osm_style(building_tag: str) -> str:
    return OSM_STYLE.get(str(building_tag), "generic")


def vworld_style(usability_code) -> str:
    if usability_code is None:
        return "generic"
    code = str(usability_code)[:2]
    return VWORLD_STYLE.get(code, "generic")


def get_texture_path(style: str, variation: int = 0) -> str:
    return os.path.join(TEXTURE_DIR, f"{style}_{variation % _VARIATIONS}.png")


def generate_all_textures(force=False):
    """Pre-generate all textures to disk. Safe to call multiple times."""
    os.makedirs(TEXTURE_DIR, exist_ok=True)
    for style, gen_fn in _GENERATORS.items():
        for v in range(_VARIATIONS):
            path = get_texture_path(style, v)
            if not force and os.path.exists(path):
                continue
            img = gen_fn(seed=v)
            img.save(path)
            print(f"  generated: {os.path.basename(path)}")
