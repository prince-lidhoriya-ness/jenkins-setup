# HMS Quality Gates (Gates 1-4)

A drop-in, Docker-only toolkit that scores **any codebase + its running app** on four gates, so the pipeline can run it
**before** modernization (baseline), **after** every Claude iteration (enforced), and then **compare**.

| Gate | What it checks | Tools (all open source, run as containers) |
|---|---|---|
| 1 Static & security | bugs, vulnerabilities, smells, duplication, ratings, SAST, vulnerable dependencies, Dockerfile/IaC misconfig | SonarQube Community + sonar-scanner, Semgrep, Trivy |
| 2 Secrets & PII | leaked secrets, hardcoded passwords, PII/PHI in code & seed data (SSN, Aadhaar, PAN, cards, e-mail, phone, DOB), PII in logs | Gitleaks + built-in scanner (`gates/gate2.py`) |
| 3 Cost | cumulative Claude spend, iteration count, max spend per call, budget pre-flight | ledger + `claude -p --output-format json` |
| 4 Evals | expected functionality: HTTP cases per service, pass rate, critical failures, p95 latency | built-in YAML eval runner (`gates/gate4.py`) |

## The contract (what other teammates rely on)

* **One command per phase:** `./run_gates.sh <phase>` - `before` is a *baseline* (records numbers, never fails); any other name (`after`, `after-iter3`) is *enforced*.
* **Exit code:** `0` = all gates met thresholds (or baseline), `1` = enforced and something failed, `2` = setup error, `42` = Claude budget exhausted (`cost-check`).
* **Output:** `results/<phase>/gate{1..4}.json` (identical schema: `metrics`, `checks`, `findings`), `summary.json`, and **`feedback.md`** - a ready-to-paste list of failing thresholds + top findings (`file:line - rule - message`) to feed back to Claude on the next iteration.
* **Thresholds:** only `thresholds.yaml` (`max`/`min` per metric). Change numbers there, no code edits.
* **Inputs:** `TARGET_DIR` = folder with the code to scan; `evals/services.yaml` = URLs of the running services. Nothing else.
* Only prerequisite: **Docker Desktop** (+ Git Bash/WSL on Windows to run the `.sh`; Jenkins on Linux runs it natively).

## Layout

```
run_gates.sh            entry point (all commands)
thresholds.yaml         pass/fail limits for every gate
docker-compose.yml      runner, sonarqube, sonar-scanner, semgrep, trivy, gitleaks
gates/                  gate1.py gate2.py cost.py(gate3) gate4.py sonar.py summary.py compare.py common.py
config/pii_allowlist.yaml   fake e-mail domains, skipped dirs/files
evals/services.yaml     base URL per service
evals/cases/*.yaml      one file per service (see patient-service.yaml)
samples/                legacy-app (defects on purpose), modernized-app (fixed), compose file to run them
results/                all outputs (git-ignore it)   Jenkinsfile.example
```

## Test it on your laptop (about 10 minutes, first run downloads images)

```bash
cd quality-gates

# 1. start the BAD sample app on :8080
docker compose -f samples/docker-compose.yml --profile legacy up -d --build

# 2. baseline run (fast mode: skip SonarQube first; Semgrep/Trivy/Gitleaks/PII/evals still run)
SKIP_SONAR=1 TARGET_DIR=./samples/legacy-app ./run_gates.sh before
#    expected: gate1 FAIL (CVEs, SQLi), gate2 FAIL (token, password, SSN, PII in logs), gate4 FAIL (5/9 cases)

# 3. swap in the FIXED sample app
docker compose -f samples/docker-compose.yml --profile legacy down
docker compose -f samples/docker-compose.yml --profile modernized up -d --build

# 4. enforced run + report
SKIP_SONAR=1 TARGET_DIR=./samples/modernized-app ./run_gates.sh after
./run_gates.sh compare before after        # -> results/comparison.md
cat results/before/feedback.md             # what Claude would be told to fix

# 5. now with SonarQube (needs ~4 GB RAM for Docker Desktop; first start takes 2-5 min). Drop SKIP_SONAR.
TARGET_DIR=./samples/legacy-app ./run_gates.sh before
./run_gates.sh down                        # stop SonarQube when finished (UI: http://localhost:9000, admin / Gates#Admin123456)
```
Windows: use Git Bash or WSL; `TARGET_DIR` can be a Windows path in quotes, e.g. `TARGET_DIR="C:/work/hms" ./run_gates.sh before`.

