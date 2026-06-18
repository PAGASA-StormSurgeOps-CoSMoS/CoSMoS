"""Cleanup routines for CoSMoS run folders.

Removes old input files, restart files, job lists, and outdated cycle data
to manage disk usage during continuous and risk map forecast modes.
"""

import datetime
import os

import cht_utils.fileops as fo

from .cosmos import cosmos


def clean_up() -> None:
    """Remove old files based on the configured cleanup mode.

    Supported modes: ``"risk_map"``, ``"continuous"``, ``"continuous_hindcast"``.
    """
    if cosmos.config.run.clean_up_mode == "risk_map":
        remove_input_folders()
        remove_overall_model_folders()
        remove_all_restart_folders()
        remove_track_folder()
        remove_job_list_folder()

    if cosmos.config.run.clean_up_mode == "continuous":
        remove_older_cycles()
        remove_older_restart_files()
        remove_older_webviewer_cycles()

    if cosmos.config.run.clean_up_mode == "continuous_hindcast":
        remove_input_folders()
        remove_job_list_folder()
        remove_older_restart_files()


def remove_input_folders() -> None:
    """Remove cycle input folders for all models."""
    for model in cosmos.scenario.model:
        fo.rmdir(model.cycle_input_path)


def remove_overall_model_folders() -> None:
    """Remove cycle folders for models that have nested flow models."""
    for model in cosmos.scenario.model:
        if len(model.nested_flow_models) > 0:
            fo.rmdir(model.cycle_path)


def remove_all_restart_folders() -> None:
    """Remove the entire restart folder for the current scenario."""
    fo.rmdir(cosmos.scenario.restart_path)


def remove_track_folder() -> None:
    """Remove the spiderweb track folder for the current cycle."""
    fo.rmdir(cosmos.scenario.cycle_track_spw_path)


def remove_job_list_folder() -> None:
    """Remove the job list folder for the current cycle."""
    fo.rmdir(cosmos.scenario.cycle_job_list_path)


def remove_older_cycles() -> None:
    """Remove cycle folders older than ``prune_after_hours``."""
    all_cycles = fo.list_folders(os.path.join(cosmos.scenario.path, "*"), basename=True)
    for cycle in all_cycles:
        if cycle.endswith("z"):
            tstr = cycle.replace("z", "")
            t = datetime.datetime.strptime(tstr, "%Y%m%d_%H").replace(
                tzinfo=cosmos.cycle.tzinfo
            )
            if t < cosmos.cycle - datetime.timedelta(
                hours=cosmos.config.run.prune_after_hours
            ):
                fo.rmdir(os.path.join(cosmos.scenario.path, cycle))


def remove_older_restart_files() -> None:
    """Remove restart files older than ``prune_after_hours`` before the current cycle."""
    rstpath = cosmos.scenario.restart_path
    if not os.path.exists(rstpath):
        return

    all_models = fo.list_folders(os.path.join(rstpath, "*"), basename=True)
    cutoff = cosmos.cycle - datetime.timedelta(
        hours=cosmos.config.run.prune_after_hours
    )

    for model in all_models:
        for subdir in ("flow", "wave"):
            restart_dir = os.path.join(rstpath, model, subdir)
            restart_files = fo.list_files(restart_dir, full_path=False)
            for file in restart_files:
                if file.endswith(".rst"):
                    tstr = file.replace(".rst", "")[-15:]
                    t = datetime.datetime.strptime(tstr, "%Y%m%d.%H%M%S").replace(
                        tzinfo=cosmos.cycle.tzinfo
                    )
                    if t < cutoff:
                        pth = os.path.join(restart_dir, file)
                        cosmos.log(f"Removing old restart file : {pth}")
                        os.remove(pth)


def remove_older_webviewer_cycles() -> None:
    """Remove webviewer cycle folders older than 24 hours."""
    wvpath = os.path.join(cosmos.webviewer.path, "data", cosmos.scenario.name)
    all_cycles = fo.list_folders(os.path.join(wvpath, "*"), basename=True)
    for cycle in all_cycles:
        if cycle.endswith("z"):
            tstr = cycle.replace("z", "")
            t = datetime.datetime.strptime(tstr, "%Y%m%d_%H").replace(
                tzinfo=cosmos.cycle.tzinfo
            )
            if t < cosmos.cycle - datetime.timedelta(hours=24):
                fo.rmdir(os.path.join(wvpath, cycle))
