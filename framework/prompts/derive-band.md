---
id: derive-band
version: 1
title: Derive a band kit from a vision
summary: >
  Turns a user's raw vision — however messy — into a complete band definition:
  narrator dossier, thematic suites with tiered lexicons, stance affinities and a
  glitch protocol. This is the onboarding prompt, and the single most important
  one for anybody arriving with nothing but an idea.
outputs: band-kit
runtimes: [agent, api, notebook]
requires:
  - vision
  - stance_roster
optional:
  - substrate
  - label_name
  - label_axiom
  - extra_context
---

# Derive a band from this vision

The user has an idea for an act. Turn it into a working definition. Push back on
vagueness rather than accepting it — a definition made of adjectives produces
songs made of adjectives.

{{#label_name}}
This act joins **{{label_name}}**{{#label_axiom}}, whose axiom is
*{{label_axiom}}*{{/label_axiom}}. The act must be able to coexist with that
without simply restating it.
{{/label_name}}

## The vision as given

{{vision}}

{{#extra_context}}
## Additional direction

{{extra_context}}
{{/extra_context}}

{{#substrate}}
## The life this act draws on

If a shared biography exists, this act is a facet of the same person rather than
an unrelated character. Its worldview must be a *posture toward* these facts, not
a different set of them.

{{substrate}}
{{/substrate}}

## What to produce

### 1. Identity

Name, role in one phrase ("the one who endures"), and a **position** — a single
sentence this act would say that at least one other act on the roster would
disagree with. If every act would agree with it, it is a label slogan and not a
position, and the roster has one opinion in several accents.

### 2. Narrator dossier

The highest-value part. Fix the speaker, because diction follows from position:

- **Who** they are, specifically.
- **Where** they are — an actual room or place, with objects in it.
- **When** — the hour of the day. Be exact; it constrains everything.
- **To whom** they are speaking. One named addressee beats a category. If nobody
  is addressed, say so, because that is a real and distinguishing choice.
- **What they want** from the listener. Keep the ambition small.
- **What they cannot admit.** The thing that is true and never said. This is
  where the unwritten songs live, so make it specific and uncomfortable.
- **Diction** — register, sentence length, vocabulary sources.
- **Off-model tells** — concrete signs a lyric has drifted.

### 3. Thematic suites

Four or five. Each is a *collision* between a technical or factual domain and a
subcultural image, not a topic heading. For each:

- **domain** — what field it draws on
- **tension** — the actual conflict, stated as a conflict
- **punk_metaphor** — the subcultural image it collides with
- **juxtaposition** — one concrete physical picture. Be specific enough that it
  could not have been written for a different band. This field does more work
  than any other; a vague one means the suite is not real yet.
- **anchors** — three to five terms that define the suite, at least one of which
  must appear in any song using it
- **rotation** — a wider working vocabulary
- **stance_fit** — which stances suit this suite

### 4. Stance affinities

From the roster below, name the stances natural to this act and one **priority**
— the one it should use first, with a reason. Prefer a stance the act has an
obvious structural reason to be good at.

{{stance_roster}}

### 5. Sound and register

Genre, vocal character, nominal tempo and a plausible range, and a Suno style
prompt. Mark the register as **unmeasured** — it can only be filled once audio
exists and has been analysed. Do not guess a tempo ceiling and present it as
known.

### 6. Glitch protocol

A name, in this act's own vocabulary, for what a synthesis failure *is* to them.
Not a description of the failure — a reframing of it. A horn player splitting a
reed, vines over stonework, a redlined tape input. Failures are kept and named,
never regenerated.

### 7. Canon rules

Five or so hard prohibitions, phrased so a violation is recognisable. "Avoid
generic lyrics" is not a rule. "Never use the words lazy, stupid or dumb; use the
specific coinage instead" is.

## Output

Two artefacts, clearly separated:

1. `band.yaml` — identity, sonic, register, stances, suites, canon_rules
2. `dossier.md` — the narrator, in prose

Where the vision does not determine something, say so explicitly and ask. Do not
fill a gap with a plausible invention — an invented dossier is worse than an
incomplete one, because nobody knows which parts to trust.
