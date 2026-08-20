"""Compile NotebookLM bundles — the tier that needs no backend at all.

Two bundles, because there are two audiences.

`fresh` is a starter kit: someone arriving with a vision and a demo song and no
label. It contains the standards, the stance taxonomy, the prompt library and
detailed instructions, and nothing label-specific. This one is committed to the
repo, because its entire audience is people who cannot run the forge — generating
it on demand would put a Python dependency in front of the no-backend tier.

`export` is an existing project compiled for notebooks: one bundle per band plus a
thin label bundle. Regenerable, so it is gitignored.

Three rules carried in from what the analysis actually showed.

The catalogue digest lists titles, stances, suites and spent phrases and NEVER
full lyrics. A notebook with its own back catalogue in the sources retrieves its
own previous choruses, and echoing them becomes the path of least resistance. The
negative space is the useful part.

Prompts are rendered to REFERENCE the sources rather than to inline them. In an
API call the dossier is substituted into the prompt text; in a notebook the
dossier is a source and the prompt points at it. Same template, different fill —
which is the claim the prompt library exists to make good on.

No timecodes and evidence-or-abstain, restated in every bundle. A notebook hears
words, not waveforms; anything it emits as a timestamp is invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import config as config_mod
from . import context as context_mod
from . import prompts as prompts_mod
from . import variety as variety_mod
from .config import Config

DIST = config_mod.REPO_ROOT / "dist"
FRESH_DIR = config_mod.REPO_ROOT / "bundles" / "fresh-spark"

# Slots that are label or band content. In a notebook these live as their own
# source files, so the prompt points at them instead of carrying a copy.
SOURCE_REFS = {
    "substrate": "See **02-substrate.md** in this notebook's sources.",
    "dossier": "See **03-dossier.md** in this notebook's sources.",
    "catalogue_digest": "See **06-catalogue-digest.md** in this notebook's sources.",
    "register": "See **05-register.md** in this notebook's sources.",
    "avoid": "See **07-spent-phrases.md** in this notebook's sources. Treat every "
             "entry there as unavailable.",
    "canon_rules": "See the canon rules in **04-matrix.md**.",
    "constraints": "See **04-matrix.md** and **07-spent-phrases.md**.",
    "song_map": "See the section map in **04-matrix.md**, if one is defined.",
    "stance_roster": "See **08-stances.md** in this notebook's sources.",
}

FRESH_REFS = {
    "substrate": "You have no shared biography yet. If you want one, write it "
                 "after the band exists — it is optional for a single act.",
    "dossier": "Derive this first with **03-prompt-derive-band.md**, then add the "
               "result to this notebook as a source.",
    "catalogue_digest": "Nothing released yet. Nothing is spent.",
    "register": "UNMEASURED. A register can only be filled after you have audio "
                "and have listened to where the voice actually breaks. Do not "
                "invent a tempo ceiling.",
    "avoid": "Nothing spent yet. Start a list the first time you notice a phrase "
             "recurring.",
    "canon_rules": "See the canon rules in your derived band definition.",
    "constraints": "See your derived band definition.",
    "song_map": "See your derived band definition, if you defined one.",
    "stance_roster": "See **02-stances.md** in this notebook's sources.",
}

HONESTY = """\
# Honesty rules for a notebook

A notebook can read and it can listen. It cannot measure. These rules exist
because the difference is invisible in the output unless you insist on it.

## Never emit a timecode

You have no access to sample peaks or beat intervals, so any timestamp you
produce is invented. It will look exactly like a real one.

Anchor every observation to **section plus lyric phrase** instead:

    Verse 2, on the word "substance"

That is verifiable from the transcript, and it is more useful in a lyric sheet
than a timestamp anyway.

## Evidence or abstain

When auditing, quote the literal thing you checked — the actual cue string, the
actual line, the actual phrase. A verdict without a quotation is an impression.

**"Cannot locate" is a distinct verdict from "pass."** Conflating them is the
single failure mode that makes an audit worthless: a previous version of this
system returned PASS on four files, three of which did not exist.

## Do not write a glitch log before the audio exists

Synthesis anomalies are observed after a render, never predicted. A glitch log
written in advance is fabricated evidence.

## Say when you are guessing

If the sources do not determine something, say so and name what is missing.
Filling a gap with a plausible invention is worse than leaving it empty, because
nobody can tell afterwards which parts to trust.
"""

STANDARDS = """\
# Production standards

## The tag stacking formula

