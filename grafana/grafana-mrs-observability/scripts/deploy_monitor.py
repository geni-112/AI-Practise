#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import io
import ipaddress
import json
import os
import posixpath
import stat
import time
import urllib.request
from pathlib import Path
from typing import Any

import paramiko
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
    ShowServerLimitsRequest,
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
DEFAULT_NAME = "grafana-mrs-observability"
DEFAULT_FLAVORS = ["c7n.large.2", "ac8.large.2", "c6.large.2"]
DEFAULT_VOLUMES = ["GPSSD", "SSD", "SAS"]


def csv_values(value: str | None, fallback: list[str] | None = None) -> list[str]:
    values = [item.strip() for item in (value or "").split(",") if item.strip()]
    return values or list(fallback or [])


def require(value: str | None, name: str) -> str:
    if not value:
        raise SystemExit(
            f"Required deployment value is missing: {name}. "
            "Pass the CLI option or set the documented environment variable."
        )
    return value


def env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise SystemExit(f"Required environment variable is missing: {name}")
    return value


def clients(region: str, project: str) -> tuple[EcsClient, VpcClient]:
    credentials = BasicCredentials(
        env("HUAWEICLOUD_ACCESS_KEY"), env("HUAWEICLOUD_SECRET_KEY"), project
    )
    ecs = (
        EcsClient.new_builder()
        .with_credentials(credentials)
        .with_endpoint(f"https://ecs.{region}.myhuaweicloud.com")
        .build()
    )
    vpc = (
        VpcClient.new_builder()
        .with_credentials(credentials)
        .with_endpoint(f"https://vpc.{region}.myhuaweicloud.com")
        .build()
    )
    return ecs, vpc


def current_public_cidr() -> str:
    with urllib.request.urlopen("https://api.ipify.org", timeout=10) as response:
        value = response.read().decode().strip()
    return f"{ipaddress.ip_address(value)}/32"


def ensure_quota(ecs: EcsClient) -> None:
    absolute = ecs.show_server_limits(ShowServerLimitsRequest()).absolute
    maximum = int(getattr(absolute, "max_total_instances", 0) or 0)
    used = int(getattr(absolute, "total_instances_used", 0) or 0)
    if maximum >= 0 and used >= maximum:
        raise RuntimeError(f"ECS instance quota is full: {used}/{maximum}")


def ensure_security_group(
    vpc: VpcClient, vpc_id: str, ssh_cidr: str, web_cidr: str
) -> str:
    ipaddress.ip_network(ssh_cidr, strict=False)
    ipaddress.ip_network(web_cidr, strict=False)
    name = "grafana-mrs-observability-sg"
    groups = vpc.list_security_groups(ListSecurityGroupsRequest(limit=100)).security_groups or []
    group = next((item for item in groups if item.name == name), None)
    if group is None:
        group = vpc.create_security_group(
            CreateSecurityGroupRequest(
                body=CreateSecurityGroupRequestBody(
                    security_group=CreateSecurityGroupOption(name=name, vpc_id=vpc_id)
                )
            )
        ).security_group
    rules = (
        vpc.list_security_group_rules(
            ListSecurityGroupRulesRequest(security_group_id=group.id, limit=100)
        ).security_group_rules
        or []
    )
    desired = [
        (22, ssh_cidr, "Operator SSH"),
        (80, web_cidr, "HTTPS bootstrap"),
        (443, web_cidr, "Grafana HTTPS"),
    ]
    for port, remote, description in desired:
        exists = any(
            item.direction == "ingress"
            and item.protocol == "tcp"
            and int(item.port_range_min or 0) == port
            and int(item.port_range_max or 0) == port
            and item.remote_ip_prefix == remote
            for item in rules
        )
        if exists:
            continue
        vpc.create_security_group_rule(
            CreateSecurityGroupRuleRequest(
                body=CreateSecurityGroupRuleRequestBody(
                    security_group_rule=CreateSecurityGroupRuleOption(
                        security_group_id=group.id,
                        direction="ingress",
                        ethertype="IPv4",
                        protocol="tcp",
                        port_range_min=port,
                        port_range_max=port,
                        remote_ip_prefix=remote,
                        description=description,
                    )
                )
            )
        )
    return group.id


def key_paths() -> tuple[Path, Path]:
    directory = Path(os.environ["LOCALAPPDATA"]) / "Codex" / "huawei-mrs-observability"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "deploy_rsa", directory / "deploy_rsa.pub"


