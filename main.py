#!/usr/bin/env python3
"""LIFTOFF.

A red-and-white lighthouse has torn free of its rock and is launching like a
rocket over a night sea.  Everything is drawn procedurally with the Python
standard library only (no Pillow, no numpy, no network) and the output bytes
are identical on every run (no clock, seeded randomness only).

Usage:  python main.py [output.png]       default: /output/entry.png
"""
import math
import os
import random
import struct
import sys
import zlib

W = H = 1024
NPIX = W * H
R = [0.0] * NPIX
G = [0.0] * NPIX
B = [0.0] * NPIX

rng = random.Random(1116)

# ----------------------------------------------------------------- helpers


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    return (lerp(c1[0], c2[0], t), lerp(c1[1], c2[1], t), lerp(c1[2], c2[2], t))


def smoothstep(e0, e1, x):
    t = clamp((x - e0) / (e1 - e0))
    return t * t * (3.0 - 2.0 * t)


def fill_poly(pts, color=None, alpha=1.0, shader=None, mode="over"):
    """Anti-aliased scanline polygon fill (4 sub-scanlines, exact x coverage).

    shader(x, y) -> (r, g, b, a) or None lets a polygon carry a gradient.
    mode "over" is normal alpha compositing, "screen" is a light-adding blend.
    """
    n = len(pts)
    if n < 3:
        return
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    y0 = max(0, int(math.floor(min(ys))))
    y1 = min(H - 1, int(math.ceil(max(ys))))
    bx0 = max(0, int(math.floor(min(xs))))
    bx1 = min(W - 1, int(math.ceil(max(xs))))
    if y1 < y0 or bx1 < bx0:
        return
    bw = bx1 - bx0 + 1
    edges = []
    for k in range(n):
        xa, ya = pts[k]
        xb, yb = pts[(k + 1) % n]
        if ya == yb:
            continue
        if ya > yb:
            xa, ya, xb, yb = xb, yb, xa, ya
        edges.append((ya, yb, xa, (xb - xa) / (yb - ya)))
    SUB = 4
    inv = 1.0 / SUB
    screen = mode == "screen"
    if color is not None:
        cr, cg, cb = color
    right = bx1 + 1
    for y in range(y0, y1 + 1):
        diff = [0.0] * (bw + 2)
        part = [0.0] * (bw + 2)
        hit = False
        for k in range(SUB):
            sy = y + (k + 0.5) * inv
            xi = [xa + (sy - ya) * sl for (ya, yb, xa, sl) in edges if ya <= sy < yb]
            if len(xi) < 2:
                continue
            xi.sort()
            for j in range(0, len(xi) - 1, 2):
                xa = xi[j]
                xb = xi[j + 1]
                if xa < bx0:
                    xa = float(bx0)
                if xb > right:
                    xb = float(right)
                if xb <= xa:
                    continue
                hit = True
                ia = int(xa)
                ib = int(xb)
                if ia == ib:
                    part[ia - bx0] += (xb - xa) * inv
                else:
                    part[ia - bx0] += (ia + 1 - xa) * inv
                    if ib <= bx1:
                        part[ib - bx0] += (xb - ib) * inv
                    diff[ia + 1 - bx0] += inv
                    diff[ib - bx0] -= inv
        if not hit:
            continue
        base = y * W
        c = 0.0
        for i in range(bw):
            c += diff[i]
            cov = c + part[i]
            if cov < 0.002:
                continue
            if cov > 1.0:
                cov = 1.0
            x = bx0 + i
            if shader is not None:
                res = shader(x + 0.5, y + 0.5)
                if res is None:
                    continue
                cr, cg, cb, a = res
                a *= cov
            else:
                a = alpha * cov
            idx = base + x
            if screen:
                R[idx] += (1.0 - R[idx]) * cr * a
                G[idx] += (1.0 - G[idx]) * cg * a
                B[idx] += (1.0 - B[idx]) * cb * a
            else:
                R[idx] += (cr - R[idx]) * a
                G[idx] += (cg - G[idx]) * a
                B[idx] += (cb - B[idx]) * a


def line(p0, p1, w0, w1, color, alpha=1.0, mode="over"):
    """Tapered line segment: half-width w0 at p0, w1 at p1."""
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    L = math.hypot(dx, dy)
    if L < 1e-6:
        return
    nx = -dy / L
    ny = dx / L
    pts = [(p0[0] + nx * w0, p0[1] + ny * w0), (p1[0] + nx * w1, p1[1] + ny * w1),
           (p1[0] - nx * w1, p1[1] - ny * w1), (p0[0] - nx * w0, p0[1] - ny * w0)]
    fill_poly(pts, color, alpha, mode=mode)


def disc(cx, cy, r, color, alpha=1.0, mode="over"):
    """Anti-aliased filled circle."""
    x0 = max(0, int(cx - r - 1))
    x1 = min(W - 1, int(cx + r + 1))
    y0 = max(0, int(cy - r - 1))
    y1 = min(H - 1, int(cy + r + 1))
    cr, cg, cb = color
    screen = mode == "screen"
    for y in range(y0, y1 + 1):
        dy = y + 0.5 - cy
        base = y * W
        for x in range(x0, x1 + 1):
            dx = x + 0.5 - cx
            a = r + 0.5 - math.sqrt(dx * dx + dy * dy)
            if a <= 0:
                continue
            if a > 1:
                a = 1.0
            a *= alpha
            idx = base + x
            if screen:
                R[idx] += (1.0 - R[idx]) * cr * a
                G[idx] += (1.0 - G[idx]) * cg * a
                B[idx] += (1.0 - B[idx]) * cb * a
            else:
                R[idx] += (cr - R[idx]) * a
                G[idx] += (cg - G[idx]) * a
                B[idx] += (cb - B[idx]) * a


