# Generate music with YuE2

Music offers two outputs: **Generate** makes a song, and **Compose** makes sheet music.
A reference recording is the source, so it turns Generate into a cover and Compose into
a transcription. Songs remain 48 kHz stereo; score-only results can be inspected, edited,
downloaded and rendered later. MLX Q8 remains the single generation engine.

Put genre, instruments, language, vocal character and tempo in Style. Put the words to
sing under `[Verse]`, `[Chorus]` and similar tags in Lyrics. Leaving Lyrics blank generates an instrumental; adding lyrics generates vocals. A seed can
repeat a request; results can still differ across engine versions and hardware.

## Install weights

Music uses native MLX Q8 on Apple Silicon. The score/token model uses 8-bit weights;
acoustic synthesis uses BF16 conditioning and acoustic weights, with an FP32 decoder.
There is no PyTorch Music engine or precision fallback.

The worker pins [mlx-Yue](https://github.com/vanch007/mlx-Yue) at
`c5b5a8190f78c74aa671a4caa19dae8b8e04b3d8`, including MLX 0.32.2 and mlx-lm 0.31.3.
Create the isolated Python 3.12 environment used by the default configuration:

```sh
runtime="$HOME/Library/Caches/yue2-mlx-runtime/c5b5a8190f78c74aa671a4caa19dae8b8e04b3d8"
uv venv --python 3.12 "$runtime/venv"
uv pip install --python "$runtime/venv/bin/python" \
  'mlx-yue @ git+https://github.com/vanch007/mlx-Yue.git@c5b5a8190f78c74aa671a4caa19dae8b8e04b3d8'
"$runtime/venv/bin/python" \
  studio/l3_interface_adapters/gateways/music/yue2/yue2_mlx_child.py \
  --download \
  --model-dir "$HOME/Library/Caches/models/yue2-mlx" \
  --vae-dir "$HOME/Library/Caches/models/yue2-mlx-vae"
```

The download uses converted checkpoint revision
`5f7620e546fb3c6130a09a7e18172e3bb7aaeddb`. The generator directory contains only
its conversion manifest and the files it declares. The decoder must live outside
that directory; placing it inside invalidates the upstream integrity check.
The downloader refuses unexpected files in an existing generator directory and
keeps them intact. Choose an empty directory instead of a previous Hub checkout.

`[yue2]` in `studio.toml` defaults to `engine = "mlx-q8"`, with `model_dir`,
`vae_dir`, and the pinned environment's `python_path`. Without `python_path`, the
worker uses its isolated `uv run --script` environment. An old `engine = "torch"`
setting is rejected. Startup and stub mode load no weights; generation uses local
checkpoints only and never downloads them. Cancellation stops the owned worker.

Token counts indicate activity during planning and semantic generation, then
acoustic synthesis reports solver steps. Neither is a whole-song percentage or ETA.

## Make a song

Start `uv run studio`, choose **Music → Generate**, enter Style and Lyrics, then choose **Generate music**. For an instrumental, leave Lyrics blank and describe the arrangement in Style.
Open **Genre** to browse 59 choices in eight families. Common styles appear first, followed by specialized styles and regional inspirations.
The section starts closed and shows your selected genre in its summary. Browse the groups directly; there is no search field.
Choose one genre. A new choice replaces the previous genre. Select the active choice again to clear it.

Open **Style presets** for Mood, Instruments, Vocals, Tempo, Production, and Language.
These six rows remain available for every genre and use the same rows and chips as Image Look.
Each row permits one preset. A new choice replaces that row’s previous choice. Select the active choice again to clear it.
Each preset adds a detailed sentence to Style. You can edit or remove it before generating.
The compact labels stay unchanged. Older drafts with preset keywords remain supported.
Generation duration follows the composition. Planning and token generation have unknown lengths;
progress becomes determinate during acoustic synthesis. Finishing includes decoding the audio.
A model that hits a token cap fails the job instead of publishing an incomplete song as success.

Each song offers playback, WAV download, **Edit score**, generation details, and **Send to Video**.
The Music gallery shows the song count and album artwork.
A record player follows generation and playback: vinyl spins at 33⅓ RPM and the
tonearm engages while active, then rests on pause. These animations respect the
browser's reduced-motion preference.
The output remains 48 kHz stereo. Keep in this browser stores recordings and drafts locally;
turning it off removes their persistent copies. Delete removes a saved recording.
Stub recordings are explicitly labeled silent test previews and cannot be sent to Video.

The mode picker offers two outputs: **Generate** and **Compose**. Add a recording in
**Reference audio** and the same choice becomes **Cover** for Generate or **Transcribe**
for Compose; the caption under the run button names the result. The form then shows only
the fields that result reads. Generate empties the form it sent: Style, Lyrics and the
reference recording. Cancel or a failed run puts them back.
**Advanced** holds the seed, planning, synthesis quality and variations.
Planning offers melody-and-chord planning (the default), melody planning, or direct generation.
An optional ABC score requires melody or full planning. Advanced shows the score read only.
**Edit score** opens the editor: the ABC text beside a sheet that follows it as you type.
Esc or Close returns to the form and keeps the edits. Rendering an edited score makes a new
recording; it does not preserve waveform regions. Non-instrumental rendering preserves the supplied ABC text. Instrumental rendering can move vocal melody into instrumental parts.
Direct generation is not an instrumental switch; instrumentals need melody or full planning.

Advanced offers 32 synthesis steps (standard), 16 (balanced), or 8
(fast), and style guidance from 0 to 5 with 1 as the model default. Fewer steps trade
synthesis quality for speed. Variations run serially; a supplied seed increases by
one for each result. All modes continue to share Studio’s single GPU operation slot.

## Compose, inspect and render a score

Choose **Compose** to write sheet music without producing audio. Inspect its complete
sheet music and ABC source in the same gallery as recordings. **Edit score** opens the
editor with that exact score; the details sheet holds the ABC source and its download.
The editor loads the score into Generate, so you can edit its notation, style, or lyrics,
then press Generate to render it.

Compose score supports instrumental output and serial variations. Score-only items
have ABC downloads and no audio playback or Send to Video action.

## Transcribe a reference recording

Choose **Compose** and upload or drop an audio recording of up to 32 MiB.
Use **Keep from reference** to choose vocal and instrumental melody, vocal melody only,
or melody and chords. This runs SheetSage2/MERT2 and returns a score rather than a
new song. When returned by the transcription engine, MIDI and LAB exports appear
beside the sheet music, labeled by their contents: vocal or instrumental melody,
key, beats, section structure, or chords. The score can then be edited and rendered through Create song.

The reference remains in the current draft and, when Keep is enabled, survives a
reload in this browser. It is sent only for Transcribe audio or Cover song, and its
binary content is excluded from public operation settings.

## Cover a reference song

Choose **Generate** and add reference audio. Use **Keep from reference** beside the attachment to choose the melody or harmony scope,
then provide a new style and the lyrics to sing. Leave Lyrics blank for a version
without vocals. YuE2 transcribes the source composition and generates a complete
new performance from that score. It does not clone the original singer, preserve
source waveform regions, or automatically transcribe lyrics. Transcription errors
can affect the result; inspect and edit the returned score when needed.

Audio transcription and covers need FFmpeg and separately cached SheetSage2/MERT2
weights. The setup helper installs the verified instrumental helpers and Torch-free
transcription dependencies into the pinned runtime, then downloads both pinned
checkpoints:

```sh
uv run python scripts/setup_yue2_workflows.py
```

Use `--python <pinned-venv/bin/python>` to select the runtime and `--cache-dir <path>`
to select the transcription cache. `--skip-download` installs the helpers and
optional dependencies without downloading weights. Their absence does not prevent
ordinary song or score creation. The cache is configured with
`[yue2].transcription_cache_dir` (default `~/Library/Caches/models/yue2-transcription`).

## Model capabilities and limits

The form exposes the stable creation, planning, transcription and cover workflows,
instrumental arrangements, supplied-score rendering, serial variations, synthesis
steps and style guidance. Experimental real-audio reconstruction/token extraction and artist LoRA adapters need
separate weights or a different precision path and are not enabled by this UI.
Native plan replay and intermediate semantic/latent tools remain runtime tools;
Create song can render any editable ABC composition without claiming exact audio replay.

## API

Read the [Music API examples](../../API.md#music-jobs) for an executable standard-library Python client.
It covers vocals, instrumentals, planning, supplied scores, references, serial batches, polling, cancellation, and downloads.
API instrumentals require `"instrumental": true`; blank lyrics alone fail validation. The browser sets this flag automatically.

Inspect `/api/v1/music/capabilities` or `/api/v1/music/backends/yue2`, then submit:

```json
{
  "kind": "music",
  "backend": "yue2",
  "style": "English, warm piano pop, expressive vocals, bass, light drums, 88 BPM",
  "lyrics": "[Verse]\nMorning settles on the street\nEvery window keeps a beat\n\n[Chorus]\nCarry light along the road\nLet the quiet story grow",
  "cot": "full",
  "seed": 42
}
```

POST it to `/api/v1/operations` and poll the returned `status_url`. The successful `result_url`
returns WAV. `/api/v1/operations/{id}/metadata` returns the score, seed, sample rate, duration,
effective configuration, timings and weight identities. Batches use the common `items` envelope;
finished songs survive cancellation or later failure. Each item has a WAV result and a metadata
route at `/api/v1/operations/{id}/items/{index}/metadata`. Download results promptly: public retention lasts at most ten minutes and has limits of 32 operations and 256 MiB.
Older public results can expire sooner, and restarting the server clears public history.
Private jobs use `/api/v1/operations` with `X-Studio-Private-Key` on every request, including metadata and result reads.
Private results remain encrypted for one hour after completion and survive restart. `/api/v1/music/generate` returns synchronous WAV for Generate/Cover or JSON for Plan/Transcribe.

## Why it looks like this

The native MLX engine runs in a separate pinned process and shares Studio's one
operation lock and model-memory slot. A batch loads one worker and generates
songs sequentially. Q8 applies only to autoregressive generation; acoustic
conditioning, synthesis and decoding retain their recommended precision.
The worker caches one successful transcription, keyed by the recording bytes and transcription task.
Repeated covers reuse the score and exports without loading the transcriber again.
A different recording or task replaces the entry. Releasing the worker clears it.
The cache retains no recording bytes or model. Returned metadata uses independent copies.

`metadata.transcription_cache_hit` identifies reuse. On a hit, `transcription.elapsed_seconds`
still describes the original transcription, not work performed for the current request.

Two covers of the same 30-second reference tested this change through Studio on the M5 Pro.
Both runs used seeds 42 and 43, eight synthesis steps, and the same style and lyrics.
The first cover took 24.93 seconds before and 25.94 seconds after the change.
The second took 21.88 seconds before and 12.78 seconds after, a 41.6% reduction.
Both output WAV files matched their baseline bytes exactly. These measurements cover one request pair, not all songs.

No generation-time estimate is shown: duration itself is generated, and a short
sample does not establish a cost fit for a full song.

The code is Apache-2.0 upstream. Model weights use CC BY-NC 4.0 plus an individual-creator
permission; company commercial use requires a separate license. Read the
[actual model terms](https://github.com/multimodal-art-projection/YuE/blob/main/MODEL_LICENSE).

## Local validation

Measured through the actual Studio operation and JSON-pipe worker on an M5 Pro
with 64 GB unified memory, macOS 26.6.2, MLX 0.32.2 and the pinned runtime above.
The request used four original English piano-pop lyric lines, full planning,
seed 42 and the standard 32 acoustic synthesis steps.

| Measurement | Result |
|---|---:|
| Generated stereo audio | 36.76 s |
| Pipeline generation | 37.59 s |
| Complete live test, including startup and integrity checks | 43.68 s |
| Score token throughput | 78.63 tokens/s |
| Semantic token throughput | 79.59 tokens/s |

The live test verified finite, non-silent 48 kHz stereo output, a score and actual
MLX Q8 configuration metadata. Browser checks verified playback, token progress,
cancellation and retaining a completed recording after cancelling another run.
The production file digests were recorded before the live measurement and
checked afterwards. These short-song figures do not establish full-song timing
or an audio quality comparison with another precision.

## Music player and artwork

Select a recording in the filmstrip or open Browse to search and sort the gallery.
Songs start as **Untitled**. Click the title to rename it; Enter saves and Escape
cancels. Names are saved with the recording and appear in the gallery.
Selecting another gallery item keeps the current song playing. Playing another song stops the previous one.
Use **Pause** in the gallery header to stop a song that plays in the background.
A **Playing** badge marks the audible song in the strip and Browse gallery.
Its bars animate during playback and stay still when reduced motion is enabled.
Leaving Music or deleting the playing song also stops playback.
Generation time shows processing duration when the operation supplies its timestamps.
Older songs and batch items omit this value when their individual timing is unavailable.

The player shows artwork, a seek bar, elapsed and remaining time, play/pause, and
**Back 5 seconds / Forward 5 seconds** controls.
**Edit score** opens the ABC editor: the text beside a live sheet. The sheet renders the
complete score, including vocal and instrumental voices and their chord symbols.
Scroll over the white sheet to read it; focus it and use arrow keys or Page Up/Page Down,
or swipe on a touchscreen. The sheet does not follow playback timing. Esc or Close keeps
the edits. If engraving is unavailable, the text stays editable and the details sheet keeps
the full ABC source.

The bar immediately above the gallery holds the style and key generation facts on
the left. On the right, the **Edit score** action, **More actions**, separator, download and remove controls match the other modes. Artwork, Send to Video and style reuse live in More actions.
Click the style caption to open the full metadata sheet. Escape
closes it and returns focus. The action bar stays visible while the preview scrolls.

Choose **More actions → Generate artwork** on a recording (or press **Alt+C**) to make and attach square artwork
from the selected song’s title, style and lyrics using the active Image model. For songs with lyrics, Studio first prepares a concrete visual concept from their imagery and emotions, then renders that concept with strict instructions forbidding words, letters, titles, logos and other visible writing. Lyrics are thematic source material, not text to typeset; section markers are removed and lyric context is limited to 6,000 characters. Instrumentals use the title/style scene template directly. The prompt follows the repo’s [studio-image prompt craft](../../plugins/open-imagine/skills/studio-image/references/prompt-craft.md). A real lyric-driven test produced the intended bird/cage metaphor without visible text; this does not guarantee every future image will follow the instruction. Concept preparation adds time before image rendering. This artwork action is separate from the **Cover song** audio workflow. Music stays
open while the cover runs. **Regenerate artwork** keeps the previous artwork until
the replacement finishes. Keeping the gallery saves both audio and artwork locally.
Abandoned requests become retryable after two minutes.

## Verify the workflows locally

The CPU suite uses `--stub` and verifies workflow switching, reference persistence,
score-only gallery entries, exact ABC reuse, artwork, metadata, and MIDI/LAB exports.
The live workflow test exercises the actual Studio operation path for composition,
score rendering, instrumentals, reference transcription, covers and cancellation.
`tests/e2e/verify_music_live.py` drives generation, playback, score editing/rendering
and cancellation through the real browser controls.

Run these live checks only with an exclusive GPU slot and your own Studio port:

```sh
STUDIO_MUSIC_LIVE_URL=http://127.0.0.1:8850 uv run pytest -m live -k yue2 --no-cov
uv run --with playwright python tests/e2e/verify_music_live.py 8850
```

Follow the repository’s shared-GPU rules before starting the real server. These are
functional checks, not full-song performance or audio-quality benchmarks.

## Read lyrics

The preview shows Style in the fixed area beside the cover by default.
Use the **Lyrics** icon button beside **Forward 5 seconds** to show the supplied words in that same area.
Use it again to return to Style. The icon stays pressed while lyrics are visible.
Long text scrolls inside the area, so the title and playback controls stay in place.

Studio receives no lyric timestamps, so lines do not follow playback or seek when selected.
Section headings separate verses and choruses. Scroll with a pointer, touch, or keyboard.
Switching views does not interrupt playback or open a modal.
The Lyrics icon is disabled for instrumentals or songs without supplied words. Score-only entries keep their Style text.
