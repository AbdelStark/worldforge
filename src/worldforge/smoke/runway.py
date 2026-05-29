"""Manual live smoke entry point for Runway deployments."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn

from worldforge import GenerationOptions, VideoClip
from worldforge.models import ProviderEvent, dump_json
from worldforge.providers import RunwayProvider
from worldforge.smoke.run_manifest import build_run_manifest, write_run_manifest

_ENV_VARS = ("RUNWAYML_API_SECRET", "RUNWAY_API_SECRET", "RUNWAYML_BASE_URL")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a live Runway generate or transfer smoke against the remote API."
    )
    parser.add_argument(
        "--capability",
        choices=("generate", "transfer"),
        default="generate",
        help="Runway capability to exercise.",
    )
    parser.add_argument("--prompt", default="a lab robot places a cube on a tray")
    parser.add_argument("--duration-seconds", type=float, default=5.0)
    parser.add_argument("--ratio", default="1280:720")
    parser.add_argument("--fps", type=float, default=24.0)
    parser.add_argument("--model", default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--input-video",
        type=Path,
        default=None,
        help="Input video for transfer smoke. Defaults to a tiny local fixture clip.",
    )
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".worldforge/runs/runway-live/artifacts/runway.mp4"),
        help="Path for downloaded Runway video bytes.",
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
    provider = RunwayProvider(event_handler=events.append)
    health = provider.health()
    if not health.healthy:
        raise RuntimeError(f"Runway health failed: {health.details}")

    options = GenerationOptions(ratio=args.ratio, fps=args.fps, model=args.model, seed=args.seed)
    if args.capability == "generate":
        clip = provider.generate(
            args.prompt,
            duration_seconds=args.duration_seconds,
            options=options,
        )
    else:
        transfer_clip = _transfer_clip(args)
        clip = provider.transfer(
            transfer_clip,
            width=args.width,
            height=args.height,
            fps=args.fps,
            prompt=args.prompt,
            options=GenerationOptions(model=args.model, seed=args.seed),
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(clip.blob())

    summary: dict[str, object] = {
        "provider": "runway",
        "capability": args.capability,
        "status": "passed",
        "output": str(args.output),
        "byte_count": len(clip.blob()),
        "content_type": clip.content_type(),
        "duration_seconds": clip.duration_seconds,
        "fps": clip.fps,
        "resolution": list(clip.resolution),
        "mode": clip.metadata.get("mode"),
        "model": clip.metadata.get("model"),
        "task_id_present": bool(clip.metadata.get("task_id")),
        "artifact_url": clip.metadata.get("artifact_url"),
        "event_count": len(events),
    }
    if args.summary_json is not None:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def _transfer_clip(args: argparse.Namespace) -> VideoClip:
    if args.input_video is None:
        return VideoClip(
            frames=[b"worldforge-runway-transfer-seed"],
            fps=args.fps,
            resolution=(args.width, args.height),
            duration_seconds=max(0.001, float(args.duration_seconds)),
            metadata={"content_type": "video/mp4", "mode": "runway-smoke-seed"},
        )
    return VideoClip(
        frames=[args.input_video.expanduser().read_bytes()],
        fps=args.fps,
        resolution=(args.width, args.height),
        duration_seconds=max(0.001, float(args.duration_seconds)),
        metadata={"content_type": "video/mp4", "mode": "runway-smoke-input"},
    )


def _write_manifest(
    args: argparse.Namespace,
    *,
    status: str,
    event_count: int,
    result: dict[str, object],
) -> None:
    if args.run_manifest is None:
        return
    artifact_paths: dict[str, Path | str] = {"video": args.output}
    artifact_url = result.get("artifact_url")
    if isinstance(artifact_url, str) and artifact_url.strip():
        artifact_paths["runway_artifact_url"] = artifact_url
    write_run_manifest(
        args.run_manifest,
        build_run_manifest(
            run_id=args.run_manifest.parent.name,
            provider_profile="runway",
            capability=args.capability,
            status=status,
            env_vars=_ENV_VARS,
            event_count=event_count,
            input_summary={
                "prompt_length": len(args.prompt),
                "duration_seconds": args.duration_seconds,
                "ratio": args.ratio,
                "fps": args.fps,
                "model": args.model or "provider default",
                "seed_present": args.seed is not None,
                "input_video_present": args.input_video is not None,
            },
            result=result,
            artifact_paths=artifact_paths,
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
            "provider": "runway",
            "capability": args.capability,
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
