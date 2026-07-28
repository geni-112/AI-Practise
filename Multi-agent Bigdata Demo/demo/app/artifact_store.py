from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from .maas_client import maas_status
from .models import ArtifactReviewRequest, CloudBindingRequest, CloudResourceProbeRequest, ImportReviewRequest
from .huawei_readonly_probe import READONLY_PROBE_ENV, run_real_huaweicloud_readonly_probe
from .production_control import canonical_release_hash

APP_ROOT = Path(__file__).resolve().parents[1]
GENERATED_ROOT = APP_ROOT / "generated"
REVIEWABLE_KINDS = {"pyspark", "sql", "dag"}
RELEASE_DIR_NAME = "release"
RELEASE_STATUS_NAME = "release_status.json"
CLOUD_BINDING_STATUS_NAME = "cloud_binding_status.json"
IMPORT_REVIEW_STATUS_NAME = "import_review_status.json"
DATAARTS_STANDARD_STATUS_NAME = "dataarts_standard_status.json"
CLOUD_RESOURCE_PROBE_STATUS_NAME = "cloud_resource_probe_status.json"


def persist_run_package(state: dict[str, Any]) -> dict[str, Any]:
    run_id = state["run_id"]
    run_dir = GENERATED_ROOT / run_id
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    artifacts = []
    review_items: dict[str, dict[str, Any]] = {}
    for artifact in state["artifacts"]:
        artifact_path = artifacts_dir / safe_artifact_name(artifact["name"])
        artifact_path.write_text(artifact["content"], encoding="utf-8")
        review_required = artifact["kind"] in REVIEWABLE_KINDS
        status = "pending" if review_required else "not_required"
        artifact_entry = {
            **artifact,
            "path": str(artifact_path.relative_to(APP_ROOT)).replace("\\", "/"),
            "url": f"/generated/{run_id}/artifacts/{artifact_path.name}",
            "review_required": review_required,
            "review_status": status,
        }
        artifacts.append(artifact_entry)
        review_items[artifact["name"]] = {
            "kind": artifact["kind"],
            "path": artifact_entry["path"],
            "url": artifact_entry["url"],
            "review_required": review_required,
            "status": status,
            "artifact_hash": file_sha256(artifact_path),
            "reviewer": None,
            "note": "",
            "updated_at": None,
        }

    write_json(run_dir / "request.json", {
        "prompt": state["request"].prompt,
        "scenario": state["request"].scenario,
        "use_maas": state["request"].use_maas,
        "template_id": state["request"].template_id,
        "template_variables": state["request"].template_variables,
    })
    (run_dir / "prompt.txt").write_text(state["request"].prompt, encoding="utf-8")
    write_json(run_dir / "synthetic_rows.json", state["synthetic_rows"])
    write_json(run_dir / "gold_preview.json", state["gold_rows"])
    write_json(run_dir / "contract_audit.json", state.get("contract_audit", {}))
    write_json(run_dir / "local_execution.json", state.get("local_execution", {}))
    write_json(run_dir / "quality_gates.json", state["quality_gates"])
    write_json(run_dir / "lineage_manifest.json", state["lineage"])
    write_json(run_dir / "maas_trace.json", {
        "status": maas_status(),
        "used": bool(state.get("maas_used")),
        "error": state.get("maas_error"),
        "strategy": state.get("maas_strategy"),
        "model_summary_present": bool(state.get("model_summary")),
    })

    review = {
        "run_id": run_id,
        "updated_at": now_iso(),
        "artifacts": review_items,
    }
    write_json(run_dir / "review_status.json", review)

    manifest = {
        "run_id": run_id,
        "generated_at": now_iso(),
        "request": {
            "scenario": state["request"].scenario,
            "template_id": state["request"].template_id,
            "template_variables": state["request"].template_variables,
        },
        "maas": {
            "status": maas_status(),
            "used": bool(state.get("maas_used")),
            "error": state.get("maas_error"),
            "strategy": state.get("maas_strategy"),
        },
        "execution": {
            "local_dev": state["decision"]["local_dev"],
            "production": state["decision"]["production"],
            "cloud_deployed": False,
        },
        "artifacts": [
            {
                "name": artifact["name"],
                "kind": artifact["kind"],
                "path": artifact["path"],
                "url": artifact["url"],
                "review_required": artifact["review_required"],
            }
            for artifact in artifacts
        ],
        "quality_gates": state["quality_gates"],
        "contract_audit": {
            "status": state.get("contract_audit", {}).get("status", "missing"),
            "summary": state.get("contract_audit", {}).get("summary", ""),
        },
        "local_execution": {
            "status": state.get("local_execution", {}).get("status", "missing"),
            "summary": state.get("local_execution", {}).get("metric_reconciliation", {}).get("summary", ""),
        },
        "lineage": state["lineage"],
    }
    write_json(run_dir / "run_manifest.json", manifest)

    return {
        "artifacts": artifacts,
        "generated_dir": str(run_dir),
        "generated_url": f"/generated/{run_id}/",
        "review": review,
    }


def save_artifact_review(
    run_id: str,
    artifact_name: str,
    request: ArtifactReviewRequest,
) -> dict[str, Any]:
    run_dir = resolve_run_dir(run_id)
    review_path = run_dir / "review_status.json"
    if not review_path.exists():
        raise FileNotFoundError(f"Review state not found for run {run_id}")

    review = read_json(review_path)
    safe_name = safe_artifact_name(artifact_name)
    artifacts = review.get("artifacts", {})
    if safe_name not in artifacts:
        raise FileNotFoundError(f"Artifact {safe_name} not found in run {run_id}")
    if not artifacts[safe_name].get("review_required", False):
        raise ValueError(f"Artifact {safe_name} does not require review")

    updated_at = now_iso()
    artifact_path = APP_ROOT / artifacts[safe_name]["path"]
    artifact_hash = file_sha256(artifact_path)
    artifacts[safe_name].update({
        "status": request.status,
        "artifact_hash": artifact_hash,
        "reviewer": request.reviewer.strip() or "local_operator",
        "note": request.note.strip(),
        "updated_at": updated_at,
    })
    review["updated_at"] = updated_at
    write_json(review_path, review)

    return {
        "run_id": run_id,
        "artifact_name": safe_name,
        "status": request.status,
        "artifact_hash": artifacts[safe_name]["artifact_hash"],
        "reviewer": artifacts[safe_name]["reviewer"],
        "note": artifacts[safe_name]["note"],
        "updated_at": updated_at,
        "review": review,
    }


def get_release_package_status(run_id: str) -> dict[str, Any]:
    run_dir = resolve_existing_run_dir(run_id)
    readiness = release_readiness(run_dir)
    release_status = read_optional_json(run_dir / RELEASE_STATUS_NAME)
    if release_status and readiness["ready"]:
        return release_response(
            run_id=run_id,
            status="generated",
            ready=True,
            message="Release package is generated locally. Cloud execution remains blocked.",
            readiness=readiness,
            release=release_status,
        )
    if release_status:
        release_status["stale"] = True
        return release_response(
            run_id=run_id,
            status="blocked",
            ready=False,
            message="Release package is stale because approvals or gates changed.",
            readiness=readiness,
            release=release_status,
        )
    if readiness["ready"]:
        return release_response(
            run_id=run_id,
            status="ready",
            ready=True,
            message="PySpark, SQL, and DataArts DAG are approved. A local release package can be generated.",
            readiness=readiness,
        )
    return release_response(
        run_id=run_id,
        status="blocked",
        ready=False,
        message="Approve all reviewable artifacts and clear failed quality gates before generating a release package.",
        readiness=readiness,
    )


def create_release_package(run_id: str) -> dict[str, Any]:
    run_dir = resolve_existing_run_dir(run_id)
    readiness = release_readiness(run_dir)
    if not readiness["ready"]:
        return release_response(
            run_id=run_id,
            status="blocked",
            ready=False,
            message="Release package was not generated because approvals or quality gates are incomplete.",
            readiness=readiness,
        )

    release_dir = run_dir / RELEASE_DIR_NAME
    release_dir.mkdir(parents=True, exist_ok=True)
    generated_at = now_iso()
    request = read_json(run_dir / "request.json")
    run_manifest = read_json(run_dir / "run_manifest.json")
    review = read_json(run_dir / "review_status.json")
    quality_gates = read_json(run_dir / "quality_gates.json")

    approval_summary = build_approval_summary(
        run_id=run_id,
        generated_at=generated_at,
        review=review,
        quality_gates=quality_gates,
        readiness=readiness,
    )
    import_package = build_dataarts_import_package(
        run_id=run_id,
        generated_at=generated_at,
        request=request,
        run_manifest=run_manifest,
        review=review,
    )
    deployment_plan = render_deployment_plan(
        run_id=run_id,
        generated_at=generated_at,
        request=request,
        run_manifest=run_manifest,
        approved_artifacts=readiness["approved_artifacts"],
    )
    rollback_plan = render_rollback_plan(run_id, generated_at)
    environment_profile = build_environment_profile(
        run_id=run_id,
        generated_at=generated_at,
        request=request,
    )
    cloud_parameter_map = build_cloud_parameter_map(environment_profile)
    preflight = build_deployment_preflight(
        run_id=run_id,
        generated_at=generated_at,
        readiness=readiness,
        environment_profile=environment_profile,
        cloud_parameter_map=cloud_parameter_map,
        import_package=import_package,
        run_manifest=run_manifest,
        release_dir=release_dir,
    )

    write_json(release_dir / "approval_summary.json", approval_summary)
    write_json(release_dir / "dataarts_import_package.json", import_package)
    write_json(release_dir / "cloud_parameter_map.json", cloud_parameter_map)
    write_json(release_dir / "deployment_preflight.json", preflight)
    (release_dir / "environment_profile.yaml").write_text(
        render_environment_profile(environment_profile),
        encoding="utf-8",
    )
    (release_dir / "deployment_plan.yaml").write_text(deployment_plan, encoding="utf-8")
    (release_dir / "rollback_plan.md").write_text(rollback_plan, encoding="utf-8")

    release_files = [
        release_file_entry(run_id, release_dir, "approval_summary.json", "Artifact approvals and quality-gate evidence."),
        release_file_entry(run_id, release_dir, "dataarts_import_package.json", "Preview import package for DataArts Factory."),
        release_file_entry(run_id, release_dir, "environment_profile.yaml", "Target Huawei Cloud environment contract with placeholders."),
        release_file_entry(run_id, release_dir, "cloud_parameter_map.json", "Cloud placeholder-to-approval map."),
        release_file_entry(run_id, release_dir, "deployment_preflight.json", "Deployment preflight checks and cloud execution lock evidence."),
        release_file_entry(run_id, release_dir, "deployment_plan.yaml", "Manual deployment plan for OBS, MRS Spark, DWS, and DataArts."),
        release_file_entry(run_id, release_dir, "rollback_plan.md", "Rollback and recovery checklist."),
    ]
    release_manifest = {
        "run_id": run_id,
        "status": "generated",
        "generated_at": generated_at,
        "package_type": "local_release_candidate",
        "cloud_execution": "blocked",
        "source_run_manifest": f"/generated/{run_id}/run_manifest.json",
        "approved_artifacts": readiness["approved_artifacts"],
        "artifact_hashes": {
            name: review["artifacts"][name]["artifact_hash"]
            for name in readiness["approved_artifacts"]
        },
        "failed_gates": [],
        "environment": {
            "region": environment_profile["region"]["id"],
            "storage_layers": list(environment_profile["storage"]["obs_layers"].keys()),
            "cloud_parameters": cloud_parameter_map["required_bindings"],
        },
        "preflight": {
            "status": preflight["status"],
            "summary": preflight["summary"],
            "cloud_execution": preflight["cloud_execution"],
            "warnings": preflight["warnings"],
            "failed": preflight["failed"],
        },
        "files": release_files,
        "next_action": "Import package only after cloud resources, IAM, OBS paths, MRS cluster, DWS connection, and DataArts workspace are explicitly approved.",
    }
    release_manifest["release_hash"] = canonical_release_hash(release_manifest)
    write_json(release_dir / "release_manifest.json", release_manifest)
    release_files.append(release_file_entry(run_id, release_dir, "release_manifest.json", "Release package file index."))

    release_status = {
        **release_manifest,
        "files": release_files,
        "release_url": f"/generated/{run_id}/{RELEASE_DIR_NAME}/release_manifest.json",
    }
    write_json(run_dir / RELEASE_STATUS_NAME, release_status)
    return release_response(
        run_id=run_id,
        status="generated",
        ready=True,
        message="Release package generated locally. Cloud execution remains blocked.",
        readiness=readiness,
        release=release_status,
    )