def soft_dot(cx, cy, r, color, alpha=1.0):
    """Small glowing dot (stars, embers), screen blended."""
    x0 = max(0, int(cx - r - 1))
    x1 = min(W - 1, int(cx + r + 1))
    y0 = max(0, int(cy - r - 1))
    y1 = min(H - 1, int(cy + r + 1))
    cr, cg, cb = color
    r2 = r * r
    for y in range(y0, y1 + 1):
        dy = y + 0.5 - cy
        base = y * W
        for x in range(x0, x1 + 1):
            dx = x + 0.5 - cx
            q = (dx * dx + dy * dy) / r2
            if q >= 1.0:
                continue
            a = (1.0 - q) * (1.0 - q) * alpha
            idx = base + x
            R[idx] += (1.0 - R[idx]) * cr * a
            G[idx] += (1.0 - G[idx]) * cg * a
            B[idx] += (1.0 - B[idx]) * cb * a


def glow(cx, cy, rx, ry, color, strength, power=2.0, streak=None, ymin=0, ymax=H - 1):
    """Elliptical screen-blended glow.  streak(y) -> per-row multiplier."""
    x0 = max(0, int(cx - rx))
    x1 = min(W - 1, int(cx + rx) + 1)
    y0 = max(0, ymin, int(cy - ry))
    y1 = min(H - 1, ymax, int(cy + ry) + 1)
    cr, cg, cb = color
    for y in range(y0, y1 + 1):
        dy = (y + 0.5 - cy) / ry
        dy2 = dy * dy
        if dy2 >= 1.0:
            continue
        m = strength if streak is None else strength * streak(y)
        if m <= 0.0005:
            continue
        hw = math.sqrt(1.0 - dy2) * rx
        xa = max(x0, int(cx - hw))
        xb = min(x1, int(cx + hw) + 1)
        base = y * W
        for x in range(xa, xb + 1):
            dx = (x + 0.5 - cx) / rx
            d2 = dx * dx + dy2
            if d2 >= 1.0:
                continue
            f = (1.0 - d2) ** power * m
            idx = base + x
            R[idx] += (1.0 - R[idx]) * cr * f
            G[idx] += (1.0 - G[idx]) * cg * f
            B[idx] += (1.0 - B[idx]) * cb * f


def ellipse_pts(cx, cy, rx, ry, n=72):
    return [(cx + rx * math.cos(2 * math.pi * k / n), cy + ry * math.sin(2 * math.pi * k / n))
            for k in range(n)]


# ------------------------------------------------------------ scene layout

HORIZON = 600
IMPACT = (672.0, 800.0)                       # where the exhaust hits the sea
TILT = math.radians(-11.0)                    # tower leans left as it climbs
U = (math.sin(TILT), -math.cos(TILT))         # up along the tower axis
V = (-U[1], U[0])                             # across the tower, to the right
D = (-U[0], -U[1])                            # exhaust direction (down the axis)
PLUME_LEN = 262.0
NOZZLE = (IMPACT[0] + U[0] * PLUME_LEN, IMPACT[1] + U[1] * PLUME_LEN)
ROCK_H = 62.0
BASE = (NOZZLE[0] + U[0] * ROCK_H, NOZZLE[1] + U[1] * ROCK_H)
L = 340.0                                     # tower height
W0, W1 = 54.0, 34.0                           # half-widths at base / top


def tp(h, s):
    """Tower-local (height along axis, sideways offset) -> screen."""
    return (BASE[0] + U[0] * h + V[0] * s, BASE[1] + U[1] * h + V[1] * s)


def tw(h):
    return W0 + (W1 - W0) * clamp(h / L)


LANTERN = tp(L + 35.0, 0.0)

# ------------------------------------------------------------------- sky

SKY_TOP = (0.012, 0.025, 0.09)
SKY_HOR = (0.07, 0.15, 0.36)
for y in range(0, HORIZON):
    t = (y / HORIZON) ** 1.7
    c = mix(SKY_TOP, SKY_HOR, t)
    R[y * W:(y + 1) * W] = [c[0]] * W
    G[y * W:(y + 1) * W] = [c[1]] * W
    B[y * W:(y + 1) * W] = [c[2]] * W

