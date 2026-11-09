# DataAgent Practice · 可安装的 Data Agent Skill

把 NEXO Data Agent 的方案、完整源码和可重复演示封装为标准 Agent Skill。支持 GitHub Copilot、Codex、Claude Code；无需华为云账号即可先运行本地演示。

## 安装到你的项目

需要 Python 3.12。克隆仓库后，从仓库根目录运行：

```bash
git clone https://github.com/geni-112/AI-Practise.git
cd AI-Practise
python "DataAgent Practice/install_skill.py" --client copilot --project /path/to/your-project
```

`--client` 可选 `copilot`、`codex`、`claude`，分别安装到项目的 `.github/skills/`、`.agents/skills/`、`.claude/skills/`。Windows 可使用 `py -3.12` 并替换项目路径；含空格的路径加引号。安装器拒绝覆盖已有不同内容，可重复安装同一版本。

在支持 Agent Skills 的客户端重新打开目标项目，然后输入：

> 使用 data-agent-practice skill，创建一个名为 nexo-demo 的 Data Agent 演示。先使用本地合成数据，保留 OpenJiuwen、MCP、DWS 适配、统一元数据、流程任务和三语言切换。

Codex 也可以显式调用 `$data-agent-practice`。客户端需启用其 Agent Skills 功能；本包不安装模型服务或编辑客户端账号配置。

## 不通过 Agent，直接启动演示

需要 Node.js 22.12+、npm、Python 3.12；首次安装前端依赖需要网络。

```bash
python "DataAgent Practice/data-agent-practice/scripts/quickstart.py" --dest ./nexo-demo
```

打开 `http://127.0.0.1:5173`。该命令创建独立目录、生成 10,000 条英文合成电商数据及界面所需下载包、安装锁定依赖并启动前端；浏览器模式不连接模型、云资源或已有本地后端。停止使用 Ctrl+C。

仅生成文件和数据：

```bash
python "DataAgent Practice/data-agent-practice/scripts/quickstart.py" --dest "./my data-agent" --prepare-only
```

完整后端演示另见 [本地集成指南](data-agent-practice/references/local-development.md)，连接真实 DWS 见 [MCP 与 DWS](data-agent-practice/references/dws-mcp.md)，云资源预检及部署见 [云部署指南](data-agent-practice/references/cloud-deployment.md)。

## 包含的能力

| 能力 | 首版实现 |
|---|---|
| ChatBI / N2SQL | 对话问数、受控结构化计划、参数化 SQL、图表与看板 |
| Agent / 数据访问 | openJiuwen Workflow → MCP 适配服务 → SQLite 或 DWS |
| 目录与治理 | OpenMetadata 统一资产、字段、血缘；Iceberg 记录元数据历史 |
| 处理任务 | 可视化流程、手动下发、Temporal 持久化执行与调度、幂等输出 |
| 分权分域 | 租户、角色、业务域、地区限制；后端鉴权与 OIDC/OPA 扩展接口 |
| 模型 | 默认 Huawei MaaS `glm-5.3`，支持配置其他 OpenAI-compatible 服务 |
| 界面 | Rappi 风格橙红、白与浅灰；中文微软雅黑、US English Arial、Español Verdana |
| 演示数据 | 固定种子，12 张表、10,000 行；内部订单/库存及虚构外部广告/竞品/评论 |

浏览器模式使用明确标识的规则模板与浏览器任务状态；真实 openJiuwen/MCP、OpenMetadata、Iceberg、Temporal 需要启动集成后端。DWS MCP 是包内适配服务，不代表华为云托管 MCP 端点。Snowflake/Redshift 接入、Polaris、完整企业组织/IAM 和 DWS 写回属于扩展项；首版任务发布到独立本地 sandbox，不移动或改写源表。

## 包结构与校验

标准入口为 [data-agent-practice/SKILL.md](data-agent-practice/SKILL.md)。`references/` 提供分阶段说明，`scripts/` 提供安装、创建和校验命令，`assets/template/` 提供完整应用源码；演示 CSV 和数据库由生成器按需创建。

```bash
python "DataAgent Practice/data-agent-practice/scripts/validate_package.py"
```

本次打包已通过三种客户端安装、前端生产构建、43 项后端测试，以及三语言在两种宽度下的 36 个页面检查。详情见 [VALIDATION.md](VALIDATION.md)。

包内不包含账号凭据、部署实例状态、登录邀请、证书私钥或运行数据库。云资源创建必须在新环境配置账号并获得对应操作授权；安装和本地启动均不创建付费资源。依赖采用各自的开源许可证，本目录未替整个仓库另设许可证。
