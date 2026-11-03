---
type: llm
---

The reply includes a JSON operation request with kind "image", backend "example_image", mode
"generate", size "256x256", and a product-photo prompt for a ceramic pear. The `loras` list
contains exactly one pick with id "example_warm", with either strength 0.8 or no strength field
(which uses its default). It omits the off `example_dim` pick. The explanation says strength 0
means off and does not count toward max_loras. Fail if it substitutes Looks or prompt words for
the actual LoRA field, invents another LoRA id, counts the off pick against the limit, or claims
it contacted the offline server or generated an image.