## How to use it on the real HMS (modernizer teammate)

1. Put/keep the HMS **running** (10 services published on ports) and list them in `evals/services.yaml`.
   If Jenkins/compose networking is used, put container names (`http://patient-service:8080`) instead of `host.docker.internal`.
2. Write evals: copy `evals/cases/patient-service.yaml` once per service (health, main CRUD flows, critical business rules, security rules). Mark must-work cases `critical: true`. Supported checks: `status`, `json` (equals / `exists` / `absent` / `type` / `min_len` / `contains` / `gt` / `regex`), `body_contains`, `max_ms`, `save` + `{{var}}` chaining.
3. Baseline: `TARGET_DIR=/path/to/hms ./run_gates.sh before`
4. Loop (see `Jenkinsfile.example`):
   ```bash
   ./run_gates.sh cost-reset
   ./run_gates.sh cost-check || exit        # exit 42 => stop, budget/iteration cap hit
   CAP=$(./run_gates.sh cost-remaining)     # pass to Claude so one call can't overspend
   claude -p "Modernize... fix everything in quality-gates/results/after/feedback.md" \
          --output-format json --max-budget-usd "$CAP" | ./run_gates.sh cost-record modernize
   # rebuild + restart the app, then
   ./run_gates.sh after                     # exit 0 => thresholds reached, stop looping
   ```
5. Final: `./run_gates.sh compare before after` and archive `results/`.

## Gate details

* **Gate 1** - `sonar.py bootstrap` waits for SonarQube, sets the admin password and makes a token automatically (no manual UI setup); scanner runs with `qualitygate.wait=true`; measures come from the Web API. Semgrep (`p/default` ruleset, ERROR=high, WARNING=medium) and Trivy (`vuln,misconfig`; HIGH/CRITICAL, deduped) add SAST and dependency/Dockerfile findings. For Java, point `-Dsonar.java.binaries` in `run_gates.sh` at the compiled classes folder (default `.` works but is less precise); for coverage add a report property and enable `sonar_coverage_pct` in thresholds.
* **Gate 2** - Gitleaks (history ignored, current tree only) + regex scanner with Luhn validation for cards, placeholder filtering (`${VAR}`, env lookups), masked output (never prints full secrets/PII). Fake data should use `@example.com` etc. (see `config/pii_allowlist.yaml`). Want ML-grade PII (names, addresses)? Add Microsoft Presidio as another container and append its count to `gate2.py` - the contract stays the same.
* **Gate 3** - No guessing: every Claude call is appended to `results/cost_ledger.jsonl` (cost + tokens from Claude's JSON output). Limits: total USD, iterations, USD per call. `cost-check` gives the loop its stop signal.
* **Gate 4** - Evals wait up to 60 s (`EVAL_WAIT_SECONDS`) for services to answer; unreachable services fail their cases and raise `tool_errors`, so a down app can never look like a pass.

## Notes / troubleshooting

* A scanner that fails to run counts as `tool_errors > 0` -> gate fails (enforced phases). Nothing is silently skipped, except with `SKIP_SONAR=1` (use it only for quick local tests, not in the real pipeline).
* SonarQube stuck/exit on Linux/WSL: `sysctl -w vm.max_map_count=262144`. Give Docker Desktop >= 4 GB.
* Trivy/Semgrep download rule/vulnerability DBs on first run (internet needed; Trivy DB is cached in a volume).
* On Linux, files in `results/` are root-owned (containers run as root); clean with `sudo rm -rf results/*`.
* Sample dependency pins are illustrative; if Trivy flags the "modernized" sample on your date, bump the versions.
