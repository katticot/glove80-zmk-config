# Glove80 repository inventory

This repository is the single source of truth for this Glove80 configuration.

| Location | Contents |
| --- | --- |
| `config/glove80.keymap` | The single source of truth. The firmware is built from this file, and everything else here is derived from it. |
| `config/keymap.json` | Glove80 Layout Editor re-import export. A mirror, not an authority: the Field Guide generator fails if any key, layer, or the title disagrees with the keymap. |
| `config/` | Remaining ZMK build configuration (`default.nix`, `info.json`, `glove80.conf`). |
| `docs/glove80.html` | Interactive Field Guide, generated from `config/glove80.keymap`. |
| `docs/reference/` | Personal guide, layer reference, historical layout snapshots, and live v38 verification notes. |
| `archive/keymaps/` | Earlier standalone keymap snapshot. |
| `archive/layouts/` | Pre-Field-Guide layout inspector snapshot. |
| `artifacts/firmware/` | Current combined UF2 and its downloaded ZIP. |
| `artifacts/firmware/legacy/` | Earlier Glorious Engrammer v38 UF2. |

## Duplicate legacy download

The two local files named `26d8993c-...v38.uf2` and `26d8993c-...v38 (1).uf2`
were byte-identical. This repository keeps one canonical copy at
`artifacts/firmware/legacy/glorious-engrammer-v38.uf2`.

## Source of truth

`config/glove80.keymap` is the only authority. The Field Guide and the Layout
Editor export are both derived from it, so firmware and documentation are
reconciled by editing the keymap, never the generated files:

* `python3 tools/generate_field_guide.py` rebuilds `docs/glove80.html`, and
  `--check` fails if the committed page is stale. The page records the commit
  and SHA-256 of the keymap it was built from, so it does not go stale silently.
* That same run verifies `config/keymap.json` against the keymap and fails on
  any disagreement, which is what keeps the editor round-trip usable. A change
  made by hand in the keymap therefore needs a fresh editor export.

The combined UF2 is stored as a build artifact for recovery and flashing; edit
`config/glove80.keymap` and let GitHub Actions build a new artifact for future
firmware changes.
