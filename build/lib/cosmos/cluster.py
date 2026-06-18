"""Conditional model execution and clustering for CoSMoS.

Groups models into clusters and applies run conditions (top-N, threshold,
ensemble threshold) to selectively execute models based on boundary water levels.
"""

import numpy as np

from .cosmos import cosmos


class Cluster:
    """Conditionally run models.

    Conditions:

    1. topn: sort models by boundary total water level and only simulate the Top N (keyword: topn) models.
    2. threshold: only run model if boundary total water level exceeds a threshold (keyword: boundary_twl_treshold).
    3. ensemble_threshold : always run model for "best track", but ensemble only if boundary threshold (keyword: boundary_twl_treshold) is exceeded.

    """

    # Run condition can be "topn", "threshold", and "ensemble_threshold"
    # 3 run condition options:
    # 1) topn      : sort models by boundary twl and only simulate Top N
    # 2) threshold : only run model is boundary twl exceeds threshold
    # 3) ensemble_threshold: always run model for "best track", but ensemble only if boundary threshold is exceeded

    def __init__(self, name: str) -> None:
        """Initialize cluster class.

        Parameters
        ----------
        name : str
            Cluster identifier.
        """
        self.name = name
        self.topn = 10
        self.hm0fac = 0.2
        self.boundary_twl_margin = 0.0
        self.use_threshold = True
        self.run_condition = "topn"
        self.model = {}
        self.ready = True

    def add_model(self, model: "Model") -> None:
        """Add a model to this cluster.

        Parameters
        ----------
        model : Model
            Model instance to be added.
        """
        self.model[model.name] = model
        model.cluster = self.name

    def check_ready_to_run(self) -> None:
        """Evaluate run conditions and remove models that do not qualify."""
        # Only need to check if this cluster was not ready before

        if self.run_condition == "topn":
            if not self.ready:
                okay = True

                # First check if all overall models have finished
                for model in self.model.values():
                    if model.flow_nested:
                        if model.flow_nested.status != "finished":
                            okay = False
                    if model.wave_nested:
                        if model.wave_nested.status != "finished":
                            okay = False

                if okay:
                    self.ready = True

                    # All overall models have finished
                    # Get peak water levels
                    for model in self.model.values():
                        try:
                            model.get_peak_boundary_conditions()
                        except Exception:
                            model.peak_boundary_twl = -999.0
                            model.peak_boundary_time = 0.0

                    zmax_all = np.zeros(len(self.model))

                    # Loop through all models
                    for i, model in enumerate(self.model.values()):
                        #                        zmax_all[i] = model.peak_boundary_twl
                        zmax_all[i] = (
                            model.peak_boundary_twl
                            - model.boundary_twl_treshold
                            - self.boundary_twl_margin
                        )

                    # Now sort
                    isort = np.argsort(zmax_all)[::-1]

                    itop = 0
                    keep_list = []
                    names = list(self.model)
                    for i in range(np.size(isort)):
                        if itop < self.topn:
                            model = self.model[names[isort[i]]]
                            iok = False
                            if self.use_threshold:
                                if zmax_all[isort[i]] > 0.0:
                                    #                                if model.peak_boundary_twl>model.boundary_twl_treshold:
                                    iok = True
                            else:
                                iok = True
                            if iok:
                                keep_list.append(model)
                                itop += 1
                        else:
                            break

                    for model in self.model.values():
                        if model not in keep_list:
                            print("Removing from scenario : " + model.name)
                            cosmos.scenario.model.remove(model)
        #                            # Also remove from cluster?
        #                            self.remove(model)

        else:
            self.ready = True

            okay = True

            for model in self.model.values():
                if model.flow_nested:
                    if model.flow_nested.status != "finished":
                        okay = False
                if model.wave_nested:
                    if model.wave_nested.status != "finished":
                        okay = False

                if okay:
                    if not model.peak_boundary_twl:
                        model.get_peak_boundary_conditions()
                        if model.peak_boundary_twl > model.boundary_twl_treshold:
                            print("Removing from scenario : " + model.name)
                            cosmos.scenario.model.remove(model)


cluster_dict = {}
