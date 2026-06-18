"""Base model class for CoSMoS.

Defines the generic Model class with shared attributes and methods for reading
model configuration, boundary conditions, nesting, station output, and tiling
that all model-specific subclasses inherit from.
"""

import copy
import os
import platform
import subprocess

import cht_utils.fileops as fo
import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
import toml
from cht_nesting import nest2
from cht_utils.fileio.yaml import dict2yaml
from pyproj import CRS, Transformer
from scipy import interpolate

from .cluster import cluster_dict as cluster
from .cosmos import cosmos
from .stations import read_station_set


class Model:
    """Read generic model data from toml file, prepare model run paths, and submit jobs."""

    def __init__(self) -> None:
        """Initialize model attributes described in model.toml file."""

        self.flow = False
        self.wave = False
        self.priority = 10
        self.flow_nested = None
        self.wave_nested = None
        self.bw_nested = None
        self.flow_nested_name = None
        self.wave_nested_name = None
        self.bw_nested_name = None
        self.nested_flow_models = []
        self.nested_wave_models = []
        self.nested_bw_models = []
        self.flow_spinup_time = 0.0
        self.wave_spinup_time = 0.0
        self.xlim = None
        self.ylim = None
        self.flow_restart_file = None
        self.wave_restart_file = None
        self.vertical_reference_level_name = "MSL"
        self.vertical_reference_level_difference_with_msl = 0.0
        self.boundary_water_level_correction = 0.0
        self.station = []
        self.meteo_dataset = None
        self.meteo_spiderweb = None
        self.meteo_dataset = None
        self.meteo_wind = True
        self.meteo_atmospheric_pressure = True
        self.meteo_precipitation = True
        self.runid = None
        self.polygon = None
        self.make_flood_map = False
        self.make_wave_map = False
        self.make_water_level_map = False
        self.make_precipitation_map = False
        self.make_sedero_map = False
        self.make_storm_surge_map = False
        self.sa_correction = None
        self.ssa_correction = None
        self.wave = False
        self.mhhw = 0.0
        self.cluster = None
        self.boundary_twl_treshold = 999.0
        self.peak_boundary_twl = None
        self.peak_boundary_time = None
        self.zb_deshoal = None
        self.ensemble = False
        self.include_tide_only = False
        self.tide_only_model = None
        self.zs_ini_max = -9999.9
        self.exterior = None
        self.role = "generic"  # can be "generic", "floodmap", "large_scale". Based on the role, we can set some predefined actions. This happens e.g. in cosmos_sfincs.py
        self.resolution = -999.0
        self.omp_num_threads = -1  # Use -1 to use max number available

    def read_generic(self) -> None:
        """Read model attributes from model.toml file.

        See Also
        --------
        cosmos.Scenario
        cosmos.ModelLoop
        """

        if not os.path.exists(self.file_name):
            cosmos.stop(
                f"Model file not found: {self.file_name}\n"
                f"  Each model folder must contain a 'model.toml' file."
            )

        try:
            mdl_dict = toml.load(self.file_name)
        except toml.TomlDecodeError as e:
            cosmos.stop(f"Failed to parse model file {self.file_name}: {e}")

        # Turn into object
        for key, value in mdl_dict.items():
            setattr(self, key, value)

        self.flow_nested_name = self.flow_nested
        self.wave_nested_name = self.wave_nested
        self.bw_nested_name = self.bw_nested

        # If running in bathtub mode and make_flood_map, set spin-up time to zero
        if cosmos.config.run.bathtub and self.role == "floodmap":
            self.flow_spinup_time = 0.0
            self.wave_spinup_time = 0.0

        # If this is a SFINCS model and self.wave_nested is not None, then this is a SFINCS/SnapWave model
        # In that case, we set self.wave = True
        if self.wave_nested is not None:
            self.wave = True

        if not self.crs:
            cosmos.stop(
                f"No 'crs' defined in model file: {self.file_name}\n"
                f'  Every model must specify a coordinate reference system (e.g. crs = "EPSG:4326").'
            )

        try:
            self.crs = CRS(self.crs)
        except Exception as e:
            cosmos.stop(f"Invalid CRS '{self.crs}' in model {self.name}: {e}")

        self.get_exterior()

        self.add_stations()

    def get_exterior(self) -> None:

        # Need to find the exterior (polygon) and extent (bbox) of the model
        # This has always been a bit of a mess in CoSMoS ...
        # Currently, the preferred way is to use a geojson file ("model.geojson"),
        # that sits in the model database at the same level as "model.toml"
        # This geojson must have a polygon geometry that outlines the model with the property "name" set to "exterior"
        # Alternatively, a polygon text file f"{model.name}.txt" can be used,
        # or geojson files "outline.geojson" or "exterior.geojson" in the "misc" folder

        if os.path.exists(os.path.join(self.path, "model.geojson")):
            gdf = gpd.read_file(os.path.join(self.path, "model.geojson")).to_crs(
                self.crs
            )
        elif os.path.exists(os.path.join(self.path, "misc", "exterior.geojson")):
            gdf = gpd.read_file(
                os.path.join(self.path, "misc", "exterior.geojson")
            ).to_crs(self.crs)
            gdf["name"] = "exterior"
        elif os.path.exists(os.path.join(self.path, "misc", "outline.geojson")):
            gdf = gpd.read_file(
                os.path.join(self.path, "misc", "outline.geojson")
            ).to_crs(self.crs)
            gdf["name"] = "exterior"
        elif os.path.exists(os.path.join(self.path, "misc", self.name + ".geojson")):
            gdf = gpd.read_file(
                os.path.join(self.path, "misc", self.name + ".geojson")
            ).to_crs(self.crs)
            gdf["name"] = "exterior"
        elif os.path.exists(os.path.join(self.path, "misc", self.name + ".txt")):
            df = pd.read_csv(
                os.path.join(self.path, "misc", self.name + ".txt"),
                index_col=False,
                header=None,
                names=["x", "y"],
                sep=r"\s+",
            )
            # Make gdf with outline
            geom = shapely.geometry.Polygon(np.squeeze(df.to_numpy()))
            # GDF with outline of model
            gdf = gpd.GeoDataFrame({"geometry": [geom]}).set_crs(self.crs)
            gdf["name"] = "exterior"

        # We now have the exterior gdf in the model crs
        # Get the extent of all geometries in the gdf
        bounds = gdf.total_bounds
        # geom = gdf[gdf["name"] == "exterior"].geometry[0]
        if not self.xlim:
            # xlim/ylim are in local coordinates and are used for meteo
            # self.xlim = [geom.bounds[0], geom.bounds[2]]
            # self.ylim = [geom.bounds[1], geom.bounds[3]]
            self.xlim = [bounds[0], bounds[2]]
            self.ylim = [bounds[1], bounds[3]]
        # Set the polygon for checking that station fall within the model
        # NOTE why is this a path???
        # self.polygon = path.Path(geom.exterior.coords)

        # Now convert to WGS 84
        self.exterior = gdf.to_crs(4326)

        # # Read polygon around model (should preferably use a geojson file for this)
        # polygon_file = os.path.join(self.path, "misc", self.name + ".txt")

        # # Check a few file names for the geojson file
        # if os.path.exists(os.path.join(self.path, "misc", "outline.geojson")):
        #     geojson_file = os.path.join(self.path, "misc", "outline.geojson")
        # elif os.path.exists(os.path.join(self.path, "misc", self.name + ".geojson")):
        #     geojson_file = os.path.join(self.path, "misc", self.name + ".geojson")
        # elif os.path.exists(os.path.join(self.path, "misc", "exterior.geojson")):
        #     geojson_file = os.path.join(self.path, "misc", "exterior.geojson")
        # else:
        #     geojson_file = "none"

        # if os.path.exists(geojson_file):
        #     outline = gpd.read_file(geojson_file).to_crs(self.crs)
        #     geom    = outline.geometry[0]
        #     if not self.xlim:
        #         self.xlim = [geom.bounds[0], geom.bounds[2]]
        #         self.ylim = [geom.bounds[1], geom.bounds[3]]
        #     self.polygon = path.Path(geom.exterior.coords)
        #     # GDF with outline of model
        #     self.outline = gpd.GeoDataFrame({"geometry": [geom]}).set_crs(self.crs).to_crs(4326)
        # elif os.path.exists(polygon_file):
        #     df = pd.read_csv(polygon_file,
        #                      index_col=False,
        #                      header=None,
        #                      names=['x', 'y'],
        #                      sep=r"\s+")

        #     xy = df.to_numpy()
        #     self.polygon = path.Path(xy)
        #     if not self.xlim:
        #         self.xlim = [self.polygon.vertices.min(axis=0)[0],
        #                      self.polygon.vertices.max(axis=0)[0]]
        #         self.ylim = [self.polygon.vertices.min(axis=0)[1],
        #                      self.polygon.vertices.max(axis=0)[1]]
        #     # Make gdf with outline
        #     geom = shapely.geometry.Polygon(np.squeeze(xy))
        #     # GDF with outline of model
        #     self.outline = gpd.GeoDataFrame({"geometry": [geom]}).set_crs(self.crs).to_crs(4326)

    def add_stations(self) -> None:

        # Stations
        if self.station:
            # At this point, self.station is a list of filenames of station toml files. The files may be in cosmos\run_folder\configuration\stations.
            # Alternatively, they may also be in the model database in the model/stations folder.

            station_list = self.station
            self.station = []

            for station_file_name in station_list:
                station_set_name = station_file_name.replace(".toml", "")

                if station_set_name in cosmos.config.stations.station_set:
                    # The station set is in the commonly available stations
                    station_set = cosmos.config.stations.station_set[station_set_name]
                elif os.path.exists(
                    os.path.join(self.path, "stations", station_file_name)
                ):
                    # The station file is in the model database stations folder
                    station_set = read_station_set(
                        os.path.join(self.path, "stations", station_file_name)
                    )
                else:
                    # Station set not found
                    cosmos.log(
                        f"Station set {station_set_name} not found for model {self.name}. Skipping these stations."
                    )
                    continue

                # Check that station is within model polygon
                wgs84 = CRS.from_epsg(4326)
                transformer = Transformer.from_crs(wgs84, self.crs, always_xy=True)
                exterior = self.exterior.geometry.iloc[0]
                for station in station_set:
                    # Use shapely inpolygon function instead of matplotlib path
                    point = shapely.geometry.Point(station.longitude, station.latitude)
                    if exterior.contains(point):
                        # Make a copy of the station object to avoid issues when the same station is used in multiple models
                        st = copy.deepcopy(station)
                        x, y = transformer.transform(
                            station.longitude, station.latitude
                        )
                        st.x = x
                        st.y = y
                        self.station.append(st)

    def write_config_yml(self) -> None:
        # Write config file to be used in run_job.py
        config = {}
        config["model"] = self.name
        config["type"] = self.type
        config["region"] = self.region
        config["scenario"] = cosmos.scenario_name
        config["cycle"] = cosmos.cycle_string
        config["ensemble"] = self.ensemble
        config["run_mode"] = cosmos.config.run.run_mode
        config["event_mode"] = cosmos.config.run.event_mode
        config["vertical_reference_level_difference_with_msl"] = (
            self.vertical_reference_level_difference_with_msl
        )

        ## INPUT for nesting
        if self.ensemble:
            config["spw_path"] = cosmos.scenario.cycle_track_ensemble_spw_path
        if cosmos.config.run.run_mode == "cloud":
            config["cloud"] = {}
            config["cloud"]["host"] = cosmos.config.cloud_config.host
            config["cloud"]["access_key"] = cosmos.config.cloud_config.access_key
            config["cloud"]["secret_key"] = cosmos.config.cloud_config.secret_key
            config["cloud"]["region"] = cosmos.config.cloud_config.region
            config["cloud"]["token"] = cosmos.config.cloud_config.token
            config["cloud"]["namespace"] = cosmos.config.cloud_config.namespace
        if self.flow_nested:
            # Water level forcing
            config["flow_nested"] = {}
            config["flow_nested"]["overall_model"] = self.flow_nested.name
            config["flow_nested"]["overall_type"] = self.flow_nested.type
            config["flow_nested"]["overall_path"] = self.flow_nested.cycle_output_path
            # This bit is needed for cloud mode (file needs to be downloaded from S3)
            if self.flow_nested.type == "sfincs":
                file_name = "sfincs_his.nc"
            elif self.flow_nested.type == "xbeach":
                file_name = "xbeach_his.nc"
            elif self.flow_nested.type == "delft3dfm":
                file_name = "flow_his.nc"
            elif self.flow_nested.type == "delft3d":
                file_name = "delft3d_his.nc"
            config["flow_nested"]["overall_file"] = file_name
            config["flow_nested"]["boundary_water_level_correction"] = (
                self.boundary_water_level_correction
            )
        if self.wave_nested:
            # Wave forcing
            config["wave_nested"] = {}
            config["wave_nested"]["overall_model"] = self.wave_nested.name
            config["wave_nested"]["overall_type"] = self.wave_nested.type
            config["wave_nested"]["overall_path"] = self.wave_nested.cycle_output_path
            # This bit is needed for cloud mode (file needs to be downloaded from S3)
            if self.wave_nested.type == "hurrywave":
                file_name = "hurrywave_sp2.nc"
            config["wave_nested"]["overall_file"] = file_name
        if self.bw_nested:
            # Beware forcing
            config["bw_nested"] = {}
            config["bw_nested"]["overall_model"] = self.bw_nested.name
            config["bw_nested"]["overall_type"] = self.bw_nested.type
            config["bw_nested"]["overall_path"] = self.bw_nested.cycle_output_path
            config["bw_nested"]["overall_crs"] = self.bw_nested.crs.to_epsg()
            config["bw_nested"]["detail_crs"] = self.crs.to_epsg()
        if self.type == "xbeach":
            config["xbeach"] = {}
            config["xbeach"]["tref"] = self.domain.tref.strftime("%Y%m%d %H%M%S")
            config["xbeach"]["tstop"] = self.domain.tstop.strftime("%Y%m%d %H%M%S")
            config["xbeach"]["flow_nesting_points"] = self.flow_nesting_points
            config["xbeach"]["wave_nesting_point"] = self.wave_nesting_point
            config["xbeach"]["zb_deshoal"] = self.domain.zb_deshoal

        # OUTPUT for webviewer

        # Flood map

        if cosmos.config.run.make_flood_maps and self.make_flood_map:
            config["flood_map"] = {}
            if self.ensemble:
                name = "flood_map_90"
            else:
                name = "flood_map"
            config["flood_map"]["name"] = name
            if cosmos.config.run.run_mode == "cloud":
                config["flood_map"]["png_path"] = "/output"
                config["flood_map"]["index_path"] = "/tiles/indices"
                config["flood_map"]["topo_path"] = "/tiles/topobathy"
                config["flood_map"]["zsmax_path"] = "/input"
            else:
                config["flood_map"]["png_path"] = os.path.join(
                    cosmos.config.webviewer.data_path
                )
                config["flood_map"]["index_path"] = os.path.join(
                    self.path, "tiling", "indices"
                )
                config["flood_map"]["topo_path"] = os.path.join(
                    self.path, "tiling", "topobathy"
                )
                config["flood_map"]["zsmax_path"] = "."
            config["flood_map"]["start_time"] = cosmos.cycle
            config["flood_map"]["stop_time"] = cosmos.stop_time
            config["flood_map"]["interval"] = cosmos.config.webviewer.tile_layer[
                "flood_map"
            ]["interval"]
            config["flood_map"]["color_map"] = cosmos.config.map_contours[
                cosmos.config.webviewer.tile_layer["flood_map"]["color_map"]
            ]

        # Water level map

        if cosmos.config.run.make_water_level_maps and self.make_water_level_map:
            config["water_level_map"] = {}
            if self.ensemble:
                name = "water_level_90"
            else:
                name = "water_level"
            config["water_level_map"]["name"] = name
            if cosmos.config.run.run_mode == "cloud":
                config["water_level_map"]["png_path"] = "/output"
                config["water_level_map"]["index_path"] = "/tiles/indices"
                config["water_level_map"]["topo_path"] = "/tiles/topobathy"
                config["water_level_map"]["zsmax_path"] = "/input"
            else:
                config["water_level_map"]["png_path"] = os.path.join(
                    cosmos.config.webviewer.data_path
                )
                config["water_level_map"]["index_path"] = os.path.join(
                    self.path, "tiling", "indices"
                )
                config["water_level_map"]["topo_path"] = os.path.join(
                    self.path, "tiling", "topobathy"
                )
                config["water_level_map"]["zsmax_path"] = "."
            config["water_level_map"]["start_time"] = cosmos.cycle
            config["water_level_map"]["stop_time"] = cosmos.stop_time
            config["water_level_map"]["interval"] = cosmos.config.webviewer.tile_layer[
                "water_level_map"
            ]["interval"]
            config["water_level_map"]["color_map"] = cosmos.config.map_contours[
                cosmos.config.webviewer.tile_layer["water_level_map"]["color_map"]
            ]

        # Storm surge map

        if cosmos.config.run.make_storm_surge_maps and self.make_storm_surge_map:
            config["storm_surge_map"] = {}
            if self.ensemble:
                name = "storm_surge_90"
            else:
                name = "storm_surge"
            config["storm_surge_map"]["name"] = name
            if cosmos.config.run.run_mode == "cloud":
                config["storm_surge_map"]["png_path"] = "/output"
                config["storm_surge_map"]["index_path"] = "/tiles/indices"
                config["storm_surge_map"]["topo_path"] = "/tiles/topobathy"
                config["storm_surge_map"]["zsmax_path"] = "/input"
            else:
                config["storm_surge_map"]["png_path"] = os.path.join(
                    cosmos.config.webviewer.data_path
                )
                config["storm_surge_map"]["index_path"] = os.path.join(
                    self.path, "tiling", "indices"
                )
                config["storm_surge_map"]["topo_path"] = os.path.join(
                    self.path, "tiling", "topobathy"
                )
                config["storm_surge_map"]["zsmax_path"] = "."
            config["storm_surge_map"]["start_time"] = cosmos.cycle
            config["storm_surge_map"]["stop_time"] = cosmos.stop_time
            config["storm_surge_map"]["interval"] = cosmos.config.webviewer.tile_layer[
                "storm_surge_map"
            ]["interval"]
            config["storm_surge_map"]["color_map"] = cosmos.config.map_contours[
                cosmos.config.webviewer.tile_layer["storm_surge_map"]["color_map"]
            ]

        # Hm0 map

        if cosmos.config.run.make_wave_maps and self.make_wave_map:
            config["hm0_map"] = {}
            if self.ensemble:
                name = "hm0_90"
            else:
                name = "hm0"
            config["hm0_map"]["name"] = name
            if cosmos.config.run.run_mode == "cloud":
                config["hm0_map"]["png_path"] = "/output"
                config["hm0_map"]["index_path"] = "/tiles/indices"
                config["hm0_map"]["output_path"] = "/input"
            else:
                config["hm0_map"]["png_path"] = os.path.join(
                    cosmos.config.webviewer.data_path
                )
                config["hm0_map"]["index_path"] = os.path.join(
                    self.path, "tiling", "indices"
                )
                config["hm0_map"]["output_path"] = "."
            config["hm0_map"]["start_time"] = cosmos.cycle
            config["hm0_map"]["stop_time"] = cosmos.stop_time
            config["hm0_map"]["interval"] = cosmos.config.webviewer.tile_layer["hm0"][
                "interval"
            ]
            config["hm0_map"]["color_map"] = cosmos.config.map_contours[
                cosmos.config.webviewer.tile_layer["hm0"]["color_map"]
            ]
        if cosmos.config.run.make_sedero_maps and self.make_sedero_map:
            config["sedero_map"] = {}
            name = "sedero"
            config["sedero_map"]["name"] = name
            if cosmos.config.run.run_mode == "cloud":
                config["sedero_map"]["png_path"] = "/output"
                config["sedero_map"]["index_path"] = "/tiles/indices"
                config["sedero_map"]["output_path"] = "/input"
            else:
                config["sedero_map"]["index_path"] = os.path.join(
                    self.path, "tiling", "indices"
                )
                config["sedero_map"]["png_path"] = os.path.join(
                    cosmos.config.webviewer.data_path
                )
                config["sedero_map"]["output_path"] = "."
            config["sedero_map"]["start_time"] = self.domain.tref
            config["sedero_map"]["stop_time"] = self.domain.tstop
            config["sedero_map"]["color_map"] = cosmos.config.map_contours[
                cosmos.config.webviewer.tile_layer["sedero"]["color_map"]
            ]
            config["sedero_map"]["color_map_zb"] = cosmos.config.map_contours[
                cosmos.config.webviewer.tile_layer["bed_levels"]["color_map"]
            ]
        if cosmos.config.run.make_meteo_maps and self.make_precipitation_map:
            config["precipitation_map"] = {}
            if self.ensemble:
                name = "precipitation_90"
            else:
                name = "precipitation"
            config["precipitation_map"]["name"] = name
            if cosmos.config.run.run_mode == "cloud":
                config["precipitation_map"]["png_path"] = "/output"
                config["precipitation_map"]["index_path"] = "/tiles/indices"
                config["precipitation_map"]["output_path"] = "/input"
            else:
                config["precipitation_map"]["index_path"] = os.path.join(
                    self.path, "tiling", "indices"
                )
                config["precipitation_map"]["png_path"] = os.path.join(
                    cosmos.config.webviewer.data_path
                )
                config["precipitation_map"]["output_path"] = "."
            config["precipitation_map"]["start_time"] = cosmos.cycle
            config["precipitation_map"]["stop_time"] = cosmos.stop_time
            config["precipitation_map"]["color_map"] = cosmos.config.map_contours[
                cosmos.config.webviewer.tile_layer["precipitation"]["color_map"]
            ]

        dict2yaml(os.path.join(self.job_path, "config.yml"), config)

    def submit_job(self) -> None:

        # And now actually kick off this job
        # CoSMoS currently support three run modes: serial, parallel and cloud.
        # hpc to be added later

        # serial: run on local machine or on the same compute node in a HPC cluster where cosmos is running
        # parallel: run on remote Windows computers (WCP nodes) in a cluster
        # cloud: run Argo workflows on AWS

        # Get the platform name
        platform_name = platform.system().lower()

        cosmos.log("Submitting " + self.long_name + " ...")
        self.status = "running"

        if self.ensemble:
            # In case of ensemble, we move all inputs to base_input subfolder
            fo.mkdir(os.path.join(self.job_path, "base_input"))
            fo.move_file(
                os.path.join(self.job_path, "*.*"),
                os.path.join(self.job_path, "base_input"),
            )
            # Copy ensemble members file to job folder
            fo.copy_file(
                os.path.join(self.job_path, "base_input", "ensemble_members.txt"),
                self.job_path,
            )
            # Copy run_job_2.py to job folder
            fo.copy_file(
                os.path.join(self.job_path, "base_input", "run_job_2.py"), self.job_path
            )
            # Copy config.yml to job folder
            fo.copy_file(
                os.path.join(self.job_path, "base_input", "config.yml"), self.job_path
            )

        # First prepare batch file
        if cosmos.config.run.run_mode == "cloud":
            # No need for a batch file. Workflow template will take care of different steps.
            pass
        else:
            # Now loop through models
            # Make windows batch file (run.bat) that activates the correct environment and runs run_job.py
            if platform_name == "windows":
                fid = open(os.path.join(self.job_path, "run_job.bat"), "w")
                fid.write("@ echo off\n")
                fid.write("DATE /T > running.txt\n")
                fid.write("set CONDAPATH=" + cosmos.config.conda.path + "\n")
                if hasattr(cosmos.config.conda, "env"):
                    fid.write(
                        r"call %CONDAPATH%\Scripts\activate.bat "
                        + cosmos.config.conda.env
                        + "\n"
                    )
                else:
                    fid.write(r"call %CONDAPATH%\Scripts\activate.bat cosmos" + "\n")
                if self.ensemble:
                    fid.write("python run_job_2.py prepare_ensemble\n")
                    fid.write("python run_job_2.py simulate\n")
                    fid.write("python run_job_2.py merge_ensemble\n")
                    if not self.type == "beware":
                        fid.write("python run_job_2.py map_tiles\n")
                    fid.write("python run_job_2.py clean_up\n")
                else:
                    fid.write("python run_job_2.py simulate\n")
                    if not self.type == "beware":
                        fid.write("python run_job_2.py map_tiles\n")
                fid.write("move running.txt finished.txt\n")
                # fid.write("exit\n")
                fid.close()
            else:
                # Linux
                fid = open(os.path.join(self.job_path, "run_job.sh"), "w")
                fid.write("#!/bin/bash\n")
                fid.write("date > running.txt\n")
                fid.write("conda init\n")
                fid.write(f"conda activate {cosmos.config.conda.env}\n")
                if self.ensemble:
                    fid.write("python run_job_2.py prepare_ensemble\n")
                    fid.write("python run_job_2.py simulate\n")
                    fid.write("python run_job_2.py merge_ensemble\n")
                    if not self.type == "beware":
                        fid.write("python run_job_2.py map_tiles\n")
                    fid.write("python run_job_2.py clean_up\n")
                else:
                    fid.write("python run_job_2.py simulate\n")
                    if not self.type == "beware":
                        fid.write("python run_job_2.py map_tiles\n")
                fid.write("mv running.txt finished.txt\n")
                fid.close()

        # Run batch file (bat or sh) and python run_job_2.py are ready. Now actually submit the job.
        if cosmos.config.run.run_mode == "serial":
            # Model needs to be run in serial mode (local on the job path of a windows machine) or on same HPC node as CoSMoS
            if platform_name == "windows":
                cosmos.log("Launching run_job.bat in " + self.job_path + " ...")
                # Spawn the job in a fresh console window so simulation output
                # is visible to the user, and so the model loop can keep
                # polling for finished.txt. Using subprocess.Popen rather than
                # `start tmp.bat` works even in non-interactive contexts.
                # The full path to run_job.bat is required because cmd.exe
                # on machines with NoDefaultCurrentDirectoryInExePath=1 will
                # not look in CWD for executables.
                creationflags = 0
                if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                    creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
                if hasattr(subprocess, "CREATE_NEW_CONSOLE"):
                    creationflags |= subprocess.CREATE_NEW_CONSOLE
                subprocess.Popen(
                    ["cmd.exe", "/c", os.path.join(self.job_path, "run_job.bat")],
                    cwd=self.job_path,
                    creationflags=creationflags,
                    close_fds=True,
                )
            else:
                # Run on HPC node
                cosmos.log("Running on HPC node ...")
                fid = open("tmp.sh", "w")
                fid.write("#!/bin/bash\n")
                fid.write("cd " + self.job_path + "\n")
                fid.write("source ./run_job.sh\n")
                fid.write("exit\n")
                fid.close()
                os.system("source ./tmp.sh")

        elif cosmos.config.run.run_mode == "cloud":
            cosmos.log("Ready to submit to Argo - " + self.long_name + " ...")
            s3key = cosmos.scenario.name + "/" + "models" + "/" + self.name
            tilesfolder = self.region + "/" + self.type + "/" + self.deterministic_name
            # webviewerfolder = cosmos.config.webviewer.name + "/data/" + cosmos.scenario.name + "/" + cosmos.cycle_string
            webviewerfolder = cosmos.config.webviewer.name + "/data"
            # Delete existing folder in cloud storage
            cosmos.log("Deleting model folder on S3 : " + self.name)
            cosmos.cloud.delete_folder("cosmos-scenarios", s3key)
            # Upload job folder to cloud storage
            cosmos.log("Uploading to S3 : " + s3key)
            cosmos.cloud.upload_folder("cosmos-scenarios", self.job_path, s3key)
            if self.ensemble:
                # Should really make sure this all happens cosmos_cloud
                cosmos.cloud.upload_folder(
                    "cosmos-scenarios",
                    os.path.join(self.job_path, "base_input"),
                    s3key + "/base_input",
                )
            cosmos.log("Submitting template job : " + self.workflow_name)
            self.cloud_job = cosmos.argo.submit_template_job(
                workflow_name=self.workflow_name,
                job_name=self.name,
                subfolder=s3key,
                scenario=cosmos.scenario.name,
                cycle=cosmos.cycle_string,
                webviewerfolder=webviewerfolder,
                tilingfolder=tilesfolder,
            )

        elif cosmos.config.run.run_mode == "parallel":
            if platform_name == "windows":
                # Drop a job-pointer file in the shared jobs folder for the
                # WCP (Windows Compute Pool) nodes to pick up.
                os.makedirs(
                    os.path.join(cosmos.config.path.jobs, cosmos.scenario.name),
                    exist_ok=True,
                )
                file_name = os.path.join(
                    cosmos.config.path.jobs,
                    cosmos.scenario.name,
                    f"{self.name}_{cosmos.cycle_string}.txt",
                )
                fid = open(file_name, "w")
                fid.write(self.job_path)
                fid.close()
            else:
                # On Linux/HPC, CoSMoS itself is already running inside an
                # sbatch allocation. Launch run_job.sh as a detached background
                # process on the same compute node so the main loop can keep
                # submitting more jobs concurrently. Completion is detected by
                # the existing finished.txt poll in model_loop.
                cosmos.log("Launching run_job.sh in background - " + self.long_name + " ...")
                log_path = os.path.join(self.job_path, "stdout.log")
                log_fh = open(log_path, "w")
                subprocess.Popen(
                    ["bash", "run_job.sh"],
                    cwd=self.job_path,
                    stdout=log_fh,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                    close_fds=True,
                )

        else:
            print("No run mode defined, should be either serial, parallel or cloud")

    def set_paths(self) -> None:
        """Set model paths (input, output, figures, restart, job).

        See Also
        --------
        cosmos.MainLoop
        """
        # First model and restart folders if necessary

        cycle_path = cosmos.scenario.cycle_path
        restart_path = cosmos.scenario.restart_path
        #        timeseries_path = cosmos.scenario.cycle_timeseries_path
        # region          = self.region
        # tp              = self.type
        name = self.name

        # # Path with model results in cycle
        # self.cycle_path = os.path.join(cycle_path,
        #                                "models", region, tp, name)
        # self.cycle_input_path   = os.path.join(cycle_path, "models", region, tp, name, "input")
        # self.cycle_output_path  = os.path.join(cycle_path, "models", region, tp, name, "output")
        # self.cycle_figures_path = os.path.join(cycle_path, "models", region, tp, name, "figures")
        # self.cycle_post_path    = os.path.join(cycle_path, "models", region, tp, name, "timeseries")

        # # Restart paths
        # self.restart_flow_path = os.path.join(restart_path,
        #                                       region, tp, name, "flow")
        # self.restart_wave_path = os.path.join(restart_path,
        #                                       region, tp, name, "wave")

        # Path with model results in cycle
        self.cycle_path = os.path.join(cycle_path, "models", name)
        self.cycle_input_path = os.path.join(cycle_path, "models", name, "input")
        self.cycle_output_path = os.path.join(cycle_path, "models", name, "output")
        self.cycle_figures_path = os.path.join(cycle_path, "models", name, "figures")
        self.cycle_post_path = os.path.join(cycle_path, "models", name, "timeseries")

        # Restart paths (use deterministic name for restart files)
        self.restart_flow_path = os.path.join(
            restart_path, self.deterministic_name, "flow"
        )
        self.restart_wave_path = os.path.join(
            restart_path, self.deterministic_name, "wave"
        )

        # Model folder in the jobs folder
        # self.job_path = os.path.join(cosmos.config.path.jobs,
        #                              cosmos.scenario.name,
        #                              self.name)
        self.job_path = self.cycle_path

    def make_paths(self) -> None:
        # Make model cycle paths
        fo.mkdir(self.cycle_path)
        # fo.mkdir(self.cycle_input_path)
        # fo.mkdir(self.cycle_output_path)
        # fo.mkdir(self.cycle_figures_path)
        # fo.mkdir(self.cycle_post_path)
        fo.mkdir(self.restart_flow_path)
        fo.mkdir(self.restart_wave_path)

    def get_nested_models(self) -> None:
        """Get which model the current model is nested in."""
        if self.flow_nested_name:
            # Look up model from which it gets it boundary conditions
            for model2 in cosmos.scenario.model:
                if model2.name == self.flow_nested_name:
                    self.flow_nested = model2
                    model2.nested_flow_models.append(self)
                    break
            # It is possible that flow_nested is defined in model database,
            # but that model is not included in the scenario. In that case, flow_nested is still a string.
            if isinstance(self.flow_nested, str):
                self.flow_nested = None
                cosmos.log(
                    f"Warning: Flow nested model '{self.flow_nested_name}' for model '{self.name}' not found in scenario. Running without flow nesting."
                )
        if self.wave_nested_name:
            # Look up model from which it gets it boundary conditions
            for model2 in cosmos.scenario.model:
                if model2.name == self.wave_nested_name:
                    self.wave_nested = model2
                    model2.nested_wave_models.append(self)
                    break
            # It is possible that wave_nested is defined in model database,
            # but that model is not included in the scenario. In that case, wave_nested is still a string.
            if isinstance(self.wave_nested, str):
                self.wave_nested = None
                cosmos.log(
                    f"Wave nested model {self.wave_nested_name} for model {self.name} not found in scenario models."
                )
        if self.bw_nested_name:
            # Look up model from which it gets it boundary conditions
            for model2 in cosmos.scenario.model:
                if model2.name == self.bw_nested_name:
                    self.bw_nested = model2
                    model2.nested_bw_models.append(self)
                    break

    def get_all_nested_models(self, tp: str, all_nested_models=None) -> list:
        """Return a list of all models nested in this model."""
        # def get_all_nested_models(self, tp, all_nested_models=[]):
        # don't define empty list as default ! (https://nikos7am.com/posts/mutable-default-arguments/)
        # Return a list of all models nested in this model

        if all_nested_models is None:
            all_nested_models = []

        if tp == "flow":
            for mdl in self.nested_flow_models:
                all_nested_models.append(mdl)
                if mdl.nested_flow_models:
                    all_nested_models = mdl.get_all_nested_models(
                        "flow", all_nested_models=all_nested_models
                    )

        if tp == "wave":
            for mdl in self.nested_wave_models:
                all_nested_models.append(mdl)
                if mdl.nested_wave_models:
                    all_nested_models = mdl.get_all_nested_models(
                        "wave", all_nested_models=all_nested_models
                    )

        return all_nested_models

    # def add_stations(self, name):
    #     """Add stations that are located within this model.

    #     Parameters
    #     ----------
    #     name : str
    #         station file name or station name
    #     """
    #     wgs84 = CRS.from_epsg(4326)
    #     transformer = Transformer.from_crs(wgs84, self.crs, always_xy=True)

    #     exterior = self.exterior.to_crs(self.crs)

    #     if name[-4:].lower() == "toml":

    #         # Get all stations in file
    #         stations = cosmos.config.stations.find_by_file(name)

    #         for st in stations:

    #             station = copy.copy(st)

    #             # Check if this station is not already present
    #             if station.name in [st.name for st in self.station]:
    #                 continue

    #             station.longitude_model = station.longitude
    #             station.latitude_model  = station.latitude

    #             x, y = transformer.transform(station.longitude_model,
    #                                          station.latitude_model)
    #             station.x = x
    #             station.y = y

    #             # Check whether this station lies with model domain

    #             for ip, polygon in exterior.iterrows():
    #                 inpol = inpolygon(x, y, polygon["geometry"])
    #                 if inpol[0]:
    #                     self.station.append(station)
    #                     break

    #             # if self.polygon:
    #             #     if not self.polygon.contains_points([(x, y)])[0]:
    #             #         # On to the next station
    #             #         continue
    #             # self.station.append(station)

    #     else:

    #         station = copy.copy(cosmos.config.stations.find_by_name(name))

    #         station.longitude_model = station.longitude
    #         station.latitude_model  = station.latitude

    #         x, y = transformer.transform(station.longitude_model,
    #                                      station.latitude_model)
    #         station.x = x
    #         station.y = y

    #         self.station.append(station)

    def get_peak_boundary_conditions(self) -> None:
        """Get boundary conditions from overall model and define peak."""
        # Water level boundary conditions

        # Get boundary conditions from overall model (Nesting 2)
        zcor = (
            self.boundary_water_level_correction
            - self.vertical_reference_level_difference_with_msl
        )

        if self.type == "xbeach":
            self.domain.tref = self.flow_start_time
            self.domain.tstop = self.flow_stop_time

        z_max = nest2(
            self.flow_nested.domain,
            self.domain,
            output_path=self.flow_nested.cycle_output_path,
            boundary_water_level_correction=zcor,
            return_maximum=True,
        )
        t = z_max.index
        z = z_max.values

        # Wave boundary conditions
        if self.wave_nested:
            # Get boundary conditions from overall model (Nesting 2)
            hm0_max = nest2(
                self.wave_nested.domain,
                self.domain,
                output_path=self.wave_nested.cycle_output_path,
                option="timeseries",
                return_maximum=True,
            )

            # Interpolate to flow boundary times
            flow_secs = z_max.index.values.astype(float)
            wave_secs = hm0_max.index.values.astype(float)
            f = interpolate.interp1d(wave_secs, hm0_max.values)
            hm0 = f(flow_secs)
            hm0 = np.nan_to_num(hm0)

        else:
            hm0 = np.zeros(np.size(z))

        # Estimate total water level above MHHW with tide + surge + 0.2*Hm0
        twl = z + cluster[self.cluster].hm0fac * hm0 - self.mhhw

        # Index of peak
        imax = np.argmax(twl)

        self.peak_boundary_twl = twl[imax]
        self.peak_boundary_time = t[imax].to_pydatetime()

    def set_stations_to_upload(self) -> None:

        all_nested_models = self.get_all_nested_models("flow")
        if self.type == "beware":
            for station in self.station:
                station.upload = False

        if all_nested_models:
            all_nested_stations = []
            if all_nested_models[0].type == "beware":
                all_nested_models = [self]
                bw = 1
            else:
                bw = 0
            for mdl in all_nested_models:
                for st in mdl.station:
                    all_nested_stations.append(st.name)
            for station in self.station:
                if station.type == "tide_gauge":
                    if station.name in all_nested_stations and bw == 0:
                        station.upload = False

        all_nested_models = self.get_all_nested_models("wave")
        if all_nested_models:
            all_nested_stations = []
            if all_nested_models[0].type == "beware":
                all_nested_models = [self]
                bw = 1
            else:
                bw = 0
            for mdl in all_nested_models:
                for st in mdl.station:
                    all_nested_stations.append(st.name)
            for station in self.station:
                if station.type == "wave_buoy":
                    if station.name in all_nested_stations and bw == 0:
                        station.upload = False

    def write_meteo_input_files(
        self, prefix: str, tref, path: str = None, format: str = "ascii"
    ) -> None:

        if not path:
            path = self.job_path

        time_range = [self.flow_start_time, self.flow_stop_time]

        header_comments = False
        if self.type.lower() == "delft3dfm":
            header_comments = True

        # Check if the model uses 2d meteo forcing from weather model

        if not self.meteo_dataset:
            return

        # Per-member ensembles re-collect the gridded data for each member
        # and write the cut-out into a <path>/<member>/ subfolder.
        # Deterministic models keep the existing single-shot behaviour.
        per_member = self.ensemble and cosmos.scenario.meteo_ensemble_mode

        def _emit_for(out_path):
            """Cut self.meteo_dataset to this model's domain and write the
            Delft3D-style forcing files into ``out_path``."""
            meteo_res = self.meteo_dataset.resolution
            if self.crs.is_geographic:
                # Model is in geographical coordinates
                dxy = self.resolution  # if not provided, dxy is -999.0
                if meteo_res < dxy * 0.5:
                    # Meteo data is much finer than model resolution
                    meteo_dataset = self.meteo_dataset.cut_out(
                        lon_range=self.xlim,
                        lat_range=self.ylim,
                        time_range=time_range,
                        dx=0.5 * dxy,  # new resolution of meteo dataset
                        dy=0.5 * dxy,  # new resolution of meteo dataset
                        crs=self.crs,
                    )
                else:
                    # Make a new cut-out that covers the domain of the model while using meteo resolution
                    meteo_dataset = self.meteo_dataset.cut_out(
                        lon_range=self.xlim,
                        lat_range=self.ylim,
                        time_range=time_range,
                        crs=self.crs,
                    )
            else:
                meteo_res_local = meteo_res
                if self.meteo_dataset.crs.is_geographic:
                    meteo_res_local = meteo_res_local * 111e3  # convert to meters
                # First check if the model has a resolution defined. If not, use meteo resolution or 20km
                dxy = self.resolution if self.resolution > 0.0 else 20000.0
                # If model resolution is larger than meteo resolution (very big default), use meteo resolution
                if dxy > meteo_res_local:
                    dxy = meteo_res_local
                x = np.arange(self.xlim[0] - dxy, self.xlim[1] + dxy, dxy)
                y = np.arange(self.ylim[0] - dxy, self.ylim[1] + dxy, dxy)
                # non-geographical coordinates always need to be reprojected to model CRS
                meteo_dataset = self.meteo_dataset.cut_out(
                    x=x,
                    y=y,
                    time_range=time_range,
                    crs=self.crs,
                )

            if (
                self.type == "delft3d"
                or self.type == "delft3dfm"
                or self.type == "xbeach"
                or self.type == "hurrywave"
                or self.type == "sfincs"
            ):
                # Simple for now

                if format == "netcdf":
                    params = []

                    if self.meteo_wind:
                        params.append("wind")
                    if self.meteo_atmospheric_pressure:
                        params.append("barometric_pressure")
                    if self.meteo_precipitation:
                        params.append("precipitation")

                    meteo_dataset.to_delft3d(
                        prefix,
                        format="netcdf",
                        parameters=params,
                        path=out_path,
                        refdate=tref,
                        time_range=time_range,
                        header_comments=header_comments,
                    )

                else:
                    # ASCII format

                    if self.meteo_wind:
                        meteo_dataset.to_delft3d(
                            prefix,
                            parameters=["wind"],
                            path=out_path,
                            refdate=tref,
                            time_range=time_range,
                            header_comments=header_comments,
                        )

                    if self.meteo_atmospheric_pressure:
                        meteo_dataset.to_delft3d(
                            prefix,
                            parameters=["barometric_pressure"],
                            path=out_path,
                            refdate=tref,
                            time_range=time_range,
                            header_comments=header_comments,
                        )

                    if self.meteo_precipitation:
                        meteo_dataset.to_delft3d(
                            prefix,
                            parameters=["precipitation"],
                            path=out_path,
                            refdate=tref,
                            time_range=time_range,
                            header_comments=header_comments,
                        )

        if per_member:
            # Loop members. Each iteration re-collects that member's gridded
            # data into self.meteo_dataset.ds, then writes amu/amv/amp into
            # <path>/<member>/. Only one member is in memory at a time.
            # We also stage the per-member spw alongside (named <prefix>.spw)
            # so the runner doesn't need to copy anything at runtime — the
            # member subfolder is self-contained.
            last_cycle = (
                cosmos.cycle if cosmos.config.run.collect_meteo_up_to_cycle else None
            )
            spw_src_dir = cosmos.scenario.cycle_track_ensemble_spw_path
            for member in cosmos.scenario.ensemble_names:
                cosmos.log(
                    f"  meteo forcing files for ensemble member {member} ..."
                )
                self.meteo_dataset.collect(
                    time_range, last_cycle=last_cycle, subfolder=member
                )
                member_path = os.path.join(path, member)
                fo.mkdir(member_path)
                _emit_for(member_path)
                # Copy this member's spw into its subfolder as <prefix>.spw
                # (the name the model binary expects).
                spw_src = os.path.join(spw_src_dir, "ensemble_" + member + ".spw")
                if os.path.exists(spw_src):
                    fo.copy_file(spw_src, os.path.join(member_path, prefix + ".spw"))
                else:
                    cosmos.log(
                        f"  warning: ensemble spw not found for member {member}: {spw_src}"
                    )
        else:
            _emit_for(path)

    def get_restart_time(self) -> "datetime.datetime":
        # If we play catch up (i.e. we may have missed one or more cycles),
        # then we write output at the last meteo analysis time.
        # However, if we want the next cycle to be the current cycle + interval, trstsec must be the
        # minimum of these to times.
        # There are three options:
        # 1) Forecast mode (i.e. the meteo dataset has a last_analysis_time)
        #   a) With catch up    -> trst = last analysis time
        #   b) Without catch up -> trst = min(next cycle time + interval, last analysis time)
        # 2) Hindcast mode      -> trst = stop time of simulation
        if self.meteo_dataset is None:
            # No meteo dataset, so just return stop time
            trst = cosmos.stop_time.replace(tzinfo=None)
            return trst
        if self.meteo_dataset.last_analysis_time:
            # 1) Forecast mode
            if cosmos.config.run.catch_up:
                # a) With catch up
                trst = self.meteo_dataset.last_analysis_time.replace(tzinfo=None)
            else:
                # b) Without catch up
                if cosmos.next_cycle_time is None:
                    # There is no next cycle (probably running in single_shot mode), so set to last analysis time
                    trst = self.meteo_dataset.last_analysis_time.replace(tzinfo=None)
                else:
                    trst = cosmos.next_cycle_time.replace(tzinfo=None)
                    trst = min(
                        trst, self.meteo_dataset.last_analysis_time.replace(tzinfo=None)
                    )
        else:
            # 2) Hindcast mode meteo
            if cosmos.next_cycle_time is None:
                # We do not actually need a restart file, but hey, what the heck.
                trst = cosmos.stop_time.replace(tzinfo=None)
            else:
                trst = cosmos.next_cycle_time.replace(tzinfo=None)

        return trst


def inpolygon(xq: float, yq: float, poly) -> bool:
    # if xq and yq are floats, turn into 1D arrays
    if isinstance(xq, float):
        xq = np.array([xq])
    if isinstance(yq, float):
        yq = np.array([yq])
    coords = np.column_stack((xq.ravel(), yq.ravel()))
    pts = shapely.points(coords)
    inside = shapely.contains(poly, pts)  # vectorized
    return inside.reshape(xq.shape)
