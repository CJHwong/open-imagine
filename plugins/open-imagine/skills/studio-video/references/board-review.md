# Blind reviews

The agent that made a storyboard cannot grade it. It knows what each frame was meant to show, and it sees that intention instead of the pixels. Every false "ready" in earlier productions came from that self-check.

This review checks the depicted story and physical relationships. Its pass is not acceptance of the film's visual treatment. Establish a new or rejected look with the producer before expanding the board, as in [production-design.md](production-design.md#establish-the-visual-treatment). Keep that visual decision separate from the cast, frame, sound and continuity verdicts; do not convert a board pass into a claim of picture quality.

Four fresh-reviewer checks run before the producer sees a board, each at the earliest point where its defect can be caught:

1. **Cast check**, before the first storyboard frame. Record it with `review.py check <project> cast`.
2. **Frame check**, on each frame as it lands. Save its verdict beside the frame with the inspected file hash. This is supporting evidence; `review.py` does not currently enforce individual frame verdicts. Resolve a failed frame before anything builds on it.
3. **Blind board review**, on the whole board. Record it with `review.py verdict`.
4. **Sound check**, on the locked audio. Record it with `review.py check <project> sound`.

Each reviewer is a fresh subagent with a scratch directory. Pass the brief verbatim. Do not pass prompts, generation notes, earlier reviews or your own assessment. A fresh reviewer runs each new round.

## Maker inspection

The lead agent must personally inspect every new native image, including rejects, and each selected crop at delivery scale. Save the file/version, content hash, observed defects and decision. Keep the image observation separate from the prompt and intended action. Missing inspection remains unassessed; do not report that all images were checked from an agent's verdict or a contact sheet. Record native and crop quality separately when enlarging loses detail.

Maker inspection and independent review have different duties. A reviewer can pass position, counts and landmarks while a picture remains soft, repetitive or poorly lit. A spatial pass does not settle picture quality, movement, audience meaning or producer acceptance. Conversely, a maker's keep decision cannot waive an independent failure. The software checks review records and hashes; it cannot prove that anyone looked or that the picture works.

## Blind board review

Hand the board to a fresh reviewer: a subagent with no access to this conversation, the prompts or the production notes. It works in two phases.

**Phase 1, tell-back.** Give it only the frames in order, with shot ID, start and duration, the film's one-line premise, and the sound script: each line of dialogue and each key sound, with its start time, its speaker or source, and how it is heard (visible speech, offscreen, device or narration). The audience hears the sound, so the reviewer reads it. Pass the tell-back brief below verbatim. It narrates what it sees and hears happen and where it got lost.

**Phase 2, checks.** Then give it the beat list (what each shot must make the audience understand), the layout cards including each cut's claimed relationship, the staging map and the world-time timeline. Include the actual preceding retained out-frame when a new frame claims to continue it. Pass the check brief verbatim. A reviewer without that reference must leave exact matching unassessed.

Give it a scratch directory for crops and pixel comparisons. Do not pass prompts, generation notes, earlier reviews or your own assessment. Save its JSON answer inside the project and record it with `review.py verdict`. A recorded pass is required for `review.py ready`, beside the cast and sound checks. A pass may hold `revise` findings. `ready` lists them, and they go to the producer with the board. `approve` stores them in `storyboard_approval.revise`. Only the reviewer sets a severity. Never change it in the reviewer's JSON. If it fails, repair the earliest broken relationship and run a new reviewer. Do not argue the old reviewer into a pass.

Look at the cited frames before you repair a finding. In one run, reviewers read a right hand as a left hand, and read a new camera angle as a change of seats. Another reviewer reported drawn text that was the film's own title. Keep the verdict as the reviewer wrote it. Write your reading of each finding in the project log, and repair the ones the frames confirm.

The loop does not always converge. In one film, fresh reviewers failed 17, 10, 11 and 15 findings over four rounds, because each one looked deeper than the last. When the count stops falling, take the board and its open failures to the producer. If the producer accepts them, record that with `approve --waive-review`.

To compare two cuts, `scripts/blind_ab.py pack` builds frame-sheet packets with hidden sides, and `blind_ab.py verdicts` reveals which cut each reviewer chose. Frame sheets carry no sound, so they cannot judge line timing, lip sync or a sound sting. Two runs with three reviewers each, but with different packet formats, preferred opposite cuts. Treat a three-reviewer result as a hint, not a decision.

