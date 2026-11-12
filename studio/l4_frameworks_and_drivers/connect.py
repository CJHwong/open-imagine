"""Share the studio with a phone over a dumbpipe ticket.

A transport starts a listener on 127.0.0.1 and publishes a ticket. The ticket is a
secret: anyone who holds it reaches this studio. The identity file holds the key that
makes the ticket stable, so it is created with owner-only access and never logged.
"""

import io
import json
import os
import re
import secrets
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

import qrcode
import qrcode.image.svg

from studio.l1_entities.errors import StudioError

TICKET = re.compile(r"\b(?:endpoint|node)[A-Za-z0-9]+")
TICKET_MIN_LENGTH = 40
PAIR_SCHEME = "openimagine"
BUNDLED_BINARY = Path(__file__).with_name("bin") / "openimagine-pipe"


@dataclass(frozen=True)
class ConnectStatus:
    enabled: bool
    running: bool
    transport: str
    ticket: str
    port: int
    error: str = ""


class ConnectTransport(Protocol):
    def devices(self) -> list[dict[str, object]]: ...
    def preflight(self) -> None: ...
    def start(self) -> ConnectStatus: ...
    def refresh(self) -> ConnectStatus: ...
    def stop(self) -> None: ...
    def status(self) -> ConnectStatus: ...


class DumbpipeTransport:
    """Run `dumbpipe` for this studio. One listener owns the GPU's front door."""

    name = "dumbpipe"

    def __init__(
        self,
        binary: str | None,
        identity_path: Path,
        studio_port: int,
        *,
        settle: float = 0.3,
        wait: float = 5.0,
    ):
        self._binary = str(binary or BUNDLED_BINARY)
        self._identity_path = identity_path
        self._studio_port = studio_port
        self._settle = settle
        self._wait = wait
        self._lock = threading.RLock()
        self._listener: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._devices: dict[str, dict] = {}
        self._ticket = ""
        self._error = ""

    def start(self) -> ConnectStatus:
        with self._lock:
            if self._running():
                return self.status()
            self._error = ""
            self._ticket = ""
            self._devices = {}
            try:
                secret = self._identity()
                self._ticket = self._stable_ticket(secret)
                self._listener = subprocess.Popen(
                    [
                        self._binary,
                        "listen",
                        "--port",
                        str(self._studio_port),
                        "--identity",
                        str(self._identity_path),
                    ],
                    env={**os.environ, "IROH_SECRET": secret, "RUST_LOG": "error"},
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
                self._reader = threading.Thread(target=self._read_status, args=(self._listener,), daemon=True)
                self._reader.start()
                time.sleep(self._settle)
                if self._listener.poll() is not None:
                    raise StudioError(f"dumbpipe stopped at once with code {self._listener.returncode}.")
            except (OSError, subprocess.SubprocessError, StudioError) as error:
                self.stop()
                self._error = str(error)
            return self.status()

    def devices(self) -> list[dict[str, object]]:
        """Every endpoint that reached this listener, newest activity first."""
        with self._lock:
            now = time.time()
            found = []
            for identifier, state in self._devices.items():
                seen = max(0.0, now - state["at"])
                found.append(
                    {
                        "id": identifier,
                        "active": bool(state["active"]) or seen < 30,
                        "seen": round(seen),
                    }
                )
            found.sort(key=lambda one: cast(float, one["seen"]))
            return found

    def _read_status(self, listener: subprocess.Popen) -> None:
        if listener.stdout is None:
            return
        for line in listener.stdout:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue  # the ticket line, or a log line
            if not isinstance(message, dict) or message.get("kind") != "device":
                continue
            identifier = message.get("id")
            if not isinstance(identifier, str):
                continue
            with self._lock:
                self._devices[identifier] = {
                    "active": message.get("state") == "active",
                    "at": float(message.get("at", time.time())),
                }

    def preflight(self) -> None:
        """Refuse to turn the feature on when this machine cannot run the pipe."""
        binary = Path(self._binary)
        if not binary.is_file():
            raise StudioError(f"The phone transport is missing at {binary}.")
        self._stable_ticket(self._identity())

    def refresh(self) -> ConnectStatus:
        """Rotate the identity, restart the listener and invalidate every old phone."""
        with self._lock:
            self.stop()
            try:
                self._identity_path.unlink(missing_ok=True)
            except OSError as error:
                self._error = f"Studio could not rotate the dumbpipe identity: {error}."
                return self.status()
            return self.start()

    def stop(self) -> None:
        with self._lock:
            listener = self._listener
            self._listener = None
            if listener is None:
                return
            if listener.stdin is not None:
                listener.stdin.close()
            # A rotate must drop established connections at once. The listener
            # holds no state that needs a graceful exit.
            if listener.poll() is None:
                listener.kill()
            listener.wait()

    def status(self) -> ConnectStatus:
        with self._lock:
            return ConnectStatus(
                enabled=True,
                running=self._running(),
                transport=self.name,
                ticket=self._ticket,
                port=self._studio_port,
                error=self._error,
            )

    def _running(self) -> bool:
        return self._listener is not None and self._listener.poll() is None

    def _identity(self) -> str:
        try:
            if self._identity_path.exists():
                secret = self._identity_path.read_text(encoding="ascii").strip()
                if not re.fullmatch(r"[0-9a-f]{64}", secret):
                    raise StudioError(f"The dumbpipe identity at {self._identity_path.name} is not 32 bytes of hex.")
                return secret
            self._identity_path.parent.mkdir(parents=True, exist_ok=True)
            secret = secrets.token_hex(32)
            descriptor = os.open(self._identity_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="ascii") as file:
                file.write(secret + "\n")
            return secret
        except OSError as error:
            raise StudioError(f"Studio could not read or create its dumbpipe identity: {error}.") from error

    def _stable_ticket(self, secret: str) -> str:
        completed = subprocess.run(
            [self._binary, "generate-ticket"],
            env={**os.environ, "IROH_SECRET": secret},
            capture_output=True,
            text=True,
            timeout=self._wait,
            check=False,
        )
        if completed.returncode != 0:
            raise StudioError(f"dumbpipe could not make a ticket: {completed.stderr.strip() or 'no reason given'}.")
        ticket = _find_ticket(completed.stdout)
        if ticket is None:
            raise StudioError("dumbpipe printed no ticket.")
        return ticket


def _find_ticket(output: str) -> str | None:
    tickets = [word for word in TICKET.findall(output) if len(word) > TICKET_MIN_LENGTH]
    return max(tickets, key=len) if tickets else None


def pair_url(status: ConnectStatus) -> str:
    """What the QR carries: the ticket and the loopback port the phone must bind."""
    return f"{PAIR_SCHEME}://pair?v=1&ticket={status.ticket}&port={status.port}"


def qr_svg(text: str) -> str:
    image = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage)
    buffer = io.BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode("utf-8")


def qr_terminal(text: str) -> str:
    code = qrcode.QRCode(border=1)
    code.add_data(text)
    code.make(fit=True)
    buffer = io.StringIO()
    code.print_ascii(out=buffer, invert=True)
    return buffer.getvalue()
