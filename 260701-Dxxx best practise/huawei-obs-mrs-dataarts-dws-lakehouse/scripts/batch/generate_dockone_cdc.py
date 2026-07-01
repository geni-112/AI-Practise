#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

TS_OFFSET_MS = 30 * 24 * 60 * 60 * 1000


def parse_args():
    skill_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Generate DockOne Debezium-style raw CDC JSONL files."
    )
    parser.add_argument(
        "--seed-dir",
        default=str(skill_root / "assets" / "seed-data"),
        help="Directory containing seed manifest.json, raw-map.json, and raw files.",
    )
    parser.add_argument(
        "--out",
        default=str(Path.cwd() / "dockone-run" / "data"),
        help="Output data directory.",
    )
    parser.add_argument(
        "--target-mib",
        type=float,
        default=50.0,
        help="Approximate target raw JSONL size in MiB.",
    )
    return parser.parse_args()


def clone_event(event, cycle, sequence):
    item = json.loads(json.dumps(event))
    for side in ("before", "after"):
        value = item.get(side)
        if isinstance(value, dict) and value.get("id") is not None:
            value["id"] = f"{value['id']}-load{cycle:02d}"
            if "payload" in value:
                try:
                    payload = json.loads(value["payload"])
                    payload["load_cycle"] = cycle
                    payload["load_sequence"] = sequence
                    value["payload"] = json.dumps(
                        payload, separators=(",", ":"), sort_keys=True
                    )
                except (TypeError, json.JSONDecodeError):
                    pass
    item["ts_ms"] = int(item["ts_ms"]) + cycle * TS_OFFSET_MS
    source = item.get("source") or {}
    source["file"] = f"load-{cycle:02d}-{sequence:08d}.json"
    source["snapshot"] = "false"
    item["source"] = source
    return item


def encoded(event):
    return (
        json.dumps(event, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def load_seed(seed_dir: Path):
    raw_map = json.loads((seed_dir / "raw-map.json").read_text(encoding="utf-8-sig"))
    manifest = json.loads((seed_dir / "manifest.json").read_text(encoding="utf-8-sig"))
    sources = []
    total = 0
    event_total = 0
    for entry in raw_map:
        src = seed_dir / entry["local_file"]
        events = [
            json.loads(line)
            for line in src.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
        lines = [encoded(event) for event in events]
        sources.append((entry, events, lines))
        total += sum(map(len, lines))
        event_total += len(lines)
    return raw_map, manifest, sources, total, event_total


def main():
    args = parse_args()
    started = time.perf_counter()
    seed_dir = Path(args.seed_dir).resolve()
    out = Path(args.out).resolve()
    raw_out = out / "raw"
    raw_out.mkdir(parents=True, exist_ok=True)
    target_bytes = int(args.target_mib * 1024 * 1024)

    raw_map, manifest, sources, total, event_total = load_seed(seed_dir)
    generated = {entry["table_name"]: list(lines) for entry, _, lines in sources}

    cycle = 2
    sequence = 0
    while True:
        added = False
        for entry, events, _ in sources:
            for event in events[:1000]:
                sequence += 1
                line = encoded(clone_event(event, cycle, sequence))
                if abs(target_bytes - (total + len(line))) > abs(target_bytes - total):
                    added = False
                    break
                generated[entry["table_name"]].append(line)
                total += len(line)
                event_total += 1
                added = True
            if total >= target_bytes:
                break
        if total >= target_bytes or not added:
            break
        cycle += 1

    table_counts = {}
    table_bytes = {}
    for entry, _, _ in sources:
        name = entry["table_name"]
        target = raw_out / f"{name}.json"
        payload = b"".join(generated[name])
        target.write_bytes(payload)
        table_counts[name] = len(generated[name])
        table_bytes[name] = len(payload)

    for table in manifest["tables"]:
        table["event_count"] = table_counts[table["table_name"]]
    manifest["dataset_name"] = f"synthetic-dockone-exampleapp-cdc-{args.target_mib:g}m"
    manifest["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    manifest["target_bytes"] = target_bytes
    manifest["actual_bytes"] = total
    manifest["total_events"] = event_total
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "raw-map.json").write_text(
        json.dumps(raw_map, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    result = {
        "target_bytes": target_bytes,
        "actual_bytes": total,
        "difference_bytes": total - target_bytes,
        "size_mib": round(total / 1024 / 1024, 6),
        "events": event_total,
        "tables": len(sources),
        "data_dir": str(out),
        "generation_seconds": round(time.perf_counter() - started, 3),
    }
    (out.parent / "generation-summary.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
