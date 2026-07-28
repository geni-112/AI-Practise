const state = {
  lastRun: null,
  lastPrompt: "",
  processSteps: [],
  currentArtifactIndex: 0,
  templates: [],
  selectedTemplate: null,
  templateVariables: {},
  maasStatus: null,
  releasePackage: null,
  cloudBinding: null,
  importReview: null,
  dataArtsStandardization: null,
  cloudResourceProbe: null,
  allowNetworkProbe: false,
  lastEvaluation: null,
  lastComparison: null,
  maasStrategies: [],
  failureSamples: [],
  lastReplay: null,
  preExecution: null,
  productionAuth: null,
  productionControl: null,
  executionProfiles: [],
  cloudReadiness: null,
  cloudEvidence: null,
  cloudGoldQuery: null,
  selectedProcessStepId: "data_context",
  activeResultTab: "overview",
  isRunning: false,
  stepEventQueue: [],
  stepEventTimer: null,
  pendingCompletedRun: null,
  chatBiHistory: [],
  chatBiBusy: false,
  localeRefreshSequence: 0,
  lastWorkbenchView: "compose",
};

const $ = (selector) => document.querySelector(selector);

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) {
    if (window.i18n) window.i18n.setText(element, text);
    else element.textContent = text;
  }
  return element;
}

function statusLabel(status) {
  const labels = {
    approved: "已通过",
    blocked: "已锁定",
    configured: "已配置",
    fallback: "本地兜底",
    failed: "失败",
    generated: "已生成",
    needs_cloud_binding: "需绑定云环境",
    needs_maas: "需配置 MaaS",
    needs_binding: "需绑定",
    needs_binding_fix: "绑定需修复",
    needs_fix: "需修复",
    not_required: "无需确认",
    operator_handoff_ready: "交接就绪",
    pending: "待确认",
    execution_requested: "待执行审批",
    queued: "已入队",
    cancel_requested: "等待取消",
    cancelled: "已取消",
    succeeded: "执行成功",
    passed: "已通过",
    rejected: "已驳回",
    replayed: "已回放",
    ready: "就绪",
    ready_for_real_resource_creation: "可创建真实资源",
    ready_for_import_review: "待导入复核",
    ready_for_review: "待复核",
    review_needed: "需复核",
    running: "进行中",
    maas_unavailable: "MaaS 不可用",
    simulated_ready: "模拟通过",
    skipped: "已跳过",
    stale: "已过期",
    used: "已使用",
    warning: "提醒",
  };
  const fallbackLabels = {
    pending_customer_demo_evidence: "\u7b49\u5f85\u5ba2\u6237\u6f14\u793a\u8bc1\u636e",
    ready_for_commercial_pilot: "\u53ef\u8fdb\u5165\u5546\u7528\u8bd5\u70b9",
    ready_for_customer_demo: "\u53ef\u5ba2\u6237\u6f14\u793a",
    cloud_e2e_verified: "云上已验证",
    invalid: "报告异常",
    missing_credentials: "缺少凭证",
    missing_required: "缺少配置",
    not_run: "未运行",
    pending_cloud_preflight: "等待云预检",
    pending_readiness: "等待准备",
    ready_for_apply: "可进入 Apply",
  };
  const label = labels[status] || fallbackLabels[status] || status;
  return window.i18n?.t(label) || label;
}

function badgeClass(status) {
  if (status === "blocked" || status === "needs_maas" || status === "skipped" || status === "review_needed" || status === "pending_readiness" || status === "pending_cloud_preflight" || status === "execution_requested" || status === "queued" || status === "cancel_requested") return "blocked";
  if (status === "failed" || status === "maas_unavailable" || status === "invalid" || status === "missing_credentials" || status === "missing_required") return "failed";
  if (status === "ready" || status === "ready_for_apply" || status === "cloud_e2e_verified" || status === "ready_for_real_resource_creation" || status === "passed" || status === "approved" || status === "generated" || status === "simulated_ready" || status === "operator_handoff_ready" || status === "succeeded") return "ready";
  return "muted";
}

function setBusy(isBusy) {
  state.isRunning = isBusy;
  const runButton = $("#runButton");
  runButton.disabled = isBusy || !$("#prompt").value.trim();
  runButton.textContent = isBusy ? "…" : "↑";
}

function setChatBIBusy(isBusy) {
  state.chatBiBusy = isBusy;
  const sendButton = $("#chatbiSend");
  if (!sendButton) return;
  sendButton.disabled = isBusy || !$("#chatbiPrompt").value.trim();
  sendButton.textContent = isBusy ? "…" : "↑";
}

function closeComposerOptions() {
  const options = $(".composer-options");
  if (options) options.open = false;
}

function setDecision(title, detail) {
  const box = $("#decisionBox");
  box.replaceChildren(node("strong", "", title), node("span", "", detail));
  const progressOutcome = $("#processOutcome");
  if (progressOutcome && state.isRunning) progressOutcome.textContent = detail;
}

function setAppView(view) {
  const shell = $("#appShell");
  shell.dataset.view = view;
  ["compose", "chatbi", "progress", "result", "metadata"].forEach((name) => {
    $(`#${name}View`)?.classList.toggle("is-active", name === view);
  });
  if (view !== "metadata") state.lastWorkbenchView = view;
  document.querySelectorAll("[data-app-nav]").forEach((link) => {
    const active = link.dataset.appNav === (view === "metadata" ? "metadata" : "workbench");
    link.classList.toggle("is-active", active);
    link.setAttribute("aria-current", active ? "page" : "false");
  });
  $("#newTaskButton")?.classList.toggle("is-hidden", !["chatbi", "result"].includes(view));

  const workspace = $("#processWorkspace");
  if (view === "progress") $("#progressProcessHost")?.append(workspace);
  if (view === "result") $("#resultProcessHost")?.append(workspace);
  window.scrollTo({ top: 0, behavior: "auto" });
}

function navigateApp(destination, options = {}) {
  const isMetadata = destination === "metadata";
  setAppView(isMetadata ? "metadata" : state.lastWorkbenchView || "compose");
  if (options.updateHistory !== false) {
    window.history.pushState({ appView: destination }, "", isMetadata ? "/metadata" : "/");
  }
}

function selectResultTab(tabName) {
  state.activeResultTab = tabName;
  document.querySelectorAll("[data-result-tab]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.resultTab === tabName);
  });
  document.querySelectorAll("[data-result-panel]").forEach((panel) => {
    panel.classList.toggle("is-active", panel.dataset.resultPanel === tabName);
  });
  if (tabName === "workflow") $("#resultProcessHost")?.append($("#processWorkspace"));
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function resetToComposer(options = {}) {
  const promptToKeep = options.preservePrompt ? state.lastPrompt || $("#prompt").value : "";
  if (state.stepEventTimer) window.clearTimeout(state.stepEventTimer);
  state.lastRun = null;
  state.lastPrompt = "";
  state.processSteps = [];
  state.selectedProcessStepId = "data_context";
  state.stepEventQueue = [];
  state.stepEventTimer = null;
  state.pendingCompletedRun = null;
  state.chatBiHistory = [];
  state.chatBiBusy = false;
  state.productionAuth = null;
  state.productionControl = null;
  state.executionProfiles = [];
  $("#chatbiConversation")?.replaceChildren();
  if ($("#chatbiPrompt")) $("#chatbiPrompt").value = "";
  $("#prompt").value = promptToKeep;
  hide("#progressFailureActions");
  $("#prompt").focus();
  closeComposerOptions();
  setBusy(false);
  setAppView("compose");
}

function show(selector) {
  const element = $(selector);
  if (!element) return;
  element.classList.remove("is-hidden");
  if (element instanceof HTMLDetailsElement) {
    element.open = true;
  }
}

function hide(selector) {
  const element = $(selector);
  if (!element) return;
  element.classList.add("is-hidden");
  if (element instanceof HTMLDetailsElement) {
    element.open = false;
  }
}

function renderUserPrompt(prompt) {
  $("#userPromptMessage").textContent = prompt.trim();
  show("#userMessage");
}

function scrollThreadToBottom() {
  return;
}

async function loadHealth() {
  const response = await fetch("/api/health", { cache: "no-store" });
  const health = await response.json();
  const badge = $("#healthBadge");
  badge.textContent = health.ok ? "接口正常" : "接口异常";
  badge.className = `badge ${health.ok ? "ready" : "failed"}`;

  const strip = $("#runtimeStrip");
  strip.replaceChildren(
    node("span", "", health.langgraph_available ? "本地编排" : "编排缺失"),
    node("span", "", health.maas_configured ? `MaaS ${health.maas_model}` : "MaaS 本地兜底"),
    node("span", "", "云上执行锁定"),
  );

  const codeServerLink = $("#codeServerLink");
  if (codeServerLink && !health.code_server_found) {
    codeServerLink.removeAttribute("href");
    codeServerLink.removeAttribute("target");
    codeServerLink.setAttribute("aria-disabled", "true");
    codeServerLink.textContent = "code-server unavailable";
  }
}

async function loadCloudEvidence() {
  const response = await fetch("/api/cloud/e2e-evidence", { cache: "no-store" });
  if (!response.ok) throw new Error(`cloud evidence request failed: ${response.status}`);
  state.cloudEvidence = await response.json();
  renderCloudEvidence(state.cloudEvidence);
  await loadCloudGoldQuery();
}

function selectedValue(selector) {
  const element = $(selector);
  return element?.value || "";
}