Every section cue carries pipe-separated attributes:

    [Section | Genre/Era | Vocal Texture | Production Vibe]

- The vertical pipe separates attributes. Always.
- Maximum **six** attributes per bracket. Past that the synthesiser starts
  ignoring them.
- No bare cues. `[Verse]` and `[Chorus]` are formatting defects.
- Section names may carry a modifier — `[Dense Verse 1 | ...]`,
  `[Anthemic Chorus | ...]` — and often should.
- Never mix conflicting attributes unless the fusion is deliberate.

## Stage directions

A line that is a performance note rather than something sung goes in
parentheses: `(Spoken)`, `(Grinding bass solo ripping through the mix)`.

They belong in the sheet, because the synthesiser reads them. The parentheses are
load-bearing: they are how the line gets excluded when a transcript is compared
against the intended lyrics.

## The lyric sheet

1. Frontmatter — band, title, slug, era
2. Production — suite, stance, declared BPM, style prompt
3. Sonic blueprint — two sentences, **written for this song**. A blueprint copied
   unchanged across a catalogue is how four tracks end up identical.
4. The lyric body, every section pipe-stacked
5. Glitch log — empty until there is audio

## The Glitch Axiom

When the synthesiser chokes, slurs or distorts, **do not regenerate**. Log it,
name it under the act's own protocol, and leave it in the mix.

The reasoning is not sentimental. Punk did not overcome the limitations of cheap
four-track recording; it made them the sound. A synthesis artefact is the same
material a generation later.

Two things follow that are easy to miss:

- Knowing *where* a voice breaks makes hard words **placeable**. Put the
  polysyllable where a slur reads as emphasis, and never on a word the whole line
  depends on.
- Which failures are badges of honour is a **human** judgement. A tool can find
  them; it must not decide.

## The two axes

A song draws two independent things:

- a **suite** — what it is about
- a **stance** — how it is spoken

Vocabulary lists constrain the first and do nothing for the second, which is
where sameness actually lives. Four thematic suites will happily produce four
songs in one speech act: same posture, rotating topic. Hold the stance.
"""


@dataclass
class BundleFile:
    name: str
    content: str


@dataclass
class Bundle:
    kind: str
    label: str
    notebooks: dict[str, list[BundleFile]] = field(default_factory=dict)

    def write(self, root: Path) -> dict[str, Any]:
        written: dict[str, list[str]] = {}
        for notebook, files in self.notebooks.items():
            target = root / notebook if notebook else root
            target.mkdir(parents=True, exist_ok=True)
            for f in files:
                (target / f.name).write_text(f.content, encoding="utf-8")
            written[notebook or "."] = [f.name for f in files]
        return {
            "kind": self.kind,
            "label": self.label,
            "root": str(root),
            "notebooks": written,
            "file_count": sum(len(v) for v in written.values()),
        }


def _render_for_notebook(prompt_id: str, refs: dict[str, str]) -> str:
    """Render a template with source references in place of inlined content."""
    prompt = prompts_mod.load(prompt_id)
    ctx: dict[str, Any] = {}
    for slot in prompt.declared_slots():
        if slot in refs:
            ctx[slot] = refs[slot]
        else:
            ctx[slot] = f"_(supply this, or see your band definition)_"
    # Filenames differ between bundles — the fresh kit numbers the stance roster
    # 02, the export bundle 08 — so the reference has to come from the ref map
    # rather than being hardcoded, or half the cross-references dangle.
    ctx["tag_formula"] = (
        "[Section | Genre/Era | Vocal Texture | Production Vibe] — see "
        "**01-standards.md**."
    )
    ctx["stance_roster"] = refs.get(
        "stance_roster", "See the stance roster in this notebook's sources."
    )
    rendered = prompts_mod.render(prompt, ctx)
    header = (
        f"# Prompt: {prompt.title}\n\n"
        f"`{prompt.ref}` — paste everything below the line into the notebook chat.\n"
        f"It refers to other sources by name; make sure they are all uploaded.\n\n"
        f"---\n\n"
    )
    return header + rendered.text


def _stances_doc() -> str:
    roster = context_mod.stance_roster()
    lines = [
        "# The stance roster",
        "",
        "A song's **stance** is how it is spoken, independent of what it is about.",
        "This is the axis that vocabulary lists cannot constrain, and it is where",
        "sameness accumulates: a catalogue can rotate its topics for years while",
        "every song remains the same speech act.",
        "",
        "**Rule: a stance may not repeat until at least two others have been used.**",
        "",
    ]
    for s in roster.get("stances", []):
        lines.append(f"## {s.get('name', s['id'])}  (`{s['id']}`)")
        lines.append("")
        lines.append(str(s.get("description", "")).strip())
        if s.get("marker"):
            lines.append("")
            lines.append(f"*Syntactic marker:* {s['marker']}")
        if s.get("example"):
            lines.append("")
            lines.append(f'*Example:* "{s["example"]}"')
        if s.get("caution"):
            lines.append("")
            lines.append(f"*Caution:* {str(s['caution']).strip()}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# fresh bundle
# ---------------------------------------------------------------------------
FRESH_START = """\
# Start here

