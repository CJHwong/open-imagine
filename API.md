# Studio API

The API and page use the same controllers, model checks, download policy, and shared model memory.
Qwen remains at full precision. Selecting a model does not load its weights.
Official Qwen Turbo temporarily raises the MLX wired-memory budget during Generate, Edit, and batch prompt preparation, bounded by MLX’s recommended working set and 75% of physical RAM. It synchronizes outstanding work and restores the previous process limit after success, failure, or cancellation. This internal memory policy also applies to UI requests; it adds no request parameter and changes no sampling settings.

## Discover controls

Read `GET /api/v1/studio` before a run. It describes the selected image, video, Voice, and Music models.
Each capability record declares its supported modes and controls.
These can include sizes, limits, Looks, templates, and effects.
The rendered API reference is at `/api/docs`, with endpoint search and request examples.
The complete OpenAPI document remains at `/api/v1/openapi.json`.
The rendered view loads a pinned Swagger UI asset from a CDN.

| Action | Route |
|---|---|
| Read shared status and recent operations | `GET /api/v1/state` |
| Start an asynchronous operation | `POST /api/v1/operations` |
| Read one operation | `GET /api/v1/operations/{id}` |
| Read its output | `GET /api/v1/operations/{id}/result` |
| Cancel that operation | `POST /api/v1/operations/{id}/cancel` |
| Select an image model | `POST /api/v1/images/backend` with `{"backend":"qwen21_turbo"}` |
| Read Music controls | `GET /api/v1/music/capabilities` |
| Read another Music model without selecting it | `GET /api/v1/music/backends/{id}` |
| Select a Music model | `POST /api/v1/music/backend` with `{"backend":"yue2"}` |
| Read Music score and metadata | `GET /api/v1/operations/{id}/metadata` |
| Select a video model | `POST /api/v1/videos/backend` with `{"backend":"ltx25_mlx"}` |
| Release model memory | `POST /api/v1/memory/release` |
| Read rewrite progress | `GET /api/v1/rewrite/state` |
| Check an image request and estimate its time | `POST /api/v1/images/plan` |
| Check a video request and estimate its time | `POST /api/v1/videos/plan` |

Existing synchronous generate, edit, rewrite, progress, and cancel routes remain available.
A synchronous image request returns JSON with base64 PNG images. A video request returns MP4 bytes.
A video stub returns JSON metadata instead of an encoded file.

## Start and observe work

```sh
curl -sS http://localhost:8765/api/v1/operations \
  -H 'Content-Type: application/json' \
  -d '{"kind":"video","backend":"ltx25_mlx","prompt":"A red sailboat crosses calm water. Fixed camera.","width":384,"height":384,"num_frames":121,"frame_rate":24,"seed":7,"enhance":true}'
```

The response uses status `202` and names the operation with `id`.
Use that ID in the status, result, and cancel routes.
Image operations use `kind: "image"`. Prompt rewrites use `kind: "rewrite"` and `workspace: "image"` or `"video"`.

| Operation status | Meaning |
|---|---|
| `running` | The server prepares the model or runs it. |
| `stopping` | The server has accepted cancellation and waits for the engine to stop. |
| `succeeded` | The complete output is ready. |
| `failed` | The operation failed. Read `error`. |
| `cancelled` | Cancellation ended the operation. Partial images can remain available. |

Wait for `succeeded` before treating a video as complete.
The sampler can reach its last step while decoding and saving continue.
The page shows at most 99% during this interval.

Only one operation runs at a time. A conflicting request returns `409`; the server has no queue.
A stale cancellation also returns `409` and cannot stop a newer operation.
A missing model follows the page's policy: download when configured, otherwise fail with the same reason.
An accepted asynchronous request can fail later. Read its terminal status and error.

## Private operations

Send `X-Studio-Private-Key` when another person or program must not see your work.
Use a random key of 32 to 512 visible ASCII characters, and send the same key on every route.

```sh
curl -sS http://localhost:8765/api/v1/operations \
  -H 'Content-Type: application/json' \
  -H "X-Studio-Private-Key: $STUDIO_PRIVATE_KEY" \
  -d '{"kind":"image","prompt":"A red teapot on a wooden table.","client_id":"job-1"}'
```

The studio keeps the SHA-256 of the key, not the key.
`/api/v1/studio` reports `"private_operations": true` when the server supports this.

| What | A private operation |
|---|---|
| Prompt, settings, library | Not in the record. The record shows `""` and `{}`, and `private: true` |
| Batch item list | Lists each item without its prompt or settings |
| Status, result, cancel | Answer only the same key. Any other caller gets `404` |
| `/api/v1/state` | Lists the operation only for the same key. Other callers see `busy: true` |
| Result | Encrypted on disk. Repeated downloads work until deletion or expiry |
| Batch item result | Encrypted on disk. Each item supports repeated downloads |
| Expiry | One hour after completion. Downloads do not extend it |
| Server restart | Completed private results remain available with the same key |
| Delete | `DELETE /api/v1/operations/{id}` with the same key removes the operation and every result |
| The page | Never shows it, because the page has no key |

Private results use authenticated encryption with a separate key derived from the caller's original key.
The authentication hash cannot decrypt the result. The server keeps the encryption key only while the operation runs.
The database is `~/.local/share/open-imagine/private-results/private-results.sqlite3`, with owner-only file permissions.
Use `--private-results-dir <folder>` to select another folder. One server can own each folder.
Stub servers use isolated storage unless this option selects a folder.
Its operation records contain redacted metadata and the authentication hash. Result bodies and batch manifests are encrypted.
After a restart, interrupted operations show `failed`; completed items remain readable until expiry.
Stored errors use a generic message, so engine errors cannot put private words into disk metadata.
Every read under `/api/v1/` accepts the key, and `/api/v1/state` uses it.
A write accepts it on `POST /api/v1/operations`, the cancel route, and the private operation delete route.
Any other write, and every route outside `/api/v1/`, answers `400` when the header is present.
A stop from the page still stops a private run, because one GPU serves all callers.

### What a run still holds

The record keeps none of your words, but the run needs them.
These copies stay on the studio machine. No HTTP answer to another caller contains them.

| Copy | How long it lasts |
|---|---|
| Prompt and inputs in the engine's memory | Until the run ends |
| Scratch files in the system temp folder, from FLUX3, Qwen edit, LTX video, voice, Music reference transcription and the video prompt enhancer | Until the run ends. A crash or `kill -9` can leave them |
| The prompt on the command line of an LTX video child | Until the clip is done. The process list shows it |
| Music reference transcription score and exports in worker memory | Until another reference/task replaces them or the worker unloads |
| The encoding of each prompt in the Qwen engines' `prompt_cache`, with the prompt text as its key | Until the model unloads |

The key keeps your work from other callers.
It does not keep your work from a person who can read the memory, disk or process list of this machine.

## Prompt aids and reference inputs

Send `looks` as a mapping from each offered row name to one option label.
The API appends the corresponding text after the prompt. Image Looks also apply their declared avoid text.

Send `template` as an offered template name.
Send `template_values` as a mapping from bracket names to replacement text.
For example, `[subject]` uses `{"subject":"a blue teapot"}`.
Unknown options and missing replacements fail explicitly.