async function loadCloudGoldQuery() {
  const params = new URLSearchParams();
  const year = selectedValue("#cloudGoldYear");
  const region = selectedValue("#cloudGoldRegion");
  const regime = selectedValue("#cloudGoldRegime");
  const resico = selectedValue("#cloudGoldResico");
  if (year) params.set("year", year);
  if (region) params.set("region", region);
  if (regime) params.set("regime", regime);
  if (resico) params.set("resico", resico);
  params.set("limit", "50");
  const response = await fetch(`/api/cloud/gold-query?${params.toString()}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`cloud gold query failed: ${response.status}`);
  state.cloudGoldQuery = await response.json();
  renderCloudGoldQuery(state.cloudGoldQuery);
}

async function loadCloudReadiness() {
  const response = await fetch("/api/cloud/readiness", { cache: "no-store" });
  if (!response.ok) throw new Error(`cloud readiness request failed: ${response.status}`);
  state.cloudReadiness = await response.json();
  renderCloudReadiness(state.cloudReadiness);
}

function renderCloudReadiness(readiness) {
  const badge = $("#cloudReadinessBadge");
  if (!badge) return;

  const status = readiness?.status || "not_run";
  badge.textContent = statusLabel(status);
  badge.className = `badge ${badgeClass(status)}`;

  $("#cloudReadinessSummary").textContent = readiness?.message || "还没有读取到真实云准备度报告。";
  $("#cloudReadinessPolicy").textContent = readiness?.source_policy || "密钥只能来自环境变量、忽略提交的本地 env 文件或云密钥服务。";

  const gateBox = $("#cloudReadinessGates");
  const gates = Array.isArray(readiness?.gates) ? readiness.gates : [];
  if (!gates.length) {
    gateBox.replaceChildren(node("div", "empty-state", "还没有 readiness gate。"));
  } else {
    gateBox.replaceChildren(
      ...gates.map((gate) => {
        const item = node("div", `readiness-gate ${badgeClass(gate.status)}`);
        const head = node("div", "readiness-gate-head");
        head.append(node("strong", "", gate.label || gate.id));
        head.append(node("span", `badge ${badgeClass(gate.status)}`, statusLabel(gate.status)));
        const detail = node("p", "", gate.detail || gate.raw_status || "");
        const meta = node("span", "readiness-meta", gate.path || "");
        item.append(head, detail, meta);
        return item;
      }),
    );
  }

  const commandBox = $("#cloudReadinessCommands");
  const commands = readiness?.commands || {};
  const commandEntries = Object.entries(commands).filter(([, value]) => value);
  if (!commandEntries.length) {
    commandBox.replaceChildren();
    return;
  }

  const commandTitle = node("strong", "", "下一步命令");
  const nextAction = node("p", "readiness-next-action", readiness?.next_action || "等待操作员选择下一步。");
  const commandList = node("div", "readiness-command-list");
  commandEntries.slice(0, 4).forEach(([key, value]) => {
    const item = node("div", "readiness-command");
    item.append(node("span", "", key), node("code", "", String(value)));
    commandList.append(item);
  });
  commandBox.replaceChildren(commandTitle, nextAction, commandList);
}

function cloudEvidenceMetric(label, value) {
  const item = node("div", "metric");
  item.append(node("span", "", label));
  item.append(node("strong", "", value));
  return item;
}

function cloudEvidenceLink(label, href) {
  const item = node("div", "metric");
  item.append(node("span", "", label));
  if (href) {
    const link = node("a", "", "查看");
    link.href = href;
    link.target = "_blank";
    link.rel = "noreferrer";
    item.append(link);
  } else {
    item.append(node("strong", "", "-"));
  }
  return item;
}

function publicCloudResourceName(value, fallback) {
  const text = String(value || "").trim();
  if (!text || /\bsat\b|sat_|sat-/i.test(text)) return fallback;
  return text;
}

function renderCloudEvidence(evidence) {
  const badge = $("#cloudEvidenceBadge");
  const available = Boolean(evidence?.available);
  const status = evidence?.status || "not_run";
  badge.textContent = available && status === "success" ? "执行成功" : available ? statusLabel(status) : "未运行";
  badge.className = `badge ${available && status === "success" ? "ready" : available ? "blocked" : "muted"}`;

  $("#cloudEvidenceSummary").textContent = available
    ? `云上运行 ${evidence.run_id || ""} 已完成，从 OBS Gold / tax / ${evidence.run_id || "current"} 读取到 ${evidence.gold_row_count || 0} 行结果。`
    : evidence?.message || "尚未发布真实华为云端到端执行证据。";

  $("#cloudEvidenceMeta").replaceChildren(
    cloudEvidenceMetric("运行 ID", evidence?.run_id || "-"),
    cloudEvidenceMetric("MRS 作业", evidence?.job?.terminal_status === "success" ? "成功" : evidence?.job?.terminal_status || status),
    cloudEvidenceMetric("Gold 行数", String(evidence?.gold_row_count || 0)),
    cloudEvidenceMetric("MRS 集群", publicCloudResourceName(evidence?.mrs?.name, "Agentic Tax Demo MRS")),
    cloudEvidenceMetric("DataArts", publicCloudResourceName(evidence?.dataarts?.instance_name, "Agentic Tax Demo DataArts")),
    cloudEvidenceMetric("Factory DAG", publicCloudResourceName(evidence?.dataarts?.factory_job_name, "Agentic Tax Demo Pipeline")),
    cloudEvidenceMetric("直接 RFC", evidence?.direct_rfc_exposed ? "已暴露" : "已脱敏"),
    cloudEvidenceMetric("DuckDB", evidence?.duckdb_used ? "已使用" : "未使用"),
    cloudEvidenceLink("客户报告", evidence?.customer_report_url || ""),
  );
  renderRowsTable("#cloudEvidenceTable", evidence?.gold_preview_rows || []);
}

function setSelectOptions(selector, values, allLabel = "All") {
  const select = $(selector);
  if (!select) return;
  const previous = select.value;
  const uniqueValues = Array.isArray(values) ? values.filter((value) => value !== undefined && value !== null && String(value) !== "") : [];
  select.replaceChildren(new Option(allLabel, ""));
  uniqueValues.forEach((value) => select.append(new Option(String(value), String(value))));
  if ([...select.options].some((option) => option.value === previous)) {
    select.value = previous;
  }
}

function renderCloudGoldQuery(result) {
  const dimensions = result?.dimensions || {};
  setSelectOptions("#cloudGoldYear", dimensions.years || []);
  setSelectOptions("#cloudGoldRegion", dimensions.regions || []);
  setSelectOptions("#cloudGoldRegime", dimensions.regimes || []);

  const summary = result?.summary || {};
  $("#cloudGoldQuerySummary").replaceChildren(
    cloudEvidenceMetric("分组数", String(summary.group_count || 0)),
    cloudEvidenceMetric("纳税人数", String(summary.taxpayer_count || 0)),
    cloudEvidenceMetric("收入合计", String(summary.income_total || 0)),
    cloudEvidenceMetric("筛选结果", `${result?.filtered_count || 0}/${result?.row_count || 0}`),
  );
  renderRowsTable("#cloudGoldQueryTable", result?.rows || []);
}

async function loadMaaSStatus() {
  const response = await fetch("/api/maas/status", { cache: "no-store" });
  if (!response.ok) throw new Error(`读取 MaaS 状态失败：${response.status}`);
  state.maasStatus = await response.json();
  renderMaaSStatus(state.maasStatus);
}

function renderMaaSStatus(status) {
  const badge = $("#maasBadge");
  const statusBox = $("#maasStatus");
  badge.textContent = status.configured ? "已配置" : "本地兜底";
  badge.className = `badge ${status.configured ? "ready" : "blocked"}`;
  statusBox.textContent = status.configured
    ? `当前模型：${status.model}。密钥来源：${status.api_key_source}。Endpoint：${status.base_url_host}${status.base_url_path}。`
    : `未配置 MaaS 密钥：${status.missing_env?.join(", ") || "HUAWEI_MAAS_API_KEY"}。现在会使用本地兜底生成。`;
}

async function testMaaS() {
  const button = $("#testMaaS");
  button.disabled = true;
  button.textContent = "测试中";
  const resultBox = $("#maasTestResult");
  resultBox.className = "maas-test-result";
  resultBox.textContent = "正在用一条短 prompt 测试 MaaS，只调用模型，不会执行大数据任务。";
  try {
    const response = await fetch("/api/maas/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt: "Return compact JSON with status ok, model glm-5.2, and purpose MaaS connectivity test.",
      }),
    });
    const result = await response.json();
    renderMaaSStatus(result.status);
    resultBox.className = `maas-test-result ${result.ok ? "ready" : "failed"}`;
    resultBox.textContent = result.ok
      ? `MaaS 测试通过，模型：${result.model}。${result.summary}`
      : result.configured
        ? `MaaS 调用失败：${result.error}`
        : `MaaS 未配置：${result.error}`;
  } catch (error) {
    resultBox.className = "maas-test-result failed";
    resultBox.textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = "测试 MaaS";
  }
}

async function loadEvaluationHistory() {
  const response = await fetch("/api/evaluations", { cache: "no-store" });
  if (!response.ok) throw new Error(`读取评测历史失败：${response.status}`);
  const data = await response.json();
  if (data.evaluations?.length) {
    renderEvaluationSummary(data.evaluations[0], { compact: true });
  }
}

async function runEvaluationSuite() {
  const button = $("#runEvaluation");
  const box = $("#evaluationResult");
  button.disabled = true;
  button.textContent = "评测中";
  box.className = "evaluation-result";
  box.replaceChildren(
    node("strong", "", "评测运行中"),
    node("span", "", "正在批量执行 5 个 Tax prompt，并自动跑完审批、发布、绑定和导入复核。"),
  );
  try {
    const response = await fetch("/api/evaluations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        use_maas: false,
        max_cases: 5,
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
    state.lastEvaluation = result;
    renderEvaluationSummary(result);
    setDecision(
      result.passed ? "评测集通过" : "评测集发现问题",
      `${result.summary} 云上执行仍然锁定。`,
    );
  } catch (error) {
    box.className = "evaluation-result failed";
    box.replaceChildren(node("strong", "", "评测失败"), node("span", "", error.message));
    setDecision("评测失败", error.message);
  } finally {
    button.disabled = false;
    button.textContent = "运行评测集";
  }
}

function renderEvaluationSummary(result, options = {}) {
  const box = $("#evaluationResult");
  if (!box || !result) return;
  const passed = Boolean(result.passed || result.status === "passed");
  const score = `${result.score ?? 0}/${result.max_score ?? 0}`;
  const passRate = `${Math.round(Number(result.pass_rate || 0) * 100)}%`;
  box.className = `evaluation-result ${passed ? "ready" : "failed"}`;
  box.replaceChildren(
    node("strong", "", options.compact ? "最近一次评测" : passed ? "评测集通过" : "评测集未通过"),
    node("span", "", `${result.summary || ""} 通过率 ${passRate}，得分 ${score}。`),
  );

  const files = result.files || [];
  const scorecard = files.find((file) => file.name === "scorecard.md") || (result.scorecard_url ? { url: result.scorecard_url } : null);
  if (scorecard?.url) {
    const link = node("a", "", "查看 scorecard");
    link.href = scorecard.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    box.append(link);
  }

  const cases = result.cases || [];
  if (!cases.length) return;
  const list = node("div", "evaluation-cases");
  cases.forEach((item) => {
    const row = node("div", `evaluation-case ${item.status === "passed" ? "ready" : "failed"}`);
    const title = node("strong", "", `${item.name || item.case_id}：${statusLabel(item.status)}`);
    const detail = node("span", "", `得分 ${item.score}/${item.max_score}`);
    row.append(title, detail);
    if (item.run_url) {
      const link = node("a", "", "查看运行");
      link.href = item.run_url;
      link.target = "_blank";
      link.rel = "noreferrer";
      row.append(link);
    }
    list.append(row);
  });
  box.append(list);
}

async function loadComparisonHistory() {
  const response = await fetch("/api/evaluations/comparisons", { cache: "no-store" });
  if (!response.ok) throw new Error(`读取对照评测历史失败：${response.status}`);
  const data = await response.json();
  if (data.comparisons?.length) {
    renderComparisonSummary(data.comparisons[0], { compact: true });
  }
}

async function runComparisonSuite() {
  const button = $("#runComparison");
  const box = $("#comparisonResult");
  button.disabled = true;
  button.textContent = "对照中";
  box.className = "comparison-result";
  box.replaceChildren(
    node("strong", "", "对照评测运行中"),
    node("span", "", "正在先跑本地兜底，再按同一组 prompt 尝试 GLM-5.2 MaaS。云上执行仍然锁定。"),
  );
  try {
    const response = await fetch("/api/evaluations/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ max_cases: 5 }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
    state.lastComparison = result;
    renderComparisonSummary(result);
    setDecision(
      result.passed ? "MaaS 对照评测通过" : `对照评测：${statusLabel(result.status)}`,
      result.recommendation || result.summary,
    );
  } catch (error) {
    box.className = "comparison-result failed";
    box.replaceChildren(node("strong", "", "对照评测失败"), node("span", "", error.message));
    setDecision("对照评测失败", error.message);
  } finally {
    button.disabled = false;
    button.textContent = "运行对照评测";
  }
}

function renderComparisonSummary(result, options = {}) {
  const box = $("#comparisonResult");
  if (!box || !result) return;
  const status = result.status || "unknown";
  const className = result.passed || status === "passed"
    ? "ready"
    : status === "needs_maas" || status === "review_needed"
      ? "blocked"
      : "failed";
  const metrics = result.metrics || {};
  const local = result.local || {};
  const maas = result.maas || {};
  const title = options.compact ? "最近一次对照" : `对照评测：${statusLabel(status)}`;
  const scoreLine = `Local ${local.score ?? metrics.local_score ?? 0}/${local.max_score ?? metrics.local_max_score ?? 0}；MaaS ${maas.score ?? metrics.maas_score ?? 0}/${maas.max_score ?? metrics.maas_max_score ?? 0}。`;
  box.className = `comparison-result ${className}`;
  box.replaceChildren(
    node("strong", "", title),
    node("span", "", `${result.summary || ""} ${scoreLine}`),
  );
  if (result.recommendation) {
    box.append(node("span", "", result.recommendation));
  }

  const files = result.files || [];
  const report = files.find((file) => file.name === "comparison_report.md") || (result.comparison_url ? { url: result.comparison_url } : null);
  if (report?.url) {
    const link = node("a", "", "查看对照报告");
    link.href = report.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    box.append(link);
  }

  const cases = result.cases || [];
  if (!cases.length) return;
  const list = node("div", "comparison-cases");
  cases.forEach((item) => {
    const row = node("div", `comparison-case ${item.status === "passed" ? "ready" : item.status === "warning" || item.status === "skipped" ? "blocked" : "failed"}`);
    const titleNode = node("strong", "", `${item.name || item.case_id}：${statusLabel(item.status)}`);
    const detail = node(
      "span",
      "",
      `Local ${item.local?.score ?? 0}/${item.local?.max_score ?? 0}；MaaS ${item.maas?.score ?? 0}/${item.maas?.max_score ?? 0}；Δ ${item.score_delta ?? 0}`,
    );
    row.append(titleNode, detail);
    if (item.recommendation) row.append(node("span", "", item.recommendation));
    list.append(row);
  });
  box.append(list);
}

async function loadMaaSStrategies() {
  const response = await fetch("/api/maas/strategies", { cache: "no-store" });
  if (!response.ok) throw new Error(`读取 MaaS 策略失败：${response.status}`);
  const data = await response.json();
  state.maasStrategies = data.strategies || [];
  renderMaaSStrategies();
}

function renderMaaSStrategies() {
  const box = $("#strategyResult");
  if (!box) return;
  if (!state.maasStrategies.length) {
    box.className = "strategy-result is-empty";
    box.textContent = "还没有可用策略。";
    return;
  }
  box.className = "strategy-result ready";
  box.replaceChildren(
    node("strong", "", `MaaS prompt 策略：${state.maasStrategies.length} 个`),
    node("span", "", state.maasStrategies.map((item) => item.name || item.id).join("、")),
  );
}

async function loadFailureSamples() {
  const response = await fetch("/api/evaluations/failures", { cache: "no-store" });
  if (!response.ok) throw new Error(`读取失败样本失败：${response.status}`);
  const data = await response.json();
  state.failureSamples = data.failures || [];
  renderFailureSamples();
}

function renderFailureSamples() {
  const box = $("#failureResult");
  if (!box) return;
  if (!state.failureSamples.length) {
    box.className = "strategy-result is-empty";
    box.textContent = "还没有失败样本。下一次 A/B 失败时会自动沉淀。";
    return;
  }
  box.className = "strategy-result blocked";
  box.replaceChildren(
    node("strong", "", `失败样本：${state.failureSamples.length} 个`),
    node("span", "", state.failureSamples.slice(0, 3).map((item) => item.case_id).join("、")),
  );
  const latest = state.failureSamples[0];
  if (latest?.diagnosis_url) {
    const link = node("a", "", "查看最新诊断");
    link.href = latest.diagnosis_url;
    link.target = "_blank";
    link.rel = "noreferrer";
    box.append(link);
  }
}

async function refreshFailureSamples() {
  const button = $("#refreshFailures");
  button.disabled = true;
  button.textContent = "刷新中";
  try {
    await loadFailureSamples();
    setDecision("失败样本已刷新", `${state.failureSamples.length} 个样本可用于回放。`);
  } catch (error) {
    const box = $("#failureResult");
    box.className = "strategy-result failed";
    box.replaceChildren(node("strong", "", "刷新失败"), node("span", "", error.message));
    setDecision("刷新失败样本失败", error.message);
  } finally {
    button.disabled = false;
    button.textContent = "刷新样本";
  }
}

async function replayFailureSamples() {
  const button = $("#replayFailures");
  const box = $("#failureResult");
  button.disabled = true;
  button.textContent = "回放中";
  box.className = "strategy-result";
  box.replaceChildren(
    node("strong", "", "失败样本回放中"),
    node("span", "", "正在用 MaaS 重新跑失败样本，只做本地验证，不触发云上执行。"),
  );
  try {
    const response = await fetch("/api/evaluations/failures/replay", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ max_failures: 3 }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
    state.lastReplay = result;
    renderReplaySummary(result);
    setDecision(
      result.passed ? "失败样本回放通过" : `失败样本回放：${statusLabel(result.status)}`,
      result.summary,
    );
  } catch (error) {
    box.className = "strategy-result failed";
    box.replaceChildren(node("strong", "", "回放失败"), node("span", "", error.message));
    setDecision("失败样本回放失败", error.message);
  } finally {
    button.disabled = false;
    button.textContent = "回放失败";
  }
}

function renderReplaySummary(result) {
  const box = $("#failureResult");
  if (!box || !result) return;
  const className = result.passed ? "ready" : result.status === "skipped" ? "blocked" : "failed";
  box.className = `strategy-result ${className}`;
  box.replaceChildren(
    node("strong", "", `回放结果：${statusLabel(result.status)}`),
    node("span", "", result.summary || ""),
  );
  if (result.replay_url) {
    const link = node("a", "", "查看回放报告");
    link.href = result.replay_url;
    link.target = "_blank";
    link.rel = "noreferrer";
    box.append(link);
  }
}

async function runPreExecutionReadiness() {
  const button = $("#runPreExecution");
  const box = $("#preExecutionResult");
  if (!state.lastRun?.run_id) {
    box.className = "pre-execution-result blocked";
    box.replaceChildren(
      node("strong", "", "先生成一个 run"),
      node("span", "", "完成发布包、DataArts 标准化和云资源只读验证后，再生成真实资源创建前准备包。"),
    );
    return;
  }
  button.disabled = true;
  button.textContent = "生成中";
  box.className = "pre-execution-result";
  box.replaceChildren(
    node("strong", "", "创建真实资源前准备包生成中"),
    node("span", "", "正在生成模式选择、目标环境、合规、资源蓝图、成本配额、IAM、IaC state 和 dry-run 八步材料。不会创建云资源。"),
  );
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(state.lastRun.run_id)}/pre-execution`, {
      method: "POST",
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
    state.preExecution = result;
    renderPreExecutionReadiness(result);
    setDecision(
      result.ready_for_execution_layer ? "创建前准备已完成" : "创建前准备仍有阻塞",
      result.summary,
    );
  } catch (error) {
    box.className = "pre-execution-result failed";
    box.replaceChildren(node("strong", "", "创建前准备失败"), node("span", "", error.message));
    setDecision("创建前准备失败", error.message);
  } finally {
    button.disabled = false;
    button.textContent = "生成创建前准备包";
  }
}

function renderPreExecutionReadiness(result) {
  const box = $("#preExecutionResult");
  if (!box || !result) return;
  const className = result.ready_for_execution_layer ? "ready" : result.status === "blocked" ? "blocked" : "failed";
  box.className = `pre-execution-result ${className}`;
  box.replaceChildren(
    node("strong", "", `创建真实资源前门禁：${statusLabel(result.status)}`),
    node("span", "", result.ready_for_execution_layer ? `${result.summary} 下一步：创建真实云资源。` : result.summary || ""),
  );

  const gates = result.gates || [];
  if (gates.length) {
    const list = node("div", "comparison-cases");
    gates.forEach((gate) => {
      const rowClass = gate.ready ? "ready" : gate.status === "warning" ? "blocked" : "failed";
      const row = node("div", `comparison-case ${rowClass}`);
      row.append(
        node("strong", "", `${gate.step}. ${gate.name}`),
        node("span", "", `${statusLabel(gate.status)} - ${gate.summary || ""}`),
      );
      list.append(row);
    });
    box.append(list);
  }

  if (result.report_url) {
    const link = node("a", "", "查看创建前报告");
    link.href = result.report_url;
    link.target = "_blank";
    link.rel = "noreferrer";
    box.append(link);
  }
  (result.files || [])
    .filter((file) => ["cloud_provisioning_blueprint.json", "iac_dry_run_plan.json", "real_resource_creation_approval_request.md"].includes(file.name))
    .forEach((file) => {
      const link = node("a", "", file.name === "real_resource_creation_approval_request.md" ? "打开创建审批申请" : `打开 ${file.name}`);
      link.href = file.url;
      link.target = "_blank";
      link.rel = "noreferrer";
      box.append(link);
    });
}

async function responseJson(response) {
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
  return result;
}

async function loadProductionControls(runId) {
  const authResponse = await fetch("/api/auth/me", { cache: "no-store" });
  state.productionAuth = await responseJson(authResponse);
  renderProductionAuth(state.productionAuth);

  const canUseProfiles = Boolean(
    state.productionAuth.permissions?.release || state.productionAuth.permissions?.approve_execution,
  );
  const profilePromise = canUseProfiles
    ? fetch("/api/execution-profiles", { cache: "no-store" }).then(responseJson)
    : Promise.resolve({ profiles: [] });
  const controlPromise = fetch(
    `/api/runs/${encodeURIComponent(runId)}/production-control`,
    { cache: "no-store" },
  ).then(responseJson);
  const [profiles, control] = await Promise.all([profilePromise, controlPromise]);
  state.executionProfiles = profiles.profiles || [];
  state.productionControl = control;
  renderProductionControl(control);
}

function renderProductionAuth(auth) {
  const box = $("#productionAuthSummary");
  if (!box || !auth) return;
  const modeReady = auth.production_mode && auth.authenticated;
  const executionReady = modeReady && auth.cloud_execution_enabled;
  box.className = `production-control-status ${executionReady ? "ready" : "blocked"}`;
  box.replaceChildren(
    node(
      "strong",
      "",
      modeReady ? `已认证：${auth.subject}` : "生产身份尚未启用",
    ),
    node(
      "span",
      "",
      executionReady
        ? `角色：${(auth.roles || []).join("、")}；云执行已启用。`
        : "当前保持只读或 POC 模式；生产写入不会启动。",
    ),
  );
}

function renderProductionControl(control) {
  const statusBox = $("#productionRunState");
  const list = $("#productionExecutionList");
  const profileSelect = $("#executionProfile");
  const requestButton = $("#requestExecution");
  const approveButton = $("#approveExecution");
  const cancelButton = $("#cancelExecution");
  if (!statusBox || !list || !profileSelect || !requestButton || !approveButton || !cancelButton) return;

  const release = control?.latest_release;
  const executions = control?.executions || [];
  const latest = executions[0] || null;
  const releaseHash = release?.release_hash || "";
  statusBox.className = `production-control-status ${release ? "ready" : "blocked"}`;
  statusBox.replaceChildren(
    node("strong", "", `生产状态：${statusLabel(control?.state || "draft")}`),
    node(
      "span",
      "",
      releaseHash
        ? `不可变 release hash：${releaseHash}`
        : "尚未记录生产发布包；完成产物审批并重新生成发布包。",
    ),
  );

  const selectedProfile = profileSelect.value;
  profileSelect.innerHTML = "";
  if (!state.executionProfiles.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "没有可用配置";
    profileSelect.append(option);
  } else {
    state.executionProfiles.forEach((profile) => {
      const option = document.createElement("option");
      option.value = profile.id;
      option.textContent = `${profile.label} (${profile.target})`;
      profileSelect.append(option);
    });
    if (state.executionProfiles.some((profile) => profile.id === selectedProfile)) {
      profileSelect.value = selectedProfile;
    }
  }

  const permissions = state.productionAuth?.permissions || {};
  const canRequest = Boolean(
    state.productionAuth?.cloud_execution_enabled
      && permissions.release
      && release
      && state.executionProfiles.length,
  );
  const canApprove = Boolean(
    permissions.approve_execution
      && latest?.status === "execution_requested"
      && latest.requested_by !== state.productionAuth?.subject,
  );
  const terminalStates = new Set(["succeeded", "failed", "cancelled"]);
  const canCancel = Boolean(
    latest
      && !terminalStates.has(latest.status)
      && (permissions.release || permissions.approve_execution),
  );
  profileSelect.disabled = !canRequest;
  requestButton.disabled = !canRequest;
  approveButton.disabled = !canApprove;
  cancelButton.disabled = !canCancel;

  list.innerHTML = "";
  if (!executions.length) {
    list.append(node("div", "empty-state", "暂无执行申请。"));
    return;
  }
  executions.slice(0, 8).forEach((execution) => {
    const item = node("div", "production-execution-item");
    item.append(
      node("strong", "", `${execution.target} · ${statusLabel(execution.status)}`),
      node("span", `badge ${badgeClass(execution.status)}`, statusLabel(execution.status)),
      node(
        "span",
        "",
        `申请人：${execution.requested_by}；审批人：${execution.approved_by || "待审批"}；request ${execution.request_id}`,
      ),
    );
    list.append(item);
  });
}

function renderProductionControlError(message) {
  const box = $("#productionAuthSummary");
  if (box) {
    box.className = "production-control-status failed";
    box.replaceChildren(
      node("strong", "", "生产控制不可用"),
      node("span", "", message),
    );
  }
  $("#requestExecution").disabled = true;
  $("#approveExecution").disabled = true;
  $("#cancelExecution").disabled = true;
}

async function requestProductionExecution() {
  const run = state.lastRun;
  const profileId = $("#executionProfile")?.value || "";
  const profile = state.executionProfiles.find((item) => item.id === profileId);
  if (!run || !profile) return;
  const releaseHash = state.productionControl?.latest_release?.release_hash || "";
  const input = $("#executionIdempotencyKey");
  const idempotencyKey = input.value.trim()
    || `${run.run_id}:${releaseHash.slice(0, 12)}:${profileId}:${Date.now()}`;
  input.value = idempotencyKey;
  try {
    await fetch(`/api/runs/${encodeURIComponent(run.run_id)}/execution-requests`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        profile_id: profileId,
        target: profile.target,
        parameters: {},
        idempotency_key: idempotencyKey,
        release_hash: releaseHash,
      }),
    }).then(responseJson);
    await loadProductionControls(run.run_id);
    setDecision("云执行申请已创建", "等待另一名云操作员批准后才会进入执行队列。");
  } catch (error) {
    setDecision("云执行申请失败", error.message);
  }
}

