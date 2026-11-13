# MiniMax H3-Image prompt aids

Sampled on 2026-11-13 through the Studio API on the office M5 Pro (64 GiB), int8 weights,
six steps, seed 7, one run at a time. Generate cases ran at 1024 x 1024; edit cases ran at
2048 x 2048 from one 1024 x 1024 portrait. Each Look was sent as the bare prompt, then the
prompt plus the option's sentence, and the two were compared side by side. That is 63
images: 35 generate and 28 edit, no failures.

The raw images and the contact sheets are not in the repository.

## Generate Looks

| Row | Offered | Verdict |
|---|---|---|
| Medium | Watercolor, 3D render, Skeleton | All three change the picture plainly. Skeleton replaces the figure, which is the option's intent. |
| Film | Portra 400, Ektachrome, Black and white | Distinct stocks, and the monochrome one is fully neutral. |
| Color | Warm, Cool, Muted | Warm adds gold, Cool adds a blue cast, Muted desaturates. All three keep the subject. |
| Light | Golden hour, Studio, Night with neon | Golden hour gives low sun and long shadows. Studio replaces the room with a seamless background. Neon works, but the model invents its own sign lettering. |
| Camera | Close-up 85mm, Wide 24mm | Both change the lens and keep the object. Top-down bent the still life, so it is not offered. |
| Room for text | Left | Leaves the requested gap. Right wrote the word "Subject" into the gap, so it is not offered. |
| Realism | Real person | Adds skin texture and pores. It also moves to a closer framing. |
| Portrait | Over the shoulder, Candid glance | Both change the pose and the gaze as named. |

## Edit Looks

| Row | Offered | Verdict |
|---|---|---|
| Exposure | Brighter, Darker | Plain, and the subject is preserved. |
| White balance | Cooler, Warmer | Plain casts, subject preserved. |
| Grade | Teal and orange, Muted filmic | Both move the whole frame. |
| Lens | Shallow depth, Wider view, Telephoto | Each is visible in the background or the framing. |
| Finish | Film grain, Vignette, Halation | All three read at 2048. |
| Retouch | Smooth the skin, Brighten the eyes | Both work, and both are subtle at this size. |

The model has no negative prompt and no mask, so no avoid part is sent and no option asks
for a marked region.

## Templates

Every template was run with all of its fields filled.

| Template | Mode | Verdict |
|---|---|---|
| Portrait photo | generate | Works, with a natural face. |
| Product shot | generate | Works. |
| Landscape | generate | Works. |
| Poster with text | generate | Works, and the headline and second line are spelled correctly. |
| Illustration | generate | Watercolour rendering works. |
| Deadpan absurdity | generate | Works: the penguin waits at the bus stop. |
| Banner | generate | Works, with correct lettering on all three lines. |
| Replace the background | edit | Works. |
| Add text | edit | Works; the sign reads as given. |
| Add an object | edit | Works, and the person reacts to it. |
| Turn into a skeleton | edit | Works. |
| Turn into a pose figure | edit | Works as a jointed artist's mannequin. |
| Change a color or material | edit | Not offered: it turned the sweater into a clay pot. |
| Alternate reality | edit | Not offered: it pasted the subject into a street without changing the world. |
| Mark a region | edit | Not offered: this model takes no mask. |

This model draws lettering, which is why the three text-carrying templates are offered here
and not on models that misspell them.

## Rerun

The case list and the runner are scratch files, not part of the repository. To rerun, take
the option sentences from `image/qwen_runtime/prompt_aids.py`, send each case to
`POST /api/v1/images/generate`, and put the baseline next to every option. The edit cases
need one reference at `2048x2048` with the `edit` route.
