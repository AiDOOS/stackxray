"""V1 report - clean, exec-read Agentify Opportunities (expand for the technical detail).

One headline: which capabilities are the strongest candidates to rebuild as AI agents,
ranked and justified. Uncluttered by design - an exec reads the top; the technical detail
is one click away. Self-contained HTML, no external resources, no scripts required.
"""

from __future__ import annotations

import html
import json

from ..agentify import Opportunity
from ..conversion import draft_scope
from ..models import CapabilityMap, Level, Verdict
from ..naming import pretty, pretty_capability
from ._brand import favicon, logo, scope_url
from .explain import describe

_CSS = """
*{box-sizing:border-box}
:root{
  --paper:#f4f2ec;--ink:#16181d;--muted:#6b7076;--faint:#9aa0a6;--line:#e5e2d9;--card:#fffdf8;
  --film:#0c0f14;--film2:#141b26;--accent:#7c5cff;--accent-soft:#efeafd;--accent-deep:#5a3fd6;
  --serif:Georgia,'Iowan Old Style','Times New Roman',serif;
  --sans:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
  --mono:ui-monospace,'SF Mono',Menlo,Consolas,monospace;}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.6}
.hero{background:radial-gradient(120% 130% at 85% -10%,rgba(124,92,255,.22)0,transparent 55%),
  linear-gradient(180deg,var(--film2),var(--film));color:#eef2f4;padding:34px 0 40px}
.wrap{max-width:820px;margin:0 auto;padding:0 26px}
.brandrow{display:flex;align-items:center;gap:12px}
.brand{height:30px;width:auto;flex:none}
.wordmark{font-weight:800;letter-spacing:.22em;font-size:12.5px}.wordmark b{color:var(--accent)}
.byline{color:#8892a0;font-size:12px;letter-spacing:.06em;margin-left:auto}
.byline b{color:#fff;font-weight:700}
.cta{background:var(--card);border:1px solid #d9ccff;border-top:4px solid var(--accent);border-radius:14px;
  padding:22px;margin:24px 0 6px;display:flex;gap:18px;align-items:center;flex-wrap:wrap}
.cta .ctxt{flex:1;min-width:220px}
.cta h3{font-family:var(--serif);font-weight:500;font-size:20px;margin:0 0 4px}
.cta p{margin:0;color:var(--muted);font-size:14px}
.cta a.btn{background:var(--accent-deep);color:#fff;text-decoration:none;font-weight:700;font-size:14px;
  padding:12px 20px;border-radius:10px;white-space:nowrap}
.cta a.btn:hover{background:#4a32b8}
.scope{display:inline-block;margin:10px 0 0;color:var(--accent-deep);font-size:13px;text-decoration:none;font-weight:600}
.scope:hover{text-decoration:underline}
.eyebrow{font-size:12px;letter-spacing:.32em;text-transform:uppercase;color:#b6a8ff;margin:26px 0 8px}
.hero h1{font-family:var(--serif);font-weight:500;font-size:38px;line-height:1.05;margin:0 0 6px}
.hero .sub{color:#aeb6bd;font-family:var(--mono);font-size:12.5px;margin:0 0 22px}
/* each stat is a tight number-over-label tile, so a figure reads with ITS OWN label - a flat
   row with one uniform gap spaced "352" from "capabilities mapped" the same as from the next
   number, and the grouping (and alignment) fell apart. */
.bignum{display:flex;gap:40px;align-items:flex-end;flex-wrap:wrap}
.stat{display:flex;flex-direction:column;gap:4px}
.stat b{font-size:40px;font-weight:700;letter-spacing:-.02em;line-height:1}
.stat .hi{color:var(--accent)}
.stat span{color:#9aa4ad;font-size:11.5px;letter-spacing:.09em;text-transform:uppercase}
.lead{max-width:820px;margin:26px auto 6px;padding:0 26px;font-size:16px;color:#3a3f45;line-height:1.6}
main{max-width:820px;margin:0 auto;padding:8px 26px 70px}
main.minor{padding-bottom:4px}   /* holds the merge cards; the 70px tail belongs to the last main only */
.opp{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--accent);
  border-radius:14px;padding:20px 22px;margin:14px 0;box-shadow:0 1px 2px rgba(20,22,28,.03)}
.opp.med{border-left-color:#b9a7ff}
.opp .top{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.rank{font-family:var(--serif);font-size:19px;color:var(--faint);min-width:26px}
.badge{font-size:10.5px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:var(--accent-deep);
  background:var(--accent-soft);border:1px solid #d9ccff;border-radius:6px;padding:3px 9px}
.aitag{font-size:10px;font-weight:700;letter-spacing:.04em;color:var(--muted);border:1px solid var(--line);
  border-radius:6px;padding:3px 8px;white-space:nowrap}
.aitag.find{color:var(--accent-deep);background:var(--accent-soft);border-color:#d9ccff}
.opp.med .badge{color:#6b6280;background:#f1eefb;border-color:#e5ddf7}
.oname{font-family:var(--serif);font-size:20px;font-weight:500;letter-spacing:-.01em;flex:1;min-width:200px}
.eff{font-size:11px;font-weight:700;color:var(--accent-deep);border:1px solid #d9ccff;border-radius:20px;padding:3px 10px;white-space:nowrap}
.reason{font-size:15px;color:#2c3036;margin:12px 0 0;line-height:1.55}
.agent{font-size:14px;color:var(--muted);margin:8px 0 0;line-height:1.55}
.agent b{color:var(--accent-deep)}
.caution{font-size:13px;color:#8a5a00;background:#fdf5e6;border:1px solid #f0dcb0;border-radius:8px;padding:8px 11px;margin:10px 0 0}
details{margin:12px 0 0}
details>summary{cursor:pointer;color:var(--accent-deep);font-size:13px;list-style:none}
details>summary::-webkit-details-marker{display:none}
details>summary::before{content:"+ ";font-family:var(--mono)}
details[open]>summary::before{content:"- "}
.tech{margin:10px 0 0;padding:14px 16px;background:#faf8f2;border:1px solid var(--line);border-radius:10px;font-size:13.5px}
.tech .k{color:var(--muted);font-size:12px}.tech .loc{font-family:var(--mono);font-size:12px;color:var(--muted)}
.tech ol{margin:8px 0 0;padding-left:18px}
.foot-note{max-width:820px;margin:8px auto 0;padding:16px 26px;color:var(--muted);font-size:13.5px;
  border-top:1px solid var(--line)}
.foot-note b{color:var(--ink)}
.more-h{font-family:var(--serif);color:var(--muted);font-weight:400;font-size:15px;margin:26px 2px 6px}
details.more{margin:16px 0 6px}
details.more>summary{cursor:pointer;font-family:var(--serif);font-size:16px;color:var(--muted);list-style:none;padding:6px 0}
details.more>summary::-webkit-details-marker{display:none}
details.more>summary::before{content:"+ ";font-family:var(--mono);color:var(--faint)}
details.more[open]>summary::before{content:"- "}
.morewrap{border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--card)}
.crow{display:flex;align-items:center;gap:12px;padding:11px 16px;border-top:1px solid var(--line);border-left:3px solid var(--accent);font-size:14px}
.crow:first-child{border-top:0}
.crow.med{border-left-color:#b9a7ff}
.crank{font-family:var(--serif);color:var(--faint);font-size:14px;min-width:22px}
.cbadge{font-size:10px;font-weight:800;letter-spacing:.04em;text-transform:uppercase;color:var(--accent-deep);min-width:56px}
.crow.med .cbadge{color:#7a72a0}
.cname{flex:1;font-weight:600}
.ceff{color:var(--muted);font-size:12px;white-space:nowrap}
.foot{max-width:820px;margin:0 auto;padding:22px 26px 0;color:var(--muted);font-size:12.5px}
@media(max-width:640px){.hero h1{font-size:29px}.bignum{gap:20px}}

/* THE META BAND - ported from the full report so local and web are ONE product. */
.exec{background:var(--card);border-top:1px solid var(--line);border-bottom:1px solid var(--line);
  padding:22px 0 24px;margin:22px 0 0}
.wrap2{max-width:820px;margin:0 auto;padding:0 26px}
.meter{display:flex;height:8px;border-radius:5px;overflow:hidden;background:var(--line)}
.meter i{display:block;height:100%}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin:10px 0 0;font-size:12.5px;color:var(--muted)}
.legend s{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:6px;text-decoration:none}
.legend b{color:var(--ink);font-weight:700}
.ex-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));gap:14px;margin:18px 0 0}
.ex-card{background:#faf8f2;border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.ex-card.do{border-left:3px solid var(--accent)}
.ex-card.wait{border-left:3px solid #9aa0a6}
.ex-card.cov{border-left:3px solid #3f8f7a}
.ex-card h3{font-family:var(--serif);font-weight:500;font-size:16px;margin:0}
.ex-sub{color:var(--faint);font-size:11.5px;margin:2px 0 9px;text-transform:uppercase;letter-spacing:.06em}
.ex-card ul{margin:0;padding-left:16px;font-size:13.5px;color:#2c3036;line-height:1.5}
.ex-card li{margin:0 0 5px}
.ex-card b{color:var(--accent-deep)}
.covbody{margin:0;font-size:13.5px;color:#2c3036;line-height:1.6}
.gapline{color:#8a5a00;font-size:12.5px}

/* THE PLAN - the loud part. This is the thing a chat window cannot produce. */
.plan{max-width:820px;margin:-20px auto 0;padding:0 26px}
.planbox{background:var(--card);border:1px solid #d9ccff;border-left:5px solid var(--accent);
  border-radius:16px;padding:26px 28px;box-shadow:0 8px 30px -18px rgba(20,22,28,.28)}
.planbox .keyline{font-family:var(--serif);font-size:26px;line-height:1.28;letter-spacing:-.01em;margin:0}
.planbox .keyline b{color:var(--accent-deep);font-weight:600}
.planbox .sub2{margin:12px 0 0;color:var(--muted);font-size:14.5px}
.phase{max-width:820px;margin:34px auto 0;padding:0 26px;display:flex;align-items:baseline;gap:12px}
.phase .pn{font-family:var(--mono);font-size:11px;letter-spacing:.18em;color:var(--accent-deep);
  background:var(--accent-soft);border:1px solid #d9ccff;border-radius:6px;padding:3px 8px;white-space:nowrap}
.phase h2{font-family:var(--serif);font-weight:500;font-size:22px;margin:0}
.phase .pd{color:var(--faint);font-size:13px;margin-left:auto;text-align:right}
/* foundation (consolidate-first) cards */
.fcard{background:#fffdf8;border:1px solid var(--line);border-left:4px solid #f0a832;border-radius:14px;
  padding:18px 20px;margin:12px 0}
.fcard .ft{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.fcard .tool{font-family:var(--mono);font-size:15px;font-weight:700;color:var(--ink)}
.fcard .cat{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:#8a5a00;
  background:#fdf5e6;border:1px solid #f0dcb0;border-radius:6px;padding:2px 8px}
.fcard .blocks{margin-left:auto;font-size:12.5px;font-weight:700;color:#b06f00}
.fcard p{margin:10px 0 0;font-size:14.5px;color:#2c3036}
.fcard .where{margin:8px 0 0;font-family:var(--mono);font-size:12.5px;color:var(--muted)}
.fcard .prov{margin:9px 0 0;font-size:12.5px;color:var(--muted);padding-top:8px;border-top:1px dashed var(--line)}
.fcard .prov b{color:var(--ink);font-weight:700}
.fcard p b{color:#b06f00;font-weight:700}
.needs{margin:10px 0 0;font-size:12.5px;color:var(--muted)}
.needs b{color:#b06f00;font-family:var(--mono)}
/* leave-alone + locked */
.quiet{max-width:820px;margin:12px auto 0;padding:16px 20px;background:#faf8f2;border:1px solid var(--line);
  border-radius:12px;color:var(--muted);font-size:14px}
.quiet b{color:var(--ink)}
.locked{max-width:820px;margin:12px auto 0;padding:18px 20px;background:#f4f6f8;border:1px dashed #c3cbd4;
  border-radius:12px;color:var(--muted);font-size:14px}
.locked b{color:var(--ink)}
.locked .u{color:var(--accent-deep);font-weight:700}

/* MERGED agents - one agent replacing N implementations. The finding a single-repo prompt
   cannot produce, so it gets the strongest card in the report. */
.mcard{background:linear-gradient(180deg,#fffdf8,#fbf9ff);border:1px solid #cbb8ff;
  border-left:5px solid var(--accent);border-radius:16px;padding:22px 24px;margin:16px 0;
  box-shadow:0 6px 24px -16px rgba(90,63,214,.45)}
.mcard .mt{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.mcard .mtag{font-size:10.5px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;
  color:#fff;background:var(--accent-deep);border-radius:6px;padding:3px 9px}
.mcard h3{font-family:var(--serif);font-size:22px;font-weight:500;margin:0;flex:1;min-width:220px}
.mcard .mloc{font-size:12px;color:var(--muted);white-space:nowrap}
.mcard .mwhy{font-size:15px;color:#2c3036;margin:12px 0 0;line-height:1.55}
.mcard .magent{font-size:14px;color:var(--muted);margin:8px 0 0}
.mcard .magent b{color:var(--accent-deep)}
.repl{margin:12px 0 0;border-top:1px dashed #ddd3f5;padding-top:10px}
.repl .rh{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
.rrow{display:flex;align-items:baseline;gap:10px;font-size:13.5px;padding:3px 0}
.rrow .rp{font-weight:700;min-width:130px}
.rrow .rf{font-family:var(--mono);font-size:12px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mcard:has(.agent-pick:checked){box-shadow:0 0 0 2px var(--accent),0 6px 24px -16px rgba(90,63,214,.45)}
.cand{font-size:12.5px;color:#8a5a00;background:#fdf5e6;border:1px solid #f0dcb0;
  border-radius:8px;padding:8px 11px;margin:10px 0 0}

/* interactive (hosted) selection */
.pick{display:inline-flex;align-items:center;gap:9px;margin:12px 0 0;cursor:pointer;
  font-size:13.5px;font-weight:600;color:var(--accent-deep);user-select:none}
.pick input{width:17px;height:17px;accent-color:var(--accent);cursor:pointer;margin:0}
.opp:has(.agent-pick:checked){border-left-color:var(--accent);background:#fbfaff;
  box-shadow:0 0 0 1px var(--accent-soft)}
.bar{position:fixed;left:0;right:0;bottom:0;z-index:20;background:rgba(12,15,20,.97);
  border-top:1px solid #2a3340;padding:14px 20px;display:none;align-items:center;gap:16px;
  justify-content:center;color:#eef2f4;flex-wrap:wrap}
.bar.on{display:flex}
.bar .cnt{font-size:14px}.bar .cnt b{color:#b6a8ff;font-size:16px}
.bar button{background:var(--accent);color:#fff;border:0;border-radius:10px;padding:12px 24px;
  font:inherit;font-weight:700;font-size:15px;cursor:pointer}
.bar button:hover:not(:disabled){background:#6a49f5}
.bar button:disabled{opacity:.6;cursor:default}
.bar .clr{background:none;color:#8892a0;font-weight:600;font-size:13px;padding:6px 4px}
.bar .clr:hover{color:#fff;background:none}
main.interactive{padding-bottom:110px}
.value{font-size:13.5px;color:#3a3f47;margin:8px 0 0;line-height:1.55}
.value b{color:#5a3fd6}
.opp.twin{border-left-color:#3f8f7a}
.badge.tw{color:#2f6d5e;background:#e6f2ee;border-color:#bfe0d6}
.aitag.tw{color:#2f6d5e;background:#e6f2ee;border-color:#bfe0d6}
.scope-note{display:block;margin-top:8px;padding-top:8px;border-top:1px dashed var(--line);font-size:12px;color:var(--muted);font-style:italic}
.value.demand b{color:#1f6feb}
"""


