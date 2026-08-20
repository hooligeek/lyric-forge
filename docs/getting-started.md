# Getting started

## Choose a tier

**No backend.** Take `bundles/fresh-spark/`, upload the files to one NotebookLM
notebook, and follow `00-START-HERE.md`. You need a vision and, ideally, a demo
song. Nothing else — no install, no command line.

**With the toolchain.** Everything below.

## Install

```bash
python3 -m venv .venv
./.venv/bin/pip install pyyaml                        # core
./.venv/bin/pip install librosa soundfile faster-whisper   # analysis extras
```

`ffmpeg` and `ffprobe` must be on `PATH` — the audio and artwork pipelines both
use them. Core commands run on stdlib plus `pyyaml`; only `forge analyze` needs
the extras.

## Orient yourself

```bash
python3 -m framework.forge status     # where every track sits
python3 -m framework.forge next       # what to do, and why
python3 -m framework.forge stages     # the process itself
```

Those three exist because an agent — or you, returning after a month — arrives
with no idea what the project needs.

## Start a label

Edit `label/label.yaml`: the label name, its axiom, and one entry per act with an
id prefix. Write `label/substrate.md` if the acts share a biography.

Then derive an act from a vision:

```bash
python3 -m framework.forge infer --id derive-band \
  --vision "a dub soundsystem crew who only play at dawn, obsessed with tide tables"
```

Save the result as `label/bands/<slug>/band.yaml` and `dossier.md`.

## Write a song

```bash
# 1. capture the raw thing
forge spark --band <slug> --file note.md

# 2. read the proposed brief, change what you disagree with, then
forge spark --confirm --band <slug> --track <track-slug>

# 3. generate
forge infer --id generate-song --band <slug> --track <track-slug> --write

# 4. review — mechanical checks computed, judgement delegated
forge review --band <slug> --track <track-slug>
forge review --band <slug> --track <track-slug> --prompt

# 5. compile the sheet, take it to your generator, then bring the render back
forge ingest-audio --band <slug> --track <track-slug> --file "Take 3.mp3"

# 6. measure it
./.venv/bin/python -m framework.forge analyze --band <slug> --track <track-slug> --write

# 7. judge the failures — this one is yours alone
forge adjudicate --band <slug> --write
forge adjudicate --band <slug> --apply
```

## Import an existing catalogue

```bash
forge bootstrap                                   # seed ledgers from audio on disk
forge import-lyrics --band <slug> --source <harvest-doc>   # dry run first
forge artwork --write
forge fingerprint --write
forge reconcile
```

`bootstrap` and `import-lyrics` are both idempotent, and `import-lyrics` dry-runs
by default so you can check the parse before it writes anything.
