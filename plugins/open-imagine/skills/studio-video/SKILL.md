---
name: studio-video
description: Create video with Open Imagine's Video, Image and Voice APIs. Make one clip, a short scene in one location, a music video from performance cutaways, or a storyboard and animatic, and run a full production when the work needs it. Invoke the studio-image skill for every still frame and video keyframe. Use for clips, scenes, shorts, storyboards, animatics and music videos; also 短片, 分鏡, 故事板, 動畫, 音樂錄影帶.
---

# Studio Video

For a production, keep story decisions, selected media, generation records and feedback in one durable project. `project.json` registers the production. The review board is its viewing interface. A single clip keeps `clip.json` beside its file. Model-specific guides govern prompting. The discovered API governs executable settings.

Requires a reachable Studio server, Python 3, and `ffmpeg`/`ffprobe` for the checks. The owned runner also needs the Studio checkout: pass `--repo` or set `STUDIO_REPO`.

## Choose the path

Decide the route before you create anything.

- **One clip.** A single shot of a few seconds. Read [quick-clip.md](references/quick-clip.md). Do not build a project or a board.
- **A short scene.** Two to five shots in one location, with one continuous action. Build one approved set plate, derive every frame from it, and keep the production below.
- **A music video.** Performance cutaways and inserts cut to a song. The viewer accepts a jump between places, so do not attempt continuous geography across the whole song.
- **A storyboard or animatic.** Frames and timing are the deliverable. Use the image route and the board without rendering video.
- **A full production.** A story that needs many locations and recurring cast. Continue below, and read [limits.md](references/limits.md) first.
- **A revision.** An existing project changes direction, timing or a selected take. Reopen its manifest and fix the smallest affected set.
- **Research or a skill change.** No production starts.


## Three rules for a production

Earlier productions failed in the same way three times. The agent that made the work checked it, called it ready, and the producer then found staging or continuity failures. These rules exist because prose warnings did not stop that.

1. **One staging map.** Before storyboard frames, save one top-down map of positions, reachable props and camera setups, plus a world-time timeline. Every shot cites a camera and a world time from it.
2. **Blind reviewers decide readiness.** The maker never grades its own work. Fresh subagents run the cast check, the blind board review and the sound check in [board-review.md](references/board-review.md), and their verdicts are recorded. A board reaches the producer only when `review.py ready` passes. A reviewer reads frames and cannot see the contradiction between two places, so the maker still inspects every image and every join.
3. **Video waits for the producer's recorded approval.** In a production, run `review.py gate` before every video submission, tests and low-resolution demos included. If it exits non-zero, do not submit. A single clip has no board: [quick-clip.md](references/quick-clip.md) gives the rule that replaces it.

```bash
python3 <skill-dir>/scripts/review.py ready   /abs/project.json                 # board, cast and sound checks current?
python3 <skill-dir>/scripts/review.py verdict /abs/project.json /abs/verdict.json
python3 <skill-dir>/scripts/review.py check   /abs/project.json cast  /abs/cast-verdict.json
python3 <skill-dir>/scripts/review.py check   /abs/project.json sound /abs/sound-verdict.json
python3 <skill-dir>/scripts/review.py approve /abs/project.json --user-words "<producer's exact words>"
python3 <skill-dir>/scripts/review.py gate    /abs/project.json --shots SH03 SH04
```

`approve` refuses a board that is not ready. The cast check is pinned to each character's selected image and reference views, and the sound check to every dialogue take and `sound_files` entry; changing one reopens that check. Approval and review are pinned per shot to hashes of the frame, timing, purpose, inputs and staging map. A change to a shot reopens only that shot. A retime after the renders reopens it too, so record a new review or approval before you render that shot again. A change to the staging map reopens every shot. A general "continue" or "finish the film" is not approval. Approval needs a board this agent showed the producer, with its version. Words about a board that was not shown, or a general "looks good", are not approval. Record only words in which the producer approves the board they saw.

## Begin with the producer

Treat the user as the producer unless someone else decides. Start a new film or a major change of direction with a short creative discussion. On a continuing project, recover the brief and decisions first, and discuss only what is unresolved or changed.

The producer may not work in film. Speak in plain words, and define a film term the first time you use it. When the producer uses a term in a different sense, such as "scene" for one shot or "opening image" for each clip's keyframe, name the usual term once, define it in one sentence, and keep to it. When a word could mean two things, ask which one before you act on it.

Triage the request: concept exploration, story development, production of an agreed concept, revision, or research and workflow work. A request for research or a skill change does not start a production.

