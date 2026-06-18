"""Model execution loop for CoSMoS.

Manages the lifecycle of all models in a scenario: pre-processing, job
submission, progress monitoring, post-processing, and web viewer updates.
"""

import os
import sched
import time

from .cluster import cluster_dict as cluster
from .cosmos import cosmos

try:
    from .argo import Argo
except Exception:
    print("Argo not available")
import cht_utils.fileops as fo


class ModelLoop:
    """Pre-process, submit, move, and post-process all models and initialize webviewer once all models are finished.

    Parameters
    ----------
    start : func
        Start running model loop with scheduler
    run : func
        Run model loop
    stop : func
        Stop model loop

    See Also
    -------
    cosmos.MainLoop
    cosmos.Model
    cosmos.beware.CoSMoS_BEWARE
    cosmos.delft3dfm.CoSMoS_Delft3DFM
    cosmos.hurrywave.CoSMoS_HurryWave
    cosmos.sfincs.CoSMoS_SFINCS
    cosmos.xbeach.CoSMoS_XBeach
    """

    def __init__(self) -> None:
        pass

    def start(self) -> None:
        """Start cosmos_model_loop.run with scheduler.

        See Also
        -------
        cosmos.ModelLoop.run
        """

        self.status = "running"
        while self.status == "running":
            # This will be repeated until the status of the model loop changes to "done"
            self.scheduler = sched.scheduler(time.time, time.sleep)
            if cosmos.config.run.run_mode == "cloud":
                dt = 20.0  # Execute the next model loop 1 second from now
            else:
                dt = 1.0  # Execute the next model loop 1 second from now
            self.scheduler.enter(dt, 1, self.run, ())
            self.scheduler.run()

    def stop(self) -> None:
        """Stop cosmos_model_loop."""
        self.scheduler.cancel()

    def run(self) -> None:
        """Run all cosmos models defined in the scenario file.

        - Check for finished simulations and move them to scenario folder
        - Make waiting list, prepare input and submit these models
        - Post process models from Step 1 (time series data)
        - Check if all models are finished. If true: make webviewer

        See Also
        -------
        cosmos.sfincs.CoSMoS_SFINCS.move
        cosmos.sfincs.CoSMoS_SFINCS.pre_process
        cosmos.Model.submit_job
        cosmos.sfincs.CoSMoS_SFINCS.post_process
        """

        # First check for finished simulations (returns a list with model objects that just finished)
        finished_list = check_for_finished_simulations()

        # If there are simulations ready ...
        for model in finished_list:
            # First move data from all finished simulations
            # (so that pre-processing of next model can commence)
            # Post-processing will happen later
            if not model.status == "failed":
                if cosmos.config.run.run_mode == "cloud":
                    # Download job folder from cloud storage (ideally we do not need to do this, but then extraction of time series data needs to be done in the cloud as well)
                    # Alternatively, we could just download the his file for local post-processing
                    subfolder = (
                        cosmos.scenario.name + "/" + "models" + "/" + model.name + "/"
                    )
                    cosmos.cloud.download_folder(
                        "cosmos-scenarios", subfolder, model.job_path
                    )
                # Moving files to input, output and restart folders
                cosmos.log("Moving model " + model.long_name)
                try:
                    fo.mkdir(model.cycle_input_path)
                    fo.mkdir(model.cycle_output_path)
                    fo.mkdir(model.cycle_post_path)
                    model.move()
                    model.status = "simulation_finished"
                except Exception as e:
                    cosmos.log(
                        f"ERROR: Failed to move output for model {model.name}: {e}"
                    )
                    model.status = "failed"

        # Now prepare new models ready to run (returns a list with model objects that are ready to run)
        waiting_list = update_waiting_list()

        # Pre process all waiting simulations
        for model in waiting_list:
            cosmos.log("Pre-processing " + model.long_name + " ...")

            try:
                # Make job path and copy inputs
                fo.rmdir(model.job_path)
                fo.mkdir(model.job_path)
                # Also make restart paths in scenario folder
                fo.mkdir(model.restart_flow_path)
                fo.mkdir(model.restart_wave_path)

                # Copy base inputs to job folder
                src = os.path.join(model.path, "input", "*")
                fo.copy_file(src, model.job_path)

                # Do some pre-processing (meteo and nesting step 1)
                model.pre_process()

                # And submit the job
                model.submit_job()

            except Exception as e:
                cosmos.log(f"ERROR: Pre-processing failed for model {model.name}: {e}")
                model.status = "failed"

        # Now do post-processing on simulations that were finished
        for model in finished_list:
            # For now, only extract time series data
            cosmos.log("Post-processing " + model.long_name + " ...")

            try:
                model.post_process()
                cosmos.log("Post-processing " + model.long_name + " done.")
            except Exception as e:
                print("An error occured while post-processing : " + model.name)
                print(f"Error: {e}")

            model.status = "finished"

            # Write finished file
            # later change to if cosmos.config.run_mode == "parallel":
            try:
                finished_file_name = os.path.join(
                    model.cycle_output_path, "finished.txt"
                )
                fid = open(finished_file_name, "r")
                pcname = fid.read().splitlines()[1]
                fid.close()

                cosmos.log(model.long_name + " was run by " + pcname)

                file_name = os.path.join(
                    cosmos.scenario.cycle_job_list_path, model.name + ".finished"
                )
                fid = open(file_name, "w")
                fid.write("finished by " + pcname)
                fid.close()

            except Exception as e:
                file_name = os.path.join(
                    cosmos.scenario.cycle_job_list_path, model.name + ".finished"
                )
                fid = open(file_name, "w")
                fid.write("finished")
                fid.close()

        # Now check if all simulations are completely finished
        all_finished = True
        for model in cosmos.scenario.model:
            if model.status != "failed" and model.status != "finished":
                all_finished = False

        if all_finished:
            cosmos.log("All models finished!")
            self.status = "done"
            cosmos.main_loop.finish()

        else:
            # Do another model loop
            pass


