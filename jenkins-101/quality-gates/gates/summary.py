"""Aggregate gate results for one phase -> summary.json + feedback.md (for Claude) ; exit 1 if enforced & failed."""
import argparse, json, sys
from common import phase_dir, read_json, is_baseline

ap = argparse.ArgumentParser(); ap.add_argument("--phase", required=True); ap.add_argument("--gates", default="1,2,3,4"); a = ap.parse_args()
d = phase_dir(a.phase); enforced = not is_baseline(a.phase); results, missing = {}, []
for g in a.gates.split(","):
    r = read_json(d / f"gate{g}.json")
    (results.__setitem__(f"gate{g}", r) if r else missing.append(f"gate{g}"))
failed = [k for k, r in results.items() if not r["passed"]] + missing
summary = {"phase": a.phase, "enforced": enforced, "all_passed": not failed, "failed_gates": failed,
           "gates": {k: {"passed": r["passed"], "metrics": r["metrics"]} for k, r in results.items()}}
(d / "summary.json").write_text(json.dumps(summary, indent=2))

md = [f"# Quality gate feedback - phase `{a.phase}`", ""]
md.append("**All gates passed.**" if not failed else f"**Failed gates: {', '.join(failed)}** - fix the items below, then re-run the gates.")
for k, r in results.items():
    bad = [c for c in r["checks"] if c["passed"] is False]
    if not bad: continue
    md += ["", f"## {k}: {r['title']}", "", "Failed thresholds:"]
    md += [f"- `{c['metric']}` = {c['value']} (required {c['rule']})" for c in bad]
    if r["findings"]:
        md += ["", "Top findings (file:line - rule - message):"]
        md += [f"- {f.get('file')}:{f.get('line', '')} - {f.get('rule')} [{f['severity']}] - {f.get('msg', '')}" for f in r["findings"][:25]]
        if r["findings_total"] > 25: md.append(f"- ... {r['findings_total'] - 25} more in results/{a.phase}/{k}.json")
(d / "feedback.md").write_text("\n".join(md) + "\n")

print(f"\n=== {a.phase} ({'ENFORCED' if enforced else 'BASELINE'}) ===")
for k, r in results.items(): print(f"  {k}: {'PASS' if r['passed'] else 'FAIL'}  {r['title']}")
for k in missing: print(f"  {k}: NOT RUN")
print(f"  feedback for Claude: results/{a.phase}/feedback.md")
sys.exit(1 if (enforced and failed) else 0)
