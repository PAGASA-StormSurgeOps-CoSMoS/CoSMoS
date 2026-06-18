"""User-supplied pre/post-processing scripts.

A scenario can hook into the forecast cycle by pointing
`cosmos.config.run.pre_processing_script` or
`cosmos.config.run.post_processing_script` at a Python file that exposes a
`main(cycle_info_file)` function. Before the hook fires, a `cycle_info.yml`
summary of the scenario, cycle and active models is written into the cycle
directory and its path is passed to the script.
"""

import importlib.util
import os

from cht_utils.fileio.yaml import dict2yaml

from .cosmos import cosmos


def write_cycle_info_yml() -> str:
    """Serialise the current cycle's scenario/model summary to YAML.

    Always called once per cycle so the file is available to any downstream
    consumer (custom pre/post-processing scripts, external dashboards, etc.).
    Returns the path of the written file.
    """
    cycle_info_file = _cycle_info_path()
    config = {
        "scenario_name": cosmos.scenario.name,
        "cycle": cosmos.cycle_string,
        "duration_hours": cosmos.scenario.runtime,
        "meteo_dataset": cosmos.scenario.meteo_dataset,
        "cyclone_track_forecast_source": cosmos.scenario.cyclone_track_forecast_source,
        "run_folder_path": cosmos.config.path.main,
        "meteo_database_path": cosmos.config.meteo_database.path,
        "model_database_path": cosmos.config.model_database.path,
        "model": [
            {
                "name": m.name,
                "long_name": m.long_name,
                "region": m.region,
                "type": m.type,
                "role": m.role,
            }
            for m in cosmos.scenario.model
        ],
    }
    dict2yaml(cycle_info_file, config)
    return cycle_info_file


def run_pre_processing() -> None:
    """Run the configured pre-processing script, if any."""
    _run_custom_script(cosmos.config.run.pre_processing_script, "pre processing")


def run_post_processing() -> None:
    """Run the configured post-processing script, if any."""
    _run_custom_script(cosmos.config.run.post_processing_script, "post processing")


def _run_custom_script(script_path, label):
    if script_path is None:
        return
    cosmos.log(f"Running {label} script ...")
    try:
        if not os.path.isfile(script_path):
            return
        spec = importlib.util.spec_from_file_location("custom_module", script_path)
        custom_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(custom_module)
        custom_module.main(_cycle_info_path())
    except Exception as e:
        cosmos.log(f"An error occurred while running the {label} script !")
        cosmos.log(f"Error: {e}")


def _cycle_info_path() -> str:
    return os.path.join(cosmos.scenario.cycle_path, "cycle_info.yml")
