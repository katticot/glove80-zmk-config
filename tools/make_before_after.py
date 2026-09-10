#!/usr/bin/env python3
"""Regenerate docs/glove80-before-after.html: a before/after key diff.

Renders two revisions of config/glove80.keymap against each other, key by key,
so a change can be reviewed without opening two Field Guides side by side. The
labels come from the same code the Field Guide uses, so whatever that page says
about a key is what this page compares.

Usage:
    python3 tools/make_before_after.py [--before REV] [--after REV]

--before defaults to 856a4ff, the last build before the layer consolidation:
24 layers, the World/Emoji tree, and the Lower layer that held the keypad.
--after defaults to the working tree. REV may also be the literal WORKTREE.

The page reuses the Field Guide's stylesheet and board geometry, both read out
of docs/glove80.html, so the two documents stay visually identical.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_field_guide as fg  # noqa: E402

ROOT = fg.ROOT
KEYMAP = fg.KEYMAP
GUIDE = fg.OUT
OUT = ROOT / "docs" / "glove80-before-after.html"

DEFAULT_BEFORE = "856a4ff"

# Differences that are not visible in the per-key grid. Kept as prose rather
# than inferred, because they are intent, not data.
NOT_KEYS = [
    ("Layers", "24 &rarr; 18. Function, Emoji, Symbol, Mouse, World and Lower are gone; "
               "Cursor was removed and restored."),
    ("Number layer", "now sends real <code>KP_*</code> keypad codes instead of the "
                     "number row, because <code>USE_NUMPAD_KEYCODES</code> is defined. "
                     "This is what replaced Lower's keypad."),
    ("Combos", "the eight sticky-shift / hyper / meh / caps-word / tab-switcher combos "
               "fire on layers 0&ndash;11 instead of 0&ndash;8, so they now work while "
               "holding right ring2, middle or index."),
    ("World &amp; Emoji", "the whole macro tree behind them is deleted: ~287 KB of source "
                          "and 117 KB of firmware that nothing could reach."),
    ("<code>&amp;lower</code>", "base <b>#52</b> and Factory <b>#54</b> no longer reach a "
                                "Lower layer. Tap does nothing, double-tap returns to the "
                                "base layer, which on Factory is the only way home."),
    ("Dead code", "58 unreachable behaviour nodes, 70 unused <code>POS_*</code> defines, the "
                  "dead <code>#ifndef OPERATING_SYSTEM</code> fallback and unused editor "
                  "scaffolding are deleted."),
]


def read_keymap(rev: str) -> str:
    if rev == "WORKTREE":
        return KEYMAP.read_text(encoding="utf-8")
    return subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:config/glove80.keymap"],
                          capture_output=True, text=True, check=True).stdout


def labelled(text: str, geometry: dict, rev: str) -> dict:
    """Label a keymap exactly the way the Field Guide would."""
    names, bindings = fg.parse_layers(text)
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return fg.build_payload(names, text, bindings, geometry, rev, sha)


def describe(key: dict) -> dict:
    return {"tap": key["tap"], "hold": key.get("hold") or "", "kind": key.get("kind") or "",
            "raw": key.get("raw") or ""}


def build(before: dict, after: dict, before_rev: str, after_rev: str,
          before_bytes: int, after_bytes: int) -> dict:
    b_by = {l["name"]: l["keys"] for l in before["layers"]}
    a_by = {l["name"]: l["keys"] for l in after["layers"]}

    order = [l["name"] for l in after["layers"]]
    order += [n for n in (l["name"] for l in before["layers"]) if n not in a_by]

    layers, changed_total = [], 0
    for name in order:
        old, new = b_by.get(name), a_by.get(name)
        keys = []
        for i in range(fg.KEYS_PER_LAYER):
            o = describe(old[i]) if old else None
            n = describe(new[i]) if new else None
            if o is None:
                status = "added"
            elif n is None:
                status = "gone"
            elif (o["tap"], o["hold"], o["kind"]) == (n["tap"], n["hold"], n["kind"]):
                status = "same"
            else:
                status = "changed"
            if status == "changed":
                changed_total += 1
            keys.append({"pos": i, "old": o, "new": n, "status": status})
        layers.append({"name": name, "in_before": old is not None,
                       "in_after": new is not None,
                       "index_before": [l["name"] for l in before["layers"]].index(name)
                       if old is not None else None,
                       "index_after": [l["name"] for l in after["layers"]].index(name)
                       if new is not None else None,
                       "keys": keys})

    return {
        "meta": {
            "before_rev": before_rev, "after_rev": after_rev,
            "before_layers": len(before["layers"]), "after_layers": len(after["layers"]),
            "changed_keys": changed_total,
            "before_bytes": before_bytes, "after_bytes": after_bytes,
            "before_sha": before["meta"]["sha256"][:12],
            "after_sha": after["meta"]["sha256"][:12],
            "letters_before": before["meta"]["letters"],
            "letters_after": after["meta"]["letters"],
        },
        "layers": layers,
        "coords": before["coords"],
        "physical": before["physical"],
    }


RENDERER = r"""
'use strict';
const data=JSON.parse(document.getElementById('layout-data').textContent);
const $=id=>document.getElementById(id);
let layer=0,selected=null;
const L=()=>data.layers[layer];
const esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
function label(k){return k?k.tap:''}
function hold(k){return k&&k.hold?k.hold:(k&&k.inherited?'base layer':'')}
function render(){
  const l=L();
  $('board').replaceChildren();
  data.physical.forEach((p,i)=>{
    const d=l.keys[i],[w,h,x,y,angle,rx,ry]=p;
    const relevant=d.status==='changed'||d.status==='added'||d.status==='gone';
    const button=document.createElement('button');button.type='button';
    button.className='key '+(d.status==='same'?(d.new||d.old).kind:'')+' '+d.status;
    if(i===selected)button.classList.add('selected');
    if($('onlyChanges').checked&&!relevant)button.classList.add('dim');
    button.dataset.position=i;
    button.style.cssText=`left:${(x+4)/18}%;top:${(y+4)/8.6}%;width:${(w-8)/18}%;height:${(h-8)/8.6}%;transform:rotate(${angle/100}deg);transform-origin:${(rx-x-4)/(w-8)*100}% ${(ry-y-4)/(h-8)*100}%;`;
    const idx=document.createElement('span');idx.className='idx';idx.textContent=i;
    const title=document.createElement('strong');
    title.textContent=d.status==='gone'?label(d.old):label(d.new||d.old);
    const sub=document.createElement('small');
    if(d.status==='changed'){
      const was=label(d.old);
      sub.textContent=(was&&was!==label(d.new))?'was '+was:'was '+hold(d.old);
    }else if(d.status==='gone'){sub.textContent='removed'}
    else if(d.status==='added'){sub.textContent='new'}
    else {sub.textContent=hold(d.new)}
    button.append(idx,title,sub);
    button.setAttribute('aria-label',`Position ${i}, ${title.textContent}, ${d.status}`);
    button.onclick=()=>{selected=i;render()};
    $('board').append(button);
  });
  document.querySelectorAll('[data-layer]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.layer)===layer)));
  $('layerTitle').textContent=l.name;
  $('layerMeta').textContent=(l.in_before&&l.in_after)
    ?`layer ${l.index_before} → ${l.index_after}`
    :l.in_after?'new layer':'layer removed';
  inspect();
}
function inspect(){
  const l=L(),d=selected===null?null:l.keys[selected];
  $('detailCard').hidden=!d;
  if(!d)return;
  $('detailName').textContent=`Key #${selected} · ${l.name}`;
  $('detailStatus').textContent=d.status==='same'?'unchanged':d.status;
  $('detailStatus').className='badge status '+d.status;
  const row=(k)=>{if(!k)return '<dd class="absent">did not exist</dd>';
    return `<dd><code>${esc(k.raw||'')}</code><br>tap <b>${esc(k.tap)}</b>${k.hold?' · hold <b>'+esc(k.hold)+'</b>':''}${k.kind?' · '+esc(k.kind):''}</dd>`};
  $('detail').innerHTML=`<dt>before</dt>${row(d.old)}<dt>after</dt>${row(d.new)}`;
}
document.querySelectorAll('[data-layer]').forEach(b=>b.onclick=()=>{layer=Number(b.dataset.layer);selected=null;render()});
$('onlyChanges').onchange=render;
render();
"""


def short(rev: str) -> str:
    """A revision as a reader should see it."""
    return "the working tree" if rev == "WORKTREE" else rev[:7]


def render_html(payload: dict, shell: str) -> str:
    css = re.search(r"<style>(.*?)</style>", shell, re.S).group(1)
    m = payload["meta"]
    tabs = []
    for i, l in enumerate(payload["layers"]):
        mark = "" if (l["in_before"] and l["in_after"]) else (" ✚" if l["in_after"] else " ✖")
        tabs.append(f'<button data-layer="{i}" aria-pressed="{"true" if i == 0 else "false"}">'
                    f'{l["name"]}{mark}</button>')
    rows = "".join(
        f"<tr><th>{title}</th><td>{body}</td></tr>" for title, body in NOT_KEYS)
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Glove80 keymap — before and after</title>
<style>{css}
.key.same{{opacity:.5}}
.key.changed{{background:#ffe8c2;border-color:#d9a13b;box-shadow:0 3px 0 #e0be86}}
.key.gone{{background:#f1e0e0;border-color:#c9a4a4;box-shadow:0 3px 0 #cdb1b1}}
.key.gone strong{{text-decoration:line-through;text-decoration-color:#b98f8f}}
.key.added{{background:#d9efdc;border-color:#8fbd8f;box-shadow:0 3px 0 #a9cfae}}
.key.changed small,.key.gone small{{color:#9a5c0c;font-weight:600}}
.key.dim{{opacity:.18}}
.key.selected{{outline:3px solid #b47c25;outline-offset:1px;z-index:3}}
.swatch{{display:inline-block;width:11px;height:11px;border-radius:3px;border:1px solid var(--line);vertical-align:-1px;margin-right:5px}}
table.diff{{border-collapse:collapse;width:100%}}
table.diff th{{text-align:left;vertical-align:top;width:170px;padding:9px 14px 9px 0;font:11px ui-monospace,monospace;letter-spacing:1px;text-transform:uppercase;color:var(--muted)}}
table.diff td{{padding:9px 0;border-top:1px solid var(--line);color:var(--ink)}}
table.diff tr:first-child th,table.diff tr:first-child td{{border-top:0}}
dl#detail{{margin:0}}dl#detail dt{{font:11px ui-monospace,monospace;letter-spacing:1px;text-transform:uppercase;color:var(--muted);margin-top:12px}}
dl#detail dd{{margin:4px 0 0}}dd.absent{{color:var(--muted);font-style:italic}}
.toggle{{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--muted)}}
</style>
<header>
  <div class="brand">Glove80 <span>before / after</span></div>
  <span class="badge">{m['before_layers']} → {m['after_layers']} layers</span>
</header>
<main>
  <section class="intro">
    <div>
      <div class="eyebrow">keymap diff</div>
      <h1>{m['changed_keys']} keys changed</h1>
      <p>Every one of the {m['after_layers']} × 80 positions, compared between
      <code>{short(m['before_rev'])}</code> and <code>{short(m['after_rev'])}</code>. Both sides
      are labelled by the same code that builds the Field Guide, so a key shows here
      exactly as that page would show it.</p>
    </div>
    <span class="badge status">{m['before_bytes']:,} → {m['after_bytes']:,} bytes of keymap</span>
  </section>
  <div class="toolbar">
    <nav class="tabs" aria-label="Layer">{"".join(tabs)}</nav>
    <label class="toggle"><input type="checkbox" id="onlyChanges"> show only changes</label>
  </div>
  <section class="stage" aria-label="Keyboard layout">
    <div class="stage-top">
      <span id="layerMeta"></span>
      <span id="layerTitle"></span>
      <span>{m['letters_before']} → {m['letters_after']} base letters</span>
    </div>
    <div class="board-scroll"><div id="board" class="board" aria-label="80 physical keys"></div></div>
    <div class="legend">
      <span><i class="swatch" style="background:#e0eee0"></i>unchanged</span>
      <span class="hold"><i class="swatch" style="background:#ffe8c2"></i>changed</span>
      <span class="inherit"><i class="swatch" style="background:#d9efdc"></i>new</span>
      <span><i class="swatch" style="background:#f1e0e0"></i>removed</span>
    </div>
  </section>
  <div class="below">
    <section class="card" id="detailCard" hidden>
      <div class="eyebrow">selected key</div>
      <h2 id="detailName"></h2>
      <span class="badge status" id="detailStatus"></span>
      <dl id="detail"></dl>
    </section>
    <section class="card">
      <div class="eyebrow">differences that are not keys</div>
      <h2>What else moved</h2>
      <table class="diff"><tbody>{rows}</tbody></table>
    </section>
  </div>
  <details>
    <summary>How this page is built</summary>
    <p><code>tools/make_before_after.py</code> reads both revisions of the keymap, labels
    them with the Field Guide generator, and writes this page. Regenerate it after any
    keymap change:</p>
    <pre><code>python3 tools/make_before_after.py --before {m['before_rev'][:7]}</code></pre>
    <p>Before <code>{m['before_sha']}</code>, after <code>{m['after_sha']}</code>.</p>
  </details>
</main>
<footer></footer>
<script id="layout-data" type="application/json">{blob}</script>
<script>{RENDERER}</script>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", default=DEFAULT_BEFORE,
                    help="revision to compare from (default: %(default)s)")
    ap.add_argument("--after", default="WORKTREE",
                    help="revision to compare to (default: %(default)s)")
    args = ap.parse_args()

    shell = GUIDE.read_text(encoding="utf-8")
    geometry = fg.geometry_from(shell)

    before_text, after_text = read_keymap(args.before), read_keymap(args.after)
    before = labelled(before_text, geometry, args.before)
    after = labelled(after_text, geometry, args.after)
    payload = build(before, after, args.before, args.after,
                    len(before_text.encode()), len(after_text.encode()))
    OUT.write_text(render_html(payload, shell), encoding="utf-8")
    m = payload["meta"]
    print(f"wrote {OUT.relative_to(ROOT)}: {m['changed_keys']} changed keys across "
          f"{m['after_layers']} layers ({m['before_layers']} before), "
          f"{len(payload['layers'])} tabs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
