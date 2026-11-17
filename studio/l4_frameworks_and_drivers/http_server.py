"""The HTTP routes. Each one hands the form to the controller and its answer to the presenter."""

import json
import logging
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from studio.l1_entities.errors import (
    BackendBusy,
    Cancelled,
    InvalidJob,
    OperationMissing,
    QueueFull,
    StudioError,
    UnreadableImage,
)
from studio.l1_entities.music_job import MusicResult
from studio.l1_entities.video_capabilities import MAX_CLIP_MEGABYTES
from studio.l1_entities.video_job import VideoResult
from studio.l1_entities.voice_job import SpeechResult
from studio.l3_interface_adapters.api.json_api import JsonApi
from studio.l3_interface_adapters.controllers.form_controller import FormController
from studio.l3_interface_adapters.controllers.image_import_controller import (
    MAX_IMAGE_IMPORT_BYTES,
    ImageImportController,
)
from studio.l3_interface_adapters.controllers.video_controller import VideoController
from studio.l3_interface_adapters.presenters.html_presenter import HtmlPresenter
from studio.l3_interface_adapters.presenters.json_presenter import lora_document, rewrite_document
from studio.l4_frameworks_and_drivers.connect import ConnectTransport, pair_url, qr_svg

# Where the page's own files live. GET /page/<name> serves one of them, and a
# test points WEB at a directory of its own to reach both rules below.
WEB = Path(__file__).with_name("web").resolve()

# Only what a browser loads as code. The documents that sit beside them, this
# design among them, are not served.
PAGE_ASSETS = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}
# A clip crosses as base64 inside JSON, which costs four bytes for every three. A body cap
# below the encoded size refuses a clip the validator would accept, so this follows the
# advertised limit instead of being picked by hand. The margin holds the audio track, the
# prompt and the rest of the request.
MAX_CLIP_BYTES = int(MAX_CLIP_MEGABYTES * 1024 * 1024)
MAX_VIDEO_REQUEST_BYTES = (MAX_CLIP_BYTES + 2) // 3 * 4 + 8 * 1024 * 1024
MAX_VIDEO_REQUEST_MEGABYTES = MAX_VIDEO_REQUEST_BYTES // (1024 * 1024)


def body_read_seconds(length: int) -> float:
    """How long a body of this size may take: the idle timeout plus the slowest rate.

    A small body still gets the idle timeout, so a stalled header is caught in seconds. A
    large one gets the time its size needs at the slowest supported throughput, up to a
    bound, so a slow but working link is not refused for being slow.
    """
    return min(MAXIMUM_BODY_READ_SECONDS, REQUEST_READ_TIMEOUT_SECONDS + length / MINIMUM_BODY_BYTES_PER_SECOND)


REQUEST_READ_TIMEOUT_SECONDS = 30.0
# The slowest upload a request may take, in bytes per second. The size cap admits a 64 MB
# clip, which crosses as about 93 MB of base64, and the old fixed 30 second deadline
# refused that from a phone on a slow link while accepting it from a fast one. The deadline
# therefore follows the size, and a client that stops sending still fails on the idle
# timeout above.
MINIMUM_BODY_BYTES_PER_SECOND = 1024 * 1024
MAXIMUM_BODY_READ_SECONDS = 300.0
# A caller that sends this header owns private operations. The routes below are the
# only ones that can keep that promise, so any other route refuses the header.
PRIVATE_KEY_HEADER = "X-Studio-Private-Key"
PRIVATE_KEY_ELSEWHERE = f"{PRIVATE_KEY_HEADER} works only with POST /api/v1/operations."

LOGGER = logging.getLogger("studio.http")


def unexpected_answer(path: str) -> dict[str, str]:
    """The sentence an unexpected failure gets, and the log line that keeps the cause.

    An upstream exception can carry a filesystem path, an account name or a library's own
    words. The caller gets one request-scoped sentence that names none of them. The cause
    goes to this machine's log, where an operator can read it.
    """
    LOGGER.exception("unexpected error while answering %s", path)
    return {"error": "The studio hit an unexpected error. Its log names the cause."}