def get_cloud_binding_status(run_id: str) -> dict[str, Any]:
    run_dir = resolve_existing_run_dir(run_id)
    binding_status = read_optional_json(run_dir / CLOUD_BINDING_STATUS_NAME)
    if binding_status:
        return cloud_binding_response(
            run_id=run_id,
            status=binding_status["status"],
            ready_for_import_review=binding_status["ready_for_import_review"],
            message=binding_status["message"],
            binding=binding_status,
        )

    release_status = read_optional_json(run_dir / RELEASE_STATUS_NAME)
    if not release_status:
        return cloud_binding_response(
            run_id=run_id,
            status="blocked",
            ready_for_import_review=False,
            message="Generate a release package before cloud parameter binding.",
            missing_bindings=[],
        )

    parameter_map = read_optional_json(run_dir / RELEASE_DIR_NAME / "cloud_parameter_map.json") or {}
    required = sorted((parameter_map.get("required_bindings") or {}).keys())
    return cloud_binding_response(
        run_id=run_id,
        status="needs_binding",
        ready_for_import_review=False,
        message="Cloud parameters are not bound. Use local simulation or operator-provided values for validation.",
        missing_bindings=required,
        binding={
            "run_id": run_id,
            "status": "needs_binding",
            "cloud_execution": "blocked",
            "required_bindings": required,
        },
    )


def create_cloud_binding_simulation(
    run_id: str,
    request: CloudBindingRequest,
) -> dict[str, Any]:
    run_dir = resolve_existing_run_dir(run_id)
    release_dir = run_dir / RELEASE_DIR_NAME
    release_status = read_optional_json(run_dir / RELEASE_STATUS_NAME)
    if not release_status:
        return cloud_binding_response(
            run_id=run_id,
            status="blocked",
            ready_for_import_review=False,
            message="Release package must be generated before cloud parameter binding.",
        )

    parameter_map = read_json(release_dir / "cloud_parameter_map.json")
    import_package = read_json(release_dir / "dataarts_import_package.json")
    required_bindings = parameter_map.get("required_bindings") or {}
    bindings = (
        sample_cloud_bindings(run_id, required_bindings)
        if request.mode == "local_simulation" and not request.bindings
        else {key: str(value).strip() for key, value in request.bindings.items()}
    )
    checks = validate_cloud_bindings(
        bindings=bindings,
        required_bindings=required_bindings,
        import_package=import_package,
    )
    failed_checks = [check for check in checks if check["status"] == "failed"]
    generated_at = now_iso()
    status = "simulated_ready" if not failed_checks else "needs_fix"
    resolved_import_package = resolve_dataarts_import_package(import_package, bindings)
    readiness = {
        "run_id": run_id,
        "generated_at": generated_at,
        "status": "ready_for_import_review" if not failed_checks else "needs_fix",
        "cloud_execution": "blocked",
        "summary": f"{sum(1 for item in checks if item['status'] == 'passed')} checks passed, {len(failed_checks)} failed.",
        "next_action": "Review these bindings in the cloud console before importing DataArts artifacts.",
        "simulation": request.mode == "local_simulation",
    }
    binding_payload = {
        "run_id": run_id,
        "generated_at": generated_at,
        "agent": "cloud-binding-agent",
        "mode": request.mode,
        "status": status,
        "ready_for_import_review": not failed_checks,
        "cloud_execution": "blocked",
        "message": (
            "Local cloud binding simulation passed. Cloud execution remains blocked."
            if not failed_checks
            else "Cloud binding validation failed. Fix missing or invalid bindings."
        ),
        "reviewer": request.reviewer.strip() or "local_operator",
        "note": request.note.strip(),
        "bindings": bindings,
        "checks": checks,
        "missing_bindings": missing_cloud_bindings(bindings, required_bindings),
        "failed_checks": [f"{check['id']}: {check['name']}" for check in failed_checks],
        "files": [],
    }

    write_json(release_dir / "cloud_binding_simulation.json", binding_payload)
    write_json(release_dir / "resolved_dataarts_import_package.json", resolved_import_package)
    write_json(release_dir / "cloud_import_readiness.json", readiness)

    new_files = [
        release_file_entry(run_id, release_dir, "cloud_binding_simulation.json", "Local cloud parameter binding validation."),
        release_file_entry(run_id, release_dir, "resolved_dataarts_import_package.json", "DataArts import preview with locally simulated bindings."),
        release_file_entry(run_id, release_dir, "cloud_import_readiness.json", "Readiness checkpoint before cloud import approval."),
    ]
    binding_payload["files"] = new_files
    release_status = append_release_files(release_status, new_files)
    release_status["cloud_binding"] = {
        "status": binding_payload["status"],
        "ready_for_import_review": binding_payload["ready_for_import_review"],
        "cloud_execution": "blocked",
        "mode": request.mode,
        "summary": readiness["summary"],
        "failed_checks": binding_payload["failed_checks"],
    }
    write_json(run_dir / RELEASE_STATUS_NAME, release_status)
    release_manifest_path = release_dir / "release_manifest.json"
    if release_manifest_path.exists():
        release_manifest = append_release_files(read_json(release_manifest_path), new_files)
        release_manifest["cloud_binding"] = release_status["cloud_binding"]
        write_json(release_manifest_path, release_manifest)

    write_json(run_dir / CLOUD_BINDING_STATUS_NAME, binding_payload)
    return cloud_binding_response(
        run_id=run_id,
        status=binding_payload["status"],
        ready_for_import_review=binding_payload["ready_for_import_review"],
        message=binding_payload["message"],
        binding=binding_payload,
        missing_bindings=binding_payload["missing_bindings"],
        failed_checks=binding_payload["failed_checks"],
    )


def get_import_review_status(run_id: str) -> dict[str, Any]:
    run_dir = resolve_existing_run_dir(run_id)
    import_review = read_optional_json(run_dir / IMPORT_REVIEW_STATUS_NAME)
    if import_review:
        return import_review_response(
            run_id=run_id,
            status=import_review["status"],
            ready_for_operator_handoff=import_review["ready_for_operator_handoff"],
            message=import_review["message"],
            review=import_review,
        )

    binding_status = read_optional_json(run_dir / CLOUD_BINDING_STATUS_NAME)
    if not binding_status:
        return import_review_response(
            run_id=run_id,
            status="blocked",
            ready_for_operator_handoff=False,
            message="Run cloud parameter binding before import review.",
        )
    if not binding_status.get("ready_for_import_review"):
        return import_review_response(
            run_id=run_id,
            status="needs_binding_fix",
            ready_for_operator_handoff=False,
            message="Cloud parameter binding is not ready for import review.",
            failed_checks=binding_status.get("failed_checks", []),
        )

    return import_review_response(
        run_id=run_id,
        status="ready_for_review",
        ready_for_operator_handoff=False,
        message="Cloud binding is ready. Generate an import review handoff package before any cloud import.",
        review={
            "run_id": run_id,
            "status": "ready_for_review",
            "cloud_execution": "blocked",
            "binding_status": binding_status.get("status"),
        },
    )


def create_import_review(
    run_id: str,
    request: ImportReviewRequest,
) -> dict[str, Any]:
    run_dir = resolve_existing_run_dir(run_id)
    release_dir = run_dir / RELEASE_DIR_NAME
    release_status = read_optional_json(run_dir / RELEASE_STATUS_NAME)
    binding_status = read_optional_json(run_dir / CLOUD_BINDING_STATUS_NAME)
    if not release_status:
        return import_review_response(
            run_id=run_id,
            status="blocked",
            ready_for_operator_handoff=False,
            message="Generate a release package before import review.",
        )
    if not binding_status or not binding_status.get("ready_for_import_review"):
        return import_review_response(
            run_id=run_id,
            status="needs_binding",
            ready_for_operator_handoff=False,
            message="Generate a successful cloud binding simulation before import review.",
            failed_checks=(binding_status or {}).get("failed_checks", []),
        )

    generated_at = now_iso()
    readiness = release_readiness(run_dir)
    preflight = read_json(release_dir / "deployment_preflight.json")
    import_readiness = read_json(release_dir / "cloud_import_readiness.json")
    resolved_import_package = read_json(release_dir / "resolved_dataarts_import_package.json")
    review_state = read_json(run_dir / "review_status.json")
    release_manifest = read_json(release_dir / "release_manifest.json")

    final_manifest = build_final_import_manifest(
        run_id=run_id,
        generated_at=generated_at,
        release_status=release_status,
        binding_status=binding_status,
        import_readiness=import_readiness,
    )
    checks = validate_import_review(
        readiness=readiness,
        release_status=release_status,
        release_manifest=release_manifest,
        binding_status=binding_status,
        preflight=preflight,
        import_readiness=import_readiness,
        resolved_import_package=resolved_import_package,
        final_manifest=final_manifest,
    )
    failed_checks = [check for check in checks if check["status"] == "failed"]
    status = "operator_handoff_ready" if not failed_checks else "needs_fix"
    message = (
        "Import review handoff is ready. Cloud execution remains blocked."
        if not failed_checks
        else "Import review found blocking issues. Fix them before handoff."
    )
    review_payload = {
        "run_id": run_id,
        "generated_at": generated_at,
        "agent": "import-review-agent",
        "status": status,
        "ready_for_operator_handoff": not failed_checks,
        "cloud_execution": "blocked",
        "message": message,
        "reviewer": request.reviewer.strip() or "local_operator",
        "note": request.note.strip(),
        "checks": checks,
        "failed_checks": [f"{check['id']}: {check['name']}" for check in failed_checks],
        "source": {
            "release_status": release_status.get("status"),
            "binding_status": binding_status.get("status"),
            "import_readiness": import_readiness.get("status"),
            "review_updated_at": review_state.get("updated_at"),
        },
        "files": [],
    }
    handoff_markdown = render_operator_handoff(
        run_id=run_id,
        generated_at=generated_at,
        review_payload=review_payload,
        final_manifest=final_manifest,
    )

    write_json(release_dir / "cloud_import_review.json", review_payload)
    write_json(release_dir / "final_import_manifest.json", final_manifest)
    (release_dir / "operator_handoff.md").write_text(handoff_markdown, encoding="utf-8")

    new_files = [
        release_file_entry(run_id, release_dir, "cloud_import_review.json", "Import review checks before operator handoff."),
        release_file_entry(run_id, release_dir, "operator_handoff.md", "Manual handoff instructions for a future cloud operator."),
        release_file_entry(run_id, release_dir, "final_import_manifest.json", "Final local import manifest; execution remains blocked."),
    ]
    review_payload["files"] = new_files
    release_status = append_release_files(release_status, new_files)
    release_status["import_review"] = {
        "status": review_payload["status"],
        "ready_for_operator_handoff": review_payload["ready_for_operator_handoff"],
        "cloud_execution": "blocked",
        "summary": f"{sum(1 for item in checks if item['status'] == 'passed')} checks passed, {len(failed_checks)} failed.",
        "failed_checks": review_payload["failed_checks"],
    }
    write_json(run_dir / RELEASE_STATUS_NAME, release_status)
    release_manifest = append_release_files(release_manifest, new_files)
    release_manifest["import_review"] = release_status["import_review"]
    write_json(release_dir / "release_manifest.json", release_manifest)
    write_json(run_dir / IMPORT_REVIEW_STATUS_NAME, review_payload)

    return import_review_response(
        run_id=run_id,
        status=review_payload["status"],
        ready_for_operator_handoff=review_payload["ready_for_operator_handoff"],
        message=review_payload["message"],
        review=review_payload,
        failed_checks=review_payload["failed_checks"],
    )


def get_dataarts_standardization_status(run_id: str) -> dict[str, Any]:
    run_dir = resolve_existing_run_dir(run_id)
    status_payload = read_optional_json(run_dir / DATAARTS_STANDARD_STATUS_NAME)
    if status_payload:
        return dataarts_standardization_response(
            run_id=run_id,
            status=status_payload["status"],
            ready_for_cloud_probe=status_payload["ready_for_cloud_probe"],
            message=status_payload["message"],
            standardization=status_payload,
        )

    release_status = read_optional_json(run_dir / RELEASE_STATUS_NAME)
    if not release_status:
        return dataarts_standardization_response(
            run_id=run_id,
            status="blocked",
            ready_for_cloud_probe=False,
            message="Generate a release package before standardizing the DataArts package.",
        )

    return dataarts_standardization_response(
        run_id=run_id,
        status="ready",
        ready_for_cloud_probe=False,
        message="Release package exists. Generate the standardized DataArts import package before cloud resource probing.",
        standardization={
            "run_id": run_id,
            "status": "ready",
            "cloud_execution": "blocked",
        },
    )