# stars: denser and brighter high up, thinning toward the glow at the horizon
for _ in range(720):
    x = rng.uniform(0, W)
    y = rng.uniform(0, HORIZON - 10)
    if rng.random() < (y / HORIZON) ** 2 * 0.9:
        continue
    k = rng.random()
    if k < 0.70:
        r = rng.uniform(0.7, 1.1)
        a = rng.uniform(0.35, 0.8)
    elif k < 0.93:
        r = rng.uniform(1.1, 1.7)
        a = rng.uniform(0.6, 1.0)
    else:
        r = rng.uniform(1.9, 2.8)
        a = 1.0
    tint = rng.random()
    col = (0.85, 0.9, 1.0) if tint < 0.5 else (1.0, 0.97, 0.9) if tint < 0.85 else (1.0, 0.85, 0.7)
    soft_dot(x, y, r, col, a)
    if r > 1.9:
        fl = r * 3.2
        line((x - fl, y), (x, y), 0.0, 0.9, col, 0.7, mode="screen")
        line((x + fl, y), (x, y), 0.0, 0.9, col, 0.7, mode="screen")
        line((x, y - fl), (x, y), 0.0, 0.9, col, 0.7, mode="screen")
        line((x, y + fl), (x, y), 0.0, 0.9, col, 0.7, mode="screen")

# ------------------------------------------------------------------- sea

SEA_TOP = (0.05, 0.19, 0.42)
SEA_BOT = (0.01, 0.045, 0.15)
for y in range(HORIZON, H):
    t = ((y - HORIZON) / (H - HORIZON)) ** 0.75
    c = mix(SEA_TOP, SEA_BOT, t)
    R[y * W:(y + 1) * W] = [c[0]] * W
    G[y * W:(y + 1) * W] = [c[1]] * W
    B[y * W:(y + 1) * W] = [c[2]] * W

# horizon line
line((0, HORIZON + 0.5), (W, HORIZON + 0.5), 0.8, 0.8, (0.30, 0.55, 0.85), 0.55)

# wave streaks (lighter horizontal dashes, perspective-scaled)
for _ in range(140):
    y = HORIZON + 6 + (H - HORIZON - 10) * rng.random() ** 1.4
    depth = (y - HORIZON) / (H - HORIZON)
    ln = rng.uniform(20, 70) * (0.4 + 2.2 * depth)
    x = rng.uniform(-ln, W)
    th = 0.5 + 1.6 * depth
    a = rng.uniform(0.18, 0.45)
    line((x, y), (x + ln, y), 0.0, th, (0.35, 0.62, 0.9), a)
    line((x + ln, y), (x + ln * 1.6, y), th, 0.0, (0.35, 0.62, 0.9), a)


def streaky(y):
    return 0.45 + 0.55 * max(0.0, math.sin(y * 0.62 + 1.8 * math.sin(y * 0.09)))


# warm light thrown on the sea by the exhaust, broken into ripples
glow(IMPACT[0], IMPACT[1] + 30, 380, 170, (1.0, 0.52, 0.18), 0.55, 1.6, streak=streaky,
     ymin=HORIZON)
glow(IMPACT[0], IMPACT[1] + 140, 130, 150, (1.0, 0.75, 0.40), 0.6, 1.4, streak=streaky,
     ymin=HORIZON)

# ------------------------------------------------------------ sky haze

glow(IMPACT[0] - 10, HORIZON + 10, 500, 330, (1.0, 0.42, 0.12), 0.45, 1.6, ymax=HORIZON - 1)
glow(NOZZLE[0], NOZZLE[1] - 20, 320, 260, (1.0, 0.55, 0.2), 0.40, 2.0)

# ------------------------------------------------------------------ beams


def beam(origin, theta_deg, length, hw0, hw1, strength):
    th = math.radians(theta_deg)
    dx, dy = math.cos(th), -math.sin(th)
    px, py = -dy, dx
    ox, oy = origin
    pts = [(ox + px * hw0, oy + py * hw0),
           (ox + dx * length + px * hw1, oy + dy * length + py * hw1),
           (ox + dx * length - px * hw1, oy + dy * length - py * hw1),
           (ox - px * hw0, oy - py * hw0)]

    def sh(x, y):
        wx, wy = x - ox, y - oy
        t = (wx * dx + wy * dy) / length
        if t <= 0.0 or t >= 1.0:
            return None
        s = wx * px + wy * py
        hw = hw0 + (hw1 - hw0) * t
        r = s / hw
        if r >= 1.0 or r <= -1.0:
            return None
        a = strength * (1.0 - t) ** 1.25 * (1.0 - r * r) ** 1.4
        a *= 0.86 + 0.14 * math.sin(r * 11.0 + t * 3.0)
        return (1.0, 0.96, 0.78, a)

    fill_poly(pts, shader=sh, mode="screen")


beam(LANTERN, 143.0, 820, 10, 230, 1.0)
beam(LANTERN, 37.0, 820, 10, 230, 1.0)
glow(LANTERN[0], LANTERN[1], 340, 340, (1.0, 0.9, 0.6), 0.40, 2.5)

# ------------------------------------------------------------- shock ring


