"""Learn how much of your rate limits Claude Code work takes. Zero tokens.

Joins two local sources and writes ~/.claude/usage-model.json:

  usage-history.jsonl   how the 5h / 7d percentages moved (statusline.py)
  ~/.claude/projects    Claude Code's transcripts: the tokens every response
                        used, in sessions, subagents and Workflow runs

and learns from them
  rates   roughly how much work is 1% of each window
  runs    what past Workflow runs and subagents cost

Work is counted in API-equivalent dollars: tokens priced at the Claude API list
price of the model that used them. A subscription isn't billed that way, but it
puts output, cache reads and different models on one scale, and the learned
rate turns it back into percent.

statusline.py starts this in the background at most every 30 minutes, so it
keeps up without anyone running it. Run it directly to see what it learned:

    python usage_learn.py

No network calls, no credentials, no API key.
"""
import bisect
import datetime
import glob
import json
import math
import os
import re
import sys
import tempfile
import time

import usage_core as core

MODEL_NAME = "usage-model.json"
MODEL_VERSION = 1
HISTORY_NAMES = ("usage-history.1.jsonl", "usage-history.jsonl")  # oldest first
LOCK_NAME = "usage-learn.lock"  # taken by statusline.py before it starts us

DAY = 86400
KEEP_DAYS = 42  # history, observations and runs older than this are dropped
TRANSCRIPT_DAYS_DEFAULT = 30  # Claude Code's cleanupPeriodDays default
RUN_SETTLE_SECONDS = 15 * 60  # a run active more recently may not be finished
RESET_TOLERANCE = 600  # resets_at values this close are the same window

# (history key, window length, anchored). The 7-day window starts from 0% at
# resets_at - 7 days: two snapshots four weeks apart gave the same rate under
# that assumption, so a first sighting mid-window can be measured from the
# window start. The 5-hour window failed the same check, so it is only ever
# measured between two sightings.
WINDOWS = (("5h", 5 * 3600, False), ("7d", 7 * DAY, True))

# $ per million tokens as (input, output, cache read); the first key found in
# the model id wins. Cache writes cost 1.25x input (5-minute) or 2x (1-hour).
PRICES = (
    ("fable-5-1", (10.0, 50.0, 0.25)),
    ("fable", (10.0, 50.0, 1.0)),
    ("mythos", (10.0, 50.0, 1.0)),
    ("opus", (5.0, 25.0, 0.5)),
    ("sonnet-4", (3.0, 15.0, 0.3)),
    ("sonnet", (2.0, 10.0, 0.2)),
    ("haiku", (1.0, 5.0, 0.1)),
)
DEFAULT_PRICE = (5.0, 25.0, 0.5)  # an unknown model is priced like Opus
FAST_MULTIPLIER = 2.0  # fast mode is billed at twice the standard rate


def claude_path(name: str) -> str:
    return os.path.join(core.claude_dir(), name)


def model_path() -> str:
    return claude_path(MODEL_NAME)


def as_num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def tokens(value) -> float:
    n = as_num(value)
    return max(0, n) if n is not None else 0


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def write_atomic(path: str, text: str) -> None:
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".usage-learn-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def parse_time(value):
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def quantile(values, q):
    """Nearest-rank quantile. With only a few values, high quantiles are the max."""
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))]


def weighted_quantile(pairs, q):
    """Quantile of (value, weight) pairs, so a 10% stretch outweighs a 1% one."""
    pairs = sorted(pairs)
    target = q * sum(weight for _, weight in pairs)
    seen = 0.0
    for value, weight in pairs:
        seen += weight
        if seen >= target:
            return value
    return pairs[-1][0]


def response_usd(model, usage) -> float:
    """API list price of one response's token usage."""
    inp, out, read = next((price for key, price in PRICES if key in (model or "")), DEFAULT_PRICE)
    split = usage.get("cache_creation")
    if isinstance(split, dict):
        write_5m = tokens(split.get("ephemeral_5m_input_tokens"))
        write_1h = tokens(split.get("ephemeral_1h_input_tokens"))
    else:
        write_5m, write_1h = tokens(usage.get("cache_creation_input_tokens")), 0
    usd = (tokens(usage.get("input_tokens")) * inp
           + write_5m * inp * 1.25
           + write_1h * inp * 2
           + tokens(usage.get("cache_read_input_tokens")) * read
           + tokens(usage.get("output_tokens")) * out) / 1e6
    return usd * FAST_MULTIPLIER if usage.get("speed") == "fast" else usd


