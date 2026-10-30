"""Everything the server sends back is HTML for htmx: the page, and fragments.

The fragments carry data, not layout. The page moves an image into its gallery
and draws the progress card itself.
"""

import base64
import html
import json
from collections.abc import Mapping
from dataclasses import asdict

from studio.l1_entities.errors import Cancelled, InvalidJob, StudioError
from studio.l1_entities.rewrite_progress import RewriteProgress
from studio.l1_entities.run_progress import RunProgress
from studio.l2_use_cases.describe_studio_use_case import StudioView
from studio.l2_use_cases.prepare_batch_use_case import BATCH_LIMIT
from studio.l2_use_cases.rewrite_prompt_use_case import RewriteResponse
from studio.l2_use_cases.run_image_use_case import NextRun, RunImageResponse
from studio.l3_interface_adapters.presenters.locale import DEFAULT_LOCALE, LocaleCatalog

ITEM = """<div class="item" data-seed="{seed}" data-width="{width}" data-height="{height}"
  data-steps="{steps}" data-elapsed="{elapsed:.0f}" data-position="{position}"
  data-mode="{mode}" data-prompt="{prompt}" data-reference="{reference}"><img src="data:image/png;base64,{b64}" alt=""></div>"""


def _script_json(value: object) -> str:
    """JSON that cannot close the script tag it travels in."""
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


CHAIN = (
    '<div class="chain" data-index="{index}" data-progress="{progress}" hx-post="/generate"'
    ' hx-vals=\'{values}\' hx-trigger="load" hx-target="this"'
    ' hx-swap="outerHTML"></div>'
)

# Every progress answer carries the next poller, so the loop clocks itself. The
# page ends it by clearing #progress. The server cannot end it: between two
# images of a batch, and between the click and the run starting, nothing runs
# but more is coming, and ending there killed the poller for the whole run.
POLLER = '<div hx-get="/progress" hx-trigger="load delay:800ms" hx-target="#progress" hx-swap="innerHTML"></div>'


