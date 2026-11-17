import io
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from studio.l3_interface_adapters.gateways.voice.drama3_cuda import drama3_cuda_child as child


@pytest.mark.parametrize("mode", ["generate", "clone"])
def test_controller_options_survive_the_gateway_and_child(monkeypatch, mode):
    import base64

    import soundfile

    from studio.l3_interface_adapters.controllers.voice_controller import VoiceController
    from studio.l3_interface_adapters.gateways.voice.drama3_cuda.capabilities import drama_cuda_capabilities
    from studio.l3_interface_adapters.gateways.voice.drama3_cuda.drama3_cuda_backend_gateway import (
        Drama3CudaBackendGateway,
    )

    fake_world(monkeypatch)
    payload = {
        "mode": mode,
        "text": "The river is quiet.",
        "seed": 19,
        "temperature": 0.55,
        "top_p": 0.9,
        "top_k": 11,
        "max_tokens": 700,
    }
    if mode == "clone":
        reference = io.BytesIO()
        soundfile.write(reference, np.zeros(4410), 44100, format="WAV")
        payload.update(
            reference={"wav_base64": base64.b64encode(reference.getvalue()).decode()}, ref_text="A clear day."
        )
    controller = VoiceController(Mock(), drama_cuda_capabilities())
    gateway_child = Mock()
    received = []

    def request(serialized, on_step, should_stop):
        received.append(child.request_for(json.loads(json.dumps(serialized))))
        return {"wav": "", "seconds": 0, "sample_rate": 44100, "steps": 1}

    gateway_child.request.side_effect = request
    Drama3CudaBackendGateway(gateway_child).run(controller.validate(payload), Mock(), lambda: False)

    assert len(received) == 1
    actual = received[0]
    assert actual["temperature"] == 0.55
    assert actual["top_p"] == 0.9
    assert actual["top_k"] == 11
    assert actual["max_new_tokens"] == 700
    assert actual["seed"] == 19
    if mode == "clone":
        assert actual["references"][0]["text"] == "A clear day."
        assert actual["references"][0]["audio"] == reference.getvalue()


class Event:
    def __init__(self, code, audio=None, error=None):
        self.code = code
        self.audio = audio
        self.error = error


class Engine:
    def __init__(self):
        self.requests = []

    def inference(self, request):
        self.requests.append(request)
        yield Event("header", (44100, np.zeros(4, dtype=np.float32)))
        yield Event("segment", (44100, np.full(4, 0.5, dtype=np.float32)))
        yield Event("final", (44100, np.zeros(4, dtype=np.float32)))


def fake_world(monkeypatch, available=True):
    torch = types.ModuleType("torch")
    monkeypatch.setattr(torch, "cuda", SimpleNamespace(is_available=lambda: available), raising=False)
    monkeypatch.setitem(sys.modules, "torch", torch)

    engine = Engine()
    manager = SimpleNamespace(tts_inference_engine=engine)
    tools = types.ModuleType("tools")
    server = types.ModuleType("tools.server")
    model_manager = types.ModuleType("tools.server.model_manager")
    monkeypatch.setattr(model_manager, "ModelManager", lambda **kwargs: manager, raising=False)
    monkeypatch.setitem(sys.modules, "tools", tools)
    monkeypatch.setitem(sys.modules, "tools.server", server)
    monkeypatch.setitem(sys.modules, "tools.server.model_manager", model_manager)

    fish = types.ModuleType("fish_speech")
    utils = types.ModuleType("fish_speech.utils")
    schema = types.ModuleType("fish_speech.utils.schema")
    monkeypatch.setattr(schema, "ServeTTSRequest", lambda **kwargs: kwargs, raising=False)
    monkeypatch.setattr(
        schema,
        "ServeReferenceAudio",
        lambda audio=None, text="", speaker=None: {"audio": audio, "text": text, "speaker": speaker},
        raising=False,
    )
    monkeypatch.setitem(sys.modules, "fish_speech", fish)
    monkeypatch.setitem(sys.modules, "fish_speech.utils", utils)
    monkeypatch.setitem(sys.modules, "fish_speech.utils.schema", schema)

    compiler = types.ModuleType("triton.backends.nvidia.compiler")
    monkeypatch.setattr(compiler, "ptx_get_version", lambda version: 90, raising=False)
    monkeypatch.setitem(sys.modules, "triton", types.ModuleType("triton"))
    monkeypatch.setitem(sys.modules, "triton.backends", types.ModuleType("triton.backends"))
    monkeypatch.setitem(sys.modules, "triton.backends.nvidia", types.ModuleType("triton.backends.nvidia"))
    monkeypatch.setitem(sys.modules, "triton.backends.nvidia.compiler", compiler)

    hugging = types.ModuleType("huggingface_hub")
    monkeypatch.setattr(hugging, "snapshot_download", lambda repo, local_files_only=False: "/snapshot", raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hugging)
    return engine


