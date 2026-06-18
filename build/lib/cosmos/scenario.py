"""Scenario configuration and model initialization for CoSMoS.

Reads scenario TOML files and sets up the collection of nested models,
clusters, and timing parameters that define a forecast scenario.
"""

import os

import toml

from .cluster import Cluster, cluster_dict
from .cosmos import cosmos


class Scenario:
    """Scenario class to read scenario file and initialize models.

    See Also
    ----------
    cosmos.MainLoop
    cosmos.ModelLoop
    cosmos.Model

    """

    def __init__(self, name: str) -> None:
        """Initialize cosmos scenario.

        Parameters
        ----------
        name : str
            Name of scenario to be executed.
        """

        self.name = name
        self.model = []
        self.long_name = name
        self.description = name
        self.cycle = None
        # Why do we need these from the web viewer again in the scenario object?
        self.lon = cosmos.config.webviewer.lon
        self.lat = cosmos.config.webviewer.lat
        self.zoom = cosmos.config.webviewer.zoom
        self.path = None
        self.cycle_path = None
        self.tile_path = None
        self.job_list_path = None
        self.restart_path = None
        self.last_cycle = None
        self.cyclone_track = None
        self.tropical_cyclone = None
        self.track_ensemble = None
        self.track_ensemble_nr_realizations = (
            cosmos.config.track_ensemble.nr_realizations
        )
        self.ensemble_models = cosmos.config.run.ensemble_models
        self.meteo_dataset = None
        self.meteo_spiderweb = None
        self.meteo_wind = True
        self.meteo_atmospheric_pressure = True
        self.meteo_precipitation = True
        self.meteo_track = None
        self.cyclone_track_forecast_source = None
        self.observations_path = ""
        self.run_ensemble = False  # Move this to config.run?
        self.meteo_string = ""
        self.storm_number = None
        # Per-member ensemble mode: when the meteo dataset's cycle folder
        # contains one subdir per ensemble member (each with its own gridded
        # nc files + <member>.cyc track), CoSMoS produces a per-member spw
        # AND per-member amu/amv from THAT member's gridded data. Detected
        # at runtime by `detect_meteo_ensemble_mode()`; the last (sorted)
        # member also acts as the deterministic best track.
        self.meteo_ensemble_mode = False
        self.ensemble_names = []
        self.meteo_ensemble_deterministic = None  # last-sorted member name

    def read(self) -> None:
        """Read scenario file, set model paths and settings, initialize models and read model generic and model specific data."""

        # Read scenario file
        cosmos.log("Reading scenario file ...")
        self.path = os.path.join(cosmos.config.path.scenarios, self.name)
        scenario_file = os.path.join(self.path, "scenario.toml")

        if not os.path.exists(self.path):
            cosmos.stop(
                f"Scenario folder not found: {self.path}\n"
                f"  Make sure a folder named '{self.name}' exists under: {cosmos.config.path.scenarios}"
            )
        if not os.path.exists(scenario_file):
            cosmos.stop(
                f"Scenario file not found: {scenario_file}\n"
                f"  Each scenario folder must contain a 'scenario.toml' file."
            )

        try:
            sc_dict = toml.load(scenario_file)
        except toml.TomlDecodeError as e:
            cosmos.stop(f"Failed to parse scenario file {scenario_file}: {e}")

        # Turn into object
        for key, value in sc_dict.items():
            if key == "model" or key == "cluster":
                pass
            else:
                setattr(self, key, value)

        # First find all the models and store in dict models_in_scenario
        models_in_scenario = {}
        if "model" not in sc_dict:
            cosmos.stop(
                f"No [[model]] entries found in scenario file: {scenario_file}\n"
                f"  At least one [[model]] section is required."
            )
        for mdl in sc_dict["model"]:
            # Add the models in this scenario
            if "name" in mdl:
                # Individual model
                name = mdl["name"].lower()
                if name not in cosmos.all_models:
                    cosmos.stop(
                        f"Model '{name}' not found in model database.\n"
                        f"  Check that a folder named '{name}' exists in: {cosmos.config.model_database.path}\n"
                        f"  Available models: {', '.join(sorted(cosmos.all_models.keys()))}"
                    )
                models_in_scenario[name] = cosmos.all_models[name]
                # Set meteo to one give in scenario
                models_in_scenario[name]["meteo_dataset"] = self.meteo_dataset
                models_in_scenario[name]["meteo_spiderweb"] = self.meteo_spiderweb
                models_in_scenario[name]["meteo_track"] = self.meteo_track
                # But override is separate dataset is provided for model
                if "meteo_dataset" in mdl:
                    models_in_scenario[name]["meteo_dataset"] = mdl["meteo_dataset"]
                if "meteo_spiderweb" in mdl:
                    models_in_scenario[name]["meteo_spiderweb"] = mdl["meteo_spiderweb"]
                if "meteo_track" in mdl:
                    models_in_scenario[name]["meteo_track"] = mdl["meteo_track"]

            else:
                # Model by region and type
                # First make list of all regions to include
                region_list = ["empty"]  # List of regions
                type_list = ["empty"]  # List of types

                if "type" in mdl:
                    type_list = mdl["type"]
                if "region" in mdl:
                    region_list.append(mdl["region"])
                if "super_region" in mdl:
                    super_region_name = mdl["super_region"].lower()
                    for region in cosmos.config.super_region[super_region_name][
                        "region"
                    ]:
                        # Avoid duplicates
                        if region not in region_list:
                            region_list.append(region)

                # Loop through all available models
                for name in cosmos.all_models.keys():
                    if any(
                        cosmos.all_models[name]["region"] == item
                        for item in region_list
                    ):
                        if cosmos.all_models[name]["type"] in type_list:
                            models_in_scenario[name] = cosmos.all_models[name]
                            # Set meteo to one give in scenario
                            models_in_scenario[name]["meteo_dataset"] = (
                                self.meteo_dataset
                            )
                            models_in_scenario[name]["meteo_spiderweb"] = (
                                self.meteo_spiderweb
                            )
                            models_in_scenario[name]["meteo_track"] = self.meteo_track
                            # But override is separate dataset is provided for model
                            if "meteo_dataset" in mdl:
                                models_in_scenario[name]["meteo_dataset"] = mdl[
                                    "meteo_dataset"
                                ]
                            if "meteo_spiderweb" in mdl:
                                models_in_scenario[name]["meteo_spiderweb"] = mdl[
                                    "meteo_spiderweb"
                                ]
                            if "meteo_track" in mdl:
                                models_in_scenario[name]["meteo_track"] = mdl[
                                    "meteo_track"
                                ]

        ### Add missing models
        # We know which models need to be added. Check if all models that provide boundary conditions are there as well.
        # TO DO: the above ...

        ### Clear model list
        self.model = []

        # Loop through models in scenario
        for name in models_in_scenario.keys():
            tp = models_in_scenario[name]["type"]

            # Initialize models
            if tp.lower() == "ww3":
                from cosmos.ww3 import CoSMoS_WW3

                model = CoSMoS_WW3()
                model.wave = True
            elif tp.lower() == "hurrywave":
                from cosmos.hurrywave import CoSMoS_HurryWave

                model = CoSMoS_HurryWave()
                model.wave = True
            elif tp.lower() == "sfincs":
                from cosmos.sfincs import CoSMoS_SFINCS

                model = CoSMoS_SFINCS()
                model.flow = True
            elif tp.lower() == "delft3dfm":
                from cosmos.delft3dfm import CoSMoS_Delft3DFM

                model = CoSMoS_Delft3DFM()
                model.flow = True
            elif tp.lower() == "xbeach":
                from cosmos.xbeach import CoSMoS_XBeach

                model = CoSMoS_XBeach()
                model.wave = True
                model.flow = True
            elif tp.lower() == "beware":
                from cosmos.beware import CoSMoS_BEWARE

                model = CoSMoS_BEWARE()
                model.wave = True
                model.flow = True

            # Set model paths
            # Path where model sits in model database
            region = models_in_scenario[name]["region"]
            vsn = "001"

            model_path = os.path.join(
                cosmos.config.model_database.path, region, tp, name
            )
            file_name = os.path.join(model_path, "model.toml")

            # Path in model database
            model.path = model_path
            model.name = name
            model.deterministic_name = name
            model.version = vsn
            model.region = region
            model.file_name = file_name
            model.type = tp

            model.meteo_dataset = models_in_scenario[name]["meteo_dataset"]
            model.meteo_spiderweb = models_in_scenario[name]["meteo_spiderweb"]
            model.meteo_track = models_in_scenario[name]["meteo_track"]

            # If wind/pressure/rain are actively turned off in scenario, also do it here
            if not self.meteo_wind and model.meteo_wind:
                model.meteo_wind = False
            if not self.meteo_atmospheric_pressure and model.meteo_atmospheric_pressure:
                model.meteo_atmospheric_pressure = False
            if not self.meteo_precipitation and model.meteo_precipitation:
                model.meteo_precipitation = False
            if not self.meteo_dataset and not model.meteo_dataset:
                model.meteo_wind = False
                model.meteo_atmospheric_pressure = False
                model.meteo_precipitation = False

            model.flow_start_time = None
            model.flow_stop_time = None

            model.tide = True

            # Read in model generic data (from toml file)
            model.read_generic()

            # Read in model specific data (input files)
            # Should move this bit to pre-processing of model
            model.read_model_specific()

            # Find matching meteo dataset
            if model.meteo_dataset:
                # Loop through all available meteo datasets
                for (
                    dataset_name,
                    meteo_dataset,
                ) in cosmos.meteo_database.dataset.items():
                    if dataset_name == model.meteo_dataset:
                        model.meteo_dataset = meteo_dataset
                        break

            # Get stations to add from scenario
            if "station" in sc_dict:
                for station in sc_dict["station"]:
                    toml_file_name = station["name"]  # toml file name
                    if "model_type" in station:
                        mdltype = station["model_type"]
                        if tp.lower() in mdltype:
                            model.station.append(toml_file_name)
                            model.add_stations()
                    if "model_name" in station:
                        mdlname = station["model_name"]
                        if name.lower() in mdlname:
                            model.station.append(toml_file_name)
                            model.add_stations()

            self.model.append(model)

        # Add models to clusters
        if "cluster" in sc_dict:
            for cld in sc_dict["cluster"]:
                cl = Cluster(name=cld["name"])
                if "run_condition" in cld:
                    cl.run_condition = cld["run_condition"]
                if "topn" in cld:
                    cl.topn = cld["topn"]
                if "hm0fac" in cld:
                    cl.hm0fac = cld["hm0fac"]
                if "boundary_twl_margin" in cld:
                    cl.boundary_twl_margin = cld["boundary_twl_margin"]
                if "use_threshold" in cld:
                    if cld["use_threshold"] == "y":
                        cl.use_threshold = True
                    else:
                        cl.use_threshold = False
                if cl.run_condition == "topn":
                    cl.ready = False
                # Add models to this cluster
                region_list = []  # List of regions
                type_list = []  # List of types
                if "region" in cld:
                    for region in cld["region"]:
                        if region not in region_list:
                            region_list.append(region)
                if "type" in cld:
                    for tp in cld["type"]:
                        type_list.append(tp)
                if "super_region" in cld:
                    super_region_name = cld["super_region"].lower()
                    for region in cosmos.config.super_region[super_region_name][
                        "region"
                    ]:
                        if region not in region_list:
                            region_list.append(region)

                # Loop through all available models
                for model in self.model:
                    okay = True
                    if type_list:
                        if model.type not in type_list:
                            okay = False
                            continue
                    if not model.flow_nested_name and not model.wave_nested_name:
                        okay = False
                        continue
                    # Filter by region
                    if region_list:
                        if model.region not in region_list:
                            # Region of this model is not in region_list
                            okay = False
                            continue
                    # Filter by type
                    if okay:
                        cl.add_model(model)

                cluster_dict[cld["name"]] = cl

        cosmos.log("Finished reading scenario")

    def set_paths(self) -> None:
        """Set cycle paths."""
        self.cycle_path = os.path.join(self.path, cosmos.cycle_string)
        self.cycle_models_path = os.path.join(self.path, cosmos.cycle_string, "models")
        self.cycle_tiles_path = os.path.join(self.path, cosmos.cycle_string, "tiles")
        self.cycle_job_list_path = os.path.join(
            self.path, cosmos.cycle_string, "job_list"
        )
        self.cycle_track_ensemble_path = os.path.join(
            self.path, cosmos.cycle_string, "track_ensemble"
        )
        self.cycle_track_ensemble_cyc_path = os.path.join(
            self.path, cosmos.cycle_string, "track_ensemble", "cyc"
        )
        self.cycle_track_ensemble_spw_path = os.path.join(
            self.path, cosmos.cycle_string, "track_ensemble", "spw"
        )
        self.cycle_track_spw_path = os.path.join(
            self.path, cosmos.cycle_string, "track"
        )
        self.restart_path = os.path.join(self.path, "restart")
        self.timeseries_path = os.path.join(self.path, "timeseries")
        self.cycle_timeseries_path = os.path.join(
            self.path, "timeseries", cosmos.cycle_string
        )

    def detect_meteo_ensemble_mode(self) -> None:
        """Detect whether the meteo dataset for this cycle is laid out per
        ensemble member.

        Layout we accept:
            <meteo_db>/<dataset>/<cycle>/<member>/
                <member>.cyc                    # member's track
                <member>.YYYYMMDD_HHMM.nc ...   # member's gridded forcing

        When present, set ``self.meteo_ensemble_mode = True``, populate
        ``self.ensemble_names`` from the (sorted) subdir names, and pick the
        last one as the deterministic best track. Otherwise leaves the flag
        ``False`` so the existing flat-layout flow is used.

        Called from main_loop after cycle + meteo_database are known.
        """
        self.meteo_ensemble_mode = False
        self.ensemble_names = []
        self.meteo_ensemble_deterministic = None

        if not self.run_ensemble or not self.meteo_dataset:
            return
        ds = cosmos.meteo_database.dataset.get(self.meteo_dataset)
        if ds is None:
            return
        cycle_folder = os.path.join(ds.path, cosmos.cycle_string)
        if not os.path.isdir(cycle_folder):
            return

        members = []
        for entry in sorted(os.listdir(cycle_folder)):
            sub = os.path.join(cycle_folder, entry)
            if not os.path.isdir(sub):
                continue
            # A member subfolder must contain <member>.cyc — that's the
            # signature that distinguishes it from any other stray directory.
            if os.path.exists(os.path.join(sub, entry + ".cyc")):
                members.append(entry)

        if not members:
            return

        self.meteo_ensemble_mode = True
        self.ensemble_names = members
        self.meteo_ensemble_deterministic = members[-1]
        self.track_ensemble_nr_realizations = len(members)
        cosmos.log(
            f"Per-member meteo ensemble detected: {len(members)} members "
            f"({', '.join(members)}); deterministic = {members[-1]}"
        )
