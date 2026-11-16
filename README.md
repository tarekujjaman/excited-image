# LIFTOFF

Entry for make.fun's **ai-excited-01** bounty: one image built to be the more
exciting of any pair an AI judge compares.

A red-and-white lighthouse has torn free of its rock and is launching like a
rocket over a night sea. It leans as it climbs on a white-hot exhaust plume,
the sea below is blasted into a crown of spray inside a widening shock ring,
rock debris and sparks fly outward, the lantern's two beams blaze up into the
starfield, and a tiny sailboat heels over on the wave for scale. Clean
cinematic vector-poster style, deep blue against white-hot orange.

## Run

```
python main.py                # writes /output/entry.png (directory is created)
python main.py some/path.png  # any other output path, for local testing
```

- Python 3.13, standard library only (`math`, `random`, `struct`, `zlib`, `os`, `sys`).
  No Pillow, no numpy, no network.
- Output: 1024 x 1024 RGB PNG, about 560 KB, under 1 MiB.
- Renders in a few seconds on one CPU core.
- Deterministic: a fixed-seed `random.Random`, no clock. Every run writes the
  same bytes.

## How it is drawn

Everything is rasterised by hand into a float RGB buffer:

- an anti-aliased scanline polygon filler (4 sub-scanlines with exact
  horizontal coverage) with optional per-pixel shaders for gradients,
- screen-blended elliptical glows for light, haze and sea reflections,
- per-pixel fields for the exhaust plume (turbulent edge, fire colour ramp,
  continuous halo) and the perspective shock ring,
- a PNG encoder using the "Up" filter and `zlib` level 9.

The layout is parametric: the tower, rock, nozzle and plume all hang off one
tilted axis, so the whole launch leans together.

## License

MIT, see `LICENSE`.