def transcript_days() -> float:
    """How long Claude Code keeps transcripts (settings.json cleanupPeriodDays)."""
    settings = load_json(claude_path("settings.json"), {})
    days = as_num(settings.get("cleanupPeriodDays")) if isinstance(settings, dict) else None
    return max(2.0, float(days)) if days else float(TRANSCRIPT_DAYS_DEFAULT)


# --- transcripts -------------------------------------------------------------

def workflow_name(session_dir: str, run_id: str):
    """The `name` from the run's script meta block, e.g. 'regression-review'."""
    record = load_json(os.path.join(session_dir, "workflows", run_id + ".json"), {})
    script = record.get("script") if isinstance(record, dict) else None
    if not isinstance(script, str):
        return None
    match = re.search(r"\bname\s*:\s*['\"]([^'\"\n]{1,80})['\"]", script)
    return match.group(1) if match else None


def scan_transcripts(since: float):
    """Every response since `since` as sorted (time, usd), plus per-run totals.

    Layout under ~/.claude/projects/<project>/:
      <session>.jsonl                                      the conversation
      <session>/subagents/agent-<id>.jsonl (+ .meta.json)  an Agent subagent
      <session>/subagents/workflows/<run>/agent-<id>.jsonl one Workflow run's agents
      <session>/workflows/<run>.json                       the run record

    A subagent started by another subagent counts towards the run it belongs
    to (via parentAgentId), so a run's cost includes everything under it.
    """
    root = claude_path("projects")
    agents = {}  # (session dir, agent id) -> (workflow run id or None, meta)
    files = []  # (path, project, session dir, agent id) for files worth reading
    for path in glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True):
        parts = os.path.relpath(path, root).split(os.sep)
        session = agent = None
        if "subagents" in parts and parts[-1].startswith("agent-"):
            i = parts.index("subagents")
            session = os.path.join(root, *parts[:i])
            agent = parts[-1][len("agent-"):-len(".jsonl")]
            run = parts[i + 2] if parts[i + 1] == "workflows" and len(parts) == i + 4 else None
            meta = load_json(path[:-len(".jsonl")] + ".meta.json", {})
            # Metas of old files too: a recent agent's parent may be older.
            agents[(session, agent)] = (run, meta if isinstance(meta, dict) else {})
        try:
            if os.path.getmtime(path) >= since:
                files.append((path, parts[0], session, agent))
        except OSError:
            pass

    def run_of(session, agent):
        seen = set()
        while agent not in seen:
            seen.add(agent)
            run, meta = agents[(session, agent)]
            if run:
                return ("workflow", run)
            parent = meta.get("parentAgentId")
            if not parent or (session, parent) not in agents:
                break
            agent = parent
        return ("agent", agent)

    responses = {}
    for path, project, session, agent in files:
        op = (session,) + run_of(session, agent) if agent else None
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"usage"' not in line:
                        continue
                    try:
                        entry = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(entry, dict) or entry.get("type") != "assistant":
                        continue
                    message = entry.get("message")
                    if not isinstance(message, dict) or not isinstance(message.get("usage"), dict):
                        continue
                    when = parse_time(entry.get("timestamp"))
                    if when is None or when < since:
                        continue
                    key = message.get("id") or entry.get("requestId") or entry.get("uuid") or (path, len(responses))
                    # A response streamed as several blocks is written as several
                    # lines with one id and output_tokens still counting up; the
                    # last line carries the final usage, so it replaces the rest.
                    responses[key] = (when, response_usd(message.get("model"), message["usage"]),
                                      op, project, agent)
        except OSError:
            continue

    events = sorted((when, usd) for when, usd, _, _, _ in responses.values())
    ops = {}
    for when, usd, op, project, agent in responses.values():
        if op is None:
            continue
        session, kind, ident = op
        rec = ops.get((kind, ident))
        if rec is None:
            if kind == "workflow":
                name = workflow_name(session, ident)
            else:
                name = agents[(session, ident)][1].get("agentType")
            rec = ops[(kind, ident)] = {"name": name or kind, "project": project, "t0": when,
                                        "t1": when, "usd": 0.0, "agents": set()}
        rec["t0"] = min(rec["t0"], when)
        rec["t1"] = max(rec["t1"], when)
        rec["usd"] += usd
        rec["agents"].add(agent)
    return events, ops


