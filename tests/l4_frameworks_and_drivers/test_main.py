import threading
import time
import urllib.error
import urllib.request
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import StudioError
from studio.l1_entities.video_job import VideoJob
from studio.l3_interface_adapters.gateways.prompt_rewriters import NoPromptRewriter
from studio.l4_frameworks_and_drivers.config import Config, ConfigError, load_config
from studio.l4_frameworks_and_drivers.main import (
    assemble_studio,
    build_backends,
    build_rewriters,
    build_video_backends,
)
from tests.support.fakes import FakeBackendGateway
from tests.support.plugins import PACK, install, pack_entries


def settings(tmp_path: Path, text: str, **flags):
    path = tmp_path / "studio.toml"
    path.write_text(text)
    return load_config(path, **flags)


def test_only_the_offered_backends_are_built(tmp_path: Path):
    config = settings(tmp_path, 'default_backend = "qwen21"\n[qwen21]\nquantize = 0\n')
    assert list(build_backends(config)) == ["qwen21"]


def test_video_models_have_an_independent_default_and_visible_list(tmp_path: Path):
    config = settings(
        tmp_path,
        'default_backend = "qwen21"\n'
        'default_video_backend = "ltx25_mlx"\n'
        'visible_video_backends = ["ltx25_mlx"]\n'
        "[qwen21]\nquantize = 0\n"
        '[mlx_video]\nmodel_ltx25 = "pack-25"\n',
    )

    assert config.default_video_backend == "ltx25_mlx"
    assert config.visible_video_backends == ("ltx25_mlx",)
    assert list(build_video_backends(config)) == ["ltx25_mlx"]


def test_video_default_is_added_when_the_visible_list_omits_it(tmp_path: Path):
    config = settings(
        tmp_path,
        'default_backend = "qwen21"\n'
        'default_video_backend = "ltx25_mlx"\n'
        'visible_video_backends = ["future-model"]\n'
        "[qwen21]\nquantize = 0\n",
    )

    assert config.visible_video_backends == ("ltx25_mlx", "future-model")


def test_a_video_backend_the_app_does_not_know_is_named(tmp_path: Path):
    config = settings(
        tmp_path,
        'default_backend = "qwen21"\ndefault_video_backend = "mystery"\n[qwen21]\nquantize = 0\n',
    )

    with pytest.raises(ConfigError, match="no video backend called mystery"):
        build_video_backends(config)


def test_a_missing_setting_is_named(tmp_path: Path):
    config = settings(tmp_path, 'default_backend = "qwen21"\n[qwen21]\nquantize = 0\n', backend="flux2")
    with pytest.raises(ConfigError, match=r"model_dir under \[flux2\]"):
        build_backends(config)


def test_the_viggle_backend_offers_the_same_prompt_rewriters(tmp_path: Path):
    """The rewriters are models of their own and do not read the image engine, so a
    backend that draws the same model family offers them too. Leaving it out hid the
    toggle on a page that had every other control."""
    settings_text = (
        'default_backend = "viggle_turbo"\n'
        'visible_backends = ["qwen21", "viggle_turbo"]\n'
        "[qwen21]\nquantize = 0\n"
        '[viggle_turbo]\nquantize = 0\nlora_path = "turbo.safetensors"\n'
        'rewrite_generate_model = "Qwen/PE-T2I"\nrewrite_edit_model = "Qwen/PE-I2I"\n'
    )
    built = build_rewriters(settings(tmp_path, settings_text))
    assert built["viggle_turbo"].modes() == ("generate", "edit")


def test_the_rewriter_is_quantized_as_its_backend_section_says(tmp_path: Path, monkeypatch):
    from studio.l4_frameworks_and_drivers import main as main_module

    factory = Mock()
    monkeypatch.setitem(main_module.REWRITERS, "qwen21_turbo", factory)
    models = 'rewrite_generate_model = "Qwen/PE-T2I"\nrewrite_edit_model = "Qwen/PE-I2I"\n'
    head = 'default_backend = "qwen21_turbo"\n[qwen21_turbo]\nquantize = 0\nmodel_dir = "weights"\n'

    build_rewriters(settings(tmp_path, head + models + "rewrite_quantize = 8\n"))
    assert factory.call_args == (({"generate": "Qwen/PE-T2I", "edit": "Qwen/PE-I2I"},), {"quantize": 8})

    build_rewriters(settings(tmp_path, head + models))
    assert factory.call_args.kwargs == {"quantize": 0}  # a section without the key keeps bf16


