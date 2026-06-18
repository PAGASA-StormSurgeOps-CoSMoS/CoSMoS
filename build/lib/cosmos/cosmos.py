"""Main CoSMoS class and singleton instance.

Provides the central CoSMoS object that manages initialization, scenario
execution, logging, and coordination of all forecast components.
"""

import datetime
import os

import cht_utils.fileops as fo


class CoSMoS:
    """This is the main CoSMoS class.

    Parameters
    ----------
    initialize : func
        Initialize cosmos based on main folder input
    run : func
        Run cosmos scenario
    stop : func
        Stop cosmos scenario
    log : func
        Make log of cosmos scenario
    make_webviewer : func
        Just make webviewer for cosmos scenario
    post_process : func
        Just post-process cosmos results

    See Also
    -------
    cosmos.MainLoop
    cosmos.Model
    cosmos.beware.CoSMoS_BEWARE
    cosmos.delft3dfm.CoSMoS_Delft3DFM
    cosmos.hurrywave.CoSMoS_HurryWave
    cosmos.sfincs.CoSMoS_SFINCS
    cosmos.xbeach.CoSMoS_XBeach

    """

    def __init__(self) -> None:
        """Initialize the CoSMoS singleton."""
        os.environ["HDF5_DISABLE_VERSION_CHECK"] = "2"

    def initialize(self, main_path: str, config_file: str = "config.toml") -> None:
        """Initialize CoSMoS configuration based on configuration file and input arguments.

        Parameters
        ----------
        main_path : str
            Path of CoSMoS main folder.
        config_file : str
            Name of the configuration file.

        See Also
        -------
        cosmos.Configuration

        """
        from .configuration import Configuration

        self.config = Configuration()

        # Set main path
        self.config.path.main = main_path

        # Set config path
        self.config.file_name = config_file

        # Read in configuration
        self.config.set()

    def validate(self, scenario_name: str) -> bool:
        """Validate a scenario without running it.

        Checks configuration paths, scenario file, model database, nesting
        chains, meteo references, station files, and executable paths.

        Call this after ``initialize()`` and before ``run()``.

        Parameters
        ----------
        scenario_name : str
            Name of the scenario to validate.

        Returns
        -------
        bool
            ``True`` if no errors were found, ``False`` otherwise.
        """
        from .validation import validate_scenario

        return validate_scenario(self, scenario_name)

    def run(
        self,
        scenario_name: str = None,
        cycle: str = None,
        last_cycle: str = None,
        validate: bool = True,
    ) -> None:
        """Run a CoSMoS scenario.

        Parameters
        ----------
        scenario_name : str, optional
            Name of the scenario to be run.
        cycle : str, optional
            Cycle to start with (e.g. ``"20231213_00z"``).
        last_cycle : str, optional
            Last cycle to process (e.g. ``"20231215_00z"``).
        validate : bool, optional
            Run validation before starting. Set to ``False`` to skip.

        See Also
        -------
        cosmos.MainLoop
        cosmos.ModelLoop
        cosmos.webviewer.WebViewer

        """

        # Validate scenario before running
        if validate:
            if not self.validate(scenario_name):
                self.log("Validation failed — aborting run.")
                return

        # Determine which cycle needs to be run
        # If no cycle is given, check the scenario file for one
        self.scenario_name = scenario_name

        if not cycle:
            cycle = self._read_cycle_from_scenario(scenario_name)

        if cycle:
            cycle = datetime.datetime.strptime(cycle, "%Y%m%d_%HZ").replace(
                tzinfo=datetime.timezone.utc
            )
        if last_cycle:
            cosmos.last_cycle = datetime.datetime.strptime(
                last_cycle, "%Y%m%d_%HZ"
            ).replace(tzinfo=datetime.timezone.utc)
        else:
            cosmos.last_cycle = None

        if not self.config.path.main:
            cosmos.log(
                "Error: CoSMoS main path not set! Do this by running cosmos.initialize(main_path) or passing main_path as input argument to cosmos.run()."
            )
            return

        from .main_loop import MainLoop
        from .model_loop import ModelLoop

        self.main_loop = MainLoop()
        self.model_loop = ModelLoop()

        # Why these things ?
        # self.main_loop.just_initialize = self.config.run.just_initialize
        # self.main_loop.run_models = self.config.run.run_models
        # self.main_loop.clean_up = self.config.run.clean_up

        self.main_loop.start(cycle=cycle)

    def stop(self, message: str) -> None:
        """Stop the forecast system and raise an exception.

        Parameters
        ----------
        message : str
            Error description to log.
        """
        # Raise exception
        self.log("Error: " + message)
        print("Error: " + message)
        raise Exception("CoSMoS was stopped, because of an error.")
        # self.model_loop.scheduler.cancel()
        # self.main_loop.scheduler.cancel()

    def log(self, message: str) -> None:
        """Write a timestamped message to ``cosmos.log`` and stdout.

        Parameters
        ----------
        message : str
            Log message.
        """
        print(message)
        log_file = os.path.join(self.config.path.main, "cosmos.log")
        tstr = (
            "["
            + datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            + " UTC] "
        )
        with open(log_file, "a") as f:
            f.write(tstr + message + "\n")
            f.close()

    def make_webviewer(self, scenario_name: str, cycle: str = None) -> None:
        """Build the web viewer for a scenario without running models.

        Parameters
        ----------
        scenario_name : str
            Scenario name.
        cycle : str, optional
            Cycle string (e.g. ``"20231213_00z"``).

        See Also
        -------
        cosmos.MainLoop
        cosmos.ModelLoop
        cosmos.webviewer.WebViewer

        """

        # if not cosmos.config.path.main:
        #     cosmos.log("Error: CoSMoS main path not set! Do this by running cosmos.initialize(main_path) or passing main_path as input argument to cosmos.run().")
        #     return

        # self.config.run.just_initialize  = True
        # self.config.run.run_models = False
        # self.run(scenario_name, cycle = cycle)

        # from .webviewer import WebViewer

        # wv = WebViewer(cosmos.config.webviewer.name)
        # wv.make()

        # # Delete job folder that was just created
        # if cosmos.config.run.run_mode != "parallel":
        #     fo.rmdir(os.path.join(cosmos.config.path.jobs,
        #                           cosmos.scenario_name))

        # if cosmos.config.run.upload:
        #     wv.upload()

        self.config.run.just_initialize = True
        self.config.run.run_models = False
        self.run(scenario_name, cycle=cycle)

        try:
            self.webviewer.make()
            if self.config.run.upload:
                current_path = os.getcwd()
                try:
                    self.webviewer.upload()
                except Exception:
                    print("An error occurred when uploading web viewer to server !!!")
                os.chdir(current_path)
        except Exception as e:
            print("An error occured while making web viewer !")
            print(f"Error: {e}")

        if cosmos.config.run.upload:
            self.webviewer.upload()

    def upload_webviewer(self, scenario_name: str, cycle: str = None) -> None:
        """Upload an existing web viewer to the remote server.

        Parameters
        ----------
        scenario_name : str
            Scenario name.
        cycle : str, optional
            Cycle string (e.g. ``"20231213_00z"``).

        See Also
        -------
        cosmos.MainLoop
        cosmos.ModelLoop
        cosmos.webviewer.WebViewer

        """
        from .cloud import Cloud
        from .scenario import Scenario
        from .webviewer import WebViewer

        self.cloud = Cloud()

        self.scenario = Scenario(scenario_name)
        self.cycle_string = cycle

        self.webviewer = WebViewer(self.config.webviewer.name)
        self.webviewer.cycle_path = os.path.join(
            self.webviewer.path, "data", scenario_name, cycle
        )

        # self.webviewer.cycle_path = os.path.join(self.config.path.main, "scenarios", scenario_name, self.cycle_string)
        self.webviewer.upload()

    def post_process(self, scenario_name: str, model=None, cycle: str = None) -> None:
        """Post-process model results without running simulations.

        Parameters
        ----------
        scenario_name : str
            Scenario name.
        model : list of str or ``"all"``, optional
            Model names to post-process, or ``"all"`` for every model.
        cycle : str, optional
            Cycle string.

        See Also
        -------
        cosmos.MainLoop
        cosmos.ModelLoop

        """

        if not cosmos.config.path.main:
            cosmos.log(
                "Error: CoSMoS main path not set! Do this by running cosmos.initialize(main_path) or passing main_path as input argument to cosmos.run()."
            )
            return

        # Overwrite settings for just_initialize and run_models
        self.config.run.just_initialize = True
        self.config.run.run_models = False
        self.run(scenario_name)

        mdls = []
        if model == "all":
            for mdl in cosmos.scenario.model:
                mdls.append(mdl)
        else:
            for model2 in model:
                for mdl in cosmos.scenario.model:
                    if mdl.name == model2:
                        mdls.append(mdl)

        # mm=cosmos.scenario.model[10]
        # mm.cycle_output_path = "d:\\cosmos\\run_folder\\scenarios\\nopp_forecast\\20240925_12z\\models\\sfincs_gom_0004_ensemble\\output"
        # mm.cycle_post_path   = "d:\\cosmos\\run_folder\\scenarios\\nopp_forecast\\20240925_12z\\models\\sfincs_gom_0004_ensemble\\timeseries"
        # mm.ensemble = True
        # mm.post_process()

        for mdl in mdls:
            fo.mkdir(mdl.cycle_path)
            fo.mkdir(mdl.cycle_input_path)
            fo.mkdir(mdl.cycle_output_path)
            fo.mkdir(mdl.cycle_figures_path)
            fo.mkdir(mdl.cycle_post_path)
            fo.mkdir(mdl.restart_flow_path)
            fo.mkdir(mdl.restart_wave_path)
            mdl.post_process()

        # Delete job folder that was just created
        if cosmos.config.run.run_mode != "parallel":
            fo.rmdir(os.path.join(cosmos.config.path.jobs, cosmos.scenario_name))

    def _read_cycle_from_scenario(self, scenario_name: str) -> str:
        """Peek at the scenario TOML file to extract the cycle string.

        Parameters
        ----------
        scenario_name : str
            Scenario name.

        Returns
        -------
        str or None
            Cycle string (e.g. ``"20231213_00z"``) if defined, otherwise ``None``.
        """
        import toml

        scenario_file = os.path.join(
            self.config.path.scenarios, scenario_name, "scenario.toml"
        )
        if not os.path.exists(scenario_file):
            return None
        try:
            sc = toml.load(scenario_file)
            return sc.get("cycle")
        except Exception:
            return None


# class Config:
#     def __init__(self):
#         self.main_path = None
#         self.run_mode  = "serial"

cosmos = CoSMoS()
