"""Encode and inspect MP4 bytes without a media file on disk."""

import io
import json
import os
import shutil
import subprocess
import threading
import wave
from contextlib import suppress

import numpy as np


def check_tools():
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise RuntimeError("Install ffmpeg and ffprobe before H3 generation.")


def encode_mp4(video, fps, audio, sample_rate, *, crf=18):
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("Install ffmpeg for H3 video encoding.")
    video = np.ascontiguousarray(video, dtype=np.uint8)
    frames, height, width, _ = video.shape
    wave_bytes = io.BytesIO()
    audio = np.asarray(audio, dtype=np.float32)
    with wave.open(wave_bytes, "wb") as writer:
        writer.setnchannels(audio.shape[0])
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes((np.clip(audio.T, -1, 1) * 32767).astype("<i2").tobytes())
    read_fd, write_fd = os.pipe()
    command = [
        ffmpeg,
        "-v",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "pipe:0",
        "-f",
        "wav",
        "-i",
        f"pipe:{read_fd}",
        "-filter:a",
        f"apad,atrim=duration={frames / fps:.6f}",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-frames:v",
        str(frames),
        "-c:v",
        "libx264",
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "frag_keyframe+empty_moov",
        "-f",
        "mp4",
        "pipe:1",
    ]

    def send_audio():
        with suppress(BrokenPipeError), os.fdopen(write_fd, "wb") as stream:
            stream.write(wave_bytes.getbuffer())

    try:
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, pass_fds=(read_fd,)
        )
    except BaseException:
        os.close(write_fd)
        raise
    finally:
        os.close(read_fd)
    sender = threading.Thread(target=send_audio, daemon=True)
    sender.start()
    try:
        output, _ = process.communicate(video.tobytes(), timeout=180)
    except BaseException:
        process.kill()
        process.communicate()
        raise
    finally:
        sender.join(timeout=3)
    if process.returncode:
        raise RuntimeError("H3 MP4 encoding failed.")
    return output


def inspect_mp4(data):
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise RuntimeError("Install ffprobe for H3 output validation.")
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-count_packets",
            "-show_entries",
            "stream=codec_type,width,height,nb_read_packets,sample_rate,channels",
            "-of",
            "json",
            "pipe:0",
        ],
        input=data,
        capture_output=True,
        timeout=60,
    )
    if result.returncode:
        raise RuntimeError("H3 returned an unreadable MP4 clip.")
    return json.loads(result.stdout)["streams"]
