# Shot design, 3D layout and finishing

A lightweight adaptation of previs and editorial practice for API-generated films.

## Design in reviewable stages

Use only the stages a shot needs. Not every shot goes through 3D.

| Stage | Artifact | Question to resolve |
|---|---|---|
| Story and editorial | Script, shot purposes, timed storyboard, scratch dialogue, animatic | Does the story read, and does the cut work? |
| Layout and blocking, when needed | Simple scene, camera, object and character motion, viewport clip | Are geography, timing, contact and camera movement right? |
| Visual treatment | One complete scene image with its intended composition and light | Does the producer accept how the film will look? |
| Look and performance draft | Art-directed reference frames, low-resolution takes | Do appearance and performance survive motion? |
| Selected edit | Assembled takes with dialogue and temp sound | Do the shots work together with the intended turn? |
| Finish | Higher-resolution derivative, composite, captions, sound, deliverable | Does the shot survive finishing and meet delivery? |

Video approval remains enforced by `review.py gate` (see SKILL.md). Visual treatment is a producer review point before expanding a new or rejected look. It does not approve a storyboard or permit video generation. An approved storyboard does not approve a later take. A selected low-resolution take does not approve its upscale. Record editorial frame ranges and handles separately from the full generated clip.

Choose the cheapest representation that resolves the beat's uncertainty, and label what it supports. A concept image proposes appearance. Inspected staging supports geometry and sightlines. An approved storyboard records the producer's selected design. Actual motion is evidence only for what was observed. Attractive concepts must not silently become buildable layouts.

## Establish the visual treatment

