"""One filter for the tests that need the MLX stack.

The suite runs on macOS because mflux and mlx-vlm install only there. The CUDA machine
has no MLX, and a test that reaches an engine then stops on an import instead of
reporting something about the product: 43 tests did exactly that on 2026-11-17.

So when the stack is missing, a ModuleNotFoundError for one of its packages is a skip.
When it is present, the same error is a real fault, and the test fails as it should.
"""

import importlib.util

import pytest

MLX_STACK = ("mlx", "mlx_vlm", "mflux")
MLX_INSTALLED = all(importlib.util.find_spec(name) is not None for name in MLX_STACK)
MISSING_REASON = "needs the MLX stack, which installs on macOS only"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    outcome = yield
    try:
        outcome.get_result()
    except ModuleNotFoundError as error:
        package = (error.name or "").partition(".")[0]
        if MLX_INSTALLED or package not in MLX_STACK:
            raise
        pytest.skip(f"{MISSING_REASON} (no {package})")
