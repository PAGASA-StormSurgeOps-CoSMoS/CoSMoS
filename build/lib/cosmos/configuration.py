"""Configuration management for CoSMoS.

Reads and stores all CoSMoS configuration settings including paths, executables,
model databases, meteo databases, web server settings, and cloud infrastructure.
"""

import os

# from cht_utils.misc_tools import rgb2hex
import cht_utils.fileops as fo
import toml

from .color_maps import read_color_maps
from .meteo import read_meteo_database
from .stations import Stations


class Path:
    """File system paths used by CoSMoS."""

    def __init__(self) -> None:
        self.main = None


class ModelDatabase:
    """Model database path configuration."""

    def __init__(self) -> None:
        self.path = None


class MeteoDatabase:
    """Meteorological database path configuration."""

    def __init__(self) -> None:
        self.path = None


class Conda:
    """Conda environment path configuration."""

    def __init__(self) -> None:
        self.path = None


class Executables:
    """Paths to model executables and Docker images."""

    def __init__(self) -> None:
        self.sfincs_path = None
        self.sfincs_docker_image = None
        self.hurrywave_path = None
        self.hurrywave_docker_image = None
        self.delft3d_path = None
        self.xbeach_path = None
        self.beware_path = None


class WebServer:
    """Remote web server connection settings."""

    def __init__(self) -> None:
        self.hostname = None
        self.path = None
        self.username = None
        self.password = None


class WebViewer:
    """Web viewer layout, color maps, and tile layer interval settings."""

    def __init__(self) -> None:
        self.name = None
        self.version = None
        self.path = None
        self.lon = 0.0  # Used for initial view
        self.lat = 0.0  # Used for initial view
        self.zoom = 1  # Used for initial view
        self.lon_lim = None  # Used for wind and meteo maps
        self.lat_lim = None  # Used for wind and meteo maps
        self.storm_classification = "saffirsimpson"  # Used for classifying track points (options: saffirsimpson, pagasa)
        self.tile_layer = {}
        self.tile_layer["flood_map"] = {}
        self.tile_layer["flood_map"]["interval"] = 24
        self.tile_layer["flood_map"]["color_map"] = "flood_map"
        self.tile_layer["water_level_map"] = {}
        self.tile_layer["water_level_map"]["interval"] = 24
        self.tile_layer["water_level_map"]["color_map"] = "water_level_map"
        self.tile_layer["storm_surge_map"] = {}
        self.tile_layer["storm_surge_map"]["interval"] = 24
        self.tile_layer["storm_surge_map"]["color_map"] = "storm_surge_map"
        self.tile_layer["hm0"] = {}
        self.tile_layer["hm0"]["interval"] = 24
        self.tile_layer["hm0"]["color_map"] = "hm0"
        self.tile_layer["sedero"] = {}
        self.tile_layer["sedero"]["color_map"] = "sedero"
        self.tile_layer["bed_levels"] = {}
        self.tile_layer["bed_levels"]["color_map"] = "bed_levels"
        self.tile_layer["precipitation"] = {}
        self.tile_layer["precipitation"]["color_map"] = "precip_log"


class CloudConfig:
    """Kubernetes / Argo / S3 cloud infrastructure settings."""

    def __init__(self) -> None:
        # The url through which the Argo client is available to submit a workflow
        self.host = None
        # Access key and secret (sort of like username/password) for reading/writing files to s3
        self.access_key = None
        self.secret_key = None
        # Region in which the Kubernetes cluster is hosted (TODO: make this configurable)
        self.region = "eu-west-1"
        # Namespace within the cluster where the argo installation is located
        self.namespace = "argo"
        # Token for accessing the argo installation
        self.token = None


class TrackEnsemble:
    """Track ensemble error statistics and realization count."""

    def __init__(self) -> None:
        # Error statistics - defaults are based on NHC of 2018-20210
        self.mean_abs_cte24 = (
            19.0397  # mean absolute error in cross-track error (CTE) in NM
        )
        self.sc_cte = 1.3253  # auto-regression CTE; typically >1
        self.mean_abs_ate24 = (
            26.224  # mean absolute error in along-track error (ATE) in NM
        )
        self.sc_ate = 1.3432  # auto-regression ATE; typically >1
        self.mean_abs_ve24 = 6.9858  # mean absolute error in wind error (VE) in knots
        self.sc_ve = 1.0000  # auto-regression VE = 1 = no auto-regression
        self.bias_ve = 0.0  # bias per hour
        self.nr_realizations = 10


class Run:
    """Runtime settings controlling the forecast loop behaviour."""

    def __init__(self) -> None:
        self.mode = "single_shot"
        self.interval = 6
        self.delay = 0
        self.clean_up = False
        self.catch_up = False
        self.make_flood_maps = True
        self.make_wave_maps = True
        self.make_water_level_maps = True
        self.make_storm_surge_maps = True
        self.make_meteo_maps = True
        self.make_sedero_maps = True
        self.make_webviewer = True
        self.upload = True
        self.download_meteo = True
        self.run_mode = "serial"
        self.event_mode = "meteo"
        self.only_run_ensemble = False
        self.just_initialize = False
        self.run_models = True
        self.collect_meteo_up_to_cycle = False
        self.prune_after_hours = 72
        self.delay = 0  # hours to wait after cycle time before starting the run
        # Run all models in ensemble model by default
        self.ensemble_models = ["sfincs", "hurrywave", "delft3d", "xbeach", "beware"]
        self.spw_wind_field = "parametric"
        self.dthis = 600.0
        self.dtmap = 21600.0
        self.dtmax = 21600.0
        self.dtwnd = 1800
        self.clear_zs_ini = False  # used to limit initial water level in sfincs models
        self.use_spw_precip = False
        self.clean_up_mode = "forecast"
        self.bathtub = False
        self.bathtub_fachs = 0.4
        self.sfincs_docker = False
        self.hurrywave_docker = False
        self.pre_processing_script = (
            None  # Custom pre processing script to be run at the start of each cycle, just before the meteo download
        )
        self.post_processing_script = (
            None  # Custom post processing script to be run after each model loop
        )
        # self.omp_num_threads  = 256


