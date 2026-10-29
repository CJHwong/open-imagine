"""Install the pinned, Torch-free YuE2 transcription and instrumental workflow support.

Run with Studio's Python: uv run python scripts/setup_yue2_workflows.py
This only installs packages and downloads files; it never loads a model or uses the GPU.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path

RUNTIME_REVISION = "c5b5a8190f78c74aa671a4caa19dae8b8e04b3d8"
SOURCE_REVISION = "1647252d68b70cbead046ffd3f7caf036dde47ee"
SOURCE_ROOT = "skills/yue2-music/instrumental/scripts"
SOURCE_FILES = {
    "abc_tools.py": "88b66e5bb73a4ba3633ae4c7a417118806e0e606",
    "common.py": "4b6c2d502f131539b26069753b6e4482eb2db280",
    "compile_score.py": "d20e19965eb58437af0415ebf4816a0070732e23",
    "instrumentalize.py": "dfd008b3537967164dd3a4aa8c0401284dcdb679",
}
MODELS = {
    "m-a-p/SheetSage2": "eab522a8168e8b8b8c4856bf8609cd86198f01fe",
    "m-a-p/MERT-v2-FullSong": "d8ba1c745e733b3908ce6ad16ebeb17ac7600a42",
}
DEPENDENCIES = ("mido==1.3.3", "mir-eval==0.8.2", "pretty-midi==0.2.11.post0", "scipy>=1.13,<2")


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data, usedforsecurity=False).hexdigest()


def fetch_source(name: str, expected: str) -> bytes:
    url = f"https://raw.githubusercontent.com/multimodal-art-projection/YuE/{SOURCE_REVISION}/{SOURCE_ROOT}/{name}"
    with urllib.request.urlopen(url, timeout=60) as answer:
        data = answer.read()
    if git_blob_sha(data) != expected:
        raise ValueError(f"Upstream source integrity mismatch: {name}")
    return data


def adapt_imports(source: bytes) -> bytes:
    text = source.decode("utf-8")
    for module in ("abc_tools", "common", "compile_score"):
        text = text.replace(f"from {module} import ", f"from .{module} import ")
    return text.encode("utf-8")


def target_info(python: Path) -> dict:
    code = "import importlib.util,json,sysconfig; print(json.dumps({'purelib':sysconfig.get_path('purelib'),'torch':importlib.util.find_spec('torch') is not None}))"
    return json.loads(subprocess.check_output([str(python), "-c", code], text=True))


def install_helpers(purelib: Path) -> Path:
    # Prepare and verify every upstream file before writing the isolated namespace.
    prepared = {name: adapt_imports(fetch_source(name, expected)) for name, expected in SOURCE_FILES.items()}
    license_url = f"https://raw.githubusercontent.com/multimodal-art-projection/YuE/{SOURCE_REVISION}/LICENSE"
    with urllib.request.urlopen(license_url, timeout=60) as answer:
        license_text = answer.read()
    destination = purelib / "lyra/music_tools/instrumental_support"
    destination.mkdir(parents=True, exist_ok=True)
    manifest = {
        "repository": "https://github.com/multimodal-art-projection/YuE",
        "revision": SOURCE_REVISION,
        "directory": SOURCE_ROOT,
        "license": "Apache-2.0",
        "modification": "Sibling imports made relative; source logic is unchanged.",
        "files": {},
    }
    for name, data in prepared.items():
        (destination / name).write_bytes(data)
        manifest["files"][name] = {
            "git_blob_sha1": SOURCE_FILES[name],
            "installed_sha256": hashlib.sha256(data).hexdigest(),
        }
    (destination / "__init__.py").write_text('"""YuE2 instrumental score helpers; see SOURCES.json and LICENSE."""\n')
    (destination / "LICENSE").write_bytes(license_text)
    (destination / "SOURCES.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return destination


def download_models(python: Path, cache_dir: Path) -> dict:
    # Execute in the configured runtime so no packages are added to Studio's own venv.
    script = """import json,sys
from pathlib import Path
from huggingface_hub import snapshot_download
models=json.loads(sys.argv[1]); cache=Path(sys.argv[2]).expanduser(); result={}
for repo, revision in models.items():
    path=Path(snapshot_download(repo_id=repo,revision=revision,cache_dir=cache,allow_patterns=['config.json','model.safetensors','LICENSE']))
    result[repo]={'revision':revision,'path':str(path),'bytes':sum((path/name).stat().st_size for name in ['config.json','model.safetensors'])}
print(json.dumps(result))
"""
    return json.loads(
        subprocess.check_output([str(python), "-c", script, json.dumps(MODELS), str(cache_dir)], text=True)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python",
        type=Path,
        default=Path.home() / f"Library/Caches/yue2-mlx-runtime/{RUNTIME_REVISION}/venv/bin/python",
    )
    parser.add_argument("--cache-dir", type=Path, default=Path.home() / "Library/Caches/models/yue2-transcription")
    parser.add_argument(
        "--skip-download", action="store_true", help="Install dependencies and verified helpers without model downloads"
    )
    args = parser.parse_args()
    python = args.python.expanduser().absolute()
    info = target_info(python)
    if info["torch"]:
        raise RuntimeError("The configured runtime contains Torch; use the isolated Torch-free YuE2 runtime.")
    subprocess.run(["uv", "pip", "install", "--python", str(python), *DEPENDENCIES], check=True)
    if target_info(python)["torch"]:
        raise RuntimeError("Transcription installation unexpectedly introduced Torch.")
    helpers = install_helpers(Path(info["purelib"]))
    probe = "from lyra.music_tools.instrumental_support.instrumentalize import convert_score; from lyra.transcription.pipeline import transcribe; print('Verified instrumental and transcription imports (no model loaded).')"
    subprocess.run([str(python), "-c", probe], check=True)
    result = {"python": str(python), "helpers": str(helpers), "torch": False, "models": {}}
    if not args.skip_download:
        result["models"] = download_models(python, args.cache_dir.expanduser())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
