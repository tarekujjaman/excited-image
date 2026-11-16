#!/usr/bin/env python3
"""LIFTOFF -- a red-and-white lighthouse tears free of its rock and launches
like a rocket over a night sea.

Fully procedural, deterministic PNG renderer. Python 3.13 standard library
only (no Pillow, no numpy, no network, no clock, seeded randomness).

Usage:  python main.py [output.png]      (default: /output/entry.png)
"""
import math
import os
import random
import struct
import sys
import zlib
from math import atan2, cos, exp, pi, sin, sqrt

# ----------------------------------------------------------------------------
# canvas
# ----------------------------------------------------------------------------
W = H = 1024
N = W * H
R = [0.0] * N
G = [0.0] * N
B = [0.0] * N

SEED = 20261116
rng = random.Random(SEED)

# scene anchors (screen space, y down)
HOR = 672                  # sea horizon
BX, BY = 548, 388          # lighthouse base centre (already airborne)
TILT = math.radians(7.0)   # lighthouse leans right as it climbs
IX, IY = 530, 568          # launch crater on the rock where the exhaust hits
RCX, RTOP = 532, 560       # sea-stack rock: centre x and peak y
SX, SY = IX, HOR + 6       # centre of the shock ring on the water

# ----------------------------------------------------------------------------
# value noise / fbm
# ----------------------------------------------------------------------------
LS = 256
LMASK = LS - 1
LAT = [rng.random() for _ in range(LS * LS)]


def vnoise(x, y):
    """Smooth value noise, x and y must be >= 0."""
    xi = int(x)
    yi = int(y)
    fx = x - xi
    fy = y - yi
    fx = fx * fx * (3.0 - 2.0 * fx)
    fy = fy * fy * (3.0 - 2.0 * fy)
    x0 = xi & LMASK
    x1 = (xi + 1) & LMASK
    y0 = (yi & LMASK) * LS
    y1 = ((yi + 1) & LMASK) * LS
    a = LAT[y0 + x0]
    b = LAT[y0 + x1]
    c = LAT[y1 + x0]
    d = LAT[y1 + x1]
    ab = a + (b - a) * fx
    return ab + ((c + (d - c) * fx) - ab) * fy


def fbm(x, y, octaves=3):
    """Fractal noise in [0, 1]."""
    x += 1000.0
    y += 1000.0
    s = 0.0
    a = 0.5
    norm = 0.0
    for _ in range(octaves):
        s += a * vnoise(x, y)
        norm += a
        x = x * 2.03 + 17.1
        y = y * 2.01 + 9.7
        a *= 0.5
    return s / norm


def clamp01(v):
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


# ----------------------------------------------------------------------------
# fire colour ramp (lookup table, index = heat * 400, heat clamped to 1.27)
# ----------------------------------------------------------------------------
_FIRE_KEYS = [
    (0.00, (0.10, 0.010, 0.00)),
    (0.22, (0.55, 0.060, 0.01)),
    (0.45, (1.00, 0.330, 0.04)),
    (0.68, (1.00, 0.700, 0.18)),
    (0.88, (1.00, 0.940, 0.62)),
    (1.10, (1.00, 1.000, 0.96)),
    (1.27, (1.00, 1.000, 1.00)),
]


def _fire_colour(h):
    for k in range(len(_FIRE_KEYS) - 1):
        h0, c0 = _FIRE_KEYS[k]
        h1, c1 = _FIRE_KEYS[k + 1]
        if h <= h1:
            t = (h - h0) / (h1 - h0)
            return (c0[0] + (c1[0] - c0[0]) * t,
                    c0[1] + (c1[1] - c0[1]) * t,
                    c0[2] + (c1[2] - c0[2]) * t)
    return _FIRE_KEYS[-1][1]


FIRE = [_fire_colour(k / 400.0) for k in range(509)]


# ----------------------------------------------------------------------------
# primitive helpers
# ----------------------------------------------------------------------------
def blend_px(i, r, g, b, a):
    ia = 1.0 - a
    R[i] = R[i] * ia + r * a
    G[i] = G[i] * ia + g * a
    B[i] = B[i] * ia + b * a


def line_add(x0, y0, x1, y1, r, g, b, width, alpha, fade=False):
    """Additive anti-aliased segment; with fade the end (x1, y1) fades out."""
    hw = width * 0.5
    xa = max(0, int(min(x0, x1) - hw - 1))
    xb = min(W - 1, int(max(x0, x1) + hw + 1))
    ya = max(0, int(min(y0, y1) - hw - 1))
    yb = min(H - 1, int(max(y0, y1) + hw + 1))
    if xa > xb or ya > yb:
        return
    vx = x1 - x0
    vy = y1 - y0
    l2 = vx * vx + vy * vy
    if l2 < 1e-9:
        l2 = 1e-9
    for y in range(ya, yb + 1):
        row = y * W
        py = y + 0.5 - y0
        for x in range(xa, xb + 1):
            px = x + 0.5 - x0
            t = (px * vx + py * vy) / l2
            if t < 0.0:
                t = 0.0
            elif t > 1.0:
                t = 1.0
            dx = px - vx * t
            dy = py - vy * t
            cov = hw + 0.5 - sqrt(dx * dx + dy * dy)
            if cov <= 0.0:
                continue
            if cov > 1.0:
                cov = 1.0
            if fade:
                cov *= 1.0 - t
            a = cov * alpha
            i = row + x
            R[i] += r * a
            G[i] += g * a
            B[i] += b * a


