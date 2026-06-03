from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


IAM_URL = "https://iam.myhuaweicloud.com/v3/auth/tokens?nocatalog=true"
REGION = "la-south-2"


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def main() -> None:
    if os.environ.get("HUAWEICLOUD_X_AUTH_TOKEN") and os.environ.get("HUAWEICLOUD_PROJECT_ID"):
        print("IAM token and project id already set in environment.")
        return

    account_name = required("HUAWEICLOUD_ACCOUNT_NAME")
    password = required("HUAWEICLOUD_ACCOUNT_PASSWORD")

    # The stored bootstrap has a single AccountName field. In the original local
    # workflow this is the Huawei Cloud account/domain name. For root-account
    # style auth, Huawei Cloud examples also use the same name as the user name.
    payload = {
        "auth": {
            "identity": {
                "methods": ["password"],
                "password": {
                    "user": {
                        "domain": {"name": account_name},
                        "name": account_name,
                        "password": password,
                    }
                },
            },
            "scope": {"project": {"name": REGION}},
        }
    }

    request = urllib.request.Request(
        IAM_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json;charset=utf8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            token = response.headers.get("X-Subject-Token", "")
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(
            "Could not obtain IAM project token from DPAPI account password. "
            "Set HUAWEICLOUD_X_AUTH_TOKEN and HUAWEICLOUD_PROJECT_ID in the local shell, "
            f"or refresh the saved credential bootstrap. HTTP {exc.code}: {detail[:500]}"
        ) from exc

    project = body.get("token", {}).get("project", {})
    project_id = project.get("id")
    if not token or not project_id:
        raise SystemExit("IAM response did not include X-Subject-Token and project.id")

    # Print non-secret project id so the parent PowerShell can capture it if run
    # directly. Also persist to a local runtime env file without the token.
    os.environ["HUAWEICLOUD_X_AUTH_TOKEN"] = token
    os.environ["HUAWEICLOUD_PROJECT_ID"] = project_id
    runtime_dir = os.path.join(os.getcwd(), "runtime")
    os.makedirs(runtime_dir, exist_ok=True)
    with open(os.path.join(runtime_dir, "resolved-project.json"), "w", encoding="utf-8") as fh:
        json.dump({"project_id": project_id, "project_name": project.get("name")}, fh, indent=2)
    print(f"IAM project token acquired for project_id={project_id}, project_name={project.get('name')}")


if __name__ == "__main__":
    main()
