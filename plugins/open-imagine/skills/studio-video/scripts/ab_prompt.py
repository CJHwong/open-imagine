#!/usr/bin/env python3
"""Write a same-seed prompt A/B queue: each job's A arm keeps its prompt, the B arm takes its b_prompt.

usage: ab_prompt.py /abs/base.json --seeds 9701 9702 --out /abs/queue.json

base.json is a list of jobs in the studio queue shape ({name, out, references, request, ...}),
each with a "b_prompt": the full prompt of the B arm. Whoever writes the B prompts computes any
per-shot text there. For each job and seed, the queue gets "<name>-A<seed>" and "<name>-B<seed>",
both with that seed, written beside the job's out path. The script refuses a pair that differs
in anything but the prompt, so a result difference can only come from the prompt.
"""

import argparse
import copy
import json
import pathlib
import sys


def arm(job, letter, seed):
    out = copy.deepcopy({k: v for k, v in job.items() if k != "b_prompt"})
    name = f"{job['name']}-{letter}{seed}"
    path = pathlib.PurePosixPath(job["out"])
    out.update(name=name, out=str(path.with_name(name + path.suffix)))
    out["request"]["seed"] = type(job["request"]["seed"])(seed)
    if letter == "B":
        out["request"]["prompt"] = job["b_prompt"]
    return out


def check_pair(a, b):
    """Refuse a pair whose arms differ in anything but the name, the output path and the prompt."""
    for key in sorted((set(a) | set(b)) - {"name", "out", "request"}):
        if a.get(key) != b.get(key):
            raise ValueError(f"{a['name']}: the arms differ in {key}")
    request_a = {k: v for k, v in a["request"].items() if k != "prompt"}
    request_b = {k: v for k, v in b["request"].items() if k != "prompt"}
    if request_a != request_b:
        raise ValueError(f"{a['name']}: the arms' requests differ outside the prompt")
    if a["request"]["prompt"] == b["request"]["prompt"]:
        raise ValueError(f"{a['name']}: the B prompt is the same as the A prompt")


def pairs(jobs, seeds):
    queue = []
    for job in jobs:
        if not str(job.get("b_prompt", "")).strip():
            raise ValueError(f"{job.get('name')}: add b_prompt, the full prompt of the B arm")
        for seed in seeds:
            a, b = arm(job, "A", seed), arm(job, "B", seed)
            check_pair(a, b)
            queue += [a, b]
    return queue


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base", type=pathlib.Path)
    parser.add_argument("--seeds", nargs="+", type=int, required=True)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        queue = pairs(json.loads(args.base.read_text()), args.seeds)
    except ValueError as error:
        sys.exit(str(error))
    args.out.write_text(json.dumps(queue, ensure_ascii=False, indent=2))
    print(f"{len(queue)} jobs -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
