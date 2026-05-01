from __future__ import annotations

import json
import sys

from worldforge.cli import main


def test_examples_cli_outputs_human_and_json_indexes(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["worldforge", "examples"])
    assert main() == 0
    output = capsys.readouterr().out
    assert output.startswith("# WorldForge Examples")
    assert "worldforge-demo-leworldmodel" in output
    assert "worldforge-demo-lerobot" in output

    monkeypatch.setattr(sys, "argv", ["worldforge", "examples", "--format", "json"])
    assert main() == 0
    examples_payload = json.loads(capsys.readouterr().out)
    example_names = {example["name"] for example in examples_payload}
    assert "leworldmodel-score-planning" in example_names
    assert "lerobot-policy-score-planning" in example_names


def test_doctor_and_provider_info_cli(tmp_path, monkeypatch, capsys) -> None:
    for env_var in (
        "COSMOS_BASE_URL",
        "NVIDIA_API_KEY",
        "COSMOS_POLICY_BASE_URL",
        "COSMOS_POLICY_API_TOKEN",
        "COSMOS_POLICY_TIMEOUT_SECONDS",
        "COSMOS_POLICY_EMBODIMENT_TAG",
        "COSMOS_POLICY_MODEL",
        "COSMOS_POLICY_RETURN_ALL_QUERY_RESULTS",
        "RUNWAYML_API_SECRET",
        "RUNWAY_API_SECRET",
        "LEWORLDMODEL_POLICY",
        "LEWM_POLICY",
        "LEWORLDMODEL_CACHE_DIR",
        "LEWORLDMODEL_DEVICE",
        "JEPA_MODEL_PATH",
        "GENIE_API_KEY",
    ):
        monkeypatch.delenv(env_var, raising=False)

    monkeypatch.setattr(
        sys,
        "argv",
        ["worldforge", "doctor", "--state-dir", str(tmp_path)],
    )
    assert main() == 0
    doctor_payload = json.loads(capsys.readouterr().out)
    provider_names = {provider["name"] for provider in doctor_payload["providers"]}
    assert {"mock", "cosmos"} <= provider_names
    assert doctor_payload["registered_provider_count"] >= 1

    monkeypatch.setattr(
        sys,
        "argv",
        ["worldforge", "provider", "info", "mock", "--state-dir", str(tmp_path)],
    )
    assert main() == 0
    provider_payload = json.loads(capsys.readouterr().out)
    assert provider_payload["registered"] is True
    assert provider_payload["profile"]["implementation_status"] == "stable"
    assert provider_payload["health"]["healthy"] is True


def test_provider_docs_cli_outputs_markdown_and_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["worldforge", "provider", "docs"])
    assert main() == 0
    output = capsys.readouterr().out
    assert output.startswith("# WorldForge Provider Docs")
    assert "`leworldmodel`" in output
    assert "`docs/src/providers/leworldmodel.md`" in output

    monkeypatch.setattr(
        sys,
        "argv",
        ["worldforge", "provider", "docs", "runway", "--format", "json"],
    )
    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == [
        {
            "name": "runway",
            "docs_path": "docs/src/providers/runway.md",
            "implementation_status": "beta",
            "capabilities": "generate, transfer",
            "registration": "RUNWAYML_API_SECRET or RUNWAY_API_SECRET",
            "runtime_ownership": "host supplies Runway credentials and persists returned artifacts",
        }
    ]


