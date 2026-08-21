from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
V4 = ROOT / "automation-v4" / "run_prepare.py"
for candidate in [ROOT / "automation", ROOT / "automation-v2", ROOT / "automation-v3", ROOT / "automation-v4"]:
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

SPEC = importlib.util.spec_from_file_location("hardening_prepare_v4", V4)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load cross-platform preparation runner")
prepare_v4 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare_v4)
prepare = prepare_v4.prepare

COPY_TOOL_RUNTIME = r'''
import { cp, mkdir, rm } from "node:fs/promises"

await rm("dist-tools/runtime", { recursive: true, force: true })
await mkdir("dist-tools", { recursive: true })
await cp("runtime", "dist-tools/runtime", { recursive: true, force: true })
'''

_original_patch_build_templates = prepare.patch_build_templates


def patch_build_templates_with_native_layout() -> None:
    _original_patch_build_templates()
    scripts = prepare.step7_build.PACKAGE_JSON["scripts"]
    scripts["build"] = "npm run clean && tsc -p tsconfig.json && tsc -p tsconfig.tools.json && node scripts/copy-tool-runtime.mjs"


prepare.patch_build_templates = patch_build_templates_with_native_layout

_original_write_files = prepare.step7_build.write_files


def write_files_with_native_layout(root: Path, files: dict[str, str]) -> list[str]:
    expanded = dict(files)
    if "scripts/check-generated.mjs" in expanded:
        expanded["scripts/copy-tool-runtime.mjs"] = COPY_TOOL_RUNTIME
    return _original_write_files(root, expanded)


prepare.step7_build.write_files = write_files_with_native_layout

if __name__ == "__main__":
    raise SystemExit(prepare.main())
