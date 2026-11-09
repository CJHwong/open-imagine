"""Regression coverage for one prompt-rewriter gateway."""

from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import InvalidJob
from studio.l3_interface_adapters.gateways.catalog_prompt_rewriter_gateway import CatalogPromptRewriterGateway
from tests.support.prompt_rewriters import Catalog, Rewriter


def test_the_rewriter_in_force_follows_the_backend_the_page_is_on():
    # A rewriter belongs to a backend and the page may switch backends, so the
    # one in force has to follow the catalog. A stale one would rewrite the
    # prompt for the model that just went away.
    catalog = Catalog("first")
    first, second = Rewriter(), Rewriter(modes=("generate", "edit"))
    rewriter = CatalogPromptRewriterGateway({"first": first, "second": second}, catalog)
    assert rewriter.modes() == ("generate",)

    rewriter.rewrite("a cat", "generate", (), lambda: None, lambda: False)
    catalog.set_active("second")
    assert rewriter.modes() == ("generate", "edit")

    rewriter.rewrite("a dog", "edit", (), lambda: None, lambda: False)
    assert [seen[:3] for seen in first.seen] == [("a cat", "generate", ())]
    assert [seen[:3] for seen in second.seen] == [("a dog", "edit", ())]


def test_the_rewriter_in_force_receives_both_callables():
    # The page needs both: the phase report draws its stop button, and the stop
    # check is what the button sets. A catalog that swallowed either would leave
    # the button wrong for whichever backend is active.
    on_writing, should_stop = Mock(), Mock()
    first = Rewriter()
    CatalogPromptRewriterGateway({"first": first}, Catalog("first")).rewrite(
        "a cat", "generate", (), on_writing, should_stop
    )
    assert first.seen[0][3:] == (on_writing, should_stop)


def test_a_backend_with_no_rewriter_takes_the_absent_one():
    rewriter = CatalogPromptRewriterGateway({"first": Rewriter()}, Catalog("second"))
    assert rewriter.modes() == ()
    with pytest.raises(InvalidJob, match="no prompt rewriter"):
        rewriter.rewrite("a cat", "generate", (), lambda: None, lambda: False)


def test_release_frees_every_backends_rewriter():
    # The rewriter is a second model and the caller asking for memory wants all
    # of it. Freeing only the active one leaves the other resident.
    first, second = Rewriter(), Rewriter()
    CatalogPromptRewriterGateway({"first": first, "second": second}, Catalog("first")).release()
    assert first.releases == 1 and second.releases == 1
