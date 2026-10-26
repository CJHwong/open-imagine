from pathlib import Path

import pytest

from studio.l4_frameworks_and_drivers.config import ConfigError, load_config
from studio.l4_frameworks_and_drivers.lora_table import lora_files, no_loras


def settings(tmp_path: Path, text: str):
    path = tmp_path / "studio.toml"
    path.write_text('default_backend = "qwen21"\n' + text)
    return load_config(path)


def test_a_section_s_lora_tables_become_its_offer(tmp_path):
    config = settings(
        tmp_path,
        "[qwen21]\nmax_loras = 2\n"
        '[[qwen21.loras]]\nid = "example_warm"\nlabel = "Warm"\npath = "loras/warm.safetensors"\n'
        "strength = 0.8\nmin_strength = -0.5\nmax_strength = 1.5\nstrength_step = 0.1\nrecommended = [0.6, 1]\n"
        'trigger = "warm light"\nhint = "Warmer light."\nmodes = ["generate"]\n',
    )

    files = lora_files(config, "qwen21")

    entry = files.files[0]
    assert files.max_loras == 2
    assert entry.path == str((tmp_path / "loras/warm.safetensors").resolve())
    assert entry.modes == ("generate",)
    assert (entry.lora.id, entry.lora.label, entry.lora.strength) == ("example_warm", "Warm", 0.8)
    assert (entry.lora.min_strength, entry.lora.max_strength, entry.lora.strength_step) == (-0.5, 1.5, 0.1)
    assert entry.lora.recommended == (0.6, 1.0)
    assert (entry.lora.trigger, entry.lora.hint) == ("warm light", "Warmer light.")


def test_a_section_without_tables_offers_none_and_one_table_takes_one_at_a_time(tmp_path):
    assert lora_files(settings(tmp_path, "[qwen21]\n"), "qwen21").files == ()
    config = settings(tmp_path, '[[qwen21.loras]]\nid = "example_warm"\nlabel = "Warm"\npath = "/w.safetensors"\n')
    assert lora_files(config, "qwen21").max_loras == 1


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('[qwen21]\nloras = "warm"\n', "must be a list"),
        ("[qwen21]\nloras = [1]\n", "must be a table"),
        ('[[qwen21.loras]]\nid = "example_warm"\nlabel = "W"\npath = "/w"\ncolour = "red"\n', "does not know: colour"),
        ('[[qwen21.loras]]\nid = "example_warm"\npath = "/w"\n', "needs label"),
        ('[[qwen21.loras]]\nid = "example_warm"\nlabel = "W"\npath = "/w"\nstrength = "high"\n', "must be numbers"),
        ('[[qwen21.loras]]\nid = "example_warm"\nlabel = "W"\npath = "/w"\nstrength = true\n', "must be numbers"),
        ('[[qwen21.loras]]\nid = "example_warm"\nlabel = "W"\npath = "/w"\nrecommended = [1]\n', "two numbers"),
        ('[[qwen21.loras]]\nid = "example_warm"\nlabel = "W"\npath = "/w"\nmin_strength = 0.1\n', "from 0 or below"),
        ('[[qwen21.loras]]\nid = "example_warm"\nlabel = "W"\npath = "/w"\nmodes = "edit"\n', "list of mode ids"),
        ('[[qwen21.loras]]\nid = "example_warm"\nlabel = "W"\npath = "/w"\ntrigger = 1\n', "trigger must be text"),
        ('[[qwen21.loras]]\nid = "Warm"\nlabel = "W"\npath = "/w"\n', "lowercase"),
        ('[[qwen21.loras]]\nid = "example_warm"\nlabel = "W"\npath = ""\n', "needs path"),
        ('[[qwen21.loras]]\nid = "example_warm"\nlabel = "W"\npath = "  "\n', "needs path"),
        ('[qwen21]\nmax_loras = "2"\n', "whole number"),
        ("[qwen21]\nmax_loras = true\n", "whole number"),
        ('[qwen21]\nmax_loras = 0\n[[qwen21.loras]]\nid = "example_warm"\nlabel = "W"\npath = "/w"\n', "at least 1"),
    ],
)
def test_a_bad_table_stops_the_start_and_names_the_section(tmp_path, text, message):
    with pytest.raises(ConfigError, match=message):
        lora_files(settings(tmp_path, text), "qwen21")


def test_a_backend_that_takes_no_loras_refuses_a_table(tmp_path):
    no_loras(settings(tmp_path, "[flux2]\n"), "flux2")
    config = settings(tmp_path, '[[flux2.loras]]\nid = "example_warm"\nlabel = "W"\npath = "/w"\n')
    with pytest.raises(ConfigError, match=r"\[flux2\] takes no LoRAs"):
        no_loras(config, "flux2")


def test_an_entry_that_is_not_a_table_keeps_its_shape_for_the_reader_to_refuse(tmp_path):
    config = settings(tmp_path, '[qwen21]\nloras = ["warm"]\n')
    assert config.backend("qwen21")["loras"] == ["warm"]


def test_a_video_table_refuses_modes_because_one_set_serves_every_mode(tmp_path):
    table = '[[ltx25_mlx.loras]]\nid = "example_warm"\nlabel = "W"\npath = "/w"\n'
    assert lora_files(settings(tmp_path, table), "ltx25_mlx", video=True).files[0].modes == ()
    with pytest.raises(ConfigError, match="applies to every mode, so remove modes"):
        lora_files(settings(tmp_path, table + 'modes = ["generate"]\n'), "ltx25_mlx", video=True)


def test_a_video_table_under_the_engine_section_points_to_the_model_s_own(tmp_path):
    config = settings(tmp_path, '[[mlx_video.loras]]\nid = "example_warm"\nlabel = "W"\npath = "/w"\n')
    with pytest.raises(ConfigError, match=r"Put LoRA tables under \[ltx23_mlx\], not \[mlx_video\]"):
        lora_files(config, "ltx23_mlx", video=True)


def test_a_path_that_links_to_a_cache_blob_keeps_its_own_name(tmp_path):
    blob = tmp_path / "blobs" / "41215670f21f"
    blob.parent.mkdir()
    blob.write_bytes(b"weights")
    link = tmp_path / "snapshots" / "pytorch_lora_weights.safetensors"
    link.parent.mkdir()
    link.symlink_to(blob)
    config = settings(
        tmp_path,
        '[[qwen21.loras]]\nid = "example_warm"\nlabel = "W"\npath = "snapshots/x/../pytorch_lora_weights.safetensors"\n',
    )

    # MLX reads the format from the extension, and the blob has none.
    assert lora_files(config, "qwen21").files[0].path == str(link)
