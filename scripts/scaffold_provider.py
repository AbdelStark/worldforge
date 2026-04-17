#!/usr/bin/env python3
"""Generate a WorldForge provider scaffold."""

from __future__ import annotations

import argparse
import json
import keyword
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

CAPABILITIES = ("predict", "generate", "transfer", "reason", "embed", "score", "policy")
DEFAULT_TAXONOMY = "unclassified provider scaffold"


@dataclass(frozen=True, slots=True)
class ProviderNames:
    raw: str
    display: str
    slug: str
    snake: str
    class_name: str


@dataclass(frozen=True, slots=True)
class ScaffoldOptions:
    root: Path
    names: ProviderNames
    taxonomy: str
    planned_capabilities: tuple[str, ...]
    is_local: bool
    env_var: str | None
    force: bool


def _split_words(name: str) -> list[str]:
    expanded = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", name.strip())
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", expanded)
    return re.findall(r"[A-Za-z][A-Za-z0-9]*|[0-9]+", expanded)


def normalize_provider_name(raw_name: str) -> ProviderNames:
    words = _split_words(raw_name)
    if not words:
        raise ValueError("provider name must contain at least one alphanumeric word")
    if not words[0][0].isalpha():
        raise ValueError("provider name must start with a letter")

    slug = "-".join(word.lower() for word in words)
    snake = "_".join(word.lower() for word in words)
    if keyword.iskeyword(snake):
        raise ValueError(f"provider module name '{snake}' is a Python keyword")

    class_name = "".join(word[:1].upper() + word[1:] for word in words) + "Provider"
    display = " ".join(word[:1].upper() + word[1:] for word in words)
    return ProviderNames(
        raw=raw_name,
        display=display,
        slug=slug,
        snake=snake,
        class_name=class_name,
    )


