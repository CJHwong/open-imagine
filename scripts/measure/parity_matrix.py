"""Write the parity manifest: one JSON line per case, with a payload for each engine.

Both engines get the same prompt, the same seed and the same reference bytes. Only the
backend id and the few fields an engine names differently change between them.
"""

import argparse
import json
from pathlib import Path

PICTURE = (
    "A weathered fisherman mends a net on a harbour wall at dawn, warm low light, calm water "
    "and open sky behind him, fine rope detail, a painted sign reading HARBOUR"
)
HARBOUR = "A harbour wall at midday, a fisherman mends a net, gulls overhead, clear sky"
SENTENCE = "Hello, the harbour is quiet."
PARAGRAPH = (
    "Every morning the fisherman walked the same wall. He knew the tide by the sound it made "
    "against the stones, and he knew the weather by the colour of the water beyond it. The "
    "harbour kept its own clock, and he had learned to read it before he could read a book. "
    "By noon the boats came back, and the wall filled with voices, rope and the smell of salt. "
    "He mended nets where the light was best and let the afternoon pass over him like weather."
)
TEN_WORDS = "The harbour is quiet at dawn and the gulls are awake."
SEVEN_WORDS = "The tide turns at dusk, and the wall is quiet again."
SHORT_SCRIPT = "The tide is low and the boats are still, and the wall is quiet."
LONG_SCRIPT = (
    "Every morning the fisherman walked the same wall. He knew the tide by the sound it made "
    "against the stones, and he knew the weather by the colour of the water beyond it."
)
SHORT_LYRIC = "[Verse]\nQuiet road, a small light"


def words(count: int) -> str:
    copies = count // len(PARAGRAPH.split()) + 1
    return " ".join(" ".join([PARAGRAPH] * copies).split()[:count])


def ref(name: str) -> dict:
    return {"$file": name, "$field": "png_base64"}


