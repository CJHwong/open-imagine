# Prompt craft for music

The request has two writing fields. `style` describes the arrangement. `lyrics` carries the
words and their sections. The engine plans and renders; you do the writing and the checks.

## Write the style as a short brief

Name, in full sentences or a comma list, what the listener should hear:

1. Language and vocal type: `English, warm female lead vocal`.
2. Genre and era: `contemporary pop with a 1970s soul feel`.
3. Mood: `intimate and unhurried`, `bright and playful`, `dark and tense`.
4. Instruments: `acoustic piano, upright bass, brushed drums, tenor saxophone`.
5. Tempo: `88 BPM`.
6. Production: `dry close vocal, wide piano, no reverb wash`.

The page's Genre and Style preset chips append sentences in this shape. They are a good
starting point, and the API takes the sentence, not the chip label. Useful examples:

- `Use a pop arrangement with a memorable melodic hook and clear verse and chorus sections over a steady pulse.`
- `Create a warm mood with rounded timbres and gentle phrasing that feels intimate and welcoming.`
- `Feature an acoustic piano with clear hammer attacks and resonant chords supporting expressive melodic lines.`
- `Use an R&B arrangement with a smooth syncopated groove and rich harmonies supporting expressive melodic phrases.`
- `Use a female lead vocal with clear words and expressive phrasing that follows the supplied lyrics.`

Adapt them. A genre label alone does not fix the instruments, the tempo or the vocal. Do not
paste every preset into one style. Contradictory instructions cancel each other, and a style
much longer than one paragraph buries the important choices.

The API has no separate tempo, key or meter field. Put the tempo in `style` and, when you
supply a score, put the matching `Q:` and `K:` in the ABC. Do not invent a `bpm` field.
The engine's plan sets the score's actual `Q:` and meter; a BPM in `style` is a request, not a
setting. In a four-style sample at one seed, requested 88, 80, 95 and 70 BPM came back as 84,
75, 92 and 100 BPM, and the plan added 2/4, 9/8 and 3/8 sections. Read the returned score when
tempo or meter matters.

## Write lyrics the engine can sing

Use section tags on their own lines:

```text
[Verse]
Neon fades along the lane
Footsteps keep the time of rain

[Chorus]
Let the day come into view
Every road begins with you
```

- One scene per verse. Keep the images concrete.
- The chorus repeats the line people remember. A short chorus usually sings better than a
  long one.
- Put one thought on each line, and leave a breath at the line end.
- Vowels carry held notes. Consonant clusters crowd short notes.
- Section tags are structure, not scheduling. A tag such as `[Instrumental]` or a style
  sentence about a saxophone solo tells the engine the intent; it does not place a solo at an
  exact bar.

Leave lyrics blank for an instrumental and send `instrumental: true`. The page sets that flag
when the field is blank; the API requires it explicitly. A blank field without the flag is a
validation error.

For a lyric rewrite, keep the meaning and sing it on the existing line lengths. Match the
syllable count first, then the stress and the vowel on the long note. A word-for-word
translation that fits the meaning can still fail the melody.

## Fields that do not exist

Do not send `bpm`, `phonemes`, `negative_prompt`, `reference_singer`, `tags` or a lyric
alignment map. The public schema has no such fields. Keep a syllable or phoneme sidecar
outside the request if you need one for review; it is not an engine input, and it does not
prove how the engine will place a syllable.

## Direct generation

`cot: "off"` skips symbolic planning and returns no usable score. Use it when the user wants
a fast take and does not need to edit the melody. Do not use it to hide a planning failure,
and do not send `abc` with it.

## Instrumentals

An instrumental still needs a real style: instruments, mood, register, tempo and texture. A
style that names no instrument usually drifts. Instrumentals need `full` or `melody`
planning.

When you supply a score for an instrumental, the engine may move the vocal melody into the
instrumental part. The returned score then differs from the one you sent. Say so, and read
the returned score if the user needs the exact notes.
