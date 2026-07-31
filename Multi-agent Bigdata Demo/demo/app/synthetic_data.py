from __future__ import annotations

from hashlib import sha256
from typing import Any


BASE_ROWS = [
    ("AAA010101A01", "CDMX", "601", False, "ACTIVE", 184500.25, "2024"),
    ("BBB020202B02", "Jalisco", "626", True, "ACTIVE", 76120.0, "2024"),
    ("CCC030303C03", "Nuevo Leon", "603", False, "ACTIVE", 239800.75, "2024"),
    ("DDD040404D04", "Yucatan", "601", False, "SUSPENDED", 41200.0, "2024"),
    ("EEE050505E05", "CDMX", "626", True, "ACTIVE", 55880.5, "2024"),
    ("FFF060606F06", "Puebla", "612", False, "ACTIVE", 119900.0, "2024"),
    ("GGG070707G07", "CDMX", "601", False, "ACTIVE", 188900.0, "2025"),
    ("HHH080808H08", "CDMX", "603", False, "ACTIVE", 301500.3, "2025"),
    ("III090909I09", "Jalisco", "626", True, "ACTIVE", 88900.0, "2025"),
    ("JJJ101010J10", "Puebla", "601", False, "ACTIVE", 97050.8, "2025"),
]


def make_synthetic_rows(scenario: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, (rfc, region, regime, is_resico, status, amount, year) in enumerate(BASE_ROWS, start=1):
        rows.append(
            {
                "row_id": idx,
                "rfc_hash": sha256(rfc.encode("utf-8")).hexdigest()[:16],
                "masked_rfc": f"{rfc[:3]}***{rfc[-3:]}",
                "region": region,
                "cve_regimen": regime,
                "is_resico": is_resico,
                "status": status,
                "declared_amount": amount,
                "ejercicio_analisis": year,
                "scenario": scenario,
            }
        )
    return rows


def aggregate_gold(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, bool], dict[str, Any]] = {}
    for row in rows:
        key = (
            row["ejercicio_analisis"],
            row["region"],
            row["cve_regimen"],
            row["is_resico"],
        )
        bucket = grouped.setdefault(
            key,
            {
                "ejercicio_analisis": row["ejercicio_analisis"],
                "region": row["region"],
                "cve_regimen": row["cve_regimen"],
                "is_resico": row["is_resico"],
                "active_taxpayers": 0,
                "total_declared_amount": 0.0,
            },
        )
        if row["status"] == "ACTIVE":
            bucket["active_taxpayers"] += 1
        bucket["total_declared_amount"] += float(row["declared_amount"])
    return list(grouped.values())