This is a starter kit for building a virtual band and writing songs for it, using
nothing but a notebook. No install, no code, no command line.

## What you need

1. **A notebook with an AI assistant that can read uploaded files.** These
   instructions were written for **Google NotebookLM** (free, notebooklm.google.com),
   which is where the "upload these as sources" wording comes from. Anything that
   can hold a dozen documents in context and answer against them will work.
2. **A music generator that accepts a lyrics box and a style prompt.** These
   instructions assume **Suno** (suno.com), because the section-cue format below
   is written for how Suno reads bracketed tags. Another generator will work but
   you may have to adapt the cue syntax.
3. **A vision.** However messy. A genre, a grievance, an image, an argument you
   had. It does not need to be tidy — the tidying is step 2.
4. **A demo song** (optional but useful). Any render, even a bad one. It tells you
   what your style prompt actually produces.

Both services have free tiers at the time of writing. Neither is required by the
*method* — the standards, the stances and the prompts are generator-agnostic —
but the wording below names them because vague instructions are useless.

## What to upload

Put every file in this folder into one notebook as sources. All of them. They
refer to each other by filename, so a missing one leaves a hole.

## The order to work in

### 1. Derive your band

Paste **03-prompt-derive-band.md** into the chat, with your vision.

You get back a band definition and a narrator dossier. Read them properly. The
dossier is the part that matters most — it fixes *who is speaking, from where, at
what hour, to whom*, and diction follows from position far more reliably than from
any word list.

**Save both as new sources in this notebook.** Everything after this depends on
them being there.

Expect to be asked questions rather than given a complete answer. A definition
made of adjectives produces songs made of adjectives, so the prompt is written to
push back on vagueness instead of filling gaps with invention.

### 2. Write a song

Paste **04-prompt-generate-song.md**. Choose:

- a **suite** — one of the thematic collisions in your definition
- a **stance** — from **02-stances.md**

Pick a stance you have not used. This is the single highest-value discipline in
the kit and the easiest to skip: one posture is easier to write than the others,
so without a deliberate choice a catalogue converges on it. A real example from
the project this kit came from — six songs, four thematic suites, and every one of
them was second-person accusation.

### 3. Review it

Paste **05-prompt-review-lyrics.md** with the lyrics and any direction for this
particular pass ("make it colder", "no second person", "must scan at 180").

Findings come back in two classes, and the split matters: **mechanical** findings
cite a rule, **judgement** findings quote the line they are about. Anything that
cannot be assessed says so rather than passing quietly.

### 4. Compile the sheet

Paste **06-prompt-compile-sheet.md**. This is formatting, not editing — it must
not change a word.

### 5. Render, then listen

Take the sheet to your generator. Then **listen for the failures** and log them.

Read **01-standards.md** on this before deciding a bad take is a
bad take. When the synthesiser chokes, that is material, not an error — but
whether a particular failure is worth keeping is your call and nobody else's.

### 6. Keep a spent list

The first time you notice a phrase recurring, write it down in a source file. That
list is the single most useful thing you will build, and it only works if you
start it early. Repetition inside one song is a chorus; repetition across songs is
a rut, and you will not notice it by memory.

## What this kit deliberately does not do

It does not measure. A notebook can read and it can listen; it cannot inspect a
waveform. **07-honesty-rules.md** covers what follows from that — the short
version is that any timecode a notebook produces is invented, so anchor
observations to section and phrase instead.

