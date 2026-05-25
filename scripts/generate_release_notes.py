"""Generate a maintainer-editable WorldForge release notes draft."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHANGELOG = ROOT / "CHANGELOG.md"
DEFAULT_RELEASE_EVIDENCE = ROOT / ".worldforge" / "release-evidence" / "release-evidence.json"
DEFAULT_OUTPUT = ROOT / ".worldforge" / "release-notes" / "release-notes-draft.md"

GITHUB_ISSUE_FIELDS = "number,title,url,labels,closedAt,state"
GITHUB_ISSUE_EXPORT_COMMAND = (
    "mkdir -p .worldforge/release-notes && "
    "gh issue list --state closed --limit 200 "
    "--json number,title,url,labels,closedAt,state "
    "> .worldforge/release-notes/closed-issues.json"
)

HOST_PATH_PATTERN = re.compile(r"(?<![A-Za-z0-9:])/(?:Users|private|Volumes)/[^\s)`|]+")
SIGNED_URL_PATTERN = re.compile(
    r"https?://[^\s)`|]*(?:X-Amz-Signature|sig=|signature=|token=|secret=)[^\s)`|]*",
    re.IGNORECASE,
)

SECTION_LABELS = {
    "added": "Added",
    "changed": "Changed",
    "fixed": "Fixed",
    "docs": "Docs",
}

PUBLIC_SURFACE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "CLI commands and scripts",
        ("worldforge ", "worldforge-", "scripts/", "CLI", "command"),
    ),
    (
        "Provider and runtime behavior",
        ("provider", "runtime", "src/worldforge/providers", ".env.example", "capability"),
    ),
    (
        "Artifacts, reports, and schemas",
        ("artifact", "evidence", "report", "schema", "manifest", "bundle"),
    ),
    (
        "Evaluation and benchmarks",
        ("evaluation", "benchmark", "budget", "score", "suite"),
    ),
    (
        "Docs and contributor surfaces",
        ("docs/", "documentation", "README", "CONTRIBUTING", "AGENTS", "MkDocs", "changelog"),
    ),
    (
        "Python API and public errors",
        ("src/worldforge", "Python API", "WorldForgeError", "WorldStateError", "ProviderError"),
    ),
)


class ReleaseNotesError(RuntimeError):
    """Raised when release notes cannot be drafted from the requested local inputs."""


@dataclass(frozen=True, slots=True)
class IssueRecord:
    number: int
    title: str
    url: str
    labels: tuple[str, ...]
    closed_at: str | None = None


@dataclass(frozen=True, slots=True)
class ReleaseEvidenceRecord:
    status: str
    path: Path
    payload: dict[str, Any] | None = None
    message: str = ""


@dataclass(frozen=True, slots=True)
class ReleaseNotesDraft:
    markdown: str
    status: str
    warnings: tuple[str, ...]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Markdown draft path. Defaults to .worldforge/release-notes/release-notes-draft.md.",
    )
    parser.add_argument(
        "--changelog",
        type=Path,
        default=DEFAULT_CHANGELOG,
        help="Changelog file to read. Defaults to CHANGELOG.md.",
    )
    parser.add_argument(
        "--release-evidence",
        type=Path,
        default=DEFAULT_RELEASE_EVIDENCE,
        help=(
            "Release evidence JSON to summarize. Defaults to "
            ".worldforge/release-evidence/release-evidence.json."
        ),
    )
    parser.add_argument(
        "--issues-json",
        type=Path,
        help=(
            "Optional closed-issues JSON exported from GitHub. Expected fields: "
            f"{GITHUB_ISSUE_FIELDS}."
        ),
    )
    parser.add_argument(
        "--github-issues",
        action="store_true",
        help="Fetch closed issue metadata with gh issue list instead of reading --issues-json.",
    )
    parser.add_argument(
        "--issue-limit",
        type=int,
        default=200,
        help="Maximum closed issues to request when --github-issues is set.",
    )
    parser.add_argument(
        "--known-caveat",
        action="append",
        default=[],
        help="Release-scoped caveat to include in the draft. Can be repeated.",
    )
    parser.add_argument(
        "--require-validation-evidence",
        action="store_true",
        help="Exit non-zero when release evidence JSON is missing or invalid.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = args.output.expanduser().resolve()
    try:
        draft = build_release_notes_draft(
            changelog_path=args.changelog,
            release_evidence_path=args.release_evidence,
            issues_json_path=args.issues_json,
            fetch_github_issues=args.github_issues,
            issue_limit=args.issue_limit,
            known_caveats=tuple(args.known_caveat),
            now_utc=_utc_now,
        )
    except ReleaseNotesError as exc:
        print(f"release notes error: {exc}", file=sys.stderr)
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(draft.markdown, encoding="utf-8")
    print(f"wrote {_display_path(output)}")
    for warning in draft.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if args.require_validation_evidence and draft.status != "ready-for-maintainer-review":
        return 1
    return 0


def build_release_notes_draft(
    *,
    changelog_path: Path = DEFAULT_CHANGELOG,
    release_evidence_path: Path = DEFAULT_RELEASE_EVIDENCE,
    issues_json_path: Path | None = None,
    fetch_github_issues: bool = False,
    issue_limit: int = 200,
    known_caveats: tuple[str, ...] = (),
    now_utc: Any | None = None,
    issue_runner: Any = subprocess.run,
) -> ReleaseNotesDraft:
    """Build a release notes draft from local changelog and optional evidence inputs."""

    changelog = _read_changelog(changelog_path)
    sections = _extract_unreleased_sections(changelog)
    release_evidence = _load_release_evidence(release_evidence_path)
    issues = _load_issues(
        issues_json_path=issues_json_path,
        fetch_github_issues=fetch_github_issues,
        issue_limit=issue_limit,
        runner=issue_runner,
    )
    status = _draft_status(release_evidence)
    warnings = tuple(_release_evidence_warnings(release_evidence))
    markdown = render_release_notes_draft(
        changelog_path=changelog_path,
        sections=sections,
        release_evidence=release_evidence,
        issues=issues,
        known_caveats=known_caveats,
        status=status,
        generated_at=_isoformat_utc((now_utc or _utc_now)()),
    )
    return ReleaseNotesDraft(markdown=markdown, status=status, warnings=warnings)


def render_release_notes_draft(
    *,
    changelog_path: Path,
    sections: dict[str, tuple[str, ...]],
    release_evidence: ReleaseEvidenceRecord,
    issues: tuple[IssueRecord, ...],
    known_caveats: tuple[str, ...],
    status: str,
    generated_at: str,
) -> str:
    """Render the maintainer-editable release notes draft."""

    all_changelog_items = tuple(
        item for key in ("added", "changed", "fixed", "docs") for item in sections.get(key, ())
    )
    docs_items = _docs_items(sections)
    public_surfaces = _public_surfaces(all_changelog_items)
    release_known_limitations = _release_known_limitations(release_evidence)
    caveats = tuple(dict.fromkeys((*known_caveats, *release_known_limitations)))
    lines = [
        "# WorldForge Release Notes Draft",
        "",
        f"- Generated at: `{generated_at}`",
        f"- Draft status: `{status}`",
        f"- Changelog source: `{_display_path(changelog_path)}`",
        f"- Release evidence source: `{_display_path(release_evidence.path)}`",
        "- GitHub issue data: "
        + ("`linked`" if issues else f"`not linked`; export with `{GITHUB_ISSUE_EXPORT_COMMAND}`"),
        "",
        "This is a draft for maintainer editing. It does not publish a GitHub release, create a "
        "tag, sign artifacts, or change trusted-publishing workflows.",
        "",
    ]

    for key in ("added", "changed", "fixed"):
        lines.extend(_render_changelog_section(SECTION_LABELS[key], sections.get(key, ())))

    lines.extend(_render_changelog_section("Docs", docs_items))
    lines.extend(_render_public_surfaces(public_surfaces))
    lines.extend(_render_closed_issues(issues))
    lines.extend(_render_validation(release_evidence))
    lines.extend(_render_compatibility_notes(release_evidence))
    lines.extend(_render_host_owned_evidence(release_evidence))
    lines.extend(_render_known_caveats(caveats))
    lines.extend(
        [
            "",
            "## Maintainer Review Checklist",
            "",
            "- Confirm every release-note claim is backed by changelog text, release evidence, "
            "or a linked issue.",
            "- Edit wording before publishing; keep generated bullets as source material, "
            "not final copy.",
            "- Remove implementation-only entries that are not user-visible.",
            "- Keep optional runtime claims scoped to linked `run_manifest.json` evidence.",
            "- Regenerate the draft after any changelog, validation, or release-evidence change.",
            "",
        ]
    )
    return "\n".join(lines)


def _read_changelog(changelog_path: Path) -> str:
    path = changelog_path.expanduser()
    if not path.exists():
        raise ReleaseNotesError(
            f"Missing changelog: `{_display_path(path)}`. First triage: restore CHANGELOG.md "
            "or pass --changelog <path>."
        )
    return path.read_text(encoding="utf-8")


def _extract_unreleased_sections(changelog: str) -> dict[str, tuple[str, ...]]:
    lines = changelog.splitlines()
    start = next(
        (index for index, line in enumerate(lines) if line.strip().lower() == "## unreleased"),
        None,
    )
    if start is None:
        raise ReleaseNotesError("CHANGELOG.md is missing a `## Unreleased` section.")

    sections: dict[str, list[str]] = {"added": [], "changed": [], "fixed": [], "docs": []}
    current: str | None = None
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if stripped.startswith("## "):
            break
        if stripped.startswith("### "):
            current = _normalize_changelog_heading(stripped.removeprefix("### ").strip())
            sections.setdefault(current, [])
            continue
        if current is None:
            continue
        if line.startswith("- "):
            sections[current].append(_sanitize_text(line.removeprefix("- ").strip()))
        elif sections[current] and stripped:
            sections[current][-1] = f"{sections[current][-1]} {_sanitize_text(stripped)}"
    return {key: tuple(value) for key, value in sections.items()}


def _normalize_changelog_heading(heading: str) -> str:
    normalized = heading.lower()
    if "add" in normalized:
        return "added"
    if "fix" in normalized or "security" in normalized:
        return "fixed"
    if "doc" in normalized:
        return "docs"
    return "changed"


def _load_release_evidence(path: Path) -> ReleaseEvidenceRecord:
    resolved = path.expanduser()
    if not resolved.exists():
        return ReleaseEvidenceRecord(
            status="missing",
            path=resolved,
            message=(
                f"Validation evidence missing: `{_display_path(resolved)}`. First triage: run "
                "`uv run python scripts/generate_release_evidence.py --run-gates`."
            ),
        )
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return ReleaseEvidenceRecord(
            status="invalid",
            path=resolved,
            message=(
                f"Validation evidence unreadable: `{_display_path(resolved)}` is invalid JSON "
                f"({exc.msg}). First triage: regenerate release evidence."
            ),
        )
    if not isinstance(payload, dict):
        return ReleaseEvidenceRecord(
            status="invalid",
            path=resolved,
            message=(
                f"Validation evidence unreadable: `{_display_path(resolved)}` is not a JSON "
                "object. First triage: regenerate release evidence."
            ),
        )
    return ReleaseEvidenceRecord(status="present", path=resolved, payload=payload)


def _load_issues(
    *,
    issues_json_path: Path | None,
    fetch_github_issues: bool,
    issue_limit: int,
    runner: Any,
) -> tuple[IssueRecord, ...]:
    if issues_json_path is not None:
        path = issues_json_path.expanduser()
        if not path.exists():
            raise ReleaseNotesError(
                f"Missing issues JSON: `{_display_path(path)}`. First triage: export closed "
                f"issues with `{GITHUB_ISSUE_EXPORT_COMMAND}`."
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        return _parse_issue_records(payload)
    if fetch_github_issues:
        return _fetch_github_issues(issue_limit=issue_limit, runner=runner)
    return ()


def _fetch_github_issues(*, issue_limit: int, runner: Any) -> tuple[IssueRecord, ...]:
    completed = runner(
        [
            "gh",
            "issue",
            "list",
            "--state",
            "closed",
            "--limit",
            str(issue_limit),
            "--json",
            GITHUB_ISSUE_FIELDS,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        stderr = _sanitize_text((completed.stderr or "").strip())
        raise ReleaseNotesError(
            "Unable to fetch closed GitHub issues. First triage: run "
            f"`{GITHUB_ISSUE_EXPORT_COMMAND}` and pass --issues-json. {stderr}"
        )
    return _parse_issue_records(json.loads(completed.stdout or "[]"))


def _parse_issue_records(payload: Any) -> tuple[IssueRecord, ...]:
    if not isinstance(payload, list):
        raise ReleaseNotesError("Issues JSON must be a list of GitHub issue objects.")
    records: list[IssueRecord] = []
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        number = raw.get("number")
        title = raw.get("title")
        if not isinstance(number, int) or not isinstance(title, str) or not title.strip():
            continue
        records.append(
            IssueRecord(
                number=number,
                title=_sanitize_text(title.strip()),
                url=_sanitize_text(str(raw.get("url") or "")),
                labels=_label_names(raw.get("labels")),
                closed_at=str(raw["closedAt"]) if raw.get("closedAt") else None,
            )
        )
    return tuple(sorted(records, key=lambda issue: issue.number))


def _label_names(raw_labels: Any) -> tuple[str, ...]:
    labels: list[str] = []
    if isinstance(raw_labels, list):
        for raw_label in raw_labels:
            if isinstance(raw_label, str):
                labels.append(raw_label)
            elif isinstance(raw_label, dict) and isinstance(raw_label.get("name"), str):
                labels.append(raw_label["name"])
    return tuple(sorted(set(labels)))


def _draft_status(release_evidence: ReleaseEvidenceRecord) -> str:
    if release_evidence.status != "present":
        return "needs-validation-evidence"
    summary = (
        release_evidence.payload.get("validation_summary", {}) if release_evidence.payload else {}
    )
    if isinstance(summary, dict) and int(summary.get("failed") or 0) > 0:
        return "needs-validation-review"
    return "ready-for-maintainer-review"


def _release_evidence_warnings(release_evidence: ReleaseEvidenceRecord) -> list[str]:
    if release_evidence.status == "present":
        return []
    return [release_evidence.message]


def _docs_items(sections: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    items: list[str] = list(sections.get("docs", ()))
    for section_items in sections.values():
        for item in section_items:
            if _is_docs_item(item) and item not in items:
                items.append(item)
    return tuple(items)


def _is_docs_item(item: str) -> bool:
    lower = item.lower()
    return any(
        token in lower
        for token in (
            "docs/",
            "documentation",
            "readme",
            "mkdocs",
            "changelog",
            "contributing",
            "agents.md",
            "playbooks",
            "operations",
        )
    )


def _public_surfaces(items: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    surfaces: dict[str, list[str]] = {label: [] for label, _patterns in PUBLIC_SURFACE_PATTERNS}
    for item in items:
        for label, patterns in PUBLIC_SURFACE_PATTERNS:
            if any(pattern.lower() in item.lower() for pattern in patterns):
                surfaces[label].append(item)
    return {label: tuple(dict.fromkeys(values)) for label, values in surfaces.items() if values}


def _render_changelog_section(title: str, items: tuple[str, ...]) -> list[str]:
    lines = ["", f"## {title}", ""]
    if items:
        lines.extend(f"- {_sanitize_text(item)}" for item in items)
    else:
        lines.append(f"- No {title.lower()} entries found under `## Unreleased`.")
    return lines


def _render_public_surfaces(surfaces: dict[str, tuple[str, ...]]) -> list[str]:
    lines = ["", "## Changed Public Surfaces", ""]
    if not surfaces:
        lines.append("- No public surfaces inferred from changelog entries.")
        return lines
    for label, items in surfaces.items():
        lines.append(f"### {label}")
        lines.append("")
        lines.extend(f"- {_sanitize_text(item)}" for item in items)
        lines.append("")
    return lines


def _render_closed_issues(issues: tuple[IssueRecord, ...]) -> list[str]:
    lines = ["", "## Closed Issues By Label", ""]
    if not issues:
        lines.append(
            f"- No closed issue data linked. Export with `{GITHUB_ISSUE_EXPORT_COMMAND}` "
            "or rerun with `--github-issues`."
        )
        return lines

    grouped: dict[str, list[IssueRecord]] = {}
    for issue in issues:
        labels = issue.labels or ("unlabeled",)
        for label in labels:
            grouped.setdefault(label, []).append(issue)
    for label in sorted(grouped):
        lines.append(f"### `{_sanitize_text(label)}`")
        lines.append("")
        for issue in grouped[label]:
            link = f" [{issue.url}]({issue.url})" if issue.url else ""
            closed = f" closed `{issue.closed_at}`" if issue.closed_at else ""
            lines.append(f"- #{issue.number} {_sanitize_text(issue.title)}{link}{closed}")
        lines.append("")
    return lines


def _render_validation(release_evidence: ReleaseEvidenceRecord) -> list[str]:
    lines = ["", "## Validation", ""]
    if release_evidence.status != "present":
        lines.append(f"- {release_evidence.message}")
        lines.append("- Draft status remains `needs-validation-evidence` until evidence is linked.")
        return lines

    payload = release_evidence.payload or {}
    summary = payload.get("validation_summary", {})
    if not isinstance(summary, dict):
        summary = {}
    lines.append(f"- Evidence JSON: `{_display_path(release_evidence.path)}`")
    lines.append(
        "- Summary: "
        + ", ".join(
            f"`{name}`={int(summary.get(name) or 0)}"
            for name in ("passed", "failed", "skipped", "host-owned")
        )
    )
    lines.extend(
        ["", "| Gate | Status | Command | First triage step |", "| --- | --- | --- | --- |"]
    )
    gates = payload.get("validation_gates", [])
    if isinstance(gates, list) and gates:
        for gate in gates:
            if not isinstance(gate, dict):
                continue
            lines.append(
                "| "
                + " | ".join(
                    (
                        _sanitize_text(str(gate.get("name") or "unknown")),
                        _sanitize_text(str(gate.get("status") or "unknown")),
                        f"`{_sanitize_text(str(gate.get('command') or ''))}`",
                        _sanitize_text(str(gate.get("triage_step") or "")),
                    )
                )
                + " |"
            )
    else:
        lines.append("| none | missing |  | regenerate release evidence |")

    references = _artifact_references(payload)
    lines.extend(["", "### Validation Evidence References", ""])
    if references:
        lines.extend(f"- {reference}" for reference in references)
    else:
        lines.append("- No benchmark, evidence bundle, or release artifact references linked.")
    return lines


def _artifact_references(payload: dict[str, Any]) -> tuple[str, ...]:
    references: list[str] = []
    for key in ("benchmark_artifacts", "release_artifacts"):
        raw_records = payload.get(key, [])
        if not isinstance(raw_records, list):
            continue
        for raw_record in raw_records:
            if not isinstance(raw_record, dict):
                continue
            path = _sanitize_text(str(raw_record.get("path") or "unknown"))
            digest = _sanitize_text(str(raw_record.get("sha256") or "sha256:not-recorded"))
            references.append(f"`{key}` `{path}` {digest}")
    return tuple(references)


def _render_compatibility_notes(release_evidence: ReleaseEvidenceRecord) -> list[str]:
    lines = ["", "## Compatibility Notes", ""]
    claim_boundary = ""
    if release_evidence.payload:
        claim_boundary = str(release_evidence.payload.get("claim_boundary") or "")
    lines.extend(
        [
            "- This draft is source material for maintainer editing; it is not a published "
            "release.",
            "- Checkout-safe gates do not prove live provider availability, model quality, "
            "physical fidelity, or robot safety without linked live-smoke manifests.",
            "- Stable or provisional API, artifact schema, CLI, provider capability, and "
            "persistence changes need migration notes before publishing.",
        ]
    )
    if claim_boundary:
        lines.append(f"- Release evidence claim boundary: {_sanitize_text(claim_boundary)}")
    return lines


def _render_host_owned_evidence(release_evidence: ReleaseEvidenceRecord) -> list[str]:
    lines = ["", "## Host-Owned Optional Runtime Evidence", ""]
    if not release_evidence.payload:
        lines.append(
            "- No release evidence JSON linked; no live provider behavior is claimed by this draft."
        )
        return lines

    provider_rows = []
    for key in ("live_provider_evidence", "extra_live_provider_evidence"):
        raw_rows = release_evidence.payload.get(key, [])
        if isinstance(raw_rows, list):
            provider_rows.extend(row for row in raw_rows if isinstance(row, dict))
    if not provider_rows:
        lines.append("- No optional runtime evidence rows found in release evidence.")
        return lines

    lines.extend(["| Provider | Status | Evidence |", "| --- | --- | --- |"])
    for row in provider_rows:
        provider = _sanitize_text(str(row.get("provider") or "unknown"))
        status = _sanitize_text(str(row.get("status") or "unknown"))
        manifests = row.get("manifests", [])
        reason = _sanitize_text(str(row.get("reason") or ""))
        evidence = (
            f"{len(manifests)} manifest(s)" if isinstance(manifests, list) and manifests else reason
        )
        if not evidence:
            evidence = "no evidence detail"
        lines.append(f"| `{provider}` | {status} | {evidence} |")
    return lines


def _render_known_caveats(caveats: tuple[str, ...]) -> list[str]:
    lines = ["", "## Known Caveats", ""]
    if caveats:
        lines.extend(f"- {_sanitize_text(caveat)}" for caveat in caveats)
    else:
        lines.append("- No additional caveats recorded. Maintainer must confirm before release.")
    return lines


def _release_known_limitations(release_evidence: ReleaseEvidenceRecord) -> tuple[str, ...]:
    if not release_evidence.payload:
        return ()
    raw_limitations = release_evidence.payload.get("known_limitations", [])
    if not isinstance(raw_limitations, list):
        return ()
    return tuple(_sanitize_text(str(item)) for item in raw_limitations if str(item).strip())


def _sanitize_text(value: str) -> str:
    return HOST_PATH_PATTERN.sub(
        "<host-local-path>", SIGNED_URL_PATTERN.sub("[redacted-url]", value)
    )


def _display_path(path: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return f"<host-local-path>/{resolved.name}"


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _isoformat_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
