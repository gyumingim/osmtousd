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
    """Korean concrete apartment facade with weathering and AC units."""
    rng = np.random.RandomState(seed)
    palette = [
        (210, 205, 195),  # cream concrete
        (195, 200, 205),  # cool concrete
        (215, 205, 185),  # warm beige
        (200, 198, 192),  # neutral gray
    ]
    base_color = palette[seed % len(palette)]

    # Concrete texture: panel lines + weathering
    noise = _fbm(RES, RES, scale=6, octaves=5, seed=seed)
    streak = _fbm(RES, RES, scale=1, octaves=3, seed=seed + 3)
    arr = _apply_noise(base_color, noise, strength=14)
    # Vertical water-stain streaks
    arr = arr.astype(np.float32)
    stain_mask = streak > 0.72
    arr[stain_mask] -= 18
    arr = np.clip(arr, 0, 255).astype(np.uint8)

    img = Image.fromarray(arr)
    draw = ImageDraw.Draw(img)

    # Horizontal floor joint
    draw.rectangle([0, RES - 6, RES, RES], fill=(80, 78, 74))
    # Vertical panel joint
    draw.line([(0, 0), (0, RES)], fill=(80, 78, 74), width=5)

    # Window
    margin_x = int(RES * 0.18)
    margin_y = int(RES * 0.17)
    # Glass: slight blue tint, reflection brightness varies
    bright = rng.randint(0, 30)
    glass = (70 + bright, 100 + bright, 145 + bright)
    frame = (65, 65, 68)
    _draw_window(draw, margin_x, margin_y,
                 RES - margin_x, RES - margin_y - 6,
                 glass_color=glass, frame_color=frame,
                 blind_prob=0.5, rng=rng)

    # AC outdoor unit (60% chance, bottom of window)
    if rng.rand() < 0.6:
        aw = int(RES * 0.28)
        ah = int(RES * 0.14)
        ax = rng.choice([margin_x, RES - margin_x - aw])
        ay = RES - margin_y - ah - 6
        draw.rectangle([ax, ay, ax + aw, ay + ah], fill=(175, 175, 178))
        draw.rectangle([ax + 4, ay + 4, ax + aw - 4, ay + ah - 4],
                       fill=(155, 155, 158))
        # Fan grille lines
        for gx in range(ax + 8, ax + aw - 4, 6):
            draw.line([(gx, ay + 6), (gx, ay + ah - 6)],
                      fill=(120, 120, 122), width=1)

    return img.filter(ImageFilter.GaussianBlur(0.4))


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
    """High-quality asphalt: aggregate, cracks, tire wear, oil stains."""
    rng = np.random.RandomState(seed)

    # Age factor: 0=fresh(dark), 1=aged(lighter gray)
    age = rng.uniform(0.2, 0.8)
    bv = int(55 + age * 30)
    base_color = (bv, bv, bv + rng.randint(0, 4))

    # Multi-scale noise base
    fine = _fbm(RES, RES, scale=2, octaves=6, seed=seed)
    coarse = _fbm(RES, RES, scale=10, octaves=3, seed=seed + 1)
    arr = np.full((RES, RES, 3), base_color, dtype=np.float32)
    arr += (fine[:, :, np.newaxis] * 2 - 1) * 14
    arr += (coarse[:, :, np.newaxis] * 2 - 1) * 7
    arr = np.clip(arr, 0, 255).astype(np.uint8)

    img = Image.fromarray(arr)
    draw = ImageDraw.Draw(img)

    # Light aggregate stones
    for _ in range(1200):
        x, y = rng.randint(0, RES), rng.randint(0, RES)
        r = rng.randint(1, 4)
        v = rng.randint(55, 95)
        tint = rng.randint(-4, 8)
        draw.ellipse([x-r, y-r, x+r, y+r],
                     fill=(v, v, max(0, v + tint)))

    # Dark aggregate
    for _ in range(600):
        x, y = rng.randint(0, RES), rng.randint(0, RES)
        r = rng.randint(1, 3)
        v = rng.randint(15, 32)
        draw.ellipse([x-r, y-r, x+r, y+r], fill=(v, v, v))

    # Cracks (aged surfaces)
    if age > 0.4:
        n_cracks = rng.randint(2, 8)
        for _ in range(n_cracks):
            x, y = rng.randint(50, RES-50), rng.randint(50, RES-50)
            angle = rng.uniform(0, 2 * np.pi)
            length = rng.randint(30, 120)
            for step in range(length):
                angle += rng.uniform(-0.3, 0.3)
                nx = int(x + np.cos(angle) * 3)
                ny = int(y + np.sin(angle) * 3)
                nx = max(0, min(RES-1, nx))
                ny = max(0, min(RES-1, ny))
                draw.line([(x, y), (nx, ny)], fill=(16, 16, 16), width=1)
                x, y = nx, ny

    # Tire wear tracks (two lighter strips)
    arr2 = np.array(img, dtype=np.float32)
    for lane_frac in [0.3, 0.7]:
        cx = int(RES * lane_frac)
        ww = int(RES * 0.09)
        xs = np.arange(max(0, cx-ww), min(RES, cx+ww))
        t = 1.0 - np.abs(xs - cx) / ww
        arr2[:, xs] += t[np.newaxis, :, np.newaxis] * 11
    arr2 = np.clip(arr2, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr2)
    draw = ImageDraw.Draw(img)

    # Oil stains
    for _ in range(rng.randint(0, 4)):
        x, y = rng.randint(100, RES-100), rng.randint(100, RES-100)
        rx, ry = rng.randint(15, 45), rng.randint(10, 30)
        stain = Image.new("RGBA", (RES, RES), (0, 0, 0, 0))
        sd = ImageDraw.Draw(stain)
        sd.ellipse([x-rx, y-ry, x+rx, y+ry], fill=(20, 15, 25, 60))
        img = Image.alpha_composite(img.convert("RGBA"), stain).convert("RGB")
        draw = ImageDraw.Draw(img)

    return img.filter(ImageFilter.GaussianBlur(0.25))


