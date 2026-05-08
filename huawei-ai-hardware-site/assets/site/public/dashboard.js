const state = {
  data: null,
  lastResult: null
};

const els = {
  form: document.getElementById("configForm"),
  hardware: document.getElementById("hardware"),
  hardwareCount: document.getElementById("hardwareCount"),
  model: document.getElementById("model"),
  scenario: document.getElementById("scenario"),
  contextTokens: document.getElementById("contextTokens"),
  concurrency: document.getElementById("concurrency"),
  resultPanel: document.getElementById("resultPanel"),
  processGrid: document.getElementById("processGrid"),
  resourceGrid: document.getElementById("resourceGrid"),
  sourceGrid: document.getElementById("sourceGrid"),
  resetBtn: document.getElementById("resetBtn"),
  sampleBtn: document.getElementById("sampleBtn"),
  deployDialog: document.getElementById("deployDialog"),
  akInput: document.getElementById("akInput"),
  skInput: document.getElementById("skInput"),
  domainInput: document.getElementById("domainInput"),
  deploySnippet: document.getElementById("deploySnippet")
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatTokens(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  if (number >= 1000000) return `${number / 1000000}M`;
  if (number >= 1000) return `${Math.round(number / 1000)}K`;
  return String(number);
}

function formatGB(value) {
  if (!Number.isFinite(value)) return "-";
  return `${Math.round(value * 10) / 10} GB`;
}

function formatPercent(value) {
  if (!Number.isFinite(value)) return "-";
  return `${Math.round(value)}%`;
}

function option(label, value) {
  return `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`;
}

function filledCount(inputs) {
  return Object.values(inputs).filter((value) => value !== "" && value !== null && value !== undefined).length;
}

function getInputs() {
  return {
    hardwareId: els.hardware.value,
    hardwareCount: els.hardwareCount.value ? Number(els.hardwareCount.value) : "",
    modelId: els.model.value,
    scenarioId: els.scenario.value,
    contextTokens: els.contextTokens.value ? Number(els.contextTokens.value) : "",
    concurrency: els.concurrency.value ? Number(els.concurrency.value) : ""
  };
}

function getModel(id) {
  return state.data.models.find((item) => item.id === id);
}

function getHardware(id) {
  return state.data.hardware.find((item) => item.id === id);
}

function quantWeightGB(model, quant) {
  return (model.totalParametersB * quant.bits / 8) * (model.weightOverheadFactor ?? 1.08);
}

function kvCacheGB(model, contextTokens, concurrency) {
  const bytesPerToken = 2 * model.layers * model.kvHeads * model.headDim * model.kvBytes;
  return bytesPerToken * contextTokens * concurrency * (model.kvCacheFactor ?? 1) / (1024 ** 3);
}

function estimateDecodeTpsPerCard(hardware, model, quant, scenario) {
  const scenarioPenalty = state.data.scenarios.find((item) => item.id === scenario)?.throughputFactor ?? 1;
  const quantPenalty = quant.throughputFactor ?? 1;
  const raw = hardware.int8Tops * 1000 * hardware.inferenceEfficiency * quantPenalty * scenarioPenalty;
  return raw / Math.max(model.activeParametersB, 1);
}

function scoreQuantization({ totalMemoryGB, availableMemoryGB, contextTokens, model, quant, scenario }) {
  const fitScore = Math.max(0, Math.min(100, (availableMemoryGB / Math.max(totalMemoryGB, 1)) * 72));
  const qualityScore = quant.qualityScore;
  const contextScore = contextTokens <= model.maxContextTokens ? 100 : Math.max(0, 100 - ((contextTokens - model.maxContextTokens) / model.maxContextTokens) * 100);
  const scenarioBoost = quant.scenarioFit?.[scenario] ?? 0;
  return Math.round(fitScore * 0.38 + qualityScore * 0.34 + contextScore * 0.2 + scenarioBoost);
}

function calculateRecommendation(inputs) {
  const hardware = getHardware(inputs.hardwareId);
  const model = getModel(inputs.modelId);
  const scenario = inputs.scenarioId || "chatbot";
  const hardwareCount = Number(inputs.hardwareCount || 1);
  const contextTokens = Number(inputs.contextTokens || 32000);
  const concurrency = Number(inputs.concurrency || 1);
  const totalMemoryAvailableGB = hardwareCount * hardware.memoryGB * hardware.usableMemoryRatio;

  const candidates = model.quantizations.map((quant) => {
    const weightsGB = quantWeightGB(model, quant);
    const kvGB = kvCacheGB(model, contextTokens, concurrency);
    const runtimeGB = weightsGB * (model.runtimeOverheadFactor ?? 1.08);
    const totalMemoryGB = runtimeGB + kvGB + model.frameworkReserveGB;
    const requiredCards = Math.ceil(totalMemoryGB / (hardware.memoryGB * hardware.usableMemoryRatio));
    const memoryUtilization = (totalMemoryGB / totalMemoryAvailableGB) * 100;
    const fits = totalMemoryGB <= totalMemoryAvailableGB && contextTokens <= model.maxContextTokens;
    const decodeTps = estimateDecodeTpsPerCard(hardware, model, quant, scenario) * hardwareCount;
    const perUserTps = decodeTps / Math.max(concurrency, 1);

    return {
      quant,
      weightsGB,
      kvGB,
      runtimeGB,
      totalMemoryGB,
      requiredCards,
      memoryUtilization,
      fits,
      decodeTps,
      perUserTps,
      score: scoreQuantization({ totalMemoryGB, availableMemoryGB: totalMemoryAvailableGB, contextTokens, model, quant, scenario })
    };
  });

  const sorted = [...candidates].sort((left, right) => {
    if (left.fits !== right.fits) return left.fits ? -1 : 1;
    return right.score - left.score || left.requiredCards - right.requiredCards;
  });

  return {
    hardware,
    model,
    scenario: state.data.scenarios.find((item) => item.id === scenario),
    hardwareCount,
    contextTokens,
    concurrency,
    totalMemoryAvailableGB,
    candidates,
    best: sorted[0]
  };
}

function meterClass(value) {
  if (value > 100) return "danger";
  if (value > 78) return "warn";
  return "";
}

function scoreCard(label, value, note, meterValue) {
  const width = Math.max(0, Math.min(100, meterValue));
  return `
    <article class="score-card">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <div class="meter ${meterClass(meterValue)}"><i style="width:${width}%"></i></div>
      <p class="note">${escapeHtml(note)}</p>
    </article>
  `;
}

function renderEmpty(message) {
  els.resultPanel.innerHTML = `
    <div class="empty-state">
      <strong>Almost there</strong>
      <p>${escapeHtml(message)}</p>
    </div>
  `;
  els.processGrid.innerHTML = "";
}

function renderRecommendation(result) {
  const { hardware, model, scenario, best } = result;
  const statusClass = best.fits ? "ok-text" : "bad-text";
  const statusText = best.fits ? "This configuration can host the selected model" : "This configuration is undersized";
  const contextText = result.contextTokens > model.maxContextTokens
    ? `Selected context exceeds the public model limit of ${formatTokens(model.maxContextTokens)}`
    : `Within the public model limit of ${formatTokens(model.maxContextTokens)}`;
  const recommendationText = best.fits
    ? `${result.hardwareCount} x ${hardware.name} for ${model.name}, using ${best.quant.name}. At ${formatTokens(result.contextTokens)} context and ${result.concurrency} concurrency, estimated memory utilization is ${formatPercent(best.memoryUtilization)}.`
    : `Use at least ${best.requiredCards} x ${hardware.name}, or reduce context, concurrency, quantization quality, or model size. The current ${result.hardwareCount} card(s) provide ${formatGB(result.totalMemoryAvailableGB)} usable memory.`;

  els.resultPanel.innerHTML = `
    <div class="recommendation">
      <div class="recommendation-top">
        <div>
          <span class="${statusClass}">${escapeHtml(statusText)}</span>
          <h2>${escapeHtml(recommendationText)}</h2>
        </div>
        <button type="button" id="deployBtn">Generate Deploy Vars</button>
      </div>

      <div class="badge-row">
        <div class="badge"><span>Model</span><strong>${escapeHtml(model.name)}</strong></div>
        <div class="badge"><span>Use case</span><strong>${escapeHtml(scenario.name)}</strong></div>
        <div class="badge"><span>Recommended quantization</span><strong>${escapeHtml(best.quant.name)}</strong></div>
        <div class="badge"><span>Minimum hardware</span><strong>${escapeHtml(best.requiredCards)} card(s)</strong></div>
      </div>

      <div class="score-grid">
        ${scoreCard("Memory pressure", formatPercent(best.memoryUtilization), `Available ${formatGB(result.totalMemoryAvailableGB)} / required ${formatGB(best.totalMemoryGB)}`, best.memoryUtilization)}
        ${scoreCard("Context fit", contextText, `${formatTokens(result.contextTokens)} tokens x ${result.concurrency} concurrency drives KV cache growth`, result.contextTokens / model.maxContextTokens * 100)}
        ${scoreCard("Estimated per-user decode", `${Math.max(1, Math.round(best.perUserTps))} tok/s`, "Based on public TOPS and a conservative inference-efficiency factor; validate with a real load test.", Math.min(100, best.perUserTps))}
      </div>

      <div class="warning">
        <strong>Recommendation rationale:</strong>
        ${escapeHtml(best.quant.rationale)} ${escapeHtml(model.notes)}
      </div>

      <div class="quant-grid">
        ${result.candidates.map((candidate) => `
          <article class="quant-card ${candidate.quant.name === best.quant.name ? "selected" : ""}">
            <span>${escapeHtml(candidate.quant.name)}</span>
            <strong>${candidate.fits ? "Fits" : "Undersized"}</strong>
            <p class="note">Requires ${formatGB(candidate.totalMemoryGB)} · min ${candidate.requiredCards} card(s) · score ${candidate.score}</p>
          </article>
        `).join("")}
      </div>
    </div>
  `;

  document.getElementById("deployBtn").addEventListener("click", openDeployDialog);
}

function renderProcess(result) {
  if (!result) {
    els.processGrid.innerHTML = "";
    return;
  }

  const { best, model, contextTokens, concurrency } = result;
  els.processGrid.innerHTML = [
    {
      label: "Weight memory",
      value: formatGB(best.weightsGB),
      formula: `${model.totalParametersB}B params x ${best.quant.bits} bit / 8 x ${model.weightOverheadFactor ?? 1.08}`
    },
    {
      label: "Runtime reserve",
      value: formatGB(best.runtimeGB - best.weightsGB + model.frameworkReserveGB),
      formula: `weights x ${((model.runtimeOverheadFactor ?? 1.08) - 1).toFixed(2)} + framework reserve ${model.frameworkReserveGB}GB`
    },
    {
      label: "KV cache",
      value: formatGB(best.kvGB),
      formula: `2 x ${model.layers} layers x ${model.kvHeads} KV heads x ${model.headDim} dim x ${model.kvBytes} bytes x ${formatTokens(contextTokens)} x ${concurrency} x cache factor ${model.kvCacheFactor ?? 1}`
    },
    {
      label: "Total memory",
      value: formatGB(best.totalMemoryGB),
      formula: `runtime weights + KV cache + reserve; requires ${best.requiredCards} card(s)`
    }
  ].map((item) => `
    <article class="process-card">
      <span>${escapeHtml(item.label)}</span>
      <strong>${escapeHtml(item.value)}</strong>
      <div class="formula">${escapeHtml(item.formula)}</div>
    </article>
  `).join("");
}

function renderResources() {
  els.resourceGrid.innerHTML = state.data.cloudResources.map((item) => `
    <article class="resource-card">
      <span>${escapeHtml(item.layer)}</span>
      <strong>${escapeHtml(item.recommendation)}</strong>
      <p class="note">${escapeHtml(item.reason)}</p>
      <div class="formula">${escapeHtml(item.terraform)}</div>
    </article>
  `).join("");
}

function renderSources() {
  els.sourceGrid.innerHTML = state.data.sources.map((source) => `
    <article class="source-card">
      <strong>${escapeHtml(source.title)}</strong>
      <p class="note">${escapeHtml(source.summary)}</p>
      <small>${escapeHtml(source.confidence)} · ${escapeHtml(source.updated || "")}</small>
      <p><a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">Open source</a></p>
    </article>
  `).join("");
}

function runCalculation() {
  const inputs = getInputs();
  const count = filledCount(inputs);
  if (count < 3) {
    renderEmpty(`You have filled ${count} field(s); at least ${3 - count} more are required.`);
    state.lastResult = null;
    renderProcess(null);
    return;
  }

  if (!inputs.hardwareId || !inputs.modelId) {
    renderEmpty("Hardware SKU and model are required before memory and quantization can be calculated.");
    state.lastResult = null;
    renderProcess(null);
    return;
  }

  state.lastResult = calculateRecommendation(inputs);
  renderRecommendation(state.lastResult);
  renderProcess(state.lastResult);
}

function openDeployDialog() {
  updateDeploySnippet();
  els.deployDialog.showModal();
}

function updateDeploySnippet() {
  const ak = els.akInput.value || "<HUAWEI_ACCESS_KEY>";
  const sk = els.skInput.value || "<HUAWEI_SECRET_KEY>";
  const domain = els.domainInput.value || "<IAM_DOMAIN_NAME>";
  els.deploySnippet.textContent = [
    "cd terraform/ai-hardware-config-site",
    "terraform init",
    "terraform apply \\",
    `  -var access_key="${ak}" \\`,
    `  -var secret_key="${sk}" \\`,
    `  -var domain_name="${domain}"`
  ].join("\n");
}

function resetForm() {
  els.form.reset();
  els.resultPanel.innerHTML = `
    <div class="empty-state">
      <strong>Waiting for input</strong>
      <p>Select at least three fields across hardware, count, model, use case, context, and concurrency.</p>
    </div>
  `;
  els.processGrid.innerHTML = "";
  state.lastResult = null;
}

function fillSample() {
  els.hardware.value = "ascend-910b";
  els.hardwareCount.value = "8";
  els.model.value = "glm-5-1";
  els.scenario.value = "coding";
  els.contextTokens.value = "200000";
  els.concurrency.value = "4";
  runCalculation();
}

async function init() {
  const response = await fetch("/data/ai-hardware-config.json");
  state.data = await response.json();

  els.hardware.innerHTML = option("Select hardware", "") + state.data.hardware.map((item) => option(item.name, item.id)).join("");
  els.model.innerHTML = option("Select model", "") + state.data.models.map((item) => option(item.name, item.id)).join("");
  els.scenario.innerHTML = option("Select use case", "") + state.data.scenarios.map((item) => option(item.name, item.id)).join("");
  renderResources();
  renderSources();
}

els.form.addEventListener("submit", (event) => {
  event.preventDefault();
  runCalculation();
});
els.resetBtn.addEventListener("click", resetForm);
els.sampleBtn.addEventListener("click", fillSample);
[els.akInput, els.skInput, els.domainInput].forEach((input) => input.addEventListener("input", updateDeploySnippet));

init().catch((error) => {
  els.resultPanel.innerHTML = `<div class="empty-state"><strong>Data failed to load</strong><p>${escapeHtml(error.message)}</p></div>`;
});
