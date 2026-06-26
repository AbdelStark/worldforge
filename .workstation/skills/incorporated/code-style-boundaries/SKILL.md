---
name: code-style-boundaries
description: "Trigger: writing Python code. Teaches style rules as contract enforcement."
tags: ["convention", "style", "python", "ruff", "contracts", "low"]
---

# Code Style Boundaries

## Python Version

```toml
requires-python = ">=3.13,<3.14"
```

## Imports

```python
from __future__ import annotations
```

## Dataclasses

```python
@dataclass(slots=True)  # Prevents attribute drift
@dataclass(slots=True, frozen=True)  # Immutable
```

## Line Length

100 characters (not 79, not 120)

## Ruff Rules

```toml
select = ["E", "F", "I", "B", "UP"]
extend-select = ["C4", "N806", "PERF", "PIE", "PLW1510", "PT013", "PT018", "RET", "RUF", "SIM"]
```

## Type Patterns

```python
ProviderCapabilities()  # Fail-closed — no capabilities by default
JSONDict = dict[str, Any]  # JSON-facing payloads
```

## Rules

1. Validate at boundary, not serialization
2. Copy mutable inputs before storing
3. Fail loud on invalid input
4. Never silently coerce

## Sharp Edges

| Symptom | Cause | Fix |
|---------|-------|-----|
| Attribute drift | Missing slots=True | Add slots=True |
| Capability leak | Not fail-closed | Use ProviderCapabilities() |
| Aliasing bug | Mutable input not copied | Copy before storing |
