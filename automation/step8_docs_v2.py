from __future__ import annotations

from pathlib import Path
import re
import sys

from common import expect_failure, run, write_files
from step8_docs import DOC_TEST, GATES_DOC, install_section, replace_section, roadmap


def apply(root: Path, log: Path, code_ref: str) -> list[str]:
    if not re.fullmatch(r"[0-9a-f]{40}", code_ref):
        raise RuntimeError(f"invalid immutable code ref: {code_ref}")

    test_path = "tests/test_docs_release.py"
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_docs_release.py", "-v"]
    changed = write_files(root, {test_path: DOC_TEST})
    expect_failure(command, cwd=root, log=log)

    readme_path = root / "README.md"
    readme = readme_path.read_text(encoding="utf-8").replace("5.1.1", "6.0.1")
    readme = re.sub(
        r"https://raw\.githubusercontent\.com/kostazol/opencode-agents/(?:main|v?6\.0\.1|[0-9a-f]{40})/opencode-agents\.py",
        f"https://raw.githubusercontent.com/kostazol/opencode-agents/{code_ref}/opencode-agents.py",
        readme,
    )
    readme = replace_section(
        readme,
        "<!-- 6.0.1-install:start -->",
        "<!-- 6.0.1-install:end -->",
        install_section(code_ref),
    )

    roadmap_path = root / "ROADMAP.md"
    existing_roadmap = roadmap_path.read_text(encoding="utf-8") if roadmap_path.exists() else "# Roadmap\n"
    changed += write_files(
        root,
        {
            "README.md": readme,
            "ROADMAP.md": roadmap(existing_roadmap, code_ref),
            "docs/RELEASE_GATES.md": GATES_DOC,
        },
    )
    run(command, cwd=root, log=log)
    return changed


if __name__ == "__main__":
    repository = Path(sys.argv[1]).resolve()
    log = Path(sys.argv[2]).resolve()
    code_ref = sys.argv[3]
    print("\n".join(apply(repository, log, code_ref)))
