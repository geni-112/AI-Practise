from __future__ import annotations

from typing import Any

from .chatbi import semantic_catalog


RAW_COLUMNS = [
    {"name": "taxpayer_id", "type": "string", "nullable": False, "classification": "internal_id"},
    {
        "name": "rfc",
        "type": "string",
        "nullable": False,
        "classification": "direct_identifier",
        "policy": "Hash and mask before Gold publication.",
    },
    {"name": "year", "type": "int", "nullable": False, "classification": "business_dimension"},
    {"name": "region", "type": "string", "nullable": False, "classification": "business_dimension"},
    {"name": "regime", "type": "string", "nullable": False, "classification": "business_dimension"},
    {"name": "resico_flag", "type": "boolean", "nullable": False, "classification": "business_dimension"},
    {"name": "annual_income", "type": "bigint", "nullable": False, "classification": "confidential"},
]

GOLD_COLUMNS = [
    {"name": "year", "type": "string", "nullable": False, "classification": "business_dimension"},
    {"name": "region", "type": "string", "nullable": False, "classification": "business_dimension"},
    {"name": "regime", "type": "string", "nullable": False, "classification": "business_dimension"},
    {"name": "resico_flag", "type": "boolean", "nullable": False, "classification": "business_dimension"},
    {"name": "taxpayer_count", "type": "bigint", "nullable": False, "classification": "aggregate_metric"},
    {"name": "annual_income_total", "type": "bigint", "nullable": True, "classification": "aggregate_metric"},
    {"name": "annual_income_avg", "type": "double", "nullable": True, "classification": "aggregate_metric"},
]


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def build_metadata_center(evidence: dict[str, object]) -> dict[str, Any]:
    catalog = semantic_catalog(evidence)
    iceberg = _dict(evidence.get("iceberg"))
    verified = bool(iceberg.get("verified"))
    bucket = str(evidence.get("bucket") or "")
    run_id = str(evidence.get("run_id") or "")
    raw_location = (
        f"obs://{bucket}/raw/sat/{run_id}/taxpayer_registry.csv"
        if bucket and run_id
        else ""
    )
    gold_location = str(
        iceberg.get("table_location")
        or evidence.get("gold_prefix")
        or ""
    )
    qualified_name = str(
        iceberg.get("qualified_name")
        or "spark_catalog.tax_gold.taxpayer_regime_year"
    )
    snapshots = [_dict(item) for item in _list(iceberg.get("snapshots"))]
    metrics = [
        {
            "name": name,
            "label": definition.get("label", name),
            "aggregation": definition.get("aggregation", ""),
            "source_columns": definition.get("source_columns", []),
        }
        for name, definition in _dict(catalog.get("metrics")).items()
        if isinstance(definition, dict)
    ]
    dimensions = [
        {
            "name": name,
            "label": definition.get("label", name),
            "column": definition.get("column", name),
            "values": definition.get("values", []),
        }
        for name, definition in _dict(catalog.get("dimensions")).items()
        if isinstance(definition, dict)
    ]

    assets = [
        {
            "id": "raw.sat.taxpayer_registry",
            "name": "taxpayer_registry",
            "display_name": "纳税人登记原始数据",
            "qualified_name": "raw.sat.taxpayer_registry",
            "kind": "source",
            "layer": "Raw",
            "format": "CSV",
            "status": "active" if raw_location else "unavailable",
            "description": "Synthetic SAT-like source rows used by the governed MRS pipeline.",
            "location": raw_location,
            "owner": "SAT Data Platform",
            "columns": RAW_COLUMNS,
            "partitioning": [],
            "properties": {
                "append_policy": "run-scoped immutable input",
                "contains_direct_identifiers": True,
            },
            "metrics": [],
            "dimensions": [],
            "snapshots": [],
        },
        {
            "id": qualified_name,
            "name": "taxpayer_regime_year",
            "display_name": "纳税人年度 Gold 表",
            "qualified_name": qualified_name,
            "kind": "table",
            "layer": "Gold",
            "format": "Apache Iceberg" if verified else "CSV compatibility output",
            "status": "verified" if verified else "migration_pending",
            "description": str(catalog.get("description") or ""),
            "location": gold_location,
            "owner": "SAT Data Platform",
            "columns": _list(iceberg.get("schema")) or GOLD_COLUMNS,
            "partitioning": _list(iceberg.get("partitioning")) or ["year"],
            "properties": {
                "format_version": iceberg.get("format_version", 2 if verified else ""),
                "catalog": iceberg.get("catalog", "spark_catalog"),
                "namespace": iceberg.get("namespace", "tax_gold"),
                "current_snapshot_id": iceberg.get("current_snapshot_id", ""),
                "manifest_list": iceberg.get("metadata_location", ""),
            },
            "metrics": metrics,
            "dimensions": dimensions,
            "snapshots": snapshots,
        },
        {
            "id": f"semantic.{catalog.get('dataset', 'tax_gold.taxpayer_regime_year')}",
            "name": str(catalog.get("dataset") or "tax_gold.taxpayer_regime_year"),
            "display_name": "ChatBI 受控语义模型",
            "qualified_name": f"semantic.{catalog.get('dataset', 'tax_gold.taxpayer_regime_year')}",
            "kind": "semantic_model",
            "layer": "Serving",
            "format": "Semantic model",
            "status": "active",
            "description": "Allowlisted dimensions and metrics supplied to deterministic and MaaS query planning.",
            "location": "/api/chatbi/catalog",
            "owner": "SAT Analytics",
            "columns": GOLD_COLUMNS,
            "partitioning": [],
            "properties": {
                "catalog_version": catalog.get("version", ""),
                "direct_identifiers_available": _dict(catalog.get("privacy")).get(
                    "direct_identifiers_available", False
                ),
                "blocked_fields": _dict(catalog.get("privacy")).get("blocked_fields", []),
            },
            "metrics": metrics,
            "dimensions": dimensions,
            "snapshots": [],
        },
    ]

    lineage = {
        "nodes": [
            {"id": assets[0]["id"], "label": "OBS Raw CSV", "kind": "source"},
            {"id": "mrs.spark.sat_taxpayer_etl", "label": "MRS Spark ETL", "kind": "job"},
            {"id": assets[1]["id"], "label": "Iceberg Gold", "kind": "table"},
            {"id": assets[2]["id"], "label": "ChatBI Semantic Model", "kind": "semantic_model"},
            {"id": "chatbi.query", "label": "Governed ChatBI Query", "kind": "consumer"},
        ],
        "edges": [
            {
                "from": assets[0]["id"],
                "to": "mrs.spark.sat_taxpayer_etl",
                "control": "Year/region validation, RFC hashing and masking",
            },
            {
                "from": "mrs.spark.sat_taxpayer_etl",
                "to": assets[1]["id"],
                "control": "Aggregate and commit an atomic Iceberg snapshot",
            },
            {
                "from": assets[1]["id"],
                "to": assets[2]["id"],
                "control": "Allowlisted dimensions, metrics and privacy policy",
            },
            {
                "from": assets[2]["id"],
                "to": "chatbi.query",
                "control": "Read-only parameterized SQL contract",
            },
        ],
    }

    return {
        "version": "sat-metadata-center-v1",
        "generated_at": evidence.get("generated_at", ""),
        "run_id": run_id,
        "region": evidence.get("region", ""),
        "summary": {
            "asset_count": len(assets),
            "table_count": 1,
            "column_count": len(GOLD_COLUMNS),
            "metric_count": len(metrics),
            "snapshot_count": len(snapshots),
            "iceberg_verified": verified,
        },
        "assets": assets,
        "lineage": lineage,
        "governance": {
            "privacy": catalog.get("privacy", {}),
            "dataarts_catalog_available": False,
            "dataarts_note": (
                "The reused DataArts Starter instance does not include DataArts Catalog. "
                "This page is backed by application semantic metadata and MRS execution evidence."
            ),
        },
    }
