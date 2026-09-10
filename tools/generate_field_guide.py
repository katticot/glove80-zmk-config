#!/usr/bin/env python3
"""Regenerate docs/glove80.html (the Field Guide) from config/keymap.json.

config/keymap.json is the Glove80 Layout Editor export: it carries the layer
names, the 24x80 binding table, and the custom-behaviors blob. The previous
Field Guide was generated from a different (now replaced) keymap, so it
described the wrong layout. This script rebuilds it from the real one.

Usage:
    python3 tools/generate_field_guide.py [--check]

--check regenerates into memory and fails if docs/glove80.html differs,
without writing.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEYMAP = ROOT / "config" / "glove80.keymap"
LAYOUT = ROOT / "config" / "keymap.json"
OUT = ROOT / "docs" / "glove80.html"

# Board geometry (MoErgo coordinates) is board-fixed, not keymap data. It is
# taken from the existing Field Guide so this script does not duplicate it.


# --------------------------------------------------------------------------
# Layout Editor JSON -> per-layer binding strings
# --------------------------------------------------------------------------

def _arg(node) -> str:
    """Render one argument of a structured binding cell."""
    if isinstance(node, (str, int)):
        return str(node)
    value = str(node.get("value", ""))
    params = node.get("params") or []
    if not params:
        return value
    return f"{value}({', '.join(_arg(p) for p in params)})"


def build_bindings(layout: dict) -> list[list[str]]:
    """Turn the JSON cell grid into canonical ZMK binding strings."""
    layers = []
    for layer in layout["layers"]:
        row = []
        for cell in layer:
            if cell.get("value") == "Custom":
                raw = cell["params"][0]["value"]
            else:
                value = str(cell.get("value", ""))
                args = " ".join(_arg(p) for p in (cell.get("params") or []))
                raw = f"{value} {args}" if args else value
            row.append(" ".join(raw.split()))
        layers.append(row)
    return layers


# --------------------------------------------------------------------------
# Defines parsed out of the keymap's custom-behaviors blob
# --------------------------------------------------------------------------

DEFINE_RE = re.compile(r"^[ \t]*#define[ \t]+(\w+)[ \t]+(.+?)[ \t]*$", re.M)


def parse_defines(text: str) -> dict[str, str]:
    """Collect #defines, mirroring C semantics for the guards this keymap uses.

    A name protected by `#ifndef NAME` keeps its *first* definition, because
    the guarded redefinition is skipped by the preprocessor. Without this,
    TAPPING_RESOLUTION would pick up the 150 ms fallback instead of the
    difficulty-derived value, and the reported timings would be wrong.
    """
    guarded = set(re.findall(r"#ifndef\s+(\w+)", text))
    found: dict[str, str] = {}
    for match in DEFINE_RE.finditer(text):
        name = match.group(1)
        if name in guarded and name in found:
            continue
        found[name] = re.sub(r"\s+//.*$", "", match.group(2)).strip()
    return found


def numeric_defines(defines: dict[str, str]) -> dict[str, int]:
    """Evaluate the arithmetic #defines (TAPPING_RESOLUTION, *_HOLDING_TIME)."""
    env: dict[str, int] = {}
    pending = dict(defines)
    for _ in range(10):
        for name, value in list(pending.items()):
            try:
                env[name] = eval(value, {"__builtins__": {}}, env)  # noqa: S307
            except Exception:
                continue
            del pending[name]
        if not pending:
            break
    return env


def branch(text: str, condition: str) -> str:
    """Return the body of `#if <condition> ... #endif` for the ColemakDHm block."""
    start = text.find(condition)
    if start < 0:
        raise SystemExit(f"generate_field_guide: condition not found: {condition!r}")
    start = text.find("\n", start) + 1
    depth, pos = 1, start
    for match in re.finditer(r"^[ \t]*#(if|endif)\b.*$", text[start:], re.M):
        word = match.group(1)
        depth += 1 if word == "if" else -1
        if depth == 0:
            pos = start + match.start()
            break
    return text[start:pos]