# --- history -----------------------------------------------------------------

def history_time(line: str):
    try:
        rec = json.loads(line)
    except ValueError:
        return None
    return as_num(rec.get("t")) if isinstance(rec, dict) else None


def read_history():
    records = []
    for name in HISTORY_NAMES:
        try:
            with open(claude_path(name), "r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue  # a torn line from two sessions appending at once
                    if isinstance(rec, dict) and as_num(rec.get("t")) is not None:
                        records.append(rec)
        except OSError:
            pass
    records.sort(key=lambda rec: rec["t"])
    return records


def prune_history(keep_from: float) -> None:
    """Drop history lines older than keep_from.

    A file is only rewritten once its first line is a day past the cutoff, so
    this happens about daily. A line statusline.py appends between the read and
    the replace here is lost; for a few milliseconds a day that's acceptable.
    """
    for name in HISTORY_NAMES:
        path = claude_path(name)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError:
            continue
        first = next((t for t in map(history_time, lines) if t is not None), None)
        if first is None or first >= keep_from - DAY:
            continue
        kept = [line for line in lines if (history_time(line) or 0) >= keep_from]
        try:
            if kept:
                write_atomic(path, "".join(kept))
            else:
                os.unlink(path)
        except OSError:
            pass


def window_runs(records, key: str, length: float, anchored: bool):
    """One stretch of history per window, from its first sighting to its last.

    Usage can't go down inside a window, so a lower reading is a stale one from
    an idle session and is skipped, as is a late reading from a window that
    already reset. statusline.py no longer logs either, but history written
    before it filtered them does contain them.
    """
    runs = []
    current = None
    for rec in records:
        pct = as_num(rec.get(key))
        reset = as_num(rec.get(key + "_reset"))
        if pct is None or reset is None:
            continue
        if current is not None:
            if abs(reset - current["reset"]) <= RESET_TOLERANCE:
                if pct >= current["p1"]:
                    current["t1"], current["p1"] = rec["t"], pct
                continue
            if reset < current["reset"]:
                continue
            runs.append(current)
        current = {"t0": rec["t"], "p0": pct, "t1": rec["t"], "p1": pct, "reset": reset}
        if anchored and reset - length <= rec["t"]:
            current.update(t0=reset - length, p0=0, anchored=True)
    if current is not None:
        runs.append(current)
    return runs


def valid_observation(obs) -> bool:
    return (isinstance(obs, dict) and obs.get("w") in [w for w, _, _ in WINDOWS]
            and all(as_num(obs.get(k)) is not None for k in ("t0", "t1", "p0", "p1", "usd")))


def learn_observations(records, events, stored, horizon: float, keep_from: float):
    """(percent moved, dollars spent) pairs, one per stretch of history.

    Stretches older than the transcript horizon can't be recomputed -- their
    transcripts may be gone -- so those come from the previous model. Newer
    ones are recomputed from the history every pass; the previous model only
    backs them up if transcripts vanished early, and is otherwise dropped, so a
    stretch the history no longer supports doesn't linger.
    """
    times = [when for when, _ in events]
    totals = [0.0]
    for _, usd in events:
        totals.append(totals[-1] + usd)

    def spent(t0, t1):
        return totals[bisect.bisect_right(times, t1)] - totals[bisect.bisect_right(times, t0)]

    found = {}
    recent = {}
    for obs in stored if isinstance(stored, list) else []:
        if valid_observation(obs) and obs["t1"] >= keep_from:
            (found if obs["t0"] < horizon else recent)[(obs["w"], int(obs["t0"] // 60))] = obs
    for key, length, anchored in WINDOWS:
        for run in window_runs(records, key, length, anchored):
            if run["p1"] <= run["p0"] or run["t0"] < horizon:
                continue
            obs = {"w": key, "t0": round(run["t0"], 1), "t1": round(run["t1"], 1),
                   "p0": run["p0"], "p1": run["p1"], "usd": round(spent(run["t0"], run["t1"]), 4)}
            if run.get("anchored"):
                obs["anchored"] = True
            slot = (key, int(run["t0"] // 60))
            known = recent.get(slot)
            # Spend since a fixed start only grows, so less means transcripts
            # were deleted early; the earlier measurement is the right one.
            found[slot] = known if known is not None and obs["usd"] < known["usd"] - 0.01 else obs
    return sorted(found.values(), key=lambda obs: obs["t0"])


def summarize_rate(observations, key: str) -> dict:
    """Dollars per 1% of a window, as a weighted median over observations.

    A stretch where the percentage rose with no local spend at all was used
    somewhere this machine can't see (claude.ai, the phone, another computer);
    it's reported but left out. Partly-elsewhere stretches make a rate look
    lower, which the median shrugs off as long as they're the minority.
    """
    moved = [obs for obs in observations if obs["w"] == key and obs["p1"] > obs["p0"]]
    explained = [obs for obs in moved if obs["usd"] > 0]
    pct = sum(obs["p1"] - obs["p0"] for obs in explained)
    out = {
        "observations": len(explained),
        "pct_observed": round(pct, 1),
        "pct_unexplained": round(sum(obs["p1"] - obs["p0"] for obs in moved if obs["usd"] <= 0), 1),
        "usd_per_pct": None,
        "confidence": "none",
    }
    if explained:
        pairs = [(obs["usd"] / (obs["p1"] - obs["p0"]), obs["p1"] - obs["p0"]) for obs in explained]
        out.update(
            usd_per_pct=round(weighted_quantile(pairs, 0.5), 3),
            low=round(weighted_quantile(pairs, 0.25), 3),
            high=round(weighted_quantile(pairs, 0.75), 3),
            # Percentages arrive as whole numbers, so each stretch carries about
            # +-1% of rounding; several stretches and 15% of movement keep that small.
            confidence="ok" if len(explained) >= 3 and pct >= 15 else "low",
        )
    return out


# --- runs --------------------------------------------------------------------

def merge_runs(stored, ops, now: float, keep_from: float):
    runs = {}
    for run in stored if isinstance(stored, list) else []:
        if (isinstance(run, dict) and as_num(run.get("t0")) is not None
                and as_num(run.get("t1")) is not None and run["t1"] >= keep_from
                and as_num(run.get("usd")) is not None):
            runs[(run.get("kind"), run.get("id"))] = run
    for (kind, ident), op in ops.items():
        known = runs.get((kind, ident))
        if known is not None and (known["t0"] < op["t0"] - 1 or op["usd"] < known["usd"] - 0.01):
            continue  # some of its transcripts are gone; keep the full count
        runs[(kind, ident)] = {
            "kind": kind, "id": ident, "name": op["name"], "project": op["project"],
            "t0": round(op["t0"], 1), "t1": round(op["t1"], 1), "usd": round(op["usd"], 4),
            "agents": len(op["agents"]), "settled": now - op["t1"] >= RUN_SETTLE_SECONDS,
        }
    return sorted(runs.values(), key=lambda run: run["t0"])


def run_group(run) -> str:
    return "workflow" if run.get("kind") == "workflow" else "agent: %s" % (run.get("name") or "?")


def summarize_runs(runs) -> dict:
    groups = {}
    for run in runs:
        if run.get("settled"):
            groups.setdefault(run_group(run), []).append(run["usd"])
    return {group: {"n": len(costs),
                    "median_usd": round(quantile(costs, 0.5), 2),
                    "p90_usd": round(quantile(costs, 0.9), 2)}
            for group, costs in groups.items()}


# --- the pass ----------------------------------------------------------------

def learn(now=None) -> dict:
    """One full pass: prune, scan, learn, write the model. Returns the model."""
    now = time.time() if now is None else now
    keep_from = now - KEEP_DAYS * DAY
    # A day's margin: transcripts right at the cleanup age may be mid-deletion.
    horizon = now - (transcript_days() - 1) * DAY
    previous = load_json(model_path(), {})
    if not isinstance(previous, dict) or previous.get("version") != MODEL_VERSION:
        previous = {}

    prune_history(keep_from)
    records = [rec for rec in read_history() if rec["t"] >= keep_from]
    events, ops = scan_transcripts(horizon)
    observations = learn_observations(records, events, previous.get("observations"), horizon, keep_from)
    runs = merge_runs(previous.get("runs"), ops, now, keep_from)

    model = {
        "version": MODEL_VERSION,
        "learned_at": round(now, 1),
        "unit": "API-equivalent USD: tokens at Claude API list price",
        "history_records": len(records),
        "rates": {key: summarize_rate(observations, key) for key, _, _ in WINDOWS},
        "run_costs": summarize_runs(runs),
        "observations": observations,
        "runs": runs,
    }
    write_atomic(model_path(), json.dumps(model, indent=1))
    return model


# --- report ------------------------------------------------------------------

def fmt_usd(value) -> str:
    if value is None:
        return "--"
    if value >= 100:
        return "$%.0f" % value
    return "$%.1f" % value if value >= 10 else "$%.2f" % value


def fmt_pct(value) -> str:
    return "%.1f%%" % value if value < 10 else "%.0f%%" % value


def report(model: dict, state=None) -> str:
    state = core.read_state() if state is None else state
    rates = model["rates"]
    costs = model.get("run_costs") or {}
    learned = datetime.datetime.fromtimestamp(model["learned_at"]).strftime("%d %b %H:%M")
    out = ["Claude usage model, learned %s" % learned,
           "Costs are API-equivalent: tokens at Claude API list price, not a bill.",
           "",
           "1% of each limit is about:"]
    for key, label in (("5h", "5-hour"), ("7d", "7-day ")):
        rate = rates[key]
        if rate["usd_per_pct"] is None:
            out.append("  %s  --      still learning: no usable change in the history yet" % label)
        else:
            spread = ("range %s-%s, " % (fmt_usd(rate["low"]), fmt_usd(rate["high"]))
                      if rate["observations"] > 1 else "")
            out.append("  %s  %-7s %sfrom %g%% seen in %d window%s, %s confidence" % (
                label, fmt_usd(rate["usd_per_pct"]), spread, rate["pct_observed"], rate["observations"],
                "" if rate["observations"] == 1 else "s", rate["confidence"]))
        if rate["pct_unexplained"]:
            out.append("          plus %g%% that rose with no Claude Code activity on this machine"
                       % rate["pct_unexplained"])

    groups = sorted(costs, key=lambda g: (g != "workflow", -costs[g]["n"]))[:6]
    out += ["", "Finished runs                      count   typical    worst   5h worst   7d worst"]
    if not groups:
        out.append("  none yet (Workflow runs and subagents appear here once they finish)")
    for group in groups:
        stats = costs[group]
        cols = []
        for key in ("5h", "7d"):
            per = rates[key]["usd_per_pct"]
            cols.append(fmt_pct(stats["p90_usd"] / per) if per else "--")
        out.append("  %-32s %6d  %8s  %7s  %9s  %9s" % (
            group[:32], stats["n"], fmt_usd(stats["median_usd"]), fmt_usd(stats["p90_usd"]), *cols))
        if group == "workflow":
            names = {}
            for run in model["runs"]:
                if run.get("settled") and run.get("kind") == "workflow":
                    names.setdefault(run.get("name") or "?", []).append(run["usd"])
            for name, values in sorted(names.items(), key=lambda kv: -len(kv[1]))[:5]:
                out.append("    %-30s %6d  %8s  %7s" % (
                    name[:30], len(values), fmt_usd(quantile(values, 0.5)), fmt_usd(quantile(values, 0.9))))

    out.append("")
    if not state.has_limits:
        out.append("Right now: %s" % (state.problem or "no usage data"))
        return "\n".join(out)
    out.append("Right now: 5h %s (resets %s), 7d %s (resets %s)%s" % (
        "--" if state.five_pct is None else "%d%%" % state.five_pct, core.fmt_clock(state.five_reset),
        "--" if state.seven_pct is None else "%d%%" % state.seven_pct, core.fmt_clock(state.seven_reset),
        "  [STALE: %s]" % core.fmt_age(state.captured_at) if state.stale and state.captured_at else ""))
    for group in groups:
        stats = costs[group]
        verdicts = []
        for key, used in (("5h", state.five_pct), ("7d", state.seven_pct)):
            per = rates[key]["usd_per_pct"]
            if per is None or used is None:
                continue
            left = 100 - used
            verdicts.append("%s %s (typical %s, worst %s, %d%% left)" % (
                key, core.fit(stats["median_usd"] / per, stats["p90_usd"] / per, left),
                fmt_pct(stats["median_usd"] / per), fmt_pct(stats["p90_usd"] / per), left))
        out.append("  %-32s %s" % (group[:32], "; ".join(verdicts) or "no rate learned yet"))
    return "\n".join(out)


def main(argv) -> int:
    if "--background" in argv:
        try:
            learn()
        except Exception:
            pass  # pythonw has nowhere to show it; the next pass tries again
        finally:
            try:
                os.unlink(claude_path(LOCK_NAME))
            except OSError:
                pass
        return 0
    print(report(learn()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
