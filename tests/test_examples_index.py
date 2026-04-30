from __future__ import annotations

from pathlib import Path

from worldforge.cli import EXAMPLE_COMMANDS

ROOT = Path(__file__).resolve().parents[1]
DOCS_EXAMPLES = ROOT / "docs" / "src" / "examples.md"
CHECKOUT_EXAMPLES = ROOT / "examples" / "README.md"


def test_example_index_metadata_is_task_grouped() -> None:
    assert all(example["task"] for example in EXAMPLE_COMMANDS)
    assert [example["task"] for example in EXAMPLE_COMMANDS] == [
        "Prediction and evaluation",
        "Provider comparison",
        "Score planning",
        "Policy plus score planning",
        "Visual harness",
        "Batch evaluation host",
        "Robotics operator host",
        "Optional runtime smoke",
        "Real robotics showcase",
    ]


def test_example_docs_cover_cli_index_commands() -> None:
    docs_index = DOCS_EXAMPLES.read_text(encoding="utf-8")
    checkout_index = CHECKOUT_EXAMPLES.read_text(encoding="utf-8")

    for example in EXAMPLE_COMMANDS:
        assert example["name"] in docs_index
        assert example["command"] in docs_index
        assert example["name"] in checkout_index
        assert example["command"] in checkout_index
