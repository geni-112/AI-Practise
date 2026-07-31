from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


REGION_ALIASES = {
    "CDMX": ("cdmx", "墨西哥城"),
    "Jalisco": ("jalisco", "哈利斯科"),
    "Nuevo Leon": ("nuevo leon", "nuevo león", "新莱昂"),
    "Puebla": ("puebla", "普埃布拉"),
    "Yucatan": ("yucatan", "yucatán", "尤卡坦"),
}

REGIME_ALIASES = {
    "Persona Moral": ("persona moral", "法人"),
    "Persona Fisica": ("persona fisica", "persona física", "自然人"),
    "General": ("general", "一般税制"),
}

METRICS = {
    "taxpayer_count": {"label": "纳税人数量", "format": "integer"},
    "annual_income_total": {"label": "收入合计", "format": "number"},
    "annual_income_avg": {"label": "人均收入", "format": "number"},
}

METRIC_LABELS_EN = {
    "taxpayer_count": "Taxpayers",
    "annual_income_total": "Total annual income",
    "annual_income_avg": "Average annual income",
}

CATALOG_PATH = Path(__file__).with_name("chatbi_catalog.json")
BASE_SEMANTIC_CATALOG = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
SEMANTIC_CATALOG_VERSION = str(BASE_SEMANTIC_CATALOG["version"])
SEMANTIC_DATASET = str(BASE_SEMANTIC_CATALOG["dataset"])
ALLOWED_DIMENSIONS = {"region", "regime", "resico_flag"}
ALLOWED_METRICS = set(METRICS)


class ChatBIIntentContract(BaseModel):
    intent: Literal["query", "development", "clarification"]
    year: str = ""
    region: str = ""
    regime: str = ""
    resico: bool | None = None
    group_by: Literal["", "region", "regime", "resico_flag"] = ""
    metrics: list[Literal["taxpayer_count", "annual_income_total", "annual_income_avg"]] = Field(
        default_factory=list,
        max_length=3,
    )
    primary_metric: Literal["taxpayer_count", "annual_income_total", "annual_income_avg"] = (
        "taxpayer_count"
    )
    limit: int = Field(default=10, ge=1, le=20)
    ascending: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    clarification: str = ""


def semantic_catalog(evidence: dict[str, object]) -> dict[str, Any]:
    raw_rows = evidence.get("gold_preview_rows")
    rows = [row for row in raw_rows if isinstance(row, dict)] if isinstance(raw_rows, list) else []
    return {
        "version": SEMANTIC_CATALOG_VERSION,
        "dataset": SEMANTIC_DATASET,
        "description": BASE_SEMANTIC_CATALOG["description"],
        "dimensions": {
            "year": {
                **BASE_SEMANTIC_CATALOG["dimensions"]["year"],
                "values": sorted({str(row.get("year", "")) for row in rows if row.get("year")}),
            },
            "region": {
                **BASE_SEMANTIC_CATALOG["dimensions"]["region"],
                "values": sorted({str(row.get("region", "")) for row in rows if row.get("region")}),
            },
            "regime": {
                **BASE_SEMANTIC_CATALOG["dimensions"]["regime"],
                "values": sorted({str(row.get("regime", "")) for row in rows if row.get("regime")}),
            },
            "resico_flag": {
                **BASE_SEMANTIC_CATALOG["dimensions"]["resico_flag"],
                "values": [True, False],
            },
        },
        "metrics": BASE_SEMANTIC_CATALOG["metrics"],
        "privacy": BASE_SEMANTIC_CATALOG["privacy"],
    }


def _contains_any(text: str, values: Iterable[str]) -> bool:
    return any(value in text for value in values)


def is_explicit_engineering_prompt(prompt: str) -> bool:
    text = re.sub(r"\s+", " ", prompt).strip().lower()
    return _contains_any(
        text,
        (
            "pyspark",
            "dataarts",
            "dag",
            "notebook",
            "迁移",
            "部署",
            "创建云资源",
            "创建集群",
            "生成脚本",
            "生成代码",
            "业务编排",
            "开发任务",
            "pipeline",
            "terraform",
        ),
    )


