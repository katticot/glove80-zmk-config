# Glove80 repository inventory

This repository is the single source of truth for this Glove80 configuration.

| Location | Contents |
| --- | --- |
| `config/glove80.keymap` | The single source of truth. The firmware is built from this file, and everything else here is derived from it. |
| `config/keymap.json` | Glove80 Layout Editor re-import export. A mirror, not an authority: the Field Guide generator fails if any key, layer, or the title disagrees with the keymap. |
| `config/` | Remaining ZMK build configuration (`default.nix`, `info.json`, `glove80.conf`). |
| `docs/glove80.html` | Interactive Field Guide, generated from `config/glove80.keymap`. |
| `docs/glove80-before-after.html` | Before/after key diff between two revisions of the keymap. Regenerate with `python3 tools/make_before_after.py --before <rev>`. |
| `docs/reference/` | Personal guide, layer reference, historical layout snapshots, and live v38 verification notes. |
| `archive/keymaps/` | Earlier standalone keymap snapshot. |
| `archive/layouts/` | Pre-Field-Guide layout inspector snapshot. |
| `artifacts/firmware/` | Current combined UF2 and its downloaded ZIP. |
| `artifacts/firmware/legacy/` | Earlier Glorious Engrammer v38 UF2. |

## Duplicate legacy download

The two local files named `26d8993c-...v38.uf2` and `26d8993c-...v38 (1).uf2`
were byte-identical. This repository keeps one canonical copy at
`artifacts/firmware/legacy/glorious-engrammer-v38.uf2`.

## Layers

18 layers, in keymap order. The ten finger layers are structural: each home-row
key holds the layer named after the finger it sits on, and `Typing` is what
`&plain` holds. None of them are optional, and neither is the layer-number
renumbering below them (`LAYER_Number` is 12, not 13).

| # | Layer | Reached by |
| --- | --- | --- |
| 0 | ColemakDHm | the base layer |
| 1 | Typing | holding `#39` or `#40` (`&plain`) |
| 2 | LeftPinky | holding left pinky home row (`#35`) |
| 3 | LeftRing1 | holding left ring1 (`#36`) |
| 4 | LeftRing2 | holding left ring2 (`#24`) |
| 5 | LeftMiddy | holding left middle (`#37`) |
| 6 | LeftIndex | holding left index (`#38`) |
| 7 | RightPinky | holding right pinky (`#44`) |
| 8 | RightRing1 | holding right ring1 (`#43`) |
| 9 | RightRing2 | holding right ring2 (`#31`) |
| 10 | RightMiddy | holding right middle (`#42`) |
| 11 | RightIndex | holding right index (`#41`) |
| 12 | Number | holding left thumb `#70` — a real keypad |
| 13 | System | holding left thumb `#57` |
| 14 | Gaming | combo on thumbs `#52`+`#57` |
| 15 | Factory | Magic `#54` |
| 16 | Magic | holding left thumb `#64` or right thumb `#79` |
| 17 | Cursor | holding Space (`#69`) |

The finger layers also carry the same-hand chords (`left_ring1_pinky` and
friends), which is why there are ten of them rather than one shared layer.

## Deliberate differences from Sunaku's v38 keymap

This keymap started as Glorious Engrammer v38 and has diverged in ways worth
knowing before comparing it against upstream:

* **18 layers, down from 24.** Removed: Function, Emoji, Symbol, Mouse, World
  and Lower. Cursor was removed and then restored as layer 17. Layers 0-11 kept
  their original numbers, which is why the numbers no longer run consecutively
  with upstream's.
* **The Number layer is a real keypad.** `USE_NUMPAD_KEYCODES` is defined, so
  its digits send `KP_*` keycodes rather than the number row. This is what
  replaced the deleted Lower layer's keypad.
* **macOS.** `OPERATING_SYSTEM 'M'`; the Linux-only SysRq key and its binding
  are gone.
* **The World and Emoji macro tree is deleted**, about 287 KB of source and
  117 KB of firmware. Nothing could reach it once its layers were gone.
* **Combos fire on layers 0-11** rather than upstream's 0-8, so one-shot Shift,
  hyper, meh, caps-word and the tab-switchers work on all ten finger layers
  instead of eight.
* **There is no Lower layer.** `&lower` on base `#52` and Factory `#54` is a
  tap-dance whose target is undefined, so it holds the base layer (nothing) and
  double-taps back to it. On Factory that double-tap is the only direct route
  home.
* The mouse-keys shim (`#if __has_include(<zmk/events/mouse_tick.h>)`) is kept
  even though no key uses it: it is what defines `mmv`/`msc`/`mkp` and the
  `MOVE_*`/`SCRL_*`/`MB*` names as empty when the firmware lacks mouse support,
  so re-adding a mouse key still builds.

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

## Building and flashing

Pushing does not trigger the workflow in this fork, so start it explicitly:

```
gh workflow run Build --ref main
gh run watch $(gh run list --workflow=Build --limit 1 --json databaseId -q '.[0].databaseId')
```

`./build.sh` does the same thing locally through Docker, but it needs a running
Docker daemon and provisions a Nix store.

Flash both halves, right first: hold positions `#30`+`#79` for `GLV80RHBOOT`,
then `#64`+`#25` for `GLV80LHBOOT`.

## Gotchas

* **Every keymap commit needs a follow-up docs commit.** The Field Guide pins
the commit that last changed the keymap, so committing the keymap makes the
page stale by definition. Regenerate and commit again.
* **The Field Guide mirror check only compares layers and cells.** It cannot see
`config/keymap.json`'s `custom_defined_behaviors` blob, which still contains the
deleted World/Emoji macro tree. That blob is deliberately left intact: seeing it
gone while the editor still binds `&emoji_*` would produce an export that does
not build.
* **A Layout Editor export restores the deleted tree** unless the missing layers
are also deleted in the editor. Hand edits to the keymap are not visible to it.

## Reviewing what changed

`docs/glove80-before-after.html` renders two revisions of the keymap against each
other, key by key, with a tab per layer, changed keys highlighted, and the
previous binding shown under each. It labels both sides with the same code the
Field Guide uses, so a key reads there exactly as the Field Guide would show it.

```
python3 tools/make_before_after.py --before 856a4ff      # the whole consolidation
python3 tools/make_before_after.py --before HEAD~1       # just the last keymap edit
```

`--before` defaults to `856a4ff`, the last build before the layer consolidation,
and `--after` defaults to the working tree. Note that the diff follows `&trans`
inheritance, so a base-layer change also shows up on the finger layers that
inherit that position, which is what those layers will actually send.