# --------------------------------------------------------------------------------------
# The meta band - "we mapped everything, here is the whole picture, and here is what we
# could NOT read".
#
# This is ported from report/render.py, and the port is the point: there were TWO renderers
# (render.py = the full report with this band; agentify_view.py = the Transformation Plan),
# so a local CLI scan and the hosted web scan produced DIFFERENT PRODUCTS. That is the same
# fork we refuse to allow in the engine, sitting in the report layer. One report, two front
# doors. Header from the full report, body (agent cards + CTA) from this one.
#
# It also gives the coverage firewall somewhere to land: unread code is UNDECIDED, so it
# flows into "awaiting data", and the Coverage card names the file types we could not parse.
# --------------------------------------------------------------------------------------

_VERDICT_LABEL = {
    Verdict.KEEP: ("Keep", "#6b7076"),
    Verdict.AGENTIFY: ("Agentify", "#7c5cff"),
    Verdict.CONSOLIDATE: ("Consolidate", "#f0a832"),
    Verdict.RETIRE: ("Retire", "#c2564b"),
    Verdict.BUY_REPLACE: ("Buy / Replace", "#3f8f7a"),
    Verdict.UNDECIDED: ("Not assessed", "#9aa0a6"),
}
_ACTIONABLE = (Verdict.RETIRE, Verdict.CONSOLIDATE, Verdict.AGENTIFY, Verdict.BUY_REPLACE)


