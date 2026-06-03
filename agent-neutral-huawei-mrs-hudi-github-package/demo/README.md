# Huawei Cloud DLI + Hudi CDC Demo

这是一个近真实的 Databricks CDC workflow 替代 demo。它把当前脚本里的 `raw -> bronze -> silver`、Auto Loader、Delta merge、Databricks Notebook 能力，替换成华为云与开源组件组合：

- OBS：raw / bronze / silver 分层存储。
- DLI：serverless Spark/Flink 主计算，贴近 Databricks serverless。
- Hudi：替代 Delta table，承接 upsert、delete、incremental pull。
- DataArts Studio：调度 DLI/CDM jobs，保留 bronze -> silver 依赖、重试和告警。
- CCE + JupyterHub：开源 Notebook 体验，通过 SDK/API 调 DLI，通过 OBS SDK 和 DWS JDBC 访问数据。
- CDM：只作为简单增量迁移可选项，不作为 Auto Loader 的一比一替代。
- MRS：只作为 Hudi/Livy/sparkmagic 兼容可选项，不作为主计算层。

## Demo 数据

本 demo 使用上一阶段生成的类生产 CDC 数据：

- 表数：`21`
- 每表事件数：`1250`
- 总事件数：`26250`
- 格式：CDC JSON Lines，顶层字段为 `before`, `after`, `op`, `source`, `ts_ms`

## 目录

- `config/`：最小资源配置、环境变量模板、DWS DDL。
- `jobs/dli/`：DLI Spark 作业，包含 bronze Hudi、silver Hudi、DWS serving。
- `jobs/dataarts/`：DataArts 编排定义模板，按时间点描述作业依赖。
- `notebooks/`：JupyterHub Notebook 和本地可执行成功率校验脚本。
- `scripts/`：按时间点执行的脚本，默认 dry-run。
- `preview/`：本地静态演示页面。
- `docs/`：运行手册、Delta 到 Hudi 替换、Notebook 成功率策略。

## 最小资源原则

先用 pay-per-use POC 资源：1 个 OBS bucket、1 条最小 DLI general-purpose queue、DataArts 作业编排、可选最小 CCE/ECS Notebook 环境、可选最小 DWS。DWS 和 CCE 在只验证 raw -> Hudi 时可以暂不创建。

## 快速本地校验

```powershell
cd "C:\Users\Matebook\Documents\Codex\2026-06-02\files-mentioned-by-the-user-databricks\outputs\huawei-dli-hudi-demo"
python scripts/06_validate_demo_package.py
python notebooks/validate_notebook_execution.py
```

## 云上执行顺序

1. 复制 `config/demo.env.example` 为本地环境变量配置，不要把 AK/SK、Token、数据库密码写入文件。
2. `scripts/00_validate_prereqs.ps1`
3. `scripts/01_package_jobs.ps1`
4. `scripts/02_upload_assets_to_obs.py --dry-run`
5. `scripts/03_build_dli_payloads.py`
6. `scripts/04_submit_dli_jobs.py --dry-run`
7. `scripts/05_poll_dli_jobs.py --dry-run`

真正提交云上任务前，把 `--dry-run` 去掉，并确认资源、配额、服务开通和 endpoint。

## 智利节点最小部署

本 demo 已按 LA-Santiago / `la-south-2` 准备最小部署脚本。最小自动创建范围只有 OBS bucket 和 DLI general queue；CCE/JupyterHub、DWS、CDM、MRS 都保持可选，避免一开始放大成本。

```powershell
cd outputs\huawei-dli-hudi-demo
powershell -ExecutionPolicy Bypass -File scripts\08_deploy_chile_minimal.ps1
```

设置凭据并确认要创建付费资源后，执行一张表 smoke test：

```powershell
pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File scripts\08_deploy_chile_minimal.ps1 -Execute -SmokeTables 1
```

详细说明见 `docs/chile-deployment.md`。
