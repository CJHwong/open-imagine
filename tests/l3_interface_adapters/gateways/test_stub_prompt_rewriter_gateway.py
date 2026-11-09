"""Regression coverage for one prompt-rewriter gateway."""

from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import Cancelled
from studio.l3_interface_adapters.gateways.stub_prompt_rewriter_gateway import StubPromptRewriterGateway
from tests.support.prompt_rewriters import quick


def test_the_stub_answers_with_a_longer_prompt_for_the_page():
    answer = quick(StubPromptRewriterGateway()).rewrite("a cat", "generate", (), lambda: None, lambda: False)
    assert answer.prompt == "a cat A longer version of it, written for the stub."
    assert answer.ratio == "3:2"  # the page checks that a suggested shape becomes a size


def test_the_stub_reports_its_writing_phase_once():
    # The page offers its stop button only once the model writes, so the stub has
    # to say when it crosses that line, exactly as the real one does.
    on_writing = Mock()
    quick(StubPromptRewriterGateway()).rewrite("a cat", "generate", (), on_writing, lambda: False)
    on_writing.assert_called_once_with()


def test_a_stop_during_the_stub_preparing_phase_writes_nothing():
    # A stop cannot land during the load, on the stub as on the real rewriter. It
    # is remembered instead, and nothing is written after it.
    on_writing = Mock()
    with pytest.raises(Cancelled):
        quick(StubPromptRewriterGateway()).rewrite("a cat", "generate", (), on_writing, lambda: True)
    on_writing.assert_not_called()


def test_a_stop_between_the_stub_slices_raises():
    # The stop is read between segments, so it lands within one segment and never
    # after the whole write has finished.
    on_writing = Mock()
    should_stop = Mock(side_effect=[False, True])
    with pytest.raises(Cancelled):
        quick(StubPromptRewriterGateway()).rewrite("a cat", "generate", (), on_writing, should_stop)
    on_writing.assert_called_once_with()


def test_the_stub_reports_the_modes_the_page_can_offer():
    # It reports every mode the qwen21 rewriter serves, so the page's toggle can
    # be checked on a machine with no GPU.
    rewriter = StubPromptRewriterGateway()
    assert rewriter.modes() == ("generate", "edit")
    rewriter.release()
