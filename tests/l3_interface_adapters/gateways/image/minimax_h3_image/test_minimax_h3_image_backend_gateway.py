import io
import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from studio.l1_entities.errors import StudioError
from studio.l1_entities.image_estimate import estimate_image
from studio.l3_interface_adapters.gateways.image.minimax_h3_image.capabilities import (
    EDIT_SIZES,
    SIZES,
    minimax_h3_image_capabilities,
)
from studio.l3_interface_adapters.gateways.image.minimax_h3_image.minimax_h3_image_backend_gateway import (
    WEIGHT_FILES,
    MinimaxH3ImageBackendGateway,
    engine_failure,
    image_size,
    reference_png,
    uv_launcher,
)
from studio.plugins.image import Cancelled, ImageJob, InvalidJob, ReferenceImage

CAPABILITIES = minimax_h3_image_capabilities()


def png(size=(64, 48)):
    data = io.BytesIO()
    Image.new("RGB", size, "blue").save(data, format="PNG")
    return data.getvalue()


def job(mode="generate", size="1024x1024", references=()):
    return ImageJob(mode, "A sign that reads OPEN", 7, {"size": size, "steps": 6}, references)


def weights(tmp_path):
    for name in WEIGHT_FILES:
        path = tmp_path / "models" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"weights")
    return tmp_path / "models"


def gateway(runner, tmp_path):
    return MinimaxH3ImageBackendGateway(str(weights(tmp_path)), runner)


def test_declared_native_controls():
    for mode in CAPABILITIES.modes:
        assert {p.id for p in mode.params} == {"size", "steps"}
        steps = next(p for p in mode.params if p.id == "steps")
        assert (steps.default, steps.minimum, steps.maximum) == (6, 6, 6)
        assert mode.looks and mode.templates and not mode.loras
    generate, edit = CAPABILITIES.mode("generate"), CAPABILITIES.mode("edit")
    assert (generate.min_references, generate.max_references) == (0, 0)
    assert (edit.min_references, edit.max_references) == (1, 4)
    assert generate.params[0].default == "1024x1024" and edit.params[0].default == "match"


def test_every_size_is_on_the_engine_grid():
    for _, width, height in SIZES:
        assert width % 32 == height % 32 == 0
        assert min(width, height) >= 256 and max(width, height) <= 4096


def test_edit_offers_only_the_sizes_of_about_four_megapixels():
    """An edit at 1 MP came out posterized, so no smaller size may reach the edit form."""
    values = [choice.value for choice in CAPABILITIES.mode("edit").params[0].choices]
    assert values == ["2048x2048", "2560x1440", "1440x2560", "2304x1728", "1728x2304", "match"]
    assert all(width * height >= 3_600_000 for _, width, height in EDIT_SIZES)


@pytest.mark.parametrize(
    "reference,expected",
    [
        ((1024, 1024), (2048, 2048)),
        ((1600, 900), (2720, 1536)),
        ((900, 1600), (1536, 2720)),
        ((400, 100), (4096, 1024)),
    ],
)
def test_match_keeps_the_first_reference_shape_at_about_four_megapixels(reference, expected):
    references = (ReferenceImage(b"", *reference), ReferenceImage(b"", 512, 4096))
    assert image_size(job("edit", "match", references)) == expected


@pytest.mark.parametrize("dimensions", [(4100, 1000), (1000, 4100)])
def test_match_refuses_a_reference_past_four_to_one(dimensions):
    with pytest.raises(InvalidJob, match="4:1"):
        image_size(job("edit", "match", (ReferenceImage(b"", *dimensions),)))


@pytest.mark.parametrize("dimensions", [(410, 100), (100, 410)])
def test_a_reference_longer_than_the_measured_shapes_does_not_launch(dimensions, tmp_path):
    reference = ReferenceImage(png(), *dimensions)
    with pytest.raises(InvalidJob, match="too narrow"):
        gateway(lambda *args, **kwargs: pytest.fail("launched"), tmp_path).run(
            job("edit", "2048x2048", (reference,)), lambda *args: None, lambda: False
        )


