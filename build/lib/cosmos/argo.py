"""Argo Workflows integration for CoSMoS.

Submits and monitors model simulation jobs on Kubernetes via Argo Workflows,
enabling cloud-based parallel execution of forecast models.
"""

from typing import Any, Dict, Optional

from hera.shared import GlobalConfig
from hera.workflows import Task, Workflow, WorkflowStatus
from hera.workflows.models import WorkflowTemplateRef

from .cosmos import cosmos


class Argo:
    """Client for submitting and monitoring Argo Workflow jobs."""

    def __init__(self) -> None:
        """Initialize Argo client from CoSMoS cloud configuration."""
        GlobalConfig.namespace = cosmos.config.cloud_config.namespace
        GlobalConfig.host = cosmos.config.cloud_config.host
        GlobalConfig.verify_ssl = False
        GlobalConfig.token = cosmos.config.cloud_config.token

    def submit_template_job(
        self,
        workflow_name: str,
        job_name: str,
        subfolder: str,
        scenario: str,
        cycle: str,
        webviewerfolder: Optional[str] = None,
        tilingfolder: Optional[str] = None,
    ) -> Workflow:
        """Submit a template job to Argo.

        Parameters
        ----------
        workflow_name : str
            Name of the Argo workflow template to submit.
        job_name : str
            Name of the model for which the job is submitted.
        subfolder : str
            S3 subfolder to copy to the compute instance as input.
        scenario : str
            Name of the scenario.
        cycle : str
            Name of the cycle.
        webviewerfolder : str, optional
            Webviewer folder on the server.
        tilingfolder : str, optional
            Tiling folder (index and topobathy files).

        Returns
        -------
        Workflow
            The created Argo workflow object.
        """
        wt_ref = WorkflowTemplateRef(name=workflow_name, cluster_scope=False)

        mname = job_name.replace("_", "-")

        arguments: Dict[str, str] = {
            "subfolder": subfolder,
            "scenario": scenario,
            "cycle": cycle,
        }
        if webviewerfolder is not None:
            arguments["webviewerfolder"] = webviewerfolder
        if tilingfolder is not None:
            arguments["tilingfolder"] = tilingfolder

        w = Workflow(
            generate_name=f"{mname}-",
            workflow_template_ref=wt_ref,
            arguments=arguments,
        )

        cosmos.log("Cloud Workflow started")
        w.create()

        return w

    @staticmethod
    def submit_single_job(model: Any) -> Any:
        """Submit a single SFINCS job to Argo.

        Parameters
        ----------
        model : Any
            Model object with a ``name`` attribute.

        Returns
        -------
        Any
            The created workflow response.
        """
        with Workflow(
            model.name.replace("_", "-"),
            generate_name=True,
            workflow_template_ref="sfincs-workflow-xzv8r",
        ) as w:
            Task(
                "sfincs-cpu-argo",
                image="deltares/sfincs-cpu:latest",
                command=["/bin/bash", "-c", "--"],
                args=["chmod +x /data/run.sh && /data/run.sh"],
            )

        return w.create()

    @staticmethod
    def get_task_status(workflow: Workflow) -> str:
        """Query the current status of an Argo workflow.

        Parameters
        ----------
        workflow : Workflow
            The workflow object to query.

        Returns
        -------
        str
            Status string (e.g. ``"Succeeded"``, ``"Running"``, ``"Unknown"``).
        """
        status = "Unknown"

        try:
            wf = workflow.workflows_service.get_workflow(
                workflow.name, namespace=workflow.namespace
            )
            status = WorkflowStatus.from_argo_status(wf.status.phase)
            cosmos.log(f"Status of workflow: {status}")
        except BaseException as e:
            cosmos.log("An error occurred while checking status !")
            cosmos.log(str(e))

        return status
