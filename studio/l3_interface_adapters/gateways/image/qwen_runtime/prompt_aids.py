"""Qwen-family prompt wording; other image models explicitly select evaluated subsets.

See each integration's PROMPT_EVALUATION.md for evidence and limitations.
"""

from functools import partial

from studio.l1_entities.capabilities import LookRow, Template
from studio.l3_interface_adapters.gateways.image.qwen_runtime.template_translations import TRANSLATIONS
from studio.l3_interface_adapters.gateways.prompt_aids import pick_looks as select_looks
from studio.l3_interface_adapters.gateways.prompt_aids import pick_templates as select_templates
from studio.l3_interface_adapters.gateways.template_translations import translate_templates

GENERATE_TEMPLATES = (
    Template(
        "Portrait photo",
        "A person, with light and lens",
        "Close-up portrait photograph of [who: age, hair, look] in [place], at [time of day]. Wearing [clothing and colors], [pose or gaze], [expression]. [Light: direction and quality], [background, softly blurred]. 85mm lens at f/1.8, shallow depth of field, natural skin texture, [color mood].",
    ),
    Template(
        "Product shot",
        "An object on a surface, with space for copy",
        "Product photograph of [product: material, color, finish] on [surface] in [setting]. [Light: direction and quality], [one or two props] beside it. [Angle, e.g. three-quarter view at eye level], 85mm lens, empty space on the [side], [mood] mood.",
    ),
    Template(
        "Landscape",
        "A place, with the time and the view",
        "Wide photograph of [place] with [landmark] at [time of day and weather]. [A path, road or river] leads the eye from [where] toward [where]. [Sky and light]. Shot from [viewpoint], 24mm lens, deep focus, [detail] in the foreground, no text.",
    ),
    Template(
        "Poster with text",
        "Exact lettering, in any language",
        'Minimalist poster for [what]. At the top, a [lettering style] title "[title text]" in [color], with "[second line]" below it in [typeface style]. In the center, [main image]. At the bottom, the text "[small text]" in small [color] letters. [Background], generous empty space, centered layout, no other text.',
    ),
    Template(
        "Illustration",
        "A drawn or painted style",
        "[Medium, e.g. watercolor] illustration of [subject doing what] in [setting]. Palette of [3 or 4 colors], [line or brush quality], [light]. [Where the subject sits in the frame], [mood] mood, no text.",
    ),
    Template(
        "Deadpan absurdity",
        "One absurd thing in an ordinary scene",
        "A realistic candid photograph of a completely ordinary [place] on [a weekday and time], except [one absurd thing] is calmly [doing what] beside [where]. The people carry on as if nothing unusual is happening. [3 or 4 everyday details], [ordinary light]. Shot with a 28mm lens at eye level, natural perspective, documentary photojournalism.",
    ),
    # Short copy only: small, dense lines come out garbled, and a line in a
    # label form such as "Main: ..." gets drawn with its label.
    Template(
        "Banner",
        "An ad or a thumbnail, with at most 3 short lines",
        'A 16:9 [kind, e.g. video thumbnail or ad banner] on [background and colors]. [Person or product: who, clothing, pose] on the [side]. On the [other side], huge [color] [letter style, e.g. extra-bold gothic] text reads "[headline]", and below it, smaller text reads "[second line]". [A button, badge or band] reads "[short label]". [Mood].',
    ),
)

EDIT_TEMPLATES = (
    Template(
        "Change a color or material",
        "One object, the rest untouched",
        "Change only the [object]'s [color or material] to [new color and finish], keeping its [shape, texture, details]. Do not change the background, the lighting or the camera angle.",
    ),
    Template(
        "Replace the background",
        "Keep the subject, move the scene",
        "Replace only the background with [new place, time, weather, 2 or 3 details]. Keep the [subject]'s face, expression, clothing, pose and framing exactly as they are, and match the light on the [subject] to the new scene.",
    ),
    Template(
        "Add text",
        "A sign, label or banner",
        'Add [a sign, label or banner] at [position] with the text "[exact text]" in [color, letter style, size], spelled exactly. Match the scene\'s lighting and perspective, and keep everything else unchanged.',
    ),
    Template(
        "Alternate reality",
        "Same shot, a different world",
        "Keep the camera position, the composition, the people and their poses exactly unchanged. Change only [which part of the world]: [the new reality, with 1 or 2 visible details]. Preserve the lighting, the lens and the photographic texture.",
    ),
    Template(
        "Add an object",
        "Something new that touches the scene",
        "Add [object or animal] [where, and how it touches the scene], [one person reacting to it]. Give it correct scale, shadows and floor contact. Do not change [what must stay], the lighting or the camera position.",
    ),
    # On a person both keep the face and hair: the edit model protects a
    # person's identity. Asking for a figure "of its species" changed the
    # person, but turned a snake into a lizard and animals into human mannequins.
    Template(
        "Turn into a skeleton",
        "The bones of any person or animal, in its pose",
        "Turn the [subject] into its 3D anatomical skeleton in exactly the same pose, position and camera angle: every bone in its true place and number, ivory bone. Replace the background with a plain dark studio backdrop and soft museum lighting.",
    ),
    Template(
        "Turn into a pose figure",
        "A jointed figure in the same pose, as a reference",
        "Turn the [subject] into a 3D pose mannequin in exactly the same pose, position and camera angle: a smooth gray jointed figure with a ball joint at every joint, matching its body proportions. Replace the background with a plain light gray backdrop and even studio light.",
    ),
    # Needs the page's draw tool: the region travels as the last image of the
    # run, and the page replaces [the region you marked] with its number.
    Template(
        "Mark a region",
        "Draw the area first, then describe the change",
        # The page pins the rest of the picture after every prompt that carries a mask, so
        # this one does not say it too. The region token becomes the number of the image
        # holding the mask, and a row is optional while this sentence names the area.
        "Change only [what changes] in the area marked in [the region you marked].",
    ),
)

