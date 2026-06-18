"""Scenario and configuration validation for CoSMoS.

Performs pre-flight checks on a scenario without downloading meteo, running
models, or building the web viewer. Reports errors (fatal) and warnings
(suspicious but not blocking).
"""

import os
from typing import Dict, List

import toml


def validate_scenario(cosmos_instance, scenario_name: str) -> bool:
    """Validate a CoSMoS scenario before running it.

    Checks the configuration, scenario file, model database, nesting chains,
    meteo references, station files, and executable paths. Prints a summary
    of all findings.

    Parameters
    ----------
    cosmos_instance : CoSMoS
        The initialized CoSMoS singleton.
    scenario_name : str
        Name of the scenario to validate.

    Returns
    -------
    bool
        ``True`` if no errors were found, ``False`` otherwise.
    """
    errors: List[str] = []
    warnings: List[str] = []
    info: List[str] = []

    config = cosmos_instance.config

    # ── Configuration checks ─────────────────────────────────────────

    _check_config(config, errors, warnings)

    # ── Scenario file checks ─────────────────────────────────────────

    scenario_path = os.path.join(config.path.scenarios, scenario_name)
    scenario_file = os.path.join(scenario_path, "scenario.toml")

    if not os.path.exists(scenario_path):
        errors.append(f"Scenario folder not found: {scenario_path}")
        _print_report(scenario_name, errors, warnings, info)
        return False

    if not os.path.exists(scenario_file):
        errors.append(f"Scenario file not found: {scenario_file}")
        _print_report(scenario_name, errors, warnings, info)
        return False

    try:
        sc_dict = toml.load(scenario_file)
    except Exception as e:
        errors.append(f"Failed to parse scenario file: {e}")
        _print_report(scenario_name, errors, warnings, info)
        return False

    # ── Resolve models in scenario ───────────────────────────────────

    models_in_scenario = _resolve_models(
        sc_dict, cosmos_instance, config, errors, warnings
    )

    info.append(f"Models in scenario: {len(models_in_scenario)}")
    for name, minfo in models_in_scenario.items():
        info.append(f"  {name} ({minfo['type']}, region: {minfo['region']})")

    # ── Per-model checks ─────────────────────────────────────────────

    model_names = set(models_in_scenario.keys())

    for name, minfo in models_in_scenario.items():
        _check_model(name, minfo, config, model_names, errors, warnings)

    # ── Nesting chain checks ─────────────────────────────────────────

    _check_nesting(models_in_scenario, model_names, errors, warnings, info)

    # ── Meteo checks ─────────────────────────────────────────────────

    meteo_dataset = sc_dict.get("meteo_dataset")
    meteo_spiderweb = sc_dict.get("meteo_spiderweb")
    meteo_track = sc_dict.get("meteo_track")

    if meteo_dataset:
        if hasattr(cosmos_instance, "meteo_database"):
            if meteo_dataset not in cosmos_instance.meteo_database.dataset:
                errors.append(
                    f"Meteo dataset '{meteo_dataset}' not found in meteo database"
                )
        else:
            warnings.append("Meteo database not loaded — cannot verify meteo dataset")
    elif meteo_spiderweb:
        spw_path = os.path.join(
            config.meteo_database.path, "spiderwebs", meteo_spiderweb
        )
        if not os.path.exists(spw_path):
            # Try without extension
            if not os.path.exists(spw_path + ".spw"):
                warnings.append(f"Spiderweb file not found: {spw_path}")
    elif meteo_track:
        track_path = os.path.join(config.meteo_database.path, "tracks", meteo_track)
        if not os.path.exists(track_path):
            if not os.path.exists(track_path + ".cyc"):
                warnings.append(f"Track file not found: {track_path}")
    else:
        warnings.append("No meteorological forcing specified in scenario")

    # ── Station checks ───────────────────────────────────────────────

    if "station" in sc_dict:
        for station_entry in sc_dict["station"]:
            station_file = station_entry.get("name")
            if station_file:
                full_path = os.path.join(config.path.stations, station_file)
                if not os.path.exists(full_path):
                    # Try with .toml extension
                    if not os.path.exists(full_path + ".toml"):
                        errors.append(f"Station file not found: {full_path}")

    # ── Executable checks (only relevant for local execution) ───────

    if config.run.run_mode == "serial":
        _check_executables(models_in_scenario, config, errors, warnings)

    # ── Print report ─────────────────────────────────────────────────

    _print_report(scenario_name, errors, warnings, info)

    return len(errors) == 0