def line_blend(x0, y0, x1, y1, r, g, b, width, alpha=1.0):
    """Opaque (alpha-blended) anti-aliased segment."""
    hw = width * 0.5
    xa = max(0, int(min(x0, x1) - hw - 1))
    xb = min(W - 1, int(max(x0, x1) + hw + 1))
    ya = max(0, int(min(y0, y1) - hw - 1))
    yb = min(H - 1, int(max(y0, y1) + hw + 1))
    vx = x1 - x0
    vy = y1 - y0
    l2 = vx * vx + vy * vy
    if l2 < 1e-9:
        l2 = 1e-9
    for y in range(ya, yb + 1):
        row = y * W
        py = y + 0.5 - y0
        for x in range(xa, xb + 1):
            px = x + 0.5 - x0
            t = (px * vx + py * vy) / l2
            t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
            dx = px - vx * t
            dy = py - vy * t
            cov = hw + 0.5 - sqrt(dx * dx + dy * dy)
            if cov <= 0.0:
                continue
            if cov > 1.0:
                cov = 1.0
            blend_px(row + x, r, g, b, cov * alpha)


def fill_convex(pts, colour_fn, alpha=1.0):
    """Anti-aliased convex polygon fill; colour_fn(x, y) -> (r, g, b)."""
    n = len(pts)
    area = 0.0
    for k in range(n):
        x0, y0 = pts[k]
        x1, y1 = pts[(k + 1) % n]
        area += x0 * y1 - x1 * y0
    sign = 1.0 if area > 0 else -1.0
    edges = []
    for k in range(n):
        x0, y0 = pts[k]
        x1, y1 = pts[(k + 1) % n]
        ex = x1 - x0
        ey = y1 - y0
        ln = sqrt(ex * ex + ey * ey)
        if ln < 1e-9:
            continue
        nx = -ey / ln * sign
        ny = ex / ln * sign
        edges.append((nx, ny, -(nx * x0 + ny * y0)))
    xa = max(0, int(min(p[0] for p in pts)) - 1)
    xb = min(W - 1, int(max(p[0] for p in pts)) + 1)
    ya = max(0, int(min(p[1] for p in pts)) - 1)
    yb = min(H - 1, int(max(p[1] for p in pts)) + 1)
    for y in range(ya, yb + 1):
        row = y * W
        yc = y + 0.5
        for x in range(xa, xb + 1):
            xc = x + 0.5
            d = 1e9
            for nx, ny, c in edges:
                v = nx * xc + ny * yc + c
                if v < d:
                    d = v
            cov = d + 0.5
            if cov <= 0.0:
                continue
            if cov > 1.0:
                cov = 1.0
            r, g, b = colour_fn(xc, yc)
            blend_px(row + x, r, g, b, cov * alpha)


def glow_dot(cx, cy, rad, r, g, b, gain):
    """Additive soft radial glow."""
    ext = int(rad * 3.0) + 1
    for y in range(max(0, int(cy) - ext), min(H, int(cy) + ext + 1)):
        row = y * W
        dy = y + 0.5 - cy
        for x in range(max(0, int(cx) - ext), min(W, int(cx) + ext + 1)):
            dx = x + 0.5 - cx
            v = gain * exp(-(dx * dx + dy * dy) / (rad * rad))
            if v < 0.003:
                continue
            i = row + x
            R[i] += r * v
            G[i] += g * v
            B[i] += b * v


# ----------------------------------------------------------------------------
# layers
# ----------------------------------------------------------------------------
def draw_sky():
    top = (0.005, 0.008, 0.028)
    hor = (0.055, 0.100, 0.170)
    for y in range(0, HOR):
        t = (y / HOR) ** 2.4
        r = top[0] + (hor[0] - top[0]) * t
        g = top[1] + (hor[1] - top[1]) * t
        b = top[2] + (hor[2] - top[2]) * t
        R[y * W:(y + 1) * W] = [r] * W
        G[y * W:(y + 1) * W] = [g] * W
        B[y * W:(y + 1) * W] = [b] * W


def draw_stars():
    for _ in range(640):
        x = rng.uniform(0, W)
        y = rng.uniform(0, HOR - 15)
        if rng.random() < (y / HOR) * 0.75:
            continue
        bright = rng.random() ** 2.4 * 0.85 + 0.10
        sig = 0.55 + 1.0 * rng.random() ** 3
        warm = rng.random()
        cr = 0.85 + 0.15 * warm
        cg = 0.88 + 0.06 * warm
        cb = 1.00 - 0.25 * warm
        xi = int(x)
        yi = int(y)
        for yy in range(max(0, yi - 3), min(H, yi + 4)):
            row = yy * W
            for xx in range(max(0, xi - 3), min(W, xi + 4)):
                dx = xx + 0.5 - x
                dy = yy + 0.5 - y
                v = bright * exp(-(dx * dx + dy * dy) / (2.0 * sig * sig))
                if v < 0.004:
                    continue
                i = row + xx
                R[i] += cr * v
                G[i] += cg * v
                B[i] += cb * v
        if bright > 0.8 and sig > 1.2:
            line_add(x - 5, y, x + 5, y, cr, cg, cb, 1.0, 0.35 * bright)
            line_add(x, y - 5, x, y + 5, cr, cg, cb, 1.0, 0.35 * bright)


def draw_clouds():
    """Thin high stratus wisps lit orange from below by the launch."""
    bands = ((168.0, 0.0043, 1.2, 34.0, 1.0), (252.0, 0.0061, 3.9, 22.0, 0.75))
    for y in range(95, 345):
        row = y * W
        for x in range(W):
            band = 0.0
            yc = 0.0
            for by, fq, ph, sg, wt in bands:
                c = by + 28.0 * sin(x * fq + ph)
                b = exp(-((y - c) / sg) ** 2) * wt
                if b > band:
                    band = b
                    yc = c
            if band < 0.04:
                continue
            n = fbm(x * 0.0052, y * 0.034, 3)
            d = (n - 0.47) * 4.5 * band
            if d <= 0.0:
                continue
            if d > 1.0:
                d = 1.0
            under = clamp01((y - yc + 18.0) / 44.0)
            light = exp(-((x - IX) / 380.0) ** 2) * 0.8 + 0.2
            lr = 0.04 + (0.80 - 0.04) * under * light
            lg = 0.04 + (0.34 - 0.04) * under * light
            lb = 0.08 + (0.16 - 0.08) * under * light
            blend_px(row + x, lr, lg, lb, d * 0.55)