def ensure_ssh_key() -> tuple[paramiko.RSAKey, str]:
    private_path, public_path = key_paths()
    if private_path.exists():
        key = paramiko.RSAKey.from_private_key_file(str(private_path))
    else:
        key = paramiko.RSAKey.generate(3072)
        key.write_private_key_file(str(private_path))
        os.chmod(private_path, stat.S_IREAD | stat.S_IWRITE)
    public = f"{key.get_name()} {key.get_base64()} codex-mrs-observability"
    public_path.write_text(public + "\n", encoding="ascii")
    return key, public


def cloud_init(public_key: str) -> str:
    content = f"""#cloud-config
users:
  - name: root
    ssh_authorized_keys:
      - {public_key}
ssh_pwauth: false
write_files:
  - path: /etc/sysctl.d/99-bigdata-monitor.conf
    permissions: '0644'
    content: |
      vm.max_map_count=262144
runcmd:
  - mkdir -p /opt/bigdata-monitor /etc/bigdata-monitor /srv/mrs-dump
  - chmod 0700 /etc/bigdata-monitor
  - dnf install -y docker docker-compose-plugin openssh-server || yum install -y docker docker-compose-plugin openssh-server
  - systemctl enable --now docker sshd
  - firewall-cmd --permanent --add-service=http || true
  - firewall-cmd --permanent --add-service=https || true
  - firewall-cmd --reload || true
"""
    return base64.b64encode(content.encode()).decode()


def find_server(ecs: EcsClient, name: str) -> Any | None:
    response = ecs.list_servers_details(ListServersDetailsRequest(name=name, limit=100))
    return next(
        (
            server
            for server in response.servers or []
            if server.name == name and server.status != "DELETED"
        ),
        None,
    )


def public_ip(server: Any) -> str:
    for rows in (server.addresses or {}).values():
        for item in rows or []:
            row = item.to_dict() if hasattr(item, "to_dict") else item
            if isinstance(row, str):
                row = json.loads(row)
            ip_type = row.get("OS-EXT-IPS:type") or row.get("os_ext_ip_stype")
            if ip_type == "floating":
                return str(row.get("addr", ""))
    return ""


def wait_job(ecs: EcsClient, job_id: str, timeout: int = 900) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = str(ecs.show_job(ShowJobRequest(job_id=job_id)).status or "").upper()
        if status in {"SUCCESS", "SUCCEEDED"}:
            return
        if status in {"FAIL", "FAILED", "ERROR"}:
            raise RuntimeError(f"ECS create job failed: {job_id}")
        time.sleep(10)
    raise TimeoutError(f"ECS create job timed out: {job_id}")


def create_server(
    ecs: EcsClient,
    name: str,
    vpc_id: str,
    subnet_id: str,
    security_group_id: str,
    region: str,
    public_key: str,
    image_id: str,
    availability_zones: list[str],
    flavors: list[str],
    volume_types: list[str],
) -> None:
    last_error: Exception | None = None
    for az in availability_zones:
        for flavor in flavors:
            for volume in volume_types:
                server = PostPaidServer(
                    name=name,
                    image_ref=image_id,
                    flavor_ref=flavor,
                    availability_zone=az,
                    vpcid=vpc_id,
                    nics=[PostPaidServerNic(subnet_id=subnet_id)],
                    security_groups=[PostPaidServerSecurityGroup(id=security_group_id)],
                    root_volume=PostPaidServerRootVolume(volumetype=volume, size=80),
                    publicip=PostPaidServerPublicip(
                        delete_on_termination=True,
                        eip=PostPaidServerEip(
                            iptype="5_bgp",
                            bandwidth=PostPaidServerEipBandwidth(
                                size=5, sharetype="PER", chargemode="traffic"
                            ),
                        ),
                    ),
                    count=1,
                    user_data=cloud_init(public_key),
                    extendparam=PostPaidServerExtendParam(
                        charging_mode="postPaid", region_id=region
                    ),
                    description="Grafana OSS observability for Huawei Cloud MRS and big-data services",
                )
                try:
                    result = ecs.create_post_paid_servers(
                        CreatePostPaidServersRequest(
                            body=CreatePostPaidServersRequestBody(server=server)
                        )
                    )
                    wait_job(ecs, result.job_id)
                    return
                except exceptions.ClientRequestException as exc:
                    last_error = exc
                    if any(text in str(exc).lower() for text in ("quota", "balance", "authentication")):
                        raise
    raise RuntimeError(f"No ECS candidate succeeded. Last error: {last_error}")


