#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import secrets
import string
import time
import urllib.request
from pathlib import Path

import paramiko
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkecs.v2 import (
    BatchRebootServersRequest,
    BatchRebootServersRequestBody,
    BatchRebootSeversOption,
    EcsClient,
    ListServersDetailsRequest,
    ResetServerPasswordOption,
    ResetServerPasswordRequest,
    ResetServerPasswordRequestBody,
    ServerId,
    ShowResetPasswordFlagRequest,
)
from huaweicloudsdkvpc.v2 import (
    CreateSecurityGroupRuleOption,
    CreateSecurityGroupRuleRequest,
    CreateSecurityGroupRuleRequestBody,
    ListSecurityGroupRulesRequest,
    VpcClient,
)

from deploy_monitor import (
    ROOT,
    current_public_cidr,
    deploy_stack,
    ensure_ssh_key,
    public_ip,
    run,
    upload_tree,
    wait_https,
)

SERVER_ID = ""
SERVER_NAME = ""
EXPECTED_IP = ""
EXPECTED_VPC = ""
CLUSTER_ID = ""
CLUSTER_NAME = ""


def clients() -> tuple[EcsClient, VpcClient, str, str]:
    region = os.environ["HUAWEICLOUD_REGION"]
    project = os.environ["HUAWEICLOUD_PROJECT_ID"]
    credentials = BasicCredentials(
        os.environ["HUAWEICLOUD_ACCESS_KEY"],
        os.environ["HUAWEICLOUD_SECRET_KEY"],
        project,
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
    return ecs, vpc, region, project


def find_exact_server(ecs: EcsClient):
    response = ecs.list_servers_details(
        ListServersDetailsRequest(name=SERVER_NAME, limit=100)
    )
    server = next((item for item in response.servers or [] if item.id == SERVER_ID), None)
    if server is None:
        raise RuntimeError("The approved existing monitor ECS was not found.")
    if public_ip(server) != EXPECTED_IP:
        raise RuntimeError("The approved EIP is no longer attached to the expected ECS.")
    vpc_id = (server.metadata or {}).get("vpc_id", "")
    if vpc_id != EXPECTED_VPC:
        raise RuntimeError("The approved ECS is no longer in the MRS VPC.")
    return server


def ensure_ssh_rule(vpc: VpcClient, server) -> None:
    groups = server.security_groups or []
    if not groups:
        raise RuntimeError("The approved ECS has no security group.")
    group_id = groups[0].id
    remote = current_public_cidr()
    rules = (
        vpc.list_security_group_rules(
            ListSecurityGroupRulesRequest(security_group_id=group_id, limit=100)
        ).security_group_rules
        or []
    )
    exists = any(
        item.direction == "ingress"
        and item.protocol == "tcp"
        and int(item.port_range_min or 0) == 22
        and int(item.port_range_max or 0) == 22
        and item.remote_ip_prefix == remote
        for item in rules
    )
    if exists:
        return
    vpc.create_security_group_rule(
        CreateSecurityGroupRuleRequest(
            body=CreateSecurityGroupRuleRequestBody(
                security_group_rule=CreateSecurityGroupRuleOption(
                    security_group_id=group_id,
                    direction="ingress",
                    ethertype="IPv4",
                    protocol="tcp",
                    port_range_min=22,
                    port_range_max=22,
                    remote_ip_prefix=remote,
                    description="Temporary operator SSH for Grafana deployment",
                )
            )
        )
    )


def temporary_password() -> str:
    alphabet = string.ascii_letters + string.digits + "@%-_=+"
    while True:
        value = "".join(secrets.choice(alphabet) for _ in range(24))
        if (
            any(c.islower() for c in value)
            and any(c.isupper() for c in value)
            and any(c.isdigit() for c in value)
            and any(c in "@%-_=+" for c in value)
        ):
            return value


def reset_and_reboot(ecs: EcsClient, password: str) -> None:
    flag = ecs.show_reset_password_flag(
        ShowResetPasswordFlagRequest(server_id=SERVER_ID)
    ).resetpwd_flag
    if str(flag).lower() not in {"true", "1", "yes"}:
        raise RuntimeError("The existing ECS does not report one-click password reset support.")
    ecs.reset_server_password(
        ResetServerPasswordRequest(
            server_id=SERVER_ID,
            body=ResetServerPasswordRequestBody(
                reset_password=ResetServerPasswordOption(
                    new_password=password, is_check_password=True
                )
            ),
        )
    )
    ecs.batch_reboot_servers(
        BatchRebootServersRequest(
            body=BatchRebootServersRequestBody(
                reboot=BatchRebootSeversOption(
                    servers=[ServerId(id=SERVER_ID)], type="SOFT"
                )
            )
        )
    )


def password_connect(password: str, timeout: int = 600) -> paramiko.SSHClient:
    deadline = time.time() + timeout
    while time.time() < deadline:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                EXPECTED_IP,
                username="root",
                password=password,
                timeout=15,
                banner_timeout=15,
                auth_timeout=15,
                look_for_keys=False,
                allow_agent=False,
            )
            return client
        except Exception:
            client.close()
            time.sleep(10)
    raise TimeoutError("SSH password login did not become ready after the approved reboot.")


