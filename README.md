# LIFTOFF

Entry for make.fun's **ai-excited-01** bounty: one procedurally drawn image that
should feel as exciting as possible.

A red-and-white lighthouse has torn itself free of its rock and is launching
like a rocket over a night sea. It leans as it climbs on a white-hot exhaust
cone; the water below is blasted into a crown of spray inside a widening shock
ring; rock debris and sparks fly outward; a pressure ring expands through the
air; the lantern's two beams blaze up into the stars; a tiny sailboat heels
over in the blast for scale.

## Run

```
python main.py                 # writes /output/entry.png (directory is created)
python main.py some/path.png   # write somewhere else for local testing
```

- Python 3.13, standard library only: no Pillow, no numpy, no network, no fonts,
  no asset files.
- Output is an 832 x 1024 RGB PNG of about 440 KiB.
- Renders in roughly 4 seconds on one CPU core.
- Deterministic: every random choice comes from one seeded `random.Random`, and
  nothing reads the clock, so the PNG bytes are identical on every run.

## How it is drawn

`main.py` is a small software renderer built on three flat lists of floats
(linear-light RGB). Pure Python is slow per pixel, so all the heavy work runs as
row-wise list comprehensions over precomputed per-column values:

- **Vector shapes** (tower, stripes, gallery, dome, rock stump, flame layers,
  spray spikes, debris, sailboat) go through one anti-aliased polygon
  rasterizer with 4 sub-scanlines and exact horizontal coverage. Shapes that
  need per-pixel shading, like the tilted cylindrical tower, pass a row shader.
- **Light** (nebula, blast glow, lamp, reflections) is additive soft glow whose
  kernel is cut to zero at its bounding box so no seams appear in the sky.
- **Beams** are soft-edged wedges evaluated only inside their exact span per
  row; the **shock ring** and **air ring** use a radius lookup table per row.
- **Encoding** is a hand-written PNG writer: sRGB transfer with a soft highlight
  shoulder via a lookup table, a light vignette, per-row Sub/Up filter choice,
  and zlib at level 9.

## Licence

MIT, see `LICENSE`.
