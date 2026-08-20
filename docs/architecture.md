# Architecture

## Two layers

```
framework/     generic — lift this into any label project untouched
  forge/         the Python toolchain
  prompts/       the prompt library, as data
  stances.yaml   the rhetorical stance taxonomy
label/         one label's instance
  label.yaml     roster, asset roots, eras, canonical phrases
  substrate.md   the shared biography the acts draw on
  bands/<slug>/  band.yaml, dossier.md, retired.yaml, tracks.yaml, lyrics/
  audio/         masters, committed
  artwork/       covers, committed
  sparks/        raw human input — gitignored
  briefs/        derived briefs — committed
```

The split is what makes the repo usable as a template: `framework/` knows nothing
about any particular label.

## Three runtimes, one prompt library

Inference happens three ways, and all three render the same templates:

| Runtime | Credentials | How |
| --- | --- | --- |
| **agent** | none | `forge infer --mode agent` renders; the agent in your editor acts |
| **api** | your own key, from the environment | `forge infer --mode api` |
| **notebook** | none | `forge bundle export` writes sources for NotebookLM |

If each runtime carried its own copy of the wording they would drift, and the
same brief would produce different songs depending on where it ran. The template
is the artefact; the runtime is only delivery.

The notebook rendering is the clearest demonstration: the same `generate-song`
template produces a ~17,000-character API prompt with the dossier substituted
in, and a ~4,700-character notebook prompt that says *"See 03-dossier.md in this
notebook's sources."*

## The data model

`label/bands/<slug>/tracks.yaml` is the spine. One entry per song, carrying:

- **identity** — id, title, slug, band, era
- **assets** — audio and artwork paths plus their `sha256`
- **brief** — matrix suite, rhetorical stance
- **suno** — style prompt, declared BPM and key, song id and url
- **measurement** — `measured_bpm`, the full `analysis` block
- **glitch_log** — adjudicated anomalies with verified timecodes
- **lifecycle** — current stage and append-only history
- **provenance** — spark id, brief, prompt template and version, model

### Declared and measured are kept apart

`declared_bpm` and `measured_bpm` are separate fields, always. A measurement and
a declaration are different claims, and merging them destroys the only evidence
that they disagree — which they do on nine of twenty-one tracks in the reference
catalogue.

### Assets are fingerprinted

Every master and cover carries a `sha256`. The ledger stores measurements derived
from those files, so without a hash the numbers degrade silently: re-export a
different render of the same title and every timecode stays put while the thing
it describes changes underneath. `forge reconcile` reports drift.

## Why the ledger is data and not prose

The predecessor of this system kept its metadata ledger inside notebook
documents, as prose. Prose ledgers cannot be checked. An audit run against one
reported `PASS` for four files, three of which did not exist — the model had no
way to distinguish verifying a file from describing one.

Everything checkable is therefore checked in Python, and only genuine judgement
is delegated to a model. That division runs through the whole tool:

| Computed | Delegated |
| --- | --- |
| burned phrase reused | is the stance held for the whole song |
| bare or overloaded cue | is the narrator on-model |
| suite anchor missing | does a line contradict the substrate |
| tempo above measured ceiling | is the addressee specific enough |
| n-gram shared with another act | is it any good |

## The gates

- `reconcile` — audio, artwork, lyrics and ledger agree; hashes match; YAML parses;
  naming convention holds. Era- and stage-aware, so work in progress is reported
  without failing the build.
- `variety` — distribution of stance, suite, tempo, key and style prompt. The
  predecessor audit had six gates and all six measured *format*, which is
  trivially satisfiable; it passed a catalogue where four tracks shared a BPM, a
  key and a byte-identical sonic blueprint.
- `mine` — phrases a band has spent, and phrases crossing between acts.
- `prompt lint` — every slot used is declared and every slot declared is used.
