from __future__ import annotations

import os
import time
import re
from datetime import date
from typing import Any
from urllib.parse import urlparse


SUCCESS_STATES = frozenset(
    {
        "COMPLETED",
        "FINISHED",
        "SUCCEEDED",
        "SUCCESS",
        "SUCCESSFUL",
    }
)
FAILURE_STATES = frozenset(
    {
        "CANCELLED",
        "DEAD",
        "ERROR",
        "FAILED",
        "FAILURE",
        "KILLED",
        "TERMINATED",
    }
)
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _allowlist(name: str) -> frozenset[str]:
    return frozenset(
        item.strip()
        for item in os.getenv(name, "").split(",")
        if item.strip()
    )


def _require_allowlisted(value: str, env_name: str, label: str) -> None:
    allowed = _allowlist(env_name)
    if not allowed:
        raise ValueError(f"{env_name} must contain at least one approved {label}.")
    if value not in allowed:
        raise ValueError(f"{label} is not allowlisted.")


def _obs_uri_allowed(uri: str) -> bool:
    parsed = urlparse(uri)
    if parsed.scheme != "obs" or not parsed.netloc:
        return False
    prefixes = _allowlist("SAT_ALLOWED_OBS_PREFIXES")
    return any(uri.startswith(prefix.rstrip("/") + "/") for prefix in prefixes)


def _credentials() -> Any:
    from huaweicloudsdkcore.auth.provider import CredentialProviderChain

    provider = CredentialProviderChain.get_default_credential_provider_chain("basic")
    credentials = provider.get_credentials()
    project_id = os.getenv("HUAWEICLOUD_PROJECT_ID", "").strip()
    if project_id and hasattr(credentials, "with_project_id"):
        credentials = credentials.with_project_id(project_id)
    return credentials


def _region() -> str:
    return os.getenv("HUAWEICLOUD_REGION", "la-south-2").strip()


def _mrs_client() -> Any:
    from huaweicloudsdkmrs.v2 import MrsClient
    from huaweicloudsdkmrs.v2.region.mrs_region import MrsRegion

    return (
        MrsClient.new_builder()
        .with_credentials(_credentials())
        .with_region(MrsRegion.value_of(_region()))
        .build()
    )


def _dataarts_client() -> Any:
    from huaweicloudsdkdataartsstudio.v1 import DataArtsStudioClient
    from huaweicloudsdkdataartsstudio.v1.region.dataartsstudio_region import (
        DataArtsStudioRegion,
    )

    return (
        DataArtsStudioClient.new_builder()
        .with_credentials(_credentials())
        .with_region(DataArtsStudioRegion.value_of(_region()))
        .build()
    )


def submit_mrs(parameters: dict[str, Any], request_id: str) -> dict[str, Any]:
    from huaweicloudsdkmrs.v2.model import CreateExecuteJobRequest, JobExecution

    cluster_id = str(parameters.get("cluster_id", "")).strip()
    program_path = str(parameters.get("program_path", "")).strip()
    job_name = str(parameters.get("job_name") or f"sat-{request_id[:8]}").strip()
    arguments = parameters.get("arguments", [])
    properties = parameters.get("properties", {})

    _require_allowlisted(cluster_id, "SAT_ALLOWED_MRS_CLUSTER_IDS", "MRS cluster")
    if not _obs_uri_allowed(program_path):
        raise ValueError("MRS program_path must be inside SAT_ALLOWED_OBS_PREFIXES.")
    if not SAFE_NAME.fullmatch(job_name):
        raise ValueError("MRS job_name contains unsupported characters.")
    if not isinstance(arguments, list) or not all(isinstance(item, str) for item in arguments):
        raise ValueError("MRS arguments must be a list of strings.")
    if len(arguments) > 64 or any(len(item) > 2048 for item in arguments):
        raise ValueError("MRS arguments exceed the production safety limit.")
    if not isinstance(properties, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in properties.items()
    ):
        raise ValueError("MRS properties must be a string map.")

    body = JobExecution(
        job_type="SparkSubmit",
        job_name=job_name,
        arguments=[program_path, *arguments],
        properties=properties,
    )
    response = _mrs_client().create_execute_job(
        CreateExecuteJobRequest(cluster_id=cluster_id, body=body)
    )
    result = response.job_submit_result
    job_id = str(getattr(result, "job_id", "") or "")
    if not job_id:
        raise RuntimeError("Huawei Cloud accepted no MRS job identifier.")
    return {
        "cloud_job_id": job_id,
        "provider_state": str(getattr(result, "state", "") or "SUBMITTED"),
        "cluster_id": cluster_id,
        "job_name": job_name,
        "write_calls": 1,
    }


