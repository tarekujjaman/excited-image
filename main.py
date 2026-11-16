#!/usr/bin/env python3
"""LIFTOFF.

A lighthouse tears itself free of its rock and launches like a rocket into the
night: a shock-diamond exhaust under it, the sea blasted into a crown of spray,
its beams blazing into the sky, and a tiny sailboat heeled over by the shock.

Everything is drawn procedurally with the Python standard library only and the
same bytes are written every run (no clock, seeded randomness only).

Usage:  python main.py [output.png]
        (default /output/entry.png, or $MAKEFUN_OUTPUT_DIR/entry.png)
"""
import math
import os
import random
import struct
import sys
import zlib

W = 1024
H = 1024
R = [0.0] * (W * H)
G = [0.0] * (W * H)
B = [0.0] * (W * H)

sqrt = math.sqrt
exp = math.exp


# ----------------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------------
def hexc(h):
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5))


def mix(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def smooth(e0, e1, x):
    t = (x - e0) / (e1 - e0)
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    return t * t * (3.0 - 2.0 * t)


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else (hi if v > hi else v)


def blend_span(y, x0, cov, cr, cg, cb, add=False):
    """Blend one scanline span. cov: list of coverage; cr/cg/cb: floats or lists."""
    o = y * W + x0
    n = len(cov)
    rs = R[o:o + n]
    gs = G[o:o + n]
    bs = B[o:o + n]
    if isinstance(cr, list):
        if add:
            R[o:o + n] = [r + c * a for r, c, a in zip(rs, cr, cov)]
            G[o:o + n] = [r + c * a for r, c, a in zip(gs, cg, cov)]
            B[o:o + n] = [r + c * a for r, c, a in zip(bs, cb, cov)]
        else:
            R[o:o + n] = [r + (c - r) * a for r, c, a in zip(rs, cr, cov)]
            G[o:o + n] = [r + (c - r) * a for r, c, a in zip(gs, cg, cov)]
            B[o:o + n] = [r + (c - r) * a for r, c, a in zip(bs, cb, cov)]
    else:
        if add:
            R[o:o + n] = [r + cr * a for r, a in zip(rs, cov)]
            G[o:o + n] = [r + cg * a for r, a in zip(gs, cov)]
            B[o:o + n] = [r + cb * a for r, a in zip(bs, cov)]
        else:
            R[o:o + n] = [r + (cr - r) * a for r, a in zip(rs, cov)]
            G[o:o + n] = [r + (cg - r) * a for r, a in zip(gs, cov)]
            B[o:o + n] = [r + (cb - r) * a for r, a in zip(bs, cov)]


def blend_column(x, y0, cov, cr, cg, cb, add=False):
    """Blend a vertical run of pixels at column x from row y0. cr/cg/cb floats or lists."""
    n = len(cov)
    s = slice(y0 * W + x, (y0 + n) * W + x, W)
    rs = R[s]
    gs = G[s]
    bs = B[s]
    if isinstance(cr, list):
        if add:
            R[s] = [r + c * a for r, c, a in zip(rs, cr, cov)]
            G[s] = [r + c * a for r, c, a in zip(gs, cg, cov)]
            B[s] = [r + c * a for r, c, a in zip(bs, cb, cov)]
        else:
            R[s] = [r + (c - r) * a for r, c, a in zip(rs, cr, cov)]
            G[s] = [r + (c - r) * a for r, c, a in zip(gs, cg, cov)]
            B[s] = [r + (c - r) * a for r, c, a in zip(bs, cb, cov)]
    else:
        if add:
            R[s] = [r + cr * a for r, a in zip(rs, cov)]
            G[s] = [r + cg * a for r, a in zip(gs, cov)]
            B[s] = [r + cb * a for r, a in zip(bs, cov)]
        else:
            R[s] = [r + (cr - r) * a for r, a in zip(rs, cov)]
            G[s] = [r + (cg - r) * a for r, a in zip(gs, cov)]
            B[s] = [r + (cb - r) * a for r, a in zip(bs, cov)]


# ----------------------------------------------------------------------------
# primitives
# ----------------------------------------------------------------------------
def poly(pts, color, alpha=1.0, add=False, soft=0.5):
    """Anti-aliased convex polygon. color: (r,g,b) or callable(x, y) -> (r,g,b)."""
    n = len(pts)
    area = 0.0
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        area += x0 * y1 - x1 * y0
    if abs(area) < 1e-9:
        return
    sign = 1.0 if area > 0 else -1.0
    edges = []
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        ex, ey = x1 - x0, y1 - y0
        L = math.hypot(ex, ey) or 1.0
        edges.append((sign * ey / L, -sign * ex / L, -sign * (ey * x0 - ex * y0) / L))
    ymin = max(0, int(math.floor(min(p[1] for p in pts))) - 1 - int(soft))
    ymax = min(H - 1, int(math.ceil(max(p[1] for p in pts))) + 1 + int(soft))
    callable_color = callable(color)
    inv = 1.0 / (2.0 * soft)
    pad = 2 + int(soft)
    for y in range(ymin, ymax + 1):
        yc = y + 0.5
        xl, xr = 1e9, -1e9
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            lo, hi = (y0, y1) if y0 < y1 else (y1, y0)
            if lo - 1.5 - soft <= yc <= hi + 1.5 + soft:
                if abs(y1 - y0) < 1e-9:
                    xs = (x0, x1)
                else:
                    t = clamp((yc - y0) / (y1 - y0))
                    xs = (x0 + (x1 - x0) * t,)
                for xv in xs:
                    if xv < xl:
                        xl = xv
                    if xv > xr:
                        xr = xv
        if xl > xr:
            continue
        x0i = max(0, int(math.floor(xl)) - pad)
        x1i = min(W, int(math.ceil(xr)) + pad + 1)
        if x1i <= x0i:
            continue
        ks = [(a, b * yc + c) for a, b, c in edges]
        xs = [x + 0.5 for x in range(x0i, x1i)]
        cov = [clamp(0.5 - max(a * xc + k for a, k in ks) * inv) * alpha for xc in xs]
        if max(cov) <= 0.0:
            continue
        if callable_color:
            cols = [color(xc, yc) if a > 0 else (0.0, 0.0, 0.0) for xc, a in zip(xs, cov)]
            blend_span(y, x0i, cov, [c[0] for c in cols], [c[1] for c in cols], [c[2] for c in cols], add)
        else:
            blend_span(y, x0i, cov, color[0], color[1], color[2], add)


def disc(cx, cy, r, color, alpha=1.0, add=False, soft=0.6):
    ymin = max(0, int(cy - r - 2))
    ymax = min(H - 1, int(cy + r + 2))
    callable_color = callable(color)
    x0i = max(0, int(cx - r - 2))
    x1i = min(W, int(cx + r + 3))
    if x1i <= x0i:
        return
    xs = [x + 0.5 for x in range(x0i, x1i)]
    inv = 1.0 / (2.0 * soft)
    for y in range(ymin, ymax + 1):
        dy2 = (y + 0.5 - cy) ** 2
        cov = [clamp(0.5 - (sqrt((xc - cx) ** 2 + dy2) - r) * inv) * alpha for xc in xs]
        if max(cov) <= 0.0:
            continue
        if callable_color:
            cols = [color(xc, y + 0.5) if a > 0 else (0.0, 0.0, 0.0) for xc, a in zip(xs, cov)]
            blend_span(y, x0i, cov, [c[0] for c in cols], [c[1] for c in cols], [c[2] for c in cols], add)
        else:
            blend_span(y, x0i, cov, color[0], color[1], color[2], add)


def ellipse(cx, cy, rx, ry, color, alpha=1.0, add=False, soft=1.0):
    """Anti-aliased axis-aligned ellipse. color constant or callable(x, y, r) with r = normalised radius."""
    ymin = max(0, int(cy - ry - soft - 2))
    ymax = min(H - 1, int(cy + ry + soft + 2))
    x0i = max(0, int(cx - rx - soft - 2))
    x1i = min(W, int(cx + rx + soft + 3))
    if x1i <= x0i:
        return
    xs = [((x + 0.5 - cx) / rx) ** 2 for x in range(x0i, x1i)]
    callable_color = callable(color)
    for y in range(ymin, ymax + 1):
        dy2 = ((y + 0.5 - cy) / ry) ** 2
        rs = [sqrt(dx + dy2) for dx in xs]
        cov = [clamp(0.5 - (r - 1.0) * min(rx, ry) / (2.0 * soft)) * alpha for r in rs]
        if max(cov) <= 0.0:
            continue
        if callable_color:
            cols = [color(x0i + i + 0.5, y + 0.5, r) if a > 0 else (0.0, 0.0, 0.0) for i, (r, a) in enumerate(zip(rs, cov))]
            blend_span(y, x0i, cov, [c[0] for c in cols], [c[1] for c in cols], [c[2] for c in cols], add)
        else:
            blend_span(y, x0i, cov, color[0], color[1], color[2], add)


def glow(cx, cy, rx, ry, color, strength, power=2.0, ymin=0, ymax=H):
    """Additive glow: strength * exp(-(d^power)) with elliptical radius."""
    ext = 2.6 if power >= 2 else 4.0
    y0 = max(ymin, int(cy - ry * ext))
    y1 = min(ymax - 1, int(cy + ry * ext))
    x0 = max(0, int(cx - rx * ext))
    x1 = min(W, int(cx + rx * ext) + 1)
    if x1 <= x0 or y1 < y0:
        return
    xs = [((x + 0.5 - cx) / rx) ** 2 for x in range(x0, x1)]
    cr, cg, cb = color
    hp = power * 0.5
    for y in range(y0, y1 + 1):
        dy = ((y + 0.5 - cy) / ry) ** 2
        if power == 2.0:
            cov = [strength * exp(-(dx + dy)) for dx in xs]
        else:
            cov = [strength * exp(-((dx + dy) ** hp)) for dx in xs]
        blend_span(y, x0, cov, cr, cg, cb, add=True)


def vgradient(y0, y1, c0, c1, ease=1.0):
    for y in range(max(0, y0), min(H, y1)):
        t = ((y - y0) / max(1, (y1 - y0))) ** ease
        c = mix(c0, c1, t)
        o = y * W
        R[o:o + W] = [c[0]] * W
        G[o:o + W] = [c[1]] * W
        B[o:o + W] = [c[2]] * W


def thick_line(p0, p1, w, color, alpha=1.0, add=False, soft=0.5):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy) or 1.0
    px, py = -dy / L * w * 0.5, dx / L * w * 0.5
    poly([(p0[0] + px, p0[1] + py), (p1[0] + px, p1[1] + py), (p1[0] - px, p1[1] - py), (p0[0] - px, p0[1] - py)],
         color, alpha=alpha, add=add, soft=soft)


