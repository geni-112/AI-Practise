const metadataState = {
  catalog: null,
  assets: [],
  selectedAssetId: "",
  activeTab: "overview",
};

const metadataQuery = (selector) => document.querySelector(selector);

function metadataNode(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) {
    if (window.i18n) window.i18n.setText(element, text);
    else element.textContent = text;
  }
  return element;
}

function setMetadataStatus(text, state = "muted") {
  const badge = metadataQuery("#metadataStatus");
  badge.className = `status-indicator ${state}`;
  if (window.i18n) window.i18n.setText(badge, text);
  else badge.textContent = text;
}

function formatMetadataValue(value) {
  if (Array.isArray(value)) return value.length ? value.join(", ") : "-";
  if (value && typeof value === "object") return JSON.stringify(value);
  if (value === true) return "是";
  if (value === false) return "否";
  return value === undefined || value === null || value === "" ? "-" : String(value);
}

function metadataStatusLabel(status) {
  return {
    active: "可用",
    verified: "已验证",
    migration_pending: "迁移待验证",
    unavailable: "不可用",
  }[status] || status;
}

function renderMetadataSummary(summary = {}) {
  const items = [
    ["资产", summary.asset_count || 0],
    ["物理表", summary.table_count || 0],
    ["字段", summary.column_count || 0],
    ["业务指标", summary.metric_count || 0],
    ["Iceberg 快照", summary.snapshot_count || 0],
    ["表格式", summary.iceberg_verified ? "Apache Iceberg" : "迁移待验证"],
  ];
  const host = metadataQuery("#metadataSummary");
  host.replaceChildren();
  items.forEach(([label, value]) => {
    const item = metadataNode("div", "metadata-summary-item");
    item.append(metadataNode("span", "", label), metadataNode("strong", "", String(value)));
    host.append(item);
  });
}

function assetMatches(asset, search) {
  if (!search) return true;
  const haystack = [
    asset.name,
    asset.display_name,
    asset.qualified_name,
    asset.kind,
    asset.layer,
    asset.format,
  ].join(" ").toLowerCase();
  return haystack.includes(search.toLowerCase());
}

function assetTreePath(asset) {
  const parts = String(asset.qualified_name || asset.id || asset.name || "")
    .split(".")
    .filter(Boolean);
  return {
    catalog: asset.properties?.catalog || parts[0] || "default",
    namespace: asset.properties?.namespace || (parts.length > 2 ? parts.slice(1, -1).join(".") : "default"),
    object: parts.at(-1) || asset.name || asset.id,
  };
}

function groupAssetsForTree(assets) {
  const catalogs = new Map();
  assets.forEach((asset) => {
    const path = assetTreePath(asset);
    if (!catalogs.has(path.catalog)) catalogs.set(path.catalog, new Map());
    const namespaces = catalogs.get(path.catalog);
    if (!namespaces.has(path.namespace)) namespaces.set(path.namespace, []);
    namespaces.get(path.namespace).push({ asset, object: path.object });
  });
  return catalogs;
}

function treeSummary(type, name, count) {
  const summary = metadataNode("summary", "catalog-tree-summary");
  summary.append(
    metadataNode("span", "catalog-tree-type", type),
    metadataNode("strong", "technical-value", name),
    metadataNode("span", "catalog-tree-count", String(count)),
  );
  return summary;
}

