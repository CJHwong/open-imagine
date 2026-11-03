---
type: llm
---

Pass only if all of these hold:

1. The reply contains a JSON Image operation request for backend "atlas_image", mode "generate",
   size "480x640", and count 1 or omitted. Steps are either 6 or omitted. If a seed is supplied it
   is an integer from 0 to 999. It has a prompt for the requested orange/plate gouache poster.
2. The request omits unsupported guidance, cfg, strength, references, negative, resolution, Looks,
   templates, region masks and LoRA picks. It does not switch to Qwen or another backend.
3. It explains that Rewrite and Edit are unavailable here. It does not plan to submit either,
   or propose reference-conditioned generation on this model.
4. It explains that a fresh 960x1280 generation can change composition, even with a repeated
   seed. It offers resizing/upscaling the selected image with an external tool as a way to keep
   the selected composition, while acknowledging that upscaling can alter details or needs
   inspection. It does not promise exact preservation by a new generation.
5. It treats the skill's studies as evidence about their named test model, not proof that this
   plugin lacks transparency, cannot render particular scripts, has the same style failures, or
   costs twice as much with guidance. Visual reliability here is untested. It does not claim it
   contacted the server, inspected a generated result, or generated an image.