### Tell-back brief

You see a film's storyboard frames for the first time, with the sound script that plays under them. Do not guess what the maker intended. Report only what the frames show and the sound script says. A still cannot show lips moving, so take a line marked as visible speech as spoken by the person in frame.

1. In order, narrate what happens, one or two plain sentences per shot, including what is said or heard.
2. Say where you first wanted to know what happens next, if anywhere.
3. Say where you got lost: a person, place, object or event you could not follow, or a jump you could not explain.
4. Say what you think the film is about, in one sentence.

Do not suggest fixes. Keep this text; it becomes the `tell_back` field of the verdict.

### Check brief

You review a film storyboard from its pixels. The frames are the only evidence. Shot purposes say what the film needs. They do not say what the frames show.

1. Build the scene first. Before you judge any shot, write down where each person, seat, reachable object and camera is, as the frames show them. Compare each frame with the staging map and its layout card.
2. Count people, hands, phones and other key props in every frame. An extra or missing one fails that frame.
3. For each person, name which hand holds what, from anatomy (thumb side, wrist accessory, sleeve), not from any label. First decide the viewpoint. When the camera faces the person, their right hand is on frame left. In a point-of-view insert, where the camera sees what the person sees, a hand enters from the side of the body it belongs to: the right hand from lower right. Follow each held object across shots. A change of hand needs a visible cause.
4. For each contact (press, grab, pour, touch), check that the limb can reach the object from the position the wider shot established. A close-up that hides the body does not establish the reach.
5. For each reverse angle or reaction, check that position and eyeline agree with the established layout. A plausible portrait with a matching background does not place the person. Locate the cause of the reaction relative to their eyes and facing direction; a target behind them is not a forward sightline.
6. For each insert, find where its camera stands on the layout. Locate it from landmarks and lines it shares with the wider shot (a window frame, a table edge, a sleeve), not from how tilted the view looks. A long lens from the same spot only magnifies part of the wide, and a nearby surface can look steep in it. Its scale, grip and neighboring landmarks must match what the wider shot shows at that spot. Matching materials, colors or a correct sign is not a match.
7. Track the world over time. When the timeline says the world changes, the environment must change accordingly. Moving vehicles must show different landmarks. Identical backgrounds then contradict the story. A world the timeline keeps still may look identical.
8. For each change of state (on/off, full/empty, open/closed, sitting/standing), find the frame that shows the cause. To find a change, crop each story prop in every frame where it appears and compare the crops: fill level, open or closed, on or off, position. A difference over the whole frame hides a small change.
9. Compare each layout card with its frame: the declared mover, camera state and mouth visibility (`hidden`, `small` or `close`). A mouth that shows more than the card plans, or a second subject posed mid-action, fails.
10. For every adjacent pair, compare the claimed continuity with visible landmarks, closed/open paths, actor position and facing direction, and camera scale. Report an apparent continuation that changes its architecture or destination. Distinct map IDs or the word "montage" are not visible evidence of a transition. For cuts between very short shots (under about one second), also measure the attention target in the outgoing and incoming frames. Fail that attention check if it moves more than a third of frame width without intended disorientation. Skip only this measured attention check for longer shots, not the place/direction check. Stills cannot establish an actual moving camera's end position.
11. In a tall frame, check that key information sits where the layout card puts it, clear of the safe areas of the platform the project names. If the project names no platform, fail this check as a gap in the brief.
12. Check each beat's purpose against your tell-back: did the frames and the sound script carry it?
13. Mark as `unassessable` what stills cannot show: speed, motion, acting, lip sync, timing. Do not guess them.
14. Give each failed finding a severity. `block`: the defect breaks a beat's story information, a count of people or props, a hand, a reach, an eyeline, the world time, or a platform safe area. `revise`: any other defect, one the producer can judge and accept, such as a background pattern that differs between cameras.

Answer with JSON only:

```json
{
  "verdict": "pass or fail",
  "tell_back": "your phase 1 text",
  "findings": [
    {"relationship": "what must hold", "shots": ["SH01", "SH05"], "result": "pass, fail or unassessable", "severity": "block or revise, on a failed finding only", "evidence": "what the pixels show"}
  ]
}
```

Report every relationship you checked, not only the failures. The verdict is `pass` only when no finding has severity `block`, no essential relationship stays unassessable from the stills, and the tell-back carries every essential beat.

