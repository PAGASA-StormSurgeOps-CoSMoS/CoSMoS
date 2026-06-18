"""Meteorological data handling for CoSMoS.

Downloads, collects, and manages meteorological forcing data (wind, pressure)
and tropical cyclone track data for driving the forecast models.
"""

import datetime
import glob
import os

import cht_utils.fileops as fo
import geopandas as gpd
from cht_cyclones import TropicalCyclone
from cht_cyclones.jtwc import jtwc
from cht_meteo import MeteoDatabase

from .cosmos import cosmos


def read_meteo_database() -> None:
    """Read the meteorological dataset catalogue from the configured path."""
    cosmos.meteo_database = MeteoDatabase()
    cosmos.meteo_database.path = cosmos.config.meteo_database.path
    cosmos.meteo_database.read_datasets()


def _collect_meteo_ensemble_deterministic() -> None:
    """Per-member ensemble meteo: load the deterministic representative.

    The last (sorted) ensemble member supplies the deterministic best track:
    its gridded data is collected once into the dataset, and its <member>.cyc
    is loaded as ``cosmos.tropical_cyclone``. The wind field is taken straight
    from the gridded data (per-member ensembles never use parametric spws),
    and ``storm.spw`` / ``storm.cyc`` are written to ``cycle_track_spw_path``.

    The OTHER members' spw + amu/amv are produced later by
    ``setup_track_ensemble()`` and ``Model.write_meteo_input_files()``, which
    re-call ``meteo_dataset.collect(subfolder=<member>)`` per member.
    """
    member = cosmos.scenario.meteo_ensemble_deterministic
    dataset_name = cosmos.scenario.meteo_dataset
    meteo_dataset = cosmos.meteo_database.dataset.get(dataset_name)
    if meteo_dataset is None:
        cosmos.stop(
            f"Per-member ensemble meteo dataset '{dataset_name}' "
            f"not found in meteo database."
        )

    # Same t0/t1 logic as the regular collect: cover all models that point at
    # this dataset.
    t0 = datetime.datetime(2100, 1, 1, 0, 0, 0)
    t1 = datetime.datetime(1970, 1, 1, 0, 0, 0)
    for model in cosmos.scenario.model:
        if model.meteo_dataset and model.meteo_dataset.name == dataset_name:
            t0 = min(t0, model.flow_start_time)
            t1 = max(t1, model.flow_stop_time)

    last_meteo_cycle = cosmos.cycle if cosmos.config.run.collect_meteo_up_to_cycle else None

    cosmos.log(
        f"Collecting meteo data (per-member, deterministic={member}) : {meteo_dataset.name}"
    )
    meteo_dataset.collect([t0, t1], last_cycle=last_meteo_cycle, subfolder=member)

    meteo_dataset.resolution = float(
        meteo_dataset.ds["lon"].values[1] - meteo_dataset.ds["lon"].values[0]
    )
    if meteo_dataset.last_forecast_cycle_time:
        cstr = meteo_dataset.last_forecast_cycle_time.strftime("%Y%m%d_%Hz")
        cosmos.scenario.meteo_string = f"{cstr} ({meteo_dataset.name})"
    else:
        cosmos.scenario.meteo_string = meteo_dataset.name

    # Load the last member's .cyc as the deterministic tc.
    cyc_file = os.path.join(
        meteo_dataset.path, cosmos.cycle_string, member, f"{member}.cyc"
    )
    if not os.path.exists(cyc_file):
        cosmos.stop(f"Deterministic track file not found: {cyc_file}")
    tc = TropicalCyclone(track_file=cyc_file, name=member)

    # Per-member ensembles always derive the spw from the gridded data —
    # this is the whole point. (Equivalent to spw_wind_field == "meteo_data".)
    tc.track.resample(1, method="spline")
    if len(meteo_dataset.subset) > 0:
        times = meteo_dataset.subset[0].ds.time.values
    else:
        times = meteo_dataset.ds.time.values
    tend = datetime.datetime.utcfromtimestamp(
        times[-1].astype(datetime.datetime) / 1e9
    )
    tc.track.shorten(tend=tend)
    tc.get_wind_field_from_meteo_dataset(meteo_dataset)

    # Write storm.spw / storm.cyc / track.geojson.js — same as the standard
    # deterministic flow below.
    cosmos.scenario.meteo_spiderweb = "storm.spw"
    fo.mkdir(cosmos.scenario.cycle_track_spw_path)
    spwfile = os.path.join(
        cosmos.scenario.cycle_track_spw_path, cosmos.scenario.meteo_spiderweb
    )
    if not os.path.exists(spwfile):
        tc.write_spiderweb(spwfile, format="ascii", include_rainfall=True)
    cycfile = os.path.join(cosmos.scenario.cycle_track_spw_path, "storm.cyc")
    tc.track.write(cycfile)
    jsfile = os.path.join(cosmos.scenario.cycle_track_spw_path, "track.geojson.js")
    tc.track.to_gdf(
        filename=jsfile, classification=cosmos.config.webviewer.storm_classification
    )

    cosmos.tropical_cyclone = tc


