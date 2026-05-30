"""Checkout-safe embodied policy replay comparison demo."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from worldforge.artifact_io import write_json_artifact as _write_json
from worldforge.demos import lerobot_e2e
from worldforge.models import JSONDict
from worldforge.providers.base import ProviderError

EMBODIED_POLICY_CLAIM_BOUNDARY = (
    "Checkout-safe replay comparison only; no robot controller, cross-provider action "
    "conversion, live GPU server, checkpoint download, or physical-safety claim."
)

EMBODIED_POLICY_NON_NORMALIZATION_BOUNDARY = (
    "Rows compare policy contracts side by side; they do not convert LeRobot tensors, "
    "GR00T named tensors, or Cosmos-Policy 14D ALOHA rows into a shared action space."
)

EMBODIED_POLICY_SUMMARY = (
    "Compared LeRobot, GR00T, and Cosmos-Policy policy replay contracts while preserving "
    "provider-specific raw action metadata and translator requirements."
)

EMBODIED_POLICY_FIRST_TRIAGE_STEP = (
    "Open `embodied-policy-replay-comparison.md` and check the provider-specific raw "
    "fields before selecting a prepared-host live smoke."
)

COMMON_POLICY_CONTRACT = (
    "provider",
    "capability",
    "action_horizon",
    "embodiment_tag",
    "raw_actions",
    "translated Action candidates",
    "provider metadata",
)


@dataclass(frozen=True, slots=True)
class EmbodiedPolicyReplaySummaries:
    lerobot: JSONDict
    gr00t: JSONDict
    cosmos_policy: JSONDict


@dataclass(frozen=True, slots=True)
class EmbodiedPolicyComparisonPaths:
    json: Path
    markdown: Path


class TranslatorMissingLeRobotPolicy:
    def to(self, _device: str) -> TranslatorMissingLeRobotPolicy:
        return self

    def eval(self) -> TranslatorMissingLeRobotPolicy:
        return self

    def requires_grad_(self, _enabled: bool) -> None:
        return None

    def select_action(self, _observation: object) -> list[list[float]]:
        return [[0.1, 0.5, 0.0]]


class TranslatorMissingGrootClient:
    def ping(self) -> bool:
        return True

    def get_action(self, _observation: object, options: object | None = None) -> object:
        if options is not None:
            _ = options
        return {"eef_9d": [[[0.1, 0.5, 0.0]]]}, {"runtime": "missing-translator-check"}


def run_embodied_policy_replay_comparison_workflow(workflow_dir: Path) -> JSONDict:
    summaries = embodied_policy_replay_summaries(workflow_dir)
    provider_rows = embodied_policy_provider_rows(summaries)
    comparison = embodied_policy_comparison_report(provider_rows)
    paths = write_embodied_policy_comparison(workflow_dir, comparison)
    return embodied_policy_comparison_result(comparison, paths)


def policy_missing_translator_checks() -> list[JSONDict]:
    return [
        policy_missing_translator_check(provider_name, provider, policy_info)
        for provider_name, provider, policy_info in policy_missing_translator_cases()
    ]


def policy_missing_translator_cases() -> list[tuple[str, Any, JSONDict]]:
    import httpx

    from worldforge.providers import (
        CosmosPolicyProvider,
        GrootPolicyClientProvider,
        LeRobotPolicyProvider,
    )

    return [
        (
            "lerobot",
            LeRobotPolicyProvider(
                policy=TranslatorMissingLeRobotPolicy(),
                policy_path="demo/lerobot-missing-translator",
            ),
            missing_translator_lerobot_info(),
        ),
        (
            "gr00t",
            GrootPolicyClientProvider(
                policy_client=TranslatorMissingGrootClient(),
                embodiment_tag="GR1",
            ),
            missing_translator_groot_info(),
        ),
        (
            "cosmos-policy",
            missing_translator_cosmos_provider(CosmosPolicyProvider, httpx),
            missing_translator_cosmos_info(),
        ),
    ]


def missing_translator_lerobot_info() -> JSONDict:
    return {
        "observation": {"observation.state": [[0.0, 0.5, 0.0]]},
        "embodiment_tag": "aloha",
        "action_horizon": 1,
    }


def missing_translator_groot_info() -> JSONDict:
    return {
        "observation": {"state": {"eef_9d": [[[0.0 for _ in range(9)]]]}},
        "embodiment_tag": "GR1",
        "action_horizon": 1,
    }


def missing_translator_cosmos_provider(provider_class: Any, httpx_module: Any) -> Any:
    return provider_class(
        base_url="http://93.184.216.34",
        transport=httpx_module.MockTransport(
            lambda _request: httpx_module.Response(
                200,
                json={"actions": [[0.0 for _ in range(14)]]},
            )
        ),
    )


def missing_translator_cosmos_info() -> JSONDict:
    return {
        "observation": {
            "primary_image": [[[[0, 0, 0]]]],
            "left_wrist_image": [[[[0, 0, 0]]]],
            "right_wrist_image": [[[[0, 0, 0]]]],
            "proprio": [0.0 for _ in range(14)],
        },
        "task_description": "translator check",
        "embodiment_tag": "aloha",
        "action_horizon": 1,
    }


def policy_missing_translator_check(
    provider_name: str,
    provider: Any,
    policy_info: JSONDict,
) -> JSONDict:
    try:
        provider.select_actions(info=policy_info)
    except ProviderError as exc:
        return policy_missing_translator_result(
            provider_name=provider_name,
            provider=provider,
            status="blocked",
            message=str(exc),
        )
    return policy_missing_translator_result(
        provider_name=provider_name,
        provider=provider,
        status="unexpected-pass",
        message="provider returned executable actions without translator",
    )


def policy_missing_translator_result(
    *,
    provider_name: str,
    provider: Any,
    status: str,
    message: str,
) -> JSONDict:
    return {
        "provider": provider_name,
        "capability": "policy",
        "status": status,
        "requires": "host action_translator",
        "message": message,
        "advertised_capabilities": provider.profile().capabilities.enabled_names(),
    }


def embodied_policy_replay_summaries(workflow_dir: Path) -> EmbodiedPolicyReplaySummaries:
    from worldforge.harness.flows import _run_cosmos_policy_demo, _run_gr00t_replay_demo

    return EmbodiedPolicyReplaySummaries(
        lerobot=lerobot_e2e.run_demo(state_dir=workflow_dir / "lerobot", emit=False),
        gr00t=_run_gr00t_replay_demo(state_dir=workflow_dir / "gr00t", emit=False),
        cosmos_policy=_run_cosmos_policy_demo(
            state_dir=workflow_dir / "cosmos-policy",
            emit=False,
        ),
    )


def embodied_policy_provider_rows(summaries: EmbodiedPolicyReplaySummaries) -> list[JSONDict]:
    return [
        lerobot_policy_replay_row(summaries.lerobot),
        groot_policy_replay_row(summaries.gr00t),
        cosmos_policy_replay_row(summaries.cosmos_policy),
    ]


def lerobot_policy_replay_row(summary: JSONDict) -> JSONDict:
    policy = summary["plan"]["metadata"]["policy_result"]
    metadata = policy["metadata"]
    return {
        "provider": "lerobot",
        "runtime_contract": "injected deterministic LeRobot policy through LeRobotPolicyProvider",
        "readiness": "checkout-safe fixture",
        "capability": "policy",
        "action_horizon": policy["action_horizon"],
        "embodiment_tag": policy["embodiment_tag"],
        "candidate_count": metadata["candidate_count"],
        "translated_action_count": len(policy["actions"]),
        "raw_action_keys": sorted(policy["raw_actions"].keys()),
        "raw_action_shape": metadata["raw_action_summary"]["shape"],
        "provider_specific_fields": {
            "policy_path": metadata["policy_path"],
            "policy_type": metadata["policy_type"],
            "mode": metadata["mode"],
            "device": metadata["device"],
        },
        "live_follow_up": "uv run python scripts/smoke_lerobot_policy.py --help",
    }


def groot_policy_replay_row(summary: JSONDict) -> JSONDict:
    artifact = summary["harness_artifacts"]["gr00t_replay"]["payload"]
    return {
        "provider": "gr00t",
        "runtime_contract": summary["runtime_contract"],
        "readiness": "checkout-safe fixture",
        "capability": "policy",
        "action_horizon": summary["action_horizon"],
        "embodiment_tag": summary["embodiment_tag"],
        "candidate_count": summary["candidate_count"],
        "translated_action_count": summary["translated_action_count"],
        "raw_action_keys": sorted(artifact["policy_output"]["raw_actions"].keys()),
        "raw_tensor_shapes": summary["raw_action_shapes"],
        "provider_specific_fields": artifact["policy_output"]["provider_info"],
        "live_follow_up": "uv run python scripts/smoke_gr00t_policy.py --help",
    }


def cosmos_policy_replay_row(summary: JSONDict) -> JSONDict:
    artifact = summary["harness_artifacts"]["cosmos_policy_replay"]["payload"]
    return {
        "provider": "cosmos-policy",
        "runtime_contract": summary["runtime_contract"],
        "readiness": "checkout-safe fixture",
        "capability": "policy",
        "action_horizon": summary["action_horizon"],
        "embodiment_tag": "aloha",
        "candidate_count": summary["candidate_count"],
        "translated_action_count": summary["translated_action_count"],
        "raw_action_keys": sorted(artifact["policy_output"].keys()),
        "raw_action_shape": summary["raw_action_shape"],
        "provider_specific_fields": {
            "server_path": summary["server_path"],
            "value_prediction": summary["value_prediction"],
            "json_numpy_rows": artifact["response"]["json_numpy_rows"],
        },
        "live_follow_up": "uv run worldforge-smoke-cosmos-policy --help",
    }


def embodied_policy_comparison_report(provider_rows: list[JSONDict]) -> JSONDict:
    return {
        "schema_version": 1,
        "safe_to_attach": True,
        "providers": provider_rows,
        "missing_translator_checks": policy_missing_translator_checks(),
        "common_policy_contract": list(COMMON_POLICY_CONTRACT),
        "non_normalization_boundary": EMBODIED_POLICY_NON_NORMALIZATION_BOUNDARY,
        "prepared_host_follow_ups": {
            row["provider"]: row["live_follow_up"] for row in provider_rows
        },
        "claim_boundary": EMBODIED_POLICY_CLAIM_BOUNDARY,
    }


def write_embodied_policy_comparison(
    workflow_dir: Path,
    comparison: JSONDict,
) -> EmbodiedPolicyComparisonPaths:
    paths = EmbodiedPolicyComparisonPaths(
        json=workflow_dir / "embodied-policy-replay-comparison.json",
        markdown=workflow_dir / "embodied-policy-replay-comparison.md",
    )
    _write_json(paths.json, comparison)
    paths.markdown.write_text(
        render_embodied_policy_comparison_markdown(comparison),
        encoding="utf-8",
    )
    return paths


def render_embodied_policy_comparison_markdown(comparison: JSONDict) -> str:
    lines = [
        "# Embodied Policy Replay Comparison",
        "",
        comparison["claim_boundary"],
        "",
        "| provider | horizon | translated | provider-specific raw fields | live follow-up |",
        "| --- | ---: | ---: | --- | --- |",
    ]
    lines.extend(
        "| {provider} | {horizon} | {translated} | {raw_fields} | `{follow_up}` |".format(
            provider=row["provider"],
            horizon=row["action_horizon"],
            translated=row["translated_action_count"],
            raw_fields=policy_replay_raw_fields(row),
            follow_up=row["live_follow_up"],
        )
        for row in comparison["providers"]
    )
    lines.extend(
        [
            "",
            "## Missing Translator Checks",
            "",
            "| provider | status | message |",
            "| --- | --- | --- |",
        ]
    )
    lines.extend(
        f"| {check['provider']} | {check['status']} | {check['message']} |"
        for check in comparison["missing_translator_checks"]
    )
    lines.extend(["", comparison["non_normalization_boundary"], ""])
    return "\n".join(lines)


def policy_replay_raw_fields(row: JSONDict) -> str:
    raw_fields = ", ".join(row["raw_action_keys"])
    if "raw_tensor_shapes" in row:
        return raw_fields + " / " + ", ".join(row["raw_tensor_shapes"])
    return raw_fields


def embodied_policy_comparison_result(
    comparison: JSONDict,
    paths: EmbodiedPolicyComparisonPaths,
) -> JSONDict:
    return {
        "status": "passed",
        "provider": "embodied-policy-replay-comparison",
        "safe_to_attach": True,
        "summary": EMBODIED_POLICY_SUMMARY,
        "report": comparison,
        "artifact_paths": {
            "comparison_json": str(paths.json),
            "comparison_markdown": str(paths.markdown),
        },
        "first_triage_step": EMBODIED_POLICY_FIRST_TRIAGE_STEP,
        "claim_boundary": comparison["claim_boundary"],
    }
