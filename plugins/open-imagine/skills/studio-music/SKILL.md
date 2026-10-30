---
name: studio-music
description: Create songs, instrumentals, covers and scores with Open Imagine's Music API. Write and adapt lyrics, choose planning and an ABC score, transcribe a recording, edit a score while preserving the melody, and compare takes by listening. Use for song requests, first songs, lyric writing, instrumental cues, covers, reharmonization, score editing, shuffled song sets and listening comparisons, and when the user does not know where to start and wants to be guided; also for 歌曲生成, 純音樂, 翻唱, 轉譜, 改譜 and 歌詞改寫.
---

# Studio Music

Turn a musical request into a playable song and an honest comparison. Operate the user's
Open Imagine server through its public Music API. Discover the backend's capabilities instead
of assuming a particular checkpoint. Requires a reachable server and tools for HTTP, saving
audio, and listening.

## Choose the path

| Request | Path |
|---|---|
| A song from words and a style | Generate with planning `full` |
| A melody first, with free accompaniment | Generate with planning `melody` |
| A song without symbolic planning | Generate with planning `off`; no useful score |
| An instrumental | Generate with `instrumental: true` and blank lyrics |
| Sheet music only | Plan: a score, no audio |
| A new performance of a recording | Cover: reference audio plus style and lyrics |
| A score from a recording | Transcribe: reference audio, a score, no audio |
| A score you provide or edited | Generate with `abc`, planning `full` or `melody` |
| Change harmony, instruments, tempo or words | Keep the source, edit the score or lyrics, generate a new version |
| Compare versions | Same seed where possible, then listen to both |

A supplied score needs `full` or `melody` planning. Cover and Transcribe reject `abc`.
To cover a melody you already have as ABC, use Generate with `abc` and `melody` planning.
An instrumental render can move vocal melody into the instrumental part, so the returned
score can differ from the one you sent.

## If the user does not know where to start

A short or vague request ("make me a nice song", "something for my video"), or a user who says
they do not know where to start, takes the [first-song guide](references/brief-to-song.md).
It asks at most three plain questions, offers four named directions, drafts a short lyric when
the user has none, and makes one take. Keep planning words, seeds and scores out of that first
conversation. A user with a full brief continues below.

## Start from capabilities

Read [the Music API notes](references/studio-music-api.md) before submitting work. Use the
user's server URL; otherwise try `http://127.0.0.1:8765`. Read `/api/v1/studio`,
`/api/v1/music/capabilities` and the live OpenAPI document. Take `modes`, `planning_modes`,
`synthesis_steps`, `transcription_tasks`, `max_batch` and the character limits from the
server, not from this file.

One operation runs at a time. A `409` creates no queued request: wait or report it. Never
cancel another caller's operation to get a turn. Do not start, stop or restart the server.

## Write the request

Read [prompt craft](references/prompt-craft.md) for the style sentence, lyric sections and
tested examples. In short:

- Style names the language, genre, mood, instruments, vocal character and intended tempo in
  full sentences. A genre word alone is thin.
- Lyrics carry section tags and actual words. Keep production notes and arrangement
  instructions out of the lyrics.
- For an instrumental, leave the lyrics blank and send `instrumental: true`. Blank lyrics
  alone do not select it in the API.
- A supplied seed is one integer. Omit it for a random seed. A same-seed pair helps trace a
  comparison; it does not hold every acoustic detail steady.
- `steps` is 8, 16 or 32. Style guidance is 0 to 5 with 1 as the default. Do not lower either
  value to hide a failure; say what changed.
- Several takes use `items` on the public API. They run one after another, not in parallel.
  The page's Variations control sends the same shape. Read the batch shape in the API notes.

## Follow the operation

Submit, save the `id` and `status_url` immediately, then poll at about two seconds. Terminal
statuses are `succeeded`, `failed` and `cancelled`. Read the `error` when present. A progress
counter that reaches the end does not prove success.

Save the audio and metadata promptly. Public results stay in server memory for ten minutes;
private results stay encrypted for one hour. Keep the exact request, seed, mode and planning
with each saved file.

A generation that reaches its token limit fails instead of publishing a partial song. Treat
that as a failure, report it, and shorten the lyrics or choose another seed. Never present an
incomplete take as a finished song.

## Work with the score

Plan returns a score with no audio. Generate with `full` or `melody` planning returns a score
next to the recording. Direct generation may return no useful score. Read the returned
`score`, not only the engraved page.

Read [score editing](references/score-editing.md) before changing a score. Keep the source,
state the invariants, edit the ABC text, and send it back with Generate. Compare musical
events, not characters. The browser's **Edit score** action does the same thing the API
does: it loads the returned score into a new Generate request.

## Covers and transcriptions

Reference audio is raw base64 bytes, at most 32 MiB. Do not send a filename, a local path or a
URL. `reference_name` is only a label.

- **Transcribe** returns a score and its exports, with no audio. Choose the task: `full` for
  melody and chords, `melody-full` for vocal and instrumental melody, `melody-vocal` for the
  vocal line alone.
- **Cover** needs style and lyrics, or an instrumental. It makes a new performance from the
  source. It does not clone the singer, preserve the waveform or remove an instrument.
- Inspect a transcription before blaming the renderer. A wrong note or a wrong meter can come
  from the transcription.

## Play a shuffled set

When the user wants a set of songs rather than one, read the [shuffle guide](references/shuffle.md).
Write a `prompts.jsonl` list, then run `scripts/shuffle.py --prompts ... --out ... --tracks N`.
The script submits one generation at a time, saves each result, plays it, and starts the next.
The track count is the stop. A per-track duration is not a request field.

## Deliver

Give the user playable audio, the exact style and lyrics, the returned score, the seed, the
mode, the planning, and any truncation flags. Listen when the environment allows it. Say
which checks you heard and which you only checked on paper. Read [delivery](references/delivery.md)
for the evidence table and the report.

Do not claim exact note realization, singer identity, instrument removal or waveform
preservation from a score check, a successful operation or a clean engraving. A playable file
is not proof of musical quality. Keep failed, truncated and rejected takes visible.

## Words used here

- **Planning**: the `cot` value: `full`, `melody` or `off`.
- **Score**: the ABC text returned by the engine.
- **Cover**: a new performance of a recording or a supplied melody.
- **Transcribe**: a score read from a recording.
- **Invariant**: what an edit must keep, such as exact pitches or a recognizable theme.
