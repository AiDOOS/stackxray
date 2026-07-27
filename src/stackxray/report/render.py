"""Render a CapabilityMap into a self-contained HTML report (SPEC §4, §8, §11).

Aesthetic: "diagnostic film -> editorial readout". A dark X-ray-film hero (luminous
stats, faint scanline, trust assurance) gives way to a light editorial body (serif
headlines, semantic verdict colours, refined capability rows).

Compliance constraints baked in:
  - ONE self-contained HTML string. NO external resources - no CDN, no web fonts, no
    remote anything. Fonts are system-stack only. A test enforces "no external resource".
  - Inline JS is progressive enhancement (verdict filtering, expand/collapse). The report
    is fully readable and navigable with JS disabled (native <details>).
  - No I/O or egress here - only data -> markup. The consent share is described honestly;
    the actual send lives in consent/ + cloud/.
"""

from __future__ import annotations

import html

from ..consent import build_fingerprint
from ..conversion import draft_scope
from ..models import Capability, CapabilityMap, Kind, Level, Verdict
from .explain import describe, resolve_hint, why

# verdict -> (label, slug). Colours are driven by the slug via CSS custom properties.
_VERDICT = {
    Verdict.KEEP:        ("Keep", "keep"),
    Verdict.RETIRE:      ("Retire", "retire"),
    Verdict.CONSOLIDATE: ("Consolidate", "consolidate"),
    Verdict.AGENTIFY:    ("Agentify", "agentify"),
    Verdict.BUY_REPLACE: ("Buy / Replace", "buy"),
    Verdict.UNDECIDED:   ("Undecided", "undecided"),
}
_ACTIONABLE = {Verdict.RETIRE, Verdict.CONSOLIDATE, Verdict.AGENTIFY, Verdict.BUY_REPLACE}