def _counts(caps) -> dict:
    out = {v: 0 for v in _VERDICT_LABEL}
    for c in caps:
        out[c.verdict] = out.get(c.verdict, 0) + 1
    return out


def _meter(caps, counts) -> str:
    total = max(1, len(caps))
    segs, legend = [], []
    for v, (label, colour) in _VERDICT_LABEL.items():
        n = counts.get(v, 0)
        if not n:
            continue
        segs.append(f'<i style="width:{n / total * 100:.3f}%;background:{colour}" '
                    f'title="{label}: {n}"></i>')
        legend.append(f'<span><s style="background:{colour}"></s>{label} <b>{n}</b></span>')
    return f'<div class="meter">{"".join(segs)}</div><div class="legend">{"".join(legend)}</div>'


def _meta_band(cmap: CapabilityMap, caps, opps, plan, twins=(), work_stats=None) -> str:
    """Actionable now / To unlock more / Coverage - the proof that we looked at everything."""
    counts = _counts(caps)
    unread = [c for c in caps if not getattr(c, "readable", True)]
    # UNDECIDED used to mean "no runtime data, so we cannot say keep-or-retire" - the old wall
    # of grey. That is gone: KEEP is now assertible from code alone. Today the ONLY thing that
    # leaves a capability undecided is that we had no parser for it. So the label is "not
    # assessed", not "awaiting data" - nothing is waiting on the customer, it is waiting on us.
    n_unassessed = counts.get(Verdict.UNDECIDED, 0)

    # --- actionable now: findings that need no runtime data --------------------------
    items = []
    if plan is not None and getattr(plan, "merge", None):
        n = sum(len(c.members) for c in plan.merge)
        items.append(f"<b>{len(plan.merge)}</b> merged agent(s) replacing <b>{n}</b> separate "
                     f"implementations of the same job")
    if opps:
        items.append(f"<b>{len(opps)}</b> candidates to rebuild as AI agents")
    if twins:
        items.append(f"<b>{len(twins)}</b> capabilities better suited to a digital twin "
                     f"(a system to model - physical or business) than to an agent")
    if counts.get(Verdict.CONSOLIDATE):
        items.append(f"<b>{counts[Verdict.CONSOLIDATE]}</b> redundant capabilities to consolidate")
    if counts.get(Verdict.BUY_REPLACE):
        items.append(f"<b>{counts[Verdict.BUY_REPLACE]}</b> commodity capabilities to buy rather "
                     f"than maintain")
    if counts.get(Verdict.RETIRE):
        items.append(f"<b>{counts[Verdict.RETIRE]}</b> candidate(s) for decommission "
                     f"(zero traffic in the logs)")
    actionable_html = "".join(f"<li>{i}</li>" for i in items) or \
        "<li>Nothing actionable surfaced from the code alone. That is a result, not an error.</li>"

    # --- to unlock more: the honest next steps. The parser-gap line leads with its own count,
    # so there is no separate "N not assessed" header sitting over an unrelated access-log line.
    cap_word = "capability" if n_unassessed == 1 else "capabilities"
    unlocks = []
    if plan is not None and getattr(plan, "retire_locked", False):
        unlocks.append("Add <b>30+ days of access logs</b> to see what gets zero traffic - the "
                       "only safe way to retire something (code on its own cannot prove a "
                       "capability is unused).")
    if unread:
        gap = ", ".join(sorted({c.name.split(": ", 1)[-1].split(" ")[0] for c in unread}))
        unlocks.append(f"<b>{n_unassessed} {cap_word} not assessed</b> - we have no parser for "
                       f"{_esc(gap)} yet. Tell us the stack and we will add it.")
    # `origin` defaults to the truthy string "heuristic", so `any(origin)` is true for every
    # non-empty list - the old guard could never fire. The honest question is simply: did ANY
    # candidate actually get code-read by the model?
    if opps and not any(o.origin in ("ai-validated", "ai-found") for o in opps):
        unlocks.append("Add an <b>AI key</b> so every candidate is read and checked against the "
                       "actual code, not just matched on names.")
    unlock_html = "".join(f"<li>{u}</li>" for u in unlocks) or \
        "<li>Nothing pending - this is everything the code can tell us.</li>"

    # --- coverage: what we read, in plain English. The kind breakdown ("Built N ·
    # Integrated-SaaS 0") was jargon and showed a meaningless 0 - dropped. SaaS lines appear
    # only when there is something to say.
    kinds: dict[str, int] = {}
    for c in caps:
        kinds[c.kind.value] = kinds.get(c.kind.value, 0) + 1
    n_prod = len(cmap.by_level(Level.PRODUCT))
    integrated = kinds.get("integrated-SaaS", 0)
    bought = kinds.get("bought-SaaS", 0)
    cov = f"<b>{n_prod}</b> products, <b>{len(caps)}</b> capabilities found in your code."
    if integrated:
        cov += (f"<br>Plus <b>{integrated}</b> third-party service"
                f"{'s' if integrated != 1 else ''} you have wired in (Stripe, Twilio, and the like).")
    if bought:
        cov += f"<br>Plus <b>{bought}</b> bought SaaS tool{'s' if bought != 1 else ''}."
    if unread:
        names = ", ".join(sorted({c.name.split(": ", 1)[-1].replace(" (not read)", "")
                                  .replace(" (not yet extracted)", "") for c in unread}))
        cov += f'<br><span class="gapline">Not read yet: {_esc(names)}</span>'
    # The work-exhaust stream, when provided. Its OWN sentence with its own verb ("we also
    # read..."), because "Plus 6 work items" next to "119 capabilities" read as if the two
    # numbers added up (Krishna misread it exactly that way). Tickets are a separate stream
    # laid OVER the map, and the copy must say so.
    if work_stats is not None and getattr(work_stats, "total", 0):
        w = work_stats
        win = f" ({_esc(w.window)})" if w.window else ""
        cov += (f"<br>We also read <b>{w.total:,}</b> tickets from your {_esc(w.source)}{win} - "
                f"these are work items, not capabilities. <b>{w.matched:,}</b> of them are about "
                f"the capabilities above")
        if w.unmatched:
            cov += (f"; <b>{w.unmatched:,}</b> "
                    f"{'matches' if w.unmatched == 1 else 'match'} none of them - work with "
                    f"no code behind it")
        cov += "."
    # Honesty line: a code scan sees only what is IN the code. Much of the real opportunity -
    # judgement, coordination, decisions - is human knowledge work that was never coded, and no
    # code scan can see it. Say so, so the scan is never mistaken for the whole picture.
    cov += ('<br><span class="scope-note">This maps what is in your code'
            + (' and your ticket stream' if work_stats is not None and getattr(work_stats, "total", 0) else '')
            + '. A lot of knowledge work '
            '- judgement, coordination, decisions - lives outside code, and a code scan cannot '
            'see it.</span>')

    return f'''<section class="exec"><div class="wrap2">
  {_meter(caps, counts)}
  <div class="ex-grid">
    <div class="ex-card cov"><h3>Coverage</h3>
      <p class="ex-sub">What we read</p><p class="covbody">{cov}</p></div>
    <div class="ex-card do"><h3>Actionable now</h3>
      <p class="ex-sub">No extra data needed</p><ul>{actionable_html}</ul></div>
    <div class="ex-card wait"><h3>To unlock more</h3>
      <ul>{unlock_html}</ul></div>
  </div>
</div></section>'''


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _js_str(s: str) -> str:
    """JSON-encode a value for embedding inside a <script>, closing the </script> escape."""
    return json.dumps(str(s or "")).replace("</", "<\\/")


