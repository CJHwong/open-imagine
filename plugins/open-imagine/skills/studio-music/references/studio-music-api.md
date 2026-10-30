# Open Imagine Music API

Use live discovery as the contract. The examples below show transport and workflow. Choose
the actual backend, modes and limits from the running server.

## Discover without changing selection

| Route | Read for |
|---|---|
| `/api/v1/state` | The one active operation across all media modes |
| `/api/v1/studio` | `music.active`, `music.backends`, `music.capabilities` |
| `/api/v1/music/capabilities` | The selected Music backend's contract |
| `/api/v1/music/backends/{id}` | A listed backend's contract without selecting it |
| `/api/v1/openapi.json` | Request schemas and named examples |
| `/api/docs` | Rendered API documentation |

Take `modes`, `planning_modes`, `synthesis_steps`, `transcription_tasks`, `max_batch`,
`max_style_characters`, `max_lyrics_characters`, `max_score_characters` and
`max_reference_bytes` from the response. A listed backend is not proof that its weights are
installed. Do not change the user's model.

## Submit a music request

POST JSON to `/api/v1/operations` with `kind: "music"`. The music route
`/api/v1/music/generate` accepts the same body without `kind`. Omit `backend` to use the
active Music backend, or name one from the discovery response.

| Field | Meaning |
|---|---|
| `mode` | `generate` (default), `plan`, `transcribe`, `cover` |
| `style` | Arrangement, mood, instruments, vocal character, language and tempo |
| `lyrics` | Sectioned words. Blank only with `instrumental: true` |
| `cot` | Planning: `full` (default), `melody`, `off` |
| `abc` | Supplied score text. Generate only; requires `full` or `melody` |
| `instrumental` | `true` for an instrumental. Required when lyrics are blank |
| `steps` | 8, 16 or 32 synthesis steps. Default 32 |
| `cfg_scale` | Style guidance from 0 to 5. Default 1 |
| `seed` | One integer. Omit, null or an empty string for a random seed |
| `reference_audio` | Raw base64 audio bytes, at most 32 MiB decoded |
| `reference_name` | A label only, never a path or a URL |
| `transcription_task` | `full`, `melody-full` (default) or `melody-vocal` |
| `items` | Several takes in one operation. Each item may override `seed` |

Rules the server enforces:

- Transcribe needs `reference_audio` and no style or lyrics.
- Cover needs `reference_audio`, style and lyrics or `instrumental: true`.
- Cover and Transcribe reject a non-empty `abc`.
- A supplied `abc` requires `full` or `melody`. Direct generation has no score.
- Instrumentals require `full` or `melody`.

## Example bodies

A song:

```json
{
  "kind": "music",
  "style": "English, warm piano pop, clear female vocal, acoustic piano, rounded bass, light drums, 88 BPM",
  "lyrics": "[Verse]\nNeon fades along the lane\nFootsteps keep the time of rain\n\n[Chorus]\nLet the day come into view\nEvery road begins with you",
  "cot": "full",
  "seed": 42
}
```

An instrumental:

```json
{
  "kind": "music",
  "style": "Instrumental, solo acoustic piano, lyrical and gentle, unhurried phrasing, 72 BPM",
  "lyrics": "",
  "instrumental": true,
  "steps": 32
}
```

A supplied score: send the complete ABC as `abc`, keep `cot` at `full` or `melody`, and send the
style and lyrics the performance should follow. To render the score of an existing recording,
use `mode: "cover"` with `reference_audio` instead, because that path reads the recording.

A transcription: send `mode: "transcribe"`, `reference_audio`, and a `transcription_task`. The
result is JSON with a score and exports, not audio.

## Follow the operation

Assign a unique `client_id` per submission and keep the exact request. Save the returned `id`
and `status_url`. Poll at about two seconds. Terminal statuses are `succeeded`, `failed` and
`cancelled`; `running` and `stopping` are not finished.

One operation runs on the server. A `409` busy response creates no queued request. Wait or
report it. Cancel only your own operation, with `POST /api/v1/operations/{id}/cancel`.

If a POST times out, read `/api/v1/state` and look for your `client_id` before resubmitting.
The request may have been accepted. Report an ambiguous match instead of creating a second
run.

## Read the result

- Audio results use `content-type: audio/wav`, 48 kHz, stereo.
- Plan and Transcribe results are JSON with `score`, `metadata`, `seed`, `seconds: 0`,
  `sample_rate: 48000` and `stub`.
- `GET /api/v1/operations/{id}/metadata` returns the score, seed, sample rate, duration, mode
  and engine details. It also follows the private-key rule.
- A batch result is a manifest with `items`. Fetch each item's own `result_url`. Indices start
  at one. Completed items can be fetched while later items run.

Save the audio, the score and the metadata promptly. Public results stay in server memory for
ten minutes and disappear on restart. Restarting the server clears public history.

## Private work

Check `private_operations: true` in `/api/v1/studio` before submitting private work. Send a
random `X-Studio-Private-Key` of 32 to 512 visible ASCII characters on the operation and on
every follow-up: status, result, metadata, cancel and delete. Private results stay encrypted
for one hour after completion and survive a restart. Without the key they answer `404`.
Never print the key or put it in a URL. Downloaded private files become plaintext on the
client machine, so choose the folder deliberately.

## Errors

- `400`: the body names the field and the reason. Fix the request; do not retry it unchanged.
- `404` or `410`: a missing, finished or expired operation or result.
- `409`: the server is busy, or a result is not ready.
- `503`: the backend or the JSON API is unavailable.

Read the response body. A progress counter is not a terminal status.
