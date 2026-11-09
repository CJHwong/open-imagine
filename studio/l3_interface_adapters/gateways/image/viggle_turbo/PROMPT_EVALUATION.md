### The Viggle Turbo test

Viggle Turbo samples Qwen-Image-2.1 on a distilled six-step schedule, so the aids
were sampled again on that schedule rather than inherited. Measured 2026-10-05 on
the M5 Pro, six steps, seed 1234, 768 x 768, bf16, the adapter unmerged.

The fixture was "a cat wearing a suit", the one the Look test used. Each option ran
next to the bare prompt, one contact sheet per row. Two rows are about people and a
cat cannot judge them, so Realism and Portrait ran again on "a woman in her thirties
reading at a cafe window", the fixture of the avoid-part test. That is 35 images in
the first run and 4 in the second.

The sheets were lost on 2026-10-06 to a delete glob wider than its folder, and all ten
were rebuilt the same day. Eight came back from this file's own set: the fixtures, seed,
schedule and option names, at 19 to 24 seconds an image, and every verdict below held,
Deep focus included, which still reads as no change in focus at any of its three seeds,
so the cut stands.

The two template sheets came back from the run's own log, which had survived the glob:
it held all 35 prompts, the seven fill-ins, the two sources and the seven instructions,
word for word. Every template verdict held as well. That log was scratch and is gone, so
the fill-ins it carried are not in this repo. A later re-run picks its own, since the
verdict below is about the template working with a sensible fill-in and not about the
words this one used. Two things the log did not carry, and what I did with each: the
size, taken as 768 x 768 except the banner at 16:9, which its own sentence and its
verdict ask for; and which source each edit used, which the verdicts name for six of the
seven and leave open for Add text, so it ran on the woman. The 18 prompts of the rebuilt
row sheets were checked against that log and every one matches the words the sample
itself used.

| Row | Option | Result |
|---|---|---|
| Medium | Documentary | Works: plausible daylight on a carpeted floor, real fur and cloth. |
| Medium | Watercolor | Works: soft washes on textured paper, visible brush edges. |
| Medium | Skeleton | Works: skull, spine, ribs and limb bones in the pose, the suit still on the body. |
| Film | Portra 400 | Works: warm natural color. |
| Film | Black and white | Works: high contrast and strong grain, the Tri-X look its sentence names. |
| Color | Warm | Works: amber and cream, a warm brown suit. |
| Color | Vivid | Works: saturated without going poster flat. |
| Light | Soft window light | Works: a visible window, soft shadow on the left. The shot widens, as it does on the base model. |
| Light | Golden hour | Works: low warm sun from the side, long shadows. Widens the shot. |
| Light | Night with neon | Works: a neon sign, a wet street and its reflections. Widens the shot. |
| Camera | Close-up 85mm | Works: tighter on the head, more blur behind. |
| Camera | Wide 24mm | Works: the room comes back into the frame. |
| Camera | Top-down | Works: a true overhead view. |
| Room for text | Left | Works: the subject on the right third, the left side empty. |
| Room for text | Top | Partly works: the empty band across the top is there, the subject stays near the centre. The same weakness the base model shows. |
| Realism | Real person | Works on the person fixture, and without its avoid part: messy hair, a plain cardigan, unretouched skin. This backend declares no negative prompt, so the avoid part cannot be sent, and the sentence alone carried it. |
| Portrait | Over the shoulder | Works: the person turns three-quarters away, one side of the face in shadow. |
| Portrait | Candid glance | Works: the gaze off camera, a small smile, unposed. |