def test_world_cli_manages_local_json_persistence(tmp_path, monkeypatch, capsys) -> None:
    state_dir = tmp_path / "worlds"
    export_path = tmp_path / "exports" / "lab-world.json"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "world",
            "create",
            "lab",
            "--provider",
            "mock",
            "--prompt",
            "A kitchen with a mug",
            "--state-dir",
            str(state_dir),
        ],
    )
    assert main() == 0
    created_payload = json.loads(capsys.readouterr().out)
    created_id = created_payload["id"]
    assert created_payload["name"] == "lab"
    assert created_payload["provider"] == "mock"
    assert created_payload["object_count"] >= 2
    assert (state_dir / f"{created_id}.json").exists()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "world",
            "list",
            "--state-dir",
            str(state_dir),
        ],
    )
    assert main() == 0
    list_payload = json.loads(capsys.readouterr().out)
    assert [world["id"] for world in list_payload] == [created_id]

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "world",
            "show",
            created_id,
            "--state-dir",
            str(state_dir),
        ],
    )
    assert main() == 0
    show_payload = json.loads(capsys.readouterr().out)
    assert show_payload["id"] == created_id
    assert show_payload["metadata"]["name"] == "lab"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "world",
            "history",
            created_id,
            "--state-dir",
            str(state_dir),
        ],
    )
    assert main() == 0
    history_payload = json.loads(capsys.readouterr().out)
    assert history_payload["world_id"] == created_id
    assert history_payload["history"][0]["summary"] == "world seeded from prompt"
    assert history_payload["history"][0]["action"] is None

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "world",
            "export",
            created_id,
            "--output",
            str(export_path),
            "--state-dir",
            str(state_dir),
        ],
    )
    assert main() == 0
    export_payload = json.loads(capsys.readouterr().out)
    assert export_payload["output_path"] == str(export_path.resolve())
    exported_payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert exported_payload["state"]["id"] == created_id

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "world",
            "import",
            str(export_path),
            "--new-id",
            "--name",
            "lab-copy",
            "--state-dir",
            str(state_dir),
        ],
    )
    assert main() == 0
    import_payload = json.loads(capsys.readouterr().out)
    assert import_payload["id"] != created_id
    assert import_payload["name"] == "lab-copy"
    assert (state_dir / f"{import_payload['id']}.json").exists()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "world",
            "fork",
            created_id,
            "--history-index",
            "0",
            "--name",
            "lab-start",
            "--format",
            "markdown",
            "--state-dir",
            str(state_dir),
        ],
    )
    assert main() == 0
    fork_output = capsys.readouterr().out
    assert fork_output.startswith("# World world_")
    assert "- name: lab-start" in fork_output


def test_generate_cli_writes_output_file(tmp_path, monkeypatch, capsys) -> None:
    output_path = tmp_path / "mock-output.bin"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "generate",
            "A cube rolling across a table",
            "--provider",
            "mock",
            "--duration",
            "1",
            "--output",
            str(output_path),
            "--state-dir",
            str(tmp_path),
        ],
    )
    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert output_path.exists()
    assert payload["output_path"] == str(output_path.resolve())


def test_cli_supports_provider_listing_predict_transfer_and_eval(
    tmp_path, monkeypatch, capsys
) -> None:
    input_path = tmp_path / "input.mp4"
    input_path.write_bytes(b"mock-input-video")
    transfer_output_path = tmp_path / "transfer-output.bin"

    monkeypatch.setattr(
        sys,
        "argv",
        ["worldforge", "providers", "--state-dir", str(tmp_path)],
    )
    assert main() == 0
    providers_payload = json.loads(capsys.readouterr().out)
    assert any(provider["name"] == "mock" for provider in providers_payload)

    monkeypatch.setattr(
        sys,
        "argv",
        ["worldforge", "provider", "list", "--state-dir", str(tmp_path)],
    )
    assert main() == 0
    provider_list_payload = json.loads(capsys.readouterr().out)
    assert any(provider["name"] == "mock" for provider in provider_list_payload)

    monkeypatch.setattr(
        sys,
        "argv",
        ["worldforge", "provider", "health", "mock", "--state-dir", str(tmp_path)],
    )
    assert main() == 0
    provider_health_payload = json.loads(capsys.readouterr().out)
    assert provider_health_payload["healthy"] is True

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "predict",
            "kitchen",
            "--provider",
            "mock",
            "--x",
            "0.3",
            "--y",
            "0.8",
            "--z",
            "0.0",
            "--steps",
            "2",
            "--state-dir",
            str(tmp_path),
        ],
    )
    assert main() == 0
    predict_payload = json.loads(capsys.readouterr().out)
    assert predict_payload["provider"] == "mock"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "transfer",
            str(input_path),
            "--provider",
            "mock",
            "--width",
            "320",
            "--height",
            "240",
            "--fps",
            "12",
            "--duration",
            "1",
            "--output",
            str(transfer_output_path),
            "--state-dir",
            str(tmp_path),
        ],
    )
    assert main() == 0
    transfer_payload = json.loads(capsys.readouterr().out)
    assert transfer_output_path.exists()
    assert transfer_payload["output_path"] == str(transfer_output_path.resolve())

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "eval",
            "--suite",
            "physics",
            "--provider",
            "mock",
            "--state-dir",
            str(tmp_path),
        ],
    )
    assert main() == 0
    eval_output = capsys.readouterr().out
    assert eval_output.startswith("# Evaluation Report")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "eval",
            "--suite",
            "planning",
            "--provider",
            "mock",
            "--format",
            "json",
            "--state-dir",
            str(tmp_path),
        ],
    )
    assert main() == 0
    eval_payload = json.loads(capsys.readouterr().out)
    assert eval_payload["suite_id"] == "planning"
    assert len(eval_payload["results"]) == 4

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "eval",
            "--suite",
            "reasoning",
            "--provider",
            "mock",
            "--format",
            "csv",
            "--state-dir",
            str(tmp_path),
        ],
    )
    assert main() == 0
    eval_csv = capsys.readouterr().out
    assert eval_csv.startswith("suite_id,suite,provider,scenario,score,passed,metrics_json")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "benchmark",
            "--provider",
            "mock",
            "--operation",
            "generate",
            "--iterations",
            "2",
            "--format",
            "json",
            "--state-dir",
            str(tmp_path),
        ],
    )
    assert main() == 0
    benchmark_payload = json.loads(capsys.readouterr().out)
    assert benchmark_payload["results"][0]["provider"] == "mock"
    assert benchmark_payload["results"][0]["operation"] == "generate"
    assert benchmark_payload["run_metadata"]["providers"] == ["mock"]
    assert benchmark_payload["run_metadata"]["iterations"] == 2


