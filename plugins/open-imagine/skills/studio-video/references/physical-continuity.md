# Scene-wide physical continuity

Read when a story depends on travel, contact, changing material state, complex motion or a persistent environment. Apply the same causal discipline to actor, props and visible world. Preserving an actor's exact out-frame can faithfully preserve a wrong background.

## One world timeline across coverage

Define the physical phases before shot prompts, and save them as `staging.timeline` beside the staging map. Each shot inherits the current phase instead of restarting from an attractive reference. Track only consequential state:

- Position, route segment, elapsed time, motion phase and camera orientation.
- Doors, entrances, obstacles and available actions.
- Actor pose, gaze, grip, support and contact. Prop identity, count and material state.
- Direction, depth and trajectory of exterior or moving objects, and device playback moment.
- Light, reflections and sound changes caused by that state.

For each shot, write on its layout card what the background shows at that world time: which landmark, where it sits in the frame, and which way and how fast it moves. Two shots at different world times must not share a background description unless the world is truly still. Hand-drawn productions fix positions, motion and camera on one layout sheet per shot before anything is drawn. Writing the background's movement on the same card extends that practice to a moving world.

Every change needs a visible cause or a motivated time omission. A new keyframe is not a cause. A cup outside the pour cannot fill. A bag cannot move before its strap takes tension. Keep object permanence, gravity, occlusion order and contact through the whole action, not only at endpoints.

For vehicle coverage, a compact timeline might be dwell → doors close → departure → cruise → arrival. A later return stays in transit after departure unless arrival is shown. Record world time separately from editorial time when coverage reuses overlapping moments. An omission may skip landmarks. It cannot silently reset motion.

## Vehicle motion is relative

A stable seat, window frame and seated passenger are correct during smooth travel. Stationary landmarks outside must move relative to the window with readable displacement. Whole-image shake, boiling texture or blank stripes do not show travel. When departure matters, choose a landmark that visibly crosses or leaves the window.

For lateral travel, near features cross faster than far ones. A reverse-facing camera can reverse screen direction legitimately. Acceleration and braking agree with the journey phase. Smooth travel needs no body sway. A strong jolt needs matching responses from body and loose objects. Light and reflections need plausible sources and timing. A rumble bed or one good departure insert cannot repair stationary exteriors elsewhere.

## Choose the cheapest controllable technique

Direct generation fits only when its motion passes review. A window composite can separate actor identity from exterior motion, but glass, occlusion, blur, reflections, light and window edges must hold in playback. A small 2.5D or 3D environment gives repeatable landmarks, parallax and trajectories. Build only enough to answer the hard motion question. Keep exact contacts or lettering in deterministic rendering or compositing. Layout to Render suits repeatable staging, camera projection and motion. Verify the current local integration and compare results against the driving layout.

After approval, prove the hardest actor-environment relationship and its return after an insert before batching. A failure changes the plan or the method, not the prompt wording around an unchanged contradiction. Keep actual inputs, plate versions and playback times in take provenance.

## Still-board checks

The blind reviewer in [board-review.md](board-review.md) runs these checks. Fix them before you send the board:

- Critical contacts: identify the pictured hand from anatomy, occupied hands, wrist accessories, grip, reach and occlusion, and compare wide and insert. A prompt label such as "left hand" is not evidence.
- Reverse views come from the one staging map. A matching background style does not place a character or an eyeline.
- Distinctive landmarks change with world time across every return to a wide.
- Composited device inserts must match the grip, height and perspective of their wide shot, not only each other.

Replacing malformed candidates, high-resolution cards and software validation do not prove scene-wide coherence.

## Observe motion and decide

At review size and normal speed:

1. Check that the intended physical phase is visible without explanatory text. For departure, track exterior displacement against the window.
2. Watch every relevant return in sequence: no unexplained reversal, speed reset, parked-world return or early door change.
3. Watch contact, support, fluid and material changes through their critical moments.
4. Check integration through the take: matte slips, geometry passing through, mismatched reflections, blur and brightness jumps.
5. Watch the actual cut. A plausible ride can still fail to express the story event.

Record pass for demo, revise, reject or unassessed, with take, time range, observation and next change. Contact sheets cannot pass motion. If you did not watch it, mark motion unassessed.
