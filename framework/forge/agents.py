"""Generate per-platform agent instruction files from one source.

Claude Code, Codex, Copilot and Kiro each look in a different place, and none of
them reliably follows a pointer to another file — Copilot injects its instructions
into context directly, so "see AGENTS.md" often means the agent never reads the
rules at all. So the content is duplicated into each location.

Duplication is acceptable here for the same reason it is acceptable in the
notebook bundles: it is *generated*. One source, `RULES`, four destinations, and
`forge docs agents` re-emits them. Four hand-maintained copies would drift, which
is the argument that ruled out the wiki and the per-runtime prompt copies.

The content is not aspirational. Every rule below corresponds to a mistake made
while building this — a duplicated glitch log, a wiped candidates file, a
lifecycle stamped backwards, timecodes that came from a system with no clock.
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# the single source
# ---------------------------------------------------------------------------
INTRO = """\
`lyric-forge` runs a virtual record label as a checkable system: personas with
fixed rhetorical positions, thematic matrices that resist repetition, a ledger
that can be verified against disk, and audio analysis that finds where the
synthesiser broke.

The tool is designed to be driven by you, from an editor. Structured output is
the primary interface — most reporting commands take `--json`.
"""

ORIENT = """\
## Orient before acting

```bash
python3 -m framework.forge status --json   # where every track sits
python3 -m framework.forge next --json     # what to do, and why
python3 -m framework.forge stages          # the process itself
```

`next` returns a computed brief proposal — suite, stance, tempo, spent phrases,
constraints — derived from what the catalogue is short of. Prefer it to inventing
a direction.
"""

NEVER_FABRICATE = """\
## Never fabricate evidence

This is the single most important rule and the easiest to break, because invented
data looks exactly like measured data.

- **Never write a timecode you did not measure.** Anchor observations to
  *section + lyric phrase* instead. Entries carry `timecode_verified` for this
  reason; a previous system produced round timecodes from a notebook with no
  ability to measure time.
- **Never write a glitch log before the audio exists.** Anomalies are observed
  after a render, never predicted.
- **Never fill an `UNMEASURED` register with a plausible number.** A guessed
  tempo ceiling presented as known is the failure the measurement layer exists to
  end.
- **`declared_*` and `measured_*` are separate claims.** Never merge them. They
  disagree on nine of twenty-one tracks in the reference catalogue, and that
  disagreement is the finding.
- **Constructed is not verified.** URLs built from an id carry
  `url_verified: false` until someone opens one. Five such URLs turned out to use
  the wrong scheme entirely.
- If the data does not determine something, **say so and name what is missing.**
  `CANNOT ASSESS` is a distinct outcome from "no issues found".
"""

GENERATED = """\
## Do not hand-edit generated files

Edit the generator, then regenerate.

| Generated | By |
| --- | --- |
| `analysis:` blocks in `tracks.yaml` | `forge analyze --write` |
| `glitch-candidates.yaml` | `forge analyze --write` |
| `adjudication.yaml` | `forge adjudicate --write` |
| `docs/`, `docs/catalog/` | `forge docs framework` / `forge docs catalog` |
| `dist/` | `forge bundle export` |
| `bundles/fresh-spark/` | `forge bundle fresh` |
| `commands.md`, `lifecycle.md` | generated from argparse and `lifecycle.py` |

`lifecycle.stage` is **derived** from what exists on disk. Do not set it by hand;
fix the underlying state instead. A recorded stage that disagrees with reality is
worse than no stage.
"""

BOUNDARIES = """\
## Privacy and credential boundaries

- **`label/sparks/` is gitignored.** It holds the rawest human input. Never copy
  spark text into a committed brief, a commit message, or a doc. The brief
  references the spark by **id only** — a "derived summary" leaks it back in
  through the side door.
- **Credentials come from environment variables only.** Never write a key to a
  file in the tree, never pass one as a command-line argument. `inference.local.yaml`
  names the variable to read; it never holds a value.
- Masters and artwork **are** committed. Decoded PCM under `.cache/` is not.
"""

JUDGEMENT = """\
## Where your judgement stops

- **You never decide which synthesis failures are kept.** That is the Glitch
  Axiom and it belongs to the operator. Present the evidence, propose a name
  under the band's protocol, and stop. `forge adjudicate` is built around this.
- **Mechanical findings are computed in Python; judgement findings are yours.**
  A mechanical finding cites the rule it broke. A judgement finding must **quote
  the line it is about** — a judgement you cannot anchor to a line is an
  impression, and impressions do not go in the report.
- **Do not retrofit the pre-standard era.** Tracks tagged `era: pre-standard`
  predate the standards and are exempt from the matrix, stance and lexicon gates.
  Their repetitions are the corpus the burned lists were mined from, not a
  compliance failure.
"""

WORKFLOW = """\
## Before you finish

```bash
python3 -m framework.forge reconcile --strict   # must exit 0
python3 -m framework.forge prompt lint          # after touching any template
```

After changing anything under `label/`, regenerate what depends on it:

