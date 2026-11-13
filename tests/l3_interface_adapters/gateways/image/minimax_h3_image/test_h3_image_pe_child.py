import io
import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from studio.l3_interface_adapters.gateways.image.minimax_h3_image import h3_image_pe_child as child


def png(size=(640, 480)):
    data = io.BytesIO()
    Image.new("RGB", size, "blue").save(data, format="PNG")
    return data.getvalue()


def prompts(tmp_path):
    (tmp_path / "t2i").mkdir(parents=True)
    (tmp_path / "edit").mkdir(parents=True)
    (tmp_path / "t2i/system_prompt.txt").write_text("Answer with one JSON object.\n")
    (tmp_path / "t2i/task_prompt.txt").write_text("Rewrite {} as a caption.\n")
    (tmp_path / "edit/task_prompt.txt").write_text("Rewrite the editing instruction.\n")
    return tmp_path


def enhancer(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "config.json").write_text("{}")
    instance = child.Enhancer(str(pack), None)
    instance.prompt_dir = prompts(tmp_path / "prompts")
    instance.model = Mock()
    instance.processor = Mock()
    return instance


def test_the_last_json_object_wins_over_reasoning_and_a_broken_object():
    text = 'thinking... {"expanded_caption": "a pear", "aspect_ratio": "1:1"} and {bad json}'
    assert child.last_json_object(text)["expanded_caption"] == "a pear"


def test_a_reply_without_json_is_an_input_error():
    with pytest.raises(ValueError, match="no JSON object"):
        child.last_json_object("only words")


def test_a_picture_ratio_is_the_lowest_whole_number():
    assert child.picture_ratio(png((640, 480))) == "4:3"
    assert child.picture_ratio(png((1024, 1024))) == "1:1"


def test_a_missing_pack_is_refused_before_loading(tmp_path):
    with pytest.raises(ValueError, match="missing at"):
        child.Enhancer(str(tmp_path / "nothing"), None).load()


def test_a_generate_rewrite_sends_the_release_system_and_task_prompts(tmp_path):
    instance = enhancer(tmp_path)
    instance.ask = Mock(return_value='caption: {"expanded_caption": "A pear on a table.", "aspect_ratio": "3:2"}')
    reply = instance.answer({"kind": "generate", "prompt": "a pear"})
    assert reply == {"prompt": "A pear on a table.", "ratio": "3:2"}
    messages = instance.ask.call_args.args[0]
    assert messages[0] == {"role": "system", "content": "Answer with one JSON object."}
    assert messages[1]["content"] == "Rewrite a pear as a caption."


def test_an_edit_rewrite_sends_each_picture_with_its_ratio(tmp_path, monkeypatch):
    monkeypatch.setenv("SPEECH_GEN_SCRATCH", str(tmp_path))
    instance = enhancer(tmp_path)
    instance.ask = Mock(return_value='{"expanded_caption": "A red jacket.", "target_aspect_ratio": "4:3"}')
    import base64

    reply = instance.answer({"kind": "edit", "prompt": "make it red", "images": [base64.b64encode(png()).decode()]})
    assert reply == {"prompt": "A red jacket.", "ratio": "4:3"}
    message = instance.ask.call_args.args[0][0]["content"]
    assert "Reference Media: <Picture 1>, aspect_ratio 4:3" in message
    assert 'User Editing Instruction (JSON string): "make it red"' in message
    assert "User Aspect Ratio Selection: adaptive" in message
    assert len(instance.ask.call_args.args[1]) == 1


def test_an_edit_without_a_ratio_answer_keeps_the_requested_one(tmp_path, monkeypatch):
    monkeypatch.setenv("SPEECH_GEN_SCRATCH", str(tmp_path))
    instance = enhancer(tmp_path)
    instance.ask = Mock(return_value='{"expanded_caption": "A red jacket."}')

    reply = instance.answer(
        {"kind": "edit", "prompt": "make it red", "images": [], "ratio": "16:9"},
    )
    assert reply["ratio"] == "16:9"
    assert "User Aspect Ratio Selection: 16:9" in instance.ask.call_args.args[0][0]["content"]


def test_an_empty_prompt_or_unknown_kind_is_refused(tmp_path):
    instance = enhancer(tmp_path)
    with pytest.raises(ValueError, match="Write a prompt"):
        instance.answer({"kind": "generate", "prompt": "  "})
    with pytest.raises(ValueError, match="Unknown"):
        instance.answer({"kind": "inpaint", "prompt": "a pear"})