async function approveLatestExecution() {
  const run = state.lastRun;
  const execution = state.productionControl?.executions?.[0];
  if (!run || !execution) return;
  try {
    await fetch(`/api/execution-requests/${encodeURIComponent(execution.request_id)}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note: "Approved in the protected production control center." }),
    }).then(responseJson);
    await loadProductionControls(run.run_id);
    setDecision("执行申请已批准", "任务已进入受控队列，独立 Worker 将按白名单提交云作业。");
  } catch (error) {
    setDecision("执行批准失败", error.message);
  }
}

async function cancelLatestExecution() {
  const run = state.lastRun;
  const execution = state.productionControl?.executions?.[0];
  if (!run || !execution) return;
  try {
    await fetch(`/api/execution-requests/${encodeURIComponent(execution.request_id)}/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note: "Cancelled in the protected production control center." }),
    }).then(responseJson);
    await loadProductionControls(run.run_id);
    setDecision("执行已取消", "取消操作已记录到生产审计事件。");
  } catch (error) {
    setDecision("执行取消失败", error.message);
  }
}

async function loadTemplates() {
  const response = await fetch("/api/prompt-templates", { cache: "no-store" });
  if (!response.ok) throw new Error(`读取模板失败：${response.status}`);
  state.templates = await response.json();
  renderTemplateSelect();
  if (state.templates.length) {
    selectTemplate(state.templates[0].id);
  }
}

function formatChatBIValue(value, format = "number") {
  if (format === "text") return String(value ?? "");
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) return String(value ?? "");
  return new Intl.NumberFormat(window.i18n?.locale === "en" ? "en-US" : "zh-CN", {
    maximumFractionDigits: format === "integer" ? 0 : 2,
  }).format(numericValue);
}

