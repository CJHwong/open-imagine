"""Fail when plugins/open-imagine changed between two commits and its version did not go up.

    python3 .github/scripts/check_plugin_version.py <base sha> <head sha>

Both manifests must carry the same version: Claude Code reads one and Codex the other.
"""

import json
import subprocess
import sys

PLUGIN = "plugins/open-imagine"
MANIFESTS = (f"{PLUGIN}/.claude-plugin/plugin.json", f"{PLUGIN}/.codex-plugin/plugin.json")


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def version_at(sha: str, path: str) -> str | None:
    shown = git("show", f"{sha}:{path}")
    return json.loads(shown.stdout)["version"] if shown.returncode == 0 else None


def numeric(version: str) -> list[int] | None:
    parts = version.split(".")
    return [int(part) for part in parts] if all(part.isdigit() for part in parts) else None


def main(base: str, head: str) -> int:
    heads = {path: version_at(head, path) for path in MANIFESTS}
    head_version = heads[MANIFESTS[0]]
    if head_version is None or set(heads.values()) != {head_version}:
        print(f"::error::the two plugin manifests must exist and carry the same version: {heads}")
        return 1
    # A push that creates the branch has an all-zero base, and a new plugin has no base manifest.
    if set(base) == {"0"} or (base_version := version_at(base, MANIFESTS[0])) is None:
        print(f"pass: no earlier version to compare ({head_version})")
        return 0
    changed = git("diff", "--name-only", base, head, "--", PLUGIN)
    if changed.returncode != 0:
        print(f"::error::git diff failed: {changed.stderr.strip()}")
        return 1
    if not changed.stdout.strip():
        print("pass: the plugin did not change")
        return 0
    old, new = numeric(base_version), numeric(head_version)
    if old is None or new is None:
        print(f"::error::{base_version} or {head_version} is not a plain numeric version such as 0.2.0")
        return 1
    if new <= old:
        print(
            f"::error file={MANIFESTS[0]}::the plugin changed but its version went {base_version} -> "
            f"{head_version}. Raise it in both manifests, from the version on main."
        )
        return 1
    print(f"pass: {base_version} -> {head_version}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
