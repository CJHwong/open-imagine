# LTX-2.5 prompt evaluation

## The video templates

### How they were sampled

Eight templates were written for LTX-2.5, each rendered once at the model's own defaults:
121 frames, 24 fps, 1024 x 576, seed 7, no references, one clip each, the same flags the
studio's runner passes. A ninth clip carried the bare sentence "A woman in a red coat walks
along a beach at sunset", which is the subject of the first template without its direction,
so a template's effect could be told apart from the subject's own motion. Every clip was
then judged against what its own text promises, from six frames spread across it and from
four numbers: the change between consecutive sampled frames, the same for the top quarter of
the frame, the mean level, and, for the two keyframe templates, the distance from the still
they were given.

The top quarter is in the measure because a subject walking across a locked-off shot leaves
it alone: a strip that moves says the frame itself moved. That is what separates a camera
move from a walk.

Seed 7, the M5 Pro, one clip each. The clips cost 308 to 496 seconds each, 430.9 for
the first.

Four more clips followed. One re-sampled the light template with a different wording, and
three chased the frame the style template drew. Each one kept the same seed, the same shape
and the same fill-in, so a pair differs by the one clause that changed. They cost 389 to 471
seconds each.

### What works

| Template | Evidence |
| --- | --- |
| Camera move | The top strip moved 16.7 across the clip against the bare control's 3.9, and the whole frame 19.3 against 12.8. The frame moves and the subject stays framed |
| First frame | Frame 0 sits 3.52 of 255 from the still it was given, and the clip evolves from there |
| Last frame | The last frame sits 5.5 from the still against 12.8 at the first, so the ending converged on it |
| Product turn | The pot turns, stays centred, and the label "PEARL" is rendered and held across all six frames |

The control is the useful half of the sample. With no template the frame is locked off: top
strip 3.9, whole frame 12.8, and every change in it is the subject walking.

The style template's own words were rewritten after this sample, and that rewrite rests on a
number that belongs to another clip. Its first text opened "shot on [film stock or camera]
with [palette and light]", and that wording draws a frame the text never asked for: black
bands down both sides with rounded corners on the picture, like a phone upload. The outer 4%
band of the frame measures 5.6 on the left and 1.2 on the right, where the bare control
measures 107.3 and 81.2. Three wordings left it standing: a clause asking for the picture to
fill the frame (3.4 and 1.0), a fill that named an editorial style instead of a documentary one
(5.6 and 1.2), and the reworded stock clause on its own. The reading that fills the frame,
38.0 and 36.5, belongs to 13-style-nofilm, and its fill differs from its pair in more than the
stock clause: it says "in the warm natural colours and fine grain of Kodak Portra 400, in a
clean editorial style", where the other says "shot on Kodak Portra 400 film with warm natural
colours and fine grain, in a 1990s documentary style". Crediting those two numbers to the
stock clause alone was wrong.

The shipped text, which reads "in the [colours and grain] of [film stock or camera]", still
draws the frame. Measured 2026-10-18: 16-audio-style-stock reads 5.6 and 1.7, and its control
08-style-stock, filled the way the template invites, reads 5.5 and 1.7, and the contact sheets
of both show the black columns and the rounded corners. Taking the word film out of the fill
does not lift it: 17-style-no-word-film reads 5.6 and 1.8 against 16's 5.6 and 1.7, with every
other word, the seed and the shape held. So the template is not proven, and one clip that
fills the frame against five that do not is not enough to name the words that decide it.

