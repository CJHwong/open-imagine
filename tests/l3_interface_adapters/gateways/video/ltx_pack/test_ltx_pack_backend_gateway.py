from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import StudioError
from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l3_interface_adapters.gateways.video.ltx_pack.ltx_pack_backend_gateway import LtxPackBackendGateway
from studio.l3_interface_adapters.gateways.video.shared.capabilities import ltx_pack_capabilities
from tests.support.loras import lora_table

JOB = VideoJob("a cat", 384, 384, 121, 24, 7)


def capabilities():
    return ltx_pack_capabilities("example_pack", "Example pack", "ltx25")


def gateway(folder, runner=None, loras=None):
    runner = runner or Mock()
    runner.run.return_value = VideoResult(b"mp4", 384, 384, 121, 24, 7)
    return LtxPackBackendGateway(runner, capabilities(), str(folder), loras), runner


def test_a_run_and_a_batch_go_to_the_runner_once_the_folder_is_there(tmp_path):
    backend, runner = gateway(tmp_path)
    progress, cancelled = Mock(), Mock()

    assert backend.run(JOB, progress, cancelled).mp4 == b"mp4"
    runner.run.assert_called_once_with(JOB, progress, cancelled)

    runner.run_batch.return_value = ["retained"]
    completed, started = Mock(), Mock()
    assert backend.run_batch([JOB], completed, started, progress, cancelled) == ["retained"]
    runner.run_batch.assert_called_once_with([JOB], completed, started, progress, cancelled)
    assert backend.release() is None


def test_the_record_is_the_pack_s_own_and_offers_its_loras(tmp_path):
    backend, _ = gateway(tmp_path, loras=lora_table(tmp_path))

    assert backend.capabilities().backend_id == "example_pack"
    assert [lora.id for lora in backend.capabilities().loras] == ["example_warm"]
    assert gateway(tmp_path)[0].capabilities() == capabilities()


def test_a_missing_folder_is_refused_before_the_engine_and_only_the_log_names_it(tmp_path, capsys):
    """The engine would take the path for a Hugging Face repo id, and name that id, not the setting."""
    folder = tmp_path / "example-pack-q8"
    backend, runner = gateway(folder)

    with pytest.raises(StudioError, match="weights of the example_pack pack are not on disk") as refused:
        backend.run(JOB)
    with pytest.raises(StudioError, match="not on disk"):
        backend.run_batch([JOB], Mock(), Mock(), Mock(), Mock())

    assert str(folder) not in str(refused.value)
    assert str(folder) in capsys.readouterr().err
    runner.run.assert_not_called()
    runner.run_batch.assert_not_called()


def test_a_pack_with_no_folder_setting_names_the_setting():
    backend, runner = gateway("")

    with pytest.raises(StudioError, match=r"Set pack_dir under \[example_pack\]"):
        backend.run(JOB)
    runner.run.assert_not_called()


def test_an_engine_error_that_quotes_the_folder_names_the_model(tmp_path):
    folder = tmp_path / "example-pack-q8"
    folder.mkdir()
    runner = Mock()
    runner.run.side_effect = StudioError(f"The engine could not read {folder}")
    backend, _ = gateway(folder, runner)

    with pytest.raises(StudioError) as failed:
        backend.run(JOB)

    assert str(failed.value) == "The engine could not read the example_pack pack"


def test_a_pack_whose_folder_cannot_be_read_is_refused_by_the_model_s_name(tmp_path):
    parent = tmp_path / "example-hidden-folder"
    folder = parent / "example-pack-q8"
    folder.mkdir(parents=True)
    backend, runner = gateway(folder)
    parent.chmod(0)
    try:
        with pytest.raises(StudioError) as refused:
            backend.run(JOB)
    finally:
        parent.chmod(0o755)

    assert "example-hidden-folder" not in str(refused.value)
    runner.run.assert_not_called()


def test_an_engine_error_that_quotes_a_file_of_the_pack_names_the_model_and_not_the_file(tmp_path):
    folder = tmp_path / "example-pack-q8"
    folder.mkdir()
    (folder / "example-private-variant.safetensors").write_bytes(b"")
    runner = Mock()
    runner.run.side_effect = StudioError(f"bad header in {folder}/example-private-variant.safetensors")
    backend, _ = gateway(folder, runner)

    with pytest.raises(StudioError) as failed:
        backend.run(JOB)

    assert str(failed.value) == "bad header in a file of the example_pack pack"
