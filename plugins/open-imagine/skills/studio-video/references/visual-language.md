# Visual language and continuity before generation

Read when you design a storyboard, translate it into prompts, or repair an edit. Develop the situation and staging first with [film-craft.md](film-craft.md). For travel and persistent physical effects, use [physical-continuity.md](physical-continuity.md).

## Decide what the audience needs to understand

For each beat, name the new information or emotional change and its visible evidence. A shot earns its place through an action, reaction, reveal, relationship or deliberate change of emphasis. A return to the same setup is valid when the action changes. New framing alone is not a new beat.

Record the viewer's focus at the end of one shot and the start of the next, and whose observation motivates the viewpoint. Name each cut's reason: a glance reveals its subject, a hand leads to a detail, a reaction follows new information, or a deliberate time or space change. Do not disguise repeated footage as coverage with crops, arbitrary angles or reversed motion. A straight cut and a camera move are choices. Neither should happen because independent references disagree.

## Write a small continuity breakdown

Give story-critical props stable world identities, such as `MAYA_CUP` and `SISTER_CUP`. Screen-left is a projection, not an identity. On cards and in briefs, name a side as frame left or right, or as the person's own left or right. A bare "left" or "right" gets read both ways. Record where each object appears for each camera on the staging map. Track only state that affects the story or the next cut:

- Actor: position, gaze target, action phase, supporting or holding hand, grip and mouth state.
- Props: location, orientation, ownership, count and material state (empty/full, open/closed).
- Geography: action axis, screen direction, camera side and focal area.
- Sound: on-screen speech, voiceover, pauses and sound bridges.

For an action, record input state → visible cause → output state. Inspect the states inside the take, not only at its endpoints. A useful shot brief:

```yaml
id: SH11
purpose: She prepares her sister's cup, acting on the decision to reconnect.
staging: {camera: C2, world_time: T6}
state_in:
  MAYA_CUP: tea already present; level stays unchanged
  SISTER_CUP: empty
visible_cause: kettle spout and continuous stream meet SISTER_CUP
state_out:
  MAYA_CUP: same level
  SISTER_CUP: tea after the pour
join: SH12 inherits the actual selected final frame and these levels
```

At selection, attach observed event times, evidence paths and open defects. If a precise contact or liquid action keeps failing, simplify the framing or action, or use a deterministic composite. Label the technique. Do not crop out a contradiction that still breaks the story's logic.

## Design joins before isolated frames

For continuous action, compare outgoing and incoming action phase, hand, grip, gaze, screen direction and momentum. A shared pose does not guarantee continuous velocity. Watch a short moving window on both sides of the cut at normal speed. Remove repeated anticipation and restarted gestures in the edit.

In a run of very short shots (under about one second), keep the attention target (face, hand, prop) at nearly the same screen position across each cut. The eye then lands on it at once. Record its position on the layout card and reference it in the next shot. A deliberate jump needs a reason. In a tall frame, center framing costs little, so use it as the default for fast sequences.

Use the actual selected outgoing frame as the incoming reference when you continue the same view. For a new viewpoint, keep world geography and match the action instead of screen coordinates. Respect the action axis. Deliberate discontinuity is available when the story calls for it. Do not force a model to morph between incompatible cameras to reach an end frame. Redesign the framing or trim the join.

## Separate actor identity from the shot look

Keep a versioned actor card for each recurring actor: canonical source face, clean face crops, verified angles, hair silhouette, wardrobe and distinguishing features. Separate identity from expression, pose, lens, light and grade. Generated turnarounds are candidates until checked against the canonical face. Never make every new generation the new identity standard.

Generate an expression set once from the locked master: neutral, the key emotions the story needs, and the speaking mouth shapes if any shot shows speech. Each shot references the nearest approved expression instead of inventing a face. Freeze the costume for the whole film unless the story changes it. Give each actor one strong costume or graphic feature (a color, a silhouette, an accessory) that identifies them when the face is small, turned away or drifting.

Pin the canonical actor and setting versions when you create a shot reference. For a motion continuation, also use the actual previous cut frame. Identity and temporal continuity are different problems. Use only supported reference forms. A tiled casting sheet can produce several people in image-to-video, so extract the single panel. Text traits and a shared seed do not lock a face.

Prefer a native high-resolution canonical portrait, for example 1024×1536 for 2:3, with individually inspectable views. Prioritize a clean frontal view with readable eyes, the angles the film uses, hair and wardrobe records, a scene-lit reference, version metadata and the voice link. Record features you cannot assess instead of passing them.

Test cast and look together at the needed angle, face scale, costume and light. Check recognizability, silhouette, separation from the background, and whether sleeves, straps or reflections block a gaze or contact. Establish the purpose of an expressive look before you call a difference drift.

