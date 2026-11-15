import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from studio.l4_frameworks_and_drivers import engines
from studio.l4_frameworks_and_drivers.config import load_config
from studio.l4_frameworks_and_drivers.engines import EngineUnavailable, mlx_available, require_engines
from studio.l4_frameworks_and_drivers.main import create_studio

CONFIG = (
    'default_backend = "qwen21"\nvisible_backends = ["qwen21"]\n[qwen21]\nquantize = 0\n'
    '[mlx_video]\nmodel_ltx25 = "pack-25"\n'
)


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "studio.toml"
    path.write_text(CONFIG)
    return load_config(path)


@pytest.fixture
def no_mlx(monkeypatch):
    monkeypatch.setattr(engines, "mlx_available", lambda: False)


@pytest.fixture
def no_engine(monkeypatch):
    """A host with neither engine, so the refusal does not depend on this machine."""
    monkeypatch.setattr(engines, "mlx_available", lambda: False)
    monkeypatch.setattr(engines, "cuda_available", lambda: False)


@pytest.fixture
def needs_mlx():
    if not mlx_available():
        pytest.skip("this host has no MLX")


def test_a_machine_without_mlx_is_refused_by_name(no_engine, config):
    """The message names the engine the visible backends need, and the way out."""
    with pytest.raises(EngineUnavailable, match="no MLX GPU") as refused:
        create_studio(config)
    assert "--stub" in str(refused.value)


def test_a_cuda_host_runs_a_cuda_backend_and_refuses_an_mlx_one(monkeypatch):
    """The gate reads the engine each visible backend names, not the platform."""
    monkeypatch.setattr(engines, "mlx_available", lambda: False)
    monkeypatch.setattr(engines, "cuda_available", lambda: True)
    require_engines({"cuda"})
    with pytest.raises(EngineUnavailable, match="no MLX GPU"):
        require_engines({"mlx"})


def test_an_unknown_engine_is_named_rather_than_silently_passing(monkeypatch):
    monkeypatch.setattr(engines, "mlx_available", lambda: True)
    monkeypatch.setattr(engines, "cuda_available", lambda: False)
    with pytest.raises(EngineUnavailable):
        require_engines({"vulkan"})


def test_an_empty_requirement_does_not_probe_the_host(monkeypatch):
    """A plugin-only studio owns its runtime, so it must not ask for an engine."""
    monkeypatch.setattr(engines, "mlx_available", Mock(side_effect=AssertionError("no probe")))
    require_engines(set())


def test_a_host_with_no_nvidia_smi_has_no_cuda(monkeypatch):
    monkeypatch.setattr(engines.shutil, "which", lambda name: None)
    assert engines.cuda_available() is False


def test_nvidia_smi_listing_a_gpu_is_cuda(monkeypatch):
    monkeypatch.setattr(engines.shutil, "which", lambda name: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(
        engines.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="GPU 0: NVIDIA GB10 (UUID: GPU-1)\n"),
    )
    assert engines.cuda_available() is True


def test_nvidia_smi_failing_is_no_cuda(monkeypatch):
    monkeypatch.setattr(engines.shutil, "which", lambda name: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(
        engines.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=9, stdout=""),
    )
    assert engines.cuda_available() is False


def test_available_engines_reports_both_probes(monkeypatch):
    monkeypatch.setattr(engines, "mlx_available", lambda: False)
    monkeypatch.setattr(engines, "cuda_available", lambda: True)
    assert engines.available_engines() == frozenset({"cuda"})
    monkeypatch.setattr(engines, "mlx_available", lambda: True)
    assert engines.available_engines() == frozenset({"mlx", "cuda"})


def test_the_stub_still_builds_where_mlx_is_missing(no_mlx, config):
    """Page work stays possible on a machine that cannot run an engine at all."""
    assert create_studio(config, stub=True).active_capabilities().backend_id == "qwen21"


def test_a_boundary_stub_uses_the_calibrated_machine_size(tmp_path, no_mlx):
    path = tmp_path / "studio.toml"
    path.write_text(
        'default_backend = "qwen21"\nvisible_backends = ["qwen21"]\n[qwen21]\nquantize = 0\n'
        '[memory]\npolicy = "boundary"\n'
    )

    studio = create_studio(load_config(path), stub=True)

    assert studio.residency.status()["boundary_gib"] == 64.0 * 84 / 100
    studio.shutdown()


def test_the_turbo_and_video_stubs_build_without_weights_or_mlx(tmp_path, no_mlx):
    path = tmp_path / "studio.toml"
    path.write_text(
        'default_backend = "qwen21_turbo"\n'
        'visible_backends = ["qwen21_turbo"]\n'
        '[qwen21_turbo]\nquantize = 0\nmodel_dir = "missing-qwen-weights"\n'
        '[ltx25]\npython_path = "missing-python"\nmodel_dir = "missing-ltx-weights"\n'
    )

    studio = create_studio(load_config(path), stub=True)

    assert studio.active_capabilities().backend_id == "qwen21_turbo"
    assert studio.handler.__name__ == "StudioHandler"