def _scope_prompt(app: str, opps: list[Opportunity], cap: int = 8) -> str:
    """Compose the problem statement handed to AiDOOS so it can scope a real proposal.

    Not a generic slug: it names the ranked capabilities the scan surfaced (with potential
    and effort), so the Instant Proposal on aidoos.com estimates against actual scope.
    """
    top = opps[:cap]
    lines = [f"{i}. {o.title.replace(': ', ' - ')} "
             f"({o.potential} potential, effort {o.effort})"
             for i, o in enumerate(top, 1)]
    more = f"\n(+ {len(opps) - cap} more in the StackXray report)" if len(opps) > cap else ""
    return (f"We ran StackXray on our {app} codebase and want to rebuild these capabilities "
            f"as AI agents. Please scope an engagement (effort, timeline, proposal):\n"
            + "\n".join(lines) + more)


def _pick(opp: Opportunity, interactive: bool) -> str:
    """A checkbox that marks this capability for the proposal (hosted report only).

    StackXray does NOT price the work. The selection is handed to AiDOOS's Proposal engine,
    which owns DU/cost/timeline (ModuleBreakdownAgent + the calibration app + the tier bands).
    A second estimator here would eventually contradict it - two prices from one company.
    """
    if not interactive:
        return ""
    name = _esc(opp.title)
    return (f'<label class="pick"><input type="checkbox" class="agent-pick" value="{name}" '
            f'data-effort="{_esc(opp.effort)}" data-potential="{_esc(opp.potential)}">'
            f'<span>Build this agent</span></label>')