def create_dataarts_standardization(run_id: str) -> dict[str, Any]:
    run_dir = resolve_existing_run_dir(run_id)
    release_dir = run_dir / RELEASE_DIR_NAME
    release_status = read_optional_json(run_dir / RELEASE_STATUS_NAME)
    if not release_status:
        return dataarts_standardization_response(
            run_id=run_id,
            status="blocked",
            ready_for_cloud_probe=False,
            message="Release package must exist before DataArts standardization.",
        )

    generated_at = now_iso()
    import_package = read_json(release_dir / "dataarts_import_package.json")
    release_manifest = read_json(release_dir / "release_manifest.json")
    run_manifest = read_json(run_dir / "run_manifest.json")
    parameter_map = read_json(release_dir / "cloud_parameter_map.json")
    standard_schema = build_dataarts_standard_schema()
    standard_package = standardize_dataarts_import_package(
        run_id=run_id,
        generated_at=generated_at,
        import_package=import_package,
        release_manifest=release_manifest,
        run_manifest=run_manifest,
        parameter_map=parameter_map,
    )
    checks = validate_standard_dataarts_package(
        standard_package=standard_package,
        standard_schema=standard_schema,
        require_resolved=False,
    )
    failed_checks = [check for check in checks if check["status"] == "failed"]
    status = "standardized" if not failed_checks else "needs_fix"
    validation = {
        "run_id": run_id,
        "generated_at": generated_at,
        "agent": "dataarts-standardization-agent",
        "status": status,
        "cloud_execution": "blocked",
        "summary": f"{sum(1 for item in checks if item['status'] == 'passed')} checks passed, {len(failed_checks)} failed.",
        "checks": checks,
        "failed_checks": [f"{check['id']}: {check['name']}" for check in failed_checks],
        "schema_version": standard_schema["schema_version"],
        "package_type": standard_package["package_type"],
        "ready_for_cloud_probe": not failed_checks,
        "next_action": "Validate existing cloud resource bindings with the read-only gate. Cloud execution remains blocked.",
    }
    standardization_payload = {
        "run_id": run_id,
        "generated_at": generated_at,
        "agent": "dataarts-standardization-agent",
        "status": status,
        "ready_for_cloud_probe": not failed_checks,
        "cloud_execution": "blocked",
        "message": (
            "DataArts import package standardized. Cloud execution remains blocked."
            if not failed_checks
            else "DataArts package standardization found blocking issues."
        ),
        "schema": {
            "name": standard_schema["name"],
            "schema_version": standard_schema["schema_version"],
        },
        "validation": validation,
        "failed_checks": validation["failed_checks"],
        "files": [],
    }

    write_json(release_dir / "dataarts_import_standard_schema.json", standard_schema)
    write_json(release_dir / "dataarts_import_standard_package.json", standard_package)
    write_json(release_dir / "dataarts_import_validation.json", validation)

    new_files = [
        release_file_entry(run_id, release_dir, "dataarts_import_standard_schema.json", "Local standard schema for DataArts import handoff."),
        release_file_entry(run_id, release_dir, "dataarts_import_standard_package.json", "Standardized DataArts Factory import package; schedules remain disabled."),
        release_file_entry(run_id, release_dir, "dataarts_import_validation.json", "Schema and governance validation for the standardized DataArts package."),
    ]
    standardization_payload["files"] = new_files
    release_status = append_release_files(release_status, new_files)
    release_status["dataarts_standardization"] = {
        "status": standardization_payload["status"],
        "ready_for_cloud_probe": standardization_payload["ready_for_cloud_probe"],
        "cloud_execution": "blocked",
        "summary": validation["summary"],
        "failed_checks": validation["failed_checks"],
    }
    write_json(run_dir / RELEASE_STATUS_NAME, release_status)
    release_manifest = append_release_files(release_manifest, new_files)
    release_manifest["dataarts_standardization"] = release_status["dataarts_standardization"]
    write_json(release_dir / "release_manifest.json", release_manifest)
    write_json(run_dir / DATAARTS_STANDARD_STATUS_NAME, standardization_payload)

    return dataarts_standardization_response(
        run_id=run_id,
        status=standardization_payload["status"],
        ready_for_cloud_probe=standardization_payload["ready_for_cloud_probe"],
        message=standardization_payload["message"],
        standardization=standardization_payload,
        failed_checks=validation["failed_checks"],
    )


def get_cloud_resource_probe_status(run_id: str) -> dict[str, Any]:
    run_dir = resolve_existing_run_dir(run_id)
    probe_status = read_optional_json(run_dir / CLOUD_RESOURCE_PROBE_STATUS_NAME)
    if probe_status:
        return cloud_resource_probe_response(
            run_id=run_id,
            status=probe_status["status"],
            ready_for_operator_execution_request=probe_status["ready_for_operator_execution_request"],
            real_cloud_verified=probe_status["real_cloud_verified"],
            message=probe_status["message"],
            probe=probe_status,
        )

    dataarts_status = read_optional_json(run_dir / DATAARTS_STANDARD_STATUS_NAME)
    if not dataarts_status:
        return cloud_resource_probe_response(
            run_id=run_id,
            status="blocked",
            ready_for_operator_execution_request=False,
            real_cloud_verified=False,
            message="Standardize the DataArts import package before cloud resource probing.",
        )

    return cloud_resource_probe_response(
        run_id=run_id,
        status="ready",
        ready_for_operator_execution_request=False,
        real_cloud_verified=False,
        message="DataArts package is standardized. Validate existing cloud resources with the read-only gate.",
        probe={
            "run_id": run_id,
            "status": "ready",
            "cloud_execution": "blocked",
        },
    )


def create_cloud_resource_probe(
    run_id: str,
    request: CloudResourceProbeRequest,
) -> dict[str, Any]:
    run_dir = resolve_existing_run_dir(run_id)
    release_dir = run_dir / RELEASE_DIR_NAME
    release_status = read_optional_json(run_dir / RELEASE_STATUS_NAME)
    dataarts_status = read_optional_json(run_dir / DATAARTS_STANDARD_STATUS_NAME)
    if not release_status:
        return cloud_resource_probe_response(
            run_id=run_id,
            status="blocked",
            ready_for_operator_execution_request=False,
            real_cloud_verified=False,
            message="Generate a release package before cloud resource probing.",
        )
    if not dataarts_status or not dataarts_status.get("ready_for_cloud_probe"):
        return cloud_resource_probe_response(
            run_id=run_id,
            status="needs_dataarts_standardization",
            ready_for_operator_execution_request=False,
            real_cloud_verified=False,
            message="Generate a successful DataArts standardization before cloud resource probing.",
            failed_checks=(dataarts_status or {}).get("validation", {}).get("failed_checks", []),
        )

    generated_at = now_iso()
    parameter_map = read_json(release_dir / "cloud_parameter_map.json")
    standard_package = read_json(release_dir / "dataarts_import_standard_package.json")
    required_bindings = parameter_map.get("required_bindings") or {}
    bindings, binding_source, source_warnings = collect_probe_bindings(
        run_dir=run_dir,
        required_bindings=required_bindings,
        request=request,
    )
    resolved_standard_package = resolve_placeholders(standard_package, bindings)
    resolved_checks = validate_standard_dataarts_package(
        standard_package=resolved_standard_package,
        standard_schema=build_dataarts_standard_schema(),
        require_resolved=True,
    )
    adapter_result = run_readonly_probe_adapter(
        allow_network_probe=request.allow_network_probe,
        bindings=bindings,
    )
    checks = validate_cloud_resource_probe(
        bindings=bindings,
        required_bindings=required_bindings,
        standard_package=standard_package,
        resolved_standard_package=resolved_standard_package,
        resolved_checks=resolved_checks,
        adapter_result=adapter_result,
        binding_source=binding_source,
        source_warnings=source_warnings,
    )
    failed_checks = [check for check in checks if check["status"] == "failed"]
    warnings = [check for check in checks if check["status"] == "warning"]
    real_cloud_verified = adapter_result["status"] == "passed"
    ready_for_operator_execution_request = not failed_checks
    status = (
        "real_cloud_verified"
        if real_cloud_verified and ready_for_operator_execution_request
        else "operator_review_ready"
        if ready_for_operator_execution_request
        else "needs_cloud_env"
    )
    message = (
        "Existing cloud resources were verified through read-only checks. Cloud execution still requires separate approval."
        if real_cloud_verified
        else "Cloud resource binding package is ready for operator review. Existing cloud resources are not yet read-only verified."
        if ready_for_operator_execution_request
        else "Cloud resource validation found missing or invalid bindings."
    )
    safe_bindings = sanitize_probe_bindings(bindings)
    probe_payload = {
        "run_id": run_id,
        "generated_at": generated_at,
        "agent": "cloud-resource-readonly-probe-agent",
        "status": status,
        "ready_for_operator_execution_request": ready_for_operator_execution_request,
        "real_cloud_verified": real_cloud_verified,
        "cloud_execution": "blocked",
        "message": message,
        "source": binding_source,
        "reviewer": request.reviewer.strip() or "local_operator",
        "note": request.note.strip(),
        "bindings": safe_bindings,
        "adapter": adapter_result,
        "checks": checks,
        "warnings": [f"{check['id']}: {check['name']}" for check in warnings],
        "missing_bindings": missing_cloud_bindings(bindings, required_bindings),
        "failed_checks": [f"{check['id']}: {check['name']}" for check in failed_checks],
        "files": [],
    }
    execution_readiness = {
        "run_id": run_id,
        "generated_at": generated_at,
        "status": "operator_review_ready" if ready_for_operator_execution_request else "needs_fix",
        "cloud_execution": "blocked",
        "real_cloud_verified": real_cloud_verified,
        "summary": f"{sum(1 for item in checks if item['status'] == 'passed')} checks passed, {len(warnings)} warnings, {len(failed_checks)} failed.",
        "next_action": "Operator may request real cloud execution approval only after read-only resource verification, console review, and separate approval.",
    }
    binding_template = build_real_cloud_resource_binding_template(
        run_id=run_id,
        generated_at=generated_at,
        required_bindings=required_bindings,
        current_bindings=safe_bindings,
        binding_source=binding_source,
    )
    readonly_checklist = render_cloud_readonly_verification_checklist(
        run_id=run_id,
        generated_at=generated_at,
        binding_template=binding_template,
        probe_payload=probe_payload,
        execution_readiness=execution_readiness,
    )
    approval_request = render_cloud_execution_approval_request(
        run_id=run_id,
        generated_at=generated_at,
        probe_payload=probe_payload,
        execution_readiness=execution_readiness,
    )

    write_json(release_dir / "resolved_dataarts_standard_package.json", resolved_standard_package)
    write_json(release_dir / "real_cloud_resource_binding_template.json", binding_template)
    write_json(release_dir / "cloud_resource_probe.json", probe_payload)
    write_json(release_dir / "cloud_execution_readiness.json", execution_readiness)
    (release_dir / "cloud_readonly_verification_checklist.md").write_text(readonly_checklist, encoding="utf-8")
    (release_dir / "cloud_execution_approval_request.md").write_text(approval_request, encoding="utf-8")

    new_files = [
        release_file_entry(run_id, release_dir, "resolved_dataarts_standard_package.json", "Resolved standardized DataArts package from selected resource bindings."),
        release_file_entry(run_id, release_dir, "real_cloud_resource_binding_template.json", "Non-secret resource binding template for a future real Huawei Cloud environment."),
        release_file_entry(run_id, release_dir, "cloud_resource_probe.json", "Read-only existing cloud resource validation report; no write calls are made."),
        release_file_entry(run_id, release_dir, "cloud_execution_readiness.json", "Final readiness marker before separate cloud execution approval."),
        release_file_entry(run_id, release_dir, "cloud_readonly_verification_checklist.md", "Operator checklist for validating existing Huawei Cloud resources without creating or modifying them."),
        release_file_entry(run_id, release_dir, "cloud_execution_approval_request.md", "Human approval request for a future real cloud execution window."),
    ]
    probe_payload["files"] = new_files
    write_json(release_dir / "cloud_resource_probe.json", probe_payload)
    release_status = append_release_files(release_status, new_files)
    release_status["cloud_resource_probe"] = {
        "status": probe_payload["status"],
        "ready_for_operator_execution_request": probe_payload["ready_for_operator_execution_request"],
        "real_cloud_verified": probe_payload["real_cloud_verified"],
        "cloud_execution": "blocked",
        "summary": execution_readiness["summary"],
        "failed_checks": probe_payload["failed_checks"],
    }
    write_json(run_dir / RELEASE_STATUS_NAME, release_status)
    release_manifest_path = release_dir / "release_manifest.json"
    if release_manifest_path.exists():
        release_manifest = append_release_files(read_json(release_manifest_path), new_files)
        release_manifest["cloud_resource_probe"] = release_status["cloud_resource_probe"]
        write_json(release_manifest_path, release_manifest)
    write_json(run_dir / CLOUD_RESOURCE_PROBE_STATUS_NAME, probe_payload)

    return cloud_resource_probe_response(
        run_id=run_id,
        status=probe_payload["status"],
        ready_for_operator_execution_request=probe_payload["ready_for_operator_execution_request"],
        real_cloud_verified=probe_payload["real_cloud_verified"],
        message=probe_payload["message"],
        probe=probe_payload,
        missing_bindings=missing_cloud_bindings(bindings, required_bindings),
        failed_checks=probe_payload["failed_checks"],
    )


