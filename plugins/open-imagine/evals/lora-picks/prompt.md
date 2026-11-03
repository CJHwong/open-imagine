---
tags: [loras]
max_turns: 12
allowed_tools: [Skill, Read, Glob, Grep]
disallowed_tools: [Bash, WebFetch]
---

My Open Imagine server is offline. Do not connect or generate. Prepare the JSON operation request
for one square product photo of a plain ceramic pear on a table, with a warm tint and no dimming.
Use this discovery snapshot I saved for the image backend `example_image`, mode `generate`:
`size` offers `256x256`, `steps` is fixed at 1, `guidance` defaults to 1, and seed 7 is valid.
The mode's `max_loras` is 1. Its `loras` are:

- `example_warm`, label Warm tint, strength 0.8, min_strength 0, max_strength 1, trigger "warm light".
- `example_dim`, label Dim, strength 0.5, min_strength 0, max_strength 1.

An old draft has `example_dim` at strength 0. Keep that effect off. Include the warm add-on at
its default strength, and explain whether the off pick uses up the one-add-on limit.