| Mode | Template | Result |
|---|---|---|
| Generate | Portrait photo | Works: every slot followed, the window light and the blurred background included. |
| Generate | Product shot | Works: the teapot, the props, the empty side. |
| Generate | Landscape | Works: the path leads the eye, the light is dawn. |
| Generate | Poster with text | Works: the title 山茶小館 came out exact and Traditional, with the second line and the small line below it. |
| Generate | Illustration | Works: washes, the named palette, the fox asleep on the log. |
| Generate | Deadpan absurdity | Works: a horse at the water cooler, and nobody reacts. |
| Generate | Banner | Works: a clean 16:9 thumbnail, all three quoted lines exact, the layout as briefed. |
| Edit | Change a color or material | Works: the chair turned deep matte blue, the floor and the light untouched. |
| Edit | Replace the background | Works: a snowy night street, the woman and her umbrella unchanged. |
| Edit | Add text | Works: "Studio 4" exact, on a sign at the top left. |
| Edit | Alternate reality | Works: Earth and stars above the buildings, the pose and the light preserved. |
| Edit | Add an object | Works: a dog beside the woman, with a shadow and floor contact. |
| Edit | Turn into a skeleton | Works, and better on a person than on the base model: the head came back a bare skull. On qwen21 the person keeps her face and hair. |
| Edit | Turn into a pose figure | Works on the body: a grey jointed figure with a ball joint at every joint. The head keeps the real face and hair, the limit the base model has too. |

#### The edit rows, measured 2026-10-10

The 15 edit options ran on this schedule: six steps, which is the only one its distillation samples, no guidance and no negative prompt because it was trained without CFG, one seed, 768 on the short side, each option beside the bare fixture. The fixtures are the base model's own, regenerated at the same seed, prompts and settings, so the pictures are the same and only the editing model differs from the table above. Each sample went through the page's own path: the adapter unmerged, and the viggle schedule supplied for the length of the edit call, which is what `ViggleTurboBackendGateway` does. A Retouch option's sentence carries the mark's token, so it was sent with the token replaced by the number of the image holding the mask, which is what the page does.

| Row | Option | Verdict | What the panel showed |
|---|---|---|---|
| Exposure | Brighter | Kept | Clearly brighter, the pale walls and the shopfronts keep their texture |
| Exposure | Darker | Kept | Clear darkening, the shadow side goes moody |
| White balance | Cooler | Kept | Cool in the shopfronts and on the paving, the jacket stays yellow |
| White balance | Warmer | Kept | Strong and clean, the left wall goes golden |
| Grade | Teal and orange | Kept | Strong, teal in the street, warm on the wall |
| Grade | Muted filmic | Kept | Soft contrast, greyer paving, a gentle fade |
| Lens | Shallow depth | Kept | Convincing, the subject sharp against a heavy bokeh |
| Lens | Wider view | Kept | Wider, and the camera moves with it: the subject smaller and further off |
| Lens | Telephoto | Kept | The subject closer, the frame tighter |
| Finish | Film grain | Kept | A fine speckle over the frame at 1:1, less colored than the base model's |
| Finish | Vignette | Kept | The corners fall off gradually, with no visible circle |
| Finish | Halation | Kept | A warm bloom on the bright edges |
| Retouch | Smooth the skin | Kept | The skin reads retouched, the pores kept |
| Retouch | Brighten the eyes | Kept | The whites brighter and the iris richer: the overreach the base model shows too |
| Retouch | Clear a blemish | Kept | The freckles cleared, and well past the mark: see below |

Fifteen of 15 landed, so this backend offers the whole catalog and not a subset. That is the opposite of its generate sample, which dropped Deep focus and kept 30 of 31 options. Nothing was reworded for this schedule.

**The mark still does not bound a retouch.** The blemish sample marked a patch of cheek 62 px wide at 768, and the freckles cleared across the whole cheek, including well outside the mark. That is the same finding the base model's table records, so a Retouch pick on six steps changes the area its sentence names rather than the area the mark covers.

**What this sample does not settle.** One seed per option, the bar the generate rows were held to and no more. Six steps is the only schedule this distillation runs, so there is no second step count to compare against, and whether these sentences would hold at another count is not a question this model can be asked. The two fixtures are one portrait and one street, so the exposure, white balance and grade verdicts are statements about those scenes. The Retouch sentences were measured at one mark shape each, drawn by a script, and not by a hand with the brush. The timings were 10 to 23 s an image at 768 x 512 and 29 to 37 s at 768 x 768, on the M5 Pro, with nothing else on the GPU.

#### The options the first pass left out, measured 2026-10-06

