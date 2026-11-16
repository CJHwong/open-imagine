# Measured memory and time

The 16 November 2026 measurements follow the gateway performance changes. The 17 November
2026 run repeated the Qwen-Image-2.1 Turbo and MiniMax H3-Image rows on both machines with the
harness in the tree, which samples free memory during the run and separates the phases.
The 17 November figures are in [the 17 November comparison](#the-17-november-comparison).

They use the Studio API and public fixtures. Each row is one request unless it says otherwise.

- [Apple M5 Pro](#apple-m5-pro)
- [DGX Spark](#dgx-spark)
- [The 17 November comparison](#the-17-november-comparison)
- [Mac and Spark comparison](#mac-and-spark-comparison)
- [Component measurements](#current-component-measurements)

## How to read the tables

GiB means gibibytes.

- **Time** runs from submission to terminal status. It excludes queue wait and weight downloads.
  An empty queue makes the two definitions the same figure. The 17 November rows print the
  operation's own span, from the studio accepting the request to its terminal status, and the
  runner recorded the submit, the fetch and the end-to-end total beside it.
- **Free drop** is the change from baseline to the lowest sampled available memory. A negative value means available memory rose during the run. Background activity affects this value.
  The 17 November runner samples five times a second, from before the submit to the terminal
  status. A model that stays resident between cases shows a small drop on every case after the
  one that loaded it.
- **Peak footprint** is the sampled peak across the process tree. On the Mac it sums physical footprints. Shared pages can be counted more than once. On Spark it sums resident memory and can omit GPU allocations. Do not compare the two directly. The 17 November run did not measure it.
- Measurements use one-second samples. fps means frames per second. Mac footprint values use rounded `footprint` output. A missing peak is shown as `not sampled`.
- A decoded result confirms the output can be read. It does not prove prompt fidelity or equal quality.

Source identifies the frozen code used for each measurement. Sources 1 and 2 precede the final H3 prompt-encoder fix. Sources 4 and 5 hold the native-size H3 studies. Source 6 is the 17 November campaign. Later page and validation changes do not change the measured model path.

| Source | Snapshot SHA-256 |
| --- | --- |
| 1 | `cf52268b6a1c4694102b44606c2c0f749b2f01d6c8e44742b087b3ff24515871` |
| 2 | `b441a062014a6a4f52e769215f1faf1fe5404dd709b97a0cfb303b9b97e6575b` |
| 3 | `aac6350dd097528822befd61c7fec45bfbe0118ac806bcabcb5c5e8e3e795a53` |
| 4 | `e97c6075aa44a376118109e9829892f2e2f78e5cf5887bff4ea525533b15cbeb` (SHA-256 of the 1,018-file source manifest) |
| 5 | `a922b0a3a95448944e7c742789726f73e3821457cb16a5f70b99a0e7e56ff82a` (SHA-256 of the 1,018-file source manifest) |
| 6 | `f47bd8e529a9e0c36235d68c90491993ce2b160f` (campaign recorded by the runner; the runner itself was amended during the campaign, and no measured engine changed) |

The [model setup guide](../how-to/set-up-models.md) lists weights and licenses. The [measurement scripts](../../scripts/measure/README.md) hold the harness, and the 17 November run used them.

## The 17 November comparison

One campaign ran on both machines from the same case list, the same asset bytes and the same
seed. Source 6 records it.

Spark runs Qwen-Image-2.1 Turbo 1.7 to 2.9 times faster than the Mac. The gap widens with the
resolution and with the number of references: 1.7 times at 512 text generation, 2.4 times at
1328, and 2.9 times at ten references.

MiniMax H3-Image does not follow that pattern. The Mac is 2.2 times faster at 1024 and level at
2048 and at the 2048-reference edit. Spark's 1024 figure is a warm repeat; the first run of
that case in a fresh studio took 80.6 s, which includes the load.

`active` is the operation's own span. The Mac reports no free-memory figure, because it has no
`/proc/meminfo`.

| Case | Mac active (s) | Spark active (s) | Spark peak free drop (GiB) |
| --- | ---: | ---: | ---: |
| `qwen21_turbo/generate/text/512` | 5.0 | 3.0 | 0.0 |
| `qwen21_turbo/generate/text/768` | 12.1 | 7.0 | 0.03 |
| `qwen21_turbo/generate/text/1024` | 22.2 | 12.1 | 0.03 |
| `qwen21_turbo/generate/text/1328` | 45.3 | 19.1 | 0.0 |
| `qwen21_turbo/edit/one-ref/out512` | 13.1 | 5.0 | 0.19 |
| `qwen21_turbo/edit/one-ref/out768` | 18.1 | 9.0 | 0.09 |
| `qwen21_turbo/edit/one-ref/out1024` | 34.2 | 15.0 | 0.03 |
| `qwen21_turbo/edit/one-ref/out1344` | 72.5 | 27.1 | 6.53 |
| `qwen21_turbo/edit/2-refs/out1024` | 42.3 | 18.1 | 0.07 |
| `qwen21_turbo/edit/4-refs/out1024` | 62.4 | 25.1 | 0.28 |
| `qwen21_turbo/edit/8-refs/out1024` | 111.8 | 40.1 | 7.18 |
| `qwen21_turbo/edit/10-refs/out1024` | 147.2 | 50.1 | 7.28 |
| `qwen21_turbo/edit/one-ref/in512` | 35.2 | 15.1 | 0.0 |
| `qwen21_turbo/edit/one-ref/in1600x900` | 37.3 | 15.1 | 0.07 |
| `qwen21_turbo/edit/one-ref/in2048` | 35.2 | 16.1 | 0.2 |
| `qwen21_turbo/edit/one-ref/in4032x3024` | 37.2 | 17.1 | 0.46 |
| `minimax_h3_image/generate/1024` | 18.1 | 40.4 | 0.04 |
| `minimax_h3_image/generate/2048` | 47.3 | 55.4 | 0.08 |
| `minimax_h3_image/edit/one-ref-2048` | 128.0 | 134.5 | 60.08 |

Both Qwen columns are bf16. The H3 columns are the Mac's int8 pack and Spark's fp8 pack, so
those three rows compare two different weight formats as well as two machines.

The Spark memory column is the transient pressure of one job, not a model footprint. The model
stays resident between cases, so most rows read near zero. The two rows that read about 7 GiB,
the eight-reference and ten-reference edits, carry the reference batch. The H3 edit reads
60.08 GiB because that case loaded the model in a studio that had released it.

Two H3 generate cases failed on Spark with `CUDA_ERROR_OUT_OF_MEMORY` while the Qwen model was
still resident in the same studio. The edit case in that session succeeded. A studio restart
cleared the memory, and both generate cases then succeeded. The rows above come from the runs
after the restart. The studio left two engine children alive after it exited, and they held
about 106 GiB until they were stopped.

The Mac now completes the 1344 edit in 72.5 s. Source 1 recorded that request as a failure at
the expected memory limit. The engine code changed between the two sources; this run changed
neither the engine nor the page.

## Apple M5 Pro

The Mac has 64 GiB of memory. Image requests use seed 7. Other requests use the seed stated in their fixture.
FLUX.3 and H3-Image load their image engines per call. A warm filesystem cache does not mean their weights stay resident.
Mac Qwen Turbo at 1344 edit resolution hit its expected memory limit. The ten-reference Turbo output lost the pear; base Qwen changed composition with four, eight, and ten references.
The LTX-2.3 previews had dark last frames. Krea reference outputs showed haze. FLUX.2 generation with a reference did not show a distinct pear.

### Image

Qwen uses BF16; FLUX.3 uses q8; H3-Image uses int8; Krea uses packed 8-bit weights.
FLUX.2 uses BF16 transformer weights and an F16 text encoder. Viggle uses BF16 LoRA weights and a BF16/F32 base.

#### FLUX.3 Klein (`flux3`)

| Request | Free drop (GiB) | Peak footprint (GiB) | Time (s) | Result | Source |
| --- | --- | --- | --- | --- | --- |
| generate, size 512 × 512, reported steps 16 | 7.68 | 48.01 | 28.7 | Decoded | 1 |
| generate, size 768 × 768, reported steps 16 | 16.64 | 46.03 | 25.2 | Decoded | 1 |
| generate, size 1024 × 1024, reported steps 16 | 26.88 | 58.03 | 45.4 | Decoded | 1 |
| edit, one reference, output 1024, 16 steps | 23.04 | 62.03 | 104.9 | Decoded | 1 |
| edit, two references, output 1024, 16 steps | 40.32 | 67.03 | 204.7 | Decoded | 1 |

#### Qwen-Image-2.1 (`qwen21`)

| Request | Free drop (GiB) | Peak footprint (GiB) | Time (s) | Result | Source |
| --- | --- | --- | --- | --- | --- |
| edit, size 1024, 10 refs, reported steps 40 | 32.64 | 72.01 | 651.4 | Succeeded (decoded; composition changed) | 1 |
| edit, size 1024, 2 refs, reported steps 40 | 2.35 | 61.01 | 258.2 | Decoded | 1 |
| edit, size 1024, 4 refs, reported steps 40 | 8.32 | 59.01 | 339.7 | Succeeded (decoded; composition changed) | 1 |
| edit, size 1024, 8 refs, reported steps 40 | 36.48 | 68.01 | 550.2 | Succeeded (decoded; composition changed) | 1 |
| edit, size 1024, 4 refs, reported steps 40, total=1, first reference only | 10.88 | 55.01 | 216.7 | Decoded | 1 |
| edit, size 1024, 1 ref, mask, reported steps 40 | 10.88 | 55.01 | 249.1 | Decoded | 1 |
| edit, size 1024, 1 ref, input 1600 × 900, reported steps 40 | 12.16 | 53.01 | 224.9 | Decoded | 1 |
| edit, size 1024, 1 ref, input 2048 × 2048, reported steps 40 | 13.44 | 60.01 | 216.9 | Decoded | 1 |
| edit, size 1024, 1 ref, input 4032 × 3024, reported steps 40 | 17.92 | 59.01 | 226.0 | Decoded | 1 |
| edit, size 1024, 1 ref, input 512 × 512, reported steps 40 | 4.48 | 60.01 | 223.9 | Decoded | 1 |
| edit, size 1024, 1 ref, reported steps 40 | 10.88 | 58.01 | 219.0 | Decoded | 1 |
| edit, size 1344, 1 ref, reported steps 40 | 16.64 | 69.01 | 460.7 | Decoded | 1 |
| edit, size 512, 1 ref, reported steps 40 | 34.56 | 51.01 | 48.5 | Decoded | 1 |
| edit, size 768, 1 ref, reported steps 40 | 30.08 | 56.01 | 104.4 | Decoded | 1 |
| generate, size 1024 × 1024, reported steps 40 | 21.76 | 50.01 | 158.4 | Decoded | 1 |
| generate, size 1328 × 1328, reported steps 40 | 23.04 | 48.01 | 295.5 | Decoded | 1 |
| generate, size 512 × 512, reported steps 40 | 26.24 | 44.01 | 33.5 | Decoded | 1 |
| generate, size 768 × 768, reported steps 40 | 24.96 | 47.01 | 79.8 | Decoded | 1 |

#### Qwen-Image-2.1 Turbo (`qwen21_turbo`)

| Request | Free drop (GiB) | Peak footprint (GiB) | Time (s) | Result | Source |
| --- | --- | --- | --- | --- | --- |
| edit, size 1024, 10 refs, reported steps 8 | 42.45 | 68.01 | 460.8 | Succeeded (decoded; pear missing) | 1 |
| edit, size 1024, 2 refs, reported steps 8 | 42.03 | 50.01 | 55.5 | Decoded | 1 |
| edit, size 1024, 4 refs, reported steps 8 | 39.68 | 54.01 | 75.8 | Decoded | 1 |
| edit, size 1024, 8 refs, reported steps 8 | 41.17 | 62.01 | 337.2 | Decoded | 1 |
| edit, size 1024, 4 refs, reported steps 8, total=1, first reference only | 36.05 | 50.01 | 47.4 | Decoded | 1 |
| edit, size 1024, 1 ref, mask, reported steps 8 | 37.33 | 50.01 | 62.6 | Decoded | 1 |
| edit, size 1024, 1 ref, input 1600 × 900, reported steps 8 | 35.84 | 50.01 | 56.5 | Decoded | 1 |
| edit, size 1024, 1 ref, input 2048 × 2048, reported steps 8 | 36.05 | 50.01 | 49.4 | Decoded | 1 |
| edit, size 1024, 1 ref, input 4032 × 3024, reported steps 8 | 36.69 | 50.01 | 55.6 | Decoded | 1 |
| edit, size 1024, 1 ref, input 512 × 512, reported steps 8 | 36.05 | 50.01 | 44.4 | Decoded | 1 |
| edit, size 1024, 1 ref, reported steps 8 | 36.05 | 50.01 | 35.3 | Decoded | 1 |
| edit, size 1344, 1 ref | 39.89 | 53.01 | 78.6 | Failed (expected limit) | 1 |
| edit, size 512, 1 ref, reported steps 8 | 45.23 | 50.01 | 12.1 | Decoded | 1 |
| edit, size 768, 1 ref, reported steps 8 | 36.05 | 50.01 | 18.1 | Decoded | 1 |
| generate, size 1024 × 1024, reported steps 8 | 46.51 | 50.01 | 23.3 | Decoded | 1 |
| generate, size 1328 × 1328, reported steps 8 | 45.87 | 50.01 | 45.5 | Decoded | 1 |
| generate, size 512 × 512, reported steps 8 | 26.03 | 31.01 | 5.2 | Decoded | 1 |
| generate, size 768 × 768, reported steps 8 | 33.49 | 40.01 | 12.2 | Decoded | 1 |

#### Krea 2 Turbo (`krea2`)

| Request | Free drop (GiB) | Peak footprint (GiB) | Time (s) | Result | Source |
| --- | --- | --- | --- | --- | --- |
| generate, text, requested 512, output 512 × 512, 8 steps | 18.56 | 33.01 | 19.195 | Decoded | 3 |
| generate, text, requested 768, output 768 × 768, 8 steps | 24.96 | 50.01 | 41.384 | Decoded | 3 |
| generate, text, requested 1024, output 1024 × 1024, 8 steps | 12.80 | 50.01 | 89.722 | Decoded | 3 |
| generate, one reference, input 512 × 512, output 1024 × 1024, 8 steps | 31.36 | 50.01 | 64.549 | Succeeded (decoded; haze) | 3 |
| generate, one reference, input 1024 × 1024, output 1024 × 1024, 8 steps | 30.72 | 50.01 | 60.550 | Succeeded (decoded; haze) | 3 |
| generate, one reference, input 2048 × 2048, output 1024 × 1024, 8 steps | 30.72 | 50.01 | 56.513 | Succeeded (decoded; haze) | 3 |
| generate, one reference, input 1600 × 900, output 1360 × 768, 8 steps | 31.36 | 50.01 | 56.482 | Succeeded (decoded; haze) | 3 |
| generate, one reference, input 4032 × 3024, output 1184 × 880, 8 steps | 30.72 | 50.01 | 56.587 | Succeeded (decoded; haze) | 3 |

#### FLUX.2 Klein (`flux2`)

| Request | Free drop (GiB) | Peak footprint (GiB) | Time (s) | Result | Source |
| --- | --- | --- | --- | --- | --- |
| generate, text, requested 512, output 512 × 512, 25 steps | 19.20 | 32.01 | 68.502 | Decoded | 3 |
| generate, text, requested 768, output 768 × 768, 25 steps | 26.88 | 41.01 | 136.441 | Decoded | 3 |
| generate, text, requested 1024, output 1024 × 1024, 25 steps | 42.24 | 49.01 | 243.688 | Decoded | 3 |
| generate, match, input 1600 × 900, output 1360 × 768, 25 steps | 29.44 | 50.01 | 243.306 | Succeeded (decoded; no distinct pear) | 3 |
| edit, one reference, requested 1024, output 1024 × 1024, 25 steps | 34.56 | 50.01 | 545.355 | Decoded | 3 |
| edit, four references, requested 1024, output 1024 × 1024, 25 steps | 35.84 | 50.01 | 1955.587 | Decoded | 3 |
| edit, one reference, input 512 × 512, output 1024 × 1024, 25 steps | 39.04 | 50.01 | 321.420 | Decoded | 3 |
| edit, one reference, input 2048 × 2048, output 1024 × 1024, 25 steps | 32.64 | 49.01 | 547.812 | Decoded | 3 |
| edit, one reference, input 4032 × 3024, output 1184 × 880, 25 steps | 32.00 | 50.01 | 547.747 | Decoded | 3 |

#### Viggle Turbo (`viggle_turbo`)

| Request | Free drop (GiB) | Peak footprint (GiB) | Time (s) | Result | Source |
| --- | --- | --- | --- | --- | --- |
| generate, text, requested 512, output 512 × 512, 6 steps | 27.09 | 34.01 | 6.214 | Decoded | 3 |
| generate, text, requested 1024, output 1024 × 1024, 6 steps | 30.08 | 50.01 | 27.445 | Decoded | 3 |
| edit, one reference, match, output 1024 × 1024, 6 steps | 37.12 | 50.01 | 50.608 | Decoded | 3 |
| edit, one reference, requested 1024, output 1024 × 1024, 6 steps | 5.76 | 50.01 | 44.374 | Decoded | 3 |

#### MiniMax H3-Image (`minimax_h3_image`)

The native-size study uses seed 7 and six steps. The 1024-square generate and edit rows are medians of three runs; other rows use one request. Peak RSS is the largest sampled process-tree resident memory.

| Request | Peak RSS (GiB) | Time (s) | Result | Source |
| --- | ---: | ---: | --- | --- |
| generate 1024x576 | 18.87 | 17.13 | Decoded 1024 × 576 | 4 |
| generate 1024x1024 | 18.89 | 16.75 | Decoded 1024 × 1024 (3 runs) | 5 |
| generate 2048x2048 | 18.89 | 48.37 | Decoded 2048 × 2048 | 4 |
| edit 1024x576 | 18.99 | 36.33 | Decoded 1024 × 576 | 4 |
| edit 1024x1024 | 18.94 | 40.00 | Decoded 1024 × 1024 (3 runs) | 5 |
| edit 2048x2048 | 18.95 | 81.69 | Decoded 2048 × 2048 | 4 |
| edit Match 1600x900 | 18.98 | 67.52 | Decoded 1600 × 900 | 4 |
| edit 4 references 1024x1024 | 1.40 | 136.17 | Decoded 1024 × 1024 | 4 |

### Video

LTX-2.5 and H3 use q8 packs. The LTX-2.3 pack uses 8-bit transformer blocks.
The LTX-2.5 audio-conditioned request uses 33 native steps. Text-only requests use 11.

#### LTX-2.5 (`ltx25_mlx`)

| Request | Free drop (GiB) | Peak footprint (GiB) | Time (s) | Result | Source |
| --- | --- | --- | --- | --- | --- |
| generate, 768 × 768, 97 frames, 1 keyframe, no enhance | 15.36 | 28.08 | 155.3 | Decoded | 3 |
| generate, 768 × 768, 97 frames, 2 keyframes, no enhance | 16.64 | 29.07 | 168.4 | Decoded | 3 |
| generate, 768 × 768, 97 frames, 4 keyframes, no enhance | 15.36 | 29.07 | 192.6 | Decoded | 3 |
| generate, 768 × 768, 97 frames, 8 keyframes, no enhance | 16.00 | 32.07 | 247.1 | Decoded | 3 |
| generate, 768 × 768, 97 frames, no enhance, audio track | 16.00 | 37.07 | 866.6 | Decoded | 3 |
| generate, 768 × 768, 121 frames, fast mode | 19.20 | 24.06 | 142.2 | Decoded | 3 |
| generate, 768 × 768, 121 frames | 15.36 | 24.07 | 192.6 | Decoded | 3 |
| generate, 768 × 768, 25 frames | 16.00 | 23.07 | 53.4 | Decoded | 3 |
| generate, 768 × 768, 49 frames | 15.36 | 24.07 | 82.7 | Decoded | 3 |
| generate, 768 × 768, 97 frames, no enhance | 14.08 | 24.07 | 153.2 | Decoded | 3 |
| generate, 1280 × 704, 97 frames | 17.07 | 26.06 | 200.7 | Decoded | 3 |
| generate, 1920 × 1088, 97 frames | 12.37 | 32.06 | 723.4 | Decoded | 3 |
| generate, 384 × 384, 25 frames | 21.97 | 23.09 | 28.2 | Decoded | 3 |
| generate, 768 × 768, 97 frames | 17.28 | 24.06 | 115.0 | Decoded | 3 |

#### MiniMax H3 video (`minimax_h3`)

| Request | Free drop (GiB) | Peak footprint (GiB) | Time (s) | Result | Source |
| --- | --- | --- | --- | --- | --- |
| generate, 512 × 288, 73 frames, 24 fps | 33.28 | 33.11 | 106.9 | Decoded | 3 |
| generate, 1024 × 576, 175 frames, 24 fps | 32.00 | 33.05 | 1653.8 | Decoded | 3 |

#### LTX-2.3 (`ltx23_mlx`)

| Request | Free drop (GiB) | Peak footprint (GiB) | Time (s) | Result | Source |
| --- | --- | --- | --- | --- | --- |
| generate, text, 768 × 768x97, 24 fps | 15.36 | 24.06 | 159.4 | Decoded (dark last-frame preview) | 3 |
| generate, one keyframe, 768 × 768x97, 24 fps | 14.72 | 34.06 | 922.6 | Decoded (dark last-frame preview) | 3 |

### Voice

Drama uses an 8-bit pack. The seed 11 request unexpectedly reached `max_tokens`. A repeat with the same input and seed failed at the same limit after 65.46 seconds. The original row retains its memory measurements. The longer requests marked as expected limits also reached that limit.

#### Drama-3 (`drama3`)

| Request | Free drop (GiB) | Peak footprint (GiB) | Time (s) | Result | Source |
| --- | --- | --- | --- | --- | --- |
| clone, 7 words, ref 15s | 28.80 | 41.09 | 4.1 | Decoded | 3 |
| clone, 7 words, ref 5s | 28.16 | 41.06 | 4.1 | Decoded | 3 |
| generate, 83 words | 28.80 | 41.08 | 39.3 | Decoded | 3 |
| generate, 7 words | 28.16 | 41.09 | 4.0 | Decoded | 3 |
| generate, 200 words | 28.16 | 41.05 | 67.5 | Failed (expected limit) | 3 |
| generate, 800 words | 28.16 | 41.05 | 67.5 | Failed (expected limit) | 3 |
| generate, 10 words, seed 11 | 28.16 | 42.07 | 95.93 | Failed (max_tokens, unexpected) | 3 |

### Music

YuE2 uses a Q8 generator, BF16 acoustic weights, and an FP32 decoder. The 10-second Cover and transcription requests use replacement speech fixtures. The 10-second transcription is a cache hit; the 15-second transcription is a cache miss.

#### YuE2 (`yue2`)

| Request | Free drop (GiB) | Peak footprint (GiB) | Time (s) | Result | Source |
| --- | --- | --- | --- | --- | --- |
| generate, style, instrumental | 3.84 | 11.15 | 264.0 | Decoded | 3 |
| generate, long lyrics | 3.84 | 10.12 | 213.6 | Decoded | 3 |
| generate, short lyrics | 5.12 | 11.08 | 123.9 | Decoded | 3 |
| plan, style, lyrics | 3.20 | 4.63 | 9.1 | Succeeded (structured result) | 3 |
| cover, 10-second speech | 6.19 | 9.35 | 66.68 | Succeeded | 3 |
| transcribe, 10-second speech, cache hit | 0.00 | 8.53 | 1.04 | Succeeded | 3 |
| transcribe, 15-second speech, cache miss | 1.28 | 4.69 | 5.11 | Succeeded | 3 |

### Mandarin

| Request | Time (s) | Audio | Result | Source |
| --- | --- | --- | --- | --- |
| `drama3`: generate, Traditional Chinese | 4.0 | 5.1 s at 44100 Hz | Decoded | 3 |
| `drama3`: generate, Simplified Chinese | 4.0 | 4.4 s at 44100 Hz | Decoded | 3 |
| `drama3`: generate, Traditional Chinese | 67.5 | none | Failed (expected limit) | 3 |
| `yue2`: generate, Mandarin lyric | 42.4 | 42.2 s at 48000 Hz | Decoded | 3 |

## DGX Spark

The Spark uses an NVIDIA GB10 with 121.7 GiB of unified memory. Requests use seed 7 unless a case says otherwise.
A resident request does not load a new model. A fresh child can still read cached weights.
MP means megapixels. H3-Image CUDA uses the selected working canvas. A non-grid Match uses the nearest 32-pixel canvas and returns the reference dimensions.
Qwen CUDA requests at 1328 × 1328 decode to 1312 × 1312.
The current CUDA LTX backend rejects Fast mode. The CUDA YuE2 backend rejects lyric requests above its 600-character limit.

### Image

#### Qwen-Image-2.1 Turbo CUDA (`qwen21_turbo_cuda`)

| Request | Free drop (GiB) | Peak footprint (GiB) | Time (s) | Result | Source |
| --- | --- | --- | --- | --- | --- |
| generate, 512 × 512, 8 steps, bf16 (bf16, first run) | 34.72 | 18.75 | 26.0 | Decoded | 1 |
| generate, 512 × 512, 8 steps, bf16 | 0.01 | 2.16 | 3.0 | Decoded | 1 |
| generate, 768 × 768, 8 steps, bf16 | 2.90 | 2.18 | 7.0 | Decoded | 1 |
| generate, 1024 × 1024, 8 steps, bf16 | 3.81 | 2.18 | 12.0 | Decoded | 1 |
| generate, 1328 × 1328, 8 steps, bf16, decoded 1312 × 1312 | 5.76 | 2.20 | 20.0 | Decoded | 1 |

#### MiniMax H3-Image CUDA (`minimax_h3_image_cuda`)

The native-size study uses seed 7, six steps, and a resident child. The 1024-square generate and edit rows are medians of three runs; other rows use one request.
Peak RSS is the largest sampled process-tree resident memory. It can omit GPU allocations.

| Request | Peak RSS (GiB) | Time (s) | Result | Source |
| --- | ---: | ---: | --- | --- |
| fp8 generate 1024x576 | 1.43 | 38.42 | Decoded 1024 × 576 | 4 |
| fp8 generate 1024x1024 | 1.57 | 39.87 | Decoded 1024 × 1024 (3 runs) | 5 |
| fp8 generate 2048x2048 | 1.45 | 56.23 | Decoded 2048 × 2048 | 4 |
| fp8 edit 1024x576 | 1.75 | 50.54 | Decoded 1024 × 576 | 4 |
| fp8 edit 1024x1024 | 1.88 | 51.92 | Decoded 1024 × 1024 (3 runs) | 5 |
| fp8 edit 2048x2048 | 1.77 | 68.38 | Decoded 2048 × 2048 | 4 |
| fp8 edit match | 1.80 | 64.32 | Decoded 1600 × 900 | 4 |
| fp8 edit four | 2.01 | 90.76 | Decoded 1024 × 1024 | 4 |
| nvfp4 generate 1024x576 | 1.33 | 19.36 | Decoded 1024 × 576 | 4 |
| nvfp4 generate 1024x1024 | 1.38 | 20.92 | Decoded 1024 × 1024 (3 runs) | 5 |
| nvfp4 generate 2048x2048 | 1.36 | 34.30 | Decoded 2048 × 2048 | 4 |
| nvfp4 edit 1024x576 | 1.74 | 29.51 | Decoded 1024 × 576 | 4 |
| nvfp4 edit 1024x1024 | 1.77 | 31.23 | Decoded 1024 × 1024 (3 runs) | 5 |
| nvfp4 edit 2048x2048 | 1.75 | 44.29 | Decoded 2048 × 2048 | 4 |
| nvfp4 edit match | 1.78 | 41.24 | Decoded 1600 × 900 | 4 |
| nvfp4 edit four | 1.98 | 64.79 | Decoded 1024 × 1024 | 4 |

#### NVFP4 configurations

These rows use the Qwen NVFP4 configuration or the H3 NVFP4 backend. The process footprint was not sampled in this table.

| Request | Free drop (GiB) | Time (s) | Result | Source |
| --- | --- | --- | --- | --- |
| `qwen21_turbo_cuda`: generate, NVFP4, 512 × 512, 8 steps, reported steps 8 (first run) | 34.86 | 31.1 | Decoded | 2 |
| `qwen21_turbo_cuda`: generate, NVFP4, 512 × 512, 8 steps, reported steps 8 | 0.01 | 3.0 | Decoded | 2 |
| `qwen21_turbo_cuda`: generate, NVFP4, 768 × 768, 8 steps, reported steps 8 | 2.94 | 6.0 | Decoded | 2 |
| `qwen21_turbo_cuda`: generate, NVFP4, 1024 × 1024, 8 steps, reported steps 8 | 3.32 | 11.0 | Decoded | 2 |
| `qwen21_turbo_cuda`: generate, NVFP4, 1328 × 1328, 8 steps, reported steps 8, decoded 1312 × 1312 | 5.69 | 18.0 | Decoded | 2 |
| `qwen21_turbo_cuda`: edit, NVFP4, 512 out, 1 reference, reported steps 8 | 0.21 | 3.1 | Decoded | 2 |
| `qwen21_turbo_cuda`: edit, NVFP4, 1344 out, 1 reference at 2048, reported steps 8 | 6.50 | 25.2 | Decoded | 2 |

#### Edit requests

These requests compare generate and edit paths. Each timing includes the recorded request lifecycle.

| Request | Time (s) | Source |
| --- | --- | --- |
| Qwen generate, 512 × 512, 8 steps, warm | 3.0 | 1 |
| Qwen edit, one reference, match | 4.1 | 1 |
| Qwen edit, two references, match | 4.2 | 1 |

#### Prompt enhancement

Each timing includes a fresh enhancer load. H3 stores its prompt encoder as NVFP4 and expands it to BF16 at runtime.

| Request | Time (s) | Result | Source |
| --- | --- | --- | --- |
| Rewrite for generate, first press | 109.3 | Structured result retained | 2 |
| Rewrite for edit, with a picture | 246.7 | Structured result retained | 2 |
| Enhance for generate, first press | 315.8 | Structured result retained | 3 |
| Enhance for edit, with a picture | 415.2 | Structured result retained | 3 |
| H3 enhance for edit, two references | 407.2 | Structured result retained | 3 |

### Video

#### LTX-2.5 CUDA (`ltx25_cuda`)

| Request | Free drop (GiB) | Peak footprint (GiB) | Time (s) | Result | Source |
| --- | --- | --- | --- | --- | --- |
| generate, 768 × 448, 97 frames, distilled eight-step schedule | 0.32 | 12.43 | 46.4 | Decoded | 1 |
| generate, 1280 × 704, 97 frames, distilled eight-step schedule | 8.38 | 13.13 | 117.4 | Decoded | 1 |
| generate, 768 × 768, 97 frames, distilled eight-step schedule | 5.66 | 12.81 | 76.4 | Decoded | 1 |
| generate, 768 × 512, 97 frames, one keyframe at frame 0, strength 1.0 | 0.04 | 11.84 | 56.5 | Decoded | 1 |

The following LTX-2.5 requests use BF16, 97 frames, 24 fps, audio, and prompt enhancement. Their process footprint was not sampled.

| Size | Model state | Time (s) |
| --- | --- | --- |
| 768×768 | Fresh child; includes model loading | 114.041 |
| 1280×704 | Model resident; first request at this size | 121.371 |

### Voice

#### Drama-3 CUDA (`drama3_cuda`)

| Request | Free drop (GiB) | Peak footprint (GiB) | Time (s) | Result | Source |
| --- | --- | --- | --- | --- | --- |
| generate, 7 words, 5.4 s of decoded audio at 44100 Hz | 0.41 | 4.06 | 8.0 | Decoded | 1 |
| generate, 13 words, one delivery cue | 0.36 | 4.06 | 7.0 | Decoded | 1 |
| generate, 83 words, 32.6 s of decoded audio at 44100 Hz | 1.38 | 4.06 | 45.1 | Decoded | 3 |
| generate, 83 words, 32.6 s of decoded audio at 44100 Hz (second pass) | 1.30 | 4.07 | 45.1 | Decoded | 3 |
| clone, 7 s reference, 4.5 s of decoded audio at 44100 Hz | 0.31 | 4.19 | 7.1 | Decoded | 1 |
| generate, Traditional Chinese, 3.7 s of decoded audio at 44100 Hz | 0.02 | 3.97 | 6.0 | Decoded | 1 |
| generate, Simplified Chinese, 3.9 s of decoded audio at 44100 Hz | 0.32 | 3.97 | 6.0 | Decoded | 1 |
| generate, Traditional Chinese, 19.6 s of decoded audio at 44100 Hz | 2.07 | 4.03 | 27.1 | Decoded | 1 |
| generate, no reference, 4.2 s of decoded audio at 44100 Hz | 0.35 | 4.03 | 6.0 | Decoded | 1 |
| clone, synthetic zh_TW reference, 3.6 s of decoded audio at 44100 Hz | 0.30 | 4.07 | 6.1 | Decoded | 1 |
| clone, 4.6 s human reference, 2.7 s of decoded audio at 44100 Hz | 0.25 | 4.07 | 5.0 | Decoded | 1 |
| clone, 10 s human reference, 2.7 s of decoded audio at 44100 Hz | 0.29 | 4.07 | 5.1 | Decoded | 1 |

### Music

#### YuE2 CUDA (`yue2_cuda`)

| Request | Free drop (GiB) | Peak footprint (GiB) | Time (s) | Result | Source |
| --- | --- | --- | --- | --- | --- |
| nvfp4, generate, style and one lyric line, 104.4 s of decoded audio at 48000 Hz | 10.29 | 5.35 | 120.3 | Decoded | 1 |
| nvfp4, generate, Mandarin style and lyric, 34.6 s of decoded audio at 48000 Hz | 3.30 | 5.47 | 33.1 | Decoded | 1 |
| bf16, generate, style and one lyric line, 67.6 s of decoded audio at 48000 Hz | 6.90 | 9.66 | 117.2 | Decoded | 3 |
| bf16, generate, Mandarin style and lyric, 41.7 s of decoded audio at 48000 Hz | 6.19 | 9.78 | 98.2 | Decoded | 1 |
| fp8, generate, style and one lyric line, 65.0 s of decoded audio at 48000 Hz | 18.59 | 14.29 | 203.4 | Decoded | 2 |
| fp8, generate, Mandarin style and lyric, 56.9 s of decoded audio at 48000 Hz | 6.64 | 11.26 | 131.3 | Decoded | 2 |
| generate, one repeated line, 159 characters, 39.8 s of decoded audio at 48000 Hz | 6.47 | 9.90 | 91.2 | Decoded | 1 |
| generate, one repeated line, 311 characters, 77.6 s of decoded audio at 48000 Hz | 7.18 | 9.93 | 137.3 | Decoded | 1 |
| generate, one repeated line, 463 characters, 84.9 s of decoded audio at 48000 Hz | 6.54 | 9.96 | 144.3 | Decoded | 1 |
| generate, style and no lyrics, 187.5 s of decoded audio at 48000 Hz | 6.70 | 10.16 | 231.5 | Decoded | 1 |

#### BF16 lyric lengths

The first and warm short requests use the same worker. The other cases use their recorded model states.

| Request | Free drop (GiB) | Time (s) | Result | Source |
| --- | --- | --- | --- | --- |
| `yue2_cuda`: generate, bf16, 33 characters, 67.6 s of decoded audio at 48000 Hz (first run) | 17.87 | 207.4 | Decoded | 3 |
| `yue2_cuda`: generate, bf16, 272 characters, 79.5 s of decoded audio at 48000 Hz | 5.64 | 147.3 | Decoded | 1 |
| `yue2_cuda`: generate, bf16, 413 characters, 222.1 s of decoded audio at 48000 Hz | 7.82 | 333.9 | Decoded | 1 |
| `yue2_cuda`: generate, bf16, 535 characters, 136.0 s of decoded audio at 48000 Hz | 6.13 | 198.4 | Decoded | 1 |
| `yue2_cuda`: bf16, style and one lyric line | 1.72 | 17.0 | Succeeded (structured result) | 1 |

#### Transcription and Cover

These requests use a verified public 20-second reference. The repeat uses the same worker and cached transcription. HTTP (Hypertext Transfer Protocol) time includes polling; native time measures the operation. RSS means resident set size.

| Request | HTTP time (s) | Native time (s) | Free drop (GiB) | Peak RSS (GiB) |
| --- | --- | --- | --- | --- |
| transcribe first | 27.144 | 26.81980 | 5.809 | 13.10 |
| transcribe repeat | 1.068 | 0.07597 | -0.036 | 9.76 |
| cover | 72.229 | 71.25909 | 6.615 | 9.86 |

### H3-Image pack setup

Each request uses the same public prompt, seed 7, six steps, and 1024 × 1024 output.
A build starts without a pack. A reload starts a fresh child with that pack; it is not warm inference.
Fresh and reloaded output PNGs match their corresponding original-pack output. The check compares tensor headers, not all fresh-pack payload bytes.

| Request | Time (s) | Peak RSS (GiB) | Minimum available (GiB) |
| --- | --- | --- | --- |
| fp8 / build-and-generate | 333.015 | 100.55 | 20.33 |
| fp8 / cached-reload-and-generate | 94.587 | 26.03 | 57.33 |
| nvfp4 / build-and-generate | 332.200 | 106.60 | 17.94 |
| nvfp4 / cached-reload-and-generate | 64.350 | 17.25 | 73.45 |

## Mac and Spark comparison

These requests use the same public prompts, reference inputs, exposed settings, and seed 7 on both machines.
The backend identifiers differ. For Qwen, the Mac `cfg` maps to CUDA `guidance` at the same value.
The earlier YuE2 CUDA adapter ignored `steps` and `cfg_scale`. These requests match its engine defaults.
The current adapter forwards both settings. See the component measurements for the real-model check.
The same seed does not guarantee identical random numbers or outputs across MLX and CUDA.
The H3 rows compare medians of three requests per machine. Each other row compares one request per machine.
The table covers four Qwen sizes, one LTX video, three Drama requests, three YuE2 requests, and H3 generation and edits at two Spark precisions.
The ratio is Mac time divided by Spark time. It does not isolate hardware speed.
For 1328-square Qwen, Mac output is 1328-square and Spark output is 1312-square.
H3 uses the selected canvas on both hosts. Audio durations differ.

| Model | M5 Pro precision | Spark precision | Model state |
| --- | --- | --- | --- |
| Qwen Turbo | BF16 | BF16 | Mac after warmup; Spark resident after warmup |
| LTX-2.5 | Native MLX Q8 pack | BF16 | Fresh pipeline or child on both hosts |
| Drama-3 | MLX 8-bit pack | FP8 W8A8 | Same-backend warmup on both hosts |
| YuE2 instrumental | Q8 generator, BF16 acoustic, FP32 decoder | BF16 | Same-backend warmup on both hosts |
| YuE2 lyrics | Q8 generator, BF16 acoustic, FP32 decoder | NVFP4 lyric stages, BF16 acoustic decoder | Same-backend warmup on both hosts |
| H3-Image | Native MLX int8 pack | FP8 transformer with NVFP4 text encoder, or NVFP4 pack | Mac per-call stages; Spark resident child |

| Request | M5 Pro (s) | Spark (s) | Mac / Spark |
| --- | --- | --- | --- |
| Qwen Turbo generate, 512 × 512, 8 steps | 5.160 | 3.009 | 1.71x |
| Qwen Turbo generate, 768 × 768, 8 steps | 12.221 | 7.020 | 1.74x |
| Qwen Turbo generate, 1024 × 1024, 8 steps | 23.305 | 12.033 | 1.94x |
| Qwen Turbo generate, 1328 × 1328, 8 steps | 46.486 | 20.048 | 2.32x |
| LTX-2.5 generate, 768 × 768, 97 frames | 115.829 | 137.379 | 0.84x |
| Drama-3 generate, 7 words | 4.047 | 6.031 | 0.67x |
| YuE2 generate, instrumental (Spark BF16, Mac Q8) | 262.982 | 270.690 | 0.97x |
| Drama-3 clone, one reference | 4.047 | 6.060 | 0.67x |
| YuE2 generate, short (Spark NVFP4, Mac Q8) | 144.177 | 71.175 | 2.03x |
| YuE2 generate, Mandarin lyric (Spark NVFP4, Mac Q8) | 39.288 | 30.063 | 1.31x |
| Drama-3 generate, 83 words | 26.216 | 56.122 | 0.47x |
| MiniMax H3-Image generate, 1024 × 1024, Spark FP8, Mac int8 | 16.754 | 39.872 | 0.42x |
| MiniMax H3-Image generate, 1024 × 1024, Spark NVFP4, Mac int8 | 16.754 | 20.920 | 0.80x |
| MiniMax H3-Image edit, 1024 × 1024, one reference, Spark FP8, Mac int8 | 40.001 | 51.917 | 0.77x |
| MiniMax H3-Image edit, 1024 × 1024, one reference, Spark NVFP4, Mac int8 | 40.001 | 31.232 | 1.28x |

### Linear kernel measurements

These Spark measurements cover isolated linear layers, not full requests.

| Measure | BF16 | NVFP4 weight-only | NVFP4 W4A4 |
| --- | --- | --- | --- |
| 512 tokens | 0.23 ms | 0.44 ms | 0.08 ms |
| 4096 tokens | 1.44 ms | 1.71 ms | 1.13 ms |
| 8192-square physical weights | 128 MiB | 36 MiB | 36 MiB |

## Current component measurements

These are component checks, not full request times. They use the final optimized paths.

| Component | Host and scope | Time | Memory |
| --- | --- | --- | --- |
| YuE2 CUDA transcription cache hit | Spark, same 20-second reference and task | 1.068 s HTTP; 0.07597 s native | 9.76 GiB sampled peak RSS |
| LTX-2.5 CUDA encoding | Spark, saved 1280 × 704 frames | 1.347 s median | 1.902 GiB peak process memory |
| H3 video encoding | M1 Pro, 97 frames at 1280 × 704 | 5.96 s median | 2.96 MiB peak traced Python allocation |
| H3-Image CUDA pack rewrite | Spark, existing FP8 pack, excluding quantization and fsync | 48.407 s | 45.96 GiB sampled peak process memory |

The encoding tests use three runs per path. The H3 video figure excludes the frame array and FFmpeg memory.
The pack rewrite checks all 3,722 stored tensors against the original. It is not a cold pack build.
See the [LTX CUDA notes](../../studio/l3_interface_adapters/gateways/video/ltx25_cuda/README.md), [H3 video notes](../../studio/l3_interface_adapters/gateways/video/minimax_h3/README.md), and [H3 image notes](../../studio/l3_interface_adapters/gateways/image/minimax_h3_image_cuda/README.md) for the methods.

### H3-Image canvas and initial noise

On Spark, six 1 MP requests per noise method had median request times of 41.20 s with PyTorch noise and 41.19 s with NumPy noise.
Three 4 MP controls took 55.29 s median. The study used three prompts and seeds 7 and 731.
NumPy noise changes the output. This small visual sample does not establish equal image quality.
The gateway now uses the selected size, by user choice. See the [H3 image notes](../../studio/l3_interface_adapters/gateways/image/minimax_h3_image_cuda/README.md) for the test.

### Drama-3 stage profile

Each result is the median of three warm requests with seed 7. The diagnostic polls every 0.5 seconds.
The backends use different engines and weight formats. Stage timings include diagnostic overhead.

| Request | Host | Request median | Audio length | Request seconds per audio second |
| --- | --- | ---: | ---: | ---: |
| Short speech | M5 Pro | 2.54 s | 3.48 s | 0.730 |
| Short speech | Spark | 5.53 s | 3.58 s | 1.547 |
| Long speech | M5 Pro | 25.43 s | 34.83 s | 0.730 |
| Long speech | Spark | 56.27 s | 40.45 s | 1.391 |

Spark used CUDA graphs in every request. For long speech, median token queue wait was 47.42 s and audio decode was 8.50 s.
On the Mac, median frame generation was 22.47 s and audio decode was 2.57 s.
The stages can overlap. Different chunking and diagnostic synchronization prevent a direct stage-by-stage attribution.
All outputs passed finite, non-silent audio checks. The Mac diagnostic child was not hash-bracketed during each run.

### YuE2 CUDA settings experiment

These warm runs use the same public short lyric, seed 7, and guidance 1.0. Each median uses three requests.
The instrumented child includes the settings fix. Its extra metadata records the engine stage times.
The BF16 and NVFP4 outputs have different durations, so the results do not isolate precision alone.

| CUDA weights | Synthesis steps | Request median | Audio length | Request seconds per audio second | Synthesis median | Decode median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NVFP4 | 32 | 70.17 s | 104.36 s | 0.672 | 15.47 s | 16.27 s |
| NVFP4 | 8 | 67.17 s | 104.36 s | 0.644 | 4.08 s | 24.04 s |
| BF16 | 32 | 119.25 s | 67.56 s | 1.765 | 8.62 s | 52.47 s |

The 8-step runs reduce synthesis time. Decode time varies, so the total saving is smaller in this sample.
The test checks finite, non-silent stereo audio. It does not establish equivalent audio quality.
One 16-step request and one guidance 1.5 request also used their requested settings. A later request restored 32 steps.
Both CUDA live tests passed against the uninstrumented fix.

### YuE2 CUDA decoder tile experiment

A public request supplied one fixed 104.36-second audio latent. Each tile size decoded it three times after a warmup.
The isolated test synchronized CUDA and measured the decoder, not the full request.

| Core frames | Median decode | Peak CUDA allocation | Maximum waveform difference |
| --- | ---: | ---: | ---: |
| 1,024 | 5.185 s | 2.67 GiB | Reference |
| 2,048 | 4.817 s | 4.75 GiB | 0.0000091 |

The larger tile saves 0.37 s and adds about 2.1 GiB of peak allocation in this sample. The gateway keeps the current tile size.
Both outputs are finite, non-silent stereo audio. This does not establish perceptual equivalence.
The request driver could not find `ffprobe` after it saved the audio. A separate decoder check verified the files and source hashes.
The driver did not retain the full request time or its host memory samples. The table uses the saved decoder trials only.

## Coverage and limits

The 16 November campaign accounts for 183 planned case IDs. Of these, 178 reached their expected outcome.
Four use replacement reference fixtures. One Drama request unexpectedly reached `max_tokens`.
Expected outcomes include expected errors and limits. They do not all represent successful media generation.
Warmups, retries, comparison requests, and component checks are separate from that count.
The 17 November campaign ran 19 of the 46 case IDs that `parity_matrix.py` writes.

| Check | Coverage and result |
| --- | --- |
| Mac and Spark comparison | 15 matched rows. Public inputs and seed match; precision and some output geometry differ. |
| 17 November parity run | 19 image cases on each machine, and all succeeded. Video, voice and music were not re-run. The Mac reports no free-memory figure. |
| macOS CPU suite | 3,601 tests passed with the 17 November changes. Statement and branch coverage reached 100%. |
| macOS CPU suite, 16 November | 3,587 tests passed after the H3 and YuE2 fixes. Statement and branch coverage reached 100%. |
| MLX product checks | Page: 181 checks passed. Batch: 12 passed. Backend switch: 19 passed. |
| H3 MLX video | Both real model tests passed. |
| Spark targeted suite | 690 tests passed. Real CUDA checks covered generation, edit, cancellation, and a backend switch. |
| Spark broad suite | 3,496 passed and 45 failed. Two Apple-only test modules could not load. |

The Spark broad-suite failures include unavailable Apple dependencies, a file-order assumption, and a macOS binary.
These results do not establish full Linux test-suite support. The matrix does not measure output quality equivalence.

Older experiments and full provenance remain available in [the previous revision](https://github.com/CJHwong/open-imagine/blob/6530af727d5d1e664593e426372d9c713f1536a5/docs/reference/measured-memory-and-time.md).
