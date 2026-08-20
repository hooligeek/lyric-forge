# Documentation

| Document | What it covers |
| --- | --- |
| [Getting started](getting-started.md) | Install, first act, first song, importing a catalogue |
| [Concepts](concepts.md) | Suites and stances, dossiers, register, the Glitch Axiom, eras, provenance |
| [Architecture](architecture.md) | The framework/label split, three runtimes, the data model, the gates |
| [Lifecycle](lifecycle.md) | The nine stages and what each gate asks for |
| [Commands](commands.md) | Full command reference |

`lifecycle.md` and `commands.md` are generated from the source. Regenerate after
any change:

```bash
python3 -m framework.forge docs framework
```
