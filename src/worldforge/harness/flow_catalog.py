"""Static metadata for packaged checkout-safe showcase flows."""

from __future__ import annotations

from worldforge.harness.models import HarnessFlow
from worldforge.models import JSONDict

FLOWS: tuple[HarnessFlow, ...] = (
    HarnessFlow(
        id="leworldmodel",
        title="LeWorldModel Score Planning",
        short_title="LeWorldModel",
        focus="score planning",
        provider="LeWorldModelProvider",
        capability="score",
        command="uv run worldforge-demo-leworldmodel",
        accent="#d8c46a",
        summary=(
            "Inject a deterministic LeWorldModel-shaped cost runtime, score three action "
            "candidates, execute the selected plan, and verify persisted world state."
        ),
    ),
    HarnessFlow(
        id="lerobot",
        title="LeRobot Policy + Score Planning",
        short_title="LeRobot",
        focus="policy plus score planning",
        provider="LeRobotPolicyProvider",
        capability="policy",
        command="uv run worldforge-demo-lerobot",
        accent="#8ec5a3",
        summary=(
            "Inject a deterministic LeRobot-shaped policy, translate raw action chunks, rank "
            "them with a score provider, execute, persist, and reload the resulting world."
        ),
    ),
    HarnessFlow(
        id="cosmos-policy",
        title="Cosmos-Policy ALOHA Replay",
        short_title="Cosmos",
        focus="saved ALOHA /act replay",
        provider="CosmosPolicyProvider",
        capability="policy",
        command="uv run python scripts/demo_showcases.py run embodied-policy-replay-comparison",
        accent="#74d7f7",
        summary=(
            "Replay a sanitized NVIDIA Cosmos-Policy ALOHA /act response through the real "
            "provider boundary, decode 50 x 14 json_numpy actions, translate them, and preserve "
            "an inspectable run artifact without requiring a live GPU."
        ),
    ),
    HarnessFlow(
        id="gr00t-replay",
        title="GR00T DROID Replay",
        short_title="GR00T",
        focus="saved GR00T PolicyClient replay",
        provider="GrootPolicyClientProvider",
        capability="policy",
        command="uv run python scripts/demo_showcases.py run embodied-policy-replay-comparison",
        accent="#b6f377",
        summary=(
            "Replay a sanitized NVIDIA GR00T N1.7 PolicyClient response through the real provider "
            "boundary, validate named action tensors, translate 40 steps, and preserve an "
            "inspectable artifact without requiring a live GPU."
        ),
    ),
    HarnessFlow(
        id="robotics-compare",
        title="Robotics Policy Replay Comparison",
        short_title="Compare",
        focus="cross-provider policy inspection",
        provider="LeRobot + Cosmos-Policy + GR00T",
        capability="policy",
        command="uv run python scripts/demo_showcases.py run embodied-policy-replay-comparison",
        accent="#ffcc66",
        summary=(
            "Run the checkout-safe LeRobot, Cosmos-Policy, and GR00T policy paths side by side, "
            "compare action shapes and translation counts, and preserve a sanitized comparison "
            "artifact without keeping GPU servers online."
        ),
    ),
    HarnessFlow(
        id="diagnostics",
        title="Provider Diagnostics + Benchmark",
        short_title="Diagnostics",
        focus="provider diagnostics and benchmark comparison",
        provider="WorldForge + ProviderBenchmarkHarness",
        capability="diagnostics",
        command="uv run worldforge benchmark --provider mock --operation predict --operation embed",
        accent="#91b7ff",
        summary=(
            "Inspect the provider catalog, surface registered and unavailable adapters, run the "
            "mock provider benchmark matrix, and compare latency, throughput, and emitted events."
        ),
    ),
    HarnessFlow(
        id="workbench",
        title="Adapter Author Workbench",
        short_title="Workbench",
        focus="adapter authoring evidence",
        provider="Provider workbench",
        capability="authoring",
        command="uv run worldforge provider workbench mock",
        accent="#f0a35e",
        summary=(
            "Run the checkout-safe provider workbench against the stable mock provider and the "
            "direct-construction jepa-wms candidate, then collect promotion evidence, safe "
            "artifact references, and validation commands."
        ),
    ),
)


def available_flows() -> tuple[HarnessFlow, ...]:
    """Return packaged checkout-safe showcase flows."""

    return FLOWS


def flow_index() -> dict[str, HarnessFlow]:
    """Return available flows keyed by id."""

    return {flow.id: flow for flow in FLOWS}


def flow_to_dicts() -> tuple[JSONDict, ...]:
    """Return flow metadata for CLI JSON output."""

    return tuple(flow.to_dict() for flow in FLOWS)
