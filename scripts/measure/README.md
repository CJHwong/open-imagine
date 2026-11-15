# Measuring a machine

The reference page (`docs/reference/measured-memory-and-time.md`) holds what these scripts
produced. This directory holds the means to produce it again: the case list, the runner, the
report, and the assets both machines must share.

A figure on that page is only worth the method behind it, so the method is here rather than
in a scratch directory.

## What a run is

1. One studio, one operation at a time. A second GPU job makes every number wrong.
2. The runner submits the payload, waits for a terminal status, and reads the result. `Time`
   is submit to terminal status: it includes the child's start but not the queue wait or a
   weight download.
3. Two runs of one case give a cold row and a warm row. The first case of a workspace carries
   that workspace's load, so the warm-up pass at the end repeats it and the warm figure is the
   one to compare.
4. Free memory is `MemAvailable` before the submit minus the lowest sample during the run, as
   a share of the machine's total. A negative figure means the run evicted more page cache
   than it allocated, which happens on unified memory.

## The four parts

| File | What it does |
|---|---|
| `build_assets.py` | Makes the references once: one picture from the image backend, two speeches from the voice backend, and slices of an audio file. Both machines then read the same bytes. |
| `parity_matrix.py` | Writes `matrix.jsonl`: one JSON line per case, carrying a payload for each engine. Same prompt, same seed, same reference; only the backend id and the field each engine names differently change. |
| `run_matrix.py` | Runs the manifest against one studio, appends one JSON line per run, and skips a case that already succeeded. |
| `report.py` | Prints both columns side by side and names every case that is missing or did not succeed. That last list is the point: it is how a case stops being forgotten. |

## Running it

On each machine, with its own studio on its own port:

```sh
uv run studio --config studio.cuda.toml --port 8899   # the CUDA machine
uv run python scripts/measure/build_assets.py --base http://127.0.0.1:8899 \
    --image-backend qwen21_turbo_cuda --voice-backend drama3_cuda --work /tmp/parity
uv run python scripts/measure/parity_matrix.py --work /tmp/parity
uv run python scripts/measure/run_matrix.py --machine cuda --base http://127.0.0.1:8899 --work /tmp/parity
```

Then, on the other machine, the same three steps with its own backends and port, and finally:

```sh
uv run python scripts/measure/parity_matrix.py --work /tmp/parity --warmup-only
uv run python scripts/measure/run_matrix.py --machine mlx --matrix /tmp/parity/warmup.jsonl \
    --out /tmp/parity/warm-mlx.jsonl --base http://127.0.0.1:8899 --work /tmp/parity
uv run python scripts/measure/report.py --work /tmp/parity
```

`report.py` reads `results-<machine>.jsonl` and, when present, `warm-<machine>.jsonl`, which it
prefers.

## What the assets are

- `picture-1024.png` is one image made by the image backend at 1024 and seed 7. Every image
  and video case cites it or a resize of it: `ref-512`, `ref-1600x900`, `ref-2048`,
  `ref-4032x3024`, `ref-768x512`. Generating it once removes the question of whether two
  machines saw the same picture.
- `voice-short.wav` and `voice-long.wav` are speeches from the voice backend with the scripts
  written down. A clone needs a transcript it can name, and a sliced recording does not have
  one.
- `music-10s.wav` and `music-15s.wav` are slices of one recording, for transcribe and cover.

Assets are generated, never committed. The manifest names them, so a missing file fails before
a GPU is touched.

## The rules that are not obvious

- One GPU job at a time, and one studio per machine. Check the other ports first.
- A case that fails is retried by the next run of the same command, because only a success is
  skipped. A payload fault shows up as a rejection in the results file with the API's own
  words.
- Both machines must run the same commit. A backend that grew a field since the other one was
  updated fails at the API, not in the engine.
- The reference bytes are the ones in `matrix.jsonl`. A case that cites a file that changed
  since the other machine's run is not the same case.
