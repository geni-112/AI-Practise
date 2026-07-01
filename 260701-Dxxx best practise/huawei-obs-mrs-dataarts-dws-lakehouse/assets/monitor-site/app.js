const iconMap = {
  obs: "./assets/obs.png",
  mrs: "./assets/mapreduce.png",
  dataarts: "./assets/dataarts.png",
  dws: "./assets/dws.png",
};

const labels = {
  obs: "OBS Data Lake",
  mrs: "MRS / Iceberg",
  dataarts: "DataArts Factory",
  dws: "DWS Warehouse",
};

const consoleLinks = {
  mrs: "https://console-intl.huaweicloud.com/mrs/?region=la-south-2#/mrs/clusterList",
  dataarts: "https://console-intl.huaweicloud.com/dataartsstudio/?region=la-south-2#/instances",
  dws: "https://console-intl.huaweicloud.com/dws/?region=la-south-2#/dws/cluster-mgmt",
};

const chartPalette = ["#7ab3ba", "#557f8e", "#86b99a", "#c7a56c", "#8da0aa"];

let currentData = null;
let refreshTimer = null;

function formatBytes(value) {
  let n = Number(value || 0);
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i += 1; }
  return `${n.toFixed(i > 1 ? 2 : 1)} ${units[i]}`;
}

function formatNumber(value) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-US").format(value);
}

function formatTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-US", { hour12: false });
}

function formatTimePoint(value) {
  if (!value) return "--:--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--:--";
  return date.toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
  });
}