def _roof(seed=0):
    """Flat rooftop: gravel, tar paper, weathered concrete."""
    rng = np.random.RandomState(seed)
    styles = ["gravel", "tarpaper", "concrete"]
    style = styles[seed % len(styles)]

    if style == "gravel":
        base = (105, 100, 95)
        noise = _fbm(RES, RES, scale=3, octaves=5, seed=seed)
        arr = _apply_noise(base, noise, strength=20)
        img = Image.fromarray(arr)
        draw = ImageDraw.Draw(img)
        for _ in range(2000):
            x, y = rng.randint(0, RES), rng.randint(0, RES)
            r = rng.randint(2, 6)
            v = rng.randint(70, 140)
            tint = rng.randint(-10, 10)
            draw.ellipse([x-r, y-r, x+r, y+r],
                         fill=(v + tint, v, v - tint))

    elif style == "tarpaper":
        base = (38, 36, 34)
        noise = _fbm(RES, RES, scale=4, octaves=4, seed=seed)
        arr = _apply_noise(base, noise, strength=10)
        img = Image.fromarray(arr)
        draw = ImageDraw.Draw(img)
        # Seam lines
        for y in range(0, RES, RES // 5):
            draw.line([(0, y), (RES, y)], fill=(25, 24, 22), width=4)
        # Patch areas
        for _ in range(rng.randint(2, 6)):
            x = rng.randint(0, RES - 80)
            y = rng.randint(0, RES - 80)
            w2 = x + rng.randint(40, 80)
            h2 = y + rng.randint(30, 60)
            draw.rectangle([x, y, w2, h2], fill=(48, 45, 42))

    else:  # concrete
        base = (155, 152, 147)
        noise = _fbm(RES, RES, scale=5, octaves=4, seed=seed)
        streak = _fbm(RES, RES, scale=1, octaves=2, seed=seed + 7)
        arr = _apply_noise(base, noise, strength=16)
        arr = arr.astype(np.float32)
        arr[streak > 0.75] -= 22
        arr = np.clip(arr, 0, 255).astype(np.uint8)
        img = Image.fromarray(arr)
        draw = ImageDraw.Draw(img)
        # Expansion joints
        for x in [RES // 3, 2 * RES // 3]:
            draw.line([(x, 0), (x, RES)], fill=(110, 108, 104), width=3)
        for y in [RES // 3, 2 * RES // 3]:
            draw.line([(0, y), (RES, y)], fill=(110, 108, 104), width=3)

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
    "commercial": _commercial,
    "industrial": _industrial,
    "educational": _educational,
    "medical": _medical,
    "generic": _generic,
    "asphalt": _asphalt,
    "roof": _roof,
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
