# lyric-forge

Run a virtual record label as a system that can be checked.

Personas with fixed rhetorical positions. Thematic matrices that resist
repetition. A ledger that can be verified against disk. Audio analysis that finds
where the synthesiser actually broke, so those failures can be kept deliberately
instead of regenerated away.

Built for [Suno](https://suno.com) output and agent-driven workflows, with a
no-install tier for [NotebookLM](https://notebooklm.google.com). Nothing in
`framework/` knows about any particular label.

---

## Why this exists

Most AI-music workflows fail the same two ways.

**They converge.** A vocabulary list constrains *words* and does nothing about
*syntax*, which is where sameness actually lives. In the catalogue this was built
from, one act had four thematic suites, six songs, and a single speech act across
all six: second-person accusation. The topic rotated; the posture never did.
Another opened three separate bridges on *"A deep lack of ___"*. No lexicon check
would ever have caught either.

**They assert instead of measuring.** The predecessor of this system kept its
metadata ledger as prose inside notebook documents and ran a six-gate compliance
audit against it. Every gate measured *format*, which is trivially satisfiable, so
it passed a catalogue where four tracks shared a BPM, a key and a byte-identical
sonic blueprint — and it once reported `PASS` for four files, three of which did
not exist. A model has no way to tell verifying a file from describing one.

So: everything checkable is checked in code, and only genuine judgement is put to
a model.

| Computed | Delegated |
| --- | --- |
| burned phrase reused | is the stance held for the whole song |
| bare or overloaded cue | is the narrator on-model |
| suite anchor missing | does a line contradict the shared biography |
| tempo above the measured ceiling | is the addressee specific enough |
| phrase shared with another act | is it any good |

---

## Three ways to use it

**No install.** Take `bundles/fresh-spark/`, upload the eight files to one
notebook, follow `00-START-HERE.md`. You need an idea and, ideally, one demo
render. That is the whole dependency list.

**Agent-driven.** Install the toolchain and drive it from your editor — Claude
Code, Codex, Copilot, Kiro. Reporting commands take `--json`; `AGENTS.md` and its
per-platform siblings carry the rules an agent needs. This is the primary case.

**Direct API.** Bring your own key for Anthropic, OpenAI or Google. Credentials
come from environment variables only.

All three render the same prompt templates. The same `generate-song` produces a
~17,000-character API prompt with the dossier substituted in, and a
~4,700-character notebook prompt that says *"See 03-dossier.md in your sources."*
One artefact, three deliveries — because if each runtime carried its own copy of
the wording, the same brief would produce different songs depending on where it
ran.

---

## Install

```bash
git clone https://github.com/hooligeek/lyric-forge
cd lyric-forge
python3 -m venv .venv
./.venv/bin/pip install -e .              # core, and provides the `forge` command
./.venv/bin/pip install -e '.[analysis]'  # optional: audio analysis
```

Python 3.12+. `ffmpeg` and `ffprobe` on `PATH`. Only `forge analyze` needs the
extras — everything else runs on the standard library plus `pyyaml`.

```bash
forge status     # where everything sits
forge next       # what to do, and why
forge stages     # the process itself
```

Those three exist because an agent — or you, returning after a month — arrives
with no idea what the project needs.

---

## Writing a song

```bash
forge spark --band <slug> --file note.md         # capture the raw thing
forge spark --confirm --band <slug> --track <t>  # agree the computed brief
forge infer --id generate-song --band <slug> --track <t> --write
forge review --band <slug> --track <t>           # mechanical checks, computed
forge review --band <slug> --track <t> --prompt  # judgement, delegated
# ... render it in Suno ...
forge ingest-audio --band <slug> --track <t> --file "Take 3.mp3"
forge analyze --band <slug> --track <t> --write
forge adjudicate --band <slug> --write           # then --apply
```

Every transition is recorded with who did it and why. The full walkthrough is in
[docs/getting-started.md](docs/getting-started.md).

Two things the tool will not do. It will not decide which synthesis failures are
worth keeping — that judgement is the whole point and automating it would gut it.
And it will not write a timecode it did not measure.

---

## Documentation

| Document | Covers |
| --- | --- |
| [Getting started](docs/getting-started.md) | Install, first act, first song, importing a catalogue |
| [Concepts](docs/concepts.md) | Suites and stances, dossiers, register, the Glitch Axiom, eras, provenance |
| [Architecture](docs/architecture.md) | The framework/label split, three runtimes, the data model, the gates |
| [Lifecycle](docs/lifecycle.md) | The nine stages and what each gate asks for |
| [Commands](docs/commands.md) | Full reference |
| [AGENTS.md](AGENTS.md) | The invariants, for an agent working here |

`commands.md` and `lifecycle.md` are generated from the source and cannot drift
from it. CI regenerates every artefact and fails on any diff.

---

## Approved forks

A fork is a label. `framework/` stays generic; `label/` is yours.

Listing here means the fork passes `forge certify` — nine gates, run against the
whole catalogue. It is not a quality judgement about anyone's music, and it never
will be. It means the catalogue is complete, internally consistent, and its
documentation was generated from the ledger it describes.

| Fork | Label | Acts | Tracks | Certified |
| --- | --- | --- | --- | --- |
| [`vector-soul`](../../tree/vector-soul) | Vector Soul Records | 5 | 21 | ✅ 9/9 |

### What certification checks

```bash
forge certify
```

| Gate | Requires |
| --- | --- |
| structural | `reconcile --strict` reports zero defects |
| evidence | no entry claims measurement that nothing performed |
| templates | every prompt slot used is declared, and vice versa |
| assets | every released track has audio, artwork, a lyric sheet, and a hash for each binary |
| brief | every released track is classified — era-aware, so imported work is exempt |
| publication | every released track has a **verified** listening link |
| documents | every lyric sheet matches its master, or the discrepancy is acknowledged with a reason |
| pipeline | nothing is stuck waiting on a human decision |
| freshness | the committed catalogue regenerates byte-identically |

Freshness is the one that makes the others hold: documentation generated from a
ledger only means anything if it came from *that* ledger.

Two of these deserve a note. **Publication** rejects a constructed URL — an id is
evidence, a URL built from one is an assumption, and five such links in the
reference fork turned out to use the wrong scheme entirely. **Documents** can be
satisfied by acknowledging a known discrepancy rather than fixing it: some sheets
are demonstrably the draft rather than the take and the real lyrics no longer
exist. Requiring recovery would make certification impossible for honest reasons;
passing them silently would make it meaningless. So the acknowledgement carries a
reason and appears in the catalogue, where anyone can read it.

### Submitting a fork

1. Fork this repository, or branch it.
2. Replace `label/` with your own. Do not edit `framework/` to accommodate your
   content — if you need to, that is a framework bug and worth an issue.
3. Get `forge certify` to exit 0.
4. Open a pull request against `main` adding one row to the table above. CI runs
   certification on your branch; the artefact it uploads is the evidence.

`forge certify` tells you exactly what is missing. None of it is subjective.

---

## Licence

[MIT](LICENSE) for `framework/` — the toolchain, which is meant to be forked.

It does **not** purport to license `label/`. The lyrics, masters, artwork and
label writing in a fork are that operator's creative work. Replace the directory;
do not inherit it.
