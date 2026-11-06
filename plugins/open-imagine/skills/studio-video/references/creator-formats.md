# Short format

Read this only when `settings.profile` is `short`. A project without a profile is a drama, and none of this applies to it.

## What the profile changes

| | `drama` | `short` |
|---|---|---|
| Aspect when unset | none | `9:16` |
| Length | `target_seconds` | at most 60 s |
| Package and beat roles | not checked | checked by `ready` |
| Promise beat ends by | not checked | 3 s |

An explicit setting wins over the profile default: `aspect_ratio` and `promise_by_seconds`.

## Plan in this order

1. **Package first.** Write `package.title` and `package.thumbnail.brief` before the storyboard or the shoot plan. The title and thumbnail set what the viewer expects, so the opening must deliver them. List each `package.critical` item, a thing without which the video fails, with the beats that deliver it.
2. **Beat roles.** Give each beat in `beats` an `id`, a `role`, its `shots` and an `energy` from 1 to 5. Roles are `promise`, `setup`, `payoff`, `re_engage`, `turn`, `reveal` and `other`. A setup lists the payoffs it sets up in `sets_up`.
3. **Check the plan.** Run `review.py beats <project>`. It prints the beats by minute mark with an energy curve, and it fails a plan that:
   - has no title or thumbnail brief, or a critical item that names no beat
   - runs outside the profile's length
   - has no promise beat, or one that ends after `promise_by_seconds`
   - has a setup without a later payoff, or a payoff without a setup
   - has no `re_engage` beat starting inside each window
   - does not end on a payoff
4. Continue with the drama pipeline for every generated shot.

Energy is a planning aid. No check reads it. A long low stretch is a question to ask, not a failure.

## What the source supports

The source is one channel's production document, supplied by the user with unverified authorship (`notes/mrbeast-production-extracted.txt`, 1-based PDF pages). It describes videos that average about 13 minutes (p8). It gives no timings for a 60 s video: the `short` promise limit of 3 s is the producer's setting, not a sourced rule.

| Idea | Page | How the skill uses it |
|---|---|---|
| Know the title and thumbnail before production; they set expectations | p5, p6 | `package` is required |
| The title and thumbnail are critical components | p14 | `package.critical` maps to beats |
| The first minute delivers what the package promised | p6, p7 | the promise beat timing; a reviewer compares the opening frames with the thumbnail brief |
| Know the minute mark of every piece of work | p8 | the minute marks in `review.py beats` |
| Payoff at the end; withhold the result | p29 | setup and payoff checks; the last beat is a payoff |
| Good light at the start, extreme titles, "wow factor", no dull moments | p5, p9, p10, p35 | advice only; the document says the wow factor cannot be tracked (p10) |
| Abrupt endings | p35 | not adopted |

The skill does not read platform analytics. Click-through rate and view duration (p5, p6) need the platform's own data after release.