def resolve_run_dir(run_id: str) -> Path:
    if not run_id.startswith("front-"):
        raise ValueError("Invalid run id")
    run_dir = (GENERATED_ROOT / run_id).resolve()
    generated_root = GENERATED_ROOT.resolve()
    if generated_root not in run_dir.parents and run_dir != generated_root:
        raise ValueError("Invalid run path")
    return run_dir


def resolve_existing_run_dir(run_id: str) -> Path:
    run_dir = resolve_run_dir(run_id)
    if not run_dir.exists():
        raise FileNotFoundError(f"Run {run_id} not found")
    return run_dir


def release_readiness(run_dir: Path) -> dict[str, Any]:
    review_path = run_dir / "review_status.json"
    gates_path = run_dir / "quality_gates.json"
    manifest_path = run_dir / "run_manifest.json"
    missing_files = [
        path.name
        for path in (review_path, gates_path, manifest_path)
        if not path.exists()
    ]
    if missing_files:
        return {
            "ready": False,
            "missing_approvals": [],
            "failed_gates": [],
            "approved_artifacts": [],
            "missing_files": missing_files,
        }

    review = read_json(review_path)
    quality_gates = read_json(gates_path)
    artifacts = review.get("artifacts", {})
    reviewable = {
        name: item
        for name, item in artifacts.items()
        if item.get("review_required", False)
    }
    stale_approvals = {
        name
        for name, item in reviewable.items()
        if item.get("status") == "approved"
        and item.get("artifact_hash")
        != file_sha256(APP_ROOT / item.get("path", ""))
    }
    missing_approvals = sorted(
        name
        for name, item in reviewable.items()
        if item.get("status") != "approved" or name in stale_approvals
    )
    approved_artifacts = sorted(
        name
        for name, item in reviewable.items()
        if item.get("status") == "approved" and name not in stale_approvals
    )
    failed_gates = [
        f"{gate.get('id', 'gate')}: {gate.get('name', 'unknown')}"
        for gate in quality_gates
        if gate.get("status") == "failed"
    ]
    return {
        "ready": not missing_approvals and not failed_gates,
        "missing_approvals": missing_approvals,
        "failed_gates": failed_gates,
        "approved_artifacts": approved_artifacts,
        "missing_files": [],
    }


def release_response(
    *,
    run_id: str,
    status: str,
    ready: bool,
    message: str,
    readiness: dict[str, Any],
    release: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "status": status,
        "ready": ready,
        "message": message,
        "release_hash": str((release or {}).get("release_hash", "")),
        "release": release or {},
        "missing_approvals": readiness.get("missing_approvals", []) + readiness.get("missing_files", []),
        "failed_gates": readiness.get("failed_gates", []),
    }


def cloud_binding_response(
    *,
    run_id: str,
    status: str,
    ready_for_import_review: bool,
    message: str,
    binding: dict[str, Any] | None = None,
    missing_bindings: list[str] | None = None,
    failed_checks: list[str] | None = None,
) -> dict[str, Any]:
    binding_payload = binding or {}
    return {
        "run_id": run_id,
        "status": status,
        "ready_for_import_review": ready_for_import_review,
        "cloud_execution": "blocked",
        "message": message,
        "binding": binding_payload,
        "missing_bindings": missing_bindings if missing_bindings is not None else binding_payload.get("missing_bindings", []),
        "failed_checks": failed_checks if failed_checks is not None else binding_payload.get("failed_checks", []),
    }


def import_review_response(
    *,
    run_id: str,
    status: str,
    ready_for_operator_handoff: bool,
    message: str,
    review: dict[str, Any] | None = None,
    failed_checks: list[str] | None = None,
) -> dict[str, Any]:
    review_payload = review or {}
    return {
        "run_id": run_id,
        "status": status,
        "ready_for_operator_handoff": ready_for_operator_handoff,
        "cloud_execution": "blocked",
        "message": message,
        "review": review_payload,
        "failed_checks": failed_checks if failed_checks is not None else review_payload.get("failed_checks", []),
    }


def dataarts_standardization_response(
    *,
    run_id: str,
    status: str,
    ready_for_cloud_probe: bool,
    message: str,
    standardization: dict[str, Any] | None = None,
    failed_checks: list[str] | None = None,
) -> dict[str, Any]:
    standardization_payload = standardization or {}
    return {
        "run_id": run_id,
        "status": status,
        "ready_for_cloud_probe": ready_for_cloud_probe,
        "cloud_execution": "blocked",
        "message": message,
        "standardization": standardization_payload,
        "failed_checks": failed_checks if failed_checks is not None else standardization_payload.get("failed_checks", []),
    }


def cloud_resource_probe_response(
    *,
    run_id: str,
    status: str,
    ready_for_operator_execution_request: bool,
    real_cloud_verified: bool,
    message: str,
    probe: dict[str, Any] | None = None,
    missing_bindings: list[str] | None = None,
    failed_checks: list[str] | None = None,
) -> dict[str, Any]:
    probe_payload = probe or {}
    return {
        "run_id": run_id,
        "status": status,
        "ready_for_operator_execution_request": ready_for_operator_execution_request,
        "real_cloud_verified": real_cloud_verified,
        "cloud_execution": "blocked",
        "message": message,
        "probe": probe_payload,
        "missing_bindings": missing_bindings if missing_bindings is not None else probe_payload.get("missing_bindings", []),
        "failed_checks": failed_checks if failed_checks is not None else probe_payload.get("failed_checks", []),
    }


def build_approval_summary(
    *,
    run_id: str,
    generated_at: str,
    review: dict[str, Any],
    quality_gates: list[dict[str, Any]],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    review_items = review.get("artifacts", {})
    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "review_updated_at": review.get("updated_at"),
        "status": "approved_for_local_release",
        "approved_artifacts": readiness["approved_artifacts"],
        "artifact_reviews": [
            {
                "name": name,
                "kind": item.get("kind"),
                "status": item.get("status"),
                "reviewer": item.get("reviewer"),
                "note": item.get("note", ""),
                "updated_at": item.get("updated_at"),
                "url": item.get("url"),
            }
            for name, item in sorted(review_items.items())
            if item.get("review_required", False)
        ],
        "quality_gates": quality_gates,
        "cloud_execution": "blocked",
    }


def build_dataarts_import_package(
    *,
    run_id: str,
    generated_at: str,
    request: dict[str, Any],
    run_manifest: dict[str, Any],
    review: dict[str, Any],
) -> dict[str, Any]:
    scenario = request.get("scenario") or run_manifest.get("request", {}).get("scenario") or "tax_agentic_task"
    artifact_paths = {
        artifact.get("name"): artifact.get("path")
        for artifact in run_manifest.get("artifacts", [])
    }
    return {
        "schema_version": "0.1-local-preview",
        "package_type": "dataarts_import_preview",
        "run_id": run_id,
        "generated_at": generated_at,
        "scenario": scenario,
        "cloud_execution": {
            "state": "blocked",
            "reason": "This package is a local release candidate. It must not submit jobs until cloud approval.",
        },
        "parameters": {
            "obs_raw_uri": "${OBS_RAW_URI}",
            "obs_silver_uri": "${OBS_SILVER_URI}",
            "obs_gold_uri": "${OBS_GOLD_URI}",
            "obs_release_uri": "${OBS_RELEASE_URI}",
            "obs_audit_uri": "${OBS_AUDIT_URI}",
            "mrs_cluster_id": "${MRS_CLUSTER_ID}",
            "dws_connection_name": "${DWS_CONNECTION_NAME}",
            "dataarts_workspace_id": "${DATAARTS_WORKSPACE_ID}",
        },
        "jobs": [
            {
                "name": f"{scenario}_{run_id}",
                "type": "dataarts_factory_job",
                "execution": "blocked_until_cloud_approval",
                "tasks": [
                    {
                        "id": "validate_contract_audit",
                        "type": "quality_gate",
                        "input": artifact_paths.get("contract_audit.json", "artifacts/contract_audit.json"),
                    },
                    {
                        "id": "submit_mrs_spark_transform",
                        "type": "mrs_spark",
                        "script": artifact_paths.get("mrs_transform.py", "artifacts/mrs_transform.py"),
                        "depends_on": ["validate_contract_audit"],
                    },
                    {
                        "id": "load_dws_serving_view",
                        "type": "dws_sql",
                        "script": artifact_paths.get("dws_serving.sql", "artifacts/dws_serving.sql"),
                        "depends_on": ["submit_mrs_spark_transform"],
                    },
                    {
                        "id": "publish_lineage_manifest",
                        "type": "metadata",
                        "input": "lineage_manifest.json",
                        "depends_on": ["load_dws_serving_view"],
                    },
                ],
            }
        ],
        "review_status": {
            "updated_at": review.get("updated_at"),
            "reviewable_artifacts": [
                name
                for name, item in sorted(review.get("artifacts", {}).items())
                if item.get("review_required", False)
            ],
        },
    }


def build_dataarts_standard_schema() -> dict[str, Any]:
    return {
        "name": "agentic_tax_dataarts_factory_import",
        "schema_version": "dataarts.factory.import.v1alpha1",
        "required_top_level_fields": [
            "schema_version",
            "package_type",
            "run_id",
            "cloud_execution",
            "workspace",
            "parameters",
            "connections",
            "jobs",
            "security",
            "audit",
        ],
        "required_parameter_keys": [
            "obs_raw_uri",
            "obs_silver_uri",
            "obs_gold_uri",
            "obs_release_uri",
            "obs_audit_uri",
            "mrs_cluster_id",
            "dws_connection_name",
            "dataarts_workspace_id",
        ],
        "required_node_types": [
            "quality_gate",
            "mrs_spark",
            "dws_sql",
            "metadata",
        ],
        "execution_controls": {
            "dataarts_schedule_enabled": False,
            "cloud_execution_state": "blocked",
            "node_execution": "blocked_until_cloud_approval",
        },
    }


def standardize_dataarts_import_package(
    *,
    run_id: str,
    generated_at: str,
    import_package: dict[str, Any],
    release_manifest: dict[str, Any],
    run_manifest: dict[str, Any],
    parameter_map: dict[str, Any],
) -> dict[str, Any]:
    scenario = import_package.get("scenario") or run_manifest.get("request", {}).get("scenario") or "tax_agentic_task"
    parameters = import_package.get("parameters", {})
    required_bindings = parameter_map.get("required_bindings") or {}
    jobs = [
        standardize_dataarts_job(
            job=job,
            scenario=scenario,
            run_id=run_id,
            release_manifest=release_manifest,
        )
        for job in import_package.get("jobs", [])
    ]
    return {
        "schema_version": "dataarts.factory.import.v1alpha1",
        "package_type": "dataarts_factory_import_standard",
        "run_id": run_id,
        "generated_at": generated_at,
        "scenario": scenario,
        "cloud_execution": {
            "state": "blocked",
            "reason": "Standard package is review-only. DataArts schedules and MRS/DWS submits require separate cloud approval.",
        },
        "workspace": {
            "workspace_id": required_bindings.get("DATAARTS_WORKSPACE_ID", parameters.get("dataarts_workspace_id", "${DATAARTS_WORKSPACE_ID}")),
            "import_mode": "draft_review_only",
            "schedule_policy": "disabled_until_cloud_approval",
        },
        "parameters": parameters,
        "connections": [
            {
                "id": "obs_lake_layers",
                "type": "OBS",
                "uris": {
                    "raw": parameters.get("obs_raw_uri", "${OBS_RAW_URI}"),
                    "silver": parameters.get("obs_silver_uri", "${OBS_SILVER_URI}"),
                    "gold": parameters.get("obs_gold_uri", "${OBS_GOLD_URI}"),
                    "release": parameters.get("obs_release_uri", "${OBS_RELEASE_URI}"),
                    "audit": parameters.get("obs_audit_uri", "${OBS_AUDIT_URI}"),
                },
                "permission": "read_write_scoped_to_run_paths",
            },
            {
                "id": "mrs_spark_cluster",
                "type": "MRS Spark",
                "cluster_id": parameters.get("mrs_cluster_id", "${MRS_CLUSTER_ID}"),
                "submit_policy": "blocked_until_cloud_approval",
            },
            {
                "id": "dws_serving_connection",
                "type": "GaussDB(DWS)",
                "connection_name": parameters.get("dws_connection_name", "${DWS_CONNECTION_NAME}"),
                "apply_policy": "blocked_until_cloud_approval",
            },
        ],
        "jobs": jobs,
        "security": {
            "secret_policy": "No AK/SK, passwords, private keys, or database credentials are allowed in this package.",
            "iam_policy": "least_privilege_required_before_import",
            "privacy_controls": [
                "direct_rfc_not_exposed_to_gold_or_dws",
                "masked_or_hash_identifiers_only_in_artifacts",
                "operator_approval_required_for_cloud_execution",
            ],
        },
        "audit": {
            "release_manifest_url": release_manifest.get("release_url") or f"/generated/{run_id}/release/release_manifest.json",
            "required_evidence": [
                "approval_summary.json",
                "deployment_preflight.json",
                "cloud_binding_simulation.json",
                "cloud_import_review.json",
                "cloud_resource_probe.json",
            ],
        },
    }