_CSS = """
*{box-sizing:border-box}
:root{
  --paper:#f4f2ec; --ink:#16181d; --muted:#6b7076; --faint:#9aa0a6;
  --line:#e5e2d9; --card:#fffdf8; --card-2:#faf8f2;
  --film:#0c0f14; --film-2:#12161d; --scan:#4fe3d6; --scan-deep:#0c8f86;
  --serif:Georgia,'Iowan Old Style','Times New Roman',serif;
  --sans:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
  --mono:ui-monospace,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace;
  --keep:#0f766e; --keep-bg:#e6f2ef;
  --retire:#c22a21; --retire-bg:#fbe9e7;
  --consolidate:#b25a06; --consolidate-bg:#fbf0e0;
  --agentify:#6d28d9; --agentify-bg:#efe9fb;
  --buy:#1d4ed8; --buy-bg:#e7eefc;
  --undecided:#5b6470; --undecided-bg:#edeff2;
}
html{scroll-behavior:smooth}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);
  font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}
.v-keep{--vc:var(--keep);--vbg:var(--keep-bg)} .v-retire{--vc:var(--retire);--vbg:var(--retire-bg)}
.v-consolidate{--vc:var(--consolidate);--vbg:var(--consolidate-bg)}
.v-agentify{--vc:var(--agentify);--vbg:var(--agentify-bg)}
.v-buy{--vc:var(--buy);--vbg:var(--buy-bg)} .v-undecided{--vc:var(--undecided);--vbg:var(--undecided-bg)}

/* ---- hero (the film) ---- */
.hero{position:relative;background:radial-gradient(120% 140% at 82% -10%,rgba(79,227,214,.10) 0,transparent 55%),
  linear-gradient(180deg,var(--film-2),var(--film));color:#eef2f4;overflow:hidden}
.hero::before{content:"";position:absolute;inset:0;pointer-events:none;opacity:.5;
  background:repeating-linear-gradient(0deg,transparent 0 3px,rgba(255,255,255,.014) 3px 4px)}
.hero::after{content:"";position:absolute;left:0;right:0;height:36%;top:-36%;pointer-events:none;
  background:linear-gradient(180deg,transparent,rgba(79,227,214,.10),transparent);
  animation:scan 7s linear infinite}
@keyframes scan{to{transform:translateY(340%)}}
.hero .inner{position:relative;max-width:1080px;margin:0 auto;padding:30px 28px 40px}
.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:34px}
.wordmark{font-weight:800;letter-spacing:.22em;font-size:13px}
.wordmark b{color:var(--scan);font-weight:800}
.assure{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#9fb6b8;
  border:1px solid rgba(79,227,214,.28);border-radius:999px;padding:6px 12px}
.assure b{color:var(--scan)}
.eyebrow{font-size:12px;letter-spacing:.34em;text-transform:uppercase;color:var(--scan);margin:0 0 10px}
.hero h1{font-family:var(--serif);font-weight:500;font-size:40px;line-height:1.05;margin:0 0 8px;letter-spacing:-.01em}
.hero .sub{color:#aeb6bd;font-family:var(--mono);font-size:12.5px;margin:0 0 30px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:rgba(255,255,255,.07);
  border:1px solid rgba(255,255,255,.09);border-radius:14px;overflow:hidden}
.stat{background:linear-gradient(180deg,rgba(255,255,255,.02),transparent);padding:18px 20px}
.stat .n{font-size:34px;font-weight:700;font-variant-numeric:tabular-nums;letter-spacing:-.02em;line-height:1}
.stat.accent .n{color:var(--scan)}
.stat .l{font-size:11px;letter-spacing:.13em;text-transform:uppercase;color:#8b949c;margin-top:8px}
.meter{display:flex;gap:2px;height:12px;margin:26px 0 12px;border-radius:999px;overflow:hidden}
.meter i{display:block;min-width:2px}
.legend{display:flex;flex-wrap:wrap;gap:16px 22px;font-size:12.5px;color:#c3cace}
.legend span{display:inline-flex;align-items:center;gap:7px}
.legend s{width:9px;height:9px;border-radius:50%;text-decoration:none}
.legend b{color:#eef2f4;font-variant-numeric:tabular-nums}

/* ---- body ---- */
.wrap{max-width:1080px;margin:0 auto;padding:0 28px 72px}
.toolbar{position:sticky;top:0;z-index:5;display:flex;flex-wrap:wrap;gap:8px;align-items:center;
  background:color-mix(in srgb,var(--paper) 88%,transparent);backdrop-filter:blur(8px);
  padding:14px 0;margin:0 0 8px;border-bottom:1px solid var(--line)}
.toolbar .lbl{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin-right:2px}
.chip{font-family:inherit;font-size:12.5px;cursor:pointer;border:1px solid var(--line);
  background:var(--card);color:var(--ink);border-radius:999px;padding:6px 12px;display:inline-flex;gap:7px;align-items:center}
.chip:hover{border-color:var(--faint)}
.chip.active{background:var(--ink);color:#fff;border-color:var(--ink)}
.chip s{width:8px;height:8px;border-radius:50%;background:var(--vc,#999);text-decoration:none}
.chip .c{font-variant-numeric:tabular-nums;opacity:.7}
.chip.active .c{opacity:.85}
.spacer{flex:1}
.tool-link{font-size:12px;color:var(--muted);cursor:pointer;background:none;border:none;font-family:inherit;padding:6px 4px}
.tool-link:hover{color:var(--ink);text-decoration:underline}

.exec{margin:22px 0 6px}
.ex-grid{display:grid;grid-template-columns:1.3fr 1.3fr 1fr;gap:14px}
.ex-card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;
  box-shadow:0 1px 2px rgba(20,22,28,.03)}
.ex-card h3{font-family:var(--serif);font-weight:500;font-size:17px;margin:0}
.ex-sub{color:var(--muted);font-size:12px;margin:3px 0 10px}
.ex-card ul{margin:0;padding-left:16px}
.ex-card li{margin:5px 0;font-size:13.5px;line-height:1.45}
.ex-do{border-top:3px solid var(--keep)}
.ex-do li b{color:var(--keep)}
.ex-wait{border-top:3px solid var(--scan-deep)}
.ex-wait li b{color:var(--scan-deep)}
.ex-cov{border-top:3px solid var(--undecided)}
.ex-cov-body{font-size:13.5px;line-height:1.7;margin:0}
.ex-cov-body .gap{color:var(--faint);font-size:12.5px}
@media (max-width:720px){.ex-grid{grid-template-columns:1fr}}
.section-h{font-family:var(--serif);font-size:15px;color:var(--muted);font-weight:400;
  letter-spacing:.02em;margin:26px 2px 12px;text-transform:none}
details.product{background:var(--card);border:1px solid var(--line);border-radius:14px;margin:0 0 12px;
  box-shadow:0 1px 2px rgba(20,22,28,.03);animation:rise .5s both}
@keyframes rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
details.product>summary{list-style:none;cursor:pointer;padding:16px 20px;display:flex;
  justify-content:space-between;align-items:center;gap:16px}
details.product>summary::-webkit-details-marker{display:none}
.product .pname{font-family:var(--serif);font-size:19px;letter-spacing:-.01em}
.product .pname .caret{color:var(--faint);font-size:13px;margin-right:9px;transition:transform .15s}
details.product[open] .pname .caret{transform:rotate(90deg);display:inline-block}
.pstrip{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--muted)}
.pstrip span{display:inline-flex;align-items:center;gap:6px;font-variant-numeric:tabular-nums}
.pstrip s{width:8px;height:8px;border-radius:50%;background:var(--vc);text-decoration:none}
.rows{padding:2px 14px 12px}

.cap{border-top:1px solid var(--line);border-left:3px solid var(--vc);margin-top:2px;
  padding:13px 14px;background:linear-gradient(90deg,var(--vbg),transparent 42%)}
.cap.is-gap{border-left-style:dashed;background:none}
.cap .top{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.badge{font-size:10.5px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;
  color:var(--vc);background:var(--vbg);border:1px solid color-mix(in srgb,var(--vc) 22%,transparent);
  padding:3px 9px;border-radius:6px;white-space:nowrap}
.cname{font-weight:650;font-size:14.5px}
.desc{margin:7px 0 0;color:#3a3f45;font-size:13.5px;line-height:1.5}
.why{margin:5px 0 0;color:var(--muted);font-size:13px;line-height:1.5}
.why b{color:var(--vc)}
.resolve{margin:6px 0 0;font-size:13px;line-height:1.5;color:#1a5f4a;
  background:color-mix(in srgb,var(--scan-deep) 8%,transparent);
  border-left:2px solid var(--scan-deep);padding:6px 10px;border-radius:0 6px 6px 0}
.resolve b{color:var(--scan-deep)}
.tag{font-size:10px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);
  border:1px solid var(--line);border-radius:5px;padding:2px 6px}
.tag.saas{color:var(--scan-deep);border-color:color-mix(in srgb,var(--scan-deep) 30%,transparent)}
.tag.gap{color:var(--faint)}
.grow{flex:1}
.conf{font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.conf b{color:var(--ink);text-transform:uppercase;letter-spacing:.04em;font-size:10px}
.metas{display:flex;flex-wrap:wrap;gap:6px;margin:9px 0 0}
.metas .m{font-size:11.5px;color:var(--muted);background:var(--card-2);border:1px solid var(--line);
  border-radius:6px;padding:2px 8px;font-variant-numeric:tabular-nums}
.metas .m.mono{font-family:var(--mono);font-size:11px}
.metas .m.stake{color:var(--retire);border-color:color-mix(in srgb,var(--retire) 30%,transparent);font-weight:700}
details.sub{margin:9px 0 0}
details.sub>summary{list-style:none;cursor:pointer;font-size:12.5px;color:var(--scan-deep);
  display:inline-flex;align-items:center;gap:6px}
details.sub>summary::-webkit-details-marker{display:none}
details.sub>summary::before{content:"+";font-family:var(--mono);color:var(--faint)}
details.sub[open]>summary::before{content:"-"}
.panel{margin:8px 0 2px;padding:12px 14px;background:var(--card-2);border:1px solid var(--line);border-radius:10px;font-size:13px}
.panel ul,.panel ol{margin:6px 0 0;padding-left:18px}
.panel li{margin:3px 0}
.loc{font-family:var(--mono);font-size:11.5px;color:var(--muted);word-break:break-all}
.scope .act{font-family:var(--serif);font-size:15px}
.scope .eff{display:inline-block;margin:6px 0;font-size:12px;font-weight:700;color:var(--scan-deep);
  background:var(--card);border:1px solid var(--line);border-radius:6px;padding:3px 9px}
.scope .note{color:var(--muted);font-size:12px;margin:8px 0 0}

.consent{border:1px solid color-mix(in srgb,var(--scan-deep) 26%,var(--line));background:var(--card)}
.consent .pname{color:var(--scan-deep)}
.consent pre{margin:10px 0 0;padding:14px;background:var(--film);color:#d7e0e3;border-radius:10px;
  overflow:auto;font-family:var(--mono);font-size:12px;line-height:1.5}
.foot{color:var(--muted);font-size:12.5px;margin:30px 2px 0;display:flex;gap:8px;align-items:center}
.foot s{width:7px;height:7px;border-radius:50%;background:var(--scan-deep);text-decoration:none}
.empty{display:none;color:var(--muted);font-size:13px;padding:20px 2px}
@media (max-width:720px){.stats{grid-template-columns:repeat(2,1fr)}.hero h1{font-size:30px}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;scroll-behavior:auto}}
"""