function renderAssetList() {
  const search = metadataQuery("#assetSearch").value.trim();
  const assets = metadataState.assets.filter((asset) => assetMatches(asset, search));
  const host = metadataQuery("#assetList");
  host.replaceChildren();
  metadataQuery("#assetCount").textContent = String(assets.length);

  if (!assets.length) {
    host.append(metadataNode("div", "empty-state", "没有匹配的数据资产。"));
    return;
  }

  const catalogs = groupAssetsForTree(assets);
  [...catalogs.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .forEach(([catalogName, namespaces]) => {
      const catalogAssets = [...namespaces.values()].reduce((total, items) => total + items.length, 0);
      const catalog = metadataNode("details", "catalog-tree-group catalog-level");
      catalog.open = true;
      catalog.append(treeSummary("Catalog", catalogName, catalogAssets));

      const catalogChildren = metadataNode("div", "catalog-tree-children");
      catalogChildren.setAttribute("role", "group");
      [...namespaces.entries()]
        .sort(([left], [right]) => left.localeCompare(right))
        .forEach(([namespaceName, entries]) => {
          const namespace = metadataNode("details", "catalog-tree-group namespace-level");
          namespace.open = true;
          namespace.append(treeSummary("Schema", namespaceName, entries.length));

          const namespaceChildren = metadataNode("div", "catalog-tree-children");
          namespaceChildren.setAttribute("role", "group");
          entries
            .sort((left, right) => left.object.localeCompare(right.object))
            .forEach(({ asset, object }) => {
              const button = metadataNode("button", "catalog-tree-item");
              button.type = "button";
              button.setAttribute("role", "treeitem");
              button.setAttribute("aria-selected", String(asset.id === metadataState.selectedAssetId));
              button.classList.toggle("is-active", asset.id === metadataState.selectedAssetId);
              button.append(
                metadataNode("strong", "technical-value", object),
                metadataNode("span", "catalog-tree-item-meta", `${asset.kind} · ${asset.format}`),
              );
              button.addEventListener("click", () => selectAsset(asset.id));
              namespaceChildren.append(button);
            });
          namespace.append(namespaceChildren);
          catalogChildren.append(namespace);
        });
      catalog.append(catalogChildren);
      host.append(catalog);
    });
}

function renderKeyValues(host, rows) {
  host.replaceChildren();
  const grid = metadataNode("div", "metadata-key-values");
  rows.forEach(([label, value]) => {
    const row = metadataNode("div", "metadata-key-value");
    row.append(
      metadataNode("span", "", label),
      metadataNode("strong", "technical-value", formatMetadataValue(value)),
    );
    grid.append(row);
  });
  host.append(grid);
}

function renderSchema(asset) {
  const host = metadataQuery("#metadataSchema");
  host.replaceChildren();
  const columns = asset.columns || [];
  if (!columns.length) {
    host.append(metadataNode("div", "empty-state", "该资产没有字段元数据。"));
    return;
  }
  const wrap = metadataNode("div", "table-wrap");
  const table = metadataNode("table", "metadata-table");
  const head = metadataNode("thead");
  const headRow = metadataNode("tr");
  ["字段", "类型", "可为空", "分类", "策略"].forEach((label) => headRow.append(metadataNode("th", "", label)));
  head.append(headRow);
  const body = metadataNode("tbody");
  columns.forEach((column) => {
    const row = metadataNode("tr");
    [
      column.name,
      column.type,
      column.nullable ? "是" : "否",
      column.classification || "-",
      column.policy || "-",
    ].forEach((value) => row.append(metadataNode("td", "", value)));
    body.append(row);
  });
  table.append(head, body);
  wrap.append(table);
  host.append(wrap);
}

function renderSemantics(asset) {
  const host = metadataQuery("#metadataSemantics");
  host.replaceChildren();
  const section = (title, items, buildDetail) => {
    const block = metadataNode("section", "metadata-list-section");
    block.append(metadataNode("h3", "", title));
    if (!items.length) {
      block.append(metadataNode("div", "empty-state", "该资产没有此类元数据。"));
      return block;
    }
    const list = metadataNode("div", "metadata-definition-list");
    items.forEach((item) => {
      const row = metadataNode("div", "metadata-definition");
      row.append(
        metadataNode("strong", "", item.label || item.name),
        metadataNode("span", "technical-value", item.name),
        metadataNode("span", "", buildDetail(item)),
      );
      list.append(row);
    });
    block.append(list);
    return block;
  };
  host.append(
    section("业务指标", asset.metrics || [], (item) => `${item.aggregation || "-"} · ${(item.source_columns || []).join(", ")}`),
    section("业务维度", asset.dimensions || [], (item) => `${item.column || item.name} · ${(item.values || []).join(", ")}`),
  );
}

function renderLineage(asset) {
  const host = metadataQuery("#metadataLineage");
  host.replaceChildren();
  const edges = metadataState.catalog?.lineage?.edges || [];
  const related = edges.filter((edge) => edge.from === asset.id || edge.to === asset.id || asset.kind === "table");
  if (!related.length) {
    host.append(metadataNode("div", "empty-state", "该资产没有已发布的血缘关系。"));
    return;
  }
  const list = metadataNode("div", "metadata-lineage-list");
  related.forEach((edge) => {
    const row = metadataNode("div", "metadata-lineage-row");
    row.append(
      metadataNode("strong", "technical-value", `${edge.from} → ${edge.to}`),
      metadataNode("span", "", edge.control),
    );
    list.append(row);
  });
  host.append(list);
}

function renderSnapshots(asset) {
  const host = metadataQuery("#metadataSnapshots");
  host.replaceChildren();
  const snapshots = asset.snapshots || [];
  if (!snapshots.length) {
    host.append(metadataNode("div", "empty-state", "尚无可验证的 Iceberg 快照。"));
    return;
  }
  const wrap = metadataNode("div", "table-wrap");
  const table = metadataNode("table", "metadata-table");
  const head = metadataNode("thead");
  const headRow = metadataNode("tr");
  ["快照 ID", "提交时间", "操作", "记录数"].forEach((label) => headRow.append(metadataNode("th", "", label)));
  head.append(headRow);
  const body = metadataNode("tbody");
  snapshots.forEach((snapshot) => {
    const row = metadataNode("tr");
    [
      snapshot.snapshot_id,
      snapshot.committed_at,
      snapshot.operation,
      snapshot.total_records,
    ].forEach((value) => row.append(metadataNode("td", "technical-value", formatMetadataValue(value))));
    body.append(row);
  });
  table.append(head, body);
  wrap.append(table);
  host.append(wrap);
}

function renderAssetDetail(asset) {
  if (!asset) return;
  metadataQuery("#assetTitle").textContent = asset.display_name || asset.name;
  metadataQuery("#assetQualifiedName").textContent = asset.qualified_name;
  metadataQuery("#assetLayer").textContent = asset.layer;
  metadataQuery("#assetFormat").textContent = asset.format;
  metadataQuery("#assetStatus").textContent = metadataStatusLabel(asset.status);
  metadataQuery("#assetStatus").className = `badge ${asset.status === "verified" || asset.status === "active" ? "ready" : "blocked"}`;

  renderKeyValues(metadataQuery("#metadataOverview"), [
    ["说明", asset.description],
    ["类型", asset.kind],
    ["负责人", asset.owner],
    ["存储位置", asset.location],
    ["分区", asset.partitioning],
    ["Catalog", asset.properties?.catalog],
    ["Namespace", asset.properties?.namespace],
    ["格式版本", asset.properties?.format_version],
    ["当前快照", asset.properties?.current_snapshot_id],
    ["Manifest 清单", asset.properties?.manifest_list || asset.properties?.metadata_location],
  ]);
  renderSchema(asset);
  renderSemantics(asset);
  renderLineage(asset);
  renderSnapshots(asset);
  window.i18n?.refresh();
}

function selectAsset(assetId) {
  metadataState.selectedAssetId = assetId;
  renderAssetList();
  renderAssetDetail(metadataState.assets.find((asset) => asset.id === assetId));
}

function selectMetadataTab(tab) {
  metadataState.activeTab = tab;
  document.querySelectorAll("[data-metadata-tab]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.metadataTab === tab);
  });
  document.querySelectorAll("[data-metadata-panel]").forEach((panel) => {
    panel.classList.toggle("is-active", panel.dataset.metadataPanel === tab);
  });
}

