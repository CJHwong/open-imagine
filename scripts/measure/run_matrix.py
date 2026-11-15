"""Run the parity manifest on one engine, one case at a time, and record what happened.

Each run appends one JSON line to `results-<machine>.jsonl`. Rerunning skips a case that
already succeeded, so a broken link or a long night costs only the cases not yet done.

The `$file` and `$field` markers in a payload are resolved here, from the asset directory, so
both engines send the same bytes.
"""

import argparse
import base64
import json
import time
import urllib.error
import urllib.request
from pathlib import Path


def resolve(value, assets: Path):
    if isinstance(value, list):
        return [resolve(item, assets) for item in value]
    if isinstance(value, dict):
        if "$file" in value:
            encoded = base64.b64encode((assets / value["$file"]).read_bytes()).decode("ascii")
            field = value.get("$field")
            return encoded if field is None else {field: encoded}
        return {key: resolve(item, assets) for key, item in value.items()}
    return value


def call(base: str, path: str, body: dict | None = None, timeout: int = 120):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        base + path, data=data, headers={"Content-Type": "application/json"}, method="POST" if body else "GET"
    )
    with urllib.request.urlopen(request, timeout=timeout) as answer:
        return json.loads(answer.read())


def memory_free_gib() -> float:
    """Free memory on a Linux host. A macOS host reports 0, and the row carries no drop."""
    try:
        with open("/proc/meminfo") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1048576
    except FileNotFoundError:
        return 0.0
    return 0.0


def done(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    picked = set()
    for line in path.read_text().splitlines():
        record = json.loads(line)
        if record["status"] == "succeeded":
            picked.add(record["id"])
    return picked


def run_case(base: str, case: dict, machine: str, assets: Path, out: Path) -> dict:
    payload = resolve(case["machines"][machine], assets)
    baseline = memory_free_gib()
    started = time.time()
    try:
        accepted = call(base, "/api/v1/operations", {"kind": case["kind"], **payload})
    except urllib.error.HTTPError as failure:
        return {
            "id": case["id"],
            "status": "rejected",
            "error": failure.read().decode()[:300],
            "seconds": round(time.time() - started, 1),
        }
    operation = accepted["id"]
    stalls = 0
    while True:
        try:
            state = call(base, f"/api/v1/operations/{operation}", timeout=180)
        except (TimeoutError, urllib.error.URLError) as failure:
            stalls += 1
            print(f"  poll stalled ({failure}); retry {stalls}", flush=True)
            if stalls >= 10:
                raise
            time.sleep(2.0)
            continue
        stalls = 0
        if state["status"] in ("succeeded", "failed", "cancelled"):
            break
        time.sleep(1.0)
    record = {
        "id": case["id"],
        "status": state["status"],
        "seconds": round(time.time() - started, 1),
        "error": (state.get("error") or "")[:300],
    }
    if baseline:
        record["free_drop_gib"] = round(baseline - memory_free_gib(), 2)
    if state["status"] == "succeeded":
        with urllib.request.urlopen(f"{base}/api/v1/operations/{operation}/result", timeout=600) as answer:
            body = answer.read()
        record["bytes"] = len(body)
        results = out.parent / "results" / machine
        results.mkdir(parents=True, exist_ok=True)
        (results / (case["id"].replace("/", "_") + ".bin")).write_bytes(body)
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--machine", required=True, help="the key in the manifest: cuda or mlx")
    parser.add_argument("--base", default="http://127.0.0.1:8899")
    parser.add_argument("--work", default="/tmp/parity")
    parser.add_argument("--matrix", default="", help="defaults to <work>/matrix.jsonl")
    parser.add_argument("--assets", default="", help="defaults to <work>/assets")
    parser.add_argument("--out", default="", help="defaults to <work>/results-<machine>.jsonl")
    parser.add_argument("--only", default="", help="run the cases whose id contains this text")
    parser.add_argument("--limit", type=int, default=0)
    arguments = parser.parse_args()

    work = Path(arguments.work)
    out = Path(arguments.out or work / f"results-{arguments.machine}.jsonl")
    assets = Path(arguments.assets or work / "assets")
    matrix = Path(arguments.matrix or work / "matrix.jsonl")
    finished = done(out)
    cases = [json.loads(line) for line in matrix.read_text().splitlines()]
    if arguments.only:
        cases = [case for case in cases if arguments.only in case["id"]]
    if arguments.limit:
        cases = cases[: arguments.limit]

    print(f"{arguments.machine}: {len(cases)} cases, {len(finished)} already done", flush=True)
    for case in cases:
        if case["id"] in finished:
            continue
        record = run_case(arguments.base, case, arguments.machine, assets, out)
        print(f"{case['id']}: {record['status']} {record['seconds']} s {record.get('error', '')}", flush=True)
        with out.open("a") as handle:
            handle.write(json.dumps(record) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