def blobs(circles, color_fn, alpha=1.0, k=18.0, soft=1.5):
    """Smooth union of circles (cx, cy, r). color_fn(x, y, depth) -> (r,g,b), depth = distance inside."""
    ymin = max(0, int(min(c[1] - c[2] for c in circles)) - 3)
    ymax = min(H - 1, int(max(c[1] + c[2] for c in circles)) + 3)
    xmin = max(0, int(min(c[0] - c[2] for c in circles)) - 3)
    xmax = min(W, int(max(c[0] + c[2] for c in circles)) + 4)
    inv = 1.0 / (2.0 * soft)
    for y in range(ymin, ymax + 1):
        yc = y + 0.5
        act = [(cx, cy, r) for (cx, cy, r) in circles if abs(yc - cy) < r + k + 3]
        if not act:
            continue
        cov = []
        cr, cg, cb = [], [], []
        for x in range(xmin, xmax):
            xc = x + 0.5
            d = 1e9
            best = 1e9
            near = act[0]
            for (cx, cy, r) in act:
                d2 = sqrt((xc - cx) ** 2 + (yc - cy) ** 2) - r
                if d2 < best:
                    best = d2
                    near = (cx, cy, r)
                h = 0.5 + 0.5 * (d2 - d) / k
                if h < 0.0:
                    h = 0.0
                elif h > 1.0:
                    h = 1.0
                d = d2 + (d - d2) * h - k * h * (1.0 - h)
            a = clamp(0.5 - d * inv) * alpha
            cov.append(a)
            if a > 0.0:
                c = color_fn(xc, yc, -d, near)
                cr.append(c[0]); cg.append(c[1]); cb.append(c[2])
            else:
                cr.append(0.0); cg.append(0.0); cb.append(0.0)
        if max(cov) > 0.0:
            blend_span(y, xmin, cov, cr, cg, cb)


