from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "automation-v3" / "run_prepare.py"
for candidate in [ROOT / "automation", ROOT / "automation-v2", ROOT / "automation-v3"]:
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

SPEC = importlib.util.spec_from_file_location("hardening_prepare_v3", V3)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load migration-corrected preparation runner")
prepare_v3 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare_v3)
prepare = prepare_v3.prepare

_original_patch_build_templates = prepare.patch_build_templates


def patch_build_templates_cross_platform() -> None:
    _original_patch_build_templates()
    if '"newLine": "lf"' not in prepare.step7_build.TSCONFIG:
        prepare.step7_build.TSCONFIG = prepare.step7_build.TSCONFIG.replace(
            '    "target": "ES2022",',
            '    "target": "ES2022",\n    "newLine": "lf",',
            1,
        )


prepare.patch_build_templates = patch_build_templates_cross_platform

_original_ensure_gitignore = prepare.ensure_gitignore


def ensure_cross_platform_files(root: Path) -> None:
    _original_ensure_gitignore(root)
    attributes = '''* text=auto
*.ts text eol=lf
*.js text eol=lf
*.mjs text eol=lf
*.d.ts text eol=lf
*.json text eol=lf
*.md text eol=lf
*.py text eol=lf
*.yml text eol=lf
*.yaml text eol=lf
'''
    (root / ".gitattributes").write_text(attributes, encoding="utf-8", newline="\n")


prepare.ensure_gitignore = ensure_cross_platform_files

_original_commit_and_push = prepare.common.commit_and_push


def commit_and_push_with_attributes(root: Path, message: str, allowed_prefixes: list[str], **kwargs):
    if message == prepare.EXPECTED_MESSAGES[5] and ".gitattributes" not in allowed_prefixes:
        allowed_prefixes = [*allowed_prefixes, ".gitattributes"]
    return _original_commit_and_push(root, message, allowed_prefixes, **kwargs)


prepare.common.commit_and_push = commit_and_push_with_attributes

if __name__ == "__main__":
    raise SystemExit(prepare.main())