def finger_mods(text: str) -> dict[str, str]:
    """Resolve the per-finger modifiers for this keymap's OS setting.

    OPERATING_SYSTEM is 'L' and MACOS_USE_GACS is defined, so both the
    macOS-only Win/Ctrl swaps in the keymap are suppressed.
    """
    mods = {
        "PINKY": "LALT",
        "RING1": "LGUI",
        "RING2": "RGUI",
        "MIDDY": "LCTL",
        "INDEX": "LSFT",
    }
    # Fail loudly if the keymap stops justifying the answer above.
    assert "#define OPERATING_SYSTEM 'L'" in text, "OPERATING_SYSTEM changed off Linux"
    assert "#define MACOS_USE_GACS" in text, "MACOS_USE_GACS no longer defined"
    for finger, mod in mods.items():
        assert f"#define {finger}_FINGER_MOD {mod}" in text or finger in (
            "PINKY",
            "MIDDY",
        ), f"{finger}_FINGER_MOD is not a literal"
    return mods


def key_table(text: str) -> dict[str, str]:
    """KEY_* -> keycode for the active base layer (ColemakDHm).

    `#define KEY_... 0` is the keymap's way of disabling a position; it is
    normalised to an empty label so the Field Guide shows it as disabled
    rather than as the digit zero.
    """
    body = branch(text, "#if defined(LAYER_ColemakDHm) && LAYER_ColemakDHm == 0")
    table = dict(DEFINE_RE.findall(body))
    return {k: ("" if v == "0" else v) for k, v in table.items()}


CHORD_RE = re.compile(
    r"^[ \t]*#define[ \t]+(Left|Right)(\w+?)[ \t]+"
    r"(?:left|right)_\w+_bilateral[ \t]+"
    r"(LEFT|RIGHT)_([A-Z0-9]+)_MOD[ \t]+(LEFT|RIGHT)_([A-Z0-9]+)_KEY[ \t]*$",
    re.M,
)


def chord_table(text: str) -> dict[str, tuple[str, str]]:
    """LeftPinkyRing2 -> (held finger mod, tapped key define)."""
    return {
        f"{side}{tap}": (f"{hold_side}_{hold}_MOD", f"{key_side}_{key}_KEY")
        for side, tap, hold_side, hold, key_side, key in CHORD_RE.findall(text)
    }


UNICODE_GLYPH_RE = re.compile(r"UNICODE\(\s*(\w+?)_macro,\s*/\*\s*(\S+)\s*\*/")


def glyphs(text: str) -> dict[str, str]:
    """emoji_tada -> the emoji itself, taken from the keymap's own comments."""
    return {name: glyph for name, glyph in UNICODE_GLYPH_RE.findall(text)}


MOD_PREFIX = {
    "LC": "Ctrl",
    "RC": "Ctrl",
    "LA": "Alt",
    "RA": "AltGr",
    "LG": "Cmd",
    "RG": "Cmd",
    "LS": "Shift",
    "RS": "Shift",
}

KEY_NAMES = {
    "EQUAL": "=", "MINUS": "−", "TAB": "Tab", "ESC": "Esc", "RET": "Enter",
    "SPACE": "Space", "BSPC": "Backspace", "DEL": "Delete", "INS": "Insert",
    "HOME": "Home", "END": "End", "LEFT": "←", "RIGHT": "→", "UP": "↑",
    "DOWN": "↓", "PG_UP": "PgUp", "PG_DN": "PgDn", "LBKT": "[", "RBKT": "]",
    "COMMA": ",", "DOT": ".", "FSLH": "/", "BSLH": "\\", "SQT": "'",
    "DQT": '"', "GRAVE": "`", "SEMI": ";", "PLUS": "+", "PAUSE_BREAK": "Pause",
    "PSCRN": "PrintScreen", "PRINTSCREEN": "PrintScreen", "SLCK": "ScrollLock",
    "CAPS": "CapsLock", "K_APP": "Menu", "UP_ARROW": "↑", "DOWN_ARROW": "↓",
    "LEFT_ARROW": "←", "RIGHT_ARROW": "→", "KP_NUM": "NumLock",
    "KP_EQUAL": "KP =", "KP_SLASH": "KP /", "KP_MULTIPLY": "KP *",
    "KP_MINUS": "KP −", "KP_PLUS": "KP +", "KP_ENTER": "KP Enter",
    "KP_DOT": "KP .", "LSHFT": "L Shift", "RSHFT": "R Shift",
    "LCTRL": "L Ctrl", "RCTRL": "R Ctrl", "LALT": "L Alt", "RALT": "R Alt",
    "LGUI": "L Cmd", "RGUI": "R Cmd", "LWIN": "L Win", "RWIN": "R Win",
    "LSFT": "Shift", "RSFT": "Shift",
    "COLON": ":", "SINGLE_QUOTE": "'", "EXCL": "!", "AT": "@", "HASH": "#",
    "DLLR": "$", "PRCNT": "%", "CARET": "^", "AMPS": "&", "STAR": "*",
    "LPAR": "(", "RPAR": ")", "TILDE": "~", "UNDER": "_", "LBRC": "{",
    "RBRC": "}", "LT": "<", "GT": ">", "PIPE": "|", "QMARK": "?",
    "K_LOCK": "Lock", "K_POWER": "Power", "DELETE": "Delete",
    "BACKSPACE": "Backspace", "ENTER": "Enter",
}

