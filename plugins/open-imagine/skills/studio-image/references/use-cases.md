# Use cases

Find the brief's kind of image here, then read the file the row names. The ratio is a default;
follow the user's format when it gives one, and crop or resize to a platform's pixels afterwards
(see [delivery](delivery.md)).

- **Rewrite** says whether the studio's Rewrite helped on Qwen-Image-2.1-Turbo: **yes**, **no**,
  **either** (a tie), or blank when untested. See [prompt craft](prompt-craft.md).
- **Accuracy** is the accuracy level from SKILL.md: **Mood** (mood only), **Rough** (roughly right,
  a human checks it), **Exact** (must be exact: draw it with a tool; the model only decorates).
- **Status**: "Tested" means one or more images on Qwen-Image-2.1-Turbo were inspected for that
  row, and the note gives what failed. "Guidance" means the row comes from practitioner research and
  was not tested here; run a concept before you rely on it.

## Text and layout

Read [design and text](design-and-text.md).

| Kind of image | Ratio | Rewrite | Accuracy | The prompt must carry | Status |
|---|---|---|---|---|---|
| Poster, flyer, event | 3:4 | either | Mood | Title, date and venue quoted with their place; one hero image; "No other text." | Tested |
| Book, album or magazine cover | 3:4 (album 1:1) | either | Mood | Title and author quoted, or plain space where a layout tool sets the masthead; one focal image; genre palette | Tested |
| Invitation, greeting card, save-the-date | 3:4 | yes | Mood | Each text block quoted in order; border or ornament; paper. Long addresses go in a layout tool | Tested |
| Menu, certificate | 3:4 or 4:3 | | Mood | Every line quoted with its price or role; few lines. Check for a repeated label ("Instructor" came out twice). Use a fictional issuer unless it is the user's | Tested |
| Business card face | 4:3 | | Mood | Flat front view; name, title and up to three contact lines quoted; logo zone | Tested |
| Quote or testimonial card | 1:1 | | Mood | Quote under about 15 words; attribution quoted separately. Check names letter by letter | Tested, a name misspelled |
| Social ad, banner | 1:1, 9:16 or 16:9 | | Mood | Headline and call to action quoted; one hero; brand colors in words | Tested |
| Story or reel cover | 9:16 | | Mood | Headline in the middle third; top band empty. The bottom band fills: pad or crop it afterwards | Tested, bottom band fails |
| Slide background, website hero | 16:9 | | Mood | Name the empty area ("the left half is plain light gray"); no text | Tested |
| Title card | 16:9 | | Mood | The title quoted; centered; texture | Tested |
| Video thumbnail | 16:9 | yes | Mood | A short quoted headline; one expressive face or object | Tested |
| Lettering, text as the image | 1:1 | either | Mood | The exact string; letterform; material (balloon, neon, chrome) | Tested |
| Chinese, Japanese or Korean text | any | either | Mood | An English prompt with the characters quoted; common words; check each character | Tested |
| Vertical Chinese text, 春聯, shop sign | 3:4 | | Mood | "Running top to bottom"; 4 common characters per line. Give a horizontal line no direction; check how it reads | Tested, check banner order |
| Japanese kana, Korean hangul | 3:4 | | Mood | One or two short quoted words in large type. Small lines fail | Tested |
| Logo | 1:1 | no | Mood | Brand name quoted in its case; one idea; 1 to 3 colors; pure white. Trace and retype it for real use | Tested |
| App or web screen | 9:16 or 16:9 | yes | Mood | Platform; sections; every visible string quoted or invented by Rewrite | Tested |
| App icon, favicon | 1:1 | | Mood | One bold glyph; no text. "The color reaches all four edges and corners; sharp square corners". "No rounded corners" draws them; check at 32 px | Tested |
| Infographic, flowchart | 3:4 | no | Rough | Title and every label quoted; each icon described | Tested |
| Chart with data | 4:3 | | Exact | Bar heights are not proportional (about 12% off). Draw the data with code | Tested, not accurate |
| Map, illustrated travel map | 4:3 | yes | Rough | Every place name quoted, 5 or 6 at most; style; route line. Geography is invented; foreign names get misspelled | Tested |
| Technical or science figure | 4:3 | yes | Exact | View (cross-section, exploded); labels quoted. Parts and leader lines are wrong | Tested, not accurate |
| Packaging | 1:1 | yes | Mood | Form and material; all label copy quoted. No dieline | Tested |
| Merchandise mockup | 4:3 | either | Mood | Object, color, print and its placement | Tested |
| Meme | 1:1 | either | Mood | Scene; short caption quoted with its position | Tested |
| 長輩圖, holiday greeting image | 1:1 | | Mood | Short greeting quoted with its color and outline; saturated flowers or festival objects | Tested |
| 紅包, 福 diamond, festival poster | 3:4 or 1:1 | | Mood | One large quoted character or short greeting; red and gold; festival objects named | Tested |
| Seamless pattern, fabric print | 1:1 | no | Mood | Motif, palette, flat top-down; every motif inside the frame with even margins; tile 2 x 2 | Tested, check seams |
| Phone or desktop wallpaper | 9:16 or 16:9 | | Mood | Empty area for the clock or icons; no text | Tested |
| Brand board, mood board, letterhead | 16:9 | | Mood | Panels named; palette in words. Hex codes, font names and body text render as gibberish | Guidance |
| Billboard, out-of-home | 16:9 | | Mood | 3 to 7 words, large, high contrast; one idea. Crop wider ratios afterwards | Guidance |
| Carousel slides | 1:1 or 3:4 | | Mood | One run per slide with the same style paragraph; each headline quoted | Guidance |

