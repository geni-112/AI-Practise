#!/usr/bin/env python3
"""Scan source trees for Databricks/Snowflake migration signals."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


TEXT_EXTENSIONS = {
    ".py",
    ".sql",
    ".scala",
    ".java",
    ".r",
    ".ipynb",
    ".json",
    ".yaml",
    ".yml",
    ".txt",
    ".md",
}

PATTERNS = {
    "delta_lake": [
        r"\bformat\s*\(\s*['\"]delta['\"]\s*\)",
        r"\bUSING\s+DELTA\b",
        r"\bDeltaTable\b",
        r"_delta_log",
        r"overwriteSchema",
        r"\bMERGE\s+INTO\b",
        r"\bOPTIMIZE\b",
        r"\bVACUUM\b",
        r"\bVERSION\s+AS\s+OF\b",
        r"\bTIMESTAMP\s+AS\s+OF\b",
        r"\breadChangeFeed\b|\bchange\s+data\s+feed\b",
    ],
    "databricks": [
        r"\bdbutils\.",
        r"dbutils\.notebook\.run",
        r"dbutils\.notebook\.exit",
        r"entry_point",
        r"dbfs:/",
        r"/mnt/",
        r"%run\b",
        r"\bnotebook_task\b",
        r"\bnew_cluster\b",
        r"\bexisting_cluster_id\b",
        r"\bspark_python_task\b",
        r"\bDATABRICKS\b",
    ],
    "snowflake": [
        r"\bCOPY\s+INTO\b",
        r"\bQUALIFY\b",
        r"\bVARIANT\b",
        r"\bTIMESTAMP_NTZ\b|\bTIMESTAMP_LTZ\b|\bTIMESTAMP_TZ\b",
        r"\bIFF\s*\(",
        r"\bTRY_TO_",
        r"\bCREATE\s+OR\s+REPLACE\b",
        r"\bSNOWFLAKE\b",
        r"::\s*(NUMBER|VARCHAR|TIMESTAMP|DATE|BOOLEAN)",
    ],
    "dws_attention": [
        r"\bQUALIFY\b",
        r"\bMERGE\s+INTO\b",
        r"\bVARIANT\b|\bOBJECT\b|\bARRAY\b",
        r"\bCREATE\s+OR\s+REPLACE\b",
        r"\bLATERAL\s+FLATTEN\b",
        r"\bDATEADD\s*\(",
        r"\bDATEDIFF\s*\(",
        r"\bSELECT\s+\*\s+EXCEPT\b",
    ],
    "spark_sql_attention": [
        r"\bDATEADD\s*\(",
        r"\bSELECT\s+\*\s+EXCEPT\b",
        r"\bEXISTS\s*\(",
        r"Couldn't find .* in \[",
        r"\bLeftExistenceJoin\b",
    ],
}


def is_text_candidate(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            return None
    except OSError:
        return None


def scan_file(path: Path) -> dict[str, list[dict[str, object]]]:
    text = read_text(path)
    if text is None:
        return {}

    findings: dict[str, list[dict[str, object]]] = defaultdict(list)
    lines = text.splitlines()
    for category, patterns in PATTERNS.items():
        for pattern in patterns:
            regex = re.compile(pattern, re.IGNORECASE)
            for line_number, line in enumerate(lines, 1):
                if regex.search(line):
                    findings[category].append(
                        {
                            "line": line_number,
                            "pattern": pattern,
                            "snippet": line.strip()[:240],
                        }
                    )
    return dict(findings)


def scan_tree(source: Path) -> dict[str, object]:
    files: dict[str, object] = {}
    counts: dict[str, int] = defaultdict(int)
    scanned = 0

    for path in sorted(source.rglob("*")):
        if not path.is_file() or not is_text_candidate(path):
            continue
        if any(part in {".git", ".venv", "node_modules", "__pycache__"} for part in path.parts):
            continue
        scanned += 1
        findings = scan_file(path)
        if findings:
            rel = str(path.relative_to(source))
            files[rel] = findings
            for category, matches in findings.items():
                counts[category] += len(matches)

    return {
        "source": str(source),
        "scanned_files": scanned,
        "category_counts": dict(sorted(counts.items())),
        "files": files,
    }


def write_markdown(report: dict[str, object], out_path: Path) -> None:
    lines = [
        "# Migration Inventory",
        "",
        f"Source: `{report['source']}`",
        f"Scanned files: {report['scanned_files']}",
        "",
        "## Category Counts",
        "",
    ]

    counts = report["category_counts"]
    if counts:
        for category, count in counts.items():
            lines.append(f"- `{category}`: {count}")
    else:
        lines.append("- No migration-specific patterns found.")

    lines.extend(["", "## Findings", ""])
    files = report["files"]
    if not files:
        lines.append("No findings.")
    else:
        for filename, categories in files.items():
            lines.extend([f"### `{filename}`", ""])
            for category, matches in categories.items():
                lines.append(f"#### `{category}`")
                for match in matches[:30]:
                    lines.append(
                        f"- line {match['line']}: `{match['snippet'].replace('`', '')}`"
                    )
                if len(matches) > 30:
                    lines.append(f"- ... {len(matches) - 30} more")
                lines.append("")

    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Source repository or folder to scan")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("migration-inventory"),
        help="Output directory for JSON and Markdown reports",
    )
    args = parser.parse_args()

    source = args.source.resolve()
    if not source.exists() or not source.is_dir():
        parser.error(f"source must be an existing directory: {source}")

    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    report = scan_tree(source)
    json_path = out_dir / "migration_inventory.json"
    md_path = out_dir / "migration_inventory.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(report, md_path)

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
