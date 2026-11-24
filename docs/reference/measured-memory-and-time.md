# Measured memory and time

The 16 November 2026 measurements follow the gateway performance changes. The 17 November
2026 run repeated every case on both machines with the harness in the tree, which samples free
memory during the run and separates the phases: all 46 cases, across image, video, voice and
music. The 17 November figures are in [the 17 November comparison](#the-17-november-comparison).

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
| 6 | `18c45f92f60e8c312396cf5119ddc6fb5c78ffb5` (the tree the runner recorded; the case payloads changed in `b9e0f87` before this campaign ran, and no measured engine changed) |

The [model setup guide](../how-to/set-up-models.md) lists weights and licenses. The [measurement scripts](../../scripts/measure/README.md) hold the harness, and the 17 November run used them.

## The 17 November comparison

One campaign ran on both machines from the same case list, the same asset bytes and the same
seed. It covers all 46 cases that `parity_matrix.py` writes, across image, video, voice and
music. Source 6 records it. The records, the media and the CSV sit outside this repository.

The campaign changed its prompt before it ran. An earlier pass used a harbour scene that both
image engines rendered badly: the painted sign came out garbled, the hands were mush, and a
backlit subject against open haze left a flat frame with no separation. The payload now asks for
a still life of two red enamel pots on a stone sill, and it names the light direction, the lens
and the depth of field. A row-for-row comparison with that earlier 19-case pass does not hold,
because the text changed: the 1328 generation reads 52.8 s here against 45.3 s there.

`active` is the operation's own span, from the studio accepting the request to its terminal
status. The Mac reports no free-memory figure, because it has no `/proc/meminfo`.

The first case of a workspace pays that workspace's model load. Each of those five cases ran
twice, and the second figure is the one below.

| Case | Mac active (s) | Spark active (s) | Spark peak free drop (GiB) |
| --- | ---: | ---: | ---: |
| `drama3/clone/ref12s` | 5.0 | 8.1 | 0.42 |
| `drama3/clone/ref5s` | 14.1 | 8.1 | 0.38 |
| `drama3/generate/paragraph700` | 21.2 | 45.1 | 1.14 |
| `drama3/generate/sentence50` | 2.0 | 8.1 | 0.4 |
| `drama3/generate/text1000` | 47.3 | 105.3 | 1.92 |
| `drama3/generate/text4000` | failed | 434.2 | 3.46 |
| `drama3/generate/text50-seed11` | 3.0 | 6.0 | 0.29 |
| `ltx25/generate/1-keyframes/768x768x97` | 112.8 | 85.5 | 0.61 |
| `ltx25/generate/2-keyframes/768x768x97` | 119.9 | 81.3 | 0.62 |
| `ltx25/generate/4-keyframes/768x768x97` | 135.0 | 85.5 | 0.62 |
| `ltx25/generate/8-keyframes/768x768x97` | 172.3 | 88.5 | 0.62 |
| `ltx25/generate/fast/768x768x121` | 108.8 | rejected | rejected |
| `ltx25/generate/frames/121` | 139.0 | 128.7 | 0.37 |
| `ltx25/generate/frames/25` | 44.3 | 31.2 | 0.34 |
| `ltx25/generate/frames/49` | 64.4 | 51.2 | 0.36 |
| `ltx25/generate/no-enhance/768x768x97` | 105.8 | 85.7 | 0.62 |
| `ltx25/generate/text/1280x704x97` | 197.5 | 120.5 | 9.06 |
| `ltx25/generate/text/1920x1088x97` | 550.1 | 413.9 | 20.19 |
| `ltx25/generate/text/384x384x25` | 26.2 | 19.1 | 0.26 |
| `ltx25/generate/text/768x768x97` | 114.9 | 78.3 | 0.63 |
| `minimax_h3_image/edit/one-ref-2048` | 152.2 | 90.4 | 0.39 |
| `minimax_h3_image/generate/1024` | 20.1 | 41.2 | 0.02 |
| `minimax_h3_image/generate/2048` | 56.5 | 57.4 | 0.07 |
| `qwen21_turbo/edit/10-refs/out1024` | 192.6 | 52.2 | 9.1 |
| `qwen21_turbo/edit/2-refs/out1024` | 52.4 | 18.1 | 0.12 |
| `qwen21_turbo/edit/4-refs/out1024` | 76.6 | 25.1 | 0.18 |
| `qwen21_turbo/edit/8-refs/out1024` | 136.1 | 41.1 | 8.76 |
| `qwen21_turbo/edit/one-ref/in1600x900` | 44.3 | 15.1 | 0.1 |
| `qwen21_turbo/edit/one-ref/in2048` | 43.3 | 16.1 | 0.13 |
| `qwen21_turbo/edit/one-ref/in4032x3024` | 45.3 | 17.1 | 0.32 |
| `qwen21_turbo/edit/one-ref/in512` | 42.4 | 15.0 | 0.03 |
| `qwen21_turbo/edit/one-ref/out1024` | 41.3 | 15.0 | 0.06 |
| `qwen21_turbo/edit/one-ref/out1344` | 86.7 | 27.1 | 4.43 |
| `qwen21_turbo/edit/one-ref/out512` | 12.3 | 4.0 | 0.28 |
| `qwen21_turbo/edit/one-ref/out768` | 21.3 | 9.1 | 0.06 |
| `qwen21_turbo/generate/text/1024` | 28.3 | 12.1 | 0.02 |
| `qwen21_turbo/generate/text/1328` | 52.8 | 20.1 | 6.5 |
| `qwen21_turbo/generate/text/512` | 5.0 | 3.0 | 0.02 |
| `qwen21_turbo/generate/text/768` | 14.1 | 7.1 | 0.02 |
| `yue2/cover/speech10s` | 64.5 | 199.4 | 6.43 |
| `yue2/generate/instrumental` | 138.0 | 193.5 | 7.54 |
| `yue2/generate/long` | 140.0 | 188.5 | 7.03 |
| `yue2/generate/short` | 118.9 | 115.3 | 6.44 |
| `yue2/plan/short` | 14.1 | 16.0 | 1.77 |
| `yue2/transcribe/speech10s` | 7.1 | 27.1 | 5.8 |
| `yue2/transcribe/speech15s` | 5.1 | 21.1 | 5.51 |

The Qwen columns are both bf16. Spark is faster on every row, from 1.7 times at 512 text
generation (5.0 s against 3.0 s) to 3.7 times at ten references (192.6 s against 52.2 s). The
gap grows with the output size and with the reference count.

The H3 columns are not one weight format: the Mac runs the int8 pack and the Spark runs fp8.
The Mac is twice as fast at 1024 (20.1 s against 41.2 s), the two are level at 2048 (56.5 s
against 57.4 s), and the Spark is faster on the edit of a 2048 reference (90.4 s against
152.2 s).

Spark is faster on all twelve video rows it ran. A 768 square clip is 78.3 s against 114.9 s,
and a 1920 by 1088 clip is 413.9 s against 550.1 s. The Spark also holds its figure as keyframes
are added, 85.5 s at one and 88.5 s at eight, where the Mac grows from 112.8 s to 172.3 s.

The Fast mode row reads `rejected` on Spark because `ltx25_cuda` declares no Fast mode, and the
gateway refuses the request with that reason. The Mac ran 121 frames in 108.8 s; the same 121
frames without Fast mode took 139.0 s.

Drama-3 generation is faster on the Mac: 50 words in 2.0 s against 8.1 s, and 1000 words in
47.3 s against 105.3 s. The 800-word request reached the token limit on the Mac and failed,
where the Spark completed it in 434.2 s. That is the `max_tokens` limit recorded in the earlier
Drama rows, not a machine fault.

YuE2 is mixed. The Mac is three times faster on a ten-second cover (64.5 s against 199.4 s) and
faster on a long song and on an instrumental, and the two are level on the short song (118.9 s
against 115.3 s).

The Spark memory column is the transient pressure of one job, not a model footprint. Most rows
read near zero because the model stays resident between cases. The large ones follow the work
size: 20.19 GiB at 1920 by 1088, 9.06 GiB at 1280 by 704, 9.1 GiB for ten references, and
8.76 GiB for eight.

This campaign did not repeat the out-of-memory failures recorded in the earlier image pass. The
H3 cases ran in the same studio after the Qwen cases, and both succeeded. The studio still
leaves its engine children alive after it exits; that fault was observed here and is not fixed.

The Mac completes the 1344 edit in 86.7 s. Source 1 recorded that request as a failure at the
expected memory limit. The engine code changed between the two sources; this run changed neither
the engine nor the page.

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

Pictures were measured on 2026-11-24 through the Studio operations API, from commit `6a9f2a0`, warm:
512 × 288, 73 frames, seed 7. Peak memory was not sampled on this path. A scratch copy of the worker
on the same day read 33.1 GiB with two pictures, against 33.0 GiB for text.

| Request | Time (s) | Result |
| --- | --- | --- |
| generate, two pictures | 103.5 | Decoded |
| generate, a first frame and one picture | 99.3 | Decoded |

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

What each enhancer costs before it writes, measured on 18 November 2026. Each figure is the
child's own `loaded ... in` line, or the time to its first sign of work where it has none.

| Enhancer | Machine | Environment | Load | First rewrite |
| --- | --- | --- | --- | --- |
| H3 Image PE | spark | cached, 188 ms | 182.5 s | not run |
| Qwen PE T2I | spark | cached, 4 ms | 4.5 s | 40 s |
| Qwen PE I2I | spark | cached, 2 ms | 4.9 s | 98 s |
| Gemma 3 for LTX | office, MLX | cached | about 2 s | 7 s |

The H3 encoder stores NVFP4 and expands it to BF16, so its load is the expansion and the
encoder computes in BF16 after it; that expansion is the whole cost. The other three load
weights directly, which is why they start in seconds. The Qwen and Gemma figures were taken
with the card already in the page cache, so a cold disk read adds to them. A rewrite keeps
the card resident, which is why the first-press figures below are much larger than a warm
press.

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

#### MiniMax H3 CUDA (`minimax_h3_cuda`)

Measured on 2026-11-20 through the Studio operations API, from commit `3076ad7`: 512 × 288, 124
frames, seed 7, one request at a time, in Fast mode (20 steps) except the cancelled run. An idle studio with the model loaded
had 62 GiB less free memory than before its first clip.

| Request | Time (s) | Result |
| --- | --- | --- |
| generate, text, first clip of the child, load included | 226.7 | Decoded |
| generate, text, warm | 82.3 | Decoded |
| generate, first and last frame, warm | 88.5 | Decoded |
| generate, one picture and a 5 s audio track, warm | 360.6 | Decoded; this run muxed the input track, which `502393f` replaced with the generated sound at no change to the run |
| generate, 50 steps, cancelled at 60 s | 62.1 | Cancelled at step 19 |

The estimate's fit came from five more warm runs on 2026-11-21, from commit `502393f`: text, Fast
mode, seed 7. A step is the gap between two step reports.

| Request | Time per step (s) | Time (s) | Result |
| --- | --- | --- | --- |
| generate, 512 × 288, 124 frames | 3.30 | 79.5 | Decoded |
| generate, 512 × 512, 124 frames | 6.14 | 145.0 | Decoded |
| generate, 1024 × 576, 124 frames | 17.86 | 380.8 | Decoded |
| generate, 1280 × 704, 124 frames | 33.09 | 716.7 | Decoded |
| generate, 512 × 288, 345 frames | 11.52 | 271.3 | Decoded |

Pictures were measured on 2026-11-24 through the Studio operations API, from commit `6a9f2a0`:
512 × 288, 124 frames, seed 7, Fast mode, one request at a time. Free memory was 124.6 GiB before
the first clip and 47.7 GiB at its last step, one sample, not a sampled peak.

| Request | Time (s) | Result |
| --- | --- | --- |
| generate, two pictures, first clip of the child, load included | 527.9 | Decoded |
| generate, one picture and a 5 s audio track, warm | 222.9 | Decoded |

The [H3 CUDA notes](../../studio/l3_interface_adapters/gateways/video/minimax_h3_cuda/README.md)
hold the FP8 and NVFP4 comparison and the load measurements.

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

### The 19 November speed pass

Each table row ran through the Studio operations API on a DGX Spark, against a server on its
own port with the revision checked before the run. Times run from submission to terminal
status and include polling. A figure in the prose that came from driving the engine child
directly says so.

Image, MiniMax H3-Image fp8 (`minimax_h3_image_cuda`). The fp8 build now multiplies in fp8,
one scale per row, in the encoder and the transformer. The earlier build held
weights in fp8 or NVFP4 and widened them on every pass. Six steps, seed 7.

| Request | Before (s) | After (s) |
| --- | ---: | ---: |
| generate 1024 × 576 | 38.42 | 4.03 |
| generate 1024 × 1024 | 41.3 | 6.55 |
| generate 2048 × 2048 | 57.4 | 30.35 |
| edit 1024 × 1024, one 512 reference | 52.32 | 20.73 |
| edit 2048 × 2048, one 512 reference | 68.38 | 57.59 |
| edit 1024 × 1024, four 512 references | 90.76 | 94.48 |
| edit to Match, one 2048 reference | 91.0 | 90.2 |
| first image, pack load included | 95.0 | 43.2 to 58.3 |

An edit with a large reference does not gain, because the reference's tokens join the
sequence and attention takes most of the time: 77.9 of 88.1 s at 2048, timed in the child. Five prompt and seed
pairs and one edit looked the same before and after, including the rendered title of a text
poster. A studio idle with the fp8 model loaded held 77.4 GiB.

The text encoder has 64 layers, and H3 reads the state that enters layer 50. The child now drops layers 51 to 63 and the output head when it builds or loads a pack, so the pack is 59 GiB and a loaded studio holds 8.4 GiB less: 60.4 GiB against 68.8 GiB after the first image. Generate at 1024 and 2048 and the edit to Match gave the same bytes as before, from an old pack and from a new one, and the same time to within 0.3 s. A fresh build and its first image took 99.9 s, and available memory stayed at 53.6 GiB or more. An older pack still loads; the child skips the layers it drops.

Before that change, the pack was 66 GiB. Building it in a script that runs the child's own build took 49.9 s with the checkpoint on disk and
writing it 43.0 s, and available memory stayed at 45.8 GiB or more. The 17 November build
fell to 20.3 GiB. Two changes keep it there: each bf16 linear is quantized as it lands, and
the pack is written one tensor at a time. Without them the W8A8 build fell to 3.9 GiB.

Video, LTX-2.5 BF16 (`ltx25_cuda`), with the transformer's repeated block compiled.
No prompt enhancement unless the row says so.

| Request | Eager (s) | Compiled (s) |
| --- | ---: | ---: |
| 768 × 768, 97 frames, warm | 70.8 | 53.0 |
| 768 × 768, 97 frames, first run, load included | 119.6 | 111.3 |
| 1280 × 704, 97 frames, first run at that size | 110.0 | 89.7 |
| 384 × 384, 25 frames, first run at that size | 7.6 | 12.1 |
| 384 × 384, 25 frames, repeat | 7.55 | 6.57 |
| 768 × 768, 97 frames, two keyframes | not run | 53.4 |
| 768 × 768, 97 frames, prompt enhancement, first run | not run | 120.9 |

Each canvas and length compiles its own graph, and the page offers 30. PyTorch compiles 8 at
most and runs every later one eager, so the child raises that limit to 64. In one process, the
tenth and eleventh lengths ran in 62.9 and 79.1 s on their first, compiling run, against 74.1
and 104.7 s eager before the change.

The child decodes a clip in tiles and hands PyTorch's cached memory back after each clip. A
clip's peak used to stay in the cache, so a session that grew to 99.7 GiB ran the next long clip
out of memory. Warm, the second run at each size, with audio and prompt enhancement:

| Clip | 5 s (s) | 10 s (s) | 15 s (s) |
| --- | ---: | ---: | ---: |
| 384 × 384 | 26.5 | 42.8 | 59.3 |
| 512 × 512 | 38.8 | 69.0 | 103.1 |
| 768 × 768 | 76.5 | 159.8 | 275.5 |
| 1024 × 576 | 77.5 | 159.9 | 275.3 |
| 1280 × 704 | 123.6 | 282.5 | 488.5 |
| 1920 × 1088 | 350.1 | not run | not run |

The 15 s clips at 768 × 768, 1024 × 576 and 1280 × 704 ran out of memory before the tiled
decode. Driven in the child, the 768 × 768, 15 s clip now peaks at 84.5 GiB with 14 GiB still
available, and a 5 s clip decodes in 4.4 s against 5.1 s. Tiled and whole frames differ by
45.3 dB, only where the tiles overlap. After every clip above, the engine held 78.2 GiB, its
weights. The 384 and 512 rows ran before the tiled decode.

Image, Qwen-Image-2.1 Turbo BF16 (`qwen21_turbo_cuda`), with the transformer compiled for
dynamic shapes. Warm runs:

| Request | Eager (s) | Compiled (s) |
| --- | ---: | ---: |
| generate 768 × 768 | 6.6 | 5.1 |
| generate 1024 × 1024 | 11.7 | 9.0 |
| generate 1328 × 1328 | 19.1 | 15.4 |
| edit 1024, one reference | 14.5 | 12.5 |
| edit 1344, one reference | 26.6 | 22.8 |
| edit 1024, ten references | 48.5 | 46.2 |
| first generate of a fresh studio, load included | 19.2 | 17.5 |
| generate 768 × 768 from a picture, strength 0.4, five steps | | 4.4 |
| generate 1024 × 1024 from a picture, strength 0.4, five steps | | 7.1 |
| generate 1024 × 1024 from a picture, strength 0.75, two steps | | 4.3 |

A compile with static shapes gained the same, but each size and prompt length is its own
sequence length, and it ran out of recompiles by its second size. Dynamic shapes recompiled
three times over four sizes and two prompt lengths. An empty compile cache adds about 14 s to
the first image; a warm cache, under 2 s to the first edit. A compiled image is the same scene
as the eager one, and at 1328 small objects differ as they would with a nearby seed.

The Qwen child also hands PyTorch's cached memory back after each image. Without it, the child
held 66.7 GiB after a ten-reference edit and kept it. With it, the child held 34.4 to 41.8 GiB,
and the same requests took the same time: 9.0 against 9.1 s at 1024, 11.7 against 11.8 s for a
one-reference edit, 44.0 against 43.9 s for ten. The H3 fp8 child kept 4.3 GiB more after a large
edit, so it does not release.

Prepare, every Spark model with no H3 pack on disk, through `studio --prepare`: 632 s in all,
with available memory at 26 GiB or more. Qwen 44.6 s, H3 fp8 145.1 s, H3 NVFP4 291.4 s, LTX
43.6 s, Drama 65.0 s, YuE2 14.5 s, YuE2 NVFP4 26.1 s.

Music, YuE2 transcription (`yue2_cuda`). The child keeps the transcriber after its first use.
A first transcription took 26.2 s with the child's own load; a cache miss after
it took 1.55 s, against about 21 s before, timed in the child.

Prompt enhancement, H3-Image's own enhancer, fp8, with its answer opened. Before the opening,
no generate press in four returned a caption in the child: the card ended its turn first.
After it, nine generate presses (three requests, three runs each, one in Mandarin) and two
edits all succeeded, at 159.3 to 229.7 s each. Each press starts a fresh enhancer, because
the studio releases a rewriter after every rewrite, so each pays the load again; the bf16
load alone measured 104 to 109 s. A
press dropped free memory by 55.3 GiB at most: the fp8 path loads bf16 and then quantizes.

The enhancer's load, stage by stage, timed in the child. It holds 28.3 GiB in every row.

| Load path | Read | Decode | To CUDA | To fp8 | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mapped shards, numpy decode | 3.4 s | 92.6 s | 3.0 s | 2.6 s | 112.1 s |
| Mapped shards, GPU decode | 0.1 s | 107.3 s | 2.9 s | 2.5 s | 117.6 s |
| One-pass reader, GPU decode, from disk | 14.5 s | 17.1 s | 3.0 s | 2.6 s | 42.2 s |
| One-pass reader, GPU decode, page cache | 1.1 s | 17.6 s | 3.0 s | 2.6 s | 28.6 s |

The GPU decode alone did not help, because a mapped shard reads its bytes by page faults
when the decode first touches them, at about 170 MB/s. A reader that takes each tensor's
bytes in one pass reads the 17.9 GB at about 1.2 GB/s. All 401 packed weights match the
numpy path byte for byte, read and decoded. Through the studio, with the enhancer's child
probed, a generate press then took 103.6 s against 171.4 s, and an edit 103.6 s against 176.9 s.

Prompt rewrite, Qwen cards (`qwen21_turbo_cuda`), fp8 with fp8 multiplies, the turn ended at
`<|im_end|>`, and the answer opened with its JSON key. Ten presses took
33.7 to 44.3 s each, the first with the card's load. An edit of a poster took 38.2 and 40.8 s,
against 392.1 and 264.4 s before the answer opening.

These were measured and not adopted. Each ran on the engine child directly, not through the
API:

- Qwen-Image-2.1 Turbo in fp8 with fp8 multiplies: 15.6 s against 11.3 s at 1024, because
  the transformer is compute-bound and quantizing each activation costs more than it saves.
- Drama-3 with its codec decode compiled for dynamic shapes: the decode took 5.96 against 6.29 s
  for a 30 s paragraph, under 1% of the request, and the first request spent about 90 s
  compiling.
- The Qwen rewrite cards with NVFP4 multiplies in the feed-forward layers: 16.0 tokens/s
  against 14.8 for fp8, for a 4-bit build and one more kernel package.

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
| LTX-2.5 CUDA prompt rewrite | Spark, warm child, NVFP4 enhancer with a static cache | 2.5 to 3.0 s | 7.14 GiB enhancer peak, inside the video child |
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
The 17 November campaign ran all 46 case IDs that `parity_matrix.py` writes, on both machines.
45 succeeded on each. One row is a refusal, and one is a documented limit.

| Check | Coverage and result |
| --- | --- |
| Mac and Spark comparison | 15 matched rows. Public inputs and seed match; precision and some output geometry differ. |
| 17 November parity run | 46 cases on each machine. 45 succeeded on each. Spark refused Fast mode, which `ltx25_cuda` does not offer. The Mac reached `max_tokens` on the 800-word Drama request. The Mac reports no free-memory figure. |
| macOS CPU suite | 3,601 tests passed with the 17 November changes. Statement and branch coverage reached 100%. |
| macOS CPU suite, 16 November | 3,587 tests passed after the H3 and YuE2 fixes. Statement and branch coverage reached 100%. |
| MLX product checks | Page: 181 checks passed. Batch: 12 passed. Backend switch: 19 passed. |
| H3 MLX video | Both real model tests passed. |
| Spark targeted suite | 690 tests passed. Real CUDA checks covered generation, edit, cancellation, and a backend switch. |
| Spark broad suite | 3,496 passed and 45 failed. Two Apple-only test modules could not load. |

The Spark broad-suite failures include unavailable Apple dependencies, a file-order assumption, and a macOS binary.
These results do not establish full Linux test-suite support. The matrix does not measure output quality equivalence.

Older experiments and full provenance remain available in [the previous revision](https://github.com/CJHwong/open-imagine/blob/6530af727d5d1e664593e426372d9c713f1536a5/docs/reference/measured-memory-and-time.md).
