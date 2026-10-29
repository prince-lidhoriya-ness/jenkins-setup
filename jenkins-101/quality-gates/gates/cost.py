"""GATE 3 - Claude cost/budget. Cumulative ledger: results/cost_ledger.jsonl (one JSON line per Claude call).
Commands: record-claude | record | check | remaining | reset | gate"""
import argparse, json, sys, time
from common import RESULTS, thresholds, finish

LEDGER = RESULTS / "cost_ledger.jsonl"


def rows():
    return [json.loads(l) for l in LEDGER.read_text().splitlines() if l.strip()] if LEDGER.exists() else []


def add(**r):
    RESULTS.mkdir(parents=True, exist_ok=True)
    r["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with LEDGER.open("a") as f: f.write(json.dumps(r) + "\n")
    print(f"recorded ${r.get('usd', 0):.4f} ({r.get('label')})")


def totals():
    rs = rows()
    return {"total_usd": round(sum(r["usd"] for r in rs), 4), "iterations": len(rs),
            "max_usd_per_iteration": round(max([r["usd"] for r in rs], default=0), 4),
            "total_tokens": sum(r.get("input_tokens", 0) + r.get("output_tokens", 0) for r in rs)}


def limits():
    t = thresholds().get("gate3", {})
    g = lambda k, d: (t.get(k) or {}).get("max", d)
    return g("total_usd", 1e9), g("iterations", 10**9), g("max_usd_per_iteration", 1e9)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["record-claude", "record", "check", "remaining", "reset", "gate"])
    ap.add_argument("--phase"); ap.add_argument("--label", default="modernize")
    ap.add_argument("--usd", type=float, default=0); ap.add_argument("--input-tokens", type=int, default=0)
    ap.add_argument("--output-tokens", type=int, default=0)
    a = ap.parse_args(); t = totals(); max_usd, max_it, max_call = limits()
    if a.cmd == "record":
        add(label=a.label, usd=a.usd, input_tokens=a.input_tokens, output_tokens=a.output_tokens)
    elif a.cmd == "record-claude":      # stdin = output of: claude -p ... --output-format json
        d = json.loads(sys.stdin.read())
        if isinstance(d, list): d = next((x for x in reversed(d) if x.get("type") == "result"), {})
        u = d.get("usage", {})
        add(label=a.label, usd=float(d.get("total_cost_usd", 0)), session=d.get("session_id"), turns=d.get("num_turns"),
            input_tokens=u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0),
            output_tokens=u.get("output_tokens", 0))
    elif a.cmd == "check":              # exit 42 => STOP calling Claude (budget or iteration cap hit)
        over = t["total_usd"] >= max_usd or t["iterations"] >= max_it
        print(f"spent ${t['total_usd']} / ${max_usd}, iterations {t['iterations']} / {max_it} -> {'BUDGET EXHAUSTED' if over else 'ok'}")
        sys.exit(42 if over else 0)
    elif a.cmd == "remaining":          # USD cap to hand to `claude --max-budget-usd`
        print(f"{max(0, min(max_usd - t['total_usd'], max_call)):.2f}")
    elif a.cmd == "reset":
        LEDGER.unlink(missing_ok=True); print("ledger cleared")
    else:
        notes = [f"budget remaining: ${max(0, max_usd - t['total_usd']):.2f}"]
        finish("gate3", "Claude cost budget", a.phase, t, [], notes)
