# P.O.W.E.R. 3.2.1 post-merge WS evidence

This directory contains sanitized, reproducible evidence from the clean
dedicated WS full sync completed after PR #186. The raw sync log remains in the
WS workspace because it includes private vault paths; `benchmark-summary.json`
contains only extracted timing and resource values.

Tested source: `8f03847f557f80c567920f07a0e35acd62feb00e`.

The checked database is `/var/tmp/power-3.2.1-test-2-final/search.db`, not the
production vault database. See `benchmark-summary.json` and `run-manifest.json`
for the canonical facts and provenance.
