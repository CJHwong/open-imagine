"""Print the parity run: both engines side by side, then every case that is not done.

The missing list is the point. A measurement campaign fails quietly when one case is skipped,
so this names each one rather than leaving a blank cell to notice.

Two figures belong together only when both machines ran the same campaign. This prints the
manifest of each machine, names every case whose record came from another campaign, and
prints the operation's own time rather than a wall clock that includes a queue and a fetch.
"""

import argparse
import json
from pathlib import Path

from run_matrix import fingerprint

GROUPS = (
    ("Image", ("qwen21_turbo", "minimax_h3_image")),
    ("Video", ("ltx25",)),
    ("Voice", ("drama3",)),
    ("Music", ("yue2",)),
)
MACHINES = ("cuda", "mlx")
# The fields two machines must agree on before their figures describe the same thing.
SHARED = ("git", "assets")


def load(path: Path) -> dict:
    picked = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            record = json.loads(line)
            picked[record["id"]] = record
    return picked


def records_for(work: Path, machine: str) -> dict:
    """The run's results, with the warm-up pass overriding where it exists."""
    base = load(work / f"results-{machine}.jsonl")
    base.update(load(work / f"warm-{machine}.jsonl"))
    return base


def manifest_for(work: Path, machine: str) -> dict:
    path = work / f"campaign-{machine}.json"
    return json.loads(path.read_text()) if path.is_file() else {}


def cell(record: dict | None, expected: str) -> str:
    if record is None:
        return "not run"
    if record["status"] != "succeeded":
        return record["status"]
    if record.get("fingerprint") != expected:
        return "other campaign"
    seconds = record.get("active", record["seconds"])
    return f"{seconds:.1f}"


def provenance(work: Path, manifests: dict) -> list[str]:
    """The lines that say whether the two columns describe the same thing."""
    lines = []
    for machine in MACHINES:
        manifest = manifests[machine]
        if not manifest:
            lines.append(f"- {machine}: no campaign manifest. Its figures carry no revision.")
            continue
        lines.append(f"- {machine}: {manifest.get('git', 'unknown')} on {manifest.get('platform', 'unknown')}")
    for field in SHARED:
        values = {
            machine: json.dumps(manifest.get(field), sort_keys=True)
            for machine, manifest in manifests.items()
            if manifest
        }
        if len(set(values.values())) > 1:
            lines.append(f"- **The machines differ in {field}.** The columns are not comparable.")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", default="/tmp/parity")
    arguments = parser.parse_args()
    work = Path(arguments.work)
    matrix = [json.loads(line) for line in (work / "matrix.jsonl").read_text().splitlines()]
    manifests = {machine: manifest_for(work, machine) for machine in MACHINES}
    sides = {machine: records_for(work, machine) for machine in MACHINES}

    def expected(case: dict, machine: str) -> str:
        manifest = manifests[machine]
        return fingerprint(case, manifest) if manifest else ""

    by_id = {case["id"]: case for case in matrix}
    print("### Provenance\n")
    print("\n".join(provenance(work, manifests)))

    for title, prefixes in GROUPS:
        cases = [case["id"] for case in matrix if case["id"].split("/")[0] in prefixes]
        if not cases:
            continue
        print(f"\n### {title}\n")
        print("| Case | M5 Pro (s) | DGX Spark (s) |")
        print("|---|---|---|")
        for case in cases:
            print(
                f"| `{case}` | {cell(sides['mlx'].get(case), expected(by_id[case], 'mlx'))} "
                f"| {cell(sides['cuda'].get(case), expected(by_id[case], 'cuda'))} |"
            )

    print("\n### Coverage\n")
    missing = 0
    for case in by_id:
        absent = [machine for machine in MACHINES if sides[machine].get(case, {}).get("status") != "succeeded"]
        if absent:
            missing += 1
            print(f"- `{case}`: {', '.join(absent)}")
    print(f"\n{len(by_id) - missing} of {len(by_id)} cases succeeded on both engines")
    for machine in MACHINES:
        failed = [case for case, record in sides[machine].items() if record["status"] != "succeeded"]
        print(f"{machine}: {len(failed)} did not succeed")
        for case in sorted(failed):
            print(f"   {case}: {sides[machine][case]['status']} {sides[machine][case].get('error', '')[:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
