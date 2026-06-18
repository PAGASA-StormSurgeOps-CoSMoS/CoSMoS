"""WaveWatch III (WW3) model integration for CoSMoS.

Handles reading, pre-processing, and job management for WaveWatch III
spectral wave models within the CoSMoS forecast framework.
"""

import os
import shutil

import cht_utils.fileio.xml as xml

from .cosmos import cosmos
from .model import Model


class CoSMoS_WW3(Model):
    """CoSMoS wrapper for WaveWatch III models."""

    def read_model_specific(self) -> None:
        """Read WW3-specific attributes from the model XML file."""
        self.wave_spinup_time = 0.0

        xml_obj = xml.xml2obj(self.file_name)
        if hasattr(xml_obj, "wavespinup"):
            self.wave_spinup_time = float(xml_obj.wavespinup[0].value)

    def move(self) -> None:
        """Remove the job folder after WW3 simulation completes."""
        job_path = os.path.join(cosmos.config.job_path, cosmos.scenario.name, self.name)
        files = os.listdir(job_path)
        for file_name in files:
            os.remove(os.path.join(job_path, file_name))
        try:
            os.rmdir(job_path)
        except Exception:
            cosmos.log(f"Could not delete {job_path}")

    def pre_process(self) -> None:
        """Copy all WW3 input files to the job folder."""
        job_path = os.path.join(cosmos.config.job_path, cosmos.scenario.name, self.name)
        if not os.path.exists(job_path):
            os.mkdir(job_path)

        src = os.path.join(self.path, "input")
        for file_name in os.listdir(src):
            full_file_name = os.path.join(src, file_name)
            if os.path.isfile(full_file_name):
                shutil.copy(full_file_name, job_path)

    def post_process(self) -> None:
        """Post-process WW3 output (not implemented)."""

    def submit_job(self) -> None:
        """Submit WW3 job (not implemented)."""
