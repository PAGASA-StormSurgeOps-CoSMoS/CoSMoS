"""Tropical cyclone track ensemble generation for CoSMoS.

Generates ensembles of synthetic cyclone tracks and associated wind fields
from a best-track forecast for probabilistic storm surge predictions.
"""

import copy
import datetime
import os
from glob import glob

import cht_utils.fileops as fo
import shapely
from cht_cyclones import TropicalCyclone
from cht_cyclones.ensemble import TropicalCycloneEnsemble

from .cosmos import cosmos

# from cht_meteo.cht.meteo.meteo import filter_cyclones_TCvitals, find_priorityTC
# import cht_utils.fileops as fo
# from datetime import datetime
# import cht_utils.misc_tools


def _meteo_track_ensemble_dir() -> str | None:
    """Return the meteo-database ``track_ensemble`` folder for this cycle.

    The folder is derived from the meteo dataset that supplied the
    deterministic track (``cosmos.tropical_cyclone``): its track file lives at
    ``<meteo_dataset>/<cycle>/<storm>.cyc``, so the ensemble cyc files are
    expected in ``<meteo_dataset>/<cycle_string>/track_ensemble``. Returns
    ``None`` if it cannot be determined.
    """
    track_file = getattr(cosmos.tropical_cyclone, "track_file", None)
    if not track_file:
        return None
    if isinstance(track_file, list):
        track_file = track_file[0]
    meteo_dataset_dir = os.path.dirname(os.path.dirname(track_file))
    return os.path.join(meteo_dataset_dir, cosmos.cycle_string, "track_ensemble")


def _generate_per_member_ensemble(tc, track_path, spw_path, tstart, tend, dt) -> None:
    """Build the per-member ensemble from the per-cycle, per-member layout.

    For each member in ``cosmos.scenario.ensemble_names`` (set by
    ``Scenario.detect_meteo_ensemble_mode``):

      1. Stage ``<meteo>/<cycle>/<member>/<member>.cyc`` to
         ``<track_path>/ensemble_<member>.cyc`` so ``generate_from_track_files``
         picks it up with the underscore-prefixed naming used downstream.
      2. Let ``generate_from_track_files`` populate the
         ``TropicalCycloneEnsemble`` (members, tracks, cone) and write
         parametric spws — those parametric spws are then overwritten in (3).
      3. Loop members, re-collect that member's gridded data via
         ``meteo_dataset.collect(subfolder=<member>)``, compute the wind field
         from the gridded data, and write ``ensemble_<member>.spw`` over the
         parametric one. ``meteo_dataset.ds`` is overwritten each iteration;
         only one member is in memory at a time.

    The last (sorted) member's deterministic spw / cyc was already produced
    by ``meteo._collect_meteo_ensemble_deterministic`` (storm.spw / storm.cyc
    in ``cycle_track_spw_path``).
    """
    members = cosmos.scenario.ensemble_names
    dataset_name = cosmos.scenario.meteo_dataset
    meteo_dataset = cosmos.meteo_database.dataset[dataset_name]
    src_root = os.path.join(meteo_dataset.path, cosmos.cycle_string)

    # 1. Stage member .cyc files under the underscore-prefixed name.
    fo.mkdir(track_path)
    fo.mkdir(spw_path)
    for member in members:
        src = os.path.join(src_root, member, member + ".cyc")
        dst = os.path.join(track_path, "ensemble_" + member + ".cyc")
        fo.copy_file(src, dst)

    # 2. TropicalCycloneEnsemble (parametric spws as side effect — overwritten
    # below). number_of_realizations=0 + generate_from_track_files is the
    # supported "load tracks from cyc files" pattern.
    cosmos.log(
        f"Generating per-member spiderwebs from gridded ensemble data "
        f"({len(members)} members) ..."
    )
    cosmos.scenario.track_ensemble = TropicalCycloneEnsemble(
        tc,
        name="ensemble",
        number_of_realizations=0,
        compute_wind_fields=False,
        dt=dt,
        tstart=tstart,
        tend=tend,
        track_path=track_path,
        spw_path=spw_path,
    )
    cosmos.scenario.track_ensemble.generate_from_track_files(
        track_path, spiderweb_radius=400.0, nr_radial_bins=100,
    )
    cosmos.scenario.track_ensemble_nr_realizations = (
        cosmos.scenario.track_ensemble.number_of_realizations
    )

    # 3. Overwrite each parametric spw with one derived from THAT member's
    # gridded wind field.
    for member in members:
        cosmos.log(f"Computing gridded spw for ensemble member {member} ...")
        meteo_dataset.collect(
            [tstart, tend],
            last_cycle=cosmos.cycle if cosmos.config.run.collect_meteo_up_to_cycle else None,
            subfolder=member,
        )
        cyc_file = os.path.join(src_root, member, member + ".cyc")
        m_tc = TropicalCyclone(track_file=cyc_file, name=member)
        m_tc.track.resample(1, method="spline")
        if len(meteo_dataset.subset) > 0:
            times = meteo_dataset.subset[0].ds.time.values
        else:
            times = meteo_dataset.ds.time.values
        m_tend = datetime.datetime.utcfromtimestamp(
            times[-1].astype(datetime.datetime) / 1e9
        )
        m_tc.track.shorten(tend=m_tend)
        m_tc.get_wind_field_from_meteo_dataset(meteo_dataset)
        spwfile = os.path.join(spw_path, "ensemble_" + member + ".spw")
        m_tc.write_spiderweb(spwfile, format="ascii", include_rainfall=True)