def poll_mrs(parameters: dict[str, Any], cloud_job_id: str) -> dict[str, Any]:
    from huaweicloudsdkmrs.v2.model import ShowSingleJobExeRequest

    cluster_id = str(parameters.get("cluster_id", "")).strip()
    _require_allowlisted(cluster_id, "SAT_ALLOWED_MRS_CLUSTER_IDS", "MRS cluster")
    response = _mrs_client().show_single_job_exe(
        ShowSingleJobExeRequest(
            job_execution_id=cloud_job_id,
            cluster_id=cluster_id,
        )
    )
    detail = response.job_detail
    state = str(getattr(detail, "job_state", "") or "UNKNOWN").upper()
    result = str(getattr(detail, "job_result", "") or "").upper()
    terminal_value = result or state
    terminal = terminal_value in SUCCESS_STATES or terminal_value in FAILURE_STATES
    succeeded = terminal_value in SUCCESS_STATES
    return {
        "terminal": terminal,
        "succeeded": succeeded,
        "provider_state": state,
        "provider_result": result,
        "progress": float(getattr(detail, "job_progress", 0.0) or 0.0),
        "started_time": getattr(detail, "started_time", None),
        "finished_time": getattr(detail, "finished_time", None),
        "app_id": str(getattr(detail, "app_id", "") or ""),
        "write_calls": 0,
    }


def cancel_mrs(parameters: dict[str, Any], cloud_job_id: str) -> dict[str, Any]:
    from huaweicloudsdkmrs.v2.model import StopJobRequest

    cluster_id = str(parameters.get("cluster_id", "")).strip()
    _require_allowlisted(cluster_id, "SAT_ALLOWED_MRS_CLUSTER_IDS", "MRS cluster")
    _mrs_client().stop_job(
        StopJobRequest(job_execution_id=cloud_job_id, cluster_id=cluster_id)
    )
    return {"cancel_requested": True, "write_calls": 1}


def submit_dataarts(parameters: dict[str, Any], request_id: str) -> dict[str, Any]:
    from huaweicloudsdkdataartsstudio.v1.model import (
        CreateFactorySupplementDataInstanceRequest,
        CreateFactorySupplementDataInstanceRequestBody,
    )

    workspace_id = str(parameters.get("workspace_id", "")).strip()
    job_name = str(parameters.get("job_name", "")).strip()
    start_date = str(parameters.get("start_date") or date.today().isoformat())
    end_date = str(parameters.get("end_date") or start_date)

    _require_allowlisted(
        workspace_id,
        "SAT_ALLOWED_DATAARTS_WORKSPACE_IDS",
        "DataArts workspace",
    )
    _require_allowlisted(
        job_name,
        "SAT_ALLOWED_DATAARTS_JOB_NAMES",
        "DataArts job",
    )
    body = CreateFactorySupplementDataInstanceRequestBody(
        name=f"sat-{request_id[:8]}",
        job_name=job_name,
        start_date=start_date,
        end_date=end_date,
        parallel=1,
        is_stop_when_fail=True,
        force="false",
    )
    submitted_after_epoch_ms = int(time.time() * 1000)
    response = _dataarts_client().create_factory_supplement_data_instance(
        CreateFactorySupplementDataInstanceRequest(
            workspace=workspace_id,
            body=body,
        )
    )
    request_trace_id = str(getattr(response, "x_request_id", "") or request_id)
    return {
        "cloud_job_id": request_trace_id,
        "provider_state": "SUBMITTED",
        "workspace_id": workspace_id,
        "job_name": job_name,
        "submitted_after_epoch_ms": submitted_after_epoch_ms,
        "write_calls": 1,
    }


