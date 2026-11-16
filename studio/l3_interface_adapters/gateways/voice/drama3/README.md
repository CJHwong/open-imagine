# Drama-3 gateway

## Why it looks like this

Drama-3 clears the MLX allocator cache after each audio chunk. A measured alternative clears it only after the complete result. The small time reduction costs more memory, so the gateway keeps the current policy.

### Cache experiment, 2026-11-15

The experiment uses the synchronous Studio operation route on an M5 Pro with 64 GiB of memory. Each policy starts a fresh Studio server and child. Each receives one warmup request, then three warm repetitions of each public script. The campaign has 14 requests.

| Warm median | Clear each chunk | Clear after result |
|---|---:|---:|
| Short script | 2.168 seconds | 2.143 seconds |
| Long script | 13.755 seconds | 13.553 seconds |

The short script has 3.019 seconds of audio. The long script has 19.180 seconds. Each policy produces identical WAV bytes and decoded samples for each script. The measured reductions are 1.13% and 1.47%. Three repetitions do not establish statistical significance.

Both policies use the same engine revision, weights, sampling, and 1 GiB allocator cache limit. The streaming interval is 0.5 seconds. The final codec reset, cache clear, and wired-memory restoration remain active under both policies.

| Setting | Value |
|---|---|
| Seed | 7 |
| Temperature | 0.7 |
| Top-p | 0.7 |
| Top-k | 30 |
| Maximum tokens | 2048 |
| Engine revision | `2209e6d76c18d0a24f7ff64d35b4176258acd909` |
| Weight revision | `fedc7cc92bab5a180709cbaae6208d10b390bb97` |

The short public script is “The morning light falls across a quiet room.”

The long public script is:

> The morning light falls across a quiet room. A small clock ticks beside the window, and a cup rests on the table. Outside, a gentle wind moves the leaves. I take one slow breath, open the door, and begin another ordinary day with a clear and steady voice.

Clearing only after the result adds about 0.70 GiB to peak MLX allocation for the long script. The sampled process tree adds about 1.19 GiB of resident memory. Process samples occur every 250 milliseconds. MLX observations occur after each audio chunk completes. These observations do not provide continuous cache-memory peaks.

No new swapouts occur in either campaign. System memory counters include other operating system activity. They do not isolate this process. Resident memory and MLX allocation use different accounting and must not be added together.

Source digests match across all 1,013 copied files before and after the campaign. The comparison uses two fixed scripts and one seed. It does not predict long sessions, other voices, or memory pressure. The gateway retains per-chunk cache clearing.
