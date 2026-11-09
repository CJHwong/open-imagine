"""LTX-family shot templates and Looks, evaluated on LTX-2.5.

See video/ltx25/PROMPT_EVALUATION.md for measured verdicts.
"""

from studio.l1_entities.capabilities import LookRow, Template
from studio.l3_interface_adapters.gateways.template_translations import translate_templates
from studio.l3_interface_adapters.gateways.video.ltx_runtime.template_translations import TRANSLATIONS

VIDEO_TEMPLATES = (
    Template(
        "Camera move",
        "One move, held steady",
        "[Who or what] [does what] in [place] at [time of day]. The camera "
        "[pushes in slowly, pulls back, pans left to right, or rises], keeping [what stays in "
        "frame]. [Light and mood]. [Sound: what is heard]. One continuous shot, [lens], no cuts.",
    ),
    Template(
        "First frame",
        "Hold the opening still",
        "Keep the first frame exactly as the reference image. From there, [what happens next] "
        "over [how long]. The camera [stays still, or moves how]. The light stays the same. "
        "[Sound: what is heard]. One continuous shot.",
        min_references=1,
    ),
    Template(
        "Last frame",
        "Reach a given ending still",
        "[A wide or a close shot] of [the scene] at the start. By the end, the frame matches the "
        "reference image: [what must be true at the end]. The camera [moves how], [light]. "
        "[Sound: what is heard]. One continuous shot.",
        min_references=1,
    ),
    Template(
        "Multi-shot",
        "Two to four shots, each cut named",
        "[Place] at [time of day], [light and atmosphere]. [Who or what] [does what], and "
        "[what is heard]. A hard cut to a [shot scale] of [who or what], [new framing and "
        "action]; [what carries across the cut]. A hard cut to a [shot scale] of [what], "
        "[action]; [how the sound changes]. Three shots, each joined by a named cut, "
        "[what the last shot ends on].",
    ),
    Template(
        "Dialogue",
        "Two people, one exchange, lines in quotes",
        "[Place] at [time of day], [light]. A [shot scale] frames [two people: age, hair, "
        "clothing], [posture or gesture], facing each other. [One of them] [physical cue] and "
        'says quietly, "[the line]". [The other] [physical reaction], then answers, "[the '
        'line]". The camera [holds on whom, or moves how]. [Ambient sound] under the voices. '
        "One continuous shot, no cuts.",
    ),
    Template(
        "Soundscape",
        "An ambient bed, with effects on the action",
        "[Place] at [time of day], [light]. [Who or what] [does what], [motion detail]. The "
        "camera [holds, or moves how]. The sound is layered: [the ambient bed of the place] "
        "underneath, [the effect the action makes] on each [beat or stroke], [a voice or a "
        "distant sound, or nothing], no music.",
    ),
    Template(
        "Product turn",
        "An object turning, with its label held",
        "[Product: material, colour, finish] on [surface] in [setting], turning slowly on a "
        "turntable. [Light], [what is behind it]. [Sound: what is heard, or none]. The object "
        'stays centred, shallow depth of field, the label text "[one or two words]" readable '
        "and spelled exactly.",
    ),
    # Style and stock was dropped on 2026-10-18. Its own text draws a frame the clip never
    # asked for: black bands down both sides with rounded corners on the picture, like a phone
    # upload. The outer 4% band reads 5.2 to 6.1 on seven of the eight fills sampled, where a
    # bare control reads 107.3 and 81.2. The one reading that filled the frame, 38.0 and 36.5,
    # does not reproduce: the same stock clause and the same style phrase measured 5.3 again in
    # one session, and its pair one style phrase away measured 5.2. Six wordings were tried,
    # among them one that asks the picture to fill the frame, and no wording lifted it, so the
    # frame follows from asking a video prompt for a film look. PROMPTS.md holds the clips, the
    # wordings and the numbers. The text was "[Who or what] [does what] in [place], in the
    # [colours and grain] of [film stock or camera], in [style]. Visible grain, [lens].
    # [Sound: what is heard]. One continuous shot, no cuts."
)

# A Look sentence is appended after the prompt, so it can only name what composes with any
# prompt: light, weather, palette and the mix. A camera move or a shot scale would fight a
# prompt that already names one, and the vendor's own guide warns about two orders to one
# camera operator. Each option below was sampled against one bare control clip on the office
# M5 Pro on 2026-10-19: 384 x 384, 121 frames, seed 7, distilled path, one prompt and one
# appended sentence. The verdicts are in PROMPTS.md.
VIDEO_TEMPLATES = translate_templates(VIDEO_TEMPLATES, TRANSLATIONS, locale="zh-TW")

VIDEO_LOOKS = (
    LookRow(
        "Light",
        options=(
            ("Golden hour", "Warm low sun from the side, long shadows."),
            ("Soft daylight", "Soft diffuse daylight from the left, gentle shadows."),
            ("Neon night", "At night, lit by colored neon signs, reflections on wet surfaces."),
        ),
    ),
    LookRow(
        "Atmosphere",
        options=(
            # The clip reads as a wet, hazy street; falling drops did not read at 384 x 384.
            ("Wet street", "Rain falls steadily, water beading on surfaces and running off edges."),
            ("Fog", "Thick fog drifts through the scene, softening the distance."),
        ),
    ),
    LookRow(
        "Grade",
        options=(
            ("Warm", "Warm palette of amber, cream and brown."),
            ("Cool", "Cool palette of blue, teal and grey."),
        ),
    ),
    # The vendor calls "no music" the single most useful audio direction, and on a scene that
    # invites a score it reproduces here: the control carried tones at 350, 263 and 522 Hz with
    # 7.4 envelope crossings a second, and the same clip with "no music" was 33 times quieter
    # with no tonal peak above 0.8 percent. "Ambient only" is not offered: it produced a
    # 524 Hz hum on a scene the model had already left unscored, so it changes nothing for the
    # better.
    LookRow(
        "Mix",
        options=(("No music", "The sound is the scene itself: footsteps, cloth, a light breeze, no music."),),
    ),
)
