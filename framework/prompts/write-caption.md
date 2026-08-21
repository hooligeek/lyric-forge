---
id: write-caption
version: 1
title: Write the published caption for a finished track
summary: >
  The 500-character blurb the platform publishes beside the song. Written last,
  after the render and the cover exist, because it names what actually happened
  rather than what was intended — including the failures that were kept.
outputs: caption
runtimes: [agent, api, notebook]
requires:
  - band_name
  - track_title
optional:
  - lyrics
  - glitch_log
  - band_position
  - band_role
  - suite_name
  - suite_domain
  - suite_tension
  - stance_name
  - label_axiom
  - glitch_protocol
  - extra_context
---

# Write the caption for {{track_title}}

One paragraph or two. **Hard limit 500 characters** — the platform rejects longer,
so a caption that overruns is a caption that does not exist. Count them.

This is the only label-authored prose most listeners will ever read. It is not a
press release, not a summary of the lyrics, and not an explanation of the song.

## What it has to do

**Set the scene in the concrete.** The room, the hour, the object. One specific
physical detail beats three abstractions — a fan pointed into an open case, not
"themes of technological strain". If the song has an hour, name it.

**Then name the failure that was kept.** This is the part nobody else writes, and
it is why the caption is written last. Quote the divergence: what was written, what
came out instead. Do not explain why it is interesting; put it down and stop.

Do not apologise for it, do not call it a happy accident, and do not claim it was
intended. It was kept. That is the whole statement.

## Who this is

{{#band_role}}{{band_name}} is **{{band_role}}**.{{/band_role}}
{{#band_position}}Its position: *{{band_position}}*{{/band_position}}
{{#stance_name}}This track is written in **{{stance_name}}** stance.{{/stance_name}}
{{#suite_name}}
Suite: **{{suite_name}}**{{#suite_domain}} — {{suite_domain}}{{/suite_domain}}
{{/suite_name}}
{{#suite_tension}}The tension it sits on: {{suite_tension}}{{/suite_tension}}

{{#glitch_protocol}}
Failures on this act are named under its own protocol: **{{glitch_protocol}}**.
{{/glitch_protocol}}

## The failures that were kept

{{#glitch_log}}
{{glitch_log}}
{{/glitch_log}}

Pick the one or two that land hardest. A caption naming five glitches names none of
them. Prefer a failure that means something over one that is merely large: a word
that came out as a different word the song is better for beats a whole line lost to
noise.

If a kept entry is an artwork artefact rather than an audible one, say so plainly —
it belongs to the image, not the take, and blurring the two misdescribes both.

## The lyrics, for the scene only

{{#lyrics}}
{{lyrics}}
{{/lyrics}}

Do not quote a lyric line as the caption's own voice. Describe the situation the
song is in; let the song do the singing.

{{#extra_context}}
## Direction for this one

{{extra_context}}
{{/extra_context}}

{{#label_axiom}}
---
Label axiom, which may recur deliberately: *{{label_axiom}}*
{{/label_axiom}}

## Output

The caption text only. No heading, no title, no quotation marks around the whole
thing, no character count, no commentary after. Two paragraphs at most, separated by
a blank line.
