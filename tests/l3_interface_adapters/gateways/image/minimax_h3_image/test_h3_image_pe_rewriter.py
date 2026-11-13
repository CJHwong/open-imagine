import base64
from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import Cancelled, InvalidJob
from studio.l1_entities.image_job import ReferenceImage
from studio.l3_interface_adapters.gateways.image.minimax_h3_image.h3_image_pe_rewriter import (
    H3ImagePeRewriter,
)


def rewriter():
    return H3ImagePeRewriter(["uv", "run", "--script", "child.py"])


def test_each_mode_the_enhancer_serves_is_named():
    assert rewriter().modes() == ("generate", "edit")


def test_a_generate_rewrite_asks_for_a_caption_and_keeps_the_ratio():
    gateway = rewriter()
    gateway._child = Mock()
    gateway._child.request.return_value = {"prompt": "a long caption", "ratio": "3:2"}
    writing = Mock()
    reply = gateway.rewrite("a pear", "generate", (), writing, lambda: False)
    assert reply.prompt == "a long caption" and reply.ratio == "3:2"
    gateway._child.wait_ready.assert_called_once()
    writing.assert_called_once()
    assert gateway._child.request.call_args.args[0] == {"kind": "generate", "prompt": "a pear"}


def test_an_edit_rewrite_carries_the_pictures_the_run_will_send():
    gateway = rewriter()
    gateway._child = Mock()
    gateway._child.request.return_value = {"prompt": "a longer instruction", "ratio": None}
    reference = ReferenceImage(b"png bytes", 640, 480)
    reply = gateway.rewrite("make it blue", "edit", (reference,), Mock(), lambda: False)
    job = gateway._child.request.call_args.args[0]
    assert job["kind"] == "edit" and job["ratio"] == "adaptive"
    assert job["images"] == [base64.b64encode(b"png bytes").decode("ascii")]
    assert reply.prompt == "a longer instruction" and reply.ratio is None


def test_a_stop_before_the_load_raises_without_starting_the_child():
    gateway = rewriter()
    gateway._child = Mock()
    with pytest.raises(Cancelled):
        gateway.rewrite("a pear", "generate", (), Mock(), lambda: True)
    gateway._child.wait_ready.assert_not_called()


def test_an_unknown_mode_is_refused():
    with pytest.raises(InvalidJob, match="does not serve"):
        rewriter().rewrite("a pear", "inpaint", (), Mock(), lambda: False)


def test_a_refusal_from_the_child_reaches_the_caller():
    gateway = rewriter()
    gateway._child = Mock()
    gateway._child.request.return_value = {"error": "The prompt enhancer wrote an empty caption.", "kind": "input"}
    with pytest.raises(InvalidJob, match="empty caption"):
        gateway.rewrite("a pear", "generate", (), Mock(), lambda: False)


def test_release_stops_the_child():
    gateway = rewriter()
    gateway._child = Mock()
    gateway.release()
    gateway._child.stop.assert_called_once()
