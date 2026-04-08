# Python API

## Entry points

```python
from worldforge import WorldForge, World, Action
```

## `WorldForge`

Top-level framework object responsible for:

- provider registration
- world creation and persistence
- generation, transfer, reasoning, and embedding helpers
- provider profiles and environment diagnostics

Common inspection helpers:

```python
from worldforge import WorldForge

forge = WorldForge()

profiles = forge.builtin_provider_profiles()
doctor = forge.doctor()

print(profiles[0].supported_tasks)
print(doctor.issues)
```

## Observability

```python
import logging

from worldforge import WorldForge
from worldforge.observability import JsonLoggerSink, ProviderMetricsSink, compose_event_handlers

metrics = ProviderMetricsSink()
forge = WorldForge(
    event_handler=compose_event_handlers(
        JsonLoggerSink(logger=logging.getLogger("demo.worldforge")),
        metrics,
    )
)

forge.generate("orbiting cube", "mock", duration_seconds=1.0)
print(metrics.get("mock", "generate").to_dict())
```

## `World`

Stateful runtime object responsible for:

- scene object management
- prediction
- comparison
- planning
- evaluation

## Evaluation

```python
from worldforge.evaluation import EvaluationSuite

suite = EvaluationSuite.from_builtin("physics")
report = suite.run_report("mock", forge=forge)
print(report.to_markdown())
```

## Provider contract testing

```python
from worldforge.providers import MockProvider
from worldforge.testing import assert_provider_contract

report = assert_provider_contract(MockProvider())
print(report.to_dict())
```
