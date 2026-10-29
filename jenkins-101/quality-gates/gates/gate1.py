"""GATE 1 - static analysis (SonarQube) + SAST (Semgrep) + dependency/IaC vulns (Trivy)."""
import argparse, os
from common import phase_dir, read_json, tool_ok, finish

ap = argparse.ArgumentParser(); ap.add_argument("--phase", required=True); a = ap.parse_args()
raw = phase_dir(a.phase, True)
metrics, findings, notes, errors = {}, [], [], 0

# ---- SonarQube (collected by sonar.py) ----
if os.environ.get("SKIP_SONAR") == "1":
    notes.append("SonarQube skipped (SKIP_SONAR=1)")
else:
    s = read_json(raw / "sonar.json")
    if not s:
        errors += 1; notes.append("SonarQube produced no result")
    else:
        m = s["measures"]; f = lambda k: float(m[k]) if k in m else None
        for key, name, cast in [("bugs", "sonar_bugs", int), ("vulnerabilities", "sonar_vulnerabilities", int),
                                ("code_smells", "sonar_code_smells", int), ("security_hotspots", "sonar_security_hotspots", int),
                                ("duplicated_lines_density", "sonar_duplication_pct", float), ("coverage", "sonar_coverage_pct", float),
                                ("security_rating", "sonar_security_rating", int), ("reliability_rating", "sonar_reliability_rating", int),
                                ("sqale_rating", "sonar_maintainability_rating", int), ("ncloc", "sonar_ncloc", int)]:
            if f(key) is not None:
                metrics[name] = cast(f(key))
        metrics["sonar_quality_gate_failed"] = 1 if s.get("quality_gate") == "ERROR" else 0
        findings += s.get("issues", [])

# ---- Semgrep ----
if not tool_ok(a.phase, "semgrep"):
    errors += 1; notes.append("Semgrep did not run")
else:
    d = read_json(raw / "semgrep.json", {"results": []})
    hi = me = 0
    for r in d.get("results", []):
        sev = r.get("extra", {}).get("severity", "INFO")
        if sev == "ERROR": hi += 1
        elif sev == "WARNING": me += 1
        findings.append({"tool": "semgrep", "severity": {"ERROR": "high", "WARNING": "medium"}.get(sev, "low"),
                         "file": r.get("path"), "line": r.get("start", {}).get("line"),
                         "rule": r.get("check_id", "").split(".")[-1], "msg": r.get("extra", {}).get("message", "")[:200]})
    metrics.update(semgrep_high=hi, semgrep_medium=me)

# ---- Trivy ----
if not tool_ok(a.phase, "trivy"):
    errors += 1; notes.append("Trivy did not run")
else:
    d = read_json(raw / "trivy.json", {}) or {}
    seen, cnt, mis = set(), {"CRITICAL": 0, "HIGH": 0}, 0
    for res in d.get("Results", []) or []:
        for v in res.get("Vulnerabilities") or []:
            k = (v["VulnerabilityID"], v["PkgName"], res.get("Target"))
            if k in seen: continue
            seen.add(k)
            if v["Severity"] in cnt: cnt[v["Severity"]] += 1
            if v["Severity"] in ("CRITICAL", "HIGH"):
                findings.append({"tool": "trivy", "severity": v["Severity"].lower(), "file": res.get("Target"),
                                 "rule": v["VulnerabilityID"],
                                 "msg": f"{v['PkgName']} {v.get('InstalledVersion')} -> fix: {v.get('FixedVersion', 'none yet')}"})
        for mc in res.get("Misconfigurations") or []:
            if mc.get("Severity") in ("CRITICAL", "HIGH"):
                mis += 1
                findings.append({"tool": "trivy", "severity": mc["Severity"].lower(), "file": res.get("Target"),
                                 "rule": mc.get("ID"), "msg": mc.get("Title", "")})
    metrics.update(trivy_critical=cnt["CRITICAL"], trivy_high=cnt["HIGH"], trivy_misconfig_high=mis)

metrics["tool_errors"] = errors
finish("gate1", "Static analysis & security", a.phase, metrics, findings, notes)