def test_prepare_environment_points_triton_at_the_cuda_ptxas(monkeypatch, tmp_path):
    ptxas = tmp_path / "ptxas"
    ptxas.write_text("")
    monkeypatch.setattr(child, "PTXAS", ptxas)
    monkeypatch.delenv("TRITON_PTXAS_PATH", raising=False)
    monkeypatch.delenv("HF_HUB_DISABLE_XET", raising=False)

    child.prepare_environment()

    assert child.os.environ["TRITON_PTXAS_PATH"] == str(ptxas)
    assert child.os.environ["HF_HUB_DISABLE_XET"] == "1"


def test_prepare_environment_leaves_a_missing_ptxas_alone(monkeypatch, tmp_path):
    monkeypatch.setattr(child, "PTXAS", tmp_path / "absent")
    monkeypatch.delenv("TRITON_PTXAS_PATH", raising=False)
    child.prepare_environment()
    assert "TRITON_PTXAS_PATH" not in child.os.environ


def test_patch_triton_teaches_it_cuda_13(monkeypatch):
    compiler = types.ModuleType("triton.backends.nvidia.compiler")
    monkeypatch.setattr(compiler, "ptx_get_version", lambda version: 90 if version == "12.0" else 0, raising=False)
    monkeypatch.setitem(sys.modules, "triton", types.ModuleType("triton"))
    monkeypatch.setitem(sys.modules, "triton.backends", types.ModuleType("triton.backends"))
    monkeypatch.setitem(sys.modules, "triton.backends.nvidia", types.ModuleType("triton.backends.nvidia"))
    monkeypatch.setitem(sys.modules, "triton.backends.nvidia.compiler", compiler)

    child.patch_triton()

    assert compiler.ptx_get_version("13.0") == 90
    assert compiler.ptx_get_version("12.0") == 90


def test_checkout_clones_once(monkeypatch, tmp_path):
    calls = []

    def fake(command, check, **_):
        calls.append(command)
        if command[1] == "clone":
            Path(command[-1]).mkdir(parents=True)
        if "rev-parse" in command:
            return SimpleNamespace(returncode=0, stdout=child.REVISION + "\n")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(child.subprocess, "run", fake)
    root = child.checkout(tmp_path)
    (root / ".project-root").write_text("")
    assert len(calls) == 3
    child.checkout(tmp_path)
    assert len(calls) == 4  # the second start reads HEAD and clones nothing

    assert root == tmp_path / child.REVISION
    assert (root / ".project-root").is_file()


def test_request_for_reads_a_reference_and_carries_the_options(monkeypatch):
    fake_world(monkeypatch)

    request = child.request_for(
        {"text": "hi", "seed": 3, "top_k": 5, "audio": "cmVm", "ref_text": "the reference words"}
    )

    assert request["text"] == "hi" and request["seed"] == 3 and request["top_k"] == 5
    reference = request["references"][0]
    assert reference["audio"] == b"ref"
    assert reference["text"] == "the reference words"


def test_a_run_collects_the_audio(monkeypatch):
    fake_world(monkeypatch)
    engine = Engine()
    manager = SimpleNamespace(tts_inference_engine=engine)
    soundfile = types.ModuleType("soundfile")
    monkeypatch.setattr(
        soundfile, "write", lambda buffer, data, rate, format=None, subtype=None: buffer.write(b"wav"), raising=False
    )
    monkeypatch.setitem(sys.modules, "soundfile", soundfile)

    reply = child.run(manager, {"text": "hi", "seed": 1, "options": {}})

    assert reply["wav"] == "d2F2" and reply["sample_rate"] == 44100
    assert reply["seconds"] >= 0 and reply["steps"] == 2


