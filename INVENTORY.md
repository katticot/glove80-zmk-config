# Glove80 repository inventory

This repository is the single source of truth for this Glove80 configuration.

| Location | Contents |
| --- | --- |
| `config/` | Current ZMK keymap and build configuration. |
| `docs/glove80.html` | Interactive Field Guide generated from the current keymap. |
| `docs/reference/` | Personal guide, layer reference, and historical layout snapshot. |
| `archive/keymaps/` | Earlier standalone keymap snapshot. |
| `archive/layouts/` | Pre-Field-Guide layout inspector snapshot. |
| `artifacts/firmware/` | Current combined UF2 and its downloaded ZIP. |
| `artifacts/firmware/legacy/` | Earlier Glorious Engrammer v38 UF2. |

## Duplicate legacy download

The two local files named `26d8993c-...v38.uf2` and `26d8993c-...v38 (1).uf2`
were byte-identical. This repository keeps one canonical copy at
`artifacts/firmware/legacy/glorious-engrammer-v38.uf2`.

## Current firmware snapshot

The current keymap and Field Guide are synchronized to commit `881e340`.
The combined UF2 is stored as a build artifact for recovery and flashing; edit
`config/glove80.keymap` and let GitHub Actions build a new artifact for future
firmware changes.