## Illustration and characters

Read [illustration and assets](illustration-and-assets.md).

| Kind of image | Ratio | Rewrite | Accuracy | The prompt must carry | Status |
|---|---|---|---|---|---|
| Sticker | 1:1 | either | Mood | "A die-cut sticker of ..." first; bold outline; white border | Tested |
| LINE-style sticker set | 1:1 | | Mood | One sticker per image, the same character paragraph each time; a 2 to 4 character caption "inside the white border, overlapping the bottom". A sheet puts captions outside | Tested |
| Planner (手帳) or sticker sheet | 1:1 | | Mood | Six or fewer named items, each separate, not touching | Tested |
| Icon or emoji set | 1:1 | either | Mood | Grid size; every member named; one style sentence | Tested |
| Avatar, mascot, profile picture | 1:1 | no | Mood | Traits; the rendering method; background color; "facing the camera, centered" first for a circle crop | Tested |
| Character sheet | 16:9 | either | Mood | One fixed character paragraph; "front, side and back views" | Tested |
| Comic, storyboard | 16:9 | yes | Mood | Panel count; one sentence per panel; actions mid-motion | Tested |
| Picture-book spread | 4:3 | either | Mood | Character paragraph; medium; calm area for text | Tested |
| Coloring page, mandala | 3:4 or 1:1 | either | Mood | Black outlines only, no shading, closed shapes; the fold count. Symmetry is close, not exact | Tested |
| Tattoo flash, fine-line tattoo | 3:4 | no | Mood | Tattoo style; line weight; flat fills; paper, no skin; any script word quoted | Tested |
| Isometric diorama | 1:1 | yes | Mood | "Isometric"; material; one light direction | Tested |
| 3D toy or product render | 1:1 | no | Mood | Material (vinyl, clay); whole figure in frame; backdrop | Tested |
| Flashcards | 3:4 | | Mood | One subject per card; the word quoted; the same style paragraph, background and subject size per deck | Tested |
| Classroom poster with a grid | 1:1 | | Mood | Grid size; each cell named. Check each cell ("cat" came out a rabbit-lamb); above 9 cells untested | Tested |

## Games and film

Read [illustration and assets](illustration-and-assets.md).

| Kind of image | Ratio | Rewrite | Accuracy | The prompt must carry | Status |
|---|---|---|---|---|---|
| Card art | 3:4 | | Mood | "Art only, no card frame, no border, no text"; one subject; strong silhouette | Tested |
| Tarot or full card with title | 3:4 | | Mood | Title and numeral quoted; border in words; the card's symbols listed | Tested |
| Game concept art, splash, matte painting | 16:9 | either | Mood | Genre, camera, mood, palette; foreground to background layers | Tested |
| Tabletop battle map | 1:1 | | Mood | "Seen from directly overhead", "no grid lines, no perspective"; features listed. Add the grid in the tabletop software | Tested |
| Token | 1:1 | | Mood | Ring; a flat key color; "filling most of the frame". Expect a front portrait in the ring | Tested |
| Visual-novel sprite | 3:4 | | Mood | Full body, neutral, plain pure white; then expressions and poses by Edit from that one master | Tested |
| Visual-novel background | 16:9 | | Mood | Location, time, no people, no text; other times of day by Edit | Tested |
| Character turnaround | 3:4 | | Rough | A-pose front view on gray; side and back views by Edit, one per image | Tested |
| Skill or spell icons | 1:1 | | Mood | Badge shape repeated; six or fewer named icons, each with its color. The grid drifts | Tested |
| Game sprite sheet | 16:9 | either | Mood | Grid, frame count, view, palette; each frame's pose. Not usable as animation | Tested, frames fail |
| Game item icons, tileset | 1:1 | | Mood | Every item named as one object. Counts drift (8 asked, 9 drawn); tile edges do not connect | Tested, concept only |
| Tileable texture | 1:1 | | Mood | Top-down, even light, no shadow, no vignette, uniform scale. Seams show: tile 2 x 2, then heal | Tested, seams show |
| 360 panorama, skybox, normal map | | | Exact | Not supported: no 2:1 size, no projection, no normal encoding. A 16:9 wrap-around strip is possible | Tested, fails |
| Film keyframe | 16:9 | | Mood | Shot size, lens, light, grade. Crop to 2.39:1 afterwards | Guidance |
| Film poster with billing | 2:3 or 3:4 | | Mood | Title and tagline quoted; the billing block goes in a layout tool | Guidance |
| Cinematic style, film still | 16:9 | | Mood | The director's camera, staging, light and palette in words; a name alone adds nothing. Count the people; the subject before the motif | Tested |

