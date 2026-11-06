# Project format

Use a project directory with `project.json`, generated `review.html`, `storyboard/`, `assets/`, `shots/SH01/v001/`, and `exports/` when those contain real files. Keep original legacy files outside this tree intact during a migration. Paths in the manifest are relative to `project.json`; legacy provenance may point outside it. Runtime scripts should resolve paths against the project root, not the shell's current directory.

A compact example of the data shape follows. Create actual assets and shot content for the user's project; do not leave these example paths in a deliverable.

```json
{
  "schema_version": 1,
  "id": "film-unique-id",
  "revision": 1,
  "title": "Film title",
  "brief": "Premise and intended emotional turn.",
  "settings": {"target_seconds": 60, "max_shot_seconds": 6, "aspect_ratio": "16:9", "platform": "YouTube", "language": "en", "api_base": "http://127.0.0.1:8765", "preview_render": {"width": 384, "height": 384, "num_frames": 121, "frame_rate": 24}},
  "status": "animatic; remaining motion blocked",
  "blockers": ["Specific operational issue and required recovery"],
  "storyboard": "storyboard/board.jpg",
  "exports": [{"label": "Timing animatic", "path": "exports/animatic.mp4", "kind": "animatic"}],
  "assets": [{
    "id": "MAYA-LOOK", "kind": "character", "label": "Maya", "description": "Stable visual traits", "selected": "v001",
    "versions": [{"id": "v001", "image": "assets/characters/MAYA/v001/reference.png", "review_status": "unreviewed", "inputs": [], "provenance": {"backend": "discovered-backend", "request": "relative/path/to/request.json"}}]
  }],
  "shots": [{
    "id": "SH01", "start": 0, "duration": 5, "purpose": "Establish isolation", "dialogue": "", "selected": "v001",
    "versions": [{"id": "v001", "image": "shots/SH01/v001/preview.png", "reference": "shots/SH01/v001/reference.png", "video": "shots/SH01/v001/clip.mp4", "render_status": "complete", "review_status": "unreviewed", "notes": "", "prompt": "Actual model prompt", "inputs": [{"asset_id": "MAYA-LOOK", "version": "v001", "use": "image_reference"}], "provenance": {"operation_id": "retained-id", "request": "shots/SH01/v001/request.json"}}]
  }],
  "history": []
}
```

IDs are stable; version IDs are unique within their owner. `selected` is the chosen take, not an approval. Asset kinds commonly include `character`, `setting`, `voice`, and `dialogue`. Voice versions may expose `audio` (casting sample or scripted performance), `reference_audio` (exact clone reference), `transcript`, and `description`. Dialogue asset versions pin the voice version in `inputs`. Record script text and speaker, and place timings in the shot or a separate dialogue timeline if needed. A shot's `dialogue` entries carry `speaker`, `line`, `at` (seconds into the shot), `audio` (the selected take) and `direction` (the written delivery the take was generated with). `sound_files` lists the effect and ambience files the shot plays. `checks.cast` and `checks.sound` hold the recorded cast and sound verdicts with the hashes of the files they judged. A version may carry `generation`: the ordered steps that made its picture or clip, earliest first, each `{step, backend, mode, seed, settings, prompt, references: [{index, path, role}], operation_id, elapsed}`. A reference that is itself generated contributes its own steps before the step that used it. A dialogue entry carries `generation` for its take the same way (a clone take lists its clone reference as an audio reference), and the shot's `sound_generation` maps each `sound_files` path to its steps. Build these from the request and metadata files saved beside each output, never from memory.

Input `use` controls iteration impact:

- `image_reference`, `scene`: update storyboard references and regenerate dependent video.
- `video_conditioning`: regenerate video because its supplied conditioning changed.
- `audio`: regenerate the dependent dialogue asset when necessary, then update captions and mix; do not regenerate silent picture merely because the soundtrack changed.

`render_status` describes production (`planned`, `complete`, `blocked`, `failed`, or `stale`). `review_status` describes the reviewed take (`unreviewed`, `approved`, or `revise`). When `review.py feedback` imports an approval, it records `approved_sha256`, the hash of the take's clip, else its frame, else its audio. If those bytes change later, the board shows the take as unreviewed with `approval_void`. An approval recorded before pinning has no hash and stays as it is. A blocked still preview has no `video` field; missing motion is not substituted silently. Failed operations may be recorded in provenance or a version's `error`.

A take conditioned on an earlier shot may use `{shot_id, version, use: "preceding_cut_frame", frame_index}` (or `selected_end_frame`). Each dependency identifies exactly one asset or shot. Validate target kind/version and cycles; propagate stale versions and change impact through shot continuations as well as assets. Save the actual extracted guide image locally in provenance; naming a frame does not prove it was supplied.