def _dedupe_capabilities(capabilities: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    deduped: list[str] = []
    for capability in capabilities:
        if capability not in seen:
            seen.add(capability)
            deduped.append(capability)
    return tuple(deduped)


def _capability_stubs(names: ProviderNames, planned_capabilities: tuple[str, ...]) -> str:
    stubs: list[str] = []
    if "predict" in planned_capabilities:
        stubs.append(
            """
    def predict(self, world_state: JSONDict, action: Action, steps: int) -> PredictionPayload:
        raise ProviderError(
            f"Provider '{self.name}' predict() scaffold is not implemented yet."
        )
"""
        )
    if "generate" in planned_capabilities:
        stubs.append(
            """
    def generate(
        self,
        prompt: str,
        duration_seconds: float,
        *,
        options: GenerationOptions | None = None,
    ) -> VideoClip:
        raise ProviderError(
            f"Provider '{self.name}' generate() scaffold is not implemented yet."
        )
"""
        )
    if "transfer" in planned_capabilities:
        stubs.append(
            """
    def transfer(
        self,
        clip: VideoClip,
        *,
        width: int,
        height: int,
        fps: float,
        prompt: str = "",
        options: GenerationOptions | None = None,
    ) -> VideoClip:
        raise ProviderError(
            f"Provider '{self.name}' transfer() scaffold is not implemented yet."
        )
"""
        )
    if "reason" in planned_capabilities:
        stubs.append(
            """
    def reason(self, query: str, *, world_state: JSONDict | None = None) -> ReasoningResult:
        raise ProviderError(
            f"Provider '{self.name}' reason() scaffold is not implemented yet."
        )
"""
        )
    if "embed" in planned_capabilities:
        stubs.append(
            """
    def embed(self, *, text: str) -> EmbeddingResult:
        raise ProviderError(
            f"Provider '{self.name}' embed() scaffold is not implemented yet."
        )
"""
        )
    if "score" in planned_capabilities:
        stubs.append(
            """
    def score_actions(self, *, info: JSONDict, action_candidates: object) -> ActionScoreResult:
        raise ProviderError(
            f"Provider '{self.name}' score_actions() scaffold is not implemented yet."
        )
"""
        )
    if "policy" in planned_capabilities:
        stubs.append(
            """
    def select_actions(self, *, info: JSONDict) -> ActionPolicyResult:
        raise ProviderError(
            f"Provider '{self.name}' select_actions() scaffold is not implemented yet."
        )
"""
        )

    if not stubs:
        raise ValueError(f"{names.slug} scaffold requires at least one planned capability")
    return "\n".join(stub.rstrip() for stub in stubs)


def _provider_source(options: ScaffoldOptions) -> str:
    names = options.names
    env_constant = f"{names.snake.upper()}_ENV_VAR"
    required_env_vars = f"[{env_constant}]" if options.env_var else "[]"
    planned = ", ".join(options.planned_capabilities)
    stubs = _capability_stubs(names, options.planned_capabilities)
    model_imports = ["ProviderCapabilities", "ProviderEvent", "ProviderHealth"]
    if "predict" in options.planned_capabilities:
        model_imports.extend(["Action", "JSONDict"])
    if "generate" in options.planned_capabilities or "transfer" in options.planned_capabilities:
        model_imports.extend(["GenerationOptions", "VideoClip"])
    if "reason" in options.planned_capabilities:
        model_imports.extend(["JSONDict", "ReasoningResult"])
    if "embed" in options.planned_capabilities:
        model_imports.append("EmbeddingResult")
    if "score" in options.planned_capabilities:
        model_imports.extend(["ActionScoreResult", "JSONDict"])
    if "policy" in options.planned_capabilities:
        model_imports.extend(["ActionPolicyResult", "JSONDict"])

    deduped_model_imports = sorted(dict.fromkeys(model_imports))
    base_imports = ["BaseProvider", "ProviderError"]
    if "predict" in options.planned_capabilities:
        base_imports.insert(1, "PredictionPayload")

    lines = [
        f'"""Provider scaffold for {names.display}.',
        "",
        "Generated by ``scripts/scaffold_provider.py``. Keep public capabilities disabled until",
        "the TODO methods return validated WorldForge models and have fixture-driven tests.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
    ]
    if options.env_var:
        lines.append("import os")
    lines.extend(
        [
            "from collections.abc import Callable",
            "from time import perf_counter",
            "",
            "from worldforge.models import (",
        ]
    )
    lines.extend(f"    {import_name}," for import_name in deduped_model_imports)
    lines.extend(
        [
            ")",
            "",
            f"from .base import {', '.join(base_imports)}",
            "",
        ]
    )
    if options.env_var:
        lines.extend([f'{env_constant} = "{options.env_var}"', "", ""])

    lines.extend(
        [
            f"class {names.class_name}(BaseProvider):",
            f'    """Generated scaffold for the {names.display} provider.',
            "",
            "    Planned capabilities are intentionally not advertised yet. Enable them",
            "    only after the corresponding methods call the real upstream runtime",
            "    and return validated public models.",
            '    """',
            "",
            f"    planned_capabilities = {options.planned_capabilities!r}",
            f"    taxonomy_category = {options.taxonomy!r}",
            "",
            "    def __init__(",
            "        self,",
            f'        name: str = "{names.slug}",',
            "        *,",
            "        event_handler: Callable[[ProviderEvent], None] | None = None,",
            "    ) -> None:",
            "        super().__init__(",
            "            name=name,",
            "            capabilities=ProviderCapabilities(predict=False),",
            f"            is_local={options.is_local!r},",
            f'            description="{names.display} provider scaffold.",',
            '            package="worldforge",',
            '            implementation_status="scaffold",',
            "            deterministic=False,",
            f"            requires_credentials={not options.is_local!r},",
            f"            required_env_vars={required_env_vars},",
            "            supported_modalities=[],",
            "            artifact_types=[],",
            "            notes=[",
            (
                '                "Generated scaffold; do not register as a real provider until '
                'implemented.",'
            ),
            f'                "Taxonomy category: {options.taxonomy}.",',
            f'                "Planned capabilities: {planned}.",',
            "            ],",
            "            event_handler=event_handler,",
            "        )",
            "",
            "    def configured(self) -> bool:",
        ]
    )
    if options.env_var:
        lines.append(f"        return bool(os.environ.get({env_constant}))")
    else:
        lines.append("        return True")

    lines.extend(
        [
            "",
            "    def health(self) -> ProviderHealth:",
            "        started = perf_counter()",
        ]
    )
    if options.env_var:
        lines.extend(
            [
                "        if not self.configured():",
                "            return ProviderHealth(",
                "                name=self.name,",
                "                healthy=False,",
                "                latency_ms=max(0.1, (perf_counter() - started) * 1000),",
                f'                details=f"missing {{{env_constant}}}",',
                "            )",
            ]
        )
    lines.extend(
        [
            "        return ProviderHealth(",
            "            name=self.name,",
            "            healthy=False,",
            "            latency_ms=max(0.1, (perf_counter() - started) * 1000),",
            '            details="scaffold generated; no runtime adapter implemented",',
            "        )",
            "",
            stubs,
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _test_source(options: ScaffoldOptions) -> str:
    names = options.names
    worldforge_imports: list[str] = []
    if "predict" in options.planned_capabilities:
        worldforge_imports.append("Action")
    if "transfer" in options.planned_capabilities:
        worldforge_imports.append("VideoClip")

    lines = [
        "from __future__ import annotations",
        "",
        "import pytest",
        "",
    ]
    if worldforge_imports:
        lines.append(f"from worldforge import {', '.join(worldforge_imports)}")
    lines.extend(
        [
            "from worldforge.providers.base import ProviderError",
            f"from worldforge.providers.{names.snake} import {names.class_name}",
            "",
            "",
            f"def test_{names.snake}_profile_starts_as_safe_scaffold() -> None:",
            f"    provider = {names.class_name}()",
            "    profile = provider.profile()",
            "",
            f'    assert profile.name == "{names.slug}"',
            '    assert profile.implementation_status == "scaffold"',
            "    assert profile.supported_tasks == []",
            f"    assert provider.planned_capabilities == {options.planned_capabilities!r}",
            f"    assert provider.taxonomy_category == {options.taxonomy!r}",
        ]
    )
    if options.env_var:
        lines.extend(
            [
                "",
                "",
                (
                    f"def test_{names.snake}_health_reports_missing_configuration"
                    "(monkeypatch) -> None:"
                ),
                f'    monkeypatch.delenv("{options.env_var}", raising=False)',
                "",
                f"    health = {names.class_name}().health()",
                "",
                "    assert health.healthy is False",
                f'    assert "{options.env_var}" in health.details',
            ]
        )
    if "predict" in options.planned_capabilities:
        lines.extend(
            [
                "",
                "",
                f"def test_{names.snake}_predict_is_not_implemented_yet() -> None:",
                f"    provider = {names.class_name}()",
                "",
                '    with pytest.raises(ProviderError, match="not implemented"):',
                "        provider.predict({}, Action.noop(), 1)",
            ]
        )
    if "generate" in options.planned_capabilities:
        lines.extend(
            [
                "",
                "",
                f"def test_{names.snake}_generate_is_not_implemented_yet() -> None:",
                f"    provider = {names.class_name}()",
                "",
                '    with pytest.raises(ProviderError, match="not implemented"):',
                '        provider.generate("prompt", 1.0)',
            ]
        )
    if "transfer" in options.planned_capabilities:
        lines.extend(
            [
                "",
                "",
                f"def test_{names.snake}_transfer_is_not_implemented_yet() -> None:",
                f"    provider = {names.class_name}()",
                "    clip = VideoClip(",
                '        frames=[b"frame"],',
                "        fps=1.0,",
                "        resolution=(1, 1),",
                "        duration_seconds=1.0,",
                "    )",
                "",
                '    with pytest.raises(ProviderError, match="not implemented"):',
                "        provider.transfer(clip, width=1, height=1, fps=1.0)",
            ]
        )
    if "reason" in options.planned_capabilities:
        lines.extend(
            [
                "",
                "",
                f"def test_{names.snake}_reason_is_not_implemented_yet() -> None:",
                f"    provider = {names.class_name}()",
                "",
                '    with pytest.raises(ProviderError, match="not implemented"):',
                '        provider.reason("query")',
            ]
        )
    if "embed" in options.planned_capabilities:
        lines.extend(
            [
                "",
                "",
                f"def test_{names.snake}_embed_is_not_implemented_yet() -> None:",
                f"    provider = {names.class_name}()",
                "",
                '    with pytest.raises(ProviderError, match="not implemented"):',
                '        provider.embed(text="query")',
            ]
        )
    if "score" in options.planned_capabilities:
        lines.extend(
            [
                "",
                "",
                f"def test_{names.snake}_score_actions_is_not_implemented_yet() -> None:",
                f"    provider = {names.class_name}()",
                "",
                '    with pytest.raises(ProviderError, match="not implemented"):',
                "        provider.score_actions(info={}, action_candidates=[])",
            ]
        )
    if "policy" in options.planned_capabilities:
        lines.extend(
            [
                "",
                "",
                f"def test_{names.snake}_select_actions_is_not_implemented_yet() -> None:",
                f"    provider = {names.class_name}()",
                "",
                '    with pytest.raises(ProviderError, match="not implemented"):',
                "        provider.select_actions(info={})",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _docs_source(options: ScaffoldOptions) -> str:
    names = options.names
    capability_rows = "\n".join(
        f"- [ ] `{capability}` implemented, advertised, and tested"
        for capability in options.planned_capabilities
    )
    env_section = (
        "- Required environment variable: none yet.\n"
        if options.env_var is None
        else f"- Required environment variable: `{options.env_var}`.\n"
    )
    return dedent(
        f"""\
        # {names.display} Provider

        Status: scaffold

        Taxonomy category: {options.taxonomy}

        This file was generated by `scripts/scaffold_provider.py`. Treat it as a checklist, not as
        proof that the provider is implemented.

        ## Planned Capabilities

        {capability_rows}

        ## Configuration

        {env_section}
        - Optional dependencies: document runtime packages, model checkpoints, and cache paths.
        - Registration rule: document the environment variables required before auto-registration.

        ## Contract To Define

        - Input shape, range, and semantic constraints.
        - Output schema and score direction, if applicable.
        - Provider-specific limits such as duration, resolution, action tensor shape, file size,
          content type, timeout, retry, and polling behavior.
        - Failure modes for malformed upstream payloads, partial task output, expired artifacts,
          unsupported content types, missing credentials, and unavailable local checkpoints.

        ## Tests To Add

        - Fixture-driven happy path.
        - Malformed upstream payload.
        - Provider-specific input limit.
        - Event emission for success and failure.
        - Contract test with `worldforge.testing.assert_provider_contract(...)` when the provider
          advertises public capabilities.

        ## Release Checklist

        - [ ] Provider capabilities are narrow and truthful.
        - [ ] Provider profile metadata is complete.
        - [ ] Public API docs mention new failure modes.
        - [ ] `docs/src/providers/README.md` links this provider page.
        - [ ] `AGENTS.md` documents any new commands, dependencies, or gotchas.
        - [ ] `CHANGELOG.md` records the user-visible behavior.
        """
    )


def _fixture_payload(options: ScaffoldOptions, *, success: bool) -> str:
    payload = {
        "provider": options.names.slug,
        "taxonomy_category": options.taxonomy,
        "planned_capabilities": list(options.planned_capabilities),
    }
    if success:
        payload["status"] = "replace-with-real-success-payload"
    else:
        payload["error"] = {
            "type": "replace-with-real-provider-error",
            "message": "Replace this scaffold fixture with a real malformed upstream response.",
        }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def scaffold_files(options: ScaffoldOptions) -> dict[Path, str]:
    names = options.names
    return {
        options.root / "src" / "worldforge" / "providers" / f"{names.snake}.py": _provider_source(
            options
        ),
        options.root / "tests" / f"test_{names.snake}_provider.py": _test_source(options),
        options.root / "tests" / "fixtures" / "providers" / f"{names.snake}_success.json": (
            _fixture_payload(options, success=True)
        ),
        options.root / "tests" / "fixtures" / "providers" / f"{names.snake}_error.json": (
            _fixture_payload(options, success=False)
        ),
        options.root / "docs" / "src" / "providers" / f"{names.slug}.md": _docs_source(options),
    }


def write_scaffold(options: ScaffoldOptions) -> list[Path]:
    files = scaffold_files(options)
    existing = [path for path in files if path.exists()]
    if existing and not options.force:
        joined = "\n".join(f"- {path}" for path in existing)
        raise FileExistsError(f"refusing to overwrite existing scaffold files:\n{joined}")

    written: list[Path] = []
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def parse_args(argv: list[str]) -> ScaffoldOptions:
    parser = argparse.ArgumentParser(
        description="Generate a safe WorldForge provider scaffold.",
    )
    parser.add_argument("name", help="Provider display name, e.g. 'Acme WM'.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root to write into. Defaults to the current directory.",
    )
    parser.add_argument(
        "--taxonomy",
        default=DEFAULT_TAXONOMY,
        help="Taxonomy category from docs/src/world-model-taxonomy.md.",
    )
    parser.add_argument(
        "--planned-capability",
        action="append",
        choices=CAPABILITIES,
        required=True,
        help="Capability stub to generate. Repeat for multiple planned capabilities.",
    )
    parser.add_argument(
        "--env-var",
        help="Optional environment variable required by the provider.",
    )
    locality = parser.add_mutually_exclusive_group()
    locality.add_argument("--local", action="store_true", help="Scaffold a local provider.")
    locality.add_argument("--remote", action="store_true", help="Scaffold a remote provider.")
    parser.add_argument("--force", action="store_true", help="Overwrite generated scaffold files.")

    args = parser.parse_args(argv)
    names = normalize_provider_name(args.name)
    planned_capabilities = _dedupe_capabilities(args.planned_capability or [])
    if not planned_capabilities:
        parser.error("at least one --planned-capability is required")
    env_var = args.env_var.strip() if args.env_var else None
    if env_var == "":
        parser.error("--env-var must not be empty")
    is_local = not args.remote
    if args.remote and env_var is None:
        env_var = f"{names.snake.upper()}_API_KEY"

    return ScaffoldOptions(
        root=args.root.expanduser().resolve(),
        names=names,
        taxonomy=args.taxonomy.strip() or DEFAULT_TAXONOMY,
        planned_capabilities=planned_capabilities,
        is_local=is_local,
        env_var=env_var,
        force=bool(args.force),
    )


def main(argv: list[str] | None = None) -> int:
    try:
        options = parse_args(sys.argv[1:] if argv is None else argv)
        written = write_scaffold(options)
    except (FileExistsError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"Generated provider scaffold for {options.names.display}:")
    for path in written:
        print(f"- {path.relative_to(options.root)}")
    print("\nNext steps:")
    print("- implement the TODO methods before advertising capabilities")
    print("- add the provider to src/worldforge/providers/__init__.py when it is ready")
    print("- register it in WorldForge._known_providers only after the adapter is tested")
    print("- link the docs stub from docs/src/providers/README.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
