# Limits of the current stack

These limits come from two real productions and one maker audit, not from reading the engine.

## What failed

- A 49-shot, 253-second music video. The maker's personal audit of every selected still and every export join found six cut-level faults: a closed bay becomes an open arcade, broad steps become a different stairwell and reset the actor to the bottom, a reaction lands beside the wrong shop, tunnel speed resets to slow walking, a destination sits behind the actor's face and then appears in a rear view, and the camera approaches a door then jumps backwards. It also found repeated chest portraits and one enlarged soft still.
- A 29-second, 11-shot film. Four blind board rounds did not reduce the fault count. The open faults were missing lip sync in two shots, a wrong gaze, a phone held overhead, and a door that swings shut.
- In both, the blind reviewers read frame sheets. Each frame was plausible alone, so the verdicts missed the contradiction between frames. The maker found the faults later, watching the assembled cuts.

## Why it happens

Each still is generated from words. The staging map is text. The pixels never share a source, so every shot invents its own architecture, and the video model then animates that invention.

## What works

- One clip with one action and one location.
- A short scene of two to five shots in one location, all derived from one approved set plate.
- A music video built from performance cutaways and inserts, where a jump between places is expected.
- A storyboard or animatic, because the image stack holds a still frame well.

## Rules that follow

1. One location, one plate. Generate and approve one empty set plate, then derive every frame in that location from it by image edit. Do not generate a continuing place from a fresh text prompt.
2. Continuations start from pixels. Begin a following shot from the selected take's actual out-frame, or from a crop of the same plate. A new still is a new place.
3. Keep a scene to five shots or fewer. Every extra shot adds a join that no review sheet can verify.
4. Avoid multi-minute journeys across many locations. Split them into separate scenes, or tell the story with cutaways and inserts.
5. Lip sync needs the audio route. Attach the actual audio to one close single, keep the dev transformer in the pack, and watch the result. A moving mouth is not proof. The route passed Mandarin, Cantonese and Japanese tests on 2026-11-04; see [the measured parameters](motion-control.md#the-audio-route-that-passed-2026-11-04).

## What to tell the producer

Name the limit before the work starts, and offer the alternative you can deliver: one strong clip, a short scene, or an animatic. A finished animatic is an honest deliverable. A generated feature with unverified continuity is not.