def _foundation_card(f) -> str:
    """A shared tool wired up separately in several products.

    Deliberately does NOT say "blocks N agents": nothing is blocked - you can build the agents
    without consolidating, you just end up with more copies. We state the arithmetic instead,
    and we separate what we DETECTED in the code from what we INFERRED.
    """
    n = len(f.blocks)
    tag = (f'<span class="blocks">{n} agent{"" if n == 1 else "s"} will land on this</span>'
           if n else '<span class="blocks" style="color:#9aa0a6">no agents land on this</span>')
    if n:
        # NOT a separate project you run before any agents. Nobody does that. The realistic
        # move: the FIRST agent establishes the shared client, the other agents reuse it, and
        # migrating the existing call sites is a schedulable cleanup.
        body = (f"You wire this up <b>{len(f.products)} times</b> today. Build the {n} agent"
                f"{'' if n == 1 else 's'} in Step 2 without a shared client and you end up with "
                f"<b>{f.after}</b>. This is not a separate project: have the <b>first agent "
                f"stand up one shared {f.tool} client</b>, let the other {max(0, n - 1)} reuse it, "
                f"then migrate the {len(f.products)} existing call sites as cleanup.")
    else:
        body = (f"{len(f.products)} products each wired this up independently. Worth consolidating, "
                f"but no agent lands on it - so it is not urgent.")

    prov = []
    if f.detected:
        prov.append(f"<b>{len(f.detected)} detected</b> - already imports it in the code")
    if f.inferred:
        prov.append(f"<b>{len(f.inferred)} inferred</b> - will need "
                    f"{'a model once it becomes an agent' if f.category == 'LLM' else 'it once built'}")
    prov_line = (f'<div class="prov">{" &middot; ".join(prov)}</div>') if prov else ""

    return f'''<div class="fcard">
  <div class="ft"><span class="tool">{_esc(f.tool)}</span>
    <span class="cat">{_esc(f.category)}</span>{tag}</div>
  <p>{body}</p>
  {prov_line}
  <div class="where">integrated separately in: {_esc(", ".join(f.products))}</div>
</div>'''


def _merge_card(c, interactive: bool) -> str:
    """One agent replacing N separate implementations of the same job.

    The honesty rule: an AI-confirmed cluster states the merge; an unconfirmed one is labelled
    a CANDIDATE and tells the reader exactly what we did and did not check. We never quietly
    present a keyword match as a verified finding - merging three working systems on a shared
    noun would be real damage.
    """
    rows = "".join(
        f'<div class="rrow"><span class="rp">{_esc(m.product)}</span>'
        f'<span class="rf">{_esc(m.locator.replace(chr(92), "/"))}</span>'
        f'<span class="mloc">{m.loc:,} LOC</span></div>'
        for m in c.members)
    n = len(c.members)
    allof = "both" if n == 2 else f"all {n}"
    if c.confirmed:
        badge = '<span class="mtag">&#10003; AI-confirmed merge</span>'
        caveat = ""
        # Confirmed: a model read code from each member and said these are the same job.
        why = c.reason or (
            f"{n} products each carry their own {c.label} implementation, and they do the same "
            f"work. Built once as an agent, it serves {allof}.")
    else:
        badge = '<span class="mtag" style="background:#8a7bbf">candidate merge</span>'
        caveat = ('<div class="cand">We matched these on what the code is <i>named</i> and how '
                  'it is shaped, not on reading every line. Confirm they are really the same job '
                  'before merging - add an AI key and we will read the code and check.</div>')
        # Unconfirmed: state what we SAW (n separate implementations of a same-named job) and
        # make the merge conditional. The old default asserted "same input, same rules, same
        # decision" - a claim the caveat immediately below it retracts. Saying it and then
        # taking it back is worse than not saying it.
        why = c.reason or (
            f"{n} products each carry their own {c.label} implementation, built separately. "
            f"If they are doing the same job, one agent serves {allof} - and that is the "
            f"question to settle first.")
    agent = c.agent_summary or (
        f"A single {c.label} agent, called by {allof} modules, replacing {c.loc:,} lines of "
        f"separately-maintained logic.")
    pick = ""
    if interactive:
        pick = (f'<label class="pick"><input type="checkbox" class="agent-pick" '
                f'value="{_esc("Unified " + c.label + " agent")}" data-effort="L" '
                f'data-potential="high" data-replaces="{_esc(", ".join(c.products))}">'
                f'<span>Build this agent</span></label>')
    return f'''<div class="mcard">
  <div class="mt">{badge}<h3>One {_esc(c.label)} agent</h3>
    <span class="mloc">replaces {n} implementations &middot; {c.loc:,} LOC</span></div>
  <p class="mwhy">{_esc(why)}</p>
  <p class="magent"><b>What the one agent would do:</b> {_esc(agent)}</p>
  <div class="repl"><div class="rh">It replaces</div>{rows}</div>
  {caveat}
  {pick}
</div>'''