@pytest.mark.parametrize("value", ["7", "16", '"8"', "true", "false", "-4"])
def test_a_rewrite_quantize_mlx_cannot_load_is_named_at_start(tmp_path: Path, value: str):
    """MLX quantizes to 2, 3, 4, 5, 6 or 8 bits. Any other value used to pass, load the
    card, then fail the first Rewrite with MLX's own message."""
    models = 'rewrite_generate_model = "Qwen/PE-T2I"\nrewrite_edit_model = "Qwen/PE-I2I"\n'
    head = 'default_backend = "qwen21_turbo"\n[qwen21_turbo]\nquantize = 0\nmodel_dir = "weights"\n'
    config = settings(tmp_path, head + models + f"rewrite_quantize = {value}\n")

    with pytest.raises(ConfigError, match=r"rewrite_quantize under \[qwen21_turbo\] must be 0, 2, 3, 4, 5, 6 or 8"):
        build_rewriters(config)


def test_a_backend_with_no_rewriter_settings_gets_none(tmp_path: Path):
    config = settings(tmp_path, 'default_backend = "qwen21"\n[qwen21]\nquantize = 0\n')
    assert build_rewriters(config)["qwen21"].modes() == ()


def test_an_unknown_backend_is_named(tmp_path: Path):
    config = settings(tmp_path, 'default_backend = "krea2"\n')
    with pytest.raises(ConfigError, match="no backend called krea2"):
        build_backends(config)


def test_the_viggle_backend_is_built_from_its_own_settings(tmp_path: Path):
    """The models are built here rather than in the backend package, because one
    backend package may not import another and Viggle drives qwen21's two models.
    Building one loads nothing."""
    config = settings(
        tmp_path,
        'default_backend = "viggle_turbo"\n[viggle_turbo]\nquantize = 0\nlora_path = "turbo.safetensors"\n',
    )
    assert list(build_backends(config)) == ["viggle_turbo"]


def test_the_viggle_backend_cannot_be_built_without_its_adapter_path(tmp_path: Path):
    """The path is required the way every other backend's settings are, so a file
    that names the backend and not its adapter says so."""
    config = settings(tmp_path, 'default_backend = "viggle_turbo"\n[viggle_turbo]\nquantize = 0\n')
    with pytest.raises(ConfigError, match=r"lora_path under \[viggle_turbo\]"):
        build_backends(config)


def test_official_turbo_backend_is_built_from_its_local_weight_directory(tmp_path: Path):
    config = settings(
        tmp_path,
        'default_backend = "qwen21_turbo"\n[qwen21_turbo]\nquantize = 0\nmodel_dir = "weights/qwen-turbo"\n',
    )

    backend = build_backends(config)["qwen21_turbo"]

    assert backend.capabilities().backend_id == "qwen21_turbo"
    assert backend._model_dir == (tmp_path / "weights/qwen-turbo").resolve()
    assert backend._generator._restore_encoder is not None
    assert backend._generator._restore_encoder.keywords == {
        "model_path": str((tmp_path / "weights/qwen-turbo").resolve()),
        "quantize": None,
    }
    assert backend._edit._prepare_model.__name__ == "cache_edit_inputs"
    assert backend._memory_scope.__name__ == "active_mlx_memory"


def test_official_turbo_needs_a_local_weight_directory_setting(tmp_path: Path):
    config = settings(tmp_path, 'default_backend = "qwen21_turbo"\n[qwen21_turbo]\nquantize = 0\n')

    with pytest.raises(ConfigError, match=r"model_dir under \[qwen21_turbo\]"):
        build_backends(config)


