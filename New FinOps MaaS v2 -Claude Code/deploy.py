#!/usr/bin/env python3
"""
LiteLLM + SearXNG + Claude-GLM 全自动部署脚本
读取 credential.skill → 置备/复用 ECS → SSH 安装全栈
"""
import json, os, sys, time, subprocess, secrets, stat, textwrap, socket
from pathlib import Path

# ── stdout UTF-8 ──────────────────────────────────────────────────────────────
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent
CRED = ROOT / "credential.skill"
DEPLOY_STATE = ROOT / "deploy_state.json"

# ── 读取凭证 ──────────────────────────────────────────────────────────────────
with open(CRED, encoding="utf-8") as f:
    C = json.load(f)

AK          = C["HUAWEI_AK"]
SK          = C["HUAWEI_SK"]
PROJECT     = C["HUAWEI_PROJECT"]
REGION      = C.get("HUAWEI_REGION", "la-south-2")
MAAS_BASE   = C["HUAWEI_MAAS_API_BASE"]
MAAS_KEY    = C["HUAWEI_MAAS_API_KEY"]
ECS_IP      = C.get("ECS_PUBLIC_IP", "").strip()
SSH_KEY     = C.get("SSH_KEY", "").strip()
SSH_USER    = C.get("SSH_USER", "root").strip() or "root"
LPORT       = C.get("LITELLM_PORT", "4000")
MPORT       = C.get("MCP_PORT", "8788")

PREFIX = "litellm-gw"

def banner(msg):
    print(f"\n{'='*60}\n  {msg}\n{'='*60}")

def step(n, msg):
    print(f"\n[Step {n}] {msg}")

def ok(msg):
    print(f"  ✓ {msg}")

def warn(msg):
    print(f"  ⚠ {msg}")

def err(msg):
    print(f"  ✗ {msg}", file=sys.stderr)

# ── 华为云 SDK 客户端 ─────────────────────────────────────────────────────────
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkcore.exceptions.exceptions import ClientRequestException

from huaweicloudsdkecs.v2 import EcsClient
from huaweicloudsdkecs.v2.region.ecs_region import EcsRegion
from huaweicloudsdkecs.v2 import (
    CreateServersRequest, CreateServersRequestBody,
    PostPaidServer, PostPaidServerRootVolume, PostPaidServerNic,
    PostPaidServerPublicip, PostPaidServerEip, PostPaidServerEipBandwidth,
    PostPaidServerSecurityGroup, ShowServerRequest,
)

from huaweicloudsdkvpc.v2 import VpcClient
from huaweicloudsdkvpc.v2.region.vpc_region import VpcRegion
from huaweicloudsdkvpc.v2 import (
    ListVpcsRequest, ListSubnetsRequest,
    CreateSecurityGroupRequest, CreateSecurityGroupRequestBody,
    CreateSecurityGroupOption,
    CreateSecurityGroupRuleRequest, CreateSecurityGroupRuleRequestBody,
    CreateSecurityGroupRuleOption,
    ListSecurityGroupsRequest,
)

from huaweicloudsdkims.v2 import ImsClient
from huaweicloudsdkims.v2.region.ims_region import ImsRegion
from huaweicloudsdkims.v2 import ListImagesRequest

creds = BasicCredentials(AK, SK, PROJECT)

ecs_client = EcsClient.new_builder() \
    .with_credentials(creds) \
    .with_region(EcsRegion.value_of(REGION)) \
    .build()

vpc_client = VpcClient.new_builder() \
    .with_credentials(creds) \
    .with_region(VpcRegion.value_of(REGION)) \
    .build()

ims_client = ImsClient.new_builder() \
    .with_credentials(creds) \
    .with_region(ImsRegion.value_of(REGION)) \
    .build()

# ── 获取本机公网 IP ────────────────────────────────────────────────────────────
def get_my_ip():
    try:
        import urllib.request
        return urllib.request.urlopen(
            urllib.request.Request("https://ifconfig.me",
                                   headers={"User-Agent": "curl/8.0"}),
            timeout=10
        ).read().decode().strip()
    except Exception:
        return None

# ── SSH 工具 ──────────────────────────────────────────────────────────────────
def ssh_run(ip, key_path, user, cmd, check=True, timeout=120):
    """Run a command on the remote ECS."""
    full = [
        "ssh", "-i", str(key_path),
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=15",
        "-o", "ServerAliveInterval=30",
        f"{user}@{ip}",
        cmd,
    ]
    result = subprocess.run(
        full, capture_output=True, timeout=timeout,
        encoding="utf-8", errors="replace",
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"SSH command failed (rc={result.returncode}):\n"
            f"STDOUT: {result.stdout or ''}\nSTDERR: {result.stderr or ''}"
        )
    return result

