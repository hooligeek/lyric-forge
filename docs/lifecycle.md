# The song lifecycle

Generated from `lifecycle.py`.

A song is tracked from raw input to adjudicated glitch log. **Stage is
derived from what exists on disk**, never read from a field somebody has
to remember to update — a recorded stage that disagrees with reality is
worse than no stage at all.

`imported` sits outside the sequence. Legacy tracks enter there rather
than at `mastered`, because they genuinely did not go through this
pipeline and inventing a spark for them would fabricate provenance.

| # | Stage | Gate | Requires | Summary |
| --- | --- | --- | --- | --- |
| — | `imported` | machine | `lyric_sheet` | Brought in from outside the pipeline. No spark, no brief, no provenance. |
| 0 | `spark` | human | `provenance.spark` | Raw human input captured — the fused idea, before it is a plan. |
| 1 | `brief` | human | `provenance.brief_confirmed`, `matrix.suite`, `matrix.stance` | Band, suite, stance, constraints and tempo target agreed. |
| 2 | `draft` | machine | `provenance.draft`, `provenance.prompt_template` | Lyrics generated against the brief. |
| 3 | `review` | human | `provenance.review` | Mechanical and judgement findings raised and resolved. |
| 4 | `sheet` | human | `lyric_sheet`, `suno.style_prompt`, `suno.declared_bpm` | Approved for render: style prompt, stacked cues, declared tempo. |
| 5 | `rendered` | human | `audio`, `audio_sha256` | Audio returned from Suno and ingested. |
| 6 | `analysed` | machine | `analysis` | Measured: clipping, tempo, key, transcript diff against the sheet. |
| 7 | `adjudicated` | human | `glitch_log` | Glitch candidates judged and named under the band protocol. |
| 8 | `mastered` | machine | — | Done. |

## What each human gate asks for

### `spark`

The raw thing. An argument you had, a phrase, an image, a line you cannot place. Do not tidy it — the tidying is the next stage's job.

### `brief`

Confirm or change the proposed band, suite, stance and tempo. The proposal is computed from what the catalogue is short of, so overriding it is a deliberate choice rather than a default.

### `review`

Each finding needs accept or override. Mechanical findings cite the rule they broke; judgement findings quote the line they are about. An override is recorded, not silently dropped.

### `sheet`

Approve the sheet for Suno. This fixes the style prompt and the declared tempo, which the analyser will later measure against.

### `rendered`

Drop the rendered mp3 in and it will be hashed, decoded and matched to this track.

### `adjudicated`

Keep, discard or rename each measured candidate. Which failures are badges of honour is the one judgement the tool must never make for you — that is the Glitch Axiom.
