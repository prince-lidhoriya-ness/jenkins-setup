"""GATE 4 - functional evals. Declarative YAML cases (evals/cases/*.yaml) run as HTTP calls against the running app."""
import argparse, glob, json, math, os, re, time, urllib.error, urllib.request
from pathlib import Path
import yaml
from common import BASE, finish

ap = argparse.ArgumentParser(); ap.add_argument("--phase", required=True); a = ap.parse_args()
MISSING = object()
TYPES = {"list": list, "dict": dict, "str": str, "int": int, "bool": bool, "number": (int, float)}
services = yaml.safe_load((BASE / "evals" / "services.yaml").read_text())["services"]


def subst(x, v):
    if isinstance(x, str): return re.sub(r"\{\{(\w+)\}\}", lambda m: str(v.get(m.group(1), m.group(0))), x)
    if isinstance(x, dict): return {k: subst(i, v) for k, i in x.items()}
    if isinstance(x, list): return [subst(i, v) for i in x]
    return x


def get_path(o, path):
    for p in str(path).split("."):
        if isinstance(o, list):
            try: o = o[int(p)]
            except (ValueError, IndexError): return MISSING
        elif isinstance(o, dict) and p in o: o = o[p]
        else: return MISSING
    return o


def match(val, exp):
    if isinstance(exp, dict) and set(exp) <= {"exists", "absent", "type", "min_len", "contains", "gt", "regex"}:
        if exp.get("absent"): return val is MISSING
        if val is MISSING: return not exp.get("exists", True)
        ok = True
        if "type" in exp: ok &= isinstance(val, TYPES.get(exp["type"], object)) and not (exp["type"] == "int" and isinstance(val, bool))
        if "min_len" in exp: ok &= hasattr(val, "__len__") and len(val) >= exp["min_len"]
        if "contains" in exp: ok &= exp["contains"] in str(val)
        if "gt" in exp: ok &= isinstance(val, (int, float)) and val > exp["gt"]
        if "regex" in exp: ok &= re.search(exp["regex"], str(val)) is not None
        return ok
    return val == exp


def call(method, url, headers, body, timeout):
    data = None
    if body is not None:
        data = json.dumps(body).encode(); headers.setdefault("Content-Type", "application/json")
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, method=method, headers=headers), timeout=timeout) as r:
            st, txt = r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        st, txt = e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return None, "", (time.perf_counter() - t) * 1000, str(e)
    return st, txt, (time.perf_counter() - t) * 1000, None


def wait_ready(url, secs):
    end = time.time() + secs
    while time.time() < end:
        try: urllib.request.urlopen(url, timeout=3); return True
        except urllib.error.HTTPError: return True
        except Exception: time.sleep(2)
    return False


down = {n for n, u in services.items() if not wait_ready(u, int(os.environ.get("EVAL_WAIT_SECONDS", 60)))}
total = passed = crit_fail = 0; lat, findings = [], []
for f in sorted(glob.glob(str(BASE / "evals" / "cases" / "*.y*ml"))):
    spec = yaml.safe_load(Path(f).read_text()); svc = spec["service"]; saved = {}
    for c in spec["cases"]:
        total += 1; errs = []
        if svc not in services: errs.append(f"service '{svc}' not in evals/services.yaml")
        elif svc in down: errs.append(f"service '{svc}' unreachable")
        else:
            rq = subst(c["request"], saved); ex = c.get("expect", {})
            st, txt, ms, err = call(rq.get("method", "GET"), services[svc].rstrip("/") + rq["path"], dict(rq.get("headers", {})), rq.get("body"), c.get("timeout", 15))
            lat.append(ms)
            if err: errs.append(err)
            else:
                want = ex.get("status", 200); want = want if isinstance(want, list) else [want]
                if st not in want: errs.append(f"status {st}, expected {want}")
                try: body = json.loads(txt)
                except json.JSONDecodeError: body = MISSING
                for path, exp in (ex.get("json") or {}).items():
                    v = MISSING if body is MISSING else get_path(body, path)
                    if not match(v, exp): errs.append(f"json[{path}] = {'<missing>' if v is MISSING else str(v)[:60]!r}, expected {exp}")
                if "body_contains" in ex and ex["body_contains"] not in txt: errs.append("body missing expected text")
                if "max_ms" in ex and ms > ex["max_ms"]: errs.append(f"{ms:.0f}ms > {ex['max_ms']}ms")
                if not errs and body is not MISSING:
                    for var, path in (c.get("save") or {}).items():
                        saved[var] = get_path(body, path)
        if errs:
            if c.get("critical"): crit_fail += 1
            findings.append({"tool": "eval", "severity": "high" if c.get("critical") else "medium", "file": f"{svc}:{c['id']}",
                             "rule": c["id"], "msg": f"{c.get('name', '')} -> " + "; ".join(errs)})
        else: passed += 1
lat.sort()
metrics = {"total_cases": total, "passed_cases": passed, "pass_rate": round(passed / total, 4) if total else 0.0,
           "critical_failures": crit_fail, "p95_latency_ms": round(lat[max(0, math.ceil(.95 * len(lat)) - 1)], 1) if lat else 0,
           "services_down": len(down), "tool_errors": 1 if (total == 0 or len(down) == len(services)) else 0}
finish("gate4", "Functional evals", a.phase, metrics, findings, [f"unreachable: {sorted(down)}"] if down else [])