MEDIA_NAMES = {
    "C_PREV": "Prev track", "C_NEXT": "Next track", "C_PP": "Play/pause",
    "C_MUTE": "Mute", "C_VOL_UP": "Volume +", "C_VOL_DN": "Volume −",
    "C_BRI_UP": "Brightness +", "C_BRI_DN": "Brightness −",
    "C_BRI_MAX": "Brightness max", "C_BRI_MIN": "Brightness min",
    "C_BRI_AUTO": "Brightness auto", "C_PLAY": "Play", "C_STOP": "Stop",
    "C_EJECT": "Eject", "C_MEDIA_HOME": "Media home", "C_AL_FILES": "File manager",
    "C_SLEEP": "Sleep", "C_POWER": "Power", "K_CALC": "Calculator",
    "K_WWW": "Browser",
}

RGB_NAMES = {
    "RGB_TOG": "RGB toggle", "RGB_EFF": "Effect cycle", "RGB_EFR": "Effect −",
    "RGB_BRI": "Brightness +", "RGB_BRD": "Brightness −", "RGB_HUI": "Hue +",
    "RGB_HUD": "Hue −", "RGB_SAI": "Saturation +", "RGB_SAD": "Saturation −",
    "RGB_SPI": "Speed +", "RGB_SPD": "Speed −",
}

MOVE_NAMES = {
    "MOVE_UP": "Mouse ↑", "MOVE_DOWN": "Mouse ↓", "MOVE_LEFT": "Mouse ←",
    "MOVE_RIGHT": "Mouse →", "SCRL_UP": "Scroll ↑", "SCRL_DOWN": "Scroll ↓",
    "SCRL_LEFT": "Scroll ←", "SCRL_RIGHT": "Scroll →",
    "LCLK": "Left click", "RCLK": "Right click", "MCLK": "Middle click",
}

TMUX_NAMES = {
    "front": "tmux: front", "back": "tmux: back", "perso": "tmux: perso",
    "obsidian": "tmux: obsidian",
}


