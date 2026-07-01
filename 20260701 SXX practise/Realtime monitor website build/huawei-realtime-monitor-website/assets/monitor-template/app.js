const iconMap = {
  obs: "./assets/obs.png",
  mrs: "./assets/mapreduce.png",
  dataarts: "./assets/dataarts.png",
  dws: "./assets/dws.png",
};

const serviceLabels = {
  obs: "OBS",
  oms: "OMS",
  rds: "RDS",
  dms: "DMS",
  mrs: "MRS",
  dataarts: "DataArts",
  dws: "DWS",
  cdm: "CDM",
  ecs: "ECS",
  vpc: "VPC",
  streaming: "RT",
};

let currentStatus = null;
let selectedService = "";

function text(value, fallback = "-") {
  return value === undefined || value === null || value === "" ? fallback : String(value);
}

function number(value) {
  return new Intl.NumberFormat("en-US").format(Number(value || 0));
}

function time(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("en-US", { hour12: false });
}

function escapeHtml(value) {
  return text(value, "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function statusClass(value) {
  const normalized = text(value, "idle").toLowerCase();
  if (["healthy", "success", "succeeded", "available", "running", "active", "sampled"].includes(normalized)) return "healthy";
  if (["warning", "executing", "submitted", "creating"].includes(normalized)) return "warning";
  if (["unavailable", "failed", "failure", "error", "deleted"].includes(normalized)) return "unavailable";
  return "idle";
}

function statusLabel(value) {
  const normalized = text(value, "idle").toLowerCase();
  const map = {
    available: "Available",
    healthy: "Healthy",
    success: "Success",
    succeeded: "Success",
    running: "Running",
    active: "Active",
    executing: "Executing",
    submitted: "Submitted",
    creating: "Creating",
    warning: "Attention",
    unavailable: "Unavailable",
    failed: "Failed",
    failure: "Failed",
    error: "Error",
    deleted: "Deleted",
    idle: "Not Found",
    unknown: "Unknown",
    sampled: "Sampled",
  };
  return map[normalized] || text(value, "Unknown");
}

function stageIcon(key) {
  if (iconMap[key]) return `<img src="${iconMap[key]}" alt="${serviceLabels[key] || key}">`;
  return `<span>${escapeHtml(serviceLabels[key] || key.slice(0, 2).toUpperCase())}</span>`;
}

function renderSummary(data) {
  const summary = data.summary || {};
  document.getElementById("healthCount").textContent = `${summary.healthy_services || 0}/${summary.total_services || 0}`;
  document.getElementById("resourceCount").textContent = number(summary.resource_count);
  document.getElementById("catalogCount").textContent = number(summary.catalog_count);
  document.getElementById("jobCount").textContent = number(summary.job_count);
  document.getElementById("riskCount").textContent = number(summary.risk_count);
  document.getElementById("lastUpdated").textContent = time(data.generated_at);
  document.getElementById("regionLabel").textContent = `Huawei Cloud / ${text(data.region, "Region pending")}`;
  document.getElementById("projectLabel").textContent = `Project ${text(data.project?.id, "pending")}`;
}

function renderPipeline(data) {
  const stages = data.topology?.stages || [];
  const root = document.getElementById("pipeline");
  root.innerHTML = stages.length ? stages.map((stage, index) => `
    <article class="stage" style="--progress:${Math.max(0, Math.min(100, Number(stage.progress || 0))) / 100}">
      <span class="stage-pulse" style="animation-delay:${index * 180}ms"></span>
      <div class="stage-top">
        <div class="stage-icon">${stageIcon(stage.key)}</div>
        <span class="status ${statusClass(stage.status)}">${statusLabel(stage.status)}</span>
      </div>
      <h3>${escapeHtml(stage.label)}</h3>
      <p>${number(stage.resource_count)} resources / ${number(stage.job_count)} jobs</p>
      <p>${number(stage.progress)}% progress signal</p>
    </article>
  `).join("") : `<div class="empty">Waiting for resource assessment results</div>`;
}

function updateServiceFilter(data) {
  const select = document.getElementById("serviceFilter");
  const services = Object.values(data.services || {});
  const options = [`<option value="">All services</option>`].concat(
    services.map(service => `<option value="${escapeHtml(service.key)}">${escapeHtml(service.label)} (${number(service.resource_count)})</option>`)
  );
  const previous = select.value || selectedService;
  select.innerHTML = options.join("");
  select.value = previous;
}

function renderResources(data) {
  const root = document.getElementById("resourceList");
  const services = Object.values(data.services || {});
  const rows = [];
  services.forEach(service => {
    if (selectedService && service.key !== selectedService) return;
    (service.resources || []).forEach(resource => rows.push({ service, resource }));
    if (!(service.resources || []).length && !selectedService) {
      rows.push({ service, resource: null });
    }
  });
  root.innerHTML = rows.length ? rows.map(({ service, resource }) => {
    if (!resource) {
      return `
        <div class="resource-row">
          <span class="resource-service">${escapeHtml(service.label)}</span>
          <div><div class="resource-name">No resources found</div><p class="resource-meta">${escapeHtml((service.errors || []).join(" | ") || "No resource records")}</p></div>
          <span class="status ${statusClass(service.status)}">${statusLabel(service.status)}</span>
        </div>`;
    }
    return `
      <div class="resource-row">
        <span class="resource-service">${escapeHtml(resource.service || service.label)}</span>
        <div>
          <div class="resource-name" title="${escapeHtml(resource.name)}">${escapeHtml(resource.name)}</div>
          <p class="resource-meta">${escapeHtml(resource.type)} / ${escapeHtml(resource.id)} ${resource.region ? `/ ${escapeHtml(resource.region)}` : ""}</p>
        </div>
        <span class="status ${statusClass(resource.status)}">${statusLabel(resource.status)}</span>
      </div>`;
  }).join("") : `<div class="empty">No matching resources</div>`;
}

function renderJobs(data) {
  const jobs = data.jobs || [];
  document.getElementById("jobMeta").textContent = `${number(jobs.length)} jobs`;
  document.getElementById("jobList").innerHTML = jobs.length ? jobs.map(job => `
    <div class="job-row">
      <span class="job-source">${escapeHtml(job.source)}</span>
      <div>
        <div class="job-name" title="${escapeHtml(job.name)}">${escapeHtml(job.name || "unnamed job")}</div>
        <p class="job-meta">${escapeHtml(job.type)} / ${escapeHtml(job.detail || "metadata only")}</p>
      </div>
      <span class="status ${statusClass(job.status)}">${statusLabel(job.status)}</span>
    </div>
  `).join("") : `<div class="empty">No MRS/DataArts job records have been collected yet</div>`;
}

function filteredCatalog() {
  const needle = document.getElementById("catalogSearch").value.trim().toLowerCase();
  return (currentStatus?.catalog || []).filter(row => {
    if (!needle) return true;
    return `${row.system} ${row.category} ${row.name} ${row.format} ${row.detail}`.toLowerCase().includes(needle);
  });
}

function renderCatalog() {
  const rows = filteredCatalog();
  document.getElementById("catalogRows").innerHTML = rows.length ? rows.map(row => `
    <tr>
      <td>${escapeHtml(row.system)}</td>
      <td>${escapeHtml(row.category)}</td>
      <td class="mono">${escapeHtml(row.name)}</td>
      <td>${escapeHtml(row.format)}</td>
      <td>${row.columns === null || row.columns === undefined ? "-" : number(row.columns)}</td>
      <td>${row.objects === null || row.objects === undefined ? "-" : number(row.objects)}</td>
      <td>${escapeHtml(row.detail || "")}</td>
    </tr>
  `).join("") : `<tr><td colspan="7" class="empty">No table structures or object prefixes have been collected yet</td></tr>`;
}

function renderNotes(id, rows, className = "") {
  const root = document.getElementById(id);
  root.innerHTML = rows && rows.length ? rows.map((item, index) => `
    <div class="note-row ${className}">
      <strong>${index + 1}. ${escapeHtml(item)}</strong>
    </div>
  `).join("") : `<div class="empty">None</div>`;
}

function render(data) {
  currentStatus = data;
  renderSummary(data);
  renderPipeline(data);
  updateServiceFilter(data);
  renderResources(data);
  renderJobs(data);
  renderCatalog();
  renderNotes("riskList", data.risks || []);
  renderNotes("recommendationList", data.recommendations || [], "recommendation");
}

async function loadStatus() {
  const stamp = Date.now();
  let response = await fetch(`/api/status?t=${stamp}`, { cache: "no-store" }).catch(() => null);
  if (!response || !response.ok) {
    response = await fetch(`./data/status.json?t=${stamp}`, { cache: "no-store" });
  }
  if (!response.ok) throw new Error(`status api ${response.status}`);
  render(await response.json());
}

async function refreshNow() {
  const button = document.getElementById("refreshBtn");
  button.classList.add("loading");
  try {
    await fetch("/api/refresh", { method: "POST" }).catch(() => null);
    await loadStatus();
  } finally {
    button.classList.remove("loading");
  }
}

document.getElementById("serviceFilter").addEventListener("change", event => {
  selectedService = event.target.value;
  renderResources(currentStatus || {});
});
document.getElementById("catalogSearch").addEventListener("input", renderCatalog);
document.getElementById("refreshBtn").addEventListener("click", refreshNow);

loadStatus().catch(console.error);
setInterval(() => loadStatus().catch(console.error), 5000);
