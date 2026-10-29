#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "mlx-yue @ git+https://github.com/vanch007/mlx-Yue.git@c5b5a8190f78c74aa671a4caa19dae8b8e04b3d8",
# ]
# ///
"""Pinned native MLX Q8 worker, isolated from Studio's dependency environment."""

import argparse
import base64
import contextlib
import gc
import hashlib
import io
import json
import os
import re
import shutil
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

MODEL_REVISION = "5f7620e546fb3c6130a09a7e18172e3bb7aaeddb"


def log(message):
    print(message, file=sys.stderr, flush=True)


def download_weights(args):
    from huggingface_hub import snapshot_download

    model_dir, vae_dir = Path(args.model_dir), Path(args.vae_dir)
    if vae_dir.resolve().is_relative_to(model_dir.resolve()):
        raise ValueError("The VAE directory must be outside the converted model directory.")
    # Hub cache metadata and the VAE subfolder violate the converter's exact-tree
    # integrity check. Download into Hub's cache, then copy only manifest files.
    source = Path(snapshot_download("vanch007/mlx-Yue2-3B", revision=MODEL_REVISION))
    manifest = json.loads((source / "conversion.json").read_text())
    files = set(manifest["files"]) | {"conversion.json"}
    directories = {parent.as_posix() for name in files for parent in PurePosixPath(name).parents}
    for path in model_dir.rglob("*"):
        allowed = directories if path.is_dir() else files
        if path.is_symlink() or path.relative_to(model_dir).as_posix() not in allowed:
            raise ValueError(
                "The converted model directory has unexpected files. Choose an empty model_dir; existing files were kept."
            )
    for name in sorted(files):
        target = model_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    for path in (source / "vae").rglob("*"):
        if path.is_file():
            target = vae_dir / path.relative_to(source / "vae")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


def load_engine(args):
    # The pinned runtime's validated attention path requires this setting.
    os.environ["MLX_ENABLE_TF32"] = "0"
    from lyra import YuE2Pipeline, nar

    original = getattr(nar.synthesize, "_studio_original", nar.synthesize)

    def synthesize(*values, on_progress=None, **kwargs):
        def progress(step, total):
            log(f"step {step}/{total}")
            if on_progress is not None:
                on_progress(step, total)

        return original(*values, on_progress=progress, **kwargs)

    synthesize._studio_original = original
    nar.synthesize = synthesize
    return YuE2Pipeline.from_pretrained(
        args.model_dir, vae=args.vae_dir, precision="8bit", local_files_only=True, progress=False
    )


class Worker:
    """The generator and transcriber never retain model memory together."""

    def __init__(self, args):
        self.args = args
        self.engine = None
        self.transcription_key = None
        self.transcription_result = None

    def generator(self):
        if self.engine is None:
            self.engine = load_engine(self.args)
        return self.engine

    def release(self):
        self.transcription_key = None
        self.transcription_result = None
        if self.engine is not None:
            self.engine.close()
            self.engine = None

    def transcribe(self, job):
        reference_hash = hashlib.sha256(base64.b64decode(job.get("reference_audio", ""), validate=True)).digest()
        key = (reference_hash, job.get("transcription_task", "melody-full"))
        hit = key == self.transcription_key
        if not hit:
            self.release()
            # The pinned transcriber uses greedy decoding. Only audio and task affect its score.
            self.transcription_result = transcribe(job, self.args.transcription_cache_dir)
            self.transcription_key = key
        score, metadata = deepcopy(self.transcription_result)
        metadata["transcription_cache_hit"] = hit
        return score, metadata


