"""Checkout-safe external provider package demo artifacts."""

from __future__ import annotations

import sys
from contextlib import suppress
from dataclasses import dataclass
from importlib.metadata import EntryPoint
from pathlib import Path

from worldforge import ENTRY_POINT_GROUP, discover_entry_point_providers
from worldforge.artifact_io import write_json_artifact as _write_json
from worldforge.models import JSONDict
from worldforge.providers import BaseProvider
from worldforge.providers.catalog import PROVIDER_CATALOG
from worldforge.providers.entry_points import EntryPointDiscoveryReport

EXTERNAL_PROVIDER_PACKAGE_SUMMARY = (
    "Generated a temp external provider package and proved entry-point discovery, "
    "disabled discovery, duplicate-name skips, and missing optional dependency skips."
)

EXTERNAL_PROVIDER_PACKAGE_FIRST_TRIAGE_STEP = (
    "Inspect `external-provider-discovery.json`, then run the generated provider package "
    "tests in the temp package before publishing."
)

EXTERNAL_PROVIDER_PACKAGE_CLAIM_BOUNDARY = (
    "Checkout-safe package-shape demo only; no PyPI publishing, credentialed provider, "
    "or remote call."
)


@dataclass(frozen=True, slots=True)
class ExternalProviderPackage:
    root: Path
    source_root: Path
    package_dir: Path
    tests_dir: Path
    pyproject_path: Path
    provider_path: Path
    missing_path: Path
    generated_test: Path

    def generated_files(self) -> list[str]:
        return sorted(
            str(path.relative_to(self.root)) for path in self.root.rglob("*") if path.is_file()
        )


def run_external_provider_package_workflow(workflow_dir: Path) -> JSONDict:
    package = write_external_provider_package(workflow_dir / "external-provider-package")
    discovery, disabled, provider = discover_external_provider_package(package.source_root)
    report = external_provider_discovery_report(
        package=package,
        discovery=discovery,
        disabled=disabled,
        provider=provider,
    )
    report_path = workflow_dir / "external-provider-discovery.json"
    _write_json(report_path, report)

    return external_provider_result(
        package=package,
        report=report,
        report_path=report_path,
    )


def write_external_provider_package(package_root: Path) -> ExternalProviderPackage:
    package = external_provider_package_paths(package_root)
    package.package_dir.mkdir(parents=True, exist_ok=True)
    package.tests_dir.mkdir(parents=True, exist_ok=True)
    (package.package_dir / "__init__.py").write_text(
        '"""Checkout-safe WorldForge demo provider."""\n',
        encoding="utf-8",
    )
    package.pyproject_path.write_text(external_provider_pyproject(), encoding="utf-8")
    package.provider_path.write_text(external_provider_source(), encoding="utf-8")
    package.missing_path.write_text(external_provider_missing_optional_source(), encoding="utf-8")
    package.generated_test.write_text(external_provider_test_source(), encoding="utf-8")
    compile_external_provider_package(package)
    return package


def external_provider_package_paths(package_root: Path) -> ExternalProviderPackage:
    source_root = package_root / "src"
    package_dir = source_root / "worldforge_demo_provider"
    return ExternalProviderPackage(
        root=package_root,
        source_root=source_root,
        package_dir=package_dir,
        tests_dir=package_root / "tests",
        pyproject_path=package_root / "pyproject.toml",
        provider_path=package_dir / "provider.py",
        missing_path=package_dir / "needs_optional.py",
        generated_test=package_root / "tests" / "test_demo_external_provider.py",
    )


def external_provider_pyproject() -> str:
    return "\n".join(
        [
            "[project]",
            'name = "worldforge-demo-provider"',
            'version = "0.0.0"',
            'description = "Checkout-safe WorldForge external provider demo"',
            'requires-python = ">=3.13,<3.14"',
            'dependencies = ["worldforge"]',
            "",
            '[project.entry-points."worldforge.providers"]',
            'demo-external = "worldforge_demo_provider.provider:create_provider"',
            'needs-optional = "worldforge_demo_provider.needs_optional:create_provider"',
            'mock = "worldforge_demo_provider.provider:create_provider"',
            "",
        ]
    )