Establish the theme or central question, the premise, the audience and viewing context, the feeling and tone, and what success looks like. Theme is what the film explores. Plot is what happens. Technique is how it is made. Discuss the constraints that shape direction: format, runtime, delivery, budget, available assets and non-negotiables. A producer may want a mood or an open question instead of a message.

Ask at most three questions per round: the ones whose answers would change the film most. Give each concrete alternatives and your recommendation. Carry every other open choice as a labeled proposal in the brief, and raise it only when it blocks the next step. Do not ask the producer to choose unfamiliar technical tools. If the direction is uncertain, offer two or three short treatments with their intended experience and main trade-off. When the brief already settles direction, restate it briefly and continue.

Save a compact producer brief in the project: theme, premise, audience experience, tone, constraints, selected direction and open choices. Keep producer decisions separate from agent proposals. An added ending or twist stays a proposal until the producer selects it.

Fit the story to what exists and what the models do well, before you write it:

- **Inventory:** list what is already available: approved actor cards, settings, voices, props, takes. Build on it.
- **Ceiling:** agree a limit on shots, cast, locations and generations. Count the beat record against it.
- **Out of scope:** name what the film will not attempt, such as long visible dialogue, crowds, or complex hand contact. When something is out of reach, bring an alternative with it, not only a "cannot".
- **Film statement:** confirm three or four sentences that describe the film. Everyone works on the same movie.

Then choose methods. Explain each recommendation through the brief: why this performance approach, camera and sound language, animation, direct generation, Layout to Render, composite or hybrid serves the intended experience, and what it costs. Do not default to photoreal coverage, twists, fast cuts, music or 3D.

## Work through connected causes

**Producer intent → dramatic change → physical staging → audience viewpoint and sound → shot and reference design → generated performance → edited sequence → observed audience effect.**

Each link constrains the next. A missed opportunity needs an available action and a moment when it becomes unavailable. Staging makes it possible. Coverage makes it legible. References preserve its geometry. Generation performs it. Editing controls when the viewer understands it. Read [connected-production.md](references/connected-production.md) before you create or revise media. It defines the beat record and how to diagnose a failure.

When a result fails, repair the earliest broken link and its dependents. A changed seat can invalidate reach, camera views, eyelines and references. Do not apply a cosmetic fix downstream of an unresolved contradiction.

## Establish or resume a project

Before creating assets, identify a unique project ID, an absolute project root and its manifest. Reopen that manifest to continue. A new story gets a separate project. Revisions stay in the same project as new versions. Read [project-format.md](references/project-format.md) for the manifest contract.

Keep all inputs, actor cards, references, requests, operation records, takes, exports and feedback inside the root. Resolve paths from the root, also in background jobs. Return pending results to their originating project after a project switch. Cross-project reuse needs a local immutable import with source and content hash.

Record duration, aspect ratio, the delivery platform, shot-length limit, language, API endpoint, preview and actor-card resolutions, exclusions and review preferences as project settings. `settings.profile` picks the format. `drama` is the default, including projects without this field. `short` means vertical video up to 60 seconds. For `short`, read [creator-formats.md](references/creator-formats.md) and check the plan with `review.py beats`. If `~/.config/studio-video/preferences.md` exists, read it for the producer's standing choices. The older `~/.config/studio-film/preferences.md` still applies when the new file is absent. Newer instructions win. Resume from saved jobs and media instead of regenerating finished work.

## Design before rendering