def transcribe(job, cache_dir):
    import mlx.core as mx
    from lyra.measure import GPUExecution
    from lyra.transcription.pipeline import transcribe as native_transcribe

    raw = base64.b64decode(job["reference_audio"], validate=True)
    if not raw:
        raise ValueError("Upload reference audio before transcribing or covering a song.")
    with TemporaryDirectory(prefix="studio-music-", dir=os.environ.get("SPEECH_GEN_SCRATCH")) as scratch:
        source = Path(scratch) / "reference.audio"
        source.write_bytes(raw)
        output = Path(scratch) / "transcription"

        def progress(event):
            if event["stage"] == "encoding":
                log(f"step {event['window']}/{event['windows']}")
            else:
                log(f"step {event['tokens']}/0")

        try:
            with GPUExecution(memory_budget_gib=16) as guard:

                def cancelled():
                    guard.check()
                    return False

                result = native_transcribe(
                    source,
                    output,
                    offline=True,
                    cache_dir=cache_dir,
                    task=job.get("transcription_task", "melody-full"),
                    progress=progress,
                    cancelled=cancelled,
                )
        finally:
            # Native transcription owns its model only inside the call. Reclaim
            # it before a cover loads the generator, including after failure.
            gc.collect()
            mx.clear_cache()
        if result["status"] != "complete" or result["truncated"] or not result.get("abc"):
            raise ValueError("Transcription was incomplete. Try a shorter reference recording.")
        artifacts = []
        for name, content in result["midis"].items():
            artifacts.append(
                {
                    "name": name + ".mid",
                    "content_type": "audio/midi",
                    "base64": base64.b64encode(content).decode("ascii"),
                }
            )
        for name, content in result["labs"].items():
            artifacts.append(
                {
                    "name": name + ".lab",
                    "content_type": "text/plain",
                    "base64": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                }
            )
        report = {key: value for key, value in result.items() if key not in {"abc", "midi", "midis"}}
        return result["abc"], {"transcription": report, "artifacts": artifacts}


def instrumental_header(score):
    """Normalize display-only headers for the strict native score converter.

    Musical fields and body lines are untouched. Unknown voice attributes may
    change pitch or timing, so they must be handled explicitly by the caller.
    """
    lines = score.splitlines()
    if len(lines) < 8:
        return score, ""
    title = lines[1].strip()
    original_title = title[2:].strip() if title.startswith("T:") else ""
    if title.startswith("T:"):
        lines[1] = "T:"
    for index, voice, name, short in ((5, "Vocal", "Vocal Melody", "Vocal"), (6, "Ins", "Ins Melody", "Inst.")):
        match = re.fullmatch(
            r"V:\s*" + voice + r'\s+clef\s*=\s*treble(?:\s+(?:name|snm)\s*=\s*"[^"\r\n]*")*\s*',
            lines[index].strip(),
        )
        if match is None:
            raise ValueError(
                "Instrumental conversion requires native Vocal and Ins treble voices. "
                "Normalize other clefs, octave or transposition attributes explicitly before rendering."
            )
        lines[index] = f'V: {voice} clef=treble name="{name}" snm="{short}"'
    return "\n".join(lines) + ("\n" if score.endswith(("\n", "\r")) else ""), original_title


def instrumental_score(score):
    try:
        from lyra.music_tools.instrumental_support.instrumentalize import convert_score
    except ImportError as error:
        raise ValueError("Install the pinned instrumental helpers with scripts/setup_yue2_workflows.py.") from error
    normalized, original_title = instrumental_header(score)
    converted, report = convert_score(normalized, overlap="vocal", keep_chords=True)
    if original_title:
        report = {**report, "original_title": original_title}
    labels = [line[2:] for line in converted.splitlines() if line.startswith("% ")]
    lyrics = "\n\n".join("[" + label.title() + "]" for label in labels)
    return converted, lyrics, report


