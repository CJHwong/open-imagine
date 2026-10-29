import base64
import io
import json
import threading
import urllib.error
import urllib.request
import wave
from dataclasses import replace
from http.server import ThreadingHTTPServer
from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import StudioError
from studio.l3_interface_adapters.gateways.music.stub_music_backend_gateway import StubMusicBackendGateway
from studio.l3_interface_adapters.gateways.prompt_rewriters import NoPromptRewriter
from studio.l4_frameworks_and_drivers.config import Config, ConfigError, load_config
from studio.l4_frameworks_and_drivers.main import assemble_studio, build_music_backends, music_yue2_backend
from tests.support.fakes import FakeBackendGateway

PAYLOAD = {"kind": "music", "style": "piano", "lyrics": "[Verse]\nhello", "seed": 7}


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(
        "studio.l3_interface_adapters.gateways.music.stub_music_backend_gateway.time.sleep", lambda _: None
    )
    studio = assemble_studio(
        {"fake": FakeBackendGateway()},
        {"fake": NoPromptRewriter()},
        "fake",
        ("fake",),
        music_backends={"yue2": StubMusicBackendGateway()},
    )
    http = ThreadingHTTPServer(("127.0.0.1", 0), studio.handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{http.server_port}"

    def request(path, payload=None, form=False):
        body = (payload if form else json.dumps(payload)).encode() if payload is not None else None
        headers = {"Content-Type": "application/x-www-form-urlencoded" if form else "application/json"}
        try:
            answer = urllib.request.urlopen(urllib.request.Request(base + path, data=body, headers=headers))
        except urllib.error.HTTPError as error:
            answer = error
        raw = answer.read()
        return (
            answer.status,
            answer.headers,
            json.loads(raw) if "json" in answer.headers.get("Content-Type", "") else raw,
        )

    yield request
    http.shutdown()
    thread.join()
    http.server_close()
    studio.shutdown()


def test_stereo_song_and_metadata_roundtrip(server):
    status, _, discovery = server("/api/v1/studio")
    assert status == 200 and discovery["music"]["active"] == "yue2"
    assert server("/api/v1/music/capabilities")[2]["channels"] == 2
    assert server("/api/v1/music/backends/yue2")[0] == 200
    assert server("/api/v1/music/backends/missing")[0] == 404
    assert server("/api/v1/music/backend", {"backend": "yue2"})[0] == 204
    assert server("/music/backend", "backend=yue2", form=True)[0] == 200
    status, headers, raw = server("/api/v1/music/generate", PAYLOAD)
    assert status == 200 and headers["X-Studio-Stub"] == "true"
    with wave.open(io.BytesIO(raw)) as audio:
        assert audio.getnchannels() == 2 and audio.getframerate() == 48000
    owner = headers["X-Studio-Operation"]
    metadata = server(f"/api/v1/operations/{owner}/metadata")[2]
    assert metadata["stub"] and metadata["seed"] == 7
    assert server(f"/api/v1/operations/{owner}/result")[2] == raw
    assert server(f"/api/v1/operations/{owner}")[2]["status"] == "succeeded"


def test_music_batches_retain_each_song_and_generation_details(server):
    status, _, operation = server("/music/operations", {**PAYLOAD, "items": [{"seed": 1}, {"seed": 2}]})
    assert status == 202
    owner = operation["id"]
    import time

    for _ in range(100):
        record = server(operation["status_url"])[2]
        if record["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.01)
    assert record["status"] == "succeeded", record
    manifest = server(record["result_url"])[2]
    assert manifest["completed"] == 2
    for index in (1, 2):
        assert server(f"/api/v1/operations/{owner}/items/{index}/metadata")[2]["seed"] == index
        assert server(f"/api/v1/operations/{owner}/items/{index}/result")[1]["Content-Type"] == "audio/wav"


def test_bad_music_requests_fail_before_reserving(server):
    for patch in ({"lyrics": ""}, {"mode": "edit"}, {"kind": "rewrite", "workspace": "music"}, {"backend": ""}):
        assert server("/api/v1/operations", {**PAYLOAD, **patch})[0] == 400
    assert server("/api/v1/state")[2]["active"] is None
    status, _headers, raw = server("/api/v1/music/generate", {**PAYLOAD, "style": ""})
    assert status == 400 and "error" in raw
    # A nonmusic operation must not be serialized as Music metadata.
    status, _headers, result = server("/api/v1/operations", {"kind": "image", "prompt": "a tree"})
    import time

    for _ in range(100):
        record = server(result["status_url"])[2]
        if record["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.01)
    assert server(result["status_url"] + "/metadata")[0] == 400


def test_music_config_and_worker_environment(tmp_path):
    config = Config("qwen21", ("qwen21",), "v", (), {})
    backend = music_yue2_backend(config)
    assert backend._child._command[:3] == ["uv", "run", "--script"]
    config = replace(
        config,
        sections={"yue2": {"python_path": "/venv/bin/python", "model_dir": "/model", "vae_dir": "/vae"}},
    )
    gateway = build_music_backends(config)["yue2"]
    assert gateway._child._command[0] == "/venv/bin/python"
    assert gateway._child._command[-4:] == ["--model-dir", "/model", "--vae-dir", "/vae"]
    assert isinstance(build_music_backends(config, stub=True)["yue2"], StubMusicBackendGateway)
    with pytest.raises(ConfigError, match="mlx-q8"):
        music_yue2_backend(replace(config, sections={"yue2": {"engine": "torch"}}))
    with pytest.raises(ConfigError, match="missing"):
        build_music_backends(replace(config, visible_music_backends=("missing",)))
    path = tmp_path / "studio.toml"
    path.write_text('default_backend="qwen21"\ndefault_music_backend="custom"\nvisible_music_backends=["yue2"]\n')
    settings = load_config(path)
    assert settings.default_music_backend == "custom" and settings.visible_music_backends == ("custom", "yue2")


def test_unconfigured_music_uses_expected_error():
    from studio.l3_interface_adapters.api.json_api import JsonApi

    api = JsonApi(Mock(), operations=Mock(), completion=Mock(), batches=Mock())
    with pytest.raises(StudioError, match="Music generation is not configured"):
        api.music_capabilities()


def test_music_id_cannot_be_replaced_by_an_installed_plugin(monkeypatch):
    from studio.l4_frameworks_and_drivers.main import discover_plugins
    from tests.support.plugins import entry, fake_plugins

    plugin = entry("image", "yue2", fake_plugins()["image"])
    monkeypatch.setattr(
        "studio.l4_frameworks_and_drivers.model_plugins.metadata.entry_points",
        lambda group: [plugin] if group == plugin.group else [],
    )
    with pytest.raises(ConfigError, match="Duplicate model id"):
        discover_plugins()


def test_mlx_q8_config_selects_an_isolated_native_worker(tmp_path):
    config = Config("qwen21", ("qwen21",), "v", (), {"yue2": {"engine": "mlx-q8", "model_dir": "/mlx"}})
    gateway = music_yue2_backend(config)
    command = gateway._child._command
    assert command[:3] == ["uv", "run", "--script"]
    assert command[3].endswith("/yue2_mlx_child.py")
    assert command[-4:] == ["--model-dir", "/mlx", "--vae-dir", "/mlx-vae"]
    assert "--device" not in command
    assert gateway.capabilities().badge == "Q8 AR / BF16 audio"
    stub = build_music_backends(config, stub=True)["yue2"]
    assert stub.capabilities() == gateway.capabilities()
    path = tmp_path / "studio.toml"
    interpreter = tmp_path / "python"
    interpreter.symlink_to("/usr/bin/python3")
    path.write_text('default_backend="qwen21"\n[yue2]\nengine="mlx-q8"\npython_path="python"\nmodel_dir="weights"\n')
    gateway = music_yue2_backend(load_config(path))
    assert gateway._child._command[0] == str(interpreter)
    assert gateway._model_dir == str(tmp_path / "weights")
    with pytest.raises(ConfigError, match="engine"):
        music_yue2_backend(replace(config, sections={"yue2": {"engine": "q4"}}))


def test_mlx_q8_default_has_no_pytorch_fallback_and_rejects_nested_vae():
    config = Config("qwen21", ("qwen21",), "v", (), {})
    gateway = music_yue2_backend(config)
    assert gateway._child._command[3].endswith("yue2_mlx_child.py")
    assert gateway.capabilities().badge == "Q8 AR / BF16 audio"
    with pytest.raises(ConfigError, match="outside model_dir"):
        music_yue2_backend(replace(config, sections={"yue2": {"model_dir": "/weights", "vae_dir": "/weights/vae"}}))


@pytest.mark.parametrize("mode", ["plan", "transcribe"])
def test_score_only_results_use_json_in_sync_and_async_transport(server, mode):
    payload = {**PAYLOAD, "mode": mode, "abc": "X:1\nK:C\nCDEF|\n"}
    if mode == "transcribe":
        payload.pop("abc")
        payload.update(reference_audio=base64.b64encode(b"audio").decode(), reference_name="source.wav")
    status, headers, result = server("/api/v1/music/generate", payload)
    assert status == 200 and headers["Content-Type"].startswith("application/json")
    assert result["score"] and result["seconds"] == 0 and result["stub"]
    owner = headers["X-Studio-Operation"]
    assert server(f"/api/v1/operations/{owner}/result")[2] == result
    record = server(f"/api/v1/operations/{owner}")[2]
    assert "reference_audio" not in record["settings"]


def test_cover_batch_never_exposes_reference_audio_in_public_item_settings(server):
    payload = {
        **PAYLOAD,
        "mode": "cover",
        "reference_audio": base64.b64encode(b"audio").decode(),
        "reference_name": "source.wav",
        "items": [{"seed": 1}, {"seed": 2}],
    }
    status, _, operation = server("/music/operations", payload)
    assert status == 202
    import time

    for _ in range(100):
        record = server(operation["status_url"])[2]
        if record["status"] in ("succeeded", "failed"):
            break
        time.sleep(0.01)
    assert record["status"] == "succeeded"
    manifest = server(record["result_url"])[2]
    assert "reference_audio" not in record["settings"]
    for item in manifest["items"]:
        assert "reference_audio" not in item["settings"]
        assert item["settings"]["reference_name"] == "source.wav"