@pytest.mark.parametrize(
    "mode,count,stages",
    [("generate", 0, ["text", "dit", "vae"]), ("edit", 2, ["text", "references", "dit", "vae"])],
)
def test_each_stage_runs_as_its_own_child_with_the_engine_request(mode, count, stages, tmp_path):
    ran, saved = [], {}
    refs = tuple(ReferenceImage(png(), 64, 48) for _ in range(count))

    def run(command, **kwargs):
        uv, run_flag, script, child, stage, root = command
        request = json.loads((Path(root) / "request.json").read_text())
        saved.update(request=request, root=Path(root))
        ran.append(stage)
        assert [run_flag, script] == ["run", "--script"] and Path(uv).name == "uv"
        assert Path(child).name == "minimax_h3_image_child.py"
        assert all(Path(path).read_bytes() == png() for path in request["references"])
        # The launcher is absolute, and no stage needs a binary from PATH.
        assert kwargs["environment"] == {"HF_HUB_OFFLINE": "1"}
        assert not kwargs["cancelled"]()
        kwargs["consume"]("loading\n")
        if stage == "dit":
            # Subprocess reads can split in the middle of a JSON event.
            for part in [
                "\nH3_IMAGE_EV",
                'ENT {"type":"step",',
                '"step":1}\n',
                'H3_IMAGE_EVENT {"type":"step","step":6}\n',
            ]:
                kwargs["consume"](part)
        kwargs["consume"]('H3_IMAGE_EVENT {"type":"result","stage":"x"}\n')
        if stage == "vae":
            (Path(root) / "image.png").write_bytes(png((2048, 2048)))

    progress = []
    model = gateway(run, tmp_path)
    result = model.run(job(mode, "2048x2048", refs), lambda *args: progress.append(args), lambda: False)
    assert ran == stages
    assert (result.width, result.height, result.seed, result.steps) == (2048, 2048, 7, 6)
    request = saved["request"]
    assert set(request) == {"prompt", "models", "width", "height", "seed", "references", "backend", "dit_mode"}
    assert request["prompt"] == "A sign that reads OPEN" and request["seed"] == 7
    assert (request["width"], request["height"]) == (2048, 2048)
    assert request["models"] == str(tmp_path / "models")
    assert (request["backend"], request["dit_mode"]) == ("auto", "auto")
    assert len(request["references"]) == count
    assert progress == [(0, 6), (1, 6), (6, 6)]
    assert not saved["root"].exists()


def test_every_stage_child_runs_under_the_uv_that_runs_the_studio(monkeypatch, tmp_path):
    """The engine lives in the child's PEP 723 environment, not in the studio's. Every stage
    starts the parent uv by its absolute path, so the child gets the same uv version."""
    monkeypatch.setenv("UV", "/parent/bin/uv")
    commands = []

    def run(command, **kwargs):
        commands.append(command[:4])
        if command[4] == "vae":
            (Path(command[5]) / "image.png").write_bytes(png((1024, 1024)))

    gateway(run, tmp_path).run(job(), lambda *args: None, lambda: False)

    assert len(commands) == 3
    assert all(head[:3] == ["/parent/bin/uv", "run", "--script"] for head in commands)
    assert all(Path(head[3]).name == "minimax_h3_image_child.py" for head in commands)


def test_the_launcher_falls_back_to_uv_on_path(monkeypatch):
    monkeypatch.delenv("UV", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: "/elsewhere/bin/uv")

    assert uv_launcher() == "/elsewhere/bin/uv"


def test_a_missing_uv_gives_setup_instruction(monkeypatch):
    monkeypatch.delenv("UV", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: None)

    with pytest.raises(InvalidJob, match=r"needs uv on PATH.*set-up-models"):
        uv_launcher()


def test_the_prompt_stays_out_of_the_command_line(tmp_path):
    """A command line shows in the process list, so the prompt travels in the scratch file only."""
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        if command[4] == "vae":
            (Path(command[5]) / "image.png").write_bytes(png((1024, 1024)))

    gateway(run, tmp_path).run(job(), lambda *args: None, lambda: False)
    assert len(commands) == 3 and not any("OPEN" in part for command in commands for part in command)


def test_a_reference_reaches_the_engine_at_the_measured_pixel_count_at_most(tmp_path):
    """The engine reads the short side at up to 2048 pixels, so a 3:1 photo of 36 MP would be
    read at 6144 x 2048. Sent at 4 MP it is read at 3552 x 1184, inside the measured cost."""
    sent = []

    def run(command, **kwargs):
        root = Path(command[5])
        if command[4] == "text":
            for name in ("reference-0.png", "reference-1.png"):
                with Image.open(root / name) as image:
                    sent.append(image.size)
        if command[4] == "vae":
            (root / "image.png").write_bytes(png((2048, 2048)))

    small = png((640, 480))
    references = (ReferenceImage(png((6000, 2000)), 6000, 2000), ReferenceImage(small, 640, 480))
    gateway(run, tmp_path).run(job("edit", "2048x2048", references), lambda *args: None, lambda: False)

    assert sent == [(3547, 1182), (640, 480)]
    assert sent[0][0] * sent[0][1] <= 2048 * 2048
    # A reference under the measured pixel count keeps its size, and still reaches the engine
    # as RGB, the one pixel format it reads.
    with Image.open(io.BytesIO(reference_png(references[1]))) as image:
        assert (image.mode, image.size) == ("RGB", (640, 480))


