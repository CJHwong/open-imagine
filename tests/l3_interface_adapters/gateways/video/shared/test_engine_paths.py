from pathlib import Path

from studio.l3_interface_adapters.gateways.video.shared.engine_paths import (
    child_command,
    engine_executable,
)


def test_an_engine_checkout_runs_a_child_under_its_own_python(tmp_path):
    engine = tmp_path / "ltx-2-mlx"
    engine.touch()
    (tmp_path / "python").touch()

    assert child_command(str(engine), "child.py", "arg") == [str(tmp_path / "python"), "child.py", "arg"]


def test_the_wrapper_runs_a_child_itself(tmp_path):
    wrapper = tmp_path / "ltx_engine.py"
    wrapper.touch()

    assert child_command(str(wrapper), "child.py", "arg") == [
        str(wrapper),
        "--studio-child",
        "child.py",
        "arg",
    ]


def test_an_empty_setting_names_the_wrapper_that_ships_with_the_studio():
    wrapper = Path(engine_executable({}))

    assert wrapper.name == "ltx_engine.py"
    assert wrapper.parent.name == "ltx_runtime"
    assert wrapper.is_file()


def test_a_configured_engine_wins(tmp_path):
    engine = tmp_path / "engine"
    engine.touch()

    assert engine_executable({"cli_path": str(engine)}) == str(engine)
