from __future__ import annotations

from pathlib import Path
import re
import sys

from common import write_files


def apply(root: Path) -> list[str]:
    changed: dict[str, str] = {}

    analysis_path = root / "src/analysis.ts"
    analysis = analysis_path.read_text(encoding="utf-8")
    analysis, count = re.subn(
        r'\s*risks:\s*strings\(item\.risks,.*?false\),',
        '\n      risks: strings(item.risks, `${field}.risks`, false),',
        analysis,
        count=1,
    )
    if count != 1:
        raise RuntimeError("analysis risk line was not normalized exactly once")
    changed["src/analysis.ts"] = analysis

    store_path = root / "src/store.ts"
    store = store_path.read_text(encoding="utf-8")
    store = store.replace(
        'return await exists(this.legacySnapshotPath) ? parseJsonFile(this.legacySnapshotPath) as LegacySnapshot : undefined',
        'return await exists(this.legacySnapshotPath) ? await parseJsonFile(this.legacySnapshotPath) as LegacySnapshot : undefined',
    )
    changed["src/store.ts"] = store

    render_path = root / "src/render.ts"
    render = render_path.read_text(encoding="utf-8")
    render = render.replace('value.replace(/\\\\/g, "/")', 'value.replace(/\\\\/g, "/")')
    changed["src/render.ts"] = render

    return write_files(root, changed)


if __name__ == "__main__":
    repository = Path(sys.argv[1]).resolve()
    print("\n".join(apply(repository)))
