"""SFINCS model integration for CoSMoS.

Handles reading, pre-processing, execution, and post-processing of SFINCS
(Super-Fast Inundation of CoastS) flood models within the CoSMoS forecast framework.
"""

import os
from pathlib import Path
# import numpy as np
import platform
import copy
import geopandas as gpd

import cht_utils.fileops as fo
import pandas as pd
import xarray as xr
from cht_nesting import nest1
from hydromt_sfincs import SfincsModel

from .cosmos import cosmos
from .model import Model


def _read_sfincs_his(
    file_name: str, parameter: str = "point_zs", ensemble_member: int = None
) -> "pd.DataFrame":
    """Read SFINCS history output as DataFrame with station name columns."""
    ds = xr.open_dataset(file_name)
    var = ds[parameter]
    # merge_nc_his (cht_utils) names the ensemble dim "ensemble"; some older
    # writers used "ensemble_member". Accept either so post-processing works
    # regardless of which produced the merged his file.
    if ensemble_member is not None:
        for ens_dim in ("ensemble", "ensemble_member"):
            if ens_dim in var.dims:
                var = var.isel({ens_dim: ensemble_member})
                break
    # Get station names
    stations = ds.station_name.values
    names = []
    for ist, st in enumerate(stations):
        names.append(st.decode().strip())
    df = pd.DataFrame(
        var.values, index=pd.DatetimeIndex(var.time.values), columns=names
    )
    ds.close()
    return df


