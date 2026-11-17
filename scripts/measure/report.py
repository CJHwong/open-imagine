"""Print the parity run: both engines side by side, then every case that is not done.

The missing list is the point. A measurement campaign fails quietly when one case is skipped,
so this names each one rather than leaving a blank cell to notice.

Two figures belong together only when both machines ran the same campaign. This prints the
manifest of each machine, names every case whose record came from another campaign, and
prints the operation's own time rather than a wall clock that includes a queue and a fetch.

A success is also a claim that the media is still there. The runner will not skip a case
whose artifact is gone, and this report will not count one, so a copied campaign that lost
its results says so instead of printing a full table.
"""

import argparse
import json
from pathlib import Path

from run_matrix import fingerprint, rows, saved

GROUPS = (
    ("Image", ("qwen21_turbo", "minimax_h3_image")),
    ("Video", ("ltx25",)),
    ("Voice", ("drama3",)),
    ("Music", ("yue2",)),
)
MACHINES = ("cuda", "mlx")
# Two machines produced the reference page. The runner is generic, so a column can be
# renamed without editing the script.
DEFAULT_LABELS = {"mlx": "M5 Pro", "cuda": "DGX Spark"}
# The fields two machines must agree on before their figures describe the same thing.
SHARED = ("git", "assets")


def load(path: Path) -> dict:
    return {record["id"]: record for record in rows(path)}


def records_for(work: Path, machine: str) -> tuple[dict, dict]:
    """The main run and the warm-up pass, kept apart so neither can hide the other."""
    return load(work / f"results-{machine}.jsonl"), load(work / f"warm-{machine}.jsonl")


def valid_success(record: dict | None, expected: str) -> bool:
    """A success this campaign produced. One definition, for the table and the coverage."""
    return record is not None and record.get("status") == "succeeded" and record.get("fingerprint") == expected


def pick(base: dict | None, warm: dict | None, expected: str) -> dict | None:
    """The warm row when it is this campaign's success, and the base row otherwise.

    The warm file holds a second run of the same case, and it can come from an older
    campaign or have failed. Either way it must not replace a good base row.
    """
    if valid_success(warm, expected):
        return warm
    return base


def manifest_for(work: Path, machine: str) -> dict:
    path = work / f"campaign-{machine}.json"
    return json.loads(path.read_text()) if path.is_file() else {}


def cell(record: dict | None, expected: str, archived: bool = True) -> str:
    if record is None:
        return "not run"
    if record["status"] != "succeeded":
        return record["status"]
    if record.get("fingerprint") != expected:
        return "other campaign"
    if not archived:
        return "no media"
    seconds = record.get("active")
    if seconds is None:
        seconds = record.get("seconds")
    return f"{seconds:.1f}" if isinstance(seconds, (int, float)) else "no time"


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
    parser.add_argument(
        "--label",
        action="append",
        default=[],
        metavar="MACHINE=TEXT",
        help="name a column, such as mlx=M5 Pro; the default names the two machines this was written on",
    )
    arguments = parser.parse_args()
    labels = dict(DEFAULT_LABELS)
    for entry in arguments.label:
        machine, _, text = entry.partition("=")
        if machine not in MACHINES or not text:
            raise SystemExit("--label takes MACHINE=TEXT, where MACHINE is cuda or mlx")
        labels[machine] = text
    work = Path(arguments.work)
    matrix = rows(work / "matrix.jsonl")
    manifests = {machine: manifest_for(work, machine) for machine in MACHINES}
    sides = {machine: records_for(work, machine) for machine in MACHINES}

    def expected(case: dict, machine: str) -> str:
        manifest = manifests[machine]
        return fingerprint(case, manifest) if manifest else ""

    by_id = {case["id"]: case for case in matrix}
    status_ok: dict[tuple[str, str], bool] = {}
    picked: dict[tuple[str, str], tuple[dict | None, bool]] = {}

    def succeeded(machine: str, case_id: str) -> bool:
        """Whether this campaign has a successful row for the case, media or not."""
        key = (machine, case_id)
        if key not in status_ok:
            base, warm = sides[machine]
            value = expected(by_id[case_id], machine) if case_id in by_id else ""
            status_ok[key] = valid_success(pick(base.get(case_id), warm.get(case_id), value), value)
        return status_ok[key]

    def chosen(machine: str, case_id: str) -> tuple[dict | None, bool]:
        """The row a table cell shows, and whether its media is still there."""
        key = (machine, case_id)
        if key not in picked:
            base, warm = sides[machine]
            value = expected(by_id[case_id], machine) if case_id in by_id else ""
            record = pick(base.get(case_id), warm.get(case_id), value)
            picked[key] = (record, record is not None and valid_success(record, value) and saved(work, record))
        return picked[key]

    print("### Provenance\n")
    print("\n".join(provenance(work, manifests)))

    for title, prefixes in GROUPS:
        cases = [case["id"] for case in matrix if case["id"].split("/")[0] in prefixes]
        if not cases:
            continue
        print(f"\n### {title}\n")
        print(f"| Case | {labels['mlx']} (s) | {labels['cuda']} (s) |")
        print("|---|---|---|")
        for case in cases:
            left, left_media = chosen("mlx", case)
            right, right_media = chosen("cuda", case)
            print(
                f"| `{case}` | {cell(left, expected(by_id[case], 'mlx'), left_media)} "
                f"| {cell(right, expected(by_id[case], 'cuda'), right_media)} |"
            )

    print("\n### Coverage\n")
    missing = 0
    for case in by_id:
        absent = []
        for machine in MACHINES:
            if not succeeded(machine, case):
                absent.append(machine)
            elif not chosen(machine, case)[1]:
                absent.append(f"{machine} (no media)")
        if absent:
            missing += 1
            print(f"- `{case}`: {', '.join(absent)}")
    with_media = len(by_id) - missing
    print(f"\n{with_media} of {len(by_id)} cases succeeded on both engines with their media")
    api_only = sum(1 for case in by_id if all(succeeded(machine, case) for machine in MACHINES))
    if api_only != with_media:
        print(f"{api_only} of {len(by_id)} succeeded by status alone; the rest have no archived media")

    for machine in MACHINES:
        base, warm = sides[machine]
        failed = [case for case in {**base, **warm} if not succeeded(machine, case)]
        print(f"{machine}: {len(failed)} did not succeed")
        for case in sorted(failed):
            record, _ = chosen(machine, case)
            reason = "not run" if record is None else record.get("status")
            if reason == "succeeded":
                reason = "other campaign"
            print(f"   {case}: {reason} {(record or {}).get('error', '')[:80]}")
        without_media = [case for case in {**base, **warm} if succeeded(machine, case) and not chosen(machine, case)[1]]
        for case in sorted(without_media):
            print(f"   {case}: no archived media")

    for machine in MACHINES:
        lost = [
            case
            for case, record in sides[machine][1].items()
            if not (
                valid_success(record, expected(by_id[case], machine) if case in by_id else "") and saved(work, record)
            )
        ]
        if lost:
            print(f"{machine}: {len(lost)} warm trials did not succeed")
            for case in sorted(lost):
                record = sides[machine][1][case]
                print(f"   {case}: {record.get('status')} {(record.get('error') or '')[:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
