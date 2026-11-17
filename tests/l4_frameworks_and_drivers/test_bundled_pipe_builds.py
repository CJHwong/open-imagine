"""The bundled pipe builds, checked against the record that says what they are.

A binary from another platform starts nothing and answers "Exec format error", which reads
as a broken transport. The record names the source, the toolchain and the digest of each
build, so a swapped file, a stale digest or a binary for the wrong architecture fails here
rather than on a phone.
"""

import hashlib
import json

from studio.l4_frameworks_and_drivers import connect
from studio.l4_frameworks_and_drivers.connect import bundled_binary

DIRECTORY = connect.BUNDLED_DIRECTORY
RECORD = DIRECTORY / "BUILDS.json"
MACHO_MAGIC = b"\xcf\xfa\xed\xfe"


def record() -> dict:
    return json.loads(RECORD.read_text())


def test_every_bundle_in_the_folder_is_recorded():
    listed = {one["file"] for one in record()["builds"].values()}

    assert {path.name for path in DIRECTORY.iterdir() if path.is_file()} - {"BUILDS.json"} == listed


def test_each_recorded_digest_is_the_digest_of_the_file():
    for platform, build in record()["builds"].items():
        data = (DIRECTORY / build["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == build["sha256"], f"{platform} is not the build it claims"


def test_each_build_is_for_the_architecture_its_name_names():
    for platform, build in record()["builds"].items():
        header = (DIRECTORY / build["file"]).read_bytes()[:20]
        if platform.startswith("darwin"):
            assert header[:4] == MACHO_MAGIC, f"{platform} is not a Mach-O binary"
        else:
            assert header[:4] == b"\x7fELF", f"{platform} is not an ELF binary"
            assert int.from_bytes(header[18:20], "little") == 183, f"{platform} is not an aarch64 build"


def test_the_transport_picks_the_build_that_is_recorded_for_this_machine(monkeypatch, tmp_path):
    record_for = record()
    (tmp_path / "BUILDS.json").write_text("{}")
    for build in record_for["builds"].values():
        (tmp_path / build["file"]).write_bytes(b"")
    monkeypatch.setattr(connect, "BUNDLED_DIRECTORY", tmp_path)
    monkeypatch.setattr(connect.platform, "system", lambda: "Linux")
    monkeypatch.setattr(connect.platform, "machine", lambda: "aarch64")

    assert bundled_binary().name == record_for["builds"]["linux-aarch64"]["file"]