async function queryChatBI(prompt) {
  const history = state.chatBiHistory.slice(-4).map((item) => ({
    prompt: item.prompt,
    contract: item.result?.query_plan?.semantic_contract || {},
  }));
  const response = await fetch("/api/chatbi/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, history, locale: window.i18n?.locale || "zh" }),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return response.json();
}

function renderChatBIUserTurn(prompt) {
  const turn = node("article", "chat-turn chat-turn-user");
  turn.append(node("p", "", prompt));
  $("#chatbiConversation").append(turn);
}

function renderChatBIChart(chart) {
  if (!chart?.rows?.length || !chart?.series?.length) return null;
  const series = chart.series[0];
  const values = chart.rows.map((row) => Number(row[series.key]) || 0);
  const maximum = Math.max(...values, 0);
  const section = node("section", "bi-section bi-chart-section");
  section.append(node("h2", "", chart.title || "结果对比"));
  const chartBody = node("div", "bi-bar-chart");
  chart.rows.forEach((row) => {
    const value = Number(row[series.key]) || 0;
    const item = node("div", "bi-bar-row");
    const label = node("span", "bi-bar-label", row[chart.category_key] || "未分类");
    const track = node("span", "bi-bar-track");
    const fill = node("span", "bi-bar-fill");
    fill.style.width = maximum ? `${Math.max((value / maximum) * 100, 2)}%` : "0";
    track.append(fill);
    item.append(label, track, node("strong", "bi-bar-value", formatChatBIValue(value, series.format)));
    chartBody.append(item);
  });
  section.append(chartBody);
  return section;
}

function renderChatBITable(table) {
  if (!table?.rows?.length || !table?.columns?.length) return null;
  const section = node("section", "bi-section");
  section.append(node("h2", "", "明细"));
  const wrap = node("div", "bi-table-wrap");
  const element = node("table", "bi-table");
  const head = node("thead");
  const headRow = node("tr");
  table.columns.forEach((column) => headRow.append(node("th", "", column.label)));
  head.append(headRow);
  const body = node("tbody");
  table.rows.forEach((row) => {
    const bodyRow = node("tr");
    table.columns.forEach((column) => {
      bodyRow.append(node("td", "", formatChatBIValue(row[column.key], column.format)));
    });
    body.append(bodyRow);
  });
  element.append(head, body);
  wrap.append(element);
  section.append(wrap);
  return section;
}

function renderChatBIMetadata(result) {
  const details = node("details", "bi-source");
  details.append(node("summary", "", "数据口径与查询过程"));
  const body = node("div", "bi-source-body");
  const filters = result.query_plan?.filters?.length ? result.query_plan.filters.join("、") : "当前发布批次";
  const parser = result.query_plan?.semantic_parser || {};
  const parserLabel = parser.used
    ? `${parser.model || "MaaS"} 语义解析`
    : parser.fallback
      ? "本地安全回退"
      : "本地确定性解析";
  const items = [
    ["数据集", result.query_plan?.dataset || "-"],
    ["语义解析", parserLabel],
    ["筛选条件", filters],
    ["分组", result.query_plan?.group_by || "none"],
    ["匹配记录", `${result.query_plan?.rows_matched ?? 0} / ${result.query_plan?.rows_scanned ?? 0}`],
    ["来源", result.source?.label || "-"],
    ["运行批次", result.source?.run_id || "-"],
  ];
  items.forEach(([label, value]) => {
    const row = node("div", "bi-source-row");
    row.append(node("span", "", label), node("strong", "", value));
    body.append(row);
  });
  if (result.source?.note) body.append(node("p", "bi-source-note", result.source.note));
  const compiled = result.query_plan?.compiled_query;
  if (compiled?.sql) {
    const queryDetails = node("details", "bi-compiled-query");
    queryDetails.append(node("summary", "", "查看受控 SQL"));
    queryDetails.append(node("pre", "bi-query-code", compiled.sql));
    body.append(queryDetails);
  }
  details.append(body);
  return details;
}

function renderChatBIAssistantTurn(result) {
  const turn = node("article", "chat-turn chat-turn-assistant");
  const heading = node("div", "chat-assistant-heading");
  heading.append(node("span", "assistant-mark", "A"), node("strong", "", "Agentic Tax Bigdata Demo"));
  turn.append(heading, node("p", "bi-answer", result.answer));

  if (result.kpis?.length) {
    const grid = node("section", "bi-kpi-grid");
    result.kpis.forEach((item) => {
      const metric = node("div", "bi-kpi");
      metric.append(
        node("span", "", item.label),
        node("strong", "", formatChatBIValue(item.value, item.format)),
      );
      grid.append(metric);
    });
    turn.append(grid);
  }

  const chart = renderChatBIChart(result.chart);
  if (chart) turn.append(chart);
  const table = renderChatBITable(result.table);
  if (table) turn.append(table);
  if (result.query_plan?.dataset || result.source?.label) {
    turn.append(renderChatBIMetadata(result));
  }

  if (result.suggestions?.length) {
    const suggestions = node("div", "bi-suggestions");
    suggestions.append(node("span", "", "继续查询"));
    result.suggestions.forEach((suggestion) => {
      const button = node("button", "secondary", suggestion);
      button.type = "button";
      button.addEventListener("click", () => askChatBI(suggestion));
      suggestions.append(button);
    });
    turn.append(suggestions);
  }
  $("#chatbiConversation").append(turn);
}

function renderChatBIError(message) {
  const turn = node("article", "chat-turn chat-turn-assistant");
  const heading = node("div", "chat-assistant-heading");
  heading.append(node("span", "assistant-mark", "A"), node("strong", "", "Agentic Tax Bigdata Demo"));
  turn.append(heading, node("p", "bi-answer", message));
  $("#chatbiConversation").append(turn);
}

function finishChatBITurn(prompt, result, reset = false) {
  if (reset) {
    $("#chatbiConversation").replaceChildren();
    state.chatBiHistory = [];
  }
  state.chatBiHistory.push({ prompt, result });
  renderChatBIUserTurn(prompt);
  renderChatBIAssistantTurn(result);
  setAppView("chatbi");
  requestAnimationFrame(() => window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" }));
}

async function askChatBI(prompt) {
  const query = prompt.trim();
  if (!query || state.chatBiBusy) return;
  $("#chatbiPrompt").value = "";
  setChatBIBusy(true);
  renderChatBIUserTurn(query);
  try {
    const result = await queryChatBI(query);
    if (!result.handled) {
      renderChatBIError("这个需求更像数据开发任务。请点击“新建任务”，我会进入 Agent 构建流程。");
    } else {
      state.chatBiHistory.push({ prompt: query, result });
      renderChatBIAssistantTurn(result);
    }
  } catch (error) {
    renderChatBIError(`查询失败：${error.message}`);
  } finally {
    setChatBIBusy(false);
    requestAnimationFrame(() => window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" }));
  }
}

function showAgentRunFailure(message) {
  if (state.stepEventTimer) window.clearTimeout(state.stepEventTimer);
  state.stepEventTimer = null;
  state.stepEventQueue = [];
  state.pendingCompletedRun = null;
  state.processSteps = state.processSteps.map((step) => step.status === "running"
    ? { ...step, status: "failed", output: message }
    : step);
  show("#statusMessage");
  setDecision("生成失败", message);
  $("#processProgressLabel").textContent = "任务执行失败";
  $("#processOutcome").textContent = message;
  renderProcessFlow(state.processSteps, "failed");
  show("#progressFailureActions");
}

async function runAgentPackage() {
  const prompt = $("#prompt").value.trim();
  if (!prompt) {
    $("#prompt").focus();
    return;
  }
  setBusy(true);
  closeComposerOptions();
  try {
    const chatBIResult = await queryChatBI(prompt);
    if (chatBIResult.handled) {
      state.lastPrompt = prompt;
      finishChatBITurn(prompt, chatBIResult, true);
      setBusy(false);
      return;
    }
  } catch (error) {
    console.warn("ChatBI routing failed; continuing with the engineering workflow.", error);
  }
  state.lastPrompt = prompt;
  state.selectedProcessStepId = "data_context";
  if (state.stepEventTimer) window.clearTimeout(state.stepEventTimer);
  state.stepEventQueue = [];
  state.stepEventTimer = null;
  state.pendingCompletedRun = null;
  renderUserPrompt(prompt);
  $("#progressPrompt").textContent = summarizeText(prompt, 180);
  setAppView("progress");
  show("#statusMessage");
  show("#resultMessage");
  hide("#reviewPanel");
  hide("#supportPanel");
  hide("#runtimePanel");
  prepareResultForRun(prompt);
  setDecision("正在生成", "FastAPI 正在调用 LangGraph。本地只生成文件，不触发云上生产执行。");
  scrollThreadToBottom();
  const payload = {
    prompt,
    scenario: $("#scenario").value,
    use_maas: $("#useMaaS").checked,
    template_id: state.selectedTemplate?.id || null,
    template_variables: collectTemplateVariables(),
  };
  try {
    await runAgentPackageStream(payload);
  } catch (error) {
    console.warn("Streaming run failed, falling back to non-streaming run.", error);
    setDecision("流式生成失败，正在改用普通生成", error.message);
    try {
      state.lastRun = await runAgentPackageOnce(payload);
      renderRun(state.lastRun);
    } catch (fallbackError) {
      showAgentRunFailure(fallbackError.message);
    }
  } finally {
    setBusy(false);
    scrollThreadToBottom();
  }
}

async function runAgentPackageOnce(payload) {
  const response = await fetch("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

async function runAgentPackageStream(payload) {
  const response = await fetch("/api/runs/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  if (!response.body) {
    throw new Error("当前浏览器不支持流式响应。");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    buffer = consumeSseBuffer(buffer);
  }
  consumeSseBuffer(`${buffer}\n\n`);
}

function consumeSseBuffer(buffer) {
  let remaining = buffer;
  let boundary = remaining.indexOf("\n\n");
  while (boundary >= 0) {
    const block = remaining.slice(0, boundary).trim();
    remaining = remaining.slice(boundary + 2);
    if (block) handleSseBlock(block);
    boundary = remaining.indexOf("\n\n");
  }
  return remaining;
}

function handleSseBlock(block) {
  const lines = block.split(/\r?\n/);
  let eventName = "message";
  const dataLines = [];
  lines.forEach((line) => {
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  });
  const payload = dataLines.length ? JSON.parse(dataLines.join("\n")) : {};
  handleRunEvent(eventName, payload);
}

function handleRunEvent(eventName, payload) {
  if (eventName === "run_started") {
    $("#runId").textContent = payload.run_id || "生成中";
    $("#runId").className = "badge muted";
    setDecision("正在生成", payload.message || "后端已开始执行 Agent 流程。");
    return;
  }
  if (eventName === "step_started" || eventName === "step_completed") {
    enqueueProcessStep(payload.step);
    return;
  }
  if (eventName === "run_completed") {
    state.pendingCompletedRun = payload.run;
    finishQueuedRunIfReady();
    return;
  }
  if (eventName === "run_error") {
    throw new Error(payload.message || "流式生成失败");
  }
}

function enqueueProcessStep(step) {
  state.stepEventQueue.push(step);
  if (!state.stepEventTimer) drainProcessStepQueue();
}

function drainProcessStepQueue() {
  const nextStep = state.stepEventQueue.shift();
  if (!nextStep) {
    state.stepEventTimer = null;
    finishQueuedRunIfReady();
    return;
  }
  updateProcessStep(nextStep);
  state.stepEventTimer = window.setTimeout(() => {
    state.stepEventTimer = null;
    drainProcessStepQueue();
  }, 130);
}

function finishQueuedRunIfReady() {
  if (!state.pendingCompletedRun || state.stepEventQueue.length || state.stepEventTimer) return;
  const completedRun = state.pendingCompletedRun;
  state.pendingCompletedRun = null;
  state.stepEventTimer = window.setTimeout(() => {
    state.stepEventTimer = null;
    state.lastRun = completedRun;
    renderRun(completedRun);
  }, 360);
}

function renderTemplateSelect() {
  const select = $("#templateSelect");
  select.innerHTML = "";
  const publicNames = {
    sat_taxpayer_annual_base: "Taxpayer annual base",
    sat_resico_control: "RESICO taxpayer control",
    sat_regime_reconciliation: "Regime reconciliation",
    tax_taxpayer_annual_base: "Taxpayer annual base",
    tax_resico_control: "RESICO taxpayer control",
    tax_regime_reconciliation: "Regime reconciliation",
  };
  state.templates.forEach((template) => {
    const option = document.createElement("option");
    option.value = template.id;
    option.textContent = publicNames[template.id] || template.name.replace(/^SAT\s+/i, "Tax ");
    select.append(option);
  });
}

function selectTemplate(templateId) {
  const template = state.templates.find((item) => item.id === templateId);
  state.selectedTemplate = template || null;
  if (!template) return;
  $("#templateSelect").value = template.id;
  const scenarioAliases = {
    sat_padron_base_anual: "tax_taxpayer_annual_base",
    sat_resico_control: "tax_resico_control",
    sat_regime_reconciliation: "tax_regime_reconciliation",
  };
  $("#scenario").value = scenarioAliases[template.scenario] || template.scenario;
  $("#templateSummary").textContent = template.summary;
  state.templateVariables = Object.fromEntries(template.variables.map((item) => [item.name, item.default]));
  renderTemplateFields(template);
  renderTemplateWarnings([]);
}

function renderTemplateFields(template) {
  const fields = $("#templateFields");
  fields.innerHTML = "";
  template.variables.forEach((variable) => {
    const wrap = node("div", "template-field");
    const label = document.createElement("label");
    label.htmlFor = `template_${variable.name}`;
    label.textContent = variable.label;
    const input = document.createElement("input");
    input.id = `template_${variable.name}`;
    input.name = variable.name;
    input.value = state.templateVariables[variable.name] || variable.default || "";
    input.addEventListener("input", () => {
      state.templateVariables[variable.name] = input.value;
    });
    wrap.append(label);
    wrap.append(input);
    if (variable.help) wrap.append(node("span", "", variable.help));
    fields.append(wrap);
  });
}

function collectTemplateVariables() {
  if (!state.selectedTemplate) return {};
  const values = {};
  state.selectedTemplate.variables.forEach((variable) => {
    const input = document.querySelector(`#template_${variable.name}`);
    values[variable.name] = input ? input.value : variable.default;
  });
  state.templateVariables = values;
  return values;
}

async function applyTemplate() {
  if (!state.selectedTemplate) return;
  const response = await fetch(`/api/prompt-templates/${encodeURIComponent(state.selectedTemplate.id)}/render`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ variables: collectTemplateVariables() }),
  });
  if (!response.ok) {
    const text = await response.text();
    setDecision("模板生成失败", text || `HTTP ${response.status}`);
    return;
  }
  const rendered = await response.json();
  $("#scenario").value = rendered.scenario;
  $("#prompt").value = rendered.prompt;
  setBusy(false);
  state.templateVariables = rendered.variables;
  renderTemplateWarnings(rendered.warnings);
  setDecision("模板已套用", "需求已经填入输入框。云上生产执行仍然锁定。");
}

function renderTemplateWarnings(warnings) {
  const box = $("#templateWarnings");
  if (!warnings || !warnings.length) {
    box.style.display = "none";
    box.textContent = "";
    return;
  }
  box.style.display = "block";
  box.textContent = warnings.join(" ");
}

async function loadSampleRows() {
  const response = await fetch(`/api/sample-data?scenario=${encodeURIComponent($("#scenario").value)}`);
  const data = await response.json();
  renderTable(data.rows);
  renderGoldTable([]);
  $("#rowCount").textContent = `${data.row_count} 行`;
  $("#goldRowCount").textContent = "0 gold";
}

function prepareResultForRun(prompt) {
  hide("#progressFailureActions");
  $("#runId").textContent = "生成中";
  $("#runId").className = "badge muted";
  $("#metricGrid").innerHTML = "";
  $("#packageBox").className = "package-box";
  $("#packageBox").replaceChildren(
    node("strong", "", "正在生成本地文件包"),
    node("span", "", "Agent 正在拆解需求、生成脚本和治理材料。"),
  );
  $("#agentGrid").replaceChildren(node("div", "empty-state", "Agent 输出完成后会显示在这里。"));
  state.releasePackage = null;
  state.cloudBinding = null;
  state.importReview = null;
  renderReleasePackage(null);
  renderDeploymentPreflight(null);
  renderCloudBinding(null);
  renderImportReview(null);
  state.processSteps = buildPendingProcess(prompt);
  renderProcessFlow(state.processSteps, "running");
}

function renderRun(run) {
  hide("#progressFailureActions");
  const cloudVerified = Boolean(state.cloudEvidence?.available && state.cloudEvidence?.status === "success");
  if (cloudVerified) {
    run.bigdata_execution = {
      ...run.bigdata_execution,
      deployed: true,
      reason: "MRS/OBS 基准作业已验证，DataArts 编排资产已创建；本次新生成包仍需完成 PySpark、SQL 和 DAG 审批。",
    };
    run.quality_gates = (run.quality_gates || []).map((gate) => gate.id === "FG-006"
      ? { ...gate, detail: "真实云环境已就绪；当前生成包尚未取得三项核心产物审批，因此继续保持生产锁。" }
      : gate);
  }
  show("#resultMessage");
  show("#reviewPanel");
  show("#supportPanel");
  show("#runtimePanel");
  $("#runId").textContent = run.run_id;
  $("#runId").className = "badge ready";
  $("#resultRunId").textContent = run.run_id;
  $("#overviewRunId").textContent = run.run_id;
  $("#resultTitle").textContent = taskDisplayName(run.business_contract || {});
  $("#resultPrompt").textContent = summarizeText(state.lastPrompt, 180);
  state.selectedProcessStepId = run.contract_audit?.status === "failed" ? "contract_audit" : "business_contract";
  renderProcessFlow(buildCompletedProcess(run), "done");
  renderMetrics(run);
  renderContractSummary(run.business_contract || {});
  renderPackage(run);
  renderAgents(run.agents);
  renderGates(run.quality_gates);
  renderArtifacts(run.artifacts);
  renderReleasePackage(null, run);
  loadReleasePackageStatus(run.run_id).catch((error) => {
    renderReleasePackage({
      status: "failed",
      ready: false,
      message: error.message,
      missing_approvals: [],
      failed_gates: [],
      release: {},
    }, run);
  });
  loadProductionControls(run.run_id).catch((error) => {
    renderProductionControlError(error.message);
  });
  renderTable(run.synthetic_rows);
  renderGoldTable(run.gold_rows || []);
  renderLineage(run.lineage);
  $("#rowCount").textContent = `${run.synthetic_rows.length} 行预览`;
  $("#goldRowCount").textContent = `${(run.gold_rows || []).length} gold`;

  const prod = run.decision.production;
  const local = run.decision.local_dev;
  const executionReason = window.i18n?.t(run.bigdata_execution.reason) || run.bigdata_execution.reason;
  setDecision(
    `本地开发：${statusLabel(local)}；生产执行：${statusLabel(prod)}`,
    window.i18n?.locale === "en"
      ? `${executionReason} Generation mode: ${run.execution_mode}.`
      : `${executionReason} 生成模式：${run.execution_mode}。`,
  );
  selectResultTab("overview");
  setAppView("result");
}

function taskDisplayName(contract) {
  const names = {
    tax_taxpayer_annual_base: "Tax 纳税人年度基础表",
    tax_resico_control: "RESICO 纳税人控制",
    tax_regime_reconciliation: "Tax 税制核对",
  };
  const name = names[contract.task_id] || summarizeText(contract.business_goal, 48) || "数据任务结果";
  return window.i18n?.t(name) || name;
}

function updateProcessStep(step) {
  if (!step?.id) return;
  const existingIndex = state.processSteps.findIndex((item) => item.id === step.id);
  if (existingIndex >= 0) {
    state.processSteps[existingIndex] = { ...state.processSteps[existingIndex], ...step };
  } else if (step.id === "artifact_branch") {
    const artifactIndex = state.processSteps.findIndex((item) => item.id === "artifact_package");
    state.processSteps.splice(Math.max(artifactIndex + 1, 0), 0, step);
  } else {
    state.processSteps.push(step);
  }
  if (step.status === "running" || step.status === "failed") state.selectedProcessStepId = step.id;
  renderProcessFlow(state.processSteps, "running");
  scrollThreadToBottom();
}

function buildPendingProcess(prompt) {
  return [
    {
      id: "data_context",
      step: "Step 1",
      title: "数据上下文预检",
      status: "running",
      note: "先准备字段、样例和脱敏约束，给后续 Agent 做上下文。",
      input: `场景=${taskDisplayName({ task_id: $("#scenario").value })}；本地合成数据；云上执行锁定。`,
      output: "准备字段画像、脱敏样例数据和聚合预览。",
    },
    {
      id: "prompt",
      step: "Step 2",
      title: "接收业务 Prompt",
      status: "pending",
      note: "把你的自然语言需求接入已经准备好的数据上下文。",
      input: summarizeText(prompt, 180),
      output: "等待业务分析 Agent 合并 prompt 与数据上下文。",
    },
    {
      id: "business_contract",
      step: "Step 3",
      title: "业务分析 Agent",
      status: "pending",
      note: "把口语化需求变成可审计的业务合约。",
      input: "Prompt + 数据上下文 + MaaS 选择。",
      output: "将生成结构化 business_contract.yaml，包含数据源、指标、维度、脱敏、质量和审批规则。",
    },
    {
      id: "contract_audit",
      step: "Step 4",
      title: "合约一致性审计",
      status: "pending",
      note: "先检查合约有没有和字段、指标、产物清单、本地执行适配器、审批策略对齐。",
      input: "business_contract.yaml + 本地字段上下文 + PySpark/SQL/DAG 适配器支持范围。",
      output: "将生成 contract_audit.json，通过后再按合约生成脚本。",
    },
    {
      id: "artifact_package",
      step: "Step 5",
      title: "代码与编排 Agents",
      status: "pending",
      note: "把合约里的维度、指标、过滤条件和审批策略拆成 PySpark、SQL 和 DataArts DAG。",
      input: "业务合约 + 本地样例字段结构。",
      output: "将按 business_contract.yaml 生成 mrs_transform.py、dws_serving.sql、dataarts_dag.yaml。",
    },
    {
      id: "local_dry_run",
      step: "Step 6",
      title: "本地试运行 Agent",
      status: "pending",
      note: "用本地合成数据跑一次等价执行，并对账指标结果和脱敏约束。",
      input: "生成脚本 + synthetic_rows.json + business_contract.yaml。",
      output: "将生成 execution_report.json、local_run_output.json、metric_reconciliation.json。",
    },
    {
      id: "governance",
      step: "Step 7",
      title: "治理审计 Agent",
      status: "pending",
      note: "检查质量规则、安全策略、血缘和生产锁。",
      input: "全部产物 + 本地试运行结果 + 样例数据 + MaaS 配置状态。",
      output: "将生成 quality_gates、security_review 和 lineage。",
    },
    {
      id: "persist",
      step: "Step 8",
      title: "落盘与人工确认",
      status: "pending",
      note: "本地文件生成后写入 generated/，生产部署仍需人工批准。",
      input: "等待 PySpark、SQL、DAG 等产物完成。",
      output: "将生成 run_manifest.json 和 review_status.json。",
    },
  ];
}

function buildCompletedProcess(run) {
  const prompt = state.lastPrompt || $("#prompt").value;
  const requiredReview = run.artifacts.filter((artifact) => artifact.review_required).map((artifact) => artifact.name);
  const gateSummary = summarizeGates(run.quality_gates);
  const contractMetrics = run.business_contract.metrics || [];
  const contractDimensions = run.business_contract.dimensions || [];
  const contractAudit = run.contract_audit || {};
  const localExecution = run.local_execution || {};
  return [
    {
      id: "data_context",
      step: "Step 1",
      title: "数据上下文预检",
      status: "ready",
      note: "先准备字段、样例和脱敏规则，再进入 prompt 转换。",
      input: `场景=${taskDisplayName(run.business_contract)}；本地合成数据源；直接 RFC 不进入 UI。`,
      output: `已准备 ${run.synthetic_rows.length} 行预览，并生成 local_synthetic_rows.json、gold_preview.json。`,
    },
    {
      id: "prompt",
      step: "Step 2",
      title: "接收业务 Prompt",
      status: "ready",
      note: "入口只接收业务需求，不直接执行云上任务。",
      input: summarizeText(prompt, 180),
      output: `已绑定数据上下文。模板：${run.business_contract.template_id}。`,
    },
    {
      id: "business_contract",
      step: "Step 3",
      title: "业务分析 Agent",
      status: "ready",
      note: "把 prompt 收敛成可审计、可落盘的业务合约。",
      input: "原始 prompt + 数据样例/字段上下文 + MaaS/本地摘要。",
      output: `生成结构化 business_contract.yaml：${contractDimensions.length} 个维度、${contractMetrics.length} 个指标。业务目标：${summarizeText(run.business_contract.business_goal, 130)}`,
    },
    {
      id: "contract_audit",
      step: "Step 4",
      title: "合约一致性审计",
      status: contractAudit.status === "failed" ? "failed" : "ready",
      note: "把业务合约和本地字段、PySpark/SQL/DAG 适配器、产物清单、审批策略逐项对齐。",
      input: "business_contract.yaml + 本地字段上下文 + PySpark/SQL/DAG 适配器支持范围。",
      output: summarizeAudit(contractAudit),
    },
    {
      id: "artifact_package",
      step: "Step 5",
      title: "代码与编排 Agents",
      status: "ready",
      note: "根据业务合约里的维度、指标、过滤条件和审批策略生成脚本草稿。",
      input: "business_contract.yaml + contract_audit.json + 目标华为云大数据服务映射。",
      output: `${artifactNames(run, ["pyspark", "sql", "dag"])}，均由业务合约派生。`,
    },
    {
      id: "artifact_branch",
      type: "branch",
      step: "Output",
      title: "产物分叉",
      branches: [
        {
          title: "PySpark",
          detail: artifactNames(run, ["pyspark"]),
        },
        {
          title: "SQL",
          detail: artifactNames(run, ["sql"]),
        },
        {
          title: "DataArts DAG",
          detail: artifactNames(run, ["dag"]),
        },
      ],
    },
    {
      id: "local_dry_run",
      step: "Step 6",
      title: "本地试运行 Agent",
      status: localExecution.status === "failed" ? "failed" : "ready",
      note: "用本地合成数据跑一次等价执行，并对账脚本语义、指标结果和脱敏约束。",
      input: "mrs_transform.py + dws_serving.sql + dataarts_dag.yaml + synthetic_rows.json + business_contract.yaml。",
      output: summarizeLocalExecution(localExecution),
    },
    {
      id: "governance",
      step: "Step 7",
      title: "治理审计 Agent",
      status: run.bigdata_execution.state === "blocked" ? "blocked" : "ready",
      note: "质量、安全、血缘和审批状态在这里统一判断。",
      input: "全部脚本产物 + 本地试运行结果 + 样例数据 + MaaS 配置状态。",
      output: `${gateSummary}；生成 ${artifactNames(run, ["audit"])}；生产执行：${statusLabel(run.bigdata_execution.state)}。`,
    },
    {
      id: "persist",
      step: "Step 8",
      title: "落盘与人工确认",
      status: "blocked",
      note: "本地文件已生成，但生产部署仍需人工批准。",
      input: requiredReview.length
        ? `需要确认：${requiredReview.join(window.i18n?.locale === "en" ? ", " : "、")}`
        : "当前产物无需人工确认。",
      output: `文件目录：generated/${run.run_id}`,
    },
  ];
}

function renderProcessFlow(steps, stateName) {
  const flow = $("#processFlow");
  const badge = $("#processBadge");
  if (badge) {
    badge.textContent = stateName === "done" ? "完成" : "进行中";
    badge.className = `badge ${stateName === "done" ? "ready" : "muted"}`;
  }

  const processSteps = steps.filter((step) => step.type !== "branch");
  const completedSteps = processSteps.filter((step) => !["pending", "running"].includes(step.status));
  const failedSteps = processSteps.filter((step) => step.status === "failed");
  const runningStep = processSteps.find((step) => step.status === "running");
  const progress = processSteps.length ? Math.round((completedSteps.length / processSteps.length) * 100) : 0;
  $("#processProgressBar").style.width = `${stateName === "done" ? 100 : progress}%`;
  $("#processCount").textContent = `${stateName === "done" ? processSteps.length : completedSteps.length} / ${processSteps.length}`;
  $("#processProgressLabel").textContent = failedSteps.length
    ? `${failedSteps.length} 个步骤失败`
    : stateName === "done"
      ? `${processSteps.length} 个步骤已完成`
      : runningStep
        ? `正在执行：${runningStep.title}`
        : "正在准备执行流程";
  $("#processOutcome").textContent = failedSteps.length
    ? failedSteps[0].output || failedSteps[0].note
    : stateName === "done"
      ? "生成与本地验证已完成，生产执行仍受人工审批控制。"
      : runningStep?.note || "等待下一步骤。";

  const selected = steps.find((step) => step.id === state.selectedProcessStepId) || runningStep || steps[0];
  if (selected) state.selectedProcessStepId = selected.id;
  flow.innerHTML = "";
  const stepList = node("div", "process-step-list");
  steps.forEach((step) => stepList.append(renderProcessStep(step, selected?.id === step.id, steps, stateName)));
  flow.append(stepList, renderProcessInspector(selected));
}

function renderProcessStep(step, isSelected, steps, stateName) {
  const status = step.type === "branch" ? "generated" : step.status;
  const button = node("button", `process-step${isSelected ? " is-selected" : ""}`);
  button.type = "button";
  button.dataset.stepId = step.id || "";
  button.dataset.status = status || "pending";
  button.append(node("span", "step-status-dot"));
  const copy = node("span", "step-copy");
  copy.append(node("strong", "", step.title));
  copy.append(node("span", "", step.step));
  button.append(copy, node("span", `badge ${badgeClass(status)}`, statusLabel(status)));
  button.addEventListener("click", () => {
    state.selectedProcessStepId = step.id;
    renderProcessFlow(steps, stateName);
  });
  return button;
}

function renderProcessInspector(step) {
  const inspector = node("section", "process-inspector");
  if (!step) {
    inspector.append(node("div", "empty-state", "尚未收到执行步骤。"));
    return inspector;
  }
  const heading = node("div", "inspector-heading");
  heading.append(node("span", "page-kicker", step.step));
  heading.append(node("h3", "", step.title));
  heading.append(node("p", "", step.note || "查看该步骤产生的输出。"));
  inspector.append(heading);

  if (step.type === "branch") {
    const grid = node("div", "branch-grid");
    (step.branches || []).forEach((branch) => {
      const card = node("div", "branch-card");
      card.append(node("strong", "", branch.title));
      card.append(node("span", "", branch.detail));
      grid.append(card);
    });
    inspector.append(grid);
    return inspector;
  }

  const card = node("div", "io-card");
  card.append(renderIoRow("输入", step.input));
  card.append(renderIoRow("输出", step.output));
  inspector.append(card);
  return inspector;
}

function renderIoRow(label, value) {
  const row = node("div", "io-row");
  row.append(node("strong", "", label));
  row.append(node("p", "", value));
  return row;
}

function summarizeText(value, maxLength = 120) {
  const normalized = String(value || "").replace(/\s+/g, " ").trim();
  if (!normalized) return "无";
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength - 3)}...` : normalized;
}

function artifactNames(run, kinds) {
  const names = run.artifacts
    .filter((artifact) => kinds.includes(artifact.kind))
    .map((artifact) => artifact.name);
  return names.length ? names.join(window.i18n?.locale === "en" ? ", " : "、") : (window.i18n?.locale === "en" ? "None" : "无");
}

function summarizeGates(gates) {
  const passed = gates.filter((gate) => gate.status === "passed").length;
  const failed = gates.filter((gate) => gate.status === "failed").length;
  const blocked = gates.filter((gate) => gate.status === "blocked").length;
  return `质量检查：${passed} 个通过，${failed} 个失败，${blocked} 个锁定`;
}

function summarizeAudit(audit) {
  const findings = audit?.findings || [];
  if (!findings.length) return "未返回审计结果。";
  const passed = findings.filter((item) => item.status === "passed").length;
  const warnings = findings.filter((item) => item.status === "warning").length;
  const failed = findings.filter((item) => item.status === "failed").length;
  const firstIssue = findings.find((item) => item.status === "failed") || findings.find((item) => item.status === "warning");
  const issueText = firstIssue ? ` 首个问题：${firstIssue.name}，${firstIssue.detail}` : "";
  return `生成 contract_audit.json：${passed} 项通过、${warnings} 项提醒、${failed} 项失败。${issueText}`;
}

function summarizeLocalExecution(execution) {
  const report = execution?.execution_report || {};
  const reconciliation = execution?.metric_reconciliation || {};
  const checks = reconciliation.checks || [];
  if (!checks.length) return "未返回本地试运行结果。";
  const passed = checks.filter((item) => item.status === "passed").length;
  const failed = checks.filter((item) => item.status === "failed").length;
  const firstFailure = checks.find((item) => item.status === "failed");
  const issueText = firstFailure ? ` 首个问题：${firstFailure.name}，${firstFailure.detail}` : "";
  return `生成 execution_report.json、local_run_output.json、metric_reconciliation.json：输入 ${report.input_rows ?? 0} 行，输出 ${report.output_rows ?? 0} 行，${passed} 项通过、${failed} 项失败。${issueText}`;
}

function renderMetrics(run) {
  const maasValue = run.maas.used ? "已使用" : run.maas.configured ? "已配置" : "本地兜底";
  const localExecutionValue = run.local_execution?.status === "passed" ? "已通过" : run.local_execution?.status || "未运行";
  const metrics = [
    ["生成模式", run.execution_mode],
    ["MaaS", maasValue],
    ["本地试运行", localExecutionValue],
    ["子任务", String(run.agents.length)],
    ["人工确认", reviewSummary(run.review)],
    ["云上执行", statusLabel(run.bigdata_execution.state)],
  ];
  const grid = $("#metricGrid");
  grid.innerHTML = "";
  metrics.forEach(([label, value]) => {
    const card = node("div", "metric");
    card.append(node("span", "", label));
    card.append(node("strong", "", value));
    grid.append(card);
  });
}

function renderContractSummary(contract) {
  const sourceValues = (contract.data_sources || []).map((item) => {
    if (typeof item === "string") return item;
    return item.uri || item.source_uri || item.name || JSON.stringify(item);
  });
  const parameters = [
    ["任务", taskDisplayName(contract)],
    ["数据粒度", contract.grain],
    ["数据来源", sourceValues],
    ["过滤条件", contract.filters],
    ["维度", contract.dimensions],
    ["指标", (contract.metrics || []).map((item) => typeof item === "string" ? item : item.name || JSON.stringify(item))],
    ["隐私规则", contract.privacy],
    ["审批策略", contract.approval_policy],
  ];
  const grid = $("#contractSummary");
  grid.innerHTML = "";
  parameters.forEach(([label, value]) => {
    const item = node("div", "parameter-item");
    item.append(node("span", "", label), node("strong", "", formatParameterValue(value)));
    grid.append(item);
  });
}

function formatParameterValue(value) {
  if (Array.isArray(value)) {
    return value.length ? value.join(window.i18n?.locale === "en" ? ", " : "、") : (window.i18n?.locale === "en" ? "None" : "无");
  }
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value || (window.i18n?.locale === "en" ? "None" : "无"));
}

function renderPackage(run) {
  const box = $("#packageBox");
  const manifestUrl = `${run.generated_url}run_manifest.json`;
  box.className = "package-box ready";
  box.replaceChildren(
    node("strong", "", "本地文件包已生成"),
    node("span", "", `generated/${run.run_id}`),
  );
  const link = node("a", "", "查看清单");
  link.href = manifestUrl;
  link.target = "_blank";
  link.rel = "noreferrer";
  box.append(link);
}

async function loadReleasePackageStatus(runId) {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/release-package`, { cache: "no-store" });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  state.releasePackage = await response.json();
  renderReleasePackage(state.releasePackage, state.lastRun);
}

