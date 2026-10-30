"""Shuffled Music set against a fresh stub server; no GPU and no playback.

uv run python tests/e2e/verify_music_shuffle.py <port>
"""

import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path


def main():
    port = int(sys.argv[1])
    base = f"http://127.0.0.1:{port}"
    script = Path(__file__).resolve().parents[2] / "plugins/open-imagine/skills/studio-music/scripts/shuffle.py"
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        prompts = root / "prompts.json"
        prompts.write_text(
            json.dumps(
                [
                    {"style": "Warm piano pop, 88 BPM", "lyrics": "[Verse]\nMorning light", "seed": 11},
                    {"style": "Acoustic folk, 95 BPM", "lyrics": "[Verse]\nEvening air", "seed": 12},
                ]
            ),
            encoding="utf-8",
        )
        out = root / "session"
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--base-url",
                base,
                "--prompts",
                str(prompts),
                "--out",
                str(out),
                "--tracks",
                "2",
                "--no-play",
                "--poll-seconds",
                "1",
                "--timeout",
                "120",
                "--shuffle-seed",
                "7",
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        session = json.loads((out / "session.json").read_text(encoding="utf-8"))
        assert session["requestedTracks"] == 2 and session["completed"] == 2 and session["failed"] == 0, session
        assert session["shuffleSeed"] == 7
        assert {track["seed"] for track in session["tracks"]} == {11, 12}
        for track in session["tracks"]:
            folder = out / f"track-{track['index']:02d}"
            for name in ("song.wav", "score.abc", "metadata.json", "request.json", "status.json"):
                assert (folder / name).is_file(), folder / name
            with wave.open(str(folder / "song.wav")) as recording:
                assert recording.getnchannels() == 2 and recording.getframerate() == 48000
                assert recording.getnframes() > 0
            request_body = json.loads((folder / "request.json").read_text(encoding="utf-8"))
            assert request_body["kind"] == "music" and request_body["mode"] == "generate"
            assert "reference_audio" not in request_body and "abc" not in request_body
            metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
            assert metadata["stub"] is True
    print("PASS shuffled set: two tracks generated, saved and listed without playback")


if __name__ == "__main__":
    main()
