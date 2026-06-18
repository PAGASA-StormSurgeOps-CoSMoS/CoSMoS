"""Main forecast loop for CoSMoS.

Orchestrates the end-to-end forecast cycle: meteo download, track ensemble
generation, scenario setup, model execution, web viewer creation, and cleanup.
"""

import copy
import datetime
import os
import sched
import time

import numpy as np

from .clean_up import clean_up
from .cloud import Cloud
from .cosmos import cosmos
from .custom_processing import (
    run_post_processing,
    run_pre_processing,
    write_cycle_info_yml,
)
from .meteo import collect_meteo, download_meteo
from .scenario import Scenario
from .track_ensemble import setup_track_ensemble
from .tsunami import CoSMoS_Tsunami
from .webviewer import WebViewer

try:
    from .argo import Argo
except Exception:
    print("Argo not available")

import cht_utils.fileops as fo


class MainLoop:
    """Read the scenario.toml file, determine cycle times, and run cosmos model loop.

    Parameters
    ----------
    start : func
        Start cosmos scenario
    run : func
        Run main loop

    See Also
    --------
    cosmos.cosmos.CoSMoS
    cosmos.Scenario
    cosmos.ModelLoop
    cosmos.Model
    """

    def __init__(self) -> None:
        """Initialize main loop state."""
        self.just_initialize = False
        self.run_models = True
        self.clean_up = False

    def start(self, cycle=None) -> None:
        """Update the configuration, read the scenario.toml file, determine cycle times, initialize webviewer, and start cosmos_main_loop.run with scheduler.

        Parameters
        ----------
        cycle : int
            Datestring of cycle time

        See Also
        --------
        cosmos.Configuration
        cosmos.MainLoop.run
        """

        # Determines cycle time and runs main loop

        cosmos.log("Starting main loop ...")

        # Set cloud object
        if cosmos.config.run.run_mode == "cloud":
            cosmos.cloud = Cloud()
            cosmos.argo = Argo()

        # Read scenario
        cosmos.scenario = Scenario(cosmos.scenario_name)
        # This also determines which models are part of this scenario
        cosmos.scenario.read()

        if not cycle:
            # Determine cycle time
            t = datetime.datetime.now(datetime.timezone.utc)
            h0 = t.hour
            h0 = h0 - np.mod(h0, cosmos.config.run.interval)
            cosmos.cycle = t.replace(microsecond=0, second=0, minute=0, hour=h0)
        else:
            cosmos.cycle = cycle.replace(tzinfo=datetime.timezone.utc)

        # Determine end time of cycle
        cosmos.stop_time = cosmos.cycle + datetime.timedelta(
            hours=cosmos.scenario.runtime
        )

        # Determine next cycle time
        if cosmos.config.run.mode == "continuous":
            # In continuous mode, but not catch up, the next cycle is based on current time + interval
            cosmos.next_cycle_time = cosmos.cycle + datetime.timedelta(
                hours=cosmos.config.run.interval
            )
            if cosmos.config.run.catch_up:
                # Get max of next cycle time (current cycle plus interval) and current time round down to nearest interval
                t = datetime.datetime.now(datetime.timezone.utc)
                h0 = t.hour
                h0 = h0 - np.mod(h0, cosmos.config.run.interval)
                now_cycle = t.replace(microsecond=0, second=0, minute=0, hour=h0)
                if now_cycle > cosmos.next_cycle_time:
                    cosmos.next_cycle_time = now_cycle

            if cosmos.last_cycle:
                if cosmos.cycle >= cosmos.last_cycle:
                    cosmos.next_cycle_time = None
        else:
            # Single shot mode, so no next cycle
            cosmos.next_cycle_time = None

        # Cycle string (used for file and folder names)
        cosmos.cycle_string = cosmos.cycle.strftime("%Y%m%d_%Hz")

        # Web viewer
        if cosmos.config.webviewer and cosmos.config.run.make_webviewer:
            # Prepare new web viewer, or copy scenario data to existing viewer
            # Add scenario folder, cycle folder to web viewer
            cosmos.webviewer = WebViewer(cosmos.config.webviewer.name)

        # Set scenario paths (with updated cycle time)
        cosmos.scenario.set_paths()

        # Determine time at which this cycle should start running
        # When running in single_shot mode, the simulation should start immediately
        delay = datetime.timedelta(hours=cosmos.config.run.delay)  # Delay in hours
        tnow = datetime.datetime.now(datetime.timezone.utc)

        if cosmos.config.run.mode == "single_shot":
            # Sigle shot, so we can start now
            start_time = tnow + datetime.timedelta(seconds=1)
        else:
            # Continuous, so we start at the cycle time (plus delay if this is set)
            start_time = cosmos.cycle + delay + datetime.timedelta(seconds=5)
            # However, if start time has already passed, start immediately
            if start_time < tnow:
                start_time = tnow + datetime.timedelta(seconds=1)

        self.scheduler = sched.scheduler(time.time, time.sleep)
        dt = start_time - tnow

        # Kick off main_loop run
        cosmos.log(
            "Next cycle "
            + cosmos.cycle_string
            + " will start at "
            + start_time.strftime("%Y-%m-%d %H:%M:%S")
            + " UTC"
        )
        self.scheduler.enter(dt.seconds, 1, self.run, ())
        self.scheduler.run()

    def run(self) -> None:
        """Run main loop.

        - Prepare models: Get list of nested models and set paths
        - Check if model data needs to be uploaded to webviewer
        - Get start and stop times
        - Download and collect meteo
        - Optional: Make track ensemble or spiderweb from track file
        - Check which models are finished
        - Start model loop

        See Also
        --------
        cosmos.Model.get_nested_models
        cosmos.Model.set_paths
        cosmos.meteo.Meteo.download_and_collect_meteo
        cosmos.track_ensemble.setup_track_ensemble
        cosmos.ModelLoop.start
        """

        # Start by reading all available models, stations, etc.
        cosmos.log("Starting cycle ...")

        # if cosmos.config.run.clean_up:
        #     # Run cleaning cycle
        #     clean_up()

        # Create scenario cycle paths
        fo.mkdir(cosmos.scenario.cycle_path)
        fo.mkdir(cosmos.scenario.cycle_models_path)
        fo.mkdir(cosmos.scenario.cycle_job_list_path)

        # Check if there are any tide_only models that need to be added
        tide_only_models = []
        for model in cosmos.scenario.model:
            if model.flow and not model.wave:
                # This is a flow only model
                if model.include_tide_only:
                    # This model should include tide only forcing
                    cosmos.log(f"Adding tide only forcing to model {model.name}")
                    # Create new model that is a copy of this one, but only for tide
                    tide_only_model = copy.deepcopy(model)
                    tide_only_model.name = model.name + "_tide_only"
                    tide_only_model.deterministic_name = tide_only_model.name
                    tide_only_model.long_name = model.long_name + " (tide only)"
                    tide_only_model.role = "tide_only"
                    # Turn off meteo forcing for this model
                    # We do not set the meteo dataset to None, because we need this for the restart file
                    # However, due to the deepcopy, we do need to set meteo_dataset again here to that of the original model
                    tide_only_model.meteo_dataset = model.meteo_dataset
                    tide_only_model.meteo_spiderweb = None
                    tide_only_model.meteo_track = None
                    tide_only_model.meteo_wind = False
                    tide_only_model.meteo_atmospheric_pressure = False
                    tide_only_model.meteo_precipitation = False
                    # Turn off water_level_map for this model (this is not necessary, as )
                    tide_only_model.make_water_level_map = False
                    tide_only_model.make_precipitation_map = False
                    # Add to scenario models
                    tide_only_models.append(tide_only_model)
                    # Link to original model
                    model.tide_only_model = tide_only_model
                    model.make_storm_surge_map = True

        cosmos.scenario.model.extend(tide_only_models)

        # Prepare some stuff for each model
        for model in cosmos.scenario.model:
            model.get_nested_models()
            model.set_paths()
            # Set model status
            model.status = "waiting"
            if model.priority == 0:
                model.run_simulation = False

        # Check if model data needs to be uploaded to webviewer (only upload for high-res nested models)
        # Can this be moved to the model class?
        modelopt = ["flow", "wave"]
        modeloptnames = ["tide_gauge", "wave_buoy"]
        for model in cosmos.scenario.model:
            for iopt, opts in enumerate(modelopt):
                all_nested_models = model.get_all_nested_models(opts)
                if all_nested_models:
                    all_nested_stations = []
                    if all_nested_models[0].type == "beware":
                        all_nested_models = [model]
                        bw = 1
                    else:
                        bw = 0
                    for mdl in all_nested_models:
                        for st in mdl.station:
                            all_nested_stations.append(st.name)
                    for station in model.station:
                        if station.type == modeloptnames[iopt]:
                            if station.name in all_nested_stations and bw == 0:
                                station.upload = False

        # Start and stop times
        cosmos.log("Getting start and stop times ...")
        get_start_and_stop_times()

        # Set reference date to minimum of all start times
        rfdate = datetime.datetime(2200, 1, 1, 0, 0, 0)
        for model in cosmos.scenario.model:
            if model.flow:
                rfdate = min(rfdate, model.flow_start_time)
            if model.wave:
                rfdate = min(rfdate, model.wave_start_time)
        cosmos.scenario.ref_date = datetime.datetime(
            rfdate.year, rfdate.month, rfdate.day, 0, 0, 0
        )

        # Write start and stop times to log file
        for model in cosmos.scenario.model:
            if model.flow:
                if model.flow_restart_file:
                    # not the entire path
                    rststr = (
                        f" (restart file : {model.flow_restart_file.split('/')[-1]})"
                    )
                else:
                    rststr = " (no restart file)"
                cosmos.log(
                    model.long_name
                    + " : "
                    + model.flow_start_time.strftime("%Y%m%d %H%M%S")
                    + " - "
                    + model.flow_stop_time.strftime("%Y%m%d %H%M%S")
                    + rststr
                )
            else:
                if model.wave_restart_file:
                    # not the entire path
                    rststr = (
                        f" (restart file : {model.wave_restart_file.split('/')[-1]})"
                    )
                else:
                    rststr = " (no restart file)"
                cosmos.log(
                    model.long_name
                    + " : "
                    + model.wave_start_time.strftime("%Y%m%d %H%M%S")
                    + " - "
                    + model.wave_stop_time.strftime("%Y%m%d %H%M%S")
                    + rststr
                )

        # Always write cycle_info.yml so downstream consumers (custom
        # pre/post-processing scripts, external dashboards) can rely on it.
        write_cycle_info_yml()

        run_pre_processing()

        if cosmos.config.run.event_mode == "meteo":
            # Running storm or other weather event

            # Detect whether the meteo dataset has one subfolder per ensemble
            # member (each with its own gridded nc files + <member>.cyc).
            # When yes, the per-member spw + amu/amv flow downstream branches
            # on cosmos.scenario.meteo_ensemble_mode.
            cosmos.scenario.detect_meteo_ensemble_mode()

            # Download meteo data
            if cosmos.config.run.download_meteo:
                download_meteo()

            # Merge meteo data (in case of forcing with track file, this is also where the spiderweb is generated)
            collect_meteo()

            if cosmos.scenario.run_ensemble and cosmos.tropical_cyclone:
                # Make track ensemble (this also add 'new' ensemble models that fall within the cone)
                setup_track_ensemble()
            # elif cosmos.scenario.meteo_spiderweb or not os.path.isabs(cosmos.scenario.meteo_track):
            #     # Make spiderweb if does not exist yet
            #     track_to_spw()

        elif cosmos.config.run.event_mode == "tsunami":
            # Generate tsunami NetCDF file. Initial conditions for model(s) are generated from this file.
            cosmos.log("Generating tsunami NetCDF file ...")
            cosmos.tsunami = CoSMoS_Tsunami()
            cosmos.tsunami.generate_from_scenario(cosmos.scenario.finite_fault_file)

        # Should remove this at some point?
        if self.just_initialize:
            # No need to do anything else here, except for setting the status of the models
            for model in cosmos.scenario.model:
                model.status = "finished"
            return

        # Get list of models that have already finished and set their status to finished
        finished_list = os.listdir(cosmos.scenario.cycle_job_list_path)
        for model in cosmos.scenario.model:
            for file_name in finished_list:
                model_name = file_name.split(".")[0]
                if model.name.lower() == model_name.lower():
                    model.status = "finished"
                    model.run_simulation = False
                    break

        # Can run_models be False?
        if self.run_models:
            # Upload spw files to S3
            if (
                cosmos.scenario.run_ensemble
                and cosmos.tropical_cyclone
                and cosmos.config.run.run_mode == "cloud"
            ):
                # Upload spw files to S3
                cosmos.log("Uploading spiderweb files to S3")
                path = cosmos.scenario.cycle_track_ensemble_spw_path
                subfolder = cosmos.scenario.name + "/track_ensemble/spw"
                cosmos.cloud.upload_folder("cosmos-scenarios", path, subfolder)

            # And now start the model loop
            cosmos.log("Starting model loop ...")
            cosmos.model_loop.start()

    def finish(self) -> None:
        """Finish the main loop by performing clean up and making web viewer."""

        # Run clean up first (this has to be done before making the webviewer, as it removes some cycle folders)
        if cosmos.config.run.clean_up:
            clean_up()

        run_post_processing()

        # Post process data (making floodmaps, uploading to server etc.)
        # Try to run post-processing. If it fails, print error message and continue.
        if cosmos.config.run.make_webviewer:
            try:
                cosmos.webviewer.make()
                if cosmos.config.run.upload:
                    current_path = os.getcwd()
                    try:
                        cosmos.webviewer.upload()
                    except Exception:
                        print(
                            "An error occurred when uploading web viewer to server !!!"
                        )
                    os.chdir(current_path)
            except Exception as e:
                print("An error occured while making web viewer !")
                print(f"Error: {e}")
        else:
            cosmos.log(
                "Not making webviewer. Set make_webviewer to True in config file to make webviewer."
            )

        # Move log file to scenario cycle path
        log_file = os.path.join(cosmos.config.path.main, "cosmos.log")
        fo.move_file(log_file, cosmos.scenario.cycle_path)

        # Delete jobs folder
        if cosmos.config.run.run_mode == "serial":
            pth = os.path.join(cosmos.config.path.jobs, cosmos.scenario.name)
            fo.rmdir(pth)

        # Check if we need to start a new cycle
        if cosmos.next_cycle_time:
            # Start new main loop
            cosmos.main_loop.start(cycle=cosmos.next_cycle_time)
        else:
            cosmos.log("All done.")


