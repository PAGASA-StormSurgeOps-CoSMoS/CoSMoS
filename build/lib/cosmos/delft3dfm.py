"""Delft3D FM model integration for CoSMoS.

Handles reading, pre-processing, execution, and post-processing of Delft3D
Flexible Mesh hydrodynamic models within the CoSMoS forecast framework.
"""

import os

# import numpy as np
import platform
from pathlib import Path

import cht_utils.fileops as fo
import hydrolib.core.dflowfm as hcdfm
from cht_delft3dfm.cht_delft3dfm import Delft3DFM
from cht_nesting.cht_nesting import nest1
from cht_utils.fileops import find_replace

from .cosmos import cosmos
from .model import Model


class CoSMoS_Delft3DFM(Model):
    """Cosmos class for Delft3d FM model.

    Delft3D FM is a hydrodynamic and morphodynamic numerical model used for simulating and predicting water flow, sediment transport,
    and morphological changes in rivers, estuaries, coasts, and oceans (see also https://oss.deltares.nl/web/delft3dfm).

    This cosmos class reads Delft3D FM model data, pre-processes, moves and post-processes Delft3D FM models.

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
        """Read Delft3D FM specific model attributes.

        See Also
        ----------
        cht_delft3dfm.delft3dfm
        """
        # First set some defaults
        #        self.flow_spinup_time = 0.0

        #        xml_obj = xml.xml2obj(self.file_name)
        #        if hasattr(xml_obj, "flowspinup"):
        #            self.flow_spinup_time = float(xml_obj.flowspinup[0].value)

        # Now read in the domain data
        #        if self.wave:
        self.input_path_flow = os.path.join(self.path, "input", "flow")
        self.input_path_wave = os.path.join(self.path, "input", "wave")
        #        else:
        #            self.input_path_flow = os.path.join(self.path, "input")
        #            self.input_path_wave = None

        input_file = os.path.join(self.input_path_flow, "flow.mdu")
        self.domain = Delft3DFM(input_file, crs=self.crs)

        # Copy some attributes to the model domain (needed for nesting)
        self.domain.crs = self.crs
        self.domain.type = self.type
        self.domain.name = self.name
        self.domain.runid = self.runid

    def pre_process(self) -> None:
        """Preprocess Delft3D FM model.

        - Extract and write wave and water level conditions.
        - Write input file.
        - Write meteo forcing.
        - Add observation points for nested models and observation stations.

        See Also
        ----------
        cht_nesting.nest2
        """
        # Set path temporarily to job path
        #        pth = self.domain.path

        #        if self.wave:
        #        self.domain.path = os.path.join(self.domain.path, "fm")
        #        else:
        #            self.domain.path = self.job_path

        job_path_flow = os.path.join(self.job_path, "flow")
        job_path_wave = os.path.join(self.job_path, "wave")

        # Start and stop times
        refdate = cosmos.scenario.ref_date
        tstart = self.flow_start_time
        tstop = self.flow_stop_time

        # Change refdate in mdw file
        if self.wave:
            tstr = cosmos.scenario.ref_date.strftime("%Y-%m-%d")
            mdw_file = os.path.join(job_path_wave, "wave.mdw")
            find_replace(mdw_file, "REFDATEKEY", tstr)

            t0 = (tstart - refdate).total_seconds()
            t1 = (tstop - refdate).total_seconds()
            dt = 1800.0
            #            tstr = str(0.0) + " " + str(dt) + " " + str(t1 - t0)
            tstr = str(0.0) + " " + str(dt) + " " + str(t1)
            dmr_file = os.path.join(self.job_path, "dimr_config.xml")
            find_replace(dmr_file, "TIMEKEY", tstr)

        # Make sure model starts and stops automatically
        self.domain.input.general.autostart = 2
        # Turn off pressure correction at open boundaries
        if self.flow_nested:
            self.domain.input.wind.pavbnd = -999.0

        # Boundary conditions
        if self.flow_nested:
            pass
            # Correct boundary water levels. Assuming that output from overall
            # model is in MSL !!!

        if self.wave_nested:
            # TODO
            pass

        # Meteo forcing
        if (
            self.meteo_wind
            or self.meteo_atmospheric_pressure
            or self.meteo_precipitation
        ):
            self.write_meteo_input_files("delft3dfm", refdate, path=job_path_flow)

            if self.meteo_wind:
                self.domain.meteo.amu_file = "delft3dfm.amu"
                self.domain.meteo.amv_file = "delft3dfm.amv"

            if self.meteo_atmospheric_pressure:
                self.domain.meteo.amp_file = "delft3dfm.amp"

            if self.meteo_precipitation:
                self.domain.meteo.ampr_file = "delft3dfm.ampr"

            # if self.meteo_spiderweb:
            #     self.domain.input.spwfile = self.meteo_spiderweb
            #     self.domain.input.baro    = 1
            #     src = os.path.join("d:\\cosmos\\externalforcing\\meteo\\",
            #                        "spiderwebs",
            #                        self.meteo_spiderweb)
            #     fo.copy_file(src, self.job_path)

        if self.meteo_spiderweb or self.meteo_track and not self.ensemble:
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
            # self.domain.input.baro    = 1
            self.domain.meteo.spw_file = "delft3dfm.spw"
            fo.copy_file(spwfile, os.path.join(self.job_path, "flow", "delft3dfm.spw"))

        if (
            self.meteo_wind
            or self.meteo_atmospheric_pressure
            or self.meteo_precipitation
            or self.meteo_spiderweb
        ):
            if not self.domain.input.external_forcing.extforcefile:
                self.domain.input.external_forcing.extforcefile = hcdfm.ExtOldModel()
                self.domain.input.external_forcing.extforcefile.filepath = Path(
                    "meteo.ext"
                )
            self.domain.write_ext_meteo(
                file_name=os.path.join(
                    job_path_flow,
                    self.domain.input.external_forcing.extforcefile.filepath,
                )
            )

        # Make observation points
        if self.domain.input.output.obsfile:
            self.domain.read_observation_points(path=job_path_flow)
        for station in self.station:
            self.domain.add_observation_point_gdf(station.x, station.y, station.name)

        # Add observation points for nested models (Nesting 1)
        if self.nested_flow_models:
            if not self.domain.input.output.obsfile:
                self.domain.input.output.obsfile[0] = hcdfm.XYNModel()
                self.domain.input.output.obsfile[0].filepath = Path("dflowfm.xyn")

            for nested_model in self.nested_flow_models:
                nest1(self.domain, nested_model.domain)

        if self.nested_wave_models:
            pass

        # Add other observation stations
        if self.nested_flow_models or len(self.station) > 0:
            if not self.domain.input.output.obsfile:
                self.domain.input.output.obsfile[0] = hcdfm.XYNModel()
                self.domain.input.output.obsfile[0].filepath = Path(self.runid + ".xyn")
            self.domain.write_observation_points(path=job_path_flow)
        if self.wave:
            self.domain.write_observation_points(path=job_path_wave)
            find_replace(
                mdw_file,
                "OBSFILEKEY",
                os.path.join(self.domain.input.output.obsfile[0].filepath),
            )

        # Make restart file
        trstsec = tstop.replace(tzinfo=None) - refdate
        if self.meteo_dataset:
            if self.meteo_dataset.last_analysis_time:
                trstsec = (
                    self.meteo_dataset.last_analysis_time.replace(tzinfo=None) - refdate
                )
        self.domain.input.output.rstinterval = [trstsec.total_seconds()]

        # # Get restart file from previous cycle
        # if self.flow_restart_file:
        #     src = os.path.join(self.restart_path, "flow",
        #                        self.flow_restart_file)
        #     dst = os.path.join(self.job_path,
        #                        "dflowfm.rst")
        #     fo.copy_file(src, dst)
        #     self.domain.input.rstfile = "dflowfm.rst"
        #     self.domain.input.tspinup = 0.0

        # Now write input file
        mdufile = os.path.join(job_path_flow, "flow.mdu")
        self.domain.input.time.startdatetime = tstart.strftime("%Y%m%d%H%M%S")
        self.domain.input.time.stopdatetime = tstop.strftime("%Y%m%d%H%M%S")
        self.domain.input.time.tstart = (tstart - refdate).total_seconds()
        self.domain.input.time.tstop = (tstop - refdate).total_seconds()
        self.domain.input.time.refdate = int(refdate.strftime("%Y%m%d"))
        self.domain.write_input_file(input_file=mdufile)

        # And now prepare the job files

        # Copy the correct run script to run_job.py
        pth = os.path.dirname(__file__)
        fo.copy_file(
            os.path.join(pth, "run_delft3dfm.py"),
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
            # Write batch file (Windows or Linux)
            if platform.system() == "Windows":
                batch_file = os.path.join(self.job_path, "run_simulation.bat")
                fid = open(batch_file, "w")
                fid.write("@ echo off\n")
                exe_path = os.path.join(
                    'call "' + cosmos.config.executables.delft3dfm_path,
                    'x64\\dimr\\scripts\\run_dimr.bat" dimr_config.xml\n',
                )
                fid.write(exe_path)
                fid.write("exit\n")
                fid.close()
            else:
                batch_file = os.path.join(self.job_path, "run_simulation.sh")
                fid = open(batch_file, "w")
                fid.write("#!/bin/bash\n")
                fid.write("unset LD_LIBRARY_PATH\n")
                fid.write(
                    "export PATH="
                    + cosmos.config.executables.delft3dfm_path
                    + ":$PATH\n"
                )
                exe_path = os.path.join(
                    cosmos.config.executables.delft3dfm_path,
                    "x64/dimr/scripts/run_dimr.sh dimr_config.xml\n",
                )
                fid.write(exe_path)
                fid.write("exit\n")
                fid.close()

        if cosmos.config.run.run_mode == "cloud":
            # Set workflow names
            if self.ensemble:
                self.workflow_name = "delft3dfm-ensemble-workflow"
            else:
                self.workflow_name = "delft3dfm-deterministic-workflow"

        # Set the path back

    #        self.domain.path = pth

    def move(self) -> None:
        """Move Delft3D FM model input, output, and restart files."""
        # Move files from job folder to archive folder

        # First clear archive folder

        job_path = self.job_path

        # Delete finished.txt file
        fo.delete_file(os.path.join(job_path, "finished.txt"))

        output_path = self.cycle_output_path
        input_path = self.cycle_input_path

        # FLOW

        # Restart files
        # First rename the restart files
        joboutpath = os.path.join(job_path, "flow", "output")
        flist = fo.list_files(os.path.join(joboutpath, "*_rst.nc"))
        for rstfile0 in flist:
            dstr = rstfile0[-22:-14]
            tstr = rstfile0[-13:-7]
            rstfile1 = "delft3dfm." + dstr + "." + tstr + ".rst"
            fo.move_file(rstfile0, os.path.join(self.restart_flow_path, rstfile1))

        # Output & diag
        fo.move_file(os.path.join(joboutpath, "*.nc"), output_path)
        fo.move_file(os.path.join(joboutpath, "*.dia"), output_path)

        # Input
        # Delete net file (this is typically quite big)
        fo.delete_file(
            os.path.join(job_path, "flow", self.domain.input.geometry.netfile.filepath)
        )
        fo.move_file(os.path.join(job_path, "flow", "*.*"), input_path)
        fo.delete_folder(os.path.join(job_path, "flow"))

        # WAVE

        # Restart files
        # First rename the restart files
        joboutpath = os.path.join(job_path, "wave")
        # flist = fo.list_files(os.path.join(joboutpath, "*_rst.nc"))
        # for rstfile0 in flist:
        #     dstr = rstfile0[-22:-14]
        #     tstr = rstfile0[-13:-7]
        #     rstfile1 = "delft3dfm." + dstr + "." + tstr + ".rst"
        #     fo.move_file(rstfile0,
        #                  os.path.join(self.restart_path, "flow", rstfile1))

        # Output
        if os.path.isdir(joboutpath):
            fo.move_file(os.path.join(joboutpath, "wav*.nc"), output_path)
            fo.delete_file(os.path.join(joboutpath, "*.nc"))
            fo.delete_file(os.path.join(joboutpath, "wavm-wave.d*"))

            # Input
            fo.move_file(os.path.join(joboutpath, "*.*"), input_path)
            fo.delete_folder(joboutpath)

    def post_process(self) -> None:
        """Post-process Delft3D FM output: generate wave and water level timeseries."""
        from cht_utils.fileio.json_js import write_csv_js

        # Extract water levels

        output_path = self.cycle_output_path
        # post_path   = self.cycle_post_path
        post_path = os.path.join(
            cosmos.config.path.webviewer,
            cosmos.config.webviewer.name,
            "data",
            cosmos.scenario.name,
        )

        hisfile = os.path.join(output_path, "flow_his.nc")

        if self.station:
            cosmos.log("Extracting time series from model " + self.name)

            v = self.domain.read_timeseries_output(file_name=hisfile)
            for station in self.station:
                if station.upload:
                    vv = v[station.name]
                    vv.index.name = "date_time"
                    vv.name = "wl"
                    vv += self.vertical_reference_level_difference_with_msl

                    fo.mkdir(os.path.join(post_path, "timeseries"))
                    csv_file = os.path.join(
                        post_path,
                        "timeseries",
                        "waterlevel." + self.name + "." + station.name + ".csv.js",
                    )

                    s = vv.to_csv(
                        date_format="%Y-%m-%dT%H:%M:%S",
                        float_format="%.3f",
                        header=False,
                    )
                    write_csv_js(csv_file, s, "var csv = `date_time,wl")

        # Extract waves
        if self.wave:
            if self.station:
                cosmos.log("Extracting wave time series from model " + self.name)
                wavefile = [os.path.join(output_path, "wavh-wave-wave.nc")]
                v = self.domain.read_timeseries_output(
                    file_name=hisfile, file_name_wave=wavefile
                )
                for station in self.station:
                    if station.upload:
                        vv = v[station.name]
                        vv.index.name = "date_time"
                        csv_file = os.path.join(
                            post_path,
                            "timeseries",
                            "waves." + self.name + "." + station.name + ".csv.js",
                        )
                        s = vv.to_csv(
                            date_format="%Y-%m-%dT%H:%M:%S",
                            float_format="%.3f",
                            header=False,
                        )
                        write_csv_js(csv_file, s, "var csv = `date_time,hm0,tp")
