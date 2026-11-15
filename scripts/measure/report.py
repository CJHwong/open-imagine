"""Print the parity run: both engines side by side, then every case that is not done.

The missing list is the point. A measurement campaign fails quietly when one case is skipped,
so this names each one rather than leaving a blank cell to notice.
"""

import argparse
import json
from pathlib import Path

GROUPS = (
    ("Image", ("qwen21_turbo", "minimax_h3_image")),
    ("Video", ("ltx25",)),
    ("Voice", ("drama3",)),
    ("Music", ("yue2",)),
)
MACHINES = ("cuda", "mlx")


def load(path: Path) -> dict:
    records = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            record = json.loads(line)
            records[record["id"]] = record
    return records


def records_for(work: Path, machine: str) -> dict:
    """The run's results, with the warm-up pass overriding where it exists."""
    base = load(work / f"results-{machine}.jsonl")
    base.update(load(work / f"warm-{machine}.jsonl"))
    return base


def cell(record: dict | None) -> str:
    if record is None:
        return "not run"
    if record["status"] != "succeeded":
        return f"{record['status']}"
    return f"{record['seconds']:.1f}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", default="/tmp/parity")
    arguments = parser.parse_args()
    work = Path(arguments.work)
    matrix = [json.loads(line)["id"] for line in (work / "matrix.jsonl").read_text().splitlines()]
    sides = {machine: records_for(work, machine) for machine in MACHINES}

    for title, prefixes in GROUPS:
        cases = [case for case in matrix if case.split("/")[0] in prefixes]
        if not cases:
            continue
        print(f"\n### {title}\n")
        print("| Case | M5 Pro (s) | DGX Spark (s) |")
        print("|---|---|---|")
        for case in cases:
            print(f"| `{case}` | {cell(sides['mlx'].get(case))} | {cell(sides['cuda'].get(case))} |")

    print("\n### Coverage\n")
    missing = 0
    for case in matrix:
        absent = [machine for machine in MACHINES if sides[machine].get(case, {}).get("status") != "succeeded"]
        if absent:
            missing += 1
            print(f"- `{case}`: {', '.join(absent)}")
    print(f"\n{len(matrix) - missing} of {len(matrix)} cases succeeded on both engines")
    for machine in MACHINES:
        failed = [case for case, record in sides[machine].items() if record["status"] != "succeeded"]
        print(f"{machine}: {len(failed)} did not succeed")
        for case in sorted(failed):
            print(f"   {case}: {sides[machine][case]['status']} {sides[machine][case].get('error', '')[:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