def get_start_and_stop_times() -> None:
    """Get cycle start and stop times."""

    y = cosmos.cycle.year
    cosmos.reference_time = datetime.datetime(y, 1, 1)

    start_time = cosmos.cycle

    stop_time = cosmos.stop_time

    start_time = start_time.replace(tzinfo=None)
    stop_time = stop_time.replace(tzinfo=None)

    cosmos.stop_time = stop_time

    # Find all the models that do not have any models nested in them

    # First waves

    for model in cosmos.scenario.model:
        if model.wave:
            model.wave_start_time = start_time
            model.wave_stop_time = stop_time

    # Make list of all wave models that do not have any models nested in them
    not_nested_models = []
    for model in cosmos.scenario.model:
        if model.wave:
            # This is a wave model
            if not model.nested_wave_models:
                # And it does not have any model nested in it
                not_nested_models.append(model)

    # Now for each of these models, loop up in the model tree until
    # not nested in any other model
    for not_nested_model in not_nested_models:
        nested = True
        model = not_nested_model
        nested_wave_start_time = start_time

        while nested:
            # nested_wave_start_time is the start time of the model that is nested in this model
            # this model should start at the same time or earlier
            model.wave_start_time = min(model.wave_start_time, nested_wave_start_time)

            # Check for restart files
            restart_time, restart_file = check_for_wave_restart_files(model)

            if not restart_time:
                # No restart file available, so subtract spin-up time
                tok = start_time - datetime.timedelta(hours=model.wave_spinup_time)
                model.wave_start_time = min(model.wave_start_time, tok)
                model.wave_restart_file = None
            else:
                model.wave_start_time = restart_time
                model.wave_restart_file = restart_file

            if model.wave_nested:
                # This model gets it's wave boundary conditions from another model
                nested_wave_start_time = model.wave_start_time
                # Set the new model to be
                model = model.wave_nested

            else:
                # Done looping through the tree
                nested = False

    # And now flow

    for model in cosmos.scenario.model:
        if model.flow:
            if model.wave:
                model.flow_start_time = model.wave_start_time
                model.flow_stop_time = model.wave_stop_time
            else:
                model.flow_start_time = start_time
                model.flow_stop_time = stop_time

    not_nested_models = []
    for model in cosmos.scenario.model:
        if model.flow:
            # This is a flow model
            if not model.nested_flow_models:
                # And it does not have any model nested in it
                not_nested_models.append(model)

    # Now for each of these models, loop up in the model tree until
    # not nested in any other model
    for not_nested_model in not_nested_models:
        nested = True
        model = not_nested_model
        nested_flow_start_time = start_time

        while nested:
            # flow_start_time is minimum this model's flow_start_time and the flow_start_time of the model that is nested in it.

            model.flow_start_time = min(model.flow_start_time, nested_flow_start_time)

            # Check for restart files
            restart_time, restart_file = check_for_flow_restart_files(model)

            if not restart_time:
                # No restart file available, so subtract spin-up time
                tok = start_time - datetime.timedelta(hours=model.flow_spinup_time)
                model.flow_start_time = min(model.flow_start_time, tok)
                model.flow_restart_file = None
            else:
                model.flow_start_time = restart_time
                model.flow_restart_file = restart_file

            if model.flow_nested:
                # This model gets it's flow boundary conditions from another model
                nested_flow_start_time = model.flow_start_time
                # On to the next model in the chain
                model = model.flow_nested

            else:
                # Done looping through the tree
                nested = False

    # For only wave model, also add flow start and stop time (used for meteo)
    for model in cosmos.scenario.model:
        if model.wave:
            if not model.flow_start_time:
                model.flow_start_time = model.wave_start_time
            if not model.flow_stop_time:
                model.flow_stop_time = model.wave_stop_time


