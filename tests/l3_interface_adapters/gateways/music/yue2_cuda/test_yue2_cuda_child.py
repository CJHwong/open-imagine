import io
import json
import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from studio.l3_interface_adapters.gateways.music.yue2_cuda import yue2_cuda_child as child


class FakePipe:
    def __init__(self):
        self.requests = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def plan(self, **request):
        self.requests.append(("plan", request))
        return SimpleNamespace(abc="X:1")

    def __call__(self, **request):
        self.requests.append(("generate", request))
        return SimpleNamespace(audio=[[0.0, 0.0]], abc="X:1", truncated={"semantic": False})


def fake_pipeline(monkeypatch, pipe, available=True):
    torch = types.ModuleType("torch")
    monkeypatch.setattr(torch, "bfloat16", "bfloat16", raising=False)
    monkeypatch.setattr(
        torch, "cuda", SimpleNamespace(is_available=lambda: available, synchronize=Mock()), raising=False
    )
    monkeypatch.setitem(sys.modules, "torch", torch)

    module = types.ModuleType("yue2")
    monkeypatch.setattr(
        module, "YuE2Pipeline", SimpleNamespace(from_pretrained=lambda model, **kwargs: pipe), raising=False
    )
    monkeypatch.setitem(sys.modules, "yue2", module)

    soundfile = types.ModuleType("soundfile")
    monkeypatch.setattr(
        soundfile,
        "write",
        lambda buffer, data, rate, format=None, subtype=None: buffer.write(b"wav-bytes"),
        raising=False,
    )
    monkeypatch.setitem(sys.modules, "soundfile", soundfile)


def job(**overrides):
    base = {"style": "piano", "lyrics": "[Verse]\nhello", "seed": 7, "cot": "full"}
    base.update(overrides)
    return base


def test_the_request_marks_an_instrumental_style():
    request = child.request_for(job(instrumental=True))

    assert request["style"].startswith("Instrumental, ")
    assert request["seed"] == 7 and request["cot"] == "full"
    assert "abc" not in request


def test_a_supplied_score_travels_and_a_blank_one_does_not():
    assert child.request_for(job(abc="X:1"))["abc"] == "X:1"
    assert "abc" not in child.request_for(job(abc="   "))


def test_a_generate_job_returns_wav_bytes_and_the_score(monkeypatch, capsys):
    pipe = FakePipe()
    fake_pipeline(monkeypatch, pipe)

    reply = child.run(pipe, job())

    assert reply["wav"] == "d2F2LWJ5dGVz"
    assert reply["score"] == "X:1" and reply["truncated"] == {"semantic": False}
    assert pipe.requests[0][0] == "generate"


def test_sampling_overrides_reach_both_stages_and_an_empty_map_stays_out(monkeypatch):
    pipe = FakePipe()
    fake_pipeline(monkeypatch, pipe)

    child.run(pipe, {"style": "piano", "lyrics": "[Verse]\nhi", "seed": 7, "sampling": {"max_tokens": 2048}})
    child.run(pipe, {"style": "piano", "lyrics": "[Verse]\nhi", "seed": 7})

    with_sampling = pipe.requests[-2][1]
    assert with_sampling["abc_sampling"] == {"max_tokens": 2048}
    assert with_sampling["semantic_sampling"] == {"max_tokens": 2048}
    assert "abc_sampling" not in pipe.requests[-1][1]


def test_a_plan_job_returns_the_score_only(monkeypatch):
    pipe = FakePipe()
    fake_pipeline(monkeypatch, pipe)

    reply = child.run(pipe, job(mode="plan"))

    assert reply == {"score": "X:1", "metadata": {"mode": "plan"}}
    assert pipe.requests[0][0] == "plan"


def test_load_enters_the_pipeline(monkeypatch, capsys):
    fake_pipeline(monkeypatch, FakePipe())

    pipe = child.load("m-a-p/YuE2-3B")

    assert isinstance(pipe, FakePipe)
    assert "loaded m-a-p/YuE2-3B" in capsys.readouterr().err


def test_main_refuses_a_host_without_cuda(monkeypatch, capsys):
    fake_pipeline(monkeypatch, FakePipe(), available=False)
    monkeypatch.setattr(sys, "argv", ["child"])

    assert child.main() == 2
    assert "CUDA is not available" in capsys.readouterr().err


def test_main_answers_each_line_and_survives_a_failed_job(monkeypatch, capsys):
    fake_pipeline(monkeypatch, FakePipe())
    monkeypatch.setattr(sys, "argv", ["child"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join([json.dumps(job()), "", json.dumps({"seed": 1})])))

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