Use the Studio Image handoff in [SKILL.md](../SKILL.md#design-before-rendering) before writing the image prompt. Save a compact look card: the audience feeling, one representative scene, camera and subject placement, foreground/background depth, light sources and readable shadows, palette, materials, and what the test must settle. Apply the relevant image guide's concrete directions rather than adding quality words or a director's name alone.

Make a complete scene concept when composition and lighting are unsettled. A neutral casting portrait remains an identity source; do not freeze its camera-facing pose, even illumination or empty background into every scene. If exact identity is deferred while testing the look, say so, preserve the canonical master, and do not treat a generated candidate face as the new actor. Match and recheck cast before it becomes a storyboard frame.

Inspect whether the image reads as the intended moment, light and shadow explain the form, depth and framing direct attention, and skin, cloth, wood or glass have plausible separate surfaces. These are picture-quality observations, not a numerical pass from a continuity check. Show the actual candidates and their defects within the agreed budget. Record the producer's selection in their words before deriving the rest of the board. If the treatment is rejected, diagnose that image before generating more coverage.

Keep the look and its geometry connected. A foreground door must occupy a real foreground position on the map. A small frontal glance cannot establish a sightline to a door behind the person. State when the person is listening without looking at the source. CPU diagrams can check these relationships; label them as diagrams, never photographic evidence.

Before making a detail from a wider image or decoded video frame, inspect how many native pixels remain in the crop. View the actual enlarged result at delivery scale. Correct geometry does not make a soft face or indistinct object usable. If the detail does not survive, choose wider framing or make a new detail from the same established scene references and recheck its geometry. Resizing and a higher-resolution export add no source detail.

## Choose the shot route

Apply [film-craft.md](film-craft.md) before choosing coverage, and [physical-continuity.md](physical-continuity.md) for moving environments or hard contacts. Inspect the current API, input alignment and controls before you commit a route. Choose by the physical relationship to preserve, setup cost and expected iteration cost.

- **Direct image-to-video:** restrained facial performance, atmospheric inserts, small movements, shots where the exact path does not matter. Pin cast and look references and supplied dialogue.
- **3D layout to render:** camera arcs, parallax, occlusion, repeatable room geography and coordinated movement where a defined path is cheaper than prompt iteration.
- **Deterministic render or composite:** contacts, text, geometry or motion that must stay exact and does not survive generation. A final may combine a generated plate with retained 3D elements.

Keep one scene coordinate system and scale for a reusable environment. Each layout shot pins scene revision, camera and lens, aspect ratio, fps, frame range and action timing. A box room, simple props and proxy bodies often suffice. A proxy body guides blocking. It does not set the actor's face or performance.

For [Layout to Render](https://docs.ltx.io/open-source-model/vfx-post-production/layout-to-render) ([model card](https://huggingface.co/Lightricks/LTX-2.5-22b-IC-LoRA-Layout-To-Render)), bind:

1. The driving viewport clip with the chosen camera and motion.
2. Its exact first frame, restyled by an image model while keeping projection and object positions.
3. The cast and setting versions that the restyled frame derives from.
4. A short prompt for the finished image, with optional aligned mid or end look frames.

Keep the raw layout frame separate from the art-directed image. Never substitute an unrelated attractive portrait for the aligned look frame. Keep soundtrack assets separate: the official surfaces do not pass audio through. Check camera drift, silhouettes, occlusion order, contacts, identity and temporal stability against the layout.

The look frame must keep every person where the layout's first frame has them. In a local pilot, the look frame had moved one person by a body width. The render then showed that person twice: a still copy from the look frame, and the layout's walking proxy as a clay figure. Score the alignment before any video. Segment the people in the look frame and compare them with a people mask rendered from the layout (intersection over union, IoU). The score does not see who stands where, a swapped pair, or a clay surface, so the eye check decides. A cast Edit of a look frame often re-frames it (zooms in or re-centres) and lowers the score. Keep the unedited frame when that happens. A later marked edit that moves or adds a person also breaks the alignment. Send such a shot to image-to-video instead.

Keep the layout-to-edit handoff with the selected take: layout and camera revision, world-time interval, source and cut in/out frames with fps, handles, and any crop, retime, composite or color change. Compare the result against the actual driving reference, then review it in the assembled cut. See [project-format.md](project-format.md) for the fields.

## Keyframe layouts from the staging map

Words place a person reliably only when one person stands in a simple spot. With two or more people, depth, or an unusual camera, the model invents its own layout for each shot. Two shots from the same camera then disagree. An Edit of one room photograph keeps that photograph's camera and room depth. So "plates" edited from one photograph do not give new viewpoints, and people placed against them land in the wrong depth.

Give every keyframe its geometry from the staging map:

1. Build the map as a simple 3D scene at map scale: walls with their doors and panels, the main furniture, and one proxy figure per character. Give each character one flat colour and keep it for the film. A few hundred lines of script that project flat polygons suffice; a 3D program is optional.
2. Place everyone present at the shot's world time at their timeline position. The camera decides who is visible. Nobody moves between shots unless the timeline moves them.
3. Give every camera a place, height, aim point and field of view. Write down the heights and lenses that the map leaves open. Frame a close shot with a narrower lens, not a crop.
4. Draw the layout for each shot, with a labelled copy for review. Show the layouts to the producer before any generation; geometry is cheap to fix here.
5. Generate each keyframe with the cast references, one look image of the setting, and the layout last. The prompt names which person each coloured figure is and asks to keep the layout's camera, walls, furniture and figure positions.
6. Run the frame check against the layout as well as the map.

Start with flat-coloured proxies. Add detail (figure silhouettes, wall texture, shading) only where a test shows that the model ignores the layout or copies its flat look. Record which level the project uses.

In a first test, flat proxies placed every person correctly in six of six frames across three cameras, and no flat colour leaked. Two things did not hold. A low camera at table height came back at standing height. A single door beside a double door was dropped. The cause was the look image: a standing view of a different wall. Without it, the same seeds followed the layout's camera height and kept both doors, but the room's look drifted between shots. So a look image with its own perspective fights the layout. Carry the look some other way than a photograph from another camera.

What carried the look in later tests:

- **Material close-ups.** Crops that show one surface head-on, such as a panel pattern, a door or a light fitting, brought the setting's look back without moving the camera. Give a close-up only to cameras that face that surface; a door close-up can add a phantom door to a wall without one.
- **An anchor frame from the same camera.** An approved keyframe from the same camera, given with the layout, held the background almost exactly while new people entered.
- **An anchor from a different camera pulls the camera.** Do not use one.
- **Anchors carry their errors forward.** A missing door in the anchor stayed missing.

So build one anchor per camera from its layout and the close-ups. Frame-check it and repair it with a marked edit before any other shot on that camera uses it. Count the references against the API's limit; the anchor and the layout come before any close-up.

Plan the background before the cameras, because image models do not keep a detailed background the same from shot to shot. A lattice, a chandelier or a patterned wall came back different on each camera in a twenty-shot test, and every blind review flagged it.

- **Keep the set simple.** Plain walls, few repeated patterns and few light fittings leave little for the model to change.
- **Generate one base background and give it to every shot.** Make one empty plate of the set, approve it, and pass it as a reference to every keyframe. Each camera's anchor comes from that plate.
- **Blur what the camera does not need.** Where the camera language fits a shallow depth of field (a close-up or a single on a long lens), ask for a wide aperture such as f/1.8. A soft background hides small changes. Do not blur a wide shot that must show the geography.

A set element that repeats across shots needs its own reference sheet. A face-on image of a plain square grid, given as Image 1 to a marked Edit of each frame, made the lattice the same grid in most shots. A prompt alone ("one regular pattern") left every shot with its own pattern. Expect a small or distant panel to keep its old pattern.

An insert generated from text alone invents its room. Name the room in the prompt (the wall colour, the lattice, the chandelier), or the close-up cuts to a different place.

A region mark projected from a fitted camera places people only when the plate's camera already matches the map. A mark covering a whole body left coloured panels beside the person.

### Two stages: layout to photograph, then cast

An Edit treats the layout as one reference among many and invents its own room. What held the geometry in a later twenty-shot test:

1. **Stage 1, Generate from the layout.** Give the layout as the only reference, with a strength around 0.2. The camera height, walls, doors and figure places come from the drawing. Describe each figure by its clothes, not as "the man from Image N". At 0.3 the people kept the layout's clay look; 0.2 kept the places and gave photographed skin and cloth.
2. **Stage 2, Edit in the cast.** Give the cast references first and the stage 1 frame last, so the frame keeps its framing. Ask to keep the camera, room, places, poses and props, and to take "only faces, hair and clothes from the references, never their poses or expressions". Without that line, a reference's pose and smile came back in the frame.
3. **Repair with a marked Edit.** Fix one prop, door or hand at a time with a region mark. A mark fix worked on some frames and did nothing on others. Two tries is the limit; after that, record the defect and select.

What the layout must get right, because stage 1 copies it:

- **Openwork panels need visible openings.** A solid gold panel came back as a door. Draw the grid with dark gaps, and call it "an open grid of thin bars" in the prompt.
- **Heads face someone.** A head with skin on every side came back facing the lens. Put skin only on the side that faces the person looked at, and a hair cap on top.
- **Draw and write the start of the move, not its end.** The video animates from the keyframe. A frame that already shows the card held out leaves the clip nothing to do.
- **Cut a person from an insert in the layout and the prompt both.** A hidden figure that still leaves a chair block comes back as a person.
- **Keep the proxies apart on screen.** Three figures on one line from the camera merged, and the model dropped one of them in every seed.
- **Render the 3D layout without a filmic tone curve.** In Blender, the default view transform turned a dark red wall pink. Use Standard and lower the exposure.

Strength is quantized by the step count. On the tested 8-step image backend, the layout kept `max(1, int(8 × strength))` steps, so 0.3 and 0.35 gave identical images and everything from 0.05 to 0.24 kept one step. Read the backend's mechanism before you sweep a strength. A close or overhead shot where one proxy fills the frame fails stage 1: the clay shape stays, or turns into furniture or a doorway. Make such a shot from text with the room named, or crop it from a wider approved frame of the same person.

Fix identity one person per Edit. Mark only that person's face plus about 10%, and give the references in this order: the master, the frame, the mark. A head-and-hair mark on a close-up leaked the mark colour into the wall. The master's expression comes with its face, so restore the shot's expression with a second Edit. On a 0.2 base, most frames kept their expression and needed no second Edit. After each marked Edit, count the new mark-coloured pixels, and look at small patches yourself. Then compare the result side by side with its source. Select it only when nothing else changed.

Count people with upper-body detection. Full-body detection counted one of three seated people.

To move a person, use two Edits: remove them, then add them back. Name the direction and the destination: "walking toward frame LEFT into the open doorway". A wording without a direction walked the person toward a wall. Give it three seeds. In the test, one of three turned the right way. When a prop must lie on one surface, name that surface and the surface it must not be on.

Overhead inserts: a Generate that names "the hand of" a person drew the whole person. Generate the table top with no people, then add only the hand and sleeve with a marked Edit.

Marked Edits can print the mark. When a box covered mostly background beside a wrist, the box colour came back as a flat patch. Keep a mark tight on the object it changes. A face box with a cast reference added (to restore identity) printed the mark around the head, and the face still drifted toward another person in the frame.

A removal box can take nearby props with it: removing an extra glass also removed the glass in the next hand. Paste the lost region back from the frame before the edit, with a soft edge, on the CPU. The same paste-back repairs a printed mark.

Consecutive shots from one locked camera drift apart when each is generated on its own (props, door, lattice, chandelier). Derive the later shot from the earlier selected frame with a marked Edit of only what moves.

A CPU paste carries its source's viewpoint. A glass cut from an overhead frame's edge showed its stem in side view and failed the insert. On a locked camera, paste a prop at the same pixels in every shot, and check what else sits there (a rim that moved).

A mark that touches another person's limb changes that limb too. A hand mark that overlapped the card hand turned it into the other man's sleeve in both seeds. Keep the box clear of every limb that must stay, and name that limb in the prompt as unchanged.

For a back view, write "seen from directly behind, his face not visible". A softer wording came back in profile.

Image models draw Chinese text wrongly. Ask for a blank card, then set the type on the CPU. Find the card as the largest connected dark area; the darkest pixels alone also take the chopsticks and a sleeve. Draw the flat card at the photographed card's aspect, or the warp squashes the type. Draw it at twice the photographed size, because a large shrink in the warp breaks thin strokes. Paint the type only where the card is dark, so a finger stays in front of it.

A text insert the audience must read is the reader's point of view: turn the frame so the text is upright for the character, rather than keep the wide camera's orientation.

Edit with a matched resolution returned 704×1280 for a 720×1280 source. Keep every keyframe of a set at the same size before the video stage.

Select a frame when every material finding passes: who is in view, places, facing, props and hands, the mover's start state, and the doors the action uses. Record a minor layout difference as a known defect for the board review, rather than spend another round on it. The frame check does not cover expression, so check emotion beats yourself.

## Draft and final are different artifacts

Low resolution exists for a fast, reviewable demo. It is not a commitment to upscale that demo. Carry forward story intent, cast, framing, blocking and timing. A new final take may differ in detail unless the brief or a review decision requires the exact draft performance.

Choose preview sizes from budget and supported geometry, in the delivery aspect ratio. A padded or square transport size is a local workaround. Tiny previews can settle timing but not eyes, hands, texture or fine detail.

A 2× upscaler doubles width and height: about 270p becomes about 540p, not 1080p. For 1080-class delivery, a 540-class source plus one 2× pass is one reasonable plan. The official Layout to Render example uses 960×544 then 1920×1088. Those are example sizes, not defaults.

Compare total turnaround for each finishing method: model loading, generation or upscale, review and likely retries. Prefer measured timings and label estimates as estimates.

| Situation | Evaluate first |
|---|---|
| Demo settled story and timing; exact motion is flexible | Native high-resolution generation from the retained cast, look and brief |
| The producer wants to keep a specific performance or camera beat | Reference-video upscale or compatible latent continuation, with drift checks |
| A 3D layout already defines motion and camera | Regenerate at final resolution from the same layout and look references |
| The draft has poor hands, faces or artifacts | Improve or regenerate the base; upscaling does not repair it |
| Upscaler setup, passes or model switches cost more than a native render | Native final generation |
| Exact source pixels, contacts or text must survive | Conventional composite or render |

- **Latent continuation:** carry the selected first-stage latent and its conditioning into a compatible finishing stage, only if the backend exposes resumable latents. A seed is not a latent cache.
- **Reference-video upscale:** feed the clean selected draft to a compatible upscaler such as the [LTX Pixel Spatial Upscaler](https://huggingface.co/Lightricks/LTX-2.5-22b-IC-LoRA-Pixel-Spatial-Upscaler). Avoid heavy compression first. Compare the result with its parent for identity and prop drift.
- **Controlled high-resolution regeneration:** the same layout, look frames, cast and performance controls at higher resolution. Reusing only seed and prompt does not preserve the draft. The result needs its own review.
- **Conventional resize:** a review or export convenience with no new detail. Label it.

Avoid chains of repeated generative upscales. Keep the exact parent take or latent, conditioning versions, model and adapter, enhanced prompt, seed, schedule, precision and output geometry. Put final-size captions, phone UI and precise lettering in the composite step. Report actual output size and source resolution separately.

## Representation and iteration

`production` may hold stage design, capability assumptions, profiles and document links. A shot's `production_plan` holds its intended route, layout brief, finishing method and acceptance criteria. Plans never rewrite an existing take's provenance. Scene files and layout clips become versioned assets once created, with pinned dependencies. Use `video_conditioning` for a layout dependency of a motion take. Do not invent media paths for planned artifacts.

A finishing output can be a new shot version with `tier: final` and `derived_from: {shot_id, version}`. Keep `selected` independent of a proposed next take. Record the review scope (layout, look, motion, edit, finish) so approval is read against the artifact actually reviewed.

Change impact:

- Camera, lens or blocking → layout, look frame if its projection changes, motion, finishing, edit.
- Palette or material → look frames, motion, finishing. Camera animation stays unless geometry changes.
- Offscreen voiceover → dialogue, caption timing, mix. Picture stays unless timing changes.
- Finishing artifacts → retry that derivative. The selected draft stays.
- Cut change → edit ranges, captions, sound. Regenerate only where handles or coverage fall short.

If the producer says to assume a capability exists, record it as an assumption and keep designing. Verify the endpoint, settings and model when you prepare to run it. Never report an assumed integration as tested.
