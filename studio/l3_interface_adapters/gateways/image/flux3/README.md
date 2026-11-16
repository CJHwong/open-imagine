# FLUX.3 gateway

## Why it looks like this

FLUX.3 keeps one process per image. A resident worker saves about one second in this small test and keeps 8.50 GiB allocated between calls. The current process releases its model memory after each image.

### Resident worker experiment, 2026-11-15

The experiment uses the Studio operations API on an M5 Pro. It uses the configured q8 weights and mflux commit `63cec2b005bbb255447e0b42521c5cc6d6d5121c`. Each path uses the same script pathname, dependency environment, weights, and request settings. Each path starts a fresh Studio server with `HF_HUB_OFFLINE=1`.

| Generate request | Process per image (seconds) | Resident prototype (seconds) |
|---|---:|---:|
| First | 9.342 | 9.412 |
| Second | 9.372 | 8.224 |
| Third | 9.397 | 8.405 |
| Median | 9.372 | 8.405 |

The public fixture uses these settings:

| Setting | Value |
|---|---|
| Mode | Generate |
| Prompt | A red ceramic cup on a plain wooden table, soft window light. |
| Size | 512 × 512 |
| Steps | 16 |
| Seed | 7 |
| Quantization | 8 bits |
| References | None |

The harness measures submission through terminal status, with 50 ms polling. It retrieves the result after the timing. All six PNG files have identical bytes and decoded pixels.

The filesystem caches are warm. An earlier pilot primes the caches. The final comparison repeats all six requests with the same offline setting. The pilot numbers do not enter this table. The experiment does not measure a cold machine or purge operating system caches.

The first resident request starts a new worker. Only its second and third requests reuse a loaded model. The resident prototype keeps one model variant at a time. It releases that variant before switching between Generate and Edit. It clears the native prompt cache before and after each request. Thus, the result measures weight reuse without reuse of encoded prompts.

The baseline Python constructor takes 0.700–0.759 seconds per request. The first resident Python constructor takes 0.804 seconds. These constructor timings have no device synchronization. They do not measure the complete weight transfer. Its next two requests reuse that model. The resident path keeps 8.50 GiB of active MLX memory after each Generate request. Its peak MLX allocation reaches 12.33 GiB across the three requests. The baseline peak reaches 11.81 GiB, then the process exits. These figures measure MLX allocation, not total system memory.

A separate pilot checks the mode switch. The pilot has an unmatched offline setting, so its timings do not enter the final comparison. Its resident Edit uses the first generated image as its reference. Its prompt is “A blue ceramic cup on the same plain wooden table, soft window light.” It keeps the same size, steps, and seed. The Edit returns a valid 512 × 512 PNG in 17.405 seconds. A subsequent Generate returns the original PNG bytes in 9.158 seconds. These controls check the variant switch and seed behavior. They do not compare Edit pixels with the baseline or prove cancellation.

Source digests match before and after each path. The isolated copy returns to its original source manifest after the experiment. The Studio server and worker stop before the GPU owner token is removed.

The median reduction is 0.967 seconds, or 10.32%. Three requests per path provide a small sample. The fixed order and warm filesystem caches limit the conclusion. This result makes no statistical significance claim and does not predict other sizes or machines.

The gateway keeps its current lifecycle. The measured saving does not justify 8.50 GiB of idle model memory and an additional worker lifecycle in this change.
