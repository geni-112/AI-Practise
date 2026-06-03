from __future__ import annotations

import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGION = "la-south-2"


def env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise SystemExit(f"{name} is required. Set it in the shell environment, not in source files.")
    return value or ""


def main() -> None:
    region = env("HUAWEICLOUD_REGION", DEFAULT_REGION)
    if region != DEFAULT_REGION:
        raise SystemExit(f"This demo is pinned to Chile LA-Santiago: {DEFAULT_REGION}. Current region={region}")

    ak = env("HUAWEICLOUD_ACCESS_KEY", required=True)
    sk = env("HUAWEICLOUD_SECRET_KEY", required=True)

    try:
        from huaweicloudsdkcore.auth.credentials import GlobalCredentials
        from huaweicloudsdkiam.v3 import IamClient, KeystoneListAuthProjectsRequest
        from huaweicloudsdkiam.v3.region.iam_region import IamRegion
    except ImportError as exc:
        raise SystemExit("Install Huawei Cloud SDK first: pip install huaweicloudsdkcore huaweicloudsdkiam") from exc

    credentials = GlobalCredentials(ak, sk)
    client = (
        IamClient.new_builder()
        .with_credentials(credentials)
        .with_region(IamRegion.value_of(region))
        .build()
    )

    response = client.keystone_list_auth_projects(KeystoneListAuthProjectsRequest())
    data = response.to_json_object()
    projects = data.get("projects") or []
    target = next((p for p in projects if p.get("name") == region), None)
    if not target:
        names = ", ".join(sorted(p.get("name", "") for p in projects if p.get("name")))
        raise SystemExit(f"No authorized project found for {region}. Available projects: {names or '<none>'}")

    out = {
        "project_id": target["id"],
        "project_name": target["name"],
        "region": region,
    }
    runtime = ROOT / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "resolved-project.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Resolved Huawei Cloud project: project_name={out['project_name']} project_id={out['project_id']}")


if __name__ == "__main__":
    main()
