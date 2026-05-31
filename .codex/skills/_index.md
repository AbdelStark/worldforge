# WorldForge Skill Registry

Last updated: 2026-05-25

Keep this directory boring: one folder per repeated workflow, one `SKILL.md` per folder, no README files, no XML/HTML tags, no tiny reference files that merely duplicate the main skill. `agents/openai.yaml` is allowed for UI metadata and must stay aligned with the corresponding `SKILL.md`.

| Skill | Use when | Keep because |
| --- | --- | --- |
| `provider-adapter-development` | provider capability, adapter, catalog, scaffold, optional provider promotion | Provider truthfulness is the highest-risk WorldForge surface. |
| `testing-validation` | choosing or repairing validation gates, CI parity, package contract, docs drift | Prevents ritualized or incomplete validation. |
| `evaluation-benchmarking` | benchmark inputs, budget gates, eval suites, report claims | Protects claim boundaries and reproducibility. |
| `optional-runtime-smokes` | LeWorldModel, GR00T, LeRobot, PushT, checkpoint/live smoke work | Keeps host-owned runtime dependencies out of the base package. |
| `persistence-state` | local JSON worlds, world IDs, history, import/export/fork | Persistence failures corrupt user state. |
| `tui-development` | robotics showcase Textual report UI, panes, launch helpers, screenshots | Textual must stay optional and isolated. |
| `public-docs-release` | README/docs/changelog/release-surface alignment | Public behavior changes have many synchronized surfaces. |

Do not add a new skill unless the workflow is repeated, multi-step, and has a stable definition of done.

## 10/10 Skill Bar

A WorldForge project skill is 10/10 only when all of these are true:

- The frontmatter description makes the trigger and key exclusions obvious before the body loads.
- The body is short, imperative, and specific to WorldForge; generic advice is absent.
- The skill names the files to inspect, commands to run, and evidence that proves completion.
- The skill prevents the most likely wrong turn for its domain.
- Any generated `agents/openai.yaml` has a human-readable name, concise description, and a default prompt that invokes the skill explicitly.
- Validation is command-backed: run `quick_validate.py` for changed skills plus the relevant repo docs/test gate.
