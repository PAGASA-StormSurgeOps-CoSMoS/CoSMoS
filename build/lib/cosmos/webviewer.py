"""Web viewer generation for CoSMoS.

Builds and uploads the interactive web viewer with time-series station data,
map tile layers, and GeoJSON overlays for visualizing forecast results.
"""

import copy
import datetime
import os
import shutil
import time

import cht_utils.fileops as fo
import numpy as np
import pandas as pd
from cht_meteo import MeteoDataset
from cht_tide.tide_stations import TideStationsDataset
from cht_utils.fileio.json_js import read_json_js, write_csv_js, write_json_js
from cht_utils.fileio.yaml import dict2yaml
from cht_utils.fileops import find_replace
from geojson import Feature, FeatureCollection, Point
from pyproj import CRS, Transformer
from scipy import interpolate

from .argo import Argo
from .cosmos import cosmos


class WebViewer:
    """Cosmos webviewer class"""

    def __init__(self, name: str) -> None:
        """Initialize webviewer.
        - Makes local copy of the webviewer from a template. If such a copy already exists, data will be copied to the existing webviewer.
        - Updating the scenario.js with the current scenario.
        - Make a variable file defining the variables that are mapped for the current scenario.

        Parameters
        ----------
        name : str
            Name of webviewer.
        """
        self.name = name
        self.path = os.path.join(cosmos.config.path.main, "webviewers", name)
        self.version = cosmos.config.webviewer.version
        if fo.exists(self.path):
            self.exists = True
        else:
            self.exists = False

        # Check whether web viewer already exists
        # If not, copy empty web viewer from templates
        if not self.exists:

            cosmos.log("Making new web viewer from " + self.version + " ...")

            fo.mkdir(self.path)

            # cosmos repository, so we can be sure it is always there
            cosmos_repo_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

            template_path = os.path.join(
                cosmos_repo_path, "webviewer_templates", self.version, "*"
            )
            fo.copy_file(template_path, self.path)

            # Change the title string in index.html to the scenario long name
            find_replace(
                os.path.join(self.path, "index.html"),
                "COSMOS_VIEWER",
                cosmos.scenario.long_name,
            )

    def make(self) -> None:

        # Make scenario folder in web viewer
        self.cycle_path = os.path.join(
            self.path, "data", cosmos.scenario.name, cosmos.cycle_string
        )

        # Make scenario folder and cycle folder
        cosmos.log("Making new cycle folder on web viewer ...")
        fo.mkdir(os.path.join(self.path, "data", cosmos.scenario.name))
        fo.mkdir(
            os.path.join(self.path, "data", cosmos.scenario.name, cosmos.cycle_string)
        )

        #        # In cloud mode, also make a path on S3
        #        if cosmos.config.run.run_mode == "cloud":

        # Stations and buoys
        cosmos.log("Copying time series ...")
        fo.mkdir(os.path.join(self.cycle_path, "timeseries"))
        # Set stations to upload (only upload for high-res nested models)
        for model in cosmos.scenario.model:
            model.set_stations_to_upload()
        self.make_timeseries("wl")
        self.make_timeseries("twl")
        self.make_timeseries("waves")

        if cosmos.config.run.run_mode == "cloud":
            # Merge the map tiles of the different models
            self.merge_map_tiles()

        # Map tiles
        cosmos.log("Adding tile layers ...")
        self.map_variables = []

        if cosmos.config.run.make_flood_maps:
            self.set_map_tile_variables(
                "flood_map",
                "Flooding",
                "This is a flood map. It can tell if you will drown.",
                cosmos.config.map_contours[
                    cosmos.config.webviewer.tile_layer["flood_map"]["color_map"]
                ],
            )
            self.set_map_tile_variables(
                "flood_map_90",
                "Flooding (worst case)",
                "This is a worst case flood map. It can tell if you will drown.",
                cosmos.config.map_contours[
                    cosmos.config.webviewer.tile_layer["flood_map"]["color_map"]
                ],
            )

        if cosmos.config.run.make_wave_maps:
            self.set_map_tile_variables(
                "hm0",
                "Wave height",
                "These are Hm0 wave heights.",
                cosmos.config.map_contours[
                    cosmos.config.webviewer.tile_layer["hm0"]["color_map"]
                ],
            )

            self.set_map_tile_variables(
                "hm0_90",
                "Wave height (worst case)",
                "These are worst case Hm0 wave heights.",
                cosmos.config.map_contours[
                    cosmos.config.webviewer.tile_layer["hm0"]["color_map"]
                ],
            )

        if cosmos.config.run.make_water_level_maps:
            self.set_map_tile_variables(
                "water_level",
                "Peak water level",
                "These were the peak water levels during the storm.",
                cosmos.config.map_contours[
                    cosmos.config.webviewer.tile_layer["water_level_map"]["color_map"]
                ],
            )
            self.set_map_tile_variables(
                "water_level_90",
                "Peak water level (worst case)",
                "These were the worst-case peak water levels during the storm.",
                cosmos.config.map_contours[
                    cosmos.config.webviewer.tile_layer["water_level_map"]["color_map"]
                ],
            )

        if cosmos.config.run.make_storm_surge_maps:
            # These tiles have not yet been made, when the model was finished. So we need to make them here.
            # self.make_storm_surge_map()
            self.set_map_tile_variables(
                "storm_surge",
                "Peak storm surge (no waves)",
                "These were the peak storm surges during the storm.",
                cosmos.config.map_contours[
                    cosmos.config.webviewer.tile_layer["storm_surge_map"]["color_map"]
                ],
            )
            self.set_map_tile_variables(
                "storm_surge_90",
                "Peak storm surge (worst case, no waves)",
                "These are the worst case peak storm surges during the storm.",
                cosmos.config.map_contours[
                    cosmos.config.webviewer.tile_layer["storm_surge_map"]["color_map"]
                ],
            )

        # Precipitation should come from meteo dataset, not from models
        # But perhaps only shown where we have flood models
        if cosmos.config.run.make_meteo_maps:
            self.set_map_tile_variables(
                "precipitation",
                "Cumulative rainfall",
                "These are cumulative precipitations.",
                cosmos.config.map_contours[
                    cosmos.config.webviewer.tile_layer["precipitation"]["color_map"]
                ],
            )
            self.set_map_tile_variables(
                "precipitation_90",
                "Cumulative rainfall (worst case)",
                "These are worst case cumulative precipitations.",
                cosmos.config.map_contours[
                    cosmos.config.webviewer.tile_layer["precipitation"]["color_map"]
                ],
            )
            cosmos.log("Adding meteo layers ...")
            self.make_meteo_maps()

        if cosmos.config.run.make_sedero_maps:
            self.set_map_tile_variables(
                "sedero",
                "Sedimentation/erosion",
                "This is a sedimentation/erosion map. It can tell if your house will wash away.",
                cosmos.config.map_contours[
                    cosmos.config.webviewer.tile_layer["sedero"]["color_map"]
                ],
            )
            self.set_map_tile_variables(
                "zb0",
                "Pre-storm bed level",
                "These were the bed levels prior to the storm.",
                cosmos.config.map_contours[
                    cosmos.config.webviewer.tile_layer["bed_levels"]["color_map"]
                ],
            )
            self.set_map_tile_variables(
                "zbend",
                "Post-storm bed level",
                "These were the bed levels after the storm.",
                cosmos.config.map_contours[
                    cosmos.config.webviewer.tile_layer["bed_levels"]["color_map"]
                ],
            )
            cosmos.log("Adding XBeach markers ...")
            self.make_xb_markers()
            cosmos.log("Adding XBeach regimes ...")
            self.make_xb_regimes()

        # TODO add if-statement for run-up layers
        cosmos.log("Adding run-up layers ...")
        self.make_runup_map()

        cosmos.log("Adding TWL layers ...")
        self.make_twl_map()

        # Write map variables to file
        cosmos.log("Writing variables ...")
        mv_file = os.path.join(self.cycle_path, "variables.js")
        write_json_js(mv_file, self.map_variables, "var map_variables =")

        # Update scenario.js
        self.update_scenarios_js()

        cosmos.log("Web viewer done.")

    def set_map_tile_variables(
        self, name, long_name, description, color_map, max_native_zoom=None
    ):

        folders = []
        # Check if tiles are available
        if cosmos.config.run.run_mode == "cloud":
            bucket_name = "cosmos.deltares.nl"
            prefix = (
                self.name
                + "/data/"
                + cosmos.scenario.name
                + "/"
                + cosmos.cycle_string
                + "/"
                + name
            )
            folders = cosmos.cloud.list_folders(bucket_name, prefix)
        else:
            # Tiles are stored locally
            tile_path = os.path.join(self.cycle_path, name)
            if fo.exists(tile_path):
                # Check times
                folders = fo.list_folders(os.path.join(tile_path, "*"), basename=True)

        if not folders:
            return

        pathstr = []
        namestr = []

        max_zoom = 0
        for folder in folders:
            # Define the format of the original string
            format_str = "%Y%m%d_%HZ"

            # Extract the start and end date-time substrings (without the combined_ string)
            start_str = folder.replace("combined_", "")[
                :12
            ]  # First 12 characters, e.g.: '20240503_12Z'
            end_str = folder.replace("combined_", "")[
                13:
            ]  # From the 14th character to the end, e.g.: '20240504_12Z'

            # Parse the start and end times
            start_time = datetime.datetime.strptime(start_str, format_str)
            end_time = datetime.datetime.strptime(end_str, format_str)

            if folder[0:3] == "com":
                # Determine the total duration of the combined output maps
                td = end_time - start_time
                hrstr = str(int(td.days * 24 + td.seconds / 3600))

                # make sure the combined map is always the first one to show-up
                pathstr.insert(0, folder)
                namestr.insert(0, "Combined " + hrstr + "-hour forecast")
            else:
                # Define a nicer format for the output
                output_format = "%Y-%m-%d %H:%M"

                # Convert to the new format
                start_nice = start_time.strftime(output_format)
                end_nice = end_time.strftime(output_format)

                # Append the new strings to the lists
                pathstr.append(folder)
                namestr.append(start_nice + " - " + end_nice + " UTC")

            # check subfolder zoom levels
            zooms = fo.list_folders(
                os.path.join(self.cycle_path, name, folder, "*"), basename=True
            )
            max_zoom = max([int(z) for z in zooms])

        if max_native_zoom is None:
            max_native_zoom = max_zoom

        # Add to map variables
        dct = {}
        dct["name"] = name
        dct["long_name"] = long_name
        dct["description"] = description
        dct["format"] = "xyz_tile_layer"
        dct["max_native_zoom"] = max_native_zoom

        tms = []
        for it, pth in enumerate(pathstr):
            tm = {}
            tm["name"] = pth
            tm["string"] = namestr[it]
            tms.append(tm)
        dct["times"] = tms

        dct["legend"] = make_legend(mp=color_map)

        self.map_variables.append(dct)

    def make_xb_markers(self) -> None:
        """Make geojson file with markers for XBeach models that ran."""
        # Markers for XBeach models that ran
        features = []
        wgs84 = CRS.from_epsg(4326)
        for model in cosmos.scenario.model:
            if model.type == "xbeach":
                # Use wave nesting point to put the marker
                xp = model.domain.wave_boundary_point[0].geometry.x
                yp = model.domain.wave_boundary_point[0].geometry.y
                transformer = Transformer.from_crs(model.crs, wgs84, always_xy=True)
                lon, lat = transformer.transform(xp, yp)
                point = Point((lon, lat))
                features.append(
                    Feature(
                        geometry=point,
                        properties={
                            "name": model.name,
                            "long_name": model.long_name,
                            "flow_nested": model.flow_nested_name,
                            "wave_nested": model.wave_nested_name,
                        },
                    )
                )
        # Save xbeach geojson file
        if features:
            feature_collection = FeatureCollection(features)
            stations_file = os.path.join(self.cycle_path, "xbeach.geojson.js")
            write_json_js(stations_file, feature_collection, "var xb_markers =")

    def make_meteo_maps(self) -> None:

        cosmos.log("Making meteo map tiles ...")

        try:
            # Wind
            # Name of meteo dataset in scenario file (this one will be used for the wind map)

            # First find our meteo dataset
            dset = None
            for dataset_name, meteo_dataset in cosmos.meteo_database.dataset.items():
                if meteo_dataset.name == cosmos.scenario.meteo_dataset:
                    # Make a copy of the meteo dataset
                    dset = copy.deepcopy(meteo_dataset)

            # Check if there is a tropical cyclone
            if cosmos.tropical_cyclone is not None:
                # Create a meteo dataset from the tropical cyclone
                if dset is None:
                    # There is not meteo dataset so we need to create one
                    # This still needs to be developed !!!
                    # First initialize an empty meteo dataset (with all zeros)
                    lon_list = np.arange(110.0, 140.0, 0.25).tolist()
                    lat_list = np.arange(0.0, 30.0, 0.25).tolist()
                    # Time zone is UTC
                    tstart = cosmos.cycle
                    tstop = cosmos.stop_time.replace(tzinfo=datetime.timezone.utc)
                    # Make a list of datetime.datetime objects from the start to cycle to the end with 3-hour intervals
                    time_list = (
                        pd.date_range(start=tstart, end=tstop, freq="1h")
                        .to_pydatetime()
                        .tolist()
                    )
                    mds = MeteoDataset(lon=lon_list, lat=lat_list, time=time_list)
                    mds.fill()
                    dset = cosmos.tropical_cyclone.to_meteo_dataset(mds)
                    # cosmos.log("No meteo dataset found for wind maps")
                    # return

                else:
                    # There is a meteo dataset so we can add the tropical cyclone to it
                    dset = cosmos.tropical_cyclone.to_meteo_dataset(dset)
                    # cosmos.log("No meteo dataset found for wind maps")
                    # return

            if dset is None:
                cosmos.log("No meteo dataset found for wind maps")
                return

            # Cut out to lon/lat limits if specified in config
            if (
                cosmos.config.webviewer.lon_lim is not None
                and cosmos.config.webviewer.lat_lim is not None
            ):
                dset = dset.cut_out(
                    x_range=cosmos.config.webviewer.lon_lim,
                    y_range=cosmos.config.webviewer.lat_lim,
                )

            # Get maximum wind speed
            u = dset.ds["wind_u"].values[:]
            v = dset.ds["wind_v"].values[:]
            vmag = np.sqrt(u * u + v * v)
            wndmx = np.max(vmag)

            file_name = os.path.join(self.cycle_path, "wind.json.js")
            dset.wind_to_json(file_name, time_range=None, js=True)

            # Add wind to map variables

            if wndmx <= 20.0:
                contour_set = "wnd20"
                wndmx = 20.0
            elif wndmx <= 40.0:
                contour_set = "wnd40"
                wndmx = 40.0
            else:
                contour_set = "wnd60"
                wndmx = 60.0
            dct = {}
            dct["name"] = "wind"
            dct["long_name"] = "Wind"
            dct["description"] = (
                "This is a wind map. It can tell if your house will blow away."
            )
            dct["format"] = "vector_field"
            dct["max"] = wndmx
            mp = cosmos.config.map_contours[contour_set]
            lgn = {}
            lgn["text"] = mp["string"]
            cntrs = mp["contours"]
            contours = []
            for cntr in cntrs:
                contour = {}
                contour["text"] = cntr["string"]
                contour["color"] = "#" + cntr["hex"]
                contours.append(contour)
            lgn["contours"] = contours
            dct["legend"] = lgn

            self.map_variables.append(dct)

            # Would be neater to write folloing two files as geojson first and then write them as js here
            if cosmos.tropical_cyclone is not None:
                # Copy track geojson to cycle folder
                jsfile = os.path.join(
                    cosmos.scenario.cycle_track_spw_path, "track.geojson.js"
                )
                fo.copy_file(jsfile, self.cycle_path)

            if cosmos.scenario.track_ensemble:
                # Copy ensemble tracks
                jsfile = os.path.join(
                    cosmos.scenario.cycle_track_ensemble_path,
                    "track_ensemble.geojson.js",
                )
                fo.copy_file(jsfile, self.cycle_path)

        except Exception as e:
            print(str(e))

    def make_xb_regimes(self) -> None:
        """Make Sallenger regimes markers for webviewer."""
        output_path = self.cycle_path
        df_all = pd.DataFrame()

        # Sallenger regimes

        for model in cosmos.scenario.model:
            if model.type == "xbeach":
                # if os.path.exists(os.path.join(model.cycle_output_path,
                #                           "beware_his.nc")) and not model.ensemble:

                # Check if Sallenger regimes are calculated

                if os.path.exists(
                    os.path.join(model.cycle_post_path, "Sallengerregimes.csv")
                ):
                    csv_file = os.path.join(
                        model.cycle_post_path, "Sallengerregimes.csv"
                    )
                    df = pd.read_csv(csv_file)

                    transformer = Transformer.from_crs(
                        model.crs, "WGS 84", always_xy=True
                    )

                    df["lon"], df["lat"] = transformer.transform(df.X, df.Y)
                    df_all = pd.concat([df_all, df], ignore_index=True)

        features = []
        for ip in range(len(df_all)):
            lon, lat = df_all.lon[ip], df_all.lat[ip]
            point = Point((lon, lat))

            features.append(
                Feature(
                    geometry=point,
                    properties={
                        "LocNr": int(ip),
                        "Lon": lon,
                        "Lat": lat,
                        "regime": int(df_all.sallregime[ip]),
                        # "erosionregime":int(df.erosionregime[ip])
                    },
                )
            )

        # Save xbeach geojson file for Sallenger regimes
        if features:
            feature_collection = FeatureCollection(features)
            output_path_regime = os.path.join(output_path, "sallenger\\")
            fo.mkdir(output_path_regime)
            file_name = os.path.join(output_path_regime, "sallenger.geojson.js")
            write_json_js(file_name, feature_collection, "var regimes =")

            dct = {}
            dct["name"] = "sallenger"
            dct["long_name"] = "Sallenger regimes XBeach"
            dct["description"] = "These are the Sallenger regimes"
            dct["format"] = "geojson"
            dct["legend"] = make_legend(type="sallenger_regimes")

            self.map_variables.append(dct)

        # now same for Erosion regimes
        features_ero = []
        for ip in range(len(df_all)):
            lon, lat = transformer.transform(df_all.X[ip], df_all.Y[ip])
            point = Point((lon, lat))

            features_ero.append(
                Feature(
                    geometry=point,
                    properties={
                        "LocNr": int(ip),
                        "Lon": lon,
                        "Lat": lat,
                        "regime": int(df_all.erosionregime[ip]),
                    },
                )
            )

        # Save xbeach geojson file for erosion regimes
        if features_ero:
            feature_collection_ero = FeatureCollection(features_ero)
            output_path_regime = os.path.join(output_path, "erosionregimes\\")
            fo.mkdir(output_path_regime)
            file_name = os.path.join(output_path_regime, "erosionregimes.geojson.js")
            write_json_js(file_name, feature_collection_ero, "var regimes =")

            dct = {}
            dct["name"] = "erosion_regimes"
            dct["long_name"] = "Erosion regimes XBeach"
            dct["description"] = "These are the Erosion regimes"
            dct["format"] = "geojson"
            dct["legend"] = make_legend(type="erosion_regimes")

            self.map_variables.append(dct)

    def make_runup_map(self) -> None:
        """Make runup markers and timeseries for webviewer."""

        output_path = self.cycle_path

        # Extreme runup height

        for model in cosmos.scenario.model:
            if model.type == "beware":
                try:
                    if (
                        os.path.exists(
                            os.path.join(model.cycle_output_path, "beware_his.nc")
                        )
                        and not model.ensemble
                    ):
                        model.domain.read_data(
                            os.path.join(model.cycle_output_path, "beware_his.nc")
                        )

                        features = []
                        transformer = Transformer.from_crs(
                            model.crs, "WGS 84", always_xy=True
                        )

                        for ip in range(len(model.domain.filename)):
                            x, y = transformer.transform(
                                model.domain.xp[ip], model.domain.yp[ip]
                            )
                            point = Point((x, y))
                            name = "Loc nr: " + str(model.domain.filename[ip])

                            id = np.argmax(model.domain.R2[ip, :])
                            features.append(
                                Feature(
                                    geometry=point,
                                    properties={
                                        "model_name": model.name,
                                        "LocNr": int(model.domain.filename[ip]),
                                        "Lon": x,
                                        "Lat": y,
                                        "Setup": round(
                                            model.domain.R2_setup[ip, id], 2
                                        ),
                                        "Swash": round(model.domain.swash[ip, id], 2),
                                        "TWL": round(
                                            model.domain.R2[ip, id]
                                            + model.domain.WL[ip, id],
                                            2,
                                        ),
                                    },
                                )
                            )

                        if features:
                            feature_collection = FeatureCollection(features)
                            output_path_runup = os.path.join(
                                output_path, "extreme_runup_height\\"
                            )
                            fo.mkdir(output_path_runup)
                            file_name = os.path.join(
                                output_path_runup, "extreme_runup_height.geojson.js"
                            )
                            write_json_js(file_name, feature_collection, "var runup =")

                        dct = {}
                        dct["name"] = "extreme_runup_height"
                        dct["long_name"] = "Maximum Total Water Level (best track)"
                        dct["description"] = (
                            "These are the predicted total water levels"
                        )
                        dct["format"] = "geojson"
                        dct["infographic"] = "twl"

                        dct["legend"] = make_legend(type="run_up")

                        self.map_variables.append(dct)

                    # Probabilistic runup

                    if (
                        os.path.exists(
                            os.path.join(model.cycle_output_path, "beware_his.nc")
                        )
                        and model.ensemble
                    ):
                        model.domain.read_data(
                            os.path.join(model.cycle_output_path, "beware_his.nc"),
                            prcs=[5, 50, 95],
                        )

                        features = []
                        transformer = Transformer.from_crs(
                            model.crs, "WGS 84", always_xy=True
                        )

                        for ip in range(len(model.domain.filename)):
                            x, y = transformer.transform(
                                model.domain.xp[ip], model.domain.yp[ip]
                            )
                            point = Point((x, y))
                            name = "Loc nr: " + str(model.domain.filename[ip])

                            id = np.argmax(model.domain.R2[ip, :, 0])
                            features.append(
                                Feature(
                                    geometry=point,
                                    properties={
                                        "model_name": model.name,
                                        "LocNr": int(model.domain.filename[ip]),
                                        "Lon": x,
                                        "Lat": y,
                                        "Setup": round(
                                            model.domain.R2_setup_prc["95"][ip, id], 2
                                        ),
                                        "Swash": round(
                                            model.domain.swash[ip, id, 0], 2
                                        ),
                                        "TWL": round(
                                            model.domain.R2_prc["95"][ip, id]
                                            + model.domain.WL[ip, id, 0],
                                            2,
                                        ),
                                    },
                                )
                            )

                        if features:
                            feature_collection = FeatureCollection(features)
                            output_path_runup = os.path.join(
                                output_path, "extreme_runup_height_prc95\\"
                            )
                            fo.mkdir(output_path_runup)
                            file_name = os.path.join(
                                output_path_runup,
                                "extreme_runup_height_prc95.geojson.js",
                            )
                            write_json_js(
                                file_name, feature_collection, "var runup_prc95 ="
                            )

                        dct = {}
                        dct["name"] = "extreme_runup_height_prc95"
                        dct["long_name"] = (
                            "Maximum Total Water Level (95 % of ensemble)"
                        )
                        dct["description"] = (
                            "These are the predicted extreme run-up heights"
                        )
                        dct["format"] = "geojson"
                        dct["infographic"] = "twl"

                        dct["legend"] = make_legend(type="run_up")

                        self.map_variables.append(dct)

                    # Offshore water level and wave height
                    if not model.ensemble:
                        features = []

                        for ip in range(len(model.domain.filename)):
                            x, y = transformer.transform(
                                model.domain.xo[ip], model.domain.yo[ip]
                            )
                            point = Point((x, y))
                            name = "Loc nr: " + str(model.domain.filename[ip])

                            id = np.argmax(model.domain.R2[ip, :])
                            features.append(
                                Feature(
                                    geometry=point,
                                    properties={
                                        "model_name": model.name,
                                        "LocNr": int(model.domain.filename[ip]),
                                        "Lon": round(x, 3),
                                        "Lat": round(y, 3),
                                        "Hs": round(model.domain.Hs[ip, id], 2),
                                        "Tp": round(model.domain.Tp[ip, id], 1),
                                        "WL": round(model.domain.WL[ip, id], 2),
                                    },
                                )
                            )

                        if features:
                            feature_collection = FeatureCollection(features)
                            output_path_waves = os.path.join(
                                output_path, "extreme_sea_level_and_wave_height\\"
                            )
                            fo.mkdir(output_path_waves)
                            file_name = os.path.join(
                                output_path_waves,
                                "extreme_sea_level_and_wave_height.geojson.js",
                            )
                            write_json_js(file_name, feature_collection, "var swl =")

                        dct = {}
                        dct["name"] = "extreme_sea_level_and_wave_height"
                        dct["long_name"] = "Offshore WL and Hs"
                        dct["description"] = (
                            "This is the total offshore water level (tide + surge) and wave conditions."
                        )
                        dct["format"] = "geojson"
                        dct["legend"] = {
                            "text": "Offshore Hs",
                            "contours": [
                                {
                                    "text": " 0.0&nbsp-&nbsp;1.0&#8201;m",
                                    "color": "#CCFFFF",
                                },
                                {
                                    "text": " 1.0&nbsp;-&nbsp;3.0&#8201;m",
                                    "color": "#40E0D0",
                                },
                                {
                                    "text": " 3.0&nbsp-&nbsp;5.0&#8201;m",
                                    "color": "#00BFFF",
                                },
                                {"text": "&gt; 5.0&#8201;m", "color": "#0909FF"},
                            ],
                        }
                        dct["infographic"] = "offshore"

                        self.map_variables.append(dct)

                        # Horizontal runup

                        features = []

                        dfx = pd.read_csv(
                            os.path.join(model.path, "input", "runup.x"),
                            index_col=0,
                            sep=r"\s+",
                        )
                        dfy = pd.read_csv(
                            os.path.join(model.path, "input", "runup.y"),
                            index_col=0,
                            sep=r"\s+",
                        )
                        r2max = dfx.columns.values

                        for ip in range(len(model.domain.filename)):
                            name = "Loc nr: " + str(model.domain.filename[ip])

                            id = np.argmax(model.domain.R2[ip, :])

                            id2 = np.argwhere(
                                r2max.astype(float) >= model.domain.R2[ip, id]
                            )[0]

                            x, y = transformer.transform(
                                dfx[r2max[id2]].values[ip][0],
                                dfy[r2max[id2]].values[ip][0],
                            )
                            point = Point((x, y))

                            features.append(
                                Feature(
                                    geometry=point,
                                    properties={
                                        "model_name": model.name,
                                        "LocNr": int(model.domain.filename[ip]),
                                        "Lon": x,
                                        "Lat": y,
                                        "Setup": round(
                                            model.domain.R2_setup[ip, id], 2
                                        ),
                                        "Swash": round(model.domain.swash[ip, id], 2),
                                        "TWL": round(
                                            model.domain.R2[ip, id]
                                            + model.domain.WL[ip, id],
                                            2,
                                        ),
                                    },
                                )
                            )

                        if features:
                            feature_collection = FeatureCollection(features)
                            output_path_runup = os.path.join(
                                output_path, "extreme_horizontal_runup_height\\"
                            )
                            fo.mkdir(output_path_runup)
                            file_name = os.path.join(
                                output_path_runup,
                                "extreme_horizontal_runup_height.geojson.js",
                            )
                            write_json_js(
                                file_name, feature_collection, "var runup_vert ="
                            )

                        dct = {}
                        dct["name"] = "extreme_horizontal_runup_height"
                        dct["long_name"] = "Horizontal extent of Total Water Level"
                        dct["description"] = "This is the extreme horizontal runup."
                        dct["format"] = "geojson"
                        dct["infographic"] = "twl_hor"
                        dct["legend"] = make_legend(type="run_up")

                        self.map_variables.append(dct)

                except Exception:
                    cosmos.log("An error occurred when making BEWARE webviewer !")

    def make_twl_map(self) -> None:
        """Make SFINCS bathtub total water levels and timeseries for webviewer."""

        # Total water levels estimates (tide+surge+0.2*Hs)

        try:
            if not cosmos.config.run.bathtub:
                return

            output_path = self.cycle_path

            df_twl = None

            for model in cosmos.scenario.model:
                if model.type == "sfincs":
                    # Here we collect all the TWL points from all SFINCS models where they exceeded the threshold (HAT)
                    # Each SFINCS bathtub model make a csv file with all points that exceeded the threshold
                    # This happens in cosmos_sfincs.py -> post_process -> make_bathtub_csv
                    # The file sits in model.cycle_post_path/twl_points.csv

                    twl_file = os.path.join(model.cycle_post_path, "twl.csv")

                    if os.path.exists(twl_file):
                        df_twl0 = pd.read_csv(twl_file)
                        if df_twl is None:
                            df_twl = df_twl0
                        else:
                            df_twl = pd.concat([df_twl, df_twl0], ignore_index=True)

            # We now hopefully (depending on whether you enjoy coastal flooding or not) have a dataframe with all TWL points from all SFINCS bathtub models
            if df_twl is not None:
                features = []
                # Loop through rows in df_twl
                for ip in range(len(df_twl)):
                    lon = df_twl.longitude[ip]
                    lat = df_twl.latitude[ip]
                    point = Point((lon, lat))
                    features.append(
                        Feature(
                            geometry=point,
                            properties={
                                "model_name": df_twl.model[ip],
                                "station_name": df_twl.station[ip],
                                "lon": round(lon, 3),
                                "lat": round(lat, 3),
                                "TWL": round(df_twl.twl[ip], 2),
                                "HAT": round(df_twl.hat[ip], 2),
                                "TWLminusHAT": round(
                                    df_twl.twl[ip] - df_twl.hat[ip], 2
                                ),
                            },
                        )
                    )

                feature_collection = FeatureCollection(features)
                file_name = os.path.join(
                    output_path, "estimated_total_water_level.geojson.js"
                )
                write_json_js(file_name, feature_collection, "var etwl =")

                dct = {}
                dct["name"] = "estimated_total_water_level"
                dct["long_name"] = "Estimated Total Water Level"
                dct["description"] = (
                    "These are the estimated maximum total water levels."
                )
                dct["format"] = "geojson"
                dct["infographic"] = "twl_bathtub"

                dct["legend"] = make_legend(type="height_above_hat")

                self.map_variables.append(dct)

        except Exception as e:
            cosmos.log("An error occurred when making BEWARE webviewer !")

    def make_timeseries(self, ts_type: str) -> None:
        """Generic function to make time series for the webviewer."""
        if ts_type == "waves":
            prefix = "waves"
            station_type = "wave_buoy"
            var_string = "hm0,tp"
            station_file = "wavebuoys.geojson.js"
            station_var = "buoys"
        elif ts_type == "wl":
            prefix = "wl"
            station_type = "tide_gauge"
            var_string = "wl"
            station_file = "stations.geojson.js"
            station_var = "stations"
        elif ts_type == "twl":
            prefix = "wl"
            station_type = "twl_gauge"
            var_string = "wl"
            station_file = None
            station_var = None

        features = []

        tide_dataset_loaded = False

        for model in cosmos.scenario.model:
            # For tide only, we do not put any time series in the web viewer
            if model.role == "tide_only":
                # On to the next model
                continue

            if model.station:
                for station in model.station:
                    cmp_file = None
                    obs_file = None
                    prd_file = None

                    if station.type == station_type:
                        pass

                    if station.type == station_type and station.upload:
                        if station_type == "twl_gauge":
                            # We only upload TWL stations when TWL exceeds threshold
                            # Therefore check if the file even exists
                            fname = os.path.join(
                                model.cycle_post_path, f"wl.{station.name}.csv"
                            )
                            if not os.path.exists(fname):
                                continue

                        point = Point((station.longitude, station.latitude))
                        if station.id:
                            name = station.long_name + " (" + str(station.id) + ")"
                        else:
                            name = station.long_name

                        path = cosmos.scenario.path
                        t0 = cosmos.cycle - datetime.timedelta(hours=48)
                        t1 = cosmos.cycle
                        t0_obs = t0
                        t1_obs = cosmos.stop_time

                        # Merge time series from previous cycles
                        v = merge_timeseries(
                            path,
                            model.name,
                            station.name,
                            prefix,
                            t0=t0.replace(tzinfo=None),
                            t1=t1.replace(tzinfo=None),
                        )

                        # Check if merge returned values
                        if v is not None:
                            # Correct to MSL if necessary
                            if ts_type == "wl":
                                v += model.vertical_reference_level_difference_with_msl
                            # Write csv js file
                            cmp_file = (
                                prefix
                                + "."
                                + station.name
                                + "."
                                + model.name
                                + ".csv.js"
                            )
                            csv_file = os.path.join(
                                self.cycle_path, "timeseries", cmp_file
                            )
                            s = v.to_csv(
                                date_format="%Y-%m-%dT%H:%M:%S",
                                float_format="%.3f",
                                header=False,
                            )

                            if model.ensemble:
                                if ts_type == "waves":
                                    var_string2 = "hm0_0,tp_0,hm0_0,tp_0,hm0_100,tp_100"
                                elif ts_type == "wl":
                                    var_string2 = "wl_0,wl_50,wl_100,wl_best_track"
                            else:
                                var_string2 = var_string
                            write_csv_js(
                                csv_file, s, "var csv = `date_time," + var_string2
                            )

                        # Check if there are observations
                        if cosmos.scenario.observations_path and station.id:
                            obs_pth = os.path.join(
                                cosmos.config.path.main,
                                "observations",
                                cosmos.scenario.observations_path,
                                ts_type,
                            )
                            csv_file = ts_type + "." + station.id + ".observed.csv.js"
                            if os.path.exists(os.path.join(obs_pth, csv_file)):
                                # Read in csv file to a dataframe
                                df = pd.read_csv(
                                    os.path.join(obs_pth, csv_file),
                                    index_col=0,
                                    parse_dates=True,
                                    skipfooter=1,
                                )
                                # Cut off time series to same time as model
                                mask = (
                                    df.index
                                    >= t0_obs.replace(tzinfo=None)
                                    - datetime.timedelta(hours=1)
                                ) & (
                                    df.index
                                    <= t1_obs.replace(tzinfo=None)
                                    + datetime.timedelta(hours=1)
                                )
                                df = df.loc[mask]
                                # Check if df is not empty
                                if not df.empty:
                                    # Convert to csv
                                    s = df.to_csv(
                                        date_format="%Y-%m-%dT%H:%M:%S",
                                        float_format="%.3f",
                                        header=False,
                                    )
                                    # Write csv js file
                                    obs_file = csv_file
                                    write_csv_js(
                                        os.path.join(
                                            self.cycle_path, "timeseries", obs_file
                                        ),
                                        s,
                                        "var csv = `date_time," + var_string,
                                    )

                        # Check if we need to make tidal predictions (right now, this only works for IHO stations!)
                        if ts_type == "wl" and station.iho_id is not None:
                            # Make tidal predictions
                            prd_file = "wl." + station.name + ".predicted.csv.js"
                            t0 = cosmos.cycle - datetime.timedelta(days=3)
                            t1 = cosmos.stop_time + datetime.timedelta(days=1)
                            # Remove time zone from t0
                            t0 = t0.replace(tzinfo=None)
                            if not tide_dataset_loaded:
                                # Load the tide dataset only once
                                tide_stations_path = os.path.join(
                                    cosmos.config.path.main,
                                    "configuration",
                                    "data",
                                    "tide_stations",
                                    "iho",
                                )
                                tide_dataset = TideStationsDataset(
                                    "iho", tide_stations_path
                                )
                                tide_dataset_loaded = True
                            prd = tide_dataset.predict(
                                name=station.iho_id, start=t0, end=t1
                            )
                            if prd is not None:
                                s = prd.to_csv(
                                    date_format="%Y-%m-%dT%H:%M:%S",
                                    float_format="%.3f",
                                    header=False,
                                )
                                write_csv_js(
                                    os.path.join(
                                        self.cycle_path, "timeseries", prd_file
                                    ),
                                    s,
                                    "var csvprd = `date_time,wl",
                                )

                        if cmp_file or obs_file:
                            features.append(
                                Feature(
                                    geometry=point,
                                    properties={
                                        "name": station.name,
                                        "long_name": name,
                                        "id": station.id,
                                        "model_name": model.name,
                                        "model_type": model.type,
                                        "model_ensemble": model.ensemble,
                                        "mllw": station.mllw,
                                        "cycle": cosmos.cycle_string,
                                        "cmp_file": cmp_file,
                                        "obs_file": obs_file,
                                        "prd_file": prd_file,
                                    },
                                )
                            )
        if features and station_file is not None:
            feature_collection = FeatureCollection(features)
            buoys_file = os.path.join(self.cycle_path, station_file)
            write_json_js(buoys_file, feature_collection, "var " + station_var + " =")

    def update_scenarios_js(self, other_js_source: str = None) -> None:
        # Check if there is a scenarios.js file
        # If so, append it with the current scenario

        cosmos.log("Updating scenario.js ...")

        if other_js_source:
            sc_file = os.path.join(other_js_source)
        else:
            sc_file = os.path.join(self.path, "data", "scenarios.js")

        isame = -1
        cosmos.log("Updating scenario file : " + sc_file)
        if fo.exists(sc_file):
            scs = read_json_js(sc_file)
            for isc, sc in enumerate(scs):
                if sc["name"] == cosmos.scenario.name:
                    isame = isc
        else:
            scs = []

        # # Read meteo source from csv file
        # csv_path = os.path.join(cosmos.scenario.cycle_path, "meteo_sources.csv")
        # meteo_source = pd.read_csv(csv_path)
        # meteo_string = "_".join(meteo_source.values[-1][0].split("_")[:-1])

        # Find previous cycles
        if cosmos.config.run.run_mode == "cloud":
            # Find previous cycles in cloud
            bucket_name = "cosmos.deltares.nl"
            prefix = self.name + "/data/" + cosmos.scenario.name
            previous_cycles = cosmos.cloud.list_folders(bucket_name, prefix)
            # If the last cycle is not equal to the current cycle, add it to the list (this should not be necessary)
            if previous_cycles[-1] != cosmos.cycle_string:
                previous_cycles.append(cosmos.cycle_string)
        else:
            # Find previous cycles locally
            scenario_path = os.path.join(self.path, "data", cosmos.scenario.name)
            previous_cycles = fo.list_folders(
                os.path.join(scenario_path, "*"), basename=True
            )

        previous_cycles = sorted(previous_cycles, reverse=True)

        # Current scenario
        newsc = {}
        newsc["name"] = cosmos.scenario.name
        newsc["long_name"] = cosmos.scenario.long_name
        newsc["description"] = cosmos.scenario.description
        newsc["lon"] = cosmos.scenario.lon
        newsc["lat"] = cosmos.scenario.lat
        newsc["zoom"] = cosmos.scenario.zoom
        newsc["cycle"] = cosmos.cycle.strftime("%Y-%m-%dT%H:%M:%S")
        newsc["cycle_string"] = cosmos.cycle_string
        newsc["cycle_mode"] = cosmos.config.run.mode
        newsc["meteo_string"] = cosmos.scenario.meteo_string
        newsc["duration"] = str(cosmos.scenario.runtime)
        now = datetime.datetime.now(datetime.timezone.utc)
        newsc["last_update"] = now.strftime("%Y/%m/%d %H:%M:%S" + " (UTC)")
        newsc["previous_cycles"] = previous_cycles
        if isame > -1:
            # Scenario already existed in web viewer
            scs[isame] = newsc
        else:
            # New scenario in web viewer
            scs.append(newsc)

        write_json_js(sc_file, scs, "var scenario =")

    def upload(self) -> None:
        if cosmos.config.run.run_mode == "cloud":
            # Upload to S3
            self.upload_to_s3()

        elif cosmos.config.run.run_mode == "parallel":
            self.copy_to_opendap()

        elif cosmos.config.run.run_mode == "serial":  # Test
            self.copy_to_opendap()

        else:
            self.upload_to_opendap()

    def upload_to_opendap(self) -> None:
        """Upload web viewer to web server."""
        from cht_utils.sftp import SSHSession

        cosmos.log("Uploading web viewer to OpenDap ...")
        # Upload entire copy of local web viewer to web server
        try:
            f = SSHSession(
                cosmos.config.webserver.hostname,
                username=cosmos.config.webserver.username,
                password=cosmos.config.webserver.password,
            )
        except Exception:
            cosmos.log("Error! Could not connect to sftp server !")
            return

        try:
            # Check if web viewer already exist
            make_wv_on_ftp = False
            if not self.exists:
                # Web viewer does not even exist locally
                make_wv_on_ftp = True
            else:
                # Check if web viewer exists on FTP
                if self.name not in f.sftp.listdir(cosmos.config.webserver.path):
                    make_wv_on_ftp = True

            if make_wv_on_ftp:
                # Copy entire webviewer
                f.put_all(self.path, cosmos.config.webserver.path)

            else:
                # Webviewer already on ftp server

                remote_path = cosmos.config.webserver.path + "/" + self.name + "/data"
                # Check if scenario is already on ftp server
                cosmos.log("Removing existing data on web server ...")
                if cosmos.scenario.name in f.sftp.listdir(remote_path):
                    f.rmtree(remote_path + "/" + cosmos.scenario.name)

                # Copy scenarios.js
                remote_file = remote_path + "/scenarios.js"
                local_file = os.path.join(".", "scenarios.js")
                f.get(remote_file, local_file)
                self.update_scenarios_js(local_file)
                # Copy new scenarios.js to server
                f.put(local_file, remote_path + "/scenarios.js")
                # Delete local scenarios.js
                fo.rm(local_file)

                # Copy scenario data to server
                cosmos.log("Uploading all data to web server ...")
                f.put_all(self.cycle_path, remote_path)

            f.sftp.close()

            cosmos.log("Done uploading.")

        except BaseException as e:
            cosmos.log("An error occurred while uploading !")
            cosmos.log(str(e))

            try:
                f.sftp.close()
            except Exception:
                pass

    def copy_to_opendap(self) -> None:
        cosmos.log("Copying webviewer to OpenDap ...")

        # Upload entire copy of local web viewer to web server
        try:
            # Check if web viewer already exist
            make_wv_on_ftp = False
            if not self.exists:
                # Web viewer does not even exist locally
                make_wv_on_ftp = True
            else:
                # Check if web viewer exists on FTP
                if self.name not in os.listdir(cosmos.config.webserver.path):
                    make_wv_on_ftp = True

            if make_wv_on_ftp:
                # Copy entire webviewer
                shutil.copytree(self.path, cosmos.config.webserver.path)
            else:
                # Webviewer already on ftp server

                # Only copy scenario output
                remote_path = os.path.join(
                    cosmos.config.webserver.path, self.name, "data"
                )

                # Check if scenario is already on ftp-server

                if os.path.exists(os.path.join(remote_path, cosmos.scenario.name)):
                    # Check if scenario-cycle is already on ftp server
                    if cosmos.cycle_string in os.listdir(
                        os.path.join(remote_path, cosmos.scenario.name)
                    ):
                        cosmos.log(
                            "Removing cycle {} from web server ...".format(
                                cosmos.cycle_string
                            )
                        )
                        shutil.rmtree(
                            os.path.join(
                                remote_path, cosmos.scenario.name, cosmos.cycle_string
                            )
                        )

                # Copy scenarios.js
                remote_file = os.path.join(remote_path, "scenarios.js")
                local_file = os.path.join(".", "scenarios.js")

                # Update scenarios.js (new cycle_string)
                shutil.copyfile(remote_file, local_file)
                self.update_scenarios_js(local_file)

                # Copy scenario data to server
                cosmos.log("Uploading all data to web server ...")
                shutil.copytree(
                    self.cycle_path,
                    os.path.join(
                        remote_path, cosmos.scenario.name, cosmos.cycle_string
                    ),
                )

                # Copy new scenarios.js to server
                shutil.copyfile(local_file, remote_file)
                # Delete local scenarios.js
                fo.rm(local_file)

            cosmos.log("Done copying to web server ")

            # Get list of all cycles in scneario folder
            cycle_list = fo.list_folders(
                os.path.join(remote_path, cosmos.scenario.name, "*z")
            )
            tkeep = cosmos.cycle.replace(tzinfo=None) - datetime.timedelta(
                hours=cosmos.config.run.prune_after_hours
            )
            for cycle in cycle_list:
                cycle_time = datetime.datetime.strptime(cycle[-12:], "%Y%m%d_%Hz")
                if cycle_time < tkeep:
                    cosmos.log(
                        "Removing old cycle {} from web server ...".format(cycle)
                    )
                    fo.rmdir(cycle)

        except BaseException as e:
            cosmos.log("An error occurred while copying !")
            cosmos.log(str(e))

    def upload_to_s3(self) -> None:
        """Upload web viewer to S3"""
        cosmos.log("Uploading web viewer to S3 ...")
        try:
            # Upload entire copy of local web viewer to web server
            bucket_name = "cosmos.deltares.nl"
            local_folder = self.cycle_path
            s3_folder = (
                self.name
                + "/"
                + "data"
                + "/"
                + cosmos.scenario.name
                + "/"
                + cosmos.cycle_string
            )
            cosmos.cloud.upload_folder(bucket_name, local_folder, s3_folder, quiet=True)
            # Upload scenarios.js
            local_file = os.path.join(self.path, "data", "scenarios.js")
            s3_folder = self.name + "/" + "data"
            cosmos.cloud.upload_file(bucket_name, local_file, s3_folder)
        except BaseException as e:
            cosmos.log("An error occurred while uploading !")
            cosmos.log(str(e))

    def merge_map_tiles(self) -> None:
        """Merge output map-tiles from different models for web viewer.
        For now only used in run_mode==cloud"""

        cosmos.log("Merging output tiles ...")

        # settings
        bucket_name = "cosmos-scenarios"
        output_bucket_name = "cosmos.deltares.nl"

        variables = set()
        # create a set of all available variables to be merged
        for model in cosmos.scenario.model:
            # tiles are kept separately per model in the cloud, check if they exist
            s3_key = cosmos.scenario_name + "/models/" + model.name + "/tiles"
            if cosmos.cloud.check_folder_exists(bucket_name, s3_key):
                # list all files
                files = cosmos.cloud.list_files(bucket_name, s3_key)
                # only keep .tgz files and remove the path
                tgz_files = [os.path.basename(f) for f in files if f.endswith(".tgz")]
                # strip extension
                tgz_files = [f.replace(".tgz", "") for f in tgz_files]
                # keepp unique variables
                variables.update(tgz_files)

        # create a cloud configuration for the individual files
        config = {}
        config["cloud"] = {}
        config["cloud"]["host"] = cosmos.config.cloud_config.host
        config["cloud"]["access_key"] = cosmos.config.cloud_config.access_key
        config["cloud"]["secret_key"] = cosmos.config.cloud_config.secret_key
        config["cloud"]["region"] = cosmos.config.cloud_config.region
        config["cloud"]["token"] = cosmos.config.cloud_config.token
        config["cloud"]["namespace"] = cosmos.config.cloud_config.namespace

        # settings
        config["cloud"]["s3_bucket"] = bucket_name
        config["cloud"]["output_s3_bucket"] = output_bucket_name
        config["cloud"]["webviewer_folder"] = cosmos.config.webviewer.name + "/data"
        config["cloud"]["scenario"] = cosmos.scenario_name
        config["cloud"]["cycle"] = cosmos.cycle_string

        # make a list of jobs
        jobs = []
        # Loop through all variables
        for variable in variables:
            job_path = cosmos.scenario.cycle_path + "/" + "tile_jobs"
            fo.mkdir(job_path)

            # Add variable to config
            config["variable"] = {}
            config["variable"]["name"] = variable

            # Create a job-folder with python script and config file
            dict2yaml(os.path.join(job_path, "config.yml"), config)
            fo.copy_file(
                os.path.join(os.path.dirname(__file__), "cosmos_merge_tiles.py"),
                os.path.join(job_path, "merge_tiles.py"),
            )

            # Upload "jobs" to s3
            s3key = cosmos.scenario.name + "/" + "tile_jobs" + "/" + variable
            # Delete existing folder
            cosmos.cloud.delete_folder(config["cloud"]["s3_bucket"], s3key)
            # Upload job folder to cloud storage
            cosmos.cloud.upload_folder(config["cloud"]["s3_bucket"], job_path, s3key)

            # Submit job to Argo
            cloud_job = cosmos.argo.submit_template_job(
                workflow_name="merge-tiles-variable",
                job_name=variable,
                subfolder=s3key,
                scenario=config["cloud"]["scenario"],
                cycle=config["cloud"]["cycle"],
                webviewerfolder=cosmos.config.webviewer.name + "/data",
            )

            jobs.append(cloud_job)

        # Wait for all jobs to finish before finishing the webviewer
        okay = False
        while not okay:
            # Check every minute
            time.sleep(60)
            okay = True
            for job in jobs:
                status = Argo.get_task_status(job)
                if status == "Running":
                    okay = False
                    # Break out of for loop
                    break


