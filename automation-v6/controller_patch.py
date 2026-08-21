from __future__ import annotations

from pathlib import Path

from final_common import prepare

_original_compile_runtime = prepare.step2_controller.compile_runtime


def compile_runtime_without_duplicate_export(root: Path, *, log: Path) -> None:
    analysis = root / "src" / "analysis.ts"
    source = analysis.read_text(encoding="utf-8")
    source = source.replace('import path from "node:path"\n', "", 1)
    start_marker = "\nexport function canonicalRelative("
    end_marker = "\nexport function affectedStageClosure("
    start = source.find(start_marker)
    end = source.find(end_marker, start + 1)
    if start < 0 or end < 0:
        raise RuntimeError("cannot isolate the legacy canonicalRelative export in src/analysis.ts")
    source = source[:start] + "\n" + source[end:]
    analysis.write_text(source, encoding="utf-8", newline="\n")
    _original_compile_runtime(root, log=log)


prepare.step2_controller.compile_runtime = compile_runtime_without_duplicate_export
