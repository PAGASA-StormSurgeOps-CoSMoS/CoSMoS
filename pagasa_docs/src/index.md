# CoSMoS — PAGASA Operational Notes

This site documents PAGASA-specific changes made to the CoSMoS source tree in
this repository. It complements — but does not replace — the main Sphinx
documentation in `docs/source/`.

## Contents

| Page | What it covers |
|---|---|
| [Overview & behaviour](trackless-ensemble.md) | What "track-less per-member ensembles" are, why the change was needed, and exactly how CoSMoS behaves with a missing or empty `.cyc` file |
| [Change reference](change-reference.md) | File-by-file description of every code change |
| [Running & verifying](running.md) | Required data layout, how to run, what to look for in `cosmos.log`, and known caveats |

## Summary of the change (July 2026)

Previously, running an ensemble in **per-member meteo mode** (one subfolder
per ensemble member inside the meteo dataset's cycle folder) required every
member — at minimum the *deterministic* member — to ship a `<member>.cyc`
tropical-cyclone track file:

- a member subfolder **without** a `.cyc` was not even recognised as a member;
- a missing deterministic `.cyc` aborted the whole cycle via `cosmos.stop()`;
- an **empty** `.cyc` crashed track parsing or silently produced no ensemble
  models at all.

After the change, the `.cyc` track is **optional**. When it is missing, empty,
or unparseable, CoSMoS runs the ensemble in a *track-less* mode: no spiderweb
(`.spw`) files, no track cone, and every ensemble member is forced purely with
its **own gridded wind / pressure / precipitation data** (`amu`/`amv`/`amp`).
This is what you want for cyclone events that the meteo provider does not provide intuitive track files.

Nothing changes for runs that *do* have a usable track — the existing
spiderweb + cone flow is untouched.
