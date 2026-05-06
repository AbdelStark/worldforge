from __future__ import annotations

import sys
from textwrap import dedent

import pytest

from worldforge.cli import main

HELP_SNAPSHOTS: dict[tuple[str, ...], str] = {
    ("examples", "--help"): """\
usage: worldforge examples [-h] [--format {markdown,json}]

options:
  -h, --help            show this help message and exit
  --format {markdown,json}
                        Output format for the examples index.
""",
    ("provider", "list", "--help"): (
        "usage: worldforge provider list [-h] [--state-dir STATE_DIR]\n"
        "                                [--registered-only]\n"
        "                                [--capability "
        "{predict,generate,reason,embed,plan,transfer,score,policy}]\n"
        "\n"
        "options:\n"
        "  -h, --help            show this help message and exit\n"
        "  --state-dir STATE_DIR\n"
        "                        World state directory.\n"
        "  --registered-only     Show only providers registered for this process.\n"
        "  --capability {predict,generate,reason,embed,plan,transfer,score,policy}\n"
        "                        Filter providers by capability name.\n"
    ),
    ("provider", "docs", "--help"): """\
usage: worldforge provider docs [-h] [--format {markdown,json}] [name]

positional arguments:
  name                  Optional provider name.

options:
  -h, --help            show this help message and exit
  --format {markdown,json}
                        Output format for provider docs metadata.
""",
    ("world", "create", "--help"): """\
usage: worldforge world create [-h] [--provider PROVIDER] [--prompt PROMPT]
                               [--description DESCRIPTION]
                               [--state-dir STATE_DIR]
                               [--format {json,markdown}]
                               name

positional arguments:
  name                  World name.

options:
  -h, --help            show this help message and exit
  --provider PROVIDER   Provider name.
  --prompt PROMPT       Optional prompt used to seed the world with
                        deterministic checkout-safe objects.
  --description DESCRIPTION
                        Optional world description.
  --state-dir STATE_DIR
                        World state directory.
  --format {json,markdown}
                        Output format for the saved world summary.
""",
    ("world", "history", "--help"): """\
usage: worldforge world history [-h] [--state-dir STATE_DIR]
                                [--format {json,markdown}]
                                world_id

positional arguments:
  world_id              World identifier.

options:
  -h, --help            show this help message and exit
  --state-dir STATE_DIR
                        World state directory.
  --format {json,markdown}
                        Output format for history entries.
""",
    ("world", "preflight", "--help"): """\
usage: worldforge world preflight [-h] [--state-dir STATE_DIR]
                                  [--workspace-dir WORKSPACE_DIR]
                                  [--world-id WORLD_IDS]
                                  [--retention-keep RETENTION_KEEP]
                                  [--format {json,markdown}]

options:
  -h, --help            show this help message and exit
  --state-dir STATE_DIR
                        World state directory.
  --workspace-dir WORKSPACE_DIR
                        WorldForge workspace directory containing runs/.
  --world-id WORLD_IDS  World identifier to validate without loading. Can be
                        repeated.
  --retention-keep RETENTION_KEEP
                        Number of newest valid run workspaces to keep before
                        warning.
  --format {json,markdown}
                        Output format for the preflight report.
""",
    ("harness", "--help"): """\
usage: worldforge harness [-h]
                          [--flow {leworldmodel,lerobot,diagnostics,workbench,eval,benchmark,runs}]
                          [--state-dir STATE_DIR] [--list] [--connectors]
                          [--runs] [--workspace-dir WORKSPACE_DIR]
                          [--provider PROVIDER] [--capability CAPABILITY]
                          [--status STATUS] [--created-from CREATED_FROM]
                          [--created-to CREATED_TO]
                          [--artifact-type ARTIFACT_TYPE]
                          [--format {markdown,json}] [--no-animation]

options:
  -h, --help            show this help message and exit
  --flow {leworldmodel,lerobot,diagnostics,workbench,eval,benchmark,runs}
                        Harness flow to open.
  --state-dir STATE_DIR
                        Directory for persisted demo worlds. Defaults to a
                        temporary directory.
  --list                List available harness flows without launching the
                        TUI.
  --connectors          List provider connector readiness without launching
                        the TUI.
  --runs                List preserved run history without launching the TUI.
  --workspace-dir WORKSPACE_DIR
                        Workspace root for --runs. Defaults to .worldforge.
  --provider PROVIDER   Filter --runs output by provider substring.
  --capability CAPABILITY
                        Filter --runs output by capability.
  --status STATUS       Filter --runs output by run status.
  --created-from CREATED_FROM
                        Filter --runs output from YYYY-MM-DD.
  --created-to CREATED_TO
                        Filter --runs output through YYYY-MM-DD.
  --artifact-type ARTIFACT_TYPE
                        Filter --runs output by safe artifact type.
  --format {markdown,json}
                        Output format for --list, --connectors, and --runs.
  --no-animation        Disable step reveal delays.
""",
    ("predict", "--help"): """\
usage: worldforge predict [-h] [--provider PROVIDER] --x X --y Y --z Z
                          [--steps STEPS] [--state-dir STATE_DIR]
                          world_name

positional arguments:
  world_name            World name to create or load.

options:
  -h, --help            show this help message and exit
  --provider PROVIDER   Provider name.
  --x X                 Target x coordinate.
  --y Y                 Target y coordinate.
  --z Z                 Target z coordinate.
  --steps STEPS         Prediction horizon in steps.
  --state-dir STATE_DIR
                        World state directory.
""",
    ("negotiate", "--help"): """\
usage: worldforge negotiate [-h] [--workflow WORKFLOW] [--list]
                            [--format {markdown,json}] [--state-dir STATE_DIR]

options:
  -h, --help            show this help message and exit
  --workflow WORKFLOW   Workflow name to negotiate. Repeat with --workflow
                        each time, or omit to cover every workflow.
  --list                List known workflows and exit.
  --format {markdown,json}
                        Output format.
  --state-dir STATE_DIR
                        World state directory.
""",
    ("eval", "--help"): """\
usage: worldforge eval [-h]
                       [--suite {generation,physics,planning,reasoning,transfer}]
                       [--provider PROVIDERS] [--format {markdown,json,csv}]
                       [--state-dir STATE_DIR] [--run-workspace RUN_WORKSPACE]

options:
  -h, --help            show this help message and exit
  --suite {generation,physics,planning,reasoning,transfer}
                        Built-in evaluation suite.
  --provider PROVIDERS  Provider name to evaluate. Can be repeated.
  --format {markdown,json,csv}
                        Evaluation report format.
  --state-dir STATE_DIR
                        World state directory.
  --run-workspace RUN_WORKSPACE
                        Preserve sanitized eval artifacts under
                        RUN_WORKSPACE/runs/<run-id>/.
""",
    ("benchmark", "--help"): """\
usage: worldforge benchmark [-h] [--provider PROVIDERS]
                            [--operation {predict,reason,generate,transfer,embed,score,policy}]
                            [--iterations ITERATIONS]
                            [--concurrency CONCURRENCY]
                            [--format {markdown,json,csv}]
                            [--input-file INPUT_FILE]
                            [--budget-file BUDGET_FILE]
                            [--state-dir STATE_DIR]
                            [--run-workspace RUN_WORKSPACE] [--preset PRESET]
                            [--list-presets] [--show-preset SHOW_PRESET]

options:
  -h, --help            show this help message and exit
  --provider PROVIDERS  Provider name to benchmark. Can be repeated.
  --operation {predict,reason,generate,transfer,embed,score,policy}
                        Operation to benchmark. Can be repeated.
  --iterations ITERATIONS
                        Iterations per operation.
  --concurrency CONCURRENCY
                        Concurrent workers.
  --format {markdown,json,csv}
                        Benchmark report format.
  --input-file INPUT_FILE
                        Optional JSON file with deterministic benchmark
                        inputs.
  --budget-file BUDGET_FILE
                        Optional JSON budget file. Failing gates exit non-zero
                        after printing the report.
  --state-dir STATE_DIR
                        World state directory.
  --run-workspace RUN_WORKSPACE
                        Preserve sanitized benchmark artifacts under
                        RUN_WORKSPACE/runs/<run-id>/.
  --preset PRESET       Run a named benchmark preset (overrides --provider,
                        --operation, --iterations, --concurrency, --input-
                        file, and --budget-file). Use --list-presets for the
                        catalogue.
  --list-presets        List benchmark presets and exit.
  --show-preset SHOW_PRESET
                        Print one benchmark preset's details and exit.
""",
}

