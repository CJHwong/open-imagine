import stat

from studio.l4_frameworks_and_drivers.connect import (
    ConnectStatus,
    DumbpipeTransport,
    pair_url,
)

TICKET = "endpoint" + "a" * 60


def fake_binary(tmp_path, body: str):
    path = tmp_path / "dumbpipe"
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return path


def scripted(tmp_path, listener_exit: int = 0) -> DumbpipeTransport:
    listener = "exec sleep 30" if listener_exit == 0 else f"exit {listener_exit}"
    binary = fake_binary(
        tmp_path,
        f'case "$1" in\n'
        f'  generate-ticket) echo "using secret key $IROH_SECRET"; echo "{TICKET}";;\n'
        f"  listen-tcp) {listener};;\n"
        f"esac\n",
    )
    return DumbpipeTransport(
        str(binary),
        tmp_path / "identity",
        8765,
        settle=0.05,
        wait=1.0,
    )


def test_a_transport_creates_an_owner_only_identity_and_reports_a_running_ticket(tmp_path):
    transport = scripted(tmp_path)

    status = transport.start()

    assert status.running and status.ticket == TICKET and status.port == 8765
    identity = tmp_path / "identity"
    assert stat.S_IMODE(identity.stat().st_mode) == 0o600
    assert len(identity.read_text().strip()) == 64
    assert identity.read_text().strip() != TICKET
    transport.stop()
    assert not transport.status().running


def test_a_second_start_keeps_the_first_listener(tmp_path):
    transport = scripted(tmp_path)
    first = transport.start()

    second = transport.start()

    assert first == second
    transport.stop()


def test_a_missing_binary_is_reported_without_stopping_the_studio(tmp_path):
    transport = DumbpipeTransport(str(tmp_path / "missing"), tmp_path / "identity", 8765, settle=0.01)

    status = transport.start()

    assert not status.running and status.error


def test_a_failed_ticket_is_reported(tmp_path):
    binary = fake_binary(tmp_path, 'case "$1" in generate-ticket) echo "no ticket" >&2; exit 4;; esac\n')
    transport = DumbpipeTransport(str(binary), tmp_path / "identity", 8765, settle=0.01)

    status = transport.start()

    assert not status.running and "no ticket" in status.error


def test_a_listener_that_exits_at_once_is_reported(tmp_path):
    transport = scripted(tmp_path, listener_exit=3)

    status = transport.start()

    assert not status.running and "code 3" in status.error


def test_a_bad_identity_file_is_refused(tmp_path):
    (tmp_path / "identity").write_text("not hex\n")
    transport = scripted(tmp_path)

    status = transport.start()

    assert not status.running and "32 bytes of hex" in status.error


def test_stopping_a_transport_that_never_started_is_safe(tmp_path):
    DumbpipeTransport("dumbpipe", tmp_path / "identity", 8765).stop()


def test_the_pair_url_carries_the_ticket_and_the_port():
    status = ConnectStatus(True, True, "dumbpipe", TICKET, 8765)

    assert pair_url(status) == f"openimagine://pair?v=1&ticket={TICKET}&port=8765"


def test_an_existing_identity_is_reused_across_restarts(tmp_path):
    transport = scripted(tmp_path)
    first = transport.start()
    secret = (tmp_path / "identity").read_text()
    transport.stop()

    second = transport.start()

    assert second.ticket == first.ticket
    assert (tmp_path / "identity").read_text() == secret
    transport.stop()


def test_an_identity_that_cannot_be_created_is_reported(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a folder")
    transport = DumbpipeTransport(str(tmp_path / "dumbpipe"), blocker / "identity", 8765, settle=0.01)

    status = transport.start()

    assert not status.running and "could not read or create" in status.error


def test_dumbpipe_that_prints_no_ticket_is_reported(tmp_path):
    binary = fake_binary(tmp_path, 'case "$1" in generate-ticket) echo "nothing useful";; esac\n')
    transport = DumbpipeTransport(str(binary), tmp_path / "identity", 8765, settle=0.01)

    status = transport.start()

    assert not status.running and "printed no ticket" in status.error


def test_stop_kills_a_listener_that_ignores_termination(tmp_path):
    binary = fake_binary(
        tmp_path,
        f'case "$1" in\n  generate-ticket) echo "{TICKET}";;\n  listen-tcp) trap \'\' TERM; exec sleep 30;;\nesac\n',
    )
    transport = DumbpipeTransport(str(binary), tmp_path / "identity", 8765, settle=0.05, wait=1.0)
    assert transport.start().running

    transport.stop()

    assert not transport.status().running
