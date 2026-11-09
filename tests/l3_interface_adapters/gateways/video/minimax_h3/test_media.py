import struct
import subprocess

import numpy as np
import pytest

from studio.l3_interface_adapters.gateways.video.minimax_h3 import media


def test_memory_mux_pipes_every_frame_and_stereo_sound_without_creating_files(tmp_path, monkeypatch, media_tools):
    monkeypatch.chdir(tmp_path)
    rng = np.random.default_rng(7)
    video = rng.integers(0, 256, (17, 64, 96, 3), dtype=np.uint8)
    audio = np.zeros((2, round(17 / 24 * 32000)), dtype=np.float32)

    data = media.encode_mp4(video, 24, audio, 32000)
    streams = media.inspect_mp4(data)

    picture = next(stream for stream in streams if stream["codec_type"] == "video")
    sound = next(stream for stream in streams if stream["codec_type"] == "audio")
    assert picture["width"] == 96 and picture["height"] == 64 and int(picture["nb_read_packets"]) == 17
    assert sound["channels"] == 2 and int(sound["sample_rate"]) == 32000
    assert not list(tmp_path.iterdir())


def test_memory_mux_requires_media_tools(monkeypatch):
    monkeypatch.setattr(media.shutil, "which", lambda _: None)

    with pytest.raises(RuntimeError, match="ffmpeg"):
        media.encode_mp4(None, 24, None, 32000)
    with pytest.raises(RuntimeError, match="ffprobe"):
        media.inspect_mp4(b"invalid")
    with pytest.raises(RuntimeError, match="before H3"):
        media.check_tools()
    with pytest.raises(RuntimeError, match="audio decoding"):
        media.decode_audio(b"track")


def test_memory_probe_rejects_an_unreadable_clip(media_tools):
    with pytest.raises(RuntimeError, match="unreadable"):
        media.inspect_mp4(b"invalid")


def test_memory_mux_rejects_an_encoder_failure_and_closes_its_pipes(monkeypatch):
    monkeypatch.setattr(media.shutil, "which", lambda _: "/usr/bin/false")

    with pytest.raises(RuntimeError, match="encoding failed"):
        media.encode_mp4(np.zeros((5, 32, 32, 3), dtype=np.uint8), 24, np.zeros((2, 100)), 32000)


def test_memory_mux_closes_pipe_descriptors_when_spawn_fails(monkeypatch, media_tools):
    def fail(*_, **__):
        raise OSError("cannot start encoder")

    monkeypatch.setattr(media.subprocess, "Popen", fail)

    with pytest.raises(OSError, match="cannot start"):
        media.encode_mp4(np.zeros((5, 32, 32, 3), dtype=np.uint8), 24, np.zeros((2, 100)), 32000)


def test_memory_mux_reaps_a_timed_out_encoder(monkeypatch, media_tools):
    from unittest.mock import Mock

    process = Mock()
    process.communicate.side_effect = [subprocess.TimeoutExpired("encoder", 180), (b"", b"")]
    monkeypatch.setattr(media.subprocess, "Popen", lambda *_, **__: process)

    with pytest.raises(subprocess.TimeoutExpired):
        media.encode_mp4(np.zeros((5, 32, 32, 3), dtype=np.uint8), 24, np.zeros((2, 100)), 32000)

    process.kill.assert_called_once_with()


def box(kind, payload=b"", large=False):
    if large:
        return struct.pack(">I4sQ", 1, kind, len(payload) + 16) + payload
    return struct.pack(">I4s", len(payload) + 8, kind) + payload


def offsets(kind, values):
    code = ">I" if kind == b"stco" else ">Q"
    return box(kind, struct.pack(">II", 0, len(values)) + b"".join(struct.pack(code, value) for value in values))


def moov(*tables):
    return box(b"moov", box(b"trak", box(b"edts", b"list") + box(b"mdia", box(b"minf", box(b"stbl", *tables)))))


FTYP = box(b"ftyp", b"M4A \0\0\0\0")
MDAT = box(b"mdat", b"sound" * 40)


