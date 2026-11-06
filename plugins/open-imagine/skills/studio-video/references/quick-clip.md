# One clip

A clip is one shot of a few seconds. Do not create a project, a storyboard or a board.

## Agree the clip

Ask at most two questions, and give a recommendation with each.

- **Action and viewpoint.** What the person or object does, and where the camera stands. One action reads better than three.
- **Shape and length.** Offer two shapes from the backend's list. A phone clip is 9:16; a screen or a film insert is 16:9.

Carry every other choice as a proposal and start. Do not ask the producer to choose model names, frame counts or sampler settings.

## Discover before you write

Read `GET /api/v1/videos/backends/{id}`. Use its modes, shapes, frame grid, reference format and audio support. Do not invent a field. Keep frames on the backend's grid, and use its frame rate.

## Build the request

- **Prompt.** Subject, one action, camera and sound in two or three sentences. Describe how the action changes over the clip.
- **Reference.** One image at `frame_index: 0` when identity or a supplied place must hold. A later index guides a later moment in the clip.
- **Audio.** When supplied, send `{"name", "data"}` with the actual bytes. The engine returns that track with the clip, and a close single can lip-sync to it. Read [the audio route](motion-control.md#the-audio-route-that-passed-2026-11-04) before you promise sync, and watch the clip.
- **Seed.** A null seed draws one. Record the seed you sent, or the clip cannot be repeated.

Read [studio-api.md](studio-api.md) for the current request fields and [motion-control.md](motion-control.md) for camera and motion wording.

## Run and keep

Submit one operation with `kind: "video"` and wait for `succeeded`. Download before retention expires: a public result lasts about ten minutes, and a restart clears it.

Save the clip as a descriptive `.mp4` and write `clip.json` beside it with the exact request, seed, backend and model, operation ID, enhanced prompt, references and what you inspected. Keep base64 out of the file.

## Inspect the actual clip

Watch it at normal speed with sound.

- The requested action happens, and it happens once.
- The camera does what you asked: fixed, or one move held steady.
- No drawn text unless the clip needs it. When a voice track is present, the model sometimes draws the words into the picture. Take frames from the clip with `ffmpeg` and look at them. `edit_check.py` gives the same reading for a one-clip edit manifest.
- When speech is visible, watch the mouth. A moving mouth is not proof of sync.
- Identity matches the reference when one was used.

Retake only for an observed defect, within three takes. A different seed is not a repair for a staging fault.

## Stop at one clip

When the request grows to two shots, a story or a recurring character, stop and switch to a scene or a production. A clip does not become a film by adding takes.
