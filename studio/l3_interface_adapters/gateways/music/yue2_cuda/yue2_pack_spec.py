"""What a YuE2 NVFP4 pack must match, readable without torch.

The child imports this beside itself and the studio imports it as a package module, so both
read one declaration. The studio compares a pack's `pack.json` with it when the model is
picked, and the child compares it again before it loads the pack.
"""

import hashlib
from pathlib import Path

PACK_FORMAT = 1

# The two torchao options the lyric stages quantize with. They are torchao 0.18.0's own
# defaults, named here so that a pack records a decision and not whatever a later release
# defaults to.
NVFP4_OPTIONS = {"use_triton_kernel": True, "use_dynamic_per_tensor_scale": True}

# package -> the `__version__` its pin in the child's header installs. A pin names the
# release and the wheel names its build: torch==2.15.0 comes from PyPI, whose Linux wheels
# report 2.15.0+cu132, and mslk==1.4.0 resolves to the cu130 index's 1.4.0+cu130. The child
# refuses to run when what it imported says otherwise, so a pack's versions are known
# before it starts.
RUNTIME_VERSIONS = {"torch": "2.15.0+cu132", "torchao": "0.18.0", "mslk": "1.4.0+cu130"}


def expected_manifest(model_name: str, source: str) -> dict:
    """Every field of `pack.json` that must match before the pack is trusted."""
    return {
        "format": PACK_FORMAT,
        "model": model_name,
        "versions": dict(RUNTIME_VERSIONS),
        "source": source,
        "block_size": 16,
        "orig_dtype": "torch.bfloat16",
        "is_swizzled_scales": True,
        "use_triton_kernel": NVFP4_OPTIONS["use_triton_kernel"],
        "act_quant": {
            "block_size": 16,
            "is_swizzled_scales": True,
            "use_triton_kernel": NVFP4_OPTIONS["use_triton_kernel"],
            "use_dynamic_per_tensor_scale": NVFP4_OPTIONS["use_dynamic_per_tensor_scale"],
        },
    }


def source_revision(model: str) -> str:
    """The committed snapshot this model resolves to, when this machine can name one.

    The cache writes `refs/main`, and that is the commit the engine's loader takes. Counting
    snapshot directories answered `unknown` as soon as a second one was cached, which let a
    pack built from one revision serve another. A local folder is named by each file's
    path, size and modification time: a rewrite changes the identity even at the same
    length, and hashing every shard on every start would cost minutes.
    """
    try:
        from huggingface_hub.constants import HF_HUB_CACHE
    except ImportError:  # the unit tests run without the engine's packages
        HF_HUB_CACHE = ""
    if HF_HUB_CACHE:
        root = Path(HF_HUB_CACHE) / f"models--{model.replace('/', '--')}"
        reference = root / "refs" / "main"
        if reference.is_file():
            commit = reference.read_text().strip()
            if (root / "snapshots" / commit).is_dir():
                return commit
        snapshots = root / "snapshots"
        if snapshots.is_dir():
            commits = sorted(one.name for one in snapshots.iterdir() if one.is_dir())
            if len(commits) == 1:
                return commits[0]
    local = Path(model).expanduser()
    if local.is_dir():
        digest = hashlib.sha256()
        for path in sorted(local.rglob("*")):
            if path.is_file():
                stat = path.stat()
                digest.update(f"{path.relative_to(local)}:{stat.st_size}:{stat.st_mtime_ns}".encode())
        return "local:" + digest.hexdigest()[:16]
    return "unknown"


def version_mismatch(found: dict) -> str | None:
    """Why the imported packages are not the declared ones, or None when they are."""
    wrong = [
        f"{name} is {found.get(name)}, the header installs {wanted}"
        for name, wanted in RUNTIME_VERSIONS.items()
        if found.get(name) != wanted
    ]
    return "; ".join(wrong) or None
