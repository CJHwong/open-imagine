#!/usr/bin/env python3
"""Play a shuffled set of Music requests, one generation at a time.

Write a prompts file (JSON array or JSONL), then run:

    python3 scripts/shuffle.py --prompts prompts.jsonl --out sessions/set --tracks 10

The script submits one request, saves the WAV, score and metadata, starts playback,
and submits the next while the last track plays. It stops after --tracks attempts.
A per-track duration is not an API field: the engine plans the length.
"""

import argparse
import json
import random
import shlex
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path
from urllib import error, request
from urllib.parse import urljoin


def call(base, path, payload=None, timeout=60):
    url = urljoin(base.rstrip("/") + "/", path.lstrip("/"))
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {} if body is None else {"Content-Type": "application/json"}
    try:
        with request.urlopen(request.Request(url, data=body, headers=headers), timeout=timeout) as answer:
            return answer.headers.get_content_type(), answer.read()
    except error.HTTPError as failure:
        text = failure.read().decode("utf-8", "replace")
        try:
            detail = json.loads(text).get("error", text)
        except ValueError:
            detail = text
        raise RuntimeError(f"HTTP {failure.code}: {detail}") from None


def get_json(base, path):
    _, raw = call(base, path)
    return json.loads(raw)


def load_prompts(path):
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        raise SystemExit("The prompt file is empty.")
    try:
        rows = json.loads(text)
    except ValueError:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not isinstance(rows, list) or not rows:
        raise SystemExit("The prompt file must hold an array or one object per line.")
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or not str(row.get("style", "")).strip():
            raise SystemExit(f"Prompt {index} needs a style.")
        if not str(row.get("lyrics", "")).strip() and not row.get("instrumental"):
            raise SystemExit(f"Prompt {index} needs lyrics, or instrumental: true.")
    return rows


def wait_idle(base, limit=120):
    announced = False
    deadline = time.time() + limit
    while time.time() < deadline:
        state = get_json(base, "/api/v1/state")
        if not state.get("active") and not state.get("busy"):
            return
        if not announced:
            print("Waiting for the studio to finish another operation.", flush=True)
            announced = True
        time.sleep(3)
    raise RuntimeError("The studio stayed busy. Nothing was submitted.")


def track_seed(row, index, fallback, cycle):
    value = row.get("seed")
    try:
        seed = int(value) if value not in (None, "") else int(fallback) + index
    except (TypeError, ValueError):
        raise SystemExit(f"Prompt {index + 1} has a seed that is not an integer.") from None
    return (seed + cycle * 1000003) & 0xFFFFFFFF


def payload_for(row, seed, capabilities):
    lyrics = str(row.get("lyrics", ""))
    return {
        "kind": "music",
        "mode": "generate",
        "cot": row.get("cot") or capabilities.get("default_planning") or "full",
        "style": str(row["style"]),
        "lyrics": lyrics,
        "instrumental": bool(row.get("instrumental", not lyrics.strip())),
        "steps": int(row.get("steps") or capabilities.get("default_steps") or 32),
        "cfg_scale": float(row.get("cfg_scale") or 1),
        "seed": seed,
    }


def wait_operation(base, operation, timeout, interval):
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = get_json(base, operation["status_url"])
        if state.get("status") in {"succeeded", "failed", "cancelled"}:
            return state
        time.sleep(interval)
    raise RuntimeError(f"The run did not finish within {timeout} seconds.")


def save_track(base, folder, state, payload, operation):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "request.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "status.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    result_url = state.get("result_url")
    if not result_url:
        raise RuntimeError("The run succeeded without a result URL.")
    content_type, audio = call(base, result_url)
    if "audio/wav" not in content_type:
        raise RuntimeError(f"The result was {content_type}, not audio/wav.")
    wav_path = folder / "song.wav"
    wav_path.write_bytes(audio)
    _, raw = call(base, result_url.removesuffix("/result") + "/metadata")
    metadata = json.loads(raw)
    (folder / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "score.abc").write_text(metadata.get("score", ""), encoding="utf-8")
    with wave.open(str(wav_path)) as recording:
        channels = recording.getnchannels()
        rate = recording.getframerate()
        frames = recording.getnframes()
        seconds = frames / rate if rate else 0
    if channels != 2 or rate != 48000 or frames == 0:
        raise RuntimeError("The result is not a nonempty 48 kHz stereo WAV.")
    return {
        "wav": str(wav_path),
        "score": str(folder / "score.abc"),
        "seconds": seconds,
        "channels": channels,
        "sample_rate": rate,
        "stub": bool(metadata.get("stub")),
    }