def draw_sea():
    for y in range(HOR, H):
        row = y * W
        depth = (y - HOR) / (H - HOR)
        inv = 1.0 / (0.28 + depth)
        fx = 0.014 * inv
        fy = 0.105 * inv
        br = 0.036 + (0.014 - 0.036) * depth
        bg = 0.082 + (0.028 - 0.082) * depth
        bb = 0.135 + (0.055 - 0.135) * depth
        rwidth = 125.0 + 340.0 * depth
        rfall = (1.0 - depth) ** 1.25
        hazef = exp(-(y - HOR) / 14.0)
        cool = 0.65 * (1.0 - depth)
        dyi = y - IY
        sy = y * 0.0045 + 2000.0
        for x in range(W):
            n = fbm(x * fx, y * fy, 3)
            hl = n * n * n
            # long vertical shimmer streaks through the reflection
            st = vnoise(x * 0.045 + 3000.0, sy)
            c = hl * cool
            dxr = (x - IX) / rwidth
            refl = exp(-dxr * dxr) * rfall * (0.16 + 1.6 * hl) * (0.5 + 1.0 * st)
            dx = x - IX
            gl = hl * exp(-(dx * dx + dyi * dyi) / 57600.0) * 0.7
            i = row + x
            R[i] = br + 0.12 * c + 1.15 * refl + 1.00 * gl + 0.08 * hazef
            G[i] = bg + 0.22 * c + 0.58 * refl + 0.50 * gl + 0.13 * hazef
            B[i] = bb + 0.30 * c + 0.22 * refl + 0.18 * gl + 0.18 * hazef


def draw_shock_ring():
    """Blast ring racing outward across the water, textured like foam."""
    rings = [(400.0, 64.0, 1.0), (235.0, 38.0, 0.45)]
    x0, x1 = max(0, SX - 440), min(W, SX + 440)
    y0, y1 = max(0, SY - 80), min(H, SY + 85)
    for y in range(y0, y1):
        row = y * W
        dy = y - SY
        for x in range(x0, x1):
            dx = x - SX
            v = 0.0
            wash = 0.0
            for rx, ry, k in rings:
                ex = dx / rx
                ey = dy / ry
                rn = sqrt(ex * ex + ey * ey)
                e = rn - 1.0
                if e > 0.25 or e < -0.5:
                    continue
                ang = atan2(ey, ex)
                tex = 0.3 + 0.7 * fbm(ang * 2.4 + 20.0 + rx * 0.01, rn * 6.0, 2)
                band = exp(-(e / 0.014) ** 2) * 1.0 + exp(-(e / 0.06) ** 2) * 0.45
                v += k * band * tex
                if e < 0.0:
                    wash += k * exp(-(e / 0.18) ** 2) * 0.3 * tex
            if v + wash < 0.004:
                continue
            front = 1.0 if dy > 0 else 0.55
            i = row + x
            R[i] += (0.78 * v + 1.00 * wash) * front
            G[i] += (0.90 * v + 0.70 * wash) * front
            B[i] += (1.00 * v + 0.45 * wash) * front


def rock_edges():
    """Per-row left/right edge of the sea stack, per-column top profile."""
    left = {}
    right = {}
    for y in range(RTOP - 40, HOR + 40):
        t = clamp01((y - RTOP) / float(HOR + 10 - RTOP))
        hw = 56.0 + 140.0 * t ** 0.72
        nl = (fbm(y * 0.035, 1.0, 3) - 0.5) * 44.0 + (fbm(y * 0.12, 5.0, 2) - 0.5) * 10.0
        nr = (fbm(y * 0.035, 7.0, 3) - 0.5) * 44.0 + (fbm(y * 0.12, 9.0, 2) - 0.5) * 10.0
        left[y] = RCX - hw + nl
        right[y] = RCX + hw + nr
    top = {}
    for x in range(0, W):
        t = (fbm(x * 0.03, 13.0, 3) - 0.5) * 36.0 + (fbm(x * 0.11, 17.0, 2) - 0.5) * 8.0
        crater = 20.0 * exp(-((x - IX) / 42.0) ** 2)
        top[x] = RTOP + t + crater
    return left, right, top


def draw_rock():
    left, right, top = rock_edges()
    for y in range(RTOP - 40, min(H, HOR + 22)):
        row = y * W
        xl = left[y]
        xr = right[y]
        for x in range(max(0, int(xl) - 2), min(W, int(xr) + 3)):
            yt = top[x]
            d = yt - (y + 0.5)
            dl = xl - (x + 0.5)
            dr = (x + 0.5) - xr
            if dl > d:
                d = dl
            if dr > d:
                d = dr
            cov = 0.5 - d
            if cov <= 0.0:
                continue
            if cov > 1.0:
                cov = 1.0
            n = fbm(x * 0.03, y * 0.03, 3)
            tex = 0.5 + 1.0 * n
            r = 0.080 * tex
            g = 0.072 * tex
            b = 0.085 * tex
            # fire light pouring down from the crater
            dxi = (x - IX) / 190.0
            lit = exp(-(y - yt) / 46.0) * exp(-dxi * dxi)
            # rim light on the flanks nearest the blaze
            edge = min(x + 0.5 - xl, xr - (x + 0.5))
            rim = exp(-edge / 9.0) * exp(-(y - RTOP) / 150.0) * 0.55
            lit += rim
            r += 1.00 * lit * 0.95
            g += 0.45 * lit * 0.95
            b += 0.14 * lit * 0.95
            # molten cracks
            cn = fbm(x * 0.045 + 3.0, y * 0.045 + 1.0, 3)
            cr = exp(-((cn - 0.5) / 0.028) ** 2) * exp(-dxi * dxi * 1.4) * exp(-(y - yt) / 70.0)
            r += 1.0 * cr
            g += 0.42 * cr
            b += 0.10 * cr
            # cool bounce from the water below
            cb = exp(-(HOR - y) / 36.0) * 0.35 if y < HOR else 0.35
            r += 0.08 * cb
            g += 0.16 * cb
            b += 0.24 * cb
            blend_px(row + x, r, g, b, cov)
    # foam at the waterline around the stack
    for x in range(int(left[HOR]) - 70, int(right[HOR]) + 71):
        if x < 0 or x >= W:
            continue
        for y in range(HOR - 4, HOR + 9):
            f = exp(-((y - HOR - 1.5) / 3.0) ** 2) * (0.3 + 0.7 * fbm(x * 0.05, 2.0, 2))
            if x < left[HOR] or x > right[HOR]:
                f *= 0.55 * exp(-min(abs(x - left[HOR]), abs(x - right[HOR])) / 30.0)
            blend_px(y * W + x, 0.60, 0.72, 0.80, f * 0.8)


