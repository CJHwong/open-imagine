# Vendored page libraries

The studio serves every page library from this directory. The page reaches no CDN, so a
build cannot change under it, and an offline machine still runs the whole studio.

| File | Upstream | Version | License |
|---|---|---|---|
| `lit.js` | lit | 3.2.1 | BSD-3-Clause |
| `abcjs.js` | abcjs | 6.6.1 | MIT |
| `lame.min.js` | lamejs | 1.2.1 | LGPL-3.0 |
| `htmx.min.js` | htmx.org | 2.0.4 | BSD-2-Clause |
| `swagger-ui-bundle.js` | swagger-ui-dist | 5.25.3 | Apache-2.0 |
| `swagger-ui.css` | swagger-ui-dist | 5.25.3 | Apache-2.0 |

`MANIFEST.json` pins the source URL, the version, the size and the SHA-256 of each file.
`tests/l4_frameworks_and_drivers/test_vendor_assets.py` checks every digest and fails if a
page file names an outside host. The license texts are in `licenses/`.

To update one:

1. Fetch the pinned upstream file, or bundle lit with
   `npx esbuild entry.js --bundle --format=esm --minify --outfile=lit.js` from an entry
   that exports `*` from `lit` and `repeat` from `lit/directives/repeat.js`.
2. Replace the file here.
3. Update its `sha256`, `bytes` and `version` in `MANIFEST.json`.
4. Run `uv run pytest tests/l4_frameworks_and_drivers/test_vendor_assets.py`.

abcjs carries optional soundfont URLs in its own code. The studio only engraves notation,
so it never requests them. They are the library's strings, not the page's.