An image edit accepts `references` as base64 strings or objects with `png_base64`.
Data URLs also work. With `each_reference: true`, `per_reference_prompts` accepts one instruction per reference.
The master prompt leads each instruction. Looks come last.
API `count` names the total output count. Repeat reference instructions in order when that count exceeds the reference count.
A region edit appends the prepared mask as the final reference and sets `mask: true`.
Use the same numbered-image references in the prompt that the model capabilities support.

A video accepts image keyframes, an audio track, or an effect clip as declared by its mode.
Keyframes use `references: [{"name":"first.png","image":"<base64>","frame_index":0,"strength":1}]`.
Audio uses `audio: {"name":"voice.wav","data":"<base64>"}`.
An effect edit uses `kind: "video"`, `mode: "edit"`, `adapter`, `adapter_strength`, and `clip`.
The clip uses `{"name":"source.mp4","data":"<base64>"}`.
Read available adapter IDs and geometry from the selected video capabilities.

Browser tools prepare media inputs: region masks, trimmed clips, and captured frames.
The API accepts those prepared inputs. Theme and Keep preferences remain in the browser.

## Tabs and retained results

Every visible tab reads shared server status from startup.
Visible tabs poll every five seconds while idle and every 350 milliseconds during generation.
Hidden tabs stop shared polling and refresh immediately when visible.
The server continues running jobs after a tab becomes hidden.
Tabs show API operations, matching cancellation, failures, and completed results.
An API rewrite appears separately until you choose Use prompt, so it does not replace an unfinished draft.
Model selection also reaches other tabs without replacing their prompt text.

Browser results enter tabs within the same browser library. API results are available across libraries.
All libraries observe the shared operation status.
Removing a browser result suppresses automatic reimport without deleting the retained server result.
Clear all also suppresses completed historical results. Outputs that complete afterward remain available.
Each image includes `completed_at`, the Unix time when that image completed.
Native video responses include the same completion time in `X-Studio-Completed`.
The browser uses completion times to reject old results whose responses arrive after Clear all.

Public results remain in server memory for up to 10 minutes after completion.
Retention also has limits of 32 operations and 256 MiB, including metadata.
Older results can expire sooner when either limit fills. Missing results return `404`.
A server restart clears public operation history. Private results remain encrypted on disk for one hour. The existing Keep setting controls browser storage independently.
The server checks expiry during requests and once per minute in the background.
Requests reject expired results immediately. Background deletion can follow expiry by about one minute while the server runs.
Startup removes expired private results.

A browser Image batch submits ordered items to the same prepared batch use case as this API. One reservation covers preparation and every image; completed items appear incrementally and survive reload or cancellation. Per-reference UI edits expand into one-reference items with their own prompts and consecutive seeds. Single-image form requests retain their compatibility transport.
Prepared UI and asynchronous API batches run entirely on the server, including after their tab closes.
Only legacy compatibility batches that wait for a client continuation cancel after a 30-second continuation timeout.
Completed images remain available.

## Choose a useful request

The rendered reference offers named examples in each request editor.
Select an example before you press **Try it out**.
Schema placeholders such as `string` do not describe a useful prompt.

For image or video templates, send the template name and its named values.
Do not copy the template text into `prompt`.
Use the exact field names, including capitalization.
This request uses the measured camera template:

```json
{
  "kind": "video",
  "backend": "ltx25_mlx",
  "template": "Slow push-in",
  "template_values": {
    "Subject": "A blue ceramic teapot",
    "surface": "a wooden table",
    "Foreground object": "A red cup",
    "background object": "a green plant",
    "subject name": "the teapot",
    "light": "Soft daylight enters through a window",
    "sound": "quiet room tone"
  },
  "width": 384,
  "height": 384,
  "num_frames": 121,
  "frame_rate": 24,
  "seed": 7,
  "enhance": true
}
```

For a video effect, read the adapter record before you build the request.
Its prompt, strength, geometry, and frame count form one recipe.
A deblur trigger cannot replace a scene instruction for another effect.
Use the named `deblur` or `day_to_night` example for specialized effects.
For a freeform Video Edit without a task LoRA, choose `adapter: "custom"` and supply your
own prompt and clip. No LoRA file or download is needed. Choose a supported shape nearest
the input clip and snap its length to the frame grid; Custom declares zero geometry in
discovery because it does not impose an effect-specific size or duration.
The `custom_no_lora` example includes the complete payload.
Custom is experimental; source fidelity and edit adherence are not yet validated on the real model.

## Encode actual media

Angle-bracket values in examples require replacement. They are not valid encoded media.
The small PNG in image examples tests transport. It does not provide a useful scene.
Image references accept data URLs. Video keyframes, video clips, audio tracks, and Voice references require bare base64.

Use Python to encode file bytes without shell line wrapping:

```python
import base64
import json
from pathlib import Path

reference = base64.b64encode(Path("speaker.wav").read_bytes()).decode("ascii")
request = {
    "kind": "voice",
    "backend": "auk",
    "mode": "clone",
    "text": "Please bring my blue bag to the front desk.",
    "reference": {"name": "speaker.wav", "wav_base64": reference},
    "seconds": 0,
    "convert": "off",
    "seed": 7,
}
Path("request.json").write_text(json.dumps(request))
```

Submit the generated file:

```sh
curl -sS http://localhost:8765/api/v1/operations \
  -H 'Content-Type: application/json' \
  --data-binary @request.json
```

Use the same encoding step for a video keyframe's `image` or a clip's `data`.
A Voice reference must contain WAV bytes. Renaming an MP3 file does not convert it.

## Voice jobs

Read `GET /api/v1/voice/capabilities` for the active Voice model modes, settings, and templates.
Its `loading` record names the weight repository, pinned revision, and first-use download policy.
The model loads lazily. Missing cached weights download on the first Voice operation.
A synchronous `POST /api/v1/voice/generate` returns WAV bytes.
An asynchronous request uses `kind: "voice"` and the same fields.
Clone and edit require one WAV reference. Design requires `voice`.
References must stay within the published duration and byte limits.

Describe a designed voice in detail:

```json
{
  "kind": "voice",
  "backend": "auk",
  "mode": "design",
  "text": "The next train leaves from platform three. Please keep your ticket ready.",
  "voice": "A woman in her thirties reads a public announcement. Her voice sounds calm, clear, and warm. She speaks at a steady pace and medium volume, with a neutral American accent.",
  "seconds": 0,
  "convert": "off",
  "seed": 7
}
```

A short voice description can become spoken content. Use age, tone, pace, volume, and accent.
`seconds: 0` chooses duration from the text for clone or design.
For edit, zero keeps the reference duration. Structured templates can apply their declared duration rule.
`convert: "tw2s"` converts Traditional Chinese characters before synthesis. It preserves Taiwan vocabulary.
Use `"off"` when the source text must stay unchanged.

Voice Design offers six templates: Voice profile, Conversation, Narration, Commanding delivery, Dramatic character, and Emotional delivery.
Each template supplies four editable voice attributes. Omitted attributes use the declared defaults.
Explicit blank attributes fail validation. The spoken `text` remains separate.
A custom Design request supplies `voice` instead of a template. There is no default voice description.
Multiple sentences in one `text` form one continuous clip. Explicit `items` produce separate clips.