def standardize_dataarts_job(
    *,
    job: dict[str, Any],
    scenario: str,
    run_id: str,
    release_manifest: dict[str, Any],
) -> dict[str, Any]:
    tasks = job.get("tasks", [])
    nodes = [standardize_dataarts_node(task) for task in tasks]
    dependencies = [
        {"from": dependency, "to": task.get("id", "")}
        for task in tasks
        for dependency in task.get("depends_on", [])
    ]
    return {
        "job_name": job.get("name") or f"{scenario}_{run_id}",
        "job_type": "batch_pipeline",
        "source_package_type": job.get("type", "dataarts_factory_job"),
        "execution": "blocked_until_cloud_approval",
        "schedule": {
            "enabled": False,
            "reason": "Schedules remain disabled until separate cloud execution approval.",
        },
        "nodes": nodes,
        "dependencies": dependencies,
        "failure_policy": {
            "on_node_failure": "stop_pipeline",
            "preserve_failed_outputs": True,
            "write_audit_event": True,
        },
        "release_files": [
            item.get("name")
            for item in release_manifest.get("files", [])
            if item.get("name")
        ],
    }


def standardize_dataarts_node(task: dict[str, Any]) -> dict[str, Any]:
    task_type = task.get("type", "unknown")
    node = {
        "node_id": task.get("id", ""),
        "node_type": task_type,
        "execution": "blocked_until_cloud_approval",
        "depends_on": task.get("depends_on", []),
        "retry_policy": {
            "max_retries": 0,
            "retry_after_seconds": 0,
        },
        "timeout_minutes": 60,
    }
    if "script" in task:
        node["script_ref"] = task["script"]
    if "input" in task:
        node["input_ref"] = task["input"]
    if task_type == "mrs_spark":
        node["target_connection"] = "mrs_spark_cluster"
        node["runtime"] = "spark"
    elif task_type == "dws_sql":
        node["target_connection"] = "dws_serving_connection"
        node["runtime"] = "sql"
    elif task_type == "quality_gate":
        node["target_connection"] = "local_release_audit"
        node["runtime"] = "validation"
    elif task_type == "metadata":
        node["target_connection"] = "obs_lake_layers"
        node["runtime"] = "metadata_publish"
    return node


def build_environment_profile(
    *,
    run_id: str,
    generated_at: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    scenario = request.get("scenario") or "tax_agentic_task"
    prefix = f"agentic-tax-{scenario}"
    return {
        "profile_id": f"{run_id}-environment",
        "generated_at": generated_at,
        "purpose": "Local environment contract for a future Huawei Cloud deployment approval.",
        "region": {
            "id": "la-south-2",
            "name": "LA-Santiago",
            "service_availability": "verify_in_cloud_console_before_deploy",
        },
        "network": {
            "vpc_id": "${VPC_ID}",
            "private_subnet_id": "${PRIVATE_SUBNET_ID}",
            "public_ingress": "disabled_for_bigdata_services",
            "security_group_policy": "allow only DataArts, MRS, DWS, and operator access paths approved by IAM.",
        },
        "storage": {
            "service": "OBS",
            "encryption": "DEW_KMS",
            "kms_key_id": "${KMS_KEY_ID}",
            "obs_layers": {
                "raw": f"obs://${{{prefix.upper().replace('-', '_')}_BUCKET}}/raw/tax/",
                "silver": f"obs://${{{prefix.upper().replace('-', '_')}_BUCKET}}/silver/tax/",
                "gold": f"obs://${{{prefix.upper().replace('-', '_')}_BUCKET}}/gold/tax/",
                "release": f"obs://${{{prefix.upper().replace('-', '_')}_BUCKET}}/release/{run_id}/",
                "audit": f"obs://${{{prefix.upper().replace('-', '_')}_BUCKET}}/audit/{run_id}/",
            },
            "retention": {
                "raw": "archive_after_validation",
                "audit": "retain_for_governance_review",
            },
        },
        "processing": {
            "service": "MRS Spark",
            "cluster_id": "${MRS_CLUSTER_ID}",
            "job_mode": "manual_submit_after_cloud_approval",
            "script": "artifacts/mrs_transform.py",
        },
        "warehouse": {
            "service": "GaussDB(DWS)",
            "connection_name": "${DWS_CONNECTION_NAME}",
            "schema": "tax_gold",
            "script": "artifacts/dws_serving.sql",
        },
        "orchestration": {
            "service": "DataArts Factory",
            "workspace_id": "${DATAARTS_WORKSPACE_ID}",
            "dag": "artifacts/dataarts_dag.yaml",
            "execution": "blocked_until_cloud_approval",
        },
        "security": {
            "secrets": "environment_variables_or_DEW_only",
            "iam_policy": "least_privilege",
            "required_roles": [
                "tax-dataarts-import-operator",
                "tax-mrs-job-submitter",
                "tax-dws-ddl-operator",
                "tax-obs-release-writer",
            ],
            "privacy_controls": [
                "direct_rfc_never_leaves_raw_processing_scope",
                "gold_and_dws_outputs_use_aggregate_dimensions_only",
                "UI_artifacts_use_masked_or_hashed_identifiers_only",
            ],
        },
        "approvals": {
            "artifact_review": ["mrs_transform.py", "dws_serving.sql", "dataarts_dag.yaml"],
            "cloud_deployment": "required",
            "production_execution": "blocked_until_explicit_cloud_approval",
            "allowed_execution_window": "22:00-05:00 local time after approval",
        },
        "observability": {
            "required_events": [
                "obs_bytes",
                "mrs_cleaned_rows",
                "dws_loaded_rows",
                "stage_duration_seconds",
                "error_count",
            ],
        },
    }


def build_cloud_parameter_map(environment_profile: dict[str, Any]) -> dict[str, Any]:
    obs_layers = environment_profile["storage"]["obs_layers"]
    bindings = {
        "HUAWEICLOUD_REGION": environment_profile["region"]["id"],
        "HUAWEICLOUD_PROJECT_ID": "${HUAWEICLOUD_PROJECT_ID}",
        "VPC_ID": environment_profile["network"]["vpc_id"],
        "PRIVATE_SUBNET_ID": environment_profile["network"]["private_subnet_id"],
        "KMS_KEY_ID": environment_profile["storage"]["kms_key_id"],
        "OBS_RAW_URI": obs_layers["raw"],
        "OBS_SILVER_URI": obs_layers["silver"],
        "OBS_GOLD_URI": obs_layers["gold"],
        "OBS_RELEASE_URI": obs_layers["release"],
        "OBS_AUDIT_URI": obs_layers["audit"],
        "MRS_CLUSTER_ID": environment_profile["processing"]["cluster_id"],
        "DWS_CONNECTION_NAME": environment_profile["warehouse"]["connection_name"],
        "DATAARTS_WORKSPACE_ID": environment_profile["orchestration"]["workspace_id"],
    }
    return {
        "status": "placeholder_only",
        "secret_policy": "Do not write AK/SK, database passwords, or private keys to this package.",
        "required_bindings": bindings,
        "approval_required_before_binding": True,
    }


def build_deployment_preflight(
    *,
    run_id: str,
    generated_at: str,
    readiness: dict[str, Any],
    environment_profile: dict[str, Any],
    cloud_parameter_map: dict[str, Any],
    import_package: dict[str, Any],
    run_manifest: dict[str, Any],
    release_dir: Path,
) -> dict[str, Any]:
    artifacts = {artifact.get("name"): artifact for artifact in run_manifest.get("artifacts", [])}
    obs_layers = environment_profile["storage"]["obs_layers"]
    checks = [
        preflight_check(
            "DP-001",
            "Release package exists locally",
            release_dir.exists(),
            f"release_dir={release_dir}",
        ),
        preflight_check(
            "DP-002",
            "Executable artifacts are approved",
            readiness["ready"],
            f"approved={readiness.get('approved_artifacts', [])}; missing={readiness.get('missing_approvals', [])}",
        ),
        preflight_check(
            "DP-003",
            "OBS layers follow raw, silver, gold, release, audit",
            {"raw", "silver", "gold", "release", "audit"}.issubset(obs_layers),
            f"layers={sorted(obs_layers)}",
        ),
        preflight_check(
            "DP-004",
            "Direct RFC is blocked from gold and DWS outputs",
            no_direct_rfc_in_serving_artifacts(artifacts),
            "PySpark drops direct rfc before aggregate output; DWS SQL exposes aggregate dimensions and metrics only.",
        ),
        preflight_check(
            "DP-005",
            "DataArts execution remains blocked",
            import_package.get("cloud_execution", {}).get("state") == "blocked"
            and all(job.get("execution") == "blocked_until_cloud_approval" for job in import_package.get("jobs", [])),
            "DataArts package is import-preview only.",
        ),
        preflight_check(
            "DP-006",
            "IAM and KMS policies are declared",
            bool(environment_profile["security"]["required_roles"]) and bool(environment_profile["storage"]["kms_key_id"]),
            "Least-privilege roles and DEW KMS key placeholder are present.",
        ),
        preflight_check(
            "DP-007",
            "Secrets are not embedded",
            not contains_secret_like_value(cloud_parameter_map),
            cloud_parameter_map["secret_policy"],
        ),
        preflight_check(
            "DP-008",
            "Production execution has an approval window",
            "blocked" in environment_profile["approvals"]["production_execution"]
            and bool(environment_profile["approvals"]["allowed_execution_window"]),
            environment_profile["approvals"]["allowed_execution_window"],
        ),
        preflight_check(
            "DP-009",
            "Cloud resources are still placeholders",
            True,
            "MRS_CLUSTER_ID, DWS_CONNECTION_NAME, DATAARTS_WORKSPACE_ID, OBS paths, VPC, subnet, and KMS key must be bound during cloud approval.",
            status="warning",
        ),
    ]
    failed = [check for check in checks if check["status"] == "failed"]
    warnings = [check for check in checks if check["status"] == "warning"]
    passed = [check for check in checks if check["status"] == "passed"]
    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "agent": "deployment-preflight-agent",
        "status": "needs_cloud_binding" if not failed else "needs_fix",
        "cloud_execution": "blocked",
        "summary": f"{len(passed)} checks passed, {len(warnings)} warnings, {len(failed)} failed.",
        "passed": len(passed),
        "warnings": len(warnings),
        "failed": len(failed),
        "checks": checks,
        "next_action": "Bind cloud parameters and verify quotas only after explicit cloud deployment approval.",
    }


def preflight_check(
    check_id: str,
    name: str,
    passed: bool,
    detail: str,
    *,
    status: str | None = None,
) -> dict[str, str]:
    return {
        "id": check_id,
        "name": name,
        "status": status or ("passed" if passed else "failed"),
        "detail": detail,
    }


def no_direct_rfc_in_serving_artifacts(artifacts: dict[str, Any]) -> bool:
    sql_path = APP_ROOT / str(artifacts.get("dws_serving.sql", {}).get("path", ""))
    pyspark_path = APP_ROOT / str(artifacts.get("mrs_transform.py", {}).get("path", ""))
    sql = sql_path.read_text(encoding="utf-8").lower() if sql_path.exists() else ""
    pyspark = pyspark_path.read_text(encoding="utf-8").lower() if pyspark_path.exists() else ""
    return " rfc" not in sql and ".drop(\"rfc\")" in pyspark


def contains_secret_like_value(payload: Any) -> bool:
    forbidden_names = ("ACCESS_KEY", "SECRET_KEY", "PASSWORD", "PRIVATE_KEY", "AK/SK")
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_upper = str(key).upper()
            if any(word in key_upper for word in forbidden_names) and str(value).strip() and "${" not in str(value):
                return True
            if contains_secret_like_value(value):
                return True
        return False
    if isinstance(payload, list):
        return any(contains_secret_like_value(item) for item in payload)
    if isinstance(payload, str):
        text = payload.strip()
        return "-----BEGIN " in text and "PRIVATE KEY-----" in text
    return False