def scp_put(ip, key_path, user, local_path, remote_path):
    cmd = [
        "scp", "-i", str(key_path),
        "-o", "StrictHostKeyChecking=accept-new",
        str(local_path), f"{user}@{ip}:{remote_path}",
    ]
    subprocess.run(cmd, check=True, encoding="utf-8", errors="replace",
                   capture_output=True)

# ── 状态持久化 ────────────────────────────────────────────────────────────────
def load_state():
    if DEPLOY_STATE.exists():
        with open(DEPLOY_STATE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(DEPLOY_STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

state = load_state()

# ══════════════════════════════════════════════════════════════════════════════
banner("LiteLLM + SearXNG + Claude-GLM 自动部署")

# ── Step 0: 生成随机密钥 ──────────────────────────────────────────────────────
step(0, "生成部署随机凭证")

if "REDIS_PWD" not in state:
    state["REDIS_PWD"]          = secrets.token_hex(16)
    state["PG_PWD"]             = secrets.token_hex(16)
    state["LITELLM_MASTER_KEY"] = "sk-" + secrets.token_hex(24)
    state["MCP_TOKEN"]          = secrets.token_hex(16)
    save_state(state)

REDIS_PWD          = state["REDIS_PWD"]
PG_PWD             = state["PG_PWD"]
LITELLM_MASTER_KEY = state["LITELLM_MASTER_KEY"]
MCP_TOKEN          = state["MCP_TOKEN"]
ok(f"LITELLM_MASTER_KEY = {LITELLM_MASTER_KEY[:12]}...")
ok(f"MCP_TOKEN = {MCP_TOKEN[:8]}...")

# ── Step 1: SSH 密钥对 ────────────────────────────────────────────────────────
step(1, "准备 SSH 密钥对")

ssh_dir = Path.home() / ".ssh"
ssh_dir.mkdir(exist_ok=True)

key_name   = f"{PREFIX}-key"
key_local  = ssh_dir / f"{PREFIX}-key"
key_pub    = ssh_dir / f"{PREFIX}-key.pub"

if SSH_KEY and Path(SSH_KEY).exists():
    key_local = Path(SSH_KEY)
    key_pub   = Path(SSH_KEY + ".pub")
    ok(f"使用已有私钥: {key_local}")
elif not key_local.exists():
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(key_local)],
        check=True
    )
    ok(f"已生成新密钥对: {key_local}")
else:
    ok(f"使用已有密钥: {key_local}")

key_local.chmod(0o600)
pub_content = key_pub.read_text().strip()
ok(f"SSH 公钥: {pub_content[:40]}...")

# ── Step 2: VPC / Subnet ─────────────────────────────────────────────────────
step(2, "获取 VPC / Subnet")

vpcs = vpc_client.list_vpcs(ListVpcsRequest()).vpcs or []
if not vpcs:
    raise RuntimeError("未找到任何 VPC，请先在控制台创建默认 VPC")
vpc = vpcs[0]
ok(f"使用 VPC: {vpc.name} ({vpc.id})")
state["VPC_ID"] = vpc.id

subnets = vpc_client.list_subnets(
    ListSubnetsRequest(vpc_id=vpc.id)
).subnets or []
if not subnets:
    raise RuntimeError("未找到可用 Subnet，请检查 VPC 配置")
subnet = subnets[0]
ok(f"使用 Subnet: {subnet.name} ({subnet.id})")
state["SUBNET_ID"] = subnet.id
save_state(state)

# ── Step 3: 安全组 ────────────────────────────────────────────────────────────
step(3, "配置安全组")

my_ip = get_my_ip()
if not my_ip:
    warn("无法获取本机公网 IP，SSH/4000/8788 将对 0.0.0.0/0 开放（不推荐）")
    laptop_cidr = "0.0.0.0/0"
else:
    laptop_cidr = f"{my_ip}/32"
    ok(f"本机公网 IP: {my_ip}  →  CIDR: {laptop_cidr}")

sg_name = f"{PREFIX}-sg"
sgs = vpc_client.list_security_groups(ListSecurityGroupsRequest()).security_groups or []
sg = next((s for s in sgs if s.name == sg_name), None)