def cases() -> list[dict]:
    rows: list[dict] = []

    def image(case_id: str, mode: str, spark: dict, office: dict) -> None:
        rows.append(
            {
                "id": case_id,
                "kind": "image",
                "machines": {
                    "cuda": {"backend": "qwen21_turbo_cuda" if "qwen" in case_id else "minimax_h3_image_cuda", **spark},
                    "mlx": {"backend": "qwen21_turbo" if "qwen" in case_id else "minimax_h3_image", **office},
                },
            }
        )

    def video(case_id: str, body: dict) -> None:
        rows.append(
            {
                "id": case_id,
                "kind": "video",
                "machines": {"cuda": {"backend": "ltx25_cuda", **body}, "mlx": {"backend": "ltx25_mlx", **body}},
            }
        )

    def voice(case_id: str, body: dict) -> None:
        rows.append(
            {
                "id": case_id,
                "kind": "voice",
                "machines": {"cuda": {"backend": "drama3_cuda", **body}, "mlx": {"backend": "drama3", **body}},
            }
        )

    def music(case_id: str, body: dict) -> None:
        rows.append(
            {
                "id": case_id,
                "kind": "music",
                "machines": {"cuda": {"backend": "yue2_cuda", **body}, "mlx": {"backend": "yue2", **body}},
            }
        )

    for size in ("512x512", "768x768", "1024x1024", "1328x1328"):
        body = {"mode": "generate", "prompt": PICTURE, "size": size, "steps": 8, "guidance": 1.0, "seed": 7}
        image(f"qwen21_turbo/generate/text/{size.split('x')[0]}", "generate", body, body)

    for out in ("512", "768", "1024", "1344"):
        image(
            f"qwen21_turbo/edit/one-ref/out{out}",
            "edit",
            {
                "mode": "edit",
                "prompt": "Make it night, lit by the window.",
                "resolution": out,
                "steps": 8,
                "guidance": 1.0,
                "seed": 7,
                "references": [ref("ref-512.png")],
            },
            {
                "mode": "edit",
                "prompt": "Make it night, lit by the window.",
                "resolution": out,
                "steps": 8,
                "cfg": 1.0,
                "seed": 7,
                "references": [ref("ref-512.png")],
            },
        )

    for count in (2, 4, 8, 10):
        image(
            f"qwen21_turbo/edit/{count}-refs/out1024",
            "edit",
            {
                "mode": "edit",
                "prompt": "Put the objects from the pictures on one table.",
                "resolution": "1024",
                "steps": 8,
                "guidance": 1.0,
                "seed": 7,
                "references": [ref("ref-512.png")] * count,
            },
            {
                "mode": "edit",
                "prompt": "Put the objects from the pictures on one table.",
                "resolution": "1024",
                "steps": 8,
                "cfg": 1.0,
                "seed": 7,
                "references": [ref("ref-512.png")] * count,
            },
        )

    for name in ("512", "1600x900", "2048", "4032x3024"):
        image(
            f"qwen21_turbo/edit/one-ref/in{name}",
            "edit",
            {
                "mode": "edit",
                "prompt": "Make it night, lit by the window.",
                "resolution": "1024",
                "steps": 8,
                "guidance": 1.0,
                "seed": 7,
                "references": [ref(f"ref-{name}.png")],
            },
            {
                "mode": "edit",
                "prompt": "Make it night, lit by the window.",
                "resolution": "1024",
                "steps": 8,
                "cfg": 1.0,
                "seed": 7,
                "references": [ref(f"ref-{name}.png")],
            },
        )

    for size in ("1024x1024", "2048x2048"):
        body = {"mode": "generate", "prompt": PICTURE, "size": size, "steps": 6, "seed": 7}
        image(f"minimax_h3_image/generate/{size.split('x')[0]}", "generate", body, body)
    edit = {
        "mode": "edit",
        "prompt": "Make <Picture 1> night time, lit by the window.",
        "size": "match",
        "steps": 6,
        "seed": 7,
        "references": [ref("ref-2048.png")],
    }
    image("minimax_h3_image/edit/one-ref-2048", "edit", edit, edit)

    for width, height, frames in ((768, 768, 97), (1280, 704, 97), (1920, 1088, 97), (384, 384, 25)):
        video(
            f"ltx25/generate/text/{width}x{height}x{frames}",
            {
                "mode": "generate",
                "prompt": HARBOUR,
                "width": width,
                "height": height,
                "num_frames": frames,
                "frame_rate": 24,
                "seed": 7,
            },
        )
    for frames in (25, 49, 121):
        video(
            f"ltx25/generate/frames/{frames}",
            {
                "mode": "generate",
                "prompt": HARBOUR,
                "width": 768,
                "height": 768,
                "num_frames": frames,
                "frame_rate": 24,
                "seed": 7,
            },
        )
    video(
        "ltx25/generate/fast/768x768x121",
        {
            "mode": "generate",
            "prompt": HARBOUR,
            "width": 768,
            "height": 768,
            "num_frames": 121,
            "frame_rate": 24,
            "seed": 7,
            "fast_mode": True,
        },
    )
    for count in (1, 2, 4, 8):
        index = (
            [0, 96]
            if count == 2
            else [0, 32, 64, 96]
            if count == 4
            else [0, 13, 27, 41, 55, 69, 83, 96]
            if count == 8
            else [0]
        )
        video(
            f"ltx25/generate/{count}-keyframes/768x768x97",
            {
                "mode": "generate",
                "prompt": HARBOUR,
                "width": 768,
                "height": 768,
                "num_frames": 97,
                "frame_rate": 24,
                "seed": 7,
                "enhance": False,
                "references": [
                    {
                        "name": f"keyframe-{frame}.png",
                        "image": {"$file": "ref-768x512.png"},
                        "frame_index": frame,
                        "strength": 1.0,
                    }
                    for frame in index
                ],
            },
        )
    video(
        "ltx25/generate/no-enhance/768x768x97",
        {
            "mode": "generate",
            "prompt": HARBOUR,
            "width": 768,
            "height": 768,
            "num_frames": 97,
            "frame_rate": 24,
            "seed": 7,
            "enhance": False,
        },
    )

    voice("drama3/generate/sentence50", {"mode": "generate", "text": SENTENCE, "seed": 7})
    voice("drama3/generate/paragraph700", {"mode": "generate", "text": PARAGRAPH, "seed": 7})
    voice("drama3/generate/text50-seed11", {"mode": "generate", "text": TEN_WORDS, "seed": 11})
    voice("drama3/generate/text1000", {"mode": "generate", "text": words(200), "seed": 7})
    voice("drama3/generate/text4000", {"mode": "generate", "text": words(800), "seed": 7})
    voice(
        "drama3/clone/ref5s",
        {
            "mode": "clone",
            "text": SEVEN_WORDS,
            "seed": 7,
            "reference": {"$file": "voice-short.wav", "$field": "wav_base64"},
            "ref_text": SHORT_SCRIPT,
        },
    )
    voice(
        "drama3/clone/ref12s",
        {
            "mode": "clone",
            "text": SEVEN_WORDS,
            "seed": 7,
            "reference": {"$file": "voice-long.wav", "$field": "wav_base64"},
            "ref_text": LONG_SCRIPT,
        },
    )

    music(
        "yue2/generate/short", {"mode": "generate", "style": "Warm acoustic piano.", "lyrics": SHORT_LYRIC, "seed": 7}
    )
    music(
        "yue2/generate/long",
        {
            "mode": "generate",
            "style": "Warm acoustic folk, fingerpicked guitar.",
            "lyrics": "[Verse]\n" + PARAGRAPH,
            "seed": 7,
        },
    )
    music(
        "yue2/generate/instrumental",
        {"mode": "generate", "style": "Warm acoustic piano.", "lyrics": SHORT_LYRIC, "instrumental": True, "seed": 7},
    )
    music("yue2/plan/short", {"mode": "plan", "style": "Warm acoustic piano.", "lyrics": SHORT_LYRIC, "seed": 7})
    music(
        "yue2/transcribe/speech10s",
        {"mode": "transcribe", "reference_audio": {"$file": "music-10s.wav"}, "transcription_task": "melody-full"},
    )
    music(
        "yue2/transcribe/speech15s",
        {"mode": "transcribe", "reference_audio": {"$file": "music-15s.wav"}, "transcription_task": "melody-full"},
    )
    music(
        "yue2/cover/speech10s",
        {
            "mode": "cover",
            "reference_audio": {"$file": "music-10s.wav"},
            "transcription_task": "melody-full",
            "style": "Acoustic folk, fingerpicked guitar.",
            "lyrics": "[Verse]\nThe harbour lights are low\n",
            "seed": 7,
        },
    )
    return rows


WARMUP = (
    "qwen21_turbo/generate/text/512",
    "minimax_h3_image/generate/1024",
    "ltx25/generate/text/768x768x97",
    "drama3/generate/sentence50",
    "yue2/generate/short",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", default="/tmp/parity")
    parser.add_argument(
        "--warmup-only", action="store_true", help="write warmup.jsonl: the first case of each workspace"
    )
    arguments = parser.parse_args()
    work = Path(arguments.work)
    work.mkdir(parents=True, exist_ok=True)
    rows = cases()
    if arguments.warmup_only:
        rows = [row for row in rows if row["id"] in WARMUP]
        target = work / "warmup.jsonl"
    else:
        target = work / "matrix.jsonl"
    target.write_text("".join(json.dumps(row) + "\n" for row in rows))
    print(f"wrote {len(rows)} cases to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
