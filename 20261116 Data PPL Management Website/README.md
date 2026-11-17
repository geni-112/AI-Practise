# 数据专项作战平台 · Data Solutions Hub

本目录是数据专项作战平台 **3.10.1** 的独立部署源码。拉美团队可以在同一工作空间管理大数据和数据库项目，从线索、POC 跟进到月报，也可以把客户架构图转成可核对、可编辑的华为云方案。网页支持中文和 English。应用运行在自己的云主机上，结构化数据保存在 MySQL 8。

## 从干净检出开始

在有 Git、Node.js 24 和 npm 的环境执行以下命令。验证会按锁文件安装依赖，构建应用，并运行权限、报表、双语架构分析、图纸和公开资料导入测试。第一次安装需要访问 npm 软件源。

```sh
git clone --depth 1 --filter=blob:none --sparse https://github.com/geni-112/AI-Practise.git
cd AI-Practise
git sparse-checkout set "20261116 Data PPL Management Website"
cd "20261116 Data PPL Management Website"
npm run agent:verify
```

**For coding agents.** Run `npm run agent:verify` from this directory. The default verification needs no database account or MaaS token. For a running website, provide the cloud-specific settings below. The agent handoff lists the entry points, environment inputs and acceptance checks. [AGENTS.md](./AGENTS.md)

## 已交付的业务功能

| 模块 | 使用方式 |
| --- | --- |
| 项目运作与 POC | 管理客户、SA、BD、现网厂家、阶段、里程碑、下一步和收入。已知但尚未交流的机会从线索收集阶段开始。POC 中心直接读取处于准备或验证阶段的项目。 |
| 数据字典与权限 | 管理员维护字段选项、中英文名称、排序、启停和自定义输入。角色区分全量与本人负责的项目，并控制技术、商务和财务字段。账号支持首次强制改密、管理员重置和会话撤销。 |
| 资料库 | 按功能命名和检索资料，支持附件和外部链接。本包附带 48 项公开资料索引，其中大数据 36 项、数据库 12 项，保留 1,387 个分支与固定提交的对应关系。 |
| 报表中心 | 按月份、范围和权限生成月报，可维护实际收入、总述、支撑信息与联系人。网页预览和 Excel 使用同一数据模型，保留模板字体、表格、合并单元格、图表和客户旅程。超出模板预留行时自动扩展，月度快照可复看。 |
| 最佳实践 | 上传 PNG、JPEG 或 WebP 架构图。云端 OCR 配合文本 MaaS，或使用多模态 MaaS，识别厂商、组件、数据流、依据及不确定项，生成华为云服务映射、方案对比和迁移步骤。 |
| 双语报告与 draw.io | 中英文结果分别保存。正文使用原图文字，读者可展开标注核对原文、识别编号及置信度。两种语言的目标架构图可在云端 draw.io 分别编辑、保存和下载。可导出包含图片和来源的离线 HTML。 |
| 案例复用与审计 | 经人工审核的摘要和服务映射供后续检索。每条分析保留失败阶段、时间和错误信息。管理员可设置 MaaS 等待时长和额度。业务修改记录审计，多人同时编辑时检查版本冲突。 |

## 云端部署

准备一台 Linux 云主机、同一私有网络内的 MySQL 8 数据库（例如华为云 RDS）、数据库应用账号和 RDS CA 证书。将站点域名及其 `drawio.` 子域解析到主机。Caddy 使用公网 80/443 申请 HTTPS 证书。应用启动时会在指定数据库创建表和执行迁移。数据库账号需要建表、变更表和业务读写权限。

1. 在目标 ECS 进入本目录。Ubuntu 24.04 可用随包脚本安装 Docker Engine 与 Compose。随后准备持久目录、私有配置示例和首次登录口令。

   ```sh
   sudo bash deploy/install-ubuntu.sh
   sudo bash deploy/prepare-config.sh
   ```

2. 在主机上填写 `.env`，将 RDS 提供的 CA 放到 `secrets/rds-ca.pem`，使容器 UID 1000 能读取证书。准备脚本生成的私有初始口令位于 `secrets/initial-account-password`。已存在的口令会继续使用。

   | 配置项 | 取值 |
   | --- | --- |
   | `SITE_DOMAIN`、`APP_ORIGIN` | 实际站点域名与对应的完整 HTTPS 来源，例如 `ppl.example.org` 与 `https://ppl.example.org` |
   | `ADMIN_EMAIL` | 首位管理员的邮箱 |
   | `DB_HOST`、`DB_PORT`、`DB_NAME` | RDS 私网地址、端口及已创建的数据库名 |
   | `DB_USER`、`DB_PASSWORD` | 本实例的应用数据库账号和密码 |
   | `DB_SSL_CA_FILE` | 容器内路径 `/run/secrets/rds-ca.pem` |
   | `INITIAL_ACCOUNT_PASSWORD_FILE` | 容器内路径 `/run/secrets/initial-account-password` |

3. 在有权访问 Docker 和私有配置的账户下启动。将示例域名替换为实际域名。

   ```sh
   sudo docker compose config --quiet
   sudo docker compose up -d --build --wait
   sudo docker compose ps
   curl -fsS https://ppl.example.org/healthz
   ```

   `/healthz` 会实际检查数据库，成功时返回 `{"status":"ok"}`。以 `ADMIN_EMAIL` 和本部署的初始口令登录，按页面提示设置个人密码。

