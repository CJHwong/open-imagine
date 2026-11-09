from studio.l3_interface_adapters.gateways.video.minimax_h3 import download


def test_download_pins_each_component_and_keeps_the_model_terms(tmp_path):
    calls = []

    download.download(tmp_path, lambda repo, **options: calls.append((repo, options)))

    assert len(calls) == 15
    assert all(len(options["revision"]) == 40 and options["local_dir"].is_relative_to(tmp_path) for _, options in calls)
    assert any(options["filename"] == "LICENSE" for _, options in calls)
    assert any(options["filename"] == "NOTICE" for _, options in calls)
    assert not tmp_path.exists() or not list(tmp_path.iterdir())


def test_download_cli_selects_an_explicit_folder_without_loading_a_model(tmp_path, monkeypatch):
    import runpy
    import sys
    from unittest.mock import Mock

    fetch = Mock()
    monkeypatch.setattr("huggingface_hub.hf_hub_download", fetch)
    monkeypatch.setattr(sys, "argv", ["download", "--model-dir", str(tmp_path)])

    download.main()

    assert fetch.call_count == 15
    monkeypatch.delitem(sys.modules, "studio.l3_interface_adapters.gateways.video.minimax_h3.download")
    runpy.run_module("studio.l3_interface_adapters.gateways.video.minimax_h3.download", run_name="__main__")
    assert fetch.call_count == 30