_JS = """
(function(){
  var chips=[].slice.call(document.querySelectorAll('[data-filter]'));
  function apply(f){
    document.querySelectorAll('.cap').forEach(function(r){
      r.style.display=(f==='all'||r.getAttribute('data-verdict')===f)?'':'none';
    });
    document.querySelectorAll('details.product').forEach(function(p){
      var any=[].slice.call(p.querySelectorAll('.cap')).some(function(r){return r.style.display!=='none';});
      p.style.display=any?'':'none'; if(any&&f!=='all'){p.open=true;}
    });
    var none=!document.querySelector('.cap[style=""],.cap:not([style])')&&f!=='all';
    var e=document.getElementById('empty'); if(e){e.style.display=none?'block':'none';}
    chips.forEach(function(c){c.classList.toggle('active',c.getAttribute('data-filter')===f);});
  }
  chips.forEach(function(c){c.addEventListener('click',function(){apply(c.getAttribute('data-filter'));});});
  var ea=document.getElementById('xall'),ca=document.getElementById('call');
  if(ea)ea.addEventListener('click',function(){document.querySelectorAll('details').forEach(function(d){d.open=true;});});
  if(ca)ca.addEventListener('click',function(){document.querySelectorAll('details.sub,details.product').forEach(function(d){d.open=false;});});
})();
"""


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _counts(caps: list[Capability]) -> dict[Verdict, int]:
    out = {v: 0 for v in _VERDICT}
    for c in caps:
        out[c.verdict] = out.get(c.verdict, 0) + 1
    return out