class CoSMoS_SFINCS(Model):
    """Cosmos class for SFINCS model.

    SFINCS (Super-Fast Inundation of CoastS) is a reduced-complexity model capable of simulating compound flooding
    with a high computational efficiency balanced with an adequate accuracy (see also https://sfincs.readthedocs.io/en/latest/).

    This cosmos class reads SFINCS  model data, pre-processes, moves and post-processes SFINCS models.

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
        """Read SFINCS specific model attributes.

        See Also
        ----------
        hydromt_sfincs.sfincs
        """
        # Read in the SFINCS model
        self.domain = SfincsModel(
            root=os.path.join(self.path, "input"), mode="r+", write_gis=False
        )
        # # Set one (random) keyword in model before switch to rw+ mode
        # self.domain.config.set("outputformat", "net")
        # # Now switch to rw+ mode to be able to write input files in pre_process step
        # self.domain.root.mode = "r+"

    def pre_process(self) -> None:
        """Preprocess SFINCS model.

        - Extract and write water level and wave conditions.
        - Write input file.
        - Write meteo forcing.
        - Add observation points for nested models and observation stations.
        - Optional: make ensemble of models.

        See Also
        ----------
        cht_nesting.nest2
        """
        # Set path temporarily to job path
        self.domain.config.read()
        pth = self.domain.root.path
        self.domain.root.set(Path(self.job_path))

        # Set start and stop times
        self.domain.config.update(
            {
                "tref": cosmos.scenario.ref_date,
                "tstart": self.flow_start_time,
                "tstop": self.flow_stop_time,
                "dthisout": cosmos.config.run.dthis,
                "dtmapout": cosmos.config.run.dtmap,
                "dtmaxout": cosmos.config.run.dtmax,
                "dtwnd": cosmos.config.run.dtwnd,
                "outputformat": "net",
            }
        )

        if self.role == "floodmap":
            # We need to make a flood map, but not max water levels
            self.make_flood_map = True
            self.make_water_level_map = False
            self.meteo_precipitation = (
                True  # Always use meteo precipitation in flood map mode
            )
        elif self.role == "large_scale":
            # We need to make max water levels, but not a flood map
            self.make_flood_map = False
            self.make_water_level_map = True
            self.meteo_precipitation = (
                False  # Never use meteo precipitation in large scale mode
            )
        elif self.role == "tide_only":
            # We need to make max water levels, but not a flood map
            self.make_flood_map = False
            self.make_water_level_map = False
            self.meteo_precipitation = (
                False  # Never use meteo precipitation in large scale mode
            )
        else:
            # Generic model, use settings from config file
            pass

        if cosmos.config.run.event_mode == "tsunami":
            # Store velocity in output file. Use for nesting, and later also damage assessment ?
            self.domain.config.set("storevel", 1)
            self.domain.config.set("storevelmax", 1)

        # Turn on bathtub mode when this is a flood map simulation
        bathtub = False
        if cosmos.config.run.bathtub and self.make_flood_map:
            bathtub = True
            self.domain.config.set("bathtub", 1, skip_validation=True)
            self.domain.config.set("bathtub_dt", 600.0, skip_validation=True)
            self.domain.config.set(
                "bathtub_fachs", cosmos.config.run.bathtub_fachs, skip_validation=True
            )

        # Turn on viscosity in all SFINCS models
        self.domain.config.set("viscosity", 1)
        self.domain.config.set("nuvisc", 0.01)

        # Limit maximum initial water level (to get rid of excess water from previous events)
        if cosmos.config.run.clear_zs_ini:
            self.domain.config.set("zsinimax", self.zs_ini_max, skip_validation=True)

        # Add some evaporation (same reason as above)
        self.domain.config.set("qeva", 10.0 / 24, skip_validation=True)  # 10 mm/day

        # Temporary fix for SFINCS bug
        if self.domain.config.get("krfile") is not None:
            self.domain.config.set("ksfile", self.domain.config.get("krfile"))

        if self.flow_nested:
            self.domain.config.set("pavbnd", -999.0)

        # Make observation points
        stations_added = False

        if self.station:

            # str() because some observation_points names come back as int
            # (numeric-looking IDs like NDBC buoy 42039 are parsed as numbers
            # somewhere upstream), and the isin() dedup below needs both sides
            # to share a dtype to actually match.
            existing_stations = {str(n) for n in self.domain.observation_points.list_names}

            # Create full GeoDataFrame from all stations.
            names, xs, ys = zip(*[(str(s.name), s.x, s.y) for s in self.station])

            gdf = gpd.GeoDataFrame(
                {
                    "name": names,
                },
                geometry=gpd.points_from_xy(xs, ys),
                crs=self.crs,
            )

            # Remove stations that already exist
            gdf = gdf[~gdf["name"].isin(existing_stations)]

            if not gdf.empty:
                try:
                    self.domain.observation_points.set(gdf, merge=True, skip_validation=True)
                    stations_added = True
                except Exception as e:
                    print(f"Error adding observation points batch: {e}")
            # self.domain.config.set("obsfile", "sfincs.obs")

        # Add observation points for nested models (Nesting 1)
        if self.nested_flow_models:
            # if not self.domain.config.get("obsfile"):
            #     self.domain.config.set("obsfile", "sfincs.obs")

            for nested_model in self.nested_flow_models:
                nest1(
                    self.domain, nested_model.domain, obs_point_prefix=nested_model.name
                )
                stations_added = True

        if stations_added > 0:
            # Stations were added
            if not self.domain.config.get("obsfile"):
                self.domain.config.set("obsfile", "sfincs.obs")
            self.domain.observation_points.write()

        # Make restart file
        if not bathtub:
            # self.get_restart_time() sits in cosmos_model.py
            trst = self.get_restart_time()
            # # If we play catch up (i.e. we may have missed one or more cycles),
            # # then we write output at the last meteo analysis time.
            # # However, if we want the next cycle to be the current cycle + interval, trstsec must be the
            # # minimum of these to times.
            # # There are three options:
            # # 1) Forecast mode (i.e. the meteo dataset has a last_analysis_time)
            # #   a) With catch up    -> trst = last analysis time
            # #   b) Without catch up -> trst = min(next cycle time + interval, last analysis time)
            # # 2) Hindcast mode      -> trst = stop time of simulation

            # if self.meteo_dataset.last_analysis_time:
            #     # 1) Forecast mode
            #     if cosmos.config.run.catch_up:
            #         # a) With catch up
            #         trst = self.meteo_dataset.last_analysis_time.replace(tzinfo=None)
            #     else:
            #         # b) Without catch up
            #         trst = cosmos.next_cycle_time.replace(tzinfo=None)
            #         trst = min(trst, self.meteo_dataset.last_analysis_time.replace(tzinfo=None))
            # else:
            #     # 2) Hindcast mode
            #     trst = cosmos.next_cycle_time.replace(tzinfo=None)

            trstsec = (trst - self.domain.config.get("tref")).total_seconds()

            self.domain.config.set("trstout", trstsec)
            self.domain.config.set("dtrstout", 0.0, skip_validation=True)

        else:
            self.domain.config.set("trstout", 0.0)
            self.domain.config.set("dtrstout", 0.0, skip_validation=True)

        # Get restart file from previous cycle
        if self.flow_restart_file and not bathtub:
            src = os.path.join(self.restart_flow_path, self.flow_restart_file)
            dst = os.path.join(self.job_path, "sfincs.rst")
            fo.copy_file(src, dst)
            self.domain.config.set("rstfile", "sfincs.rst")
            self.domain.config.set("tspinup", 0.0)

        if cosmos.config.run.event_mode == "tsunami":
            # Only make tsunami for large model
            if not self.flow_nested:
                # Interpolate the data to the mesh
                self.domain.initial_conditions.create(cosmos.tsunami.data["dZ"])
                # Write the initial conditions to the SFINCS input file
                self.domain.config.set("ncinifile", "sfincs_ini.nc")
                self.domain.initial_conditions.write()

        # Boundary conditions
        if self.flow_nested:
            # The actual nesting occurs in the run_job.py file
            self.domain.config.set("bzsfile", "sfincs.bzs")

        elif self.domain.config.get("bcafile"):
            # Get boundary conditions from astronomic components!
            pass

        if self.wave_nested:
            # The actual nesting occurs in the run_job.py file
            self.domain.config.set("snapwave_bhsfile", "snapwave.bhs")
            self.domain.config.set("snapwave_btpfile", "snapwave.btp")
            self.domain.config.set("snapwave_bwdfile", "snapwave.bwd")
            self.domain.config.set("snapwave_bdsfile", "snapwave.bds")

        # If SFINCS nested in Hurrywave for SNAPWAVE setup, separately run BEWARE nesting for LF waves
        if self.bw_nested:
            # The actual nesting occurs in the run_job.py file
            self.domain.config.set("wfpfile", "sfincs.wfp")
            self.domain.config.set("whifile", "sfincs.whi")
            self.domain.config.set("wtifile", "sfincs.wti")

        # Meteo forcing
        if (
            self.meteo_wind
            or self.meteo_atmospheric_pressure
            or self.meteo_precipitation
        ):
            # Write netcdf meteo forcing files
            self.write_meteo_input_files(
                "sfincs", self.domain.config.get("tref"), format="netcdf"
            )
            if self.meteo_wind:
                self.domain.config.set("netamuamvfile", "sfincs_wind.nc")
            if self.meteo_atmospheric_pressure:
                self.domain.config.set("netampfile", "sfincs_barometric_pressure.nc")
                self.domain.config.set("baro", 1)
            if self.meteo_precipitation:
                self.domain.config.set("netamprfile", "sfincs_precipitation.nc")
            else:
                self.domain.config.set("scsfile", None)

        # Spiderweb file (only when not tide only model!)
        if self.role != "tide_only":
            self.meteo_spiderweb = cosmos.scenario.meteo_spiderweb

        if self.meteo_spiderweb or self.meteo_track and not self.ensemble:
            self.domain.config.set("spwfile", "sfincs.spw")
            # Spiderweb file given, copy to job folder
            if self.meteo_spiderweb:
                spwfile = os.path.join(
                    cosmos.scenario.cycle_track_spw_path, self.meteo_spiderweb
                )
            elif self.meteo_track:
                spwfile = os.path.join(
                    cosmos.scenario.cycle_track_spw_path,
                    self.meteo_track.split(".")[0] + ".spw",
                )
            fo.copy_file(spwfile, os.path.join(self.job_path, "sfincs.spw"))
            self.domain.config.set("baro", 1)
            if self.crs.is_projected:
                self.domain.config.set("utmzone", self.crs.utm_zone)
            if cosmos.config.run.use_spw_precip and self.make_flood_map:
                # This must me an overland flood model
                self.domain.config.set("usespwprecip", 1)
                self.make_precipitation_map = True
            else:
                self.domain.config.set("usespwprecip", 0)

        if self.ensemble:
            # Use spiderweb from ensemble
            self.domain.config.set("spwfile", "sfincs.spw")
            if self.crs.is_projected:
                self.domain.config.set("utmzone", self.crs.utm_zone)

        # Now write input file (sfincs.inp)
        self.domain.config.write()

        # Finally set the path back to the one in model_database
        self.domain.root.set(pth)

        # And now prepare the job files

        # Copy the correct run script to run_job.py
        pth = os.path.dirname(__file__)
        # Keep calling it run_job_2.py for now, otherwise the cloud workflow will not work
        fo.copy_file(
            os.path.join(pth, "run_sfincs.py"),
            os.path.join(self.job_path, "run_job_2.py"),
        )

        # If there is an associated tide_only model, copy its map file to the job folder. It is used
        # to make storm surge maps.
        if self.tide_only_model:
            src = os.path.join(self.tide_only_model.cycle_output_path, "sfincs_map.nc")
            dst = os.path.join(self.job_path, "sfincs_map_tide_only.nc")
            fo.copy_file(src, dst)

        # Write config.yml file to be used in job
        self.write_config_yml()

        if self.ensemble:
            # Write ensemble members to file
            with open(os.path.join(self.job_path, "ensemble_members.txt"), "w") as f:
                for member in cosmos.scenario.ensemble_names:
                    f.write(member + "\n")

        # Write run_simulation.bat or .sh file
        if cosmos.config.run.run_mode != "cloud":
            # Make run batch file (only for windows and linux)
            if platform.system() == "Windows":
                batch_file = os.path.join(self.job_path, "run_simulation.bat")
                # Docker or exe? We do not run docker in bathtub mode, as it is slower.
                if cosmos.config.run.sfincs_docker and not bathtub:
                    fid = open(batch_file, "w")
                    fid.write("@ echo off\n")
                    fid.write(
                        f"docker pull {cosmos.config.executables.sfincs_docker_image}\n"
                    )
                    fid.write(
                        f"docker run --rm -it --gpus all -v %cd%:/data {cosmos.config.executables.sfincs_docker_image}\n"
                    )
                    fid.close()
                else:
                    fid = open(batch_file, "w")
                    fid.write("@ echo off\n")
                    fid.write(f"set OMP_NUM_THREADS={self.omp_num_threads}\n")
                    exe_path = os.path.join(
                        cosmos.config.executables.sfincs_path, "sfincs.exe"
                    )
                    fid.write(exe_path + "\n")
                    fid.close()
            elif platform.system() == "Linux":
                batch_file = os.path.join(self.job_path, "run_simulation.sh")
                fid = open(batch_file, "w")
                fid.write("#!/bin/bash\n")
                fid.write("unset LD_LIBRARY_PATH\n")
                fid.write(f"export OMP_NUM_THREADS={self.omp_num_threads}\n")
                fid.write(
                    "export PATH=" + cosmos.config.executables.sfincs_path + ":$PATH\n"
                )
                fid.write(
                    os.path.join(cosmos.config.executables.sfincs_path, "sfincs\n")
                )
                fid.close()

        if cosmos.config.run.run_mode == "cloud":
            # Set workflow names
            if self.ensemble:
                self.workflow_name = "sfincs-ensemble-workflow"
            else:
                self.workflow_name = "sfincs-deterministic-workflow"

    def move(self) -> None:
        job_path = self.job_path
        output_path = self.cycle_output_path
        input_path = self.cycle_input_path
        restart_path = self.restart_flow_path
        # Output
        fo.move_file(os.path.join(job_path, "sfincs_map.nc"), output_path)
        fo.move_file(os.path.join(job_path, "sfincs_his.nc"), output_path)
        fo.move_file(os.path.join(job_path, "sfincs.log"), output_path)
        # Restart file used in simulation
        fo.move_file(os.path.join(self.job_path, "sfincs.rst"), input_path)
        # Restart files created during simulation
        fo.move_file(os.path.join(self.job_path, "*.rst"), restart_path)
        # Input (all the rest)
        fo.move_file(os.path.join(self.job_path, "*.*"), input_path)

    def post_process(self) -> None:
        # Extract water levels
        # if self.role == "tide_only":
        #     # No post processing for tide only model
        #     return
        output_path = self.cycle_output_path
        post_path = self.cycle_post_path
        his_file_name = os.path.join(output_path, "sfincs_his.nc")
        if self.station:
            # Read in data for all stations
            data = {}
            if self.ensemble:
                prcs = [0.0, 0.50, 1.0]
                for i, v in enumerate(prcs):
                    data["wl"] = _read_sfincs_his(
                        his_file_name, ensemble_member=0, parameter="point_zs"
                    )
                    data["wl_" + str(round(v * 100))] = _read_sfincs_his(
                        his_file_name,
                        parameter="point_zs_" + str(round(v * 100)),
                    )

            else:
                data["wl"] = _read_sfincs_his(his_file_name, parameter="point_zs")
            # Loop through stations
            for station in self.station:
                if self.ensemble:
                    indx = data["wl_" + str(round(prcs[0] * 100))].index
                    df = pd.DataFrame(index=indx)
                    df.index.name = "date_time"
                    for i, v in enumerate(prcs):
                        df["wl_" + str(round(v * 100))] = data[
                            "wl_" + str(round(v * 100))
                        ][station.name]
                    # Best track
                    df["wl_best_track"] = data["wl"][station.name]
                else:
                    df = pd.DataFrame(index=data["wl"].index)
                    df.index.name = "date_time"
                    df["wl"] = data["wl"][station.name]

                # Write csv file for station
                file_name = os.path.join(post_path, "wl." + station.name + ".csv")
                df.to_csv(
                    file_name, date_format="%Y-%m-%dT%H:%M:%S", float_format="%.3f"
                )

            # Now we go through the stations and check if they are twl_gauge stations
            # Make an  empty Dataframe with columns for: model, station, lon, lat, twl and hat
            rows = []
            for station in self.station:
                if station.type == "twl_gauge":
                    # Read in the water level time series
                    file_name = os.path.join(post_path, "wl." + station.name + ".csv")
                    df = pd.read_csv(
                        file_name, parse_dates=["date_time"], index_col="date_time"
                    )
                    # Get maximum TWL
                    twl = df["wl"].max()
                    hat = station.hat
                    if twl > hat:  # High water!
                        # Add a row to the dataframe
                        row = {
                            "model": self.name,
                            "station": station.name,
                            "longitude": station.longitude,
                            "latitude": station.latitude,
                            "twl": twl,
                            "hat": hat,
                        }
                        rows.append(row)
                    else:
                        # We delete the wl file as TWL did not exceed HAT
                        os.remove(file_name)

            df = pd.DataFrame(rows)

            if not df.empty:
                # Write TWL to csv including headers
                twl_file_name = os.path.join(post_path, "twl.csv")

                df.to_csv(
                    twl_file_name, date_format="%Y-%m-%dT%H:%M:%S", float_format="%.3f"
                )
