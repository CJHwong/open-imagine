---
type: llm
---

Pass only if all of these hold:

1. The reply says the model `qwen21_turbo_cuda` is not downloaded, so an image run would be
   refused (a `409`) until it is prepared.
2. It names the prepare request: `POST /api/v1/operations` with `kind` "prepare" and the backend
   `qwen21_turbo_cuda` (a `workspace` of "image" is optional), followed by polling that operation.
3. It asks the user before it starts that download, or states that it waits for the user's
   approval, because the download is large. It does not start the download on its own.
4. It places the image request after the prepare succeeds, for backend `qwen21_turbo_cuda`, and
   does not switch to another model to avoid the download.
5. It does not claim it contacted the server or generated an image.