WORLD_HELP_COMMANDS: tuple[tuple[str, str], ...] = (
    ("list", "List persisted worlds."),
    ("create", "Create and save a world."),
    ("show", "Show a persisted world."),
    ("history", "Show persisted world history."),
    ("objects", "List objects in a world."),
    ("add-object", "Add an object to a persisted world."),
    ("update-object", "Patch an object in a persisted world."),
    ("remove-object", "Remove an object from a persisted world."),
    ("delete", "Delete a persisted world."),
    ("predict", "Predict and save the next state for a persisted world."),
    ("export", "Export a persisted world as JSON."),
    ("import", "Import and save exported world JSON."),
    ("fork", "Fork a world from a history entry."),
    ("preflight", "Check local world JSON state and run workspaces without"),
)


def _help_output(argv: tuple[str, ...], monkeypatch, capsys) -> str:
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.setattr(sys, "argv", ["worldforge", *argv])

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 0
    return capsys.readouterr().out


def test_top_level_help_lists_command_surface(monkeypatch, capsys) -> None:
    output = _help_output(("--help",), monkeypatch, capsys)

    assert output.startswith("usage: worldforge [-h] command ...")
    assert "CLI for WorldForge provider diagnostics" in output
    for command in (
        "examples",
        "providers",
        "provider",
        "world",
        "doctor",
        "negotiate",
        "generate",
        "transfer",
        "predict",
        "eval",
        "benchmark",
        "harness",
        "runs",
        "drills",
    ):
        assert command in output
    for common_command in (
        "worldforge examples",
        "worldforge world create lab --provider mock",
        "worldforge world history <world-id>",
        "worldforge world preflight",
        "worldforge provider list",
        "worldforge provider docs",
        "worldforge provider info mock",
        "worldforge harness --list",
        "worldforge eval --suite planning --provider mock --format json",
        "worldforge runs list",
        "worldforge drills list",
    ):
        assert common_command in output


def test_world_help_lists_persistence_command_surface(monkeypatch, capsys) -> None:
    output = _help_output(("world", "--help"), monkeypatch, capsys)

    assert output.startswith("usage: worldforge world [-h] command ...")
    for command, help_text in WORLD_HELP_COMMANDS:
        assert command in output
        assert help_text in output


@pytest.mark.parametrize("argv", HELP_SNAPSHOTS)
def test_cli_help_snapshots(argv: tuple[str, ...], monkeypatch, capsys) -> None:
    assert _help_output(argv, monkeypatch, capsys) == dedent(HELP_SNAPSHOTS[argv])