def wait_server(ecs: EcsClient, name: str, timeout: int = 600) -> Any:
    deadline = time.time() + timeout
    while time.time() < deadline:
        server = find_server(ecs, name)
        if server and server.status == "ACTIVE" and public_ip(server):
            return server
        time.sleep(10)
    raise TimeoutError(f"ECS did not become ready: {name}")


def connect(host: str, key: paramiko.RSAKey, timeout: int = 600) -> paramiko.SSHClient:
    deadline = time.time() + timeout
    while time.time() < deadline:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                host,
                username="root",
                pkey=key,
                timeout=15,
                banner_timeout=15,
                auth_timeout=15,
            )
            return client
        except Exception:
            client.close()
            time.sleep(10)
    raise TimeoutError(f"SSH did not become ready: {host}")


def mkdirs(sftp: paramiko.SFTPClient, remote_path: str) -> None:
    parts = remote_path.strip("/").split("/")
    current = ""
    for part in parts:
        current += "/" + part
        try:
            sftp.stat(current)
        except FileNotFoundError:
            sftp.mkdir(current)


def upload_tree(sftp: paramiko.SFTPClient, source: Path, destination: str) -> None:
    for path in source.rglob("*"):
        if any(
            part in {".git", "exports", "logs", "__pycache__"}
            for part in path.parts
        ):
            continue
        if path.name in {".env", "huawei.env"} or path.suffix == ".pyc":
            continue
        relative = path.relative_to(source).as_posix()
        remote = posixpath.join(destination, relative)
        if path.is_dir():
            mkdirs(sftp, remote)
        else:
            mkdirs(sftp, posixpath.dirname(remote))
            sftp.put(str(path), remote)


def write_remote(sftp: paramiko.SFTPClient, path: str, text: str, mode: int) -> None:
    mkdirs(sftp, posixpath.dirname(path))
    with sftp.file(path, "w") as handle:
        handle.write(text)
    sftp.chmod(path, mode)


def run(client: paramiko.SSHClient, command: str, stdin_text: str = "") -> str:
    stdin, stdout, stderr = client.exec_command(command, timeout=900)
    if stdin_text:
        stdin.write(stdin_text)
        stdin.flush()
        stdin.channel.shutdown_write()
    code = stdout.channel.recv_exit_status()
    output = stdout.read().decode(errors="replace")
    error = stderr.read().decode(errors="replace")
    if code:
        raise RuntimeError(f"Remote command failed ({code}): {error[-2000:]}")
    return output


def deploy_stack(
    client: paramiko.SSHClient,
    host: str,
    region: str,
    project: str,
    cluster_id: str,
    cluster_name: str,
) -> None:
    grafana_password = env("GRAFANA_ADMIN_PASSWORD")
    dump_password = env("MRS_DUMP_PASSWORD")
    sftp = client.open_sftp()
    upload_tree(sftp, ROOT, "/opt/bigdata-monitor")
    domain = f"{host.replace('.', '-')}.sslip.io"
    compose_env = (
        f"PUBLIC_DOMAIN={domain}\n"
        "GRAFANA_ADMIN_USER=admin\n"
        f"GRAFANA_ADMIN_PASSWORD={grafana_password}\n"
    )
    huawei_env = (
        f"HUAWEICLOUD_ACCESS_KEY={env('HUAWEICLOUD_ACCESS_KEY')}\n"
        f"HUAWEICLOUD_SECRET_KEY={env('HUAWEICLOUD_SECRET_KEY')}\n"
        f"HUAWEICLOUD_REGION={region}\n"
        f"HUAWEICLOUD_PROJECT_ID={project}\n"
        f"MRS_CLUSTER_ID={cluster_id}\n"
        f"MRS_CLUSTER_NAME={cluster_name}\n"
    )
    write_remote(sftp, "/opt/bigdata-monitor/.env", compose_env, 0o600)
    write_remote(sftp, "/etc/bigdata-monitor/huawei.env", huawei_env, 0o600)
    sftp.close()
    run(
        client,
        "id mrsdump >/dev/null 2>&1 || useradd --create-home --home-dir /srv/mrs-dump --shell /bin/bash mrsdump; "
        "chown -R mrsdump:mrsdump /srv/mrs-dump; chmod 0750 /srv/mrs-dump; chpasswd",
        f"mrsdump:{dump_password}\n",
    )
    run(
        client,
        "cd /opt/bigdata-monitor && "
        "if docker compose version >/dev/null 2>&1; then "
        "docker compose pull && docker compose build --pull && docker compose up -d; "
        "else "
        "docker-compose pull && docker-compose build --pull && docker-compose up -d; "
        "fi",
    )