Review identity on a face contact sheet across edited shots at comparable scale: eye spacing and lids, nose, mouth, jaw, hairline and apparent age. Allow changes from expression, perspective and light. Flag structural changes. Identify affected shots before you propose recasting or retakes.

## Decide whether a graphic belongs

Before you design an overlay, write the information it adds beyond picture and sound. If nothing important is lost without it, omit it. A person holding a phone to their ear already shows a call. A reply's exact words can add information the audience lacks. An overlay informs the audience; it does not prove that the character saw the message.

Choose one graphic grammar for the film: device insert, restrained floating text or familiar chat bubbles. Keep sender, reading order and reading time clear at delivery size, away from faces, hands and action. Captions for accessibility are separate and stay.

For repeated device inserts, keep a good physical phone-and-hand plate and composite exact screen states. Keep the editable UI, mask, source plate and content provenance. A tiny avatar can use the canonical portrait directly; passing that portrait to a broad image edit can add the actor as a whole person. Check that pixels outside the screen stay unchanged. Still composites do not prove moving tracking, reflection or finger occlusion.

## Tall frames

Apply when the aspect ratio is vertical (for example 9:16 or 2:3). Generate natively in that ratio. Never crop a horizontal composition.

- Decide the zones first. Put the key information in one band, often the upper part of the frame, as a horizontal window. Ask where the film will play, and keep the platform's interface areas clear. Published safe-area numbers disagree, so take them from the destination, not from a blog.
- Avoid true wides. Sky and floor fill the frame and the subject gets small. Establish place with a medium shot plus one landmark.
- Keep groups small: about three people in a frame, entering in at most a few waves. Fewer bodies means fewer hands and eyelines to keep consistent.
- Stack people in depth instead of side by side. A depth two-shot can show speaker and listener in one frame and remove a reverse angle that would need its own geometry.
- Keep the camera locked. A large pan in a narrow frame disorients more than in a wide one.
- A split panel can give two people one frame each without a reverse angle. It breaks the single shared space, so offer it as a choice, not a default.
- The opening shot answers who, where and what is at stake. A legible situation is a hook. A stunt is not required, and a calm film may want neither.

## Sound and duration

Classify each voice: visible speech, offscreen story sound, device playback, memory or narration. Each has different picture and mix needs. Sound bridges and J/L cuts can carry a reaction or an insert. They cannot explain incompatible physical events. Keep an ambience bed and match effects to visible contacts. Place impact sounds on their contact frame before you place the voice. Viewers notice an impact out of sync sooner than speech.

Keep the visible-speech surface small. Generated lip sync is the least reliable part of a take, and practitioners in stop-motion, limited animation and AI film all design around it. For each line, choose the delivery first: offscreen, over a reaction, from behind or in profile, through a device, or visible speech. Record `mouth_visible` on the layout card as one of three levels:

- `hidden`: no mouth on screen. Any delivery works.
- `small`: the mouth is too small to read shapes. Only the start and end of each line must match the mouth movement.
- `close`: the shapes must match the sounds. Check the lip closures on b, m and p first.

Use `close` when the producer wants it or the beat needs the face speaking, and keep those shots short. Keep sound within 1 frame early and 3 frames late of the picture at 24 fps. Viewers forgive late sound far more than early sound. If a take will not sync, slide picture against audio first. If no offset works, reframe to a lower level before regenerating.

For each visible line, lock the voice take first, then split it into phrases. Give each phrase one attitude or action and its duration in seconds. Animation timing reads quicker than real time, so favor the shorter beat. The phrase table becomes the action timing in the prompt and the slot in the animatic.

A shot-length cap is not pacing. Choose duration for noticing, understanding and responding. Low resolution can reject coarse staging but leaves face detail, lips and text unassessable. Recheck those at finishing resolution.

## Translate the checked brief into prompts

Give each shot a motion budget: one thing moves, and everything else holds. Declare the mover and the camera state on the layout card. The camera is locked unless the card names a move and its reason. Video models add gestures and camera moves on their own, and a declared budget lets the reviewer reject them. Start the action already under way, and cut in after it begins, not on its first frame.

Describe the starting arrangement once, one main action, contacts and trajectory, what changes, what stays fixed, camera behavior and sound. Use the model's prompting guide and the API's supported controls. Avoid unseen objects that invite a camera reveal. Do not rely on long prohibition lists or seeds for identity or physics.

Before submitting, resolve contradictions among storyboard, state ledger, reference pixels, prompt, end keyframes and audio. An "empty cup" prompt with a full-cup image has already failed. Prompts express staging decided earlier. They are not where staging is invented.

Keep shared look and identity guidance separate from shot camera constraints. Name the roles of a scene anchor and an actor card. If an edit adds an extra hand or phone instead of reframing the existing one, reject it and change the route or source reference.

Schedule by dependency and loaded model. Finish and inspect the image-reference phase before switching to video. Batch independent shots. Dependent continuations wait for actual results.
