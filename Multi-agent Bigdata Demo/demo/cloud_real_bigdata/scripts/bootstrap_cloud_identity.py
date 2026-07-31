#!/usr/bin/env python3
"""Resolve the regional project and import a locally generated ECS public key."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from huaweicloudsdkcore.auth.credentials import BasicCredentials, GlobalCredentials
from huaweicloudsdkecs.v2 import (
    EcsClient,
    NovaCreateKeypairOption,
    NovaCreateKeypairRequest,
    NovaCreateKeypairRequestBody,
    NovaListKeypairsRequest,
)
from huaweicloudsdkecs.v2.region.ecs_region import EcsRegion
from huaweicloudsdkiam.v3 import IamClient, KeystoneListAuthProjectsRequest
from huaweicloudsdkiam.v3.region.iam_region import IamRegion


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def redact_error(error: Exception, secrets_to_hide: list[str]) -> str:
    message = f"{type(error).__name__}: {error}"
    for value in secrets_to_hide:
        if value:
            message = message.replace(value, "<redacted>")
    return message[:800]


def response_dict(response: Any) -> dict[str, Any]:
    if hasattr(response, "to_dict"):
        value = response.to_dict()
        if isinstance(value, dict):
            return value
    return {}


def build_ecs_client(
    ak: str, sk: str, project_id: str, region: str, security_token: str = ""
) -> EcsClient:
    credentials = BasicCredentials(ak, sk, project_id)
    if security_token:
        credentials = credentials.with_security_token(security_token)
    return (
        EcsClient.new_builder()
        .with_credentials(credentials)
        .with_region(EcsRegion.value_of(region))
        .build()
    )


def list_keypair_names(client: EcsClient) -> set[str]:
    response = client.nova_list_keypairs(NovaListKeypairsRequest(limit=1000))
    payload = response_dict(response)
    names: set[str] = set()
    for item in payload.get("keypairs") or []:
        keypair = item.get("keypair", item) if isinstance(item, dict) else {}
        name = keypair.get("name") if isinstance(keypair, dict) else None
        if name:
            names.add(str(name))
    return names


def discover_projects(
    ak: str, sk: str, region: str, security_token: str = ""
) -> list[dict[str, Any]]:
    credentials = GlobalCredentials(ak, sk)
    if security_token:
        credentials = credentials.with_security_token(security_token)
    client = (
        IamClient.new_builder()
        .with_credentials(credentials)
        .with_region(IamRegion.value_of(region))
        .build()
    )
    response = client.keystone_list_auth_projects(KeystoneListAuthProjectsRequest())
    payload = response_dict(response)
    return [item for item in (payload.get("projects") or []) if isinstance(item, dict)]


def resolve_project_id(
    ak: str,
    sk: str,
    region: str,
    candidate_project_id: str,
    security_token: str = "",
) -> tuple[str, EcsClient, str]:
    discovery_error = ""
    try:
        projects = discover_projects(ak, sk, region, security_token)
        matching = [
            item
            for item in projects
            if item.get("id")
            and (
                item.get("name") == region
                or item.get("region_id") == region
                or item.get("parent_id") == region
            )
        ]
        for project in matching:
            project_id = str(project["id"])
            client = build_ecs_client(ak, sk, project_id, region, security_token)
            list_keypair_names(client)
            return project_id, client, "iam_discovery"
    except Exception as error:  # The candidate path still verifies credentials.
        discovery_error = type(error).__name__

    if candidate_project_id:
        client = build_ecs_client(ak, sk, candidate_project_id, region, security_token)
        list_keypair_names(client)
        source = "verified_candidate"
        if discovery_error:
            source += f"_after_{discovery_error}"
        return candidate_project_id, client, source

    raise RuntimeError(
        "No project for the selected region could be discovered and no candidate project ID was supplied."
    )


def generate_local_keypair(key_dir: Path, name: str) -> tuple[Path, Path, str]:
    key_dir.mkdir(parents=True, exist_ok=True)
    private_path = key_dir / name
    public_path = key_dir / f"{name}.pub"
    if private_path.exists() or public_path.exists():
        raise RuntimeError(f"Local key path already exists: {private_path}")

    command = [
        "ssh-keygen",
        "-q",
        "-t",
        "rsa",
        "-b",
        "4096",
        "-m",
        "PEM",
        "-N",
        "",
        "-C",
        name,
        "-f",
        str(private_path),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    public_key = public_path.read_text(encoding="utf-8").strip()
    if not public_key.startswith("ssh-rsa "):
        raise RuntimeError("ssh-keygen did not produce an RSA public key.")
    return private_path, public_path, public_key


def create_cloud_keypair(client: EcsClient, name: str, public_key: str) -> None:
    existing_names = list_keypair_names(client)
    if name in existing_names:
        raise RuntimeError(f"Huawei Cloud key pair already exists: {name}")
    option = NovaCreateKeypairOption(name=name, public_key=public_key)
    body = NovaCreateKeypairRequestBody(keypair=option)
    client.nova_create_keypair(NovaCreateKeypairRequest(body=body))


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="la-south-2")
    parser.add_argument("--candidate-project-id", default="")
    parser.add_argument("--key-dir", required=True)
    parser.add_argument("--key-prefix", default="sat-agentic-poc")
    parser.add_argument("--report", required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    report_path = Path(args.report).resolve()
    ak = os.environ.get("HUAWEICLOUD_ACCESS_KEY", "")
    sk = os.environ.get("HUAWEICLOUD_SECRET_KEY", "")
    security_token = os.environ.get("HUAWEICLOUD_SECURITY_TOKEN") or os.environ.get(
        "HW_SECURITY_TOKEN", ""
    )
    private_path: Path | None = None
    public_path: Path | None = None
    cloud_keypair_created = False

    try:
        ak = required_env("HUAWEICLOUD_ACCESS_KEY")
        sk = required_env("HUAWEICLOUD_SECRET_KEY")
        project_id, ecs_client, project_source = resolve_project_id(
            ak=ak,
            sk=sk,
            region=args.region,
            candidate_project_id=args.candidate_project_id.strip(),
            security_token=security_token,
        )

        if args.verify_only:
            report = {
                "status": "ready",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "region": args.region,
                "project_id": project_id,
                "project_id_source": project_source,
                "credentials_verified": True,
                "cloud_keypair_created": False,
                "secret_values_printed": False,
                "paid_resources_created": False,
            }
            write_report(report_path, report)
            print(f"Cloud identity verification ready. Report: {report_path}")
            return 0

        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        keypair_name = f"{args.key_prefix}-{stamp}-{secrets.token_hex(2)}"
        private_path, public_path, public_key = generate_local_keypair(
            Path(args.key_dir).resolve(), keypair_name
        )
        create_cloud_keypair(ecs_client, keypair_name, public_key)
        cloud_keypair_created = True

        report = {
            "status": "ready",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "region": args.region,
            "project_id": project_id,
            "project_id_source": project_source,
            "credentials_verified": True,
            "cloud_keypair_created": True,
            "keypair_name": keypair_name,
            "private_key_path": str(private_path),
            "public_key_path": str(public_path),
            "secret_values_printed": False,
            "paid_resources_created": False,
        }
        write_report(report_path, report)
        print(f"Cloud identity bootstrap ready. Report: {report_path}")
        return 0
    except Exception as error:
        if not cloud_keypair_created and private_path and private_path.exists():
            private_path.unlink(missing_ok=True)
        if not cloud_keypair_created and public_path and public_path.exists():
            public_path.unlink(missing_ok=True)
        report = {
            "status": "failed",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "region": args.region,
            "credentials_verified": False,
            "cloud_keypair_created": cloud_keypair_created,
            "secret_values_printed": False,
            "paid_resources_created": False,
            "error": redact_error(error, [ak, sk, security_token]),
        }
        if cloud_keypair_created and private_path and public_path:
            report["private_key_path"] = str(private_path)
            report["public_key_path"] = str(public_path)
        write_report(report_path, report)
        print(f"Cloud identity bootstrap failed. Report: {report_path}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
