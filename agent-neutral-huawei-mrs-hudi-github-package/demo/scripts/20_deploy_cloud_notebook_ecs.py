from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGION = "la-south-2"
OBS_ENDPOINT = "https://obs.la-south-2.myhuaweicloud.com"

VPC_ID = "86688b29-1c42-4e71-9f75-9d260a6428ae"
SUBNET_ID = "4bc25a96-2798-431e-adb4-abe34f6566f5"
AZ = "la-south-2a"

IMAGE_ID = "a4605ecc-7558-4d2c-95f7-3a595ec3f876"  # Ubuntu 22.04 server 64bit
FLAVOR_CANDIDATES = ["s6.medium.2", "t6.medium.2", "s6.large.2", "t6.large.2", "c6.large.2"]


def env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise SystemExit(f"{name} is required")
    return value or ""


def response_to_json(response: Any) -> dict:
    if hasattr(response, "to_json_object"):
        return response.to_json_object()
    if hasattr(response, "to_dict"):
        return response.to_dict()
    return {}


def credentials():
    from huaweicloudsdkcore.auth.credentials import BasicCredentials

    c = BasicCredentials(
        env("HUAWEICLOUD_ACCESS_KEY", required=True),
        env("HUAWEICLOUD_SECRET_KEY", required=True),
        env("HUAWEICLOUD_PROJECT_ID", required=True),
    )
    if os.environ.get("HUAWEICLOUD_SECURITY_TOKEN"):
        c.with_security_token(os.environ["HUAWEICLOUD_SECURITY_TOKEN"])
    return c


def get_public_ip() -> str:
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=15) as resp:
            return resp.read().decode("utf-8").strip()
    except Exception:
        return "0.0.0.0"


def package_demo(bucket: str) -> tuple[str, str]:
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    zip_path = dist / "cloud-notebook-demo.zip"
    if zip_path.exists():
        zip_path.unlink()

    include_dirs = ["config", "jobs", "notebooks", "scripts", "sql"]
    include_files = ["requirements.txt", "README.md", "architecture-v2.drawio"]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirname in include_dirs:
            base = ROOT / dirname
            for file in base.rglob("*"):
                if file.is_file():
                    zf.write(file, Path("huawei-dli-hudi-demo") / file.relative_to(ROOT))
        for filename in include_files:
            file = ROOT / filename
            if file.exists():
                zf.write(file, Path("huawei-dli-hudi-demo") / file.relative_to(ROOT))

    try:
        from obs import ObsClient
    except ImportError as exc:
        raise SystemExit("Install OBS SDK first: pip install esdk-obs-python") from exc

    client = ObsClient(
        access_key_id=env("HUAWEICLOUD_ACCESS_KEY", required=True),
        secret_access_key=env("HUAWEICLOUD_SECRET_KEY", required=True),
        security_token=os.environ.get("HUAWEICLOUD_SECURITY_TOKEN") or None,
        server=OBS_ENDPOINT,
    )
    key = "cloud-notebook/cloud-notebook-demo.zip"
    resp = client.putFile(bucket, key, str(zip_path))
    if getattr(resp, "status", 0) >= 300:
        raise RuntimeError(f"OBS upload failed: status={getattr(resp, 'status', None)} body={getattr(resp, 'body', None)}")
    signed = client.createSignedUrl("GET", bucket, key, expires=86400)
    return f"obs://{bucket}/{key}", signed.signedUrl