Immutable media and request files live beside their take. A new take creates `v002` and pins its actual input versions. Keep old versions available in the board. `history` records feedback imports and old selections. Browser feedback includes project ID, the manifest revision used for the review, per-shot and per-asset base selection, chosen version, review decision, and notes. Import rejects mismatched project/revision/selection and invalid version IDs before changing the manifest.

Asset changes should create a new version and advance `selected`, then increment the manifest revision. The board detects staleness transitively through selected assets' pinned inputs. A dry-run `plan --changed ID` can preview impact before creating that new version. To express an approval of cast or voice, record that asset version's `review_status` explicitly; never infer it from a render finishing.

Feedback may include `shots` and `assets` arrays with the same review shape. A `takes` map preserves draft decisions for previously visited versions when switching takes; import validates every referenced take before writing.

## Profiles, package and beats

`settings.profile` is `drama` or `short`. A missing profile means `drama`. A shot may carry `source`: `generated` (the default) or `footage`. Footage shots skip the staging, card, hash and shot-length checks. Creator projects add:

```json
{
  "package": {"title": "...", "thumbnail": {"brief": "..."}, "critical": [{"item": "...", "beats": ["B1"]}]},
  "beats": [{"id": "B1", "role": "promise", "shots": ["SH01"], "energy": 4},
            {"id": "B2", "role": "setup", "shots": ["SH02"], "energy": 2, "sets_up": ["B3"]},
            {"id": "B3", "role": "payoff", "shots": ["SH03"], "energy": 5}]
}
```

A beat spans its shots. `review.py beats` checks the plan and `ready` runs the same check for creator profiles. See [creator-formats.md](creator-formats.md).

## Project identity, ownership and lifecycle

`project.json` is the production register. Its `id` is stable across title changes and revisions and unique across films; shot IDs such as SH01 are only unique inside their project. Use the project ID together with an asset/shot ID and version when recording external jobs, imports or feedback. The absolute root is an execution context, not a portable media path inside the manifest.

At project creation, save the brief and settings and register planned work honestly. A planned version may contain its prompt and intended inputs without image/video paths; add actual outputs only once they exist. Do not label an existing low-resolution face candidate as a completed high-resolution actor card. Update the manifest as references, media, selections and review decisions become available.

Before resuming, read the manifest, inspect pending operations and local results, and continue missing work rather than creating a second project or duplicating finished jobs. Before switching projects, persist pending operation IDs and their destination paths in the originating project's operation records. Download their results back into that project even if another film is active. Keep API result URLs as provenance, never as the sole retained copy.

Use project-relative paths for local media and documents. Referenced creative inputs and deliverables should resolve inside the project root, including after symlink resolution. Historical migration provenance may identify an external original; it is not a live dependency. When an outside asset must be used, import a local immutable copy first. Do not move legacy originals or break existing scripts during organization.

For an imported version, record provenance such as:

```json
{"imported_from": {"project_id": "source-film-id", "asset_id": "ACTOR-LOOK", "version": "v003", "path": "/source/project/assets/actor/v003/master.png", "sha256": "actual-source-content-hash"}}
```

A local import should have its own asset ID/version, local media path and review status. Updates to the source do not update the import automatically. Actor identity cards, voice references and setting images count as project assets even when reusable. Keep reusable UI templates free of a previous project's embedded manifest, cast names, media paths, export links and browser-storage keys. Bind browser notes and feedback to the project ID and manifest revision; reject imports for a different project.

Before publishing a review, check that every displayed clip, poster, reference, audio file and export belongs to the intended project or is an explicitly recorded local import. A separate review server must serve that project's root; do not replace another project's server. Archive by retaining the manifest, requests, actual inputs, selected and historical media, and feedback together. Cleanup or deletion requires the user's scope; creating a new film does not authorize clearing an old one.

## Production design and finishing

Keep the treatment and ending, the timed action-and-sound script, the staging map and the storyboard inside the project. Link the documents from `production`. They may share one compact document.

`review.py` reads four records for the storyboard gates:

```json
{
  "staging": {
    "map": "storyboard/staging/v001/map.png",
    "cameras": ["C1", "C2"],
    "timeline": [{"id": "T1", "state": "Kettle boils; both cups still empty"}]
  },
  "shots": [{"id": "SH01", "staging": {
    "camera": "C1", "world_time": "T1", "lens": "normal",
    "background": "kettle on the left burner, steam rising; window shows morning light",
    "mover": "her right hand lifts the kettle", "camera_move": "locked",
    "mouth_visible": "hidden", "end_state": "kettle tilted over the first cup", "attention": "center", "slot": [0.0, 3.5]
  }}],
  "storyboard_review": {"at": "...", "verdict": "pass", "shots": {"SH01": "<sha256>"}, "findings": []},
  "storyboard_approval": {"at": "...", "user_words": "producer's exact words", "shots": {"SH01": "<sha256>"}}
}
```

