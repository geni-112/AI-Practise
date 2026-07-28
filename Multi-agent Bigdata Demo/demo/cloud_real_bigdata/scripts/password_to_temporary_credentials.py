#!/usr/bin/env python3
"""Exchange a Huawei Cloud password for short-lived programmatic credentials."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

import requests


IAM_ENDPOINT = "https://iam.myhuaweicloud.com"


def safe_error(message: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "password_persisted": False,
        "iam_token_persisted": False,
        "error": message[:800],
    }


def checked_json(response: requests.Response, operation: str) -> dict[str, Any]:
    if response.status_code >= 300:
        if response.status_code in {401, 403}:
            raise RuntimeError(
                f"{operation} was rejected. Check account/domain, username, password, IAM permissions, and MFA policy."
            )
        raise RuntimeError(f"{operation} failed with HTTP {response.status_code}.")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{operation} returned an invalid response.")
    return payload


def obtain_global_token(
    session: requests.Session,
    account_name: str,
    user_name: str,
    password: str,
) -> tuple[str, dict[str, Any]]:
    body = {
        "auth": {
            "identity": {
                "methods": ["password"],
                "password": {
                    "user": {
                        "name": user_name,
                        "password": password,
                        "domain": {"name": account_name},
                    }
                },
            },
            "scope": {"domain": {"name": account_name}},
        }
    }
    response = session.post(
        f"{IAM_ENDPOINT}/v3/auth/tokens?nocatalog=true",
        json=body,
        timeout=30,
    )
    payload = checked_json(response, "Password authentication")
    token = response.headers.get("X-Subject-Token", "").strip()
    if not token:
        raise RuntimeError("Password authentication succeeded without returning X-Subject-Token.")
    return token, payload


def discover_project_id(
    session: requests.Session,
    token: str,
    region: str,
    candidate_project_id: str,
) -> tuple[str, str]:
    response = session.get(
        f"{IAM_ENDPOINT}/v3/auth/projects",
        headers={"X-Auth-Token": token},
        timeout=30,
    )
    payload = checked_json(response, "Project discovery")
    projects = payload.get("projects") or []
    for project in projects:
        if not isinstance(project, dict) or not project.get("id"):
            continue
        if project.get("name") == region or project.get("region_id") == region:
            return str(project["id"]), "iam_project_discovery"
    if candidate_project_id:
        return candidate_project_id, "candidate_after_iam_project_list"
    raise RuntimeError(f"No project for region {region} was visible to this identity.")


def obtain_temporary_credentials(
    session: requests.Session,
    token: str,
    duration_seconds: int,
) -> dict[str, str]:
    body = {
        "auth": {
            "identity": {
                "methods": ["token"],
                "token": {
                    "id": token,
                    "duration_seconds": duration_seconds,
                },
            }
        }
    }
    response = session.post(
        f"{IAM_ENDPOINT}/v3.0/OS-CREDENTIAL/securitytokens",
        json=body,
        timeout=30,
    )
    payload = checked_json(response, "Temporary credential exchange")
    credential = payload.get("credential") or {}
    required = ["access", "secret", "securitytoken", "expires_at"]
    if not all(credential.get(name) for name in required):
        raise RuntimeError("Temporary credential exchange returned incomplete credentials.")
    return {name: str(credential[name]) for name in required}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-name", required=True)
    parser.add_argument("--user-name", default="")
    parser.add_argument("--region", default="la-south-2")
    parser.add_argument("--candidate-project-id", default="")
    parser.add_argument("--duration-seconds", type=int, default=14400)
    args = parser.parse_args()

    password = os.environ.get("HUAWEICLOUD_LOGIN_PASSWORD", "")
    if not password:
        print(json.dumps(safe_error("Local password input was empty.")))
        return 1
    if not 900 <= args.duration_seconds <= 86400:
        print(json.dumps(safe_error("Temporary credential duration must be between 900 and 86400 seconds.")))
        return 1

    user_name = args.user_name.strip() or args.account_name.strip()
    try:
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json;charset=utf8"})
        token, token_payload = obtain_global_token(
            session,
            args.account_name.strip(),
            user_name,
            password,
        )
        project_id, project_source = discover_project_id(
            session,
            token,
            args.region,
            args.candidate_project_id.strip(),
        )
        credential = obtain_temporary_credentials(session, token, args.duration_seconds)
        token_info = token_payload.get("token") or {}
        domain = ((token_info.get("user") or {}).get("domain") or {})
        result = {
            "status": "ready",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "region": args.region,
            "project_id": project_id,
            "project_id_source": project_source,
            "domain_id": str(domain.get("id") or ""),
            "access_key": credential["access"],
            "secret_key": credential["secret"],
            "security_token": credential["securitytoken"],
            "expires_at": credential["expires_at"],
            "password_persisted": False,
            "iam_token_persisted": False,
            "temporary_credentials": True,
        }
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except Exception as error:
        message = str(error).replace(password, "<redacted>")
        print(json.dumps(safe_error(message), ensure_ascii=True))
        return 1
    finally:
        password = ""


if __name__ == "__main__":
    raise SystemExit(main())
