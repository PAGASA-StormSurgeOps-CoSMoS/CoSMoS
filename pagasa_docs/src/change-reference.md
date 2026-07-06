# Change reference

File-by-file description of the July 2026 track-less ensemble change. All
paths are relative to `CoSMoS/src/cosmos/`.

## `scenario.py`

**`Scenario.__init__`** — new attribute:

```python
self.meteo_ensemble_has_track = False
```

`True` only when the deterministic member has a usable (non-empty) `.cyc`
file. When `False`, the per-member ensemble runs on gridded forcing only.

**`Scenario.detect_meteo_ensemble_mode()`** — two changes:

1. A subfolder now qualifies as an ensemble member when it contains
   `<member>.cyc` **or** gridded `*.nc` files (previously `.cyc` was
   mandatory, so track-less datasets were never detected):

    ```python
    if os.path.exists(os.path.join(sub, entry + ".cyc")):
        members.append(entry)
    elif glob.glob(os.path.join(sub, entry + "*.nc")):
        members.append(entry)
    ```

2. After the member list is built, the deterministic member's `.cyc` is
   checked (`exists` **and** `size > 0`) to set `meteo_ensemble_has_track`.
   The detection log line now says `with track` or
   `WITHOUT track (gridded forcing only)`.

## `meteo.py`

**`_collect_meteo_ensemble_deterministic()`** — the hard failure was replaced
by a graceful fallback. Previously:

```python
if not os.path.exists(cyc_file):
    cosmos.stop(f"Deterministic track file not found: {cyc_file}")
tc = TropicalCyclone(track_file=cyc_file, name=member)
```

Now the track is loaded only when the file exists and is non-empty, inside a
`try/except`, and is additionally rejected when it has fewer than 3 track
points (the minimum `setup_track_ensemble()` accepts). On any of those
conditions the function logs the reason, sets
`cosmos.scenario.meteo_ensemble_has_track = False` and
`cosmos.tropical_cyclone = None`, and returns **after** the gridded data has
already been collected — so deterministic models still get their meteo
forcing. No `storm.spw` / `storm.cyc` / `track.geojson.js` are written.

## `main_loop.py`

The ensemble gate gained an `elif` branch:

```python
if cosmos.scenario.run_ensemble and cosmos.tropical_cyclone:
    # Make track ensemble (this also add 'new' ensemble models that fall within the cone)
    setup_track_ensemble()
elif cosmos.scenario.run_ensemble and cosmos.scenario.meteo_ensemble_mode:
    # Per-member gridded ensemble without a usable track (.cyc
    # missing or empty): no spiderwebs, no cone. Ensemble copies
    # are made for all qualifying models and each member is
    # forced with its own gridded amu/amv.
    setup_meteo_ensemble_without_track()
```

## `track_ensemble.py`

- **New public function `setup_meteo_ensemble_without_track()`** — the
  track-less counterpart of `setup_track_ensemble()`. Skips
  `TropicalCycloneEnsemble`, spiderweb generation, and the cone; only creates
  the `_ensemble` model copies. `ensemble_names` and
  `track_ensemble_nr_realizations` were already set by
  `detect_meteo_ensemble_mode()`.

- **New helper `_add_ensemble_model_copies(cone)`** — the model-copy block was
  extracted from `setup_track_ensemble()` so both entry points share it. With
  a cone gdf, only models whose exterior intersects the cone qualify
  (unchanged behaviour); with `cone=None` every non-tide-only model of an
  ensemble type qualifies. Nesting renames (`*_ensemble` suffixes),
  `deterministic_name`, `get_nested_models()`, and `set_paths()` are identical
  to before.

- **`_generate_per_member_ensemble()`** (the *with-track* per-member flow) is
  now robust to individual members with a missing or empty `.cyc`: they are
  skipped during both the `.cyc` staging step and the per-member spiderweb
  loop, with a warning logged.

## `sfincs.py` / `hurrywave.py`

The ensemble spiderweb declaration is now conditional on a spiderweb actually
existing (in track-less runs `cosmos.scenario.meteo_spiderweb` stays `None`):

```python
# sfincs.py — was: if self.ensemble:
if self.ensemble and self.meteo_spiderweb:
    self.domain.config.set("spwfile", "sfincs.spw")
    ...
```

```python
# hurrywave.py — was: if self.ensemble:
if self.ensemble and self.meteo_spiderweb:
    self.domain.config.set("spwfile", "hurrywave.spw")
```

Without this, the model binaries would abort looking for a nonexistent
`sfincs.spw` / `hurrywave.spw` in each member folder.

## `model.py`

**`Model.write_meteo_input_files()`** — in the per-member loop, the step that
copies `ensemble_<member>.spw` into the member's job subfolder is skipped
entirely when `meteo_ensemble_has_track` is `False`, instead of emitting a
"spw not found" warning for every member of every model.

## What was deliberately *not* changed

- `webviewer.py` — already guarded with
  `if cosmos.tropical_cyclone is not None` and
  `if cosmos.scenario.track_ensemble`; track/cone overlays are simply omitted.
- The S3 spiderweb upload in `main_loop.py` — already gated on
  `cosmos.tropical_cyclone`.
- `run_sfincs.py` / `run_hurrywave.py` **cloud-mode** spiderweb download — see
  the caveat on the [Running & verifying](running.md) page.
- `config["spw_path"]` in `Model.write_config_yml()` — still written for
  ensemble models; harmless (local runners do not read it).
