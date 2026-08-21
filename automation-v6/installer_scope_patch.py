from __future__ import annotations

from final_common import prepare


_original_commit_and_push = prepare.common.commit_and_push


def commit_and_push_with_installer_baseline(root, message, allowed, **kwargs):
    if message == "fix(installer): support immutable remote installs and guarded retirement":
        allowed = [*allowed, "tests/test_installer_hardening.py"]
    return _original_commit_and_push(root, message, allowed, **kwargs)


prepare.common.commit_and_push = commit_and_push_with_installer_baseline