async function generateReleasePackage() {
  const run = state.lastRun;
  if (!run) return;
  const button = $("#generateRelease");
  button.disabled = true;
  button.textContent = "生成中";
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(run.run_id)}/release-package`, {
      method: "POST",
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
    state.releasePackage = result;
    renderReleasePackage(result, run);
    await loadProductionControls(run.run_id).catch((error) => {
      renderProductionControlError(error.message);
    });
    setDecision(
      result.status === "generated" ? "发布候选包已生成" : "发布候选包未生成",
      `${result.message} 发布前检查会继续保持云上执行锁定。`,
    );
  } catch (error) {
    renderReleasePackage({
      status: "failed",
      ready: false,
      message: error.message,
      missing_approvals: [],
      failed_gates: [],
      release: {},
    }, run);
    setDecision("发布候选包生成失败", error.message);
  }
}

function renderReleasePackage(release, run = state.lastRun) {
  const box = $("#releaseBox");
  const button = $("#generateRelease");
  if (!box || !button) return;

  if (!run) {
    button.disabled = true;
    button.textContent = "生成发布包";
    box.className = "release-box blocked";
    box.replaceChildren(
      node("strong", "", "发布候选包未就绪"),
      node("span", "", "通过 PySpark、SQL、DataArts DAG 后，才能生成本地 DataArts 预导入包。"),
      button,
    );
    renderDeploymentPreflight(null);
    renderImportReview(null);
    return;
  }

  const status = release?.status || "blocked";
  const ready = Boolean(release?.ready);
  const missing = release?.missing_approvals || [];
  const failedGates = release?.failed_gates || [];
  const generated = status === "generated";
  const className = generated || ready ? "ready" : status === "failed" ? "failed" : "blocked";
  const title = generated
    ? "发布候选包已生成"
    : ready
      ? "发布候选包就绪"
      : "发布候选包未就绪";
  const detail = releaseMessage(release, missing, failedGates);

  button.disabled = !ready || generated;
  button.textContent = generated ? "已生成" : "生成发布包";
  box.className = `release-box ${className}`;
  box.replaceChildren(node("strong", "", title), node("span", "", detail));

  if (generated) {
    const files = release?.release?.files || [];
    const manifest = files.find((file) => file.name === "release_manifest.json") || release?.release;
    const importPackage = files.find((file) => file.name === "dataarts_import_package.json");
    if (manifest?.url || release?.release?.release_url) {
      const link = node("a", "", "查看发布清单");
      link.href = manifest.url || release.release.release_url;
      link.target = "_blank";
      link.rel = "noreferrer";
      box.append(link);
    }
    if (importPackage?.url) {
      const link = node("a", "", "查看 DataArts 预导入包");
      link.href = importPackage.url;
      link.target = "_blank";
      link.rel = "noreferrer";
      box.append(link);
    }
  }

  box.append(button);
  renderDeploymentPreflight(generated ? release?.release : null, run);
  if (generated) {
    renderCloudBinding(null, release?.release, run);
    renderDataArtsStandardization(null, release?.release, run);
    loadCloudBindingStatus(run.run_id).catch((error) => {
      renderCloudBinding({
        status: "failed",
        ready_for_import_review: false,
        cloud_execution: "blocked",
        message: error.message,
        binding: {},
        missing_bindings: [],
        failed_checks: [],
      }, release?.release, run);
    });
    loadDataArtsStandardizationStatus(run.run_id).catch((error) => {
      renderDataArtsStandardization({
        status: "failed",
        ready_for_cloud_probe: false,
        cloud_execution: "blocked",
        message: error.message,
        standardization: {},
        failed_checks: [],
      }, release?.release, run);
    });
  } else {
    renderCloudBinding(null, null, run);
    renderDataArtsStandardization(null, null, run);
  }
}

function releaseMessage(release, missing, failedGates) {
  if (!release) return "正在读取审批状态。";
  if (release.status === "generated") return `本地发布候选包已生成，云上执行仍然锁定。已写入 generated/${release.run_id}/release/。`;
  if (release.ready) return "三个可执行产物已经通过人工确认，可以生成本地发布候选包；不会触发云上执行。";
  const parts = [];
  if (missing.length) parts.push(`待确认：${missing.join("、")}`);
  if (failedGates.length) parts.push(`失败门禁：${failedGates.join("、")}`);
  return parts.length ? parts.join("；") : release.message;
}

function renderDeploymentPreflight(releaseStatus, run = state.lastRun) {
  const box = $("#preflightBox");
  if (!box) return;

  if (!run) {
    box.className = "preflight-box blocked";
    box.replaceChildren(
      node("strong", "", "发布前检查未运行"),
      node("span", "", "生成发布候选包后，会检查目标华为云环境、OBS 分层、安全策略、参数绑定和执行锁。"),
    );
    return;
  }

  if (!releaseStatus?.preflight) {
    box.className = "preflight-box blocked";
    box.replaceChildren(
      node("strong", "", "发布前检查等待发布包"),
      node("span", "", "先完成三份核心产物审批并生成发布候选包。云上执行仍然锁定。"),
    );
    return;
  }

  const preflight = releaseStatus.preflight;
  const environment = releaseStatus.environment || {};
  const failed = Number(preflight.failed || 0);
  box.className = `preflight-box ${failed ? "failed" : "blocked"}`;
  const layers = environment.storage_layers?.join(" / ") || "raw / silver / gold / release / audit";
  const detail = `区域 ${environment.region || "la-south-2"}；OBS ${layers}；${preflight.summary}；云上执行：${statusLabel(preflight.cloud_execution)}。`;
  box.replaceChildren(
    node("strong", "", failed ? "发布前检查需修复" : "发布前检查完成，等待云环境绑定"),
    node("span", "", detail),
  );

  const files = releaseStatus.files || [];
  [
    ["deployment_preflight.json", "查看发布前检查"],
    ["environment_profile.yaml", "查看环境合约"],
    ["cloud_parameter_map.json", "查看云参数映射"],
  ].forEach(([name, label]) => {
    const file = files.find((item) => item.name === name);
    if (!file?.url) return;
    const link = node("a", "", label);
    link.href = file.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    box.append(link);
  });
}

async function loadCloudBindingStatus(runId) {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/cloud-binding`, { cache: "no-store" });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  state.cloudBinding = await response.json();
  renderCloudBinding(state.cloudBinding, state.releasePackage?.release, state.lastRun);
}