def test_an_engine_error_becomes_a_failed_job(monkeypatch):
    fake_world(monkeypatch)

    class Failing(Engine):
        def inference(self, request):
            yield Event("error", error="no audio")

    with pytest.raises(ValueError, match="no audio"):
        child.run(SimpleNamespace(tts_inference_engine=Failing()), {"text": "hi", "seed": 1, "options": {}})


def test_no_audio_at_all_is_refused(monkeypatch):
    fake_world(monkeypatch)

    class Silent(Engine):
        def inference(self, request):
            return iter(())

    with pytest.raises(ValueError, match="no audio was generated"):
        child.run(SimpleNamespace(tts_inference_engine=Silent()), {"text": "hi", "seed": 1, "options": {}})


def test_load_builds_the_manager(monkeypatch):
    fake_world(monkeypatch)
    manager = child.load("/weights", False)
    assert manager.tts_inference_engine is not None


def test_main_refuses_a_host_without_cuda(monkeypatch, capsys):
    fake_world(monkeypatch, available=False)
    monkeypatch.setattr(sys, "argv", ["child"])
    assert child.main() == 2
    assert "CUDA is not available" in capsys.readouterr().err


def test_main_answers_each_line_and_survives_a_failed_job(monkeypatch, capsys, tmp_path):
    fake_world(monkeypatch)
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".project-root").write_text("")
    monkeypatch.setattr(child, "checkout", lambda cache: root)
    monkeypatch.setattr(child, "load", lambda checkpoint, half: SimpleNamespace(tts_inference_engine=Engine()))
    soundfile = types.ModuleType("soundfile")
    monkeypatch.setattr(
        soundfile, "write", lambda buffer, data, rate, format=None, subtype=None: buffer.write(b"wav"), raising=False
    )
    monkeypatch.setitem(sys.modules, "soundfile", soundfile)
    monkeypatch.setattr(sys, "argv", ["child", "--checkpoint", "/weights"])
    monkeypatch.setattr(
        sys, "stdin", io.StringIO("\n".join([json.dumps({"text": "hi", "seed": 1}), "", json.dumps({"seed": 2})]))
    )

    assert child.main() == 0

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert "wav" in lines[0]
    assert lines[1]["error"].startswith("KeyError")


def test_the_script_enters_through_its_main_guard(monkeypatch):
    import runpy

    monkeypatch.setattr(sys, "argv", ["child", "--help"])
    with pytest.raises(SystemExit) as exited:
        runpy.run_path(child.__file__, run_name="__main__")
    assert exited.value.code == 0


def test_a_job_without_a_reference_carries_no_references(monkeypatch):
    fake_world(monkeypatch)
    assert child.request_for({"text": "hi", "seed": 1, "options": {}})["references"] == []


def test_a_segment_without_audio_is_ignored(monkeypatch):
    fake_world(monkeypatch)
    soundfile = types.ModuleType("soundfile")
    monkeypatch.setattr(
        soundfile, "write", lambda buffer, data, rate, format=None, subtype=None: buffer.write(b"wav"), raising=False
    )
    monkeypatch.setitem(sys.modules, "soundfile", soundfile)

    class Half(Engine):
        def inference(self, request):
            yield Event("segment", None)
            yield Event("final", (44100, np.zeros(4, dtype=np.float32)))

    reply = child.run(SimpleNamespace(tts_inference_engine=Half()), {"text": "hi", "seed": 1, "options": {}})
    assert reply["steps"] == 1


def test_a_local_checkpoint_directory_skips_the_snapshot(monkeypatch, tmp_path):
    fake_world(monkeypatch)
    weights = tmp_path / "weights"
    weights.mkdir()
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".project-root").write_text("")
    monkeypatch.setattr(child, "checkout", lambda cache: root)
    seen = {}

    def fake_load(checkpoint, half):
        seen["checkpoint"] = checkpoint
        return SimpleNamespace(tts_inference_engine=Engine())

    monkeypatch.setattr(child, "load", fake_load)
    monkeypatch.setattr(sys, "argv", ["child", "--checkpoint", str(weights)])
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    assert child.main() == 0
    assert seen["checkpoint"] == str(weights)


