"""A stand-in ffmpeg and ffprobe for the H3 media tests, so the suite needs no media tools.

The first argument names the tool. As ffmpeg, it checks the command that the plugin builds:
raw RGB frames on stdin, a WAV on the descriptor that `pipe:N` names, and the MP4 on stdout,
with no file path. `-frames:v` caps the frame count, as it does in ffmpeg. The answer is a
header that names what arrived. As ffprobe, it reads that header back in ffprobe's JSON shape,
and it counts packets only when the command asks for them.

A command that asks for `f32le` decodes a track from stdin. Each 1000 bytes of the track are one
second, and the answer is stereo float32 with a ramp on the left and its negative on the right.
`-ss` and `-t` cut it as they do in ffmpeg. An MP4 whose `moov` index follows its `mdat` data
gives no samples, as it does in ffmpeg on a pipe, because a pipe cannot go back to the data.
ffmpeg reports "partial file" there and still exits 0.
"""

import io
import json
import os
import struct
import sys
import wave

HEADER = b"\0\0\0\x18ftypfake"


def decode(arguments: list[str]) -> None:
    inputs = [arguments[index + 1] for index, value in enumerate(arguments) if value == "-i"]
    if inputs != ["pipe:0"] or arguments[-1] != "pipe:1" or arguments[arguments.index("-ac") + 1] != "2":
        sys.exit("fake ffmpeg: the track must arrive on stdin and leave as stereo on stdout")
    track = sys.stdin.buffer.read()
    if track[4:8] == b"ftyp" and 0 <= track.find(b"mdat") < track.find(b"moov"):
        print("fake ffmpeg: partial file", file=sys.stderr)
        return
    rate = int(arguments[arguments.index("-ar") + 1])
    start = float(arguments[arguments.index("-ss") + 1]) if "-ss" in arguments else 0.0
    seconds = max(0.0, len(track) / 1000 - start)
    if "-t" in arguments:
        seconds = min(seconds, float(arguments[arguments.index("-t") + 1]))
    count = round(seconds * rate)
    left = [index / rate for index in range(count)]
    sys.stdout.buffer.write(struct.pack(f"<{2 * count}f", *(value for sample in left for value in (sample, -sample))))


def ffmpeg(arguments: list[str]) -> None:
    if "f32le" in arguments:
        return decode(arguments)
    inputs = [arguments[index + 1] for index, value in enumerate(arguments) if value == "-i"]
    if len(inputs) != 2 or inputs[0] != "pipe:0" or not inputs[1].startswith("pipe:") or arguments[-1] != "pipe:1":
        sys.exit("fake ffmpeg: every input and the output must be a pipe")
    width, height = map(int, arguments[arguments.index("-s") + 1].split("x"))
    frame = width * height * 3
    video = sys.stdin.buffer.read()
    with os.fdopen(int(inputs[1].removeprefix("pipe:")), "rb") as stream, wave.open(io.BytesIO(stream.read())) as sound:
        channels, rate = sound.getnchannels(), sound.getframerate()
    if not video or len(video) % frame:
        sys.exit("fake ffmpeg: the video pipe holds no whole frames")
    facts = {
        "width": width,
        "height": height,
        "frames": min(len(video) // frame, int(arguments[arguments.index("-frames:v") + 1])),
        "channels": channels,
        "rate": rate,
    }
    sys.stdout.buffer.write(HEADER + json.dumps(facts).encode())


def ffprobe(arguments: list[str]) -> None:
    data = sys.stdin.buffer.read()
    if arguments[-1] != "pipe:0" or not data.startswith(HEADER):
        sys.exit("fake ffprobe: invalid data")
    facts = json.loads(data[len(HEADER) :])
    picture = {"codec_type": "video", "width": facts["width"], "height": facts["height"]}
    if "-count_packets" in arguments:
        picture["nb_read_packets"] = str(facts["frames"])
    sound = {"codec_type": "audio", "sample_rate": str(facts["rate"]), "channels": facts["channels"]}
    print(json.dumps({"streams": [picture, sound]}))


if __name__ == "__main__":
    (ffmpeg if sys.argv[1] == "ffmpeg" else ffprobe)(sys.argv[2:])
