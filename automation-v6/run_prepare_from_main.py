from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from final_common import BASE_SHA, MESSAGES, assert_expected_head, clean, commit_stage, common, configure, history, prepare, write_json, write_output
import controller_patch  # noqa: F401


SUPPORTED_NODE_RANGE = "^22.22.2 || ^24.15.0"


def align_node_support(root: Path, log: Path) -> None:
    package_path = root / "package.json"
    lock_path = root / "package-lock.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    package.setdefault("engines", {})["node"] = SUPPORTED_NODE_RANGE
    lock.setdefault("packages", {}).setdefault("", {}).setdefault("engines", {})["node"] = SUPPORTED_NODE_RANGE
    package_path.write_text(json.dumps(package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    lock_path.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    common.npm_exec(root, ["ci"], log=log)
    common.npm_exec(root, ["run", "check:generated"], log=log)
    common.npm_exec(root, ["test"], log=log)
    common.npm_exec(root, ["run", "typecheck"], log=log)
    common.npm_exec(root, ["run", "check:generated"], log=log)
    clean(root)


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: run_prepare_from_main.py <target-checkout> <result-dir>")
    root = Path(sys.argv[1]).resolve()
    result_dir = Path(sys.argv[2]).resolve()
    logs = result_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)

    configure(root)
    current = history(root)
    if not current:
        assert_expected_head(root, BASE_SHA)
        baseline = logs / "00-red-baseline.log"
        common.expect_failure(["node", "--test", "tests-ts/release-blockers.test.mjs"], cwd=root, log=baseline)
        common.expect_failure(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_installer_hardening.py", "-v"],
            cwd=root,
            log=baseline,
        )

    if len(history(root)) < 1:
        log = logs / "01-controller.log"
        prepare.step2_controller.apply(root, log)
        commit_stage(root, MESSAGES[0], ["src", "runtime", "types", "tests-ts/controller-hardening.test.mjs"], log)

    if len(history(root)) < 2:
        log = logs / "02-routing.log"
        prepare.step3_routing.apply(root, log)
        commit_stage(root, MESSAGES[1], ["src/routing.ts", "src/state.ts", "runtime", "tests-ts/routing-state-hardening.test.mjs"], log)

    if len(history(root)) < 3:
        log = logs / "03-protocol.log"
        prepare.step4_protocol.apply(root, log)
        commit_stage(root, MESSAGES[2], ["src/analysis.ts", "runtime", "tests-ts/nfr-adversarial.test.mjs"], log)

    if len(history(root)) < 4:
        log = logs / "04-migration.log"
        prepare.patch_legacy_mode(root)
        prepare.step5_migration.apply(root, log)
        commit_stage(root, MESSAGES[3], ["src/render.ts", "src/store.ts", "src/routing.ts", "runtime", "tests-ts/legacy-resume-hardening.test.mjs"], log)

    if len(history(root)) < 5:
        log = logs / "05-installer.log"
        prepare.patch_installer_template()
        prepare.step6_installer.historical_manifests = prepare.enhanced_historical_manifests
        prepare.step6_installer.apply(root, log)
        commit_stage(root, MESSAGES[4], ["opencode-agents.py", "README.md", "tests/test_installer_regression.py"], log)

    if len(history(root)) < 6:
        log = logs / "06-build.log"
        prepare.patch_build_templates()
        prepare.step7_runtime.apply(root, log)
        prepare.step7_fixups.apply(root)
        prepare.patch_final_sources(root)
        prepare.step7_build.apply(root, log)
        prepare.ensure_gitignore(root)
        clean(root)

        common.npm_exec(root, ["ci"], log=log)
        common.npm_exec(root, ["run", "check:generated"], log=log)
        common.npm_exec(root, ["test"], log=log)
        common.npm_exec(root, ["run", "typecheck"], log=log)
        common.npm_exec(root, ["run", "check:generated"], log=log)
        clean(root)

        commit_stage(
            root,
            MESSAGES[5],
            [
                "src", "runtime", "tools", "tests-ts", "tests", "scripts", ".github/workflows",
                ".npmrc", ".gitignore", ".gitattributes", "package.json", "package-lock.json",
                "tsconfig.json", "tsconfig.tools.json", "types", "opencode-agents.py",
            ],
            log,
        )

    if len(history(root)) < 7:
        log = logs / "07-node-support.log"
        align_node_support(root, log)
        commit_stage(root, MESSAGES[6], ["package.json", "package-lock.json"], log)

    commits = history(root)
    if len(commits) < 7:
        raise RuntimeError(f"preparation stopped before the Node-supported implementation tree: {commits}")
    sha_build = commits[6]["sha"]
    result = {
        "schema_version": 1,
        "base_sha": BASE_SHA,
        "commits": commits[:7],
        "sha_build": sha_build,
        "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "supported_node": ["22.22.2+", "24.15.0+"],
    }
    write_json(result_dir / "prepare.json", result)
    write_output("sha_build", sha_build)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
