# Running the studio on two machines

Status: two engines, one tree. macOS runs the MLX engine. The DGX Spark runs a CUDA
engine in a child process. The provider names its engine and layer 4 compares that
with the host, so neither machine sees a branch inside an adapter.

## What decides today

Each `ModelProvider` carries `engine`: `"mlx"`, `"cuda"`, or `""` for a plugin that
owns its runtime. `engines.py` answers what the host has. `mlx_available()` imports
`mlx.core` and asks for a GPU device. `cuda_available()` runs `nvidia-smi -L`, because
the server does not import torch: a CUDA engine lives in its own environment, and the
driver is the whole of what this process can check.

Layer 4 offers only the backends whose engine the host has, so the page lists what will
run here. A studio left with no Image backend is refused by name, and the stub keeps
every backend, so the page stays workable on a machine that cannot run a model at all.
The refusal happens before the port is bound, so such a host never occupies it.

**There is one startup gate now, not two.** Instruction editing used to run on a
diffusers pipeline in a child process, and a non-Apple host was blocked from it
separately by that script's MPS device check. mflux 0.21.0 ported the Qwen3-VL
vision tower, so editing runs on the same MLX engine as generation and the child
is gone. Both models behind qwen21 and the one behind flux2 are now mflux models.

## The DGX Spark, measured 2026-11-13

| Fact | Value | Source |
|---|---|---|
| GPU | GB10, capability sm_121, 48 SMs, driver 580.178.04 | `torch.cuda.get_device_properties` |
| Memory | 121.7 GiB usable, unified with the CPU | same |
| Peak bf16 GEMM | 83 to 90 TFLOPS at 2048², 4096² and 8192² | `a @ b`, warmed |
| Achievable bandwidth | 133 GB/s on a 1 GiB copy-add, against 273 GB/s nominal | MLX copy-add before the pivot |
| torch | 2.14.1+cu130 aarch64 wheel from PyTorch's index | `torch.__version__` |
| MSLK | 1.4.0+cu130 has aarch64 wheels; installs with `--index-strategy unsafe-best-match` | PyTorch wheel index |
| NVFP4 W4A4 | 2.9x bf16 at 512 tokens, 1.4x at 4096; weights 72% smaller | torchao prototype config, MSLK installed |
| NVFP4 weight-only | 0.5 to 0.97x of bf16, and stores the same bytes | same run |
| Studio run, warm | 4.0s at 512x512, 8 steps; 12.0s at 1024x1024 | studio API, NVFP4 W4A4 |
| Studio run, cold | 20.1s including the load | same |
| Weights to the device | 128 MB/s from safetensors' mmap, 14 GiB/s from ordinary memory | 16 GiB shard, 135s against 1.3s |

The weight-only number is the trap. It stores four bits and computes in bf16, so it is
slower than doing nothing. Only W4A4 with MSLK puts the matmul on the FP4 tensor cores.

MSLK 1.4.0 declares torch 2.15 and ran correctly on 2.14.1 here. Pin the pair the child
actually tested, and re-test when either moves.

## Why a Mac cannot test this

The CUDA branch needs an NVIDIA driver. Any Apple machine exercises the macOS path,
which is the path that already works.

A second Mac is still worth running: it catches hardcoded assumptions from the
development machine and gives a second chip. It is not portability proof.

## The decisions a CUDA engine forces

| Decision | Today | Why it changes |
|---|---|---|
| The engine | MLX only on the Mac; a diffusers child on the Spark | The engine is named on the provider, so each machine builds only what it can run |
| The memory guard | The two qwen21 models are freed against each other, sized for a 64 GB machine | That is a VRAM fact, not a platform fact. `mx.device_info()` reports `max_recommended_working_set_size`; CUDA has `torch.cuda.mem_get_info()`, and on unified memory `/proc/meminfo` `MemAvailable` is the honest figure |
| The quantization | mflux quantizes the transformer and the VAE | A CUDA engine quantizes with torchao, and the badge has to follow that engine. `nvfp4` is a badge this page has never shown |
| The weight layout | mflux reads its own layout and downloads `Qwen/Qwen-Image-2.1` itself | diffusers reads the same Hub repo through `QwenImage21Pipeline` |

## Numbers already measured, all on Apple Silicon

| Fact | Value | Source |
|---|---|---|
| mflux generate peak | 30.68 GB | `generator.py` `build_model` |
| Peak without the memory saver | 45.01 GB | same |
| Text encoder, resident | 17.5 GB | mflux qwen21 README |
| Weights on disk | about 33 GB bf16 | README |
| Model rebuild after a release | 3.8s | `qwen21_backend_gateway.py` |
| Generate, seconds per step at 1.05 MP | 5.76 | `capabilities.py` |

The edit constants in `capabilities.py` were fitted against the removed diffusers
path and were re-measured against the in-process engine when it landed. Read the
comment beside them for the numbers and the machine.

## Upstream, checked 2026-10-05

| Pull request | State | What it does |
|---|---|---|
| mflux #736 | merged 2026-09-21 | txt2img, img2img, quantization. This was the pin. |
| mflux #741 | merged 2026-09-27 | Reference editing, RGBA output and prefix caching. |
| mflux #749 | merged 2026-10-01 | Instruction edit with prefix KV cache. It removed the diffusers child on macOS, which is what this repo then did. |
| mflux #764 | merged 2026-10-01 | The `viggle_turbo` scheduler. |

The pin is the `v.0.21.0` release. Two things about that release are worth knowing
before a port is built on it:

- The edit variant's `generate_image` takes no `scheduler` argument, so the viggle
  schedule reaches it through `gateways/image/viggle_turbo_schedule.py`. That module is a patch
  with a test that fails the day upstream adds the argument.
- The edit call takes `image_paths`, not images, so the references go to disk for
  the length of a run. `edit.py` records why.

## What the Spark runs today

`qwen21_cuda` generates through `QwenImage21Pipeline` at NVFP4 W4A4, through the studio API.
A cold run takes 20.1s at 512 and a warm one 4.0s; at 1024 a warm run takes 12.0s.
At these sizes NVFP4 costs nothing and wins nothing in time: the linear layers are not
the bottleneck, and the text encoder and VAE stay in bf16. It does cut the transformer's
weights by 72%, which is what leaves room for larger checkpoints later.

## Next steps, in order

1. **Add Edit.** The checkpoint edits, but only Generate is wired. `QwenImage21Pipeline`
   takes `image`; the edit path needs the same measurement the generate path has.
2. **Fit the Spark's step constants** and give the mode an estimate. Until then the
   page shows no time for this backend, which is honest, not a placeholder.
3. **Keep the version pair tested.** MSLK 1.4.0 declares torch 2.15 and ran on 2.14.1.
   Re-test when either moves, and never quote a time from a mixed pair.
4. **Compare a Mac result against a Spark result** on the same model, seed, and size.
   The community figure of 54 s for Qwen-Image-2.1 at 1024 and 40 steps, bf16, is a
   sanity check only.
