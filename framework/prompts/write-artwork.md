---
id: write-artwork
version: 1
title: Write the cover art prompt for a finished track
summary: >
  The prompt an image model gets. Written after the render, because the strongest
  covers quote the song's own measured failure back at it — and that is not known
  until the take exists.
outputs: artwork-prompt
runtimes: [agent, api, notebook]
requires:
  - band_name
  - track_title
optional:
  - glitch_log
  - suite_name
  - suite_domain
  - suite_juxtaposition
  - suite_metaphor
  - stance_name
  - band_position
  - band_role
  - genre
  - label_axiom
  - extra_context
---

# Write the cover prompt for {{track_title}}

One prompt, ready to paste into an image model. Not a description of the artwork —
the instructions that produce it.

## What this sleeve is for

{{#band_role}}{{band_name}} is **{{band_role}}**.{{/band_role}}
{{#band_position}}Its position on the roster: *{{band_position}}*{{/band_position}}
{{#genre}}Genre, which sets the sleeve's whole visual tradition: {{genre}}{{/genre}}
{{#suite_name}}Suite: **{{suite_name}}**{{/suite_name}}
{{#suite_domain}}
Subject matter: {{suite_domain}}
{{/suite_domain}}

## Start from the act's existing covers

Look at what this band's other sleeves already do and name it: palette, ink count,
illustration style, where the title sits, what the typography is. **Continuity is
the job.** A cover that does not look like the act is a cover for a different act,
however good it is on its own.

Then check the existing covers against the act's own definition, because they may
disagree. A band whose dossier says its subject is one person in one room, whose
covers are all ruined cities, has artwork that is off-model — and the new cover is
where that gets corrected rather than repeated.

## Scale is usually the mistake

Most weak covers are the right subject at the wrong size. If the song is about one
person and one object, the cover is one person and one object; a landscape makes it
generic. Write the scale constraint in as an explicit instruction and say what it
excludes, because an image model will reach for the epic by default.

{{#suite_juxtaposition}}
This suite already names a physical image to work from:

> {{suite_juxtaposition}}
{{/suite_juxtaposition}}
{{#suite_metaphor}}
And a metaphor: *{{suite_metaphor}}*
{{/suite_metaphor}}

{{#stance_name}}
The stance is **{{stance_name}}**, and it should govern the register. A song that
reports rather than argues wants a document, not a scene: flatness is the point.
{{/stance_name}}

## Quote the glitch

{{#glitch_log}}
These are the failures that were kept on this track:

{{glitch_log}}
{{/glitch_log}}

Pick one and put it **in** the image, legibly, as text or as the subject. Instruct
the model not to correct it to something more plausible — it will try. A cover that
carries the song's own measured failure is doing something no stock sleeve can.

## Then ask for one failure of its own

Brief a deliberate defect appropriate to the medium: a misregistered plate, a
dropped scanline, an ink-starved band, a double-struck letter. Say plainly that it
must not be cleaned up.

Be honest about what that is, though. **A briefed defect is designed, not kept.** It
makes the axiom visible; it is not the axiom. The real thing is whatever the
generator gets wrong *unbidden* on top of it — so when the image comes back, read it
closely before re-rolling. Zoom in on small text especially. The best accidents hide
where a thumbnail looks like noise.

## Say what is excluded

End with an explicit not-wanted list. Genre defaults, borrowed iconography from
other acts on the roster, and anything that would make the record about a subject it
is not about. If the song concerns a person's circumstances, exclude the symbols
that would turn those circumstances into the artwork's topic.

{{#extra_context}}
## Direction for this one

{{extra_context}}
{{/extra_context}}

{{#label_axiom}}
---
Label axiom: *{{label_axiom}}*
{{/label_axiom}}

## Output

The image prompt only. No preamble, no explanation of your choices, no alternatives.
One prompt, in prose and bulleted instruction, of the length the model needs — detail
is the point, brevity is not a virtue here. State the aspect ratio and pixel
dimensions.
