---
id: adjudicate-glitch
version: 1
title: Present measured glitch candidates for human judgement
summary: >
  Walks the operator through measured candidates so they can keep, discard or
  rename each. The model presents evidence and proposes a naming; it never
  decides. Which failures are badges of honour is the one judgement automating
  away would gut the whole idea.
outputs: adjudication
runtimes: [agent, api]
requires:
  - candidates
  - glitch_protocol
  - glitch_reading
optional:
  - band_name
  - track_title
  - register
  - asr_verdict
---

# Adjudicate the glitches on {{track_title}}

{{#band_name}}Act: {{band_name}}.{{/band_name}} Protocol: **{{glitch_protocol}}**
— {{glitch_reading}}

Your job is to **present**, not to decide. For each candidate, lay out the
evidence and propose how it would be named under the protocol if kept. The
operator keeps, discards or renames. Do not express a preference about which
failures are worth keeping.

{{#asr_verdict}}
## Read this first

Transcript verdict for this track: **{{asr_verdict}}**

- `sheet-mismatch` — the sheet and the master are different arrangements.
  Divergences below are document differences, **not** glitches. Say so and stop;
  adjudicating them would record fiction in the glitch log.
- `asr-unreliable` — the model did not hear enough of the vocal to conclude
  anything. Present the candidates as unverified and recommend an ear.
- `ok` — proceed normally.
{{/asr_verdict}}

## Measured candidates

{{candidates}}

{{#register}}
## What this voice is known to break on

Use this to say whether a candidate is characteristic of the voice or unusual for
it. That is genuinely useful context; a recommendation is not.

{{register}}
{{/register}}

## For each candidate, output

1. **What was measured** — the timecode, and expected versus heard where it
   applies. Quote it; do not paraphrase evidence.
2. **Confidence** — carried through from the measurement, plus anything that
   should qualify it. Clipping detected from mp3 can be decoder overshoot; a low
   confidence transcript word is weak evidence.
3. **Proposed name** — how it would be logged under {{glitch_protocol}}, in this
   act's vocabulary rather than generic audio-engineering terms.
4. **What is genuinely unclear** — anything the measurement cannot settle.

Then stop and ask. One question covering all candidates, offering keep, discard
or rename per item. Do not write the glitch log yourself — it is written from the
operator's answers, after they answer.
