"""Manual live smoke entry point for Cosmos deployments."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn

from worldforge import GenerationOptions
from worldforge.models import ProviderEvent, dump_json
from worldforge.providers import CosmosProvider
from worldforge.smoke.run_manifest import build_run_manifest, write_run_manifest

_ENV_VARS = ("COSMOS_BASE_URL", "NVIDIA_API_KEY")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a live Cosmos generate smoke against a host-owned endpoint."
    )
    parser.add_argument("--prompt", default="a robot arm moves a mug across a table")
    parser.add_argument("--duration-seconds", type=float, default=1.0)
    parser.add_argument("--size", default="1280x720")
    parser.add_argument("--fps", type=float, default=24.0)
    parser.add_argument("--seed", type=int, default=4)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".worldforge/runs/cosmos-live/artifacts/cosmos.mp4"),
        help="Path for the generated video bytes.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="Optional JSON summary path.",
    )
    parser.add_argument(
        "--run-manifest",
        type=Path,
        default=None,
        help="Optional sanitized run_manifest.json evidence path.",
    )
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    events: list[ProviderEvent] = []
    provider = CosmosProvider(event_handler=events.append)
    health = provider.health()
    if not health.healthy:
        raise RuntimeError(f"Cosmos health failed: {health.details}")

    clip = provider.generate(
        args.prompt,
        duration_seconds=args.duration_seconds,
        options=GenerationOptions(size=args.size, fps=args.fps, seed=args.seed),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(clip.blob())

    summary: dict[str, object] = {
        "provider": "cosmos",
        "capability": "generate",
        "status": "passed",
        "output": str(args.output),
        "byte_count": len(clip.blob()),
        "content_type": clip.content_type(),
        "duration_seconds": clip.duration_seconds,
        "fps": clip.fps,
        "resolution": list(clip.resolution),
        "mode": clip.metadata.get("mode"),
        "event_count": len(events),
    }
    if args.summary_json is not None:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def _write_manifest(
    args: argparse.Namespace,
    *,
    status: str,
    event_count: int,
    result: dict[str, object],
) -> None:
    if args.run_manifest is None:
        return
    write_run_manifest(
        args.run_manifest,
        build_run_manifest(
            run_id=args.run_manifest.parent.name,
            provider_profile="cosmos",
            capability="generate",
            status=status,
            env_vars=_ENV_VARS,
            event_count=event_count,
            input_summary={
                "prompt_length": len(args.prompt),
                "duration_seconds": args.duration_seconds,
                "size": args.size,
                "fps": args.fps,
                "seed_present": args.seed is not None,
            },
            result=result,
            artifact_paths={"video": args.output},
        ),
    )


def _fail(message: str) -> NoReturn:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        summary = run(args)
    except Exception as exc:
        result = {
            "provider": "cosmos",
            "capability": "generate",
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        _write_manifest(args, status="failed", event_count=0, result=result)
        _fail(str(exc))
    _write_manifest(
        args,
        status="passed",
        event_count=int(summary["event_count"]),
        result=summary,
    )
    print(dump_json(summary))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