def start_player(command, path):
    return subprocess.Popen([*shlex.split(command), path])


def main():
    parser = argparse.ArgumentParser(description="Play a shuffled set of Music requests.")
    parser.add_argument("--prompts", required=True, help="JSON array or JSONL of style, lyrics and seed rows")
    parser.add_argument("--out", required=True, help="Session folder")
    parser.add_argument("--tracks", required=True, type=int, help="Stop after this many attempts")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--shuffle-seed", type=int, default=None, help="Recorded shuffle order seed")
    parser.add_argument("--player", default="afplay", help="Playback command")
    parser.add_argument("--no-play", action="store_true", help="Generate without playing")
    parser.add_argument("--dry-run", action="store_true", help="Print the order and stop")
    parser.add_argument("--poll-seconds", type=float, default=3)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    if args.tracks < 1:
        raise SystemExit("--tracks must be at least 1.")

    rows = load_prompts(args.prompts)
    shuffle_seed = args.shuffle_seed if args.shuffle_seed is not None else random.SystemRandom().randrange(2**31)
    order = rows[:]
    random.Random(shuffle_seed).shuffle(order)
    plan = []
    for index in range(args.tracks):
        cycle, offset = divmod(index, len(order))
        row = order[offset]
        plan.append((row, track_seed(row, index, shuffle_seed, cycle), cycle))
    if args.dry_run:
        print(f"Shuffle seed {shuffle_seed}")
        for index, (row, seed, _) in enumerate(plan, 1):
            print(f"{index:02d}  seed {seed}  {str(row['style'])[:90]}")
        return 0

    if not args.no_play and shutil.which(shlex.split(args.player)[0]) is None:
        raise SystemExit(f"The player {args.player} is not on PATH. Use --player or --no-play.")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    capabilities = get_json(args.base_url, "/api/v1/music/capabilities")
    session = {
        "shuffleSeed": shuffle_seed,
        "requestedTracks": args.tracks,
        "baseUrl": args.base_url,
        "prompts": str(Path(args.prompts).resolve()),
        "completed": 0,
        "failed": 0,
        "tracks": [],
    }
    (out / "session.json").write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    player = None
    current = None
    width = max(2, len(str(args.tracks)))
    try:
        for index, (row, seed, _) in enumerate(plan, 1):
            folder = out / f"track-{index:0{width}d}"
            payload = payload_for(row, seed, capabilities)
            print(f"[{index}/{args.tracks}] {str(row['style'])[:80]}", flush=True)
            wait_idle(args.base_url)
            _, raw = call(args.base_url, "/api/v1/operations", payload)
            current = json.loads(raw)
            print("  operation {}".format(current["id"]), flush=True)
            state = wait_operation(args.base_url, current, args.timeout, args.poll_seconds)
            if state.get("status") != "succeeded":
                print("  {}: {}".format(state.get("status"), state.get("error", "")), flush=True)
                session["failed"] += 1
                session["tracks"].append(
                    {"index": index, "seed": seed, "status": state.get("status"), "error": state.get("error")}
                )
                current = None
                continue
            track = save_track(args.base_url, folder, state, payload, current)
            session["completed"] += 1
            session["tracks"].append({"index": index, "seed": seed, **track})
            (out / "session.json").write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
            print("  saved {}, {:.1f} s".format(track["wav"], track["seconds"]), flush=True)
            current = None
            if not args.no_play:
                if player and player.poll() is None:
                    player.wait()
                player = start_player(args.player, track["wav"])
                print("  playing {}".format(track["wav"]), flush=True)
    except KeyboardInterrupt:
        print("\nStopping. The current run is cancelled; finished tracks stay.", flush=True)
        if current:
            try:
                call(args.base_url, "/api/v1/operations/{}/cancel".format(current["id"]), {})
            except Exception as failure:
                print(f"  cancel failed: {failure}", flush=True)
        if player and player.poll() is None:
            player.terminate()
        session["interrupted"] = True
        (out / "session.json").write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
        return 130
    except Exception as failure:
        print(f"Stopped: {failure}", flush=True)
        if current:
            try:
                call(args.base_url, "/api/v1/operations/{}/cancel".format(current["id"]), {})
            except Exception as cancel_failure:
                print(f"  cancel failed: {cancel_failure}", flush=True)
        if player and player.poll() is None:
            player.terminate()
        session["error"] = str(failure)
        (out / "session.json").write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
        return 1
    if player and player.poll() is None:
        player.wait()
    (out / "session.json").write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{session['completed']} of {args.tracks} tracks completed. {out / 'session.json'}", flush=True)
    return 1 if session["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