# What a video model is asked for. A still is described; a shot is directed, so these name
# the camera and the moment, and they carry no Look rows: a Look is a sentence about how one
# picture is made, and the video form offers none. Each of the five below rendered a clip
# whose text it kept, in the sample the module docstring describes.
#
# "First frame" and "Last frame" both name the reference image, and the page offers them
# only while the video carries one: without a still there is no frame to hold or to reach.
GENERATE_TEMPLATES = translate_templates(GENERATE_TEMPLATES, TRANSLATIONS, locale="zh-TW")
EDIT_TEMPLATES = translate_templates(EDIT_TEMPLATES, TRANSLATIONS, locale="zh-TW")

GENERATE_LOOKS = (
    LookRow(
        "Medium",
        options=(
            (
                "Documentary",
                "Documentary photograph with natural exposure, physically plausible light, accurate shadows and reflections, realistic skin and material texture, subtle sensor noise.",
            ),
            (
                "Phone snapshot",
                "Unedited phone photo straight out of the camera, candid and unposed, imperfect framing, uneven everyday light.",
            ),
            ("Watercolor", "Watercolor painting on textured paper, soft washes, visible brush edges."),
            ("Ink drawing", "Black ink drawing with fine linework and cross-hatching on white paper."),
            ("3D render", "Stylized 3D animated character, smooth rounded shapes, soft studio light."),
            (
                "Skeleton",
                "Rendered as a 3D anatomical skeleton of the subject in the same pose: every bone in its true place and number, ivory bone on a plain dark studio backdrop, soft museum lighting.",
            ),
        ),
    ),
    LookRow(
        "Film",
        options=(
            ("Portra 400", "Shot on Kodak Portra 400 film, warm natural colors, fine grain."),
            ("Fuji 400H", "Shot on Fuji Pro 400H film, cool soft pastel tones and smooth fine grain."),
            (
                "Ektachrome",
                "Shot on Kodak Ektachrome 64 slide film, high contrast, rich vivid colors and deep clean shadows.",
            ),
            ("Black and white", "Black and white photograph on Kodak Tri-X 400 film, strong grain, high contrast."),
        ),
    ),
    LookRow(
        "Color",
        options=(
            ("Warm", "Warm palette of amber, cream and brown."),
            ("Cool", "Cool palette of blue, teal and grey."),
            ("Muted", "Muted, desaturated colors."),
            ("Vivid", "Rich, deep, saturated colors."),
        ),
    ),
    LookRow(
        "Light",
        options=(
            ("Soft window light", "Soft daylight from a window on the left, gentle shadows."),
            ("Golden hour", "Warm low sun from the side, long shadows."),
            ("Studio", "Clean, even studio lighting against a plain seamless backdrop."),
            ("Overcast", "Overcast sky, soft diffuse light, gentle shadows."),
            ("Night with neon", "At night, lit by colored neon signs, reflections on wet surfaces."),
        ),
    ),
    LookRow(
        "Camera",
        options=(
            ("Close-up 85mm", "Close-up, 85mm lens at f/1.8, shallow depth of field."),
            ("Wide 24mm", "Wide shot, 24mm lens, deep focus."),
            ("Top-down", "Shot from directly above."),
            ("Low angle", "Low angle, looking up at the subject."),
            (
                "Telephoto",
                "Shot from a distance on a 135mm telephoto lens, compressed background, the subject isolated as if unaware of the camera.",
            ),
            ("Deep focus", "Deep focus at f/11, everything sharp from the nearest foreground to the far background."),
        ),
    ),
    LookRow(
        "Room for text",
        options=(
            ("Left", "Subject on the right third, empty space on the left."),
            ("Right", "Subject on the left third, empty space on the right."),
            ("Top", "Subject in the bottom third, a wide plain empty area across the top of the frame."),
        ),
    ),
    LookRow(
        "Realism",
        options=(
            (
                "Real person",
                "An everyday photo of a real person, like one posted on social media, not an advertising model or a CG character. Natural skin with visible pores, fine facial hair, faint redness and soft shadows, unretouched. A few loose strands of hair.",
            ),
        ),
        avoids=(
            (
                "Real person",
                "beauty filter, airbrushed skin, smooth plastic skin, CGI, 3D render, perfectly symmetric face, glossy magazine retouching",
            ),
        ),
    ),
    LookRow(
        "Portrait",
        options=(
            (
                "Over the shoulder",
                "The person turns three-quarters toward the camera, face and shoulders angled, one side of the face falling into soft shadow.",
            ),
            (
                "Candid glance",
                "The person is caught unposed in a passing moment, gaze slightly off camera, a faint smile with only small movement at the mouth and eyes.",
            ),
        ),
    ),
)