def redact_prompt_for_maas(prompt: str) -> tuple[str, bool]:
    redacted = re.sub(
        r"\b[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}\b",
        "[RFC_REDACTED]",
        prompt,
        flags=re.IGNORECASE,
    )
    redacted = re.sub(
        r"(?i)\b(api[_ -]?key|secret[_ -]?key|access[_ -]?key|password|token)\s*[:=]\s*\S+",
        r"\1=[REDACTED]",
        redacted,
    )
    redacted = re.sub(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", redacted)
    return redacted, redacted != prompt


def is_chatbi_prompt(prompt: str) -> bool:
    text = re.sub(r"\s+", " ", prompt).strip().lower()
    if not text:
        return False

    result_markers = (
        "报表",
        "结果",
        "查询",
        "查一下",
        "看一下",
        "展示",
        "多少",
        "排名",
        "趋势",
        "对比",
        "分布",
        "占比",
        "汇总",
        "平均",
        "最高",
        "最低",
        "how many",
        "show me",
        "report",
        "dashboard",
        "compare",
        "rank ",
        "ranking",
        "top ",
    )
    data_markers = (
        "纳税人",
        "收入",
        "税基",
        "税制",
        "resico",
        "地区",
        "region",
        "regime",
        "taxpayer",
        "income",
    )
    summary_markers = (
        "最终结果",
        "最终的结果",
        "整体结果",
        "整体情况",
        "总览",
        "summary",
    )

    wants_result = _contains_any(text, result_markers)
    if is_explicit_engineering_prompt(prompt):
        return False
    return (wants_result and _contains_any(text, data_markers)) or _contains_any(text, summary_markers)


def _number(value: object) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _match_alias(text: str, aliases: dict[str, tuple[str, ...]]) -> str:
    for canonical, values in aliases.items():
        if any(value in text for value in values):
            return canonical
    return ""


def _metric_selection(text: str) -> tuple[list[str], str]:
    wants_average = _contains_any(text, ("平均", "人均", "均值", "average", "avg"))
    wants_income = _contains_any(text, ("收入", "金额", "税基", "income", "amount"))
    wants_count = _contains_any(text, ("纳税人", "人数", "数量", "户数", "count"))

    metrics: list[str] = []
    if wants_count:
        metrics.append("taxpayer_count")
    if wants_income:
        metrics.append("annual_income_avg" if wants_average else "annual_income_total")
    if wants_average and "annual_income_avg" not in metrics:
        metrics.append("annual_income_avg")
    if not metrics:
        metrics = ["taxpayer_count", "annual_income_total"]

    if wants_average:
        primary = "annual_income_avg"
    elif wants_income:
        primary = "annual_income_total"
    else:
        primary = "taxpayer_count"
    if primary not in metrics:
        metrics.append(primary)
    return metrics, primary


def _query_spec(prompt: str) -> dict[str, Any]:
    text = re.sub(r"\s+", " ", prompt).strip().lower()
    year_match = re.search(r"\b(20\d{2})\b", text)
    region = _match_alias(text, REGION_ALIASES)
    regime = _match_alias(text, REGIME_ALIASES)

    resico_compare = "resico" in text and _contains_any(
        text,
        ("对比", "比较", "vs", "versus", "非resico", "非 resico"),
    )
    resico_filter: bool | None = None
    if not resico_compare and "resico" in text:
        resico_filter = not _contains_any(text, ("非resico", "非 resico", "not resico"))
        if resico_filter:
            regime = "RESICO"

    group_by = ""
    if "地区" in text and _contains_any(text, ("各地区", "按地区", "地区排名", "地区分布", "哪个地区", "不同地区")):
        group_by = "region"
    elif _contains_any(text, ("by region", "regional ranking", "regions")):
        group_by = "region"
    elif "税制" in text and _contains_any(text, ("各税制", "按税制", "税制排名", "税制分布", "不同税制")):
        group_by = "regime"
    elif _contains_any(text, ("by regime", "by tax regime", "tax regimes", "regimes")):
        group_by = "regime"
    elif resico_compare:
        group_by = "resico_flag"
    elif not region and not regime and _contains_any(text, ("报表", "report", "dashboard", "排名", "分布")):
        group_by = "region"

    metrics, primary_metric = _metric_selection(text)
    top_match = re.search(r"(?:top\s*|前\s*)(\d{1,2})", text)
    limit = max(1, min(int(top_match.group(1)), 20)) if top_match else 10
    ascending = _contains_any(text, ("最低", "最少", "bottom", "least", "ascending"))
    return {
        "year": year_match.group(1) if year_match else "",
        "region": region,
        "regime": regime,
        "resico": resico_filter,
        "group_by": group_by,
        "metrics": metrics,
        "primary_metric": primary_metric,
        "limit": limit,
        "ascending": ascending,
    }


def _matches(row: dict[str, object], spec: dict[str, Any]) -> bool:
    if spec["year"] and str(row.get("year", "")) != spec["year"]:
        return False
    if spec["region"] and str(row.get("region", "")) != spec["region"]:
        return False
    if spec["regime"] and str(row.get("regime", "")) != spec["regime"]:
        return False
    if spec["resico"] is not None:
        row_resico = str(row.get("resico_flag", "")).lower() in {"true", "1", "yes"}
        if row_resico is not spec["resico"]:
            return False
    return True


def _group_label(group_by: str, value: str, locale: str = "zh") -> str:
    if group_by == "resico_flag":
        if value.lower() in {"true", "1", "yes"}:
            return "RESICO"
        return "Non-RESICO" if locale == "en" else "非 RESICO"
    return value or ("Unclassified" if locale == "en" else "未分类")


def _aggregate(
    rows: list[dict[str, object]],
    spec: dict[str, Any],
    locale: str = "zh",
) -> list[dict[str, Any]]:
    group_by = spec["group_by"]
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        raw_key = str(row.get(group_by, "全部")) if group_by else "全部"
        bucket = buckets.setdefault(
            raw_key,
            {
                "group": _group_label(group_by, raw_key, locale),
                "taxpayer_count": 0,
                "annual_income_total": 0.0,
            },
        )
        bucket["taxpayer_count"] += int(_number(row.get("taxpayer_count")))
        bucket["annual_income_total"] += _number(row.get("annual_income_total"))

    for bucket in buckets.values():
        count = bucket["taxpayer_count"]
        bucket["annual_income_total"] = round(bucket["annual_income_total"], 2)
        bucket["annual_income_avg"] = round(bucket["annual_income_total"] / count, 2) if count else 0.0

    primary = spec["primary_metric"]
    return sorted(
        buckets.values(),
        key=lambda item: (item.get(primary, 0), item["group"]),
        reverse=not spec["ascending"],
    )


def _format_number(value: float | int) -> str:
    return f"{value:,.0f}"


def _answer_text(
    spec: dict[str, Any],
    aggregated: list[dict[str, Any]],
    total_count: int,
    total_income: float,
    locale: str = "zh",
) -> str:
    if not aggregated:
        if locale == "en":
            return (
                "No Gold results match these filters. Try removing a region, regime, "
                "or year constraint."
            )
        return "当前 Gold 结果中没有匹配这些条件的数据。你可以减少地区、税制或年份限制后再试。"

    if locale == "en":
        scope = f"For {spec['year']}, " if spec["year"] else "In the current published batch, "
        if spec["group_by"]:
            leader = aggregated[0]
            metric = _metric_label(spec["primary_metric"], locale)
            leader_value = _format_number(leader[spec["primary_metric"]])
            direction = "lowest" if spec["ascending"] else "highest"
            return (
                f"{scope}{_format_number(total_count)} taxpayers match, with total annual income "
                f"of {_format_number(total_income)}. Grouped by "
                f"{_dimension_label(spec['group_by'], locale).lower()}, {leader['group']} has the "
                f"{direction} {metric.lower()} at {leader_value}."
            )
        row = aggregated[0]
        return (
            f"{scope}{_format_number(row['taxpayer_count'])} taxpayers match, with total annual "
            f"income of {_format_number(row['annual_income_total'])} and average annual income "
            f"of {_format_number(row['annual_income_avg'])}."
        )

    scope = f"{spec['year']} 年" if spec["year"] else "当前发布批次"
    if spec["group_by"]:
        leader = aggregated[0]
        metric = _metric_label(spec["primary_metric"], locale)
        leader_value = _format_number(leader[spec["primary_metric"]])
        direction = "最低" if spec["ascending"] else "最高"
        return (
            f"{scope}匹配结果包含 {_format_number(total_count)} 名纳税人，收入合计 "
            f"{_format_number(total_income)}。按{_dimension_label(spec['group_by'], locale)}比较，"
            f"{leader['group']}的{metric}{direction}，为 {leader_value}。"
        )
    row = aggregated[0]
    return (
        f"{scope}匹配 {_format_number(row['taxpayer_count'])} 名纳税人，收入合计 "
        f"{_format_number(row['annual_income_total'])}，人均收入 "
        f"{_format_number(row['annual_income_avg'])}。"
    )


def _metric_label(metric: str, locale: str = "zh") -> str:
    if locale == "en":
        return METRIC_LABELS_EN.get(metric, metric)
    return METRICS.get(metric, {"label": metric})["label"]


def _metric_metadata(metric: str, locale: str = "zh") -> dict[str, str]:
    return {**METRICS[metric], "label": _metric_label(metric, locale)}


def _dimension_label(group_by: str, locale: str = "zh") -> str:
    labels = {
        "region": "地区",
        "regime": "税制",
        "resico_flag": "RESICO 状态",
    }
    if locale == "en":
        labels = {
            "region": "Region",
            "regime": "Tax regime",
            "resico_flag": "RESICO status",
        }
    return labels.get(group_by, "Group" if locale == "en" else "分组")


def _filter_labels(spec: dict[str, Any], locale: str = "zh") -> list[str]:
    labels = []
    if spec["year"]:
        labels.append(f"{'Year' if locale == 'en' else '年份'}={spec['year']}")
    if spec["region"]:
        labels.append(f"{'Region' if locale == 'en' else '地区'}={spec['region']}")
    if spec["regime"]:
        labels.append(f"{'Tax regime' if locale == 'en' else '税制'}={spec['regime']}")
    if spec["resico"] is False:
        labels.append("RESICO=No" if locale == "en" else "RESICO=否")
    return labels


def _suggestions(locale: str) -> list[str]:
    if locale == "en":
        return [
            "Rank total annual income by region for 2025",
            "Compare taxpayer counts by tax regime",
            "What is the average income of RESICO taxpayers?",
        ]
    return [
        "2025 年各地区收入合计排名",
        "各税制的纳税人数量对比",
        "RESICO 纳税人的人均收入是多少？",
    ]


def _canonical_catalog_value(
    value: str,
    allowed_values: list[object],
    aliases: dict[str, tuple[str, ...]] | None = None,
) -> str:
    if not value:
        return ""
    allowed = {str(item).lower(): str(item) for item in allowed_values}
    normalized = value.strip().lower()
    if normalized in allowed:
        return allowed[normalized]
    if aliases:
        alias_match = _match_alias(normalized, aliases)
        if alias_match and alias_match.lower() in allowed:
            return allowed[alias_match.lower()]
    raise ValueError(f"Value is not present in the governed semantic catalog: {value}")


def normalize_maas_intent(payload: dict[str, Any], evidence: dict[str, object]) -> dict[str, Any]:
    try:
        contract = ChatBIIntentContract.model_validate(payload)
    except ValidationError as exc:
        raise ValueError("MaaS ChatBI intent did not match the required contract") from exc

    if contract.intent != "query":
        return contract.model_dump(mode="json")

    catalog = semantic_catalog(evidence)
    dimensions = catalog["dimensions"]
    year = _canonical_catalog_value(contract.year, dimensions["year"]["values"])
    region = _canonical_catalog_value(
        contract.region,
        dimensions["region"]["values"],
        REGION_ALIASES,
    )
    regime = _canonical_catalog_value(
        contract.regime,
        dimensions["regime"]["values"],
        REGIME_ALIASES,
    )
    metrics = list(dict.fromkeys(contract.metrics or [contract.primary_metric]))
    if contract.primary_metric not in metrics:
        metrics.append(contract.primary_metric)
    if not set(metrics).issubset(ALLOWED_METRICS):
        raise ValueError("MaaS requested a metric outside the governed semantic catalog")
    if contract.group_by and contract.group_by not in ALLOWED_DIMENSIONS:
        raise ValueError("MaaS requested a dimension outside the governed semantic catalog")

    normalized = contract.model_dump(mode="json")
    normalized.update(
        {
            "year": year,
            "region": region,
            "regime": regime,
            "metrics": metrics,
        }
    )
    return normalized


def _spec_from_intent(intent: dict[str, Any]) -> dict[str, Any]:
    return {
        "year": intent.get("year", ""),
        "region": intent.get("region", ""),
        "regime": intent.get("regime", ""),
        "resico": intent.get("resico"),
        "group_by": intent.get("group_by", ""),
        "metrics": intent.get("metrics") or [intent.get("primary_metric", "taxpayer_count")],
        "primary_metric": intent.get("primary_metric", "taxpayer_count"),
        "limit": max(1, min(int(intent.get("limit", 10)), 20)),
        "ascending": bool(intent.get("ascending", False)),
    }


def compile_safe_sql(spec: dict[str, Any]) -> dict[str, Any]:
    dimension_columns = {
        "region": "region",
        "regime": "regime",
        "resico_flag": "resico_flag",
    }
    metric_expressions = {
        "taxpayer_count": "SUM(taxpayer_count) AS taxpayer_count",
        "annual_income_total": "SUM(annual_income_total) AS annual_income_total",
        "annual_income_avg": (
            "CASE WHEN SUM(taxpayer_count) = 0 THEN 0 "
            "ELSE SUM(annual_income_total) / SUM(taxpayer_count) END AS annual_income_avg"
        ),
    }
    metrics = [metric for metric in spec["metrics"] if metric in metric_expressions]
    primary_metric = spec["primary_metric"] if spec["primary_metric"] in metric_expressions else metrics[0]
    if primary_metric not in metrics:
        metrics.append(primary_metric)

    select_parts = []
    group_by = spec.get("group_by", "")
    if group_by:
        select_parts.append(dimension_columns[group_by])
    select_parts.extend(metric_expressions[metric] for metric in metrics)

    predicates = []
    parameters: dict[str, Any] = {}
    if spec.get("year"):
        predicates.append("year = :year")
        parameters["year"] = int(spec["year"])
    if spec.get("region"):
        predicates.append("region = :region")
        parameters["region"] = spec["region"]
    if spec.get("regime"):
        predicates.append("regime = :regime")
        parameters["regime"] = spec["regime"]
    if spec.get("resico") is not None:
        predicates.append("resico_flag = :resico")
        parameters["resico"] = bool(spec["resico"])

    lines = [f"SELECT {', '.join(select_parts)}", f"FROM {SEMANTIC_DATASET}"]
    if predicates:
        lines.append(f"WHERE {' AND '.join(predicates)}")
    if group_by:
        lines.append(f"GROUP BY {dimension_columns[group_by]}")
    lines.append(f"ORDER BY {primary_metric} {'ASC' if spec['ascending'] else 'DESC'}")
    lines.append(f"LIMIT {max(1, min(int(spec['limit']), 20))}")
    return {
        "dialect": "GaussDB(DWS)-compatible SQL",
        "sql": "\n".join(lines),
        "parameters": parameters,
        "read_only": True,
        "identifiers_allowlisted": True,
        "values_parameterized": True,
    }


def _base_empty_response(
    *,
    handled: bool,
    available: bool,
    answer: str = "",
    query_plan: dict[str, Any] | None = None,
    suggestions: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "handled": handled,
        "available": available,
        "answer": answer,
        "kpis": [],
        "chart": {},
        "table": {"columns": [], "rows": []},
        "query_plan": query_plan or {},
        "source": {},
        "suggestions": suggestions or [],
    }


def build_chatbi_response(
    prompt: str,
    evidence: dict[str, object],
    intent_contract: dict[str, Any] | None = None,
    parser_trace: dict[str, Any] | None = None,
    locale: Literal["zh", "en"] = "zh",
) -> dict[str, Any]:
    parser = parser_trace or {
        "mode": "deterministic",
        "requested": False,
        "configured": False,
        "used": False,
        "model": "",
        "fallback": False,
    }
    if intent_contract:
        intent = intent_contract.get("intent")
        if intent == "development":
            return _base_empty_response(
                handled=False,
                available=bool(evidence.get("available")),
                query_plan={"semantic_parser": parser, "intent": "development"},
            )
        if intent == "clarification":
            answer = intent_contract.get("clarification") or (
                "I cannot map that question to the governed Tax metric catalog yet. "
                "Add a year, region, tax regime, and the taxpayer or income metric you need."
                if locale == "en"
                else "我还不能把这个问题映射到当前 Tax 指标目录。请补充年份、地区、税制，"
                "以及要查看的纳税人数量或收入指标。"
            )
            return _base_empty_response(
                handled=True,
                available=bool(evidence.get("available")),
                answer=answer,
                query_plan={
                    "semantic_parser": parser,
                    "intent": "clarification",
                    "catalog_version": SEMANTIC_CATALOG_VERSION,
                },
                suggestions=_suggestions(locale),
            )
        spec = _spec_from_intent(intent_contract)
    else:
        if not is_chatbi_prompt(prompt):
            return _base_empty_response(
                handled=False,
                available=bool(evidence.get("available")),
                query_plan={"semantic_parser": parser},
            )
        spec = _query_spec(prompt)

    raw_rows = evidence.get("gold_preview_rows")
    rows = [row for row in raw_rows if isinstance(row, dict)] if isinstance(raw_rows, list) else []
    if not evidence.get("available") or not rows:
        result = _base_empty_response(
            handled=True,
            available=False,
            answer=(
                "No published Gold result is available yet. Run and publish a data task first."
                if locale == "en"
                else "当前还没有可查询的 Gold 结果。请先完成一次数据任务执行并发布结果。"
            ),
            query_plan={"semantic_parser": parser},
        )
        result["source"] = {"status": evidence.get("status", "not_run")}
        return result

    filtered = [row for row in rows if _matches(row, spec)]
    all_aggregated = _aggregate(filtered, spec, locale)
    aggregated = all_aggregated[: spec["limit"]]
    total_count = sum(int(row["taxpayer_count"]) for row in all_aggregated)
    total_income = sum(float(row["annual_income_total"]) for row in all_aggregated)
    total_average = round(total_income / total_count, 2) if total_count else 0.0

    dimension_label = _dimension_label(spec["group_by"], locale)
    columns = []
    if spec["group_by"]:
        columns.append({"key": "group", "label": dimension_label, "format": "text"})
    else:
        columns.append(
            {"key": "group", "label": "Scope" if locale == "en" else "范围", "format": "text"}
        )
    columns.extend(
        {"key": metric, **_metric_metadata(metric, locale)}
        for metric in spec["metrics"]
    )

    chart = {}
    if spec["group_by"] and aggregated:
        primary = spec["primary_metric"]
        chart = {
            "type": "bar",
            "title": (
                f"{_metric_label(primary, locale)} by {dimension_label.lower()}"
                if locale == "en"
                else f"按{dimension_label}查看{_metric_label(primary, locale)}"
            ),
            "category_key": "group",
            "series": [{"key": primary, **_metric_metadata(primary, locale)}],
            "rows": aggregated,
        }

    return {
        "handled": True,
        "available": True,
        "answer": _answer_text(spec, aggregated, total_count, total_income, locale),
        "kpis": [
            {"label": _metric_label("taxpayer_count", locale), "value": total_count, "format": "integer"},
            {"label": _metric_label("annual_income_total", locale), "value": round(total_income, 2), "format": "number"},
            {"label": _metric_label("annual_income_avg", locale), "value": total_average, "format": "number"},
            {"label": "Result groups" if locale == "en" else "结果分组", "value": len(all_aggregated), "format": "integer"},
        ],
        "chart": chart,
        "table": {"columns": columns, "rows": aggregated},
        "query_plan": {
            "dataset": SEMANTIC_DATASET,
            "catalog_version": SEMANTIC_CATALOG_VERSION,
            "filters": _filter_labels(spec, locale),
            "group_by": spec["group_by"] or "none",
            "metrics": spec["metrics"],
            "sort": f"{spec['primary_metric']} {'asc' if spec['ascending'] else 'desc'}",
            "rows_scanned": len(rows),
            "rows_matched": len(filtered),
            "execution_mode": "maas_semantic_contract" if parser.get("used") else "deterministic_semantic_layer",
            "maas_used": bool(parser.get("used")),
            "semantic_parser": parser,
            "semantic_contract": {
                "year": spec["year"],
                "region": spec["region"],
                "regime": spec["regime"],
                "resico": spec["resico"],
                "group_by": spec["group_by"],
                "metrics": spec["metrics"],
                "primary_metric": spec["primary_metric"],
                "limit": spec["limit"],
                "ascending": spec["ascending"],
                "confidence": intent_contract.get("confidence", 1.0) if intent_contract else 1.0,
            },
            "compiled_query": compile_safe_sql(spec),
        },
        "source": {
            "label": (
                "Published Huawei Cloud MRS Gold result"
                if locale == "en"
                else "Huawei Cloud MRS Gold 发布结果"
            ),
            "run_id": evidence.get("run_id", ""),
            "generated_at": evidence.get("generated_at", ""),
            "gold_prefix": evidence.get("gold_prefix", ""),
            "note": (
                "This demo queries the published Gold snapshot and never scans raw RFC values."
                if locale == "en"
                else "当前演示查询已发布的 Gold 快照，不会扫描原始 RFC。"
            ),
        },
        "suggestions": _suggestions(locale),
    }