class Labeler:
    def __init__(self, text: str, defines: dict[str, str], layer_names: list[str]):
        self.text = text
        self.defines = defines
        self.layer_names = layer_names
        self.table = key_table(text)
        self.chords = chord_table(text)
        self.mods = finger_mods(text)
        self.glyphs = glyphs(text)
        self.unknown: set[str] = set()

    # -- keycodes ---------------------------------------------------------
    def macro_expand(self, expr: str, depth: int = 0) -> str:
        """Expand the keymap's _C/_W/_KP_* style defines into raw keycodes."""
        expr = expr.strip()
        if depth > 8:
            return expr
        if expr in self.table:  # KEY_LH_C4R4 -> A
            return self.table[expr]
        if expr in self.mods:
            return self.mods[expr]
        if expr.endswith("_FINGER_MOD"):
            finger = expr[: -len("_FINGER_MOD")]
            if finger in self.mods:
                # PINKY_FINGER_MOD etc. have both macOS and non-macOS branches
                # in the keymap text; finger_mods() has already picked the one
                # this configuration actually compiles.
                return self.mods[finger]
        if expr.endswith("_MOD") or expr.endswith("_KEY"):
            resolved = self.table.get(expr) or self.defines.get(expr)
            if resolved:
                return self.macro_expand(resolved, depth + 1)
        value = self.defines.get(expr)
        if value and value != expr:
            if "(" in value:  # applied macro, e.g. _C(LEFT)
                return value
            return self.macro_expand(value, depth + 1)
        # function-style application: _C(K), _W(LEFT)
        match = re.fullmatch(r"(_\w+)\((.+)\)", expr)
        if match:
            head, inner = match.group(1), match.group(2)
            prefix = self.defines.get(head)
            if prefix:
                return f"{prefix}({self.macro_expand(inner, depth + 1)})"
        return expr

    def key_label(self, expr: str) -> str:
        code = self.macro_expand(expr)
        # peel nested modifier wrappers, innermost last
        parts: list[str] = []
        while True:
            match = re.fullmatch(r"([A-Z]{2})\((.+)\)", code)
            if not match or match.group(1) not in MOD_PREFIX:
                break
            parts.append(MOD_PREFIX[match.group(1)])
            code = match.group(2)
        name = KEY_NAMES.get(code) or MEDIA_NAMES.get(code) or code
        if re.fullmatch(r"KP_N\d", code):
            name = "KP " + code[-1]
        elif re.fullmatch(r"N\d", code):
            name = code[1]
        if parts:
            name = " + ".join(parts) + " + " + name
        return name

    # -- whole bindings ---------------------------------------------------
    def describe(self, binding: str, index: int, chain: list[str]) -> dict:
        match = re.match(r"(&\S+)\s*(.*)$", binding)
        if not match:
            raise SystemExit(f"generate_field_guide: unparsable binding {binding!r} at {index}")
        behavior, rest = match.group(1), match.group(2).strip()
        # Keep the first argument intact so nested calls like LS(N2) or _C(K)
        # survive; flatten only where a macro takes several arguments.
        first = rest.split()[0] if rest else ""
        flat = re.sub(r"[(),]", " ", rest).split()

        if behavior == "&trans":
            inherited = chain[index]
            return {"tap": inherited["tap"], "hold": inherited["hold"],
                    "kind": inherited["kind"], "raw": "&trans", "inherited": True,
                    "effective": inherited["tap"]}

        return self._direct(behavior, first, flat)

    def _direct(self, behavior: str, first: str, args: list[str]) -> dict:
        out = {"tap": "", "hold": "", "kind": "", "raw": "", "inherited": False,
               "effective": ""}

        if behavior == "&none":
            out.update(tap="—", kind="disabled")
        elif behavior == "&kp":
            resolved = self.key_label(first)
            if resolved:
                out.update(tap=resolved, kind="keypad" if "KP" in first else "")
            else:
                out.update(tap="—", kind="disabled")
        elif behavior in ("&LeftPinky", "&LeftRing1", "&LeftRing2", "&LeftMiddy",
                          "&LeftIndex", "&RightPinky", "&RightRing1", "&RightRing2",
                          "&RightMiddy", "&RightIndex"):
            mod = self.mods.get("PINKY" if "Pinky" in behavior else
                                "RING1" if "Ring1" in behavior else
                                "RING2" if "Ring2" in behavior else
                                "MIDDY" if "Middy" in behavior else "INDEX")
            hold = f"{KEY_NAMES.get(mod, mod)} + {behavior[1:]} layer"
            out.update(tap=self.key_label(args[0]), hold=hold, kind="mod")
        elif behavior[1:] in self.chords:
            mod_def, key_def = self.chords[behavior[1:]]
            mod = self.mods.get(mod_def.split("_")[1], mod_def)
            out.update(tap=self.key_label(key_def),
                       hold=f"{KEY_NAMES.get(mod, mod)} + chord", kind="mod")
        elif re.fullmatch(r"&(?:left|right)_\w+_tap", behavior):
            # plain-key taps used on the bilateral layers
            out.update(tap=self.key_label(args[0]), kind="")
        elif behavior[1:] in self.defines and self.defines[behavior[1:]].startswith("kp "):
            out.update(tap=self.key_label(self.defines[behavior[1:]][3:].strip()), kind="")
        elif behavior in ("&plain",):
            out.update(tap=self.key_label(args[1]), hold=f"{args[0].replace('LAYER_', '')} layer",
                       kind="layer")
        elif behavior in ("&thumb", "&space"):
            out.update(tap=self.key_label(args[1]), hold=f"{args[0].replace('LAYER_', '')} layer",
                       kind="layer")
        elif behavior == "&thumb_parang_left":
            out.update(tap="(", hold=f"{args[0].replace('LAYER_', '')} layer", kind="layer")
        elif behavior == "&parang_right":
            out.update(tap=")", kind="")
        elif behavior == "&parang_left":
            out.update(tap="(", kind="")
        elif behavior == "&lower":
            out.update(tap="Lower", hold="Lower layer", kind="layer")
        elif behavior == "&magic":
            out.update(tap="Magic", hold="Magic layer", kind="layer")
        elif behavior == "&sticky_key_modtap":
            out.update(tap=f"one-shot {self.key_label(first)}", kind="mod")
        elif behavior == "&sk":
            out.update(tap=f"one-shot {KEY_NAMES.get(args[0], args[0])}", kind="mod")
        elif behavior == "&caps_word":
            out.update(tap="Caps Word", kind="action")
        elif behavior in ("&select_word", "&select_line", "&select_none",
                          "&extend_word", "&extend_line"):
            out.update(tap=behavior[1:].replace("_", " ").title(), kind="action")
        elif behavior == "&mod_tab":
            out.update(tap=f"hold {self.key_label(args[0])} + Tab", kind="action")
        elif behavior == "&linux_magic_sysrq":
            out.update(tap="Magic SysRq (REISUB)", kind="action")
        elif behavior.startswith("&tmux_shortcut_"):
            suffix = behavior[len("&tmux_shortcut_"):]
            out.update(tap=TMUX_NAMES.get(suffix, f"tmux: window {suffix}"), kind="action")
        elif behavior in ("&bootloader",):
            out.update(tap="Bootloader", kind="action")
        elif behavior in ("&reset", "&sys_reset"):
            out.update(tap="Restart", kind="action")
        elif behavior == "&bt":
            code = args[0] if args else ""
            out.update(tap={"BT_CLR": "Clear BT", "BT_CLR_ALL": "Clear all BT"}.get(code, code),
                       kind="action")
        elif re.fullmatch(r"&bt_\d", behavior):
            out.update(tap=f"Bluetooth {behavior[-1]}", kind="action")
        elif behavior == "&out":
            out.update(tap="USB output", kind="action")
        elif behavior == "&to":
            name = self.layer_names[int(args[0])]
            out.update(tap=f"→ {name}", kind="layer")
        elif behavior == "&tog":
            token = args[0]
            name = self.layer_names[int(token)] if token.isdigit() else token.replace("LAYER_", "")
            out.update(tap=f"Toggle {name}", kind="layer")
        elif behavior == "&rgb_ug":
            out.update(tap=RGB_NAMES.get(args[0], args[0]), kind="action")
        elif behavior in ("&mmv", "&msc", "&mkp"):
            out.update(tap=MOVE_NAMES.get(args[0], args[0]), kind="action")
        elif behavior in ("&emoji_zwj",):
            out.update(tap="ZWJ (combiner)", kind="action")
        elif behavior.startswith("&emoji_"):
            name = behavior[len("&emoji_"):]
            glyph = self.glyphs.get("emoji_" + name, "")
            pretty = name.replace("_", " ").capitalize()
            out.update(tap=f"{glyph} {pretty}".strip(), kind="action")
        elif behavior.startswith("&world_"):
            name = behavior[len("&world_"):]
            out.update(tap=WORLD_LABELS.get(name, name.replace("_", " ")), kind="action")
        else:
            self.unknown.add(behavior)
            out.update(tap=behavior[1:], kind="")
        return out