def check_for_wave_restart_files(model) -> tuple:
    """Check if there are wave restart files."""
    restart_time = None
    restart_file = None

    path = model.restart_wave_path

    if os.path.exists(path):
        restart_list = os.listdir(path)
        times = []
        files = []
        for file_name in restart_list:
            tstr = file_name[-19:-4]
            t = datetime.datetime.strptime(tstr, "%Y%m%d.%H%M%S")
            times.append(t)
            files.append(file_name)

        # Now find the last time that is greater than the start time
        # and smaller than
        for it, t in enumerate(times):
            if (
                t
                > model.wave_start_time
                - datetime.timedelta(hours=model.wave_spinup_time)
                and t <= model.wave_start_time
            ):
                restart_time = t
                restart_file = files[it]
    else:
        fo.mkdir(path)

    return restart_time, restart_file


def check_for_flow_restart_files(model) -> tuple:
    """Check if there are flow restart files."""
    restart_time = None
    restart_file = None

    path = model.restart_flow_path

    if os.path.exists(path):
        restart_list = os.listdir(path)
        times = []
        files = []
        for file_name in restart_list:
            tstr = file_name[-19:-4]
            t = datetime.datetime.strptime(tstr, "%Y%m%d.%H%M%S")
            times.append(t)
            files.append(file_name)

        # Now find the last time that is greater than the start time
        # and smaller than
        for it, t in enumerate(times):
            if (
                t
                >= model.flow_start_time
                - datetime.timedelta(hours=model.flow_spinup_time)
                and t <= model.flow_start_time
            ):
                restart_time = t
                restart_file = files[it]
    else:
        fo.mkdir(path)

    return restart_time, restart_file