class Configuration:
    """CoSMoS Configuration class.

    Set configuration for:

    - Main CoSMoS path.
    - Model database path.
    - Meteo database path.
    - Conda path
    - Model executable paths.
    - Webserver and webviewer settings.
    - Cycle settings (can be overwritten by CoSMoS initialization settings).
    - Cloud configuration
    """

    def __init__(self) -> None:
        """Initialize all configuration sub-objects with defaults."""
        self.path = Path()
        self.model_database = ModelDatabase()
        self.meteo_database = MeteoDatabase()
        self.conda = Conda()
        self.executables = Executables()
        self.webserver = WebServer()
        self.webviewer = WebViewer()
        self.run = Run()
        self.cloud_config = CloudConfig()
        self.track_ensemble = TrackEnsemble()
        self.kwargs = {}

    def set(self) -> None:
        """Set CoSMoS configuration settings.

        - Set configuration paths.
        - Read configuration file.
        - Overwrite values in configuration file with input arguments.
        - Find all available models in model database.
        - Read all available Stations.
        - Read all available meteo datasets.
        - Read all available super regions.
        - Load color maps.
        """

        from .cosmos import cosmos

        # Doing something new here. Configuration can sit in the run folder (as in the past) or one level up (as in the future).

        # Check if "configuration" folder exists in the main path
        # If not, check if it exists in the parent folder
        # If not, raise error
        main_path_parent = os.path.dirname(self.path.main)
        if os.path.exists(os.path.join(self.path.main, "configuration")):
            # Configuration folder exists in main path
            self.path.config = os.path.join(self.path.main, "configuration")
        elif os.path.exists(os.path.join(main_path_parent, "configuration")):
            # Configuration folder exists in parent path
            self.path.config = os.path.join(main_path_parent, "configuration")
        else:
            raise FileNotFoundError(
                "Configuration folder does not exist in main path or parent folder."
            )

        # self.path.config    = os.path.join(self.path.main, "configuration")
        self.path.jobs = os.path.join(self.path.main, "jobs")
        self.path.stations = os.path.join(self.path.config, "stations")
        self.path.scenarios = os.path.join(self.path.main, "scenarios")
        self.path.webviewer = os.path.join(self.path.main, "webviewers")

        # Read config file
        self.read_config_file()

        # Now read other config data
        # Find all available models and store in dict cosmos.all_models
        cosmos.log("Finding available models ...")
        cosmos.all_models = {}
        region_list = fo.list_folders(
            os.path.join(cosmos.config.model_database.path, "*")
        )
        for region_path in region_list:
            region_name = os.path.basename(region_path)
            type_list = fo.list_folders(os.path.join(region_path, "*"))
            for type_path in type_list:
                type_name = os.path.basename(type_path)
                name_list = fo.list_folders(os.path.join(type_path, "*"))
                for name_path in name_list:
                    name = os.path.basename(name_path).lower()
                    # Check if toml file exists
                    toml_file = os.path.join(name_path, "model.toml")
                    if os.path.exists(toml_file):
                        cosmos.all_models[name] = {
                            "type": type_name,
                            "region": region_name,
                        }

        # Color maps
        tml_file = os.path.join(self.path.config, "color_maps", "map_contours.toml")
        self.map_contours = read_color_maps(tml_file)

        # Available stations (the ones that are available for all models)
        cosmos.log("Reading stations ...")
        self.stations = Stations()
        self.stations.read_all()

        # Add metget_api configuration path for coamps-tc data (save only path to be able to change priority storm while cosmos is running)
        self.metget_config_path = os.path.join(
            self.path.main, "configuration", "metget_config.toml"
        )

        # Available meteo sources
        cosmos.log("Reading meteo database ...")
        read_meteo_database()

        # Find all available super regions
        cosmos.log("Reading super regions ...")
        self.super_region = {}
        super_region_path = os.path.join(
            self.path.main, "configuration", "super_regions"
        )
        super_region_list = fo.list_files(os.path.join(super_region_path, "*.toml"))
        for super_file in super_region_list:
            name = os.path.splitext(os.path.basename(super_file))[0]
            self.super_region[name] = toml.load(super_file)

        # Set webviewer path
        self.webviewer.path = os.path.join(
            cosmos.config.path.main, "webviewers", self.webviewer.name
        )
        self.webviewer.data_path = os.path.join(
            cosmos.config.path.main, "webviewers", self.webviewer.name, "data"
        )

    def read_config_file(self) -> None:
        """Read configuration file (.toml file)."""
        from .cosmos import cosmos

        config_file = os.path.join(self.path.config, self.file_name)

        if not os.path.exists(config_file):
            raise FileNotFoundError(
                f"Configuration file not found: {config_file}\n"
                f"  Make sure '{self.file_name}' exists in: {self.path.config}"
            )

        try:
            config_dict = toml.load(config_file)
        except toml.TomlDecodeError as e:
            raise ValueError(
                f"Failed to parse configuration file {config_file}: {e}"
            ) from e

        # Turn into object
        for section_key in config_dict:
            if not hasattr(self, section_key):
                cosmos.log(
                    f"Warning: Unknown section [{section_key}] in {self.file_name} — skipping."
                )
                continue
            obj = getattr(self, section_key)
            for key, value in config_dict[section_key].items():
                setattr(obj, key, value)
