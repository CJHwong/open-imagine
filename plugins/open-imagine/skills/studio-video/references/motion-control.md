# Reference design and motion onset

Read when a shot drifts from its intended staging, a fixed camera needs precise action, or generated clips hesitate before moving. Extra images constrain visible states. They do not set velocity or the path between states. Treat a hesitant start as a defect to diagnose.

## Choose references by function

| Need | Useful input | Check before use |
|---|---|---|
| Identity and wardrobe | High-resolution actor master and verified angle library | These are identity references, not automatically frames on the timeline |
| Opening composition | A single-person, shot-aligned first frame | Correct lens/projection, grip, prop state and current world phase |
| Fixed-camera action with a clear destination | First and last frames from the same setup | No change of camera, seat/window geometry, lighting or identity unless intentional |
| One critical intermediate contact | Sparse timed mid-action guide, only if supported | Reach → contact → release must be plausible and correctly timed |
| Exact velocity/trajectory or coordinated motion | Compatible driving-video, pose/depth or sparse-motion-track workflow | Verify adapter/model/surface support; stills alone cannot determine velocity |
| Stable interior plus independently moving exterior | Controlled window plate/composite | Glass/occlusion/light integration and journey time must agree |

Start with the fewest references that resolve the actual uncertainty. For a locked shot, two coherent endpoints are often a useful experiment; add an intermediate guide only for a specific unconstrained event. Do not generate a mandatory three-frame pack for every shot. Additional conflicting anchors can cause morphing, stalls, speed ramps or contact errors; these are failure risks to inspect, not guaranteed effects.

Derive action anchors from a common scene/camera master rather than unrelated attractive images. Record each guide's role, intended frame/time, strength, exact asset/version and geometry. Compare stationary landmarks after alignment; reject camera/lens/prop-size drift before video. Distinguish a locked camera from a frozen world: in a vehicle, camera and seat may stay fixed while exterior landmarks keep travelling. Identical exterior positions at both anchors can contradict ongoing travel. Do not use the same entire image at both ends of an action simply to enforce identity.

Separate the storyboard's representative key moment from the video's opening reference. A storyboard showing fingertip contact or the revealed face may depict the action endpoint. Supply an appropriate incoming-action frame for the opening and keep the key moment as a distinct destination guide when supported. Inspect both for consistent camera projection, hand ownership, support and world phase before submission.

A first-frame-only API does not gain multi-keyframe capability by putting a contact sheet or collage into one input. A multi-angle actor card is not a temporal sequence. A batch of separate images does not imply reference-set conditioning. Check the actual backend rather than translate controls from a different interface by name.

## What is documented, and what remains local

