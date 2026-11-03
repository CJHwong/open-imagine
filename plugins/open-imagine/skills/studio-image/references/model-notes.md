# Model-specific observations

Read only the section matching the selected backend. These are measured observations, not
requirements for every Image model. An unlisted model is untested here; use its live capabilities,
its official prompting guidance and inspection of its own outputs. Creative vocabulary elsewhere
in this skill can still be useful, but success and failure verdicts do not transfer automatically.

## Qwen-Image-2.1 and Qwen-Image-2.1-Turbo

### Settings and prompting

On these backends, Generate exposes `size` and `guidance`, while Edit exposes `resolution` and
`cfg`. The recorded Turbo checkpoint fixes Generate at 8 steps. Use live defaults and choices:
these values describe the tested checkpoints, not every distilled or full model.

A negative prompt on these Qwen paths has no effect unless guidance/CFG is above 1. Above 1,
true CFG adds another model evaluation per step, roughly doubling generation time. Do not infer
this behavior from a similarly named parameter on another backend.

The official Qwen PE-T2I prompt enhancer uses medium/subject/background first, followed by
positional details, quoted text, lighting and composition. This informed the general prompt
checklist; it is not a required format for other models. The Findings tables in
[prompt craft](prompt-craft.md), [use cases](use-cases.md), [style library](style-library.md) and
other references record Qwen trials. Their recommendations apply to those trials.

### Observed limitations in Turbo trials

- No transparent background. Generate on pure white and cut it out afterwards.
- No guaranteed seamless repeat. Keep motifs inside the frame, then tile 2 x 2 and check.
- No usable animation frames. A sprite sheet is concept art.
- Edit cannot zoom out or extend the canvas.
- Rare or technical Chinese, Japanese or Korean characters come out malformed at any size.
- Technical diagrams look right but are not accurate. Do not use them as reference material.
- Chart bars are not proportional to their values. Draw a data chart with code.
- Grid counts drift. A sheet of 8 icons can come back with 9, and tiles do not connect.
- Quoted names can lose their letter order ("Sheryl" came back "Sherly"). Check names letter by
  letter.
- Small Japanese, Korean or Arabic lines come out with wrong characters, even when the headline
  above them is exact. Set small non-Latin copy in a layout tool.

### Concept to final

On Qwen-Image-2.1-Turbo, Generate with the concept as a reference and `strength: 0.5` kept the
composition and added detail in one trial at 1536×1024 (33 s versus 60 s without a reference).
At 0.7 the result was soft; at 0.3 the subject moved. These are trial results, not a portable
strength recommendation. Edit at the largest offered resolution kept the composition but took
longer. The recorded Qwen Edit policy takes the frame from the last reference for `match`;
check another backend's documented policy rather than reordering references on that assumption.

### Full versus Turbo

Six finished Turbo prompts, made again on full Qwen-Image-2.1 at its own 40 steps, took about five times as long. Two came back richer
(finer stained glass, more dragons), three about the same, and one worse (the jellyfish turned into
flat saucers). This comparison does not establish the relative quality or speed of other models.
