#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkcore.exceptions import exceptions
from huaweicloudsdkecs.v2 import (
    CreatePostPaidServersRequest,
    CreatePostPaidServersRequestBody,
    EcsClient,
    ListServersDetailsRequest,
    PostPaidServer,
    PostPaidServerEip,
    PostPaidServerEipBandwidth,
    PostPaidServerExtendParam,
    PostPaidServerNic,
    PostPaidServerPublicip,
    PostPaidServerRootVolume,
    PostPaidServerSecurityGroup,
    ShowJobRequest,
)
from huaweicloudsdkvpc.v2 import (
    CreateSecurityGroupOption,
    CreateSecurityGroupRequest,
    CreateSecurityGroupRequestBody,
    CreateSecurityGroupRuleOption,
    CreateSecurityGroupRuleRequest,
    CreateSecurityGroupRuleRequestBody,
    ListSecurityGroupRulesRequest,
    ListSecurityGroupsRequest,
    VpcClient,
)

ROOT = Path(__file__).resolve().parents[1]
EXPORTS = ROOT / "exports"

DEFAULT_REGION = "la-north-2"
DEFAULT_PROJECT_ID = ""
DEFAULT_VPC_ID = ""
DEFAULT_SUBNET_ID = ""
DEFAULT_BUCKET = ""
DEFAULT_NAME = "realtime-monitor-web"

IMAGE_CANDIDATES = [
    "aeb3f35e-2852-4c6f-8085-3d0419d58483",  # Huawei Cloud EulerOS 2.0 Standard 64 bit
    "55ef99a3-0cad-48f6-b6ee-386547327351",  # CentOS 7.9 64bit
]
FLAVOR_CANDIDATES = ["ac7.large.2", "ac8.large.2", "c6.large.2", "c6ne.large.2", "ac9.large.2"]
AZ_CANDIDATES = ["la-north-2a", "la-north-2b", "la-north-2c"]
ROOT_VOLUME_TYPES = ["SAS", "SSD", "GPSSD"]
SITE_FILES = [
    "index.html",
    "app.js",
    "styles.css",
    "data/status.json",
    "assets/obs.png",
    "assets/mapreduce.png",
    "assets/dataarts.png",
    "assets/dws.png",
]


def env(name: str, fallback: str = "") -> str:
    return os.environ.get(name, fallback)


def clients(region: str, project_id: str) -> tuple[EcsClient, VpcClient]:
    ak = env("HUAWEICLOUD_ACCESS_KEY")
    sk = env("HUAWEICLOUD_SECRET_KEY")
    if not (ak and sk and project_id):
        raise SystemExit("HUAWEICLOUD_ACCESS_KEY, HUAWEICLOUD_SECRET_KEY, and HUAWEICLOUD_PROJECT_ID are required.")
    credentials = BasicCredentials(ak, sk, project_id)
    ecs = EcsClient.new_builder().with_credentials(credentials).with_endpoint(f"https://ecs.{region}.myhuaweicloud.com").build()
    vpc = VpcClient.new_builder().with_credentials(credentials).with_endpoint(f"https://vpc.{region}.myhuaweicloud.com").build()
    return ecs, vpc


def server_public_ip(server: Any) -> str:
    addresses = getattr(server, "addresses", None) or {}
    for rows in addresses.values():
        for row in rows or []:
            row_data = row.to_dict() if hasattr(row, "to_dict") else row
            if not isinstance(row_data, dict):
                continue
            ip_type = row_data.get("OS-EXT-IPS:type") or row_data.get("os_ext_ip_stype")
            if ip_type == "floating" and row_data.get("addr"):
                return str(row_data["addr"])
    for rows in addresses.values():
        for row in rows or []:
            row_data = row.to_dict() if hasattr(row, "to_dict") else row
            if not isinstance(row_data, dict):
                continue
            if row_data.get("addr") and str(row_data.get("version")) == "4":
                return str(row_data["addr"])
    return ""


def find_server(ecs: EcsClient, name: str) -> Any | None:
    response = ecs.list_servers_details(ListServersDetailsRequest(limit=100))
    for server in response.servers or []:
        if getattr(server, "name", "") == name and getattr(server, "status", "") != "DELETED":
            return server
    return None


