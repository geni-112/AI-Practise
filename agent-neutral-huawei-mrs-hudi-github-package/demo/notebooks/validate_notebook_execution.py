from __future__ import annotations

import json
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / "notebooks" / "dli_hudi_demo.ipynb"


def main():
    notebook = json.loads(NB.read_text(encoding="utf-8"))
    total = 0
    passed = 0
    failures = []
    namespace = {"__name__": "__notebook_demo__"}
    for index, cell in enumerate(notebook["cells"], start=1):
        if cell["cell_type"] != "code":
            continue
        if cell.get("metadata", {}).get("run_on_validate") is False:
            continue
        total += 1
        code = "".join(cell["source"])
        try:
            exec(compile(code, f"{NB.name}:cell-{index}", "exec"), namespace)
            passed += 1
        except Exception:
            failures.append({"cell": index, "traceback": traceback.format_exc()})
    result = {
        "notebook": str(NB),
        "cells_total": total,
        "cells_passed": passed,
        "success_rate": round(passed / total, 4) if total else 1.0,
        "failures": failures,
    }
    print(json.dumps(result, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
