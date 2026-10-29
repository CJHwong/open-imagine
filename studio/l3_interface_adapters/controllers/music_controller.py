"""Validate composition requests before taking model memory."""

import base64
import binascii
import math
import secrets
from collections.abc import Mapping
from dataclasses import asdict

from studio.l1_entities.errors import InvalidJob
from studio.l1_entities.music_job import MusicJob


class MusicController:
    def __init__(self, run, catalog, switch):
        self._run, self._catalog, self._switch = run, catalog, switch

    def active_id(self):
        return self._catalog.active_id()

    def backends(self):
        return [{"id": name, "name": self.model_capabilities(name).name} for name in self._catalog.visible_ids()]

    def model_capabilities(self, backend_id=""):
        if not isinstance(backend_id, str):
            raise InvalidJob("backend must be a Music model id")
        return self._catalog.get(backend_id or self.active_id()).capabilities()

    def capabilities(self):
        return asdict(self.model_capabilities())

    def switch(self, payload):
        self._switch.execute(self._backend_id(payload))

    def _backend_id(self, payload):
        backend_id = payload.get("backend", self.active_id())
        if not isinstance(backend_id, str) or not backend_id:
            raise InvalidJob("backend must be a nonempty Music model id")
        return backend_id

    def validate(self, payload):
        return music_job(payload, self.model_capabilities(self._backend_id(payload)))

    def run(self, payload):
        return self._run.execute(self.validate(payload), self._backend_id(payload))

    def run_batch(self, payloads, completed, started, cancelled):
        backend_id = self._backend_id(payloads[0])
        capabilities = self.model_capabilities(backend_id)
        if len(payloads) > capabilities.max_batch:
            raise InvalidJob(f"A Music batch takes at most {capabilities.max_batch} songs.")
        jobs = [music_job(payload, capabilities) for payload in payloads]
        return self._run.execute_batch(jobs, completed, started, backend_id)


def music_job(payload: Mapping, capabilities) -> MusicJob:
    if payload.get("backend", capabilities.backend_id) != capabilities.backend_id:
        raise InvalidJob(f"backend must be {capabilities.backend_id}")
    mode = payload.get("mode", "generate")
    if mode not in capabilities.modes:
        raise InvalidJob("Music mode must be generate, plan, transcribe or cover.")
    instrumental = payload.get("instrumental", False)
    if type(instrumental) is not bool:
        raise InvalidJob("instrumental must be true or false")
    values = {}
    for name, limit, required in (
        ("style", capabilities.max_style_characters, mode != "transcribe"),
        ("lyrics", capabilities.max_lyrics_characters, mode != "transcribe" and not instrumental),
        ("abc", capabilities.max_score_characters, False),
    ):
        value = payload.get(name, "")
        if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
            raise InvalidJob(f"{name} must contain {'1' if required else '0'} to {limit} characters")
        values[name] = value if name == "abc" and value.strip() else value.strip()
    if mode in ("cover", "transcribe") and values["abc"]:
        raise InvalidJob(
            "Reference audio and a supplied ABC score cannot be used together. Render the reviewed score in Create song instead."
        )
    cot = payload.get("cot", capabilities.default_planning)
    if cot not in capabilities.planning_modes:
        raise InvalidJob("cot must be full, melody or off")
    if values["abc"].strip() and cot == "off":
        raise InvalidJob("A supplied score needs full or melody planning.")
    if mode == "plan" and cot == "off":
        raise InvalidJob("Compose score needs melody or full planning.")
    if instrumental and cot == "off":
        raise InvalidJob("Instrumental music needs melody or full planning.")
    steps = payload.get("steps", capabilities.default_steps)
    if type(steps) is not int or steps not in capabilities.synthesis_steps:
        raise InvalidJob("steps must be 8, 16 or 32")
    cfg_scale = payload.get("cfg_scale", 1.0)
    if type(cfg_scale) not in (int, float) or not math.isfinite(cfg_scale) or not 0 <= cfg_scale <= 5:
        raise InvalidJob("cfg_scale must be a number between 0 and 5")
    task = payload.get("transcription_task", "melody-full")
    if task not in capabilities.transcription_tasks:
        raise InvalidJob("transcription_task must be full, melody-full or melody-vocal")
    reference, reference_name = _reference(payload, mode, capabilities.max_reference_bytes)
    seed = payload.get("seed")
    if seed is None or seed == "":
        seed = secrets.randbelow(2**32)
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise InvalidJob("seed must be a whole number between 0 and 4294967295")
    return MusicJob(
        seed=seed,
        cot=cot,
        mode=mode,
        instrumental=instrumental,
        steps=steps,
        cfg_scale=float(cfg_scale),
        transcription_task=task,
        reference_audio=reference,
        reference_name=reference_name,
        **values,
    )


def _reference(payload, mode, limit):
    name = payload.get("reference_name", "")
    if not isinstance(name, str) or len(name) > 255 or "\x00" in name:
        raise InvalidJob("reference_name must be a filename of at most 255 characters")
    encoded = payload.get("reference_audio", "")
    if not isinstance(encoded, str) or len(encoded) > ((limit + 2) // 3) * 4:
        raise InvalidJob("Reference audio must be base64 and no larger than 32 MiB")
    try:
        audio = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise InvalidJob("Reference audio must be valid base64") from None
    if len(audio) > limit:
        raise InvalidJob("Reference audio must be no larger than 32 MiB")
    if mode in ("transcribe", "cover") and not audio:
        raise InvalidJob("Choose a reference audio file for this mode")
    if mode in ("generate", "plan") and audio:
        raise InvalidJob("Reference audio requires Cover song or Transcribe audio mode")
    return audio, name
