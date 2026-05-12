from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE_STUDIES = ROOT / "docs/src/adoption-case-studies"
TEMPLATE = CASE_STUDIES / "_template.md"
ISSUE_TEMPLATE = ROOT / ".github/ISSUE_TEMPLATE/adoption_story.yml"

REQUIRED_TEMPLATE_SECTIONS = (
    "## Adopter",
    "## Context",
    "## WorldForge Surface Used",
    "## Custom Versus Out Of The Box",
    "## What Worked",
    "## What Was Awkward",
    "## Links",
    "## Safe-To-Publish Notes",
)


def _case_study_files() -> list[Path]:
    return sorted(
        path for path in CASE_STUDIES.glob("*.md") if path.name not in {"README.md", "_template.md"}
    )


def test_adoption_case_study_template_is_well_formed() -> None:
    template = TEMPLATE.read_text(encoding="utf-8")

    for section in REQUIRED_TEMPLATE_SECTIONS:
        assert section in template

    for safety_signal in (
        "Anonymized: yes/no",
        "Custom",
        "Out Of The Box",
        "secrets",
        "host-local paths",
    ):
        assert safety_signal in template


def test_committed_adoption_case_studies_follow_template_sections() -> None:
    for path in _case_study_files():
        text = path.read_text(encoding="utf-8")
        missing = [section for section in REQUIRED_TEMPLATE_SECTIONS if section not in text]
        assert not missing, f"{path.relative_to(ROOT)} missing sections: {missing}"


def test_adoption_story_issue_template_captures_case_study_fields() -> None:
    issue_template = ISSUE_TEMPLATE.read_text(encoding="utf-8")

    for field in (
        "Adopter name or project",
        "Context",
        "WorldForge surface used",
        "Custom versus out of the box",
        "What worked",
        "What was awkward",
        "Safe-to-publish confirmation",
    ):
        assert field in issue_template

    assert "https://abdelstark.github.io/worldforge/adoption-case-studies/" in issue_template