def test_a_reply_without_a_caption_is_refused(tmp_path):
    instance = enhancer(tmp_path)
    instance.ask = Mock(return_value='{"expanded_caption": "  "}')
    with pytest.raises(ValueError, match="empty caption"):
        instance.answer({"kind": "generate", "prompt": "a pear"})


def test_the_worker_answers_one_json_job_per_line(tmp_path, monkeypatch, capsys):
    instance = enhancer(tmp_path)
    instance.answer = Mock(
        side_effect=[{"prompt": "long", "ratio": "1:1"}, ValueError("bad job"), RuntimeError("engine died")]
    )
    monkeypatch.setattr(sys, "argv", ["worker", "--model-dir", str(tmp_path)])
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}\n{}\n{}\n"))
    instance.load = Mock()
    monkeypatch.setattr(child, "Enhancer", Mock(return_value=instance))
    child.main()
    replies = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert replies[0] == {"prompt": "long", "ratio": "1:1"}
    assert replies[1] == {"error": "bad job", "kind": "input"}
    assert "check its pack" in replies[2]["error"]


def test_the_model_is_loaded_once_and_reports_ready(monkeypatch, tmp_path, capsys):
    load = Mock(return_value=(object(), object()))
    monkeypatch.setitem(sys.modules, "mlx_vlm", SimpleNamespace(load=load))
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "config.json").write_text("{}")
    instance = child.Enhancer(str(pack), None)
    instance.load()
    assert "ready" in capsys.readouterr().err
    load.assert_called_once_with(str(pack))
    assert instance.model is not None and instance.processor is not None


def test_the_ask_uses_the_release_sampling(monkeypatch, tmp_path):
    generate = Mock(return_value=SimpleNamespace(text="reply"))
    template = Mock(return_value="templated text")
    monkeypatch.setitem(sys.modules, "mlx_vlm", SimpleNamespace(generate=generate))
    monkeypatch.setitem(sys.modules, "mlx_vlm.prompt_utils", SimpleNamespace(apply_chat_template=template))
    instance = enhancer(tmp_path)
    assert instance.ask([{"role": "user", "content": "hi"}]) == "reply"
    assert generate.call_args.args[2] == "templated text"
    assert template.call_args.kwargs["num_images"] == 0
    kwargs = generate.call_args.kwargs
    assert (kwargs["temperature"], kwargs["top_p"], kwargs["top_k"]) == (1.0, 0.95, 20)
    assert kwargs["max_tokens"] == child.MAX_TOKENS and kwargs["image"] is None


def test_nested_objects_and_a_stray_close_are_handled():
    text = 'noise {"a": {"b": 1}} } {"c": 2}'
    assert list(child.json_objects(text)) == ['{"a": {"b": 1}}', '{"c": 2}']


def test_the_first_request_loads_the_pack(tmp_path):
    instance = enhancer(tmp_path)
    instance.model = None
    instance.load = Mock(side_effect=lambda: setattr(instance, "model", Mock()))
    instance.ask = Mock(return_value='{"expanded_caption": "A pear.", "aspect_ratio": "1:1"}')
    assert instance.answer({"kind": "generate", "prompt": "a pear"})["prompt"] == "A pear."
    instance.load.assert_called_once()


def test_an_edit_reply_without_a_caption_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("SPEECH_GEN_SCRATCH", str(tmp_path))
    instance = enhancer(tmp_path)
    instance.ask = Mock(return_value='{"target_aspect_ratio": "1:1"}')
    with pytest.raises(ValueError, match="empty caption"):
        instance.answer({"kind": "edit", "prompt": "make it red", "images": []})


def test_the_script_entry_point_runs(monkeypatch, tmp_path, capsys):
    import runpy

    monkeypatch.setattr(sys, "argv", ["worker", "--model-dir", str(tmp_path / "pack")])
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    load = Mock(return_value=(object(), object()))
    monkeypatch.setitem(sys.modules, "mlx_vlm", SimpleNamespace(load=load))
    (tmp_path / "pack").mkdir()
    (tmp_path / "pack/config.json").write_text("{}")
    runpy.run_path(child.__file__, run_name="__main__")
    assert "ready" in capsys.readouterr().err
