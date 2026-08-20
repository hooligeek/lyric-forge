# Documentation

| Document | What it covers |
| --- | --- |
| [Getting started](getting-started.md) | Install, first act, first song, importing a catalogue |
| [Concepts](concepts.md) | Suites and stances, dossiers, register, the Glitch Axiom, eras, provenance |
| [Architecture](architecture.md) | The framework/label split, three runtimes, the data model, the gates |
| [Lifecycle](lifecycle.md) | The nine stages and what each gate asks for |
| [Commands](commands.md) | Full command reference |
| `AGENTS.md` (repo root) | Rules for an agent working here — also emitted as `CLAUDE.md`, `.github/copilot-instructions.md` and `.kiro/steering/` |
| [Adversarial audit brief](adversarial-audit.md) | A reusable brief for an independent security, code and docs review. Any fork should run it. |
| [Audit report](audit-report.md) | Historical: the 2026-08-20 review, all findings since addressed. Kept for its method and calibration. |

`lifecycle.md` and `commands.md` are generated from the source. Regenerate after
any change:

```bash
python3 -m framework.forge docs framework
python3 -m framework.forge docs agents
```

The agent files are four copies of one source. They are duplicated because most tools inject their instructions directly rather than following a pointer — and generated, because four hand-maintained copies would drift.