```bash
python3 -m framework.forge docs catalog
python3 -m framework.forge bundle export
```

Commit or push only when asked.
"""

GOTCHAS = """\
## Known sharp edges

- **`forge analyze` needs the venv** (`librosa`, `faster-whisper`) and takes
  **minutes per track**. Run it as `./.venv/bin/python -m framework.forge analyze`
  and watch `tail -f .cache/analyze.log`. Piping its stdout through `grep` buffers
  the output and looks like a hang.
- **`import-lyrics` dry-runs by default.** Check the parse before `--write`.
- **The catalogue digest must never contain lyrics.** A model shown its own
  previous choruses echoes them; the negative space is the useful part.
- **Nested heredocs mangle escapes** in this WSL setup: `\\n` inside a bash
  heredoc that writes Python becomes a literal newline and breaks the file. Write
  the script to a file, or use the editor tools, rather than nesting.
- **Read the output you generate.** Almost every defect found while building this
  was caught by looking at what a command produced, not by the code looking
  wrong — including two in work that had already been reported as passing.
"""

RULES = [INTRO, ORIENT, NEVER_FABRICATE, GENERATED, BOUNDARIES, JUDGEMENT, WORKFLOW, GOTCHAS]


@dataclass
class AgentFile:
    path: str
    content: str


def _body() -> str:
    return "\n".join(RULES).strip() + "\n"


HEADER_NOTE = (
    "<!-- Generated by `forge docs agents` from framework/forge/agents.py.\n"
    "     Edit that file, not this one — four hand-maintained copies would drift. -->\n"
)


def build() -> list[AgentFile]:
    body = _body()
    files: list[AgentFile] = []

    # AGENTS.md — the cross-tool convention, read natively by Codex among others.
    files.append(
        AgentFile(
            "AGENTS.md",
            HEADER_NOTE
            + "# Agent instructions\n\n"
            + "Canonical rules for any agent working in this repository. The "
            + "per-platform files carry the same content because most tools "
            + "inject their instructions directly and do not follow pointers.\n\n"
            + body,
        )
    )

    # Claude Code.
    files.append(
        AgentFile(
            "CLAUDE.md",
            HEADER_NOTE
            + "# CLAUDE.md\n\n"
            + body
            + """
## Claude Code specifics

- Prefer `--json` on reporting commands and parse the result rather than scraping
  the formatted table. Both come from the same dict, so nothing is lost.
- `forge analyze` runs long enough to exceed a foreground timeout. Start it in
  the background and follow `.cache/analyze.log`.
- The masters are ~102 MB of committed mp3. Avoid commands that would rewrite
  them; mp3 does not delta-compress, so a rewrite is a full new copy in history.
"""
        )
    )

    # GitHub Copilot — repository-wide custom instructions.
    files.append(
        AgentFile(
            ".github/copilot-instructions.md",
            HEADER_NOTE + "# Copilot instructions\n\n" + body,
        )
    )

    # Copilot also supports path-scoped instructions, which is the one genuinely
    # platform-specific win here: the data rules and the code rules are different
    # jobs and apply to different trees.
    files.append(
        AgentFile(
            ".github/instructions/label-data.instructions.md",
            HEADER_NOTE
            + "---\napplyTo: \"label/**\"\n---\n\n"
            + "# Working in `label/` — the data\n\n"
            + NEVER_FABRICATE
            + "\n"
            + BOUNDARIES
            + "\n"
            + JUDGEMENT
            + "\n## Regenerate after editing\n\n"
            + "```bash\npython3 -m framework.forge reconcile --strict\n"
            + "python3 -m framework.forge docs catalog\n"
            + "python3 -m framework.forge bundle export\n```\n",
        )
    )
    files.append(
        AgentFile(
            ".github/instructions/framework-code.instructions.md",
            HEADER_NOTE
            + "---\napplyTo: \"framework/**\"\n---\n\n"
            + "# Working in `framework/` — the toolchain\n\n"
            + "`framework/` must stay label-agnostic. It is lifted into other "
            + "projects untouched, so nothing here may reference a specific "
            + "label, band, or track.\n\n"
            + "- Prompt templates are markdown with YAML frontmatter. Run "
            + "`forge prompt lint` after any change: every slot used must be "
            + "declared and every slot declared must be used, or a literal "
            + "`{{slot}}` reaches a model and degrades output silently.\n"
            + "- Reporting commands return a dict; the formatted view is a second "
            + "rendering of it. Do not add a separate formatting path that can "
            + "drift from the data.\n"
            + "- Checkable things are checked in Python. Only genuine judgement is "
            + "delegated to a model.\n\n"
            + GOTCHAS,
        )
    )

    # Kiro steering. `inclusion: always` is the steering equivalent of a
    # repository-wide instruction file.
    files.append(
        AgentFile(
            ".kiro/steering/lyric-forge.md",
            HEADER_NOTE
            + "---\ninclusion: always\n---\n\n"
            + "# lyric-forge\n\n"
            + body,
        )
    )
    return files
