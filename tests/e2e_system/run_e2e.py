#!/usr/bin/env python3
"""Isolated OpenCode configuration smoke test for the installed package."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = (
    "orchestrator-analyst",
    "orchestrator-discovery",
    "orchestrator-stage-planner",
    "orchestrator-stage-reviewer",
    "orchestrator_next",
    "orchestrator_apply",
    "orchestrator_validate",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--opencode", default=shutil.which("opencode"))
    args = parser.parse_args()
    if not args.opencode:
        print("environment-blocked: opencode executable is unavailable", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="opencode-agents-e2e-") as temporary:
        base = Path(temporary)
        config = base / "config"
        workspace = base / "workspace"
        workspace.mkdir()
        subprocess.run(
            [sys.executable, str(ROOT / "opencode-agents.py"), "install", "--source", str(ROOT), "--target", str(config)],
            check=True,
            text=True,
        )
        environment = os.environ.copy()
        environment.update(
            {
                "HOME": str(base / "home"),
                "XDG_CONFIG_HOME": str(base / "xdg-config"),
                "XDG_DATA_HOME": str(base / "xdg-data"),
                "XDG_STATE_HOME": str(base / "xdg-state"),
                "XDG_CACHE_HOME": str(base / "xdg-cache"),
                "OPENCODE_CONFIG_DIR": str(config),
            }
        )
        result = subprocess.run(
            [args.opencode, "debug", "config"],
            cwd=workspace,
            env=environment,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            print(result.stdout, end="")
            print(result.stderr, file=sys.stderr, end="")
            return 1
        combined = result.stdout + "\n" + result.stderr
        missing = [name for name in EXPECTED if name not in combined]
        if missing:
            print(combined)
            print(f"missing installed OpenCode inventory: {missing}", file=sys.stderr)
            return 1
        print("OpenCode config smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
