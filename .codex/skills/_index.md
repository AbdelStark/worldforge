# WorldForge Skill Registry

Last updated: 2026-04-30

Keep this directory boring: one folder per repeated workflow, one `SKILL.md` per folder, no README files, no XML/HTML tags, no tiny reference files that merely duplicate the main skill.

| Skill | Use when | Keep because |
| --- | --- | --- |
| `provider-adapter-development` | provider capability, adapter, catalog, scaffold, optional provider promotion | Provider truthfulness is the highest-risk WorldForge surface. |
| `testing-validation` | choosing or repairing validation gates, CI parity, package contract, docs drift | Prevents ritualized or incomplete validation. |
| `evaluation-benchmarking` | benchmark inputs, budget gates, eval suites, report claims | Protects claim boundaries and reproducibility. |
| `optional-runtime-smokes` | LeWorldModel, GR00T, LeRobot, PushT, checkpoint/live smoke work | Keeps host-owned runtime dependencies out of the base package. |
| `persistence-state` | local JSON worlds, world IDs, history, import/export/fork | Persistence failures corrupt user state. |
| `tui-development` | TheWorldHarness flows, Textual screens, screenshots | Textual must stay optional and isolated. |
| `public-docs-release` | README/docs/changelog/release-surface alignment | Public behavior changes have many synchronized surfaces. |

Do not add a new skill unless the workflow is repeated, multi-step, and has a stable definition of done.