async function generateCloudBindingSimulation() {
  const run = state.lastRun;
  if (!run) return;
  const button = $("#simulateBinding");
  button.disabled = true;
  button.textContent = "模拟中";
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(run.run_id)}/cloud-binding`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: "local_simulation",
        reviewer: "local_operator",
        note: "Local simulation for cloud import readiness. No cloud service is called.",
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
    state.cloudBinding = result;
    renderCloudBinding(result, state.releasePackage?.release, run);
    setDecision(
      result.ready_for_import_review ? "云参数本地模拟通过" : "云参数绑定需修复",
      `${result.message} 云上执行仍然锁定。`,
    );
  } catch (error) {
    renderCloudBinding({
      status: "failed",
      ready_for_import_review: false,
      cloud_execution: "blocked",
      message: error.message,
      binding: {},
      missing_bindings: [],
      failed_checks: [],
    }, state.releasePackage?.release, run);
    setDecision("云参数绑定失败", error.message);
  }
}

function renderCloudBinding(binding, releaseStatus = state.releasePackage?.release, run = state.lastRun) {
  const box = $("#bindingBox");
  const button = $("#simulateBinding");
  if (!box || !button) return;

  if (!run) {
    button.disabled = true;
    button.textContent = "本地模拟绑定";
    box.className = "binding-box blocked";
    box.replaceChildren(
      node("strong", "", "云参数绑定未开始"),
      node("span", "", "发布前检查完成后，可生成一份本地模拟绑定，用于验证 DataArts 导入参数，不会连接云服务。"),
      button,
    );
    renderImportReview(null);
    return;
  }

  if (!releaseStatus?.preflight) {
    button.disabled = true;
    button.textContent = "本地模拟绑定";
    box.className = "binding-box blocked";
    box.replaceChildren(
      node("strong", "", "云参数绑定等待发布前检查"),
      node("span", "", "先生成发布候选包和发布前检查结果。"),
      button,
    );
    renderImportReview(null, binding, run);
    return;
  }

  const status = binding?.status || "needs_binding";
  const ready = Boolean(binding?.ready_for_import_review);
  const className = ready ? "ready" : status === "failed" || status === "needs_fix" ? "failed" : "blocked";
  const requiredCount = Object.keys(releaseStatus.environment?.cloud_parameters || {}).length;
  const missing = binding?.missing_bindings || [];
  const failed = binding?.failed_checks || [];
  const title = ready
    ? "云参数本地模拟通过"
    : failed.length
      ? "云参数绑定需修复"
      : "云参数绑定待模拟";
  const detail = ready
    ? `已验证 ${requiredCount} 个云参数映射，生成解析后的 DataArts 导入预览；云上执行：${statusLabel(binding.cloud_execution)}。`
    : missing.length
      ? `待绑定 ${missing.length} 个参数：${missing.slice(0, 5).join("、")}${missing.length > 5 ? "..." : ""}`
      : "使用本地模拟值验证参数映射；不会连接 OBS、MRS、DWS 或 DataArts。";

  button.disabled = ready;
  button.textContent = ready ? "模拟通过" : "本地模拟绑定";
  box.className = `binding-box ${className}`;
  box.replaceChildren(node("strong", "", title), node("span", "", detail));

  const files = binding?.binding?.files || [];
  [
    ["cloud_binding_simulation.json", "查看绑定模拟"],
    ["resolved_dataarts_import_package.json", "查看解析后导入包"],
    ["cloud_import_readiness.json", "查看导入就绪检查"],
  ].forEach(([name, label]) => {
    const file = files.find((item) => item.name === name);
    if (!file?.url) return;
    const link = node("a", "", label);
    link.href = file.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    box.append(link);
  });
  box.append(button);

  if (ready) {
    renderImportReview(null, binding, run);
    loadImportReviewStatus(run.run_id).catch((error) => {
      renderImportReview({
        status: "failed",
        ready_for_operator_handoff: false,
        cloud_execution: "blocked",
        message: error.message,
        review: {},
        failed_checks: [],
      }, binding, run);
    });
  } else {
    renderImportReview(null, binding, run);
  }
}

async function loadImportReviewStatus(runId) {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/import-review`, { cache: "no-store" });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  state.importReview = await response.json();
  renderImportReview(state.importReview, state.cloudBinding, state.lastRun);
}