def test_benchmark_cli_applies_budget_file(tmp_path, monkeypatch, capsys) -> None:
    passing_budget = tmp_path / "passing-budget.json"
    passing_budget.write_text(
        json.dumps(
            {
                "budgets": [
                    {
                        "provider": "mock",
                        "operation": "generate",
                        "min_success_rate": 1.0,
                        "max_error_count": 0,
                        "max_retry_count": 0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "benchmark",
            "--provider",
            "mock",
            "--operation",
            "generate",
            "--iterations",
            "1",
            "--format",
            "json",
            "--budget-file",
            str(passing_budget),
            "--state-dir",
            str(tmp_path),
        ],
    )

    assert main() == 0
    passing_payload = json.loads(capsys.readouterr().out)
    assert passing_payload["gate"]["passed"] is True
    assert passing_payload["benchmark"]["results"][0]["operation"] == "generate"
    assert passing_payload["benchmark"]["run_metadata"]["budget_file"]["path"] == str(
        passing_budget.resolve()
    )
    assert len(passing_payload["benchmark"]["run_metadata"]["budget_file"]["sha256"]) == 64

    failing_budget = tmp_path / "failing-budget.json"
    failing_budget.write_text(
        json.dumps(
            {
                "budgets": [
                    {
                        "provider": "mock",
                        "operation": "generate",
                        "max_average_latency_ms": 0.0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "benchmark",
            "--provider",
            "mock",
            "--operation",
            "generate",
            "--iterations",
            "1",
            "--format",
            "markdown",
            "--budget-file",
            str(failing_budget),
            "--state-dir",
            str(tmp_path),
        ],
    )

    assert main() == 1
    failing_output = capsys.readouterr().out
    assert "# Benchmark Report" in failing_output
    assert "# Benchmark Gate Report" in failing_output
    assert "average_latency_ms" in failing_output


def test_benchmark_cli_accepts_input_file(tmp_path, monkeypatch, capsys) -> None:
    input_file = tmp_path / "benchmark-inputs.json"
    input_file.write_text(
        json.dumps(
            {
                "metadata": {"fixture": "unit"},
                "inputs": {
                    "generation_prompt": "fixture benchmark generation",
                    "generation_duration_seconds": 1.0,
                    "embedding_text": "fixture benchmark embedding",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worldforge",
            "benchmark",
            "--provider",
            "mock",
            "--operation",
            "generate",
            "--iterations",
            "1",
            "--format",
            "json",
            "--input-file",
            str(input_file),
            "--state-dir",
            str(tmp_path),
        ],
    )

    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"][0]["provider"] == "mock"
    assert payload["results"][0]["operation"] == "generate"
    assert payload["results"][0]["success_count"] == 1
    assert payload["run_metadata"]["input_file"]["path"] == str(input_file.resolve())
    assert len(payload["run_metadata"]["input_file"]["sha256"]) == 64
    assert payload["run_metadata"]["input_file"]["metadata"] == {"fixture": "unit"}
    assert payload["run_metadata"]["inputs"]["generation_prompt"] == "fixture benchmark generation"