Thirteen options were missing from the sample above, so they ran on the same fixture,
the same seed and the same schedule, each beside the bare prompt. Twelve did what their
sentence says and one did not.

| Row | Option | Result |
|---|---|---|
| Medium | Phone snapshot | Works: a candid phone photo, plainer light and framing. |
| Medium | Ink drawing | Works: black linework and cross-hatching on white paper. |
| Medium | 3D render | Works: a smooth rounded character under soft studio light. |
| Film | Fuji 400H | Works: cool soft pastels and fine grain. |
| Film | Ektachrome | Works: high contrast, vivid color, deep clean shadows. |
| Color | Cool | Works: a blue and grey palette. |
| Color | Muted | Works: desaturated greys. |
| Light | Studio | Works: even light on a plain backdrop, with no light stand in the picture. The base model needed its wording rewritten for exactly that. |
| Light | Overcast | Works: soft diffuse light, gentle shadows. |
| Camera | Low angle | Works: the subject looms and the view looks up at it. |
| Camera | Telephoto | Works: shot from a distance, the background compressed. |
| Room for text | Right | Works: the subject on the left third, the right side empty. |
| Camera | Deep focus | Cut, on three seeds. At seed 1234 it changed nothing visible. At 5678 and 9012 it changed the picture, but not in the direction the sentence names: the framing pulled tighter and the background became a readable textured surface rather than a sharp version of the same shot. No seed read as an even f/11 focus. The base model kept it at "a little crisper" at best, so it is weak on both. |

So one option is out and this backend offers the other 30.

#### What this sample does not settle

One seed and one fixture per row, except deep focus, which was run at three seeds because
one image is thin ground for dropping an option. The distilled schedule has no other step
count, so there is nothing to compare a six-step result against, and no option was run
twice otherwise.

An avoid part cannot be tested on this backend, because it declares no negative prompt
and the page sends none. Real person keeps its avoid part in the shared wording, where a
mode with a negative prompt would send it.

#### The cost, re-measured 2026-10-06

The generate cost was checked twice on 2026-10-06, and both checks were wrong. The first,
at about 01:00, read 8.0s, 27.8s and 68.7s, and the constant in
`gateways/image/viggle_turbo/capabilities.py` was replaced on that evidence. The Look sample above
ran at about 21s an image at 768 x 768 on 2026-10-05, which agreed with it.

Measured again on 2026-10-06 at 11:25, GPU free, one job at a time, two passes of six
steps each at seed 1234 on the cat fixture:

| Tier | The two runs | Mean | The pair in the file predicts |
|---|---|---|---|
| 0.26 MP | 4.9, 6.1 | 5.5 | 5.4s |
| 0.59 MP | 10.3, 9.9 | 10.1 | 11.4s |
| 1.05 MP | 23.9, 23.5 | 23.7 | 23.4s |

The pair in the file is the base model's, and it stands: 13% high at the middle tier and
within 2% at the other two. Six runs with this spread do not improve on it.

A busy machine was the explanation for the 8.0, 27.8 and 68.7 check, and the machine is
not that simple. Thirty-six of the same runs at 1024 x 1024, back to back at 11:33, took
between 20.0s and 51.6s, median 30.7s. The first 27 averaged 33.7s and the last 9
averaged 21.4s, which is the figure above again. The load average recorded beside each
run correlates with the time at 0.56: the two highest loads gave the two slowest runs,
and one run took 45.2s at load 1.71. So most of the spread is inside the machine, and I
did not instrument which part of it.

What that means for the constant: the idle figure is the one to ship, because the page
shows the estimate before a run and learns this device's own rate from the run itself,
so a machine at the slow end corrects the page within one run. The check that recorded
8.0, 27.8 and 68.7 read that slow end as the machine's speed, which would have promised
about three times the time an idle machine gives.

The edit half needed no change, and it is now measured rather than inherited: its 19.3s
at 0.59 MP was reproduced at 20.2s and 26.3s against a pair that predicts 24.0s.

One process drawing many prompts also grows, and the sample above is where that showed.
Across fourteen of its images the MLX active memory read 16.9 GB, then 30.6 GB, then
33.7 GB, while its peak reached 64.4 GB on a 64 GB machine.