def fake_omni(monkeypatch, tensors=None, with_iterator=True):
    for name in (
        "fish_speech.models",
        "fish_speech.models.text2semantic",
        "fish_speech.models.text2semantic.fish_omni",
    ):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "fish_speech", types.ModuleType("fish_speech"))
    module = types.ModuleType("fish_speech.models.text2semantic.fish_omni.model")
    if with_iterator:
        monkeypatch.setattr(module, "iter_checkpoint_tensors", lambda *a, **k: iter(tensors or []), raising=False)
    monkeypatch.setitem(sys.modules, "fish_speech.models.text2semantic.fish_omni.model", module)
    return module


def test_patch_checkpoint_copies_clones_each_tensor(monkeypatch):
    class Tensor:
        def __init__(self):
            self.clones = 0

        def clone(self):
            self.clones += 1
            return self

    weight = Tensor()
    module = fake_omni(monkeypatch, [("a", weight)])

    child.patch_checkpoint_copies()

    assert [(name, tensor) for name, tensor in module.iter_checkpoint_tensors("dir")] == [("a", weight)]
    assert weight.clones == 1


def test_patch_checkpoint_copies_says_so_when_the_engine_moved(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "fish_speech", types.ModuleType("fish_speech"))
    monkeypatch.delitem(sys.modules, "fish_speech.models", raising=False)

    child.patch_checkpoint_copies()

    assert "keeps the slow copy" in capsys.readouterr().err


def test_patch_checkpoint_copies_says_so_when_the_iterator_is_gone(monkeypatch, capsys):
    fake_omni(monkeypatch, with_iterator=False)

    child.patch_checkpoint_copies()

    assert "no checkpoint iterator" in capsys.readouterr().err


def test_snapshot_downloads_only_when_the_cache_is_cold(monkeypatch):
    calls = []
    hub = types.ModuleType("huggingface_hub")

    def download(repo, local_files_only=False):
        calls.append(local_files_only)
        if local_files_only:
            raise OSError("no cache")
        return "/downloaded"

    monkeypatch.setattr(hub, "snapshot_download", download, raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)

    assert child.snapshot("fishaudio/drama-3") == "/downloaded"
    assert calls == [True, False]


def test_a_checkout_on_another_commit_is_replaced(monkeypatch, tmp_path):
    """A clone that succeeded and a checkout that did not leaves the marker on the
    default branch. The marker is not proof: HEAD is."""
    target = tmp_path / child.REVISION
    target.mkdir(parents=True)
    (target / ".project-root").write_text("")
    cloned = []

    def fake(command, check, **_):
        if command[1] == "clone":
            cloned.append(command[-1])
            Path(command[-1]).mkdir(parents=True)
        if "rev-parse" in command:
            # The old install answers with another commit; the fresh clone with the pinned one.
            if str(target) in command:
                return SimpleNamespace(returncode=0, stdout="deadbeef\n")
            return SimpleNamespace(returncode=0, stdout=child.REVISION + "\n")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(child.subprocess, "run", fake)

    root = child.checkout(tmp_path)

    assert cloned, "an install on another commit is cloned again"
    assert root == target
    assert (root / ".project-root").is_file() or root.is_dir()


def test_a_failed_checkout_leaves_no_install(monkeypatch, tmp_path):
    def fake(command, check, **_):
        if command[1] == "clone":
            Path(command[-1]).mkdir(parents=True)
            return SimpleNamespace(returncode=0, stdout="")
        if "checkout" in command:
            raise child.subprocess.CalledProcessError(1, command)
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(child.subprocess, "run", fake)

    with pytest.raises(child.subprocess.CalledProcessError):
        child.checkout(tmp_path)

    assert not (tmp_path / child.REVISION).exists()
    assert not list(tmp_path.glob(f".{child.REVISION}.building-*"))


def test_a_checkout_on_an_unpinned_commit_is_refused(monkeypatch, tmp_path):
    def fake(command, check, **_):
        if command[1] == "clone":
            Path(command[-1]).mkdir(parents=True)
        if "rev-parse" in command:
            return SimpleNamespace(returncode=0, stdout="other-commit\n")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(child.subprocess, "run", fake)

    with pytest.raises(RuntimeError, match="fish-speech checked out"):
        child.checkout(tmp_path)

    assert not (tmp_path / child.REVISION).exists()
