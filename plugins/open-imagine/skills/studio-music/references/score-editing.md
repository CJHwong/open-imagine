# Score editing

A score edit is a new version, not a change to the recording. Keep the source score and the
source request. Write a new score, then render it with a new operation.

## Get the score

- A Plan result is JSON with `score` and no audio.
- A Generate result with `full` or `melody` planning also returns a score next to the audio.
- `GET /api/v1/operations/{id}/metadata` returns the score for a completed audio operation.
- A Transcribe result is a score read from a recording. Inspect it before treating it as a
  musical source.
- In the page, **Edit score** loads the song's score into a new Generate request. The API
  equivalent is Generate with `abc`.

Save the source. Never edit the only copy.

## State the contract before editing

| Contract | What must stay fixed |
|---|---|
| Exact melody and rhythm | Sounding pitch, onset and duration in the named voices and passages |
| Same pitches, new rhythm | Ordered sounding pitches. Record the rhythm and articulation you allow. |
| Recognizable theme | The complete phrase sequence and the stated repetitions. List allowed embellishments. |
| Free adaptation | The agreed phrases, range, contour, cadences or motifs. Report the notes that changed. |

Name the voices, sections, tempo, meter, lyrics and instrumental passages that may change. A
chord-only edit should not touch the melody. A style change belongs in `style` as well as in
the score.

## Preserve the returned ABC dialect

The engine writes a narrow, native ABC. Treat the returned score as the authority.

- Keep `X:`, `T:`, `M:`, `L:`, `Q:`, `K:` and the voice declarations.
- Keep `L:` as exported. YuE2 often writes `L:1/32`; do not rescale a score to a familiar
  unit unless you also rewrite every duration deliberately.
- The two voices are melody lines, `V: Vocal` and `V: Ins`. They are not a piano chord staff.
  Harmony appears as quoted symbols, usually in the Vocal voice, including while it rests.
- Keep `%` section comments such as `% verse` and `% chorus`. Keep the bar grouping and the
  order of the voice blocks.
- A chord change inside a held note needs a tie. Without it, the second note is a new attack.
- Count sounding notes after merging ties, not raw note tokens.
- An accidental lasts through its bar and then resets. A tied continuation across a barline
  keeps the pitch. The engine's writer can propagate an accidental by letter across octaves.
  Do not paste the score into a parser with different accidentals and assume it means the
  same thing. The browser engraving is a reading aid, not the engine's pitch proof.
- Use only the chord shapes the returned score uses. Do not invent suffixes to ask for
  advanced harmony. Put voicing requests in `style`; they remain a request, not a guarantee.
- Do not add `w:` lyric lines, a chord-voicing staff, tuplets, repeat signs, alternate
  endings, grace notes, decorations or custom directives. If the task needs them, say the
  native format is the limit and keep the change inside the format.

## Edit and check

1. Copy the source to a new file. Keep the original unchanged.
2. Make one musical change in the intended bars.
3. Compare the source and the edit as events: per voice, pitch, onset, duration, ties, meter
   and tempo. A string comparison says nothing about whether the melody moved.
4. If the contract allows rhythm or pitch changes, read the differences instead of calling an
   exact comparison a failure. Report the permitted differences.
5. Send the complete edited score as `abc` with `mode: "generate"` and `cot: "full"`. Use
   `melody` only when the score is melody-only and the harmony should be free.
   A supplied score requires full or melody planning.
6. The result preserves the supplied ABC text for a non-instrumental render. Instrumental
   rendering can move the vocal melody, so compare the returned score when that matters.
7. Listen to the changed passage and its entry and exit, and to the full song. A correct
   score check does not prove the performance followed it.

A same seed makes a comparison easier to trace. It does not hold the performance steady.

## Lyric changes

Edit the words in the request, not inside the ABC. Check every sung line against the vocal
notes: syllable count, stress, the vowel on a held note, consonant density on short notes and
breathing rests.

For a translation, adapt the line to sing rather than translating word for word. Keep a
sidecar mapping if you need to review syllable placement. It is not an engine input and does
not prove the engine used it. A word can span several notes, and one phoneme is not one note.

## Limits

A score accepts up to the server's `max_score_characters` (100000 on YuE2). A render starts a
new operation and takes the same single GPU slot as any other run. If the operation fails
with a generation limit, shorten the lyrics or choose another seed. Do not cut the score and
call the remainder the edit.
