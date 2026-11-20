import base64
from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import Cancelled, InvalidJob, StudioError
from studio.l1_entities.image_job import ReferenceImage
from studio.l1_entities.video_job import VideoReference
from studio.l3_interface_adapters.gateways.video.ltx25_cuda.rewriter import Ltx25CudaRewriter, RewrittenPrompts


def child_answering(text):
    child = Mock()
    child.request.return_value = {"text": text}
    return child


def test_it_serves_generate_and_runs_inside_the_video_model():
    rewriter = Ltx25CudaRewriter(Mock(), RewrittenPrompts())
    assert rewriter.modes() == ("generate",)
    assert rewriter.resident_in() == "ltx25_cuda"


def test_a_rewrite_asks_the_resident_child_and_says_when_it_writes():
    child = child_answering("A fox runs through fresh snow.")
    on_writing, should_stop = Mock(), Mock(return_value=False)

    rewrite = Ltx25CudaRewriter(child, RewrittenPrompts()).rewrite("a fox", "generate", (), on_writing, should_stop)

    assert rewrite.prompt == "A fox runs through fresh snow."
    on_writing.assert_called_once()
    payload, _, stop = child.request.call_args.args
    assert payload == {"task": "rewrite", "prompt": "a fox", "references": []}
    assert stop is should_stop


def test_a_keyframe_reaches_the_child_as_the_first_reference_only():
    child = child_answering("A red frame.")
    references = (ReferenceImage(b"first", 4, 4), ReferenceImage(b"second", 4, 4))

    Ltx25CudaRewriter(child, RewrittenPrompts()).rewrite("go", "generate", references, Mock(), Mock())

    assert child.request.call_args.args[0]["references"] == [base64.b64encode(b"first").decode("ascii")]


def test_a_mode_it_does_not_serve_is_refused():
    with pytest.raises(InvalidJob, match="edit"):
        Ltx25CudaRewriter(Mock(), RewrittenPrompts()).rewrite("a fox", "edit", (), Mock(), Mock())


def test_an_empty_answer_is_a_failure_not_a_blank_prompt():
    with pytest.raises(StudioError, match="empty prompt"):
        Ltx25CudaRewriter(child_answering("  "), RewrittenPrompts()).rewrite("a fox", "generate", (), Mock(), Mock())


def test_a_cancel_reaches_the_caller():
    child = Mock()
    child.request.side_effect = Cancelled("stopped")
    with pytest.raises(Cancelled):
        Ltx25CudaRewriter(child, RewrittenPrompts()).rewrite("a fox", "generate", (), Mock(), Mock())


def test_the_written_prompt_is_remembered_with_its_keyframe():
    rewritten = RewrittenPrompts()
    Ltx25CudaRewriter(child_answering("Longer."), rewritten).rewrite(
        "a fox", "generate", (ReferenceImage(b"key", 4, 4),), Mock(), Mock()
    )

    # The run carries the keyframe as a video reference with the same picture.
    assert rewritten.wrote("Longer.", (VideoReference("key", b"key", 0, 1.0),))
    assert not rewritten.wrote("Longer.", ())
    assert not rewritten.wrote("a fox", (VideoReference("key", b"key", 0, 1.0),))


def test_release_leaves_the_video_model_to_its_backend():
    child = Mock()
    Ltx25CudaRewriter(child, RewrittenPrompts()).release()
    child.stop.assert_not_called()


def test_the_record_keeps_only_the_latest_prompts():
    rewritten = RewrittenPrompts()
    for index in range(RewrittenPrompts.LIMIT + 1):
        rewritten.add(f"prompt {index}", ())
    assert not rewritten.wrote("prompt 0", ())
    assert rewritten.wrote(f"prompt {RewrittenPrompts.LIMIT}", ())