def ensure_security_group(vpc: VpcClient, vpc_id: str, name: str) -> str:
    response = vpc.list_security_groups(ListSecurityGroupsRequest(limit=100))
    for group in response.security_groups or []:
        if getattr(group, "name", "") == name:
            sg_id = group.id
            break
    else:
        created = vpc.create_security_group(
            CreateSecurityGroupRequest(
                body=CreateSecurityGroupRequestBody(
                    security_group=CreateSecurityGroupOption(name=name, vpc_id=vpc_id)
                )
            )
        )
        sg_id = created.security_group.id

    rules = vpc.list_security_group_rules(ListSecurityGroupRulesRequest(security_group_id=sg_id, limit=100)).security_group_rules or []
    for port in (80, 443):
        has_rule = False
        for rule in rules:
            if (
                getattr(rule, "direction", "") == "ingress"
                and getattr(rule, "protocol", "") == "tcp"
                and int(getattr(rule, "port_range_min", 0) or 0) == port
                and int(getattr(rule, "port_range_max", 0) or 0) == port
                and getattr(rule, "remote_ip_prefix", "") == "0.0.0.0/0"
            ):
                has_rule = True
                break
        if has_rule:
            continue
        try:
            vpc.create_security_group_rule(
                CreateSecurityGroupRuleRequest(
                    body=CreateSecurityGroupRuleRequestBody(
                        security_group_rule=CreateSecurityGroupRuleOption(
                            security_group_id=sg_id,
                            direction="ingress",
                            ethertype="IPv4",
                            protocol="tcp",
                            port_range_min=port,
                            port_range_max=port,
                            remote_ip_prefix="0.0.0.0/0",
                            description=f"SAT Mexico monitor TCP/{port}",
                        )
                    )
                )
            )
        except exceptions.ClientRequestException as exc:
            if "duplicate" not in str(exc).lower() and "exists" not in str(exc).lower():
                raise
    return sg_id


def sslip_domain(public_ip: str) -> str:
    return f"{public_ip.replace('.', '-')}.sslip.io" if public_ip else ""


def cloud_init(bucket: str, region: str) -> str:
    base = f"https://{bucket}.obs.{region}.myhuaweicloud.com/"
    obs_host = f"{bucket}.obs.{region}.myhuaweicloud.com"
    files_json = json.dumps(SITE_FILES)
    bootstrap = f"""#!/usr/bin/env python3
import os
import time
import urllib.request

BASE = {base!r}
FILES = {files_json}
ROOT = "/opt/sat-monitor"

for rel in FILES:
    target = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    last_error = None
    for _ in range(8):
        try:
            urllib.request.urlretrieve(BASE + rel, target)
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            time.sleep(5)
    if last_error:
        raise last_error
"""
    caddy_setup = f"""#!/bin/bash
set -euo pipefail

mkdir -p /opt/sat-monitor /etc/caddy /var/lib/caddy /var/log/caddy /usr/local/bin
if [ ! -x /usr/local/bin/caddy ]; then
  curl -fsSL --retry 8 --retry-delay 5 --connect-timeout 10 \
    'https://caddyserver.com/api/download?os=linux&arch=amd64' \
    -o /usr/local/bin/caddy
  chmod 0755 /usr/local/bin/caddy
fi

PUBLIC_IP=""
for attempt in $(seq 1 60); do
  PUBLIC_IP=$(curl -fsS --max-time 5 https://api.ipify.org || true)
  if echo "$PUBLIC_IP" | grep -Eq '^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$'; then
    break
  fi
  PUBLIC_IP=$(curl -fsS --max-time 5 http://169.254.169.254/latest/meta-data/public-ipv4 || true)
  if echo "$PUBLIC_IP" | grep -Eq '^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$'; then
    break
  fi
  sleep 5
done
if ! echo "$PUBLIC_IP" | grep -Eq '^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$'; then
  echo "Could not determine public IP for sslip.io domain" >&2
  exit 1
fi
DOMAIN="$(echo "$PUBLIC_IP" | tr . -).sslip.io"
echo "$DOMAIN" >/opt/sat-monitor/domain.txt

cat >/etc/caddy/Caddyfile <<'EOF'
__DOMAIN__ {{
  encode gzip
  root * /opt/sat-monitor

  header {{
    Cache-Control "no-store"
    X-Content-Type-Options "nosniff"
    X-Frame-Options "DENY"
    Referrer-Policy "no-referrer"
    Content-Security-Policy "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
  }}

  handle /api/refresh {{
    respond "" 204
  }}

  handle /api/status {{
    rewrite * /data/status.json
    reverse_proxy https://__OBS_HOST__ {{
      header_up Host __OBS_HOST__
      header_down -Content-Disposition
    }}
  }}

  handle /data/status.json {{
    reverse_proxy https://__OBS_HOST__ {{
      header_up Host __OBS_HOST__
      header_down -Content-Disposition
    }}
  }}

  handle / {{
    rewrite * /index.html
    reverse_proxy https://__OBS_HOST__ {{
      header_up Host __OBS_HOST__
      header_down -Content-Disposition
    }}
  }}

  handle {{
    reverse_proxy https://__OBS_HOST__ {{
      header_up Host __OBS_HOST__
      header_down -Content-Disposition
    }}
  }}
}}
EOF
sed -i "s/__DOMAIN__/$DOMAIN/g; s/__OBS_HOST__/{obs_host}/g" /etc/caddy/Caddyfile
"""
    service = """[Unit]
Description=SAT Mexico realtime monitor static web server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/sat-monitor
ExecStart=/usr/local/bin/caddy run --environ --config /etc/caddy/Caddyfile --adapter caddyfile
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
    payload = f"""#cloud-config
