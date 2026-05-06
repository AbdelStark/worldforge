# External Provider Packages

External adapter packages can register WorldForge providers without modifying the WorldForge
repository. WorldForge discovers them at construction time through the
``worldforge.providers`` Python entry-point group.

## Entry-point declaration

Add an entry to your package's ``pyproject.toml``:

```toml
[project.entry-points."worldforge.providers"]
my-policy = "my_pkg.adapters:make_my_policy_provider"
```

The entry-point **name** (``my-policy``) is the provider name WorldForge will surface in
``providers()``, ``doctor()``, and benchmark/evaluation reports. The **value**
(``my_pkg.adapters:make_my_policy_provider``) is a fully qualified callable that returns a
:class:`~worldforge.providers.base.BaseProvider`.

## Factory contract

The referenced callable takes one optional keyword argument and returns a `BaseProvider`:

```python
from worldforge.providers import BaseProvider, ProviderProfileSpec
from worldforge import ProviderCapabilities


def make_my_policy_provider(*, event_handler=None) -> BaseProvider:
    return MyPolicyProvider(event_handler=event_handler)
```

Three rules:

1. The provider's ``name`` attribute must equal the entry-point name. WorldForge raises
   ``WorldForgeError`` from ``ProviderCatalogEntry.create()`` when they disagree, which
   prevents accidental name collisions in user-facing output.
2. The factory must return a ``BaseProvider`` subclass. Returning anything else is rejected
   with a typed error when the entry is invoked.
3. The provider follows the same env-gated auto-registration rules as in-repo providers:
   ``configured()`` must return ``True`` for the provider to be auto-registered. Hosts can
   still register an unconfigured provider explicitly via ``forge.register_provider(...)``.

## Failure behaviour

Discovery never crashes the host. Each entry-point that cannot be wrapped is recorded with a
typed reason:

| Cause | Example reason |
| --- | --- |
| Module import fails (missing optional dependency) | ``missing dependency: No module named 'torch'`` |
| Loaded value is not callable | ``entry point did not resolve to a callable`` |
| Name collides with an in-repo provider | ``duplicate name (in-repo provider already registered)`` |
| Two entry points share a name | ``duplicate name (already discovered earlier in this group)`` |
| Loader raises any other exception | ``load failed: <message>`` |
| Factory raises at construction time | ``factory raised: <message>`` |

The full report lives on ``WorldForge.entry_point_discovery()``:

```python
from worldforge import WorldForge

forge = WorldForge()
report = forge.entry_point_discovery()
print(report.discovered_count, "external providers discovered")
for skip in report.skipped:
    print(f"skipped {skip.name}: {skip.reason}")
```

## Disabling discovery

Two switches turn discovery off:

1. **Constructor flag**: ``WorldForge(discover_entry_points=False)`` skips discovery entirely.
2. **Environment variable**: setting ``WORLDFORGE_DISABLE_ENTRY_POINTS`` to a non-empty value
   has the same effect for all forges in the process. Hosted environments use this to keep CI
   runs deterministic when third-party packages are installed for unrelated reasons.

When discovery is disabled, ``forge.entry_point_discovery().enabled`` is ``False`` and no
external providers are registered.

## Stability

This surface is **provisional**. The entry-point group name and discovery report shape are
stable for the current release, but ``EntryPointSkip.reason`` strings are human-readable
diagnostics rather than a machine-parseable contract. Treat them like log messages.

## Related public API

| Symbol | Purpose |
| --- | --- |
| ``worldforge.ENTRY_POINT_GROUP`` | The entry-point group name (``worldforge.providers``). |
| ``worldforge.ENTRY_POINT_DISABLE_ENV_VAR`` | Name of the disable env var. |
| ``worldforge.discover_entry_point_providers`` | Run discovery without instantiating a forge. |
| ``worldforge.EntryPointDiscoveryReport`` | Frozen dataclass with the run summary. |
| ``worldforge.EntryPointSkip`` | One skip record (name, value, reason). |
| ``WorldForge.entry_point_discovery()`` | The report captured at construction time. |

## Validation

```bash
uv run pytest tests/test_provider_entry_points.py tests/test_provider_catalog.py
uv run mkdocs build --strict
```