async function generateImportReview() {
  const run = state.lastRun;
  if (!run) return;
  const button = $("#generateImportReview");
  button.disabled = true;
  button.textContent = "复核中";
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(run.run_id)}/import-review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reviewer: "local_operator",
        note: "Local import review handoff. No Huawei Cloud service is called.",
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
    state.importReview = result;
    renderImportReview(result, state.cloudBinding, run);
    setDecision(
      result.ready_for_operator_handoff ? "导入复核交接包已生成" : "导入复核需修复",
      `${result.message} 云上执行仍然锁定。`,
    );
  } catch (error) {
    renderImportReview({
      status: "failed",
      ready_for_operator_handoff: false,
      cloud_execution: "blocked",
      message: error.message,
      review: {},
      failed_checks: [],
    }, state.cloudBinding, run);
    setDecision("导入复核失败", error.message);
  }
}

async function loadDataArtsStandardizationStatus(runId) {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/dataarts-standardization`, { cache: "no-store" });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  state.dataArtsStandardization = await response.json();
  renderDataArtsStandardization(state.dataArtsStandardization, state.releasePackage?.release, state.lastRun);
}

async function generateDataArtsStandardization() {
  const run = state.lastRun;
  if (!run) return;
  const button = $("#standardizeDataArts");
  button.disabled = true;
  button.textContent = "标准化中";
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(run.run_id)}/dataarts-standardization`, {
      method: "POST",
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
    state.dataArtsStandardization = result;
    renderDataArtsStandardization(result, state.releasePackage?.release, run);
    setDecision(
      result.ready_for_cloud_probe ? "DataArts 标准包已就绪" : "DataArts 标准包需要修复",
      `${result.message} 云上执行仍保持锁定。`,
    );
  } catch (error) {
    renderDataArtsStandardization({
      status: "failed",
      ready_for_cloud_probe: false,
      cloud_execution: "blocked",
      message: error.message,
      standardization: {},
      failed_checks: [],
    }, state.releasePackage?.release, run);
    setDecision("DataArts 标准化失败", error.message);
  }
}

function renderDataArtsStandardization(result, releaseStatus = state.releasePackage?.release, run = state.lastRun) {
  const box = $("#dataArtsStandardBox");
  const button = $("#standardizeDataArts");
  if (!box || !button) return;

  if (!run || !releaseStatus?.preflight) {
    button.disabled = true;
    button.textContent = "标准化 DataArts";
    box.className = "binding-box blocked";
    box.replaceChildren(
      node("strong", "", "DataArts 标准包未生成"),
      node("span", "", "请先生成发布包；此步骤不会触发云上执行。"),
      button,
    );
    renderCloudResourceProbe(null, result, run);
    return;
  }

  const status = result?.status || "ready";
  const ready = Boolean(result?.ready_for_cloud_probe);
  const failed = result?.failed_checks || [];
  const className = ready ? "ready" : status === "failed" || status === "needs_fix" ? "failed" : "blocked";
  const title = ready
    ? "DataArts 标准包已就绪"
    : failed.length
      ? "DataArts 标准包需要修复"
      : "DataArts 标准包待生成";
  const detail = ready
    ? `Schema dataarts.factory.import.v1alpha1 已通过；云上执行：${statusLabel(result.cloud_execution)}。`
    : failed.length
      ? `失败检查：${failed.slice(0, 3).join("；")}${failed.length > 3 ? "..." : ""}`
      : "在资源探测前，将预览包转换为稳定的 DataArts 导入合约。";

  button.disabled = ready;
  button.textContent = ready ? "已标准化" : "标准化 DataArts";
  box.className = `binding-box ${className}`;
  box.replaceChildren(node("strong", "", title), node("span", "", detail));

  const files = result?.standardization?.files || [];
  [
    ["dataarts_import_standard_schema.json", "查看 Schema"],
    ["dataarts_import_standard_package.json", "查看标准包"],
    ["dataarts_import_validation.json", "查看验证结果"],
  ].forEach(([name, label]) => {
    const file = files.find((item) => item.name === name);
    if (!file?.url) return;
    const link = node("a", "", label);
    link.href = file.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    box.append(link);
  });
  box.append(button);

  if (ready) {
    renderCloudResourceProbe(null, result, run);
    loadCloudResourceProbeStatus(run.run_id).catch((error) => {
      renderCloudResourceProbe({
        status: "failed",
        ready_for_operator_execution_request: false,
        real_cloud_verified: false,
        cloud_execution: "blocked",
        message: error.message,
        probe: {},
        missing_bindings: [],
        failed_checks: [],
      }, result, run);
    });
  } else {
    renderCloudResourceProbe(null, result, run);
  }
}

async function loadCloudResourceProbeStatus(runId) {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/cloud-resource-probe`, { cache: "no-store" });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  state.cloudResourceProbe = await response.json();
  renderCloudResourceProbe(state.cloudResourceProbe, state.dataArtsStandardization, state.lastRun);
}

async function runCloudResourceProbe() {
  const run = state.lastRun;
  if (!run) return;
  const button = $("#runCloudProbe");
  button.disabled = true;
  button.textContent = "验证中";
  try {
    const source = state.cloudBinding?.ready_for_import_review ? "existing_binding" : "environment";
    const response = await fetch(`/api/runs/${encodeURIComponent(run.run_id)}/cloud-resource-probe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source,
        allow_network_probe: state.allowNetworkProbe,
        reviewer: "local_operator",
        note: "Validate existing Huawei Cloud resources with read-only checks. No cloud write call is allowed.",
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
    state.cloudResourceProbe = result;
    renderCloudResourceProbe(result, state.dataArtsStandardization, run);
    setDecision(
      result.ready_for_operator_execution_request ? "云资源只读验证可复核" : "云资源只读验证需修复",
      `${result.message} Cloud execution remains blocked.`,
    );
  } catch (error) {
    renderCloudResourceProbe({
      status: "failed",
      ready_for_operator_execution_request: false,
      real_cloud_verified: false,
      cloud_execution: "blocked",
      message: error.message,
      probe: {},
      missing_bindings: [],
      failed_checks: [],
    }, state.dataArtsStandardization, run);
    setDecision("云资源只读验证失败", error.message);
  }
}

function renderCloudResourceProbe(probe, standardization = state.dataArtsStandardization, run = state.lastRun) {
  const box = $("#cloudProbeBox");
  const button = $("#runCloudProbe");
  if (!box || !button) return;

  const standardReady = Boolean(standardization?.ready_for_cloud_probe);
  if (!run || !standardReady) {
    button.disabled = true;
    button.textContent = "验证云资源";
    box.className = "binding-box blocked";
    box.replaceChildren(
      node("strong", "", "云资源只读验证等待中"),
      node("span", "", "请先完成 DataArts 标准化。这个步骤只检查现有资源，不创建、不修改、不执行。"),
      button,
    );
    return;
  }

  const ready = Boolean(probe?.ready_for_operator_execution_request);
  const verified = Boolean(probe?.real_cloud_verified);
  const failed = probe?.failed_checks || [];
  const missing = probe?.missing_bindings || [];
  const className = ready ? "ready" : failed.length || missing.length ? "failed" : "blocked";
  const title = verified
    ? "真实云资源只读验证通过"
    : ready
      ? "云资源绑定已可人工复核"
      : failed.length || missing.length
        ? "云资源验证缺少绑定"
        : "云资源只读验证未开始";
  const detail = ready
    ? `${probe.message} real_cloud_verified=${verified}; cloud_execution=${probe.cloud_execution}.`
    : missing.length
      ? `Missing bindings: ${missing.slice(0, 5).join(", ")}${missing.length > 5 ? "..." : ""}`
      : "只验证现有资源和只读访问状态，不创建资源、不修改资源、不提交任务。";

  button.disabled = false;
  button.textContent = ready ? "重新验证" : "验证云资源";
  box.className = `binding-box ${className}`;
  box.replaceChildren(node("strong", "", title), node("span", "", detail));

  const probeToggle = node("label", "toggle cloud-probe-toggle");
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.id = "allowNetworkProbe";
  checkbox.checked = state.allowNetworkProbe;
  checkbox.addEventListener("change", () => {
    state.allowNetworkProbe = checkbox.checked;
  });
  probeToggle.append(checkbox, node("span", "", "调用华为云只读 API 验证现有资源"));
  box.append(probeToggle);

  const files = probe?.probe?.files || [];
  [
    ["cloud_resource_probe.json", "打开验证报告"],
    ["real_cloud_resource_binding_template.json", "打开资源绑定模板"],
    ["resolved_dataarts_standard_package.json", "打开标准化导入包"],
    ["cloud_execution_readiness.json", "打开执行就绪状态"],
    ["cloud_readonly_verification_checklist.md", "打开只读验证清单"],
    ["cloud_execution_approval_request.md", "打开执行审批申请"],
  ].forEach(([name, label]) => {
    const file = files.find((item) => item.name === name);
    if (!file?.url) return;
    const link = node("a", "", label);
    link.href = file.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    box.append(link);
  });
  box.append(button);
}

