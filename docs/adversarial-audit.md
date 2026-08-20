# Adversarial audit brief

Carry this to a fresh session. Point the agent at this file and say: **"Read
`docs/adversarial-audit.md` and execute it."**

---

## Your role

You are an independent reviewer with no stake in this codebase. You did not
build it, you owe it nothing, and your job is to find what is wrong with it.

The author has read the code and has private suspicions about its weak points.
Those are **deliberately not shared with you**, because the value of this exercise
is an independent read. Do not ask for hints.

## Two failure modes, and they are equally bad

**Rubber-stamping.** Finding three cosmetic issues, praising the architecture, and
concluding it is production-ready. If you catch yourself writing "overall, the
code is well-structured", stop and go look harder at something you have not opened
yet.

**Padding.** Inventing findings to look thorough. A report with twenty items where
six are real is worse than a report with six, because the reader now has to
re-audit your audit. Style opinions, framework preferences, and "consider adding
type hints" are noise. Do not include them.

You are being judged on whether every finding is **real**, **specific**, and
**consequential** — not on how many you produce. Zero findings in a category is a
legitimate result if you can say what you checked to get there.

## Evidence or abstain

This is the project's own discipline and it applies to your report.

- Every finding cites `path/to/file.py:LINE`.
- Every finding states a **concrete failure scenario**: specific inputs or state,
  leading to a specific wrong outcome. "Could be exploited" is not a scenario.
- Every finding is marked **CONFIRMED** (you reproduced it — show the command and
  the output) or **PLAUSIBLE** (you reasoned it from the code but did not run it).
  Do not blur these.
- If you could not assess something, say so and name what you would have needed.
  `CANNOT ASSESS` is a legitimate and useful outcome. It is not the same as "no
  issues found", and conflating them is the exact failure this project was built
  to correct.

## What this thing is

`lyric-forge` runs a virtual record label as a checkable system. A Python CLI
(`framework/forge/`, 26 modules) manages a YAML ledger of songs, analyses audio
(ffmpeg, librosa, faster-whisper), renders prompt templates for three inference
runtimes, and generates documentation, NotebookLM bundles and a release catalogue.

```bash
python3 -m framework.forge stages     # the song lifecycle
python3 -m framework.forge status     # current state
cat docs/architecture.md              # the design, as claimed
cat AGENTS.md                         # the invariants, as claimed
```

Read `docs/architecture.md` and `docs/concepts.md` first, then treat both as
**claims to be tested** rather than as fact.

---

## Scope 1 — Security

The interesting surface is not a web endpoint. It is a local tool that handles
credentials, executes subprocesses with user-controlled arguments, writes files at
paths derived from user data, and — most importantly — **feeds untrusted document
content into prompts sent to language models.**

Areas to work through. This list is where to look, not what you will find:

**Credential handling.** `framework/forge/inference.py`. Keys come from
environment variables by design. Verify that claim holds: can a key reach a file,
a log, an error message, a generated doc, stdout, or a committed artefact? Check
the redaction in `Request.redacted()` against every path a request or exception
can take. Google's key travels in a URL query string — follow it everywhere that
URL goes.

**Subprocess execution.** `audio.py`, `artwork.py`. ffmpeg and ffprobe are invoked
with filenames that originate from user files and from ledger data. Argument lists
rather than shells are used — verify that is true everywhere, and consider what a
filename beginning with `-` does.

**Path construction.** Destination paths are built from band slugs, track slugs
and filenames. `config.slugify()` is the sanitiser. Try to escape the intended
directory: a crafted filename, a crafted `slug:` field in `tracks.yaml`, a crafted
`--out`. Follow `ingest.py`, `docs.py`, `bundle.py`, `spark.py`.

**Deserialisation.** Confirm every YAML read is `safe_load`. Check what a
malicious `tracks.yaml` or `band.yaml` can do — these are data files a
collaborator could edit in a pull request.

**Prompt injection.** This is the most under-considered surface. `import-lyrics`
ingests third-party harvest documents; `review` accepts arbitrary lyrics;
`context.py` assembles all of it into prompts sent to a model that may have tool
access in the calling agent. What happens if a lyric file contains instructions
addressed to the agent? Trace `lyrics.parse()` → `context.build()` →
`prompts.render()` and say whether anything constrains it.

**Secrets already in the tree.** Do not assume. Check:
```bash
git log --all -p | grep -nEi '(api[_-]?key|secret|token|bearer|sk-[A-Za-z0-9]{20,})' | head
git ls-files | xargs grep -lEi 'sk-ant|sk-[A-Za-z0-9]{32}|AIza[A-Za-z0-9_-]{30}' 2>/dev/null
cat .gitignore
git check-ignore -v label/sparks/x.md inference.local.yaml .env
```
The repository contains ~110 MB of committed audio and images. Consider whether
anything sensitive travels in file metadata.

**Privacy invariant.** `label/sparks/` is gitignored and holds the operator's
rawest personal input. The claim is that nothing from a spark reaches a committed
file. Try to break that: trace every consumer of the spark text and check what
each one writes.

---

## Scope 2 — Code quality

Judge it as a tool someone else will maintain. Not style — consequences.

**Tests.** Establish what test coverage exists. If the answer is none, do not
simply report "no tests" — that is not useful on its own. Identify the **three
functions where absence of tests is most dangerous**, and for each say what a
plausible regression would silently break and how long it would go unnoticed.
Candidates worth weighing: the lyric parser's state machine, the triage
heuristics, the lifecycle stage derivation.