If you later want real measurement — tempo verification, clipping detection,
transcript-versus-sheet diffing with actual timestamps — that needs the toolchain
this kit was generated from. The document formats are identical, so nothing has to
be rebuilt when you upgrade.
"""


def build_fresh() -> Bundle:
    b = Bundle(kind="fresh", label="(none)")
    # One standards file. It already contains the Glitch Axiom section, and
    # shipping the same bytes twice under two names wastes a notebook source slot
    # and splits retrieval across identical documents.
    files = [
        BundleFile("00-START-HERE.md", FRESH_START),
        BundleFile("01-standards.md", STANDARDS),
        BundleFile("02-stances.md", _stances_doc()),
    ]
    for num, pid in (
        ("03", "derive-band"),
        ("04", "generate-song"),
        ("05", "review-lyrics"),
        ("06", "compile-sheet"),
    ):
        files.append(
            BundleFile(f"{num}-prompt-{pid}.md", _render_for_notebook(pid, FRESH_REFS))
        )
    files.append(BundleFile("07-honesty-rules.md", HONESTY))
    b.notebooks[""] = sorted(files, key=lambda f: f.name)
    return b


# ---------------------------------------------------------------------------
# export bundle
# ---------------------------------------------------------------------------
def _band_start(cfg: Config, slug: str, spec: dict) -> str:
    bblock = spec.get("band") or {}
    return f"""\
# Start here — {bblock.get('name', slug)} notebook

This notebook is **one act**. Keep it that way. Putting several acts in one
notebook blends their voices, which is the exact failure the roster is built to
avoid — retrieval does not respect the boundary you had in mind.

Act: **{bblock.get('name', slug)}** — {bblock.get('role', '')}
Position: *{bblock.get('disagreement', '')}*

## Upload every file in this folder as a source

They refer to each other by filename.

| File | What it is |
| --- | --- |
| 01-standards.md | Formats, the tag formula, the Glitch Axiom |
| 02-substrate.md | The shared life every act on the label draws on |
| 03-dossier.md | Who is speaking. The most important file here. |
| 04-matrix.md | Suites, lexicons, canon rules |
| 05-register.md | What this voice can physically deliver |
| 06-catalogue-digest.md | What is already released and what is spent |
| 07-spent-phrases.md | Phrases that may not be reused |
| 08-stances.md | The eleven ways a song can be spoken |
| 09..-prompt-*.md | The prompt library |
| 99-honesty-rules.md | What a notebook must not claim to know |

## Writing a song

1. Read **06-catalogue-digest.md** and pick a stance this act has *not* used, and
   its least-mined suite.
2. Paste **09-prompt-generate-song.md**, naming your suite and stance.
3. Review with **10-prompt-review-lyrics.md**.
4. Compile with **11-prompt-compile-sheet.md**.
5. Render, then listen for failures and log them under this act's glitch protocol.

## Two things this notebook cannot do

It cannot measure, so it must not emit timecodes — see **99-honesty-rules.md**.

