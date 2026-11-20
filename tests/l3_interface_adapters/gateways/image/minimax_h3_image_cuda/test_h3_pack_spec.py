import re
import sys
from pathlib import Path

from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda import construction, h3_pack_spec
from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda import minimax_h3_image_cuda_child as child

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

    for package, runtime in h3_pack_spec.RUNTIME_VERSIONS.items():
        assert pins.get(package) == runtime.split("+")[0], package


def test_the_studio_expects_the_manifest_the_child_checks_and_writes(monkeypatch):
    monkeypatch.setattr(child, "source_revision", lambda model: "5f90473")
    monkeypatch.setattr(h3_pack_spec, "source_revision", lambda model: "5f90473")

    (asset,) = pack_assets(construction.PROVIDER, {"pack_dir": "/packs"})

    assert asset.expected is not None
    assert asset.expected() == child.expected_manifest("MiniMaxAI/MiniMax-H3-Image", "fp8")
    assert asset.expected() == {
        "format": 1,
        "model": "MiniMaxAI/MiniMax-H3-Image",
        "quantize": "fp8",
        "recipe": "w8a8-per-row",
        "versions": {"torch": "2.15.0+cu132", "torchao": "0.18.0", "diffusers": "0.43.0"},
        "source": "5f90473",
    }


def test_a_matching_environment_has_no_mismatch_and_another_names_each_package():
    assert h3_pack_spec.version_mismatch(dict(h3_pack_spec.RUNTIME_VERSIONS)) is None
    assert h3_pack_spec.version_mismatch({**h3_pack_spec.RUNTIME_VERSIONS, "torch": "2.14.1+cu130"}) == (
        "torch is 2.14.1+cu130, the header installs 2.15.0+cu132"
    )


def test_main_refuses_an_environment_the_header_does_not_declare(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "torch", type(sys)("torch"))
    monkeypatch.setattr(child, "versions", lambda: {**h3_pack_spec.RUNTIME_VERSIONS, "diffusers": "0.44.0"})
    monkeypatch.setattr(child, "load", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("loaded")))
    monkeypatch.setattr(sys, "argv", ["child", "--quantize", "fp8", "--pack-dir", "/packs"])

    assert child.main() == 2
    assert "diffusers is 0.44.0, the header installs 0.43.0" in capsys.readouterr().err