WORLD_LABELS = {
    "degree_sign": "°", "section_sign": "§", "paragraph_sign": "¶",
    "o_ordinal": "º", "a_ordinal": "ª", "micro_sign": "µ",
    "exclaim_left": "¡", "question_left": "¿",
    "y_base": "ý ÿ", "o_base": "ó ö ô ò õ ø", "u_base": "ú ü û ù",
    "i_base": "í ï î ì", "e_base": "é ë ê è æ", "a_base": "á ä â à ã å",
    "consonants_base": "ç ß ñ", "currency_base": "$ ¥ ₩ € £",
    "quotes_left_base": "‹ « ‘ “ ‚ „ 「 『 `",
    "quotes_right_base": "› » ’ ” 」 』 ´",
}


def active_define(text: str, name: str) -> bool:
    """True if `#define <name>` is present and not commented out."""
    return bool(re.search(rf"^[ \t]*#define[ \t]+{name}\b", text, re.M))


def timings(text: str) -> dict[str, int]:
    """Resolve the timing defines the Field Guide describes."""
    env = numeric_defines(parse_defines(text))
    out = {"tapping_resolution": env["TAPPING_RESOLUTION"],
           "difficulty": env.get("DIFFICULTY_LEVEL", 0),
           "index_streak": env.get("INDEX_STREAK_DECAY"),
           "shift_forgiveness": active_define(text, "SHIFT_FORGIVENESS")}
    for name in ("HOMEY", "INDEX", "MIDDY", "RING1", "PINKY", "PLAIN", "THUMB",
                 "SPACE", "STICKY", "CHORD"):
        if f"{name}_HOLDING_TIME" in env:
            out[name.lower()] = env[f"{name}_HOLDING_TIME"]
    return out


