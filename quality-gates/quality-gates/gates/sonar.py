"""SonarQube helper:  bootstrap (wait, change admin pw, create token)  |  collect (fetch measures)."""
import argparse, base64, json, os, sys, time, urllib.error, urllib.parse, urllib.request
from common import RESULTS, phase_dir

HOST = os.environ.get("SONAR_HOST_URL", "http://sonarqube:9000")
KEY = os.environ.get("SONAR_PROJECT_KEY", "hms")
NEW_PW = os.environ.get("SONAR_ADMIN_PASSWORD", "Gates#Admin123456")


def api(path, auth, method="GET", data=None):
    h = {"Authorization": "Basic " + base64.b64encode(f"{auth}:".encode() if ":" not in auth else auth.encode()).decode()}
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    try:
        with urllib.request.urlopen(urllib.request.Request(HOST + path, data=body, method=method, headers=h), timeout=60) as r:
            t = r.read().decode(); return r.status, (json.loads(t) if t.strip().startswith(("{", "[")) else t)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def bootstrap():
    for _ in range(120):  # up to ~10 min for first start
        try:
            with urllib.request.urlopen(HOST + "/api/system/status", timeout=5) as r:
                if json.loads(r.read()).get("status") == "UP": break
        except Exception: pass
        time.sleep(5)
    else:
        sys.exit("SonarQube did not become UP (give Docker Desktop >= 4GB RAM)")
    api("/api/users/change_password", "admin:admin", "POST",
        {"login": "admin", "previous_password": "admin", "password": NEW_PW})  # ignored if already changed
    cred = f"admin:{NEW_PW}"
    api("/api/user_tokens/revoke", cred, "POST", {"name": "gates"})
    st, r = api("/api/user_tokens/generate", cred, "POST", {"name": "gates"})
    if st != 200: sys.exit(f"cannot create token ({st}): {r}. If you changed the admin password set SONAR_ADMIN_PASSWORD")
    (RESULTS / ".sonar_token").write_text(r["token"]); print("sonar ready, token saved")


def collect(phase):
    tok = (RESULTS / ".sonar_token").read_text().strip() + ":"
    mk = "bugs,vulnerabilities,code_smells,security_hotspots,duplicated_lines_density,coverage,security_rating,reliability_rating,sqale_rating,ncloc"
    st, m = api(f"/api/measures/component?component={KEY}&metricKeys={mk}", tok)
    if st != 200: sys.exit(f"no measures ({st}): {m}")
    measures = {x["metric"]: x.get("value", x.get("period", {}).get("value")) for x in m["component"]["measures"]}
    _, q = api(f"/api/qualitygates/project_status?projectKey={KEY}", tok)
    _, iss = api(f"/api/issues/search?componentKeys={KEY}&resolved=false&severities=BLOCKER,CRITICAL,MAJOR&ps=100", tok)
    sevmap = {"BLOCKER": "critical", "CRITICAL": "high", "MAJOR": "medium"}
    issues = [{"tool": "sonar", "severity": sevmap.get(i["severity"], "low"), "file": i["component"].split(":", 1)[-1],
               "line": i.get("line"), "rule": i["rule"], "msg": i["message"][:200]} for i in (iss.get("issues", []) if isinstance(iss, dict) else [])]
    out = {"measures": measures, "quality_gate": q.get("projectStatus", {}).get("status") if isinstance(q, dict) else None, "issues": issues}
    (phase_dir(phase, True) / "sonar.json").write_text(json.dumps(out, indent=2)); print("sonar measures collected")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["bootstrap", "collect"]); ap.add_argument("--phase")
    a = ap.parse_args(); bootstrap() if a.cmd == "bootstrap" else collect(a.phase)
