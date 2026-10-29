"""Shared helpers. Every gate writes results/<phase>/<gate>.json with ONE schema:
{gate, title, phase, enforced, passed, metrics{}, checks[], findings[], notes[]}"""
import json, os, time
from pathlib import Path
import yaml

BASE = Path(__file__).resolve().parent.parent
RESULTS = Path(os.environ.get("RESULTS_DIR", BASE / "results"))
SRC = Path(os.environ.get("SRC_DIR", "/src"))
SEV = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def thresholds():
    return yaml.safe_load(Path(os.environ.get("THRESHOLDS_FILE", BASE / "thresholds.yaml")).read_text())


def is_baseline(phase):
    return any(phase.startswith(p) for p in thresholds().get("baseline_phases", ["before"]))


def phase_dir(phase, raw=False):
    d = RESULTS / phase / ("raw" if raw else "")
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_json(path, default=None):
    try:
        txt = Path(path).read_text().strip()
        return json.loads(txt) if txt else default
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def tool_ok(phase, tool):
    return (phase_dir(phase, True) / f"{tool}.ok").exists()


def evaluate(gate, metrics):
    checks = []
    for m, rule in (thresholds().get(gate) or {}).items():
        if m not in metrics:
            checks.append({"metric": m, "value": None, "rule": rule, "passed": None})
            continue
        v = metrics[m]
        ok = ("max" not in rule or v <= rule["max"]) and ("min" not in rule or v >= rule["min"])
        checks.append({"metric": m, "value": v, "rule": rule, "passed": bool(ok)})
    return checks


def finish(gate, title, phase, metrics, findings=None, notes=None):
    checks = evaluate(gate, metrics)
    findings = sorted(findings or [], key=lambda f: SEV.get(f.get("severity", "info"), 9))
    res = {"gate": gate, "title": title, "phase": phase, "enforced": not is_baseline(phase),
           "passed": all(c["passed"] is not False for c in checks), "metrics": metrics,
           "checks": checks, "findings": findings[:200], "findings_total": len(findings),
           "notes": notes or [], "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (phase_dir(phase) / f"{gate}.json").write_text(json.dumps(res, indent=2))
    bad = [c["metric"] for c in checks if c["passed"] is False]
    print(f"[{gate}] {title}: {'PASS' if res['passed'] else 'FAIL'}"
          f"{'' if res['enforced'] else ' (baseline, not enforced)'}  failed={bad}")
    return res