The official [LTX image-to-video guide](https://docs.ltx.io/open-source-model/usage-guides/image-to-video/) distinguishes source-image animation from a first/last-frame template. It recommends action/camera/audio-focused prompts and explains that its endpoints guide the generated transition. This is not evidence of exact motion preservation or support in every local API.

The official [workflow compatibility reference](https://docs.ltx.io/open-source-model/reference/workflow-asset-compatibility) separates first/last-frame, sparse Motion Control tracks, Motion Transfer and video/depth/pose conditioning. These require their own compatible workflow and assets; ComfyUI controls cannot be assumed to exist in native Python or the Studio API. The [prompt guide](https://ltx.io/blog/ltx-2-5-prompt-guide) supports concrete chronological action and explicit camera behaviour. These sources do not document a universal startup-stall cause or guarantee that any wording cures it.

Earlier Studio schemas described `VideoRequest.references[]` entries with `name`, base64 `image`, `frame_index` and `strength`. Verify current intermediate-frame handling, allowed indices and strength behavior on the loaded backend. Rediscover `/api/docs`, the backend and relevant implementation when available. Never submit a made-up `motion_strength` or change sampler/conditioning settings blindly. Preserve the actual enhanced prompt where available; Studio may rewrite “locked camera” or action timing despite the submitted prompt.

## Diagnose the apparent startup stutter

Compare the original downloaded clip, the assembled export and browser playback before choosing a remedy:

- If the raw file has motion but browser playback pauses, examine buffering, decode load and media encoding. Do not regenerate the performance to fix a player problem.
- If source motion is smooth but the edit pauses, inspect held-frame pads, repeated endpoints, timestamp/frame-rate conversion and how clips were concatenated.
- If the raw clip itself holds then moves, record the actual onset and whether that hold is dramatic intention or unwanted settling. Inspect the moving subject and exterior separately; a fixed interior is not proof of a freeze.
- Inspect the saved submitted and enhanced prompts and all endpoint pixels. A prompt that asks for a motionless actor or a stationary platform conflicts with expected travel. Fix contradictory intent before attributing the result to a model defect. Do not preserve a bad reference more strongly with additional anchors.
- Repeated exact frames, low pixel difference and frame-rate metadata are useful flags, not semantic judgments. Breathing or a deliberate pause may be subtle. Whole-frame averages can miss a frozen window or penalize an intentional still reaction; use a relevant region and watch it.

Use `scripts/motion_audit.py` for a reproducible low-motion/duplicate-frame report. It requires local `ffmpeg` and `ffprobe` and proposes candidate ranges only. For example:

```bash
python3 <skill-dir>/scripts/motion_audit.py /absolute/project/shots/SH01/v001/clip.mp4 --roi 10,20,200,180 --output /absolute/project/reports/SH01-motion.json
```

Choose actual source-pixel ROI coordinates, or omit `--roi` for a whole-frame screening pass. Its downsampled-frame equality is not proof of exact original-frame duplication. Times use average fps; inspect actual timestamps for variable-rate sources. View the critical interval at normal speed, then frame-step to localize it. Record source vs edit time and intended motion; do not call a threshold result a confirmed freeze.

## Improve the generated entry and the cut

1. **Plan incoming motion.** Mark the action already underway at the cut, its direction and expected early change. The first frame should show a plausible action phase rather than a generic neutral pose that must prepare again. A static image contains no velocity: use explicit motion or a compatible driving signal when velocity matters.
2. **Separate camera from subject.** Describe a locked camera once, then concrete ongoing action: “Her left forearm is already lifting toward the button and continues upward; the phone stays in her right hand; buildings keep passing left-to-right outside.” Avoid contradictions such as “everything stays still” during bus travel. Do not demand a twitch solely to prove life.
3. **Budget short handles.** As a starting experiment, allow roughly 0.3–0.7 seconds before/after the intended excerpt, adjusted to action, backend grid and measured cost. These are proposed editorial allowances, not validated LTX settings. A five-second edit can come from a modestly longer source; the user's six-second limit applies to edited shots unless they specify otherwise. Do not default to ten-second generations for every short cut.
4. **Choose the excerpt after viewing.** Trim unwanted settling only if sufficient continuous action remains. Preserve the required reach/contact/response, planned story time and cut momentum. Record source in/out frame, fps and resulting timeline duration. If the usable span is too short, revise/regenerate; do not hide missing action with repeated frames, aggressive speed changes or interpolation. A take can be right up to a point and then grow a flaw, such as a shape that swells in the background. If the line fits before that point, cut the slot there. Give the time to a neighbouring shot whose clip has spare frames, so the total stays the same.
5. **Keep audio aligned.** For on-camera dialogue, place the selected audio within the planned handles before generation, and trim picture/audio together. Verify words and lips after cutting. Non-dialogue room/vehicle ambience can bridge picture cuts. Do not trim away the start of a spoken line or separate a bell from contact. Do not quote the spoken words in a video prompt. In a twenty-shot local test, three of six clips whose prompt quoted a Mandarin line drew that line into the picture as caption text, often garbled, and one added extra characters on the wall. The three clean ones were close singles of the speaker. Describe the delivery ("he stammers a short question") and let the soundtrack and the edit's subtitles carry the words. Check each clip for drawn text before the edit. Removing the quote was not enough. In the same test, the drawn captions came only with the voice track: 5 of 9 renders given a voice track drew a caption, and none of 17 silent renders did. The prompt line "No on-screen text, captions or subtitles" did not stop it (2 of 3 retakes still drew one). A silent render of the same shots drew none, but it pushed the camera in and lost the lip movement. `edit_check.py --text` finds these captions; retake what it fails. A later eleven-shot run confirmed it: 5 of 14 voiced renders drew no caption. All five were close singles of one man, who came back clean 5 of 6 times. A close single of a woman and a wide shot with a small speaker drew text on all 4 seeds each. One run cannot separate the voice, the speaker and the framing. Within the agreed take budget, test voiced alternatives. Render a silent fallback only when visible speech is optional or the producer accepts an offscreen delivery; it does not preserve lip sync. OCR also reads a phone's camera ring as "◎"; look at the frame, then accept that reading.

Name each person by place when more than one is in frame. A prompt that opens with "He", or names a man only by his clothes, moved the nearest or largest figure instead: the foreground man turned round, and the wrong man bowed. "At frame left, the grey-haired man bows. At frame right, the man in the dark jacket stands still" fixed both on the next seed.

Write the video prompt in what the camera sees. Character IDs and names from the shot cards mean nothing to the video model. Replace each one with a visible description, such as "the young man in the grey jacket". When nobody should move, write "Nobody in the frame moves."

Sweep seeds one at a time. Render one seed, run the drawn-text check on it, and stop at the first clean take. A fixed batch spends GPU time on takes you will not use. Name which hand holds each prop, or the model lifts the other hand and fuses the props. Do not write "toward the camera" for a gesture; the actor walked into the lens. A requested end state, held for the last half second, made no measurable difference to how still the last half second was.
6. **Continue from the actual selected cut.** Use the last retained frame, not a discarded generated tail, as the continuity reference. A single frame preserves pose but not velocity; inspect incoming and outgoing motion around the real cut, or use a supported motion reference. Avoid displaying the same endpoint twice.
7. **Escalate selectively.** After storyboard approval, compare a simple first-frame baseline with a coherent endpoint pair on one difficult shot, keeping model/settings comparable. If the problem concerns motion timing rather than final pose, consider supported motion control/compositing. Batch the remaining independent jobs only after the small proof succeeds.

Record planned reference strategy, motion entry and handle budget in `production_plan`. Record actual guides and editorial ranges on immutable take versions. The review page exposes these under “References & motion”; preserve one shared page layout across projects.

## Review the moving joins

Inspect the real retained ending of one shot and beginning of the next in the assembled edit. Start with roughly the last and first second, extending the interval to include the action. Check architecture and open paths, actor position and facing, movement direction and speed, camera position and framing, and what the viewer follows. Review every cut, including long shots. A push toward a door followed by a wider restart from nearly the same angle can jump backwards even when both source clips look plausible alone.

Use decoded frames to locate defects, then moving playback to assess continuity and rhythm. A few frames around a cut cannot establish smooth motion. When playback or listening is unavailable, name the exact sampled interval and leave those judgments unassessed. Neither clean OCR nor a non-frozen clip proves a coherent cut. Keep a cut log with the two sources, retained bounds, observed defect and repair decision.

## Prove visible singing before expansion

When the requested result includes visible lip sync, a silent take, generic mouth movement or adding the song after generation does not satisfy it. Discover a route that actually accepts the selected audio and references. API parsing or published support establishes capability, not convincing singing. Keep an untested local adapter or model path labelled unproven until a real run succeeds.

### The audio route that passed (2026-11-04)

Real runs passed the producer's eye. LTX-2.5 Generate took an `audio` track on a close single at 640×960, 121 frames, seed 7. The first clip used a five-second Mandarin song excerpt. The saved clip carried the supplied audio unchanged (envelope correlation 0.999 against the source), and the mouth articulated at the sung syllables. Three more clips used short Drama-3 lines in Mandarin, Cantonese and Japanese; the mouths differed by language, and the producer judged the set good. Each run took about 19 minutes.

The route needs `transformer-dev.safetensors` in the LTX-2.5 pack. The audio pipeline uses CFG guidance, and without the dev transformer it fails with `Dev transformer not found`. A pack with only the distilled transformer can still generate silent and text-only clips.

Use this route when the result needs visible singing or speech:

- one close single of the speaker, with the mouth large enough to read;
- the exact audio excerpt attached, trimmed to the clip length;
- the seed recorded with the take;
- the clip watched before anyone calls it synced.

Not yet measured on this route: takes longer than five seconds, other framings, joins between two spoken or sung shots, and whether Cantonese and Japanese pronunciation is correct. The ear decides the language; the eye decides the sync.

Pin the selected recording and each guide's hash, original sample interval, leading handle, picture in-frame and fps. Place the real audio within the handles before generation; keep the selected picture aligned to that same source interval. Record the audio input in the reviewed submission specification and immutable take inputs, alongside the image. Run the actual video gate immediately before every pilot or retake submission. Preserve the original recording when that is the chosen soundtrack.

Test one representative phrase before expanding: a single singer with a clear, adequately sized mouth and simple framing. Compare the actual output to the original phrase at normal speed with sound, then inspect articulations, closures, sustained vowels and pauses. Check identity, drawn captions and both edited joins. Record the observed sync quality and interval. Audio conditioning alone is not a pass, and still sheets or waveform equality cannot judge articulation. If audiovisual assessment is unavailable, lip sync stays unassessed and expansion waits.

The historical silent fallback described above applies only when visible speech is optional or the producer explicitly accepts an offscreen delivery. It cannot replace requested visible singing. Fix the supported route, framing or timing within the take budget rather than silently dropping the requirement.