def harden_and_prepare(client: paramiko.SSHClient, public_key: str) -> None:
    sftp = client.open_sftp()
    try:
        try:
            sftp.stat("/root/.ssh")
        except FileNotFoundError:
            sftp.mkdir("/root/.ssh", mode=0o700)
        with sftp.file("/root/.ssh/authorized_keys", "a") as handle:
            handle.write(public_key + "\n")
        sftp.chmod("/root/.ssh", 0o700)
        sftp.chmod("/root/.ssh/authorized_keys", 0o600)
    finally:
        sftp.close()
    run(
        client,
        "mkdir -p /etc/ssh/sshd_config.d; "
        "printf 'PasswordAuthentication no\\nPermitRootLogin prohibit-password\\n' "
        ">/etc/ssh/sshd_config.d/90-bigdata-monitor.conf; "
        "sshd -t; systemctl restart sshd",
    )
    run(
        client,
        "dnf install -y openssh-server || yum install -y openssh-server; "
        "systemctl enable --now sshd; "
        "mkdir -p /opt/bigdata-monitor /etc/bigdata-monitor /srv/mrs-dump; "
        "chmod 0700 /etc/bigdata-monitor",
    )


def ensure_container_runtime(client: paramiko.SSHClient) -> None:
    # HCE 2.0 provides Docker Engine 18.09, whose CLI predates `docker compose`
    # plugin discovery. Install Docker and a pinned standalone Compose v2 binary
    # separately so a missing compose-plugin package cannot abort the transaction.
    run(
        client,
        "command -v docker >/dev/null 2>&1 || "
        "(dnf install -y docker || yum install -y docker); "
        "systemctl enable --now docker; "
        "if ! command -v docker-init >/dev/null 2>&1; then "
        "mkdir -p /tmp/docker-static-18.09.9; "
        "curl -fL --retry 3 "
        "https://download.docker.com/linux/static/stable/x86_64/"
        "docker-18.09.9.tgz -o /tmp/docker-18.09.9.tgz; "
        "tar -xzf /tmp/docker-18.09.9.tgz "
        "-C /tmp/docker-static-18.09.9 docker/docker-init; "
        "install -m 0755 /tmp/docker-static-18.09.9/docker/docker-init "
        "/usr/bin/docker-init; "
        "fi; "
        "if ! docker compose version >/dev/null 2>&1 && "
        "! docker-compose version >/dev/null 2>&1; then "
        "mkdir -p /usr/local/lib/docker/cli-plugins; "
        "curl -fL --retry 3 "
        "https://github.com/docker/compose/releases/download/v2.24.7/"
        "docker-compose-linux-x86_64 "
        "-o /usr/local/lib/docker/cli-plugins/docker-compose; "
        "install -m 0755 /usr/local/lib/docker/cli-plugins/docker-compose "
        "/usr/local/bin/docker-compose; "
        "fi; "
        "(docker compose version 2>/dev/null || docker-compose version)",
    )