That paragraph was rewritten again on 2026-10-18, when the clip that fills the frame was run
again beside its pair. Two clips, the stock clause held and the style phrase moved, everything
else the same, seed 7, 1024 x 576, 121 frames: `30-style-editorial-fill`, which reads "in the
warm natural colours and fine grain of Kodak Portra 400, in a clean editorial style", measures
5.3 and 0.9 on the outer 4% band, and `31-style-documentary-fill`, one style phrase away,
measures 5.2 and 1.6. Both are pillarboxed, so the style phrase does not decide it, and the
38.0 that 13-style-nofilm measured does not reproduce: the same clause and the same style
phrase draw the frame tonight. Seven of the eight fills sampled now sit between 5.2 and 6.1,
against a bare control's 107.3 and 81.2, and six wordings were tried, among them one that asks
the picture to fill the frame. So the frame is what asking a video prompt for a film look
does, and the template was dropped rather than offered with the fault. Its text is in
`prompt_aids.py`, where it sat, with this evidence.

### What did not, and why they are not offered

| Template | Evidence |
| --- | --- |
| Style and stock | Draws the film look and a frame the text never asked for: black columns down both sides with rounded corners on the picture. 5.2 to 6.1 on the outer 4% band for seven of eight fills, against a bare control's 107.3 and 81.2, and no wording lifted it. Dropped 2026-10-18 |
| Loop | First frame against last 14.72 while the palette matched to a point, so the content moved rather than the light. A seamless loop wants near zero |
| One action | One continuous shot, but the empty cup to full arc never read, and the camera drifted closer after being told to stay put |
| Light changes | Two wordings, and both lose on the camera. The first asked for a pan and brightened where dusk should darken: level 91.6 to 96.6, and the top strip 43 to 49. The second asks for the camera locked off and names no pan, and the top strip still moves 38 to 42 against the bare control's 1.7 to 2.0, while the picture drifts forward down the street. The level turns the right way this time, 79.1 to 76.7, so the words can name the direction; they cannot hold the camera |

The last frame template shipped with the sentence that failed removed: it promises the ending
still and says nothing about an empty opening, which the clip did not deliver.

### The sound direction, sampled 2026-10-18

Each of the five shipped templates was rendered again with a sentence that names what is
heard. The vendor's guide lists audio as one of the six elements of a video prompt, and the
model's own enhancer writes one on every enhanced run, which the shipped templates did not
invite. Every clip held its template's fill-in, its seed 7, its shape 1024 x 576 and its
length of 121 frames, so a clip differs from the one it is paired with by that sentence and
nothing else. One clip each, 330 to 444 seconds a clip.

| Template | With the sentence, against its pair without |
| --- | --- |
| Camera move | The frame still moves: the top strip 22.08 from first to last against 16.66, the whole frame 24.58 against 19.33 |
| First frame | The opening frame sits 3.48 of 255 from the still it was given, against 3.52 |
| Last frame | The ending sits 5.52 from the still against 5.50, and the opening 12.88 against 12.76 |
| Product turn | The pot turns, stays centred, and holds "PEARL" on every one of the six frames, as its pair does |
| Style and stock | The look is unchanged, level 89.1 against 90.2, and both frames are pillarboxed, which is the fault above and not this sentence |

The sentence costs no template its own promise. The soundtrack changed in all five pairs, by
the mean level of the audio track: 12-audio-camera-move is 2.5 dB louder than 01-camera-move,
and the other four run 6.2 to 32.9 dB quieter, the largest being 13-audio-first-frame at -61.2
dB against -28.3 dB. Every clip carries an AAC track either way, 5.01 seconds, so nothing is
lost to silence.

What these numbers cannot say is whether the words named the sound the model made. A level
says the track changed, not that the sea is the sea. Two things follow. The words are kept,
because they cost the picture nothing and the guide asks for them. And a person has to listen
before the words are trusted: "only the sound of the sea" left one clip all but silent, which
is a plausible reading of the words and a poor soundtrack.

### What this sample does not settle

- One clip per template, one seed. A template that failed here might pass on another seed,
  or on another fill-in: one of the three that failed was re-sampled once, and the style
  template, which shipped, three times.
- One length and one shape, both the model's defaults. Nothing here says what these words do
  at 2 seconds or at 640 x 384.
