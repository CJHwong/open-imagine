"""Encode, inspect and decode media bytes without a media file on disk."""

import io
import json
import os
import shutil
import struct
import subprocess
import threading
import wave
from contextlib import suppress

import numpy as np

# The boxes on the path from `moov` to the chunk offset tables.
INDEX_CONTAINERS = {b"moov", b"trak", b"mdia", b"minf", b"stbl"}


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


def decode_audio(data, sample_rate=32000, start_seconds=0.0, duration_seconds=None):
    """Decode a track held in memory into what the engine's `read_audio` returns for a file:
    float32 stereo at `sample_rate`, shaped (2, samples)."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("Install ffmpeg for H3 audio decoding.")
    command = [ffmpeg, "-v", "error"]
    if start_seconds > 0:
        command += ["-ss", f"{start_seconds:.6f}"]
    command += ["-i", "pipe:0"]
    if duration_seconds is not None:
        command += ["-t", f"{max(0.0, duration_seconds):.6f}"]
    command += ["-vn", "-ac", "2", "-ar", str(int(sample_rate)), "-f", "f32le", "pipe:1"]
    result = subprocess.run(command, input=faststart(data), capture_output=True, timeout=180)
    # ffmpeg exits 0 with no samples when a pipe ends before it finds the audio.
    if result.returncode or not result.stdout:
        raise RuntimeError("H3 could not read the audio track.")
    samples = np.frombuffer(result.stdout, dtype="<f4")
    samples = samples[: samples.size - samples.size % 2]
    return np.ascontiguousarray(samples.reshape(-1, 2).T, dtype=np.float32)


def faststart(data):
    """Move an MP4 index that follows the media data to the front, the way qt-faststart does.

    ffmpeg reads a pipe forward only. It cannot go back to the data after it reads an index at
    the end, and a phone recording in M4A often has its index there. Other bytes, and an MP4
    that this cannot change, return unchanged, and ffmpeg reports what it cannot read.
    """
    try:
        top = list(_boxes(data, 0, len(data), tail=True))
        kinds = [kind for kind, _start, _header, _end in top]
        if kinds[:1] != [b"ftyp"] or b"moov" not in kinds or b"mdat" not in kinds:
            return data
        index, media = kinds.index(b"moov"), kinds.index(b"mdat")
        # Only the data between the first `mdat` and `moov` moves. Data after `moov` stays put,
        # so its offsets would need no shift, and one shift for every offset would be wrong.
        if index < media or b"mdat" in kinds[index + 1 :]:
            return data
        _kind, start, _header, end = top[index]
        if not struct.unpack_from(">I", data, start)[0]:
            return data  # a size of 0 means "to the end of the file", which stops being true
        moov = bytearray(data[start:end])
        _shift_chunk_offsets(moov, 0, len(moov), len(moov))
    except (ValueError, OverflowError):
        return data
    before = b"".join(data[start:end] for _kind, start, _header, end in top[:media])
    after = b"".join(data[start:end] for kind, start, _header, end in top[media:] if kind != b"moov")
    return before + bytes(moov) + after + data[top[-1][3] :]


def _boxes(data, start, end, tail=False):
    """The (kind, start, header size, end) of each box in data[start:end].

    With `tail`, fewer than 8 bytes after the last box end the list instead of an error. Some
    writers leave such padding at the end of a file, and ffmpeg ignores it.
    """
    position = start
    while position < end:
        if end - position < 8:
            if tail:
                return
            raise ValueError("truncated box header")
        size, kind = struct.unpack_from(">I4s", data, position)
        header = 8
        if size == 1:
            if end - position < 16:
                raise ValueError("truncated box header")
            size = struct.unpack_from(">Q", data, position + 8)[0]
            header = 16
        elif size == 0:
            size = end - position
        if size < header or position + size > end:
            raise ValueError("box size outside its parent")
        yield kind, position, header, position + size
        position += size


def _shift_chunk_offsets(moov, start, end, shift):
    """Add `shift` to every chunk offset under `moov`, because the media data moves by it."""
    for kind, box, header, box_end in list(_boxes(moov, start, end)):
        if kind in INDEX_CONTAINERS:
            _shift_chunk_offsets(moov, box + header, box_end, shift)
        elif kind in (b"stco", b"co64"):
            width, code, limit = (4, ">I", 2**32) if kind == b"stco" else (8, ">Q", 2**64)
            table = box + header + 8
            if box_end - box - header < 8:
                raise ValueError("truncated chunk offset table")
            count = struct.unpack_from(">I", moov, box + header + 4)[0]
            if table + count * width > box_end:
                raise ValueError("truncated chunk offset table")
            for entry in range(table, table + count * width, width):
                value = struct.unpack_from(code, moov, entry)[0] + shift
                if value >= limit:
                    raise OverflowError("chunk offset past the table's width")
                struct.pack_into(code, moov, entry, value)