def shock_ring(cx, cy, a, b):
    x0 = max(0, int(cx - a * 1.25))
    x1 = min(W - 1, int(cx + a * 1.25))
    y0 = max(0, int(cy - b * 1.25))
    y1 = min(H - 1, int(cy + b * 1.25))
    for y in range(y0, y1 + 1):
        ey = (y + 0.5 - cy) / b
        ey2 = ey * ey
        if ey2 > 1.5625:
            continue
        base = y * W
        for x in range(x0, x1 + 1):
            ex = (x + 0.5 - cx) / a
            e = math.sqrt(ex * ex + ey2)
            if e > 1.25:
                continue
            d = e - 1.0
            idx = base + x
            # lit water inside the ring
            if e < 1.0:
                lit = 0.55 * (1.0 - e) ** 0.6
                R[idx] += (1.0 - R[idx]) * 0.30 * lit
                G[idx] += (1.0 - G[idx]) * 0.70 * lit
                B[idx] += (1.0 - B[idx]) * 0.95 * lit
                # inner, earlier ring
                a3 = 0.55 * math.exp(-((e - 0.58) / 0.03) ** 2)
                if a3 > 0.003:
                    R[idx] += (1.0 - R[idx]) * 0.85 * a3
                    G[idx] += (1.0 - G[idx]) * 0.95 * a3
                    B[idx] += (1.0 - B[idx]) * 1.0 * a3
            a1 = 0.97 * math.exp(-(d / 0.03) ** 2)
            a2 = 0.40 * math.exp(-((d - 0.07) / 0.06) ** 2)
            a12 = a1 + a2 * (1.0 - a1)
            if a12 > 0.003:
                R[idx] += (1.0 - R[idx]) * 0.92 * a12
                G[idx] += (1.0 - G[idx]) * 0.98 * a12
                B[idx] += (1.0 - B[idx]) * 1.0 * a12


shock_ring(IMPACT[0], IMPACT[1], 450.0, 118.0)

# ------------------------------------------------------------ spray crown

CROWN_RX, CROWN_RY = 150.0, 40.0
spikes = []
nsp = 26
for k in range(nsp):
    th = 2 * math.pi * k / nsp + rng.uniform(-0.08, 0.08)
    spikes.append(th)


def spike(th):
    cx, cy = IMPACT
    bx = cx + CROWN_RX * math.cos(th)
    by = cy + CROWN_RY * math.sin(th)
    ox, oy = math.cos(th), 0.3 * math.sin(th)
    front = math.sin(th) > 0
    Ls = rng.uniform(90, 230)
    if math.cos(th) < -0.6:
        Ls *= 1.3
    elif math.cos(th) > 0.6:
        Ls *= 0.95
    tipx = bx + ox * Ls * 0.78
    tipy = by + oy * Ls * 0.3 - Ls * 0.80
    bw = rng.uniform(16, 34)
    tx, ty = -math.sin(th), 0.3 * math.cos(th)
    tn = math.hypot(tx, ty)
    tx, ty = tx / tn, ty / tn
    midx = (bx + tipx) * 0.5
    midy = (by + tipy) * 0.5
    bul = 0.60 * bw
    # bow the spike outward so the crown curls like a splash
    midx += ox * Ls * 0.16
    midy += oy * Ls * 0.16
    pts = [(bx - tx * bw * 0.5, by - ty * bw * 0.5),
           (midx - tx * bul, midy - ty * bul),
           (tipx, tipy),
           (midx + tx * bul, midy + ty * bul),
           (bx + tx * bw * 0.5, by + ty * bw * 0.5)]
    col = (0.98, 0.99, 1.0) if front else (0.86, 0.93, 1.0)
    fill_poly(pts, col, 1.0)
    # the flank facing the exhaust catches its fire; the other flank falls into shadow
    inner = -1.0 if (tx * ox + ty * oy) > 0 else 1.0
    for sign, fcol, fa in ((inner, (1.0, 0.82, 0.55), 0.6), (-inner, (0.72, 0.84, 1.0), 0.55)):
        fx_, fy_ = tx * sign, ty * sign
        shp = [(midx + fx_ * bul * 0.3, midy + fy_ * bul * 0.3), (tipx, tipy),
               (midx + fx_ * bul, midy + fy_ * bul), (bx + fx_ * bw * 0.5, by + fy_ * bw * 0.5),
               (bx + fx_ * bw * 0.1, by + fy_ * bw * 0.1)]
        fill_poly(shp, fcol, fa)
    # droplets beyond the tip
    dxn, dyn = tipx - bx, tipy - by
    dn = math.hypot(dxn, dyn)
    dxn, dyn = dxn / dn, dyn / dn
    for j in range(rng.randint(1, 3)):
        dd = rng.uniform(14, 48) + j * 24
        rr = rng.uniform(2.0, 6.0) - j * 0.8
        px = tipx + dxn * dd + rng.uniform(-10, 10)
        py = tipy + dyn * dd + rng.uniform(-6, 6)
        disc(px, py, max(1.2, rr), col, 0.95)


# low steam skimming out across the water on both sides of the crown
for side in (-1, 1):
    glow(IMPACT[0] + side * 230, IMPACT[1] + 14, 170, 34, (1.0, 0.92, 0.85), 0.55, 1.3)
    glow(IMPACT[0] + side * 330, IMPACT[1] + 26, 110, 22, (1.0, 0.92, 0.85), 0.35, 1.3)

back = [th for th in spikes if math.sin(th) <= 0]
front_spikes = [th for th in spikes if math.sin(th) > 0]
for th in back:
    spike(th)
# foam collar with the glowing steam core inside it, soft-edged into the water
glow(IMPACT[0], IMPACT[1] + 6, CROWN_RX + 60, CROWN_RY + 26, (0.95, 0.98, 1.0), 0.8, 1.2)
fill_poly(ellipse_pts(IMPACT[0], IMPACT[1], CROWN_RX + 4, CROWN_RY + 2), (0.93, 0.97, 1.0), 0.95)
fill_poly(ellipse_pts(IMPACT[0], IMPACT[1] - 4, CROWN_RX - 30, CROWN_RY - 12), (1.0, 0.90, 0.68), 0.9)