- The reference strength control was not sampled. Both keyframe clips used 1.0.
- The camera move template originally ended "Locked off on a tripod", which contradicts a
  moving camera, and the model drew a tripod standing in the sand. The shipped text drops it.

### The vendor's own example prompts, run once each, 2026-10-20

Ten prompts, one from the 2.5 prompt guide and nine from the vendor's published samples, were
sent to `/api/v1/videos/generate` with no template and no words of this studio's own. Every
clip ran at 384 x 384, 121 frames and seed 7 on the M5 Pro, 115 to 207 seconds each.
Each clip was judged on a contact sheet at 1:1, and the cuts and the audio were measured;
"change" is a spike in the frame difference that the sheet confirms is a cut, not a re-render.

| Prompt | What the clip did |
| --- | --- |
| Multishot (guide) | Cuts at frames 46 and 82: the wide of the yellow raincoat, the close-up under the hood, the man. The guide's example reproduces |
| Car race | One shot, no cut, and the sound follows the action at r 0.89 |
| Riad perfume | Three shot changes at frames 29, 64 and 82, in the order the words ask: courtyard, bottle, bronze silk, back to the wide |
| Carnival | One shot, dense saturated crowd, motion-audio r 0.87 |
| Vienna 1974 | Continuous; the man looks up on the beat. Audio rms 0.057, 0.33 of the energy in the speech band |
| Decanter pour | Locked off. One change at frame 67, the ice drop, not a cut |
| Ballroom | The transformation runs; one change at frame 94 when the dancers arrive, no camera cut |
| Flamenco | The scene and the light read; the dance is generic, not flamenco heelwork. Audio rms 0.40, a guitar-like peak at 221 Hz |
| Courtroom | The scene is right and the audio is silent, rms 0.0009. A quoted line in a video prompt made no speech in this run |
| Motorcycle | The turntable rotates through four angles, but the frame difference reads 0.34 because the set is black. The sheet decides, not the metric |

Two things this sample says about words. A multi-shot prompt can name its cuts and get them,
and a quoted line alone does not make the video pass speak: text to audio does, and the track
then drives the sound rather than the mouth.

## The seven LTX-2.5 effects on the q8 packs (2026-10-20)

The port's `ic-lora` task runs these weights on its single-stage path with the distilled
transformer. That path applies the reference at full resolution throughout, which is the
topology each card names. The default two-stage path applies the reference at half resolution
and drops it in stage 2, so it erases the change and tiles the frame.

An effect renders at the size and length its card trained at. Clean plate at 384 x 384 kept
the crowd; at 1024 x 576 and 49 frames it emptied the street. Each adapter carries its own
`width`, `height` and `num_frames`, and the controller and the form use them.

| Effect | Measured output | Verdict |
| --- | --- | --- |
| Day to night | 768 x 448, 97 | A daylight room becomes night: blue moonlight, lit windows, the dancer and the room held. 273.3 s through the API |
| Water simulation | 1280 x 704, 97 | A dry room floods: water across the floor and a splash at the feet. 958.8 s through the API. At 960 x 544 the same prompt added no water |
| Clean plate | 1024 x 576, 49 | Pedestrians gone, street rebuilt, light held |
| Deblur | 960 x 544, 121 | A soft clip comes back sharp, faces and flame detail hold |
| Decompression | 960 x 544, 121 | Edges clean from a crushed clip; colour unchanged |
| Restore | 960 x 544, 97 | Colour and detail return on damaged footage, with a warm cast |
| Upscale 2x | twice the clip | 384 to 768, faces, hands and the floor planks at 1:1. 399.1 s through the API |

The times are the studio's own run on the M5 Pro, with no other GPU job on the
machine: one clip, seed 7, one effect per request through `/api/v1/videos/edit`.

Water's card asks for 1920 x 1088. On the M5 Pro with 64 GB, that single-stage edit fails with insufficient Metal memory during reference encoding. The `--upsample-only` alternative writes a clip, but its frames contain dense noise and tiles. Neither run validates water at that size. Water stays at the measured 1280 x 704 pair.

