"""Before/after comparison -> results/comparison.md + comparison.json"""
import json, sys
from common import RESULTS, thresholds, read_json

b, a = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("before", "after")
th = thresholds(); rows, md = [], [f"# Modernization report: `{b}` vs `{a}`", "",
    "| Gate | Metric | Before | After | Change | Verdict | Threshold |", "|---|---|---|---|---|---|---|"]
improved = regressed = 0
for g in ("gate1", "gate2", "gate3", "gate4"):
    rb, ra = read_json(RESULTS / b / f"{g}.json"), read_json(RESULTS / a / f"{g}.json")
    if not rb or not ra: continue
    for m in ra["metrics"]:
        vb, va = rb["metrics"].get(m), ra["metrics"][m]
        rule = (th.get(g) or {}).get(m)
        if vb is None or not isinstance(va, (int, float)): continue
        d = round(va - vb, 4)
        better = (d < 0 if "max" in rule else d > 0) if rule else None
        v = "info" if (rule is None or g == "gate3") else ("same" if d == 0 else ("improved" if better else "REGRESSED"))
        improved += v == "improved"; regressed += v == "REGRESSED"
        ok = "" if not rule else ("pass" if all(c["passed"] for c in ra["checks"] if c["metric"] == m) else "FAIL")
        rows.append({"gate": g, "metric": m, "before": vb, "after": va, "delta": d, "verdict": v, "threshold": rule, "status": ok})
        md.append(f"| {g} | {m} | {vb} | {va} | {d:+g} | {v} | {rule or ''} {ok} |")
sa, sb = read_json(RESULTS / a / "summary.json", {}), read_json(RESULTS / b / "summary.json", {})
md += ["", f"**Improved: {improved} - Regressed: {regressed}** - gates passing after: "
       f"{[k for k, v in sa.get('gates', {}).items() if v['passed']]} - failing: {sa.get('failed_gates')}"]
(RESULTS / "comparison.md").write_text("\n".join(md) + "\n"); (RESULTS / "comparison.json").write_text(json.dumps(rows, indent=2))
print("\n".join(md))