def download_meteo() -> None:
    """Download meteorological data for all required datasets."""
    # Per-member ensemble meteo (scenario.detect_meteo_ensemble_mode()) is
    # assumed to be pre-staged on disk in the per-cycle, per-member layout —
    # the cht_meteo download flow doesn't know about subfolders. Skip.
    if cosmos.scenario.meteo_ensemble_mode:
        cosmos.log(
            "Per-member meteo ensemble: skipping download_meteo "
            "(data is pre-staged in member subfolders)."
        )
        return
    # Loop through all available meteo datasets
    # Determine if the need to be downloaded
    # Get start and stop times for meteo data
    for dataset_name, meteo_dataset in cosmos.meteo_database.dataset.items():
        download = False
        t0 = datetime.datetime(2100, 1, 1, 0, 0, 0)
        t1 = datetime.datetime(1970, 1, 1, 0, 0, 0)
        for model in cosmos.scenario.model:
            if model.meteo_dataset:
                if model.meteo_dataset.name == meteo_dataset.name:
                    download = True
                    t0 = min(t0, model.flow_start_time)
                    t1 = max(t1, model.flow_stop_time)
        if download:
            # Download the data
            cosmos.log("Downloading meteo data : " + meteo_dataset.name)
            if cosmos.config.run.collect_meteo_up_to_cycle:
                last_meteo_cycle = cosmos.cycle
            else:
                last_meteo_cycle = None
            # meteo_dataset.download([t0, t1], storm_number=cosmos.scenario.storm_number, last_cycle=last_meteo_cycle)
            meteo_dataset.download([t0, t1], last_cycle=last_meteo_cycle)

    # Download cyclone tracks if needed
    if cosmos.scenario.cyclone_track_forecast_source is not None:
        if cosmos.scenario.cyclone_track_forecast_source.lower() == "jtwc":
            # Download JTWC tracks
            jtwc_path = os.path.join(cosmos.meteo_database.path, "tracks", "jtwc")
            jtwc.download(jtwc_path)