It does not hold the full back catalogue. **06-catalogue-digest.md** lists what
exists and what is spent, deliberately without the lyrics: a notebook holding its
own previous choruses retrieves them, and echoing them becomes the easiest thing
to do. What is used up is the useful information.
"""


def _matrix_doc(slug: str, spec: dict) -> str:
    bblock = spec.get("band") or {}
    lines = [f"# {bblock.get('name', slug)} — thematic matrix", ""]
    if bblock.get("facet_note"):
        lines += [str(bblock["facet_note"]).strip(), ""]

    sonic = spec.get("sonic") or {}
    lines += ["## Sound", ""]
    for k in ("genre", "style_prompt", "bpm_nominal", "bpm_range", "vocal"):
        if sonic.get(k):
            lines.append(f"- **{k}**: {str(sonic[k]).strip()}")
    if sonic.get("song_map"):
        lines += ["", "### Section map", ""]
        lines += [f"{i}. {s}" for i, s in enumerate(sonic["song_map"], 1)]

    gp = spec.get("glitch_protocol") or {}
    if gp:
        lines += ["", "## Glitch protocol", "",
                  f"**{gp.get('name','')}** — {str(gp.get('reading','')).strip()}"]

    lines += ["", "## Suites", "",
              "Each suite is a *collision* between a domain and a subcultural image,",
              "not a topic heading. At least one anchor must appear in any song using it.",
              ""]
    for sid, s in (spec.get("suites") or {}).items():
        lines.append(f"### Suite {sid} — {s.get('name','')}")
        lines.append("")
        for label, key in (
            ("Domain", "domain"), ("Tension", "tension"),
            ("Punk metaphor", "punk_metaphor"), ("Physical image", "juxtaposition"),
        ):
            if s.get(key):
                lines.append(f"*{label}:* {str(s[key]).strip()}")
                lines.append("")
        if s.get("anchors"):
            lines.append(f"*Anchors (one required):* {', '.join(s['anchors'])}")
            lines.append("")
        if s.get("rotation"):
            lines.append(f"*Rotation:* {', '.join(s['rotation'])}")
            lines.append("")
        if s.get("stance_fit"):
            lines.append(f"*Stances that suit it:* {', '.join(s['stance_fit'])}")
            lines.append("")
        if s.get("priority"):
            lines.append(f"**Priority suite.** {str(s.get('priority_reason','')).strip()}")
            lines.append("")

    if spec.get("canon_rules"):
        lines += ["## Canon rules", ""]
        lines += [f"- {r}" for r in spec["canon_rules"]]
    return "\n".join(lines)


def _register_doc(slug: str, spec: dict) -> str:
    reg = spec.get("register") or {}
    body = context_mod._register_block(spec)
    lines = [
        f"# {slug} — register",
        "",
        "What this voice can and cannot physically deliver. **Measured from real",
        "audio**, not guessed — where it says unmeasured, it is genuinely unknown",
        "and must not be filled in with a plausible number.",
        "",
    ]
    if not body:
        lines.append("UNMEASURED. No audio has been analysed for this act yet.")
        return "\n".join(lines)
    lines.append(body)
    lines += [
        "",
        "## How to use it",
        "",
        "This is a compositional instrument, not a warning list. If you know where",
        "a voice breaks, a hard word becomes *placeable*: put the polysyllable",
        "where a slur reads as emphasis, and never on a word the line depends on.",
        "",
        "A real example from this catalogue: a track lost the word *faders* to a",
        "slur, and the line lost its meaning with it. Another lost *analog* — the",
        "word its own song was named after. Both were placement decisions nobody",
        "made.",
    ]
    return "\n".join(lines)


def _spent_doc(slug: str, retired: dict) -> str:
    lines = [
        f"# {slug} — spent phrases",
        "",
        "Repetition inside one song is a chorus. Repetition across songs is a rut.",
        "Everything below has been used; the burned list may not be reused at all.",
        "",
    ]
    canonical = retired.get("canonical_hooks") or []
    burned = retired.get("burned") or []
    candidates = retired.get("candidates") or []
    tics = retired.get("opening_tics") or []

    lines += ["## Canonical — deliberate repetition, allowed", ""]
    lines += [f'- "{p}"' for p in canonical] or ["_(none marked yet)_"]
    lines += ["", "## Burned — do not reuse, and do not paraphrase closely", ""]
    lines += [f'- "{p}"' for p in burned] or ["_(none marked yet)_"]

    if candidates:
        lines += [
            "", "## Untriaged — appears more than once, not yet decided", "",
            "These have not been sorted into canonical or burned. Treat them as",
            "unavailable unless you are deliberately making one a recurring motif.",
            "",
        ]
        lines += [f'- "{c.get("phrase")}"' for c in candidates[:40]]

    if tics:
        lines += [
            "", "## Opening tics — no section may open this way again", "",
            "A shared opening is a syntactic rut, and it reads worse than a shared",
            "noun because it shapes the whole sentence.",
            "",
        ]
        lines += [f'- "{t.get("opening")} ..."' for t in tics]
    return "\n".join(lines)


def _label_notebook(cfg: Config) -> list[BundleFile]:
    label = context_mod.label_spec()
    lblock = label.get("label") or {}
    results, summary = variety_mod.run(cfg)

    roster_lines = [
        "# The roster",
        "",
        "The acts do not share a position. They share a life and argue about what",
        "it means, and that disagreement has to be audible — a roster where every",
        "act would agree with every line is one opinion in several accents.",
        "",
    ]
    for slug in cfg.bands:
        spec = context_mod.band_spec(cfg, slug)
        b = spec.get("band") or {}
        roster_lines += [
            f"## {b.get('name', slug)} — {b.get('role','')}",
            "",
            f"*Position:* {b.get('disagreement','')}",
            "",
        ]
        if b.get("facet_note"):
            roster_lines += [str(b["facet_note"]).strip(), ""]

    dist = summary.get("label_stances") or {}
    total = sum(dist.values()) or 1
    variety_lines = [
        "# Where the catalogue is thin",
        "",
        "Computed from the ledger, not remembered. Use it to choose what to write",
        "next rather than defaulting to whatever comes easily.",
        "",
        "## Stance distribution",
        "",
    ]
    for stance, n in sorted(dist.items(), key=lambda kv: -kv[1]):
        variety_lines.append(f"- **{stance}** — {n} tracks ({n/total:.0%})")
    unused = summary.get("unused_stances") or []
    if unused:
        variety_lines += [
            "",
            f"## Never used ({len(unused)})",
            "",
            ", ".join(unused),
            "",
            "Each is an available song nobody on the roster has written.",
        ]
    for bv in results:
        if bv.warnings:
            variety_lines += ["", f"## {bv.slug}", ""]
            variety_lines += [f"- {w}" for w in bv.warnings]

    canonical = label.get("canonical_phrases") or []
    cross_lines = [
        "# Phrases allowed to cross acts",
        "",
        "Everything shared between two acts is the roster collapsing into one",
        "voice — except these, which are deliberate.",
        "",
    ]
    cross_lines += [f'- "{p}"' for p in canonical] or ["_(none)_"]

    start = f"""\