def _meter(caps: list[Capability]) -> str:
    counts = _counts(caps)
    total = max(1, len(caps))
    segs, legend = [], []
    for v, (label, slug) in _VERDICT.items():
        n = counts[v]
        if not n:
            continue
        segs.append(f'<i class="v-{slug}" style="width:{n/total*100:.3f}%;background:var(--vc)" title="{label}: {n}"></i>')
        legend.append(f'<span class="v-{slug}"><s style="background:var(--vc)"></s>{label} <b>{n}</b></span>')
    return f'<div class="meter">{"".join(segs)}</div><div class="legend">{"".join(legend)}</div>'


def _filter_bar(caps: list[Capability]) -> str:
    counts = _counts(caps)
    chips = [f'<button class="chip active" data-filter="all">All <span class="c">{len(caps)}</span></button>']
    for v, (label, slug) in _VERDICT.items():
        n = counts[v]
        if n:
            chips.append(f'<button class="chip v-{slug}" data-filter="{slug}"><s></s>{label} '
                         f'<span class="c">{n}</span></button>')
    return (f'<div class="toolbar"><span class="lbl">Filter</span>{"".join(chips)}'
            f'<span class="spacer"></span>'
            f'<button class="tool-link" id="xall">Expand all</button>'
            f'<button class="tool-link" id="call">Collapse</button></div>')


