"""V1 flow - Agentify Opportunities from a path, zero dependencies, no server.

extract capabilities -> assess agent candidates -> write a clean HTML report -> open it.
Deliberately avoids the deploy/runtime/consumption tiers (and their pyyaml dependency),
so V1 is pure standard library: install Python, run one command, the report opens.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile

from .config import LLMConfig, ScanConfig

_GIT_URL = re.compile(r"^(https?://(github|gitlab|bitbucket)\.|git@|https?://\S+\.git$)", re.I)


def is_git_url(source: str) -> bool:
    return bool(_GIT_URL.match((source or "").strip()))


def _repo_name(url: str) -> str:
    return re.sub(r"\.git$", "", url.rstrip("/").rsplit("/", 1)[-1]) or "repo"


def resolve_source(source: str) -> tuple[str, str | None]:
    """Return (local_path, cleanup_dir). If `source` is a Git URL, clone it locally (shallow)
    so the code is read on THIS machine, never uploaded. Otherwise treat it as a folder."""
    source = (source or "").strip().strip('"')
    if os.path.isdir(source):
        return source, None
    if is_git_url(source):
        tmp = tempfile.mkdtemp(prefix="stackxray-")
        try:
            subprocess.run(["git", "clone", "--depth", "1", source, tmp],
                           check=True, capture_output=True, timeout=600)
        except FileNotFoundError:
            shutil.rmtree(tmp, ignore_errors=True)
            raise ValueError("Git is not installed. Install Git, or download the repo as a "
                             "folder and point at that folder instead.")
        except subprocess.CalledProcessError as e:
            shutil.rmtree(tmp, ignore_errors=True)
            tail = (e.stderr.decode(errors="replace")[-160:] if e.stderr else "")
            raise ValueError(f"Could not clone that repo (check the URL / access). {tail}")
        except subprocess.TimeoutExpired:
            shutil.rmtree(tmp, ignore_errors=True)
            raise ValueError("Cloning timed out. For a very large repo, download it and point "
                             "at the folder instead.")
        return tmp, tmp
    raise ValueError(f"Not a folder or a Git URL: {source}")


def _consolidate_note(capabilities) -> str:
    """A single-line footnote: redundant integrations worth consolidating (secondary to
    the Agentify headline). Reuses the redundancy analysis; no pyyaml."""
    from .models import Verdict
    from .verdict.clustering import analyze_portfolio
    cats = []
    for tag in analyze_portfolio(capabilities).values():
        if tag.verdict == Verdict.CONSOLIDATE and tag.cluster_id:
            cat = tag.cluster_id.split(":")[1] if ":" in tag.cluster_id else "group"
            if cat not in cats:
                cats.append(cat)
    if not cats:
        return ""
    plural = "y" if len(cats) == 1 else "ies"
    return (f"<b>Also worth a look:</b> redundant integrations in {len(cats)} categor{plural} "
            f"({', '.join(cats)}) - consolidation candidates, in the full rationalization view.")


class MissingKeyError(RuntimeError):
    """Raised when the local tool is run without an LLM key.

    The local bundle CANNOT ship the AiDOOS key (it would be extracted and run up our bill), and
    it must not phone home for the AI pass (that would send code excerpts out, breaking the whole
    "your code never left this environment" promise that is the reason to run locally). So local
    requires the customer's own key. Without it the scan would fall back to name-only heuristics -
    the identical-template output we already rejected - so we refuse rather than hand back a
    worse report with our name on it.
    """


def build_report_html(source: str, llm: LLMConfig | None = None,
                      require_key: bool = True, tickets_path: str | None = None) -> str:
    """Run the V1 Agentify scan and return the report HTML. `source` is a folder path OR a
    Git URL (cloned locally). No file written.

    `require_key` is the LOCAL-TOOL policy (see MissingKeyError) - the engine itself can render
    heuristic-only, which is what the hosted free tier falls back to when tokens run out, so the
    gate is a choice of the local entry point, not an engine invariant.
    """
    from . import agentify
    from .agentify.rejudge import rejudge           # read the code, validate + recover (key)
    from .extract import extract_capabilities
    from .llm_client import available, probe, provider_from_env
    from .report.agentify_view import render_agentify

    if require_key and not available():
        raise MissingKeyError(
            "StackXray needs an AI key to read your code and give specific, validated findings.\n"
            "  - Anthropic: put ANTHROPIC_API_KEY=sk-ant-... in API-KEY.txt (next to this tool),\n"
            "               or set it as an environment variable.\n"
            "  - OpenAI:    OPENAI_API_KEY=sk-... the same way.\n"
            "Your key and your code stay on this machine - nothing is sent to AiDOOS.")
    if require_key:
        # A key that is PRESENT but rejected used to sail straight through: every model call
        # failed silently, the report fell back to name-only heuristics, and the footer still said
        # the code had been read by your model. Check it once, up front, and say so plainly.
        ok, err = probe()
        if not ok:
            raise MissingKeyError(
                f"StackXray found an AI key, but {err}.\n"
                "Nothing could be read, so the scan stopped rather than hand you a weaker report "
                "that claimed otherwise.\n"
                "Fix the key in API-KEY.txt (next to this tool) or in ANTHROPIC_API_KEY / "
                "OPENAI_API_KEY, then run it again.")

    path, cleanup = resolve_source(source)
    try:
        # One provider for the whole run: it reads unparsed languages during extraction (the LLM
        # universal track) AND validates candidates during rejudge, so a local run with a key sees
        # its PHP/Ruby/etc. read, not just flagged. Local = unmetered (the customer's own key).
        provider = provider_from_env()
        cmap = extract_capabilities(ScanConfig(repo_path=path, llm=llm or LLMConfig()),
                                    provider=provider)
        if is_git_url(source):
            cmap.scan_id = f"scan:{_repo_name(source)}"   # nice name, not the temp dir
        from .plan import build_plan
        from .verdict import assign_verdicts

        from .duplication import adjudicate, find_duplicates

        caps = assign_verdicts(cmap.capabilities)     # keep / consolidate / agentify / retire
        opps = agentify.assess(caps)
        opps, ai_validated = rejudge(opps, caps, os.path.abspath(path), provider=provider)
        # The complement of the agent list: human-judgement / physical-process work where a
        # digital twin fits better than automating the decision away.
        from .agentify.twin import assess_twins
        twins = assess_twins(caps)
        # The same job built separately in several modules -> ONE agent replaces them all.
        merges = find_duplicates(os.path.abspath(path), caps)
        merges, _ = adjudicate(merges, os.path.abspath(path))
        plan = build_plan(caps, opps, merge=merges)   # merged agents lead; foundation first
        # The plan is the authority: it drops the singles a merged agent already replaces.
        opps = [s.opportunity for s in plan.build]
        # Work exhaust (tickets/issues export): joined onto the map, volumes land on the cards.
        work_stats = None
        if tickets_path and os.path.isfile(tickets_path):
            from .tickets import attach_demand, join_demand, parse_any, rerank_by_demand
            with open(tickets_path, encoding="utf-8", errors="replace") as fh:
                items, src = parse_any(fh.read())
            if items:
                work_stats = join_demand(caps, items, source=src)
                attach_demand(opps, work_stats)
                rerank_by_demand(opps, work_stats)   # volume moves rank; report says so
        return render_agentify(cmap, opps, _consolidate_note(caps),
                               ai_validated=ai_validated, plan=plan, twins=twins,
                               work_stats=work_stats)
    finally:
        if cleanup:
            shutil.rmtree(cleanup, ignore_errors=True)


def run_agentify(source: str, out_path: str | None = None, llm: LLMConfig | None = None,
                 require_key: bool = True) -> str:
    """Run the V1 Agentify scan (folder or Git URL) and write the HTML report. Returns path."""
    html = build_report_html(source, llm, require_key=require_key)
    out_path = out_path or os.path.abspath("stackxray-agentify-report.html")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return out_path


def run_and_open(source: str, llm: LLMConfig | None = None) -> str:
    """Run the scan (folder or Git URL), open the report in the browser, return the path."""
    try:
        path = run_agentify(source, llm=llm)
    except MissingKeyError as e:
        raise SystemExit(f"\n{e}\n")               # clean message, not a traceback
    except ValueError as e:
        raise SystemExit(str(e))
    print(f"Report written to {path}")
    try:
        import webbrowser
        webbrowser.open("file:///" + path.replace("\\", "/"))
    except Exception:
        pass
    return path
