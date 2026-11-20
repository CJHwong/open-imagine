import os
import re
import sys
from pathlib import Path

from studio.l3_interface_adapters.gateways.music.yue2_cuda import construction, yue2_pack_spec
from studio.l3_interface_adapters.gateways.music.yue2_cuda import yue2_cuda_child as child

CHILD = Path(child.__file__)


class Config:
    def __init__(self, settings):
        self._settings = settings

    def backend(self, _):
        return self._settings

    def required(self, _, key):
        return self._settings[key]


def pack_assets(provider, settings):
    assert provider.ready_assets is not None
    return provider.ready_assets(Config(settings))


def header_pins(path: Path) -> dict:
    """package -> the version its `==` pin in the script's PEP 723 header names."""
    header = path.read_text().split("# /// script", 1)[1].split("# ///", 1)[0]
    return dict(re.findall(r'"([A-Za-z0-9_.-]+)==([^"]+)"', header))


def test_each_declared_version_is_the_build_of_a_release_the_header_pins():
    pins = header_pins(CHILD)

    for package, runtime in yue2_pack_spec.RUNTIME_VERSIONS.items():
        assert pins.get(package) == runtime.split("+")[0], package


def test_the_studio_expects_the_manifest_the_child_checks_and_writes(monkeypatch):
    monkeypatch.setattr(child, "source_revision", lambda model: "8f24312")
    monkeypatch.setattr(yue2_pack_spec, "source_revision", lambda model: "8f24312")

    (asset,) = pack_assets(construction.NVFP4_PROVIDER, {"pack_dir": "/packs"})

    assert asset.location == os.path.join("/packs", "m-a-p--YuE2-3B")
    assert asset.expected is not None
    assert asset.expected() == child.expected_manifest("m-a-p/YuE2-3B")
    assert asset.expected()["versions"] == {"torch": "2.15.0+cu132", "torchao": "0.18.0", "mslk": "1.4.0+cu130"}
    assert asset.expected()["act_quant"]["use_dynamic_per_tensor_scale"] is True


def test_an_entry_that_runs_in_the_engine_reads_no_pack():
    assert pack_assets(construction.PROVIDER, {}) == ()
    assert pack_assets(construction.NVFP4_PROVIDER, {"quantize": "fp8"}) == ()
    assert len(pack_assets(construction.PROVIDER, {"quantize": "nvfp4"})) == 1


def test_a_matching_environment_has_no_mismatch_and_another_names_each_package():
    assert yue2_pack_spec.version_mismatch(dict(yue2_pack_spec.RUNTIME_VERSIONS)) is None
    assert yue2_pack_spec.version_mismatch({"torch": "2.15.0+cu132", "torchao": "0.18.0"}) == (
        "mslk is None, the header installs 1.4.0+cu130"
    )


def test_main_refuses_an_environment_the_header_does_not_declare(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "torch", type(sys)("torch"))
    monkeypatch.setattr(child, "versions", lambda: {**yue2_pack_spec.RUNTIME_VERSIONS, "mslk": "1.4.0"})
    monkeypatch.setattr(child, "load", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("loaded")))
    monkeypatch.setattr(sys, "argv", ["child", "--quantize", "nvfp4", "--pack-dir", "/packs"])

    assert child.main() == 2
    assert "mslk is 1.4.0, the header installs 1.4.0+cu130" in capsys.readouterr().err