# ----------------------------------------------------------------- plume

FIRE_STOPS = [(0.00, (0.42, 0.05, 0.03)), (0.18, (0.86, 0.19, 0.03)), (0.40, (1.0, 0.50, 0.06)),
              (0.62, (1.0, 0.78, 0.26)), (0.82, (1.0, 0.95, 0.72)), (1.00, (1.0, 1.0, 1.0))]
LUT = []
for i in range(257):
    h = i / 256.0
    for (s0, c0), (s1, c1) in zip(FIRE_STOPS, FIRE_STOPS[1:]):
        if s0 <= h <= s1:
            LUT.append(mix(c0, c1, (h - s0) / (s1 - s0)))
            break
DIAMONDS = [(0.08, 9.0), (0.19, 11.0), (0.30, 13.0), (0.41, 15.0)]


def plume():
    nx, ny = NOZZLE
    corners = [(nx + V[0] * 60, ny + V[1] * 60), (nx - V[0] * 60, ny - V[1] * 60),
               (nx + D[0] * PLUME_LEN * 1.15 + V[0] * 260, ny + D[1] * PLUME_LEN * 1.15 + V[1] * 260),
               (nx + D[0] * PLUME_LEN * 1.15 - V[0] * 260, ny + D[1] * PLUME_LEN * 1.15 - V[1] * 260)]
    x0 = max(0, int(min(c[0] for c in corners)))
    x1 = min(W - 1, int(max(c[0] for c in corners)))
    y0 = max(0, int(min(c[1] for c in corners)))
    y1 = min(H - 1, int(max(c[1] for c in corners)))
    for y in range(y0, y1 + 1):
        base = y * W
        wy = y + 0.5 - ny
        for x in range(x0, x1 + 1):
            wx = x + 0.5 - nx
            t = (wx * D[0] + wy * D[1]) / PLUME_LEN
            if t < -0.02 or t > 1.12:
                continue
            s = wx * V[0] + wy * V[1]
            tt = t if t > 0 else 0.0
            hw = 40.0 + 172.0 * tt ** 1.3
            if tt > 0.1:
                k = (tt - 0.1) / 0.3
                if k > 1.0:
                    k = 1.0
                if s > 0:
                    n = math.sin(9.0 * t + 2.1) * 0.10 + math.sin(21.0 * t + 1.3) * 0.06
                else:
                    n = math.sin(9.0 * t + 0.4) * 0.10 + math.sin(21.0 * t + 3.9) * 0.06
                hw *= 1.0 + k * n
            r = abs(s) / hw
            idx = base + x
            if r >= 1.35:
                continue
            # everything fades out just past the impact point, inside the foam collar
            fade = 1.0 if t <= 0.97 else max(0.0, 1.0 - (t - 0.97) / 0.12)
            # soft orange halo, continuous across the plume edge (no hard iso-line)
            a = 0.7 * (1.0 - r / 1.35) ** 2 * (0.3 + 0.7 * tt) * fade
            R[idx] += (1.0 - R[idx]) * 1.0 * a
            G[idx] += (1.0 - G[idx]) * 0.45 * a
            B[idx] += (1.0 - B[idx]) * 0.12 * a
            if r >= 1.0:
                continue
            core = (1.0 - r * r) ** 1.6
            heat = core * (0.82 - 0.40 * tt) + 0.30 * (1.0 - r) ** 4
            for tc, dw in DIAMONDS:
                dd = 1.0 - abs(t - tc) / 0.05 - abs(s) / dw
                if dd > 0:
                    heat += 0.6 * dd
            if heat > 1.0:
                heat = 1.0
            cr, cg, cb = LUT[int(heat * 256)]
            a = core * 2.4
            if a > 1.0:
                a = 1.0
            a *= fade
            R[idx] += (cr - R[idx]) * a
            G[idx] += (cg - G[idx]) * a
            B[idx] += (cb - B[idx]) * a


plume()
glow((NOZZLE[0] + IMPACT[0]) * 0.5, (NOZZLE[1] + IMPACT[1]) * 0.5, 300, 280,
     (1.0, 0.5, 0.15), 0.5, 2.0)
# hot burst where exhaust meets water
glow(IMPACT[0], IMPACT[1] - 20, 210, 95, (1.0, 0.85, 0.6), 0.8, 1.6)
for th in front_spikes:
    spike(th)

# ---------------------------------------------------------- sparks/embers

for _ in range(110):
    # embers thrown from the impact crown, outward and up
    ang = rng.uniform(math.radians(195), math.radians(345))
    r0 = rng.uniform(70, 190)
    sx = IMPACT[0] + math.cos(ang) * r0
    sy = IMPACT[1] + math.sin(ang) * r0 * 0.5
    ln = rng.uniform(20, 95)
    ex = sx + math.cos(ang) * ln
    ey = sy + math.sin(ang) * ln
    line((sx, sy), (ex, ey), 0.3, 1.6, (1.0, 0.62, 0.18), 0.9, mode="screen")
    soft_dot(ex, ey, 2.6, (1.0, 0.95, 0.75), 1.0)