def _kind_tag(cap: Capability) -> str:
    if "(not yet extracted)" in cap.name:
        return '<span class="tag gap">Gap</span>'
    if cap.kind == Kind.INTEGRATED_SAAS:
        return '<span class="tag saas">SaaS</span>'
    if cap.kind == Kind.BOUGHT_SAAS:
        return '<span class="tag saas">Bought SaaS</span>'
    return ""


def _cap_row(cap: Capability) -> str:
    _label, slug = _VERDICT[cap.verdict]
    is_gap = "(not yet extracted)" in cap.name
    metas = []
    if cap.est_effort_to_act:
        metas.append(f'<span class="m stake">{_esc(cap.est_effort_to_act)}</span>')
    if cap.size_complexity:
        metas.append(f'<span class="m">{_esc(cap.size_complexity)}</span>')
    if cap.deployed_service:
        metas.append(f'<span class="m mono">{_esc(cap.deployed_service)}</span>')
    if cap.usage and cap.usage.requests is not None:
        metas.append(f'<span class="m">{cap.usage.requests:,} req / {cap.usage.window_days}d</span>')
    if cap.dependencies:
        metas.append(f'<span class="m">{_esc(", ".join(cap.dependencies[:4]))}</span>')

    evidence = "".join(
        f'<li>{_esc(e.detail)}'
        + (f'<br><span class="loc">{_esc(e.locator)}</span>' if e.locator else "")
        + "</li>"
        for e in cap.evidence
    ) or "<li>(no evidence recorded)</li>"

    sc = draft_scope(cap)
    eff = f'<span class="eff">{_esc(sc["effort"])} · {_esc(sc["rough_range"])}</span>' if sc["effort"] else ""
    steps = "".join(f"<li>{_esc(s)}</li>" for s in sc["steps"])

    hint = resolve_hint(cap)
    hint_html = f'<p class="resolve"><b>→ To resolve:</b> {_esc(hint)}</p>' if hint else ""

    return f'''<div class="cap v-{slug}{' is-gap' if is_gap else ''}" data-verdict="{slug}">
  <div class="top"><span class="badge">{_esc(_VERDICT[cap.verdict][0])}</span>
    <span class="cname">{_esc(cap.name)}</span>{_kind_tag(cap)}
    <span class="grow"></span><span class="conf">confidence <b>{_esc(cap.confidence.value)}</b></span></div>
  <p class="desc">{_esc(describe(cap))}</p>
  <p class="why"><b>Why {_esc(_VERDICT[cap.verdict][0].lower())}:</b> {_esc(why(cap))}</p>
  {hint_html}
  <div class="metas">{"".join(metas)}</div>
  <details class="sub"><summary>Evidence</summary><ul class="panel">{evidence}</ul></details>
  <details class="sub"><summary>What would it take to do this?</summary>
    <div class="panel scope"><span class="act">{_esc(sc["action"])}</span> {eff}
      <ol>{steps}</ol><div class="note">{_esc(sc["note"])}</div></div></details>
</div>'''


