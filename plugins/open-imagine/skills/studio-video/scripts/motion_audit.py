#!/usr/bin/env python3
"""Flag low-motion intervals in a source clip; never certify a semantic freeze."""

import argparse
import array
import json
import math
import pathlib
import subprocess
import sys


def rate(value):
    a, _, b = value.partition("/")
    return float(a) / float(b or 1) if float(b or 1) else 0


def audit(path, roi=None, threshold=0.5, minimum=0.2):
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,avg_frame_rate,nb_frames,duration:format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    metadata = json.loads(probe.stdout)
    streams = metadata.get("streams", [])
    if not streams:
        raise ValueError("No video stream")
    info = streams[0]
    fps = rate(info.get("avg_frame_rate", "0/1")) or rate(info.get("r_frame_rate", "0/1"))
    if fps <= 0:
        raise ValueError("Unknown frame rate; inspect timestamps manually")
    if roi:
        x, y, w, h = roi
        if min(x, y) < 0 or min(w, h) <= 0 or x + w > info["width"] or y + h > info["height"]:
            raise ValueError("ROI must lie inside the video frame")
    filters = ([f"crop={roi[2]}:{roi[3]}:{roi[0]}:{roi[1]}"] if roi else []) + ["scale=96:96", "format=gray"]
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(path),
        "-an",
        "-sn",
        "-dn",
        "-vf",
        ",".join(filters),
        "-fps_mode",
        "passthrough",
        "-pix_fmt",
        "gray",
        "-f",
        "rawvideo",
        "pipe:1",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.stdout, process.stderr
    if stdout is None or stderr is None:
        raise RuntimeError("ffmpeg pipes were not opened")
    previous, count, start = None, 0, None
    diffs = array.array("f")
    ranges = []
    try:
        while True:
            raw = stdout.read(96 * 96)
            if not raw:
                break
            if len(raw) != 96 * 96:
                raise ValueError("Truncated decoded frame")
            if previous is not None:
                difference = sum(abs(a - b) for a, b in zip(raw, previous, strict=True)) / len(raw)
                diffs.append(difference)
                # A difference at index i compares source frames i and i+1.
                i = count - 1
                if difference <= threshold:
                    if start is None:
                        start = i
                elif start is not None:
                    if (i - start) / fps >= minimum:
                        ranges.append((start, i))
                    start = None
            previous = raw
            count += 1
        error = stderr.read().decode(errors="replace")
        if process.wait():
            raise ValueError("Video decoding failed: " + error[:400])
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        stdout.close()
        stderr.close()
    if start is not None and (len(diffs) - start) / fps >= minimum:
        ranges.append((start, len(diffs)))
    onset = next((i for i in range(max(0, len(diffs) - 2)) if all(diffs[j] > threshold for j in range(i, i + 3))), None)
    duration = float(info.get("duration") or metadata.get("format", {}).get("duration") or count / fps)
    return {
        "source": str(path.resolve()),
        "kind": "low_motion_candidates_not_semantic_freeze_detection",
        "region_pixels": roi,
        "analysis": {
            "grayscale_size": [96, 96],
            "mean_pixel_difference_threshold": threshold,
            "minimum_interval_seconds": minimum,
            "time_basis": "frame index / average fps; verify PTS for variable-rate media",
        },
        "video": {
            "width": info["width"],
            "height": info["height"],
            "avg_fps": fps,
            "nominal_fps": info.get("r_frame_rate"),
            "decoded_frames": count,
            "duration_seconds": duration,
        },
        "first_three_consecutive_above_threshold_time_seconds": None if onset is None else round(onset / fps, 4),
        "unchanged_downsampled_frame_pairs": sum(d == 0 for d in diffs),
        "candidate_ranges": [
            {
                "source_start_frame": a,
                "source_end_frame_inclusive": b,
                "start_seconds": round(a / fps, 4),
                "end_seconds": round(b / fps, 4),
                "duration_seconds": round((b - a) / fps, 4),
            }
            for a, b in ranges
        ],
        "interpretation": "Inspect original moving playback and intended action. A static camera, still actor, untextured exterior or downsampling can produce low differences. Never auto-trim from this report.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=pathlib.Path)
    parser.add_argument("--roi", help="x,y,width,height in source pixels; choose the intended moving subject/window")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--minimum-seconds", type=float, default=0.2)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    try:
        roi = [int(x) for x in args.roi.split(",")] if args.roi else None
        if roi is not None and len(roi) != 4:
            raise ValueError("ROI requires four integers")
        if (
            not math.isfinite(args.threshold)
            or args.threshold < 0
            or not math.isfinite(args.minimum_seconds)
            or args.minimum_seconds <= 0
        ):
            raise ValueError("Use a nonnegative finite threshold and positive minimum interval")
        result = audit(args.video, roi, args.threshold, args.minimum_seconds)
        output = json.dumps(result, indent=2) + "\n"
        if args.output:
            args.output.write_text(output)
        else:
            print(output, end="")
    except (ValueError, subprocess.CalledProcessError, FileNotFoundError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