def test_official_turbo_gets_the_same_optional_prompt_rewriters(tmp_path: Path):
    config = settings(
        tmp_path,
        'default_backend = "qwen21_turbo"\n'
        '[qwen21_turbo]\nquantize = 0\nmodel_dir = "weights"\n'
        'rewrite_generate_model = "Qwen/PE-T2I"\nrewrite_edit_model = "Qwen/PE-I2I"\n',
    )

    assert build_rewriters(config)["qwen21_turbo"].modes() == ("generate", "edit")


@pytest.fixture
def served():
    """A real server on a free port, over a backend whose run lasts until it is cancelled."""
    started = threading.Event()
    backend = FakeBackendGateway(stop_check=lambda step: started.set() or time.sleep(0.2))
    studio = assemble_studio({"fake": backend}, {"fake": NoPromptRewriter()}, "fake", ("fake",))
    server = ThreadingHTTPServer(("127.0.0.1", 0), studio.handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield studio, server, backend, started
    server.shutdown()
    server.server_close()


def post(server, path, body=b"", **headers):
    url = f"http://127.0.0.1:{server.server_address[1]}{path}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as answer:
            return answer.status, answer.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, ""


def test_shutdown_stops_the_run_before_it_frees_the_backend(served):
    """The frees wait in line on the GPU thread, behind any run, so a Ctrl-C that
    did not cancel first waited for the image to finish."""
    studio, server, backend, started = served
    answers = []
    run = threading.Thread(target=lambda: answers.append(post(server, "/generate", b"prompt=p&steps=50")))
    run.start()
    assert started.wait(5)
    began = time.monotonic()
    studio.shutdown()
    assert time.monotonic() - began < 2
    run.join(5)
    assert "Cancelled" in answers[0][1] and backend.events == ["release"]


def test_shutdown_without_a_rewriter_skips_unused_model_adapters(served):
    """The rewriter is optional, and an unused backend has no model memory to release."""
    studio, _, backend, _ = served
    replace(studio, rewriter=None).shutdown()
    assert backend.events == []


def test_the_two_mlx_packs_are_separate_video_backends(tmp_path: Path):
    config = settings(
        tmp_path,
        'default_backend = "qwen21"\n'
        'default_video_backend = "ltx25_mlx"\n'
        'visible_video_backends = ["ltx25_mlx", "ltx23_mlx"]\n'
        "[qwen21]\nquantize = 0\n"
        '[mlx_video]\ncli_path = "/tmp/ltx-2-mlx"\n'
        'model_ltx25 = "pack-25"\nmodel_ltx23 = "pack-23"\n',
    )

    video = build_video_backends(config)

    assert list(video) == ["ltx25_mlx", "ltx23_mlx"]
    assert video["ltx25_mlx"].capabilities().name == "LTX-2.5"
    assert video["ltx23_mlx"].capabilities().name == "LTX-2.3"
    assert video["ltx25_mlx"]._runner._enhances is True
    assert video["ltx23_mlx"]._runner._enhances is True
    assert video["ltx25_mlx"]._runner._keyframe_two_stage is False
    assert video["ltx23_mlx"]._runner._keyframe_two_stage is True


def test_a_pack_without_its_model_setting_fails_when_it_runs(tmp_path: Path):
    """A studio with no video settings still builds and serves images; only a video run
    names the missing pack."""
    config = settings(
        tmp_path,
        'default_backend = "qwen21"\n'
        'default_video_backend = "ltx25_mlx"\n'
        'visible_video_backends = ["ltx25_mlx"]\n'
        "[qwen21]\nquantize = 0\n"
        '[mlx_video]\ncli_path = "/tmp/ltx-2-mlx"\n',
    )

    backend = build_video_backends(config)["ltx25_mlx"]

    with pytest.raises(StudioError, match="model_ltx25"):
        backend.run(VideoJob("a cat", 384, 384, 121, 24, 7))


def test_voice_models_open_drama_by_default_and_keep_both_auk_models(tmp_path):
    from studio.l4_frameworks_and_drivers.main import build_voice_backends

    config = settings(tmp_path, 'default_backend="qwen21"\n[qwen21]\nquantize=0\n')
    assert config.default_voice_backend == "drama3"
    assert config.visible_voice_backends == ("drama3",)
    config = replace(config, visible_voice_backends=("drama3", "auk_base", "auk"))
    backends = build_voice_backends(config)
    assert [backend.capabilities().name for backend in backends.values()] == ["Drama-3", "AuK", "AuK Flash"]
    assert backends["auk"]._engine._child._command[-1] == "flash"
    assert backends["auk_base"]._engine._child._command[-1] == "base"
    config = settings(
        tmp_path,
        'default_backend="qwen21"\ndefault_voice_backend="auk_base"\nvisible_voice_backends=["auk"]\n[qwen21]\nquantize=0\n',
    )
    assert config.visible_voice_backends == ("auk_base", "auk")
    with pytest.raises(ConfigError):
        build_voice_backends(replace(config, visible_voice_backends=("missing",)))


def test_singular_voice_backend_assembly_still_uses_shared_residency():
    from studio.l3_interface_adapters.gateways.audio.stub_voice_backend_gateway import StubVoiceBackendGateway

    studio = assemble_studio(
        {"fake": FakeBackendGateway()},
        {"fake": NoPromptRewriter()},
        "fake",
        ("fake",),
        voice_backend=StubVoiceBackendGateway(),
    )
    studio.residency.activate("auk")
    assert studio.residency.active_id() == "auk"
    studio.shutdown()


@pytest.mark.parametrize("dedicated", [False, True])
def test_drama_builder_keeps_the_engine_environment_separate(tmp_path, dedicated):
    from studio.l4_frameworks_and_drivers.main import build_voice_backends

    text = 'default_backend="qwen21"\nvisible_voice_backends=["auk_base", "drama3"]\n[qwen21]\nquantize=0\n[drama3]\n'
    if dedicated:
        text += 'python_path="runtime/bin/python"\nchild_script="drama.py"\n'
    config = settings(tmp_path, text)
    gateway = build_voice_backends(config)["drama3"]
    assert gateway.capabilities().default_mode == "generate"
    command = gateway._child._command
    if dedicated:
        assert command == [str(tmp_path / "runtime/bin/python"), str(tmp_path / "drama.py")]
    else:
        assert command[:3] == ["uv", "run", "--script"] and command[-1].endswith("drama3_child.py")


def test_each_model_has_its_own_gateway_class_under_its_media_family():
    from pathlib import Path

    from studio.l4_frameworks_and_drivers.main import BACKENDS, VIDEO_BACKENDS, VOICE_BACKENDS

    config = load_config(Path(__file__).parents[2] / "studio.toml")
    models = []
    for family, builders in (("image", BACKENDS), ("video", VIDEO_BACKENDS), ("audio", VOICE_BACKENDS)):
        for backend_id, builder in builders.items():
            gateway = builder(config)
            assert gateway.capabilities().backend_id == backend_id
            assert f".gateways.{family}." in type(gateway).__module__
            models.append(type(gateway))
    assert len(models) == len(set(models)) == 10


LORA_TABLE = '[[{id}.loras]]\nid = "example_warm"\nlabel = "Warm"\npath = "warm.safetensors"\n{modes}'


@pytest.mark.parametrize("backend_id", ["qwen21", "qwen21_turbo", "viggle_turbo"])
def test_a_qwen_backend_offers_the_loras_of_its_section(tmp_path: Path, backend_id):
    text = (
        f'default_backend = "{backend_id}"\n[{backend_id}]\nmodel_dir = "turbo"\nlora_path = "speed.safetensors"\n'
        + LORA_TABLE.format(id=backend_id, modes='modes = ["edit"]\n')
    )
    backend = build_backends(settings(tmp_path, text))[backend_id]

    record = backend.capabilities()
    assert [lora.id for lora in record.mode("edit").loras] == ["example_warm"]
    assert record.mode("generate").loras == ()


def test_a_lora_that_names_a_mode_the_model_lacks_stops_the_start(tmp_path: Path):
    text = 'default_backend = "qwen21"\n' + LORA_TABLE.format(id="qwen21", modes='modes = ["inpaint"]\n')
    with pytest.raises(ConfigError, match=r"\[qwen21\]: A LoRA names a mode"):
        build_backends(settings(tmp_path, text))


def test_flux2_refuses_a_lora_table(tmp_path: Path):
    text = 'default_backend = "flux2"\n[flux2]\nmodel_dir = "klein"\n' + LORA_TABLE.format(id="flux2", modes="")
    with pytest.raises(ConfigError, match="takes no LoRAs"):
        build_backends(settings(tmp_path, text))


@pytest.mark.parametrize("backend_id", ["ltx25_mlx", "ltx23_mlx"])
def test_a_video_backend_offers_the_loras_of_its_own_section(tmp_path: Path, backend_id):
    text = f'default_backend = "qwen21"\ndefault_video_backend = "{backend_id}"\n[qwen21]\n' + LORA_TABLE.format(
        id=backend_id, modes=""
    )
    backend = build_video_backends(settings(tmp_path, text))[backend_id]

    assert [lora.id for lora in backend.capabilities().loras] == ["example_warm"]
    assert backend._runner._lora_files.files[0].path == str((tmp_path / "warm.safetensors").resolve())


def pack_settings(tmp_path: Path, section: str = "") -> Config:
    """Plugin image and voice models, the example pack as the one video model, and its section."""
    return settings(
        tmp_path,
        'default_backend = "example_image"\n'
        'default_video_backend = "example_pack"\n'
        'default_voice_backend = "example_voice"\n'
        '[mlx_video]\ncli_path = "bin/ltx-2-mlx"\n' + section,
    )


@pytest.mark.parametrize("family", ["ltx25", "ltx23"])
def test_a_pack_is_built_like_the_base_packs_from_its_own_section(monkeypatch, tmp_path: Path, family):
    from studio.l3_interface_adapters.gateways.video.ltx_pack.ltx_pack_backend_gateway import LtxPackBackendGateway

    registry = install(monkeypatch, pack_entries(replace(PACK, family=family)))
    section = '[example_pack]\npack_dir = "pack"\n' + LORA_TABLE.format(id="example_pack", modes="")

    def enhanced(prompt, references):
        return False

    backend = build_video_backends(pack_settings(tmp_path, section), enhanced, registry)["example_pack"]

    assert isinstance(backend, LtxPackBackendGateway)
    assert backend.capabilities().name == "Example pack"
    assert [lora.id for lora in backend.capabilities().loras] == ["example_warm"]
    runner = backend._runner
    assert (runner._model, runner._model_key) == (str((tmp_path / "pack").resolve()), "pack_dir")
    assert runner._cli == str(tmp_path / "bin/ltx-2-mlx")
    assert runner._enhances is True and runner._enhanced_prompt is enhanced
    assert runner._keyframe_two_stage is (family == "ltx23")
    assert runner._lora_files.files[0].path == str(tmp_path / "warm.safetensors")


def test_each_field_of_the_record_reaches_the_pack_s_capabilities(monkeypatch, tmp_path: Path):
    pack = replace(PACK, description="A pack.", precision="int4", edit=True, audio=True, fast_mode=True)
    backend = build_video_backends(pack_settings(tmp_path), plugins=install(monkeypatch, pack_entries(pack)))[
        "example_pack"
    ]

    record = backend.capabilities()
    assert (record.description, record.precision, record.fast_mode) == ("A pack.", "int4", True)
    assert [mode.id for mode in record.modes] == ["generate", "edit"]
    assert record.mode("generate").accepts_audio is True


def test_a_pack_that_its_record_cannot_build_stops_the_start(monkeypatch, tmp_path: Path):
    registry = install(monkeypatch, pack_entries(replace(PACK, family="ltx23", edit=True)))
    with pytest.raises(ConfigError, match="Cannot build the LTX pack example_pack: only an ltx25 pack"):
        build_video_backends(pack_settings(tmp_path), plugins=registry)


@pytest.mark.parametrize("section", ["", '[example_pack]\npack_dir = ""\n'])
def test_a_pack_with_no_folder_setting_still_starts_and_its_run_names_the_setting(monkeypatch, tmp_path, section):
    """`--all-backends` offers every installed pack, also one that the settings do not mention.
    A blank setting stays blank: resolved, it would name the folder of the settings file."""
    registry = install(monkeypatch, pack_entries())
    backend = build_video_backends(pack_settings(tmp_path, section), plugins=registry)["example_pack"]
    with pytest.raises(StudioError, match=r"Set pack_dir under \[example_pack\]"):
        backend.run(VideoJob("a cat", 384, 384, 121, 24, 7))


def test_a_pack_takes_the_base_packs_rewriter_and_only_visible_packs_are_imported(monkeypatch, tmp_path: Path):
    from studio.l4_frameworks_and_drivers import main

    entries = pack_entries(PACK, replace(PACK, backend_id="hidden_pack"))
    studio = main.create_studio(pack_settings(tmp_path), stub=True, plugins=install(monkeypatch, entries))
    try:
        assert studio.video_catalog is not None and studio.video_rewriter is not None
        assert studio.video_catalog.get("example_pack").capabilities().name == "Example pack"
        assert studio.video_rewriter.modes() == ("generate", "edit")
    finally:
        studio.shutdown()
    assert not next(item for item in entries if item.name == "hidden_pack").load.called


def test_a_real_pack_needs_the_host_platform_and_gets_the_gemma_rewriter(monkeypatch, tmp_path: Path):
    """A plugin of its own has no rewriter, so its modes are empty. The Gemma rewriter offers Generate."""
    from studio.l3_interface_adapters.gateways.video.ltx_pack.ltx_pack_backend_gateway import LtxPackBackendGateway
    from studio.l4_frameworks_and_drivers import main

    platform = Mock()
    monkeypatch.setattr(main, "require_mlx", platform)
    studio = main.create_studio(pack_settings(tmp_path), plugins=install(monkeypatch, pack_entries()))
    try:
        assert studio.video_catalog is not None and studio.video_rewriter is not None
        assert isinstance(studio.video_catalog.get("example_pack"), LtxPackBackendGateway)
        assert studio.video_rewriter.modes() == ("generate",)
    finally:
        studio.shutdown()
    platform.assert_called_once_with()


def test_an_engine_error_names_the_pack_and_its_lora_by_id_and_never_by_path(monkeypatch, tmp_path: Path):
    """The runner rewords its LoRA paths, and the pack's gateway rewords its folder around it."""
    from studio.l1_entities.lora import LoraUse

    folder = tmp_path / "example-pack-q8"
    folder.mkdir()
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin/ltx-2-mlx").write_text("")
    (tmp_path / "warm.safetensors").write_bytes(b"weights")
    section = '[example_pack]\npack_dir = "example-pack-q8"\n' + LORA_TABLE.format(id="example_pack", modes="")
    registry = install(monkeypatch, pack_entries())
    backend = build_video_backends(pack_settings(tmp_path, section), plugins=registry)["example_pack"]

    def engine(command, *arguments, **options):
        lora = command[command.index("--lora") + 1]
        raise StudioError(f"cannot open {command[command.index('--model') + 1]}/transformer.safetensors | lora {lora}")

    backend._runner._execute_process = engine
    with pytest.raises(StudioError) as failed:
        backend.run(VideoJob("a cat", 384, 384, 49, 24, 7, loras=(LoraUse("example_warm", 1.0),)))

    assert str(failed.value) == "cannot open the example_pack pack/transformer.safetensors | lora LoRA example_warm"
    assert str(tmp_path) not in str(failed.value)


def test_the_example_pack_is_a_valid_record(monkeypatch, tmp_path: Path):
    from importlib import import_module

    from studio.l4_frameworks_and_drivers.main import ltx_pack_backend

    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / "examples/model_plugin"))
    pack = import_module("open_imagine_example.ltx").plugin

    backend = ltx_pack_backend(pack_settings(tmp_path), pack)
    assert backend.capabilities().backend_id == "example_ltx"
    assert [mode.id for mode in backend.capabilities().modes] == ["generate"]
