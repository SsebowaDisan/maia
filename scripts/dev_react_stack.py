from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


def _terminate_process(name: str, process: subprocess.Popen[object]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        print(f"[maia] Force killing {name}...", flush=True)
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    root_dir = Path(__file__).resolve().parents[1]
    frontend_dir = root_dir / "frontend" / "user_interface"

    backend_cmd = [sys.executable, "run_api.py"]
    frontend_cmd = ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

    print("[maia] Starting backend on http://127.0.0.1:8000", flush=True)
    backend = subprocess.Popen(backend_cmd, cwd=root_dir)
    print("[maia] Starting React UI on http://127.0.0.1:5173", flush=True)
    frontend = subprocess.Popen(frontend_cmd, cwd=frontend_dir)

    processes: list[tuple[str, subprocess.Popen[object]]] = [
        ("backend", backend),
        ("frontend", frontend),
    ]

    exit_code = 0
    try:
        while True:
            for name, process in processes:
                code = process.poll()
                if code is None:
                    continue
                print(f"[maia] {name} exited with code {code}", flush=True)
                if code != 0:
                    exit_code = code
                return exit_code
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("[maia] Stopping React stack...", flush=True)
        return exit_code
    finally:
        _terminate_process("frontend", frontend)
        _terminate_process("backend", backend)


if __name__ == "__main__":
    raise SystemExit(main())
