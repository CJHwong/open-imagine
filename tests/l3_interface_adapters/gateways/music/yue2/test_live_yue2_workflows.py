"""Functional proof through Studio; use an owned server and an exclusive GPU slot."""

import base64
import io
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pytest
import soundfile

SCORE = (
    "X:1\nT:Original verification melody\nM:4/4\nL:1/4\nQ:1/4=100\n"
    'V: Vocal clef=treble name="Vocal Melody"\nV: Ins clef=treble name="Instrumental"\nK:C\n'
    '% verse\nV: Vocal\n"C"C2E2|"Am"G2E2|"F"F2A2|"G"G4|\n'
    "V: Ins\nC,2G,2|A,2E,2|F,2C2|G,4|\n"
)


@pytest.mark.live
def test_live_yue2_all_workflows_through_studio():
    base = os.environ.get("STUDIO_MUSIC_LIVE_URL")
    if not base:
        pytest.skip("Set STUDIO_MUSIC_LIVE_URL to your owned Studio server after acquiring the GPU slot.")

    def request(path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        with urllib.request.urlopen(
            urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"}), timeout=60
        ) as answer:
            body = answer.read()
            return json.loads(body) if "json" in answer.headers["Content-Type"] else body

    def run(payload):
        operation = request("/music/operations", {"kind": "music", "backend": "yue2", **payload})
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            state = request(operation["status_url"])
            if state["status"] in ("succeeded", "failed", "cancelled"):
                break
            time.sleep(0.5)
        else:
            request(operation["status_url"] + "/cancel", {})
            raise AssertionError("Music workflow exceeded ten minutes")
        artifact_dir = os.environ.get("STUDIO_MUSIC_LIVE_ARTIFACT_DIR")
        if artifact_dir:
            folder = Path(artifact_dir)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / (state["id"] + ".json")).write_text(json.dumps(state, indent=2))
        assert state["status"] == "succeeded", json.dumps(state)
        assert "reference_audio" not in state["settings"]
        metadata = request(state["status_url"] + "/metadata")
        assert metadata["score"] and not metadata["stub"]
        result = request(state["result_url"])
        if artifact_dir:
            (folder / (state["id"] + "-metadata.json")).write_text(json.dumps(metadata, indent=2))
            if isinstance(result, bytes):
                (folder / (state["id"] + ".wav")).write_bytes(result)
        print(
            "PASS real workflow",
            payload.get("mode", "generate"),
            payload.get("instrumental", False),
            state["id"],
            flush=True,
        )
        return result, metadata

    def audio(result):
        assert isinstance(result, bytes)
        samples, rate = soundfile.read(io.BytesIO(result), always_2d=True)
        assert rate == 48000 and samples.shape[1] == 2 and len(samples) > 48000
        assert np.isfinite(samples).all() and np.sqrt(np.mean(samples**2)) > 0.001

    common = {
        "style": "English, warm piano pop, clear expressive vocals, piano, bass, light drums, 100 BPM",
        "lyrics": "[Verse]\nMorning settles on the street\nEvery window keeps a beat",
        "seed": 42,
        "cot": "full",
    }
    planned, details = run({**common, "mode": "plan"})
    assert isinstance(planned, dict) and planned["seconds"] == 0
    assert details["metadata"]["plan"]["abc_ids"]
    assert details["metadata"]["config"]["ar_precision"] == "8bit"
    recording, details = run({**common, "abc": SCORE, "steps": 32, "cfg_scale": 1})
    audio(recording)
    assert details["score"] == SCORE
    instrumental, details = run({**common, "abc": SCORE, "lyrics": "", "instrumental": True, "steps": 8})
    audio(instrumental)
    assert details["metadata"]["instrumental_transfer"]
    assert details["metadata"]["config"]["generation"]["ode_steps"] == 8
    composed_instrumental, details = run(
        {
            **common,
            "style": "Instrumental acoustic piano solo, gentle nocturne, 90 BPM",
            "lyrics": "",
            "instrumental": True,
            "steps": 8,
        }
    )
    audio(composed_instrumental)
    assert details["metadata"]["instrumental_transfer"]["vocal_notes_after"] == 0
    source = base64.b64encode(recording).decode()
    transcription, details = run(
        {
            "mode": "transcribe",
            "reference_audio": source,
            "reference_name": "original-verification.wav",
            "transcription_task": "melody-full",
        }
    )
    assert isinstance(transcription, dict)
    assert details["metadata"]["transcription"]["status"] == "complete"
    assert details["metadata"]["transcription_cache_hit"] is False
    transcribed_score = details["score"]
    artifacts = details["metadata"]["artifacts"]
    assert any(one["name"].endswith(".mid") for one in artifacts)
    assert any(one["name"].endswith(".lab") for one in artifacts)
    cover, details = run(
        {
            **common,
            "mode": "cover",
            "style": "English, small acoustic jazz ensemble, piano, upright bass",
            "reference_audio": source,
            "reference_name": "original-verification.wav",
            "steps": 8,
            "transcription_task": "melody-full",
        }
    )
    audio(cover)
    assert details["metadata"]["transcription"]["status"] == "complete"
    assert details["metadata"]["config"]["cot"] == "melody"
    assert details["metadata"]["transcription_cache_hit"] is True
    assert details["score"] == transcribed_score

    operation = request("/music/operations", {"kind": "music", **common, "mode": "plan", "seed": 12345})
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        state = request(operation["status_url"])
        if state.get("progress", {}).get("step", 0) > 0:
            break
        time.sleep(0.1)
    request(operation["status_url"] + "/cancel", {})
    for _ in range(100):
        state = request(operation["status_url"])
        if state["status"] == "cancelled":
            break
        time.sleep(0.1)
    assert state["status"] == "cancelled", state
    print("PASS real cancellation while planning", flush=True)
