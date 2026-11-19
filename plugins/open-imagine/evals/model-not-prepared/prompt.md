---
tags: [models]
max_turns: 12
allowed_tools: [Skill, Read, Glob, Grep]
disallowed_tools: [Bash, WebFetch]
---

Use Open Imagine to make one photo of a red bicycle against a white wall. My server is offline
right now; do not connect or generate. Tell me what you would send, in order.

Here is the saved discovery information. The active Image backend is `qwen21_turbo_cuda`, with a
`generate` mode whose default `size` is `1024x1024`. `GET /api/v1/models` answered:

```json
{"models": [{"id": "qwen21_turbo_cuda", "workspace": "image", "name": "Qwen-Image-2.1-Turbo",
  "state": "missing", "bytes": 0, "missing": ["Weights"]}]}
```
