from __future__ import annotations

from pathlib import Path

from final_common import prepare


_original_git_changed = prepare.common.git_changed


def git_changed_with_directory_expansion(root: Path) -> list[str]:
    expanded: list[str] = []
    for relative in _original_git_changed(root):
        normalized = relative.replace("\\", "/")
        candidate = root / normalized.rstrip("/")
        if normalized.endswith("/") and candidate.is_dir():
            files = sorted(
                item.relative_to(root).as_posix()
                for item in candidate.rglob("*")
                if item.is_file() or item.is_symlink()
            )
            if not files:
                raise RuntimeError(f"untracked directory contains no stageable files: {normalized}")
            expanded.extend(files)
        else:
            expanded.append(normalized)
    return sorted(set(expanded))


prepare.common.git_changed = git_changed_with_directory_expansion
