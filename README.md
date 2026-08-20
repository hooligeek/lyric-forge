# lyric-forge

A framework for running a virtual record label as a real system: personas with
fixed rhetorical positions, thematic matrices that resist repetition, a checkable
track ledger, and audio analysis that finds the moments where the synthesiser
broke so they can be documented instead of regenerated away.

Built for [Suno](https://suno.com) output and NotebookLM-hosted band notebooks,
but nothing in `framework/` knows about a specific label.

## Two tiers

The system is designed so the interesting half needs no backend at all.

### Tier 1 — Notebook only

Bring **a vision and a demo song**. Drop the compiled document set into a
NotebookLM notebook and Gemini does everything that is a language or listening
judgement: derive the band persona and narrator dossier, build the thematic
suites and lexicons, generate lyrics, compile the lyric sheet, run the six-gate
self-audit, and write a perceptual glitch log.

Two rules make this tier honest, because a model grading its own homework will
otherwise pass itself every time:

- **No timecodes.** A notebook hears words, not waveforms — it cannot measure,
  so any timestamp it emits is invented. Glitches are anchored to
  *section + lyric phrase* ("Verse 2, on the word *substance*"), which is
  verifiable from the transcript and more useful in a lyric sheet anyway.
- **Evidence or abstain.** Every audit verdict must quote the literal thing it
  checked. "Cannot locate" is a distinct verdict from "pass".

### Tier 2 — Notebook + forge

Adds measured truth: real timecodes, clipping detection, tempo-drift curves, key
verification, section-count reconciliation, word-level transcript diffs against
intended lyrics, burned-phrase mining across the whole catalogue, and variety
gates. The forge then writes its findings back into the compiled notebook bundle,
so a Tier 2 notebook is *better informed* than a Tier 1 one — its matrices carry
real usage counts and real burned lists instead of the model's impressions.

Same document formats in both tiers. Upgrading is additive; nothing is rebuilt.

## Layout

```
framework/          generic — lift this into any label project untouched
  forge/            the Python toolchain
  schema/           JSON Schema for bands and tracks
  prompts/          the five prompts (derive, generate, compile, audit, harvest)
  templates/        band kit and lyric sheet templates
  docs/             per-tier setup guides
label/              the instance — one label's bands, matrices, ledger, lyrics
  label.yaml        roster, audio root, era definitions
  substrate.md      the shared biography the personas all draw from
  bands/<slug>/     band.yaml, matrix.yaml, retired.yaml, tracks.yaml, lyrics/
```

Audio is never committed. The Suno mp3s are the archival source of truth and live
outside the repo (`audio_root` in `label.yaml`); decoded PCM is a disposable cache
under `.cache/`.

## Quickstart

```bash
python3 -m framework.forge probe        # audio facts table
python3 -m framework.forge bootstrap    # seed ledgers from audio on disk
python3 -m framework.forge reconcile    # audio <-> ledger <-> lyric sheets
python3 -m framework.forge decode --band warhead --kind both
python3 -m framework.forge import-lyrics --band warhead --source context_harvest
python3 -m framework.forge mine --band silicon-kings --write
```

`bootstrap` is idempotent: it only adds entries for audio it has not seen, so
hand-enrichment survives re-runs. `import-lyrics` defaults to a dry run — pass
`--write` once the parse looks right.

## Importing from notebook harvests

Harvest documents arrive in whatever shape a notebook produced: `#### TRACK 01:
TITLE`, `Track 5: Title`, escaped `\#\#\# 1\. Title`, or a ruler-delimited dump
with every section flattened onto one line. Rather than a parser per dialect,
the importer segments on the invariant that holds across all of them: a song is
a run of bracketed section cues, preceded by its title.

Two things that dialect-specific parsers get wrong and this one handles:

- **Section cues do not lead with their keyword.** The real material says
  `[Dense Verse 1 | ...]`, `[Grievance-Driven Chorus | ...]`,
  `[Meltdown Bridge | ...]`. Anchoring the keyword to the start of the bracket
  silently drops most of a song — and the loss is invisible, because what
  survives still parses.
- **Songs bleed into each other.** Most sheets end on `[Outro]`, not `[End]`, so
  the next track's seal, metadata block, and sonic blueprint land inside the
  previous song's outro — and then show up in repetition mining as fake shared
  phrases like *"bpm g major suno style prompt roots reggae"*. Markdown headings
  and horizontal rules therefore close the current section and suspend capture
  until the next cue.

Matching parsed songs to ledger entries is deliberately fuzzy in one direction
only. `Systemic Obsolescence One.mp3` is
`Systemic Obsolescence (Pt. 1: The Infrastructure Grievance)` — a filename
convention, matched at 0.95. But `Local Sentinel` is not `Under My Own Metal`,
and the importer reports that as unmatched rather than guessing.

## Repetition mining

`forge mine` finds phrases a band has already spent. The premise is that
"functional equilibrium" is not running out of *words* but out of *structural
moves* — a model handed a bag of vocabulary reuses the same handful forever,
because those scan and rhyme easiest.

Repetition *within* a song is a chorus and is wanted. Repetition *across* songs
is the failure mode, so everything counts distinct songs rather than raw
occurrences. Alongside phrases it reports **shared section openings**, which
catch syntactic ruts that vocabulary checks miss entirely — three Silicon Kings
bridges opening on *"A deep lack of ..."* is a tic, not a shared word.

Output is triage, not verdict. Everything lands in `candidates` in the band's
`retired.yaml`, and the operator promotes each entry to either `canonical_hooks`
(deliberate — brand slogans, recurring motifs) or `burned` (spent, never again).
Only a human knows which is which: *"the machine is a vessel, but the man is the
soul"* recurring across two songs is the label axiom working as intended, while
*"get out of the way"* closing three of six songs is a rut.

Stage directions are excluded from the corpus. A line wholly wrapped in
parentheses — `(Spoken)`, `(Grinding Lemmy-esque bass solo ripping through the
mix)` — belongs in the sheet, because it goes into Suno's lyric box, but nobody
sings it. Counting them made two Warhead songs look like they shared a phrase
when what they shared was an outro instruction. The same exclusion matters more
for the transcript diff, where a stage direction would read as a divergence.

### Cross-band mining

```bash
python3 -m framework.forge mine --label
```

When the roster premise is "several facets of one person" rather than several
unrelated acts, the more dangerous repetition is *between* bands, and per-band
mining is structurally blind to it. One band repeating itself has a motif; two
bands sharing phrasing is the roster collapsing into a single voice.

Deliberate label-wide axioms surface here too, and that is correct — the
operator should confirm they are intentional rather than have the tool guess.

## Why the ledger is data and not prose

The predecessor of this system kept its metadata ledger inside notebook
documents, as prose. Prose ledgers cannot be checked. An audit run against one
reported `PASS` for four files, three of which did not exist — the model had no
way to tell the difference between verifying a file and describing one. A YAML
file either has a field or it does not, and `forge reconcile` walks the actual
filesystem.

## On mp3 versus WAV

Converting Suno's mp3 exports to WAV recovers no quality — lossy artefacts are
baked in at encode time. The forge decodes to WAV anyway, for a different reason:
**timestamp alignment**. Every analysis library brings its own mp3 decoder, and
mp3's encoder delay and padding are handled inconsistently, so the same event can
land tens of milliseconds apart depending on which tool read the file. Since the
entire point is cross-referencing acoustic events against lyric events, all tools
must read one canonical decode. The 16 kHz mono ASR derivative is resampled from
the 48 kHz decode rather than from the mp3, for the same reason.

What mp3 actually costs, at Suno's ~190 kbps VBR / 48 kHz:

| Analysis | Impact |
| --- | --- |
| Beat tracking / tempo drift | none |
| Key and chroma estimation | none |
| Transcription and lyric diff | none |
| Spectral comparison *within* a catalogue | none — the encoder skew is uniform |
| Absolute spectral thresholds | unusable; mp3 lowpasses around 19–20 kHz |
| True-peak clipping detection | degraded; decode overshoot causes false positives |

Only clipping detection genuinely suffers, and it is the least important of the
set — perceptually significant overdrive also shows up as lyric divergence or
dropout. Paying for lossless exports buys forensic-grade clipping evidence and
nothing else.

## The matrix: two axes, not one

A lyrical matrix constrains *vocabulary*. It does not constrain *syntax*, and
syntax is where sameness actually lives. Screen-Lit Panic has four thematic
suites and six songs, and all six are the same speech act: second-person
accusation. The topic rotates; the posture never does. Silicon Kings opens three
separate bridges on "A deep lack of ___" — not a vocabulary problem, and no
lexicon check will ever catch it.

So every song draws two independent things:

- a **suite** — what it is about (`label/bands/<slug>/band.yaml`)
- a **stance** — how it is spoken (`label/stances.yaml`)

Eleven stances against four or five suites gives 44+ distinct premises per band
instead of four, and the stance is what changes the sentences rather than just
the nouns. Measured baseline across the existing catalogue: **65% of classified
tracks are one stance, and 7 of 11 stances have never been used at all.**

### Narrator dossiers

Each band carries a `dossier.md` fixing who speaks, from where, at what hour, to
whom, what they want, and what they cannot admit. A fixed speaker generates
consistent diction automatically — it does more for voice consistency than any
word list, because word choice follows from position.

The acts are differentiated by **room, hour, and addressee**, which are concrete
and checkable, rather than by adjectives. Four of the five are alone; only one
has a crowd in the room, and that is why only one can be patient.

### The shared substrate

`label/substrate.md` holds the biography every act draws on. When the roster
premise is "several facets of one person," consistency stops depending on
remembering invented lore and starts depending on one set of real facts read
several ways — which is far more robust, and lets one event be written five times
without repetition.

It also records what each facet *cannot admit*, which turns out to be the most
valuable unwritten material on a roster: the only things the speaker is actually
hiding.

### Register: aiming the glitch

Each `band.yaml` carries a measured `register` block — the tempo ceiling and the
lexical classes that break this particular voice, with the evidence. Screen-Lit
Panic froze outright at 200 BPM and slurs consonant clusters at 170. Silicon
Kings has no tempo failures at all but chokes reliably on Latinate compounds
("anthropogenic drought" became "the edge of Virginia").

That converts the Glitch Axiom from post-hoc rationalisation into a compositional
tool: if you know where the voice breaks, hard words become *placeable*. Put the
compound where the choke is the point. And it surfaces opportunities that were
invisible before — Roots Futuria at 85 BPM is the most stable voice on the
roster and could deliver, cleanly, the exact academic vocabulary that destroys
Silicon Kings.

## The analyzer

```bash
python3 -m framework.forge analyze --band warhead --write
tail -f .cache/analyze.log
```

Four passes: DSP (clipping, loudness, dropouts), rhythm (tempo + local drift),
tonal (key), and ASR (faster-whisper `large-v3`, word-aligned diff against the
lyric sheet). Requires the venv — see `pyproject`/`.venv`. CUDA is used when
available; the NVIDIA runtime libraries are preloaded by absolute path because
CTranslate2 links cuBLAS at *inference* time, so a model will build happily on
CUDA and then die mid-decode with `libcublas.so.12 not found`.

Everything emits **candidates, never verdicts**, into
`label/bands/<slug>/glitch-candidates.yaml`. The Glitch Axiom is a human
judgement about which failures are badges of honour; automating it would gut the
idea. Promote entries into a track's `glitch_log` by hand.

### What it will and will not tell you

Four things it measures reliably:

- **Tempo**, when seeded. Unseeded beat tracking is useless on this material —
  Confident Ignorance at a declared 170 tracked to 112, neither 170 nor its half.
  Seeding from the track's declared BPM (or the band nominal) fixes it. When the
  grid does not lock, drift candidates are **suppressed entirely** rather than
  reported, because on a mis-locked grid every inter-beat interval looks like
  drift and reporting that would recreate the invented-timecode problem this
  module exists to eliminate.
- **Transcript divergence with real timecodes**, which is the point.
- **Clipping and dropouts**, with an mp3 caveat on the former.
- **Whether a sheet matches its master**, which turned out to matter more than
  glitch detection.

One thing it does **not** measure reliably: **key**. The chroma detector agreed
with the declared key on 1 of the 4 Roots Futuria tracks, despite all four
sharing one style prompt and one declared key — it most likely locks to the
dominant rather than the tonic on a bass-heavy mix. Treat `detected_key` as
unusable evidence until it is replaced with something that separates the bassline.

### Two failure modes, not one

Low word accuracy has two completely different causes, and conflating them would
make the tool report correct sheets as wrong purely because a vocal is fast.
Transcript **coverage** discriminates:

| | accuracy | coverage | verdict |
| --- | --- | --- | --- |
| Lazy | 0.12 | 0.59 | `asr-unreliable` — heard 130 words of 221 and returned word salad |
| Deterministic Drift | 0.36 | 1.18 | `sheet-mismatch` — heard plenty, heard coherent rhyming couplets absent from the sheet |

Coverage only *proxies* coherence, so results near the threshold carry a
`-borderline` suffix and need an ear rather than a number.

## Cover art

```bash
python3 -m framework.forge artwork --write
```

Art is the third per-track asset alongside audio and lyrics, matched to the
ledger by slugified filename (filenames in the wild carry trailing spaces, so
they are stripped first). Decoding goes through ffmpeg rather than Pillow —
already a hard requirement for the audio pipeline, and both checks below are
one-line filter graphs.

### Two hashes, because one asks the wrong question

These covers are template-built: a fixed band-name plate, a shared background
treatment, a fixed border, a title stamp in the same corner. A whole-frame
perceptual hash is dominated by that furniture. It reported Screen-Lit Panic's
*MINE!* and *Take the L* as the same picture at distance 8 — when one is a pair
of hands clutching pearls and the other is a reel-to-reel deck. False positive
for duplication; true positive for a shared template, which is the art direction
working rather than a defect.

So there are two measurements:

- **full frame** → template consistency, reported as a separate, non-alarming
  category.
- **centre crop** (excluding the plate and the stamp) → whether the *subject art*
  actually repeats. This is the one that matters.

Validated both ways against the catalogue: the retuned check separates the
Screen-Lit Panic template pairs correctly, and catches that three of four Roots
Futuria covers are one beach photograph re-titled — identical sunset, guitar,
angle and leaf, at centre distances of 1, 2 and 3.

Exact `sha256` matches are reported distinctly, since a byte-identical file is a
different problem from a re-render.

### Palette

Coarse quantisation to dominant colours with shares — enough to check a declared
palette, not enough to argue about. It found that Screen-Lit Panic's declared
"blood-red splatters" appear nowhere in its actual art (measured white,
near-black, green) and that Warhead's declared amber/orange is really a dark red.

## The variety gate

```bash
python3 -m framework.forge variety
```

The predecessor audit had six gates and all six measured *format* — seal present,
cues pipe-stacked, ledger tidy. Format compliance is trivially satisfiable, which
is why it returned PASS on a catalogue where four tracks shared a BPM, a key, and
a byte-identical sonic blueprint. A label whose declared enemy is homogenisation
had an auditor that could not detect homogenisation.

This measures distribution instead: stance, suite, tempo, key, and style-prompt
concentration. Era-aware — pre-standard tracks are counted for evidence but never
failed.

## Era tagging

A label whose founding axiom is *leave the glitch in the mix* does not sanitise
its own back catalogue. Tracks written before the standards existed are tagged
`era: pre-standard` and exempted from the matrix, stance, lexicon, and variety
gates. They still get lyric sheets and glitch logs. Their repetitions are not a
compliance failure — they are the corpus the burned-phrase lists are mined from.