Before you write or revise any still prompt or video keyframe, invoke the installed `studio-image` skill. Use its main guide and the selected image backend's model notes before drafting the frame. In this checkout, read [its main guide](../studio-image/SKILL.md). Use it to direct each frame's composition, viewpoint, depth, focus, light and visual treatment for the intended video mood. For film frames, follow its [film-still use case](../studio-image/references/use-cases.md#games-and-film), [prompt craft](../studio-image/references/prompt-craft.md), [shot design](../studio-image/references/shot-design.md), [photography guidance](../studio-image/references/photography-genres.md) and [cinematic styles](../studio-image/references/style-library.md#cinematic-styles). For frame edits, read its [editing guidance](../studio-image/references/editing.md). For animation or illustration, follow the matching image-skill route. `studio-video` directs story, staging, continuity, keyframe timing and motion. `studio-image` directs how each still looks and how to prompt or edit it. Keep the selected backend and project format. Treat a style result as evidence only for the model that made it. If the sibling link is unavailable, locate the installed skill named `studio-image` and invoke the installed skill by that name before making frames. Keep image-prompt rules in that skill instead of copying them here.

For a new or rejected visual treatment, establish the story and staging, then develop one complete scene within the agreed image budget, as in [production-design.md](references/production-design.md#establish-the-visual-treatment). Record the camera, depth, light sources, shadow detail, palette and materials. Inspect the actual image at full size and get the producer's choice before expanding that treatment into the board. An existing accepted treatment can be reused. Keep the actor master for identity; its neutral pose and studio lighting do not define the scene. Label a concept that has not yet matched the cast honestly.

Visual acceptance and continuity are separate judgments. A cast or board check, `review.py ready`, or a passing code test does not establish that the producer likes the pictures. A chosen look does not approve video. Explicit limits on generation or GPU use still apply to look tests and to API discovery that would start a model server.

The lead agent personally inspects every new native image, including rejects, and each selected crop at delivery scale before building on it. On resume, inspect the selected images used by the active work. Save observations as described in [maker inspection](references/board-review.md#maker-inspection). Contact sheets and delegated reviews do not replace this duty; it supplements the independent readiness checks.

1. Develop the story with [film-craft.md](references/film-craft.md): objective, obstacle, stakes, consequential response and ending, then a timed action-and-sound script.
2. Stage it. Save the staging map and the world-time timeline. For travel, contact or changing physical state, use [physical-continuity.md](references/physical-continuity.md).
3. Give each shot a layout card derived from the map: camera, lens class, world time, what the background shows at that moment, the one thing that moves, the camera state (locked by default), how visible a mouth is (hidden, small or close) and the state the shot ends in. `review.py lint` names every card that lacks one of these. Use [visual-language.md](references/visual-language.md). Never derive an insert or reverse view from an isolated attractive image. Every character stays at their timeline position in every shot: draw each keyframe's layout from the map, as in [production-design.md](references/production-design.md), rather than placing people with words. Before generating adjacent frames, state [what each cut claims](references/connected-production.md#state-what-each-cut-claims) about place, direction and time.
4. Save a storyboard with actual frames, stable shot IDs, purposes, durations, action, sound, dialogue, pinned reference versions, layout cards and intended prompts. A shot list without frames is a plan, not a storyboard. In one location, derive every frame by image edit from one approved empty set plate; a fresh text prompt is a new place, as [limits.md](references/limits.md) records. Run the frame check on each frame as it lands, and retake a failed frame before you build on it.
5. Lock the voice and key sounds, then cut a timed animatic: each frame held for its slot against that audio. Total duration and the longest shot must fit the settings. A changed line later reopens every shot that holds it. Run the sound check.
6. Run the blind board review. Repair failures and review again until it passes.
7. When `review.py ready` passes, present the board and the animatic to the producer, with the list of each line to play. Record the approval with `review.py approve`. A board that is not ready goes to the producer only as an explicit progress report that names its open failures. If the producer approves it after reading those failures, record the approval with `review.py approve --waive-review`. The waiver names the failed review and its fail count, and it covers only that review: a later review or a changed shot closes the gate again.

Choose direct generation, Layout to Render, composites or draft-to-final finishing with [production-design.md](references/production-design.md). For fixed-camera precision or hesitant motion starts, read [motion-control.md](references/motion-control.md).

## Prepare cast and sound

Pin a canonical actor master, the verified views the coverage needs, and wardrobe, hair and setting references. Keep identity separate from expression and scene lighting. Generate the actor's expression set once from the locked master, and reference the nearest approved expression in each shot. Freeze the costume for the film unless the story changes it, and give each actor one strong costume or graphic feature that reads when the face is small. Each character's selected version lists `angles_needed`, the angles the shots show that character from, and `reference_views` that cover them, plus a close-up of the hands and any accessory whose side matters. When the model will not turn a figure to a needed angle, mirror a view of the other side and correct the flipped accessory with a marked edit. Generated angles are candidates until compared with the master. Run the cast check before the first storyboard frame. Never use a tiled sheet as a single-person opening frame. Derive small generation references from high-resolution masters. A new card cannot repair existing footage.

When Drama-3 is selected, read [drama3-speech.md](references/drama3-speech.md). Retain short casting takes, clone the selected recording when supported, and keep its exact waveform and transcript. A clone carries the voice, not the performance: give every line its own written direction, record it as the line's `direction`, and generate the take with it. Separate visible dialogue, offscreen speech, device sound and narration. Visible speech needs aligned lip sync.

For visible singing, read [the singing proof procedure](references/motion-control.md#prove-visible-singing-before-expansion). The audio route passed close singles in Mandarin, Cantonese and Japanese on 2026-11-04 and needs the dev transformer in the LTX-2.5 pack. Test one actual audio-driven performance and its edited joins before making the remaining performances. A supported audio input or a moving mouth does not establish lip sync.

## Generate and retain

Read [studio-api.md](references/studio-api.md) and discover current modes, shapes, frame counts and reference formats. Batch independent jobs by loaded model, because switching is costly. A continuation starts from the selected take's actual out-frame, not a new still, and waits for that result.

Save exact requests before submission. Download partial and terminal media before server retention expires. Each take gets immutable media, request and provenance: backend, model, settings, seed, actual inputs and versions, audio, operation ID and enhanced prompt when available. Keep base64 out of the manifest and review page.

Expect a low yield. Practitioners keep a few seconds from each clip and a small share of all clips. Agree a take budget per shot with the producer, generate within it, and select across takes. Drop each selected take into its animatic slot and check duration, opening action and ending action before you make the next dependent shot. Trim inside the slot; never stretch the locked audio.

After approval, test a small proof of the hardest physical relationship and its join across a cut before you scale up. If an essential action fails, change staging, references or technique. "More cinematic" retries are not a recovery. Stop repeated deterministic retries. Never restart the user's server or change its app to recover rendering without authorization. Label crops, held frames, composites and animatics honestly.

## Review and revise

Rebuild the board when assets, versions, selections, blockers or exports change. After you assemble a cut, register it in `exports` first: the Edit tab plays the first export listed.

```bash
python3 <skill-dir>/scripts/review.py build /abs/project.json
```

Always use the shared `assets/review.html` template. Read [review-interface.md](references/review-interface.md) before you change the UI. Improve the shared template instead of making a bespoke page.

Before anyone watches a cut, run `scripts/edit_check.py edit.json --export <film> --text --expect-text <shots meant to show text>`. It fails a clip that does not cover its slot, black frames, a still run over a second, text the video model drew into the picture, overlapping subtitles, and an export of the wrong length, without audio or peaking above -1 dBTP. It measures each clip's last half second for the end-state hold. The text reader also reads round objects (a phone lens, a shirt button) and hands as text. Look at the frame. If it shows no drawn text, pass that reading with `--accept-text SHOT:TEXT`. Retake what it fails, then watch. Watch the assembled edit at normal speed with sound for story, performance and rhythm. Compare identity at similar face scale. Watch critical physical actions in full, and watch the moving interval around each cut. Muted playback diagnoses visible motion. Audio-only listening diagnoses source, perspective and timing. Record take, time range, observed defect and a result: pass for demo, revise, reject or unassessed. Never accept a known essential failure to finish. Fix the smallest affected set, and keep old takes and feedback.

Record producer feedback in their own words beside your reading of it. Paraphrase alone loses the evidence the next revision needs:

```bash
python3 <skill-dir>/scripts/review.py note /abs/project.json --user-words "<exact words>" --interpretation "<what you will change>"
python3 <skill-dir>/scripts/review.py feedback /abs/project.json /abs/feedback.json
python3 <skill-dir>/scripts/review.py plan /abs/project.json --changed ACTOR-LOOK
```

`feedback` imports browser drafts and rejects a different project, revision or base selection. `plan` previews dependency impact and submits no jobs.

## Evidence

State which stage you inspected and what remains unassessed. A plan holds intentions. A storyboard holds still staging. A motion proof covers only its tested action and joins. The assembled edit covers timing, performance and meaning. A finished render, a passing script, a written prompt, research, or a high-resolution actor card is not visual evidence. Finish with direct review and video links, the actual readiness, and the material open limits. Never call an animatic a finished film.

## Deliver

Give the producer playable files with descriptive names, and keep each final beside its request and provenance. Say what you measured, what you watched and what remains unassessed. A storyboard, an animatic and a finished film are different deliverables; name the one you made. Read [delivery](references/delivery.md) for the file, audio, caption and sharing checks. Publishing is a separate action.

## Words used here

- **Brief**: what the producer wants, in their words.
- **Clip**: one shot of a few seconds.
- **Scene**: a short run of shots in one location.
- **Beat**: one unit of change the audience can feel, with a setup and a payoff.
- **Coverage**: the shots that make one action legible from chosen viewpoints.
- **Staging map**: one top-down plan of positions, reachable props and camera setups.
- **Layout card**: per-shot camera, lens class, world time, background, the one moving thing and the end state.
- **Set plate**: one approved empty image of a location, from which every frame in that location is derived.
- **Storyboard**: frames with shot IDs, durations, action, sound and intended prompts.
- **Animatic**: the storyboard cut to the locked audio at real timing.
- **Take**: one generated clip.
- **Out-frame**: the last frame of a selected take.
- **Keyframe**: an image bound to a frame index as a reference.
- **Board**: the review page that shows the storyboard, takes and exports.
- **Gate**: the recorded approval that must exist before a production submits video.