def _card(opp: Opportunity, rank: int, interactive: bool = False,
          prereqs: tuple = ()) -> str:
    cap = opp.capability
    sc = draft_scope(cap)
    steps = "".join(f"<li>{_esc(s)}</li>" for s in sc["steps"])
    deps = f'<div class="k">Integrates: {_esc(", ".join(cap.dependencies))}</div>' if cap.dependencies else ""
    loc = ""
    for e in cap.evidence:
        if e.source == "extract" and e.locator:
            loc = f'<div class="loc">{_esc(e.locator)}</div>'
            break
    caution = f'<div class="caution">⚠ {_esc(opp.caution)}</div>' if opp.caution else ""
    med = " med" if opp.potential == "medium" else ""
    origin = ""
    if opp.origin == "ai-found":
        origin = '<span class="aitag find">AI-surfaced</span>'
    elif opp.origin == "ai-validated":
        origin = '<span class="aitag">&#10003; AI-checked</span>'
    return f'''<div class="opp{med}">
  <div class="top"><span class="rank">{rank:02d}</span>
    <span class="badge">{_esc(opp.potential)} potential</span>{origin}
    <span class="oname">{_esc(pretty_capability(cap.name).replace(": ", " - "))}</span>
    <span class="eff">effort {_esc(opp.effort)}</span></div>
  <p class="reason">{_esc(opp.reason)}</p>
  {f'<p class="agent"><b>What an agent would do:</b> {_esc(opp.agent_summary)}</p>' if opp.agent_summary else ''}
  {f'<p class="value"><b>What it means:</b> {_esc(opp.value)}</p>' if getattr(opp, "value", "") else ''}
  {f'<p class="value demand"><b>Observed demand:</b> {_esc(opp.demand)}</p>' if getattr(opp, "demand", "") else ''}
  {f'<p class="needs">Stands on: <b>{_esc(", ".join(prereqs))}</b> - consolidate those first (Step 1).</p>' if prereqs else ''}
  {caution}
  <details><summary>Technical detail</summary>
    <div class="tech">{_esc(describe(cap))}{deps}{loc}
      <div class="k" style="margin-top:8px">What it would take - {_esc(sc["action"])}:</div>
      <ol>{steps}</ol></div></details>
  {_pick(opp, interactive) if interactive else
   f'<a class="scope" href="{_esc(scope_url("Rebuild our " + cap.name + " capability as an AI agent"))}"'
   f' target="_blank" rel="noopener">Scope this with AiDOOS &rarr;</a>'}
</div>'''


def _twin_card(t, rank: int) -> str:
    """A digital-twin candidate. Same card shape as an agent, a different verdict: model the
    process, don't automate the decision away."""
    cap = t.capability
    loc = ""
    for e in cap.evidence:
        if e.source == "extract" and e.locator:
            loc = f'<div class="tech"><div class="loc">{_esc(e.locator)}</div></div>'
            break
    kindlabel = "physical system" if t.twin_kind == "physical" else "decision system"
    return f'''<div class="opp twin">
  <div class="top"><span class="rank">{rank:02d}</span>
    <span class="badge tw">digital twin</span><span class="aitag tw">{kindlabel}</span>
    <span class="oname">{_esc(t.title.replace(": ", " - "))}</span>
    <span class="eff">effort {_esc(t.effort)}</span></div>
  <p class="reason">{_esc(t.summary)}</p>
  <p class="value"><b>How it helps:</b> {_esc(t.value)}</p>
  {loc}
</div>'''


def _twins_section(twins) -> str:
    """The digital-twin lens - the complement to the agent list. Physical/operational work and
    human-decision points, where a live model beats automating the choice away."""
    if not twins:
        return ""
    cards = "".join(_twin_card(t, i + 1) for i, t in enumerate(twins[:6]))
    more = ""
    if len(twins) > 6:
        rows = "".join(
            f'<div class="crow"><span class="crank">{i + 7:02d}</span>'
            f'<span class="cbadge">twin</span>'
            f'<span class="cname">{_esc(t.title.replace(": ", " - "))}</span>'
            f'<span class="ceff">effort {_esc(t.effort)}</span></div>'
            for i, t in enumerate(twins[6:]))
        more = (f'<details class="more"><summary>{len(twins) - 6} more twin candidates</summary>'
                f'<div class="morewrap">{rows}</div></details>')
    lead = (f"<b style=\"color:#2f6d5e\">{len(twins)}</b> capabilities fit a <b>digital twin</b> "
            "rather than an agent: a live model of a system - physical operations, or a business "
            "system worth simulating - that you monitor, run what-if on, and make the higher-level "
            "calls against. An agent runs the transactions; a twin models the system they move.")
    return f'''<div class="phase"><span class="pn" style="color:#2f6d5e;background:#e6f2ee;border-color:#bfe0d6">TWINS</span>
  <h2>Digital-twin opportunities</h2><span class="pd">model it, don't just automate it</span></div>
<p class="lead">{lead}</p>
<main>{cards}{more}</main>'''


def _compact_row(opp: Opportunity, rank: int) -> str:
    med = " med" if opp.potential == "medium" else ""
    return (f'<div class="crow{med}"><span class="crank">{rank:02d}</span>'
            f'<span class="cbadge">{_esc(opp.potential)}</span>'
            f'<span class="cname">{_esc(opp.title.replace(": ", " - "))}</span>'
            f'<span class="ceff">effort {_esc(opp.effort)}</span></div>')


_BAR_JS = """
(function(){
  var bar=document.getElementById('bar'), cnt=document.getElementById('cnt'),
      go=document.getElementById('build'), clr=document.getElementById('clr');
  function picks(){return [].slice.call(document.querySelectorAll('.agent-pick:checked'));}
  // No price here on purpose. StackXray reports; AiDOOS's Proposal engine prices. The
  // selection is handed to it, and it returns the DU / cost / timeline.
  function sync(){
    var n=picks().length;
    bar.classList.toggle('on', n>0);
    cnt.innerHTML='<b>'+n+'</b> agent'+(n===1?'':'s')+' selected';
  }
  document.addEventListener('change',function(e){
    if(e.target && e.target.classList.contains('agent-pick')) sync();
  });
  clr.addEventListener('click',function(){
    picks().forEach(function(c){c.checked=false;}); sync();
  });
  go.addEventListener('click',function(){
    var sel=picks().map(function(c){return c.value;});
    if(!sel.length) return;
    go.disabled=true; go.textContent='Preparing your proposal...';
    fetch(PROPOSAL_URL,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({capabilities:sel})})
      .then(function(r){return r.json();})
      .then(function(j){
        if(j.redirect_url){window.location=j.redirect_url;return;}
        go.disabled=false; go.textContent='Build these agents';
        alert(j.detail||'Could not start the proposal.');
      })
      .catch(function(){go.disabled=false;go.textContent='Build these agents';
        alert('Could not reach the server.');});
  });
})();
"""