def answer(worker, job):
    import numpy as np
    import soundfile

    mode = job.get("mode", "generate")
    tokens = 0
    extra = {"mode": mode, "instrumental": job.get("instrumental", False)}

    def on_token(_phase, _token):
        nonlocal tokens
        tokens += 1
        if tokens == 1 or tokens % 16 == 0:
            log(f"step {tokens}/0")

    log("step 0/0")
    score = job["abc"] if job["abc"].strip() else None
    cot = job["cot"]
    if mode in {"transcribe", "cover"}:
        score, transcription = worker.transcribe(job)
        extra.update(transcription)
        if mode == "transcribe":
            return {"wav": "", "score": score, "metadata": {**extra, "engine": "mlx-q8"}}
        cot = "full" if job.get("transcription_task", "melody-full") == "full" else "melody"
    engine = worker.generator() if isinstance(worker, Worker) else worker
    if "steps" in job:
        engine.generation_config = replace(engine.generation_config, ode_steps=job["steps"])
    params = dict(
        style=job["style"],
        lyrics=job["lyrics"],
        seed=job["seed"],
        cot=cot,
        abc=score,
        cfg_scale=job.get("cfg_scale", 1.0),
        on_token=on_token,
    )
    planned = None
    if job.get("instrumental"):
        if not params["style"].lower().startswith("instrumental"):
            params["style"] = "Instrumental, " + params["style"]
        if params["cot"] == "off":
            raise ValueError("Instrumental music requires melody or full score planning.")
        if not score:
            planned = engine.plan(**params)
            if planned.truncated:
                return {
                    "error": "YuE2 reached a generation limit. Shorten the lyrics or try another seed.",
                    "kind": "input",
                }
            score = planned.abc
        params["abc"], params["lyrics"], extra["instrumental_transfer"] = instrumental_score(score)
    if mode == "plan":
        plan = engine.plan(**params)
        if plan.truncated:
            return {
                "error": "YuE2 reached a generation limit. Shorten the lyrics or try another seed.",
                "kind": "input",
            }
        return {
            "wav": "",
            "score": plan.abc or "",
            "metadata": {
                **extra,
                "engine": "mlx-q8",
                "config": engine.effective_config(plan.request),
                "weights": engine.weights,
                "timing": {"abc": plan.timing},
                "generated_tokens": tokens,
                "plan": {"request": plan.request.to_dict(), "abc_ids": plan.abc_ids, "prefix": plan.prefix},
            },
        }
    result = engine(**params)
    if any(result.truncated.values()):
        return {"error": "YuE2 reached a generation limit. Shorten the lyrics or try another seed.", "kind": "input"}
    if (
        result.sample_rate != 48000
        or result.audio.ndim != 2
        or result.audio.shape[1] != 2
        or not np.isfinite(result.audio).all()
    ):
        raise ValueError("YuE2 returned invalid stereo audio.")
    output = io.BytesIO()
    soundfile.write(output, result.audio, result.sample_rate, format="WAV", subtype="PCM_24")
    return {
        "wav": base64.b64encode(output.getvalue()).decode("ascii"),
        "score": result.abc or "",
        "truncated": result.truncated,
        "metadata": {
            **extra,
            "config": result.config,
            "weights": result.weights,
            "timing": result.timing,
            "request_identity": result.request_identity,
            "engine": "mlx-q8",
            "ar_precision": "8bit",
            "nar_precision": "bfloat16",
            "vae_precision": "float32",
            "generated_tokens": tokens,
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--vae-dir", required=True)
    parser.add_argument("--download", action="store_true")
    parser.add_argument(
        "--transcription-cache-dir", default=str(Path.home() / "Library/Caches/models/yue2-transcription")
    )
    args = parser.parse_args()
    with contextlib.redirect_stdout(sys.stderr):
        if args.download:
            download_weights(args)
            return
        engine = Worker(args)
    log("ready")
    try:
        for line in sys.stdin:
            try:
                with contextlib.redirect_stdout(sys.stderr):
                    reply = answer(engine, json.loads(line))
            except (ValueError, ImportError, FileNotFoundError) as error:
                log(f"{type(error).__name__}: {error}")
                reply = {"error": str(error), "kind": "input"}
            except Exception as error:
                log(f"{type(error).__name__}: {error}")
                reply = {"error": "YuE2 MLX generation failed; check the engine installation and try again."}
            print(json.dumps(reply), flush=True)
    finally:
        engine.release()


if __name__ == "__main__":
    main()
