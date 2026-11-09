# Model integration ownership

Status: implemented in the current working tree.
`studio/ARCHITECTURE.md` describes the resulting architecture. This document keeps
the ownership decisions and migration rationale.

## Ownership

Every real model integration maintained in this repository ships as a built-in
backend. Each model owns its capabilities, configuration rules, gateway creation,
prompt aids, calibrated memory estimate, and model-specific evidence. External
plugin packages use the public SDK and are maintained outside this repository.
Runnable examples demonstrate the SDK on the CPU without weights.

One model's integration must be understandable from its own package. It may depend
on an explicitly named shared runtime, generic contracts, and common data helpers.
The integration does not depend on another model's implementation.

Self-contained models do not require copying the same inference engine into every
model package. Qwen variants can share a Qwen runtime; LTX checkpoints can share an
LTX runtime. Their capabilities, schedules, defaults, prompts and measurements
remain owned by the model that declares them. Sharing a prompt catalog requires
an intentional family-level ownership decision, rather than treating one model's
measured wording as the universal default.

## Problems addressed by this refactor

| Current location | Responsibility that needs separating |
|---|---|
| `l4_frameworks_and_drivers/model_factories/` | Model-specific assembly mixes resolved settings with host configuration and process construction. |
| `l4_frameworks_and_drivers/model_registration/` | Contracts, registration validation, lazy package discovery, and backend construction live in the same outer layer. |
| `l4_frameworks_and_drivers/memory_estimates.py` | A second model registry repeats concrete IDs and accepts a Qwen-specific quantization argument. |
| `l4_frameworks_and_drivers/lora_table.py` | A shared parser enforces a rule about the LTX `mlx_video` section for every Video caller. |
| `gateways/prompt_aids.py` and `gateways/PROMPTS.md` | Shared mechanisms, model-tuned prompt data, user guidance, and evaluation evidence have accumulated together. |
| `gateways/video/ltx_pack/` | A custom-checkpoint adapter is named after the weights' directory layout. It is not a selectable model. |
| `model_plugins/minimax_h3/` | A repository-maintained real integration has a separate installation path despite host-owned memory estimation. |
| Stub Voice and Music gateways | Simulators import AuK and YuE2 capabilities instead of receiving the selected model's capabilities. |

## Layer boundaries

### L1: model descriptions

Keep pure metadata and value records here: model identity, workspace, capabilities,
and measurement provenance where needed. These records contain no engine loading,
configuration-file reads, factory implementation, or imports from the public SDK.
A record containing factories that return L2 gateways belongs with the L2 contract,
not in L1.

### L2: contracts used by the application

Define the model catalog and provider contracts inward. A catalog lists and finds
providers; a provider describes one model and constructs its backend using resolved
settings and injected dependencies. Keep the existing media-specific execution
ports: Image, Video, Voice, and Music have different jobs and lifecycles.

Define a process-running port for construction paths that currently instantiate
`SubprocessRunner` directly. Introduce additional ports only where a caller needs
to substitute I/O or a concrete implementation. Ordinary pure helpers do not need
an interface each.

Application contracts must not import `studio.plugins` or an SDK union containing
specific checkpoint registration types. External declarations are normalized into
the internal contracts at the plugin adapter boundary.

### L3: implementations and model ownership

Keep each supported model under its current media package, for example:

```text
l3_interface_adapters/gateways/
  image/qwen21_turbo/
    qwen21_turbo_model_provider_gateway.py
    official_qwen_turbo_backend_gateway.py
    capabilities.py
    configuration.py
    prompt_aids.py
    memory_estimate.py
    PROMPT_EVALUATION.md
  video/minimax_h3/
    minimax_h3_model_provider_gateway.py
    minimax_h3_backend_gateway.py
    capabilities.py
    configuration.py
    memory_estimate.py
    worker.py
    media.py
    runtime.py
  model_catalog/
    builtin_model_catalog_gateway.py
    installed_model_catalog_gateway.py
  in_memory/
  stub/
```

Each model uses `construction.py` for its provider declaration and factory; the
illustrative provider filenames above describe ownership, rather than literal paths. Shared runtime packages implement the inference mechanism
rather than enumerate supported models. A worker and its separate engine
environment remain appropriate when dependency isolation is needed.

Model providers own backend construction, rewriter construction, and the binding
of model configuration to memory estimation. Building a provider or reading its
description must stay cheap and must not load weights or initialize a GPU engine.

Use one explicit built-in provider list as the concrete enumeration point. Provider
metadata supplies IDs; memory estimators and rewriters are obtained from those
providers. Adding a model requires one registry entry, not separate edits to the
backend, rewriter, and memory registries. Do not replace the explicit list with
filesystem scanning or import-time self-registration.

The installed-model adapter performs SDK declaration validation and translation.
The concrete package-metadata reader can remain a thin L4 driver behind an inward
contract. The catalog and construction logic consume resolved settings and injected
services rather than import L4 `Config`, `ConfigError`, or `SubprocessRunner`.

### L4: host configuration, I/O and composition

L4 owns reading TOML, probing the host, constructing process drivers, reading
installed-distribution metadata, serving HTTP and the page, and choosing production
or stub composition. It creates catalogs and injects dependencies. Model-specific
construction and model-ID conditionals leave the composition module.

The normal server and stub server use the same provider descriptions. The stub
composition supplies the selected model's capabilities to a simulator for that
workspace. Stub gateways must not import a particular model to choose defaults.
In-memory catalogs, references, progress and settings are shared infrastructure
used by real and stub instances. The operation gateway's process-local state may
continue to delegate private result storage to the encrypted result adapter.

