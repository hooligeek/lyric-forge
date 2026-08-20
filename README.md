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
```

`bootstrap` is idempotent: it only adds entries for audio it has not seen, so
hand-enrichment survives re-runs.

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

## Era tagging

A label whose founding axiom is *leave the glitch in the mix* does not sanitise
its own back catalogue. Tracks written before the standards existed are tagged
`era: pre-standard` and exempted from the matrix, stance, lexicon, and variety
gates. They still get lyric sheets and glitch logs. Their repetitions are not a
compliance failure — they are the corpus the burned-phrase lists are mined from.
