from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "automation-v2" / "run_prepare.py"
if str(ROOT / "automation-v2") not in sys.path:
    sys.path.insert(0, str(ROOT / "automation-v2"))
if str(ROOT / "automation") not in sys.path:
    sys.path.insert(0, str(ROOT / "automation"))

SPEC = importlib.util.spec_from_file_location("hardening_prepare_v2", V2)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load resumable preparation runner")
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)

_original_patch_store = prepare.step5_migration.patch_store


def patch_store_with_await(source: str) -> str:
    result = _original_patch_store(source)
    old = "return await exists(this.legacySnapshotPath) ? parseJsonFile(this.legacySnapshotPath) as LegacySnapshot : undefined"
    new = "return await exists(this.legacySnapshotPath) ? await parseJsonFile(this.legacySnapshotPath) as LegacySnapshot : undefined"
    if old in result:
        return result.replace(old, new, 1)
    if new not in result:
        raise RuntimeError("legacy snapshot loader is not recognized after migration patch")
    return result


prepare.step5_migration.patch_store = patch_store_with_await

if __name__ == "__main__":
    raise SystemExit(prepare.main())