class StudioHTTPServer(ThreadingHTTPServer):
    expire: Callable[[], None]
    _next_expiry_check = 0.0

    def service_actions(self) -> None:
        now = time.monotonic()
        if now < self._next_expiry_check:
            return
        self._next_expiry_check = now + 60
        self.expire()


def make_handler(
    controller: FormController,
    presenter: HtmlPresenter,
    video_controller: VideoController | None = None,
    api: JsonApi | None = None,
    allowed_origins: tuple[str, ...] = (),
    connect: ConnectTransport | None = None,
) -> type[BaseHTTPRequestHandler]:
    """`allowed_origins` are pages at another address that may post here, such as
    a Tailscale serve URL that proxies to this port."""

    class StudioHandler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            super().setup()
            self._response_timeout = self.connection.gettimeout()
            self.connection.settimeout(REQUEST_READ_TIMEOUT_SECONDS)

        def log_message(self, format: str, *args) -> None:
            """Silence the access log. Prompts live in POST bodies, and none of
            this is wanted on disk or on the terminal."""

        def do_GET(self):
            if not self._trusted_host():
                self._send("forbidden", status=403, content_type="text/plain")
                return
            path = urlsplit(self.path).path
            if path == "/connect/qr.svg":
                self._connect_qr()
                return
            if path == "/connect/devices":
                self._connect_devices()
                return
            if path.startswith("/api/v1/"):
                self._api_get(path)
                return
            if self._refused_private_key():
                return
            if path == "/":
                # A handler without the API offers no optional workspace, and
                # the presenter draws no tab for one it was not told about.
                query = parse_qs(urlsplit(self.path).query)
                self._send(
                    presenter.page(
                        controller.page(),
                        api.workspaces() if api else None,
                        presenter.locale_for(
                            requested=(query.get("lang") or [None])[0],
                            cookie=self.headers.get("Cookie"),
                            accept_language=self.headers.get("Accept-Language"),
                        ),
                    )
                )
            elif path == "/api/docs":
                self._send((WEB / "api-docs.html").read_text())
            elif path == "/progress":
                self._send_shared(lambda: presenter.progress(api.progress_snapshot() if api else controller.progress()))
            elif path == "/video/progress":
                self._send_shared(
                    lambda: presenter.video_progress(api.progress_snapshot() if api else controller.progress()),
                    content_type="application/json",
                )
            elif path == "/rewrite/state":
                # The page polls this while a rewrite is in flight, so it is data
                # the page reads, not a fragment it appends.
                self._send_shared(
                    lambda: presenter.rewrite_state(api.rewrite_snapshot() if api else controller.rewrite_state()),
                    content_type="application/json",
                )
            elif path.startswith("/page/"):
                self._send_page_asset(path.removeprefix("/page/"))
            else:
                self._send("not found", status=404, content_type="text/plain")

        def do_DELETE(self):
            if not self._from_this_page():
                self._send("forbidden", status=403, content_type="text/plain")
                return
            path = urlsplit(self.path).path
            if not path.startswith("/api/v1/"):
                if not self._refused_private_key():
                    self._send_json({"error": "Not found"}, status=404)
                return
            if api is None:
                self._send_json({"error": "The JSON API is not configured."}, status=503)
                return
            viewer, status = self._api_result(self._viewer)
            if status != 200:
                self._send_json(viewer, status=status)
                return
            suffix = path.removeprefix("/api/v1/operations/")
            if path == "/api/v1/operations/" + suffix and suffix and "/" not in suffix:
                body, status = self._api_result(lambda: api.delete_operation(suffix, viewer))
                if status == 200:
                    self._send_bytes(b"", status=204)
                else:
                    self._send_json(body, status=status)
                return
            self._send_json({"error": PRIVATE_KEY_ELSEWHERE if viewer else "Not found"}, status=400 if viewer else 404)

        def do_POST(self):
            if not self._from_this_page():
                self._send("forbidden", status=403, content_type="text/plain")
                return
            path = urlsplit(self.path).path
            if path.startswith("/api/v1/"):
                self._api_post(path)
                return
            if path == "/connect/refresh":
                if self._refused_private_key():
                    return
                self._refresh_connect()
                return
            if self._refused_private_key():
                return
            if path == "/image/normalize":
                self._normalize_image()
                return
            if path in ("/voice/operations", "/image/operations", "/music/operations"):
                self._start_operation(source="ui")
                return
            if path == "/video/generate":
                self._run_video()
                return
            if path == "/video/cancel":
                self._cancel_video()
                return
            try:
                form = self._read_form()
            except InvalidJob as error:
                self._send_json({"error": str(error)}, status=400)
                return
            if path == "/generate":
                self._send(self._outcome(lambda: self._run_image_form(form)))
            elif path == "/cancel":
                self._send_shared(
                    lambda: api.cancel_image() if api else controller.cancel(), success=204, content_type="text/plain"
                )
            elif path == "/backend":
                self._send(
                    self._outcome(lambda: (api.switch_backend(form, "image") if api else controller.switch(form)) or "")
                )
            elif path == "/video/backend":
                if video_controller is None:
                    self._send_json({"error": "Video generation is not configured."}, status=503)
                else:
                    self._send(
                        self._outcome(
                            lambda: (api.switch_backend(form, "video") if api else video_controller.switch(form)) or ""
                        )
                    )
            elif path in ("/voice/backend", "/music/backend"):
                self._send(
                    self._outcome(
                        lambda: api.switch_backend(form, "music" if path == "/music/backend" else "voice") or ""
                    )
                    if api
                    else "Voice generation is not configured."
                )
            elif path == "/workspace":
                self._send(self._outcome(lambda: (api.leave_workspace() if api else controller.release_model()) or ""))
            elif path == "/rewrite":
                # The page reads this one as data, so a failure arrives as JSON
                # too. The other routes send HTML, which the page appends or toasts.
                self._send(
                    self._outcome(
                        lambda: presenter.rewrite(
                            api.observe(
                                "rewrite", form, lambda: controller.rewrite(form), rewrite_document, source="ui"
                            )
                            if api
                            else controller.rewrite(form)
                        ),
                        as_json=True,
                    ),
                    content_type="application/json",
                )
            elif path == "/rewrite/cancel":
                # The rewrite answers on its own request, so this one only asks for
                # the stop, the way `/cancel` does for a run.
                self._send_shared(
                    lambda: api.cancel_rewrite() if api else controller.cancel_rewrite(),
                    success=204,
                    content_type="text/plain",
                )
            elif path == "/hidden/cancel" and api is not None:
                # The page cannot see a private run, but that run holds the one GPU.
                # This stop frees it, and its answer names nothing about the run.
                self._send_shared(api.cancel_hidden, success=204, content_type="text/plain")
            else:
                self._send("not found", status=404, content_type="text/plain")

        def _connect_qr(self) -> None:
            if connect is None or not connect.status().running:
                self._send(
                    "The phone connection is off. Set [connect] enabled = true and restart the studio.",
                    status=404,
                    content_type="text/plain",
                )
                return
            self._send(qr_svg(pair_url(connect.status())), status=200, content_type="image/svg+xml")

        def _connect_devices(self) -> None:
            devices = [] if connect is None else connect.devices()
            self._send_json(
                {
                    "devices": devices,
                    "active": sum(1 for device in devices if device.get("active")),
                    "total": len(devices),
                }
            )

        def _refresh_connect(self) -> None:
            if connect is None:
                self._send("The phone connection is off.", status=404, content_type="text/plain")
                return
            try:
                status = connect.refresh()
            except StudioError as error:
                self._send(str(error), status=503, content_type="text/plain")
                return
            if not status.running:
                self._send(status.error or "The listener did not start.", status=503, content_type="text/plain")
                return
            self._send("", status=204, content_type="text/plain")

        def _run_image_form(self, form) -> str:
            if api is None:
                return presenter.run(controller.run(form))
            result, operation = api.image_form_run(form)
            markup = presenter.run(result)
            attributes = f' data-operation-id="{operation["id"]}" data-operation-started="{operation["started_at"]}"'
            attributes += f' data-operation-completed="{operation["result_completed_at"]}"'
            return markup.replace('class="item', attributes + ' class="item', 1)

        def _api_get(self, path: str) -> None:
            if api is None:
                self._send_json({"error": "The JSON API is not configured."}, status=503)
                return
            viewer, status = self._api_result(self._viewer)
            if status != 200:
                self._send_json(viewer, status=status)
                return
            if path in ("/api/v1/settings", "/api/v1/model-storage") and self._refused_private_key():
                return
            readers = {
                "/api/v1/openapi.json": api.openapi,
                "/api/v1/studio": api.studio,
                "/api/v1/settings": api.settings,
                "/api/v1/model-storage": api.model_storage,
                "/api/v1/voice/capabilities": api.voice_capabilities,
                "/api/v1/music/capabilities": api.music_capabilities,
                "/api/v1/progress": lambda: api.progress(viewer),
                "/api/v1/state": lambda: api.state(viewer),
                "/api/v1/rewrite/state": lambda: api.rewrite_state(viewer),
            }
            if (
                path.startswith(
                    (
                        "/api/v1/images/backends/",
                        "/api/v1/videos/backends/",
                        "/api/v1/voice/backends/",
                        "/api/v1/music/backends/",
                    )
                )
                and path.count("/") == 5
            ):
                workspace = (
                    "music"
                    if "/music/" in path
                    else "voice"
                    if "/voice/" in path
                    else "image"
                    if "/images/" in path
                    else "video"
                )
                body, status = self._api_result(lambda: api.backend_capabilities(workspace, path.rsplit("/", 1)[1]))
                self._send_json(body, status=status)
                return
            if path.startswith("/api/v1/operations/"):
                self._operation_get(path, viewer)
                return
            reader = readers.get(path)
            if reader is None:
                self._send_json({"error": "not found"}, status=404)
                return
            body, status = self._api_result(reader)
            self._send_json(body if body is not None else {}, status=status)

        def _api_post(self, path: str) -> None:
            """The API's own routes. A JSON body goes to the same controller the page
            uses, and every failure comes back as JSON with the status that names it."""
            if api is None:
                self._send_json({"error": "The JSON API is not configured."}, status=503)
                return
            viewer, status = self._api_result(self._viewer)
            if status != 200:
                self._send_json(viewer, status=status)
                return
            cancel = path.startswith("/api/v1/operations/") and path.endswith("/cancel")
            if viewer and path != "/api/v1/operations" and not cancel:
                self._send_json({"error": PRIVATE_KEY_ELSEWHERE}, status=400)
                return
            if path == "/api/v1/audio/trim":
                result, status = self._api_result(lambda: api.trim_audio(self._read_json()))
                if status == 200:
                    audio, seconds = result
                    self._send_bytes(audio, content_type="audio/wav", headers={"X-Studio-Duration": str(seconds)})
                else:
                    self._send_json(result, status=status)
                return
            if path == "/api/v1/music/generate":
                self._run_voice(kind="music")
                return
            if path == "/api/v1/voice/generate":
                self._run_voice()
                return
            if path == "/api/v1/operations":
                self._start_operation(owner=viewer)
                return
            if cancel:
                operation_id = path.removeprefix("/api/v1/operations/").removesuffix("/cancel")
                body, status = self._api_result(lambda: api.cancel_operation(operation_id, viewer))
            elif path in (
                "/api/v1/images/backend",
                "/api/v1/videos/backend",
                "/api/v1/voice/backend",
                "/api/v1/music/backend",
            ):
                workspace = (
                    "music"
                    if "/music/" in path
                    else "voice"
                    if "/voice/" in path
                    else "image"
                    if "/images/" in path
                    else "video"
                )
                body, status = self._api_result(lambda: api.switch_backend(self._read_json(), workspace))
            elif path == "/api/v1/settings":
                body, status = self._api_result(lambda: api.update_settings(self._read_json(include_identity=False)))
            elif path == "/api/v1/model-storage/plan":
                body, status = self._api_result(lambda: api.storage_plan(self._read_json(include_identity=False)))
            elif path == "/api/v1/model-storage/remove":
                body, status = self._api_result(
                    lambda: api.remove_model_assets(self._read_json(include_identity=False))
                )
            elif path == "/api/v1/memory/release":
                body, status = self._api_result(api.release_model)
            elif path in ("/api/v1/images/generate", "/api/v1/images/edit"):
                mode = "edit" if path.endswith("edit") else "generate"
                body, status = self._api_result(lambda: api.image_run(self._read_json(), mode))
            elif path == "/api/v1/images/plan":
                body, status = self._api_result(lambda: api.image_plan(self._read_json()))
            elif path == "/api/v1/videos/plan":
                body, status = self._api_result(lambda: api.video_plan(self._read_json()))
            elif path == "/api/v1/images/rewrite":
                body, status = self._api_result(lambda: api.image_rewrite(self._read_json()))
            elif path == "/api/v1/videos/rewrite":
                body, status = self._api_result(lambda: api.video_rewrite(self._read_json()))
            elif path == "/api/v1/images/cancel":
                body, status = self._api_result(api.cancel_image)
            elif path == "/api/v1/rewrite/cancel":
                body, status = self._api_result(api.cancel_rewrite)
            elif path == "/api/v1/videos/generate":
                self._run_video(mode="generate")
                return
            elif path == "/api/v1/videos/edit":
                self._run_video(mode="edit")
                return
            elif path == "/api/v1/videos/cancel":
                self._cancel_video(via_api=True)
                return
            else:
                self._send_json({"error": "not found"}, status=404)
                return
            if body is None:
                self._send("", status=204, content_type="text/plain")
            else:
                self._send_json(body, status=status)

        def _start_operation(self, source="api", owner="") -> None:
            assert api is not None
            payload = {}

            def reserve():
                payload.update(self._read_json())
                return api.reserve(payload, source=source, owner=owner, queued=True)

            operation, status = self._api_result(reserve)
            if status != 200:
                self._send_json(operation, status=status)
                return
            try:
                worker = threading.Thread(target=self._perform_operation, args=(operation, payload), daemon=True)
                worker.start()
            except RuntimeError as error:
                # The reservation is recorded and no worker exists to finish it. Ending the
                # operation here is what keeps the studio from staying busy for ever.
                api.abandon_operation(operation["id"], error)
                self._send_json({"error": "The studio could not start this operation."}, status=503)
                return
            self._send_json(operation, status=202, headers={"Location": operation["status_url"]})

        @staticmethod
        def _perform_operation(operation, payload) -> None:
            assert api is not None
            try:
                api.execute_operation(operation, payload)
            except Exception:
                # complete() records the failure for polling clients.
                return

        def _operation_get(self, path: str, viewer: str) -> None:
            assert api is not None
            suffix = path.removeprefix("/api/v1/operations/")
            if suffix.endswith("/metadata"):
                owner = suffix.removesuffix("/metadata")

                def read_metadata():
                    result = (
                        api.item_result(*owner.split("/items/", 1), viewer=viewer)
                        if "/items/" in owner
                        else api.operation_result(owner, viewer)
                    )
                    if not isinstance(result, MusicResult):
                        raise InvalidJob("This operation has no Music metadata.")
                    return {
                        "score": result.score,
                        "metadata": result.metadata,
                        "stub": result.stub,
                        "seed": result.seed,
                        "seconds": result.seconds,
                        "sample_rate": result.sample_rate,
                    }

                body, status = self._api_result(read_metadata)
                self._send_json(body, status=status)
                return
            if suffix.endswith("/result"):
                operation_id = suffix.removesuffix("/result")
                if "/items/" in operation_id:
                    owner, index = operation_id.split("/items/", 1)
                    result, status = self._api_result(lambda: api.item_result(owner, index, viewer))
                else:
                    result, status = self._api_result(lambda: api.operation_result(operation_id, viewer))
                if isinstance(result, VideoResult):
                    self._send_video_result(result)
                elif isinstance(result, (MusicResult, SpeechResult)):
                    self._send_voice_result(result)
                else:
                    self._send_json(result, status=status)
                return
            body, status = self._api_result(lambda: api.operation(suffix, viewer))
            self._send_json(body, status=status)

        def _refused_private_key(self) -> bool:
            """The page's own routes keep no owner. A key sent to one of them would start
            shared work, so the route refuses the key and does not drop it."""
            if self.headers.get(PRIVATE_KEY_HEADER) is None:
                return False
            self._send_json({"error": PRIVATE_KEY_ELSEWHERE}, status=400)
            return True

        def _viewer(self) -> str:
            """Validate the caller's key. The API stores its digest and uses the key only for encryption."""
            key = self.headers.get(PRIVATE_KEY_HEADER)
            if key is None:
                return ""
            if not 32 <= len(key) <= 512 or not all("!" <= character <= "~" for character in key):
                raise InvalidJob(f"{PRIVATE_KEY_HEADER} must be 32 to 512 visible ASCII characters.")
            return key

        def _run_voice(self, kind="voice"):
            assert api is not None
            operation = {}

            def run():
                payload = self._read_json()
                operation.update(api.reserve({**payload, "kind": kind}))
                return api.execute_operation(operation, payload)

            result, status = self._api_result(run)
            if not isinstance(result, (SpeechResult, MusicResult)):
                self._send_json(result, status=status)
                return
            self._send_voice_result(
                result, {"X-Studio-Operation": operation["id"], "X-Studio-Completed": str(operation["finished_at"])}
            )

        def _send_voice_result(self, result, headers=None):
            if isinstance(result, MusicResult) and not result.wav:
                self._send_json(
                    {
                        "score": result.score,
                        "metadata": result.metadata,
                        "stub": result.stub,
                        "seed": result.seed,
                        "seconds": result.seconds,
                        "sample_rate": result.sample_rate,
                    },
                    headers=headers,
                )
                return
            headers = {
                **(headers or {}),
                "X-Studio-Seed": str(result.seed),
                "X-Studio-Duration": str(result.seconds),
                "X-Studio-Sample-Rate": str(result.sample_rate),
                "X-Studio-Stub": str(getattr(result, "stub", False)).lower(),
            }
            self._send_bytes(result.wav, content_type="audio/wav", headers=headers)

        def _send_video_result(self, result, headers: dict[str, str] | None = None) -> None:
            headers = dict(headers or {})
            if result.stub:
                self._send_json(
                    {
                        "stub": True,
                        "width": result.width,
                        "height": result.height,
                        "num_frames": result.num_frames,
                        "frame_rate": result.frame_rate,
                        "seed": result.seed,
                        "loras": lora_document(result.loras),
                    },
                    headers=headers,
                )
            elif result.mp4 is None:
                self._send_json({"error": "The video backend returned no MP4 file."}, status=500)
            else:
                if result.seed is not None:
                    headers["X-Studio-Seed"] = str(result.seed)
                if result.loras:
                    headers["X-Studio-Loras"] = json.dumps(lora_document(result.loras))
                self._send_bytes(result.mp4, content_type="video/mp4", headers=headers)

        def _send_shared(self, action, *, success=200, content_type="text/html; charset=utf-8") -> None:
            body, status = self._api_result(action)
            if status != 200:
                self._send_json(body, status=status)
            else:
                self._send(body or "", status=success, content_type=content_type)

        def _api_result(self, action) -> tuple[Any, int]:
            """One answer shape for every API route: the document and its status, or an
            error object and the status that names the failure."""
            try:
                return action(), 200
            except OperationMissing as error:
                return {"error": str(error)}, 404
            except Cancelled:
                return {"error": "Cancelled"}, 409
            except (InvalidJob, UnreadableImage) as error:
                return {"error": str(error)}, 400
            except BackendBusy as error:
                return {"error": str(error)}, 409
            except QueueFull as error:
                return {"error": str(error)}, 429
            except StudioError as error:
                return {"error": str(error)}, 503
            except Exception:
                return unexpected_answer(self.path), 500

        def _run_video(self, mode: str | None = None) -> None:
            if video_controller is None:
                self._send_json({"error": "Video generation is not configured."}, status=503)
                return
            try:
                payload = self._read_json()
                operation = (
                    api.reserve(
                        {**payload, "kind": "video", "mode": mode or payload.get("mode", "generate")},
                        source="ui" if mode is None else "api",
                    )
                    if api
                    else None
                )
                if operation is not None:
                    assert api is not None
                    if mode is None:
                        result = api.complete(
                            operation["id"], lambda: video_controller.run(payload), observed=operation
                        )
                    else:
                        result = api.execute_operation(operation, payload)
                else:
                    result = video_controller.run(payload)
            except Cancelled:
                self._send_json({"cancelled": True})
                return
            except (InvalidJob, UnreadableImage) as error:
                self._send_json({"error": str(error)}, status=400)
                return
            except BackendBusy as error:
                self._send_json({"error": str(error)}, status=409)
                return
            except StudioError as error:
                self._send_json({"error": str(error)}, status=503)
                return
            except Exception:
                self._send_json(unexpected_answer(self.path), status=500)
                return
            headers = {"X-Studio-Operation": operation["id"]} if operation else None
            if headers is not None and operation is not None and operation.get("finished_at") is not None:
                headers["X-Studio-Completed"] = str(operation["finished_at"])
            self._send_video_result(result, headers)

        def _cancel_video(self, via_api: bool = False) -> None:
            if video_controller is None:
                self._send_json({"error": "Video generation is not configured."}, status=503)
                return
            try:
                payload = self._read_json()
                if api is not None:
                    cancelled = api.cancel_video(payload, allow_implicit=via_api)
                else:
                    cancelled = video_controller.cancel(payload)
            except OperationMissing as error:
                self._send_json({"error": str(error)}, status=404)
                return
            except BackendBusy as error:
                self._send_json({"error": str(error)}, status=409)
                return
            except InvalidJob as error:
                self._send_json({"error": str(error)}, status=400)
                return
            if not cancelled:
                self._send_json({"error": "This video render is no longer active."}, status=409)
                return
            self._send("", status=204, content_type="text/plain")

        def _trusted_host(self, *, allow_proxy: bool = True) -> bool:
            hosts = self.headers.get_all("Host", [])
            if len(hosts) != 1 or not isinstance(self.server.server_address, tuple):
                return False
            bound, port = self.server.server_address[:2]
            if bound in ("0.0.0.0", "::"):
                bound = self.connection.getsockname()[0]
            trusted = {f"{bound}:{port}", f"[{bound}]:{port}", f"localhost:{port}"}
            if allow_proxy:
                trusted.update(urlsplit(origin).netloc for origin in allowed_origins)
            return hosts[0] in trusted

        def _from_this_page(self) -> bool:
            """Any site open in the browser can post here. Its page sends its own
            Origin. With DNS rebinding its host name points here, and then its
            Host header names that site. So a POST must name this server in both.

            A proxy such as Tailscale serve
            gives the page an https origin and a host name that this server did not
            bind. Only a configured proxy host and origin can use that exception."""
            if not StudioHandler._trusted_host(self):
                return False
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            if origin is not None and origin in allowed_origins:
                return True
            if origin is not None and origin != f"http://{host}":
                return False
            return StudioHandler._trusted_host(self, allow_proxy=False)

        @staticmethod
        def _outcome(action, as_json: bool = False) -> str:
            try:
                return action()
            except Exception as error:  # every failure reaches the page as one line
                if as_json:
                    return json.dumps({"error": f"{type(error).__name__}: {error}"}, ensure_ascii=False)
                return presenter.failure(error)

        def _normalize_image(self) -> None:
            try:
                contents = self._read_body(MAX_IMAGE_IMPORT_BYTES, "The image size must be between 1 byte and 64 MB.")
                image = ImageImportController().normalize(contents)
            except StudioError as error:
                self._send_json({"error": str(error)}, status=400)
                return
            self._send_bytes(image, 200, "image/png")

        def _read_form(self) -> dict[str, str]:
            try:
                body = self._read_body(
                    MAX_VIDEO_REQUEST_BYTES,
                    f"The form request size must be between 0 bytes and {MAX_VIDEO_REQUEST_MEGABYTES} MB",
                    allow_empty=True,
                ).decode("utf-8")
            except UnicodeDecodeError:
                raise InvalidJob("The form request must contain valid UTF-8") from None
            form = {key: values[0] for key, values in parse_qs(body, keep_blank_values=True).items()}
            form["client_id"] = self.headers.get("X-Studio-Client", "")
            form["library_id"] = self.headers.get("X-Studio-Library", "")
            return form

        def _read_json(self, *, include_identity: bool = True) -> dict:
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                raise InvalidJob("The request must use application/json")
            contents = self._read_body(
                MAX_VIDEO_REQUEST_BYTES,
                f"The request size must be between 1 byte and {MAX_VIDEO_REQUEST_MEGABYTES} MB",
            )
            try:
                payload = json.loads(contents.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise InvalidJob("The request must contain valid JSON") from None
            if not isinstance(payload, dict):
                raise InvalidJob("The request must be a JSON object")
            if include_identity:
                payload["client_id"] = self.headers.get("X-Studio-Client") or payload.get("client_id", "")
                payload["library_id"] = self.headers.get("X-Studio-Library") or payload.get("library_id", "")
            return payload

        def _read_body(self, maximum: int, size_error: str, *, allow_empty: bool = False) -> bytes:
            lengths = self.headers.get_all("Content-Length", [])
            if self.headers.get("Transfer-Encoding") is not None:
                raise InvalidJob("The request must not use Transfer-Encoding")
            if not lengths and allow_empty:
                return b""
            if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
                raise InvalidJob(size_error)
            if len(lengths[0]) > 10:
                raise InvalidJob(size_error)
            length = int(lengths[0])
            minimum = 0 if allow_empty else 1
            if not minimum <= length <= maximum:
                raise InvalidJob(size_error)
            return self._read_body_bytes(length)

        def _read_body_bytes(self, length: int) -> bytes:
            deadline = time.monotonic() + body_read_seconds(length)
            previous_timeout = self.connection.gettimeout()
            contents = bytearray()
            ran_out = False
            try:
                while len(contents) < length:
                    left = deadline - time.monotonic()
                    if left <= 0:
                        ran_out = True
                        raise TimeoutError
                    # The socket waits no longer than the idle timeout, so a client that
                    # stops altogether is told so in seconds, not minutes.
                    self.connection.settimeout(min(left, REQUEST_READ_TIMEOUT_SECONDS))
                    chunk = self.rfile.read1(min(length - len(contents), 64 * 1024))
                    if not chunk:
                        raise InvalidJob("The request body is shorter than Content-Length")
                    contents.extend(chunk)
            except TimeoutError:
                if ran_out:
                    raise InvalidJob(
                        f"The request body did not arrive within {body_read_seconds(length):.0f} seconds, "
                        "which is the time this size is given at the slowest supported rate"
                    ) from None
                raise InvalidJob(
                    "The request body stopped arriving. The read deadline is "
                    f"{REQUEST_READ_TIMEOUT_SECONDS:.0f} seconds without a byte"
                ) from None
            finally:
                self.connection.settimeout(previous_timeout)
            return bytes(contents)

        def _send_page_asset(self, name: str) -> None:
            """One module or stylesheet out of web/. Two rules keep it to those:
            the resolved path stays inside web/, so `..` cannot escape it, and
            only .js and .css are handed out. Without both, every document in
            that directory would be readable."""
            asset = (WEB / name).resolve()
            if not asset.is_relative_to(WEB) or asset.suffix not in PAGE_ASSETS or not asset.is_file():
                self._send("not found", status=404, content_type="text/plain")
                return
            self._send(asset.read_text(encoding="utf-8"), content_type=PAGE_ASSETS[asset.suffix])

        def _send(self, body: str, status: int = 200, content_type: str = "text/html; charset=utf-8"):
            self._send_bytes(body.encode("utf-8"), status, content_type)

        def _send_json(self, payload: dict, status: int = 200, headers: dict[str, str] | None = None) -> None:
            self._send_bytes(
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                status,
                "application/json; charset=utf-8",
                headers,
            )

        def _send_bytes(
            self,
            payload: bytes,
            status: int = 200,
            content_type: str = "application/octet-stream",
            headers: dict[str, str] | None = None,
        ):
            self.connection.settimeout(self._response_timeout)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            # The studio serves files that change between restarts, and it sent no cache
            # header at all, so a browser was free to keep an old page.css or module and show
            # a form the server no longer had. Nothing here is worth caching.
            self.send_header("Cache-Control", "no-store")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(payload)

    return StudioHandler
