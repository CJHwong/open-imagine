import io
import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l3_interface_adapters.gateways.image.flux3.capabilities import flux3_capabilities
from studio.l3_interface_adapters.gateways.image.flux3.flux3_backend_gateway import (
    Flux3BackendGateway,
    engine_failure,
    image_size,
    uv_launcher,
)
from studio.plugins.image import Cancelled, ImageJob, InvalidJob, ReferenceImage

CAPABILITIES = flux3_capabilities("int8")


def png(size=(64, 48)):
    data = io.BytesIO()
    Image.new("RGB", size, "blue").save(data, format="PNG")
    return data.getvalue()


def job(mode="generate", size="512x512", references=()):
    return ImageJob(mode, "Full scene caption", 7, {"size": size, "steps": 16}, references)


def gateway(runner, tmp_path, **settings):
    return Flux3BackendGateway(
        str(settings.get("model_dir", tmp_path)),
        settings.get("quantize", 8),
        "int8",
        runner,
    )


def test_child_runs_as_a_uv_script(monkeypatch, tmp_path):
    monkeypatch.setenv("UV", "/parent/uv/bin/uv")
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(png((512, 512)))

    gateway(run, tmp_path).run(job(), lambda *args: None, lambda: False)
    assert commands[0][0] == "/parent/uv/bin/uv"
    assert Path(commands[0][0]).is_absolute()
    assert commands[0][1:3] == ["run", "--script"]
    assert Path(commands[0][3]).name == "flux3_child.py"
    assert len(commands[0]) == 6


def test_child_uses_the_parent_uv_binary(monkeypatch):
    monkeypatch.setenv("UV", "/parent/uv/bin/uv")
    assert uv_launcher() == "/parent/uv/bin/uv"
    monkeypatch.delenv("UV")
    monkeypatch.setattr(shutil, "which", lambda name: "/found/uv" if name == "uv" else None)
    assert uv_launcher() == "/found/uv"
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(ModelConfigurationError, match="uv"):
        uv_launcher()


def test_declared_native_controls():
    for mode in CAPABILITIES.modes:
        assert {p.id for p in mode.params} == {"size", "steps"}
        assert next(p for p in mode.params if p.id == "steps").default == 16
        assert not mode.looks and not mode.templates and not mode.loras
        for choice in next(p for p in mode.params if p.id == "size").choices:
            if choice.value == "match":
                continue
            assert all(int(side) % 16 == 0 for side in choice.value.split("x"))
    edit = CAPABILITIES.mode("edit")
    assert edit.params[0].default == "match"
    assert (edit.min_references, edit.max_references) == (1, 2)


def test_match_uses_first_reference_and_caps_area():
    refs = (ReferenceImage(b"", 2048, 1024), ReferenceImage(b"", 512, 512))
    width, height = image_size(job("edit", "match", refs))
    assert width > height
    assert width * height <= 1024 * 1024
    assert width % 16 == height % 16 == 0


@pytest.mark.parametrize("dimensions", [(1_000_000, 1), (1, 1_000_000), (16, 16), (8192, 128)])
def test_match_refuses_shapes_that_cannot_fit_safely(dimensions):
    reference = ReferenceImage(b"", *dimensions)
    with pytest.raises(InvalidJob, match="64 pixels"):
        image_size(job("edit", "match", (reference,)))


@pytest.mark.parametrize("mode,count", [("generate", 0), ("generate", 2), ("edit", 2)])
def test_request_transport_progress_and_cleanup(mode, count, tmp_path):
    saved = {}
    refs = tuple(ReferenceImage(png(), 64, 48) for _ in range(count))

    def run(command, **kwargs):
        request = json.loads(Path(command[-2]).read_text())
        saved.update(request)
        saved["root"] = Path(command[-2]).parent
        assert Path(command[3]).name == "flux3_child.py"
        assert len(request["references"]) == count
        assert all(Path(path).read_bytes() == png() for path in request["references"])
        assert kwargs["environment"]["HF_HUB_OFFLINE"] == "1"
        assert not kwargs["cancelled"]()
        # Subprocess reads can split in the middle of a JSON event.
        for part in ["loading\nFLUX3_EV", 'ENT {"type":"step","step":1,', '"total":16}\n']:
            kwargs["consume"](part)
        kwargs["consume"]('FLUX3_EVENT {"type":"result"}\n')
        Path(command[-1]).write_bytes(png((512, 512)))

    progress = []
    result = gateway(run, tmp_path).run(job(mode, references=refs), lambda *args: progress.append(args), lambda: False)
    assert result.width == result.height == 512
    assert result.seed == 7 and result.steps == 16
    assert saved["quantize"] == 8 and saved["prompt"] == "Full scene caption"
    assert "guidance" not in saved and "negative_prompt" not in saved
    assert progress == [(0, 16), (1, 16)]
    assert not saved["root"].exists()


def test_cancel_before_start_does_not_launch(tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("launched while cancelled")

    with pytest.raises(Cancelled):
        gateway(forbidden, tmp_path).run(job(), lambda *args: None, lambda: True)


def test_cancel_propagates_and_removes_references(tmp_path):
    roots = []

    def run(command, **kwargs):
        roots.append(Path(command[-2]).parent)
        raise Cancelled("Owned child terminated")

    with pytest.raises(Cancelled):
        gateway(run, tmp_path).run(job(), lambda *args: None, lambda: False)
    assert not roots[0].exists()


def test_invalid_engine_setting_does_not_launch(tmp_path):
    with pytest.raises(InvalidJob, match="quantize"):
        gateway(lambda *args, **kwargs: pytest.fail("launched"), tmp_path, quantize=3).run(
            job(),
            lambda *args: None,
            lambda: False,
        )


@pytest.mark.parametrize("bad_output", [None, (16, 16)])
def test_missing_or_wrong_output_is_not_success(bad_output, tmp_path):
    def run(command, **kwargs):
        if bad_output:
            Path(command[-1]).write_bytes(png(bad_output))

    with pytest.raises(InvalidJob):
        gateway(run, tmp_path).run(job(), lambda *args: None, lambda: False)


def test_release_and_load_are_idempotent(tmp_path):
    model = gateway(None, tmp_path)
    model.release()
    model.load()
    model.release()
    model.load()


def test_match_without_reference_uses_recommended_square():
    assert image_size(job(size="match")) == (1024, 1024)


@pytest.mark.parametrize("lines,detail", [([], "no error output"), (["first", "last"], "last")])
def test_engine_failure_preserves_exit_and_final_diagnostic(lines, detail):
    assert engine_failure(12, lines) == f"FLUX3 engine exited 12: {detail}"


def test_missing_weights_gives_setup_instruction(tmp_path):
    with pytest.raises(InvalidJob, match="weights are missing"):
        gateway(None, tmp_path, model_dir=tmp_path / "missing").load()


def test_cancel_after_child_finishes_discards_result(tmp_path):
    stopped = False

    def run(command, **kwargs):
        nonlocal stopped
        Path(command[-1]).write_bytes(png((512, 512)))
        stopped = True

    with pytest.raises(Cancelled):
        gateway(run, tmp_path).run(job(), lambda *args: None, lambda: stopped)


def test_non_png_output_is_rejected(tmp_path):
    def run(command, **kwargs):
        Image.new("RGB", (512, 512)).save(command[-1], format="BMP")

    with pytest.raises(InvalidJob, match="unexpected image format"):
        gateway(run, tmp_path).run(job(), lambda *args: None, lambda: False)