def draw_fireball():
    """Impact cloud: fire, steam and smoke mushrooming out of the crater."""
    RX = 335.0
    RYU = 150.0
    RYD = 72.0
    x0, x1 = max(0, IX - 390), min(W, IX + 390)
    y0, y1 = IY - 215, min(H, IY + 115)
    for y in range(y0, y1):
        row = y * W
        dy = y - IY
        # upward-stretched licks of flame on top, blended smoothly into the skirt
        kmix = clamp01((dy + 50.0) / 100.0)
        kmix = kmix * kmix * (3.0 - 2.0 * kmix)
        ny = IY * 0.025 + dy * (0.017 + 0.015 * kmix) + 6.0
        ry0 = RYU + (RYD - RYU) * kmix
        for x in range(x0, x1):
            dx = x - IX
            ex = dx / RX
            ey = dy / ry0
            rn0 = ex * ex + ey * ey
            if rn0 > 1.9:
                continue
            wn = fbm(x * 0.0095 + 5.0, y * 0.013 + 2.0, 3)
            wx = dx + (wn - 0.5) * 130.0
            wy = dy + (vnoise(x * 0.012 + 1900.0, y * 0.016 + 1400.0) - 0.5) * 100.0
            km = clamp01((wy + 50.0) / 100.0)
            ry = RYU + (RYD - RYU) * km * km * (3.0 - 2.0 * km)
            rn = sqrt((wx / RX) ** 2 + (wy / ry) ** 2)
            if rn > 1.2:
                continue
            n2 = fbm(x * 0.026 + 1.0, ny, 3)
            dens = (1.1 - rn) * 2.4 + (n2 - 0.5) * 1.3
            if dens <= 0.0:
                continue
            if dens > 1.0:
                dens = 1.0
            heat = (exp(-rn * rn * 3.0) * (0.45 + 1.05 * n2)
                    + 0.9 * exp(-rn * rn * 14.0) + 0.1 * (1.0 - rn))
            if heat > 1.27:
                heat = 1.27
            fr, fg, fb = FIRE[int(heat * 400.0)]
            steam = clamp01((rn - 0.7) * 3.0) * clamp01(1.0 - heat * 2.5)
            sv = 0.45 + 0.5 * n2
            fr = fr + (0.80 * sv - fr) * steam
            fg = fg + (0.86 * sv - fg) * steam
            fb = fb + (0.92 * sv - fb) * steam
            top = clamp01((n2 - 0.5) * 3.0) * exp(-rn * 1.4) * 0.6
            fr += top * 1.0
            fg += top * 0.5
            fb += top * 0.2
            blend_px(row + x, fr, fg, fb, dens * (0.70 + 0.30 * n2) * (1.0 - 0.7 * steam))


def draw_plume():
    """The white-hot exhaust column from the lighthouse base to the crater."""
    ax = IX - BX
    ay = IY - BY
    L = sqrt(ax * ax + ay * ay)
    ax /= L
    ay /= L
    px = -ay
    py = ax
    x0 = max(0, min(BX, IX) - 260)
    x1 = min(W, max(BX, IX) + 260)
    y0 = max(0, BY - 70)
    y1 = min(H, IY + 80)
    for y in range(y0, y1):
        row = y * W
        dy = y - BY
        for x in range(x0, x1):
            dx = x - BX
            t = (dx * ax + dy * ay) / L
            if t < -0.25 or t > 1.3:
                continue
            s = dx * px + dy * py
            tt = t if t > 0.0 else 0.0
            r = 28.0 + 54.0 * tt
            if abs(s) > r * 2.8:
                continue
            turb = (fbm(x * 0.03 + 2.0, y * 0.0085, 3) - 0.5) * (6.0 + 54.0 * tt)
            u = abs(s + turb) / r
            inten = exp(-u * u * 1.5)
            if t < 0.0:
                inten *= exp(-(t * 6.0) ** 2)
            if t > 1.0:
                inten *= exp(-((t - 1.0) * 4.0) ** 2)
            if t < 0.85 and u < 0.6:
                c = cos(t * 2.0 * pi * 3.3)
                if c > 0.0:
                    inten *= 1.0 + 0.6 * c ** 8 * exp(-u * u * 9.0)
            heat = inten * (1.34 - 0.26 * tt)
            if heat > 1.27:
                heat = 1.27
            fr, fg, fb = FIRE[int(heat * 400.0)]
            a = inten * 2.4
            if a > 1.0:
                a = 1.0
            hz = exp(-u * u * 0.28) * 0.30
            i = row + x
            ia = 1.0 - a
            R[i] = R[i] * ia + fr * a + hz * 1.0
            G[i] = G[i] * ia + fg * a + hz * 0.45
            B[i] = B[i] * ia + fb * a + hz * 0.12