def wait_https(url: str, timeout: int = 600) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                if response.status in {200, 302}:
                    return True
        except Exception:
            pass
        time.sleep(10)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default=os.environ.get("HUAWEICLOUD_REGION"))
    parser.add_argument("--project-id", default=os.environ.get("HUAWEICLOUD_PROJECT_ID"))
    parser.add_argument("--vpc-id", default=os.environ.get("MONITOR_VPC_ID"))
    parser.add_argument("--subnet-id", default=os.environ.get("MONITOR_SUBNET_ID"))
    parser.add_argument("--cluster-id", default=os.environ.get("MRS_CLUSTER_ID"))
    parser.add_argument("--cluster-name", default=os.environ.get("MRS_CLUSTER_NAME"))
    parser.add_argument("--image-id", default=os.environ.get("MONITOR_IMAGE_ID"))
    parser.add_argument(
        "--availability-zones", default=os.environ.get("MONITOR_AVAILABILITY_ZONES")
    )
    parser.add_argument("--flavors", default=os.environ.get("MONITOR_FLAVORS"))
    parser.add_argument("--volume-types", default=os.environ.get("MONITOR_VOLUME_TYPES"))
    parser.add_argument("--web-cidr", default=os.environ.get("MONITOR_WEB_CIDR"))
    parser.add_argument("--name", default=DEFAULT_NAME)
    parser.add_argument(
        "--confirm-create",
        action="store_true",
        help="Explicitly allow creation of a pay-per-use ECS when the named host is absent.",
    )
    args = parser.parse_args()

    region = require(args.region, "--region / HUAWEICLOUD_REGION")
    project_id = require(args.project_id, "--project-id / HUAWEICLOUD_PROJECT_ID")
    vpc_id = require(args.vpc_id, "--vpc-id / MONITOR_VPC_ID")
    subnet_id = require(args.subnet_id, "--subnet-id / MONITOR_SUBNET_ID")
    cluster_id = require(args.cluster_id, "--cluster-id / MRS_CLUSTER_ID")
    cluster_name = require(args.cluster_name, "--cluster-name / MRS_CLUSTER_NAME")
    image_id = require(args.image_id, "--image-id / MONITOR_IMAGE_ID")
    availability_zones = csv_values(args.availability_zones)
    if not availability_zones:
        raise SystemExit(
            "At least one availability zone is required via --availability-zones "
            "or MONITOR_AVAILABILITY_ZONES."
        )
    flavors = csv_values(args.flavors, DEFAULT_FLAVORS)
    volume_types = csv_values(args.volume_types, DEFAULT_VOLUMES)
    web_cidr = require(args.web_cidr, "--web-cidr / MONITOR_WEB_CIDR")

    ecs, vpc = clients(region, project_id)
    existing = find_server(ecs, args.name)
    key, public_key = ensure_ssh_key()
    if existing is None:
        if not args.confirm_create:
            raise SystemExit(
                "The monitoring ECS does not exist. Re-run with --confirm-create "
                "after confirming quota, image, flavor, network, and pay-per-use cost."
            )
        ensure_quota(ecs)
        sg_id = ensure_security_group(vpc, vpc_id, current_public_cidr(), web_cidr)
        create_server(
            ecs,
            args.name,
            vpc_id,
            subnet_id,
            sg_id,
            region,
            public_key,
            image_id,
            availability_zones,
            flavors,
            volume_types,
        )
    server = wait_server(ecs, args.name)
    host = public_ip(server)
    client = connect(host, key)
    try:
        deploy_stack(
            client,
            host,
            region,
            project_id,
            cluster_id,
            cluster_name,
        )
    finally:
        client.close()
    domain = f"{host.replace('.', '-')}.sslip.io"
    url = f"https://{domain}/"
    ok = wait_https(url)
    result = {
        "server_id": server.id,
        "server_name": args.name,
        "public_ip": host,
        "private_vpc_id": vpc_id,
        "grafana_url": url,
        "https_ok": ok,
        "mrs_sftp_host": next(
            (
                item.addr
                for rows in (server.addresses or {}).values()
                for item in rows
                if getattr(item, "os_ext_ip_stype", "") == "fixed"
            ),
            "",
        ),
        "mrs_sftp_port": 22,
        "mrs_sftp_user": "mrsdump",
        "mrs_sftp_path": "/srv/mrs-dump",
    }
    EXPORTS.mkdir(exist_ok=True)
    (EXPORTS / "deployment.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
