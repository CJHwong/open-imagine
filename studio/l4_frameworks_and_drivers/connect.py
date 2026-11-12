"""Share the studio with a phone over a dumbpipe ticket.

A transport starts a listener on 127.0.0.1 and publishes a ticket. The ticket is a
secret: anyone who holds it reaches this studio. The identity file holds the key that
makes the ticket stable, so it is created with owner-only access and never logged.
"""

import io
import os
import re
import secrets
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import qrcode

from studio.l1_entities.errors import StudioError

TICKET = re.compile(r"\b(?:endpoint|node)[A-Za-z0-9]+")
TICKET_MIN_LENGTH = 40
PAIR_SCHEME = "openimagine"


@dataclass(frozen=True)
class ConnectStatus:
    enabled: bool
    running: bool
    transport: str
    ticket: str
    port: int
    error: str = ""


class ConnectTransport(Protocol):
    def start(self) -> ConnectStatus: ...
    def stop(self) -> None: ...
    def status(self) -> ConnectStatus: ...


class DumbpipeTransport:
    """Run `dumbpipe` for this studio. One listener owns the GPU's front door."""

    name = "dumbpipe"

    def __init__(
        self,
        binary: str,
        identity_path: Path,
        studio_port: int,
        *,
        settle: float = 0.3,
        wait: float = 5.0,
    ):
        self._binary = binary
        self._identity_path = identity_path
        self._studio_port = studio_port
        self._settle = settle
        self._wait = wait
        self._lock = threading.RLock()
        self._listener: subprocess.Popen | None = None
        self._ticket = ""
        self._error = ""

    def start(self) -> ConnectStatus:
        with self._lock:
            if self._running():
                return self.status()
            self._error = ""
            self._ticket = ""
            try:
                secret = self._identity()
                self._ticket = self._stable_ticket(secret)
                self._listener = subprocess.Popen(
                    [self._binary, "listen-tcp", "--host", f"127.0.0.1:{self._studio_port}"],
                    env={**os.environ, "IROH_SECRET": secret, "RUST_LOG": "error"},
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                time.sleep(self._settle)
                if self._listener.poll() is not None:
                    raise StudioError(f"dumbpipe stopped at once with code {self._listener.returncode}.")
            except (OSError, subprocess.SubprocessError, StudioError) as error:
                self.stop()
                self._error = str(error)
            return self.status()

    def stop(self) -> None:
        with self._lock:
            listener = self._listener
            self._listener = None
            if listener is None:
                return
            if listener.poll() is None:
                listener.terminate()
                try:
                    listener.wait(timeout=self._wait)
                except subprocess.TimeoutExpired:
                    listener.kill()
                    listener.wait(timeout=self._wait)

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


def qr_terminal(text: str) -> str:
    code = qrcode.QRCode(border=1)
    code.add_data(text)
    code.make(fit=True)
    buffer = io.StringIO()
    code.print_ascii(out=buffer, invert=True)
    return buffer.getvalue()