def _product(cmap: CapabilityMap, prod: Capability, idx: int) -> str:
    children = sorted(cmap.children_of(prod.id),
                      key=lambda c: (c.verdict != Verdict.RETIRE, c.verdict.value, c.name))
    counts = _counts(children)
    strip = "".join(
        f'<span class="v-{slug}"><s></s>{n}</span>'
        for v, (label, slug) in _VERDICT.items() if (n := counts[v])
    )
    rows = "".join(_cap_row(c) for c in children) or '<div class="cap">no capabilities</div>'
    delay = f'animation-delay:{min(idx * 0.03, 0.4):.2f}s'
    return (f'<details class="product" style="{delay}"><summary>'
            f'<span class="pname"><span class="caret">▸</span>{_esc(prod.name)}</span>'
            f'<span class="pstrip">{strip}</span></summary>'
            f'<div class="rows">{rows}</div></details>')


def _shelfware_cost(caps: list[Capability]) -> int:
    total = 0
    for c in caps:
        if c.verdict == Verdict.RETIRE and c.kind == Kind.BOUGHT_SAAS and c.est_effort_to_act:
            digits = "".join(ch for ch in c.est_effort_to_act if ch.isdigit())
            total += int(digits) if digits else 0
    return total


def _exec_summary(cmap: CapabilityMap, caps: list[Capability], counts: dict) -> str:
    # --- actionable now (needs no runtime data) --------------------------------------
    items = []
    clusters: dict[str, int] = {}
    for c in caps:
        if c.verdict == Verdict.CONSOLIDATE and c.redundancy_cluster:
            cat = c.redundancy_cluster.split(":")[1] if ":" in c.redundancy_cluster else "group"
            clusters[cat] = clusters.get(cat, 0) + 1
    for cat, n in sorted(clusters.items(), key=lambda x: -x[1]):
        items.append(f"<b>{n}</b> redundant {_esc(cat)} capabilities - consolidate to one")
    shelf = _shelfware_cost(caps)
    n_shelf = sum(1 for c in caps if c.verdict == Verdict.RETIRE and c.kind == Kind.BOUGHT_SAAS)
    if n_shelf:
        cost = f" - <b>${shelf:,}/yr</b> at stake" if shelf else ""
        items.append(f"<b>{n_shelf}</b> shelfware SaaS to retire{cost}")
    n_retire = sum(1 for c in caps if c.verdict == Verdict.RETIRE and c.kind != Kind.BOUGHT_SAAS)
    if n_retire:
        items.append(f"<b>{n_retire}</b> capabilities dead in production - safe to retire")
    if counts[Verdict.AGENTIFY]:
        items.append(f"<b>{counts[Verdict.AGENTIFY]}</b> candidates to rebuild as AI agents")
    gaps = sorted({c.name.split(': ', 1)[-1].replace(' (not yet extracted)', '')
                   for c in caps if "not yet extracted" in c.name})
    actionable_html = ("".join(f"<li>{it}</li>" for it in items)
                       or "<li>Add runtime or SaaS data below to surface actions.</li>")

    # --- awaiting data: the ONE thing to do next -------------------------------------
    n_undecided = counts[Verdict.UNDECIDED]
    unlocks = []
    if n_undecided:
        unlocks.append("Connect <b>runtime evidence</b> - an access-log export (monoliths) or a "
                       "Prometheus / Datadog / OTel query (services) - to turn these into Keep / Retire.")
    if not any(c.kind == Kind.BOUGHT_SAAS for c in caps):
        unlocks.append("Add an <b>SSO / spend export</b> to surface shelfware SaaS (paid-for, unused).")
    if gaps:
        unlocks.append(f"Add your <b>LLM key</b> to extract {_esc(', '.join(gaps))}.")
    unlock_html = "".join(f"<li>{u}</li>" for u in unlocks) or "<li>Nothing pending - full coverage.</li>"

    # --- coverage --------------------------------------------------------------------
    kinds = {"built": 0, "integrated-SaaS": 0, "bought-SaaS": 0}
    for c in caps:
        kinds[c.kind.value] = kinds.get(c.kind.value, 0) + 1
    cov = (f"<b>{len(cmap.by_level(Level.PRODUCT))}</b> products · <b>{len(caps)}</b> capabilities<br>"
           f"Built {kinds['built']} · Integrated-SaaS {kinds['integrated-SaaS']}"
           + (f" · Bought-SaaS {kinds['bought-SaaS']}" if kinds['bought-SaaS'] else "")
           + (f"<br><span class='gap'>Gaps: {_esc(', '.join(gaps))}</span>" if gaps else ""))

    return f'''<section class="exec">
  <div class="ex-grid">
    <div class="ex-card ex-do"><h3>Actionable now</h3>
      <p class="ex-sub">Findings that need no runtime data</p>
      <ul>{actionable_html}</ul></div>
    <div class="ex-card ex-wait"><h3>To unlock more</h3>
      <p class="ex-sub">{n_undecided:,} capabilities awaiting evidence</p>
      <ul>{unlock_html}</ul></div>
    <div class="ex-card ex-cov"><h3>Coverage</h3>
      <p class="ex-sub">What was mapped</p>
      <p class="ex-cov-body">{cov}</p></div>
  </div>
</section>'''