# ----------------------------------------------------------------------------
# scene constants
# ----------------------------------------------------------------------------
rng = random.Random(20261116)

LEAN = math.radians(5.0)          # the tower leans right as it climbs
CA, SA = math.cos(LEAN), math.sin(LEAN)
PX, PY = 484.0, 440.0             # pivot: centre of the torn base on screen
HORIZON = 548                     # the camera looks slightly down on the sea
TOWER_H = 262.0                   # masonry height (along the axis)
W_BASE = 68.0
W_TOP = 44.0
S_IMPACT = 382.0                  # exhaust length from the base to the sea
IMPACT_Y = PY + S_IMPACT * CA     # where the exhaust meets the water (screen y)
IX = PX - S_IMPACT * SA
RING_A, RING_B = 430.0, 98.0      # the shock ring on the water around the impact

SKY_TOP = hexc('#02041a')
SKY_MID = hexc('#071a44')
SKY_HOR = hexc('#0b3250')
SEA_TOP = hexc('#0d4b68')
SEA_BOT = hexc('#03131f')

FIRE_BLUE = (0.78, 0.9, 1.0)
FIRE_WHITE = (1.0, 0.99, 0.94)
FIRE_YEL = (1.0, 0.86, 0.38)
FIRE_ORA = (1.0, 0.5, 0.08)
FIRE_RED = (0.85, 0.18, 0.02)

RED = hexc('#cf2a1e')
WHITE = hexc('#f6f3ec')


def to_screen(across, along):
    """Local tower frame (across to the right, along up the axis) -> screen."""
    return (PX + across * CA + along * SA, PY + across * SA - along * CA)


def to_local(x, y):
    dx, dy = x - PX, y - PY
    return (dx * CA + dy * SA, dx * SA - dy * CA)


def tower_hw(along):
    return W_BASE + (W_TOP - W_BASE) * clamp(along / TOWER_H)


