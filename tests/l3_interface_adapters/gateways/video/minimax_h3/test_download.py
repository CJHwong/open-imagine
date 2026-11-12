from studio.l3_interface_adapters.gateways.video.minimax_h3 import download

PACK = "pipenetwork/MiniMax-H3-MLX-8bit"
PACK_REVISION = "e55f97c8ebf340066de8d6b4554a2a6767fe54e9"


def test_download_pins_each_component_and_keeps_the_model_terms(tmp_path):
    calls = []

    download.download(tmp_path, lambda repo, **options: calls.append((repo, options)))

    assert len(calls) == 26
    assert all(len(options["revision"]) == 40 and options["local_dir"].is_relative_to(tmp_path) for _, options in calls)
    assert any(options["filename"] == "LICENSE" for _, options in calls)
    assert any(options["filename"] == "NOTICE" for _, options in calls)
    assert not tmp_path.exists() or not list(tmp_path.iterdir())


def test_download_fetches_the_pre_quantized_pack_into_the_dit_folder(tmp_path):
    calls = []

    download.download(tmp_path, lambda repo, **options: calls.append((repo, options)))

    assert {repo for repo, _ in calls} == {PACK, "ddalcu/MiniMax-H3-FL2VA-MLX-Serve-8bit", "MiniMaxAI/MiniMax-H3"}
    pack = [(options["filename"], options["revision"], options["local_dir"]) for repo, options in calls if repo == PACK]
    shards = {f"model-{index:05d}-of-00007.safetensors" for index in range(1, 8)}
    terms = {"model.safetensors.index.json", "config.json", "quant_config.json", "LICENSE", "README.md"}
    assert {filename for filename, _, _ in pack} == shards | terms
    assert {revision for _, revision, _ in pack} == {PACK_REVISION}
    assert {folder for _, _, folder in pack} == {tmp_path / "h3-dit-q8"}


def test_download_cli_selects_an_explicit_folder_without_loading_a_model(tmp_path, monkeypatch):
    import runpy
    import sys
    from unittest.mock import Mock

    fetch = Mock()
    monkeypatch.setattr("huggingface_hub.hf_hub_download", fetch)
    monkeypatch.setattr(sys, "argv", ["download", "--model-dir", str(tmp_path)])

    download.main()

    assert fetch.call_count == 26
    monkeypatch.delitem(sys.modules, "studio.l3_interface_adapters.gateways.video.minimax_h3.download")
    runpy.run_module("studio.l3_interface_adapters.gateways.video.minimax_h3.download", run_name="__main__")
    assert fetch.call_count == 52
