"""HurryWave model integration for CoSMoS.

Handles reading, pre-processing, execution, and post-processing of HurryWave
spectral wave models within the CoSMoS forecast framework.
"""

import os
import platform
from pathlib import Path

import cht_utils.fileops as fo
import pandas as pd
import xarray as xr
from cht_nesting import nest1

# from cht_utils.misc_tools import dict2yaml
from hydromt_hurrywave import HurrywaveModel

from .cosmos import cosmos
from .model import Model


def _read_hurrywave_his(file_name: str, parameter: str = "point_hm0") -> "pd.DataFrame":
    """Read HurryWave history output as DataFrame with station name columns."""
    ds = xr.open_dataset(file_name)
    var = ds[parameter]
    if "station_name" in ds:
        import numpy as np

        names = ds["station_name"].values
        names = [
            (
                s.decode("utf-8").strip()
                if isinstance(s, (bytes, np.bytes_))
                else str(s).strip()
            )
            for s in names
        ]
    else:
        names = [f"station_{i}" for i in range(var.shape[1])]
    df = pd.DataFrame(
        var.values, index=pd.DatetimeIndex(var.time.values), columns=names
    )
    ds.close()
    return df


class CoSMoS_HurryWave(Model):
    """Cosmos class for HurryWave model.

    HurryWave is a computationally efficient third generation spectral wave model, with physics similar to
    those of SWAN and WAVEWATCH III.

    This cosmos class reads HurryWave model data, pre-processes, moves and post-processes HurryWave models.

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
        """Read HurryWave specific model attributes.

        See Also
        ----------
        hydromt_hurrywave
        """
        # Read in the HurryWave model
        self.domain = HurrywaveModel(
            root=os.path.join(self.path, "input"), mode="r+", write_gis=False
        )

    def pre_process(self) -> None:
        """Preprocess HurryWave model.

        - Extract and write wave conditions.
        - Write input file.
        - Write meteo forcing.
        - Add observation points for nested models and observation stations.
        - Optional: make ensemble of models.

        See Also
        ----------
        cht_nesting.nest2
        """
        # Set path temporarily to job path
        pth = self.domain.root.path
        self.domain.root.set(Path(self.job_path))

        # Start and stop times
        self.domain.config.set("tref", cosmos.scenario.ref_date)
        self.domain.config.set("tstart", self.wave_start_time)
        self.domain.config.set("tstop", self.wave_stop_time)
        self.domain.config.set("dtmaxout", cosmos.config.run.dtmax)
        self.domain.config.set("dtmapout", cosmos.config.run.dtmap)
        self.domain.config.set("dtwnd", cosmos.config.run.dtwnd)
        self.domain.config.set("outputformat", "net")

        self.meteo_atmospheric_pressure = False
        self.meteo_precipitation = False

        # Boundary conditions
        if self.wave_nested:
            self.domain.config.set("bspfile", "hurrywave.bsp")
            self.domain.boundary_conditions.forcing = "spectra"
        else:
            self.domain.config.set("bndfile", None)

        # Meteo forcing
        if self.meteo_wind:
            self.write_meteo_input_files(
                "hurrywave", self.domain.config.get("tref"), format="netcdf"
            )
            self.domain.config.set("netamuamvfile", "hurrywave_wind.nc")

        # Spiderweb file
        self.meteo_spiderweb = cosmos.scenario.meteo_spiderweb

        if self.meteo_spiderweb or self.meteo_track and not self.ensemble:
            self.domain.config.set("spwfile", "hurrywave.spw")
            # Spiderweb file given, copy to job folder. Mirrors the SFINCS path —
            # the deterministic model always reads cycle_track_spw_path/storm.spw
            # (a hardcoded ensemble00000.spw used to be picked here when
            # run_ensemble=true, which broke under the per-member layout).
            if self.meteo_spiderweb:
                spwfile = os.path.join(
                    cosmos.scenario.cycle_track_spw_path, self.meteo_spiderweb
                )
            elif self.meteo_track:
                spwfile = os.path.join(
                    cosmos.scenario.cycle_track_spw_path,
                    self.meteo_track.split(".")[0] + ".spw",
                )
            fo.copy_file(spwfile, os.path.join(self.job_path, "hurrywave.spw"))

        if self.ensemble:
            # Copy all spiderwebs to jobs folder
            self.domain.config.set("spwfile", "hurrywave.spw")

        # Make observation points.
        # str() coerces numeric-looking station IDs (e.g. NDBC buoy 42039,
        # parsed as int upstream) so downstream code sees a consistent dtype.
        if self.station:
            for station in self.station:
                if not self.domain.config.get("obsfile"):
                    self.domain.config.set("obsfile", "hurrywave.obs")
                self.domain.observation_points.add_point(
                    station.x, station.y, str(station.name)
                )

        # Add observation points for nested models (Nesting 1)
        if self.nested_wave_models:
            for nested_model in self.nested_wave_models:
                specout = False
                if nested_model.type == "xbeach":
                    specout = True
                    nest1(
                        self.domain,
                        nested_model.domain,
                        option="sp2",
                        obs_point_prefix=nested_model.name,
                    )
                elif nested_model.type == "sfincs":
                    # No sp2 output
                    # The next two lines are already done when reading in sfincs model, right?
                    # nested_model.domain.input.variables.snapwave_bnd = "snapwave.bnd"
                    # nested_model.domain.read_wave_boundary_points()
                    nest1(
                        self.domain,
                        nested_model.domain,
                        obs_point_prefix=nested_model.name,
                    )
                    # nested_model.domain.input.bwvfile = None
                elif nested_model.type == "beware":
                    specout = False
                    nest1(
                        self.domain,
                        nested_model.domain,
                        obs_point_prefix=nested_model.name,
                    )
                else:
                    specout = True
                    nest1(
                        self.domain,
                        nested_model.domain,
                        obs_point_prefix=nested_model.name,
                    )

            if specout:
                if not self.domain.config.get("ospfile"):
                    self.domain.config.set("ospfile", "hurrywave.osp")
                self.domain.observation_points_spectra.write()
                if self.domain.config.get("dtsp2out") == 0.0:
                    self.domain.config.set("dtsp2out", 3600.0)

        if len(self.domain.observation_points.gdf) > 0:
            if not self.domain.config.get("obsfile"):
                self.domain.config.set("obsfile", "hurrywave.obs")
            self.domain.observation_points.write()

        # Make restart file
        # self.get_restart_time() sits in cosmos_model.py
        trst = self.get_restart_time()
        trstsec = (trst - self.domain.config.get("tref")).total_seconds()
        self.domain.config.set("trstout", trstsec)
        self.domain.config.set("dtrstout", 0.0)

        # Get restart file from previous cycle
        if self.wave_restart_file:
            src = os.path.join(self.restart_wave_path, self.wave_restart_file)
            dst = os.path.join(self.job_path, "hurrywave.rst")
            fo.copy_file(src, dst)
            self.domain.config.set("rstfile", "hurrywave.rst")
            self.domain.config.set("tspinup", 0.0)

        # Now write input file (hurrywave.inp)
        self.domain.config.write()

        # Set the path back to the one in cosmos\models\etc.
        self.domain.root.set(pth)

        ### And now prepare the job files ###

        # Copy the correct run script to run_job.py
        pth = os.path.dirname(__file__)
        fo.copy_file(
            os.path.join(pth, "run_hurrywave.py"),
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
            # Make run batch file (only for windows and linux).
            if platform.system() == "Windows":
                batch_file = os.path.join(self.job_path, "run_simulation.bat")
                # Docker or exe?
                if cosmos.config.run.hurrywave_docker:
                    fid = open(batch_file, "w")
                    fid.write("@ echo off\n")
                    fid.write(
                        f"docker pull {cosmos.config.executables.hurrywave_docker_image}\n"
                    )
                    fid.write(
                        f"docker run --rm -it --gpus all -v %cd%:/data {cosmos.config.executables.hurrywave_docker_image}\n"
                    )
                    fid.close()
                else:
                    fid = open(batch_file, "w")
                    fid.write("@ echo off\n")
                    exe_path = os.path.join(
                        cosmos.config.executables.hurrywave_path, "hurrywave.exe"
                    )
                    fid.write(exe_path + "\n")
                    fid.close()
            elif platform.system() == "Linux":
                batch_file = os.path.join(self.job_path, "run_simulation.sh")
                fid = open(batch_file, "w")
                fid.write("unset LD_LIBRARY_PATH\n")
                fid.write(
                    "export PATH="
                    + cosmos.config.executables.hurrywave_path
                    + ":$PATH\n"
                )
                fid.write(
                    os.path.join(
                        cosmos.config.executables.hurrywave_path, "hurrywave\n"
                    )
                )
                fid.close()

        if cosmos.config.run.run_mode == "cloud":
            # Set workflow names
            if self.ensemble:
                self.workflow_name = "hurrywave-ensemble-workflow"
            else:
                self.workflow_name = "hurrywave-deterministic-workflow"

    def move(self) -> None:
        job_path = self.job_path
        output_path = self.cycle_output_path
        input_path = self.cycle_input_path
        restart_path = self.restart_wave_path

        # Output
        fo.move_file(os.path.join(job_path, "hurrywave_map.nc"), output_path)
        fo.move_file(os.path.join(job_path, "hurrywave_his.nc"), output_path)
        fo.move_file(os.path.join(job_path, "hurrywave_sp2.nc"), output_path)
        fo.move_file(os.path.join(job_path, "*.txt"), output_path)

        # Restart file used in simulation
        fo.move_file(os.path.join(job_path, "hurrywave.rst"), input_path)
        # Restart files created during simulation
        fo.move_file(os.path.join(self.job_path, "hurrywave.*.rst"), restart_path)
        # Input
        fo.move_file(os.path.join(job_path, "*.*"), input_path)

    def post_process(self) -> None:
        # Extract wave time series
        # input_path  = self.cycle_input_path
        output_path = self.cycle_output_path
        post_path = self.cycle_post_path
        # if not self.domain.input.variables.tref:
        #     # This model has been run before. The model instance has not data on tref, obs points etc.
        #     self.domain.read_input_file(os.path.join(input_path, "hurrywave.inp"))
        #     self.domain.read_observation_points()
        if self.station:
            # Read in data for all stations
            his_file = os.path.join(output_path, "hurrywave_his.nc")
            data = {}
            if self.ensemble:
                prcs = [0.05, 0.5, 0.95]
                for i, v in enumerate(prcs):
                    data["hm0_" + str(round(v * 100))] = _read_hurrywave_his(
                        his_file,
                        parameter="point_hm0_" + str(round(v * 100)),
                    )
                    data["tp_" + str(round(v * 100))] = _read_hurrywave_his(
                        his_file,
                        parameter="point_tp_" + str(round(v * 100)),
                    )
            else:
                data["hm0"] = _read_hurrywave_his(his_file, parameter="point_hm0")
                data["tp"] = _read_hurrywave_his(his_file, parameter="point_tp")

            # Loop through stations
            for station in self.station:
                if self.ensemble:
                    indx = data["hm0_" + str(round(prcs[0] * 100))].index
                    df = pd.DataFrame(index=indx)
                    df.index.name = "date_time"
                    for i, v in enumerate(prcs):
                        df["Hm0_" + str(round(v * 100))] = data[
                            "hm0_" + str(round(v * 100))
                        ][station.name]
                        df["Tp_" + str(round(v * 100))] = data[
                            "tp_" + str(round(v * 100))
                        ][station.name]

                else:
                    df = pd.DataFrame(index=data["hm0"].index)
                    df.index.name = "date_time"
                    df["Hm0"] = data["hm0"][station.name]
                    df["Tp"] = data["tp"][station.name]

                # Write csv file for station
                file_name = os.path.join(post_path, "waves." + station.name + ".csv")
                df.to_csv(
                    file_name, date_format="%Y-%m-%dT%H:%M:%S", float_format="%.3f"
                )