def test_the_turbo_stub_builds_where_mlx_cannot_be_imported_at_all(tmp_path, monkeypatch):
    """The availability probe is not the import, and this is the test that tells them
    apart. `no_mlx` above only answers no; a host with no mlx package raises on the
    import, and building a backend that reached for mflux would break the page there.

    A None entry halts the import, which is the trick the test below uses too.
    """
    monkeypatch.setitem(sys.modules, "mlx", None)
    monkeypatch.setitem(sys.modules, "mlx.core", None)
    path = tmp_path / "studio.toml"
    path.write_text(
        'default_backend = "qwen21_turbo"\nvisible_backends = ["qwen21_turbo"]\n'
        '[qwen21_turbo]\nquantize = 0\nmodel_dir = "missing-qwen-weights"\n'
    )

    studio = create_studio(load_config(path), stub=True)

    assert studio.active_capabilities().backend_id == "qwen21_turbo"


def test_the_real_studio_builds_where_mlx_runs(needs_mlx, config, tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    studio = create_studio(config)
    try:
        assert studio.active_capabilities().name == "Qwen-Image-2.1"
        assert (tmp_path / ".local/share/open-imagine/private-results/storage.lock").is_file()
    finally:
        studio.shutdown()


def fake_mlx(monkeypatch, gpu_available: bool):
    """A stand-in mlx.core, for builds this machine does not have."""
    core = types.ModuleType("mlx.core")
    device_type = types.SimpleNamespace(gpu=object())
    monkeypatch.setattr(core, "DeviceType", device_type, raising=False)
    monkeypatch.setattr(core, "Device", lambda requested_type: requested_type, raising=False)
    monkeypatch.setattr(
        core,
        "is_available",
        lambda requested_device: requested_device is device_type.gpu and gpu_available,
        raising=False,
    )
    monkeypatch.setitem(sys.modules, "mlx", types.ModuleType("mlx"))
    monkeypatch.setitem(sys.modules, "mlx.core", core)


def test_mlx_gpu_is_detected_without_a_metal_namespace(monkeypatch):
    """The generic GPU probe supports CUDA builds that do not expose Metal."""
    fake_mlx(monkeypatch, gpu_available=True)
    assert mlx_available() is True


def test_a_host_with_no_mlx_package_answers_no(monkeypatch):
    """A machine with MLX not installed is a no, not an ImportError. The caller
    gets a decision to act on either way."""
    monkeypatch.setitem(sys.modules, "mlx.core", None)  # a None entry halts the import
    assert mlx_available() is False


def test_mlx_with_no_device_answers_no(monkeypatch):
    fake_mlx(monkeypatch, gpu_available=False)
    assert mlx_available() is False


def test_a_connect_settings_file_builds_the_dumbpipe_transport(tmp_path, no_mlx):
    from studio.l4_frameworks_and_drivers.connect import DumbpipeTransport

    path = tmp_path / "studio.toml"
    path.write_text(
        'default_backend = "qwen21"\nvisible_backends = ["qwen21"]\n[qwen21]\nquantize = 0\n'
        '[connect]\nenabled = true\nidentity_path = "identity"\n'
    )

    studio = create_studio(load_config(path), stub=True, port=9000)

    assert isinstance(studio.connect, DumbpipeTransport)
    assert studio.connect.status().port == 9000
    studio.shutdown()


def test_nvidia_smi_that_cannot_run_means_no_cuda(monkeypatch):
    monkeypatch.setattr(engines.shutil, "which", lambda name: "/usr/bin/nvidia-smi")

    def broken(*args, **kwargs):
        raise OSError("no driver")

    monkeypatch.setattr(engines.subprocess, "run", broken)
    assert engines.cuda_available() is False


def test_the_page_offers_only_the_models_this_host_can_run(monkeypatch, tmp_path):
    """A CUDA host lists the CUDA model and drops the MLX one, without refusing to start."""
    monkeypatch.setattr(engines, "mlx_available", lambda: False)
    monkeypatch.setattr(engines, "cuda_available", lambda: True)
    path = tmp_path / "studio.toml"
    path.write_text(
        'default_backend = "qwen21"\nvisible_backends = ["qwen21", "qwen21_turbo_cuda"]\n'
        "[qwen21]\nquantize = 0\n"
        '[qwen21_turbo_cuda]\nquantize = "nvfp4"\n'
    )

    studio = create_studio(load_config(path), private_results_dir=tmp_path / "private")
    try:
        assert studio.catalog.visible_ids() == ("qwen21_turbo_cuda",)
        assert studio.catalog.active_id() == "qwen21_turbo_cuda"
    finally:
        studio.shutdown()


def test_the_stub_still_offers_every_model_on_a_host_with_no_engine(monkeypatch, tmp_path):
    monkeypatch.setattr(engines, "mlx_available", lambda: False)
    monkeypatch.setattr(engines, "cuda_available", lambda: False)
    path = tmp_path / "studio.toml"
    path.write_text(
        'default_backend = "qwen21"\nvisible_backends = ["qwen21", "qwen21_turbo_cuda"]\n'
        "[qwen21]\nquantize = 0\n"
        '[qwen21_turbo_cuda]\nquantize = "nvfp4"\n'
    )

    studio = create_studio(load_config(path), stub=True)

    assert studio.catalog.visible_ids() == ("qwen21", "qwen21_turbo_cuda")
    studio.shutdown()


def test_a_studio_with_no_image_backend_says_so(monkeypatch, tmp_path):
    """Every engine is present, so nothing is missing to name; the list itself is empty."""
    monkeypatch.setattr(engines, "mlx_available", lambda: True)
    monkeypatch.setattr(engines, "cuda_available", lambda: False)
    path = tmp_path / "studio.toml"
    path.write_text('default_backend = "qwen21"\nvisible_backends = []\n')

    with pytest.raises(EngineUnavailable, match="no Image backend is offered"):
        create_studio(load_config(path))