def sample_cloud_bindings(run_id: str, required_bindings: dict[str, str]) -> dict[str, str]:
    bucket = f"agentic-tax-local-simulated-{run_id}"
    samples = {
        "HUAWEICLOUD_REGION": "la-south-2",
        "HUAWEICLOUD_PROJECT_ID": "project-placeholder-approve-in-console",
        "VPC_ID": "vpc-approved-placeholder",
        "PRIVATE_SUBNET_ID": "subnet-approved-placeholder",
        "KMS_KEY_ID": "kms-approved-placeholder",
        "MRS_CLUSTER_ID": "mrs-approved-placeholder",
        "DWS_CONNECTION_NAME": "dws-tax-approved-placeholder",
        "DATAARTS_WORKSPACE_ID": "dataarts-approved-placeholder",
        "OBS_RAW_URI": f"obs://{bucket}/raw/tax/",
        "OBS_SILVER_URI": f"obs://{bucket}/silver/tax/",
        "OBS_GOLD_URI": f"obs://{bucket}/gold/tax/",
        "OBS_RELEASE_URI": f"obs://{bucket}/release/{run_id}/",
        "OBS_AUDIT_URI": f"obs://{bucket}/audit/{run_id}/",
    }
    return {key: samples.get(key, str(value)) for key, value in required_bindings.items()}


def validate_cloud_bindings(
    *,
    bindings: dict[str, str],
    required_bindings: dict[str, str],
    import_package: dict[str, Any],
) -> list[dict[str, str]]:
    missing = missing_cloud_bindings(bindings, required_bindings)
    checks = [
        binding_check(
            "CB-001",
            "All required cloud bindings are present",
            not missing,
            f"missing={missing}" if missing else f"bound={sorted(required_bindings)}",
        ),
        binding_check(
            "CB-002",
            "Bindings do not contain unresolved placeholders",
            not unresolved_binding_values(bindings),
            f"unresolved={unresolved_binding_values(bindings)}",
        ),
        binding_check(
            "CB-003",
            "Region matches environment contract",
            bindings.get("HUAWEICLOUD_REGION") == "la-south-2",
            f"region={bindings.get('HUAWEICLOUD_REGION', '')}; expected=la-south-2",
        ),
        binding_check(
            "CB-004",
            "OBS bindings preserve raw, silver, gold, release, audit layers",
            obs_bindings_are_layered(bindings),
            "OBS_*_URI values point to their matching lake layers.",
        ),
        binding_check(
            "CB-005",
            "No credential-like keys are bound",
            not has_forbidden_secret_binding(bindings),
            "AK/SK, passwords, private keys, and database passwords are not part of this binding package.",
        ),
        binding_check(
            "CB-006",
            "DataArts import preview remains blocked",
            import_package.get("cloud_execution", {}).get("state") == "blocked"
            and all(job.get("execution") == "blocked_until_cloud_approval" for job in import_package.get("jobs", [])),
            "Resolved import package must still require explicit cloud approval.",
        ),
    ]
    return checks


def binding_check(check_id: str, name: str, passed: bool, detail: str) -> dict[str, str]:
    return {
        "id": check_id,
        "name": name,
        "status": "passed" if passed else "failed",
        "detail": detail,
    }


def missing_cloud_bindings(bindings: dict[str, str], required_bindings: dict[str, str]) -> list[str]:
    return sorted(
        key
        for key in required_bindings
        if not str(bindings.get(key, "")).strip()
    )


def unresolved_binding_values(bindings: dict[str, str]) -> list[str]:
    return sorted(
        key
        for key, value in bindings.items()
        if "${" in str(value) or "<" in str(value) or ">" in str(value)
    )


def obs_bindings_are_layered(bindings: dict[str, str]) -> bool:
    required_layers = {
        "OBS_RAW_URI": "/raw/",
        "OBS_SILVER_URI": "/silver/",
        "OBS_GOLD_URI": "/gold/",
        "OBS_RELEASE_URI": "/release/",
        "OBS_AUDIT_URI": "/audit/",
    }
    return all(
        str(bindings.get(key, "")).startswith("obs://") and layer in str(bindings.get(key, ""))
        for key, layer in required_layers.items()
    )


def has_forbidden_secret_binding(bindings: dict[str, str]) -> bool:
    forbidden_names = ("ACCESS_KEY", "SECRET_KEY", "PASSWORD", "PRIVATE_KEY", "DWS_ADMIN_PASSWORD")
    return any(any(word in key.upper() for word in forbidden_names) for key in bindings)


def resolve_dataarts_import_package(import_package: dict[str, Any], bindings: dict[str, str]) -> dict[str, Any]:
    resolved = json.loads(json.dumps(import_package, ensure_ascii=False))
    parameters = resolved.get("parameters", {})
    for name, value in list(parameters.items()):
        binding_key = name.upper()
        if binding_key in bindings:
            parameters[name] = bindings[binding_key]
    resolved["parameters"] = parameters
    resolved["cloud_execution"] = {
        "state": "blocked",
        "reason": "Bindings are locally simulated or operator-provided for review. Import and execution still require cloud approval.",
    }
    resolved["binding_mode"] = "local_validation_only"
    for job in resolved.get("jobs", []):
        job["execution"] = "blocked_until_cloud_approval"
    return resolved


def validate_standard_dataarts_package(
    *,
    standard_package: dict[str, Any],
    standard_schema: dict[str, Any],
    require_resolved: bool,
) -> list[dict[str, str]]:
    required_fields = standard_schema["required_top_level_fields"]
    required_parameters = standard_schema["required_parameter_keys"]
    jobs = standard_package.get("jobs", [])
    all_nodes = [
        node
        for job in jobs
        for node in job.get("nodes", [])
    ]
    node_ids = [node.get("node_id") for node in all_nodes]
    dependencies = [
        dependency
        for job in jobs
        for node in job.get("nodes", [])
        for dependency in node.get("depends_on", [])
    ]
    required_node_types = set(standard_schema["required_node_types"])
    actual_node_types = {node.get("node_type") for node in all_nodes}
    parameters = standard_package.get("parameters", {})
    checks = [
        import_review_check(
            "DS-001",
            "Standard schema version is declared",
            standard_package.get("schema_version") == standard_schema["schema_version"],
            f"schema_version={standard_package.get('schema_version')}",
        ),
        import_review_check(
            "DS-002",
            "Required top-level fields exist",
            not [field for field in required_fields if field not in standard_package],
            f"missing={[field for field in required_fields if field not in standard_package]}",
        ),
        import_review_check(
            "DS-003",
            "DataArts schedules remain disabled",
            all(job.get("schedule", {}).get("enabled") is False for job in jobs),
            "All jobs must keep schedule.enabled=false until cloud approval.",
        ),
        import_review_check(
            "DS-004",
            "Cloud execution remains blocked",
            standard_package.get("cloud_execution", {}).get("state") == "blocked"
            and dataarts_standard_jobs_blocked(standard_package),
            "Package and all jobs/nodes must be blocked_until_cloud_approval.",
        ),
        import_review_check(
            "DS-005",
            "Required parameters are present",
            not [key for key in required_parameters if key not in parameters],
            f"missing={[key for key in required_parameters if key not in parameters]}",
        ),
        import_review_check(
            "DS-006",
            "Required node types are present",
            required_node_types.issubset(actual_node_types),
            f"node_types={sorted(actual_node_types)}",
        ),
        import_review_check(
            "DS-007",
            "Node ids are unique and dependencies resolve",
            len(node_ids) == len(set(node_ids)) and set(dependencies).issubset(set(node_ids)),
            f"node_ids={node_ids}; dependencies={dependencies}",
        ),
        import_review_check(
            "DS-008",
            "No credential-like fields are embedded",
            not contains_secret_like_value(standard_package),
            "Package must not include AK/SK, passwords, private keys, or database credentials.",
        ),
    ]
    if require_resolved:
        checks.append(
            import_review_check(
                "DS-009",
                "Resolved standard package has no placeholders",
                not has_unresolved_placeholder(standard_package),
                "Resolved package must not contain ${...}, <...>, or > placeholder tokens.",
            )
        )
    return checks


def dataarts_standard_jobs_blocked(standard_package: dict[str, Any]) -> bool:
    return all(
        job.get("execution") == "blocked_until_cloud_approval"
        and all(node.get("execution") == "blocked_until_cloud_approval" for node in job.get("nodes", []))
        for job in standard_package.get("jobs", [])
    )


def collect_probe_bindings(
    *,
    run_dir: Path,
    required_bindings: dict[str, str],
    request: CloudResourceProbeRequest,
) -> tuple[dict[str, str], str, list[str]]:
    warnings: list[str] = []
    if request.source == "operator_provided":
        return {key: str(value).strip() for key, value in request.bindings.items()}, "operator_provided", warnings
    if request.source == "existing_binding":
        binding_status = read_optional_json(run_dir / CLOUD_BINDING_STATUS_NAME) or {}
        bindings = {
            key: str(value).strip()
            for key, value in (binding_status.get("bindings") or {}).items()
        }
        warnings.append("Existing binding may be locally simulated; verify every value in Huawei Cloud console.")
        return bindings, "existing_binding", warnings

    bindings = collect_environment_bindings(required_bindings)
    warnings.append("Environment source reads only non-secret resource identifiers and OBS URIs.")
    return bindings, "environment", warnings


def collect_environment_bindings(required_bindings: dict[str, str]) -> dict[str, str]:
    direct_env_aliases = {
        "VPC_ID": "HUAWEICLOUD_VPC_ID",
        "PRIVATE_SUBNET_ID": "HUAWEICLOUD_PRIVATE_SUBNET_ID",
        "KMS_KEY_ID": "HUAWEICLOUD_KMS_KEY_ID",
        "MRS_CLUSTER_ID": "HUAWEICLOUD_MRS_CLUSTER_ID",
        "DWS_CONNECTION_NAME": "HUAWEICLOUD_DWS_CONNECTION_NAME",
        "DATAARTS_WORKSPACE_ID": "HUAWEICLOUD_DATAARTS_WORKSPACE_ID",
    }
    obs_bucket = os.getenv("HUAWEICLOUD_OBS_BUCKET", "").strip()
    bindings: dict[str, str] = {}
    for key in required_bindings:
        value = os.getenv(key, "").strip()
        if not value and key in direct_env_aliases:
            value = os.getenv(direct_env_aliases[key], "").strip()
        if not value and key == "HUAWEICLOUD_REGION":
            value = os.getenv("HUAWEICLOUD_REGION", "la-south-2").strip()
        if not value and key == "OBS_RAW_URI" and obs_bucket:
            value = f"obs://{obs_bucket}/raw/tax/"
        if not value and key == "OBS_SILVER_URI" and obs_bucket:
            value = f"obs://{obs_bucket}/silver/tax/"
        if not value and key == "OBS_GOLD_URI" and obs_bucket:
            value = f"obs://{obs_bucket}/gold/tax/"
        if not value and key == "OBS_RELEASE_URI" and obs_bucket:
            value = str(required_bindings[key]).replace("${AGENTIC_TAX_TAX_TAXPAYER_ANNUAL_BASE_BUCKET}", obs_bucket)
        if not value and key == "OBS_AUDIT_URI" and obs_bucket:
            value = str(required_bindings[key]).replace("${AGENTIC_TAX_TAX_TAXPAYER_ANNUAL_BASE_BUCKET}", obs_bucket)
        if value:
            bindings[key] = value
    return bindings


def run_readonly_probe_adapter(
    *,
    allow_network_probe: bool,
    bindings: dict[str, str],
) -> dict[str, Any]:
    if not allow_network_probe:
        return {
            "status": "skipped",
            "reason": "Real cloud read-only API validation was not requested.",
            "credentials_present": bool(os.getenv("HUAWEICLOUD_ACCESS_KEY")) and bool(os.getenv("HUAWEICLOUD_SECRET_KEY")),
            "network_calls": 0,
            "write_calls": 0,
        }
    return run_real_huaweicloud_readonly_probe(bindings)