**Silent failure.** Hunt for places where an error is swallowed and the caller
receives a plausible-looking wrong answer instead of a failure. `except Exception`
with a fallback is the pattern to grep for. Rank by how invisible the wrong answer
would be.

**Correctness of the heuristics.** Several functions make judgement calls in code:
`adjudicate.triage()`, `adjudicate._materiality()`, `review.syllables()`,
`analyze.diff_pass()` verdict thresholds, `artwork.dhash()` and its two distance
thresholds. Pick the two you consider least defensible and construct inputs where
they give the wrong answer. Thresholds derived from a single catalogue are the
obvious target.

**Private API coupling.** `docs.py` generates a command reference by walking
argparse internals (`parser._actions`, `_choices_actions`). Other modules reach
into each other's underscore-prefixed functions. Identify what breaks on a Python
upgrade or a refactor, and how loudly.

**Idempotence and destructiveness.** Commands write to shared files. Two bugs of
this class were already found and fixed during development: a single-track
`analyze --write` replaced a whole band's candidates file, and `adjudicate --apply`
duplicated log entries on re-run. **Assume there are more of the same shape.** For
every command that writes, ask what running it twice does, and what running the
narrow form does to data belonging to siblings.

**Performance.** `review.check_catalogue_overlap()` and `mine._prune_contained()`
are the obvious candidates. State the complexity and the catalogue size at which
they become unusable. Do not report performance as a finding unless you can name
the threshold.

**Error messages.** The tool is designed to be driven by an agent. Sample failures
and judge whether the message tells an agent what to do next, or merely what went
wrong.

---

## Scope 3 — Documentation quality

Documentation here makes **checkable claims**. Check them.

`docs/architecture.md`, `docs/concepts.md`, `docs/getting-started.md`, `AGENTS.md`,
`bundles/fresh-spark/`, and the generated `docs/commands.md` and
`docs/lifecycle.md`.

**Verify the specific claims.** The docs assert particular numbers and behaviours.
Test them:
- Does `getting-started.md` actually work? Follow it literally from a clean state
  and record where it breaks or requires undocumented knowledge.
- The catalogue claims 21 resolvable audio elements and working asset links.
  Verify.
- `commands.md` claims it cannot drift from the code. Verify it matches
  `--help` for every subcommand.
- `AGENTS.md` states invariants. For each, find whether the code actually enforces
  it or merely asks.

**Find the gap between stated and actual.** Where does a doc describe an intention
the code does not implement? That gap is the most valuable thing you can find in
this scope, because it misleads silently.

**Onboarding honesty.** `bundles/fresh-spark/00-START-HERE.md` targets someone
with no toolchain at all. Read it as that person. What does it assume that they
will not have?

**What is missing.** No changelog, no contribution guide, no licence — assess
whether each absence matters for a repository intended to be forked as a template.

---

## Method

Do not review by reading alone. Run it.

```bash
python3 -m framework.forge reconcile --strict ; echo "exit: $?"
python3 -m framework.forge prompt lint        ; echo "exit: $?"
python3 -m framework.forge status --json | head -40
python3 -m framework.forge docs framework && git diff --stat   # is it reproducible?
python3 -m framework.forge bundle fresh && git diff --stat
```

If a generator produces different output than what is committed, that is a
finding: the committed artefact is stale.

Then attack it with bad input. Malformed YAML. A lyric file of one megabyte. A
filename with a newline, a semicolon, a leading dash. A `slug` containing `../`.
An empty audio file. A `--out` pointing at `/`. Record what happens, including the
cases that behave correctly.

**Work in a scratch clone or a git worktree**, so your probing cannot damage the
repository under review, and so you can distinguish your own mess from pre-existing
state.

The analysis extras (`librosa`, `faster-whisper`) are heavy and `forge analyze`
takes minutes per track. You are **not** expected to run it. Review it by reading
and say that you did.

---

## Deliverable

Write **`docs/audit-report.md`**. One file. This structure:

```markdown
# Adversarial audit — <date>

## Verdict
Three to five sentences. What is the state of this thing, and what is the single
most important thing to fix. No hedging.

## What I checked
Concrete. Commands run, files read, inputs tried. Include what behaved correctly —
a reviewer who reports only failures cannot be calibrated.

## What I did not check
And why. Be specific.

## Findings
One block each, ordered by severity across all three scopes together.

### F1 — <one-line summary>
- **Scope**: security | code | docs
- **Severity**: critical | high | medium | low
- **Confidence**: CONFIRMED | PLAUSIBLE
- **Location**: `path/file.py:120-135`
- **Failure scenario**: specific inputs or state -> specific wrong outcome
- **Evidence**: the command and its output, or the code path traced
- **Fix**: what you would change, concretely

## Decisions I want to challenge
Separate from findings. The project makes several deliberate choices with stated
reasoning — committing ~110 MB of audio masters to git, duplicating agent
instruction files across four platforms, keeping a documented-unreliable key
detector, storing the ledger as YAML rather than a database.

These are decisions, not defects, and the reasoning is written down in the module
docstrings and commit messages. **Read the stated reasoning, then challenge it if
it is weak.** Do not simply flag the choice as though nobody had considered it,
and do not accept it because it is documented. Say what the reasoning gets wrong
and what the consequence will be.

## Calibration
What would make you change your verdict? What is the weakest part of your own
audit?
```

Severity means consequence, not effort:
- **critical** — data loss, credential exposure, or silently wrong output the
  operator would act on
- **high** — a real defect that will bite, or a doc claim that is false
- **medium** — a defect requiring unusual conditions, or a maintainability trap
- **low** — real but minor

Do not soften. The author's stated preference is to be told plainly what is broken.
A report that flatters this codebase has failed its only job.