def collect_meteo() -> None:
    """Collect meteorological data from NetCDF files and process cyclone tracks."""
    # Per-member ensemble meteo: handled separately. The "deterministic"
    # representative is the last (sorted) member; we collect ONLY that member
    # here and use its track + grids to build storm.spw / storm.cyc.
    # The per-member loop (spw + amu/amv for every other member) lives in
    # setup_track_ensemble() and Model.write_meteo_input_files().
    if cosmos.scenario.meteo_ensemble_mode:
        _collect_meteo_ensemble_deterministic()
        return

    # Loop through all available meteo datasets
    # Determine if the need to be downloaded
    # Get start and stop times for meteo data

    tau = 0

    for dataset_name, meteo_dataset in cosmos.meteo_database.dataset.items():
        collect = False
        t0 = datetime.datetime(2100, 1, 1, 0, 0, 0)
        t1 = datetime.datetime(1970, 1, 1, 0, 0, 0)

        for model in cosmos.scenario.model:
            if model.meteo_dataset:
                if model.meteo_dataset.name == meteo_dataset.name:
                    collect = True
                    t0 = min(t0, model.flow_start_time)
                    t1 = max(t1, model.flow_stop_time)

        if collect:
            # Collect the data from netcdf files
            cosmos.log("Collecting meteo data : " + meteo_dataset.name)
            if cosmos.config.run.collect_meteo_up_to_cycle:
                last_meteo_cycle = cosmos.cycle
            else:
                last_meteo_cycle = None
            meteo_dataset.collect([t0, t1], last_cycle=last_meteo_cycle)

            # Get the approximate resolution of the meteo_dataset in degrees.
            # This is used to determine in order to adjust the resolution of the meteo forcing grid.
            meteo_dataset.resolution = float(
                meteo_dataset.ds["lon"].values[1] - meteo_dataset.ds["lon"].values[0]
            )

            if meteo_dataset.last_analysis_time:
                cosmos.log(
                    "Last analysis time : "
                    + meteo_dataset.last_analysis_time.strftime("%Y%m%d_%H%M%S")
                )

            if meteo_dataset.last_forecast_cycle_time:
                cosmos.log(
                    "Last forecast cycle time : "
                    + meteo_dataset.last_forecast_cycle_time.strftime("%Y%m%d_%H%M%S")
                )
                cstr = meteo_dataset.last_forecast_cycle_time.strftime("%Y%m%d_%Hz")
                cosmos.scenario.meteo_string = f"{cstr} ({meteo_dataset.name})"

            else:
                cosmos.scenario.meteo_string = (
                    meteo_dataset.name + " (no cycle information available)"
                )

    # Cyclone track

    # Now we collect the cyclone track file. There are three options:
    # 1. Track file provided in scenario file
    # 2. Track file provided by cyclone_track_forecast_source (e.g. JTWC)
    # 3. Track file found in meteo data folders

    # The track file will be copied to the cycle folder\\track folder and will be named storm.cyc.
    # The matching spiderweb file will be stored in the same folder and will be named storm.spw.

    cosmos.tropical_cyclone = None
    tc = None
    # track_file_name = None
    # storm_name = None

    # How do we determine where the deterministic track forecast is coming from? We check in the following order:
    # 1. A track file is provided in the scenario file (cosmos.scenario.meteo_track)
    # 2. A track forecast source is provided in the scenario file (cosmos.scenario.cyclone_track_forecast_source).
    #    Track forecast source is "jtwc" or "nhc", or some other provider.
    #    In this case, we also need either:
    #      A. an area file (cosmos.scenario.cyclone_track_forecast_area_file) to determine which track to use.
    #      B. a storm number (cosmos.scenario.storm_number) to determine which track to use.
    # 3. If not 1 or 2, we look for track files in the meteo data folders. This is now the case for COAMPS-TC, but also
    #    for ECMWF as used by PAGASA.

    if cosmos.scenario.meteo_track is not None:

        # 1. Track name provided in scenario file (cosmos.scenario.meteo_track is the name without path or extension!)

        cosmos.log("Using track file provided in scenario file")
        track_file_name = os.path.join(
            cosmos.config.meteo_database.path,
            "tracks",
            cosmos.scenario.meteo_track + ".cyc",
        )
        storm_name = cosmos.scenario.meteo_track
        # Create a TropicalCyclone object
        tc = TropicalCyclone(track_file=track_file_name, name=storm_name)

    elif cosmos.scenario.cyclone_track_forecast_source is not None:

        # 2) Track provided by cyclone_track_forecast_source (e.g. JTWC)

        if cosmos.scenario.cyclone_track_forecast_area_file is not None:

            # A. Read the file (geojson) and get the Polygon geometry

            forecast_area = gpd.read_file(
                os.path.join(
                    cosmos.config.path.main,
                    "configuration",
                    "areas",
                    cosmos.scenario.cyclone_track_forecast_area_file,
                )
            ).geometry.iloc[0]

        elif cosmos.scenario.storm_number is not None:

            # B. Get the storm number from the scenario file and use that to find the track 
            forecast_area = None    

        else:
            cosmos.stop(
                "Track forecast area file (cyclone_track_forecast_area_file) not provided in scenario.toml !"
            )

        if cosmos.scenario.cyclone_track_forecast_source.lower() == "jtwc":

            jtwc_path = os.path.join(cosmos.meteo_database.path, "tracks", "jtwc")

            t0 = cosmos.cycle.replace(tzinfo=None)
            t1 = cosmos.stop_time.replace(tzinfo=None)

            # Find the track
            track_file_name, storm_name = jtwc.find_jtwc_track_file(
                jtwc_path, t0, t1, forecast_area
            )

            if track_file_name is None:
                cosmos.log("No JTWC track found for this cycle")
                return

            # Make a TropicalCyclone object
            tc = TropicalCyclone(track_file=track_file_name, name=storm_name)



    else:

        # 3) Track may be found in meteo data folders. This is now the case for COAMPS-TC.

        for dataset_name, meteo_dataset in cosmos.meteo_database.dataset.items():

            collect = False

            for model in cosmos.scenario.model:
                if model.meteo_dataset:
                    if model.meteo_dataset.name == meteo_dataset.name:
                        collect = True

            if collect:
                # Check if track files are available in any of the cycle folders
                cycle_folders = fo.list_folders(os.path.join(meteo_dataset.path, "*"))
                track_file_list = []
                # tau = meteo_dataset.tau
                # Loop through folders and determine time of cycle
                for folder in cycle_folders:
                    try:
                        t = datetime.datetime.strptime(
                            os.path.basename(folder), "%Y%m%d_%Hz"
                        )
                        # For hindcasts, only use data up to the last cycle
                        if last_meteo_cycle:
                            if t > last_meteo_cycle.replace(tzinfo=None):
                                continue
                        # Track start time needs to be after or at the start time of the scenario.
                        if t >= t0:
                            # Check if track file is available
                            track_files = glob.glob(os.path.join(folder, "*.cyc"))
                            if len(track_files) > 0:
                                track_file_list.append(track_files[0])
                                storm_name = meteo_dataset.name
                    except Exception:
                        print("Error in reading folder name")

                if len(track_file_list) == 0:
                    cosmos.log("No track files found for dataset: " + dataset_name)
                    return

                # Make a TC with list of track files
                tc = TropicalCyclone(track_file=track_file_list, name=storm_name)

    if tc is None:
        cosmos.log("No cyclone track found")
        return

    # There is a tropical cyclone track. Now determine how to get the wind field.
    # Two options:
    # 1. Parametric wind field (Holland 2010)
    # 2. Wind field from meteo data

    cosmos.scenario.meteo_spiderweb = "storm.spw"

    if cosmos.config.run.spw_wind_field == "parametric":
        # 1) Use Holland (2010)
        # If there is no background wind, we want a large radius
        # If there is background wind, we want a small radius
        if cosmos.scenario.meteo_dataset is None:
            tc.config["spiderweb_radius"] = 800.0  # km
            tc.config["nr_radial_bins"] = 100
        else:
            tc.config["spiderweb_radius"] = 400.0  # km
            tc.config["nr_radial_bins"] = 100
        tc.compute_wind_field()

    elif cosmos.config.run.spw_wind_field == "meteo_data":
        # Use the meteo data
        for dataset_name, meteo_dataset in cosmos.meteo_database.dataset.items():
            if meteo_dataset.name == cosmos.scenario.meteo_dataset:
                if len(meteo_dataset.subset) > 0:
                    times = meteo_dataset.subset[0].ds.time.values
                else:
                    times = meteo_dataset.ds.time.values

                dthours = 1
                tc.track.resample(dthours, method="spline")
                # Limit length of track to the meteo data (convert last time from np.datetime64 to datetime)
                tend = datetime.datetime.utcfromtimestamp(
                    times[-1].astype(datetime.datetime) / 1e9
                )
                tc.track.shorten(tend=tend)
                # Get wind field from meteo data
                tc.get_wind_field_from_meteo_dataset(meteo_dataset)
                break

    else:
        cosmos.log(
            f"cosmos.config.run.spw_wind_field option {cosmos.config.run.spw_wind_field} not recognized!"
        )
        return

    # We now have the wind field, so write the spiderweb file and cyc file in the cycle folder

    # Check if track path exists. If not, create it.
    if not os.path.exists(cosmos.scenario.cycle_track_spw_path):
        os.makedirs(cosmos.scenario.cycle_track_spw_path)

    spwfile = os.path.join(
        cosmos.scenario.cycle_track_spw_path, cosmos.scenario.meteo_spiderweb
    )

    if not os.path.exists(spwfile):
        # Only write spw file is it does not already exist
        tc.write_spiderweb(spwfile, format="ascii", include_rainfall=True)

    # Also save the track file
    cycfile = os.path.join(cosmos.scenario.cycle_track_spw_path, "storm.cyc")
    tc.track.write(cycfile)
    # And the js file (to be uploaded to the webviewer)
    jsfile = os.path.join(cosmos.scenario.cycle_track_spw_path, "track.geojson.js")
    tc.track.to_gdf(
        filename=jsfile, classification=cosmos.config.webviewer.storm_classification
    )

    cosmos.tropical_cyclone = tc