if not sg:
    sg = vpc_client.create_security_group(CreateSecurityGroupRequest(
        body=CreateSecurityGroupRequestBody(
            security_group=CreateSecurityGroupOption(name=sg_name)
        )
    )).security_group
    ok(f"已创建安全组: {sg_name} ({sg.id})")

    for port, desc in [("22", "SSH"), (LPORT, "LiteLLM"), (MPORT, "MCP")]:
        vpc_client.create_security_group_rule(CreateSecurityGroupRuleRequest(
            body=CreateSecurityGroupRuleRequestBody(
                security_group_rule=CreateSecurityGroupRuleOption(
                    security_group_id=sg.id,
                    direction="ingress",
                    protocol="tcp",
                    port_range_min=int(port),
                    port_range_max=int(port),
                    remote_ip_prefix=laptop_cidr,
                    description=f"{desc} from operator",
                )
            )
        ))
    ok(f"已添加入站规则: 22/{LPORT}/{MPORT} ← {laptop_cidr}")
else:
    ok(f"复用安全组: {sg_name} ({sg.id})")

state["SG_ID"]        = sg.id
state["LAPTOP_CIDR"]  = laptop_cidr
save_state(state)

# ── Step 4: 查询 Ubuntu 22.04 镜像 ───────────────────────────────────────────
step(4, "查询 Ubuntu 22.04 公共镜像")

imgs = ims_client.list_images(ListImagesRequest(
    imagetype="gold",
    name="Ubuntu 22.04 server 64bit",
    os_type="Linux",
    status="active",
)).images or []

if not imgs:
    imgs = ims_client.list_images(ListImagesRequest(
        imagetype="gold",
        status="active",
    )).images or []
    # Prefer non-GPU Ubuntu 22.04 images
    imgs = [i for i in imgs
            if "ubuntu" in (i.name or "").lower()
            and "22" in (i.name or "")
            and "cuda" not in (i.name or "").lower()
            and "tesla" not in (i.name or "").lower()]

if not imgs:
    raise RuntimeError("未找到 Ubuntu 22.04 公共镜像，请检查区域或镜像名称")

image = imgs[0]
ok(f"镜像: {image.name} ({image.id})")
state["IMAGE_ID"] = image.id
save_state(state)

# ── Step 5: 置备 ECS（若未有） ────────────────────────────────────────────────
step(5, "置备 ECS")

if ECS_IP and ECS_IP not in ("", "None"):
    ok(f"使用已有 ECS: {ECS_IP}")
    state["ECS_PUBLIC_IP"] = ECS_IP
    state["ECS_SSH_KEY"]   = str(key_local)
    save_state(state)
