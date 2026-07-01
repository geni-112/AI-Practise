#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MONITOR = ROOT / "monitor"
DIST_ROOT = ROOT / "dist"


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build static SAT Mexico monitor site assets.")
    parser.add_argument("--out", default=str(DIST_ROOT / "realtime-monitor-site"))
    parser.add_argument("--zip", action="store_true")
    args = parser.parse_args()

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    for name in ("index.html", "app.js", "styles.css"):
        copy_file(MONITOR / name, out / name)
    if (MONITOR / "assets").exists():
        shutil.copytree(MONITOR / "assets", out / "assets")
    data_dir = out / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    status_src = MONITOR / "data" / "status.json"
    if not status_src.exists():
        status_src = MONITOR / "data" / "sample_status.json"
    copy_file(status_src, data_dir / "status.json")

    if args.zip:
        zip_path = out.with_suffix(".zip")
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in out.rglob("*"):
                if path.is_file():
                    zf.write(path, path.relative_to(out).as_posix())
        print(f"Static site package: {zip_path}")

    print(f"Static site directory: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
