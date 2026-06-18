"""Tsunami source generation for CoSMoS.

Generates initial tsunami water surface deformation from earthquake fault
parameters and writes the result as a NetCDF forcing file.
"""

import os

from cht_tsunami.tsunami import Tsunami

from .cosmos import cosmos


class CoSMoS_Tsunami(Tsunami):
    """Compute tsunami initial deformation from fault parameters.

    Inherits from :class:`cht_tsunami.tsunami.Tsunami` and adds a convenience
    method for generating the deformation from a CoSMoS scenario source file.
    """

    def __init__(self) -> None:
        """Initialize the tsunami object."""
        super().__init__()

    def generate_from_scenario(self, source_file: str) -> None:
        """Generate tsunami deformation from a fault source file.

        If *source_file* is not an absolute path, it is assumed to reside in
        the ``<scenario>/tsunami/`` folder.

        Parameters
        ----------
        source_file : str
            Path (absolute or filename only) to the earthquake fault file.
        """
        if not os.path.isfile(source_file):
            source_file = os.path.join(cosmos.scenario.path, "tsunami", source_file)

        self.read_fault_file(source_file)
        self.compute(smoothing=True, dx=1.0 / 60.0)

        output_file = os.path.join(cosmos.scenario.path, "tsunami", "tsunami.nc")
        self.write(output_file)