class HtmlPresenter:
    def __init__(self, page_template: str, locales: LocaleCatalog | None = None):
        self._page = page_template
        self._locales = locales

    def locale_for(
        self,
        requested: str | None = None,
        cookie: str | None = None,
        accept_language: str | None = None,
    ) -> str:
        """The locale a request asks for, chosen the same way the picker persists one."""
        if self._locales is None:
            return DEFAULT_LOCALE
        return self._locales.negotiate(requested, cookie, accept_language)

    def page(
        self,
        view: StudioView,
        workspaces: Mapping[str, bool] | None = None,
        locale: str = DEFAULT_LOCALE,
    ) -> str:
        """`workspaces` says which optional workspaces this studio offers, so the
        page can draw all four tabs on the first paint. A studio that passes
        nothing offers neither, and the tabs stay out of the nav.

        `locale` picks the string table, which travels inline so the first paint
        needs no request and no bundle of a language nobody reads."""
        active = view.active
        studio = {
            "batch_limit": BATCH_LIMIT,
            "workspaces": {
                "voice": bool((workspaces or {}).get("voice")),
                "music": bool((workspaces or {}).get("music")),
            },
            "backend": {
                "id": active.backend_id,
                "name": active.name,
                "badge": active.badge,
                "max_batch": active.max_batch,
            },
            "backends": [list(backend) for backend in view.backends],
            "video": {
                "backend": (
                    {
                        "id": view.active_video.backend_id,
                        "name": view.active_video.name,
                        "badge": view.active_video.badge,
                    }
                    if view.active_video
                    else None
                ),
                "backends": [list(backend) for backend in view.video_backends],
                "capabilities": asdict(view.active_video) if view.active_video else None,
                "rewrite_modes": list(view.video_rewrite_modes),
            },
            "modes": [asdict(mode) for mode in active.modes],
            # Which modes a prompt rewriter serves. Empty leaves the page's
            # toggle out, so a backend without one offers no dead button.
            "rewrite_modes": list(view.rewrite_modes),
        }
        # The JSON sits in a script tag, where "</" would end the tag early.
        data = json.dumps(studio, ensure_ascii=False).replace("</", "<\\/")
        strings = self._locales.strings(locale) if self._locales else {}
        available = (
            [{"code": item.code, "label": item.label} for item in self._locales.locales] if self._locales else []
        )
        locale_script = (
            "window.STUDIO_STRINGS = "
            + _script_json(strings)
            + ";\n  window.STUDIO_LOCALES = "
            + _script_json(available)
            + ";"
        )
        tag = f'<html lang="{html.escape(locale)}" data-locale="{html.escape(locale)}"'
        if locale != DEFAULT_LOCALE:
            tag += ' class="locale-pending"'
        return (
            self._page.replace('<html lang="en">', tag + ">")
            .replace("__NAME__", html.escape(active.name))
            .replace("__BACKEND__", html.escape(active.backend_id))
            .replace("__STUDIO__", data)
            .replace("__LOCALE__", locale_script)
        )

    def run(self, response: RunImageResponse) -> str:
        image = response.image
        item = ITEM.format(
            b64=base64.b64encode(image.png).decode("ascii"),
            position=response.position,
            seed=image.seed,
            width=image.width,
            height=image.height,
            steps=image.steps,
            elapsed=response.elapsed,
            prompt=html.escape(response.prompt, quote=True),
            mode=response.mode,
            reference=response.reference,
        )
        return item + (self._chain(response.next_run) if response.next_run else "")

    @staticmethod
    def rewrite(response: RewriteResponse) -> str:
        """JSON, not HTML. Every other fragment is appended to the page; this one
        is data the page reads into the prompt box and the size menu.

        A rewrite the page stopped carries no words: the page keeps what the box
        already holds, and there is nothing to say about it.
        """
        if response.cancelled:
            return json.dumps({"cancelled": True})
        return json.dumps(
            {"prompt": response.prompt, "size": response.size, "elapsed": round(response.elapsed, 1)},
            ensure_ascii=False,
        )

    @staticmethod
    def rewrite_state(state: RewriteProgress) -> str:
        """JSON, like the rewrite's own answer, because the page reads it into a control.

        `stage` is what the button follows, and `stopping` is what it says while a
        stop is on its way.
        """
        return json.dumps({"running": state.running, "stage": state.stage, "stopping": state.stopping})

    @staticmethod
    def _chain(next_run: NextRun) -> str:
        """The placeholder that fetches the next image of the batch.

        It carries every text value it needs, and its own index, which is the image
        of the batch it asks for. The reference images are the one exception: they
        stay on the server under the token, so a large image is not posted again for
        each image.
        """
        values = {
            **next_run.options,
            "mode": next_run.mode,
            "prompt": next_run.prompt,
            "seed": str(next_run.seed),
            "total": str(next_run.total),
            "index": str(next_run.index),
            "reference_token": next_run.reference_token,
            "backend": next_run.backend,
        }
        if next_run.each_reference:
            values["each_reference"] = "1"
        if next_run.mask:
            values["mask"] = "1"
        return CHAIN.format(
            index=str(next_run.index),
            progress=f"{next_run.index} of {next_run.total}",
            values=html.escape(json.dumps(values), quote=True),
        )

    @staticmethod
    def failure(error: Exception) -> str:
        if isinstance(error, Cancelled):
            return f'<div class="hint">Cancelled ({html.escape(str(error))}).</div>'
        if isinstance(error, InvalidJob):
            message = f"Bad form value: {error}"
        elif isinstance(error, StudioError):
            message = str(error)
        else:
            message = f"{type(error).__name__}: {error}"
        return f'<div class="err">{html.escape(message)}</div>'

    @staticmethod
    def progress(state: RunProgress) -> str:
        if not state.running:
            return POLLER
        return (
            f'<div class="progress-state" data-stage="{state.stage}"'
            f' data-step="{state.step}" data-total="{state.total}"'
            f' data-label="{html.escape(state.label, quote=True)}" data-kind="{state.kind}"'
            f' data-stopping="{1 if state.stopping else 0}"></div>{POLLER}'
        )

    @staticmethod
    def video_progress(state: RunProgress) -> str:
        return json.dumps(
            {
                "running": state.running,
                "stage": state.stage,
                "step": state.step,
                "total": state.total,
                "phase": state.phase,
                "kind": state.kind,
                "stopping": state.stopping,
                "request_id": state.request_id,
            }
        )