## Specific changes

### Memory estimates

Replace the independent estimator registry with a generic catalog-backed
`MemoryEstimateGateway`. Each provider binds its estimator to its own resolved
settings, including precision and quantization. Calibration conditions remain
explicit; an unmeasured setup still returns unavailable rather than an invented
peak. Preserve strict-by-default app settings, relaxed-mode enforcement of known
limits, and batch result-memory accounting.

### LoRA configuration

The common parser accepts a resolved settings mapping and an explicit provider-owned
`LoraTablePolicy` for supported fields and mode scoping. It does not infer support
from the workspace. A model may use another configuration reader; its runtime owns
weight formats, tensor shapes and target-module compatibility. It validates table structure and builds LoRA values without naming models
or runtime sections. The LTX provider owns the error for LoRA tables mistakenly
placed under `mlx_video`; an unrelated Video model does not inherit that check.
Capabilities remain the source of supported LoRAs and limits.

### Prompt data and evidence

Keep selection, placeholder validation, and prompt composition generic. Move
concrete prompt sentences and templates to their model or explicitly shared family.
Move model-specific evaluations beside the integration, retaining measured settings,
verdicts, failed options, and limitations. General user guidance belongs in the
how-to documentation. The central `PROMPTS.md` may become an index during the
migration. Update `AGENTS.md` and all references so evaluations are written to their
owners rather than accumulating centrally again.

Moving text must preserve the exact runtime strings and current capability offers.
Do not reinterpret one model's evidence as validation of another model.

### Checkpoints and the word pack

Use **model** for a selectable integration, **checkpoint** for weights, and
**runtime** for inference code. An LTX pack is the upstream on-disk layout of a
checkpoint. A generic custom-checkpoint adapter belongs with the LTX runtime and
is named as a checkpoint adapter, not as another model.

Named built-in models still have their own provider packages. External checkpoint
registrations are translated to a provider configured for the appropriate runtime.
Retain supported SDK aliases such as `LtxPack` and the existing `pack_dir` setting
at the compatibility boundary. Internal APIs and new documentation use checkpoint
terminology. Avoid a single universal engine class branching over unrelated models.

### Built-in H3 and demonstration-only examples

Move H3's gateway, capabilities, worker, media helpers, dependency pins, downloader
and tests into Studio's built-in integration. Its estimator is already in the host's
Video package. Replace `GatewayModelRegistration` construction with the built-in
provider path, retain optional visibility, and update setup recipes to run without
`--with ./model_plugins/minimax_h3`. Remove the separate package and its special
pytest/type-check source paths once the migration passes.

Retain H3's private memory transport, path redaction, cancellation ownership, lazy
loading, capabilities and measured limits. Separate engine dependencies can remain
in their own environment even though support ships with Studio.

Keep the SDK and its independently installed package mechanism. Preserve duplicate-ID
checks and document removal of an older separately installed H3 distribution before
using the built-in ID. Do not silently change precedence for arbitrary external
packages that collide with built-ins.

Keep runnable examples to the CPU PNG, test-video, and WAV demonstrations. Move
Qwen/LTX checkpoint declaration examples into the SDK documentation and test fixtures;
they teach the registration shape without offering additional runnable real models
from the examples package.

## Migration sequence

1. Group simulated backends and process-local state implementations into `stub/`
   and `in_memory/`, with mirrored tests and import guards. This established the infrastructure boundary before moving model ownership.
2. Define inward catalog/provider/process contracts and normalize SDK registrations
   at the adapter boundary. Move validation and construction behavior into L3;
   inject settings and services in place of imports from L4.
3. Move each built-in's construction and configuration into its model provider.
   Reduce registration to one explicit provider list and derive rewriters and memory
   estimates from it. Remove the separate L4 estimator registry and model-specific
   exceptions from the shared LoRA parser.
4. Move prompt data/evaluation evidence to their owners and clarify custom-checkpoint
   terminology. Preserve exact strings and compatibility names throughout.
5. Move H3 into the built-in provider path, then simplify examples and remove the
   separate model-plugin package layout and tooling exceptions.

Each step includes tests and documentation and should produce a usable Studio.
Commit and PR publication remain separate user-directed actions.

## Acceptance checks

- One model owns its defaults, construction, prompt aids and memory estimate.
- Generic catalogs, admission, LoRA parsing and simulators contain no concrete
  model imports or model-ID branches. The explicit provider list is the intentional
  enumeration point.
- L3 providers and registration adapters import inward contracts, not L4 configuration
  or concrete process drivers. L2 does not depend on SDK declarations.
- Model packages do not import each other's implementations; shared runtimes have
  explicit ownership. Real model packages do not depend on stub implementations.
- Stub and production descriptions agree for every supported model; selecting and
  describing models load no weights.
- Existing model IDs, SDK compatibility aliases, configuration keys, capability
  offers, exact prompt strings, and memory decisions retain their behavior.
- Private operation contents keep their existing ownership and storage guarantees.
- Run the full CPU suite with the existing 100% statement/branch coverage gate,
  import-linter and prek, and relevant browser suites. Prove new import guards with
  negative checks in an isolated copy.
- For runtime moves or backend behavior changes, run the repository's applicable
  live checks through Studio using the shared-GPU protocol. CPU/stub checks alone
  are not evidence that a moved inference worker still runs correctly.