```json
{
  "backend": "auk",
  "mode": "design",
  "template": "Narration",
  "template_values": {
    "speaker": "documentary narrator",
    "subject": "an everyday discovery",
    "pace": "measured, unhurried",
    "tone": "warm and thoughtful"
  },
  "text": "The river flows past the quiet village. The first light reaches the bridge.",
  "seconds": 4,
  "convert": "off",
  "seed": 7
}
```

For a batch, set `kind: "voice"` and place each script and template in `items`.
Shared settings apply to each item. Each item can override its template and attribute values.

```json
{
  "kind": "voice",
  "backend": "auk",
  "mode": "design",
  "seconds": 4,
  "convert": "off",
  "seed": 7,
  "items": [
    {"text": "The river flows past the village.", "template": "Narration"},
    {
      "text": "I am glad you made it home.",
      "template": "Conversation",
      "template_values": {"emotion": "warmth and gentle concern"}
    }
  ]
}
```

Designs can produce different speakers. Clone one saved WAV when the script needs a consistent speaker.

The Design structures adapt the [official cookbook](https://github.com/Tencent-Hunyuan/AuK/blob/9481474f107ee4d8dec959b3aed05b0627cebbf8/docs/COOKBOOK.md#12-instruct-tts)
and [official demo descriptions](https://github.com/Tencent-Hunyuan/AuK/blob/9481474f107ee4d8dec959b3aed05b0627cebbf8/src/auk/infer/infer_gradio.py#L25).
These sources describe the structures. They do not prove this application's output quality.

Voice edit templates use `{field}` placeholders and declare their fields separately.
Send the exact template name and its values. The server compiles the instruction.
The Speed template divides the decoded reference duration by its speed value when `seconds` is zero or absent.
An explicit positive `seconds` value overrides that rule.

```json
{
  "backend": "auk",
  "mode": "edit",
  "template": "Speed",
  "template_values": {"speed": "1.5"},
  "reference": {"name": "speaker.wav", "wav_base64": "<replace with base64 of your WAV>"},
  "seconds": 0,
  "convert": "off"
}
```

Use the declared field names, types, choices, and limits.
Offered defaults apply to omitted numeric and choice fields. Supply required text fields.
Unknown names, unknown fields, and invalid values return `400`.
Raw `text` stays available. Raw speed instructions need explicit `seconds` to change the output duration.
For example, the Enhance template compiles this instruction:

```text
Preserve all speakers, remove noise and reverberation, and output clean speech of the same length.
```

The Voice page generates one continuous clip by default.
The UI generates one continuous clip. Use explicit API items for independent clips.
Each batch press submits the next 16 pending sentences, or the remaining count when smaller.
The next press reuses the first designed voice for the same description and character conversion.
The public API still accepts at most 16 items per operation.

## An agent's request procedure

1. Read the current model capabilities and shared status.
2. Choose the exact backend and mode that support the requested inputs.
3. Check parameter limits, reference limits, frame grids, and offered prompt aids.
4. Use an offered template when it matches the requested scene or camera move.
5. For effects, use the adapter's recipe instead of a generic edit prompt.
6. Encode actual media bytes and replace every media placeholder.
7. Submit one asynchronous operation and save its returned status URL.
8. Poll that URL until the status becomes terminal.
9. Fetch retained outputs, including completed partial outputs after failure or cancellation.
10. Save the outputs before retention expires.

A busy response does not create a queued operation. Wait for the active operation to finish before retrying.
Never interpret an engine's 100% sampler progress as a completed operation.

## Ordered batches

Send `items` to run distinct jobs under one operation.
The batch uses one backend and one media kind: `image`, `video`, `voice`, or `music`.
Top-level fields supply defaults. Each item can override its prompt, seed, settings, or media.
Each item produces one output. Set `count` to one and keep `each_reference` false.
A batch accepts 1 to 16 items and runs them in order.

For image variations of one prompt, the existing `count` field remains simpler.
For distinct scenes, use the named `image_storyboard` or `video_shots` examples.

This Voice batch shares one reference across two segments.
Replace the placeholder with actual WAV bytes:

```json
{
  "kind": "voice",
  "backend": "auk",
  "mode": "clone",
  "reference": {
    "name": "narrator.wav",
    "wav_base64": "<replace with base64 of your WAV>"
  },
  "seconds": 0,
  "convert": "off",
  "seed": 7,
  "items": [
    {"text": "First, place the blue cup on the table."},
    {"text": "Next, pour the tea slowly and serve.", "seed": 8}
  ]
}
```

For a new narrator, use a detailed shared `voice` description and `mode: "design"`.
The batch designs each distinct voice description and character conversion setting once.
Later design segments with matching settings clone that voice.
This keeps the speaker consistent across the batch.
For later operations, save the first WAV and supply it as a clone reference.

Read `batch_index` and `batch_total` from shared operation status.
The retained result is a manifest with `items`, `completed`, and `batch_total`.
You can read that manifest while the batch runs. Fetch each available item without waiting for later items.
A running single job still returns `409` from its result route.
Each completed item names its own `result_url`. Item indices start at one.
Its `prompt` contains the text sent to the engine after template and Look composition.
For Voice, this is the validated requested text or compiled edit instruction. It is never a transcript.
Its `settings` preserve the requested fields, including the original template and Look selections.
An item result returns image JSON, MP4, or WAV according to its kind.
Fetch completed items after cancellation or failure. A later failure does not discard earlier outputs.

## Inspect another model

The backend lists in `/api/v1/studio` name available model IDs.
Read an inactive model's capabilities without changing shared selection:

```text
GET /api/v1/images/backends/{id}
GET /api/v1/videos/backends/{id}
```

These routes do not load weights or switch the active model.
Use them to compare supported modes, prompt aids, effect recipes, and parameter limits.
Then submit the chosen `backend` in the generation request.

## Plan a request

Send the body of a run to `POST /api/v1/images/plan` or `POST /api/v1/videos/plan`.
One route serves both modes, so add `"mode": "edit"` to the body of an edit.
The server runs the same checks as the run, but it does not run the model.
It does not switch the active model, take the GPU, or record an operation.
It answers while another run holds the GPU.

```sh
curl -sS http://localhost:8765/api/v1/images/plan \
  -H 'Content-Type: application/json' \
  -d '{"backend":"qwen21_turbo","mode":"edit","reference_sizes":[[1536,1024]],"count":2}'
```

```json
{
  "backend": "qwen21_turbo",
  "mode": "edit",
  "count": 2,
  "effective_options": {"resolution": "match", "steps": 8, "cfg": 1.0, "negative": ""},
  "estimate": {
    "basis": "constants",
    "steps": 8,
    "width": 1536,
    "height": 1024,
    "reference_count": 1,
    "per_item_seconds": 70.3,
    "setup_seconds": 0.0,
    "total_seconds": 140.7,
    "excludes": ["weight download", "model load", "queue wait"]
  }
}
```

A request that the run refuses gets the same `400` error from the plan.
A model that the studio does not offer also gets `400`.
An image plan for more than 16 images gets `400`, because a JSON run stops at 16.

| Field | Meaning |
|---|---|
| `count` | The images or clips that the request makes. One result for each reference multiplies it. |
| `effective_options` | Every setting of the mode, with each default filled in. Send it back to the run as it is. |
| `estimate.basis` | `constants`, `provisional`, or `unavailable`. |
| `estimate.total_seconds` | The time of the whole request, or `null` when the basis is `unavailable`. |
| `estimate.excludes` | The time that the figure does not hold. |

A plan needs no prompt and no media.
For an image, send `reference_sizes` as `[width, height]` pairs in place of `references`.
For a video, send `reference_count` in place of `references` and `has_audio` in place of `audio`.
An edit plan needs no clip.

An image figure is the figure that the page shows under the run button for a fresh tab.
It uses the same constants and the same formula.

A video figure is `provisional`. It comes from a fit to recorded runs on one machine.
Expect an error of about 10 to 40%. The fit counts these parts of a clip:

- The latent tokens of the clip, from its size and frame count.
- The steps of the two stages, and the decode.
- The prompt enhancer, unless the request sends `enhance: false`.
- Each LoRA, at about 10 seconds.
- The guided path for an audio track, and for a keyframe on LTX-2.3. This path costs about 2.5 times more.
- For an edit, a fit over the tokens of the output, times the effect's own `cost_factor`. An edit never costs less than the model loads.

The figure counts Fast mode at the default speed and adds `Fast mode speedup` to `excludes`.
No run measured the time that Fast mode saves.
The constants are in the `estimate` field of each video model's capabilities.

## Cut an audio selection

`POST /api/v1/audio/trim` cuts a WAV recording without a model or generation operation.
It also runs while the studio generates another result.

```json
{
  "audio": {"name": "speaker.wav", "data": "<bare base64 of your WAV>"},
  "start_seconds": 0.25,
  "end_seconds": 1.25
}
```

The response is `audio/wav`. It preserves the sample rate, channel count, sample width, and selected PCM bytes.
`X-Studio-Duration` gives the exact output duration after sample rounding.
The rendered reference includes a complete named example with real WAV bytes.

Inputs must use uncompressed PCM with 1 to 4 bytes per sample.
The limits are 32 MiB decoded and 120 seconds.
Both bounds must be finite numbers within the source duration.
The end must follow the start. The selection must include at least one sample frame.
The server uses `round(seconds * sample_rate)` for each boundary.
Invalid requests return status `400` with the existing JSON error shape.

## Select a Voice model

Voice offers `drama3` (Drama-3, the default), `auk_base` (AuK), and `auk` (AuK Flash).
Flash uses 4 steps. AuK uses 32 steps and the upstream guidance setting.
The two AuK variants share their modes and templates. Drama-3 declares Generate and Clone; all three support ordered batches.

```json
{"backend": "auk_base"}
```

Send that payload to `POST /api/v1/voice/backend`.
Selection releases the previous model but loads no weights.
`GET /api/v1/voice/backends/auk_base` reads capabilities without selecting or loading it.
Shared state reports the selected model across tabs.

A generation request can set `"backend": "auk_base"` directly.
The server selects that model before the run, and each result records the actual model.
One batch uses one model. A request cannot switch models between its items.
A model switch returns `409` while an operation is active.
The first AuK run downloads about 1.75 GB beyond the shared Flash files, if those files are cached.


## Drama-3 speech

Read `GET /api/v1/voice/backends/drama3` without loading the model. Its default mode is `generate`; AuK defaults to `design`. Omitting backend uses the active Voice model. Send an explicit backend for a reproducible request.

```json
{
  "kind": "voice",
  "backend": "drama3",
  "mode": "generate",
  "text": "[whispers] Keep your voice down. Someone is listening.",
  "temperature": 0.7,
  "top_p": 0.7,
  "top_k": 30,
  "max_tokens": 2048,
  "seed": 7
}
```

Use `POST /api/v1/operations` for asynchronous work, or `POST /api/v1/voice/generate` without `kind` for a synchronous WAV response. Drama-3 returns 44.1 kHz audio and chooses duration from the script. Its Templates target `text`, not `voice`. The selected engine does not expose Design, Edit, a target duration, or a generation-speed option.

Clone adds `"mode": "clone"`, `reference: {"wav_base64": "<actual WAV bytes>"}`, and `ref_text` containing the exact spoken reference words. References must be at most 15 seconds and 32 MiB. The adapter resamples API WAV inputs to native rate. A trimmed reference needs a corrected transcript. New scripts never become implicit references for later batch items.

A batch supplies `items: [{"text": "First line."}, {"text": "Second line."}]` under shared `kind`, `backend`, and optional reference/sampling settings. Up to 16 independent clips run in order with resident weights and cached reference conditioning. This preserves the same warm-engine advantage as consecutive single API calls; it is not parallel tensor batching.

Progress has an unknown total while Drama-3 generates. Do not derive completion from `max_tokens`: it is a safety cap per internal text chunk, and reaching it fails the operation. The server also rejects an entirely missing audio chunk. Short English synthesis, inline cues and cloning passed the initial checks. Unconditioned Chinese and a longer repeated English script hit the cap; treat them as measured limitations rather than guaranteed capabilities.

Drama-3 internally splits long scripts into 180-byte chunks and joins them into one continuous WAV. This is independent of the explicit API batch items and does not create extra gallery entries.

Drama-3 is the default Voice model and uses the pinned eight-bit MLX checkpoint. The UI automatically keeps the first 15 seconds of longer Clone references, including gallery selections and references carried over from AuK. Trimming clears a copied full-recording transcript: enter the exact words in the retained excerpt. API callers use `/api/v1/audio/trim` before submitting a reference longer than the model limit. Script and prompt fields expand while focused.

LTX Generate applies the pipeline's Gemma-3 prompt enhancer before video encoding by default, for both LTX-2.3 and LTX-2.5 and for audio-conditioned generation. LTX-2.5 still uses its Gemma-4 tower for text encoding. Send `"enhance": false` to skip this pass, for a prompt that must reach the engine word for word. The page always enhances, and Edit never does. The Video Rewrite endpoint/button uses the same native Gemma-3 enhancer, independently of the selected Image model. With references, it reads the first attached image through Gemma’s vision tower using LTX’s native I2V instructions. Later references remain video keyframes and are not passed to the enhancer. Audio is used by the video generator, not read by the enhancer. The server remembers up to 128 exact Rewrite outputs and the first reference image’s SHA-256 identity (or text-only conditioning) for its lifetime. Generate with unchanged output and the same first reference image skips duplicate enhancement; changed text (including appended Looks) or a different first reference image enhances again. This applies equally to UI, direct API calls and explicit batches. Restarting the server clears this cache. Edit adapters retain their supplied prompt unchanged. Eligible Generate batches group enhancement by checkpoint and text/image strategy, loading each group once and freeing it before the next; they release the enhancement process before rendering. Item and render order stay unchanged. Auto retains per-item generation for measured regressions, including the enhanced LTX-2.5 two-item 1920×1088, 17-frame, 24-fps text case. Eligible LTX-2.5 text batches reuse the video pipeline within its measured geometry/memory limits. Other Generate batches render clips sequentially after shared enhancement. Mixed Edit batches retain per-item execution. One operation reserves the engine throughout both phases; enhancement is preparation, not a completed result.

Each endpoint description now explains when to choose it, required discovery, how to use its output, and recovery choices. Start with `/api/v1/studio`, inspect a candidate's capabilities without switching models, then submit an operation and poll its status URL. Named template and adapter recipes are preferred when they match the task.

## Voice model contract and validation

Choose backend explicitly, then use only its discovered modes and parameters.

| Contract | Drama-3 (drama3) | AuK (auk_base) / AuK Flash (auk) |
|---|---|---|
| Modes / default | generate, clone / generate | design, clone, edit / design |
| No-reference speech | text with optional inline direction | text plus voice or a Design template |
| Clone | text, reference, exact ref_text | text and reference; no transcript required |
| Controls | temperature, top_p, top_k, max_tokens | seconds, convert; voice for Design |
| Reference / native WAV rate | at most 15 seconds / 44.1 kHz | at most 120 seconds / 24 kHz |
| Duration / progress | script-driven / indeterminate during synthesis | seconds=0 selects automatically / sampler steps |

Drama sampling defaults match the pinned MLX Audio implementation: temperature=0.7, top_p=0.7
and top_k=30. Studio sets max_tokens=2048 per internal chunk, increased from the engine default of
1024 to allow more completion headroom. It remains a ceiling, not a target length; looping output may
run longer before failing. These are implementation and product defaults, not a Fish Audio
recommendation established as best for every task. See the [pinned MLX source](https://github.com/Blaizzy/mlx-audio/blob/2209e6d76c18d0a24f7ff64d35b4176258acd909/mlx_audio/tts/models/fish_drama3/drama3.py).
AuK uses the upstream 32-step setting; Flash uses its fixed 4-step path. See the
[AuK inference implementation](https://github.com/Tencent-Hunyuan/AuK/blob/9481474f107ee4d8dec959b3aed05b0627cebbf8/src/auk/infer/infer_gradio.py)
and [official Flash setup](https://github.com/Tencent-Hunyuan/AuK/blob/main/docs/COMFYUI.md).
These settings have real-run coverage but have not been proven optimal by a systematic quality sweep.
Adapter chunking, voice-description wording and Chinese character conversion have targeted experimental
evidence; this does not establish universally best model settings.

Both use one model per ordered batch, at most 16 items, and the same operation/result/cancel contract.
The API checks supported modes, required inputs, declared parameter values, templates, seeds and decoded WAV limits.
Unknown top-level fields and parameters not declared by the selected mode are currently ignored, not rejected.
For example, seconds does not set Drama duration and temperature does not tune AuK. Do not rely on ignored fields.
Unknown template fields do reject the request. A supplied reference is rejected in modes that accept none.
Send backend and mode explicitly for schema validation: an omitted backend depends on server state and cannot
be fully checked by a static schema. Batch items inherit defaults; validate each merged item as a VoiceRequest.
Synchronous invalid requests return 400. Async 202 only acknowledges acceptance; inspect terminal status/error
for validation failures in the worker. API references over the model limit must be trimmed explicitly;
UI trimming is not applied to API payloads.

## Official Voice prompting references

Read the primary model guide first, then discover the selected Studio model/mode.
For Drama put spoken words and inline directions in text. For AuK Design put only spoken words in text and
speaker attributes in voice, or select an offered template. For AuK Edit put the change instruction in text
and supply reference.wav_base64. Never paste upstream ChatML, CLI commands, or hosted request envelopes into text.

The guides describe upstream systems too. Studio does not expose Fish hosted voice IDs/reference_id arrays,
multi-reference speaker casting, previous_takes/continuation editing, streaming responses, pronunciation
dictionary management, or an AuK Prompt Enhancer flag. Additional fields are ignored rather than enabling them.
Delivery/phoneme markup stays in the script passed to the local engine, but every upstream tag/language has
not been tested on the pinned MLX checkpoint. Language-switch markup is experimental upstream; local
unconditioned Chinese has measured completion failures. Prefer short probes and a clean reference where needed.
Upstream reference lengths, normalization controls, duration budgets and serving speeds do not override
Studio discovery. Links were checked 2026-10-22; current upstream pages may evolve beyond our pinned engines.

| Model | Reference | Scope and use |
|---|---|---|
| drama3 | [Drama-3 direction guide](https://docs.fish.audio/features/text-to-speech/drama-3) | primary: Delivery, sounds, pauses, word-scoped tags, language changes and phonemes. |
| drama3 | [Drama-3 model examples](https://huggingface.co/fishaudio/drama-3#example-usage) | upstream examples: Point cues and continuation editing; Studio does not expose continuation history. |
| drama3 | [English pronunciation](https://docs.fish.audio/developer-guide/core-features/fine-grained-control/english) | upstream syntax: CMU Arpabet notation; test the desired pronunciation on the pinned MLX model. |
| drama3 | [Chinese pronunciation](https://docs.fish.audio/developer-guide/core-features/fine-grained-control/chinese) | upstream syntax: Tone-number pinyin; local unconditioned Chinese has measured completion limitations. |
| drama3 | [Japanese pronunciation](https://docs.fish.audio/developer-guide/core-features/fine-grained-control/japanese) | upstream syntax: Romaji and pitch notation; not independently certified by Studio. |
| drama3 | [Recording a clone reference](https://docs.fish.audio/developer-guide/best-practices/voice-cloning) | shared recording advice: Recording quality; its hosted recording lengths do not override Studio's 15-second limit. |
| drama3 | [Emotion vocabulary](https://docs.fish.audio/developer-guide/core-features/emotions) | S2 background: Additional cue ideas. This page describes S2 and legacy S1; prefer the Drama-3 guide for syntax. |
| drama3 | [Fine control background](https://docs.fish.audio/developer-guide/core-features/fine-grained-control) | mixed-version background: Pronunciation and older control forms; avoid copying legacy parenthesis syntax into Drama scripts. |
| drama3 | [Fish documentation index](https://docs.fish.audio/llms.txt) | publisher index: Discover current canonical documentation; hosted API fields are not Studio fields. |
| drama3 | [Open-weight inference](https://speech.fish.audio/inference/#drama-3) | upstream runtime: Reference/transcript examples for the official runtime; Studio uses a separate MLX adapter. |
| drama3 | [Drama-3 serving cookbook](https://sgl-project.github.io/sglang-omni/cookbook/fishaudio_drama3.html) | model-card-linked integration: More request examples; reference limits, streaming and performance are specific to that runtime. |
| drama3 | [Drama-3 vLLM recipe](https://recipes.vllm.ai/fishaudio/drama-3) | model-card-linked integration: Alternative serving examples, not parameters accepted by this Studio. |
| auk, auk_base | [AuK instruction cookbook](https://github.com/Tencent-Hunyuan/AuK/blob/main/docs/COOKBOOK.md) | primary: Bilingual instructions across generation, editing, restoration and separation. |
| auk, auk_base | [AuK cloning and voice design](https://github.com/Tencent-Hunyuan/AuK/blob/main/docs/COOKBOOK.md#1-speech-generation) | task instructions: Map the target script to text and the designed speaker to voice; Studio builds the model instruction. |
| auk, auk_base | [AuK word and lyric edits](https://github.com/Tencent-Hunyuan/AuK/blob/main/docs/COOKBOOK.md#2-content-editing) | task instructions: Edit instructions; upstream lyric recipes have input requirements and are not all locally validated. |
| auk, auk_base | [AuK acoustic edits](https://github.com/Tencent-Hunyuan/AuK/blob/main/docs/COOKBOOK.md#3-acoustic-editing) | task instructions: Pitch, speed and volume instructions for Edit. |
| auk, auk_base | [AuK expressive edits](https://github.com/Tencent-Hunyuan/AuK/blob/main/docs/COOKBOOK.md#4-paralinguistic-editing) | task instructions: Emotion, timbre, accent, nonverbal sounds and whisper conversion. |
| auk, auk_base | [AuK restoration and isolation](https://github.com/Tencent-Hunyuan/AuK/blob/main/docs/COOKBOOK.md#5-enhancement--separation) | task instructions: Cleanup and source-isolation recipes; use an offered Edit template when available. |
| auk, auk_base | [AuK demo prompts](https://github.com/Tencent-Hunyuan/AuK/blob/main/src/auk/infer/infer_gradio.py) | publisher examples: Concrete English/Chinese instructions paired with example source audio and durations. |
| auk, auk_base | [AuK Prompt Enhancer](https://github.com/Tencent-Hunyuan/AuK#prompt-enhancer) | upstream tooling: Optional upstream instruction preparation; Studio does not expose this CLI tool or a PE request flag. |
| auk, auk_base | [AuK ComfyUI notes](https://github.com/Tencent-Hunyuan/AuK/blob/main/docs/COMFYUI.md) | upstream integration: Duration and Flash examples; ComfyUI's shared 30-second budget is not Studio's duration contract. |
| auk, auk_base | [AuK authors' audio demos](https://auk-project.github.io/) | authors' demonstrations: Listen to task examples; the site is maintained by the paper authors. |
| auk_base | [AuK model card](https://huggingface.co/tencent/AuK) | publisher model card: Base-model context and links; use Studio's pinned MLX settings rather than copying inference flags. |
| auk | [AuK Flash model card](https://huggingface.co/tencent/AuK-Flash) | publisher model card: Distilled variant context; Studio fixes the Flash sampler to four steps. |

## Official Image prompting references

For Qwen-Image-2.1 start with the [publisher model card](https://huggingface.co/Qwen/Qwen-Image-2.1),
[2.1 release examples](https://qwen.ai/blog?id=qwen-image-2.1), and
[official repository](https://github.com/QwenLM/Qwen-Image). These provide generation, editing,
text-rendering and transparency examples; they are not a separate comprehensive 2.1 prompt manual.
Describe the desired image concretely. In Edit, identify what changes and what should remain consistent;
when supplying multiple references, explain each image's role. For lettering, specify the exact words
and their placement. Use the model card's transparency wording only if the discovered local output path
supports the required alpha behavior; a prompt alone is not an output-format guarantee.

These sources describe the full upstream model. Studio's selected backend capabilities determine reference
counts, dimensions, alpha output and available controls. Turbo is a separate accelerated checkpoint:
do not copy the full-model step count into Turbo requests. Use discovered defaults and named API examples.
Prompt examples are guidance, not proof that every upstream task works on the pinned MLX engine.
References checked 2026-10-22.

## Official Video prompting references

Start with Lightricks' [prompting guide](https://docs.ltx.io/api-documentation/implementation-guides/prompting-guide)
for shot framing, visible action, characters, camera movement, lighting and audio. Describe action in time,
make camera movement relative to the subject explicit, and put spoken dialogue in quotation marks.
For one take use a flowing present-tense description; match the amount of action to the requested length.
The guide's multi-shot section is explicitly about LTX-2.5. Use a continuous shot for uninterrupted camera
movement or dialogue in one framing; do not assume 2.5-specific behavior transfers to 2.3.

| Reference | Scope and use |
|---|---|
| [LTX-2.3 model card](https://huggingface.co/Lightricks/LTX-2.3) | Version-specific upstream assets and examples. |
| [LTX-2.5 model card](https://huggingface.co/Lightricks/LTX-2.5) | Version-specific upstream assets and examples. |
| [Text-to-Video](https://docs.ltx.io/open-source-model/usage-guides/text-to-video) | LTX-2.5 workflow and prompting examples. |
| [Image-to-Video](https://docs.ltx.io/open-source-model/usage-guides/image-to-video) | LTX-2.5 motion from an opening image; upstream first/last-frame controls are not automatically Studio controls. |
| [Audio-to-Video](https://docs.ltx.io/open-source-model/usage-guides/audio-to-video) | LTX-2.5 supplied-audio conditioning; describe compatible visible action rather than contradictory dialogue. |
| [Workflow and asset compatibility](https://docs.ltx.io/open-source-model/reference/workflow-asset-compatibility) | Check 2.3 versus 2.5 compatibility before choosing an adapter. |
| [Publisher documentation index](https://docs.ltx.io/llms.txt) | Discover current guides and task-specific adapter instructions. |

The publisher covers hosted services, ComfyUI and native PyTorch. Studio uses pinned MLX pipelines:
its discovered modes, adapters, reference formats, frame counts and size limits are the API contract.
Hosted retake/extend/reframe, duration prediction, HDR and other upstream workflows are not enabled by
adding their fields to a Studio payload. Multi-shot prose does not create an API batch or guarantee cuts
on the pinned checkpoint. Studio enhances LTX Generate prompts by default, including 2.3 and 2.5;
send enhance=false to keep a prompt word for word. The page always enhances. Rewrite remains
a separate API operation. References checked 2026-10-22.

## Video Fast mode

LTX-2.5 offers optional Fast mode through `fast_mode: true`. Check the backend's `fast_mode`
capability before using it. It uses reduced transformer compute precision with the same q8
weights and sampling steps. Generated details and motion may differ even at the same seed;
speed varies by output size and conditioning. It is separate from Rewrite and prompt enhancement.

```json
{
  "kind": "video",
  "backend": "ltx25_mlx",
  "prompt": "A blue ceramic teapot on an oak table. Steam rises. Soft daylight, quiet room tone.",
  "width": 384,
  "height": 384,
  "num_frames": 49,
  "frame_rate": 24,
  "seed": 7,
  "fast_mode": true
}
```

POST this to `/api/v1/operations`, or omit `kind` for `/api/v1/videos/generate`.
The same field applies to image/audio-conditioned Generate and `/api/v1/videos/edit`; supply
that mode's normal references, audio, or clip/adapter fields. Omit it or send false to restore
default rendering on the next request, without restarting Studio. It must be a JSON boolean.
LTX-2.3 rejects true. A video batch sets it once at the top level; items cannot override it.
Operation `settings.fast_mode` records an explicitly submitted value. The UI names the option
Fast mode and records it with the result. Watching another client's operation temporarily shows
its setting while preserving the observer's own setting for the next render.

## LoRAs

A model that offers LoRAs lists them in `/api/v1/studio`. For an image model they are on each
mode, as `loras` and `max_loras`. For a video model they are on its capabilities, beside
`loras_with_audio`. The page calls them add-ons, and shows each as a slider in Advanced, where
0 is off. Send the picks as `loras`, a list of `{id, strength}` objects:

```json
{
  "kind": "image",
  "backend": "example_image",
  "prompt": "A pear on a table",
  "loras": [{"id": "example_warm", "strength": 0.8}]
}
```

A pick without `strength` gets the LoRA's own `strength`. A pick at strength 0 is off: Studio
checks it, then leaves it out, so it does not count toward `max_loras`. Studio refuses an
unknown id, a repeated id, a strength outside the LoRA's range, and more picks than
`max_loras`. The model gets each LoRA's `trigger` words after the prompt, unless the prompt
holds them already. The result records the prompt that you sent, without them. An empty list,
or no field, means no LoRA.

The result records the LoRAs that ran, each at the strength it got: `loras` on each image and
each batch item, and the `X-Studio-Loras` header, a JSON list, on a video's MP4.

Every item of a video batch must pick the same LoRAs. Set `loras` once at the top level. A
video model with `loras_with_audio: false` refuses LoRAs on a request that sends `audio`.

## Installed model plugins

Installed and enabled model plugins appear in `/api/v1/studio` with their own capabilities.
Their IDs work with the existing Image, Video, Voice and batch operation endpoints. Always read
the selected model's modes, parameters, sizes and limits; built-in model recipes do not apply
implicitly to plugins. A plugin without its own rewriter has no Rewrite capability.
See [adding a model](docs/how-to/add-a-model-plugin.md) and [the plugin contract](docs/reference/model-plugins.md).


## Layout to Render

Use `POST /api/v1/videos/edit` with `adapter: "layout-to-render"`, or submit the same
payload through `/api/v1/operations` with `kind: "video", mode: "edit"`.
The layout MP4 in `clip` supplies camera, framing and motion. Exactly one image in `references`
must depict its first frame with the desired materials and lighting (`frame_index: 0`, recommended
`strength: 1`). Studio maps that image to virtual position -1 and reapplies both references in
both stages. Other shipped Edit adapters accept no image references.
Describe the finished shot in one or two sentences; avoid describing the clay/blockout source.
Use 24 fps, supported dimensions divisible by 64 and 8k+1 frames. The official known-good size
is 1920×1088. Install the Layout-To-Render adapter and the LTX-2.5 pack's v1_0 spatial upscaler;
missing upscaler files fail clearly. Source audio is not preserved.
The rendered docs contain a complete example with explicit base64 placeholders.
[Official guide](https://docs.ltx.io/open-source-model/vfx-post-production/layout-to-render) ·
[Model card](https://huggingface.co/Lightricks/LTX-2.5-22b-IC-LoRA-Layout-To-Render).

## Music jobs

Music uses `kind: "music"` in the shared operations API. Read `/api/v1/studio` for available models.
Read `/api/v1/music/capabilities` for the selected model or `/api/v1/music/backends/yue2` without changing selection.
Install the [Music runtime and weights](docs/how-to/music.md#install-weights) before a real run.

| Mode | Required inputs | Result |
|---|---|---|
| `generate` | Style and lyrics, or Style with `instrumental: true` | 48 kHz stereo WAV |
| `plan` | Same inputs as Generate; `cot: full` or `melody` | JSON score without audio |
| `transcribe` | `reference_audio` | JSON score and transcription metadata |
| `cover` | `reference_audio`, Style, and lyrics or `instrumental: true` | New performance as stereo WAV |

For API instrumentals, explicitly send `"instrumental": true`. Blank lyrics alone fail validation.
The browser sets this flag for you when its Lyrics field is blank.

For example, this request returns `400` with `lyrics must contain 1 to 20000 characters`:

```json
{"kind": "music", "style": "Warm acoustic piano.", "lyrics": ""}
```

Add the explicit flag to generate an instrumental:

```json
{"kind": "music", "style": "Warm acoustic piano.", "lyrics": "", "instrumental": true}
```

Supply sectioned lyrics for vocals. Transcription does not require Style or lyrics and does not transcribe sung words into Lyrics.
Send full descriptions in `style`; the browser's Genre and Style preset chips expand text before submission.

Use `abc` with `mode: generate` to render a supplied score. `cot` must be `full` or `melody`.
Non-instrumental rendering preserves the supplied ABC text. Instrumental rendering can transform the score to move vocal melody into instrumental parts.
Reference modes reject a simultaneous `abc` value. Encode actual audio bytes as bare base64 in `reference_audio`; use `reference_name` for the filename.
The decoded limit is 32 MiB. Uploaded reference bytes stay out of public operation and item settings.

`steps` accepts 8, 16, or 32; `cfg_scale` accepts 0 through 5. The defaults are 32 and 1.
Duration follows the generated composition; there is no fixed-duration request field.
Instrumentals and score planning require `cot: full` or `melody`. A token-cap failure does not produce a successful incomplete song.

### Runnable Python client

Save this standard-library example as `music_api.py`. It submits one operation, polls its own ID, and saves retained results under `music-api-output`.
The `cancel` command starts a vocal request and immediately cancels that same ID. It never cancels another client's operation.
The `batch` command runs two items serially with shared defaults and explicit item overrides.
Set `STUDIO_PRIVATE_KEY` to a random key for private jobs. The client sends it on submissions, polling, cancellation, and downloads.
Music audio, scores, metadata, and batch results follow the [private operations](#private-operations) contract.
Keep the same key for repeated downloads or recovery after restart. Other callers receive `404`, including on metadata routes.
Server-side private storage is encrypted. This example saves your authorized downloads as plaintext files on the client machine.
Choose a protected output folder, or keep downloaded bytes in memory if you need no plaintext files.

```python
import base64
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = os.environ.get("STUDIO_URL", "http://127.0.0.1:8765").rstrip("/")
LYRICS = "[Verse]\nMorning light crosses the floor\nFootsteps gather at the door\n\n[Chorus]\nCarry this song into the day\nLet the bright notes lead the way"
STYLE = "Use a pop arrangement with a steady pulse and a clear melodic hook. Feature acoustic piano and warm lead vocals."


def request(path, payload=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {} if body is None else {"Content-Type": "application/json"}
    private_key = os.environ.get("STUDIO_PRIVATE_KEY")
    if private_key:
        headers["X-Studio-Private-Key"] = private_key
    with urlopen(Request(BASE + path, data=body, headers=headers), timeout=60) as response:
        return response.read(), response.headers.get_content_type()


def read_json(path, payload=None):
    body, _ = request(path, payload)
    return json.loads(body) if body else None


def build_payload(choice, filename=None):
    common = {"kind": "music", "backend": "yue2", "cot": "full", "steps": 32, "cfg_scale": 1, "seed": 42}
    vocal = {**common, "mode": "generate", "style": STYLE, "lyrics": LYRICS, "instrumental": False}
    instrumental = {**vocal, "style": "Warm acoustic piano with a clear melody and gentle rhythmic accents.", "lyrics": "", "instrumental": True}
    examples = {
        "vocal": vocal,
        "instrumental": instrumental,
        "plan": {**instrumental, "mode": "plan"},
        "batch": {**vocal, "items": [{"seed": 42}, {"seed": 43, "lyrics": "", "instrumental": True, "style": instrumental["style"]}]},
        "cancel": vocal,
    }
    if choice in examples:
        return examples[choice]
    if choice not in {"render", "transcribe", "cover"} or not filename:
        raise SystemExit("Choose vocal, instrumental, plan, batch, cancel, or render/transcribe/cover FILE")
    source = Path(filename)
    if choice == "render":
        return {**instrumental, "abc": source.read_text(encoding="utf-8")}
    reference = {"reference_audio": base64.b64encode(source.read_bytes()).decode("ascii"), "reference_name": source.name}
    return {**(vocal if choice == "cover" else common), **reference, "mode": choice, "transcription_task": "full"}


def poll(operation):
    while True:
        current = read_json(operation["status_url"])
        if current["status"] not in {"running", "stopping"}:
            return current
        time.sleep(1)


def download(result_url, folder):
    folder.mkdir(parents=True, exist_ok=True)
    body, media_type = request(result_url)
    suffix = ".wav" if media_type == "audio/wav" else ".json"
    (folder / ("result" + suffix)).write_bytes(body)
    document = json.loads(body) if suffix == ".json" else {}
    if "items" in document:
        for item in document["items"]:
            download(item["result_url"], folder / str(item["index"]))
        return
    details = read_json(result_url.removesuffix("/result") + "/metadata")
    (folder / "metadata.json").write_text(json.dumps(details, indent=2), encoding="utf-8")
    (folder / "score.abc").write_text(details["score"], encoding="utf-8")


def main():
    choice = sys.argv[1] if len(sys.argv) > 1 else "vocal"
    payload = build_payload(choice, sys.argv[2] if len(sys.argv) > 2 else None)
    capabilities = read_json("/api/v1/music/backends/yue2")
    print("Music modes:", capabilities["modes"])
    operation = read_json("/api/v1/operations", payload)
    folder = Path("music-api-output") / operation["id"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "receipt.json").write_text(json.dumps(operation, indent=2), encoding="utf-8")
    print("Operation:", operation["id"], flush=True)
    if choice == "cancel":
        try:
            request(operation["status_url"] + "/cancel", {})
        except HTTPError as error:
            if error.code != 409:
                raise
            print("The operation finished before cancellation was accepted.")
    current = poll(operation)
    (folder / "status.json").write_text(json.dumps(current, indent=2), encoding="utf-8")
    if current.get("result_url"):
        download(current["result_url"], folder)
    print(current["status"], folder)
    if current["status"] == "failed":
        raise SystemExit(str(current.get("error", "Music operation failed")))


if __name__ == "__main__":
    try:
        main()
    except HTTPError as error:
        raise SystemExit(f"HTTP {error.code}: {error.read().decode('utf-8', errors='replace')}")
    except URLError as error:
        raise SystemExit(str(error.reason))
```

Run one command at a time. Set `STUDIO_URL` when your server uses another address.
For `render`, replace `<operation-id>` below with the ID printed by your successful `plan` command.
For reference modes, supply an actual recording instead of an encoded placeholder.

```sh
python3 music_api.py vocal
python3 music_api.py instrumental
python3 music_api.py plan
python3 music_api.py render "music-api-output/<operation-id>/score.abc"
python3 music_api.py transcribe reference.wav
python3 music_api.py cover reference.wav
python3 music_api.py batch
python3 music_api.py cancel
```

The example renders supplied scores as instrumentals. For a vocal score, use `instrumental: false` and provide its matching lyrics.
The example uses `transcription_task: full`. Choose the scope that matches what you want to keep from the reference:

| `transcription_task` | Musical scope |
|---|---|
| `full` | Melody and chords |
| `melody-full` | Vocal and instrumental melody |
| `melody-vocal` | Vocal melody only |

One request makes one result. For variations, submit `items` with explicit seeds; the advertised maximum is 16 items.
The batch result is a manifest, even after failure or cancellation. Download each completed item's `result_url`; indices start at one.
Item metadata uses `/api/v1/operations/{id}/items/{index}/metadata`. A batch has no single Music metadata result.
The client saves JSON scores, WAV audio, metadata, and ABC files. Metadata also retains available MIDI/LAB artifacts as base64.

### Completion, timing, and retention

A `202` response acknowledges the operation; it does not mean generation succeeded. Poll until `succeeded`, `failed`, or `cancelled`.
A running single result returns `409`. A batch manifest exposes completed items while later items run.
The client downloads partial batch results before reporting a terminal failure.

Invalid requests return `400`; a busy server or stale cancellation returns `409`. Missing Music support returns `503`.
Engine failures appear in the operation's `error` field. Do not retry a busy request as though it entered a queue.
Public results expire after at most ten minutes. The 32-operation and 256 MiB limits can evict them sooner, including metadata.
Restarting the server clears public history. Private results remain encrypted for one hour after completion and survive restart.
Expired or deleted results return `404`. Save downloads promptly; browser Keep is separate.

Use `finished_at - started_at` from the operation for total processing time; `seconds` describes output audio duration.
For batches, those operation timestamps cover the whole batch. Do not report them as each item's generation time.
Nested engine timings describe individual phases and can overlap with other recorded timing scopes.
`metadata.transcription_cache_hit` marks reuse of a reference transcription.
On a cache hit, `metadata.transcription.elapsed_seconds` describes the original transcription, not work performed for the current request.
The worker retains one successful transcription for the same audio bytes and transcription task. Releasing the worker clears that cache.

The synchronous `POST /api/v1/music/generate` accepts the same single-job fields and returns WAV or JSON according to mode.
Prefer asynchronous operations for polling, cancellation, retained metadata, and serial batches.

A successful synchronous response includes its ID in `X-Studio-Operation`.
Use that ID with `/api/v1/operations/{id}/metadata` to fetch the score and generation details.
The synchronous endpoint rejects `X-Studio-Private-Key`; use asynchronous operations for private Music jobs.
After saving `music_api.py` above, run this public header example beside it with `STUDIO_PRIVATE_KEY` unset:

```python
import json
from pathlib import Path
from urllib.request import Request, urlopen
from music_api import BASE, build_payload, read_json
import os

if os.environ.get("STUDIO_PRIVATE_KEY"):
    raise SystemExit("Use the asynchronous client for private Music jobs.")
payload = json.dumps(build_payload("instrumental")).encode("utf-8")
request = Request(BASE + "/api/v1/music/generate", data=payload,
                  headers={"Content-Type": "application/json"})
with urlopen(request, timeout=3600) as response:
    operation_id = response.headers["X-Studio-Operation"]
    Path("synchronous.wav").write_bytes(response.read())
metadata = read_json(f"/api/v1/operations/{operation_id}/metadata")
Path("synchronous-metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
```