def _check_config(config, errors: List[str], warnings: List[str]) -> None:
    """Check configuration paths exist."""
    if not config.path.main or not os.path.exists(config.path.main):
        errors.append(f"Main path does not exist: {config.path.main}")

    if not config.model_database.path or not os.path.exists(config.model_database.path):
        errors.append(
            f"Model database path does not exist: {config.model_database.path}"
        )

    if not config.meteo_database.path or not os.path.exists(config.meteo_database.path):
        warnings.append(
            f"Meteo database path does not exist: {config.meteo_database.path}"
        )


def _resolve_models(
    sc_dict: dict, cosmos_instance, config, errors: List[str], warnings: List[str]
) -> Dict[str, dict]:
    """Resolve which models are in the scenario, returning a dict of name → info."""
    models: Dict[str, dict] = {}

    if "model" not in sc_dict:
        errors.append("No [[model]] entries found in scenario file")
        return models

    for mdl in sc_dict["model"]:
        if "name" in mdl:
            name = mdl["name"].lower()
            if name in cosmos_instance.all_models:
                models[name] = dict(cosmos_instance.all_models[name])
            else:
                errors.append(f"Model '{name}' not found in model database")

        elif "region" in mdl or "super_region" in mdl:
            region_list = []
            type_list = mdl.get("type", [])

            if "region" in mdl:
                region_list.append(mdl["region"])

            if "super_region" in mdl:
                sr_name = mdl["super_region"].lower()
                if hasattr(config, "super_region") and sr_name in config.super_region:
                    for region in config.super_region[sr_name].get("region", []):
                        if region not in region_list:
                            region_list.append(region)
                else:
                    errors.append(f"Super region '{sr_name}' not found")

            for aname, ainfo in cosmos_instance.all_models.items():
                if ainfo["region"] in region_list:
                    if not type_list or ainfo["type"] in type_list:
                        models[aname] = dict(ainfo)
        else:
            warnings.append(
                "Model entry in scenario has no 'name', 'region', or 'super_region'"
            )

    return models


def _check_model(
    name: str,
    minfo: dict,
    config,
    model_names: set,
    errors: List[str],
    warnings: List[str],
) -> None:
    """Check a single model's files and configuration."""
    region = minfo["region"]
    mtype = minfo["type"]
    model_path = os.path.join(config.model_database.path, region, mtype, name)

    if not os.path.exists(model_path):
        errors.append(f"Model folder not found: {model_path}")
        return

    # Check model.toml
    toml_file = os.path.join(model_path, "model.toml")
    if not os.path.exists(toml_file):
        errors.append(f"model.toml not found for {name}: {toml_file}")
        return

    try:
        model_dict = toml.load(toml_file)
    except Exception as e:
        errors.append(f"Failed to parse model.toml for {name}: {e}")
        return

    # Check input folder
    input_path = os.path.join(model_path, "input")
    if not os.path.exists(input_path):
        errors.append(f"Input folder not found for {name}: {input_path}")

    # Check CRS
    if "crs" not in model_dict:
        warnings.append(f"No CRS defined for model {name}")

    # Check nesting references
    for nest_key in ("flow_nested", "wave_nested", "bw_nested"):
        if nest_key in model_dict and model_dict[nest_key]:
            parent = model_dict[nest_key].lower()
            if parent not in model_names:
                errors.append(
                    f"Model {name}: {nest_key} references '{parent}' "
                    f"which is not in the scenario"
                )

    # Check tiling folders if maps are enabled
    if model_dict.get("make_flood_map", False):
        tiling_path = os.path.join(model_path, "tiling")
        if not os.path.exists(tiling_path):
            warnings.append(f"Tiling folder missing for {name} (make_flood_map=true)")
        else:
            if not os.path.exists(os.path.join(tiling_path, "indices")):
                warnings.append(f"Tiling indices folder missing for {name}")
            if not os.path.exists(os.path.join(tiling_path, "topobathy")):
                warnings.append(f"Tiling topobathy folder missing for {name}")

    if model_dict.get("make_wave_map", False):
        tiling_path = os.path.join(model_path, "tiling")
        if not os.path.exists(os.path.join(tiling_path, "indices")):
            warnings.append(
                f"Tiling indices folder missing for {name} (make_wave_map=true)"
            )


