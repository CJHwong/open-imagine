# Prompt aids and evaluation evidence

[Use templates and Looks](../../../docs/how-to/use-prompt-aids.md) explains the controls
and model-specific prompting guidance.

Prompt wording belongs to its model or shared runtime family. This index links the
measurements; a shared catalog does not imply that every model passed its tests.

- [Qwen-Image-2.1: prompting, Looks, templates and marked regions](image/qwen21/PROMPT_EVALUATION.md)
- [Official Qwen Turbo](image/qwen21_turbo/PROMPT_EVALUATION.md)
- [Viggle Turbo](image/viggle_turbo/PROMPT_EVALUATION.md)
- [FLUX.2](image/flux2/PROMPT_EVALUATION.md)
- [MiniMax H3-Image](image/minimax_h3_image/PROMPT_EVALUATION.md)
- [LTX-2.5: shot templates, Looks, effects and sound](video/ltx25/PROMPT_EVALUATION.md)

New model evaluations belong beside their integration in `PROMPT_EVALUATION.md`.
Generic selection helpers in `prompt_aids.py` contain no model wording.

Template translations live beside their family prompt data. English and Traditional Chinese
are offered, with English fallback. On 2026-11-09, the real Studio API on the M5 Pro ran a
Chinese Product shot template through official Turbo at 512 × 512, seed 7, then the Chinese
color-change template on that result. Visual inspection confirmed the blue teapot changed
to yellow while the red cup and scene remained. AuK base also completed a four-second
Chinese Voice profile template. These are smoke checks, not an evaluation of every translated
option. LTX and other unavailable model weights were not tested with the translated wording.
