"""Private Music uses the same encrypted retention and ownership rules as other modes."""

import base64
import json
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import ThreadingHTTPServer

import pytest

from studio.l3_interface_adapters.gateways.music.stub_music_backend_gateway import StubMusicBackendGateway
from studio.l3_interface_adapters.gateways.prompt_rewriters import NoPromptRewriter
from studio.l4_frameworks_and_drivers.main import assemble_studio
from tests.support.fakes import FakeBackendGateway

KEY = "synthetic-music-owner-key-for-tests-only"
OTHER_KEY = "synthetic-other-owner-key-for-tests-only"
PAYLOAD = {"kind": "music", "style": "private-test-style", "lyrics": "[Verse]\nprivate-test-lyrics", "seed": 7}


@contextmanager
def music_server(directory):
    studio = assemble_studio(
        {"fake": FakeBackendGateway()},
        {"fake": NoPromptRewriter()},
        "fake",
        ("fake",),
        music_backends={"yue2": StubMusicBackendGateway()},
        private_results_dir=directory,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), studio.handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(path, payload=None, key=KEY, method=None):
        headers = {"Content-Type": "application/json"}
        if key:
            headers["X-Studio-Private-Key"] = key
        body = None if payload is None else json.dumps(payload).encode()
        message = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}{path}", data=body, headers=headers, method=method
        )
        try:
            response = urllib.request.urlopen(message)
        except urllib.error.HTTPError as error:
            response = error
        raw = response.read()
        content = json.loads(raw) if "json" in response.headers.get("Content-Type", "") else raw
        return response.status, content

    try:
        yield request
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
        studio.shutdown()


def wait_finished(request, path):
    for _ in range(200):
        status, record = request(path)
        assert status == 200
        if record["status"] not in ("running", "stopping"):
            assert record["status"] == "succeeded", record
            return record
        time.sleep(0.01)
    raise AssertionError("Music did not finish")


@pytest.mark.parametrize("mode", ["generate", "plan", "transcribe", "cover"])
@pytest.mark.parametrize("batch", [False, True])
def test_private_music_roundtrips_only_for_owner_after_restart_and_deletes(tmp_path, mode, batch):
    payload = {**PAYLOAD, "mode": mode}
    if mode in ("transcribe", "cover"):
        payload["reference_audio"] = base64.b64encode(b"private-test-reference").decode()
        payload["reference_name"] = "private-test-filename.wav"
    if batch:
        payload["items"] = [{"seed": 7}, {"seed": 8}]
    with music_server(tmp_path) as request:
        status, operation = request("/api/v1/operations", payload)
        assert status == 202 and operation["private"]
        path = operation["status_url"]
        record = wait_finished(request, path)
        assert record["settings"] == {} and record["prompt"] == ""
        assert request("/api/v1/state", key="")[1]["operations"] == []
        result_paths = [path + "/result"]
        metadata_paths = [path + "/metadata"]
        if batch:
            result_paths.extend(f"{path}/items/{index}/result" for index in (1, 2))
            metadata_paths = [f"{path}/items/{index}/metadata" for index in (1, 2)]
        for hidden_key in ("", OTHER_KEY):
            for hidden_path in [path, *result_paths, *metadata_paths]:
                assert request(hidden_path, key=hidden_key)[0] == 404
            assert request(path + "/cancel", {}, key=hidden_key)[0] == 404
            assert request(path, key=hidden_key, method="DELETE")[0] == 404
        expected = {route: request(route) for route in [*result_paths, *metadata_paths]}
        assert all(status == 200 for status, _ in expected.values())
        if batch:
            manifest = expected[path + "/result"][1]
            assert manifest["completed"] == 2
            assert all("settings" not in item and "prompt" not in item for item in manifest["items"])
        for index, route in enumerate(metadata_paths):
            assert expected[route][1]["seed"] == 7 + index
        if mode in ("plan", "transcribe"):
            assert all(expected[route][1]["score"] for route in metadata_paths)
        else:
            audio_path = result_paths[-1]
            assert expected[audio_path][1].startswith(b"RIFF")
        assert {route: request(route) for route in expected} == expected

    forbidden = [
        KEY.encode(),
        b"private-test-style",
        b"private-test-lyrics",
        b"Stub composition",
        b"RIFF",
        b"private-test-reference",
        b"private-test-filename",
        base64.b64encode(b"private-test-reference"),
    ]
    for file in tmp_path.iterdir():
        stored = file.read_bytes()
        assert all(secret not in stored for secret in forbidden)
    with music_server(tmp_path) as request:
        assert {route: request(route) for route in expected} == expected
        assert request(path, key=OTHER_KEY)[0] == 404
        assert request(path, method="DELETE")[0] == 204
        for route in [path, *expected]:
            assert request(route)[0] == 404
    with music_server(tmp_path) as request:
        assert request(path)[0] == 404


@pytest.mark.parametrize("path", ["/music/operations", "/api/v1/music/generate", "/api/v1/music/backend"])
def test_music_routes_without_private_ownership_refuse_key(tmp_path, path):
    with music_server(tmp_path) as request:
        status, answer = request(path, PAYLOAD)
        assert status == 400 and "only with POST /api/v1/operations" in answer["error"]
        assert request("/api/v1/state")[1]["operations"] == []