def draw_spray():
    """Crown of water thrown up from the shock ring."""
    # rising sheets of water on the front half
    for _ in range(230):
        a = rng.uniform(-0.25, pi + 0.25)
        rr = rng.uniform(0.9, 1.06)
        x = SX + 400.0 * rr * cos(a)
        y = SY + 64.0 * rr * sin(a)
        height = rng.uniform(18.0, 95.0) * (0.5 + 0.5 * sin(a) ** 2 if sin(a) > 0 else 0.35)
        lean = cos(a) * 0.35
        al = rng.uniform(0.15, 0.5)
        line_add(x, y, x + lean * height, y - height, 0.80, 0.90, 1.00, rng.uniform(1.5, 4.0), al, fade=True)
    # droplets everywhere along the rim
    for _ in range(420):
        a = rng.uniform(0.0, 2.0 * pi)
        rr = rng.uniform(0.86, 1.14)
        x = SX + 400.0 * rr * cos(a)
        y = SY + 64.0 * rr * sin(a)
        dxn = cos(a)
        dyn = -rng.uniform(0.6, 1.6)
        ln = sqrt(dxn * dxn + dyn * dyn)
        dxn /= ln
        dyn /= ln
        length = rng.uniform(5.0, 30.0)
        wid = rng.uniform(1.0, 2.2)
        al = rng.uniform(0.35, 0.9) * (1.0 if sin(a) > 0 else 0.6)
        warm = rng.random() * 0.5
        line_add(x + dxn * length, y + dyn * length, x, y,
                 0.85 + 0.15 * warm, 0.92 - 0.1 * warm, 1.0 - 0.4 * warm, wid, al, fade=True)


def draw_sparks():
    # sparks spraying down and out of the nozzle
    for _ in range(170):
        ox = BX + rng.uniform(-30.0, 30.0)
        oy = BY + rng.uniform(-5.0, 40.0)
        ang = pi / 2 + rng.uniform(-1.3, 1.3)
        dist = rng.uniform(20.0, 330.0)
        x = ox + cos(ang) * dist
        y = oy + sin(ang) * dist
        length = rng.uniform(8.0, 46.0)
        hot = rng.random()
        line_add(x, y, x - cos(ang) * length, y - sin(ang) * length,
                 1.0, 0.55 + 0.4 * hot, 0.15 + 0.6 * hot, rng.uniform(1.0, 2.0),
                 rng.uniform(0.4, 1.0), fade=True)
    # embers bouncing up out of the crater
    for _ in range(210):
        ang = -pi / 2 + rng.uniform(-1.5, 1.5)
        dist = rng.uniform(60.0, 540.0)
        x = IX + cos(ang) * dist + rng.uniform(-30, 30)
        y = IY + sin(ang) * dist * 0.75
        if y > HOR + 20:
            continue
        length = rng.uniform(6.0, 40.0)
        hot = rng.random()
        line_add(x, y, x - cos(ang) * length, y - sin(ang) * length,
                 1.0, 0.5 + 0.45 * hot, 0.1 + 0.6 * hot, rng.uniform(1.0, 2.2),
                 rng.uniform(0.35, 1.0), fade=True)


def draw_debris():
    """Angular rock shards blasted out of the crater, with motion trails."""
    chunks = []
    for _ in range(40):
        ang = -pi / 2 + rng.uniform(-1.6, 1.6)
        dist = rng.uniform(150.0, 520.0)
        x = IX + cos(ang) * dist
        y = IY + sin(ang) * dist * 0.8
        size = rng.uniform(3.0, 13.0) * (0.55 + 0.45 * (dist / 520.0))
        if y > HOR - 5 or y < 10 or x < 10 or x > W - 10:
            continue
        k = rng.randint(5, 7)
        angs = sorted(rng.uniform(0, 2 * pi) for _ in range(k))
        rot = rng.uniform(0, 2 * pi)
        pts = []
        for a in angs:
            rr = size * rng.uniform(0.55, 1.0)
            pts.append((x + rr * cos(a + rot), y + rr * sin(a + rot)))
        chunks.append((x, y, size, ang, pts, rng.random()))
    for x, y, size, ang, pts, hot in chunks:
        tl = size * 3.0 + 12.0
        line_add(x, y, x - cos(ang) * tl, y - sin(ang) * tl * 0.8,
                 1.0, 0.55, 0.25, max(1.0, size * 0.45), 0.4, fade=True)
    for x, y, size, ang, pts, hot in chunks:
        tox = IX - x
        toy = IY - y
        tl = sqrt(tox * tox + toy * toy)
        tox /= tl
        toy /= tl

        def col(px, py, x=x, y=y, size=size, tox=tox, toy=toy, hot=hot):
            dx = px - x
            dy = py - y
            nd = (dx * tox + dy * toy) / size
            lit = clamp01(nd * 1.6 + 0.1)
            r = 0.06 + 0.95 * lit
            g = 0.05 + 0.42 * lit
            b = 0.06 + 0.14 * lit
            if hot > 0.72:
                r += 0.5 * lit
                g += 0.2 * lit
            return (r, g, b)

        fill_convex(pts, col)


