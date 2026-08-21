from __future__ import annotations

from final_common import prepare


_original_build_apply = prepare.step7_build.apply


def apply_without_app_restricted_workflow(root, log):
    changed = _original_build_apply(root, log)
    workflow = root / ".github" / "workflows" / "release-gates.yml"
    workflow.unlink(missing_ok=True)
    return [
        relative
        for relative in changed
        if relative.replace("\\", "/") != ".github/workflows/release-gates.yml"
    ]


prepare.step7_build.apply = apply_without_app_restricted_workflow
