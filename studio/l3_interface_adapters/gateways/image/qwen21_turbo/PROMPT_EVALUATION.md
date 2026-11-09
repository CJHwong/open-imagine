### The official Turbo test

The official Turbo checkpoint samples its own eight-node sigma table, so the aids
were sampled on that schedule rather than inherited. Measured 2026-10-16 on the
M5 Pro, eight steps on that table, seed 1234, 768 x 768, bf16.

The fixture was "a cat wearing a suit", the one the Look test used. Each option ran
next to the bare prompt, one contact sheet per row. Two rows are about people and a
cat cannot judge them, so Realism and Portrait ran again on "a woman in her thirties
reading at a cafe window", the fixture of the avoid-part test. Every prompt went
through the page's own composition: the option's sentence after the user's text,
closed with a full stop, and an avoid part sent as the negative prompt, which is what
raises the scale to 2.5 and turns true CFG on.

The sample covered every aid this backend offers: 31 generate options, the 15 edit
options, and all 15 templates, in 61 runs of the image plus their bare controls.

| Row | Option | Result |
|---|---|---|
| Medium | Documentary | Works: natural exposure, real fur and cloth |
| Medium | Phone snapshot | Works: flatter light, uneven framing, a room behind |
| Medium | Watercolor | Works: soft washes on textured paper, visible brush edges |
| Medium | Ink drawing | Works: fine black linework and cross-hatching on white |
| Medium | 3D render | Works: smooth rounded shapes, soft studio light |
| Medium | Skeleton | Works: skull, spine, ribs and limb bones in the pose, the suit still on the body |
| Film | Portra 400 | Works: warm natural color |
| Film | Fuji 400H | Works: cool soft pastel tones |
| Film | Ektachrome | Works: high contrast, deep clean shadows |
| Film | Black and white | Works: strong grain and high contrast, the Tri-X look its sentence names |
| Color | Warm | Works: amber and cream, a warm brown suit |
| Color | Cool | Works: blue and teal, a cool grey cat |
| Color | Muted | Works: desaturated |
| Color | Vivid | Works: saturated without going poster flat |
| Light | Soft window light | Works: a visible window, soft shadow on the left. The shot widens, as on the base model |
| Light | Golden hour | Works: low warm sun, long shadows. Widens the shot |
| Light | Studio | Works: even light, a plain seamless backdrop, and no light stand in the picture |
| Light | Overcast | Works: soft diffuse light, gentle shadows |
| Light | Night with neon | Works: a neon sign, a wet street and its reflections. Widens the shot |
| Camera | Close-up 85mm | Works: tighter on the head, more blur behind |
| Camera | Wide 24mm | Works: a bookshelf comes back into the frame |
| Camera | Top-down | Works: a true overhead view |
| Camera | Low angle | Works: looking up at the subject |
| Camera | Telephoto | Works: the subject comes closer and the background compresses |
| Camera | Deep focus | Does not land: identical to the bare fixture, which has no depth in it to recover. The Viggle sample cut this option for the same reason. It ships here anyway, because this backend's catalog is the base model's by design and one option that changes nothing costs a user nothing |
| Room for text | Left | Works: the subject moves right and a plain area opens on the left |
| Room for text | Right | Works: the subject moves left and a plain area opens on the right |
| Room for text | Top | Works: the subject drops and a wide plain area opens across the top |
| Realism | Real person | Works on the woman fixture, with its avoid part at guidance 2.5: a plain, candid person rather than a posed beauty portrait |
| Portrait | Over the shoulder | Works: the person turns three-quarters, one side of the face in shadow |
| Portrait | Candid glance | Works: caught unposed, gaze slightly off camera |

#### The edit rows

The 15 options ran on this checkpoint's own two fixtures, generated at the seed and
prompts the earlier edit table records: a street at 768 x 512 for the five whole-frame
rows, and a portrait at 768 x 768 for Retouch. Each option ran beside its own fixture,
because for an edit the question is what the sentence changed. A Retouch sentence
carries the mark's token, so it went with the token replaced by the number of the image
holding the mask, and the mask itself was an ellipse in the palette's orange on black
over the face, which is what the page sends.

| Row | Option | Result |
|---|---|---|
| Exposure | Brighter | Works: clearly brighter, the pale walls keep their texture |
| Exposure | Darker | Works: the shadow side goes moody and the highlights stay |
| White balance | Cooler | Works: blue in the shopfronts and on the paving |
| White balance | Warmer | Works: a strong clean golden cast, the composition untouched |
| Grade | Teal and orange | Works: teal in the street, warm on the wall, the jacket stays yellow |
| Grade | Muted filmic | Works: soft contrast, lifted blacks, a warm fade |
| Lens | Shallow depth | Works: the subject sharp against a heavy bright bokeh |
| Lens | Wider view | Works: more of the street in frame, the subject further off |
| Lens | Telephoto | Works: the subject closer, the frame tighter, the background softer |
| Finish | Film grain | Works: visible grain across the frame |
| Finish | Vignette | Works: the corners fall off gradually, with no visible circle |
| Finish | Halation | Works: a warm bloom on the bright edges |
| Retouch | Smooth the skin | Works: the face reads retouched, the hair and sweater untouched |
| Retouch | Brighten the eyes | Works: the eyes open up and read brighter |
| Retouch | Clear a blemish | Works: the skin clears. The mark does not bound it, as the region table below and the base model's own note both record |

#### The templates

Each template ran with its first fill-in, and the two that ask for lettering were
judged on the lettering.

| Template | Result |
|---|---|
| Portrait photo | Works: every slot followed, light from the left, 85mm, a plain blurred background |
| Product shot | Works: the mug, the oak table, the napkin, the window light, space on the right |
| Landscape | Works: the fjord, the red boathouse, the gravel path leading the eye |
| Poster with text | Works: "Midnight Sessions", "Friday, doors at eight" and "The Old Ship, Hackney" all exact |
| Illustration | Works: gouache, the fox on the right third, the palette named |
| Deadpan absurdity | Works: a horse waiting by the launderette machines while the people carry on |
| Banner | Works: "BUILD FASTER" and "Ship every Friday" exact, the badge reads "New", 16:9 |
| Change a color or material | Works: the oilskin jacket goes deep red and matte, the same cut, seams and pockets |
| Replace the background | Works: the woman in a sunlit kitchen with a kettle and a window box |
| Add text | Works: a "Bakery" sign above the shopfront, dark green painted serif, legible |
| Alternate reality | Works: the same street in 1920, a horse cart and gas lamps |
| Add an object | Works: the dog on the cobbles with its shadow, the man glancing down and smiling |
| Turn into a skeleton | Works: the woman's bones reading a book, in her pose |
| Turn into a pose figure | Works: a jointed grey figure in the same pose |
| Mark a region | Works, subtly: the eyes read slightly brighter than the bare portrait and it is hard to separate the two by eye at this size |

**What this sample does not settle.** One seed per option, the bar the generate rows
were held to and no more; an option that failed here can still be re-run on a second
seed. The two fixtures are one cat and one woman, so the exposure, white balance and
grade verdicts are statements about those scenes and not about the words in general.
The Retouch and Mark a region sentences were measured at one mark shape each, drawn by
a script. Deep focus is the only option this schedule did not reward; the Viggle sample
cut it and this one keeps it, for the reason its row above gives. The mark's containment
on this checkpoint is measured separately, in "The same metric on three scenes" below.