# ------------------------------------------------------------------- rock

rock_local = [(-66, 0), (-72, -14), (-60, -30), (-68, -46), (-46, -62), (-26, -52),
              (-12, -66), (6, -56), (22, -70), (40, -58), (52, -68), (66, -44), (60, -24),
              (70, -10), (66, 0)]
rock_pts = [tp(h, s) for (s, h) in rock_local]
ROCK_LIT = (0.26, 0.18, 0.20)
ROCK_DK = (0.12, 0.08, 0.10)
fill_poly(rock_pts, ROCK_LIT)
# shadow on the right half (same split as the tower)
rock_sh = [tp(h, s) for (s, h) in rock_local if s >= 6] + [tp(-70, 6), tp(0, 6)]
fill_poly(rock_sh, ROCK_DK)
# warm rim light on the under-facets
for (s0, h0), (s1, h1) in zip(rock_local, rock_local[1:]):
    if h0 < -24 and h1 < -24:
        line(tp(h0, s0), tp(h1, s1), 3.0, 3.0, (1.0, 0.55, 0.18), 0.9)
# glowing cracks
for crack in [[(-34, -4), (-26, -26), (-38, -48)], [(16, -6), (10, -30), (24, -54)],
              [(44, -8), (50, -28)]]:
    for (s0, h0), (s1, h1) in zip(crack, crack[1:]):
        line(tp(h0, s0), tp(h1, s1), 2.2, 1.0, (1.0, 0.50, 0.14), 1.0)
glow(NOZZLE[0], NOZZLE[1], 110, 70, (1.0, 0.55, 0.2), 0.55, 1.5)
# ignition flash right under the rock
glow(NOZZLE[0] + D[0] * 18, NOZZLE[1] + D[1] * 18, 58, 42, (1.0, 0.95, 0.8), 0.9, 1.8)

# flying rock debris with motion trails
DARK = (0.10, 0.07, 0.09)
HOT = (1.0, 0.50, 0.16)
for _ in range(18):
    ang = rng.uniform(math.radians(-30), math.radians(210))
    dist = rng.uniform(70, 300)
    cx = NOZZLE[0] + math.cos(ang) * dist
    cy = NOZZLE[1] + math.sin(ang) * dist * 0.8
    if cx < 20 or cx > W - 20 or cy > H - 30:
        continue
    rad = rng.uniform(5, 16)
    nv = rng.randint(5, 7)
    poly = []
    for k in range(nv):
        a = 2 * math.pi * k / nv + rng.uniform(-0.25, 0.25)
        rr = rad * rng.uniform(0.6, 1.0)
        poly.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    # trail back toward the rock
    tx, ty = NOZZLE[0] - cx, NOZZLE[1] - cy
    tn = math.hypot(tx, ty)
    tx, ty = tx / tn, ty / tn
    tl = rng.uniform(30, 90)
    line((cx, cy), (cx + tx * tl, cy + ty * tl), rad * 0.6, 0.0, (1.0, 0.55, 0.2), 0.35,
         mode="screen")

    def sh(x, y, cx=cx, cy=cy, ldx=tx, ldy=ty):
        dx, dy = x - cx, y - cy
        d = math.hypot(dx, dy) + 1e-6
        k = smoothstep(-0.15, 0.75, (dx * ldx + dy * ldy) / d)
        c = mix(DARK, HOT, k)
        return (c[0], c[1], c[2], 1.0)

    fill_poly(poly, shader=sh)

# sparks from the torn rock
for _ in range(55):
    ang = rng.uniform(math.radians(-20), math.radians(200))
    r0 = rng.uniform(40, 110)
    sx = NOZZLE[0] + math.cos(ang) * r0
    sy = NOZZLE[1] + math.sin(ang) * r0
    ln = rng.uniform(20, 70)
    ex = sx + math.cos(ang) * ln
    ey = sy + math.sin(ang) * ln
    line((sx, sy), (ex, ey), 0.2, 1.5, (1.0, 0.70, 0.25), 0.9, mode="screen")
    soft_dot(ex, ey, 2.4, (1.0, 0.95, 0.8), 1.0)

# motion streaks: air tearing past the climbing tower
for _ in range(14):
    side = -1 if rng.random() < 0.5 else 1
    s = side * (tw(0) + rng.uniform(12, 70))
    h0 = rng.uniform(20, 300)
    ln = rng.uniform(70, 190)
    a = rng.uniform(0.10, 0.22)
    line(tp(h0, s), tp(h0 - ln, s), 1.0, 0.0, (1.0, 0.92, 0.8), a, mode="screen")

# ------------------------------------------------------------------ tower

RED = (0.88, 0.14, 0.17)
RED_SH = (0.52, 0.06, 0.10)
WHITE = (0.97, 0.96, 0.93)
WHITE_SH = (0.62, 0.65, 0.76)
DARKM = (0.13, 0.11, 0.14)


def band_poly(h0, h1, s0=-1.0, s1=1.0, extra=0.0):
    return [tp(h0, s0 * (tw(h0) + extra)), tp(h0, s1 * (tw(h0) + extra)),
            tp(h1, s1 * (tw(h1) + extra)), tp(h1, s0 * (tw(h1) + extra))]