else:
    if "ECS_ID" in state:
        try:
            srv = ecs_client.show_server(
                ShowServerRequest(server_id=state["ECS_ID"])
            ).server
            if srv.status == "ACTIVE":
                ok(f"ECS 已存在且运行中: {state['ECS_ID']}")
                state["ECS_STATUS"] = "ACTIVE"
                save_state(state)
            else:
                warn(f"ECS 状态: {srv.status}，继续等待...")
        except Exception:
            pass

    if state.get("ECS_STATUS") != "ACTIVE":
        ok("创建新 ECS (s6.xlarge.2, 100GB EVS, Ubuntu 22.04)...")

        import base64 as _b64
        # cloud-init injects the public key into root's authorized_keys
        userdata_script = textwrap.dedent(f"""\
            #!/bin/bash
            mkdir -p /root/.ssh
            chmod 700 /root/.ssh
            echo '{pub_content}' >> /root/.ssh/authorized_keys
            chmod 600 /root/.ssh/authorized_keys
            chown -R root:root /root/.ssh
        """)
        userdata_b64 = _b64.b64encode(userdata_script.encode()).decode()

        server_body = PostPaidServer(
            name=f"{PREFIX}-ecs",
            flavor_ref="s6.xlarge.2",
            image_ref=state["IMAGE_ID"],
            root_volume=PostPaidServerRootVolume(volumetype="GPSSD", size=100),
            vpcid=state["VPC_ID"],
            nics=[PostPaidServerNic(subnet_id=state["SUBNET_ID"])],
            user_data=userdata_b64,
            security_groups=[PostPaidServerSecurityGroup(id=state["SG_ID"])],
            publicip=PostPaidServerPublicip(
                eip=PostPaidServerEip(
                    iptype="5_bgp",
                    bandwidth=PostPaidServerEipBandwidth(
                        size=100, sharetype="PER", chargemode="traffic"
                    )
                )
            ),
            availability_zone=f"{REGION}a",
            count=1,
        )

        resp = ecs_client.create_servers(CreateServersRequest(
            body=CreateServersRequestBody(server=server_body)
        ))
        ecs_id = resp.server_ids[0]
        state["ECS_ID"] = ecs_id
        save_state(state)
        ok(f"ECS 创建请求已提交: {ecs_id}")

        # Wait for ACTIVE
        print("  等待 ECS 启动 (最长 5 分钟)...", end="", flush=True)
        for _ in range(60):
            time.sleep(5)
            srv = ecs_client.show_server(
                ShowServerRequest(server_id=ecs_id)
            ).server
            if srv.status == "ACTIVE":
                print(" ACTIVE")
                break
            print(".", end="", flush=True)
        else:
            raise RuntimeError("ECS 启动超时，请在控制台检查")

        state["ECS_STATUS"] = "ACTIVE"

        # Get EIP from server addresses (ServerAddress objects)
        addresses = srv.addresses or {}
        eip = None
        for net_name, addrs in addresses.items():
            for addr in (addrs or []):
                addr_type = getattr(addr, "os_ext_ip_stype", None)  # SDK maps OS-EXT-IPS:type
                addr_ip   = getattr(addr, "addr", None)
                if addr_type == "floating" and addr_ip:
                    eip = addr_ip
                    break
            if eip:
                break

        if not eip:
            warn("未从 server.addresses 找到浮动 IP，请从控制台查看 EIP")
            eip = input("请手动输入 ECS 公网 IP: ").strip()

        state["ECS_PUBLIC_IP"] = eip
        state["ECS_SSH_KEY"]   = str(key_local)
        save_state(state)
        ok(f"ECS 公网 IP: {eip}")

        # Update credential.skill with new ECS IP
        C["ECS_PUBLIC_IP"] = eip
        C["SSH_KEY"]       = str(key_local)
        with open(CRED, "w", encoding="utf-8") as f:
            json.dump(C, f, indent=2, ensure_ascii=False)
        ok("credential.skill 已更新 (ECS_PUBLIC_IP, SSH_KEY)")

ECS_IP    = state["ECS_PUBLIC_IP"]
key_local = Path(state["ECS_SSH_KEY"])

# ── Step 6: 等待 SSH 就绪 ─────────────────────────────────────────────────────
step(6, "等待 SSH 就绪")

print(f"  连接 {SSH_USER}@{ECS_IP} ...", end="", flush=True)
for attempt in range(30):
    try:
        r = ssh_run(ECS_IP, str(key_local), SSH_USER, "echo ready", check=False, timeout=20)
        if r.returncode == 0:
            print(" OK")
            break
    except Exception:
        pass
    print(".", end="", flush=True)
    time.sleep(5)
else:
    raise RuntimeError("SSH 连接超时，请检查安全组或 ECS 状态")

r = ssh_run(ECS_IP, str(key_local), SSH_USER,
            "uname -a && id && df -h / | tail -1 && free -h | head -2")
print(r.stdout)

# ── Step 7: 推送并执行 install_litellm.sh ────────────────────────────────────
step(7, "安装 LiteLLM + Redis + PostgreSQL")

install_litellm = (ROOT / "scripts" / "install_litellm.sh").read_text(encoding="utf-8")

scp_put(ECS_IP, str(key_local), SSH_USER,
        ROOT / "scripts" / "install_litellm.sh",
        "/root/install_litellm.sh")

r = ssh_run(
    ECS_IP, str(key_local), SSH_USER,
    f"REDIS_PWD='{REDIS_PWD}' PG_PWD='{PG_PWD}' "
    f"LITELLM_MASTER_KEY='{LITELLM_MASTER_KEY}' "
    f"HUAWEI_MAAS_API_BASE='{MAAS_BASE}' "
    f"HUAWEI_MAAS_API_KEY='{MAAS_KEY}' "
    f"bash /root/install_litellm.sh",
    timeout=600,
)
out = r.stdout or ""
print(out[-3000:] if len(out) > 3000 else out)
ok("LiteLLM 安装完成")
state["litellm_installed"] = True
save_state(state)

# ── Step 8: 安装 SearXNG + MCP ────────────────────────────────────────────────
step(8, "安装 SearXNG + MCP 服务")