def _check_nesting(
    models: Dict[str, dict],
    model_names: set,
    errors: List[str],
    warnings: List[str],
    info: List[str],
) -> None:
    """Check nesting chains for cycles and build a nesting tree."""
    from .cosmos import cosmos

    # Build parent→children mapping for display
    children: Dict[str, List[str]] = {}
    roots: List[str] = []

    for name in models:
        model_path = os.path.join(
            cosmos.config.model_database.path,
            models[name]["region"],
            models[name]["type"],
            name,
        )
        toml_file = os.path.join(model_path, "model.toml")
        if not os.path.exists(toml_file):
            continue
        try:
            md = toml.load(toml_file)
        except Exception:
            continue

        parent = md.get("flow_nested") or md.get("wave_nested")
        if parent:
            parent = parent.lower()
            if parent not in children:
                children[parent] = []
            children[parent].append(name)
        else:
            roots.append(name)

    # Check for circular nesting
    for name in models:
        visited = set()
        current = name
        while current:
            if current in visited:
                errors.append(f"Circular nesting detected involving model {name}")
                break
            visited.add(current)
            model_path = os.path.join(
                cosmos.config.model_database.path,
                models.get(current, models.get(name, {})).get("region", ""),
                models.get(current, models.get(name, {})).get("type", ""),
                current,
            )
            toml_file = os.path.join(model_path, "model.toml")
            if not os.path.exists(toml_file):
                break
            try:
                md = toml.load(toml_file)
            except Exception:
                break
            parent = md.get("flow_nested") or md.get("wave_nested")
            current = parent.lower() if parent else None

    # Print nesting tree
    if roots:
        info.append("Nesting tree:")
        for root in sorted(roots):
            _print_tree(root, children, info, indent=2)


def _print_tree(
    name: str, children: Dict[str, List[str]], info: List[str], indent: int
) -> None:
    """Recursively build nesting tree for display."""
    info.append(" " * indent + name)
    if name in children:
        for child in sorted(children[name]):
            _print_tree(child, children, info, indent + 2)


def _check_executables(
    models: Dict[str, dict], config, errors: List[str], warnings: List[str]
) -> None:
    """Check that required model executables exist."""
    types_used = {minfo["type"] for minfo in models.values()}

    exe_map = {
        "sfincs": ("sfincs_path", config.executables.sfincs_path),
        "hurrywave": ("hurrywave_path", config.executables.hurrywave_path),
        "delft3dfm": (
            "delft3dfm_path",
            getattr(config.executables, "delft3dfm_path", None),
        ),
        "xbeach": ("xbeach_path", config.executables.xbeach_path),
        "beware": ("beware_path", config.executables.beware_path),
    }

    for mtype in types_used:
        if mtype in exe_map:
            key, path = exe_map[mtype]
            if not path:
                warnings.append(
                    f"Executable path not set for {mtype} (config.executables.{key})"
                )
            elif not os.path.exists(path):
                warnings.append(f"Executable path does not exist for {mtype}: {path}")


def _print_report(
    scenario_name: str,
    errors: List[str],
    warnings: List[str],
    info: List[str],
) -> None:
    """Print the validation report."""
    print("")
    print("=" * 60)
    print(f"  Validation report for scenario: {scenario_name}")
    print("=" * 60)

    if info:
        print("")
        for line in info:
            print(f"  {line}")

    if warnings:
        print("")
        print(f"  WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"    ! {w}")

    if errors:
        print("")
        print(f"  ERRORS ({len(errors)}):")
        for e in errors:
            print(f"    X {e}")

    print("")
    if errors:
        print(f"  RESULT: FAILED ({len(errors)} errors, {len(warnings)} warnings)")
    elif warnings:
        print(f"  RESULT: PASSED with {len(warnings)} warnings")
    else:
        print("  RESULT: PASSED")
    print("=" * 60)
    print("")
