"""Check checkout-safe portability contracts for shell wrappers and smoke scripts."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class WrapperContract:
    path: str
    invocation: str
    executable: bool
    shebang_prefix: str
    required_text: tuple[str, ...]
    docs: tuple[str, ...]
    triage_step: str


@dataclass(frozen=True, slots=True)
class WrapperCheckResult:
    path: str
    passed: bool
    failures: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "passed": self.passed, "failures": list(self.failures)}


WRAPPER_CONTRACTS = (
    WrapperContract(
        path="scripts/robotics-showcase",
        invocation="scripts/robotics-showcase",
        executable=True,
        shebang_prefix="#!/usr/bin/env bash",
        required_text=(
            "set -euo pipefail",
            "uv run --python 3.13",
            "worldforge-robotics-showcase",
            '--with "stable-worldmodel @ git+https://github.com/galilai-group/stable-worldmodel.git"',
            '--with "lerobot[transformers-dep]==0.5.1"',
        ),
        docs=("README.md", "docs/src/robotics-showcase.md", "docs/src/playbooks.md"),
        triage_step="Restore the bash wrapper, Python 3.13 uv runtime, and documented command.",
    ),
    WrapperContract(
        path="scripts/lewm-real",
        invocation="scripts/lewm-real",
        executable=True,
        shebang_prefix="#!/usr/bin/env bash",
        required_text=(
            "set -euo pipefail",
            "uv run --python 3.13",
            "stable-worldmodel @ git+https://github.com/galilai-group/stable-worldmodel.git",
            'lewm-real "$@"',
        ),
        docs=("docs/src/cli.md", "docs/src/playbooks.md", "docs/src/providers/leworldmodel.md"),
        triage_step="Keep the LeWorldModel wrapper executable and pinned to Python 3.13.",
    ),
    WrapperContract(
        path="scripts/lewm-lerobot-real",
        invocation="scripts/lewm-lerobot-real",
        executable=True,
        shebang_prefix="#!/usr/bin/env bash",
        required_text=(
            "set -euo pipefail",
            "uv run --python 3.13",
            "stable-worldmodel @ git+https://github.com/galilai-group/stable-worldmodel.git",
            "lerobot[transformers-dep]==0.5.1",
            'lewm-lerobot-real "$@"',
        ),
        docs=("AGENTS.md", "docs/src/robotics-showcase-deep-dive.md"),
        triage_step="Keep the policy-plus-score wrapper host-owned and Python 3.13-only.",
    ),
    WrapperContract(
        path="scripts/smoke_gr00t_policy.py",
        invocation="uv run python scripts/smoke_gr00t_policy.py",
        executable=False,
        shebang_prefix="#!/usr/bin/env python",
        required_text=("PolicyClient", "--gr00t-root", "--start-server"),
        docs=(
            "AGENTS.md",
            "docs/src/cli.md",
            "docs/src/playbooks.md",
            "docs/src/providers/gr00t.md",
        ),
        triage_step="Keep GR00T setup behind `uv run python` and host-owned runtime arguments.",
    ),
    WrapperContract(
        path="scripts/smoke_lerobot_policy.py",
        invocation="uv run python scripts/smoke_lerobot_policy.py",
        executable=True,
        shebang_prefix="#!/usr/bin/env python",
        required_text=("PreTrainedPolicy", "--policy-path", "--translator"),
        docs=(
            "AGENTS.md",
            "docs/src/cli.md",
            "docs/src/playbooks.md",
            "docs/src/providers/lerobot.md",
        ),
        triage_step="Keep LeRobot setup behind host-supplied observations and translators.",
    ),
    WrapperContract(
        path="scripts/test_package.sh",
        invocation="bash scripts/test_package.sh",
        executable=False,
        shebang_prefix="#!/usr/bin/env bash",
        required_text=("set -euo pipefail", "uv build --out-dir", "scripts/check_distribution.py"),
        docs=("README.md", "docs/src/contributing.md", "docs/src/quality.md"),
        triage_step="Keep the package contract shell-safe and documented in contributor gates.",
    ),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Output format for the portability report.",
    )
    args = parser.parse_args(argv)

    payload = check_wrapper_portability()
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(render_wrapper_portability_markdown(payload))
    return 0 if payload["passed"] else 1


def check_wrapper_portability(
    *, contracts: tuple[WrapperContract, ...] = WRAPPER_CONTRACTS
) -> dict[str, Any]:
    results = [_check_contract(contract) for contract in contracts]
    return {
        "schema_version": 1,
        "passed": all(result.passed for result in results),
        "claim_boundary": (
            "This checker validates checkout-safe wrapper contracts only. It does not install "
            "optional runtimes, start provider servers, download checkpoints, or claim Windows "
            "support."
        ),
        "results": [result.to_dict() for result in results],
    }


def render_wrapper_portability_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Wrapper Portability Report",
        "",
        f"Overall status: `{'passed' if payload['passed'] else 'failed'}`",
        "",
        payload["claim_boundary"],
        "",
        "| Script | Status | Failures |",
        "| --- | --- | --- |",
    ]
    for result in payload["results"]:
        failures = "; ".join(result["failures"]) if result["failures"] else "none"
        lines.append(
            f"| `{result['path']}` | `{'passed' if result['passed'] else 'failed'}` | {failures} |"
        )
    return "\n".join(lines) + "\n"


def _check_contract(contract: WrapperContract) -> WrapperCheckResult:
    path = ROOT / contract.path
    failures: list[str] = []
    if not path.is_file():
        return WrapperCheckResult(
            path=contract.path,
            passed=False,
            failures=(f"{contract.path} is missing; {contract.triage_step}",),
        )

    text = path.read_text(encoding="utf-8")
    first_line = text.splitlines()[0] if text.splitlines() else ""
    if not first_line.startswith(contract.shebang_prefix):
        failures.append(
            f"{contract.path} shebang is {first_line!r}; expected {contract.shebang_prefix!r}"
        )

    is_executable = os.access(path, os.X_OK)
    if contract.executable and not is_executable:
        failures.append(f"{contract.path} must be executable; run `chmod +x {contract.path}`")
    if not contract.executable and is_executable and path.suffix == ".sh":
        failures.append(f"{contract.path} should be invoked as `{contract.invocation}`")

    failures.extend(
        f"{contract.path} is missing required text: {required!r}"
        for required in contract.required_text
        if required not in text
    )

    for doc in contract.docs:
        doc_path = ROOT / doc
        if not doc_path.is_file():
            failures.append(f"{doc} is missing for documented wrapper command {contract.path}")
            continue
        doc_text = doc_path.read_text(encoding="utf-8")
        if contract.invocation not in doc_text:
            failures.append(f"{doc} does not document `{contract.invocation}`")

    return WrapperCheckResult(
        path=contract.path,
        passed=not failures,
        failures=tuple(failures),
    )


if __name__ == "__main__":
    raise SystemExit(main())