def draw_lighthouse():
    ct = cos(TILT)
    st = sin(TILT)
    HT = 255.0          # tower height
    W0, W1 = 47.0, 34.0  # half widths at base and top
    P = 58.0            # stripe period (px along the tower)
    red = (0.86, 0.07, 0.05)
    white = (0.96, 0.93, 0.86)
    x0 = max(0, BX - 150)
    x1 = min(W, BX + 210)
    y0 = max(0, BY - 420)
    y1 = min(H, BY + 70)
    for y in range(y0, y1):
        row = y * W
        dyy = BY - y
        for x in range(x0, x1):
            dx = x + 0.5 - BX
            dy = dyy - 0.5
            u = dx * ct - dy * st
            v = dx * st + dy * ct
            if v < -58.0 or v > HT + 118.0:
                continue
            r = g = b = 0.0
            cov = 0.0
            if 0.0 <= v < HT:
                w = W0 - (W0 - W1) * (v / HT)
                d = abs(u) - w
                cov = 0.5 - d
                if cov <= 0.0:
                    continue
                if cov > 1.0:
                    cov = 1.0
                uu = u / w
                if uu > 1.0:
                    uu = 1.0
                elif uu < -1.0:
                    uu = -1.0
                theta = math.asin(uu)
                phase = v / P + theta / pi * 0.55
                k = 0.5 + 0.5 * cos(2.0 * pi * phase)
                m = clamp01((k - 0.42) / 0.16)   # 1 = red band
                br = white[0] + (red[0] - white[0]) * m
                bg = white[1] + (red[1] - white[1]) * m
                bb = white[2] + (red[2] - white[2]) * m
                lat = cos(theta)
                shade = 0.30 + 0.70 * max(0.0, cos(theta + 0.55))
                shade = 0.22 + 0.78 * shade
                warm = exp(-v / 95.0) * 1.05
                r = br * shade + warm * 1.0
                g = bg * shade + warm * 0.5
                b = bb * shade + warm * 0.16
                rim = (1.0 - lat) ** 3 * (1.0 if u > 0 else 0.3)
                r += 0.18 * rim
                g += 0.32 * rim
                b += 0.55 * rim
                for wv in (62.0, 130.0, 198.0):
                    if abs(v - wv) < 7.0 and abs(u) < 4.0:
                        glow = 0.3 if wv < 150 else 0.9
                        r = 0.05 + 0.9 * glow
                        g = 0.04 + 0.55 * glow
                        b = 0.04 + 0.2 * glow
                if v > HT - 7.0:
                    r *= 0.5
                    g *= 0.5
                    b *= 0.5
            elif HT <= v < HT + 14.0:
                wg = W1 + 15.0
                d = abs(u) - wg
                cov = clamp01(0.5 - d)
                if cov <= 0.0:
                    continue
                r, g, b = 0.11, 0.09, 0.11
                if v < HT + 4.0:
                    r, g, b = 0.55, 0.26, 0.10
            elif HT + 14.0 <= v < HT + 74.0:
                wl = W1 - 2.0
                d = abs(u) - wl
                cov = clamp01(0.5 - d)
                if cov <= 0.0:
                    wg = W1 + 15.0
                    if v < HT + 38.0 and abs(u) <= wg + 1.0:
                        post = False
                        for kk in range(9):
                            pu = -wg + kk * (2.0 * wg / 8.0)
                            if abs(u - pu) < 1.3:
                                post = True
                                break
                        rail = abs(v - (HT + 36.0)) < 1.3 or abs(v - (HT + 24.0)) < 0.9
                        if post or rail:
                            cov = 1.0
                            r, g, b = 0.10, 0.08, 0.10
                        else:
                            continue
                    else:
                        continue
                else:
                    vc = HT + 46.0
                    core = exp(-((u * u) + (v - vc) * (v - vc) * 0.7) / 500.0)
                    r = 1.0
                    g = 0.92 + 0.08 * core
                    b = 0.55 + 0.45 * core
                    gl = 0.75 + 0.6 * core
                    r *= gl
                    g *= gl
                    b *= gl
                    for kk in range(5):
                        pu = -wl + kk * (2.0 * wl / 4.0)
                        if abs(u - pu) < 1.6:
                            r, g, b = 0.12, 0.09, 0.09
                    if abs(v - (HT + 44.0)) < 1.3 or v < HT + 20.0:
                        r, g, b = 0.12, 0.09, 0.09
            elif HT + 74.0 <= v < HT + 102.0:
                h = (v - (HT + 74.0)) / 28.0
                wd = (W1 + 3.0) * sqrt(max(0.0, 1.0 - h * h))
                d = abs(u) - wd
                cov = clamp01(0.5 - d)
                if cov <= 0.0:
                    continue
                sh = 0.4 + 0.6 * max(0.0, cos(math.asin(min(1.0, abs(u) / (wd + 1.0))) * 0.8 + (0.4 if u > 0 else -0.4)))
                spec = exp(-((u + 9.0) ** 2 + (v - (HT + 84.0)) ** 2) / 70.0) * 0.55
                r = 0.46 * sh + spec
                g = 0.09 * sh + spec * 0.9
                b = 0.07 * sh + spec * 0.7
            elif HT + 102.0 <= v < HT + 118.0:
                if abs(u) < 2.2:
                    cov = 1.0
                    r, g, b = 0.12, 0.10, 0.10
                else:
                    continue
            elif -14.0 <= v < 0.0:
                wp = W0 + 9.0
                d = abs(u) - wp
                cov = clamp01(0.5 - d)
                if cov <= 0.0:
                    continue
                warm = 0.55
                r = 0.16 + 1.0 * warm
                g = 0.14 + 0.45 * warm
                b = 0.14 + 0.12 * warm
            else:
                depth = (-v - 14.0) / 44.0
                n = fbm(u * 0.06 + 4.0, v * 0.06 + 2.0, 2)
                wr = (W0 + 4.0) * (1.0 - depth) ** 0.7 * (0.75 + 0.5 * n)
                d = abs(u) - wr
                cov = clamp01(0.5 - d)
                if cov <= 0.0:
                    continue
                tex = 0.6 + 0.8 * fbm(u * 0.09 + 1.0, v * 0.09 + 7.0, 2)
                r = 0.09 * tex
                g = 0.08 * tex
                b = 0.09 * tex
                hot = depth ** 2 * 1.1
                cn = fbm(u * 0.08 + 8.0, v * 0.08 + 3.0, 2)
                crack = exp(-((cn - 0.5) / 0.035) ** 2)
                hot += crack * 0.9
                r += 1.0 * hot
                g += 0.45 * hot
                b += 0.12 * hot
            blend_px(row + x, r, g, b, cov)


def lantern_pos():
    v = 255.0 + 46.0
    return BX + v * sin(TILT), BY - v * cos(TILT)


