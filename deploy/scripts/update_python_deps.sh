#!/usr/bin/env bash
set -euo pipefail

# Update/audit pinned Python dependencies in requirements.txt.
#
# Default mode:
#   - run pip-audit in strict mode against the requirements file
#
# --apply-fixes mode:
#   - run audit and collect fixed versions from advisories
#   - update direct pinned requirements (name==version) in-place
#   - validate with pip install + strict pip-audit

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

REQUIREMENTS_FILE="${REQUIREMENTS_FILE:-$ROOT/backend/nunet_api/requirements.txt}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
APPLY_FIXES=0

usage() {
  cat <<'EOF'
Usage:
  deploy/scripts/update_python_deps.sh [--apply-fixes] [--requirements PATH] [--python PATH]

Options:
  --apply-fixes         Update vulnerable pinned direct requirements in-place.
  --requirements PATH   Path to requirements file (default: backend/nunet_api/requirements.txt).
  --python PATH         Python interpreter to use for tooling (default: python3).
  -h, --help            Show this help text.

Examples:
  # Audit only
  deploy/scripts/update_python_deps.sh

  # Audit + apply advisory-driven pin updates
  deploy/scripts/update_python_deps.sh --apply-fixes
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply-fixes)
      APPLY_FIXES=1
      shift
      ;;
    --requirements)
      REQUIREMENTS_FILE="$2"
      shift 2
      ;;
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
  echo "Requirements file not found: $REQUIREMENTS_FILE" >&2
  exit 1
fi

WORK_VENV="$(mktemp -d /tmp/python-deps-audit-venv.XXXXXX)"
AUDIT_JSON="$(mktemp /tmp/python-deps-audit-json.XXXXXX.json)"
cleanup() {
  rm -rf "$WORK_VENV" "$AUDIT_JSON"
}
trap cleanup EXIT

"$PYTHON_BIN" -m venv "$WORK_VENV"
# shellcheck disable=SC1090
source "$WORK_VENV/bin/activate"
python -m pip install --upgrade pip pip-audit >/dev/null

set +e
python -m pip_audit -r "$REQUIREMENTS_FILE" --strict --format json -o "$AUDIT_JSON"
AUDIT_STATUS=$?
set -e

if [[ "$APPLY_FIXES" -eq 0 ]]; then
  if [[ $AUDIT_STATUS -eq 0 ]]; then
    echo "No known vulnerabilities found."
    exit 0
  fi
  echo "Vulnerabilities detected. Re-run with --apply-fixes to auto-update direct pinned requirements." >&2
  exit $AUDIT_STATUS
fi

python - "$REQUIREMENTS_FILE" "$AUDIT_JSON" <<'PY'
import json
import re
import sys
from pathlib import Path
from packaging.version import Version, InvalidVersion

req_path = Path(sys.argv[1])
audit_path = Path(sys.argv[2])

audit = json.loads(audit_path.read_text())
deps = audit.get("dependencies", [])

line_re = re.compile(r"^\s*([A-Za-z0-9_.-]+)==([^\s#]+)\s*(#.*)?$")

lines = req_path.read_text().splitlines()
direct = {}
for i, line in enumerate(lines):
    m = line_re.match(line)
    if not m:
        continue
    pkg = m.group(1)
    direct[pkg.lower().replace("_", "-")] = (i, pkg, m.group(2), m.group(3) or "")

updates = []
skipped = []

for dep in deps:
    vulns = dep.get("vulns", [])
    if not vulns:
        continue
    norm = dep["name"].lower().replace("_", "-")
    if norm not in direct:
        skipped.append((dep["name"], "not a direct pinned requirement"))
        continue

    fix_versions = []
    for vuln in vulns:
        for fv in vuln.get("fix_versions", []):
            if fv:
                fix_versions.append(fv)

    if not fix_versions:
        skipped.append((dep["name"], "no fixed version published"))
        continue

    # Pick the highest fix version advertised across vulnerabilities.
    parsed = []
    for fv in set(fix_versions):
        try:
            parsed.append((Version(fv), fv))
        except InvalidVersion:
            parsed.append((None, fv))
    parsed.sort(key=lambda x: (x[0] is not None, x[0] if x[0] is not None else x[1]))
    target = parsed[-1][1]

    idx, pkg_token, current, suffix = direct[norm]
    if current == target:
        continue
    lines[idx] = f"{pkg_token}=={target}{suffix}"
    updates.append((pkg_token, current, target))

if not updates:
    print("No direct pinned requirements needed updates.")
else:
    req_path.write_text("\n".join(lines) + "\n")
    print("Updated requirements:")
    for name, old, new in updates:
        print(f"  - {name}: {old} -> {new}")

if skipped:
    print("\nSkipped:")
    for name, reason in skipped:
        print(f"  - {name}: {reason}")
PY

echo
echo "Validating updated requirements..."
python -m pip install -r "$REQUIREMENTS_FILE" >/dev/null
python -m pip_audit -r "$REQUIREMENTS_FILE" --strict
echo "Done."