@pytest.mark.parametrize("mode", ["RGBA", "L", "P"])
def test_a_reference_of_any_pixel_format_reaches_the_engine_as_rgb(mode):
    """The engine reads one pixel format. A reference of any mode is decoded and written as
    RGB, whether or not it needed a downscale."""
    data = io.BytesIO()
    Image.new(mode, (320, 240), "blue").save(data, format="PNG")

    sent = reference_png(ReferenceImage(data.getvalue(), 320, 240))

    with Image.open(io.BytesIO(sent)) as image:
        assert (image.mode, image.size) == ("RGB", (320, 240))


@pytest.mark.parametrize("line", ["H3_IMAGE_EVENT {bad", 'H3_IMAGE_EVENT {"step": 2}', "H3_IMAGE_EVENT 7"])
def test_a_progress_line_that_does_not_parse_is_skipped(line, tmp_path):
    steps = []

    def run(command, **kwargs):
        kwargs["consume"](line + '\nH3_IMAGE_EVENT {"type": "step", "step": 3}\nH3_IMAGE_EVENT {"type": "note"}\n')
        if command[4] == "vae":
            (Path(command[5]) / "image.png").write_bytes(png((1024, 1024)))

    gateway(run, tmp_path).run(job(), lambda step, total: steps.append(step), lambda: False)

    assert steps == [0, 3, 3, 3]


def test_a_failed_child_removes_the_scratch_files(tmp_path):
    roots = []

    def run(command, **kwargs):
        roots.append(Path(command[5]))
        raise StudioError("MiniMax H3-Image engine exited 1: boom")

    with pytest.raises(StudioError):
        gateway(run, tmp_path).run(
            job("edit", "match", (ReferenceImage(png(), 64, 48),)), lambda *args: None, lambda: False
        )
    assert len(roots) == 1 and not roots[0].exists()


def test_cancel_after_the_last_stage_returns_no_image(tmp_path):
    stages = []

    def run(command, **kwargs):
        stages.append(command[4])
        if command[4] == "vae":
            (Path(command[5]) / "image.png").write_bytes(png((1024, 1024)))

    with pytest.raises(Cancelled):
        gateway(run, tmp_path).run(job(), lambda *args: None, lambda: len(stages) == 3)
    assert stages == ["text", "dit", "vae"]


def test_cancel_before_start_does_not_launch(tmp_path):
    with pytest.raises(Cancelled):
        gateway(lambda *args, **kwargs: pytest.fail("launched"), tmp_path).run(job(), lambda *args: None, lambda: True)


def test_cancel_propagates_and_removes_the_scratch_files(tmp_path):
    roots = []

    def run(command, **kwargs):
        roots.append(Path(command[5]))
        raise Cancelled("Owned child terminated")

    with pytest.raises(Cancelled):
        gateway(run, tmp_path).run(job(), lambda *args: None, lambda: False)
    assert len(roots) == 1 and not roots[0].exists()


def test_cancel_between_stages_launches_no_later_stage(tmp_path):
    stages = []

    def run(command, **kwargs):
        stages.append(command[4])

    with pytest.raises(Cancelled):
        gateway(run, tmp_path).run(job(), lambda *args: None, lambda: bool(stages))
    assert stages == ["text"]


@pytest.mark.parametrize("missing", WEIGHT_FILES)
def test_any_missing_weight_file_gives_setup_instruction(missing, tmp_path):
    model = gateway(lambda *args, **kwargs: pytest.fail("launched"), tmp_path)
    (tmp_path / "models" / missing).unlink()
    with pytest.raises(InvalidJob, match=r"weights are missing.*set-up-models"):
        model.run(job(), lambda *args: None, lambda: False)


