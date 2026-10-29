"""GATE 2 - secrets (gitleaks) + hardcoded credentials + PII/PHI scan (built-in, regex+Luhn)."""
import argparse, os, re
from pathlib import Path
import yaml
from common import BASE, SRC, phase_dir, read_json, tool_ok, finish

ap = argparse.ArgumentParser(); ap.add_argument("--phase", required=True); ap.add_argument("--src", default=str(SRC)); a = ap.parse_args()
cfg = yaml.safe_load((BASE / "config" / "pii_allowlist.yaml").read_text())
SKIP_D, SKIP_E, SKIP_F = set(cfg["skip_dirs"]), tuple(cfg["skip_extensions"]), set(cfg["skip_files"])
OK_DOMAINS = tuple(d.lower() for d in cfg["email_domains"])


def luhn(s):
    d = [int(c) for c in re.sub(r"\D", "", s)]
    if not 13 <= len(d) <= 19: return False
    t = 0
    for i, x in enumerate(reversed(d)):
        if i % 2: x = x * 2 - 9 if x * 2 > 9 else x * 2
        t += x
    return t % 10 == 0


PII = {  # name: (regex, validator)
    "ssn": (re.compile(r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b"), None),
    "aadhaar": (re.compile(r"\b[2-9]\d{3}[ -]\d{4}[ -]\d{4}\b"), None),
    "pan": (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), None),
    "credit_card": (re.compile(r"\b(?:\d[ -]?){13,19}\b"), luhn),
    "email": (re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})\b"),
              lambda s: not s.lower().endswith(OK_DOMAINS)),
    "phone": (re.compile(r"(?<![\d.])(?:\+?91[- ]?)?[6-9]\d{9}(?![\d.])|(?<![\d.])\(?\d{3}\)?[-. ]\d{3}[-. ]\d{4}(?![\d.])"), None),
    "dob": (re.compile(r"(?i)\b(?:dob|date_of_birth|birth_?date)\b[\"'\s:=,]{1,6}\d{4}-\d{2}-\d{2}"), None),
}
CRED_LIT = re.compile(r"""(?i)(password|passwd|pwd|secret|api[_-]?key|access[_-]?key|token)\w*["']?\s*[:=]\s*["']([^"'\s]{4,})["']""")
CRED_CFG = re.compile(r"(?im)^\s*[\w.\-]*(password|secret|api[_-]?key|token)[\w.\-]*\s*[:=]\s*([^\s#\"'$\{<][^\s#]*)\s*$")
CFG_EXT = (".properties", ".yml", ".yaml", ".env", ".conf", ".ini", ".toml", ".cfg")
PLACEHOLDER = re.compile(r"\$\{|\{\{|%\(|<[^>]+>|getenv|environ|process\.env|^x{3,}$|^\*+$|^changeme$", re.I)
LOG_PII = re.compile(r"(?i)(log\w*\.\w+|logger\.\w+|\bprint|console\.\w+|System\.out\.print\w*|println)\s*\(.*\b(ssn|aadhaar|password|passwd|dob|phone|email|card|diagnosis)\b")


def mask(s): return s[:2] + "*" * max(len(s) - 2, 2)


def files(root):
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_D]
        for f in fn:
            p = Path(dp) / f
            if f in SKIP_F or f.lower().endswith(SKIP_E): continue
            try:
                if p.stat().st_size > 1_000_000: continue
                data = p.read_bytes()
            except OSError: continue
            if b"\0" in data[:1024]: continue
            yield p, data.decode("utf-8", "ignore")


pii_f, cred_f, log_f = [], [], []
for p, text in files(a.src):
    rel = str(p.relative_to(a.src))
    for n, line in enumerate(text.splitlines(), 1):
        if len(line) > 2000: continue
        for name, (rx, val) in PII.items():
            for m in rx.finditer(line):
                if val is None or val(m.group(0)):
                    pii_f.append({"tool": "pii", "severity": "high", "file": rel, "line": n, "rule": name, "msg": f"{name} found: {mask(m.group(0))}"})
        rxs = [CRED_LIT] + ([CRED_CFG] if rel.lower().endswith(CFG_EXT) else [])
        for rx in rxs:
            m = rx.search(line)
            if m and not PLACEHOLDER.search(m.group(2)):
                cred_f.append({"tool": "creds", "severity": "critical", "file": rel, "line": n, "rule": "hardcoded-credential", "msg": f"{m.group(1)} = {mask(m.group(2))}"}); break
        if LOG_PII.search(line):
            log_f.append({"tool": "pii", "severity": "medium", "file": rel, "line": n, "rule": "pii-in-logs", "msg": "PII/PHI field written to log/stdout"})

secrets, errors, notes = [], 0, []
if not tool_ok(a.phase, "gitleaks"):
    errors += 1; notes.append("gitleaks did not run")
else:
    for r in read_json(phase_dir(a.phase, True) / "gitleaks.json", []) or []:
        secrets.append({"tool": "gitleaks", "severity": "critical", "file": r.get("File", "").replace("/src/", ""),
                        "line": r.get("StartLine"), "rule": r.get("RuleID"), "msg": r.get("Description", "secret detected")})

metrics = {"tool_errors": errors, "secrets_found": len(secrets), "hardcoded_credentials": len(cred_f),
           "pii_findings": len(pii_f), "pii_in_logs": len(log_f)}
for t in ("ssn", "aadhaar", "pan", "credit_card", "email", "phone", "dob"):
    metrics[f"pii_{t}"] = sum(1 for f in pii_f if f["rule"] == t)
finish("gate2", "Secrets, credentials & PII", a.phase, metrics, secrets + cred_f + pii_f + log_f, notes)
