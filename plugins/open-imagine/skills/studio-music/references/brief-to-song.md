# A first song, with no brief

Use this flow when the request is short or vague ("make me a nice song", "something for my
video"), or when the user says they do not know where to start. A user with a full brief skips
it.

The user is not expected to know music or API words. Ask in plain words, offer numbered picks,
and turn each pick into a style sentence and a request yourself. Ask at most three questions
before the first take. Never ask about planning, seeds, synthesis steps, scores or settings in
this conversation.

## 1. What is it for?

Ask once, with picks:

1. **A gift or a message.** Ask who it is for and one true detail about them. The words matter
   more than the arrangement.
2. **A background track for a video or a room.** This is usually an instrumental. Ask the mood
   and whether it should sit under talking or carry attention.
3. **Just to hear something.** Ask for one feeling and one kind of music they like, or offer the
   four directions below.
4. **A version of a recording they have.** Ask for the recording. This is a cover, not a new song.

If the request already says it ("for my sister", "for a travel video"), do not ask. Say what you
assumed.

## 2. How should it feel?

If the user named a style or an artist, translate it into plain sound words. Do not copy a
living artist's voice or a protected song. Name the traits instead: the instruments, the tempo,
the vocal character.

Otherwise offer four directions. Read the label and the plain sentence. Keep the style sentence
for the request.

1. **Warm piano pop.** Clear voice, piano, bass and light drums, around 88 BPM, easy to sing.
   Style: `English, warm piano pop, clear lead vocal, acoustic piano, rounded bass, light drums, unhurried phrasing, 88 BPM`.
2. **Soul and R&B.** A smooth groove, rich harmony and an expressive lead, around 80 BPM.
   Style: `English, smooth R&B, expressive lead vocal, electric piano, warm bass, soft drums, rich harmony, 80 BPM`.
3. **Acoustic folk.** Guitar and voice, close and honest, around 95 BPM.
   Style: `English, acoustic folk, close male vocal, fingerpicked acoustic guitar, light upright bass, 95 BPM`.
4. **Electronic or ambient.** Soft synths and space, with little or no percussion, around 70 BPM.
   Style: `Instrumental, warm ambient electronic, soft synthesizer pads, gentle pulse, spacious mix, 70 BPM`.

Add one line: "Or tell me a song you like, and I will describe its sound in plain words."

## 3. Words or no words?

- **The user has words.** Use them. Put a section tag on each part, keep the lines short, and
  show the result before you send it.
- **The user wants words but has none.** Ask for one sentence about the subject and one true
  detail. Write one verse and one chorus. Show it and say it is a draft. Four short lines per
  part are enough for a first take.
- **The user wants no words.** Leave the lyrics blank and set `instrumental: true`. Do not write
  a placeholder line.
- **Language.** Use the language of the request. Ask only when the request is ambiguous.

## 4. Make one take

Tell the user what will happen: one song, one run, the length follows the music. Then:

1. Build the style from the answers. Add the language, the voice, the instruments they named,
   the tempo and the mood.
2. Send one Generate request with planning `full`. Keep the default steps and guidance. Do not
   ask them to choose a seed.
3. Save the audio, the score and the request. Show the score only if they ask for it.
4. If the run fails, say what failed and what you will change. Do not silently lower the quality
   or shorten the request.

## 5. Listen and revise

Listen when you can. Check the words, the voice, the instruments and the ending. If you cannot
hear it, say which checks you made instead.

Ask: "Which part is closest? Or tell me one thing to change." Offer this menu:

1. Closer to what you imagined.
2. Warmer or brighter.
3. Slower or faster.
4. A different instrument.
5. A male or a female voice.
6. More energy, or calmer.
7. A shorter chorus, or a different structure.
8. Instrumental instead of words.

Apply one or two changes per round. Edit the words for a lyric change and the style for an
instrument or mood change. Explain that the length follows the composition, so "longer" is a
request and not a setting. Keep the previous take so the user can compare.

After two rounds without progress, ask what they hear as wrong, in their own words. Do not keep
regenerating the same request.

## 6. When to hand over control

When the user asks for a cover, a score edit, exact repetition, a specific seed, or planning
control, move to the main workflow. Read [score editing](score-editing.md) for a score change,
and the [API notes](studio-music-api.md) for the fields. Explain the new word once in plain
language, then use it.

## A safe default

If the user refuses every choice, use this and say it is a starting point: warm piano pop at
88 BPM, a clear voice, one verse and a repeated chorus, a four-line lyric about one true
detail. Make one take. Ask for one change.