@pytest.mark.parametrize("bad_output", [None, (16, 16)])
def test_missing_or_wrong_output_is_not_success(bad_output, tmp_path):
    def run(command, **kwargs):
        if bad_output and command[4] == "vae":
            (Path(command[5]) / "image.png").write_bytes(png(bad_output))

    with pytest.raises(InvalidJob):
        gateway(run, tmp_path).run(job(), lambda *args: None, lambda: False)


def test_non_png_output_is_rejected(tmp_path):
    def run(command, **kwargs):
        Image.new("RGB", (1024, 1024)).save(Path(command[5]) / "image.png", format="BMP")

    with pytest.raises(InvalidJob, match="unexpected image format"):
        gateway(run, tmp_path).run(job(), lambda *args: None, lambda: False)


def test_release_and_load_are_idempotent(tmp_path):
    model = gateway(None, tmp_path)
    model.release()
    model.load()
    model.release()
    model.load()


@pytest.mark.parametrize("lines,detail", [([], "no error output"), (["first", "last"], "last")])
def test_engine_failure_preserves_exit_and_final_diagnostic(lines, detail):
    assert engine_failure(12, lines) == f"MiniMax H3-Image engine exited 12: {detail}"


def test_the_estimates_track_the_measured_runs():
    """The page's formula, against the table beside the constants: one image, six steps."""
    caps = minimax_h3_image_capabilities()
    generate, edit = caps.mode("generate").estimate, caps.mode("edit").estimate
    assert generate is not None and edit is not None

    def seconds(estimate, megapixels, references=1):
        factor = 1 + estimate.per_reference * (references - 1)
        return 6 * estimate.step_cost * factor * megapixels**estimate.exponent + estimate.overhead

    for megapixels, measured in ((0.59, 16.8), (1.05, 20.9), (1.33, 26.4), (3.69, 49.9), (4.19, 55.7)):
        assert seconds(generate, megapixels) == pytest.approx(measured, rel=0.15)
    # The page reads Match as 1 MP, so an edit must not scale with the size.
    for megapixels in (1.05, 4.19):
        assert seconds(edit, megapixels) == pytest.approx(142.9, rel=0.05)
        assert seconds(edit, megapixels, 2) == pytest.approx(252.3, rel=0.1)
        assert seconds(edit, megapixels, 4) == pytest.approx(556.4, rel=0.15)
    assert generate.overhead_per_image and edit.overhead_per_image


@pytest.mark.parametrize(
    "reference,measured",
    [((2048, 2048), 142.9), ((2896, 1448), 164.8), ((6000, 2000), 184.4), ((4096, 1024), 208.4), ((1024, 4096), 208.4)],
)
def test_the_edit_estimate_tracks_the_measured_runs_from_a_long_reference(reference, measured):
    """The figure of the plan route, for Match from one reference of each measured shape."""
    edit = CAPABILITIES.mode("edit")

    figure = estimate_image(edit, edit.parse_options({}), (reference,), 1)

    assert figure.total_seconds == pytest.approx(measured, rel=0.03)


def test_the_model_refuses_private_operations_because_its_engine_reads_files():
    assert minimax_h3_image_capabilities().private_operations is False


def test_the_prompt_aids_are_the_ones_the_sample_kept():
    capabilities = minimax_h3_image_capabilities()
    generate, edit = capabilities.mode("generate"), capabilities.mode("edit")
    assert [(row.name, len(row.options)) for row in generate.looks] == [
        ("Medium", 3),
        ("Film", 3),
        ("Color", 3),
        ("Light", 3),
        ("Camera", 2),
        ("Room for text", 1),
        ("Realism", 1),
        ("Portrait", 2),
    ]
    assert [(row.name, len(row.options)) for row in edit.looks] == [
        ("Exposure", 2),
        ("White balance", 2),
        ("Grade", 2),
        ("Lens", 3),
        ("Finish", 3),
        ("Retouch", 2),
    ]
    assert [template.name for template in generate.templates] == [
        "Portrait photo",
        "Product shot",
        "Landscape",
        "Poster with text",
        "Illustration",
        "Deadpan absurdity",
        "Banner",
    ]
    assert [template.name for template in edit.templates] == [
        "Replace the background",
        "Add text",
        "Add an object",
        "Turn into a skeleton",
        "Turn into a pose figure",
    ]


def test_a_look_this_model_refused_is_not_offered():
    capabilities = minimax_h3_image_capabilities()
    camera = next(row for row in capabilities.mode("generate").looks if row.name == "Camera")
    assert "Top-down" not in dict(camera.options)
    assert all(template.name != "Mark a region" for template in capabilities.mode("edit").templates)
