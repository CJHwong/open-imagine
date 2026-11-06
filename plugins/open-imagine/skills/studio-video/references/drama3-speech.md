# Drama-3 speech direction

Read this before writing spoken performance text when Drama-3 is selected. These are speech-generation controls, not a replacement for the screenplay. Prefer the [Drama-3 guide](https://docs.fish.audio/features/text-to-speech/drama-3) over syntax documented only for older models; recheck documentation when the backend changes.

## Performance text

Drama-3 accepts actor-style directions in square brackets immediately before the affected words. Describe intention, pace and addressee, rather than loading every line with emotion labels. Put an audible breath, laugh or pause where it belongs. Paired word-level delivery tags include `<whisper>`, `<emphasis>`, `<soft>`, `<fast>`, `<slow>`, `<stress>` and `<forceful>`. Language switching is experimental and needs listening tests with the actual voice. Multi-speaker cloud requests use indexed speaker markers and corresponding voice IDs; this does not establish support in a local wrapper. For the direct Fish cloud service, explicitly select the Drama-3 model header: omission can silently choose another model. Local Studio uses its discovered backend field instead.

An original, restrained announcement example:

```text
[clear, measured public-address delivery] The next stop is Museum.
```

The [emotion guide](https://docs.fish.audio/developer-guide/core-features/emotions) distinguishes newer square-bracket cues from legacy parenthesized syntax. The [fine-control guide](https://docs.fish.audio/developer-guide/core-features/fine-grained-control) still includes older experimental parenthesized effects; do not combine all examples indiscriminately. Phoneme tags can survive normal text normalization. Disabling normalization affects surrounding text such as numbers and dates and is not necessary just to insert phonemes. A normalization language setting is not an accent/voice selector.

## Pronunciation and dictionaries

Use phonemes for a demonstrated ambiguous name or term, not every ordinary word. Keep punctuation outside `<|phoneme_start|>…<|phoneme_end|>` and retain the readable script alongside the submitted phonetic form.

| Language | Unit and notation | Official details |
|---|---|---|
| English | One word; CMU Arpabet with vowel stress digits, not IPA | [English control](https://docs.fish.audio/developer-guide/core-features/fine-grained-control/english) |
| Chinese | One syllable per tag; lowercase pinyin with tone number, including 5 for neutral | [Chinese control](https://docs.fish.audio/developer-guide/core-features/fine-grained-control/chinese) |
| Japanese | Short word/phrase; OpenJTalk-style romaji with pitch digits; no literal pitch brackets inside phoneme tags | [Japanese control](https://docs.fish.audio/developer-guide/core-features/fine-grained-control/japanese) |

For repeated terms, [pronunciation dictionaries](https://docs.fish.audio/developer-guide/core-features/fine-grained-control/pronunciation-dictionaries) support versioned managed dictionaries or inline rules. Pin actual dictionary/version IDs with the take; publishing a new version does not advance old requests. Keys match literal substrings, so short keys can unintentionally affect longer words. Values contain phonemes without wrapper tags. Do not add dictionary API fields to a local request unless exposed; retain a project-local pronunciation record and test supported inline phonemes instead.

## Voice identity versus line delivery

[Voice Design](https://docs.fish.audio/features/voice-design) is a separate candidate-generation operation using a voice-design model. Its brief can describe timbre, age, accent, pacing and context; shared preview text helps compare candidates. A Drama-3 delivery cue or an unconditioned casting sample is not proof that dedicated Voice Design ran.

[Voice cloning](https://docs.fish.audio/features/voice-cloning) may use a persistent voice ID or per-request reference audio. Keep a clean single-speaker source, exact spoken transcript, source version and actual clone method. Cloud advice about longer recordings does not override a local reference-duration limit. Do not confuse speaker identity with a temporary emotional performance.

## Local execution and project records

Discover what the local Studio exposes for `drama3` (modes, reference format and length, `ref_text`, voice design, dictionaries, multiple voices). Audition text-level controls; cloud documentation does not show that a control survives the local implementation.

Keep readable words, submitted direction/phoneme text, speaker/voice version, pronunciation rules, request and waveform under the project root. The clone transcript matches audible words, excluding unspoken direction markup. Inspect for spoken-out tags, dropped/repeated words, wrong names, identity drift and unnatural pauses; ASR helps check words but cannot validate acting. A clone without a cue repeats the reference's delivery, so a shocked line cloned from a boast comes out as a boast: record each line's `direction` and generate with it. `scripts/sound_check.py` measures pitch range, pauses and loudness per take for the sound check in [board-review.md](board-review.md). Measure actual line length before placing it in the edit. Align on-camera speech to the selected waveform; keep offscreen dialogue independent of silent picture. Batch script variants using the pinned cast reference, preserve successful performances, and retry only observed defects.

What a twenty-shot local test showed:

- **A clone of its own sentence copies the reference.** When the reference says the exact line, every take came back with the reference's melody and length, whatever the cue or temperature. Clone that line from another take of the same speaker.
- **Put the cue before the line, not inside it.** A cue placed mid-line made the model say the words after it twice.
- **Long non-speech cues can run out of tokens.** A belly-laugh cue ran past `max_tokens` and the server refused the request. One short laugh with short laugh text worked.
- **A clone can land too close to another voice.** When a cloned voice sat within a few hertz of another character, a Drama-3 generate take from a written voice description (age, depth, texture) placed it clearly apart.
- **Trim a held pause after generation.** When every take held the same long pause at a comma, cutting the middle of the pause was cheaper than more seeds. Keep the cut take's source in its request record.
- **ASR misses names on some voices.** Whisper dropped or merged a name on one deep voice, even on the reference that says it. Compare sounds, not characters (toneless pinyin for Chinese), and leave the final word check to a listen.
