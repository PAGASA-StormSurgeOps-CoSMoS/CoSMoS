"""Utility to convert TOML scenario files to YAML format."""

import toml
import yaml

ymlfile = r"c:\work\cosmos\run_folder\scenarios\hurricane_laura_03\scenario.yml"
tmlfile = r"c:\work\cosmos\run_folder\scenarios\hurricane_laura_03\scenario.toml"


xxx = toml.load(tmlfile)

with open(ymlfile, "w") as f:
    new_toml_string = yaml.dump(xxx, f, sort_keys=False)
