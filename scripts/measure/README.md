# Measuring a machine

The reference page (`docs/reference/measured-memory-and-time.md`) holds what these scripts
produced. This directory holds the means to produce it again: the case list, the runner, the
report, and the assets both machines must share.

A figure on that page is only worth the method behind it, so the method is here rather than
in a scratch directory.

## What a run is

1. One studio, one operation at a time. A second GPU job makes every number wrong.
2. The runner records four spans, because one number hides where the time went.
   `submit_to_accept` is the POST and the response. `active` is the studio's own start to
   terminal status, which is the job itself. `queue_wait` is the accept to that start, and
   it is zero unless another operation held the slot. `fetch` is the download of the
   result. `seconds` is the whole thing end to end, and it is the only number that includes
   the queue wait and the load. Two machines compare on `active`.
3. Two runs of one case give a cold row and a warm row. The first case of a workspace carries
   that workspace's load, so the warm-up pass at the end repeats it and the warm figure is the
   one to compare.
4. Free memory is `MemAvailable` sampled five times a second from the submit to the end of
   the case, and the download is inside that window. The figure is the start minus the lowest
   sample, in GiB, with the start and the end recorded beside it. Read it as end-to-end host
   pressure, not model memory: other processes share the machine, and the download's own
   buffers are counted. The peak drop cannot go negative, because the minimum starts at the
   start value; the end value can sit above the start, which means the run evicted more page
   cache than it allocated. A macOS host has no `/proc/meminfo`, so it reports no figure.
5. Every successful result is recorded with its SHA-256 and with the facts its own bytes
   carry: the width and height of a whole PNG, the sample rate, channels and seconds of a
   WAV read from its chunks, and whether an MP4 holds a track whose handler names sound.
   A success says the API answered. These say what it answered with.

## A campaign

A campaign is a commit, its dirty state, a platform, an interpreter, a set of asset bytes,
and what the studio says it serves: the backend each workspace offers, and that backend's
own capabilities, which carry the sizes and the weight precision. The active selection and
the resident list are left out, because they move while a campaign runs. The first
`run_matrix.py` writes all of it to `campaign-<machine>.json` and every later run must match.

- A case is skipped only when a result of this campaign already succeeded on it and the
  file it names still hashes to the digest in the row. A results file copied without its
  media, or a truncated artifact, is scheduled again. If the checkpoint still names the
  operation, the rerun fetches the result instead of generating it.
- Each artifact is named by the digest of its own media, so a repeat trial with different
  bytes is a second file, and the earlier row keeps the bytes it hashed.
- `--reuse-compatible` keeps the manifest on disk when this tree differs from it. Use it to
  add cases to a campaign that is already running, not to mix two revisions.
- `--force` runs a case this campaign already finished. Use it for a deliberate repeat.
- `--strict` makes a run exit nonzero unless every selected case ended as a success of this
  campaign with its artifact present. The default stays exploratory, because a partial
  campaign is still worth reading.
- `--deadline` caps one case in seconds, 1800 by default. On a breach the runner asks the
  studio to cancel and records `timeout` with the reason. A stuck operation costs one row,
  not the night. A download that fails after a success records `fetch_failed` with its
  operation, and the next run fetches it.
- A case that finished but whose result never arrived is fetched on the next run, not
  generated again.
- A results file that ends in half a line loses that line and keeps the rest. A bad line
  anywhere else stops the run, because that is corruption and not an interrupted append.

## The four parts

| File | What it does |
|---|---|
| `build_assets.py` | Makes the references once: one picture from the image backend, two speeches from the voice backend, and slices of an audio file. It writes `assets.sha256` beside the directory, and it refuses to build over assets another machine already owns. A build assembles the whole set in `assets.new` and swaps it in, so a build that dies leaves the previous set and its manifest untouched. |
| `parity_matrix.py` | Writes `matrix.jsonl`: one JSON line per case, carrying a payload for each engine. Same prompt, same seed, same reference; only the backend id and the field each engine names differently change. |
| `run_matrix.py` | Runs the manifest against one studio, appends one JSON line per run, and skips a case this campaign already succeeded on. |
| `report.py` | Prints both columns side by side and names every case that is missing or did not succeed. It also prints the manifest of each machine and marks a figure that came from another campaign. That last part is the point: it is how a case stops being forgotten and how a stale figure stops being compared. |

## Running it

On the machine that owns the engines, build the assets once:

```sh
uv run studio --config studio.cuda.toml --port 8899   # the CUDA machine
uv run python scripts/measure/build_assets.py --base http://127.0.0.1:8899 \
    --image-backend qwen21_turbo_cuda --voice-backend drama3_cuda --work /tmp/parity
uv run python scripts/measure/parity_matrix.py --work /tmp/parity
uv run python scripts/measure/run_matrix.py --machine cuda --base http://127.0.0.1:8899 --work /tmp/parity
```

Then copy `/tmp/parity/assets` and `/tmp/parity/assets.sha256` to the other machine. Do not
run `build_assets.py` there: a second generated picture is a different picture, and a case
that cites it is not the same case.

On the other machine, with its own studio on its own port:

```sh
uv run python scripts/measure/run_matrix.py --machine mlx --base http://127.0.0.1:8899 --work /tmp/parity
uv run python scripts/measure/parity_matrix.py --work /tmp/parity --warmup-only
uv run python scripts/measure/run_matrix.py --machine mlx --matrix /tmp/parity/warmup.jsonl \
    --out /tmp/parity/warm-mlx.jsonl --base http://127.0.0.1:8899 --work /tmp/parity
```

Finally, collect both result files, both `campaign-<machine>.json` files and the media in
`results/`, then:

```sh
uv run python scripts/measure/report.py --work /tmp/parity
```

`report.py` reads `results-<machine>.jsonl` and, when present, `warm-<machine>.jsonl`. It
shows the warm row when that row belongs to this campaign and succeeded, and the base row
otherwise. A warm row from an older campaign or a failed one must not hide a good cold row,
and a table cell and the coverage count use one definition of a valid success.

## What the assets are

- `picture-1024.png` is one image made by the image backend at 1024 and seed 7. Every image
  and video case cites it or a resize of it: `ref-512`, `ref-1600x900`, `ref-2048`,
  `ref-4032x3024`, `ref-768x512`. Generating it once removes the question of whether two
  machines saw the same picture.
- `voice-short.wav` and `voice-long.wav` are speeches from the voice backend with the scripts
  written down. A clone needs a transcript it can name, and a sliced recording does not have
  one.
- `music-10s.wav` and `music-15s.wav` are slices of one recording, for transcribe and cover.

Assets are generated, never committed. The manifest names them, and the runner checks every
byte it reads against it, so a missing or changed asset fails before a GPU is touched.

## The rules that are not obvious

- One GPU job at a time, and one studio per machine. Check the other ports first.
- A case that fails is retried by the next run of the same command, because only a success of
  this campaign is skipped. A payload fault shows up as a rejection in the results file with
  the API's own words.
- Both machines must run the same commit and the same asset bytes. `report.py` says so when
  they do not, because the two columns then describe two different products.
- A case id may contain a slash. The result file name carries a short fingerprint as well, so
  two ids that read alike cannot overwrite each other.