def poll_dataarts(
    parameters: dict[str, Any],
    cloud_job_id: str,
    submitted_after_epoch_ms: int = 0,
) -> dict[str, Any]:
    from huaweicloudsdkdataartsstudio.v1.model import (
        ListFactoryJobInstancesByNameRequest,
    )

    workspace_id = str(parameters.get("workspace_id", "")).strip()
    job_name = str(parameters.get("job_name", "")).strip()
    _require_allowlisted(
        workspace_id,
        "SAT_ALLOWED_DATAARTS_WORKSPACE_IDS",
        "DataArts workspace",
    )
    _require_allowlisted(
        job_name,
        "SAT_ALLOWED_DATAARTS_JOB_NAMES",
        "DataArts job",
    )
    response = _dataarts_client().list_factory_job_instances_by_name(
        ListFactoryJobInstancesByNameRequest(
            workspace=workspace_id,
            limit=10,
            offset=0,
            job_name=job_name,
            min_plan_time=submitted_after_epoch_ms or None,
        )
    )
    instances = sorted(
        list(getattr(response, "instances", []) or []),
        key=lambda item: int(getattr(item, "submit_time", 0) or 0),
        reverse=True,
    )
    if not instances:
        return {
            "terminal": False,
            "succeeded": False,
            "provider_state": "WAITING_FOR_INSTANCE",
            "request_trace_id": cloud_job_id,
            "write_calls": 0,
        }
    instance = instances[0]
    state = str(getattr(instance, "status", "") or "UNKNOWN").upper()
    terminal = state in SUCCESS_STATES or state in FAILURE_STATES
    return {
        "terminal": terminal,
        "succeeded": state in SUCCESS_STATES,
        "provider_state": state,
        "instance_id": str(getattr(instance, "instance_id", "") or ""),
        "job_id": str(getattr(instance, "job_id", "") or ""),
        "start_time": getattr(instance, "start_time", None),
        "end_time": getattr(instance, "end_time", None),
        "write_calls": 0,
    }


def submit(target: str, parameters: dict[str, Any], request_id: str) -> dict[str, Any]:
    if target == "mrs":
        return submit_mrs(parameters, request_id)
    if target == "dataarts":
        return submit_dataarts(parameters, request_id)
    if target == "dry_run":
        return {
            "cloud_job_id": f"dry-run-{request_id}",
            "provider_state": "SUCCEEDED",
            "write_calls": 0,
        }
    raise ValueError(f"Unsupported execution target: {target}")


def poll(
    target: str,
    parameters: dict[str, Any],
    cloud_job_id: str,
    submission: dict[str, Any],
) -> dict[str, Any]:
    if target == "mrs":
        return poll_mrs(parameters, cloud_job_id)
    if target == "dataarts":
        return poll_dataarts(
            parameters,
            cloud_job_id,
            int(submission.get("submitted_after_epoch_ms", 0) or 0),
        )
    if target == "dry_run":
        return {
            "terminal": True,
            "succeeded": True,
            "provider_state": "SUCCEEDED",
            "write_calls": 0,
        }
    raise ValueError(f"Unsupported execution target: {target}")


def cancel(target: str, parameters: dict[str, Any], cloud_job_id: str) -> dict[str, Any]:
    if target == "mrs":
        return cancel_mrs(parameters, cloud_job_id)
    if target == "dry_run":
        return {"cancel_requested": True, "write_calls": 0}
    raise ValueError(f"Cancellation is not implemented for execution target: {target}")
