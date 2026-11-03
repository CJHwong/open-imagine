---
tags: [models]
max_turns: 12
allowed_tools: [Skill, Read, Glob, Grep]
disallowed_tools: [Bash, WebFetch]
---

Use Open Imagine to plan a flat gouache-style poster of one orange on a blue plate, with no text,
for a 3:4 print. My server is offline; do not connect or generate. Write the JSON operation
request for one small concept, then explain how you would make the final if I choose it and want
to keep its composition. Use my current model, not a different one.

Here is the saved discovery information. The active Image backend is `atlas_image`, a local
model plugin. Its only mode is `generate`. That mode's complete `params` list is:

- `size`: choice, default `480x640`, choices `480x640` and `960x1280`.
- `steps`: number, default 6, minimum 6, maximum 6, integer true.
- `seed`: number, default 7, minimum 0, maximum 999, integer true.

It has min_references 0, max_references 0, each_reference false, region_marking false, no Looks,
no templates, no LoRAs, max_loras 0, and max_batch 1. The studio's top-level `rewrite_modes` is
empty. I haven't tested this model's visual reliability yet. Would you use Rewrite or Edit for
the final, and what limitations can you actually infer about this model from the skill's studies?