async function loadMetadata() {
  setMetadataStatus("正在加载", "muted");
  const response = await fetch("/api/metadata/catalog", { cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  metadataState.catalog = await response.json();
  metadataState.assets = metadataState.catalog.assets || [];
  renderMetadataSummary(metadataState.catalog.summary || {});
  const preferred = metadataState.assets.find((asset) => asset.kind === "table") || metadataState.assets[0];
  if (!metadataState.selectedAssetId || !metadataState.assets.some((asset) => asset.id === metadataState.selectedAssetId)) {
    metadataState.selectedAssetId = preferred?.id || "";
  }
  renderAssetList();
  renderAssetDetail(metadataState.assets.find((asset) => asset.id === metadataState.selectedAssetId));
  setMetadataStatus(
    metadataState.catalog.summary?.iceberg_verified ? "Iceberg 已验证" : "元数据可用",
    metadataState.catalog.summary?.iceberg_verified ? "ready" : "blocked",
  );
}

metadataQuery("#assetSearch").addEventListener("input", renderAssetList);
metadataQuery("#refreshMetadata").addEventListener("click", () => {
  loadMetadata().catch((error) => setMetadataStatus(`加载失败: ${error.message}`, "failed"));
});
document.querySelectorAll("[data-metadata-tab]").forEach((button) => {
  button.addEventListener("click", () => selectMetadataTab(button.dataset.metadataTab));
});
window.addEventListener("app:localechange", () => window.i18n?.refresh());

loadMetadata().catch((error) => {
  setMetadataStatus(`加载失败: ${error.message}`, "failed");
  metadataQuery("#assetList").replaceChildren(metadataNode("div", "empty-state", error.message));
});