# foundation ring
fill_poly(band_poly(-4, 12, extra=6), (0.22, 0.19, 0.23))
fill_poly(band_poly(-4, 12, 0.1, 1.0, extra=6), (0.12, 0.10, 0.13))

NB = 6
for k in range(NB):
    h0 = L * k / NB
    h1 = L * (k + 1) / NB + 0.7
    col, sh = (RED, RED_SH) if k % 2 == 0 else (WHITE, WHITE_SH)
    fill_poly(band_poly(h0, h1), col)
    fill_poly(band_poly(h0, h1, 0.10, 1.0), sh)
    fill_poly(band_poly(h0, h1, 0.10, 0.28), mix(col, sh, 0.5))
    fill_poly(band_poly(h0, h1, -1.0, -0.80), mix(col, (1.0, 1.0, 1.0), 0.3), 0.7)

# warm underlight from the exhaust creeping up the lower tower


def underlight(x, y):
    wx, wy = x - BASE[0], y - BASE[1]
    h = wx * U[0] + wy * U[1]
    a = 0.75 * (1.0 - clamp(h / 120.0)) ** 1.5
    return (1.0, 0.55, 0.2, a)


fill_poly(band_poly(-4, 120), shader=underlight)

# windows (lit) and door
for k in range(1, 5):
    hc = L * (k + 0.5) / NB
    s = -8.0
    fr = [tp(hc - 10, s - 7), tp(hc - 10, s + 7), tp(hc + 7, s + 7), tp(hc + 10, s + 3),
          tp(hc + 10, s - 3), tp(hc + 7, s - 7)]
    fill_poly(fr, DARKM)
    fr2 = [tp(hc - 8, s - 5), tp(hc - 8, s + 5), tp(hc + 6, s + 5), tp(hc + 8, s + 2),
           tp(hc + 8, s - 2), tp(hc + 6, s - 5)]
    fill_poly(fr2, (1.0, 0.80, 0.38))
door = [tp(10, -12), tp(10, 12), tp(36, 12), tp(42, 6), tp(42, -6), tp(36, -12)]
fill_poly(door, DARKM)

# gallery platform + brackets
fill_poly([tp(L - 16, -W1 - 2), tp(L - 16, W1 + 2), tp(L, W1 + 18), tp(L, -W1 - 18)], DARKM)
fill_poly(band_poly(L, L + 12, extra=18), (0.18, 0.16, 0.20))
fill_poly(band_poly(L, L + 12, 0.1, 1.0, extra=18), DARKM)
# railing
for s in (-W1 - 16, -W1 - 9, W1 + 9, W1 + 16):
    line(tp(L + 12, s), tp(L + 36, s), 1.2, 1.2, DARKM)
line(tp(L + 36, -W1 - 17), tp(L + 36, W1 + 17), 1.4, 1.4, DARKM)
line(tp(L + 24, -W1 - 17), tp(L + 24, W1 + 17), 0.9, 0.9, DARKM)

# lantern room
GL = 28.0
fill_poly([tp(L + 12, -GL), tp(L + 12, GL), tp(L + 60, GL), tp(L + 60, -GL)], (1.0, 0.93, 0.62))
fill_poly([tp(L + 12, 0), tp(L + 12, GL), tp(L + 60, GL), tp(L + 60, 0)], (1.0, 0.85, 0.45), 0.6)
for s in (-GL, -GL / 2, 0.0, GL / 2, GL):
    line(tp(L + 12, s), tp(L + 60, s), 2.0, 2.0, DARKM)
fill_poly([tp(L + 12, -GL - 2), tp(L + 12, GL + 2), tp(L + 17, GL + 2), tp(L + 17, -GL - 2)], DARKM)
fill_poly([tp(L + 56, -GL - 3), tp(L + 56, GL + 3), tp(L + 61, GL + 3), tp(L + 61, -GL - 3)], DARKM)

# dome + finial
dome = [tp(L + 60 + 34 * math.sin(math.pi * k / 40), -36 * math.cos(math.pi * k / 40))
        for k in range(41)]
fill_poly(dome, RED)
dome_sh = [tp(L + 60 + 34 * math.sin(math.pi * k / 40), -36 * math.cos(math.pi * k / 40))
           for k in range(20, 41)] + [tp(L + 60, 0)]
fill_poly(dome_sh, RED_SH)
line(tp(L + 92, 0), tp(L + 118, 0), 1.5, 1.0, DARKM)
disc(*tp(L + 98, 0), 5.0, DARKM)

# lantern blaze over everything
glow(LANTERN[0], LANTERN[1], 130, 130, (1.0, 0.95, 0.7), 1.0, 2.2)
for ang in (143.0, 37.0):
    th = math.radians(ang)
    ex = LANTERN[0] + math.cos(th) * 140
    ey = LANTERN[1] - math.sin(th) * 140
    line(LANTERN, (ex, ey), 5.0, 0.0, (1.0, 0.98, 0.85), 0.9, mode="screen")

# ------------------------------------------------------------- sailboat


