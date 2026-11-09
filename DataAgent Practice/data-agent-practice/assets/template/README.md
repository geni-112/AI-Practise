# NEXO Data Agent

可运行的 Data Agent 模板：React / ChatBI / 流程画布 + FastAPI / openJiuwen / MCP + OpenMetadata / Iceberg / Temporal。默认浏览器演示使用 10,000 条英文合成电商数据；没有配置云资源、真实模型或线上访问地址。

## 浏览器演示

需要 Python 3.12 和 Node.js 22.12+。从项目根目录运行；如果通过 Skill 创建，数据已经生成，无需重复第一步。

```bash
python scripts/generate_data.py
npm ci
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

打开 `http://127.0.0.1:5173`。右上角切换中文 / English (US) / Español，偏好在刷新后保留。浏览器规则演示不调用模型，任务只在当前浏览器内推进。首次引导、目录展开、资产详情、问数、图表、看板、流程、任务及角色切换均可直接体验。

主题为 Rappi 风格橙红、白和浅灰；中文使用微软雅黑及本地回退，US English 使用 Arial，Español 使用 Verdana。共享文案在 `src/messages.json`，后端也依赖这个文件。

## 完整本地集成

使用 `integrated` profile 创建的项目已带私有 `.env`。从浏览器模式转换时，在 `.env` 中设置 `NEXO_BROWSER_ONLY=false`、`TEMPORAL_ENABLED=true`、`OPENMETADATA_URL=http://127.0.0.1:8585`。账号密钥保持空白即可使用标记为 `demo_rules` 的规则计划。

需要 Python 3.12、uv、Docker Compose，以及约 8 GB 可用内存；OpenMetadata/OpenSearch 比纯前端需要更多资源。以下为 Linux/macOS 命令，Windows 使用 `.venv/Scripts/python.exe`：

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.lock.txt
docker compose --env-file .env -p nexo -f infra/local-compose.yml -f infra/runtime-compose.yml up -d
```

等待 `http://127.0.0.1:8585/api/v1/system/version` 返回成功，Temporal 接受 7233 端口连接后：

```bash
.venv/bin/python -m backend.metadata
.venv/bin/python -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

另一个终端运行 `npm ci` 和 `npm run dev -- --host 127.0.0.1 --port 5173`。OpenMetadata 为 `http://127.0.0.1:8585`，Temporal UI 为 `http://127.0.0.1:8233`。这些开发服务只绑定回环地址，使用开发账号；本地启动不是正式企业部署。

FastAPI → openJiuwen Workflow → openJiuwen MCP client → 包内 scoped MCP server → SQLite。OpenMetadata 管理统一资产与血缘，实际 Iceberg 表保存元数据历史，Temporal 执行处理任务。确认 `/api/health` 返回服务状态后再验收；`model_connected` 仅表示模型配置存在，实际模型调用需单独问数验证。

## 模型与 DWS 配置

通过安全配置修改被 Git 忽略的 `.env`，勿向聊天或浏览器表单粘贴密钥：

```dotenv
MODEL_PROVIDER=huawei_maas
MODEL_NAME=glm-5.3
MODEL_BASE_URL=
MODEL_API_KEY=
MODEL_TIMEOUT=90
```

支持 `MODEL_PROVIDER=openai_compatible` 并替换模型、base URL 和 key；不自动切换供应商。模型输出结构化计划，再编译为受控参数化 SQL，禁止执行任意模型 SQL。`DEMO_MODE=false` 时缺少模型配置会失败，演示角色切换也会关闭，需接入有效 OIDC 身份。

真实 DWS 设置 `DATA_BACKEND=dws` 和 `DWS_HOST/PORT/DATABASE/USER/PASSWORD/SSLMODE/SSLROOTCERT`。运行 API 的主机需能访问 DWS 私网；默认 `verify-full`，华为官方证书方案可使用 `verify-ca` 与对应可信 CA。不要关闭 TLS 验证。读取使用独立只读账号；初始化导入通过单独授权的管理员会话完成。

`scripts/load_dws.py` 读取**进程环境变量**，不自行加载 `.env`；可通过已配置的安全运行环境执行 `.venv/bin/python -m scripts.load_dws`。它只导入虚构数据，遇到非空且行数不符的表会停止。同样行数不会证明数据内容相同，应使用新的专用演示 schema。包内 MCP 是适配器，不是华为云托管 MCP 服务。

## 场景与边界

数据生成器 seed `20261106`：12 表共 10,000 行，包含两租户、客户900、商品120、订单2600、明细3500、库存240、退货250、配送900、活动24、广告600、竞价480、评论384和租户控制表2行。全部为虚构英文数据，金额为 USD；18 个客户缺失电话、6 条负库存用于质量场景。

可提问：`分析10月各地区销售额`、`Show October sales by region`、`Analiza las ventas de octubre por región`、`分析广告ROAS`、`检查库存健康`。规则模式只支持明确的模板场景。

处理流程支持订单单链路：读取→过滤→聚合→质量检查→发布。后端执行身份逐节点鉴权，质量失败阻断发布，产出进入独立本地 sandbox，按租户/目标/分区幂等更新。每天 08:00 Mexico City 的调度需要真实 Temporal，浏览器模式拒绝持久调度。

浏览器角色切换是演示。后端有租户、角色、业务域、地区限制以及签名 OIDC 和 OPA 扩展；完整生产组织与权限生命周期仍需建设。Iceberg 使用本地 SQL Catalog，未部署 Polaris。Snowflake、Redshift 和 DWS 写回是扩展项。

## 验证与维护

```bash
npm run build
MODEL_API_KEY='' MODEL_BASE_URL='' HUAWEICLOUD_MODEL_API_KEY='' .venv/bin/python -m pytest tests -q
```

测试本地集成链路时运行 `.venv/bin/python tests/verify_integration.py`，会创建合成任务、sandbox 输出与短暂测试调度并清理该调度；只用于专用演示环境。云端脚本是 Mexico City2 的部署参考，执行前需补齐新环境的配置、资源计划、库存、证书和对应授权，不能直接依赖本模板的空状态运行。

通过 Skill 的 quickstart 启动时会生成 UI 下载包；手动启动或修改源码后，运行 `python scripts/package_downloads.py` 后再构建前端。下载包不随模板预生成。应用源码不包含密钥或已部署资源状态；`.env`、`.runtime/`、`public/downloads/` 不得提交到公开仓库。
