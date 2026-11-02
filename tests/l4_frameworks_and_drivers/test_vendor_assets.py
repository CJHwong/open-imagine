"""The page serves its own libraries, and the manifest pins what it serves."""

import hashlib
import json
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "studio" / "l4_frameworks_and_drivers" / "web"
VENDOR = WEB / "vendor"
OUTSIDE = ("cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com", "esm.sh")
NAMES = ("lit.js", "abcjs.js", "lame.min.js", "htmx.min.js", "swagger-ui-bundle.js", "swagger-ui.css")


def test_every_vendor_file_matches_its_manifest_digest():
    manifest = json.loads((VENDOR / "MANIFEST.json").read_text())
    for entry in manifest["files"]:
        data = (VENDOR / entry["file"]).read_bytes()
        assert len(data) == entry["bytes"], entry["file"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["file"]


def test_the_page_reaches_no_cdn():
    offenders = []
    for path in WEB.rglob("*"):
        if not path.is_file() or "vendor" in path.parts or path.suffix not in {".js", ".html"}:
            continue
        text = path.read_text()
        offenders.extend((str(path.relative_to(WEB)), host) for host in OUTSIDE if host in text)
    assert not offenders, offenders


def test_every_page_reference_has_a_vendored_file():
    missing = []
    for path in WEB.rglob("*"):
        if not path.is_file() or path.suffix not in {".js", ".html"}:
            continue
        text = path.read_text()
        missing.extend(
            (str(path.relative_to(WEB)), name)
            for name in NAMES
            if "/page/vendor/" + name in text and not (VENDOR / name).exists()
        )
    assert not missing, missing
