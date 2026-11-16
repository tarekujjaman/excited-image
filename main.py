#!/usr/bin/env python3
"""LIFTOFF -- make.fun ai-excited-01 entry.

A red-and-white lighthouse has torn itself free of its rock and is launching
like a rocket over a night sea. It leans as it climbs on a white-hot exhaust
plume; the sea below is blasted into a crown of spray inside a widening shock
ring; rock debris and sparks fly outward; the lantern's two beams blaze up
into the stars; a tiny sailboat heels over in the blast for scale.

Everything is drawn procedurally with the Python standard library only
(no Pillow, no numpy, no network, no fonts, no asset files) and written as a
valid PNG. The output is byte-for-byte identical on every run: all randomness
comes from one fixed seed and nothing reads the clock.

Usage:
    python main.py                 # writes /output/entry.png
    python main.py some/path.png   # writes somewhere else (local testing)
"""

import math
import os
import random
import struct
import sys
import time
import zlib

WIDTH, HEIGHT = 832, 1024
SEED = 20261116
DEFAULT_OUT = "/output/entry.png"


# ---------------------------------------------------------------------------
# Colour helpers (we composite in linear light, encode to sRGB at the end)
# ---------------------------------------------------------------------------

def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def col(hexstr):
    """'#rrggbb' -> linear-light RGB tuple."""
    h = hexstr.lstrip("#")
    return tuple(_lin(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


def lerp3(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def scale3(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def smoothstep(e0, e1, x):
    t = (x - e0) / (e1 - e0)
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------------------
# Canvas: three flat float lists. Heavy work happens in row-wise list
# comprehensions, which is what keeps pure Python fast enough.
# ---------------------------------------------------------------------------

class Canvas:
    def __init__(self, w, h):
        self.w = w
        self.h = h
        n = w * h
        self.R = [0.0] * n
        self.G = [0.0] * n
        self.B = [0.0] * n
        self.xf = [x + 0.5 for x in range(w)]

    # -- whole-row fills ----------------------------------------------------
    def vgradient(self, y0, y1, c0, c1, curve=1.0):
        """Fill rows y0..y1 with a vertical gradient c0 -> c1."""
        y0 = max(0, y0)
        y1 = min(self.h, y1)
        w = self.w
        for y in range(y0, y1):
            t = ((y - y0) / max(1, (y1 - y0 - 1))) ** curve
            r, g, b = lerp3(c0, c1, t)
            s = slice(y * w, (y + 1) * w)
            self.R[s] = [r] * w
            self.G[s] = [g] * w
            self.B[s] = [b] * w

    # -- spans --------------------------------------------------------------
    def blend_span(self, y, x0, x1, color, alpha):
        if y < 0 or y >= self.h:
            return
        x0 = max(0, int(x0))
        x1 = min(self.w, int(x1))
        if x1 <= x0:
            return
        s = slice(y * self.w + x0, y * self.w + x1)
        cr, cg, cb = color
        a = alpha
        self.R[s] = [v + a * (cr - v) for v in self.R[s]]
        self.G[s] = [v + a * (cg - v) for v in self.G[s]]
        self.B[s] = [v + a * (cb - v) for v in self.B[s]]

    # -- anti-aliased polygon (4 sub-scanlines, exact horizontal coverage) ---
    def polygon(self, pts, color=None, alpha=1.0, shader=None, add=False):
        """Fill a polygon. `shader(y, xa, xb)` may return per-pixel (R,G,B) lists."""
        n = len(pts)
        if n < 3:
            return
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0 = max(0, int(math.floor(min(xs))))
        x1 = min(self.w, int(math.ceil(max(xs))) + 1)
        y0 = max(0, int(math.floor(min(ys))))
        y1 = min(self.h, int(math.ceil(max(ys))) + 1)
        if x1 <= x0 or y1 <= y0:
            return
        edges = []
        for i in range(n):
            ax, ay = pts[i]
            bx, by = pts[(i + 1) % n]
            if ay != by:
                edges.append((ax, ay, bx, by, (bx - ax) / (by - ay)))
        SS = 4
        sub = 1.0 / SS
        width = x1 - x0
        R, G, B = self.R, self.G, self.B
        W = self.w
        for y in range(y0, y1):
            cov = [0.0] * width
            lo = width
            hi = 0
            for k in range(SS):
                sy = y + (k + 0.5) * sub
                xc = [ax + (sy - ay) * m for ax, ay, bx, by, m in edges
                      if (sy >= ay) != (sy >= by)]
                if len(xc) < 2:
                    continue
                xc.sort()
                for i in range(0, len(xc) - 1, 2):
                    xl = xc[i] - x0
                    xr = xc[i + 1] - x0
                    if xl < 0:
                        xl = 0.0
                    if xr > width:
                        xr = float(width)
                    if xr <= xl:
                        continue
                    il = int(xl)
                    ir = int(xr)
                    if il == ir:
                        cov[il] += (xr - xl) * sub
                    else:
                        cov[il] += (il + 1 - xl) * sub
                        if ir < width:
                            cov[ir] += (xr - ir) * sub
                        if ir > il + 1:
                            cov[il + 1:ir] = [c + sub for c in cov[il + 1:ir]]
                    if il < lo:
                        lo = il
                    e = ir + 1 if ir < width else width
                    if e > hi:
                        hi = e
            if hi <= lo:
                continue
            cv = cov[lo:hi]
            if alpha != 1.0:
                cv = [c * alpha for c in cv]
            s = slice(y * W + x0 + lo, y * W + x0 + hi)
            if shader is None:
                cr, cg, cb = color
                if add:
                    R[s] = [v + c * cr for v, c in zip(R[s], cv)]
                    G[s] = [v + c * cg for v, c in zip(G[s], cv)]
                    B[s] = [v + c * cb for v, c in zip(B[s], cv)]
                else:
                    R[s] = [v + c * (cr - v) for v, c in zip(R[s], cv)]
                    G[s] = [v + c * (cg - v) for v, c in zip(G[s], cv)]
                    B[s] = [v + c * (cb - v) for v, c in zip(B[s], cv)]
            else:
                rl, gl, bl = shader(y, x0 + lo, x0 + hi)
                if add:
                    R[s] = [v + c * cr for v, c, cr in zip(R[s], cv, rl)]
                    G[s] = [v + c * cg for v, c, cg in zip(G[s], cv, gl)]
                    B[s] = [v + c * cb for v, c, cb in zip(B[s], cv, bl)]
                else:
                    R[s] = [v + c * (cr - v) for v, c, cr in zip(R[s], cv, rl)]
                    G[s] = [v + c * (cg - v) for v, c, cg in zip(G[s], cv, gl)]
                    B[s] = [v + c * (cb - v) for v, c, cb in zip(B[s], cv, bl)]

    # -- small anti-aliased disc (per pixel; use polygon() for big ones) ----
    def disc(self, cx, cy, r, color, alpha=1.0, add=False):
        if r > 5.0:
            pts = [(cx + r * math.cos(a), cy + r * math.sin(a))
                   for a in [i * 2 * math.pi / 36 for i in range(36)]]
            self.polygon(pts, color, alpha, add=add)
            return
        x0 = max(0, int(cx - r - 1))
        x1 = min(self.w, int(cx + r + 2))
        y0 = max(0, int(cy - r - 1))
        y1 = min(self.h, int(cy + r + 2))
        cr, cg, cb = color
        R, G, B = self.R, self.G, self.B
        w = self.w
        for y in range(y0, y1):
            dy = y + 0.5 - cy
            base = y * w
            for x in range(x0, x1):
                dx = x + 0.5 - cx
                c = r + 0.5 - math.sqrt(dx * dx + dy * dy)
                if c <= 0:
                    continue
                if c > 1:
                    c = 1.0
                c *= alpha
                i = base + x
                if add:
                    R[i] += c * cr
                    G[i] += c * cg
                    B[i] += c * cb
                else:
                    R[i] += c * (cr - R[i])
                    G[i] += c * (cg - G[i])
                    B[i] += c * (cb - B[i])

    def line(self, x0, y0, x1, y1, width, color, alpha=1.0, add=False):
        dx = x1 - x0
        dy = y1 - y0
        L = math.hypot(dx, dy)
        if L < 1e-6:
            return
        nx = -dy / L * width * 0.5
        ny = dx / L * width * 0.5
        self.polygon([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny),
                      (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)], color, alpha, add=add)

    # -- additive soft elliptical glow --------------------------------------
    def glow(self, cx, cy, rx, ry, color, strength, extent=3.0):
        x0 = max(0, int(cx - rx * extent))
        x1 = min(self.w, int(cx + rx * extent) + 1)
        y0 = max(0, int(cy - ry * extent))
        y1 = min(self.h, int(cy + ry * extent) + 1)
        if x1 <= x0 or y1 <= y0:
            return
        irx = 1.0 / rx
        iry = 1.0 / ry
        dx2 = [((x + 0.5 - cx) * irx) ** 2 for x in range(x0, x1)]
        cut = 1.0 / ((1.0 + extent * extent) ** 2)   # kernel reaches 0 at the box edge
        cr, cg, cb = scale3(color, strength / (1.0 - cut))
        R, G, B = self.R, self.G, self.B
        w = self.w
        for y in range(y0, y1):
            dy2 = ((y + 0.5 - cy) * iry) ** 2 + 1.0
            s = slice(y * w + x0, y * w + x1)
            wr = [(t * t - cut) if (t := 1.0 / (d + dy2)) * t > cut else 0.0 for d in dx2]
            R[s] = [v + k * cr for v, k in zip(R[s], wr)]
            G[s] = [v + k * cg for v, k in zip(G[s], wr)]
            B[s] = [v + k * cb for v, k in zip(B[s], wr)]

    # -- lighthouse beam: soft-edged wedge from an apex, fading with distance
    def beam(self, ax, ay, angle, half, color, strength, fade_len):
        dxb = math.cos(angle)
        dyb = math.sin(angle)
        d1 = (math.cos(angle - half), math.sin(angle - half))
        d2 = (math.cos(angle + half), math.sin(angle + half))
        if d1[1] >= -1e-3 or d2[1] >= -1e-3:
            raise ValueError("beam must point upward")
        tanh = math.tan(half)
        inv_fade = 1.0 / fade_len
        cr, cg, cb = scale3(color, strength)
        R, G, B = self.R, self.G, self.B
        w = self.w
        xf = self.xf
        for y in range(0, min(self.h, int(ay))):
            dy = y + 0.5 - ay
            xa_f = ax + dy / d1[1] * d1[0]
            xb_f = ax + dy / d2[1] * d2[0]
            if xa_f > xb_f:
                xa_f, xb_f = xb_f, xa_f
            xa = max(0, int(xa_f))
            xb = min(w, int(xb_f) + 1)
            if xb <= xa:
                continue
            xs = xf[xa:xb]
            dy_dyb = dy * dyb
            dy_dxb = dy * dxb
            wr = [(e * e) / (1.0 + a * inv_fade)
                  if (e := 1.0 - ((dy_dxb - (x - ax) * dyb) / (a * tanh + 1e-6)) ** 2) > 0.0 else 0.0
                  for x in xs if (a := (x - ax) * dxb + dy_dyb) > 0.0 or True]
            s = slice(y * w + xa, y * w + xb)
            R[s] = [v + k * cr for v, k in zip(R[s], wr)]
            G[s] = [v + k * cg for v, k in zip(G[s], wr)]
            B[s] = [v + k * cb for v, k in zip(B[s], wr)]


# ---------------------------------------------------------------------------
# PNG encoding (stdlib only; per-row Sub/Up filter choice keeps it small)
# ---------------------------------------------------------------------------

def build_tone_lut():
    lut = []
    for i in range(4096):
        v = i / 1024.0
        if v > 0.78:
            v = 0.78 + 0.22 * (1.0 - math.exp(-(v - 0.78) / 0.22))
        s = 1.055 * v ** (1 / 2.4) - 0.055 if v > 0.0031308 else 12.92 * v
        lut.append(max(0, min(255, int(round(s * 255)))))
    return lut


def encode_png(path, canvas, vignette=0.42):
    w, h = canvas.w, canvas.h
    lut = build_tone_lut()
    R, G, B = canvas.R, canvas.G, canvas.B
    cx, cy = w / 2, h / 2
    vx = [((x + 0.5 - cx) / cx) ** 2 for x in range(w)]
    rows = []
    prev = bytes(3 * w)
    zeros3 = (0, 0, 0)
    for y in range(h):
        s = slice(y * w, (y + 1) * w)
        dy2 = ((y + 0.5 - cy) / cy) ** 2
        m = [(1.0 - vignette * (0.5 * (d + dy2)) ** 1.5) * 1024.0 for d in vx]
        rr = [lut[t if (t := int(v * k)) < 4096 else 4095] for v, k in zip(R[s], m)]
        gg = [lut[t if (t := int(v * k)) < 4096 else 4095] for v, k in zip(G[s], m)]
        bb = [lut[t if (t := int(v * k)) < 4096 else 4095] for v, k in zip(B[s], m)]
        raw = [0] * (3 * w)
        raw[0::3] = rr
        raw[1::3] = gg
        raw[2::3] = bb
        sub = [(a - b) & 255 for a, b in zip(raw, zeros3 + tuple(raw[:-3]))]
        up = [(a - b) & 255 for a, b in zip(raw, prev)]
        cost_sub = sum(v if v < 128 else 256 - v for v in sub[::7])
        cost_up = sum(v if v < 128 else 256 - v for v in up[::7])
        if cost_up <= cost_sub:
            rows.append(b"\x02" + bytes(up))
        else:
            rows.append(b"\x01" + bytes(sub))
        prev = raw
    data = zlib.compress(b"".join(rows), 9)

    def chunk(tag, body):
        return (struct.pack(">I", len(body)) + tag + body
                + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", data)
           + chunk(b"IEND", b""))
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


# ---------------------------------------------------------------------------
# Palette (sRGB, converted to linear light)
# ---------------------------------------------------------------------------

SKY_TOP = col("#03081C")
SKY_HOR = col("#0E2558")
NEB_A = col("#2A2E80")
NEB_B = col("#15406E")
STAR = col("#FFFFFF")
STAR_BLUE = col("#C9DDFF")
STAR_WARM = col("#FFE3B0")
BEAM = col("#FFF1C2")
SEA_TOP = col("#12336A")
SEA_BOT = col("#030B20")
SEA_STREAK = col("#6A93D6")
WARM = col("#FF7A1A")
WARM_WHITE = col("#FFD9A0")
RING_CREST = col("#EAF4FF")
FOAM = col("#9FC2EE")
SPRAY_WHITE = col("#F8FBFF")
SPRAY_BLUE = col("#B3CFF0")
ROCK = col("#121A32")
ROCK_LIT = col("#2A3658")
ROCK_HOT = col("#FF6A1C")
TOWER_WHITE = col("#F4F0E7")
TOWER_RED = col("#E53A2C")
GALLERY = col("#1C2034")
RAIL = col("#3B4466")
GLASS = col("#FFE39A")
LAMP = col("#FFFBE6")
GOLD = col("#FFC53D")
DOME = col("#8C2019")
WINDOW = col("#0A1026")
SAIL = col("#F6F8FF")
SAIL_LIT = col("#FFC98A")
HULL = col("#0A1230")
STREAK = col("#A9C2F0")
TRAIL = col("#7F97C4")


def plume_ramp():
    """64-entry colour ramp across the plume (core -> edge), pre-scaled."""
    stops = [(0.00, scale3(col("#FFFFFF"), 3.4)),
             (0.18, scale3(col("#FFF4B0"), 3.0)),
             (0.42, scale3(col("#FFC43A"), 2.2)),
             (0.70, scale3(col("#FF7A1E"), 1.4)),
             (1.00, scale3(col("#D8321A"), 0.6))]
    ramp = []
    for i in range(64):
        t = i / 63.0
        for j in range(len(stops) - 1):
            t0, c0 = stops[j]
            t1, c1 = stops[j + 1]
            if t0 <= t <= t1:
                ramp.append(lerp3(c0, c1, (t - t0) / (t1 - t0)))
                break
    return ramp


# ---------------------------------------------------------------------------
# Scene elements
# ---------------------------------------------------------------------------

def draw_stars(cv, rng, horizon):
    for _ in range(1100):
        x = rng.uniform(0, cv.w)
        y = rng.uniform(0, horizon - 20) ** 1.0
        b = rng.random() ** 3.2
        r = 0.45 + 1.5 * b
        pick = rng.random()
        c = STAR if pick < 0.6 else (STAR_BLUE if pick < 0.85 else STAR_WARM)
        cv.disc(x, y, r, c, 0.25 + 1.3 * b, add=True)
    for _ in range(14):
        x = rng.uniform(20, cv.w - 20)
        y = rng.uniform(10, horizon * 0.75)
        L = rng.uniform(5, 11)
        cv.disc(x, y, 2.0, STAR, 1.6, add=True)
        cv.line(x - L, y, x + L, y, 1.0, STAR, 0.5, add=True)
        cv.line(x, y - L, x, y + L, 1.0, STAR, 0.5, add=True)
        cv.glow(x, y, 7, 7, STAR_BLUE, 0.35)


def draw_sea(cv, rng, horizon):
    cv.vgradient(horizon, cv.h, SEA_TOP, SEA_BOT, curve=0.85)
    cv.blend_span(horizon, 0, cv.w, col("#4A6FB5"), 0.55)
    cv.blend_span(horizon + 1, 0, cv.w, col("#2A4A8A"), 0.35)
    for _ in range(170):
        t = rng.random() ** 0.6
        y = int(horizon + 6 + t * (cv.h - horizon - 10))
        L = rng.uniform(14, 40) + 130 * t
        x = rng.uniform(-20, cv.w)
        cv.blend_span(y, x, x + L, SEA_STREAK, rng.uniform(0.05, 0.16) + 0.1 * t)


def shock_ring(cv, cx, cy, a, b, y_min):
    N = 512
    Q = 256.0
    x0 = max(0, int(cx - a * 1.3))
    x1 = min(cv.w, int(cx + a * 1.3) + 1)
    y0 = max(y_min, int(cy - b * 1.3))
    y1 = min(cv.h, int(cy + b * 1.3) + 1)
    dx2 = [((x + 0.5 - cx) / a) ** 2 for x in range(x0, x1)]
    # radius-only terms, built once: inner foam, a second smaller ring, shadow
    mul, br, bg, bb = [], [], [], []
    for i in range(N):
        q = i / Q
        ring2 = math.exp(-((q - 0.62) / 0.03) ** 2) * 0.35
        inner = (1.0 - q) ** 1.4 * 0.55 if q < 1.0 else 0.0
        shadow = 0.5 * math.exp(-((q - 1.1) / 0.06) ** 2)
        fc = lerp3(FOAM, WARM_WHITE, min(1.0, inner * 2.2))
        mul.append(1.0 - shadow)
        br.append(inner * fc[0] + ring2 * FOAM[0])
        bg.append(inner * fc[1] + ring2 * FOAM[1])
        bb.append(inner * fc[2] + ring2 * FOAM[2])
    qs = [i / Q - 1.0 for i in range(N)]
    R, G, B = cv.R, cv.G, cv.B
    w = cv.w
    for y in range(y0, y1):
        dyn = (y + 0.5 - cy) / b
        dy2 = dyn * dyn
        near = smoothstep(-1.0, 1.0, dyn)
        inv = 1.0 / (0.022 + 0.030 * near)          # crest thicker on the near side
        amp = 0.9 + 0.9 * near
        crest = [math.exp(-(q * inv) ** 2) * amp if abs(q) < 0.25 else 0.0 for q in qs]
        ar = [c * RING_CREST[0] + v for c, v in zip(crest, br)]
        ag = [c * RING_CREST[1] + v for c, v in zip(crest, bg)]
        ab = [c * RING_CREST[2] + v for c, v in zip(crest, bb)]
        idx = [t if (t := int(math.sqrt(d + dy2) * Q)) < N else N - 1 for d in dx2]
        s = slice(y * w + x0, y * w + x1)
        R[s] = [v * mul[i] + ar[i] for v, i in zip(R[s], idx)]
        G[s] = [v * mul[i] + ag[i] for v, i in zip(G[s], idx)]
        B[s] = [v * mul[i] + ab[i] for v, i in zip(B[s], idx)]


def air_ring(cv, cx, cy, a, b, sigma, color, strength, y_max):
    """Thin expanding pressure ring in the air above the blast (additive)."""
    x0 = max(0, int(cx - a * 1.2))
    x1 = min(cv.w, int(cx + a * 1.2) + 1)
    y0 = max(0, int(cy - b * 1.2))
    y1 = min(cv.h, y_max, int(cy) + 1)
    dx2 = [((x + 0.5 - cx) / a) ** 2 for x in range(x0, x1)]
    cr, cg, cb = scale3(color, strength)
    R, G, B = cv.R, cv.G, cv.B
    w = cv.w
    inv = 1.0 / sigma
    for y in range(y0, y1):
        dyn = (y + 0.5 - cy) / b
        dy2 = dyn * dyn
        lift = min(1.0, -dyn * 1.6)            # fades out toward the water
        if lift <= 0:
            continue
        wr = [math.exp(-(((d + dy2) ** 0.5 - 1.0) * inv) ** 2) * lift for d in dx2]
        s = slice(y * w + x0, y * w + x1)
        R[s] = [v + k * cr for v, k in zip(R[s], wr)]
        G[s] = [v + k * cg for v, k in zip(G[s], wr)]
        B[s] = [v + k * cb for v, k in zip(B[s], wr)]


def draw_plume(cv, px, py, ax, ay, length, w0, grow, ramp):
    """Exhaust plume from (px, py) along unit direction (ax, ay)."""
    wm = w0 * 1.12
    gm = grow * 1.12
    den1 = -ay - gm * ax
    den2 = ay - gm * ax
    R, G, B = cv.R, cv.G, cv.B
    w = cv.w
    xf = cv.xf
    rr = [c[0] for c in ramp]
    rg = [c[1] for c in ramp]
    rb = [c[2] for c in ramp]
    y0 = max(0, int(py - 6))
    y1 = min(cv.h, int(py + length + 40))
    inv_fade = 1.0 / 70.0
    for y in range(y0, y1):
        dy = y + 0.5 - py
        xa_f = (wm - dy * (ax - gm * ay)) / den1 + px
        xb_f = (wm - dy * (-ax - gm * ay)) / den2 + px
        if xa_f > xb_f:
            xa_f, xb_f = xb_f, xa_f
        xa = max(0, int(xa_f))
        xb = min(w, int(xb_f) + 1)
        if xb <= xa:
            continue
        xs = xf[xa:xb]
        dy_ay = dy * ay
        dy_ax = dy * ax
        A = [(x - px) * ax + dy_ay for x in xs]
        P = [dy_ax - (x - px) * ay for x in xs]
        Nn = [p / ((w0 + grow * a) * (1.0 + 0.03 * math.sin(a * 0.11 + 1.3))) for a, p in zip(A, P)]
        I = [(e * e) * max(0.0, min(1.0, a * 0.12, (length + 24 - a) * inv_fade))
             * (1.0 + 0.26 * math.cos(a * 0.21) * max(0.0, 1.0 - 2.4 * abs(n)))
             if (e := 1.0 - n * n) > 0.0 else 0.0
             for a, n in zip(A, Nn)]
        idx = [min(63, int(abs(n) * 64)) if n < 1.0 and n > -1.0 else 63 for n in Nn]
        s = slice(y * w + xa, y * w + xb)
        R[s] = [v + i * rr[j] for v, i, j in zip(R[s], I, idx)]
        G[s] = [v + i * rg[j] for v, i, j in zip(G[s], I, idx)]
        B[s] = [v + i * rb[j] for v, i, j in zip(B[s], I, idx)]


def draw_flame(cv, px, py, ax, ay, length, w0, grow):
    """Crisp poster flame: red rim, orange body, yellow, white core + Mach diamonds."""
    nx, ny = -ay, ax

    def outline(ws, gs, end, wobble, phase, diamonds=0.0, n=30):
        left, right = [], []
        for i in range(n + 1):
            a = -8.0 + (end + 8.0) * i / n
            wd = w0 * ws + grow * gs * max(0.0, a)
            wd *= 1.0 + wobble * math.sin(a * 0.17 + phase) + 0.6 * wobble * math.sin(a * 0.31 + 2.3 * phase)
            if diamonds:
                wd *= 1.0 - diamonds + diamonds * abs(math.cos(a * math.pi / 36.0))
            cxp = px + ax * a
            cyp = py + ay * a
            left.append((cxp + nx * wd, cyp + ny * wd))
            right.append((cxp - nx * wd, cyp - ny * wd))
        return left + right[::-1]

    cv.polygon(outline(1.00, 1.00, length - 16, 0.0, 0.0), col("#D8321A"))
    cv.polygon(outline(0.93, 0.94, length - 12, 0.0, 1.1), col("#FF7A1E"))
    cv.polygon(outline(0.74, 0.80, length - 6, 0.0, 2.2), col("#FFC43A"))
    cv.polygon(outline(0.50, 0.55, length, 0.0, 3.3, diamonds=0.3), col("#FFF6D8"))
    cv.polygon(outline(0.30, 0.30, length, 0.0, 0.0), col("#FFFFFF"), 1.2, add=True)
    for k in range(4):
        a = 16.0 + 36.0 * k
        half = (w0 * 0.50 + grow * 0.55 * a) * 0.95
        cxp = px + ax * a
        cyp = py + ay * a
        rhombus = [(cxp + nx * half, cyp + ny * half), (cxp + ax * half * 1.4, cyp + ay * half * 1.4),
                   (cxp - nx * half, cyp - ny * half), (cxp - ax * half * 1.4, cyp - ay * half * 1.4)]
        cv.polygon(rhombus, col("#FFFFFF"))
        cv.glow(cxp, cyp, half * 1.2, half * 1.2, LAMP, 0.6 - 0.1 * k)


def spray_crown(cv, seed, cx, cy, rr, aspect, layer):
    """Crown of spray. layer='back' draws the far spikes, 'front' the near ones
    plus droplets, so the flame can sit between them."""
    rng = random.Random(seed)
    spikes = []
    n = 44
    for i in range(n):
        phi = (i + rng.uniform(-0.3, 0.3)) * 2 * math.pi / n
        spikes.append((math.sin(phi), phi, rng.uniform(55, 175), rng.uniform(6, 15),
                       rng.uniform(-0.12, 0.12), rng.uniform(-4, 4)))
    spikes.sort()
    if layer == "back":
        mound = [(cx + rr * 1.05 * math.cos(a), cy + rr * aspect * 1.05 * math.sin(a))
                 for a in [i * 2 * math.pi / 40 for i in range(40)]]
        cv.polygon(mound, SPRAY_BLUE)
    for sphi, phi, h0, hw, lean_j, tip_j in spikes:
        if (sphi < 0.15) != (layer == "back"):
            continue
        bxs = cx + rr * math.cos(phi)
        bys = cy + rr * aspect * math.sin(phi)
        nearness = (sphi + 1.0) * 0.5
        hgt = h0 * (0.5 + 0.6 * abs(math.cos(phi))) * (0.8 + 0.3 * nearness)
        lean = 0.42 * math.cos(phi) + lean_j
        tipx = bxs + lean * hgt
        tipy = bys - hgt
        pale = [(bxs - hw * 1.25, bys + 4), (tipx + tip_j, tipy + 8), (bxs + hw * 1.25, bys + 4)]
        cv.polygon(pale, SPRAY_BLUE)
        white = [(bxs - hw, bys + 4), (tipx, tipy), (bxs + hw, bys + 4)]
        cv.polygon(white, SPRAY_WHITE if nearness > 0.35 else lerp3(SPRAY_BLUE, SPRAY_WHITE, 0.6))
    if layer == "back":
        return
    # droplets flung upward and outward, elongated by their speed
    for _ in range(70):
        phi = rng.uniform(math.pi * 1.05, math.pi * 1.95)
        d = rng.uniform(rr * 0.8, rr * 2.1)
        x = cx + math.cos(phi) * d * 1.3
        y = cy + math.sin(phi) * d * 0.9
        r = rng.uniform(1.0, 3.0)
        L = rng.uniform(2, 9) * (d / rr)
        cv.line(x, y, x + math.cos(phi) * L, y + math.sin(phi) * L, r * 1.5, SPRAY_WHITE, 0.85)
        cv.disc(x, y, r, SPRAY_WHITE)


def draw_debris(cv, rng, ox, oy, hot_centre):
    chunks = []
    for _ in range(26):
        phi = rng.uniform(math.radians(-165), math.radians(-15))
        d = 70 + 330 * rng.random() ** 0.8
        size = rng.uniform(6, 24) * (1.1 - d / 520)
        chunks.append((phi, d, size))
    chunks.sort(key=lambda c: c[2])
    for phi, d, size in chunks:
        x = ox + math.cos(phi) * d * 1.15
        y = oy + math.sin(phi) * d * 0.95
        rot = rng.uniform(0, math.pi * 2)
        pts = []
        for i in range(6):
            a = rot + i * math.pi / 3
            rad = size * rng.uniform(0.55, 1.0)
            pts.append((x + math.cos(a) * rad, y + math.sin(a) * rad))
        # faint motion trail back toward the blast (only on the bigger rocks)
        if size > 9:
            tl = rng.uniform(14, 40)
            cv.line(x, y, x - math.cos(phi) * tl, y - math.sin(phi) * tl, size * 0.5, TRAIL, 0.13)
        if math.hypot(x - hot_centre[0], y - hot_centre[1]) < 230:
            ox2 = (hot_centre[0] - x)
            oy2 = (hot_centre[1] - y)
            L = math.hypot(ox2, oy2) + 1e-6
            off = [(p[0] + ox2 / L * 2.5, p[1] + oy2 / L * 2.5) for p in pts]
            cv.polygon(off, ROCK_HOT)
        cv.polygon(pts, ROCK)


def draw_sparks(cv, rng, ox, oy, count, spread_up=True):
    for _ in range(count):
        if spread_up:
            phi = rng.uniform(math.radians(-175), math.radians(-5))
        else:
            phi = rng.choice([0.0, math.pi]) + rng.uniform(-0.55, 0.55)
        d = 20 + 250 * rng.random() ** 0.7
        x = ox + math.cos(phi) * d * 1.1
        y = oy + math.sin(phi) * d
        L = rng.uniform(4, 16) * (0.3 + d / 160)
        wdt = rng.uniform(0.9, 1.7)
        c = lerp3(col("#FFEB9A"), col("#FF8A2A"), rng.random())
        k = 1.3 * max(0.1, 1.0 - d / 320)
        cv.line(x, y, x + math.cos(phi) * L, y + math.sin(phi) * L, wdt, c, k, add=True)


def draw_sailboat(cv, x, y, heel, k=1.0):
    c, s = math.cos(heel), math.sin(heel)

    def P(lx, ly):
        return (x + (lx * c - ly * s) * k, y + (lx * s + ly * c) * k)

    # reflection and a wake on the water (unrotated: the water stays flat)
    cv.polygon([(x - 24 * k, y + 3), (x + 24 * k, y + 3), (x + 14 * k, y + 16 * k), (x - 14 * k, y + 16 * k)],
               col("#061020"), 0.55)
    sx, sy = P(-28, 5)
    cv.line(sx, sy, sx - 40 * k, sy + 3 * k, 3.5 * k, SPRAY_WHITE, 0.6)
    cv.line(sx + 6 * k, sy + 5 * k, sx - 22 * k, sy + 7 * k, 2.0 * k, SPRAY_WHITE, 0.35)
    # mainsail (lit by the blast), jib, mast, hull with a bow
    cv.polygon([P(1, -10), P(1, -68), P(32, -10)], lerp3(SAIL, SAIL_LIT, 0.55))
    cv.polygon([P(-2, -60), P(-2, -14), P(-26, -11)], SAIL)
    cv.line(*P(0, 2), *P(0, -70), 2.0 * k, HULL)
    cv.polygon([P(-30, -2), P(-8, -3), P(14, -3), P(34, -6), P(20, 8), P(-22, 8)], HULL)
    cv.polygon([P(-29, -2), P(14, -3), P(33, -6), P(32, -3), P(12, 0), P(-28, 1)], col("#4A5C8E"))


# ---------------------------------------------------------------------------
# The picture
# ---------------------------------------------------------------------------

def render(seed=SEED):
    rng = random.Random(seed)
    cv = Canvas(WIDTH, HEIGHT)
    W, H = WIDTH, HEIGHT
    horizon = int(0.70 * H)

    # Launch geometry ------------------------------------------------------
    tilt = math.radians(14.0)
    c, s = math.cos(tilt), math.sin(tilt)
    bx, by = 0.47 * W, 0.49 * H          # centre of the tower base

    def to_world(lx, ly):                 # local: lx across, ly along (negative = up)
        return (bx + lx * c - ly * s, by + lx * s + ly * c)

    tower_h = 0.29 * H
    wb, wt = 0.062 * W, 0.043 * W
    stump_depth = 0.058 * H
    lamp_ly = -(tower_h + 0.033 * H)
    lamp = to_world(0, lamp_ly)
    p0 = to_world(0, stump_depth)          # nozzle: bottom of the torn rock
    impact_y = 0.78 * H
    plume_len = (impact_y - p0[1]) / c
    impact = (p0[0] - plume_len * s, impact_y)
    down = (-s, c)

    # Sky ------------------------------------------------------------------
    cv.vgradient(0, horizon, SKY_TOP, SKY_HOR, curve=1.5)
    cv.glow(0.18 * W, 0.22 * H, 260, 210, NEB_A, 0.13)
    cv.glow(0.80 * W, 0.10 * H, 230, 190, NEB_B, 0.11)
    cv.glow(0.60 * W, 0.42 * H, 300, 160, NEB_A, 0.06)
    draw_stars(cv, rng, horizon)

    # Lantern beams (behind the tower) ---------------------------------------
    up_angle = -math.pi / 2 + tilt
    for sgn in (-1, 1):
        cv.beam(lamp[0], lamp[1], up_angle + sgn * math.radians(42), math.radians(9.5),
                BEAM, 1.9, 330.0)

    # Sea ------------------------------------------------------------------
    draw_sea(cv, rng, horizon)

    # Heat and light of the blast ------------------------------------------
    cv.glow(impact[0], impact[1], 240, 150, WARM, 0.55)
    cv.glow(p0[0], p0[1], 150, 150, WARM, 0.35)
    cv.glow(impact[0], impact[1] + 80, 60, 170, WARM, 0.45)      # reflection on water
    cv.glow(lamp[0], horizon + 60, 12, 110, GOLD, 0.22)         # lantern reflection

    # Shock ring on the water ------------------------------------------------
    shock_ring(cv, impact[0], impact[1], 0.36 * W, 0.072 * H, horizon + 1)

    # Spray crown (far half), then the plume, then the near half of the crown
    crown_r = 0.14 * W
    spray_crown(cv, seed + 1, impact[0], impact[1] + 6, crown_r, 0.30, "back")
    halo = [scale3(cc, 0.45) for cc in plume_ramp()]
    draw_plume(cv, p0[0], p0[1], down[0], down[1], plume_len, 0.06 * W, 0.45, halo)
    draw_flame(cv, p0[0], p0[1], down[0], down[1], plume_len, 0.052 * W, 0.34)
    spray_crown(cv, seed + 1, impact[0], impact[1] + 6, crown_r, 0.30, "front")
    # pressure ring expanding through the air above the blast
    air_ring(cv, impact[0], impact[1] - 10, 0.46 * W, 0.30 * H, 0.012, BEAM, 0.45, horizon)
    air_ring(cv, impact[0], impact[1] - 10, 0.30 * W, 0.19 * H, 0.016, BEAM, 0.18, horizon)
    cv.glow(impact[0], impact[1], 90, 48, WARM_WHITE, 2.0)
    cv.glow(p0[0] + 14 * down[0], p0[1] + 14 * down[1], 46, 30, LAMP, 2.4)   # nozzle flash
    cv.glow(p0[0] + 70 * down[0], p0[1] + 70 * down[1], 90, 90, WARM, 0.8)

    # Debris and sparks --------------------------------------------------------
    draw_debris(cv, rng, impact[0], impact[1] - 10, impact)
    draw_sparks(cv, rng, impact[0], impact[1] - 20, 170, spread_up=True)
    draw_sparks(cv, rng, p0[0], p0[1], 70, spread_up=False)

    # The torn rock stump ------------------------------------------------------
    sw = wb + 0.03 * W
    outline = [(-wb - 4, 0.0), (wb + 4, 0.0), (sw, stump_depth * 0.22), (sw + 10, stump_depth * 0.55)]
    nseg = 11
    for i in range(nseg + 1):
        lx = sw - (2 * sw) * i / nseg
        ly = stump_depth * (rng.uniform(0.55, 1.0) if 0 < i < nseg else 0.8)
        outline.append((lx + rng.uniform(-5, 5), ly))
    outline.append((-sw - 10, stump_depth * 0.55))
    outline.append((-sw, stump_depth * 0.22))

    def stump_shader(y, xa, xb):
        xs = cv.xf[xa:xb]
        dyc = (y + 0.5 - by) * c
        dys = (y + 0.5 - by) * s
        LY = [-(x - bx) * s + dyc for x in xs]
        LX = [(x - bx) * c + dys for x in xs]
        T = [smoothstep(stump_depth * 0.35, stump_depth * 1.0, ly) ** 1.3 for ly in LY]
        E = [0.5 * max(0.0, 1.0 - abs(lx) / sw) * (1.0 - t) for lx, t in zip(LX, T)]
        return ([ROCK[0] + (ROCK_LIT[0] - ROCK[0]) * e + (ROCK_HOT[0] * 1.8 - ROCK[0]) * t for t, e in zip(T, E)],
                [ROCK[1] + (ROCK_LIT[1] - ROCK[1]) * e + (ROCK_HOT[1] * 1.8 - ROCK[1]) * t for t, e in zip(T, E)],
                [ROCK[2] + (ROCK_LIT[2] - ROCK[2]) * e + (ROCK_HOT[2] * 1.8 - ROCK[2]) * t for t, e in zip(T, E)])

    cv.polygon([to_world(*p) for p in outline], shader=stump_shader)
    for _ in range(10):
        lx = rng.uniform(-sw * 0.9, sw * 0.9)
        y_top = rng.uniform(0.1, 0.45) * stump_depth
        a_ = to_world(lx, stump_depth * 0.9)
        b_ = to_world(lx + rng.uniform(-10, 10), y_top)
        cv.line(a_[0], a_[1], b_[0], b_[1], rng.uniform(2.0, 3.6), ROCK_HOT, 1.6, add=True)
        cv.line(a_[0], a_[1], b_[0], b_[1], rng.uniform(0.8, 1.4), LAMP, 0.9, add=True)
    # rock fragments still falling away from the torn base
    for _ in range(12):
        lx = rng.uniform(-sw, sw)
        ly = stump_depth + rng.uniform(8, 90)
        size = rng.uniform(3, 11)
        x, y = to_world(lx, ly)
        pts = [(x + math.cos(a) * size * rng.uniform(0.5, 1.0), y + math.sin(a) * size * rng.uniform(0.5, 1.0))
               for a in [i * math.pi / 2.5 for i in range(5)]]
        cv.polygon([(p[0] - 2, p[1] - 2) for p in pts], ROCK_HOT)
        cv.polygon(pts, ROCK)

    # Tower ------------------------------------------------------------------
    inv_h = 1.0 / tower_h
    dwt = wt - wb
    nb = 5

    def tower_shader(y, xa, xb):
        xs = cv.xf[xa:xb]
        dyc = (y + 0.5 - by) * c
        dys = (y + 0.5 - by) * s
        LX = [(x - bx) * c + dys for x in xs]
        LY = [-(x - bx) * s + dyc for x in xs]
        T = [max(0.0, min(1.0, -ly * inv_h)) for ly in LY]
        U = [max(-1.0, min(1.0, lx / (wb + dwt * t))) for lx, t in zip(LX, T)]
        F = [0.2 + 0.8 * max(0.0, math.sqrt(1.0 - u * u) * 0.82 - u * 0.57) for u in U]
        Wm = [(1.0 - t) ** 2.2 * 0.55 for t in T]
        Bd = [int(t * nb - 1e-6) & 1 for t in T]
        out = []
        for ch in range(3):
            red = TOWER_RED[ch]
            white = TOWER_WHITE[ch]
            hot = WARM[ch]
            out.append([(white if b else red) * f + hot * wm for b, f, wm in zip(Bd, F, Wm)])
        return out

    cv.polygon([to_world(-wb, 0), to_world(wb, 0), to_world(wt, -tower_h), to_world(-wt, -tower_h)],
               shader=tower_shader)
    # door and windows
    cv.polygon([to_world(-8, 0), to_world(8, 0), to_world(8, -22), to_world(0, -28), to_world(-8, -22)], WINDOW)
    for frac in (0.3, 0.52, 0.74):
        ly = -tower_h * frac
        cv.polygon([to_world(-5, ly), to_world(5, ly), to_world(5, ly - 11), to_world(0, ly - 15), to_world(-5, ly - 11)], WINDOW)
        wx, wy = to_world(0, ly - 6)
        cv.disc(wx, wy, 2.2, GOLD, 0.9, add=True)

    # Gallery, lantern room, dome -------------------------------------------
    g0 = -tower_h
    gw = wt + 0.02 * W
    cv.polygon([to_world(-gw, g0), to_world(gw, g0), to_world(gw, g0 - 13), to_world(-gw, g0 - 13)], GALLERY)
    for i in range(9):
        lx = -gw + 4 + (2 * gw - 8) * i / 8
        a_ = to_world(lx, g0 - 13)
        b_ = to_world(lx, g0 - 30)
        cv.line(a_[0], a_[1], b_[0], b_[1], 1.6, RAIL)
    a_ = to_world(-gw + 2, g0 - 30)
    b_ = to_world(gw - 2, g0 - 30)
    cv.line(a_[0], a_[1], b_[0], b_[1], 1.8, RAIL)
    lw = wt - 5
    l0, l1 = g0 - 13, g0 - 54
    cv.polygon([to_world(-lw, l0), to_world(lw, l0), to_world(lw, l1), to_world(-lw, l1)], GLASS)
    cv.disc(lamp[0], lamp[1], 12, LAMP)
    for lx in (-lw * 0.5, 0.0, lw * 0.5):
        a_ = to_world(lx, l0)
        b_ = to_world(lx, l1)
        cv.line(a_[0], a_[1], b_[0], b_[1], 2.0, GALLERY, 0.8)
    cv.polygon([to_world(-lw - 4, l1), to_world(lw + 4, l1), to_world(lw + 4, l1 - 6), to_world(-lw - 4, l1 - 6)], GALLERY)
    dome = []
    dw = lw + 4
    for i in range(17):
        a = math.pi * i / 16
        dome.append(to_world(dw * math.cos(a), l1 - 6 - 34 * math.sin(a)))
    cv.polygon(dome, DOME)
    a_ = to_world(0, l1 - 38)
    b_ = to_world(0, l1 - 52)
    cv.line(a_[0], a_[1], b_[0], b_[1], 2.4, RAIL)
    cv.disc(b_[0], b_[1], 3.5, GOLD)

    # Lamp glow and speed lines ------------------------------------------------
    cv.glow(lamp[0], lamp[1], 20, 20, LAMP, 2.2)
    cv.glow(lamp[0], lamp[1], 70, 70, GOLD, 1.1)
    for _ in range(8):
        side = rng.choice([-1, 1])
        lx = side * (wb + rng.uniform(10, 48))
        ly0 = rng.uniform(-tower_h * 0.85, -tower_h * 0.1)
        L = rng.uniform(40, 150)
        a_ = to_world(lx, ly0)
        b_ = to_world(lx, ly0 + L)
        cv.line(a_[0], a_[1], b_[0], b_[1], rng.uniform(1.4, 2.6), STREAK, rng.uniform(0.25, 0.55))

    # Sailboat for scale --------------------------------------------------------
    draw_sailboat(cv, 0.82 * W, 0.845 * H, math.radians(34), 1.25)
    return cv


def main(argv):
    out = argv[1] if len(argv) > 1 else DEFAULT_OUT
    t0 = time.perf_counter()
    cv = render()
    t1 = time.perf_counter()
    size = encode_png(out, cv)
    t2 = time.perf_counter()
    print("wrote %s  %dx%d  %.0f KiB  (render %.1fs, encode %.1fs)"
          % (out, cv.w, cv.h, size / 1024.0, t1 - t0, t2 - t1))


if __name__ == "__main__":
    main(sys.argv)
