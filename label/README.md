# Your label goes here

`framework/` is the toolchain and is generic. **This directory is yours.**

```
label/
  label.yaml       start here — the roster, your axiom, your eras
  substrate.md     optional: the shared biography your acts draw on
  bands/<slug>/    band.yaml, dossier.md, tracks.yaml, retired.yaml, lyrics/
  audio/<slug>/    masters, named <track-slug>.mp3
  artwork/songs/   covers, named <track-slug>.jpeg
  artwork/albums/  per-band release covers
  sparks/          raw human input — GITIGNORED, never committed
  briefs/          derived briefs — committed, and they reference sparks by id only
```

## First steps

```bash
forge status                 # tells you what is missing
forge infer --id derive-band --vision "your idea, however messy"
```

Save the derived result as `bands/<slug>/band.yaml` and `bands/<slug>/dossier.md`,
add the act to `label.yaml`, and you can write a song.

## If you already have a catalogue

```bash
forge bootstrap                                        # seed ledgers from audio on disk
forge import-lyrics --band <slug> --source <document>  # dry-runs first
forge artwork --write
forge fingerprint --write
forge reconcile
```

## Getting listed as an approved fork

```bash
forge certify
```

Nine gates. It tells you exactly what is missing, and none of it is a judgement
about the music. See the repository README for how to submit.
