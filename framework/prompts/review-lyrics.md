---
id: review-lyrics
version: 1
title: Review lyrics for issues
summary: >
  Scans supplied lyrics — generated here or written anywhere — against the band's
  standards plus whatever ad-hoc direction the user gives. Keeps mechanical
  findings (which cite a rule) strictly apart from judgement findings (which must
  quote the line), because a model grading its own homework will otherwise pass
  itself every time.
outputs: findings
runtimes: [agent, api, notebook]
requires:
  - lyrics
optional:
  - band_name
  - band_role
  - band_position
  - dossier
  - substrate
  - suite_id
  - suite_name
  - suite_anchors
  - stance_name
  - stance_description
  - register
  - bpm_target
  - tag_formula
  - avoid
  - constraints
  - canon_rules
  - catalogue_digest
  - extra_context
---

# Review these lyrics

Report problems. Do not rewrite, do not offer a better version, do not praise.

## The lyrics under review

```
{{lyrics}}
```

{{#extra_context}}
## What the user is asking for

This is the direction for *this* review and takes precedence over general
standards where the two disagree.

{{extra_context}}
{{/extra_context}}

{{#band_name}}
## The standard they are being held to

{{band_name}} — {{band_role}}. Position: *{{band_position}}*

{{#dossier}}
### The narrator these lyrics must sound like

{{dossier}}
{{/dossier}}

{{#substrate}}
### The life they must not contradict

{{substrate}}
{{/substrate}}
{{/band_name}}

{{#suite_name}}
### Intended suite

Suite {{suite_id}} — {{suite_name}}. At least one anchor should appear:
{{suite_anchors}}
{{/suite_name}}

{{#stance_name}}
### Intended stance

**{{stance_name}}** — {{stance_description}}

Check the whole piece holds it. A song that rotates its topic while keeping one
speech act throughout has not varied at all.
{{/stance_name}}

{{#register}}
### What this voice can physically deliver

{{register}}

{{#bpm_target}}
Intended tempo for this song: {{bpm_target}} BPM. Flag any line whose syllable
density will not survive at that speed given the breakage profile above, and flag
a target outside the measured ceiling as a mechanical finding.
{{/bpm_target}}
{{/register}}

{{#tag_formula}}
### Required cue format

{{tag_formula}}
{{/tag_formula}}

{{#avoid}}
### Spent phrases — reuse is a finding

{{avoid}}
{{/avoid}}

{{#constraints}}
### Rules in force

{{constraints}}
{{/constraints}}

{{#canon_rules}}
### Band canon

{{canon_rules}}
{{/canon_rules}}

{{#catalogue_digest}}
### What this act has already released

{{catalogue_digest}}
{{/catalogue_digest}}

## How to report

Two classes of finding, and they must not be mixed. The distinction exists
because one class is checkable and the other is a judgement call, and presenting
a judgement with the confidence of a measurement is how an audit becomes theatre.

**MECHANICAL** — a rule was broken and you can name the rule. A bare cue where
the formula requires stacking. A spent phrase reused. A section opening on a
banned construction. An anchor term missing. A tempo outside the measured
register. Cite the rule and quote the offending text.

**JUDGEMENT** — a call about quality, voice or coherence. Stance not held.
Narrator off-model. Abstraction where the dossier demands a specific addressee.
A line that contradicts the substrate. **Every judgement finding must quote the
exact line it is about.** A judgement you cannot anchor to a line is an
impression, and impressions do not go in the report.

If you cannot determine something — because the information is not here — say
`CANNOT ASSESS` and name what is missing. That is a distinct outcome from
`no issues found`, and conflating them is the failure this format exists to
prevent.

## Output format

```
MECHANICAL
- [rule] quoted text -> what is wrong
JUDGEMENT
- [aspect] "quoted line" -> what is wrong
CANNOT ASSESS
- what you would need
```

Order findings most serious first. If a class is empty, write the header and
`none`. Do not pad.
