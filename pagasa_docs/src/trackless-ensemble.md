# Track-less per-member ensembles — overview & behaviour

## Background: per-member meteo ensemble mode

CoSMoS detects a **per-member meteo ensemble** when the meteo dataset's cycle
folder contains one subfolder per ensemble member:

```text
<meteo_db>/<dataset>/<YYYYMMDD_HHz>/
    <member_A>/
        <member_A>.cyc                   # member's cyclone track (now OPTIONAL)
        ***.nc ...  # member's gridded forcing
    <member_B>/
        ...
```

Detection happens in `Scenario.detect_meteo_ensemble_mode()` (called from the
main loop, before meteo download/collect). When members are found:

- `scenario.meteo_ensemble_mode = True`
- `scenario.ensemble_names` = the sorted member folder names
- the **last (sorted) member** acts as the *deterministic* representative
- `scenario.track_ensemble_nr_realizations` = number of members

With a usable track, the flow then builds `storm.spw` for the deterministic
member, a per-member `ensemble_<member>.spw` from each member's gridded wind
field, and a track cone that decides which models get `_ensemble` copies.

## What the `.cyc` file was needed for

| Consumer | Role of the track |
|---|---|
| `detect_meteo_ensemble_mode()` | `<member>.cyc` was the *signature* that marked a folder as an ensemble member |
| `_collect_meteo_ensemble_deterministic()` (meteo.py) | Loaded the deterministic member's `.cyc`; aborted the run (`cosmos.stop`) if absent; wrote `storm.spw` / `storm.cyc` / `track.geojson.js` |
| `setup_track_ensemble()` (track_ensemble.py) | Built the `TropicalCycloneEnsemble`, wrote per-member spiderwebs, and computed the **cone** used to select which models get ensemble copies |
| SFINCS / HurryWave wrappers | Pointed the ensemble model input at `sfincs.spw` / `hurrywave.spw` |
| Web viewer | Track and cone overlays (already guarded — skipped when absent) |

## New behaviour matrix

The deterministic member is the **last sorted** member; its `.cyc` decides the
mode of the whole run.

| Deterministic member's `.cyc` | Behaviour |
|---|---|
| Present, parseable, ≥ 3 track points | **Unchanged.** Spiderwebs + cone flow as before. |
| Missing | **Track-less mode** (was: fatal `cosmos.stop`). |
| Present but empty (0 bytes) | **Track-less mode** (was: parse crash). |
| Present but unparseable, or < 3 track points | **Track-less mode**, with the reason logged (was: crash or silent no-ensemble). |

In **track-less mode**:

1. Member folders are recognised by their gridded `*.nc` files alone —
   no `.cyc` needed.
2. A new scenario flag `meteo_ensemble_has_track` is set to `False`.
3. `collect_meteo()` still collects the deterministic member's gridded data
   (deterministic models run normally, forced by netcdf wind/pressure), but
   writes **no** `storm.spw` / `storm.cyc`, and leaves
   `cosmos.tropical_cyclone = None`.
4. Instead of `setup_track_ensemble()`, the main loop calls the new
   `setup_meteo_ensemble_without_track()`: **every** non-tide-only model whose
   type is listed in `ensemble_models` gets an `_ensemble` copy — there is no
   cone to intersect with, so no spatial filtering.
5. Each ensemble member is forced purely with its own gridded data: the
   existing per-member loop in `Model.write_meteo_input_files()` re-collects
   that member's grids and writes the forcing cut-out into
   `<job>/<member>/`. The spiderweb staging step is skipped.
6. The SFINCS / HurryWave input files do **not** declare a `spwfile`, so the
   binaries never look for a spiderweb that does not exist.
7. The web viewer simply omits the track and cone overlays (existing guards).

## Mixed case: only *some* members have a usable track

If the deterministic member has a good track but *other* members have a
missing/empty `.cyc`, the run stays in the normal with-track flow, and the
affected members are **skipped during spiderweb generation** with a logged
warning:

```text
warning: no usable track for ensemble member <name> — skipping its spiderweb (gridded forcing only).
```

!!! warning
    In this mixed case the ensemble model's input file still declares
    `spwfile` (because the run as a whole has spiderwebs), so a member without
    one will fail at the model binary. Watch for the warning above and either
    fix that member's `.cyc` or delete it from the cycle folder. Making this
    fall back gracefully per member is a possible follow-up.

## Caveats

!!! warning "Mixed tracks"
    As described above: keep tracks **all-or-nothing per cycle**. If the
    deterministic member has a usable track but other members do not, those
    members get no spiderweb yet their model input still declares `spwfile`,
    so their simulations will fail at the model binary.

!!! warning "Cloud run mode is not supported for track-less runs"
    `run_sfincs.py` / `run_hurrywave.py` unconditionally download the member
    spiderweb from S3 when `run_mode = "cloud"` and the model is an ensemble
    member. Track-less ensembles have no spiderwebs on S3, so that download
    fails. Use local `serial` / `parallel` run modes; guarding the cloud
    download is a small follow-up if ever needed.

!!! warning "The deterministic member decides for the whole run"
    Only the **last sorted** member's `.cyc` is inspected to choose the mode.
    A run is either fully track-driven or fully track-less — there is no
    per-member mixing (see "Mixed tracks" above).

!!! note "Deterministic models lose the spiderweb layer"
    Deterministic (non-ensemble) models still run, forced by the
    deterministic member's gridded data. Previously they also received
    `storm.spw` on top of the gridded forcing; in track-less runs that extra
    spiderweb layer simply does not exist, so near-storm winds are only as
    good as the gridded product's resolution.

!!! note "No cone means no spatial filtering"
    Without a track cone, **every** non-tide-only model whose type is in
    `ensemble_models` gets an `_ensemble` copy — including models far from
    the event. Trim the scenario's model list (or `ensemble_models`) if that
    creates unnecessary ensemble runs.

!!! note "Web viewer overlays"
    The track and cone overlays are simply omitted from the web viewer;
    everything else (maps, timeseries) is unaffected.