def make_cloud_init(download_url: str, bucket: str, jupyter_token: str) -> str:
    project_id = env("HUAWEICLOUD_PROJECT_ID", required=True)
    script = f"""#!/bin/bash
set -euo pipefail
exec > >(tee -a /var/log/dockone-notebook-bootstrap.log) 2>&1

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-venv python3-pip unzip curl jq ca-certificates

mkdir -p /opt/dockone-demo
cd /opt/dockone-demo
curl -L --retry 5 --retry-delay 10 -o cloud-notebook-demo.zip "{download_url}"
rm -rf huawei-dli-hudi-demo
unzip -o cloud-notebook-demo.zip

python3 -m venv /opt/dockone-demo/venv
/opt/dockone-demo/venv/bin/pip install --upgrade pip
/opt/dockone-demo/venv/bin/pip install -r /opt/dockone-demo/huawei-dli-hudi-demo/requirements.txt jupyterlab nbformat

cat >/opt/dockone-demo/refresh_huawei_env.sh <<'EOS'
#!/bin/bash
set -euo pipefail
META=$(curl -fsS http://169.254.169.254/openstack/latest/securitykey)
ACCESS=$(echo "$META" | jq -r '.credential.access')
SECRET=$(echo "$META" | jq -r '.credential.secret')
TOKEN=$(echo "$META" | jq -r '.credential.securitytoken')
cat >/opt/dockone-demo/huawei_env.sh <<EOF
export HUAWEICLOUD_ACCESS_KEY="$ACCESS"
export HUAWEICLOUD_SECRET_KEY="$SECRET"
export HUAWEICLOUD_SECURITY_TOKEN="$TOKEN"
export HUAWEICLOUD_PROJECT_ID="{project_id}"
export HUAWEICLOUD_REGION="{REGION}"
export OBS_ENDPOINT="{OBS_ENDPOINT}"
export DEMO_BUCKET="{bucket}"
EOF
chmod 600 /opt/dockone-demo/huawei_env.sh
EOS
chmod +x /opt/dockone-demo/refresh_huawei_env.sh

cat >/opt/dockone-demo/run_cloud_notebook.sh <<'EOS'
#!/bin/bash
set -euo pipefail
/opt/dockone-demo/refresh_huawei_env.sh
source /opt/dockone-demo/huawei_env.sh
export PATH=/opt/dockone-demo/venv/bin:$PATH
cd /opt/dockone-demo/huawei-dli-hudi-demo
PYTHONUNBUFFERED=1 /opt/dockone-demo/venv/bin/python -u notebooks/run_notebook_auto.py --engine mrs --bucket "$DEMO_BUCKET" --transient-mrs-cluster --smoke-tables 1
EOS
chmod +x /opt/dockone-demo/run_cloud_notebook.sh

cat >/etc/systemd/system/dockone-jupyter.service <<'EOS'
[Unit]
Description=DockOne JupyterLab cloud notebook
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/dockone-demo/huawei-dli-hudi-demo
ExecStart=/opt/dockone-demo/venv/bin/jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --NotebookApp.token={jupyter_token} --notebook-dir=/opt/dockone-demo/huawei-dli-hudi-demo --allow-root
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOS

cat >/etc/systemd/system/dockone-run-onboot.service <<'EOS'
[Unit]
Description=Run DockOne MRS notebook smoke workflow once after boot
After=network-online.target dockone-jupyter.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/opt/dockone-demo/run_cloud_notebook.sh
StandardOutput=append:/var/log/dockone-notebook-run.log
StandardError=append:/var/log/dockone-notebook-run.log
EOS

cat >/etc/systemd/system/dockone-run-onboot.timer <<'EOS'
[Unit]
Description=Trigger DockOne MRS notebook smoke workflow once after boot

[Timer]
OnBootSec=15min
Unit=dockone-run-onboot.service

[Install]
WantedBy=timers.target
EOS

systemctl daemon-reload
systemctl enable --now dockone-jupyter.service
systemctl enable --now dockone-run-onboot.timer
"""
    return base64.b64encode(script.encode("utf-8")).decode("ascii")


def vpc_client():
    from huaweicloudsdkvpc.v2 import VpcClient
    from huaweicloudsdkvpc.v2.region.vpc_region import VpcRegion

    return VpcClient.new_builder().with_credentials(credentials()).with_region(VpcRegion.value_of(REGION)).build()


def ecs_client():
    from huaweicloudsdkecs.v2 import EcsClient
    from huaweicloudsdkecs.v2.region.ecs_region import EcsRegion

    return EcsClient.new_builder().with_credentials(credentials()).with_region(EcsRegion.value_of(REGION)).build()


def ensure_security_group(name: str, cidr: str, execute: bool) -> str:
    from huaweicloudsdkvpc.v2 import (
        CreateSecurityGroupOption,
        CreateSecurityGroupRequest,
        CreateSecurityGroupRequestBody,
        CreateSecurityGroupRuleOption,
        CreateSecurityGroupRuleRequest,
        CreateSecurityGroupRuleRequestBody,
        ListSecurityGroupsRequest,
    )

    client = vpc_client()
    groups = response_to_json(client.list_security_groups(ListSecurityGroupsRequest())).get("security_groups") or []
    for group in groups:
        if group.get("name") == name:
            sg_id = group["id"]
            break
    else:
        if not execute:
            return "dry-run-security-group-id"
        body = CreateSecurityGroupRequestBody(security_group=CreateSecurityGroupOption(name=name, vpc_id=VPC_ID))
        sg_id = response_to_json(client.create_security_group(CreateSecurityGroupRequest(body=body)))["security_group"]["id"]

    if execute and cidr != "0.0.0.0":
        existing = response_to_json(client.list_security_groups(ListSecurityGroupsRequest())).get("security_groups") or []
        current = next((g for g in existing if g.get("id") == sg_id), {})
        rules = current.get("security_group_rules") or []
        for port in [22, 8888]:
            exists = any(
                r.get("direction") == "ingress"
                and r.get("protocol") == "tcp"
                and r.get("port_range_min") == port
                and r.get("port_range_max") == port
                and r.get("remote_ip_prefix") == f"{cidr}/32"
                for r in rules
            )
            if not exists:
                rule = CreateSecurityGroupRuleOption(
                    security_group_id=sg_id,
                    direction="ingress",
                    ethertype="IPv4",
                    protocol="tcp",
                    port_range_min=port,
                    port_range_max=port,
                    remote_ip_prefix=f"{cidr}/32",
                    description=f"DockOne notebook access from {cidr}",
                )
                client.create_security_group_rule(CreateSecurityGroupRuleRequest(body=CreateSecurityGroupRuleRequestBody(security_group_rule=rule)))
    return sg_id