# ----------------------------------------------------------------------------
# layers
# ----------------------------------------------------------------------------
def draw_sky():
    vgradient(0, HORIZON // 2, SKY_TOP, SKY_MID, 1.3)
    vgradient(HORIZON // 2, HORIZON, SKY_MID, SKY_HOR, 0.8)
    # horizon haze
    for y in range(HORIZON - 60, HORIZON):
        a = 0.16 * smooth(HORIZON - 60, HORIZON, y) ** 1.5
        blend_span(y, 0, [a] * W, 0.25, 0.55, 0.7, add=True)


def draw_stars():
    for _ in range(640):
        x = rng.uniform(0, W)
        y = rng.uniform(0, HORIZON - 40)
        if rng.random() < (y / HORIZON) ** 2 * 0.9:
            continue
        r = rng.choice([0.6, 0.7, 0.9, 1.1, 1.4, 1.9])
        br = rng.uniform(0.35, 1.0)
        tint = rng.choice([(1.0, 1.0, 1.0), (0.8, 0.9, 1.0), (1.0, 0.95, 0.85)])
        disc(x, y, r, (tint[0] * br, tint[1] * br, tint[2] * br), add=True)
        if r >= 1.4 and rng.random() < 0.6:
            glow(x, y, 4.0, 4.0, tint, 0.35)


def draw_sea():
    for y in range(HORIZON, H):
        t = (y - HORIZON) / (H - HORIZON)
        c = mix(SEA_TOP, SEA_BOT, t ** 0.8)
        o = y * W
        R[o:o + W] = [c[0]] * W
        G[o:o + W] = [c[1]] * W
        B[o:o + W] = [c[2]] * W
    # fire reflection: a shimmering column under the blast, broken into slivers
    for y in range(int(IMPACT_Y) - 30, H):
        d = (y - IMPACT_Y) / (H - IMPACT_Y)
        if d < 0:
            d = 0.0
        half = 150.0 + 380.0 * d ** 1.2
        fall = (1.0 - d) ** 0.9
        yy = float(y)
        shimmer = 0.55 + 0.45 * math.sin(yy * 0.37 + math.sin(yy * 0.091) * 3.1) * math.sin(yy * 0.173 + 1.3) * math.sin(yy * 0.051)
        amp = 0.8 * fall * (0.35 + 0.65 * shimmer)
        x0 = max(0, int(IX - half) - 1)
        x1 = min(W, int(IX + half) + 2)
        inv = 1.0 / half
        cov = [amp * max(0.0, 1.0 - abs((x + 0.5 - IX) * inv)) ** 1.6 for x in range(x0, x1)]
        c = mix(FIRE_ORA, FIRE_RED, d)
        blend_span(y, x0, cov, c[0], c[1], c[2], add=True)


def cyl_shade(u):
    nz = sqrt(max(0.0, 1.0 - u * u))
    lam = max(0.0, -0.58 * u + 0.81 * nz)      # key light upper-left
    rim = max(0.0, 0.75 * u + 0.3 * nz) ** 3   # warm rim from the right
    return nz, lam, rim


def draw_tower():
    bands = 6
    band_h = TOWER_H / bands
    corners = [to_screen(-W_BASE, 0), to_screen(W_BASE, 0), to_screen(-W_TOP, TOWER_H), to_screen(W_TOP, TOWER_H)]
    ymin = int(min(c[1] for c in corners)) - 2
    ymax = int(max(c[1] for c in corners)) + 2
    xmin = int(min(c[0] for c in corners)) - 2
    xmax = int(max(c[0] for c in corners)) + 3
    for y in range(ymin, ymax + 1):
        yc = y + 0.5
        cov = []
        cr, cg, cb = [], [], []
        for x in range(xmin, xmax):
            xc = x + 0.5
            across, along = to_local(xc, yc)
            if along < -1.0 or along > TOWER_H + 1.0:
                cov.append(0.0); cr.append(0.0); cg.append(0.0); cb.append(0.0)
                continue
            hw = tower_hw(along)
            a = clamp(hw - abs(across) + 0.5)
            a *= clamp(along + 0.5) * clamp(TOWER_H - along + 0.5)
            if a <= 0.0:
                cov.append(0.0); cr.append(0.0); cg.append(0.0); cb.append(0.0)
                continue
            bi = int((TOWER_H - along) / band_h)
            base = RED if bi % 2 == 0 else WHITE
            bt = ((TOWER_H - along) / band_h) % 1.0
            seam = 1.0 - (0.4 * smooth(0.0, 0.025, bt) * (1 - smooth(0.025, 0.07, bt)) if bt < 0.1 else 0.0)
            u = clamp(across / hw, -1.0, 1.0)
            nz, lam, rim = cyl_shade(u)
            k = (0.2 + 0.8 * lam) * seam
            fire = 1.0 * smooth(1.0, 0.0, along / TOWER_H) ** 2.0
            r = base[0] * k + 0.02 * (1 - lam)
            g = base[1] * k + 0.04 * (1 - lam)
            b = base[2] * k + 0.10 * (1 - lam)
            f = fire * (0.45 + 0.55 * nz) + 0.6 * rim
            r += FIRE_ORA[0] * f * (0.5 + 0.5 * base[0])
            g += FIRE_ORA[1] * f * (0.5 + 0.5 * base[1])
            b += FIRE_ORA[2] * f * (0.5 + 0.5 * base[2])
            scorch = smooth(50.0, 0.0, along) * 0.5
            r *= 1 - scorch * 0.45; g *= 1 - scorch * 0.7; b *= 1 - scorch * 0.8
            cov.append(a); cr.append(r); cg.append(g); cb.append(b)
        if max(cov) > 0.0:
            blend_span(y, xmin, cov, cr, cg, cb)
    # torn base: irregular broken blocks hanging below the bottom edge
    dark = hexc('#17100d')
    hot = mix(FIRE_ORA, FIRE_YEL, 0.4)
    edge = -W_BASE
    pieces = []
    while edge < W_BASE - 4:
        wdt = rng.uniform(11, 26)
        nxt = min(W_BASE, edge + wdt)
        depth = rng.uniform(6, 24)
        pieces.append((edge, nxt, depth))
        edge = nxt
    for (a0, a1, depth) in pieces:
        m = (a0 + a1) / 2
        pts = [to_screen(a0, 2), to_screen(a1, 2), to_screen(a1 - rng.uniform(0, 5), -depth * rng.uniform(0.4, 1.0)),
               to_screen(m, -depth), to_screen(a0 + rng.uniform(0, 5), -depth * rng.uniform(0.4, 1.0))]

        def col(x, y, depth=depth):
            _, al = to_local(x, y)
            return mix(dark, hot, 0.8 * smooth(2.0, -depth, al))

        poly(pts, col)
    for i in range(3):
        across = rng.uniform(-W_BASE * 0.7, W_BASE * 0.7)
        along = -2.0
        for seg in range(rng.randint(3, 5)):
            d_al = rng.uniform(14, 30)
            d_ac = rng.uniform(-9, 9)
            p0 = to_screen(across, along)
            p1 = to_screen(across + d_ac, along + d_al)
            w = 2.4 * (1 - seg / 6.0)
            thick_line(p0, p1, w, (0.08, 0.04, 0.03), alpha=0.9)
            across += d_ac
            along += d_al


def draw_lantern():
    top = TOWER_H
    hw = W_TOP
    deck_w = hw * 1.5
    deck_h = 10.0
    deck = hexc('#1b1d26')
    c = to_screen(0, top)
    ymin = int(c[1] - deck_w * SA - deck_h - 3)
    ymax = int(c[1] + deck_w * SA + deck_h + 3)
    xmin = int(c[0] - deck_w - 4)
    xmax = int(c[0] + deck_w + 5)
    for y in range(ymin, ymax + 1):
        yc = y + 0.5
        cov = []
        cr, cg, cb = [], [], []
        for x in range(xmin, xmax):
            across, along = to_local(x + 0.5, yc)
            dy = (along - top) / deck_h
            dd = sqrt((across / deck_w) ** 2 + dy * dy) - 1.0
            a = clamp(0.5 - dd * deck_w)
            cov.append(a)
            lit = 0.28 * max(0.0, dy)
            cr.append(deck[0] + lit); cg.append(deck[1] + lit); cb.append(deck[2] + lit * 1.2)
        blend_span(y, xmin, cov, cr, cg, cb)
    poly([to_screen(-hw - 1, top - 14), to_screen(hw + 1, top - 14), to_screen(hw + 1, top), to_screen(-hw - 1, top)],
         (0.02, 0.02, 0.05), alpha=0.5, soft=4.0)
    rail_h = 28.0
    for i in range(13):
        t = math.pi * i / 12.0
        ax = deck_w * 0.96 * math.cos(t)
        ay = top - deck_h * 0.9 * math.sin(t)
        thick_line(to_screen(ax, ay), to_screen(ax, ay + rail_h), 2.0, (0.07, 0.07, 0.09), alpha=0.9)
    prev = None
    for i in range(25):
        t = math.pi * i / 24.0
        p = to_screen(deck_w * 0.96 * math.cos(t), top + rail_h - deck_h * 0.9 * math.sin(t))
        if prev:
            thick_line(prev, p, 2.0, (0.07, 0.07, 0.09), alpha=0.9)
        prev = p
    lw = hw * 0.8
    l0 = top + rail_h + 1
    l1 = l0 + 56
    corners = [to_screen(-lw, l0), to_screen(lw, l0), to_screen(-lw, l1), to_screen(lw, l1)]
    ymin = int(min(c[1] for c in corners)) - 2
    ymax = int(max(c[1] for c in corners)) + 2
    xmin = int(min(c[0] for c in corners)) - 2
    xmax = int(max(c[0] for c in corners)) + 3
    for y in range(ymin, ymax + 1):
        yc = y + 0.5
        cov = []
        cr, cg, cb = [], [], []
        for x in range(xmin, xmax):
            across, along = to_local(x + 0.5, yc)
            a = clamp(lw - abs(across) + 0.5) * clamp(along - l0 + 0.5) * clamp(l1 - along + 0.5)
            cov.append(a)
            if a <= 0:
                cr.append(0.0); cg.append(0.0); cb.append(0.0)
                continue
            u = clamp(across / lw, -1.0, 1.0)
            nz = sqrt(max(0.0, 1 - u * u))
            k = 0.7 + 0.3 * nz
            m = min(abs(u - m0) for m0 in (-0.62, -0.21, 0.21, 0.62))
            mull = smooth(0.0, 0.05, m) * 0.85 + 0.15
            bar = 1.0 - 0.75 * (1 - smooth(0.0, 3.0, abs(along - (l0 + l1) / 2)))
            kk = k * mull * bar
            cr.append(1.0 * kk); cg.append(0.95 * kk); cb.append(0.74 * kk)
        blend_span(y, xmin, cov, cr, cg, cb)
    r_top = l1 + 42
    roof_dark = hexc('#4a0f0e')
    roof_lit = hexc('#b8382a')
    poly([to_screen(-lw - 7, l1), to_screen(lw + 7, l1), to_screen(0, r_top)],
         lambda x, y: mix(roof_lit, roof_dark, smooth(-0.7, 0.7, to_local(x, y)[0] / lw)))
    thick_line(to_screen(0, r_top - 2), to_screen(0, r_top + 20), 2.4, (0.1, 0.08, 0.08))
    fin = to_screen(0, r_top + 20)
    disc(fin[0], fin[1], 4.2, (0.22, 0.09, 0.07))
    disc(fin[0], fin[1] - 1.5, 1.8, (0.9, 0.8, 0.7), add=True)
    lc = to_screen(0, (l0 + l1) / 2)
    glow(lc[0], lc[1], 120, 90, (1.0, 0.94, 0.72), 0.5, power=1.6)
    glow(lc[0], lc[1], 32, 24, (1.0, 1.0, 0.95), 0.8)
    glow(lc[0], lc[1], 360, 1.8, (0.6, 0.8, 1.0), 0.6, power=1.4)
    glow(lc[0], lc[1], 1.8, 70, (0.8, 0.9, 1.0), 0.4, power=1.4)
    return lc


def draw_beams(lc):
    half_ang = math.radians(5.0)
    tan_h = math.tan(half_ang)
    for side in (-1, 1):
        ang = math.radians(180 if side < 0 else 0) + side * math.radians(-30)
        length = 980.0
        dx, dy = math.cos(ang), math.sin(ang)
        px, py = -dy, dx
        sp = length * tan_h
        p1 = (lc[0] + dx * length + px * sp, lc[1] + dy * length + py * sp)
        p2 = (lc[0] + dx * length - px * sp, lc[1] + dy * length - py * sp)

        def col(x, y, dx=dx, dy=dy, px=px, py=py):
            rx, ry = x - lc[0], y - lc[1]
            along = rx * dx + ry * dy
            if along <= 0:
                return (0.0, 0.0, 0.0)
            across = abs(rx * px + ry * py)
            w = along * tan_h
            edge = 1.0 - (across / max(w, 1.0)) ** 2
            k = 0.95 * max(0.0, edge) / (1.0 + along / 300.0)
            return (k, k * 0.97, k * 0.82)

        poly([(lc[0], lc[1]), p1, p2], col, add=True)


def draw_plume_back():
    glow(IX, IMPACT_Y - 60, 420, 330, FIRE_ORA, 0.45, power=2.2)
    glow(IX, IMPACT_Y - 80, 230, 230, FIRE_YEL, 0.4, power=2.0)
    glow(PX, PY + 40, 80, 110, FIRE_WHITE, 0.55, power=2.0)


def draw_plume_core():
    for y in range(int(PY) - 8, int(IMPACT_Y) + 20):
        yc = y + 0.5
        s = (yc - PY) / CA
        if s < -6:
            continue
        ax = to_screen(0, -max(0.0, s))[0]
        ts = clamp(s / S_IMPACT)
        hw_core = 28.0 + 0.075 * s + 0.00018 * s * s
        hw_env = hw_core * 1.9 + 12
        x0 = max(0, int(ax - hw_env) - 2)
        x1 = min(W, int(ax + hw_env) + 3)
        xs = [x + 0.5 for x in range(x0, x1)]
        c_env = mix(mix(FIRE_ORA, FIRE_RED, clamp(ts * 1.2 - 0.2)), FIRE_RED, clamp(ts * 1.5 - 0.8))
        env = [0.95 * max(0.0, 1.0 - abs(xc - ax) / hw_env) ** 1.8 for xc in xs]
        blend_span(y, x0, env, c_env[0], c_env[1], c_env[2], add=True)
        cov = [clamp((hw_core - abs(xc - ax)) / 1.4 + 0.5) for xc in xs]
        if max(cov) <= 0:
            continue
        # shock diamonds: the white core swells and pinches along the axis
        lobe = 0.5 + 0.5 * math.cos(2 * math.pi * s / 58.0)
        if ts < 0.1:
            body = mix(FIRE_BLUE, FIRE_WHITE, ts / 0.1)
        else:
            body = mix(FIRE_WHITE, (1.0, 0.95, 0.75), smooth(0.4, 1.0, ts) * 0.6)
        core_w = hw_core * (0.3 + 0.3 * lobe)
        yel = mix(FIRE_YEL, FIRE_ORA, 0.25 + 0.3 * ts)
        cr, cg, cb = [], [], []
        for xc in xs:
            dxa = abs(xc - ax)
            u = min(1.0, dxa / hw_core)
            c = mix(body, yel, smooth(core_w, core_w + hw_core * 0.45, dxa))
            c = mix(c, FIRE_ORA, smooth(0.72, 1.0, u) ** 1.3)
            c = mix(c, (1.0, 1.0, 1.0), smooth(core_w * 0.9, 0.0, dxa) * (0.4 + 0.6 * lobe) * 0.7)
            cr.append(c[0]); cg.append(c[1]); cb.append(c[2])
        blend_span(y, x0, cov, cr, cg, cb)


def draw_impact():
    def dome(x, y, r):
        return mix(mix(FIRE_WHITE, FIRE_YEL, smooth(0.3, 0.8, r)), FIRE_ORA, smooth(0.8, 1.0, r))
    ellipse(IX, IMPACT_Y + 4, 108, 25, dome, soft=6.0)
    glow(IX, IMPACT_Y, 120, 50, FIRE_WHITE, 0.4, power=2.0)


def crown(a, b, cy, wall_h, spire_h, strength, back, col_lo, col_hi, n_spires):
    """A wall of spray along an elliptical ring (front or back half): low wall plus distinct spires."""
    sgn = -1 if back else 1
    for x in range(max(0, int(IX - a) + 1), min(W, int(IX + a))):
        t = (x + 0.5 - IX) / a
        if abs(t) >= 1.0:
            continue
        yr = cy + sgn * b * sqrt(1 - t * t)
        n = 0.5 + 0.5 * math.sin(x * 0.09) * math.sin(x * 0.031 + 1.0)
        hgt = wall_h * (0.6 + 0.8 * n) * (0.45 + 0.55 * (1 - abs(t)) ** 0.5)
        y0 = max(0, int(yr - hgt))
        y1 = min(H - 1, int(yr + 4))
        if y1 <= y0:
            continue
        cov, cr, cg, cb = [], [], [], []
        for y in range(y0, y1 + 1):
            f = (yr - (y + 0.5)) / hgt
            if f < 0:
                a_ = strength * (1 - min(1.0, -f * hgt / 4.0))
            else:
                a_ = strength * max(0.0, 1.0 - f) ** 1.4
            cov.append(a_)
            c = mix(col_lo, col_hi, clamp(f))
            cr.append(c[0]); cg.append(c[1]); cb.append(c[2])
        blend_column(x, y0, cov, cr, cg, cb, add=True)
    for i in range(n_spires):
        th = math.pi * (i + 0.5) / n_spires + rng.uniform(-0.6, 0.6) * math.pi / n_spires
        x = IX + a * math.cos(th)
        y = cy + sgn * b * math.sin(th)
        hgt = max(4.0, spire_h * rng.uniform(0.35, 1.0) * (0.45 + 0.55 * max(0.0, math.sin(th)) ** 0.5))
        wdt = rng.uniform(0.012, 0.028) * a
        lean = math.cos(th) * rng.uniform(0.15, 0.45)
        pts = [(x - wdt, y + 4), (x + wdt, y + 4), (x + lean * hgt + wdt * 0.35, y - hgt), (x + lean * hgt - wdt * 0.35, y - hgt)]

        def col(xx, yy, x=x, y=y, hgt=hgt, wdt=wdt, lean=lean):
            f = clamp((y - yy) / hgt)
            cx_ = x + lean * hgt * f
            wloc = wdt * (1 - 0.65 * f) + 0.8
            across = abs(xx - cx_) / wloc
            k = strength * (1 - f) ** 1.2 * max(0.0, 1 - across * across)
            c = mix(col_lo, col_hi, f)
            return (c[0] * k, c[1] * k, c[2] * k)

        poly(pts, col, add=True, soft=1.2)


def draw_ring_rim():
    for (aa, bb, strength, width, col) in ((RING_A, RING_B, 0.6, 0.035, (0.85, 1.0, 1.0)),
                                           (RING_A * 1.18, RING_B * 1.18, 0.1, 0.04, (0.5, 0.85, 0.95))):
        x0 = max(0, int(IX - aa * 1.06)); x1 = min(W, int(IX + aa * 1.06) + 1)
        xs = [((x + 0.5 - IX) / aa) ** 2 for x in range(x0, x1)]
        for y in range(max(HORIZON, int(IMPACT_Y - bb * 1.1)), min(H, int(IMPACT_Y + bb * 1.1) + 1)):
            dy2 = ((y + 0.5 - IMPACT_Y) / bb) ** 2
            cov = []
            for dx in xs:
                r = sqrt(dx + dy2)
                band = exp(-((r - 1.0) / width) ** 2)
                inner = 0.22 * (1.0 - r) if r < 1.0 else 0.0
                cov.append(strength * (band + inner))
            blend_span(y, x0, cov, col[0], col[1], col[2], add=True)


def draw_deluge_flames():
    for i in range(18):
        side = -1 if i % 2 else 1
        f = (i // 2) / 8.0
        bx = IX + side * (30 + 40 * f)
        by = IMPACT_Y - 10 + rng.uniform(-14, 10)
        length = rng.uniform(150, 320) * (1.0 - 0.45 * f)
        a_deg = rng.uniform(-26, 10)
        ang = math.radians(a_deg) if side > 0 else math.radians(180 - a_deg)
        dx, dy = math.cos(ang), math.sin(ang)
        px, py = -dy, dx
        wdt = rng.uniform(14, 36)
        k = 0.33
        tip = (bx + dx * length, by + dy * length)
        mid = (bx + dx * length * k, by + dy * length * k)
        pts = [(bx, by), (mid[0] + px * wdt, mid[1] + py * wdt), tip, (mid[0] - px * wdt, mid[1] - py * wdt)]
        c0 = mix(FIRE_WHITE, FIRE_YEL, 0.4 + f * 0.6)

        def col(x, y, bx=bx, by=by, dx=dx, dy=dy, px=px, py=py, length=length, wdt=wdt, c0=c0):
            rx, ry = x - bx, y - by
            t = clamp((rx * dx + ry * dy) / length)
            wloc = wdt * (t / k if t < k else (1 - t) / (1 - k)) + 1.0
            across = abs(rx * px + ry * py) / wloc
            fade = max(0.0, 1.0 - across * across)
            c = mix(mix(c0, FIRE_ORA, t ** 0.7), FIRE_RED, clamp(t * 1.5 - 0.5))
            k2 = 0.9 * (1 - t ** 1.4) * fade
            return (c[0] * k2, c[1] * k2, c[2] * k2)

        poly(pts, col, add=True, soft=1.6)


def draw_sparks():
    for i in range(240):
        th = rng.uniform(math.radians(-20), math.radians(200))
        if rng.random() < 0.5:
            th = math.pi / 2 + (th - math.pi / 2) * 1.15
        d = 80 + 460 * rng.random() ** 1.4
        x = IX + d * math.cos(th)
        y = IMPACT_Y - 6 - d * math.sin(th) * 0.5
        L = 6 + d * rng.uniform(0.05, 0.1)
        p1 = (x + math.cos(th) * L, y - math.sin(th) * L * 0.5)
        c = mix(FIRE_WHITE, mix(FIRE_YEL, FIRE_ORA, rng.random()), smooth(60, 300, d))
        thick_line((x, y), p1, rng.uniform(1.2, 2.6), c, alpha=rng.uniform(0.35, 1.0) * (1 - d / 700.0), add=True, soft=0.8)
    for i in range(40):
        across = rng.choice((-1, 1)) * rng.uniform(80, 230)
        along = rng.uniform(-60, 160)
        L = rng.uniform(6, 20)
        p0 = to_screen(across, along)
        p1 = to_screen(across + math.copysign(rng.uniform(0, 6), across), along + L)
        c = mix(FIRE_WHITE, FIRE_YEL, rng.random())
        thick_line(p0, p1, rng.uniform(1.0, 2.2), c, alpha=rng.uniform(0.35, 0.9), add=True, soft=0.8)
    # water droplets thrown up off the inner crown
    for i in range(90):
        th = rng.uniform(0.0, math.pi)
        rr = rng.uniform(0.7, 1.25)
        x = IX + 150.0 * rr * math.cos(th)
        y = IMPACT_Y + 6 + 36.0 * rr * math.sin(th) - rng.uniform(40, 190)
        L = rng.uniform(3, 14)
        p1 = (x + math.cos(th) * L * 0.3, y - L)
        a = rng.uniform(0.3, 0.9) * smooth(IMPACT_Y - 220, IMPACT_Y - 60, y)
        thick_line((x, y), p1, rng.uniform(1.2, 2.4), (0.95, 0.98, 1.0), alpha=a, add=True, soft=0.8)


def draw_debris():
    rock = hexc('#120d0b')
    hot = mix(FIRE_ORA, FIRE_YEL, 0.35)
    for i in range(10):
        side = -1 if i % 2 else 1
        f = (i // 2) / 4.0
        across = side * rng.uniform(95, 240) * (0.6 + 0.4 * f)
        along = -rng.uniform(10, 40) - 180 * f * rng.uniform(0.3, 1.0)
        x, y = to_screen(across, along)
        size = rng.uniform(8, 20) * (1.2 - 0.5 * f)
        n = rng.randint(5, 7)
        pts = []
        for k in range(n):
            ang = 2 * math.pi * k / n + rng.uniform(-0.25, 0.25)
            rr = size * rng.uniform(0.6, 1.0)
            pts.append((x + rr * math.cos(ang), y + rr * math.sin(ang)))
        bx, by = to_screen(across * 0.55, along * 0.55 + 8)
        poly([(x - size * 0.5, y), (x + size * 0.5, y), (bx + 1.5, by), (bx - 1.5, by)],
             (0.95, 0.4, 0.06), alpha=0.28, add=True, soft=3.0)

        def col(px, py, x=x, size=size, side=side):
            u = (px - x) / size * -side
            return mix(rock, hot, smooth(-0.6, 1.0, u) ** 1.3 * 0.9)

        poly(pts, col)


def draw_boat():
    bx, by = 150.0, 952.0
    lean = -0.34
    sc = 1.0
    hull = [(bx - 46 * sc, by), (bx + 42 * sc, by), (bx + 30 * sc, by + 12 * sc), (bx - 34 * sc, by + 12 * sc)]
    poly(hull, (0.02, 0.02, 0.04))
    mast_top = (bx + lean * 100 * sc, by - 100 * sc)
    thick_line((bx, by), mast_top, 2.8, (0.02, 0.02, 0.04))
    sail = [(bx + 3, by - 6), (mast_top[0] + 2, mast_top[1] + 6), (bx + 3 + lean * 20 + 64 * sc, by - 18)]
    poly(sail, lambda x, y: mix(hexc('#cfc6b6'), FIRE_ORA, 0.6 * smooth(bx - 10, bx + 55, x)))
    jib = [(bx - 2, by - 6), (mast_top[0] - 1, mast_top[1] + 10), (bx - 44 * sc + lean * 10, by - 8)]
    poly(jib, lambda x, y: mix(hexc('#a89f92'), hexc('#5a4838'), smooth(bx - 40, bx, x)))
    poly([(bx + 3, by + 14), (mast_top[0] + 2, by + 14 + (by - mast_top[1]) * 0.6), (bx + 3 + lean * 20 + 64 * sc, by + 26)],
         (0.3, 0.17, 0.07), alpha=0.3, soft=2.5)
    poly([(bx - 70, by + 10), (bx + 60, by + 10), (bx + 60, by + 13), (bx - 70, by + 13)], (0.5, 0.75, 0.8), alpha=0.35, add=True, soft=2.0)


def vignette_and_grade():
    cx, cy = W / 2, H * 0.5
    for y in range(H):
        dy = ((y + 0.5 - cy) / (H * 0.74)) ** 2
        o = y * W
        vs = [1.0 - 0.45 * smooth(0.5, 1.6, sqrt(((x + 0.5 - cx) / (W * 0.74)) ** 2 + dy)) for x in range(W)]
        R[o:o + W] = [min(1.0, max(0.0, r * v)) for r, v in zip(R[o:o + W], vs)]
        G[o:o + W] = [min(1.0, max(0.0, g * v)) for g, v in zip(G[o:o + W], vs)]
        B[o:o + W] = [min(1.0, max(0.0, b * v)) for b, v in zip(B[o:o + W], vs)]


# ----------------------------------------------------------------------------
# PNG
# ----------------------------------------------------------------------------
def write_png(path):
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)

    absval = [b if b < 128 else 256 - b for b in range(256)]
    raw = bytearray()
    prev = bytes(W * 3)
    for y in range(H):
        o = y * W
        row = bytearray(W * 3)
        row[0::3] = bytes([int(v * 255.0 + 0.5) for v in R[o:o + W]])
        row[1::3] = bytes([int(v * 255.0 + 0.5) for v in G[o:o + W]])
        row[2::3] = bytes([int(v * 255.0 + 0.5) for v in B[o:o + W]])
        row = bytes(row)
        sub = bytes([(a - b) & 255 for a, b in zip(row, bytes(3) + row[:-3])])
        up = bytes([(a - b) & 255 for a, b in zip(row, prev)])
        s_sub = sum([absval[b] for b in sub])
        s_up = sum([absval[b] for b in up])
        if s_sub <= s_up:
            raw.append(1)
            raw.extend(sub)
        else:
            raw.append(2)
            raw.extend(up)
        prev = row
    ihdr = struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0)
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
           + chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + chunk(b'IEND', b''))
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    with open(path, 'wb') as f:
        f.write(png)
    return len(png)


def main():
    if len(sys.argv) > 1:
        out = sys.argv[1]
    else:
        out = os.path.join(os.environ.get('MAKEFUN_OUTPUT_DIR', '/output'), 'entry.png')
    draw_sky()
    draw_stars()
    draw_sea()
    draw_plume_back()
    crown(RING_A, RING_B, IMPACT_Y, 8, 30, 0.45, True, (0.5, 0.8, 0.9), (0.7, 0.9, 1.0), 20)        # far ring, back half
    draw_plume_core()
    draw_impact()
    crown(150.0, 36.0, IMPACT_Y + 6, 26, 110, 0.7, True, (1.0, 0.9, 0.75), (0.9, 0.95, 1.0), 14)    # inner crown, back
    draw_deluge_flames()
    crown(150.0, 36.0, IMPACT_Y + 6, 30, 140, 0.85, False, (1.0, 0.9, 0.75), (0.95, 0.98, 1.0), 18) # inner crown, front
    crown(RING_A, RING_B, IMPACT_Y, 12, 50, 0.8, False, (0.75, 0.95, 1.0), (0.85, 0.97, 1.0), 22)   # far ring, front
    draw_ring_rim()
    draw_sparks()
    draw_debris()
    draw_tower()
    lc = draw_lantern()
    draw_beams(lc)
    draw_boat()
    vignette_and_grade()
    size = write_png(out)
    print('wrote %s (%d bytes)' % (out, size))


if __name__ == '__main__':
    main()