def test_faststart_moves_a_trailing_index_in_front_of_the_data_and_shifts_its_chunk_offsets():
    index = moov(offsets(b"stco", [16, 116]) + offsets(b"co64", [2**40]))
    data = FTYP + box(b"free") + MDAT + index

    moved = media.faststart(data)

    assert moved[: len(FTYP) + 8] == FTYP + box(b"free")
    assert moved.endswith(MDAT) and len(moved) == len(data)
    shifted = moov(offsets(b"stco", [16 + len(index), 116 + len(index)]) + offsets(b"co64", [2**40 + len(index)]))
    assert moved[len(FTYP) + 8 : -len(MDAT)] == shifted


def test_faststart_keeps_a_short_tail_after_the_last_box():
    index = moov(offsets(b"stco", [16]))

    moved = media.faststart(FTYP + MDAT + index + b"\0\0\0")

    assert moved == FTYP + moov(offsets(b"stco", [16 + len(index)])) + MDAT + b"\0\0\0"


def test_faststart_reads_a_64_bit_box_size():
    index = moov(offsets(b"stco", [16]))
    data = FTYP + box(b"mdat", b"sound", large=True) + index

    assert media.faststart(data).startswith(FTYP + moov(offsets(b"stco", [16 + len(index)])))


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"RIFF\0\0\0\0WAVEfmt ", id="not-mp4"),
        pytest.param(FTYP + moov(offsets(b"stco", [16])) + MDAT, id="index-first"),
        pytest.param(FTYP + MDAT, id="no-index"),
        pytest.param(FTYP + box(b"free") + moov(), id="no-data"),
        pytest.param(FTYP + MDAT + struct.pack(">I4s", 0, b"moov") + b"rest", id="index-to-end-of-file"),
        pytest.param(FTYP + MDAT + b"moov", id="truncated-header"),
        pytest.param(FTYP + MDAT + struct.pack(">I4s", 1, b"moov"), id="truncated-64-bit-header"),
        pytest.param(FTYP + MDAT + struct.pack(">I4s", 99, b"moov"), id="past-the-end"),
        pytest.param(FTYP + MDAT + struct.pack(">I4s", 4, b"moov"), id="smaller-than-its-header"),
        pytest.param(FTYP + MDAT + moov(box(b"stco", b"\0\0")), id="short-table"),
        pytest.param(FTYP + MDAT + moov(box(b"stco", struct.pack(">II", 0, 9))), id="truncated-table"),
        pytest.param(FTYP + MDAT + moov(offsets(b"stco", [2**32 - 8])), id="stco-overflow"),
        pytest.param(FTYP + MDAT + moov(offsets(b"co64", [2**64 - 8])), id="co64-overflow"),
        pytest.param(FTYP + MDAT + moov(offsets(b"stco", [16])) + MDAT, id="data-after-the-index"),
        pytest.param(FTYP + MDAT + box(b"moov", b"half"), id="truncated-header-inside-the-index"),
    ],
)
def test_faststart_returns_other_bytes_unchanged(data):
    assert media.faststart(data) is data


def test_memory_decode_returns_the_engine_shape_and_honours_its_window(media_tools, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    whole = media.decode_audio(b"\0" * 3000, 8000)
    window = media.decode_audio(b"\0" * 3000, 8000, start_seconds=0.5, duration_seconds=1.0)

    assert whole.shape == (2, 24000) and whole.dtype == np.float32 and whole.flags.c_contiguous
    assert window.shape == (2, 8000)
    np.testing.assert_allclose(window[0], np.arange(8000) / 8000)
    np.testing.assert_array_equal(window[1], -window[0])
    assert not list(tmp_path.iterdir())


def test_memory_decode_reads_an_m4a_whose_index_follows_its_data(media_tools):
    data = FTYP + MDAT + moov(offsets(b"stco", [16]))

    assert media.decode_audio(data, 8000).shape == (2, round(len(data) / 1000 * 8000))


def test_memory_decode_refuses_a_track_that_gives_no_samples(media_tools):
    # ffmpeg exits 0 here: it reports the partial file and writes nothing.
    with pytest.raises(RuntimeError, match="could not read the audio"):
        media.decode_audio(FTYP + MDAT + struct.pack(">I4s", 0, b"moov") + b"rest")


def test_memory_decode_refuses_a_decoder_failure(monkeypatch):
    monkeypatch.setattr(media.shutil, "which", lambda _: "/usr/bin/false")

    with pytest.raises(RuntimeError, match="could not read the audio"):
        media.decode_audio(b"\0" * 3000)
