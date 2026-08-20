# Prompt: Review lyrics for issues

`review-lyrics@v1` — paste everything below the line into the notebook chat.
It refers to other sources by name; make sure they are all uploaded.

---

# Review these lyrics

Report problems. Do not rewrite, do not offer a better version, do not praise.

## The lyrics under review

```
_(supply this, or see your band definition)_
```

## What the user is asking for

This is the direction for *this* review and takes precedence over general
standards where the two disagree.

_(supply this, or see your band definition)_

## The standard they are being held to

_(supply this, or see your band definition)_ — _(supply this, or see your band definition)_. Position: *_(supply this, or see your band definition)_*

{{#dossier}}
### The narrator these lyrics must sound like

Derive this first with **03-prompt-derive-band.md**, then add the result to this notebook as a source.
{{/dossier}}

{{#substrate}}
### The life they must not contradict

You have no shared biography yet. If you want one, write it after the band exists — it is optional for a single act.
{{/substrate}}

### Intended suite

Suite _(supply this, or see your band definition)_ — _(supply this, or see your band definition)_. At least one anchor should appear:
_(supply this, or see your band definition)_

### Intended stance

**_(supply this, or see your band definition)_** — _(supply this, or see your band definition)_

Check the whole piece holds it. A song that rotates its topic while keeping one
speech act throughout has not varied at all.

### What this voice can physically deliver

UNMEASURED. A register can only be filled after you have audio and have listened to where the voice actually breaks. Do not invent a tempo ceiling.

{{#bpm_target}}
Intended tempo for this song: _(supply this, or see your band definition)_ BPM. Flag any line whose syllable
density will not survive at that speed given the breakage profile above, and flag
a target outside the measured ceiling as a mechanical finding.
{{/bpm_target}}

### Required cue format

[Section | Genre/Era | Vocal Texture | Production Vibe] — see **01-standards.md**.

### Spent phrases — reuse is a finding

Nothing spent yet. Start a list the first time you notice a phrase recurring.

### Rules in force

See your derived band definition.

### Band canon

See the canon rules in your derived band definition.

### What this act has already released

Nothing released yet. Nothing is spent.

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
