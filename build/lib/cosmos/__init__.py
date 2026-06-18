"""CoSMoS - Coastal Storm Modelling System.

Operational flood forecasting framework that orchestrates hydrodynamic, wave,
and morphodynamic models for coastal storm impact assessment.
"""

# Core classes (always available)
from .cluster import Cluster as Cluster
from .configuration import Configuration as Configuration
from .cosmos import CoSMoS as CoSMoS
from .cosmos import cosmos as cosmos
from .main_loop import MainLoop as MainLoop
from .model import Model as Model
from .model_loop import ModelLoop as ModelLoop
from .scenario import Scenario as Scenario
from .stations import Station as Station
from .stations import Stations as Stations

# Model-specific and supporting classes are imported lazily to avoid requiring
# all model dependencies (cht_delft3dfm, cht_xbeach, etc.) at import time.
# Access them via e.g. cosmos.sfincs.CoSMoS_SFINCS or import directly:
#   from cosmos.sfincs import CoSMoS_SFINCS