def check_for_finished_simulations() -> list:
    """Check if there are finished simulations to be post-processed."""
    finished_list = []

    for model in cosmos.scenario.model:
        try:
            if model.status == "running":
                if cosmos.config.run.run_mode == "cloud":
                    # TODO: Implement handling of failed workflow. What happens
                    #      when a workflow fails?
                    if Argo.get_task_status(model.cloud_job) != "Running":
                        finished_list.append(model)
                else:
                    file_name = os.path.join(model.job_path, "finished.txt")
                    if os.path.exists(file_name):
                        finished_list.append(model)
        except Exception:
            print("An error occurred when checking job status!")

    return finished_list


def update_waiting_list() -> list:
    """Check which models can be run next according to their status and prioritization level."""
    # Check which models need to run next

    waiting_list = []
    priorities = []
    running = False

    # Check for all clusters if they are ready to run
    for cl in cluster.values():
        cl.check_ready_to_run()

    for model in cosmos.scenario.model:
        if model.status == "waiting":
            # This model is waiting

            okay = True

            if model.flow_nested:
                if model.flow_nested.status != "finished":
                    okay = False
                if model.flow_nested.status == "failed":
                    model.status = "failed"
            if model.wave_nested:
                if model.wave_nested.status != "finished":
                    okay = False
                if model.wave_nested.status == "failed":
                    model.status = "failed"
            if model.bw_nested:
                if model.bw_nested.status != "finished":
                    okay = False
                if model.bw_nested.status == "failed":
                    model.status = "failed"
            if model.tide_only_model:
                # We always first want to run the tide only model first!
                if model.tide_only_model.status != "finished":
                    okay = False
                if model.tide_only_model.status == "failed":
                    model.status = "failed"

            if okay and model.cluster:
                # Model appears ready to run, and is member of a cluster
                # if not model.peak_boundary_twl:
                #     #  Peak boundary data has not yet been determined
                #     model.get_peak_boundary_conditions()
                if not cluster[model.cluster].ready:
                    # This model sits in a cluster that is not ready to run
                    okay = False

            if okay:
                waiting_list.append(model)
                priorities.append(model.priority)

        if model.status == "running":
            # There are model(s) running
            running = True

    if waiting_list:
        # Sort waiting list according to prioritization
        waiting_list.sort(key=lambda x: priorities, reverse=True)
        if cosmos.config.run.run_mode == "serial":
            # Only put first job in waiting list
            waiting_list = waiting_list[:1]
            if running:
                # There is already a model running. Wait for it to finish.
                waiting_list = []
        elif cosmos.config.run.run_mode == "parallel":
            # Put all jobs at certain priority level in waiting list
            waiting_list = waiting_list[:]

    return waiting_list