## Anime and animation

Read [style directions](style-directions.md) and [illustration and assets](illustration-and-assets.md).

| Kind of image | Ratio | Rewrite | Accuracy | The prompt must carry | Status |
|---|---|---|---|---|---|
| Anime scene, key visual | 16:9 | no | Mood | The method ("clean line art, flat cel shading with hard-edged shadow shapes, a hand-painted background"), not only "anime style"; the era if it matters; every sign quoted | Tested |
| Anime cast, recurring character | 16:9 | no | Mood | One full character paragraph, re-sent each time; for a group, one trait and one prop per person. New expressions and outfits by Edit. Side words do not steer: flip the image | Tested |
| Action, sports, duel | 16:9 | | Mood | The count of each role ("two blockers"); different styles for two fighters, or they come out as twins | Tested, counts drift |
| Mecha, magical girl, other genre staples | 16:9 | | Mood | Your own design in words. A genre word can pull in a famous franchise's style: check and redesign | Tested, trade dress appears |
| Manga page, 4-koma | 3:4 | | Mood | Panel count and order; one sentence per panel; dialogue and sound effects quoted. A vertical strip came out 2 x 2 | Tested |
| Anime title card, episode card | 16:9 | | Mood | The title and episode number quoted in Japanese | Tested |
| Animation school (stop-motion, clay, ink wash, ligne claire, puppet, cut-out) | 16:9 | | Mood | The material or method in words; then the subject and its count again. Era styles change the subject's clothes and body | Tested |

## Commerce and product

Read [shot design](shot-design.md) and [editing](editing.md). A product that must match a real item
comes from an Edit of a real photo, never from a generation.

| Kind of image | Ratio | Rewrite | Accuracy | The prompt must carry | Status |
|---|---|---|---|---|---|
| Product on white, marketplace image | 1:1 | | Rough | One product, whole item, even margin, "pure white, no shadow". Clip to 255 afterwards | Tested |
| Lifestyle product shot | 4:3 | | Rough | The product as reference; scene, light direction, surface, a scale cue | Tested (composite) |
| Packshot with reflection | 1:1 | | Mood | Glossy surface; a fading mirror reflection; softbox light | Tested |
| Jewelry, watch macro | 1:1 | | Mood | Metal, stone cut and count, prongs; the brand quoted. Dial numerals come out wrong | Tested |
| Interior, real-estate staging | 4:3 | either | Rough | Room, style, furniture, window light. Label staged photos as staged | Tested |
| Fashion flat lay | 1:1 | yes | Mood | Every item named; "each item separate, nothing touching"; do not ask to fold a coat in half | Tested |
| Food photo | 4:3 | | Mood | Dish and its parts; angle; steam or gloss; light | Tested |
| Headshot | 3:4 | either | Mood | Head and shoulders; plain backdrop; even light | Tested |
| Automotive | 16:9 | | Mood | Body type, angle, location. A real model's badges, wheels and lights drift | Guidance |

## Photography

Read [photography genres](photography-genres.md) and [shot design](shot-design.md).

| Kind of image | Ratio | Rewrite | Accuracy | The prompt must carry | Status |
|---|---|---|---|---|---|
| Street, candid, documentary | 3:2 | yes | Mood | Place and 2 or 3 local details; "candid, nobody looks at the camera, off-center"; light and time; short sign texts quoted | Tested |
| Reflection, silhouette, motion blur, fog | 3:2 | | Mood | What is sharp, blurred, reflected or dark | Tested |
| Phone snapshot, party flash, selfie | 3:2 | | Mood | The device and its flaws; flash makes people pose; count the people | Tested |
| Film or period snapshot | 3:2 | | Mood | Decade, print fading, period props. Check props for the wrong decade | Tested |

## Learning, science and architecture

Read [design and text](design-and-text.md).