def draw_beams_and_glow():
    LX, LY = lantern_pos()
    th1 = math.radians(-26.0)        # beam up to the right, its twin down-left
    c1 = cos(th1)
    s1 = sin(th1)
    sig = 0.040
    tan_lim = math.tan(0.30)
    for y in range(H):
        row = y * W
        dyl = y + 0.5 - LY
        dyb = y + 0.5 - BY
        dyi = y + 0.5 - IY
        dyb2 = (dyb / 0.5) ** 2
        dyi2 = dyi * dyi
        for x in range(W):
            dxl = x + 0.5 - LX
            rho2 = dxl * dxl + dyl * dyl
            # ---- beams (double cone test before the expensive atan2)
            along = dxl * c1 + dyl * s1
            across = dxl * s1 - dyl * c1
            if along < 0.0:
                along = -along
                side = 0.62
            else:
                side = 1.0
            add_r = add_g = add_b = 0.0
            if abs(across) < along * tan_lim and rho2 > 200.0:
                phi = atan2(across, along)
                core = exp(-(phi / sig) ** 2)
                halo = exp(-(phi / (sig * 3.2)) ** 2) * 0.22
                smear = exp(-((phi - 0.075) / (sig * 1.8)) ** 2) * 0.28
                rho = sqrt(rho2)
                fall = 1.0 / (1.0 + rho / 520.0)
                vol = 0.78 + 0.45 * fbm(x * 0.008 + 2.0, y * 0.008 + 7.0, 2)
                bm = (core + halo + smear) * fall * side * 0.95 * vol
                add_r = bm * 1.00
                add_g = bm * 0.93
                add_b = bm * 0.72
            # ---- lantern halo
            lh = 0.9 / (1.0 + rho2 / 900.0) + 0.22 / (1.0 + rho2 / 9000.0)
            add_r += lh * 1.0
            add_g += lh * 0.96
            add_b += lh * 0.82
            # ---- white-hot flash at the nozzle
            dxb = x + 0.5 - BX
            fb = 1.1 / (1.0 + (dxb * dxb + dyb2) / 1900.0)
            add_r += fb * 1.00
            add_g += fb * 0.88
            add_b += fb * 0.62
            # ---- broad orange glow from the impact
            dxi = x + 0.5 - IX
            di2 = dxi * dxi + dyi2
            gi = 1.0 / (1.0 + di2 / 62000.0)
            gi = gi * gi * 0.55
            if dyi < -40.0 and di2 < 230000.0:
                # god rays fanning up out of the crater through the debris
                rays = 0.55 + 0.9 * fbm(atan2(dyi, dxi) * 6.0 + 60.0, 3.0, 2)
                k = clamp01((sqrt(di2) - 70.0) / 160.0)
                gi *= 1.0 + (rays - 1.0) * k
            add_r += gi * 1.00
            add_g += gi * 0.42
            add_b += gi * 0.12
            if add_r > 0.002:
                i = row + x
                R[i] += add_r
                G[i] += add_g
                B[i] += add_b


def draw_boat():
    """Small fishing boat, a dark silhouette against the fire's reflection."""
    bx, by = 430.0, 806.0           # waterline, mid-hull
    dark = (0.030, 0.026, 0.040)

    def sil(x, y):
        return dark

    # hull in two convex pieces: flat stern on the left, raised bow on the right
    stern = [(bx - 62.0, by - 19.0), (bx, by - 14.0), (bx, by + 4.0), (bx - 52.0, by + 4.0)]
    bow = [(bx, by - 14.0), (bx + 74.0, by - 34.0), (bx + 66.0, by + 4.0), (bx, by + 4.0)]
    fill_convex(stern, sil)
    fill_convex(bow, sil)
    # wheelhouse with a slanted front and a small lit window
    house = [(bx - 36.0, by - 44.0), (bx - 4.0, by - 44.0), (bx + 2.0, by - 14.0), (bx - 38.0, by - 14.0)]
    fill_convex(house, sil)
    fill_convex([(bx - 26.0, by - 40.0), (bx - 10.0, by - 40.0), (bx - 10.0, by - 32.0), (bx - 26.0, by - 32.0)],
                lambda x, y: (1.0, 0.72, 0.30))
    # gunwale catching the fire light
    line_blend(bx - 62.0, by - 19.0, bx, by - 14.0, 0.95, 0.5, 0.22, 1.5, 0.75)
    line_blend(bx, by - 14.0, bx + 74.0, by - 34.0, 1.0, 0.6, 0.28, 1.8, 0.9)
    line_blend(bx - 36.0, by - 44.0, bx - 4.0, by - 44.0, 0.9, 0.5, 0.25, 1.3, 0.6)
    # mast, boom, masthead light
    line_blend(bx - 20.0, by - 44.0, bx - 20.0, by - 96.0, dark[0], dark[1], dark[2], 2.2)
    line_blend(bx - 20.0, by - 70.0, bx + 22.0, by - 62.0, dark[0], dark[1], dark[2], 1.6)
    line_blend(bx - 20.0, by - 96.0, bx + 30.0, by - 40.0, dark[0], dark[1], dark[2], 1.0, 0.8)
    glow_dot(bx - 20.0, by - 97.0, 2.4, 1.0, 0.9, 0.6, 1.5)
    glow_dot(bx - 20.0, by - 97.0, 8.0, 1.0, 0.85, 0.5, 0.25)
    # dark reflection of the hull broken by the waves
    for yy in range(int(by + 4), int(by + 50)):
        f = exp(-(yy - by - 4.0) / 16.0)
        row = yy * W
        for xx in range(int(bx - 56), int(bx + 70)):
            n = fbm(xx * 0.05, yy * 0.2, 2)
            a = f * (0.25 + 0.75 * n) * 0.8
            blend_px(row + xx, dark[0], dark[1], dark[2], a)
    # foam at the bow and stern
    line_add(bx + 64.0, by + 2.0, bx + 96.0, by + 8.0, 0.85, 0.9, 0.95, 2.0, 0.5, fade=True)
    line_add(bx - 54.0, by + 3.0, bx - 80.0, by + 8.0, 0.75, 0.8, 0.85, 1.5, 0.3, fade=True)


