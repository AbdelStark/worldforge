---
name: mock-provider-inline-pattern
description: "Trigger: creating mock providers for tests. Teaches inline mock pattern."
tags: ["testing", "mocks", "providers", "inline", "low"]
---

# Mock Provider Inline Pattern

## The Pattern

Mock providers are defined INLINE in test files. No shared mock library.

## Naming

- Private: `class _ScoreBenchmarkProvider(BaseProvider):`
- Descriptive: `class BadPredictionProvider(BaseProvider):`

## Template

```python
class _MyTestProvider(BaseProvider):
    def __init__(self) -> None:
        super().__init__(
            name="test-provider",
            capabilities=ProviderCapabilities(score=True),
            profile=ProviderProfileSpec(description="Test provider."),
        )
        self.calls: list[dict[str, object]] = []

    def score_actions(self, *, info: JSONDict, action_candidates: object) -> ActionScoreResult:
        self.calls.append({"info": info, "action_candidates": action_candidates})
        self._emit_event(
            ProviderEvent(
                provider=self.name,
                operation="score",
                phase="success",
                duration_ms=0.1,
            )
        )
        return ActionScoreResult(
            provider=self.name,
            scores=[0.5],
            best_index=0,
            lower_is_better=True,
        )
```

## Rules

1. Define mocks inline — each test file owns its test doubles
2. Declare capabilities explicitly
3. Emit events for conformance testing
4. Track calls for assertion

## Sharp Edges

| Symptom | Cause | Fix |
|---------|-------|-----|
| Mock drifts from reality | Shared mock library | Define inline |
| Missing events | No event emission | Add _emit_event |
| No call tracking | Missing self.calls | Add call tracking |