# --------------------------------------------------------------------------
# Field Guide HTML
# --------------------------------------------------------------------------

RENDERER = r"""
'use strict';
const data=JSON.parse(document.getElementById('layout-data').textContent);
const $=id=>document.getElementById(id);
let layer=0,selected=64,pair=[];
const keys=i=>data.layers[layer].keys[i];
function info(i){const k=keys(i);return k}
function select(i){selected=i;render()}
function render(){
  const query=$('search').value.trim().toLowerCase();
  $('board').replaceChildren();let found=0;
  data.physical.forEach((p,i)=>{
    const d=info(i),[w,h,x,y,angle,rx,ry]=p;
    const button=document.createElement('button');button.type='button';
    button.className='key '+d.kind+(d.inherited?' inherited':'')+(i===selected?' selected':'');
    button.dataset.position=i;
    button.style.cssText=`left:${(x+4)/18}%;top:${(y+4)/8.6}%;width:${(w-8)/18}%;height:${(h-8)/8.6}%;transform:rotate(${angle/100}deg);transform-origin:${(rx-x-4)/(w-8)*100}% ${(ry-y-4)/(h-8)*100}%;`;
    const match=query?(query.startsWith('#')?String(i)===query.slice(1):query.length===1?d.tap.toLowerCase()===query:[d.tap,d.hold,d.raw].some(v=>String(v).toLowerCase().includes(query))):pair.includes(i);
    if(match){button.classList.add('match');found++}else if(query||pair.length)button.classList.add('dim');
    button.setAttribute('aria-label',`Position ${i}, ${d.tap}${d.hold?', hold '+d.hold:''}${d.inherited?', inherited':''}`);
    button.setAttribute('aria-pressed',String(i===selected));
    const idx=document.createElement('span');idx.className='idx';idx.textContent=i;
    const title=document.createElement('strong');title.textContent=d.tap;
    const sub=document.createElement('small');
    sub.textContent=d.hold?'hold '+d.hold:d.inherited?'\u21b3 base layer':d.kind==='keypad'?'keypad':'';
    button.append(idx,title,sub);button.onclick=()=>select(i);$('board').append(button);
  });
  $('searchStatus').textContent=query?`${found} matching ${found===1?'key':'keys'}`:pair.length?'Bootloader pair highlighted':'';
  document.querySelectorAll('[data-layer]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.layer)===layer)));
  $('layerHelp').textContent=data.layers[layer].help;
  inspect();
}
function inspect(){
  const d=info(selected),[r,c]=data.coords[selected];
  const hand=c<7?'Left':'Right',thumb=c===6||c===7;
  $('selectedName').textContent=d.tap+' · #'+selected;
  const rows=[['Location',`${hand} ${thumb?'thumb cluster':'key'}`],
    ['Tap',d.kind==='disabled'?'No action':d.tap],
    ['Hold',d.hold||'No separate hold action'],
    ['Matrix',`row ${r}, column ${c} (zero-based)`],
    ['Binding',d.raw],
    ...(d.inherited?[['Resolves to',d.effective||d.raw]]:[])];
  $('details').replaceChildren();
  for(const [name,value]of rows){const dt=document.createElement('dt'),dd=document.createElement('dd');
    dt.textContent=name;dd.textContent=value;$('details').append(dt,dd)}
}
document.querySelectorAll('[data-layer]').forEach(b=>b.onclick=()=>{layer=Number(b.dataset.layer);pair=[];render()});
$('search').oninput=()=>{pair=[];render()};
document.querySelectorAll('[data-find]').forEach(b=>b.onclick=()=>{layer=Number(b.dataset.layer||0);pair=[];$('search').value='#'+b.dataset.find;select(Number(b.dataset.find))});
document.querySelectorAll('[data-pair]').forEach(b=>b.onclick=()=>{layer=0;$('search').value='';pair=b.dataset.pair.split(',').map(Number);selected=pair[0];render();$('board').scrollIntoView({behavior:'smooth',block:'center'})});
$('typing').onkeydown=e=>{$('event').textContent=`Received: ${e.key===' '?'Space':e.key} \u00b7 code: ${e.code} \u00b7 ${[e.ctrlKey?'Ctrl':'',e.altKey?'Alt':'',e.shiftKey?'Shift':'',e.metaKey?'Cmd':''].filter(Boolean).join(' + ')||'no modifiers'}`};
$('clear').onclick=()=>{$('typing').value='';$('event').textContent='Waiting for input.';$('typing').focus()};
const bad=[];if(data.layers.length!==data.meta.layer_count)bad.push('layer count');
data.layers.forEach(l=>{if(l.keys.length!==80)bad.push('keys in '+l.name)});
if(data.meta.letters!==26)bad.push('base letters ('+data.meta.letters+')');
if(data.coords.length!==80||data.physical.length!==80)bad.push('geometry');
if(bad.length)throw Error('Field guide verification failed: '+bad.join(', '));
$('audit').textContent=`${data.meta.layer_count} layers \u00b7 80 keys \u00b7 26 letters \u00b7 checked`;
$('provenance').textContent=`${data.meta.title} \u00b7 keymap ${data.meta.commit.slice(0,7)} \u00b7 MoErgo source ${data.meta.upstream.slice(0,7)} \u00b7 keymap SHA-256 ${data.meta.sha256}`;
render();
"""