def _plan_blocks(plan, opps, interactive: bool) -> tuple[str, str, str]:
    """The four phases. Returns (headline_html, phase1_html, phase_rest_html)."""
    if plan is None:
        return "", "", ""

    # --- the loud part: one sentence only a portfolio view can say ---------------------
    key = _esc(plan.headline())
    for frag in (f"{len(plan.build)} AI agents", f"{plan.existing_llm_clients} separate times",
                 f"finish with {plan.existing_llm_clients + len(plan.build)}"):
        key = key.replace(_esc(frag), f"<b>{_esc(frag)}</b>")
    head = (f'<div class="plan"><div class="planbox"><p class="keyline">{key}</p>'
            f'<p class="sub2">A plan, not a list: the order matters. '
            f'{plan.total} capabilities mapped from the code.</p></div>'
            f'</div>')

    # --- Phase 1: foundations (only those the agents actually stand on lead) -----------
    blocking = [f for f in plan.foundation if f.blocks]
    idle = [f for f in plan.foundation if not f.blocks]
    if blocking:
        cards = "".join(_foundation_card(f) for f in blocking)
        extra = ""
        if idle:
            rows = "".join(
                f'<div class="crow"><span class="cname">{_esc(f.tool)}</span>'
                f'<span class="ceff">{len(f.products)} products &middot; no agents on it</span></div>'
                for f in idle)
            extra = (f'<details class="more"><summary>{len(idle)} more duplicated '
                     f'{"tool" if len(idle) == 1 else "tools"}, not blocking any agent</summary>'
                     f'<div class="morewrap">{rows}</div></details>')
        p1 = (f'<div class="phase"><span class="pn">STEP 1</span><h2>Consolidate the foundation</h2>'
              f'<span class="pd">fold into the first agent</span></div>'
              f'<main>{cards}{extra}</main>')
    else:
        p1 = ('<div class="phase"><span class="pn">STEP 1</span><h2>Consolidate the foundation</h2>'
              '<span class="pd">nothing to do</span></div>'
              '<div class="quiet">No shared foundation is wired up more than once. '
              '<b>Clean base - go straight to build.</b></div>')

    # --- Phases 3 & 4 (rendered after the build cards) ---------------------------------
    p3 = (f'<div class="phase"><span class="pn">STEP 3</span><h2>Leave alone</h2>'
          f'<span class="pd">no action indicated</span></div>'
          f'<div class="quiet"><b>{plan.leave}</b> capabilities need no change: not redundant, '
          f'not agent-suited, not commodity. Saying so is the point - this is a map of the whole '
          f'estate, not a list of ideas. <i>(Whether they are still USED needs runtime evidence - '
          f'see Step 4.)</i></div>')
    if plan.retire_locked:
        p4 = ('<div class="phase"><span class="pn">STEP 4</span><h2>Retire</h2>'
              '<span class="pd">locked</span></div>'
              '<div class="locked"><b>We will not guess at this one.</b> Nothing in your code '
              'proves a capability is <i>unused</i> - only runtime evidence can. Upload 30+ days '
              'of access logs and we will tell you what has had zero traffic. '
              '<span class="u">Even then we say "candidate", never "retire"</span> - a 30-day '
              'window cannot see a quarterly job.</div>')
    elif plan.retire:
        rows = "".join(
            f'<div class="crow"><span class="cname">{_esc(r.name.replace(": ", " - "))}</span>'
            f'<span class="ceff">0 requests in {r.window_days}d</span></div>'
            for r in plan.retire)
        n = len(plan.retire)
        p4 = (f'<div class="phase"><span class="pn">STEP 4</span><h2>Retire</h2>'
              f'<span class="pd">{plan.window_days} days of logs</span></div>'
              f'<div class="quiet"><b>{n} candidate{"" if n == 1 else "s"} for decommission</b> - '
              f'zero traffic across {plan.window_days} days of access logs. '
              f'<b>These are candidates, not a verdict.</b> Confirm each with its owner before '
              f'switching anything off: a {plan.window_days}-day window cannot see a month-end '
              f'close, a quarterly reconciliation, or an annual job. Absence of evidence is not '
              f'evidence of absence.</div>'
              f'<main><div class="morewrap">{rows}</div></main>')
    else:
        p4 = (f'<div class="phase"><span class="pn">STEP 4</span><h2>Retire</h2>'
              f'<span class="pd">{plan.window_days} days of logs</span></div>'
              f'<div class="quiet"><b>Nothing looks dead.</b> Every capability we could join to '
              f'a route saw traffic across {plan.window_days} days of logs. Nothing to '
              f'decommission - which is a real result, not an empty one.</div>')
    return head, p1, (p3 + p4)


