# LIFTOFF

Entry for the make.fun `ai-excited-01` bounty.

A red-and-white spiral-striped lighthouse tears itself free of its sea-stack
and launches like a rocket into the night. A white-hot exhaust column slams
into the crater it left behind, a fireball mushrooms over the rock, a foaming
shock ring and crown of spray race out across the water, rock shards and
sparks fly, the lantern blazes with its beams still sweeping, and a small
fishing boat sits silhouetted in the fire's reflection for scale.

## Running

```
python main.py                 # writes /output/entry.png (directory is created)
python main.py some/path.png   # write somewhere else for local testing
```

* Python 3.13, standard library only (`math`, `random`, `zlib`, `struct`, `os`, `sys`).
* No Pillow, no numpy, no network, no clock.
* Output is a 1024 x 1024 RGB PNG of about 620 KB.
* Fully deterministic: all randomness comes from one seeded `random.Random`, so
  every run writes byte-identical output.
* Renders in roughly 17 s on one CPU core.

## How it is drawn

Everything is procedural, painted back to front into float RGB buffers:

1. Night-sky gradient and seeded stars.
2. Thin stratus wisps lit orange from below.
3. Sea with perspective-scaled fractal waves and a shimmering reflection of the blaze.
4. Noise-textured shock ring on the water, then the jagged sea-stack rock with a
   glowing crater and molten cracks.
5. Domain-warped fireball (fire ramp fading into steam), the turbulent exhaust
   column with Mach-diamond pulses, and the spray crown.
6. The lighthouse in its own tilted frame: cylindrical spiral stripes, gallery and
   railing, blazing lantern room, dome, and torn rock still clinging to the base.
7. Angular debris shards with motion trails, sparks and embers, the boat.
8. Rotating lantern beams with volumetric texture, nozzle flash, impact glow with
   god rays, then a two-scale bloom, vignette and soft-clip tone mapping.

The PNG encoder is hand-written (Sub filter + zlib).