def verify_key(key: paramiko.RSAKey) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        EXPECTED_IP,
        username="root",
        pkey=key,
        timeout=20,
        banner_timeout=20,
        auth_timeout=20,
    )
    return client


def try_existing_key(key: paramiko.RSAKey) -> paramiko.SSHClient | None:
    try:
        return verify_key(key)
    except Exception:
        return None


def main() -> int:
    global SERVER_ID, SERVER_NAME, EXPECTED_IP, EXPECTED_VPC, CLUSTER_ID, CLUSTER_NAME

    parser = argparse.ArgumentParser()
    parser.add_argument("--server-id", default=os.environ.get("MONITOR_SERVER_ID"))
    parser.add_argument("--server-name", default=os.environ.get("MONITOR_SERVER_NAME"))
    parser.add_argument("--public-ip", default=os.environ.get("MONITOR_PUBLIC_IP"))
    parser.add_argument("--vpc-id", default=os.environ.get("MONITOR_VPC_ID"))
    parser.add_argument("--cluster-id", default=os.environ.get("MRS_CLUSTER_ID"))
    parser.add_argument("--cluster-name", default=os.environ.get("MRS_CLUSTER_NAME"))
    parser.add_argument("--public-domain", default=os.environ.get("MONITOR_PUBLIC_DOMAIN"))
    parser.add_argument(
        "--allow-password-reset",
        action="store_true",
        help="Allow an ECS password reset and reboot only when SSH key authentication fails.",
    )
    args = parser.parse_args()
    required = {
        "--server-id / MONITOR_SERVER_ID": args.server_id,
        "--server-name / MONITOR_SERVER_NAME": args.server_name,
        "--public-ip / MONITOR_PUBLIC_IP": args.public_ip,
        "--vpc-id / MONITOR_VPC_ID": args.vpc_id,
        "--cluster-id / MRS_CLUSTER_ID": args.cluster_id,
        "--cluster-name / MRS_CLUSTER_NAME": args.cluster_name,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise SystemExit("Missing required deployment values: " + ", ".join(missing))
    SERVER_ID = args.server_id
    SERVER_NAME = args.server_name
    EXPECTED_IP = args.public_ip
    EXPECTED_VPC = args.vpc_id
    CLUSTER_ID = args.cluster_id
    CLUSTER_NAME = args.cluster_name

    ecs, vpc, region, project = clients()
    server = find_exact_server(ecs)
    ensure_ssh_rule(vpc, server)
    key, public_key = ensure_ssh_key()
    client = try_existing_key(key)
    if client is None:
        if not args.allow_password_reset:
            raise RuntimeError(
                "SSH key authentication failed. No password reset was performed. "
                "Verify the approved host/key, or re-run with --allow-password-reset "
                "only after accepting an ECS reboot."
            )
        password = temporary_password()
        reset_and_reboot(ecs, password)
        client = password_connect(password)
        try:
            harden_and_prepare(client, public_key)
        finally:
            client.close()
        client = verify_key(key)
    try:
        ensure_container_runtime(client)
        deploy_stack(client, EXPECTED_IP, region, project, CLUSTER_ID, CLUSTER_NAME)
        diagnostics = run(
            client,
            "cd /opt/bigdata-monitor && "
            "(docker compose ps --format json 2>/dev/null || "
            "docker-compose ps --format json); "
            "curl -fsS http://huawei-exporter:9108/health 2>/dev/null || true",
        )
    finally:
        client.close()
    domain = args.public_domain or f"{EXPECTED_IP.replace('.', '-')}.sslip.io"
    url = f"https://{domain}/"
    ok = wait_https(url, timeout=600)
    result = {
        "server_id": SERVER_ID,
        "server_name": SERVER_NAME,
        "public_ip": EXPECTED_IP,
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
        "diagnostics_tail": diagnostics[-3000:],
    }
    exports = ROOT / "exports"
    exports.mkdir(exist_ok=True)
    (exports / "deployment.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
