# Running & verifying

## Required data layout

Stage the ensemble data in the meteo database exactly as before, minus the
`.cyc` files (or with empty ones — both work):

```text
<meteo_db>/<dataset>/<YYYYMMDD_HHz>/
    <member_01>/
        <member_01>.20260706_0000.nc
        <member_01>.20260706_0600.nc
        ...
    <member_02>/
        ...
```

Requirements:

- The scenario must have `run_ensemble = true` and point `meteo_dataset` at
  this dataset.
- Member folder names must prefix their `.nc` files (`<member>*.nc`) — that
  prefix is now the detection signature when no `.cyc` is present.
- `config.run.event_mode` must be `"meteo"` (the default storm/weather flow).
- Per-member data is assumed pre-staged: `download_meteo()` skips per-member
  datasets, unchanged.

Then run as usual:

```powershell
python -m cosmos run <scenario_name> --path <run_folder> --cycle <YYYYMMDD_HHz>
```

## What to look for in `cosmos.log`

A healthy track-less run logs, in order:

```text
Per-member meteo ensemble detected WITHOUT track (gridded forcing only): N members (...); deterministic = <member>
Collecting meteo data (per-member, deterministic=<member>) : <dataset>
No (usable) deterministic track file found: <path>/<member>.cyc
Per-member ensemble will run on gridded forcing only (no spiderwebs, no track cone).
Setting up per-member meteo ensemble without cyclone track (N members) ...
Meteo ensemble (no track) done ...
```

If the deterministic `.cyc` exists but is empty or broken you will instead see
one of:

```text
Deterministic track file <path> has fewer than 3 track points — ignoring track.
Could not read deterministic track file <path> (<error>) — ignoring track.
```

followed by the same "gridded forcing only" lines.

During pre-processing, each ensemble model logs one line per member as its
forcing cut-out is written:

```text
  meteo forcing files for ensemble member <member> ...
```

## Quick checklist after pre-processing

- Each `_ensemble` model's job folder contains one subfolder per member with
  `sfincs_wind.nc` (or `hurrywave_wind.nc`, `amu`/`amv`/`amp`) inside.
- **No** `sfincs.spw` / `hurrywave.spw` in the member folders, and no
  `spwfile` line in `sfincs.inp` / `hurrywave.inp`.
- `<cycle>/track/` in the scenario cycle folder is absent or empty (no
  `storm.spw` / `storm.cyc`).
- The web viewer builds without a track or cone overlay.

## Caveats

!!! warning "Mixed tracks"
    If the **deterministic** (last-sorted) member has a usable track but other
    members do not, the run uses the normal spiderweb flow and the track-less
    members are skipped during spiderweb generation with a warning. Those
    member simulations will then fail, because the shared model input declares
    a `spwfile` the member folder does not have. Keep tracks all-or-nothing
    per cycle, or ask for the per-member fallback to be implemented.

!!! warning "Cloud run mode"
    `run_sfincs.py` / `run_hurrywave.py` unconditionally download the member
    spiderweb from S3 when `run_mode = "cloud"` and the model is an ensemble
    member. Track-less ensembles have no spiderwebs on S3, so **cloud mode is
    not yet supported for track-less runs**. Local `serial` / `parallel`
    modes are fine.

!!! note "Deterministic models"
    Deterministic (non-ensemble) models are unaffected: they are forced by
    the deterministic member's gridded data, which is still collected before
    the track check. They previously also received `storm.spw` on top of the
    gridded forcing; in track-less runs that extra spiderweb layer simply does
    not exist.