def validate_cloud_resource_probe(
    *,
    bindings: dict[str, str],
    required_bindings: dict[str, str],
    standard_package: dict[str, Any],
    resolved_standard_package: dict[str, Any],
    resolved_checks: list[dict[str, str]],
    adapter_result: dict[str, Any],
    binding_source: str,
    source_warnings: list[str],
) -> list[dict[str, str]]:
    missing = missing_cloud_bindings(bindings, required_bindings)
    unresolved = unresolved_binding_values(bindings)
    failed_resolved_checks = [check for check in resolved_checks if check["status"] == "failed"]
    checks = [
        probe_check(
            "CP-001",
            "All required non-secret resource bindings are present",
            not missing,
            f"source={binding_source}; missing={missing}",
        ),
        probe_check(
            "CP-002",
            "Bindings contain no unresolved placeholders",
            not unresolved,
            f"unresolved={unresolved}",
        ),
        probe_check(
            "CP-003",
            "OBS paths preserve lake layers",
            obs_bindings_are_layered(bindings),
            "OBS_RAW/SILVER/GOLD/RELEASE/AUDIT URIs must point to their matching layers.",
        ),
        probe_check(
            "CP-004",
            "Region and project id are bound",
            bool(bindings.get("HUAWEICLOUD_REGION")) and bool(bindings.get("HUAWEICLOUD_PROJECT_ID")),
            f"region={bindings.get('HUAWEICLOUD_REGION', '')}; project_id_present={bool(bindings.get('HUAWEICLOUD_PROJECT_ID'))}",
        ),
        probe_check(
            "CP-005",
            "No credential-like binding names are included",
            not has_forbidden_secret_binding(bindings),
            "AK/SK, passwords, private keys, and database passwords must not be in binding values.",
        ),
        probe_check(
            "CP-006",
            "Resolved standard DataArts package is valid",
            not failed_resolved_checks,
            f"failed_standard_checks={[check['id'] for check in failed_resolved_checks]}",
        ),
        probe_check(
            "CP-007",
            "Cloud execution remains blocked",
            standard_package.get("cloud_execution", {}).get("state") == "blocked"
            and resolved_standard_package.get("cloud_execution", {}).get("state") == "blocked",
            "Read-only validation must not authorize DataArts, MRS, DWS, or OBS execution.",
        ),
        probe_check(
            "CP-008",
            "Read-only cloud API validation did not perform write calls",
            adapter_result.get("write_calls", 0) == 0 and adapter_result.get("status") != "failed",
            f"{adapter_result.get('reason', '')} write_calls={adapter_result.get('write_calls', 0)}",
            status="warning" if adapter_result.get("status") == "skipped" else None,
        ),
    ]
    for index, warning in enumerate(source_warnings, start=1):
        checks.append(
            probe_check(
                f"CP-W{index:02d}",
                "Operator verification warning",
                True,
                warning,
                status="warning",
            )
        )
    return checks


def probe_check(
    check_id: str,
    name: str,
    passed: bool,
    detail: str,
    *,
    status: str | None = None,
) -> dict[str, str]:
    return {
        "id": check_id,
        "name": name,
        "status": status or ("passed" if passed else "failed"),
        "detail": detail,
    }


def resolve_placeholders(payload: Any, bindings: dict[str, str]) -> Any:
    if isinstance(payload, dict):
        return {key: resolve_placeholders(value, bindings) for key, value in payload.items()}
    if isinstance(payload, list):
        return [resolve_placeholders(item, bindings) for item in payload]
    if isinstance(payload, str):
        resolved = payload
        parameter_to_binding = {
            "obs_raw_uri": "OBS_RAW_URI",
            "obs_silver_uri": "OBS_SILVER_URI",
            "obs_gold_uri": "OBS_GOLD_URI",
            "obs_release_uri": "OBS_RELEASE_URI",
            "obs_audit_uri": "OBS_AUDIT_URI",
            "mrs_cluster_id": "MRS_CLUSTER_ID",
            "dws_connection_name": "DWS_CONNECTION_NAME",
            "dataarts_workspace_id": "DATAARTS_WORKSPACE_ID",
        }
        for key, value in bindings.items():
            resolved = resolved.replace("${" + key + "}", value)
        for parameter_name, binding_key in parameter_to_binding.items():
            if binding_key in bindings and resolved == "${" + binding_key + "}":
                resolved = bindings[binding_key]
            if binding_key in bindings and resolved == "${" + parameter_name.upper() + "}":
                resolved = bindings[binding_key]
        return resolved
    return payload


def sanitize_probe_bindings(bindings: dict[str, str]) -> dict[str, str]:
    forbidden_names = ("ACCESS_KEY", "SECRET_KEY", "PASSWORD", "PRIVATE_KEY")
    safe: dict[str, str] = {}
    for key, value in bindings.items():
        if any(word in key.upper() for word in forbidden_names):
            safe[key] = "<redacted>"
        else:
            safe[key] = value
    return safe


def validate_import_review(
    *,
    readiness: dict[str, Any],
    release_status: dict[str, Any],
    release_manifest: dict[str, Any],
    binding_status: dict[str, Any],
    preflight: dict[str, Any],
    import_readiness: dict[str, Any],
    resolved_import_package: dict[str, Any],
    final_manifest: dict[str, Any],
) -> list[dict[str, str]]:
    checks = [
        import_review_check(
            "IR-001",
            "Executable artifact approvals are still current",
            readiness["ready"],
            f"approved={readiness.get('approved_artifacts', [])}; missing={readiness.get('missing_approvals', [])}",
        ),
        import_review_check(
            "IR-002",
            "Deployment preflight has no failed checks",
            int(preflight.get("failed", 0)) == 0 and preflight.get("cloud_execution") == "blocked",
            f"preflight_status={preflight.get('status')}; failed={preflight.get('failed')}; cloud_execution={preflight.get('cloud_execution')}",
        ),
        import_review_check(
            "IR-003",
            "Cloud binding is ready for import review",
            bool(binding_status.get("ready_for_import_review")) and not binding_status.get("failed_checks"),
            f"binding_status={binding_status.get('status')}; failed={binding_status.get('failed_checks', [])}",
        ),
        import_review_check(
            "IR-004",
            "Cloud import readiness is review-only",
            import_readiness.get("status") == "ready_for_import_review"
            and import_readiness.get("cloud_execution") == "blocked",
            f"readiness_status={import_readiness.get('status')}; cloud_execution={import_readiness.get('cloud_execution')}",
        ),
        import_review_check(
            "IR-005",
            "Resolved DataArts package has no placeholders",
            not has_unresolved_placeholder(resolved_import_package),
            "No ${...}, <...>, or > placeholder tokens remain in the resolved import package.",
        ),
        import_review_check(
            "IR-006",
            "DataArts and MRS execution remain blocked",
            dataarts_package_execution_blocked(resolved_import_package),
            "All jobs keep execution=blocked_until_cloud_approval and package cloud_execution.state=blocked.",
        ),
        import_review_check(
            "IR-007",
            "No secret-like values are included",
            not has_forbidden_secret_binding(binding_status.get("bindings", {}))
            and not has_forbidden_secret_binding(resolved_import_package.get("parameters", {})),
            "Credential-like binding names are not part of the handoff package.",
        ),
        import_review_check(
            "IR-008",
            "Final import manifest is handoff-only",
            final_manifest_requires_manual_approval(final_manifest),
            f"import_permission={final_manifest.get('import_permission')}; cloud_execution={final_manifest.get('cloud_execution')}",
        ),
        import_review_check(
            "IR-009",
            "Release manifest carries binding evidence",
            release_manifest.get("cloud_binding", {}).get("ready_for_import_review") is True
            and release_status.get("cloud_binding", {}).get("ready_for_import_review") is True,
            "Release status and manifest both include successful cloud binding evidence.",
        ),
    ]
    return checks


def import_review_check(check_id: str, name: str, passed: bool, detail: str) -> dict[str, str]:
    return {
        "id": check_id,
        "name": name,
        "status": "passed" if passed else "failed",
        "detail": detail,
    }


def has_unresolved_placeholder(payload: Any) -> bool:
    text = json.dumps(payload, ensure_ascii=False)
    return "${" in text or "<" in text or ">" in text


def dataarts_package_execution_blocked(package: dict[str, Any]) -> bool:
    return (
        package.get("cloud_execution", {}).get("state") == "blocked"
        and all(job.get("execution") == "blocked_until_cloud_approval" for job in package.get("jobs", []))
    )


def final_manifest_requires_manual_approval(manifest: dict[str, Any]) -> bool:
    controls = manifest.get("execution_controls", {})
    confirmations = manifest.get("required_operator_confirmations", [])
    return (
        manifest.get("cloud_execution") == "blocked"
        and manifest.get("import_permission") == "review_only"
        and controls.get("dataarts_schedule") == "disabled_until_cloud_approval"
        and controls.get("mrs_submit") == "blocked_until_cloud_approval"
        and len(confirmations) >= 5
    )


def build_final_import_manifest(
    *,
    run_id: str,
    generated_at: str,
    release_status: dict[str, Any],
    binding_status: dict[str, Any],
    import_readiness: dict[str, Any],
) -> dict[str, Any]:
    release_files = {
        item.get("name"): item
        for item in release_status.get("files", [])
        if item.get("name")
    }
    required_names = [
        "approval_summary.json",
        "deployment_preflight.json",
        "environment_profile.yaml",
        "cloud_binding_simulation.json",
        "resolved_dataarts_import_package.json",
        "cloud_import_readiness.json",
    ]
    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "package_type": "cloud_import_handoff_preview",
        "cloud_execution": "blocked",
        "import_permission": "review_only",
        "binding_mode": binding_status.get("mode", "unknown"),
        "binding_status": binding_status.get("status"),
        "import_readiness_status": import_readiness.get("status"),
        "source_files": [
            release_files[name]
            for name in required_names
            if name in release_files
        ],
        "required_operator_confirmations": [
            "Verify region la-south-2 service availability and quotas in Huawei Cloud console.",
            "Verify OBS raw, silver, gold, release, and audit paths exist and use approved KMS encryption.",
            "Verify IAM roles follow least privilege for DataArts, MRS Spark, DWS, and OBS release access.",
            "Import DataArts package only into an approved workspace and keep schedules disabled.",
            "Submit MRS Spark and DWS changes only after a separate cloud execution approval.",
            "Do not paste AK/SK, database credentials, or signing material into this package.",
        ],
        "execution_controls": {
            "dataarts_schedule": "disabled_until_cloud_approval",
            "mrs_submit": "blocked_until_cloud_approval",
            "dws_apply": "blocked_until_cloud_approval",
            "production_window": "requires_separate_approval",
        },
    }


def render_operator_handoff(
    *,
    run_id: str,
    generated_at: str,
    review_payload: dict[str, Any],
    final_manifest: dict[str, Any],
) -> str:
    status = review_payload.get("status", "unknown")
    failed = review_payload.get("failed_checks", [])
    confirmations = "\n".join(
        f"{index}. {item}"
        for index, item in enumerate(final_manifest.get("required_operator_confirmations", []), start=1)
    )
    failed_text = "\n".join(f"- {item}" for item in failed) if failed else "- None"
    source_files = "\n".join(
        f"- {item['name']}: {item['url']}"
        for item in final_manifest.get("source_files", [])
    )
    return f"""# Operator Handoff

- run_id: {run_id}
- generated_at: {generated_at}
- status: {status}
- cloud_execution: blocked
- import_permission: review_only

## Purpose

This handoff is a local review package for a future Huawei Cloud DataArts import. It does not call OBS, MRS, DWS, DataArts, IAM, or KMS APIs.

## Required Confirmations

{confirmations}

## Source Files

{source_files}

## Failed Checks

{failed_text}

## Next Action

Review `cloud_import_review.json` and `final_import_manifest.json`. If every check is still green, a cloud operator may prepare a manual DataArts import plan, but execution remains blocked until a separate cloud deployment approval.
"""