def external_provider_source() -> str:
    return "\n".join(
        [
            "from __future__ import annotations",
            "",
            "from worldforge import Action, ProviderCapabilities",
            "from worldforge.providers import BaseProvider, PredictionPayload, ProviderProfileSpec",
            "",
            "",
            "class DemoExternalProvider(BaseProvider):",
            "    def __init__(self, *, event_handler=None) -> None:",
            "        super().__init__(",
            '            name="demo-external",',
            "            capabilities=ProviderCapabilities(predict=True),",
            "            profile=ProviderProfileSpec(",
            '                description="Checkout-safe external provider package demo.",',
            '                implementation_status="demo",',
            "                is_local=True,",
            "                deterministic=True,",
            "            ),",
            "            event_handler=event_handler,",
            "        )",
            "",
            "    def predict(",
            "        self, world_state: dict, action: Action, steps: int",
            "    ) -> PredictionPayload:",
            "        next_state = dict(world_state)",
            '        next_state["provider"] = self.name',
            '        next_state["step"] = int(next_state.get("step", 0)) + steps',
            "        return PredictionPayload(",
            "            world_state=next_state,",
            "            confidence=0.91,",
            "            physics_score=0.89,",
            "            latency_ms=0.5,",
            "        )",
            "",
            "",
            "def create_provider(*, event_handler=None) -> DemoExternalProvider:",
            "    return DemoExternalProvider(event_handler=event_handler)",
            "",
        ]
    )


def external_provider_missing_optional_source() -> str:
    return "\n".join(
        [
            "import worldforge_demo_missing_runtime",
            "",
            "",
            "def create_provider(*, event_handler=None):",
            "    return worldforge_demo_missing_runtime.create_provider(",
            "        event_handler=event_handler",
            "    )",
            "",
        ]
    )


def external_provider_test_source() -> str:
    return "\n".join(
        [
            "from worldforge_demo_provider.provider import create_provider",
            "",
            "",
            "def test_provider_factory_name_matches_entry_point():",
            '    assert create_provider().name == "demo-external"',
            "",
        ]
    )


def compile_external_provider_package(package: ExternalProviderPackage) -> None:
    for path in (package.provider_path, package.missing_path, package.generated_test):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


def external_provider_entry_points() -> tuple[EntryPoint, ...]:
    return (
        EntryPoint(
            name="demo-external",
            value="worldforge_demo_provider.provider:create_provider",
            group=ENTRY_POINT_GROUP,
        ),
        EntryPoint(
            name="needs-optional",
            value="worldforge_demo_provider.needs_optional:create_provider",
            group=ENTRY_POINT_GROUP,
        ),
        EntryPoint(
            name="mock",
            value="worldforge_demo_provider.provider:create_provider",
            group=ENTRY_POINT_GROUP,
        ),
    )


def discover_external_provider_package(
    source_root: Path,
) -> tuple[EntryPointDiscoveryReport, EntryPointDiscoveryReport, BaseProvider]:
    entry_points = external_provider_entry_points()

    def entry_points_provider(group: str) -> tuple[EntryPoint, ...]:
        return entry_points if group == ENTRY_POINT_GROUP else ()

    sys.path.insert(0, str(source_root))
    try:
        discovery = discover_entry_point_providers(
            enabled=True,
            catalog=PROVIDER_CATALOG,
            entry_points_provider=entry_points_provider,
        )
        disabled = discover_entry_point_providers(
            enabled=False,
            catalog=PROVIDER_CATALOG,
            entry_points_provider=entry_points_provider,
        )
        provider = discovery.entries[0].create()
    finally:
        remove_external_provider_imports(source_root)
    return discovery, disabled, provider


def remove_external_provider_imports(source_root: Path) -> None:
    with suppress(ValueError):
        sys.path.remove(str(source_root))
    for module_name in tuple(sys.modules):
        if module_name.startswith("worldforge_demo_provider"):
            sys.modules.pop(module_name, None)


def external_provider_discovery_report(
    *,
    package: ExternalProviderPackage,
    discovery: EntryPointDiscoveryReport,
    disabled: EntryPointDiscoveryReport,
    provider: BaseProvider,
) -> JSONDict:
    return {
        "schema_version": 1,
        "entry_point_group": ENTRY_POINT_GROUP,
        "package_root": str(package.root),
        "generated_files": package.generated_files(),
        "discovery_enabled": discovery.to_dict(),
        "discovery_disabled": disabled.to_dict(),
        "provider": {
            "name": provider.name,
            "capabilities": provider.capabilities.to_dict(),
            "configured": provider.configured(),
            "description": provider.description,
        },
        "skip_reasons": {skip.name: skip.reason for skip in discovery.skipped},
        "safe_to_attach": True,
    }


def external_provider_result(
    *,
    package: ExternalProviderPackage,
    report: JSONDict,
    report_path: Path,
) -> JSONDict:
    return {
        "status": "passed",
        "provider": "demo-external",
        "safe_to_attach": True,
        "summary": EXTERNAL_PROVIDER_PACKAGE_SUMMARY,
        "report": report,
        "artifact_paths": {
            "discovery_report": str(report_path),
            "pyproject": str(package.pyproject_path),
            "provider": str(package.provider_path),
            "generated_test": str(package.generated_test),
        },
        "first_triage_step": EXTERNAL_PROVIDER_PACKAGE_FIRST_TRIAGE_STEP,
        "claim_boundary": EXTERNAL_PROVIDER_PACKAGE_CLAIM_BOUNDARY,
    }