| Kind of image | Ratio | Rewrite | Accuracy | The prompt must carry | Status |
|---|---|---|---|---|---|
| Historical reconstruction | 16:9 | | Rough | Period, region, materials, clothing; caption it "artist's impression" | Guidance |
| Botanical or zoological plate | 3:4 | | Rough | One species; medium and paper; one or two short quoted labels. Six beetles came back as one species | Tested |
| Unlabeled science art: cutaway, cell, solar system | 16:9 | | Rough | "No text"; add labels in a layout tool. A cell looked right; a solar system had two Earths and the wrong order; a volcano lost its side vent | Tested |
| Anatomy, cell, chemistry, math figure | | | Exact | Draw it with code or an illustrator. The model mislabels parts | Tested, fails |
| Floor plan, site plan | 4:3 | | Exact | Draw it with a CAD or drawing tool. Rooms and labels drift | Tested, fails |
| Elevation, section | 4:3 | | Rough | "Orthographic, flat, no perspective"; counts of windows per floor | Tested |
| Architecture exterior render | 16:9 | | Rough | Type, massing, materials, site, time, eye level. Proportions in words, not meters | Tested |
| Axonometric cutaway, section with washes | 4:3 | | Rough | The roof lifted off, the floors and furniture, thin lines and pastel fills | Tested |

## Craft and fashion

Read [illustration and assets](illustration-and-assets.md), "Craft, print and cut work".

| Kind of image | Ratio | Rewrite | Accuracy | The prompt must carry | Status |
|---|---|---|---|---|---|
| Print-on-demand graphic | 1:1 | | Mood | Flat colors; a flat key color absent from the art; no shadow. Key it out afterwards | Tested |
| Stencil, cut file | 1:1 | | Exact | Black on white, bold shapes. Islands float: add bridges by hand | Tested, bridges fail |
| Cross-stitch, bead or pixel pattern | 1:1 | | Exact | A coarse pixel style, a named small palette. Grid and palette come from a script | Tested |
| Embroidery, stained glass, quilt | 1:1 | | Mood | Flat closed shapes, few colors, thick outlines. Counts and cut lines need a tool | Guidance |
| Fashion technical flat | 3:4 | | Rough | Front view, symmetric, stitching dashed, details listed. Count the details; back view by Edit | Tested |
| Fashion illustration | 3:4 | | Mood | Elongated figure, medium, garment details | Guidance |
| Jewelry design sketch | 1:1 | | Mood | Three-quarter view, metal and stone. Not manufacturable | Guidance |

## Edit

All edit rows read [editing](editing.md).

| Task | The instruction must carry | Status |
|---|---|---|
| Background swap | What stays, quoted label included; the new setting | Tested |
| Cutout to white | "Pure white background, no shadow"; what stays. The border comes back near-white (245 to 252), so clip it to 255 before you cut out | Tested |
| Remove or add an object | The target; its place named by nearby objects; a region mark for exact placement | Tested |
| Region-marked edit | The mark as the last reference with `mask: true`; the change "in the orange area of <imageN>". Places a change exactly; does not protect the rest | Tested |
| Restore an old photo | Each kind of damage; "do not add anything" | Tested |
| Colorize | Era; known colors; natural, muted saturation | Tested |
| Season, weather, time of day, relight | The target condition; the light source; "keep the layout" | Tested |
| Restyle, photo to watercolor, line art or chibi | The target medium; what must stay (faces, markings). Faces resist a style: ask for it on the faces too | Tested |
| Sketch to render | "Keep the exact shape of the sketch"; materials and light | Tested |
| Replace or translate text | Old and new strings quoted; same font, size, color | Tested |
| Ad localization | Each translated string supplied by you, old and new quoted. Latin is exact; small Japanese, Korean and Arabic lines fail | Tested, small non-Latin fails |
| A/B variant of an ad | One change only; everything else named as kept | Tested |
| Expression or pose | The new expression; identity, clothes and background kept | Tested |
| Composite, product placement, logo on product | Each image's role; scale; light and shadow; frame image last | Tested |
| Colorway | The part that changes and its color; shape and light kept | Tested |
| Try-on | The garment's details; face, pose and background kept; person last | Tested |
| Hair color, skin cleanup | One zone; "keep the face, skin texture, pores and moles" | Tested (hair); skin not tested: the model would not draw the blemishes to remove |
| ID or passport-style photo | Plain background, facing the camera, even light. Not for official documents. Likeness is not proven | Tested |
| Remove people, sky swap | Which people; what fills the space; light matched to the new sky | Tested |
| Empty a room, restage it | "Remove all furniture"; then the furniture list in a second edit | Tested |
| Character in a new scene | A character sheet as the reference; the new scene | Tested |
| Turnaround, back view of a flat | "Same character from the side" or "the back view of the same jacket"; one view per edit | Tested |
| Background to a key color | Not for a person or hair: the key color fringes the hair. Matte the original photo instead | Tested, fringes |
| Heal a texture seam with a mark | Not supported: a large mark tints the whole image its color | Tested, fails |
| Zoom out, outpaint | Not supported: Edit has no canvas size | Tested, fails |