def build_real_cloud_resource_binding_template(
    *,
    run_id: str,
    generated_at: str,
    required_bindings: dict[str, str],
    current_bindings: dict[str, str],
    binding_source: str,
) -> dict[str, Any]:
    descriptions = {
        "HUAWEICLOUD_REGION": "Huawei Cloud region id, for example la-south-2.",
        "HUAWEICLOUD_PROJECT_ID": "Project id for read-only SDK clients.",
        "VPC_ID": "Existing VPC id for MRS, DWS, DataArts connectivity checks.",
        "PRIVATE_SUBNET_ID": "Existing private subnet id inside the VPC.",
        "KMS_KEY_ID": "Existing DEW/KMS key id approved for the data lake paths.",
        "OBS_RAW_URI": "Existing OBS raw landing path.",
        "OBS_SILVER_URI": "Existing OBS cleaned/silver path.",
        "OBS_GOLD_URI": "Existing OBS curated/gold path.",
        "OBS_RELEASE_URI": "Existing OBS release evidence path for generated artifacts.",
        "OBS_AUDIT_URI": "Existing OBS audit evidence path.",
        "MRS_CLUSTER_ID": "Existing MRS cluster id for future Spark execution.",
        "DWS_CONNECTION_NAME": "Existing DWS connection name or approved target alias.",
        "DATAARTS_WORKSPACE_ID": "Existing DataArts Studio workspace id.",
    }
    env_aliases = {
        "VPC_ID": "HUAWEICLOUD_VPC_ID",
        "PRIVATE_SUBNET_ID": "HUAWEICLOUD_PRIVATE_SUBNET_ID",
        "KMS_KEY_ID": "HUAWEICLOUD_KMS_KEY_ID",
        "MRS_CLUSTER_ID": "HUAWEICLOUD_MRS_CLUSTER_ID",
        "DWS_CONNECTION_NAME": "HUAWEICLOUD_DWS_CONNECTION_NAME",
        "DATAARTS_WORKSPACE_ID": "HUAWEICLOUD_DATAARTS_WORKSPACE_ID",
        "OBS_*_URI": "HUAWEICLOUD_OBS_BUCKET can derive OBS_RAW_URI, OBS_SILVER_URI, OBS_GOLD_URI, OBS_RELEASE_URI, and OBS_AUDIT_URI.",
    }
    fields = []
    request_bindings: dict[str, str] = {}
    for key in sorted(required_bindings):
        value = binding_template_value(key, current_bindings.get(key, ""))
        request_bindings[key] = value
        fields.append(
            {
                "key": key,
                "required": True,
                "secret": False,
                "value": value,
                "description": descriptions.get(key, "Existing non-secret Huawei Cloud resource binding."),
                "environment_alias": env_aliases.get(key, key),
            }
        )

    return {
        "schema": "tax.agentic.real_cloud_resource_binding.v1",
        "run_id": run_id,
        "generated_at": generated_at,
        "purpose": "Template for validating existing Huawei Cloud resources before any real execution layer is enabled.",
        "binding_source": binding_source,
        "cloud_execution": "blocked",
        "creates_resources": False,
        "modifies_resources": False,
        "submits_jobs": False,
        "required_bindings": fields,
        "environment_aliases": env_aliases,
        "operator_provided_request_template": {
            "source": "operator_provided",
            "allow_network_probe": False,
            "reviewer": "cloud_operator",
            "note": "Non-secret resource ids copied from an approved Huawei Cloud environment review.",
            "bindings": request_bindings,
        },
        "readonly_probe_enablement": {
            "optional": True,
            "requires_local_environment_flag": READONLY_PROBE_ENV,
            "requires_readonly_iam_credentials_in_environment": True,
            "credential_values_must_not_be_written_here": True,
        },
        "forbidden_in_this_file": [
            "access key values",
            "secret key values",
            "passwords",
            "private keys",
            "database credentials",
        ],
        "approval_boundary": "Passing this template validation does not create resources, import DataArts jobs, submit MRS jobs, run SQL, enable schedules, or approve production execution.",
    }


def binding_template_value(key: str, value: str) -> str:
    clean = str(value or "").strip()
    lowered = clean.lower()
    if not clean or "${" in clean or "placeholder" in lowered or "local-simulated" in lowered:
        return f"<fill-{key}>"
    return clean


def render_cloud_readonly_verification_checklist(
    *,
    run_id: str,
    generated_at: str,
    binding_template: dict[str, Any],
    probe_payload: dict[str, Any],
    execution_readiness: dict[str, Any],
) -> str:
    bindings = "\n".join(
        f"- {item['key']}: {item['description']}"
        for item in binding_template.get("required_bindings", [])
    )
    adapter = probe_payload.get("adapter", {})
    return f"""# Huawei Cloud Existing Resource Read-only Verification Checklist

- run_id: {run_id}
- generated_at: {generated_at}
- current_status: {probe_payload.get("status")}
- real_cloud_verified: {str(probe_payload.get("real_cloud_verified")).lower()}
- cloud_execution: blocked

## What This Step Means

This step verifies existing Huawei Cloud resource bindings and read-only access. It does not create resources, modify resources, upload files, import DataArts packages, submit MRS jobs, run DWS SQL, enable schedules, or approve production execution.

## Required Non-secret Bindings

Use `real_cloud_resource_binding_template.json` as the source template. Fill only non-secret identifiers and URIs:

{bindings}

## Read-only Credential Boundary

Read-only IAM credentials, if used, must be supplied only through the operator shell environment. Do not put credential values in prompts, request JSON, generated files, screenshots, README edits, or commits.

The local flag `{READONLY_PROBE_ENV}` must be enabled before the backend is allowed to call Huawei Cloud read-only APIs. The page checkbox alone is not enough.

## Operator Steps

1. Confirm every binding in `real_cloud_resource_binding_template.json` points to an approved existing Huawei Cloud resource.
2. Install the optional Huawei Cloud SDK dependencies on the operator machine if they are not already present.
3. Set read-only IAM credential values in the operator shell environment only.
4. Set `{READONLY_PROBE_ENV}=true` in the same shell that runs FastAPI.
5. Open the workbench, enable "调用华为云只读 API 验证现有资源", and click "验证云资源".
6. Confirm `real_cloud_verified=true` only after the report shows read-only service checks passed and `write_calls=0`.
7. Keep `cloud_execution=blocked` until a separate execution-window approval is recorded.

## Expected Pass Criteria

- All required non-secret bindings are present.
- No binding value contains unresolved placeholders.
- OBS raw, silver, gold, release, and audit paths stay in their approved layers.
- The read-only adapter reports `write_calls=0`.
- If live SDK checks are enabled, each service check reports read-only success.
- Generated files contain no AK/SK values, passwords, private keys, or database credentials.

## Stop Conditions

- Any resource id points to an unapproved environment.
- The IAM role has write privileges beyond the approved read-only test role.
- Any generated file contains credential values.
- DataArts schedules, MRS jobs, DWS SQL execution, OBS uploads, or package imports are requested before separate approval.

## Current Adapter Result

- adapter_status: {adapter.get("status")}
- adapter_reason: {adapter.get("reason")}
- network_calls: {adapter.get("network_calls", 0)}
- write_calls: {adapter.get("write_calls", 0)}
- readiness_summary: {execution_readiness.get("summary")}

Cloud execution remains blocked after this checklist.
"""


def render_cloud_execution_approval_request(
    *,
    run_id: str,
    generated_at: str,
    probe_payload: dict[str, Any],
    execution_readiness: dict[str, Any],
) -> str:
    checks = "\n".join(
        f"- {item['id']} {item['name']}: {item['status']} - {item['detail']}"
        for item in probe_payload.get("checks", [])
    )
    service_lines = "\n".join(
        f"- {service.get('service')}: {service.get('status')} ({', '.join(service.get('readonly_calls', []))})"
        for service in probe_payload.get("adapter", {}).get("services", [])
    ) or "- No live service calls were executed."
    warnings = "\n".join(f"- {item}" for item in probe_payload.get("warnings", [])) or "- None"
    failed = "\n".join(f"- {item}" for item in probe_payload.get("failed_checks", [])) or "- None"
    bindings = "\n".join(
        f"- {key}: {value}"
        for key, value in sorted((probe_payload.get("bindings") or {}).items())
    )
    return f"""# Cloud Execution Approval Request

- run_id: {run_id}
- generated_at: {generated_at}
- status: {execution_readiness.get("status")}
- real_cloud_verified: {str(probe_payload.get("real_cloud_verified")).lower()}
- cloud_execution: blocked

## Purpose

This file is the final local approval request before a future Huawei Cloud execution window. It does not authorize execution by itself, and it must not be treated as a resource creation or job submission request.

## Resource Bindings

{bindings}

## Read-only Resource Verification Result

- adapter_status: {probe_payload.get("adapter", {}).get("status")}
- adapter_reason: {probe_payload.get("adapter", {}).get("reason")}
- network_calls: {probe_payload.get("adapter", {}).get("network_calls", 0)}
- write_calls: {probe_payload.get("adapter", {}).get("write_calls", 0)}

## Service Checks

{service_lines}

## Gate Checks

{checks}

## Warnings

{warnings}

## Failed Checks

{failed}

## Approval Conditions

1. `real_cloud_verified` must be true for a real execution request, or a named operator must explicitly accept console-only verification.
2. OBS raw, silver, gold, release, and audit paths must exist and use approved encryption.
3. MRS, DWS, DataArts, KMS, VPC, and subnet bindings must be verified in Huawei Cloud.
4. This approval request must not create resources, import DataArts jobs, submit MRS jobs, run SQL, upload OBS objects, or enable schedules.
5. DataArts schedules must remain disabled until the execution window opens.
6. The approved execution window, rollback owner, and audit evidence destination must be recorded outside this local POC.
7. AK/SK, passwords, private keys, and database credentials must stay outside generated files.

## Current Decision

{execution_readiness.get("summary")}

Cloud execution remains blocked until a separate explicit operator approval.
"""


def append_release_files(release_status: dict[str, Any], files: list[dict[str, str]]) -> dict[str, Any]:
    existing = {
        file.get("name"): file
        for file in release_status.get("files", [])
        if file.get("name")
    }
    for file in files:
        existing[file["name"]] = file
    release_status["files"] = list(existing.values())
    return release_status


def render_environment_profile(profile: dict[str, Any]) -> str:
    return render_simple_yaml(profile)


def render_simple_yaml(value: Any, indent: int = 0) -> str:
    lines: list[str] = []
    spaces = " " * indent
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, (dict, list)):
                lines.append(f"{spaces}{key}:")
                lines.append(render_simple_yaml(child, indent + 2))
            else:
                lines.append(f"{spaces}{key}: {yaml_scalar(child)}")
    elif isinstance(value, list):
        if not value:
            lines.append(f"{spaces}[]")
        for child in value:
            if isinstance(child, (dict, list)):
                lines.append(f"{spaces}-")
                lines.append(render_simple_yaml(child, indent + 2))
            else:
                lines.append(f"{spaces}- {yaml_scalar(child)}")
    else:
        lines.append(f"{spaces}{yaml_scalar(value)}")
    return "\n".join(line for line in lines if line != "")


def yaml_scalar(value: Any) -> str:
    text = str(value).replace("\n", " ").strip()
    if not text:
        return '""'
    if any(char in text for char in [":", "#", "{", "}", "[", "]", ","]):
        return '"' + text.replace('"', '\\"') + '"'
    return text


def render_deployment_plan(
    *,
    run_id: str,
    generated_at: str,
    request: dict[str, Any],
    run_manifest: dict[str, Any],
    approved_artifacts: list[str],
) -> str:
    scenario = request.get("scenario") or run_manifest.get("request", {}).get("scenario") or "tax_agentic_task"
    approved = "\n".join(f"  - {name}: approved" for name in approved_artifacts)
    return f"""release_id: {run_id}
generated_at: {generated_at}
scenario: {scenario}
status: local_release_candidate
cloud_execution: blocked
target_services:
  - OBS
  - MRS Spark
  - GaussDB(DWS)
  - DataArts Factory
required_manual_approvals:
{approved}
steps:
  - id: upload_artifacts_to_obs
    action: copy reviewed artifacts to approved OBS release path
    execution: manual
  - id: create_or_update_dataarts_job
    action: import dataarts_import_package.json into a reviewed workspace
    execution: manual
  - id: bind_mrs_and_dws
    action: map placeholders to approved MRS cluster and DWS connection
    execution: manual
  - id: run_cloud_smoke_test
    action: execute only after cloud approval and IAM verification
    execution: blocked
controls:
  secrets: environment_or_cloud_secret_service_only
  iam: least_privilege
  production_submit: blocked_until_explicit_approval
"""


def render_rollback_plan(run_id: str, generated_at: str) -> str:
    return f"""# Rollback Plan

- release_id: {run_id}
- generated_at: {generated_at}
- cloud_execution: blocked

## Before Cloud Submit

1. Do not import the DataArts package if any artifact review is revoked.
2. Delete the local `release/` directory and regenerate after re-approval.
3. Keep OBS, MRS, DWS, and DataArts unchanged.

## After Future Cloud Submit

1. Disable the DataArts job schedule.
2. Stop or cancel the MRS Spark job if it is running.
3. Repoint DWS serving objects to the previous approved view or snapshot.
4. Preserve logs, run_manifest.json, approval_summary.json, and lineage_manifest.json for audit.
"""


def release_file_entry(run_id: str, release_dir: Path, name: str, description: str) -> dict[str, str]:
    path = release_dir / name
    return {
        "name": name,
        "description": description,
        "path": str(path.relative_to(APP_ROOT)).replace("\\", "/"),
        "url": f"/generated/{run_id}/{RELEASE_DIR_NAME}/{name}",
        "sha256": file_sha256(path),
    }


def safe_artifact_name(name: str) -> str:
    artifact_name = Path(name).name
    if artifact_name != name or "/" in name or "\\" in name or not artifact_name:
        raise ValueError("Invalid artifact name")
    return artifact_name


def file_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    return sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_optional_json(path: Path) -> Any:
    if not path.exists():
        return None
    return read_json(path)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