## Cast check brief

Give the reviewer each character's selected master, its reference views, the cast card text and the character's `angles_needed`: each angle the shots show the character from, with the shots. Nothing else.

You check whether a character's reference set can hold one person across a film. The images are the only evidence.

1. List the views each character has, with the angle each one shows. Fail the character if an angle in `angles_needed` has no view that shows it, or if a hand or accessory the film shows has no close-up. An angle is the camera's view of the body (front, back, a side, three-quarter). A pose such as sitting or bowing is not an angle; the frame check judges poses.
2. Compare every view with the master: face shape, hair, age, build, and each wardrobe item. A different person or a changed garment fails that view.
3. For each accessory whose side matters (a watch, a ring, a bag strap, an earpiece), name the side in every view from anatomy, not from frame position. A side that changes between views fails.
4. Check every item the cast card names. An item the card names that no view shows fails, because frames cannot copy what the references never show.
5. Mark as `unassessable` what stills cannot show.

Answer with JSON only: `{"verdict": "pass or fail", "findings": [{"relationship": "what must hold", "shots": ["SH01"], "result": "pass, fail or unassessable", "evidence": "what the pixels or numbers show"}]}`, using character IDs in `shots`. The verdict is `pass` only when no finding fails.

## Frame check brief

Give the reviewer one new frame, its layout card, the staging map with its camera legend, the timeline state for its world time and the cast cards, plus the shot's drawn layout when it has one. For claimed continuity, also supply the selected scene plate or actual preceding retained out-frame. No prompts, production notes, earlier verdicts or maker assessment.

You check one storyboard frame against its plan before anything is built on it. The frame is the only evidence.

1. From the map, say where the camera stands, how high, and what it faces. Say whether the frame agrees: horizon height, which walls and landmarks show and on which side.
2. Place every person: which side of each table or object they are on, standing or seated, and whom they face. A person on the wrong side of furniture, inside it, or facing the wrong way fails.
3. Count the people the timeline puts in view. A missing or extra person fails.
4. Check each prop the timeline places, and the hand it is in.
5. Check the card's mover and mouth visibility, and that nobody else is posed mid-action. The mover moves in the video; the frame shows its state at the start of the shot.
6. If a drawn layout is given, compare the frame with it: the camera height and angle, each person's place and size against their coloured figure, and each door, panel and piece of furniture. Check features inside this camera's declared framing; distinguish a cropped-out landmark from a missing one. Essential story evidence must remain visible. A schematic without projected scale cannot prove an exact person size or camera height.

Answer with JSON only: `{"verdict": "pass or fail", "findings": [{"relationship": "what must hold", "shots": ["SH01"], "result": "pass, fail or unassessable", "evidence": "what the pixels or numbers show"}]}`, with the frame's shot ID in `shots`. The verdict is `pass` only when no finding fails. A failed frame is retaken before the next dependent frame.

## Sound check brief

Give the reviewer the sound script with each line's written direction, the measurements from `sound_check.py --words`, each shot's purpose and the attention line of its layout card, and the project's sound sources: who is heard, from where, and whether they are seen. Nothing else.

You check the soundtrack's takes against their written direction. You cannot hear them, so judge only what the numbers and the script show, and mark acting itself `unassessable`.

1. Words: the transcription must match the script line. A dropped, added or wrong word fails.
2. Fit: every line must fit its shot.
3. Delivery against direction: compare pitch range, pauses and loudness range with the direction and with the speaker's other lines. A direction of shock, stammering or hesitation needs a pause. Mockery, boasting or anger needs a wider pitch range than the same speaker's calm lines. A take whose numbers contradict its direction fails.
4. Sources: every crowd or offscreen sound needs a source that the frames show or that the script has established. Several takes meant as different people (a laughing table) must differ in median pitch. Takes within a few hertz of each other read as one voice repeated, and fail.
5. Mark acting, timing feel and lip sync `unassessable`. The producer's listening judges them; list each line for the producer to play.

Answer with JSON only: `{"verdict": "pass or fail", "findings": [{"relationship": "what must hold", "shots": ["SH01"], "result": "pass, fail or unassessable", "evidence": "what the pixels or numbers show"}]}`, with shot IDs in `shots`. The verdict is `pass` only when no finding fails.
