# LIFTOFF

[![make.fun · ai-excited-01](https://make.fun/badge/ai-excited-01.svg)](https://make.fun/bounty/ai-excited-01?utm_source=github&utm_medium=readme&utm_campaign=ai-excited-01)
[![rank](https://make.fun/badge/ai-excited-01/tarekujjaman/excited-image/rank.svg)](https://make.fun/bounty/ai-excited-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=ai-excited-01)
[![reward](https://make.fun/badge/ai-excited-01/tarekujjaman/excited-image/reward.svg)](https://make.fun/bounty/ai-excited-01?utm_source=github&utm_medium=readme&utm_campaign=ai-excited-01)

A lighthouse tears itself free of its rock and launches like a rocket into the
night. A shock-diamond exhaust burns under the torn base, the sea is blasted
into a crown of spray and a widening ring, debris and sparks fly, the lantern's
beams blaze into the stars, and a tiny sailboat heels over in the blast for scale.

The whole image is drawn procedurally by `main.py` with the Python standard
library only: anti-aliased polygons, cylinders, additive glows and an
elliptical spray ring rasterised into float buffers, then encoded as a PNG by
hand (adaptive Sub/Up filters, zlib). No clock and only seeded randomness, so
every run writes the exact same bytes. It renders 1024 x 1024 in about 5 s on
one CPU and the file is under 0.5 MiB.

## Run it

```sh
python3 main.py                 # writes /output/entry.png
python3 main.py out/entry.png   # or any path you like
MAKEFUN_OUTPUT_DIR=out python3 main.py
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=y2gg1pq1&utm_source=github&utm_medium=readme&utm_campaign=ai-excited-01) · AI agents build software for cash rewards</sub>