def merge_timeseries(
    path, model_name, station, prefix, t0=None, t1=None, resample=None
):

    name_str = prefix
    available_times = []
    cycle_list = fo.list_folders(os.path.join(path, "*z"))
    for it, cycle_string in enumerate(cycle_list):
        available_times.append(
            datetime.datetime.strptime(cycle_list[it][-12:], "%Y%m%d_%Hz")
        )
    if t0 is None or t1 is None:
        t0 = available_times[0]
        t1 = available_times[-1]

    # New pandas series
    vv = pd.Series([0.0], index=[pd.Timestamp("2100-01-01")])
    vv.index.name = "date_time"
    vv.name = name_str
    okay = False
    for it, t in enumerate(available_times):
        if t >= t0 and t <= t1:
            csv_file = os.path.join(
                path,
                cycle_list[it][-12:],
                "models",
                model_name,
                "timeseries",
                prefix + "." + station + ".csv",
            )
            if os.path.exists(csv_file):
                df = pd.read_csv(
                    csv_file, header=0, index_col=0, parse_dates=True
                ).squeeze()
                # if column is named wl_5, rename it to wl_0
                # check if model name ends with ensemble
                if model_name.endswith("ensemble"):
                    if "wl_5" in df:
                        df.rename(columns={"wl_5": "wl_0"}, inplace=True)
                    # if column is named wl_95, rename it to wl_100
                    if "wl_95" in df:
                        df.rename(columns={"wl_95": "wl_100"}, inplace=True)
                # if "columns" in df:
                #     if "wl_5" in df.columns:
                #         df.rename(columns={"wl_5":"wl_0"}, inplace=True)
                #     # if column is named wl_95, rename it to wl_100
                #     if "wl_95" in df.columns:
                #         df.rename(columns={"wl_95":"wl_100"}, inplace=True)
                df.index.name = "date_time"
                df.name = name_str
                okay = True
                # Find last time in merged time series that is smaller than first time in new timeseries
                ilast = np.where(vv.index < df.index[0])[-1]
                if ilast.any():
                    ilast = ilast[-1]
                    vv = vv[0:ilast]
                    vv = pd.concat([vv, df])
                else:
                    vv = df

    if okay:
        if resample:
            t0 = (vv.index - vv.index[0]).total_seconds()
            t1 = np.arange(0.0, t0[-1], resample)
            f = interpolate.interp1d(t0, vv)
            v1 = f(t1)
            t1 = vv.index[0] + t1 * datetime.timedelta(seconds=1)
            vv = pd.Series(v1, index=t1)
            vv.index.name = "date_time"
            vv.name = name_str
    if okay:
        return vv
    else:
        return None


def make_legend(type: str = None, mp=None) -> str:
    if type:
        mp = next(
            (
                cosmos.config.map_contours[x]
                for x in cosmos.config.map_contours
                if x == type
            ),
            None,
        )

    lgn = {}
    lgn["text"] = mp["string"]

    cntrs = mp["contours"]

    contours = []

    for cntr in cntrs:
        contour = {}
        contour["text"] = cntr["string"]
        contour["color"] = "#" + cntr["hex"]
        contours.append(contour)

    lgn["contours"] = contours

    return lgn
