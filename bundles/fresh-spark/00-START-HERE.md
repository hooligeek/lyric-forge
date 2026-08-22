# Start here

This is a starter kit for building a virtual band and writing songs for it, using
nothing but a notebook. No install, no code, no command line.

## What you need

1. **A notebook with an AI assistant that can read uploaded files.** These
   instructions were written for **Google NotebookLM** (free, notebooklm.google.com),
   which is where the "upload these as sources" wording comes from. Anything that
   can hold a dozen documents in context and answer against them will work.
2. **A music generator that accepts a lyrics box and a style prompt.** These
   instructions assume **Suno** (suno.com), because the section-cue format below
   is written for how Suno reads bracketed tags. Another generator will work but
   you may have to adapt the cue syntax.
3. **A vision.** However messy. A genre, a grievance, an image, an argument you
   had. It does not need to be tidy — the tidying is step 2.
4. **A demo song** (optional but useful). Any render, even a bad one. It tells you
   what your style prompt actually produces.

Both services have free tiers at the time of writing. Neither is required by the
*method* — the standards, the stances and the prompts are generator-agnostic —
but the wording below names them because vague instructions are useless.

## What to upload

Put every file in this folder into one notebook as sources. All of them. They
refer to each other by filename, so a missing one leaves a hole.

## The order to work in

### 1. Derive your band

Paste **03-prompt-derive-band.md** into the chat, with your vision.

You get back a band definition and a narrator dossier. Read them properly. The
dossier is the part that matters most — it fixes *who is speaking, from where, at
what hour, to whom*, and diction follows from position far more reliably than from
any word list.

**Save both as new sources in this notebook.** Everything after this depends on
them being there.

Expect to be asked questions rather than given a complete answer. A definition
made of adjectives produces songs made of adjectives, so the prompt is written to
push back on vagueness instead of filling gaps with invention.

### 2. Write a song

Paste **04-prompt-generate-song.md**. Choose:

- a **suite** — one of the thematic collisions in your definition
- a **stance** — from **02-stances.md**

Pick a stance you have not used. This is the single highest-value discipline in
the kit and the easiest to skip: one posture is easier to write than the others,
so without a deliberate choice a catalogue converges on it. A real example from
the project this kit came from — six songs, four thematic suites, and every one of
them was second-person accusation.

### 3. Review it

Paste **05-prompt-review-lyrics.md** with the lyrics and any direction for this
particular pass ("make it colder", "no second person", "must scan at 180").

Findings come back in two classes, and the split matters: **mechanical** findings
cite a rule, **judgement** findings quote the line they are about. Anything that
cannot be assessed says so rather than passing quietly.

### 4. Compile the sheet

Paste **06-prompt-compile-sheet.md**. This is formatting, not editing — it must
not change a word.

### 5. Render, then listen

Take the sheet to your generator. Then **listen for the failures** and log them.

Read **01-standards.md** on this before deciding a bad take is a
bad take. When the synthesiser chokes, that is material, not an error — but
whether a particular failure is worth keeping is your call and nobody else's.

### 6. Write the caption, last

Paste **07-prompt-write-caption.md**, once the render exists and you have decided
which failures you are keeping. It is written last on purpose: a caption names what
actually happened, and until the take exists there is nothing to name.

Hard limit 500 characters, because that is what the platform accepts. Set the scene
in the concrete — the room, the hour, one physical object — and then quote the
divergence: what was written, what came out instead. Do not explain why it is
interesting and do not claim it was intended. It was kept; that is the statement.

### 7. Then the cover

Paste **08-prompt-write-artwork.md**. It goes after the caption for the same reason
the caption goes after the render: the strongest covers put the song's own kept
failure into the image, and until the take exists there is no failure to put there.

**09-example-artwork-prompt.md** is a real one, with what it produced and what it got
wrong. It is the only page in this kit that cites an actual release, because a prompt
of that kind is far easier to copy than to describe.

### 8. Keep a spent list

The first time you notice a phrase recurring, write it down in a source file. That
list is the single most useful thing you will build, and it only works if you
start it early. Repetition inside one song is a chorus; repetition across songs is
a rut, and you will not notice it by memory.

## What this kit deliberately does not do

It does not measure. A notebook can read and it can listen; it cannot inspect a
waveform. **10-honesty-rules.md** covers what follows from that — the short
version is that any timecode a notebook produces is invented, so anchor
observations to section and phrase instead.

If you later want real measurement — tempo verification, clipping detection,
transcript-versus-sheet diffing with actual timestamps — that needs the toolchain
this kit was generated from. The document formats are identical, so nothing has to
be rebuilt when you upgrade.