4. 如需架构分析，在网站的「最佳实践 → 架构分析设置」或 `/settings/maas` 填写华为云 MaaS Endpoint、模型和 API Key，并执行「保存并测试」。使用文本模型时选择「云端 OCR + 文本 MaaS」。应用内的 OCR 和 draw.io 在目标云主机运行。AI 调用的时限默认 10 分钟，可调为 1–30 分钟。

## 工作台栏目名称与排序

管理员在左侧「工作台」旁选择「编辑导航」。点击栏目旁的铅笔可分别填写中文名称和英文名称，清空某个语言的名称即可恢复该语言的默认值。拖动栏目或使用上下箭头可调整位置。「保存导航」会同时保存名称和顺序。成员刷新后，菜单、页面标题和面包屑会按所选语言显示新名称。并发编辑时会提示载入最新设置。

## 账号、客户资料权限与月报

- 初始口令由云端私有配置提供。更换口令并重启应用后，仍待首次改密的账号会使用新口令，其旧会话失效。管理员在创建或重置账号的成功提示中获取初始口令。
- 新建项目时可选传一张 PNG、JPEG 或 WebP 技术架构图，最大 2 MB。项目、原图和分析队列一起保存。云端分析成功后自动归档。若分析失败，项目 SA 或平台管理员可查看日志并重试。项目 BD 可查看和导出。项目详情的「查看项目架构图」会打开最佳实践中的该项目记录，包含归档结果。
- 项目原图、分析、失败日志和双语图纸仅供当前指派的 BD、SA 和平台管理员访问。更换负责人后按新指派生效。项目图和摘要不进入团队参考案例库，也不供其他项目检索。
- 团队参考库发布审核后的标题、摘要和服务映射。旧案例需重新确认脱敏再发布。中英文分析和离线 HTML 内的可定位 OCR 引用可跳到原图高亮。
- 工作台、POC 中心和月报都统计正在准备或验证的项目，挂起、丢单和归档项目退出进行中 POC。历史月报优先显示同月、同业务类别与代表处的已归档快照。开始记录历史后，可按圣地亚哥月末状态还原，无完整记录的更早月份会在网页和 Excel 标明按当前台账重算。报表查看者获得汇总，项目明细按当前项目权限提供。

## 导入公开资料

新实例的业务台账为空。资料索引取自下列两个仓库的已审核快照。每项资料都保留功能名称、说明、所属模块和固定提交链接。

- [geni-112/AI-Practise](https://github.com/geni-112/AI-Practise)
- [binrogithub/1-3-Cloud-Adoption-Skills](https://github.com/binrogithub/1-3-Cloud-Adoption-Skills)

```sh
npm run catalog:check
sudo docker compose exec -T app node server/import-catalog.mjs --dry-run
sudo docker compose exec -T app node server/import-catalog.mjs --apply
```

`--check` 在本地验证索引结构。后两条命令在运行中的云端应用内执行。首次导入空资料库会创建 48 项，再次执行会跳过相同条目。已有同源资料只更新来源信息，保留团队编辑的标题和正文。写入和审计使用同一事务。

## 源码与运行数据

| 位置 | 职责 |
| --- | --- |
| `public/` | 中英文界面、项目与字典表单、最佳实践、draw.io 编辑和用户端导出 |
| `server/index.mjs`、`server/auth.mjs` | HTTP、会话、账号、权限与事务边界 |
| `worker/` | 项目、POC、资源、审计、报表等业务逻辑，由独立服务调用 |
| `server/architecture-*.mjs`、`ocr/` | MaaS、OCR、语言版本、来源、案例检索和目标图纸 |
| `templates/`、`migrations/` | 空白月报模板和网页布局、MySQL 迁移 |
| `compose.yaml`、`deploy/` | 应用容器、私网 OCR、HTTPS 入口、独立 HTTPS 来源的 draw.io 子域、备份示例 |

RDS 保存账号、台账、报表快照、分析状态、审核案例以及 draw.io XML 和 PNG 预览。从新建项目上传的原图也保存在 RDS，与项目信息同一事务提交。常规资料附件和从最佳实践单独上传的原图保存在 `data/uploads`。MaaS API Key 用 AES-256-GCM 加密，其主密钥保存在 `data/private/maas.key`。恢复一套实例需要同一个恢复点的数据库、上传文件、加密主密钥，以及部署私有配置。备份脚本与 systemd 示例位于 `deploy/`，示例默认安装路径为 `/opt/data-ppl-management`。自定义库名时给备份任务传入相同的 `DB_NAME`。

## English deployment summary

Use a cloud Linux host, Docker Compose, a private MySQL 8 database and DNS for both the website and its draw.io subdomain. Run `deploy/prepare-config.sh` on that host. Fill in `.env`, install the database CA, then run `docker compose up -d --build --wait`. The first administrator signs in with the configured email and the private initial password, then changes it. Configure Huawei Cloud MaaS in the admin UI to enable architecture reviews. The project workspace, project-derived POC list, native Excel reporting and public resource catalog work independently of model credentials.