`staging.map` is a project image. Every shot cites one of `staging.cameras` and one `staging.timeline` id. The rest of a shot's `staging` is its layout card: lens class, what the background shows at that world time, the one mover, the camera state, how visible a mouth is (`hidden`, `small` or `close`), the state the shot ends in, where the attention target sits, and the animatic slot in seconds. `review.py lint` fails a card without `camera`, `world_time`, `mover`, `camera_move`, `mouth_visible` or `end_state`, and `review.py verdict` refuses to record a review of such a board. `ready` and `gate` do not run the lint, so a board approved before the lint existed stays open. The blind reviewer checks the card against the frame. A shot's `production_plan` may add `take_budget`, the number of takes agreed for it. Write `storyboard_review` only with `review.py verdict`, and `storyboard_approval` only with `review.py approve`. A failed finding in `storyboard_review.findings` carries `severity`: `block` or `revise`. Only `block` keeps the board from `ready`. A failed finding recorded before severities existed counts as `block`. `storyboard_approval.revise` lists the revise findings the producer approved the board with. With `--waive-review`, `storyboard_approval.waived_review` holds the `at`, the fail count and the `digest` of the failed review the producer accepted. Any change to that review record voids the waiver. A waiver recorded before digests existed matches by `at`. The script computes each shot hash from the selected version's storyboard frame bytes, start, duration, purpose, dialogue, selected version, inputs, staging citation, and the staging map. Prompt edits do not change the hash. A change to story, action, staging, timing or references does. `review.py gate` exits non-zero until both records match the current hashes of the shots about to be submitted. Older projects without these records still build and plan. Only `ready`, `gate`, `verdict` and `approve` require them.

History entries of kind `user_feedback` keep `user_words` (verbatim) beside `interpretation`. Approval and blind-review events are logged in history as well. Take selection is not approval.

Store scene-wide physical phases and cut/attention purposes in production documents or per-shot plans. Keep intended states separate from observed take results. Quality records should identify actual take/time range, review mode, observed defect and pass-for-demo/revise/reject/unassessed outcome. Do not overwrite historical failures with planned fixes or equate structural validation with motion/story approval.

Optional `production` holds stage descriptions, capability assumptions, render/finish profiles, and design-document links. Optional per-shot `production_plan` holds `route`, `reason`, `action`, `camera`, `layout`, `finish`, and `acceptance` criteria. Keep these intended next-iteration choices separate from existing versions' actual provenance. See [production-design.md](production-design.md) for stage contracts and change impact.

For motion planning, `production_plan` may include `reference_strategy`, `motion_entry` and `handles`. These are descriptions of intended roles, action already underway and handle budgets, not executable API fields. Pin actual conditioning guides in take inputs/provenance with role, frame index/time and strength, plus local image paths when created. Record actual editorial source in/out frames, fps and duration on the take; keep source and timeline times distinct. `storyboard_image` can identify an explicit planned frame independently of a take's reference/preview. All registered live media must stay inside the project and exist.

An illustrated action's key moment may be its destination rather than its opening pose. Where needed, retain separate `guides: [{role, image, frame_index, strength}]` on the version, after those images exist. The shared viewer exposes these images under References & motion and the helper checks project ownership. Do not silently use a fully pressed button or completed turn as the starting state for a prompt asking the action to begin. Actor-card versions may expose high-resolution `reference_views` with image and provenance; alternate views remain candidates until compared with the canonical master. A character's version also lists `angles_needed`: `[{angle, shots}]`, each angle the shots show that character from (for example "back, head turned over the right shoulder" for SH03). The cast check compares the views with this list, so a view no shot needs is not required, and a mirrored view counts once the flipped accessory is corrected.

For a finished derivative, a shot version may add `tier: "final"` and `derived_from: {"shot_id": "SH01", "version": "v001"}`. Keep its parent and actual upscaler/latent provenance. A new final derivative begins unreviewed even when its parent draft was approved. Current review decisions are per take; richer per-stage approval controls remain a future UI extension.

For layout-driven or transformed shots, retain optional turnover details in the take's provenance or an existing linked edit record: `layout_revision`, `camera_revision`, `world_time_interval`, source/cut in/out frames with fps and explicit inclusive/exclusive convention, available handles, crop/scale, retime, composites and colour interpretation where applicable. Keep source ranges distinct from edit-timeline positions. These are local descriptive records, not executable API fields or new UI requirements. Use them to reconstruct the reviewed cut and compare a replacement against its driving layout and parent take; see [production-design.md](production-design.md) for practitioner attribution and scope. Preserve canonical media and record transforms rather than overwriting the source.
