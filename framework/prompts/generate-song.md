---
id: generate-song
version: 1
title: Write a song from a brief
summary: >
  The core generation prompt. Takes a band, a suite, a stance and a measured
  register, and produces a stacked lyric body. The stance constraint is the load
  bearing part — it is what stops four thematic suites producing one speech act.
outputs: lyric-body
runtimes: [agent, api, notebook]
requires:
  - band_name
  - band_role
  - band_position
  - dossier
  - substrate
  - suite_id
  - suite_name
  - suite_domain
  - suite_tension
  - suite_anchors
  - stance_name
  - stance_description
  - tag_formula
  - bpm_target
  - genre
  - vocal
optional:
  - spark
  - band_facet_note
  - suite_metaphor
  - suite_juxtaposition
  - suite_rotation
  - stance_marker
  - stance_example
  - stance_caution
  - register
  - glitch_protocol
  - glitch_reading
  - song_map
  - canon_rules
  - avoid
  - constraints
  - catalogue_digest
  - extra_context
  - label_axiom
  - style_prompt
  - bpm_reason
---

# Write one song for {{band_name}}

You are writing for a virtual act on a DIY label. Write the lyrics only — no
commentary, no explanation, no alternatives. One song.

## Who is speaking

{{band_name}} is **{{band_role}}**. Its position, which it holds against the
other acts on the roster: *{{band_position}}*

{{#band_facet_note}}
{{band_facet_note}}
{{/band_facet_note}}

### The narrator

{{dossier}}

### The shared life underneath

Every act on this label is a facet of the same real person, drawing on one set of
real facts. Do not contradict them, and do not invent a different life. Use them
concretely — a specific object, a specific hour, a named error — never as
abstraction.

{{substrate}}

## What this song is about

**Suite {{suite_id}} — {{suite_name}}**

Domain: {{suite_domain}}

The tension to write into: {{suite_tension}}

{{#suite_metaphor}}
Punk metaphor: {{suite_metaphor}}
{{/suite_metaphor}}

{{#suite_juxtaposition}}
A physical image to reach for: {{suite_juxtaposition}}
{{/suite_juxtaposition}}

At least one of these anchor terms must appear:
{{suite_anchors}}

{{#suite_rotation}}
Available vocabulary, not obligatory:
{{suite_rotation}}
{{/suite_rotation}}

## How it must be spoken — this is the hard constraint

**Stance: {{stance_name}}**

{{stance_description}}

{{#stance_marker}}
Syntactic marker: {{stance_marker}}
{{/stance_marker}}

{{#stance_example}}
Example of the register: "{{stance_example}}"
{{/stance_example}}

{{#stance_caution}}
{{stance_caution}}
{{/stance_caution}}

This is the constraint most likely to be violated by accident, because one
posture is easier to write than the others. A song can rotate its topic and still
be the same song if the speech act never changes. **Hold the stance for the whole
piece.** If you find yourself writing second-person accusation when the stance is
something else, stop and restart the section.

## Sound

- Genre: {{genre}}
- Vocal: {{vocal}}
- Target tempo: {{bpm_target}} BPM{{#bpm_reason}} — {{bpm_reason}}{{/bpm_reason}}
{{#style_prompt}}
- Suno style prompt in use: {{style_prompt}}
{{/style_prompt}}

{{#register}}
### What this voice can and cannot physically deliver

This is measured from the existing catalogue, not guessed.

{{register}}

Use it. Where a hard word will break, that is a placement decision rather than an
accident — put it where the break reads as emphasis, and never put a word the
whole line depends on in a position that will slur.
{{/register}}

{{#glitch_protocol}}
Synthesis failures are kept, not regenerated, and are named under this band's
protocol: **{{glitch_protocol}}** — {{glitch_reading}}
{{/glitch_protocol}}

## Structure

{{tag_formula}}

{{#song_map}}
Standard section map for this act:
{{song_map}}
{{/song_map}}

## Do not reuse

{{#avoid}}
These phrases are spent. Do not use them, and do not paraphrase them closely:
{{avoid}}
{{/avoid}}

{{#constraints}}
Rules in force:
{{constraints}}
{{/constraints}}

{{#canon_rules}}
Band canon:
{{canon_rules}}
{{/canon_rules}}

{{#catalogue_digest}}
### Already said

What this act has released, so you can avoid repeating its moves. Note that the
lyrics themselves are deliberately withheld — you are being shown what is used
up, not given something to echo.

{{catalogue_digest}}
{{/catalogue_digest}}

{{#spark}}
## The spark

This is the raw human input that started the song. It is not tidy and does not
need to be quoted. Find what is actually alive in it.

{{spark}}
{{/spark}}

{{#extra_context}}
## Additional direction for this song

{{extra_context}}
{{/extra_context}}

{{#label_axiom}}
---
Label axiom, which may recur deliberately: *{{label_axiom}}*
{{/label_axiom}}

## Output

The lyric body only. Every section opens with a pipe-stacked cue on its own line.
No title, no preamble, no notes after. If a line is a stage direction rather than
something sung, wrap it in parentheses so it can be excluded from transcript
comparison later.