def _write_cone_and_tracks(track_ensemble):
    """Write the ensemble track geojson / pli files and return the cone gdf."""
    track_ensemble.to_gdf(
        option="tracks",
        varname="track_ensemble_data",
        filename=os.path.join(
            cosmos.scenario.cycle_track_ensemble_path, "track_ensemble.geojson.js"
        ),
    )
    track_ensemble.to_gdf(
        option="tracks",
        filename=os.path.join(
            cosmos.scenario.cycle_track_ensemble_path, "track_ensemble.pli"
        ),
    )
    return track_ensemble.to_gdf(
        option="outline",
        buffer=200000.0,
        filename=os.path.join(
            cosmos.scenario.cycle_track_ensemble_path, "ensemble_cone.geojson"
        ),
    )


def setup_track_ensemble() -> None:
    """Generate a tropical cyclone track ensemble and tag qualifying models.

    Builds synthetic track realizations from the best-track forecast, writes
    spiderweb files, determines which models fall within the ensemble cone, and
    creates ensemble copies of those models in the scenario.
    """
    tc = cosmos.tropical_cyclone

    if len(tc.track.gdf) < 3:
        # Track too short
        return

    tstart = cosmos.cycle.replace(tzinfo=None)
    tend = cosmos.stop_time.replace(tzinfo=None)
    dt = 3
    nens = cosmos.scenario.track_ensemble_nr_realizations
    track_path = cosmos.scenario.cycle_track_ensemble_cyc_path
    spw_path = cosmos.scenario.cycle_track_ensemble_spw_path

    # Decide how to obtain the track ensemble, in priority order:
    # 0. Per-member meteo ensemble (scenario.detect_meteo_ensemble_mode found
    #    a <cycle>/<member>/<member>.cyc layout) -> use those tracks AND
    #    compute the spiderweb for each member from THAT member's gridded data
    #    (not parametric Holland). The last (sorted) member is the deterministic.
    # 1. cyc files in the meteo database track_ensemble folder for this cycle ->
    #    use those tracks and compute a parametric spiderweb for each.
    # 2. Otherwise -> generate a synthetic ensemble from the best track (DeMaria).
    if cosmos.scenario.meteo_ensemble_mode:
        # 0. Per-member meteo ensemble: tracks AND gridded forcing live in
        # per-member subfolders. We build the spw for each member from THAT
        # member's gridded wind field (not parametric Holland).
        _generate_per_member_ensemble(tc, track_path, spw_path, tstart, tend, dt)

    else:
        meteo_track_ensemble_dir = _meteo_track_ensemble_dir()
        meteo_cyc_files = []
        if meteo_track_ensemble_dir and os.path.exists(meteo_track_ensemble_dir):
            meteo_cyc_files = sorted(
                glob(os.path.join(meteo_track_ensemble_dir, "*.cyc"))
            )

        if meteo_cyc_files:
            # 1. Track ensemble provided as cyc files in the meteo database
            # cycle folder. Use those tracks and compute a parametric (Holland)
            # spiderweb for each member.
            cosmos.log("Generating track ensemble from meteo database cyc files ...")
            cosmos.scenario.track_ensemble = TropicalCycloneEnsemble(
                tc,
                name="ensemble",
                number_of_realizations=0,
                compute_wind_fields=False,
                dt=dt,
                tstart=tstart,
                tend=tend,
                track_path=track_path,
                spw_path=spw_path,
            )
            # Spiderweb settings mirror the deterministic parametric track in
            # meteo.py: larger radius when there is no background meteo wind field.
            if cosmos.scenario.meteo_dataset is None:
                spiderweb_radius = 800.0
            else:
                spiderweb_radius = 400.0
            cosmos.scenario.track_ensemble.generate_from_track_files(
                meteo_track_ensemble_dir,
                spiderweb_radius=spiderweb_radius,
                nr_radial_bins=100,
            )
            cosmos.scenario.track_ensemble_nr_realizations = (
                cosmos.scenario.track_ensemble.number_of_realizations
            )

        else:
            # 2. Generate a synthetic track ensemble from the best track (DeMaria).
            cosmos.log("Generating track ensemble ...")
            cosmos.scenario.track_ensemble = tc.make_ensemble(
                name="ensemble",
                number_of_realizations=nens,
                dt=dt,
                tstart=tstart,
                tend=tend,
                track_path=track_path,
                spw_path=spw_path,
                mean_abs_cte24=cosmos.config.track_ensemble.mean_abs_cte24,  # mean absolute error in cross-track error (CTE) in NM
                sc_cte=cosmos.config.track_ensemble.sc_cte,  # auto-regression CTE; typically >1
                mean_abs_ate24=cosmos.config.track_ensemble.mean_abs_ate24,  # mean absolute error in along-track error (ATE) in NM
                sc_ate=cosmos.config.track_ensemble.sc_ate,  # auto-regression ATE; typically >1
                mean_abs_ve24=cosmos.config.track_ensemble.mean_abs_ve24,  # mean absolute error in wind error (VE) in knots
                sc_ve=cosmos.config.track_ensemble.sc_ve,  # auto-regression VE = 1 = no auto-regression
                bias_ve=cosmos.config.track_ensemble.bias_ve,  # bias per hour
            )

    cone = _write_cone_and_tracks(cosmos.scenario.track_ensemble)

    # Loop through all models and check if they fall within cone
    models_to_add = []
    for model in cosmos.scenario.model:
        # First check if this type of model should be run in ensemble mode
        if model.type not in cosmos.scenario.ensemble_models:
            # Not an ensemble model
            continue
        if model.exterior is None:
            # No outline defined
            continue
        if model.role == "tide_only":
            # Tide only model
            continue
        if shapely.intersects(
            cone.loc[0]["geometry"], model.exterior.loc[0]["geometry"]
        ):
            # Add model
            # Make a shallow copy of the model
            ensemble_model = copy.copy(model)
            # Change name and long name
            ensemble_model.name = model.name + "_ensemble"
            ensemble_model.long_name = model.long_name + " (ensemble)"
            # Re-initialize the model domain
            ensemble_model.read_model_specific()
            # Set ensemble flag
            ensemble_model.ensemble = True
            # Set name of matching deterministic model
            ensemble_model.deterministic_name = model.name
            # Change nesting (new nested models will be set later in this function)
            ensemble_model.nested_flow_models = []
            ensemble_model.nested_wave_models = []
            if ensemble_model.flow_nested_name:
                ensemble_model.flow_nested_name += "_ensemble"
            if ensemble_model.wave_nested_name:
                ensemble_model.wave_nested_name += "_ensemble"
            if ensemble_model.bw_nested_name:
                ensemble_model.bw_nested_name += "_ensemble"
            # Add to list of models to add
            models_to_add.append(ensemble_model)

    cosmos.scenario.model = cosmos.scenario.model + models_to_add

    for model in models_to_add:
        # Get nested models for ensemble models
        model.get_nested_models()
        # Set and make paths for ensemble models
        model.set_paths()

    # if cosmos.config.run.only_run_ensemble:
    #     # Remove all models that are not ensembles
    #     cosmos.scenario.model = [model for model in cosmos.scenario.model if model.ensemble]

    # Set ensemble names. In per-member meteo mode they're already the actual
    # member names (set by Scenario.detect_meteo_ensemble_mode) and must NOT
    # be overwritten with zero-padded indices.
    if not cosmos.scenario.meteo_ensemble_mode:
        cosmos.scenario.ensemble_names = []
        for iens in range(cosmos.scenario.track_ensemble_nr_realizations):
            cosmos.scenario.ensemble_names.append(str(iens).zfill(5))

    cosmos.log("Track ensemble done ...")
