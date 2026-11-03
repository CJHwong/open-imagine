# Score-editing task

Goal: <the one musical change to make, and the target it serves>

Inputs: the source `score.abc`, its `request.json`, and any listening notes.

Constraints:

- Preserve the sounding pitch, onset and duration in every voice the change does not name.
- Keep the native headers, voices, bar grouping, `%` section comments and the ABC dialect.
- Keep the lyrics and the phrase lengths unless the task asks for a lyric change.
- Use only the chord shapes the source score uses. Put voicing words in `style`.
- Keep the supplied tempo and meter unless the task asks for a change.
- Do not add `w:` lines, tuplets, repeat signs, decorations or a second chord staff.

Outputs in a new directory:

- `edited.abc`: the complete score, including the passages you did not touch.
- `request.json`: the request that will send it, with the edited score as `abc` and `cot`
  `full` or `melody`.
- `edit_manifest.json`: the two hashes, the bars and voices that changed, the invariant
  level, each permitted change and each check that ran.
- A short rationale tied to actual bars and beats.

Check the whole score, not only the edited bars. Run:

```sh
python3 scripts/abc_tools.py inspect edited.abc
python3 scripts/abc_tools.py compare score.abc edited.abc --voices Vocal
```

Report what the comparison found, including the differences the contract permits. If you
only edited notation, do not report audio generation or listening.
