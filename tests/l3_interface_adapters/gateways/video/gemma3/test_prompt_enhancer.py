import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from studio.l1_entities.errors import Cancelled, StudioError
from studio.l3_interface_adapters.gateways.video.gemma3.prompt_enhancer import Gemma3PromptEnhancer
from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner

UV_PATH = "/opt/homebrew/bin/uv"


def enhancer(monkeypatch):
    monkeypatch.setenv("UV", UV_PATH)
    return Gemma3PromptEnhancer(SubprocessRunner().execute)


def test_the_child_uses_the_uv_that_runs_the_studio(monkeypatch):
    monkeypatch.setenv("UV", "/opt/uv/bin/uv")
    engine = Gemma3PromptEnhancer(SubprocessRunner().execute)
    commands = []

    def execute(command, *_, **options):
        commands.append(command)
        Path(command[5]).write_text(json.dumps({"prompt": "A directed shot."}))

    monkeypatch.setattr(engine, "_execute_process", execute)
    assert engine("A cup", (), lambda: None, lambda: False) == "A directed shot."
    assert commands[0][0] == "/opt/uv/bin/uv"
    assert commands[0][1:3] == ["run", "--script"]
    assert Path(commands[0][3]).name == "mlx_prompt_enhancement_child.py"
    assert Path(commands[0][3]).is_file()


def test_uv_falls_back_to_PATH_when_the_studio_sets_no_UV(monkeypatch):
    monkeypatch.delenv("UV", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/local/bin/uv")
    engine = Gemma3PromptEnhancer(SubprocessRunner().execute)
    commands = []
    monkeypatch.setattr(
        engine,
        "_execute_process",
        lambda command, *_, **options: (
            commands.append(command) or Path(command[5]).write_text(json.dumps({"prompt": "A shot."}))
        ),
    )
    assert engine("A cup", (), lambda: None, lambda: False) == "A shot."
    assert commands[0][0] == "/usr/local/bin/uv"


def test_a_missing_uv_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("UV", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    engine = Gemma3PromptEnhancer(SubprocessRunner().execute)
    with pytest.raises(StudioError, match="needs uv"):
        engine("A cup", (), lambda: None, lambda: False)
    assert not engine._enhanced


@pytest.mark.parametrize("conditioned", [False, True])
def test_native_enhancement_uses_the_script_environment_and_tracks_exact_output(monkeypatch, conditioned):
    engine = enhancer(monkeypatch)
    writing = []
    references = (SimpleNamespace(png=b"image-a"),) if conditioned else ()

    def execute(command, stop, consume, **options):
        assert command[0] == UV_PATH
        assert command[1:3] == ["run", "--script"]
        assert Path(command[3]).name == "mlx_prompt_enhancement_child.py"
        request = json.loads(Path(command[4]).read_text())
        assert request["prompt"] == "A cup"
        if conditioned:
            assert Path(request["image"]).read_bytes() == b"image-a"
        else:
            assert request["image"] is None
        assert stop() is False
        consume("Loading weights\n[Studio enhan")
        consume("cer writing]\n" + "Writing tokens\n" * 100)
        assert writing == [True]
        consume("[Studio enhancer writing]\n")
        Path(command[5]).write_text(json.dumps({"prompt": "A directed shot."}))

    monkeypatch.setattr(engine, "_execute_process", execute)
    assert engine("A cup", references, lambda: writing.append(True), lambda: False) == "A directed shot."
    assert writing == [True]
    assert engine.is_enhanced("A directed shot.", references)
    assert not engine.is_enhanced("A directed shot. Edited.", references)
    assert not engine.is_enhanced("A directed shot.", () if conditioned else (SimpleNamespace(png=b"other"),))


@pytest.mark.parametrize("output", ["", None])
def test_empty_enhancement_is_not_cached(monkeypatch, output):
    engine = enhancer(monkeypatch)
    monkeypatch.setattr(
        engine,
        "_execute_process",
        lambda command, *_, **options: Path(command[5]).write_text(json.dumps({"prompt": output})),
    )
    with pytest.raises(StudioError, match="empty prompt"):
        engine("A cup", (), lambda: None, lambda: False)
    assert not engine._enhanced


def test_enhancement_cancellation_does_not_cache_output(monkeypatch):
    engine = enhancer(monkeypatch)

    def execute(*_, **options):
        raise Cancelled("Stopped")

    monkeypatch.setattr(engine, "_execute_process", execute)
    with pytest.raises(Cancelled):
        engine("A cup", (), lambda: None, lambda: True)
    assert not engine._enhanced


def test_enhancement_history_is_bounded(monkeypatch):
    engine = enhancer(monkeypatch)
    count = iter(range(129))
    monkeypatch.setattr(
        engine,
        "_execute_process",
        lambda command, *_, **options: Path(command[5]).write_text(json.dumps({"prompt": str(next(count))})),
    )
    for _ in range(129):
        engine("A cup", (), lambda: None, lambda: False)
    assert len(engine._enhanced) == 128
    assert not engine.is_enhanced("0", ()) and engine.is_enhanced("128", ())


def test_enhanced_image_cache_matches_pixels_instead_of_reference_presence(monkeypatch):
    engine = enhancer(monkeypatch)
    monkeypatch.setattr(
        engine,
        "_execute_process",
        lambda command, *_, **options: Path(command[5]).write_text(json.dumps({"prompt": "A shot."})),
    )
    first, changed = SimpleNamespace(png=b"first"), SimpleNamespace(png=b"changed")
    engine("A cup", (first,), lambda: None, lambda: False)
    assert engine.is_enhanced("A shot.", (first,))
    assert engine.is_enhanced("A shot.", (SimpleNamespace(png=b"first"), changed))
    assert not engine.is_enhanced("A shot.", (changed,))
    assert not engine.is_enhanced("A shot.", ())