The cause is not a cache. mflux's MemorySaver drops the text encoder before every
denoising loop, and a prompt that is not already in the model's cache needs it back.
Studio's only way back is to drop the whole model and rebuild it, which re-applies the
LoRA, and the frame that asked for the rebuild still named the old model. So the rebuild
built a second copy of the weights while the first was live. Measured 2026-10-06 on three
prompts at 768 x 768 in one process, the peak read 16.9 + 30.7 = 47.6 GB, and the active
memory climbed for the same reason, because each rebuild leaves a set behind.

Dropping that name before the release lets the old set go first. Measured the same way
with one line changed: the peak reads 30.7 GB, the weights alone, and the active memory
holds at 16.9 GB across the three instead of climbing to 32.2 GB. That is the difference
between fitting on a 64 GB machine and reaching its ceiling, which is why the first
attempt at this sample died at image 21 with no traceback. A later death was a plain
Python error, so the two were not the same event.

The time follows the same line. Four separate processes alternating the two arms put the
changed one ahead in both pairs, 16.1 seconds an image against 18.5 and 19.6 against
21.5, but their means rose in run order, so the machine's drift over those six minutes
was as large as the effect. Alternating the two inside one process controls it, and with
the order reversed in half the pairs so the drift lands on both arms in turn: twelve
images, 14.8 seconds an image against 21.5, and all six pairs reading the same way, by
6.6, 5.5, 10.6, 6.9, 5.3 and 5.3 seconds. So the rebuild over a live copy was costing a
third of the time of every image with a new prompt, not only the memory it doubled.

#### What a cancelled rewrite gives back, measured 2026-10-06

The cancel frees the rewriter, and MLX reports its own memory, so the free is read
rather than inferred. Active memory is the live tensors.

| Moment | Active | Cache | Peak |
|---|---|---|---|
| The rewriter resident and writing | 31.58 GB | 0.00 GB | 31.58 GB |
| Stopped, model still in hand | 31.58 GB | 0.17 GB | 33.27 GB |
| After the free | 14.05 GB | 0.00 GB | 33.27 GB |

So the free gives back **17.53 GB**. The 14.05 GB the last row starts from is that
script's own earlier image-engine phase, so the delta belongs to the rewriter. The peak
never falls, which is what a peak is.

#### Several pictures at once, measured 2026-10-12

The page's note claimed that the rewriter reads the pictures, so its answer names the one
it read. Four pictures of four different subjects were put to it: a golden retriever, a
black cat, a grey rabbit and a red parrot, each generated on the M5 Pro at the
first tier size the form offers, eight steps. The same words go with them both ways:
"make it a chihuahua sitting in a dog bed".

| What was asked | What came back |
|---|---|
| all four pictures in one call | one paragraph of 1588 characters, about one of the four. Its first sentence places "the golden retriever from `<image1>`", and the other three are named nowhere |
| one picture per call | four answers of four, 643 to 1950 characters, and each names its own subject: the golden retriever, the black cat, the grey rabbit, the red parrot |

The single calls took 14, 16, 24 and 30 seconds, and the one call over the four took 49: the
other three are encoded and attended to and then left out of the answer.

So one picture is what the rewriter can be asked about, and a run of several pictures that
takes one instruction for all of them is pulled toward whichever one the answer names. The
page gives the rewriter one picture at a time for a batch, and each answer lands in that
image's own row.

Asked one picture at a time, the rewriter keeps its own reading of the words. In a later run
of four, with "make it a chihuahua sitting in a dog bed" and one picture per call, three of the
four answers carried the transformation: one turned the parrot's plumage into the chihuahua's
own coat, as its own instruction asked. The fourth left its subject alone. Given the black cat,
the answer was to keep the cat completely unchanged and set it in a bed, so the result is a cat
in a bed and not the change the words asked for. A press is one model's reading, and the row
it lands in is the user's to correct.

What this does not settle: one sample, one seed and one instruction, and the answer's own
quality is not read here. The subject each answer names is found by looking for that
subject's own words in it, which is a reader and not a judgement.