def sailboat(bx, by, heel_deg, scale):
    hr = math.radians(heel_deg)
    ch, sh = math.cos(hr), math.sin(hr)

    def bt(x, y):
        return (bx + scale * (x * ch - y * sh), by + scale * (-x * sh - y * ch))

    HULL = (0.04, 0.05, 0.11)
    # geometry of the wave that will be drawn over the hull later, and a snapshot
    # of the untouched water under it so the hump blends seamlessly
    hx, hy = bx + 4 * scale, by + 12 * scale
    half_w, height = 130 * scale, 24 * scale
    sigma = half_w * 0.45
    yb = hy + 26 * scale
    sx0 = max(0, int(hx - half_w) - 1)
    sx1 = min(W - 1, int(hx + half_w) + 2)
    sy0 = max(0, int(hy - height) - 1)
    sy1 = min(H - 1, int(yb) + 2)
    sw = sx1 - sx0 + 1
    snap = []
    for yy in range(sy0, sy1 + 1):
        i0 = yy * W + sx0
        snap.append((R[i0:i0 + sw], G[i0:i0 + sw], B[i0:i0 + sw]))

    hull = [bt(-36, 0), bt(44, 0), bt(40, -6), bt(18, -13), bt(-24, -12), bt(-36, -5)]
    fill_poly(hull, HULL)
    fill_poly([bt(-36, 0), bt(44, 0), bt(44, -2.2), bt(-36, -2.2)], (0.85, 0.80, 0.70))
    # mast and boom
    line(bt(0, 0), bt(0, 102), 1.4 * scale, 1.0 * scale, HULL)
    line(bt(2, 9), bt(-42, 7), 1.0 * scale, 1.0 * scale, HULL)
    # mainsail (aft) and jib (forward, lit by the blast)
    main = [bt(0, 97), bt(-27, 52), bt(-42, 8), bt(0, 10)]
    fill_poly(main, (0.90, 0.93, 0.98))
    fill_poly([bt(0, 97), bt(-12, 52), bt(-20, 9), bt(0, 10)], (0.97, 0.97, 0.99))
    jib = [bt(0, 86), bt(13, 46), bt(11, 10), bt(45, 2)]
    fill_poly(jib, (1.0, 0.90, 0.72))
    fill_poly([bt(0, 86), bt(13, 46), bt(11, 10), bt(6, 9)], (1.0, 0.96, 0.88))
    # pennant
    fill_poly([bt(0, 102), bt(-12, 99), bt(0, 95)], RED)
    # the wave lifting the boat: a hump of water drawn over the submerged,
    # leeward part of the heeled hull, with foam breaking along its crest
    n = 48
    top = []
    for k in range(n + 1):
        x = hx - half_w + 2 * half_w * k / n
        u = (x - hx) / sigma
        top.append((x, hy - height * math.exp(-u * u)))
    hump = top + [(hx + half_w, yb), (hx - half_w, yb)]

    def water(x, y):
        ix = int(x) - sx0
        iy = int(y) - sy0
        if ix < 0 or ix >= sw or iy < 0 or iy >= len(snap):
            return None
        rr, gg, bb = snap[iy]
        k = clamp((yb - y) / (height + 26 * scale)) ** 1.6
        return (rr[ix] + 0.10 * k, gg[ix] + 0.20 * k, bb[ix] + 0.26 * k, 1.0)

    fill_poly(hump, shader=water)
    crest = []
    under = []
    for (x, y) in top:
        u = (x - hx) / sigma
        g = math.exp(-u * u)
        if g < 0.05:
            continue
        w_ = 3.8 * g * scale
        crest.append((x, y - w_ * 0.4))
        under.append((x, y + w_ * 1.6))
    fill_poly(crest + under[::-1], (0.95, 0.98, 1.0), 0.95)
    # spray torn off the crest, leeward (left)
    for _ in range(18):
        px = hx + rng.uniform(-120, -10) * scale
        py = hy - height * 0.6 + rng.uniform(-26, 4) * scale
        disc(px, py, rng.uniform(1.0, 3.2) * scale, (0.95, 0.98, 1.0), 0.85)


sailboat(176.0, 782.0, 34.0, 1.15)

# ---------------------------------------------------------------- vignette

fx = [1.0 - 0.30 * (((x + 0.5) / W - 0.5) * 2.0) ** 2 for x in range(W)]
for y in range(H):
    fy = 1.0 - 0.26 * (((y + 0.5) / H - 0.5) * 2.0) ** 2
    s = y * W
    e = s + W
    R[s:e] = [v * f * fy for v, f in zip(R[s:e], fx)]
    G[s:e] = [v * f * fy for v, f in zip(G[s:e], fx)]
    B[s:e] = [v * f * fy for v, f in zip(B[s:e], fx)]

# ------------------------------------------------------------------ output


def write_png(path):
    raw = bytearray()
    prev = bytes(W * 3)
    rowf = [0.0] * (W * 3)
    for y in range(H):
        s = y * W
        rowf[0::3] = R[s:s + W]
        rowf[1::3] = G[s:s + W]
        rowf[2::3] = B[s:s + W]
        row = bytes(255 if v >= 1.0 else 0 if v <= 0.0 else int(v * 255.0 + 0.5) for v in rowf)
        raw.append(2)                                   # "Up" filter
        raw += bytes((a - b) & 255 for a, b in zip(row, prev))
        prev = row
    data = zlib.compress(bytes(raw), 9)

    def chunk(tag, payload):
        c = tag + payload
        return struct.pack(">I", len(payload)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", data)
           + chunk(b"IEND", b""))
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "/output/entry.png"
    write_png(out)