function renderImportReview(importReview, binding = state.cloudBinding, run = state.lastRun) {
  const box = $("#importReviewBox");
  const button = $("#generateImportReview");
  if (!box || !button) return;

  if (!run) {
    button.disabled = true;
    button.textContent = "生成导入复核";
    box.className = "import-box blocked";
    box.replaceChildren(
      node("strong", "", "导入复核未开始"),
      node("span", "", "云参数绑定模拟通过后，可生成操作员交接包；仍不会导入或执行云上任务。"),
      button,
    );
    return;
  }

  const bindingReady = Boolean(binding?.ready_for_import_review);
  if (!bindingReady) {
    button.disabled = true;
    button.textContent = "生成导入复核";
    box.className = "import-box blocked";
    box.replaceChildren(
      node("strong", "", "导入复核等待云绑定"),
      node("span", "", "先完成云参数本地模拟绑定，再生成导入复核交接包。"),
      button,
    );
    return;
  }

  const status = importReview?.status || "ready_for_review";
  const ready = Boolean(importReview?.ready_for_operator_handoff);
  const failed = importReview?.failed_checks || [];
  const className = ready ? "ready" : status === "failed" || status === "needs_fix" ? "failed" : "blocked";
  const title = ready
    ? "导入复核交接包就绪"
    : failed.length
      ? "导入复核需修复"
      : "导入复核待生成";
  const detail = ready
    ? `已生成操作员 handoff、最终导入清单和复核报告；云上执行：${statusLabel(importReview.cloud_execution)}。`
    : failed.length
      ? `复核失败：${failed.slice(0, 3).join("；")}${failed.length > 3 ? "..." : ""}`
      : "将复核发布包、绑定结果、解析后 DataArts 包和执行锁，生成本地交接材料。";

  button.disabled = ready;
  button.textContent = ready ? "交接就绪" : "生成导入复核";
  box.className = `import-box ${className}`;
  box.replaceChildren(node("strong", "", title), node("span", "", detail));

  const files = importReview?.review?.files || [];
  [
    ["cloud_import_review.json", "查看复核报告"],
    ["operator_handoff.md", "查看交接说明"],
    ["final_import_manifest.json", "查看最终导入清单"],
  ].forEach(([name, label]) => {
    const file = files.find((item) => item.name === name);
    if (!file?.url) return;
    const link = node("a", "", label);
    link.href = file.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    box.append(link);
  });
  box.append(button);
}

function renderAgents(agents) {
  const grid = $("#agentGrid");
  grid.innerHTML = "";
  agents.forEach((agent) => {
    const card = node("article", "agent-card");
    const top = node("div", "agent-top");
    top.append(node("strong", "", agent.name));
    top.append(node("span", `badge ${badgeClass(agent.status)}`, statusLabel(agent.status)));
    card.append(top);
    card.append(node("p", "", agent.summary));
    const outputs = node("div", "output-list");
    agent.outputs.forEach((output) => outputs.append(node("span", "", output)));
    card.append(outputs);
    grid.append(card);
  });
}

function renderGates(gates) {
  const list = $("#gateList");
  list.innerHTML = "";
  gates.forEach((gate) => {
    const row = node("div", `gate ${gate.status}`);
    row.append(node("strong", "", `${gate.name}：${statusLabel(gate.status)}`));
    row.append(node("span", "", gate.detail));
    list.append(row);
  });
}

function renderArtifacts(artifacts, selectedIndex = 0) {
  const select = $("#artifactSelect");
  select.innerHTML = "";
  artifacts.forEach((artifact, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = `${artifact.kind}: ${artifact.name} (${statusLabel(artifact.review_status)})`;
    select.append(option);
  });
  const show = () => {
    state.currentArtifactIndex = Number(select.value || 0);
    const artifact = artifacts[state.currentArtifactIndex];
    renderSelectedArtifact(artifact);
  };
  select.onchange = show;
  select.value = String(Math.min(selectedIndex, Math.max(artifacts.length - 1, 0)));
  show();
}

function renderSelectedArtifact(artifact) {
  const preview = $("#artifactPreview");
  const open = $("#artifactOpen");
  const approve = $("#approveArtifact");
  const reject = $("#rejectArtifact");
  const reviewState = $("#artifactReviewState");

  if (!artifact) {
    preview.textContent = "未选择文件。";
    open.href = "#";
    open.setAttribute("aria-disabled", "true");
    approve.disabled = true;
    reject.disabled = true;
    reviewState.textContent = "未选择文件。";
    reviewState.className = "review-state";
    return;
  }

  preview.textContent = artifact.content;
  open.href = artifact.url || "#";
  open.setAttribute("aria-disabled", artifact.url ? "false" : "true");
  approve.disabled = !artifact.review_required;
  reject.disabled = !artifact.review_required;

  const reviewInfo = state.lastRun?.review?.artifacts?.[artifact.name];
  const status = reviewInfo?.status || artifact.review_status;
  const reviewer = reviewInfo?.reviewer ? `，确认人：${reviewInfo.reviewer}` : "";
  const note = reviewInfo?.note ? `，备注：${reviewInfo.note}` : "";
  reviewState.textContent = artifact.review_required
    ? `需要人工确认：${statusLabel(status)}${reviewer}${note}`
    : `无需人工确认：${statusLabel(status)}`;
  reviewState.className = `review-state ${status}`;
}

async function reviewCurrentArtifact(status) {
  const run = state.lastRun;
  if (!run) return;
  const selectedIndex = Number($("#artifactSelect")?.value ?? state.currentArtifactIndex);
  if (Number.isInteger(selectedIndex) && run.artifacts[selectedIndex]) {
    state.currentArtifactIndex = selectedIndex;
  }
  const artifact = run.artifacts[state.currentArtifactIndex];
  if (!artifact || !artifact.review_required) return;

  const response = await fetch(
    `/api/runs/${encodeURIComponent(run.run_id)}/artifacts/${encodeURIComponent(artifact.name)}/review`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        status,
        reviewer: "local_operator",
        note: status === "approved" ? "Approved in frontend review." : "Rejected in frontend review.",
      }),
    },
  );
  if (!response.ok) {
    const text = await response.text();
    setDecision("确认失败", text || `HTTP ${response.status}`);
    return;
  }
  const result = await response.json();
  run.review = result.review;
  const reviewed = run.review.artifacts[artifact.name];
  artifact.review_status = reviewed.status;
  renderArtifacts(run.artifacts, state.currentArtifactIndex);
  renderMetrics(run);
  await loadReleasePackageStatus(run.run_id).catch((error) => {
    renderReleasePackage({
      status: "failed",
      ready: false,
      message: error.message,
      missing_approvals: [],
      failed_gates: [],
      release: {},
    }, run);
  });
  await loadProductionControls(run.run_id).catch((error) => {
    renderProductionControlError(error.message);
  });
  setDecision(
    `文件${status === "approved" ? "已通过" : "已驳回"}`,
    `${artifact.name} 当前状态：${statusLabel(status)}。生产执行仍需云上部署确认。`,
  );
}

function reviewSummary(review) {
  if (!review?.artifacts) return "未开始";
  const items = Object.values(review.artifacts).filter((item) => item.review_required);
  if (!items.length) return "无需确认";
  const approved = items.filter((item) => item.status === "approved").length;
  const rejected = items.filter((item) => item.status === "rejected").length;
  const pending = items.filter((item) => item.status === "pending").length;
  if (rejected) return `${rejected} 个驳回`;
  if (pending) return `${approved}/${items.length} 已通过`;
  return "已通过";
}

function renderTable(rows) {
  renderRowsTable("#dataTable", rows);
}

function renderGoldTable(rows) {
  renderRowsTable("#goldTable", rows);
}

function renderRowsTable(selector, rows) {
  const table = $(selector);
  table.innerHTML = "";
  if (!rows || !rows.length) {
    table.append(node("tbody", "", ""));
    return;
  }
  const headers = Object.keys(rows[0]);
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  headers.forEach((header) => headerRow.append(node("th", "", header)));
  thead.append(headerRow);

  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const bodyRow = document.createElement("tr");
    headers.forEach((header) => bodyRow.append(node("td", "", String(row[header]))));
    tbody.append(bodyRow);
  });
  table.replaceChildren(thead, tbody);
}

function renderLineage(items) {
  const list = $("#lineageList");
  list.innerHTML = "";
  items.forEach((item) => {
    const row = node("div", "lineage-item");
    row.append(node("strong", "", `${item.from} -> ${item.to}`));
    row.append(node("span", "", item.control));
    list.append(row);
  });
}

$("#runButton").addEventListener("click", runAgentPackage);
$("#sampleButton").addEventListener("click", loadSampleRows);
$("#approveArtifact").addEventListener("click", () => reviewCurrentArtifact("approved"));
$("#rejectArtifact").addEventListener("click", () => reviewCurrentArtifact("rejected"));
$("#generateRelease").addEventListener("click", generateReleasePackage);
$("#simulateBinding").addEventListener("click", generateCloudBindingSimulation);
$("#generateImportReview").addEventListener("click", generateImportReview);
$("#standardizeDataArts").addEventListener("click", generateDataArtsStandardization);
$("#runCloudProbe").addEventListener("click", runCloudResourceProbe);
$("#refreshCloudEvidence").addEventListener("click", loadCloudEvidence);
$("#queryCloudGold").addEventListener("click", loadCloudGoldQuery);
$("#cloudGoldYear").addEventListener("change", loadCloudGoldQuery);
$("#cloudGoldRegion").addEventListener("change", loadCloudGoldQuery);
$("#cloudGoldRegime").addEventListener("change", loadCloudGoldQuery);
$("#cloudGoldResico").addEventListener("change", loadCloudGoldQuery);
$("#refreshCloudReadiness").addEventListener("click", loadCloudReadiness);
$("#runEvaluation").addEventListener("click", runEvaluationSuite);
$("#runComparison").addEventListener("click", runComparisonSuite);
$("#refreshFailures").addEventListener("click", refreshFailureSamples);
$("#replayFailures").addEventListener("click", replayFailureSamples);
$("#runPreExecution").addEventListener("click", runPreExecutionReadiness);
$("#requestExecution").addEventListener("click", requestProductionExecution);
$("#approveExecution").addEventListener("click", approveLatestExecution);
$("#cancelExecution").addEventListener("click", cancelLatestExecution);
$("#templateSelect").addEventListener("change", () => selectTemplate($("#templateSelect").value));
$("#applyTemplate").addEventListener("click", applyTemplate);
$("#testMaaS").addEventListener("click", testMaaS);
$("#newTaskButton").addEventListener("click", resetToComposer);
$("#retryRunButton").addEventListener("click", () => {
  hide("#progressFailureActions");
  $("#prompt").value = state.lastPrompt;
  runAgentPackage();
});
$("#returnToPromptButton").addEventListener("click", () => resetToComposer({ preservePrompt: true }));
$("#prompt").addEventListener("input", () => setBusy(state.isRunning));
$("#prompt").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    if (!$("#runButton").disabled) runAgentPackage();
  }
});
$("#chatbiPrompt").addEventListener("input", () => setChatBIBusy(state.chatBiBusy));
$("#chatbiPrompt").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    if (!$("#chatbiSend").disabled) askChatBI($("#chatbiPrompt").value);
  }
});
$("#chatbiComposer").addEventListener("submit", (event) => {
  event.preventDefault();
  if (!$("#chatbiSend").disabled) askChatBI($("#chatbiPrompt").value);
});
document.querySelectorAll("[data-result-tab]").forEach((button) => {
  button.addEventListener("click", () => selectResultTab(button.dataset.resultTab));
});
document.querySelectorAll("[data-app-nav]").forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    navigateApp(link.dataset.appNav);
  });
});
document.querySelectorAll("[data-open-metadata]").forEach((button) => {
  button.addEventListener("click", () => navigateApp("metadata"));
});
window.addEventListener("popstate", () => {
  navigateApp(window.location.pathname === "/metadata" ? "metadata" : "workbench", { updateHistory: false });
});

window.addEventListener("app:localechange", async () => {
  if ($("#appShell").dataset.view === "result" && state.lastRun) {
    const activeTab = state.activeResultTab;
    renderRun(state.lastRun);
    selectResultTab(activeTab);
  }
  if ($("#appShell").dataset.view !== "chatbi" || !state.chatBiHistory.length) return;

  const prompt = state.chatBiHistory[state.chatBiHistory.length - 1].prompt;
  const refreshSequence = ++state.localeRefreshSequence;
  setChatBIBusy(true);
  try {
    const result = await queryChatBI(prompt);
    if (refreshSequence !== state.localeRefreshSequence) return;
    finishChatBITurn(prompt, result, true);
  } catch (error) {
    if (refreshSequence !== state.localeRefreshSequence) return;
    $("#chatbiConversation").replaceChildren();
    state.chatBiHistory = [];
    renderChatBIUserTurn(prompt);
    renderChatBIError(`查询失败：${error.message}`);
  } finally {
    if (refreshSequence === state.localeRefreshSequence) setChatBIBusy(false);
  }
});

$("#progressProcessHost").append($("#processWorkspace"));
setAppView(window.location.pathname === "/metadata" ? "metadata" : "compose");
setBusy(false);
setChatBIBusy(false);

loadHealth().catch((error) => {
  $("#healthBadge").textContent = "接口异常";
  $("#healthBadge").className = "badge failed";
  setDecision("健康检查失败", error.message);
});

loadCloudEvidence().catch((error) => {
  $("#cloudEvidenceBadge").textContent = "error";
  $("#cloudEvidenceBadge").className = "badge failed";
  $("#cloudEvidenceSummary").textContent = error.message;
});

loadCloudReadiness().catch((error) => {
  $("#cloudReadinessBadge").textContent = "error";
  $("#cloudReadinessBadge").className = "badge failed";
  $("#cloudReadinessSummary").textContent = error.message;
});

loadTemplates().catch((error) => {
  const option = node("option", "", "模板加载失败");
  option.value = "";
  $("#templateSelect").replaceChildren(option);
  setDecision("模板加载失败", error.message);
});

loadMaaSStatus().catch((error) => {
  $("#maasBadge").textContent = "异常";
  $("#maasBadge").className = "badge failed";
  $("#maasStatus").textContent = error.message;
});

loadEvaluationHistory().catch(() => {
  $("#evaluationResult").className = "evaluation-result is-empty";
  $("#evaluationResult").textContent = "还没有运行评测。";
});

loadComparisonHistory().catch(() => {
  $("#comparisonResult").className = "comparison-result is-empty";
  $("#comparisonResult").textContent = "还没有运行对照评测。";
});

loadMaaSStrategies().catch((error) => {
  $("#strategyResult").className = "strategy-result failed";
  $("#strategyResult").textContent = error.message;
});

loadFailureSamples().catch(() => {
  $("#failureResult").className = "strategy-result is-empty";
  $("#failureResult").textContent = "还没有失败样本。";
});