# The edit Look: what a photograph gets after it exists, which is the half the generate
# rows do not cover. A generate row decides how the model draws; a row here changes a
# picture that was already drawn, and the edit model keeps the rest of that picture, so
# every option is either a change to the whole frame or a change to the area the user
# marked. Only a Retouch option wants the mark, and such an option carries the page's token
# for it, `[the region you marked]`, in its own sentence: the page replaces the token with
# the number of the image holding the mask, which is the same token a template uses. So the
# catalog holds the intent, and the page stays ignorant of which options want an area. An
# option without the token is a change to the whole frame, and a mark does not scope it.
#
# Sampled twice on 2026-10-10, one seed and 768 on the short side each time, each option
# beside the bare fixture: on Qwen-Image-2.1 at 20 steps, where 15 of the 18 tried landed,
# and on Viggle Turbo at its six steps, where all 15 landed. Both models kept the whole set,
# which is why this is the catalog itself and not a subset a backend picks from. PROMPTS.md
# holds both tables, the two fixtures, the three options that did not land on the base, and
# what neither sample settles.
EDIT_LOOKS = (
    LookRow(
        "Exposure",
        options=(
            ("Brighter", "Raise the exposure by half a stop, keeping the highlight detail in the pale walls."),
            ("Darker", "Lower the exposure and deepen the shadows for a moodier image."),
        ),
    ),
    LookRow(
        "White balance",
        options=(
            (
                "Cooler",
                "Cool the white balance toward open shade, so the shadows read blue and the skin stays neutral.",
            ),
            ("Warmer", "Warm the white balance as at golden hour, without changing the composition."),
        ),
    ),
    LookRow(
        "Grade",
        options=(
            ("Teal and orange", "Teal and orange color grade, cinematic, warm skin against cool shadows."),
            ("Muted filmic", "Muted filmic grade, soft contrast, slightly lifted blacks, gentle desaturation."),
        ),
    ),
    LookRow(
        "Lens",
        options=(
            (
                "Shallow depth",
                "Shallow depth of field, the subject sharp and the background softly blurred with round bokeh.",
            ),
            (
                "Wider view",
                "Wider view, 24mm: more of the scene in frame and the subject further off, mild perspective stretch at the edges.",
            ),
            ("Telephoto", "Telephoto compression, 85mm, the background drawn in close behind the subject."),
        ),
    ),
    LookRow(
        "Finish",
        options=(
            ("Film grain", "Add visible film grain across the frame, like a high ISO color film."),
            ("Vignette", "Add a subtle vignette, darkening the corners without a visible circle."),
            ("Halation", "Add a slight halation on the highlights, a soft warm glow around the bright edges."),
        ),
    ),
    LookRow(
        "Retouch",
        options=(
            (
                "Smooth the skin",
                "Smooth the skin on the face, keeping the pores and the natural texture visible in the area marked in [the region you marked].",
            ),
            (
                "Brighten the eyes",
                "Brighten the whites of the eyes and deepen the iris, keeping the catchlights in the area marked in [the region you marked].",
            ),
            (
                "Clear a blemish",
                "Remove the blemish on the cheek, leaving no trace of it in the area marked in [the region you marked].",
            ),
        ),
    ),
)


pick_looks = partial(select_looks, GENERATE_LOOKS)
pick_templates = partial(select_templates, GENERATE_TEMPLATES + EDIT_TEMPLATES)
