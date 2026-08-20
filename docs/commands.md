# Command reference

Generated from the argument parser — this file cannot drift from the code.

```bash
python3 -m framework.forge <command> [options]
```

Commands that report accept `--json`. Structured output is the primary
rendering, since the tool is normally driven by an agent; the formatted
view is a second rendering of the same data.

## `adjudicate`

judge measured glitch candidates

| Option | Meaning |
| --- | --- |
| `--band` | band slug (default: all) |
| `--write` | write/refresh the decision file |
| `--apply` | write kept candidates to glitch logs |
| `--json` | structured output |

## `analyze`

measure audio: dsp, tempo, key, transcript diff

| Option | Meaning |
| --- | --- |
| `--band` | band slug (default: all) |
| `--track` | single track slug |
| `--model` | whisper model (default: large-v3) |
| `--no-asr` | skip transcription and diff |
| `--limit` | candidates shown per track |
| `--write` | write metrics + candidate files |

## `artwork`

link cover art and report duplicates/palette

| Option | Meaning |
| --- | --- |
| `--write` | write artwork paths to the ledger |
| `--no-palette` | skip palette extraction |

## `bootstrap`

seed band ledgers from audio on disk

## `bundle`

compile a NotebookLM bundle

| Option | Meaning |
| --- | --- |
| `kind` |  — one of fresh, export **(required)** |
| `--band` | export: limit to one band |
| `--out` | destination directory |
| `--json` | structured output |

## `decode`

populate the canonical PCM cache

| Option | Meaning |
| --- | --- |
| `--kind` |  — one of dsp, asr, both |
| `--band` | limit to one band slug (default: all) |
| `--force` | re-decode even if cached |

## `docs`

generate documentation

| Option | Meaning |
| --- | --- |
| `kind` |  — one of framework, catalog, agents **(required)** |
| `--out` | destination (e.g. a wiki clone) |
| `--json` | structured output |

## `fingerprint`

hash audio and artwork into the ledger

| Option | Meaning |
| --- | --- |
| `--write` | record hashes |

## `import-lyrics`

import lyric sheets from a harvest document

| Option | Meaning |
| --- | --- |
| `--band` | band slug **(required)** |
| `--source` | harvest document path **(required)** |
| `--write` | write sheets (default: dry run) |

## `infer`

run a prompt: via the surrounding agent, or an API

| Option | Meaning |
| --- | --- |
| `--id` | prompt id **(required)** |
| `--mode` |  — one of agent, api |
| `--band` | band slug |
| `--track` | track slug |
| `--spark` | path to a spark file |
| `--lyrics` | path to lyrics |
| `--vision` | vision text, for derive-band |
| `--context` | ad-hoc direction |
| `--provider` | override the configured provider (api mode) — one of anthropic, openai, google |
| `--model` | override the configured model (api mode) |
| `--out` | write the result here |
| `--write` | write to the conventional destination for this output type |
| `--record` | record prompt/model provenance and stamp the draft stage |
| `--dry-run` | api mode: show the request that would be sent, send nothing |
| `--json` | structured output |

## `ingest-audio`

file a render against a track and hash it

| Option | Meaning |
| --- | --- |
| `--band` | band slug **(required)** |
| `--track` | track slug **(required)** |
| `--file` | the rendered audio **(required)** |
| `--artwork` | cover art for the same track |
| `--replace` | supersede existing audio, archiving its analysis |
| `--move` | move rather than copy the source |
| `--analyze` | measure it immediately |
| `--model` | whisper model for --analyze |
| `--json` | structured output |

## `mine`

find phrases the band has already spent

| Option | Meaning |
| --- | --- |
| `--band` | band slug (default: all) |
| `--label` | cross-band repetition instead |
| `--limit` | max rows per section |
| `--write` | write retired.yaml triage file |

## `next`

outstanding decisions, plus a brief proposal

| Option | Meaning |
| --- | --- |
| `--band` | limit to one band |
| `--json` | structured output |

## `probe`

print an audio facts table

## `prompt`

the prompt library: list, show, lint, render

| Option | Meaning |
| --- | --- |
| `action` |  — one of list, show, lint, render **(required)** |
| `--id` | prompt id, for show/render |
| `--band` | band slug — fills band, dossier, suite, register slots |
| `--track` | track slug — fills candidates, verdict (for adjudicate-glitch) |
| `--suite` | override the proposed suite |
| `--stance` | override the proposed stance |
| `--bpm` | override the proposed tempo |
| `--lyrics` | path to a lyric file (for review/compile) |
| `--spark` | path to a spark file |
| `--vision` | vision text (for derive-band) |
| `--context` | ad-hoc direction for this run |
| `--json` | structured output |

## `reconcile`

check audio, ledger, and lyric sheets agree

| Option | Meaning |
| --- | --- |
| `--fast` | skip ffprobe duration checks |
| `--no-hash` | skip asset drift checks |
| `--strict` | exit 1 on defects; informational findings (IN_PROGRESS, WIP_GAP) do not fail the gate |

## `relink`

wire hand-authored lyric sheets into the ledger

## `review`

scan lyrics for issues; mechanical checks computed

| Option | Meaning |
| --- | --- |
| `--lyrics` | path to lyrics (any source, need not be ours) |
| `--band` | band slug — enables burned lists, anchors, register |
| `--track` | track slug — reads its sheet and its brief |
| `--context` | ad-hoc direction for this review |
| `--prompt` | emit the judgement prompt |
| `--record` | save the review, advance the stage |
| `--json` | structured output |

## `spark`

capture raw input and open a tracked song

| Option | Meaning |
| --- | --- |
| `--text` | the spark, inline |
| `--file` | the spark, from a file |
| `--band` | band slug (omit to see a comparison first) |
| `--title` | provisional title, if you have one |
| `--id` | override the generated spark id |
| `--confirm` | confirm a proposed brief |
| `--track` | track slug, for --confirm |
| `--json` | structured output |

## `stages`

describe the lifecycle and its gates

| Option | Meaning |
| --- | --- |
| `--json` | structured output |

## `status`

where every track sits in the lifecycle

| Option | Meaning |
| --- | --- |
| `--json` | structured output |

## `variety`

stance/suite/tempo distribution across the catalogue

| Option | Meaning |
| --- | --- |
| `--strict` | exit 1 on any warning |
