# Deliver and verify

A finished operation is not a finished song. Deliver audio the user can play, and the exact
conditions that made it. Keep the evidence separate from the judgment.

## What to save

Save the audio, the returned score, the metadata and the exact request together. Use a folder
per take. Include:

- The complete style and lyrics, the seed, the mode, the planning value, `steps` and
  `cfg_scale`.
- The operation ID, the start and finish times, and any truncation flags.
- The score, and for a score edit, both the source and the edited version.
- For a cover or a transcription, the reference name and the transcription task. Keep the
  source recording separately.
- For a batch, each item's own seed and result, including the items that failed.

Public results expire after ten minutes. Private results expire one hour after completion.
Save before either deadline. Do not leave the only copy in the server.

## Give the user a way to listen

Hand over the WAV, or a lossless copy, with the exact style and lyrics beside it. If the
interface supports a local page, a small player can help. A listening page is a delivery aid,
not a benchmark result.

Listen when the environment allows it. Check:

- The melody is the one you asked for, and the words are the ones you supplied.
- The chords support sustained melody notes. A short passing tone and a held clash are
  different problems.
- The instruments you asked for are audible, and the ones you excluded are absent. A style
  sentence is a request, not proof.
- Sections enter and leave as intended, and the ending resolves.
- The lyrics are not dropped, repeated or garbled.

If you cannot hear the audio, say so. Report the checks you actually performed. Do not invent
an impression of the sound.

## Keep the evidence honest

| Check | What it supports | What it does not establish |
|---|---|---|
| Operation status and metadata | The run completed, with its seed, mode and settings | Musical quality |
| Score inspection | The returned symbolic material, its durations and structure | That the performance followed it |
| Event comparison before and after an edit | The selected symbolic notes, onsets and durations were preserved | Identical audio or a preserved singer |
| Transcription of the result | A diagnostic estimate of what sounds | Ground truth; transcription has its own errors |
| Listening | Your reported audible observations | A measured score or a preference study |

A same-seed pair is provenance, not a controlled experiment. Do not select a seed after
hearing the options and present that take as the planned one.

## Failures

Keep failed, truncated and rejected takes visible. Report:

- The requested modes and takes, and which ones completed.
- The error text, the truncation flags and the point where the run stopped.
- Whether the failure came from the request, the transcription, the engine, the GPU or the
  server.

A failed operation is not proof that a shorter song or a lower quality setting is what the
user wants. Retry only after a real change, at most once for the same approach. If the same
failure repeats, report it and ask.

## Private work

For a private operation, keep the key out of files, logs, prompts and URLs. Private results
are encrypted on the server. A downloaded file is plaintext on this machine, so choose the
folder and say where it went. Without the key, the server answers `404` for the operation,
its status, its metadata, its result and its cancel route.