write_files:
  - path: /usr/local/bin/sat-monitor-bootstrap.py
    permissions: '0755'
    content: |
{indent(bootstrap, 6)}
  - path: /etc/systemd/system/sat-monitor.service
    permissions: '0644'
    content: |
{indent(service, 6)}
  - path: /usr/local/bin/setup-sat-monitor-caddy.sh
    permissions: '0755'
    content: |
{indent(caddy_setup, 6)}
runcmd:
  - mkdir -p /opt/sat-monitor
  - python3 /usr/local/bin/sat-monitor-bootstrap.py || python /usr/local/bin/sat-monitor-bootstrap.py
  - bash /usr/local/bin/setup-sat-monitor-caddy.sh
  - systemctl stop firewalld || true
  - systemctl disable firewalld || true
  - systemctl daemon-reload
  - systemctl enable --now sat-monitor.service
"""
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


def indent(text: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line if line else prefix for line in text.splitlines())


def wait_job(ecs: EcsClient, job_id: str, timeout_seconds: int = 900) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        response = ecs.show_job(ShowJobRequest(job_id=job_id))
        status = str(getattr(response, "status", "") or "").upper()
        if status in {"SUCCESS", "SUCCEEDED"}:
            return
        if status in {"FAIL", "FAILED", "ERROR"}:
            raise RuntimeError(f"ECS job {job_id} failed: {response}")
        time.sleep(10)
    raise TimeoutError(f"Timed out waiting for ECS job {job_id}.")


def wait_http(url: str, timeout_seconds: int = 420) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=8) as response:
                body = response.read(20000).decode("utf-8", errors="replace")
                if response.status == 200 and "SAT Mexico Realtime Monitor" in body:
                    return True
        except Exception:
            pass
        time.sleep(10)
    return False


def create_server(
    ecs: EcsClient,
    name: str,
    vpc_id: str,
    subnet_id: str,
    security_group_id: str,
    bucket: str,
    region: str,
) -> str:
    last_error: Exception | None = None
    for az in AZ_CANDIDATES:
        for flavor in FLAVOR_CANDIDATES:
            for image in IMAGE_CANDIDATES:
                for volume_type in ROOT_VOLUME_TYPES:
                    server = PostPaidServer(
                        name=name,
                        image_ref=image,
                        flavor_ref=flavor,
                        availability_zone=az,
                        vpcid=vpc_id,
                        nics=[PostPaidServerNic(subnet_id=subnet_id)],
                        security_groups=[PostPaidServerSecurityGroup(id=security_group_id)],
                        root_volume=PostPaidServerRootVolume(volumetype=volume_type, size=40),
                        publicip=PostPaidServerPublicip(
                            delete_on_termination=True,
                            eip=PostPaidServerEip(
                                iptype="5_bgp",
                                bandwidth=PostPaidServerEipBandwidth(size=5, sharetype="PER", chargemode="traffic"),
                            ),
                        ),
                        count=1,
                        user_data=cloud_init(bucket, region),
                        extendparam=PostPaidServerExtendParam(charging_mode="postPaid", region_id=region),
                        description="SAT Mexico realtime monitor web endpoint deployed by Codex",
                    )
                    try:
                        response = ecs.create_post_paid_servers(
                            CreatePostPaidServersRequest(body=CreatePostPaidServersRequestBody(server=server))
                        )
                        job_id = getattr(response, "job_id", "")
                        if not job_id:
                            raise RuntimeError(f"ECS create response did not include job_id: {response}")
                        print(f"ECS create submitted: az={az} flavor={flavor} image={image} volume={volume_type} job={job_id}")
                        return job_id
                    except exceptions.ClientRequestException as exc:
                        last_error = exc
                        message = str(exc)
                        if any(token in message.lower() for token in ("quota", "balance", "real-name", "authentication")):
                            raise
                    except Exception as exc:
                        last_error = exc
    raise RuntimeError(f"All ECS create candidates failed. Last error: {last_error}")


def result_payload(region: str, name: str, server: Any, security_group_id: str, http_ok: bool) -> dict[str, Any]:
    public_ip = server_public_ip(server)
    domain = sslip_domain(public_ip)
    return {
        "region": region,
        "server_name": name,
        "server_id": getattr(server, "id", ""),
        "server_status": getattr(server, "status", ""),
        "security_group_id": security_group_id,
        "public_ip": public_ip,
        "domain": domain,
        "website_url": f"https://{domain}/" if domain else "",
        "http_ok": http_ok,
        "refresh_seconds": 5,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy a Huawei realtime monitor to a small ECS web endpoint.")
    parser.add_argument("--region", default=env("HUAWEICLOUD_REGION", DEFAULT_REGION))
    parser.add_argument("--project-id", default=env("HUAWEICLOUD_PROJECT_ID", DEFAULT_PROJECT_ID))
    parser.add_argument("--vpc-id", default=DEFAULT_VPC_ID)
    parser.add_argument("--subnet-id", default=DEFAULT_SUBNET_ID)
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--name", default=DEFAULT_NAME)
    args = parser.parse_args()

    missing = [
        name
        for name, value in {
            "--project-id or HUAWEICLOUD_PROJECT_ID": args.project_id,
            "--vpc-id": args.vpc_id,
            "--subnet-id": args.subnet_id,
            "--bucket": args.bucket,
        }.items()
        if not value
    ]
    if missing:
        raise SystemExit("Missing required deployment inputs: " + ", ".join(missing))

    ecs, vpc = clients(args.region, args.project_id)
    sg_id = ensure_security_group(vpc, args.vpc_id, f"{args.name}-sg")

    server = find_server(ecs, args.name)
    if server is None:
        job_id = create_server(ecs, args.name, args.vpc_id, args.subnet_id, sg_id, args.bucket, args.region)
        wait_job(ecs, job_id)
        for _ in range(30):
            server = find_server(ecs, args.name)
            if server and getattr(server, "status", "") == "ACTIVE" and server_public_ip(server):
                break
            time.sleep(10)

    if server is None:
        raise RuntimeError(f"Could not find ECS server {args.name} after deployment.")
    public_ip = server_public_ip(server)
    if not public_ip:
        raise RuntimeError(f"ECS server {args.name} does not have a public IP yet.")

    url = f"https://{sslip_domain(public_ip)}/"
    http_ok = wait_http(url)
    result = result_payload(args.region, args.name, server, sg_id, http_ok)
    EXPORTS.mkdir(parents=True, exist_ok=True)
    out = EXPORTS / f"ecs_monitor_web_{args.region}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if http_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
