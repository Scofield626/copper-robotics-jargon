# Copper Robotics Jargon

A fast, searchable reference for the robotics abbreviations, protocols,
coordinate conventions, hardware models, and Copper-specific vocabulary used
across [copper-rs](https://github.com/copper-project/copper-rs).

**[Open the rendered cheatsheet](https://scofieldliu.com/copper-robotics-jargon/)**

The page is self-contained and needs no build step, package installation, or
local server. You can also open [`index.html`](index.html) directly after cloning.

## Repository layout

- `index.html` — the complete static cheatsheet, including its curated term data
- `audit.py` — validates entries and finds uncatalogued terms in a copper-rs checkout
- `.nojekyll` — publishes the static files directly through GitHub Pages
- `.gitignore` / `.gitattributes` — local-artifact exclusions and consistent text handling

## Refreshing it after copper-rs changes

Run the reviewer-oriented audit against any checkout:

```bash
python3 audit.py --repo /path/to/copper-rs
```

The report groups uppercase abbreviations and hardware-style model identifiers
that are not yet represented by a term, exact alias, or related search term. Use
`aliases` only for equivalent spellings or names; put associated signals,
variants, products, and broader families in `related`. For each candidate:

1. Add a useful robotics/Copper term to the `term-data` JSON block in
   `index.html`, including at least one repository source.
2. If it is a code constant, register/bit-field name, test identifier, or generic
   software term, add it to the documented suppression table in `audit.py`.
3. Rerun the audit. Unknown candidates are informational; malformed entries,
   duplicate aliases, invalid categories, or missing repository sources fail.

Use `--show-suppressed` when reviewing the existing exclusions and `--limit N`
to change the number of candidates printed.

## Scope

“All” means useful robotics and Copper vocabulary present in first-party
copper-rs code and documentation—not every uppercase token. Generated output,
vendored sources, logs, register fields, safety-case IDs, and generic code noise
are intentionally outside the cheatsheet.
