"""Regression coverage for one prompt-rewriter gateway."""

import pytest

from studio.l1_entities.errors import InvalidJob
from studio.l3_interface_adapters.gateways.no_prompt_rewriter_gateway import NoPromptRewriterGateway


def test_the_absent_rewriter_refuses_instead_of_answering():
    # Its empty mode list hides the page's toggle, so a call here comes from a
    # caller that ignored the list. A silent answer would send the prompt on
    # unimproved and look like it worked.
    rewriter = NoPromptRewriterGateway()
    assert rewriter.modes() == ()
    with pytest.raises(InvalidJob, match="no prompt rewriter"):
        rewriter.rewrite("a cat", "generate", (), lambda: None, lambda: False)
    rewriter.release()