def find_existing_server(client: Any, name: str) -> dict | None:
    from huaweicloudsdkecs.v2 import ListServersDetailsRequest

    data = response_to_json(client.list_servers_details(ListServersDetailsRequest(name=name, limit=10)))
    servers = data.get("servers") or []
    return servers[0] if servers else None


def wait_ecs_job(client: Any, job_id: str, timeout_seconds: int = 900) -> dict:
    from huaweicloudsdkecs.v2 import ShowJobRequest

    deadline = time.time() + timeout_seconds
    last = {}
    while time.time() < deadline:
        last = response_to_json(client.show_job(ShowJobRequest(job_id=job_id)))
        status = str(last.get("status") or "").upper()
        print(json.dumps({"ecs_job_id": job_id, "status": status, "entities": last.get("entities")}, default=str))
        if status == "SUCCESS":
            return last
        if status in {"FAIL", "FAILED", "ERROR"}:
            raise RuntimeError(f"ECS job failed: {last}")
        time.sleep(20)
    raise RuntimeError(f"Timed out waiting for ECS job: {last}")


def create_server(args: argparse.Namespace, sg_id: str, user_data: str) -> dict:
    from huaweicloudsdkecs.v2 import (
        CreatePostPaidServersRequest,
        CreatePostPaidServersRequestBody,
        PostPaidServer,
        PostPaidServerEip,
        PostPaidServerEipBandwidth,
        PostPaidServerExtendParam,
        PostPaidServerNic,
        PostPaidServerPublicip,
        PostPaidServerRootVolume,
        PostPaidServerSecurityGroup,
        PostPaidServerTag,
    )

    client = ecs_client()
    existing = find_existing_server(client, args.name)
    if existing:
        return {"existing": True, "server": existing}
    if not args.execute:
        return {"dry_run": True, "name": args.name, "security_group_id": sg_id, "flavors": FLAVOR_CANDIDATES}

    last_error = None
    for flavor in FLAVOR_CANDIDATES:
        body = CreatePostPaidServersRequestBody(
            server=PostPaidServer(
                name=args.name,
                image_ref=IMAGE_ID,
                flavor_ref=flavor,
                availability_zone=AZ,
                vpcid=VPC_ID,
                nics=[PostPaidServerNic(subnet_id=SUBNET_ID)],
                security_groups=[PostPaidServerSecurityGroup(id=sg_id)],
                root_volume=PostPaidServerRootVolume(volumetype="SAS", size=40),
                publicip=PostPaidServerPublicip(
                    eip=PostPaidServerEip(
                        iptype="5_bgp",
                        bandwidth=PostPaidServerEipBandwidth(size=1, sharetype="PER", chargemode="traffic"),
                    ),
                ),
                extendparam=PostPaidServerExtendParam(charging_mode="0", enterprise_project_id="0"),
                metadata={"agency_name": args.agency_name},
                admin_pass=env("ECS_ADMIN_PASSWORD", required=True),
                user_data=user_data,
                count=1,
                server_tags=[PostPaidServerTag(key="demo", value="dockone-cloud-notebook")],
            )
        )
        try:
            resp = response_to_json(client.create_post_paid_servers(CreatePostPaidServersRequest(body=body)))
            job_id = resp.get("job_id")
            if job_id:
                wait_ecs_job(client, job_id)
            server = find_existing_server(client, args.name)
            return {"existing": False, "flavor": flavor, "create_response": resp, "server": server}
        except Exception as exc:
            last_error = {
                "flavor": flavor,
                "class": exc.__class__.__name__,
                "status_code": getattr(exc, "status_code", None),
                "error_code": getattr(exc, "error_code", None),
                "error_msg": getattr(exc, "error_msg", None),
            }
            print(json.dumps({"flavor_failed": last_error}, default=str))
    raise RuntimeError(f"All ECS flavor candidates failed: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy cloud-hosted JupyterLab notebook scheduler on Huawei Cloud ECS.")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--name", default=os.environ.get("CLOUD_NOTEBOOK_NAME", "dockone-notebook-scheduler"))
    parser.add_argument("--bucket", default=os.environ.get("DEMO_BUCKET", "docktest"))
    parser.add_argument("--agency-name", default=os.environ.get("ECS_AGENCY_NAME", "dockone_mrs_ecs_agency"))
    args = parser.parse_args()

    jupyter_token = env("JUPYTER_TOKEN", "dry-run-token", required=args.execute)
    obs_uri, signed_url = package_demo(args.bucket)
    current_ip = get_public_ip()
    sg_id = ensure_security_group(f"{args.name}-sg", current_ip, args.execute)
    user_data = make_cloud_init(signed_url, args.bucket, jupyter_token)
    result = create_server(args, sg_id, user_data)

    summary = {
        "region": REGION,
        "name": args.name,
        "bucket": args.bucket,
        "package": obs_uri,
        "security_group_id": sg_id,
        "allowed_ip": f"{current_ip}/32" if current_ip != "0.0.0.0" else None,
        "jupyter_port": 8888,
        "agency_name": args.agency_name,
        "result": result,
    }
    runtime = ROOT / "runtime"
    runtime.mkdir(exist_ok=True)
    (runtime / "cloud-notebook-ecs-deployment.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
