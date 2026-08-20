# Prompt: Compile an approved lyric sheet

`compile-sheet@v1` — paste everything below the line into the notebook chat.
It refers to other sources by name; make sure they are all uploaded.

---

# Compile this into a lyric sheet

Formatting, not authorship. **Do not change a word of the lyrics** — not to
improve a line, not to fix a rhyme, not to correct grammar. If something looks
wrong, note it after the sheet; do not silently repair it.

## Lyric body

```
_(supply this, or see your band definition)_
```

## Required output shape

```markdown
---
band: _(supply this, or see your band definition)_
track_id: <assigned by the ledger — leave as TBD>
title: <title>
slug: <kebab-case of title, ampersand becomes "and">
document_class: LYRIC_SHEET_STANDARD
era: acap
---

# <title>

## Production
- band: _(supply this, or see your band definition)_
- suite: _(supply this, or see your band definition)_ — _(supply this, or see your band definition)_
- stance: _(supply this, or see your band definition)_
- declared_bpm: _(supply this, or see your band definition)_
- style_prompt: _(supply this, or see your band definition)_

## Sonic blueprint
<two sentences: the vocal profile and the instrumental bed, drawn from
genre "_(supply this, or see your band definition)_" and vocal "_(supply this, or see your band definition)_". Write it for this song specifically —
a blueprint copied unchanged across a band's whole catalogue is how four tracks
end up with one identical paragraph.>

## Lyrics

<the stacked lyric body, verbatim>

## Glitch log

(empty — populated from measurement after the render, never in advance)
```

## Cue rules

[Section | Genre/Era | Vocal Texture | Production Vibe] — see **01-standards.md**.

Every section cue is pipe-stacked. If the body arrived with a bare cue such as
`[Verse]` or `[Chorus]`, expand it using this act's vocabulary — that is the one
edit permitted, because a bare cue is a formatting defect rather than a lyric.

Section names should map onto this act's standard structure where the song allows:
See your derived band definition, if you defined one.

Lines that are stage directions rather than sung text stay wrapped in
parentheses. They belong in the sheet — Suno reads them — but they are excluded
from transcript comparison, so the parentheses are load-bearing.

The glitch log stays **empty**. Anomalies are measured from the render and named
under this act's protocol (_(supply this, or see your band definition)_) afterwards. A glitch log written
before the audio exists is fabricated evidence.

Output the sheet and nothing else, except any note about text you were tempted to
change and did not.
