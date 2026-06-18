"""BEWARE model integration for CoSMoS.

Handles reading, pre-processing, execution, and post-processing of BEWARE
(XBeach-based meta-model) for nearshore wave heights and total water levels
at reef-lined coasts.
"""

import os
import platform

# from pyproj import CRS
# from pyproj import Transformer
import shutil

import cht_utils.fileops as fo
import pandas as pd
from cht_beware.beware import BEWARE
from cht_utils.fileops import find_replace

from .cosmos import cosmos
from .model import Model


class CoSMoS_BEWARE(Model):
    """Cosmos class for BEWARE model.

    BEWARE is a meta-model based on XBeach for predicting nearshore wave heights and total water levels at reef-lined coasts.

    This cosmos class reads BEWARE model data, pre-processes, moves and post-processes BEWARE models.

    Parameters
    ----------
    Model : class
        Generic cosmos model attributes

    See Also
    ----------
    cosmos.scenario.Scenario
    cosmos.model_loop.ModelLoop
    cosmos.model.Model
    """

    def read_model_specific(self) -> None:
        """Read BEWARE specific model attributes.

        See Also
        ----------
        cht_beware.beware
        """
        # Read in the BEWARE model
        input_file = os.path.join(self.path, "input", "beware.inp")
        self.domain = BEWARE(input_file)
        self.domain.crs = self.crs
        self.domain.type = self.type
        self.domain.name = self.name
        self.domain.runid = self.runid

    def pre_process(self) -> None:
        """Preprocess BEWARE model.

        - Extract and write wave and water level conditions.
        - Write input file.
        - Optional: make ensemble of models.

        See Also
        ----------
        cht_nesting.nest2
        """

        # Set path temporarily to job path
        pth = self.domain.path
        self.domain.path = self.job_path
        self.domain.input.tref = cosmos.scenario.ref_date
        self.domain.input.tstart = self.flow_start_time
        self.domain.input.tstop = self.flow_stop_time

        # Boundary conditions
        if self.flow_nested:
            # The actual nesting occurs in the run_job.py file
            self.domain.input.bzsfile = "beware.bzs"
            self.domain.input.bndfile = "beware.bnd"
            self.domain.write_flow_boundary_points()

        if self.wave and self.wave_nested:
            self.domain.input.btpfile = "beware.btp"
            self.domain.input.bhsfile = "beware.bhs"
            self.domain.input.bwvfile = "beware.bwv"
            self.domain.write_wave_boundary_points()

        # Now write input file (sfincs.inp)
        self.domain.write_input_file()
        # Set the path back to the one in cosmos\models\etc.
        self.domain.path = pth

        # And now prepare the job files

        # Copy the correct run script to run_job.py
        pth = os.path.dirname(__file__)
        fo.copy_file(
            os.path.join(pth, "run_beware.py"),
            os.path.join(self.job_path, "run_job_2.py"),
        )

        # Write config.yml file to be used in job
        self.write_config_yml()

        if self.ensemble:
            # Write ensemble members to file
            with open(os.path.join(self.job_path, "ensemble_members.txt"), "w") as f:
                for member in cosmos.scenario.ensemble_names:
                    f.write(member + "\n")

        if cosmos.config.run.run_mode != "cloud":
            # Make run batch file (windows or linux)
            if platform.system() == "Windows":
                src = os.path.join(cosmos.config.executables.beware_path, "run_bw.bas")
                batch_file = os.path.join(self.job_path, "run_simulation.bat")
                shutil.copyfile(src, batch_file)
                find_replace(
                    batch_file, "EXEPATHKEY", cosmos.config.executables.beware_path
                )
            else:
                # Something like this
                src = os.path.join(cosmos.config.executables.beware_path, "run_bw.sh")
                batch_file = os.path.join(self.job_path, "run_simulation.sh")
                shutil.copyfile(src, batch_file)
                find_replace(
                    batch_file, "EXEPATHKEY", cosmos.config.executables.beware_path
                )

        if cosmos.config.run.run_mode == "cloud":
            # Set workflow names
            if self.ensemble:
                self.workflow_name = "beware-ensemble-workflow"
            else:
                self.workflow_name = "beware-deterministic-workflow"

    def move(self) -> None:
        """Move BEWARE model input and output files."""
        # Move files from job folder to archive folder

        # First clear archive folder

        job_path = self.job_path
        output_path = self.cycle_output_path
        input_path = self.cycle_input_path
        fo.move_file(os.path.join(job_path, "beware_his.nc"), output_path)

        # Input
        fo.move_file(os.path.join(job_path, "*.*"), input_path)

    def post_process(self) -> None:
        """Post-process BEWARE output: generate (probabilistic) runup timeseries.

        See Also
        ----------
        cht_utils.prob_maps
        """
        # Post-processing occurs in cosmos_webviewer.py
        from cht_utils.fileio.json_js import write_csv_js

        output_path = self.cycle_output_path
        post_path = self.cycle_post_path
        web_path = os.path.join(
            cosmos.webviewer.path,
            "data",
            cosmos.scenario.name,
            cosmos.cycle_string,
            "timeseries",
        )
        os.makedirs(web_path, exist_ok=True)

        if self.ensemble:
            self.domain.read_data(
                os.path.join(output_path, "beware_his.nc"), prcs=[5, 50, 95]
            )

            for ip in range(len(self.domain.filename)):
                d = {
                    "WL": self.domain.WL[ip, :, 0],
                    "Setup": self.domain.R2_setup[ip, :, 0],
                    "Swash": self.domain.swash[ip, :, 0],
                    "Runup": self.domain.R2[ip, :, 0],
                    "Setup_5": self.domain.R2_setup_prc["5"][ip, :],
                    "Setup_50": self.domain.R2_setup_prc["50"][ip, :],
                    "Setup_95": self.domain.R2_setup_prc["95"][ip, :],
                    "Runup_5": self.domain.R2_prc["5"][ip, :],
                    "Runup_50": self.domain.R2_prc["50"][ip, :],
                    "Runup_95": self.domain.R2_prc["95"][ip, :],
                }

                v = pd.DataFrame(
                    data=d,
                    index=pd.date_range(
                        self.domain.input.tstart,
                        periods=len(self.domain.swash[ip, :]),
                        freq="0.5H",
                    ),
                )
                file_name = os.path.join(
                    post_path,
                    "extreme_runup_height." + str(self.domain.filename[ip]) + ".csv",
                )
                v.index.name = "date_time"
                s = v.to_csv(
                    file_name, date_format="%Y-%m-%dT%H:%M:%S", float_format="%.3f"
                )
                s = v.to_csv(
                    path_or_buf=None,
                    date_format="%Y-%m-%dT%H:%M:%S",
                    float_format="%.3f",
                    header=False,
                    index_label="datetime",
                )
                file_name = os.path.join(
                    web_path,
                    "extreme_runup_height."
                    + self.name
                    + "."
                    + str(self.domain.filename[ip])
                    + ".csv.js",
                )
                write_csv_js(
                    file_name,
                    s,
                    "var csv = `date_time,wl,setup,swash,runup, setup_5, setup_50, setup_95, runup_5, runup_50, runup_95",
                )

        else:
            self.domain.read_data(os.path.join(output_path, "beware_his.nc"))
            for ip in range(len(self.domain.filename)):
                d = {
                    "WL": self.domain.WL[ip, :],
                    "Setup": self.domain.R2_setup[ip, :],
                    "Swash": self.domain.swash[ip, :],
                    "Runup": self.domain.R2[ip, :],
                }

                v = pd.DataFrame(
                    data=d,
                    index=pd.date_range(
                        self.domain.input.tstart,
                        periods=len(self.domain.swash[ip, :]),
                        freq="0.5H",
                    ),
                )
                file_name = os.path.join(
                    post_path,
                    "extreme_runup_height." + str(self.domain.filename[ip]) + ".csv",
                )
                v.index.name = "date_time"
                s = v.to_csv(
                    file_name,
                    date_format="%Y-%m-%dT%H:%M:%S",
                    float_format="%.3f",
                    header=False,
                    index_label="datetime",
                )

                s = v.to_csv(
                    path_or_buf=None,
                    date_format="%Y-%m-%dT%H:%M:%S",
                    float_format="%.3f",
                    header=False,
                    index_label="datetime",
                )
                file_name = os.path.join(
                    web_path,
                    "extreme_runup_height."
                    + self.name
                    + "."
                    + str(self.domain.filename[ip])
                    + ".csv.js",
                )
                write_csv_js(file_name, s, "var csv = `date_time,wl,setup,swash,runup")

        # output_path = self.cycle_output_path
        # post_path   = self.cycle_post_path

        # self.domain.read_data(os.path.join(output_path, "BW_output.nc"))
        # self.domain.write_to_geojson(output_path, cosmos.scenario.name)
        # # Time series
        # self.domain.write_to_csv(post_path, cosmos.scenario.name)
