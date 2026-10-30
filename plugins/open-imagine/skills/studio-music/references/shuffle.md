# Shuffle a set

Use this for a continuous set of songs rather than one: a dinner, a party, a writing sprint, or
a sweep across styles.

## The stop is a track count

The track count is the stop: `--tracks N`. There is no per-track duration field. The engine
plans each length, and the style tempo and lyric length only steer it. Report each actual
duration. Ten tracks are not a fixed clock time.

If the user asks for a duration, say that the count is what you can set, and offer N tracks
from the observed lengths, for example ten tracks of about one to two minutes.

## Write the list

The agent writes the prompts. The script is the transport, not the author.

1. Choose the axes: genre, mood, instruments, vocal, language and tempo. Keep one axis in
   common when the set should feel like one evening; vary the rest.
2. Write 10 to 20 rows so the count has room. Each row is an object with `style`, sectioned
   `lyrics` and a `seed`. For an instrumental row, set `instrumental: true` and leave the
   lyrics blank.
3. Do not put `abc` or `reference_audio` in a row. The shuffle is text to song. A score set or
   a cover set needs its own requests.
4. Save `prompts.jsonl`, one object per line, or a JSON array. Do not repeat a lyric.

A row:

```json
{"style": "English, warm piano pop, clear lead vocal, acoustic piano, light drums, 88 BPM", "lyrics": "[Verse]\nMorning finds the empty street\nEvery window holds the heat\n\n[Chorus]\nCarry me into the light\nKeep the morning in our sight", "seed": 101}
```

## Run it

```sh
python3 scripts/shuffle.py --prompts prompts.jsonl --out sessions/dinner --tracks 10
```

- `--shuffle-seed` fixes the order so the session can be reproduced. The script records it.
- `--dry-run` prints the order and stops before any request.
- `--player` defaults to `afplay` on macOS. `--no-play` generates without playback.
- The script reads `/api/v1/music/capabilities` for the default planning and steps.

The script checks the one-operation slot before each submission, saves the WAV, score and
metadata, starts playback, and submits the next track while the last one plays. It waits
instead of cancelling someone else's run. Generation is slower than playback, so the player
may wait between tracks. The first track is the long wait.

## Stop

Ctrl-C stops the player and cancels only the operation the script started. Finished tracks
stay in the session folder. The script writes the partial session.

## Files

Each track is `track-01/` with `song.wav`, `score.abc`, `metadata.json`, `request.json` and
`status.json`. `session.json` holds the shuffle seed, the order, each seed, the durations and
any failure. Public results expire after ten minutes, so the script fetches each result
immediately.

## Report

Give the user the session folder, the shuffle order and the actual durations. The script
verifies the WAV header. It cannot hear the set. Listen yourself, or say that you did not.
The track count does not promise a style match or a fixed clock.