def build_payload(layout: dict, text: str, bindings: list[list[str]],
                  geometry: dict, commit: str, sha256: str) -> dict:
    names = layout["layer_names"]
    labeler = Labeler(text, parse_defines(text), names)

    layers = []
    for li, (name, row) in enumerate(zip(names, bindings)):
        base = layers[0]["keys"] if layers else None
        keys = []
        for i, binding in enumerate(row):
            if binding == "&trans" and base is not None:
                d = dict(base[i])
                d.update(raw="&trans", inherited=True, effective=base[i]["tap"])
                keys.append(d)
            else:
                d = labeler.describe(binding, i, base or [])
                d["raw"] = binding
                keys.append(d)
        layers.append({
            "name": name,
            "help": layer_help(name, keys),
            "keys": keys,
        })

    if labeler.unknown:
        raise SystemExit("generate_field_guide: unlabelled behaviors: "
                         + ", ".join(sorted(labeler.unknown)))

    letters = {k["tap"] for k in layers[0]["keys"] if re.fullmatch(r"[A-Za-z]", k["tap"] or "")}
    payload = {
        "meta": {
            "title": layout.get("title", "Glove80 layout"),
            "uuid": layout.get("uuid", ""),
            "date": layout.get("date", 0),
            "layer_count": len(names),
            "letters": len(letters),
            "commit": commit,
            "sha256": sha256,
            "upstream": geometry["upstream"],
            "timings": timings(text),
        },
        "layers": layers,
        "coords": geometry["coords"],
        "physical": geometry["physical"],
    }
    return payload


def layer_help(name: str, keys: list[dict]) -> str:
    holds = []
    for k in keys:
        hold = k.get("hold") or ""
        if k["kind"] == "layer" and hold and not k.get("inherited") and hold not in holds:
            holds.append(hold)
    if name == "ColemakDHm":
        return "Base layer · tap to type, hold home-row keys for modifiers"
    if holds:
        return f"{name} layer · holds: " + ", ".join(holds[:4])
    return f"{name} layer"