def bloom():
    """Two-scale bloom: downsample, threshold, box blur, bilinear upsample, add."""
    s = 4
    w = W // s
    h = H // s
    br = [0.0] * (w * h)
    bg = [0.0] * (w * h)
    bb = [0.0] * (w * h)
    for yy in range(h):
        y = yy * s
        row0 = y * W
        row1 = (y + 2) * W
        base = yy * w
        for xx in range(w):
            x = xx * s
            i0 = row0 + x
            i1 = row1 + x + 2
            r = (R[i0] + R[i1]) * 0.5
            g = (G[i0] + G[i1]) * 0.5
            b = (B[i0] + B[i1]) * 0.5
            l = r * 0.3 + g * 0.59 + b * 0.11
            if l > 0.8:
                k = (l - 0.8) / l
                br[base + xx] = r * k
                bg[base + xx] = g * k
                bb[base + xx] = b * k

    def box_blur(src, rad, passes):
        cur = src
        inv = 1.0 / (2 * rad + 1)
        for _ in range(passes):
            tmp = [0.0] * (w * h)
            for yy in range(h):
                base = yy * w
                acc = 0.0
                for xx in range(0, rad + 1):
                    acc += cur[base + xx]
                for xx in range(w):
                    tmp[base + xx] = acc * inv
                    xo = xx - rad
                    xi = xx + rad + 1
                    if xo >= 0:
                        acc -= cur[base + xo]
                    if xi < w:
                        acc += cur[base + xi]
            out = [0.0] * (w * h)
            for xx in range(w):
                acc = 0.0
                for yy in range(0, rad + 1):
                    acc += tmp[yy * w + xx]
                for yy in range(h):
                    out[yy * w + xx] = acc * inv
                    yo = yy - rad
                    yi = yy + rad + 1
                    if yo >= 0:
                        acc -= tmp[yo * w + xx]
                    if yi < h:
                        acc += tmp[yi * w + xx]
            cur = out
        return cur

    planes = []
    for src in (br, bg, bb):
        tight = box_blur(src, 2, 2)
        wide = box_blur(src, 9, 2)
        planes.append([tight[k] * 0.55 + wide[k] * 0.9 for k in range(w * h)])
    for y in range(H):
        fy = (y + 0.5) / s - 0.5
        if fy < 0.0:
            fy = 0.0
        yy0 = int(fy)
        if yy0 >= h - 1:
            yy0 = h - 2
        ty = fy - yy0
        rowa = yy0 * w
        rowb = rowa + w
        row = y * W
        rows = []
        for pl in planes:
            rows.append([pl[rowa + k] * (1.0 - ty) + pl[rowb + k] * ty for k in range(w)])
        pr, pg, pb = rows
        if max(pr) < 0.001 and max(pg) < 0.001 and max(pb) < 0.001:
            continue
        for x in range(W):
            fx = (x + 0.5) / s - 0.5
            if fx < 0.0:
                fx = 0.0
            xx0 = int(fx)
            if xx0 >= w - 1:
                xx0 = w - 2
            tx = fx - xx0
            vr = pr[xx0] + (pr[xx0 + 1] - pr[xx0]) * tx
            if vr < 0.001:
                continue
            vg = pg[xx0] + (pg[xx0 + 1] - pg[xx0]) * tx
            vb = pb[xx0] + (pb[xx0 + 1] - pb[xx0]) * tx
            i = row + x
            R[i] += vr
            G[i] += vg
            B[i] += vb


# ----------------------------------------------------------------------------
# output
# ----------------------------------------------------------------------------
def soft_clip_lut():
    lut = []
    for k in range(2049):
        v = k / 1024.0
        if v < 0.78:
            o = v
        else:
            o = 0.78 + 0.22 * (1.0 - exp(-(v - 0.78) / 0.22))
        lut.append(int(min(255, max(0, round(o * 255)))))
    lut[-1] = 255
    return lut


def write_png(path):
    lut = soft_clip_lut()
    # vignette lookup over squared normalised radius
    vlut = [1.0 - 0.36 * clamp01((k / 256.0 - 0.42) / 0.9) ** 1.5 for k in range(1025)]
    cx, cy = W * 0.5, H * 0.47
    vx = [((x + 0.5 - cx) / (W * 0.5)) ** 2 for x in range(W)]
    rows = []
    zero3 = b'\x00\x00\x00'
    for y in range(H):
        dy2 = ((y + 0.5 - cy) / (H * 0.5)) ** 2
        row = y * W
        vig = [vlut[int((v + dy2) * 256.0)] for v in vx]
        rr = [lut[int(a * b * 1024.0)] if a * b < 2.0 else 255 for a, b in zip(R[row:row + W], vig)]
        gg = [lut[int(a * b * 1024.0)] if a * b < 2.0 else 255 for a, b in zip(G[row:row + W], vig)]
        bb = [lut[int(a * b * 1024.0)] if a * b < 2.0 else 255 for a, b in zip(B[row:row + W], vig)]
        raw = bytes([c for trip in zip(rr, gg, bb) for c in trip])
        prev = zero3 + raw[:-3]
        rows.append(b'\x01' + bytes([(a - b) & 255 for a, b in zip(raw, prev)]))
    data = b''.join(rows)

    def chunk(tag, payload):
        c = struct.pack('>I', len(payload)) + tag + payload
        return c + struct.pack('>I', zlib.crc32(tag + payload) & 0xffffffff)

    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(data, 9))
           + chunk(b'IEND', b''))
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, 'wb') as f:
        f.write(png)


STAGES = [
    draw_sky, draw_stars, draw_clouds, draw_sea, draw_shock_ring, draw_rock,
    draw_fireball, draw_plume, draw_spray, draw_lighthouse,
    draw_debris, draw_sparks, draw_boat, draw_beams_and_glow, bloom,
]


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else '/output/entry.png'
    for stage in STAGES:
        stage()
    write_png(out)


if __name__ == '__main__':
    main()