# Start here — label notebook

This notebook coordinates. It **deliberately does not contain any act's matrix**,
because several voices in one context blend, and that blending is the failure the
roster exists to avoid.

Label: **{lblock.get('name','')}**
Axiom: *{lblock.get('axiom','')}*

Use this notebook for what spans the roster:

- deciding which act should take an idea
- planning splits and compilations, which are arguments rather than packaging
- checking where the catalogue is thin — see **05-where-the-catalogue-is-thin.md**

Each act has its own notebook. Generation happens there.

## The strongest available format

One event, written by several acts from their different positions. It is only
possible because they share a life — see **02-substrate.md** — and it is the
clearest demonstration that the roster is more than five names.
"""
    return [
        BundleFile("00-START-HERE.md", start),
        BundleFile("01-standards.md", STANDARDS),
        BundleFile("02-substrate.md", context_mod.substrate()),
        BundleFile("03-roster.md", "\n".join(roster_lines)),
        BundleFile("04-canonical-phrases.md", "\n".join(cross_lines)),
        BundleFile("05-where-the-catalogue-is-thin.md", "\n".join(variety_lines)),
        BundleFile("99-honesty-rules.md", HONESTY),
    ]


def build_export(cfg: Config, bands: list[str] | None = None) -> Bundle:
    b = Bundle(kind="export", label=cfg.label_name)
    b.notebooks["_label"] = _label_notebook(cfg)

    for slug in bands or list(cfg.bands):
        spec = context_mod.band_spec(cfg, slug)
        retired = context_mod.retired(cfg, slug)
        files = [
            BundleFile("00-START-HERE.md", _band_start(cfg, slug, spec)),
            BundleFile("01-standards.md", STANDARDS),
            BundleFile("02-substrate.md", context_mod.substrate()),
            BundleFile("03-dossier.md", context_mod.dossier(cfg, slug)),
            BundleFile("04-matrix.md", _matrix_doc(slug, spec)),
            BundleFile("05-register.md", _register_doc(slug, spec)),
            BundleFile(
                "06-catalogue-digest.md",
                f"# {slug} — catalogue digest\n\n"
                "What exists and what is spent. **Deliberately without the lyrics:**\n"
                "a notebook holding its own previous choruses retrieves them, and\n"
                "echoing them becomes the easiest thing to do.\n\n"
                + context_mod.catalogue_digest(cfg, slug),
            ),
            BundleFile("07-spent-phrases.md", _spent_doc(slug, retired)),
            BundleFile("08-stances.md", _stances_doc()),
            BundleFile("99-honesty-rules.md", HONESTY),
        ]
        for num, pid in (
            ("09", "generate-song"),
            ("10", "review-lyrics"),
            ("11", "compile-sheet"),
        ):
            files.append(
                BundleFile(
                    f"{num}-prompt-{pid}.md", _render_for_notebook(pid, SOURCE_REFS)
                )
            )
        b.notebooks[slug] = files
    return b


def format_result(result: dict) -> str:
    lines = ["=" * 78, f"BUNDLE  {result['kind']}  ({result['label']})", "=" * 78]
    lines.append(f"root: {result['root']}")
    lines.append(f"{result['file_count']} files across {len(result['notebooks'])} notebook(s)")
    lines.append("")
    for notebook, files in result["notebooks"].items():
        lines.append(f"-- {notebook}  ({len(files)} sources)")
        for f in files:
            lines.append(f"     {f}")
    lines.append("")
    lines.append("Upload every file in a notebook folder as sources to ONE notebook.")
    lines.append("One act per notebook — several acts in one context blend their voices.")
    return "\n".join(lines)