def render_html(shell: str, payload: dict) -> str:
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    html = re.sub(r'(<script id="layout-data" type="application/json">).*?(</script>)',
                  lambda m: m.group(1) + blob + m.group(2), shell, flags=re.S)
    html = re.sub(r"<script>\n.*?</script>\n</html>",
                  lambda m: "<script>" + RENDERER + "</script>\n</html>",
                  html, flags=re.S)
    names = [l["name"] for l in payload["layers"]]
    html = re.sub(r'(<span class="badge">)[^<]*(</span>)',
                  lambda m: m.group(1) + f"{payload['meta']['title']} · {len(names)} layers"
                  + m.group(2), html, count=1)
    tabs = "".join(
        f'<button data-layer="{i}" aria-pressed="{"true" if i == 0 else "false"}">'
        f'{i:02d} · {n}</button>' for i, n in enumerate(names))
    html = re.sub(r'(<nav class="tabs"[^>]*>).*?(</nav>)',
                  lambda m: m.group(1) + tabs + m.group(2), html, flags=re.S)

    base = payload["layers"][0]["keys"]
    label = lambda i: (base[i]["tap"] or "—").replace("<", "&lt;").replace(">", "&gt;")

    # quick-find buttons: the base layer's layer-access keys
    finds = [(i, k) for i, k in enumerate(base) if k["kind"] == "layer" and k["hold"]]
    quick = "".join(
        f'<button data-find="{i}" data-layer="0">Find {k["hold"].replace("<", "")}</button>'
        for i, k in finds[:5])
    html = re.sub(r'(<div class="quick">).*?(</div>)',
                  lambda m: m.group(1) + quick + m.group(2), html, flags=re.S)

    # bootloader instructions: positions are fixed physical switches
    html = re.sub(
        r'(<ol>).*?(</ol>)',
        lambda m: m.group(1)
        + "<li><strong>Right first:</strong> power off, connect USB, hold positions "
          f'<button class="plain" data-pair="30,79">#30 + #79</button> (currently '
          f'{label(30)} + {label(79)}), then power on. Copy your UF2 to '
          "<code>GLV80RHBOOT</code>.</li>"
        + "<li><strong>Left:</strong> power off, connect USB, hold positions "
          f'<button class="plain" data-pair="64,25">#64 + #25</button> (currently '
          f'{label(64)} + {label(25)}), then power on. Copy the same UF2 to '
          "<code>GLV80LHBOOT</code>.</li>"
        + m.group(2),
        html, flags=re.S)

    t = payload["meta"]["timings"]
    timing_text = (
        f"Home-row holds: {t.get('homey', '?')} ms tapping term, with per-finger "
        f"times (pinky {t.get('pinky', '?')}, ring {t.get('ring1', '?')}, "
        f"middle {t.get('middy', '?')}, index {t.get('index', '?')}); chord holds "
        f"{t.get('chord', '?')} ms. Thumb layer holds: {t.get('thumb', '?')} ms. "
        f"Sticky one-shot keys: {t.get('sticky', '?')} ms. Tapping resolution "
        f"{t.get('tapping_resolution', '?')} ms (difficulty level {t.get('difficulty', '?')}). "
        "Home-row keys also hold their own finger layer, so a one-handed hold "
        "falls back to a plain tap when ENFORCE_BILATERAL is set in the keymap. "
        f"Shift forgiveness is {'on' if t.get('shift_forgiveness') else 'off'}; "
        f"index streak decay {t.get('index_streak', '?')} ms "
        "(0 = home-row shift stays available while typing fast).")
    html = re.sub(r'<p>Home-row holds:.*?</p>',
                  lambda m: "<p>" + timing_text + "</p>", html, flags=re.S)

    # source link should point at the commit this Field Guide was built from
    html = re.sub(r'(blob/)[0-9a-f]{40}(/config/glove80\.keymap)',
                  lambda m: m.group(1) + payload["meta"]["commit"] + m.group(2), html)
    return html


def geometry_from(shell: str) -> dict:
    """Reuse the geometry already embedded in whichever Field Guide is on disk."""
    match = re.search(r'<script id="layout-data" type="application/json">(.*?)</script>',
                      shell, re.S)
    if not match:
        raise SystemExit("generate_field_guide: no geometry source found")
    data = json.loads(match.group(1))
    upstream = data.get("upstream") or data.get("meta", {}).get("upstream")
    if not upstream or "coords" not in data or "physical" not in data:
        raise SystemExit("generate_field_guide: incomplete geometry source")
    return {"coords": data["coords"], "physical": data["physical"],
            "upstream": upstream}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="fail if the committed Field Guide is out of date")
    args = parser.parse_args()

    layout = json.loads(LAYOUT.read_text(encoding="utf-8"))
    text = KEYMAP.read_text(encoding="utf-8")
    shell = OUT.read_text(encoding="utf-8")
    # Pin to the commit that last changed the keymap, not to HEAD: the Field
    # Guide is a snapshot of that revision, and this stays stable when unrelated
    # files are committed (so --check does not fail after every commit).
    commit = subprocess.run(
        ["git", "-C", str(ROOT), "log", "-1", "--format=%H", "--",
         str(KEYMAP.relative_to(ROOT))],
        capture_output=True, text=True, check=True).stdout.strip()
    sha256 = hashlib.sha256(KEYMAP.read_bytes()).hexdigest()

    bindings = build_bindings(layout)
    payload = build_payload(layout, text, bindings, geometry_from(shell), commit, sha256)
    html = render_html(shell, payload)

    if args.check:
        if html != shell:
            print("docs/glove80.html is out of date; run tools/generate_field_guide.py")
            return 1
        print("docs/glove80.html is up to date")
        return 0

    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {payload['meta']['layer_count']} layers, "
          f"{payload['meta']['letters']} base letters, {len(html)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