def render_html(cmap: CapabilityMap) -> str:
    caps = cmap.by_level(Level.CAPABILITY)
    products = cmap.by_level(Level.PRODUCT)
    counts = _counts(caps)
    actionable = sum(counts[v] for v in _ACTIONABLE)

    stat_data = [
        ("products", len(products), False),
        ("capabilities", len(caps), False),
        ("actionable now", actionable, True),
        ("awaiting data", counts[Verdict.UNDECIDED], False),
    ]
    stats = "".join(
        f'<div class="stat{" accent" if accent else ""}"><div class="n">{n:,}</div>'
        f'<div class="l">{label}</div></div>'
        for label, n, accent in stat_data
    )

    prod_blocks = "".join(
        _product(cmap, p, i) for i, p in enumerate(sorted(products, key=lambda p: p.name))
    )

    fingerprint_json = _esc(build_fingerprint(cmap).to_json())
    consent = (
        '<details class="product consent"><summary>'
        '<span class="pname"><span class="caret">▸</span>What would leave this environment</span>'
        '<span class="pstrip">consent-gated · nothing sent yet</span></summary>'
        '<div class="rows"><div class="cap v-undecided" data-verdict="none">'
        'Only an <b>abstract capability fingerprint</b> - counts, sizes, redundancy shapes, '
        'never source, data, or secrets - would ever leave, and only when you explicitly '
        'confirm. This is the <em>entire</em> payload; read it below. Enabling the send is the '
        f'AiDOOS cloud step. Until then this report is fully local.<pre>{fingerprint_json}</pre>'
        '</div></div></details>'
    )

    scan = _esc(cmap.scan_id or "local scan")
    title = _esc((cmap.scan_id or "portfolio").replace("scan:", ""))
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>StackXray - {scan}</title><style>{_CSS}</style></head><body>
<header class="hero"><div class="inner">
  <div class="topbar"><div class="wordmark">STACK<b>XRAY</b></div>
    <div class="assure"><b>Local scan</b> · nothing left this environment</div></div>
  <p class="eyebrow">Capability X-Ray</p>
  <h1>{title}</h1>
  <p class="sub">{scan} · portfolio → product → capability</p>
  <div class="stats">{stats}</div>
  {_meter(caps)}
</div></header>
<main class="wrap">
  {_exec_summary(cmap, caps, counts)}
  {_filter_bar(caps)}
  <p class="section-h">Products &amp; capabilities</p>
  {prod_blocks}
  <div class="empty" id="empty">No capabilities match this filter.</div>
  <p class="section-h">Trust boundary</p>
  {consent}
  <p class="foot"><s></s>Generated locally by StackXray. Your code and data never left this environment.</p>
</main>
<script>{_JS}</script></body></html>'''
