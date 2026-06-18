"""XBeach model integration for CoSMoS.

Handles reading, pre-processing, execution, and post-processing of XBeach
nearshore morphodynamic models within the CoSMoS forecast framework.
"""

import datetime
import os
import platform

import cht_utils.fileops as fo
import pandas as pd
import toml
import xarray as xr
from cht_xbeach.xbeach import XBeach
from cht_xbeach.xbeach_output_morphology import Map

from .cosmos import cosmos
from .model import Model


class CoSMoS_XBeach(Model):
    """Cosmos class for XBeach model.

    XBeach (XB) is a physics-based nearshore model that solves the horizontal equations for flow,
    wave propagation, sediment transport, and changes in bathymetry (see also https://xbeach.readthedocs.io/en/latest/).

    This cosmos class reads XBeach model data, pre-processes, moves and post-processes XBeach models.

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
        """Read XBeach specific model attributes.

        See Also
        ----------
        cht_xbeach.xbeach
        """

        # Now read in the domain data
        input_file = os.path.join(self.path, "input", "params.txt")
        self.domain = XBeach(input_file=input_file, get_boundary_coordinates=False)

        mdl_dict = toml.load(self.file_name)
        if "flow_nesting_points" in mdl_dict:
            self.flow_nesting_points = mdl_dict["flow_nesting_points"]
            # remove the default found boundary locations based on the tideloc and xbeach routine
            self.domain.flow_boundary_point[len(self.flow_nesting_points) :] = []
            for ipnt, pnt in enumerate(self.flow_nesting_points):
                self.domain.flow_boundary_point[ipnt].name = str(ipnt + 1).zfill(4)
                self.domain.flow_boundary_point[ipnt].geometry.x = pnt[0]
                self.domain.flow_boundary_point[ipnt].geometry.y = pnt[1]
                # TODO change tideloc in the params as a function of the new boundary points?

        if "wave_nesting_point" in mdl_dict:
            self.wave_nesting_point = mdl_dict["wave_nesting_point"]
            self.domain.wave_boundary_point[0].name = str(1).zfill(4)
            self.domain.wave_boundary_point[0].geometry.x = self.wave_nesting_point[0]
            self.domain.wave_boundary_point[0].geometry.y = self.wave_nesting_point[1]

        if "zb_deshoal" in mdl_dict:
            self.domain.zb_deshoal = mdl_dict["zb_deshoal"]

        # Copy some attributes to the model domain (needed for nesting)
        self.domain.crs = self.crs
        self.domain.type = self.type
        self.domain.name = self.name
        self.domain.runid = self.runid

    def pre_process(self) -> None:
        """Preprocess XBeach model.

        - Extract and write water level and wave conditions.
        - Optional: only run XBeach for peak conditions.
        - Write input file.

        See Also
        ----------
        cht_nesting.nest2
        """

        # First generate input that is identical for all members

        # Set path temporarily to job path
        pth = self.domain.path
        self.domain.path = self.job_path

        # Start and stop times
        self.domain.tref = self.flow_start_time
        self.domain.tstop = self.flow_stop_time
        self.domain.params["tstop"] = (
            self.flow_stop_time - self.flow_start_time
        ).total_seconds()

        t0 = None
        t1 = None
        if self.peak_boundary_time:
            # Round to nearest hour
            h0 = self.peak_boundary_time.hour
            tpeak = self.peak_boundary_time.replace(
                microsecond=0, second=0, minute=0, hour=h0
            )
            t0 = tpeak - 12 * datetime.timedelta(hours=1)
            t1 = tpeak + 12 * datetime.timedelta(hours=1)
            t0 = max(t0, self.flow_start_time)
            t1 = min(t1, self.flow_stop_time)
            self.domain.tref = t0
            self.domain.tstop = t1
            self.domain.params["tstop"] = (t1 - t0).total_seconds()
            self.domain.params["tintg"] = (t1 - t0).total_seconds()
            self.domain.params["tintm"] = (t1 - t0).total_seconds()

        # Boundary conditions
        if self.flow_nested:
            pass

        # Boundary conditions
        if self.wave_nested:
            # define whether you want to use jonstable or sp2-files as boundary conditions
            option = "timeseries"

            if option == "sp2":
                self.domain.params["bcfile"] = "sp2list.txt"
                self.domain.params["instat"] = 5
            elif option == "timeseries":
                self.domain.params["bcfile"] = "jonswap.txt"
                self.domain.params["wbctype"] = "jonstable"

        # Now write input file (params.txt)
        params_file = os.path.join(self.job_path, "params.txt")
        self.domain.params.tofile(filename=params_file)

        # And now prepare the job files

        # Copy the correct run script to run_job.py
        pth = os.path.dirname(__file__)
        fo.copy_file(
            os.path.join(pth, "run_xbeach.py"),
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
                batch_file = os.path.join(self.job_path, "run_simulation.bat")
                fid = open(batch_file, "w")
                fid.write("@ echo off\n")
                fid.write(
                    "set xbeachdir=" + cosmos.config.executables.xbeach_path + "\n"
                )
                fid.write('set mpidir="c:\\Program Files\\MPICH2\\bin"\n')
                fid.write("set PATH=%xbeachdir%;%PATH%\n")
                fid.write("set PATH=%mpidir%;%PATH%\n")
                fid.write("mpiexec.exe -n 5 -mapall %xbeachdir%\\xbeach.exe\n")
                fid.write("del q_*\n")
                fid.write("del E_*\n")
                fid.close()
            else:
                batch_file = os.path.join(self.job_path, "run_simulation.sh")
                fid = open(batch_file, "w")
                fid.write("#!/bin/bash\n")
                fid.write("unset LD_LIBRARY_PATH\n")
                fid.write(
                    "export PATH=$PATH:" + cosmos.config.executables.xbeach_path + "\n"
                )
                fid.write("export PATH=$PATH:/usr/lib/mpich/bin\n")
                fid.write("mpirun -np 5 xbeach\n")
                fid.write("rm q_*\n")
                fid.write("rm E_*\n")
                fid.close()

        if cosmos.config.run.run_mode == "cloud":
            # Set workflow names
            if self.ensemble:
                self.workflow_name = "xbeach-ensemble-workflow"
            else:
                self.workflow_name = "xbeach-deterministic-workflow"

        # Set the path back to the one in cosmos\models\etc.
        self.domain.path = pth

    def move(self) -> None:
        """Move XBeach model input and output files."""
        # Move files from job folder to archive folder

        # First clear archive folder

        job_path = self.job_path
        output_path = self.cycle_output_path
        input_path = self.cycle_input_path

        # Output
        fo.move_file(os.path.join(job_path, "*.nc"), output_path)
        fo.move_file(os.path.join(job_path, "finished.txt"), output_path)

        # Input
        fo.move_file(os.path.join(job_path, "*.*"), input_path)

    def post_process(self) -> None:
        """Post-process XBeach output: generate Sallenger regimes."""

        output_path = self.cycle_output_path
        post_path = self.cycle_post_path

        try:
            # read xbeach output
            output_file = os.path.join(output_path, "xboutput.nc")
            dt = xr.open_dataset(output_file)
        except Exception:
            print("ERROR while making xbeach regimes")
            return

        # get Sallenger regimes
        x_grid = dt["globalx"].values
        y_grid = dt["globaly"].values
        zsmean = dt["zs_mean"].values
        zsmax = dt["zs_max"].values
        zb0 = dt["zb"][0, :, :].values  # todo: check if this is needed
        zbend = dt["zb"][-1, :, :].values

        # make object for 2D XBeach output
        map2D = Map(
            x2D=x_grid, y2D=y_grid, zb02D=zb0, zbend2D=zbend, plot_dir=output_path
        )
        # get Sallenger regimes
        # 1) still need to fix something for MHW, for now a fixed value
        # 2) for now no figures are generated, takes too long to do operationally, but would be nice to include
        x_crest, y_crest, regimenos, erosionregimenos = (
            map2D.alongshore_sallenger_regimes(
                zsmean, zsmax, MHW=0.25, plot_transects=False, plot_map=False
            )
        )
        df = pd.DataFrame(
            {
                "X": x_crest,
                "Y": y_crest,
                "sallregime": regimenos,
                "erosionregime": erosionregimenos,
            }
        )
        # Save DataFrame to CSV
        file_name = os.path.join(post_path, "Sallengerregimes.csv")
        df.to_csv(file_name, index=False)
