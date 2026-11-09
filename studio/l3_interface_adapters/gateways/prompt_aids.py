"""Select declared prompt aids without owning model-specific wording."""

from collections.abc import Mapping

from studio.l1_entities.capabilities import LookRow, Template


def pick_looks(
    catalog: tuple[LookRow, ...], picks: Mapping[str, tuple[str, ...]], sentences: Mapping[str, str] | None = None
) -> tuple[LookRow, ...]:
    """The rows named in `picks`, each cut to the named options, in the shared order.

    A picked option keeps its avoid part. The page sends it only in a mode
    with a negative prompt.

    `sentences` replaces the sentence of an option by its name, for a model that
    reads the shared wording in a way the option does not mean. A name that
    matches nothing raises, so a typo cannot drop an option without a word.
    """
    rows = {row.name: row for row in catalog}
    unknown = [name for name in picks if name not in rows]
    unknown += [
        option for name in picks if name in rows for option in picks[name] if option not in dict(rows[name].options)
    ]
    if unknown:
        raise ValueError(f"no Look named {', '.join(unknown)}")
    replaced = sentences or {}
    return tuple(
        LookRow(
            row.name,
            tuple((name, replaced.get(name, text)) for name, text in row.options if name in picks[row.name]),
            tuple((name, avoid) for name, avoid in row.avoids if name in picks[row.name]),
        )
        for row in catalog
        if row.name in picks
    )


def pick_templates(catalog: tuple[Template, ...], names: tuple[str, ...]) -> tuple[Template, ...]:
    """The named templates, generate or edit, in the order given.

    A name that matches nothing raises, so a typo cannot drop a template
    without a word.
    """
    templates = {template.name: template for template in catalog}
    unknown = [name for name in names if name not in templates]
    if unknown:
        raise ValueError(f"no template named {', '.join(unknown)}")
    return tuple(templates[name] for name in names)
