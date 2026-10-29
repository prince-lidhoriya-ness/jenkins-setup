#!/usr/bin/env bash
# Usage:
#   ./run_gates.sh <phase> [gates]     e.g. ./run_gates.sh before     ./run_gates.sh after 1,2,4
#   ./run_gates.sh compare before after
#   ./run_gates.sh cost-check | cost-remaining | cost-reset | cost-record [label]   (stdin = claude --output-format json)
#   ./run_gates.sh down                stop SonarQube
# Env: TARGET_DIR (code to scan, default samples/legacy-app)  SKIP_SONAR=1 (fast mode)  SONAR_PROJECT_KEY
set -uo pipefail
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'           # Git Bash on Windows: don't mangle /src paths
cd "$(dirname "${BASH_SOURCE[0]}")"
: "${TARGET_DIR:=./samples/legacy-app}" "${SONAR_PROJECT_KEY:=hms}" "${SKIP_SONAR:=0}"
export TARGET_DIR SONAR_PROJECT_KEY SKIP_SONAR
run() { docker compose run -T --rm "$@"; }
py()  { run runner python "$@"; }

case "${1:-}" in
  compare)        shift; py gates/compare.py "$@"; exit $? ;;
  cost-check)     py gates/cost.py check; exit $? ;;
  cost-remaining) py gates/cost.py remaining; exit $? ;;
  cost-reset)     py gates/cost.py reset; exit $? ;;
  cost-record)    py gates/cost.py record-claude --label "${2:-modernize}"; exit $? ;;
  down)           docker compose down; exit $? ;;
  ""|-h|--help)   sed -n '2,8p' "$0"; exit 0 ;;
esac

PHASE="$1"; GATES="${2:-1,2,3,4}"
has() { [[ ",$GATES," == *",$1,"* ]]; }
rm -rf "results/$PHASE"; mkdir -p "results/$PHASE/raw"
RAW="results/$PHASE/raw"; echo ">> phase=$PHASE gates=$GATES target=$TARGET_DIR"
docker compose build runner >/dev/null || { echo "docker build failed"; exit 2; }

if has 1; then
  echo ">> GATE 1: static analysis & security"
  if [ "$SKIP_SONAR" != 1 ]; then
    docker compose up -d sonarqube && py gates/sonar.py bootstrap &&
    SONAR_TOKEN="$(cat results/.sonar_token)" run sonar-scanner sonar-scanner \
      -Dsonar.projectKey="$SONAR_PROJECT_KEY" -Dsonar.sources=. -Dsonar.working.directory=/tmp/.scannerwork \
      -Dsonar.qualitygate.wait=true -Dsonar.qualitygate.timeout=900 -Dsonar.scm.disabled=true \
      -Dsonar.java.binaries=. -Dsonar.exclusions='**/node_modules/**,**/target/**,**/build/**,**/*.min.js' ;
    py gates/sonar.py collect --phase "$PHASE"      # scanner exit code ignored: a failed Sonar gate is data, not a crash
  fi
  run semgrep semgrep scan --config p/default --metrics=off --json --output "/results/$PHASE/raw/semgrep.json" /src && touch "$RAW/semgrep.ok"
  run trivy fs --scanners vuln,misconfig --format json --output "/results/$PHASE/raw/trivy.json" /src && touch "$RAW/trivy.ok"
  py gates/gate1.py --phase "$PHASE"
fi
if has 2; then
  echo ">> GATE 2: secrets, credentials, PII"
  run gitleaks detect --no-git --source /src --report-format json --report-path "/results/$PHASE/raw/gitleaks.json" --exit-code 0 --redact && touch "$RAW/gitleaks.ok"
  py gates/gate2.py --phase "$PHASE"
fi
if has 3; then echo ">> GATE 3: Claude cost"; py gates/gate3.py --phase "$PHASE"; fi
if has 4; then echo ">> GATE 4: functional evals"; py gates/gate4.py --phase "$PHASE"; fi

py gates/summary.py --phase "$PHASE" --gates "$GATES"