scp_put(ECS_IP, str(key_local), SSH_USER,
        ROOT / "scripts" / "install_searxng_and_mcp.sh",
        "/root/install_searxng_and_mcp.sh")

r = ssh_run(
    ECS_IP, str(key_local), SSH_USER,
    f"MCP_TOKEN='{MCP_TOKEN}' bash /root/install_searxng_and_mcp.sh",
    timeout=600,
)
out = r.stdout or ""
print(out[-3000:] if len(out) > 3000 else out)
ok("SearXNG + MCP 安装完成")
state["searxng_installed"] = True
save_state(state)

# ── Step 9: 端对端验证 ────────────────────────────────────────────────────────
step(9, "端对端验证")

scp_put(ECS_IP, str(key_local), SSH_USER,
        ROOT / "scripts" / "validate_e2e.sh",
        "/root/validate_e2e.sh")

r = ssh_run(
    ECS_IP, str(key_local), SSH_USER,
    f"ECS_PUBLIC_IP='127.0.0.1' "
    f"LITELLM_MASTER_KEY='{LITELLM_MASTER_KEY}' "
    f"HUAWEI_MAAS_API_BASE='{MAAS_BASE}' "
    f"HUAWEI_MAAS_API_KEY='{MAAS_KEY}' "
    f"MCP_TOKEN='{MCP_TOKEN}' "
    f"bash /root/validate_e2e.sh",
    timeout=120,
    check=False,
)
print(r.stdout)
if r.returncode != 0:
    warn(f"验证脚本返回 rc={r.returncode}，请检查输出")
    print(r.stderr)
else:
    ok("所有验证通过")
state["e2e_validated"] = (r.returncode == 0)
save_state(state)

# ── Step 10: 配置本地 claude-glm ─────────────────────────────────────────────
step(10, "配置本地 claude-glm 客户端")

scp_put(ECS_IP, str(key_local), SSH_USER,
        ROOT / "scripts" / "wire_claude_glm.sh",
        "/root/wire_claude_glm.sh")
scp_put(ECS_IP, str(key_local), SSH_USER,
        ROOT / "assets" / "config" / "claude-code-router.config.json.example",
        "/root/claude-code-router.config.json.example")
scp_put(ECS_IP, str(key_local), SSH_USER,
        ROOT / "assets" / "config" / "claude-glm-wrapper.sh.example",
        "/root/claude-glm-wrapper.sh.example")

# Run wire_claude_glm.sh on the LAPTOP (not ECS)
wire_script = (ROOT / "scripts" / "wire_claude_glm.sh").read_text(encoding="utf-8")
env = os.environ.copy()
env.update({
    "ECS_PUBLIC_IP":      ECS_IP,
    "LITELLM_MASTER_KEY": LITELLM_MASTER_KEY,
    "MCP_TOKEN":          MCP_TOKEN,
    "ASSETS_DIR":         str(ROOT / "assets" / "config"),
})
r2 = subprocess.run(["bash", str(ROOT / "scripts" / "wire_claude_glm.sh")],
                    env=env, capture_output=True, text=True)
print(r2.stdout)
if r2.returncode != 0:
    warn(f"wire_claude_glm.sh rc={r2.returncode}: {r2.stderr[:500]}")
else:
    ok("claude-glm 本地配置完成")

state["claude_glm_wired"] = True
save_state(state)

# ── 完成摘要 ──────────────────────────────────────────────────────────────────
banner("部署完成 — Operator 摘要")
print(f"""
  ECS 公网 IP       : {ECS_IP}
  SSH 私钥          : {key_local}
  SSH 用户          : {SSH_USER}

  LiteLLM           : http://{ECS_IP}:{LPORT}
  LiteLLM 主密钥    : {LITELLM_MASTER_KEY}
  MCP               : http://{ECS_IP}:{MPORT}/mcp
  MCP Bearer Token  : {MCP_TOKEN}

  服务状态检查      :
    ssh -i {key_local} {SSH_USER}@{ECS_IP} \\
      "systemctl is-active litellm searxng-mcp"

  本机 claude-glm 测试:
    claude-glm -p '只回复两个字：你好'

  SG 允许 CIDR      : {state.get('LAPTOP_CIDR','?')}

  状态文件          : {DEPLOY_STATE}
  credential.skill  : {CRED}
""")

print("提示: 如需为其他笔记本接入，运行 scripts/install_claude_glm_client.sh")
print("提示: 如果笔记本 IP 变更，请在控制台更新安全组 /32 规则。")
