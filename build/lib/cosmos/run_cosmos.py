""" Run COSMOS for a single scenario. """

# TODO: Add multiple scenarios to create a testebd

from cosmos import cosmos

# main_path = r"p:\11206085-onr-fhics\03_cosmos"
main_path = r"c:\CoSMoS\run_folder"

scenario_name = "nopp_forecast_2024"

# CoSMoS is always initialized with the main path and optianlly a configuration file
cosmos.initialize(
    main_path,
    config_file="config_kva.toml",
    )

# Eventually, you can overwrite configuration settings like this:
# cosmos.config.run.mode = "single"
# cosmos.config.run.just_initialize = False
# cosmos.config.run.clean_up = False
# cosmos.config.run.run_models = False

# Finally, run the scenario and optionally specify the cycle
cosmos.run(scenario_name, cycle="20240627_00z")
