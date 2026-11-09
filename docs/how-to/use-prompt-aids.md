# Prompts

The templates and the Look were written and tested on Qwen-Image-2.1. FLUX.2 offers the part that passed its own test, in [The flux2 test](../../studio/l3_interface_adapters/gateways/image/flux2/PROMPT_EVALUATION.md#the-flux2-test).

Qwen-Image-2.1 makes a good image from a short prompt. A longer prompt does not make it better. It gives you control over what you get. The templates below give that control with the least typing.

In the page, open **Templates** above the prompt. Pick one, then press Tab to jump from one `[placeholder]` to the next. The run button stays off until no `[bracket]` is left.

## Template language

Templates follow the page language: English or Traditional Chinese. Their prompt text, fillable
placeholders, and Voice field labels and defaults use that language. Templates without a translation
fall back to English. The language changes the instructions; it does not add language support to a model.
Engine tags such as `[whispers]` and the marked-region token keep their original spelling.

API clients select `template_locale` while keeping canonical template names, field keys and choice
values. Model integrations attach `TemplateTranslation` records to their templates; each model family
owns its translated prompt data. See [API.md](../../API.md#prompt-aids-and-reference-inputs).

## What works

- **Name what you can see.** Use concrete nouns, named colors and materials, and the clothing. "A yellow oilskin jacket" lands. "Weathered" only partly lands.
- **Say where the light comes from.** "Soft light from the left, cool shadows" steers the image more than any quality word.
- **Give the camera.** A lens and a viewpoint, such as "85mm at f/1.8" or "shot from a high rim looking down", fix the framing.
- **Place things in the frame.** "Empty space on the left" and "subject on the right third" are followed.
- **Name the mood you want.** Mood words steer hard. "Minimal, neutral, catalog" gives a flat, plain image. Use it only when you want that.
- **Put text in double quotes.** Then say where the text goes and how big it is, and end with "no other text". This works in Traditional Chinese and English. Text without quotes gets misspelled, and fake glyphs appear around it.
- **Check Chinese titles in a hand-lettered style.** In one test, 麥田烘焙 came out with the Simplified 麦. The same poster's small printed 盛大開幕 was correct. If a glyph drifts, try a printed style or another seed.
- **Expect small details to drop.** A small prop far from the subject, such as a kayak on a river, may not appear. Put what matters near the subject or make it bigger.

## What to leave out

- **Quality suffixes** such as "Ultra HD, 4K, cinematic composition". They do not add quality. They make the image darker and more dramatic, and they change the framing.
- **A negative prompt.** It needs guidance above 1, which doubles the time per step. In the test, it gave little or no visible gain. The one exception is the Realism avoid part: see "The avoid-part test".

## Look

In the page, **Look** adds one sentence after your prompt when you press Generate. The prompt field keeps your own text. Pick at most one option per row.

| Row | Options | What it adds |
|---|---|---|
| Medium | Documentary, Phone snapshot, Watercolor, Ink drawing, 3D render, Skeleton (qwen21 only) | A camera habit, or a drawn or rendered style |
| Film | Portra 400, Fuji 400H, Ektachrome, Black and white | A film stock and its color |
| Color | Warm, Cool, Muted, Vivid | A palette |
| Light | Soft window light, Golden hour, Studio, Overcast, Night with neon | Where the light comes from and how hard it is |
| Camera | Close-up 85mm, Wide 24mm, Top-down, Low angle, Telephoto, Deep focus | A lens and a viewpoint |
| Room for text | Left, Right, Top | Where the subject sits, and which side stays empty |
| Realism | Real person | An everyday, unretouched person, plus an avoid part for the negative prompt |
| Portrait | Over the shoulder, Candid glance | A pose and a gaze |

The rows go from the style (Medium, Film, Color) to the shot (Light, Camera, Room for text) to the subject (Realism, Portrait). Every film stock sits in the Film row, so one pick per row keeps two stocks from fighting. Portra 400 was "Film photo" in Medium, and Black and white was in Color; their sentences did not change.

Each option names what to show, never what to leave out. The exception is Real person: its avoid part goes to the negative prompt, which raises guidance to 2.5 and doubles the time of each image. Realism fights Watercolor, Ink drawing, 3D render and Skeleton, because its avoid part names CGI and 3D render. Real person is for people. For an animal, Documentary is enough: see "The avoid-part test". These are the rows for a run that draws. The edit form has its own rows, below, and the reason the earlier note said it had none was the style rows, which the edit model does not draw: it keeps the rest of the picture.

## Edit Look

The edit form offers its own **Look**, and a pick adds one sentence after your instruction. These rows are separate from the generate ones because the edit model keeps the rest of the picture by itself: an option here is either a change to the whole frame or a change to the area you marked. Every option passed a test on Qwen-Image-2.1 on 2026-10-10, one seed, 20 steps, 768 on the short side, each one beside the bare fixture: see "The edit Look test". Viggle Turbo offers the same 15, because its own six steps kept them all: see "The edit rows, measured 2026-10-10". The official Turbo checkpoint offers them as well, on its own eight-node table: see "The official Turbo test". FLUX.2 offers no edit rows yet, because it has not been sampled on its own.

| Row | Options | What it adds |
|---|---|---|
| Exposure | Brighter, Darker | The exposure of the whole frame |
| White balance | Cooler, Warmer | The color of the light, not the palette |
| Grade | Teal and orange, Muted filmic | A color grade |
| Lens | Shallow depth, Wider view, Telephoto | A lens, and with it the framing |
| Finish | Film grain, Vignette, Halation | A film finish over the frame |
| Retouch | Smooth the skin, Brighten the eyes, Clear a blemish | Skin and eyes, and the area you mark is what they change |

**Retouch** is the one row that wants a mark. Its sentences carry the page's own token for the region, `[the region you marked]`, and the page puts the number of the image holding the mask where that token stands: "Smooth the skin on the face, keeping the pores and the natural texture visible in the area marked in <image2>. Keep the background and everything else unchanged." That is the sentence the Retouch row was measured with, character for character. A pick that wants a mark and has none blocks the run and asks for one, the same way the "Mark a region" template does. The other five rows carry no token, so a mark does not scope them: a grade, an exposure or a film finish applies to the whole frame whether a region is drawn or not, and the sentence says what it does.

## Generate templates

**Portrait photo**

```
Close-up portrait photograph of [who: age, hair, look] in [place], at [time of day]. Wearing [clothing and colors], [pose or gaze], [expression]. [Light: direction and quality], [background, softly blurred]. 85mm lens at f/1.8, shallow depth of field, natural skin texture, [color mood].
```

**Product shot**

```
Product photograph of [product: material, color, finish] on [surface] in [setting]. [Light: direction and quality], [one or two props] beside it. [Angle, e.g. three-quarter view at eye level], 85mm lens, empty space on the [side], [mood] mood.
```

**Landscape**

```
Wide photograph of [place] with [landmark] at [time of day and weather]. [A path, road or river] leads the eye from [where] toward [where]. [Sky and light]. Shot from [viewpoint], 24mm lens, deep focus, [detail] in the foreground, no text.
```

**Poster with text**

```
Minimalist poster for [what]. At the top, a [lettering style] title "[title text]" in [color], with "[second line]" below it in [typeface style]. In the center, [main image]. At the bottom, the text "[small text]" in small [color] letters. [Background], generous empty space, centered layout, no other text.
```

**Illustration**

```
[Medium, e.g. watercolor] illustration of [subject doing what] in [setting]. Palette of [3 or 4 colors], [line or brush quality], [light]. [Where the subject sits in the frame], [mood] mood, no text.
```

**Deadpan absurdity** (qwen21 only)

```
A realistic candid photograph of a completely ordinary [place] on [a weekday and time], except [one absurd thing] is calmly [doing what] beside [where]. The people carry on as if nothing unusual is happening. [3 or 4 everyday details], [ordinary light]. Shot with a 28mm lens at eye level, natural perspective, documentary photojournalism.
```

**Banner** (qwen21 only)

```
A 16:9 [kind, e.g. video thumbnail or ad banner] on [background and colors]. [Person or product: who, clothing, pose] on the [side]. On the [other side], huge [color] [letter style, e.g. extra-bold gothic] text reads "[headline]", and below it, smaller text reads "[second line]". [A button, badge or band] reads "[short label]". [Mood].
```

Keep each line short, and check every character. One dropped or swapped kanji is common, most often in the smaller lines. A batch of several seeds gives you a clean one to pick.

## Edit templates

The edit model keeps the rest of the image by itself. The prompt only has to name the exact target and the exact result.

**Change a color or material**

```
Change only the [object]'s [color or material] to [new color and finish], keeping its [shape, texture, details]. Do not change the background, the lighting or the camera angle.
```

**Replace the background**

```
Replace only the background with [new place, time, weather, 2 or 3 details]. Keep the [subject]'s face, expression, clothing, pose and framing exactly as they are, and match the light on the [subject] to the new scene.
```

**Add text**

```
Add [a sign, label or banner] at [position] with the text "[exact text]" in [color, letter style, size], spelled exactly. Match the scene's lighting and perspective, and keep everything else unchanged.
```

**Alternate reality** (qwen21 only)

```
Keep the camera position, the composition, the people and their poses exactly unchanged. Change only [which part of the world]: [the new reality, with 1 or 2 visible details]. Preserve the lighting, the lens and the photographic texture.
```

**Add an object** (qwen21 only)

```
Add [object or animal] [where, and how it touches the scene], [one person reacting to it]. Give it correct scale, shadows and floor contact. Do not change [what must stay], the lighting or the camera position.
```

**Turn into a skeleton** (qwen21 only)

```
Turn the [subject] into its 3D anatomical skeleton in exactly the same pose, position and camera angle: every bone in its true place and number, ivory bone. Replace the background with a plain dark studio backdrop and soft museum lighting.
```

**Turn into a pose figure** (qwen21 only)

```
Turn the [subject] into a 3D pose mannequin in exactly the same pose, position and camera angle: a smooth gray jointed figure with a ball joint at every joint, matching its body proportions. Replace the background with a plain light gray backdrop and even studio light.
```

On a person, both keep the face and hair. See "The skeleton test".

## Video templates

The four older video templates were sampled on 2026-10-17 and 2026-10-18. Their verdicts sit in the comment above `VIDEO_TEMPLATES` in `prompt_aids.py`, next to the template text.

Three more were added on 2026-10-19, from the vendor's 2.5 prompt guide, its native-audio guide, and its audio-driven guide. The shape is theirs; the text is not, and every slot stays a bracket.

| Template | Result |
|---|---|
| Multi-shot | Works. Two hard cuts read at frames 38 and 82 against a 0.27 median frame difference, 28.6 and 16.9 at the cuts. The sheet shows the wide wash, the hood close-up and the doorway wide, in the order the prompt names. |
| Dialogue | Works as a shot. One continuous two-shot of two men at a kitchen table, no cuts (max difference 1.76). The audio is 54 percent speech band with a 2 Hz envelope and a 118 Hz fundamental. The words were not transcribed, so line accuracy is unproven here; the vendor's own samples are the evidence for that. |
| Soundscape | Works. One continuous medium shot of a woman sanding a board, no cuts. The audio envelope follows the hand motion at r 0.56 with a 0.6 Hz modulation, and no musical score dominates its strongest bins. |

Each ran once at 384 x 384, 121 frames, seed 7, with a filled-in prompt and no reference image, through the studio's own endpoint and the distilled pipeline. A filled-in prompt is not the template; it is one reading of it.

## Video Look

The video Look appends one sentence after the prompt, so its options can only name what composes with any prompt: light, weather, palette and the mix. Camera moves and shot scales stay in the templates, where a prompt that already names one cannot fight the appended text.

Each option ran once against one bare control clip on 2026-10-19, at 384 x 384, 121 frames, seed 7, through the studio's endpoint and the distilled pipeline. The control prompt was a woman walking along an empty stone street. The Mix options needed a second scene, because that control carried no score to remove: they ran against a city-at-dusk control that did.

| Row | Option | Result |
|---|---|---|
| Light | Golden hour | Works. Warm low sun and long shadows. Luminance 120.4 to 82.3, red minus blue -0.2 to +30.4. |
| Light | Soft daylight | Works. Natural, soft light with no hard shadows. Luminance 105.9, red minus blue +17.3. |
| Light | Neon night | Works. A dark street with lit shop signs and coloured reflections. Luminance 52.9. |
| Atmosphere | Wet street | Works as wetness. The stone turns wet, darker and reflective, luminance 120.4 to 89.1. Falling drops did not read at 384 x 384, so the row is named for what the clip shows. |
| Atmosphere | Fog | Works. Thick fog, the far end of the street softened. |
| Grade | Warm | Works. Amber cast, red minus blue +151.7 against -0.2. |
| Grade | Cool | Works. Teal cast, red minus blue -66.8. |
| Mix | No music | Works on a scene that invites a score. The control carried tones at 350, 263 and 522 Hz with 7.4 envelope crossings a second; with "no music" the clip was 33 times quieter, with no tonal peak above 0.8 percent. |
| Mix | Ambient only | Cut. On a scene the model had already left unscored it produced a 524 Hz hum, so it changes nothing for the better. |
