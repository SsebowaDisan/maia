from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.services.agent.eval_suite import run_agent_eval_suite


def main() -> int:
    report = run_agent_eval_suite()
    print(json.dumps(report, indent=2, ensure_ascii=True))
    gates = report.get("gates") if isinstance(report, dict) else {}
    if not isinstance(gates, dict):
        return 1
    return 0 if all(bool(value) for value in gates.values()) else 2


if __name__ == "__main__":
    sys.exit(main())