The form offers 1920 x 1088 for generation. That does not validate edits at the same size. Deblur and decompression were trained at 960 x 544. Their cards name 1920 x 1088 for production, but only the trained pair has a valid measured result here.

With `fetch_loras = true`, the current runner fetched Deblur into an empty directory through `/api/v1/videos/edit`. The downloaded file matches the existing verified adapter byte for byte. Cancel returned 204, the edit returned `{"cancelled": true}`, and the engine child exited in 0.163 seconds. A separate server check confirms that Cancel stops a stalled download and releases the shared run lock.

Portrait checks use `/api/v1/videos/edit` on the M5 Pro with 64 GB, seed 7. Each check compares its first, middle and last frames with the input.

| Effect | Portrait output | Seconds | Visual result |
| --- | --- | --- | --- |
| Day to night | 448 x 768, 97 frames | 338.0 | Blue window light and darker walls replace daylight; the dancer and framing remain |
| Deblur | 544 x 960, 121 frames | 850.9 | The softened face, clothing edges and floor regain detail; the shot remains |
| Clean plate | 576 x 1024, 49 frames | 324.5 | The dancer disappears; the room, window light and floor remain |
| Decompression | 544 x 960, 121 frames | 544.0 | Blocks disappear from the damaged input; the face, hands and floor regain detail |
| Restore | 544 x 960, 97 frames | 633.1 | Noise falls and edges sharpen, but colour restoration is weak: the shot stays mostly grey, with pink hands |
| Upscale 2x | 768 x 1280, 121 frames | 986.1 | A 384 x 640 input gains sharper edges and floor detail at twice its width and height |
| Water simulation | 704 x 1280, 97 frames | 1376.9 | The dry floor floods, with standing water and splashes around the dancer's feet |

The day-to-night card asks 768 x 448 and 97 frames, which is what ships. Its first MLX run
looked like a failure because the test clip was already a torch-lit night street. On a
daylight clip the adapter relights.

The port's README still says 2.5 IC-LoRA is unsupported. That line predates Lightricks
publishing these adapters. The pipeline runs the topology the cards specify, and the runs
above are the evidence.

**Dub-It.** The 2.3 Dub-It LoRA works on the PyTorch 2.3 engine: the user judged the
2026-10-20 output perfect. The same LoRA on 2.5 weights loads but copies the reference's mouth
timing rather than retiming it. The MLX port has no Dub-It task; its LipDub entry is
experimental and re-syncs to source audio. Removing the PyTorch engine removed the only Dub-It
path, so Dub is deferred and would need that engine restored.


### LTX-2.5 speech and camera probes (2026-10-20)

Six sequential asynchronous API operations use seed 7, 384 x 384, 121 frames, and 24 fps.
The M5 Pro runs one GPU job at a time. Source digests match before and after every run.

| Probe | Seconds | Verdict |
| --- | --- | --- |
| Generated speech | 52.5 | Speech recognition returns the exact quoted sentence; mouth movement broadly follows the voice |
| Supplied speech | 396.9 | The supplied voice and timing remain; mouth movement broadly follows the voice |
| Fixed composition | 66.6 | Mostly stable, with small background drift |
| Slow push-in | 66.3 | Clear enlargement and foreground parallax |
| Sideways move | 66.9 | Partial: forward movement appears too, and the subject leaves the center |
| Clockwise orbit | 66.5 | Unproven: no clear new side of the object appears |

Only Speak to camera, Fixed composition, and Slow push-in become new LTX-2.5 templates.
LTX-2.3 keeps its existing templates. Tests reproduce the exact measured prompts from the new template fields.
The supplied audio correlates at 0.999686 with the padded input, with zero sample lag at 16 kHz mono.
This proves audio preservation, not exact lip alignment. No phoneme alignment score was measured.
Each prompt has one seed, so these results do not establish reliability across seeds.