def render_agentify(cmap: CapabilityMap, opps: list[Opportunity], consolidate_note: str = "",
                    ai_validated: bool = False, hosted: bool = False,
                    interactive: bool = False, proposal_url: str = "", plan=None,
                    twins=None, work_stats=None) -> str:
    twins = twins or []
    high = [o for o in opps if o.potential == "high"]
    app_raw = (cmap.scan_id or "your codebase").replace("scan:", "")
    app = _esc(pretty(app_raw))        # "hrms" -> "HRMS", "erpnext" stays as the author cased it

    prereq_of = {}
    if plan is not None:
        prereq_of = {s.opportunity.title: tuple(s.prerequisites) for s in plan.build}

    # A full CARD carries a reason paragraph; a compact ROW is just name + effort. So only put
    # on a card what earns that paragraph. When the AI pass ran, that is exactly the code-READ
    # opportunities (rejudge sorts them first): every card then states something specific about
    # the code, and the name-only tail - which would otherwise repeat one identical template
    # sentence card after card - drops to the collapsed list where no reason is shown. Without a
    # key there is nothing to verify against, so the honest fallback is the top-N by score.
    _TOP = 8
    verified = [o for o in opps if o.origin in ("ai-validated", "ai-found")]
    if ai_validated and verified:
        cut = min(len(verified), 12)
        rest_label = f"{len(opps) - cut} more, flagged by name (not code-verified)"
    else:
        cut = _TOP
        rest_label = f"{max(0, len(opps) - cut)} more opportunities"
    primary = opps[:cut]
    rest = opps[cut:]
    primary_cards = "".join(
        _card(o, i + 1, interactive, prereq_of.get(o.title, ()))
        for i, o in enumerate(primary))
    rest_block = ""
    if rest:
        rows = "".join(_compact_row(o, cut + i + 1) for i, o in enumerate(rest))
        rest_block = (f'<details class="more"><summary>{rest_label}</summary>'
                      f'<div class="morewrap">{rows}</div></details>')

    plan_head, phase1, phase_rest = _plan_blocks(plan, opps, interactive)

    # The meta band: header from the full report, body (cards + CTA) from this one. It sits
    # UNDER the headline on purpose - the duplication line is the loud part and must land
    # first; the band is then the proof that we looked at the whole estate, not a slice.
    all_caps = cmap.by_level(Level.CAPABILITY)
    n_products = len(cmap.by_level(Level.PRODUCT))
    n_awaiting = sum(1 for c in all_caps if c.verdict == Verdict.UNDECIDED)
    meta_band = _meta_band(cmap, all_caps, opps, plan, twins, work_stats) if all_caps else ""

    # Merged agents lead Step 2: they retire the most code per agent built, and they are the one
    # finding a per-repo prompt cannot reach - it is a claim about the relationship BETWEEN
    # modules, visible only if you looked at all of them at once.
    merges = list(getattr(plan, "merge", []) or []) if plan else []
    merge_cards = "".join(_merge_card(c, interactive) for c in merges)
    merge_lead = ""
    if merges:
        replaced = sum(len(c.members) for c in merges)
        merge_lead = (f'<p class="lead">Start here. <b>{len(merges)}</b> '
                      f'{"agent replaces" if len(merges) == 1 else "agents replace"} '
                      f'<b>{replaced}</b> separate implementations of the same job, spread across '
                      f'your modules. Each is built once and retires everything under it.</p>')

    if opps:
        lead = (f"<b>{len(opps)}</b> capabilities are strong candidates to rebuild as AI agents: "
                f"repetitive, rules-driven work an agent could own. "
                + (f"<b>{len(high)}</b> are high-potential. " if high else ""))
        if merges:
            lead = ("Then the single-module agents. " + lead
                    + "These sit inside one module each, so they replace one implementation, "
                      "not several. ")
    else:
        lead = ("No strong agent candidates surfaced from the code alone: mostly data models, thin "
                "API layers, or already-AI. That's an honest signal, not a miss.")
    if ai_validated:
        found = sum(1 for o in opps if o.origin == "ai-found")
        lead += (" Each candidate was <b>read and validated against the actual code</b> by your "
                 "own AI model"
                 + (f", which also surfaced {found} the name-based scan missed." if found
                    else " (not just matched on names)."))
    if work_stats is not None and getattr(work_stats, "reranked", False):
        lead += (" <b>Ranking reflects your ticket volume:</b> candidates carrying real, "
                 "measured workload from your tracker rise.")
    lead = lead.replace("<b>", '<b style="color:#5a3fd6">')

    note = f'<div class="foot-note">{consolidate_note}</div>' if consolidate_note else ""

    if interactive:
        # Hosted: the reader picks the agents, and AiDOOS proposes on exactly those.
        if opps:
            lead += (" Tick the agents you want built, then get a proposal for that "
                     "scope.")
        cta = ""
        bar = ('<div class="bar" id="bar"><span class="cnt" id="cnt"></span>'
               '<button id="build">Build these agents</button>'
               '<button class="clr" id="clr">Clear</button></div>')
        script = (f'<script>var PROPOSAL_URL={_js_str(proposal_url)};{_BAR_JS}</script>')
    else:
        cta = f'''<div class="cta">
    <div class="ctxt"><h3>Want to make these real?</h3>
      <p>AiDOOS scopes and builds the agents - get the effort, timeline, and a proposal for
      any opportunity above.</p></div>
    <a class="btn" href="{_esc(scope_url(_scope_prompt(app_raw, opps)))}" target="_blank" rel="noopener">Scope with AiDOOS &rarr;</a>
  </div>'''
        bar = script = ""

    # The trust claim must match where the scan actually ran. The local tool can honestly say
    # the code never left; the hosted tool cannot, and says what it does instead.
    if hosted:
        subline = "where to go AI-native &middot; scanned in an isolated sandbox"
        footline = ("Generated by StackXray on AiDOOS. Your code was parsed, never executed, "
                    "and deleted as soon as this report was produced. We never train on it.")
    else:
        subline = "where to go AI-native &middot; local scan &middot; nothing left this environment"
        footline = "Generated locally by StackXray. Your code never left this environment."

    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>StackXray {"Transformation Plan" if plan else "Agentify Opportunities"} - {app}</title>{favicon()}<style>{_CSS}</style></head><body>
<header class="hero"><div class="wrap">
  <div class="brandrow">{logo()}<div class="wordmark">STACK<b>XRAY</b></div>
    <div class="byline">by <b>AiDOOS</b></div></div>
  <p class="eyebrow">{"Transformation Plan" if plan else "Agentify Opportunities"}</p>
  <h1>{app}</h1>
  <p class="sub">{subline}</p>
  <div class="bignum">
    <div class="stat"><b>{n_products}</b><span>products</span></div>
    {f'<div class="stat"><b>{plan.total}</b><span>capabilities</span></div>' if plan else ''}
    <div class="stat"><b class="hi">{len(opps) + len(merges)}</b><span>agents to build</span></div>
    {f'<div class="stat"><b>{sum(len(c.members) for c in merges)}</b><span>duplicate implementations found</span></div>' if merges else (f'<div class="stat"><b>{n_awaiting}</b><span>not assessed</span></div>')}</div>
</div></header>
{plan_head}
{meta_band}
{phase1}
<div class="phase"><span class="pn">STEP 2</span><h2>Build the agents</h2>
  <span class="pd">{f"{len(merges)} replace duplicated work" if merges else ("after Step 1 lands" if plan and any(f.blocks for f in plan.foundation) else "ready to start")}</span></div>
{f'{merge_lead}<main class="minor">{merge_cards}</main>' if merges else ''}
<p class="lead">{lead}</p>
<main class="{'interactive' if interactive else ''}">
  {primary_cards}
  {rest_block}
</main>
{_twins_section(twins)}
{phase_rest}
<main class="{'interactive' if interactive else ''}">
  {cta}
  {note}
  <p class="foot">{footline}
  Candidates are ranked from the code; connecting runtime usage later re-ranks them by real value.</p>
</main>{bar}{script}</body></html>'''