function escapeAttr(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function formatDuration(ms) {
  if (!ms) return "—";
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function clamp(value, min = 0, max = 100) {
  return Math.min(max, Math.max(min, Number(value || 0)));
}

function percentage(value, total) {
  if (!total) return 0;
  return clamp((Number(value || 0) / total) * 100);
}

function statusClass(status = "") {
  const normalized = status.toLowerCase();
  if (["healthy", "success", "succeeded", "finished", "active"].includes(normalized)) return "healthy";
  if (["running", "warning", "submitted"].includes(normalized)) return "warning";
  if (["failed", "failure", "unavailable", "error"].includes(normalized)) return "unavailable";
  return "idle";
}

function statusText(status = "") {
  const map = {
    healthy: "Healthy", success: "Success", succeeded: "Success", running: "Running",
    warning: "Warning", unavailable: "Unavailable", failed: "Failed", idle: "Idle",
    stopped: "Stopped", active: "Active", finished: "Finished",
  };
  return map[status.toLowerCase()] || status || "Unknown";
}

function serviceDetails(key, service) {
  if (key === "obs") {
    return `${service.objects || 0} objects · ${formatBytes(service.bytes)}`;
  }
  if (key === "mrs") {
    return `${service.state || "—"} · latest job ${service.progress || 0}%`;
  }
  if (key === "dataarts") {
    return `${(service.jobs || []).length} jobs · batch orchestration`;
  }
  if (key === "dws") return `${service.state || "—"} · ${(service.tables || []).length} catalog objects`;
  return `${service.state || "—"} · ${(service.tables || []).length} validated tables`;
}

function renderObsLayerChart(data) {
  const root = document.getElementById("obsLayerChart");
  const layers = (data.services.obs?.layers || []).filter(layer => Number(layer.bytes || 0) > 0);
  const total = layers.reduce((sum, layer) => sum + Number(layer.bytes || 0), 0);
  if (!layers.length) {
    root.innerHTML = `<div class="empty-mini">No storage samples</div>`;
    return;
  }
  root.innerHTML = layers.map((layer, index) => {
    const pct = percentage(layer.bytes, total);
    return `
      <div class="mini-bar" title="${layer.name}: ${formatBytes(layer.bytes)}">
        <span class="mini-bar-label">${layer.name}</span>
        <span class="mini-bar-track"><span class="mini-bar-fill" style="width:${Math.max(3, pct)}%; background:${chartPalette[index % chartPalette.length]}"></span></span>
        <span class="mini-bar-value">${Math.round(pct)}%</span>
      </div>`;
  }).join("");
}

function renderTableDonut(data) {
  const root = document.getElementById("tableDonut");
  const value = document.getElementById("tableDonutValue");
  const rows = data.tables || [];
  const groups = [
    { label: "MRS", value: rows.filter(row => row.system === "MRS Iceberg").length, color: chartPalette[0] },
    { label: "DWS", value: rows.filter(row => row.system === "DWS").length, color: chartPalette[2] },
  ];
  const total = groups.reduce((sum, item) => sum + item.value, 0);
  value.textContent = formatNumber(total);
  if (!total) {
    root.style.background = "conic-gradient(rgba(112, 134, 144, .18) 0deg 360deg)";
    root.title = "No catalog objects";
    return;
  }
  let cursor = 0;
  const segments = groups.filter(item => item.value > 0).map(item => {
    const start = cursor;
    const end = cursor + (item.value / total) * 360;
    cursor = end;
    return `${item.color} ${start.toFixed(1)}deg ${end.toFixed(1)}deg`;
  });
  root.style.background = `conic-gradient(${segments.join(", ")})`;
  root.title = groups.map(item => `${item.label}: ${item.value}`).join(" | ");
}

function renderProgressRing(data) {
  const root = document.getElementById("progressRing");
  const value = document.getElementById("progressRingValue");
  const progress = clamp(data.summary?.mrs_progress || 0);
  value.textContent = `${Math.round(progress)}%`;
  root.style.background = `conic-gradient(${chartPalette[0]} 0deg ${(progress * 3.6).toFixed(1)}deg, rgba(112, 134, 144, .18) ${(progress * 3.6).toFixed(1)}deg 360deg)`;
}

function renderHistorySparkline(data) {
  const root = document.getElementById("historySparkline");
  const rows = (data.history || []).slice(0, 16).reverse();
  if (!rows.length) {
    root.innerHTML = `<div class="empty-mini">No runs</div>`;
    return;
  }
  const maxDuration = Math.max(...rows.map(row => Number(row.duration_ms || 0)), 1);
  root.innerHTML = rows.map(row => {
    const height = Math.max(12, percentage(row.duration_ms || 0, maxDuration));
    const state = String(row.status || "").toLowerCase();
    const label = formatTimePoint(row.started_at);
    const title = `${row.source || "Run"} | ${statusText(row.status)} | Started ${formatTime(row.started_at)} | Duration ${formatDuration(row.duration_ms)}`;
    return `
      <span class="spark-item" title="${escapeAttr(title)}">
        <span class="spark-bar-wrap"><span class="spark-bar ${state}" style="height:${height}%"></span></span>
        <span class="spark-time">${label}</span>
      </span>`;
  }).join("");
}

function renderKpiVisuals(data) {
  renderObsLayerChart(data);
  renderTableDonut(data);
  renderProgressRing(data);
  renderHistorySparkline(data);
}

function renderPipeline(data) {
  const root = document.getElementById("pipeline");
  root.innerHTML = data.pipeline.map((key) => {
    const service = data.services[key] || {};
    const progress = clamp(data.stage_progress?.[key] ?? 0);
    const icon = `<img class="service-icon" src="${iconMap[key]}" alt="${labels[key]}"/>`;
    const linkedIcon = consoleLinks[key]
      ? `<a class="service-link" href="${consoleLinks[key]}" target="_blank" rel="noopener noreferrer" title="Open ${labels[key]} console">${icon}</a>`
      : icon;
    return `
      <article class="stage">
        <div class="stage-head">
          ${linkedIcon}
          <span class="chip ${statusClass(service.status)}">${statusText(service.status)}</span>
        </div>
        <h4>${labels[key]}</h4>
        <p>${serviceDetails(key, service)}</p>
        <div class="stage-meter"><span style="width:${progress}%"></span></div>
      </article>`;
  }).join("");
}

function resourceTags(key, service) {
  if (key === "mrs") {
    return (service.components || []).map(x => `<span>${x.name} ${x.version}</span>`).join("");
  }
  if (key === "obs") {
    return (service.layers || []).map(x => `<span>${x.name}: ${x.objects}</span>`).join("");
  }
  if (key === "dataarts") {
    return (service.jobs || []).map(x => `<span>${x.name}: ${x.last_status || x.definition_status}</span>`).join("");
  }
  if (key === "dws") return `<span>${(service.nodes || []).length} nodes</span><span>Port ${service.port || 8000}</span>`;
  return `<span>${service.state || "Ready"}</span>`;
}

function renderResources(data) {
  const root = document.getElementById("resourceGrid");
  root.innerHTML = data.pipeline.map((key) => {
    const service = data.services[key] || {};
    const icon = `<img src="${iconMap[key]}" alt=""/>`;
    const linkedIcon = consoleLinks[key]
      ? `<a class="service-link compact" href="${consoleLinks[key]}" target="_blank" rel="noopener noreferrer" title="Open ${labels[key]} console">${icon}</a>`
      : icon;
    return `
      <article class="resource-card">
        <header>
          <div class="resource-name">${linkedIcon}<strong>${service.name || labels[key]}</strong></div>
          <span class="chip ${statusClass(service.status)}">${statusText(service.status)}</span>
        </header>
        <p>${service.spec || "Specification unavailable"}</p>
        <div class="component-tags">${resourceTags(key, service)}</div>
      </article>`;
  }).join("");
}

function renderProgress(data) {
  const mrs = data.services.mrs || {};
  const dataarts = data.services.dataarts || {};
  const dws = data.services.dws || {};
  const latestMRS = (mrs.history || [])[0] || {};
  const latestDA = (dataarts.history || []).find(row => row.name === "dockone_golden_to_dws") || (dataarts.history || [])[0] || {};
  const progress = data.stage_progress || {};
  const items = [
    { name: "OBS Raw landing", value: progress.obs ?? 0, note: `${data.services.obs?.objects || 0} objects visible` },
    { name: "MRS Spark / Iceberg", value: progress.mrs ?? 0, note: latestMRS.name || "Waiting for job" },
    { name: "DataArts Golden publish", value: progress.dataarts ?? 0, note: latestDA.name || "Waiting for DataArts publish" },
    { name: "DWS Golden serving", value: progress.dws ?? 0, note: `${(dws.tables || []).length} catalog objects visible` },
  ];
  document.getElementById("progressList").innerHTML = items.map(item => `
    <div class="progress-item">
      <header><span>${item.name}</span><b>${item.value}%</b></header>
      <div class="progress-track"><span style="width:${clamp(item.value)}%"></span></div>
      <p>${item.note}</p>
    </div>`).join("");
}

function filteredTables() {
  const search = document.getElementById("tableSearch").value.toLowerCase().trim();
  const system = document.getElementById("systemFilter").value;
  return (currentData?.tables || []).filter(row => {
    const matchesSystem = !system || row.system === system;
    const matchesSearch = !search || `${row.name} ${row.category} ${row.format}`.toLowerCase().includes(search);
    return matchesSystem && matchesSearch;
  });
}

function renderTables() {
  const rows = filteredTables();
  const root = document.getElementById("tableRows");
  root.innerHTML = rows.length ? rows.map(row => `
    <tr>
      <td>${row.system}</td>
      <td><span class="category-dot"></span>${row.category}</td>
      <td class="table-name">${row.name}</td>
      <td>${row.format || "—"}</td>
      <td>${formatNumber(row.rows)}</td>
      <td>${formatNumber(row.objects)}</td>
      <td>${row.bytes === null || row.bytes === undefined ? "—" : formatBytes(row.bytes)}</td>
    </tr>`).join("") : `<tr><td colspan="7" class="empty">No matching data objects</td></tr>`;
}

function renderHistory(data) {
  const root = document.getElementById("history");
  const rows = data.history || [];
  root.innerHTML = rows.length ? rows.map(row => `
    <div class="history-row">
      <span class="history-source">${row.source}</span>
      <span class="history-name" title="${row.name || ""}">${row.name || "unnamed job"}</span>
      <span class="chip ${statusClass(row.status)}">${statusText(row.status)}</span>
      <span class="history-time"><small>Started</small>${formatTime(row.started_at)}<em>Finished ${formatTime(row.finished_at)}</em></span>
      <span class="history-duration">${formatDuration(row.duration_ms)}</span>
    </div>`).join("") : `<div class="empty">No processing history yet</div>`;
}

function renderErrors(data) {
  const panel = document.getElementById("errorsPanel");
  const errors = data.errors || [];
  panel.classList.toggle("hidden", errors.length === 0);
  document.getElementById("errors").innerHTML = errors.map(item =>
    `<div class="error-item"><b>${item.service}</b> · ${item.message}</div>`
  ).join("");
}

function render(data) {
  currentData = data;
  const summary = data.summary || {};
  document.getElementById("healthCount").textContent = `${summary.healthy_services || 0}/${summary.total_services || 4}`;
  document.getElementById("obsBytes").textContent = formatBytes(summary.obs_bytes);
  document.getElementById("tableCount").textContent = formatNumber(summary.table_count);
  document.getElementById("mrsProgress").textContent = `${summary.mrs_progress || 0}%`;
  document.getElementById("historyCount").textContent = formatNumber(summary.history_count);
  document.getElementById("lastUpdated").textContent = formatTime(data.generated_at);

  const global = document.getElementById("globalStatus");
  const allHealthy = (data.errors || []).length === 0;
  global.className = `status-badge ${allHealthy ? "healthy" : "warning"}`;
  global.textContent = allHealthy ? "All live" : `${data.errors.length} sources limited`;

  renderKpiVisuals(data);
  renderPipeline(data);
  renderResources(data);
  renderProgress(data);
  renderTables();
  renderHistory(data);
  renderErrors(data);
}

async function loadStatus() {
  const response = await fetch(`/api/status?t=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Status API ${response.status}`);
  render(await response.json());
}

async function manualRefresh() {
  const button = document.getElementById("refreshBtn");
  button.classList.add("spinning");
  button.textContent = "Refreshing…";
  try {
    await fetch("/api/refresh", { method: "POST" });
    await new Promise(resolve => setTimeout(resolve, 1000));
    await loadStatus();
  } finally {
    button.classList.remove("spinning");
    button.textContent = "Refresh now";
  }
}

document.getElementById("refreshBtn").addEventListener("click", manualRefresh);
document.getElementById("tableSearch").addEventListener("input", renderTables);
document.getElementById("systemFilter").addEventListener("change", renderTables);

loadStatus().catch(console.error);
refreshTimer = setInterval(() => loadStatus().catch(console.error), 5000);
