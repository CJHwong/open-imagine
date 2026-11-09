"""Fake catalog, rewriter and clock setup for the concrete gateway tests."""

from studio.l2_use_cases.boundaries.backend_catalog_gateway import BackendCatalogGateway
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway


class Catalog(BackendCatalogGateway):
    """A catalog whose active backend the test can move."""

    def __init__(self, active="first"):
        self.active = active

    def get(self, backend_id):
        raise AssertionError("a rewriter never asks the catalog for an engine")

    def visible_ids(self):
        return ()

    def active_id(self):
        return self.active

    def set_active(self, backend_id):
        self.active = backend_id


class Rewriter(PromptRewriterGateway):
    def __init__(self, modes=("generate",)):
        self._modes = modes
        self.seen = []
        self.releases = 0

    def modes(self):
        return self._modes

    def rewrite(self, prompt, mode, references, on_writing, should_stop):
        self.seen.append((prompt, mode, references, on_writing, should_stop))
        return f"longer {prompt}"

    def release(self):
        self.releases += 1


def quick(rewriter):
    """Set the stub's two clocks to zero on the instance.

    The stub's sleeps are real, so a test that reads the order of its calls would
    otherwise wait 4.2 seconds. The instance attribute shadows the class constant,
    so no other test is slowed or changed.
    """
    rewriter.PREPARING_SECONDS = 0
    rewriter.WRITING_SLICE_SECONDS = 0
    return rewriter
