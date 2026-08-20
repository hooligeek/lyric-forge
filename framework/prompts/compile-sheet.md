---
id: compile-sheet
version: 1
title: Compile an approved lyric sheet
summary: >
  Turns a lyric body into the canonical sheet: frontmatter, production metadata,
  sonic blueprint, stacked cues, and an empty glitch log ready for measurement.
  Mechanical work, so the prompt is short and its rules are absolute.
outputs: lyric-sheet
runtimes: [agent, api, notebook]
requires:
  - lyrics
  - band_slug
  - band_name
  - tag_formula
optional:
  - style_prompt
  - bpm_target
  - genre
  - vocal
  - suite_id
  - suite_name
  - stance_id
  - glitch_protocol
  - song_map
---

# Compile this into a lyric sheet

Formatting, not authorship. **Do not change a word of the lyrics** — not to
improve a line, not to fix a rhyme, not to correct grammar. If something looks
wrong, note it after the sheet; do not silently repair it.

## Lyric body

{{lyrics}}

## Required output shape

```markdown
---
band: {{band_slug}}
track_id: <assigned by the ledger — leave as TBD>
title: <title>
slug: <kebab-case of title, ampersand becomes "and">
document_class: LYRIC_SHEET_STANDARD
era: acap
---

# <title>

## Production
- band: {{band_name}}
- suite: {{suite_id}} — {{suite_name}}
- stance: {{stance_id}}
- declared_bpm: {{bpm_target}}
- style_prompt: {{style_prompt}}

## Sonic blueprint
<two sentences: the vocal profile and the instrumental bed, drawn from
genre "{{genre}}" and vocal "{{vocal}}". Write it for this song specifically —
a blueprint copied unchanged across a band's whole catalogue is how four tracks
end up with one identical paragraph.>

## Lyrics

<the stacked lyric body, verbatim>

## Glitch log

(empty — populated from measurement after the render, never in advance)
```

## Cue rules

{{tag_formula}}

Every section cue is pipe-stacked. If the body arrived with a bare cue such as
`[Verse]` or `[Chorus]`, expand it using this act's vocabulary — that is the one
edit permitted, because a bare cue is a formatting defect rather than a lyric.

{{#song_map}}
Section names should map onto this act's standard structure where the song allows:
{{song_map}}
{{/song_map}}

Lines that are stage directions rather than sung text stay wrapped in
parentheses. They belong in the sheet — Suno reads them — but they are excluded
from transcript comparison, so the parentheses are load-bearing.

{{#glitch_protocol}}
The glitch log stays **empty**. Anomalies are measured from the render and named
under this act's protocol ({{glitch_protocol}}) afterwards. A glitch log written
before the audio exists is fabricated evidence.
{{/glitch_protocol}}

Output the sheet and nothing else, except any note about text you were tempted to
change and did not.
