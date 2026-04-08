#!/usr/bin/env bash
set -euo pipefail

# Audit and remediate frontend npm vulnerabilities with a release-age guardrail.
#
# Default mode:
#   - install with frozen lockfile
#   - run strict prod audit
#   - print remediation candidates and whether they satisfy minimum release age
#
# --apply-fixes mode:
#   - for candidates with available fixes and sufficient release age,
#     write/update pnpm overrides in frontend/package.json
#   - run install + strict audit to validate

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FRONTEND_DIR="${FRONTEND_DIR:-$ROOT/frontend}"
MIN_RELEASE_AGE_DAYS="${MIN_RELEASE_AGE_DAYS:-7}"
PNPM_VERSION="${PNPM_VERSION:-10.33.0}"
AUDIT_LEVEL="${AUDIT_LEVEL:-high}"
APPLY_FIXES=0

usage() {
  cat <<'EOF'
Usage:
  deploy/scripts/update_frontend_deps.sh [--apply-fixes] [--min-release-age-days N] [--audit-level LEVEL]

Options:
  --apply-fixes               Apply safe fixes as pnpm overrides in frontend/package.json.
  --min-release-age-days N    Minimum age in days for auto-applied versions (default: 7).
  --audit-level LEVEL         Audit threshold (default: high).
  -h, --help                  Show this help text.

Examples:
  # Audit + recommendations only
  deploy/scripts/update_frontend_deps.sh

  # Apply safe overrides (meeting age gate), then validate
  deploy/scripts/update_frontend_deps.sh --apply-fixes --min-release-age-days 14
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply-fixes)
      APPLY_FIXES=1
      shift
      ;;
    --min-release-age-days)
      MIN_RELEASE_AGE_DAYS="$2"
      shift 2
      ;;
    --audit-level)
      AUDIT_LEVEL="$2"
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

if [[ ! -d "$FRONTEND_DIR" ]]; then
  echo "Frontend directory not found: $FRONTEND_DIR" >&2
  exit 1
fi

WORK_DIR="$(mktemp -d /tmp/frontend-deps-audit.XXXXXX)"
AUDIT_JSON="$WORK_DIR/audit.json"
REMEDIATION_JSON="$WORK_DIR/remediation.json"
cleanup() {
  rm -rf "$WORK_DIR"
}
trap cleanup EXIT

echo "Preparing pnpm@$PNPM_VERSION via Corepack..."
corepack prepare "pnpm@${PNPM_VERSION}" --activate >/dev/null

echo "Installing frontend dependencies with frozen lockfile..."
(
  cd "$FRONTEND_DIR"
  corepack pnpm install --frozen-lockfile >/dev/null
)

echo "Running pnpm audit (prod, level=$AUDIT_LEVEL)..."
set +e
(
  cd "$FRONTEND_DIR"
  corepack pnpm audit --prod --audit-level="$AUDIT_LEVEL" --json > "$AUDIT_JSON"
)
AUDIT_STATUS=$?
set -e

python3 - "$AUDIT_JSON" "$REMEDIATION_JSON" "$MIN_RELEASE_AGE_DAYS" "$AUDIT_LEVEL" <<'PY'
import json
import re
import subprocess
import sys
from datetime import datetime, timezone

audit_path = sys.argv[1]
remediation_path = sys.argv[2]
min_age_days = int(sys.argv[3])
audit_level = (sys.argv[4] or "high").lower()

severity_rank = {"info": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}
threshold = severity_rank.get(audit_level, 3)

raw = open(audit_path, "r", encoding="utf-8").read().strip()
if not raw:
    print("No audit output received.")
    with open(remediation_path, "w", encoding="utf-8") as f:
        json.dump({"candidates": []}, f)
    sys.exit(0)

try:
    data = json.loads(raw)
except json.JSONDecodeError:
    # Some pnpm versions can emit additional lines; try last JSON object line.
    line = ""
    for entry in reversed(raw.splitlines()):
        entry = entry.strip()
        if entry.startswith("{") and entry.endswith("}"):
            line = entry
            break
    if not line:
        print("Unable to parse pnpm audit JSON output.")
        with open(remediation_path, "w", encoding="utf-8") as f:
            json.dump({"candidates": []}, f)
        sys.exit(0)
    data = json.loads(line)

def _parse_fix_version_from_advisory(vuln: dict) -> str | None:
    patched_versions = str(vuln.get("patched_versions") or "").strip()
    if patched_versions:
        matches = re.findall(r">=?\s*([0-9][0-9A-Za-z.\-+]*)", patched_versions)
        if matches:
            return matches[0]

    recommendation = str(vuln.get("recommendation") or "").strip()
    if recommendation:
        match = re.search(r"([0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.\-]+)?)", recommendation)
        if match:
            return match.group(1)
    return None

def npm_version_publish_time(package: str, version: str):
    try:
        cp = subprocess.run(
            ["npm", "view", package, "time", "--json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except Exception:
        return None
    if cp.returncode != 0 or not cp.stdout.strip():
        return None
    try:
        payload = json.loads(cp.stdout)
    except Exception:
        return None
    ts = payload.get(version) if isinstance(payload, dict) else None
    if not isinstance(ts, str) or not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None

advisories = data.get("advisories", {}) if isinstance(data, dict) else {}
vulnerabilities = data.get("vulnerabilities", {}) if isinstance(data, dict) else {}

# pnpm can return "advisories" keyed by id (legacy npm-audit style), while other tools
# can return "vulnerabilities" keyed by package. Support both and normalize to candidates.
normalized: dict[str, dict] = {}

if isinstance(advisories, dict) and advisories:
    for advisory in advisories.values():
        if not isinstance(advisory, dict):
            continue
        pkg = str(advisory.get("module_name") or "").strip()
        if not pkg:
            continue
        sev = str(advisory.get("severity") or "").lower()
        if severity_rank.get(sev, -1) < threshold:
            continue
        fix_version = _parse_fix_version_from_advisory(advisory)
        key = pkg.lower()
        current = normalized.get(key)
        if current is None:
            normalized[key] = {
                "package": pkg,
                "severity": sev,
                "fix_name": pkg,
                "fix_version": fix_version,
                "reason": "",
            }
        else:
            # Keep highest severity and a discovered fix version if previous did not have one.
            if severity_rank.get(sev, -1) > severity_rank.get(str(current.get("severity")), -1):
                current["severity"] = sev
            if not current.get("fix_version") and fix_version:
                current["fix_version"] = fix_version
else:
    for pkg, vuln in (vulnerabilities.items() if isinstance(vulnerabilities, dict) else []):
        if not isinstance(vuln, dict):
            continue
        sev = str(vuln.get("severity") or "").lower()
        if severity_rank.get(sev, -1) < threshold:
            continue
        fix = vuln.get("fixAvailable")
        fix_name = pkg
        fix_version = None
        if isinstance(fix, dict):
            fix_name = fix.get("name") or pkg
            fix_version = fix.get("version")
        if not isinstance(fix_name, str):
            fix_name = str(pkg)
        if isinstance(fix_version, str):
            fix_version = fix_version.strip() or None
        normalized[pkg.lower()] = {
            "package": pkg,
            "severity": sev,
            "fix_name": fix_name,
            "fix_version": fix_version,
            "reason": "",
        }

if not normalized:
    print("No production vulnerabilities found at requested threshold.")
    with open(remediation_path, "w", encoding="utf-8") as f:
        json.dump({"candidates": []}, f)
    sys.exit(0)

candidates = []
for entry in normalized.values():
    pkg = entry["package"]
    sev = entry["severity"]
    fix_name = entry["fix_name"]
    fix_version = entry["fix_version"]
    if not isinstance(fix_version, str) or not fix_version:
        candidates.append(
            {
                "package": pkg,
                "severity": sev,
                "fix_name": fix_name,
                "fix_version": None,
                "age_days": None,
                "age_ok": False,
                "reason": "No automatic fix version suggested by audit output.",
            }
        )
        continue

    published_at = npm_version_publish_time(fix_name, fix_version)
    age_days = None
    age_ok = False
    reason = ""
    if published_at is None:
        reason = "Could not determine publish time for fix version."
    else:
        age_days = (datetime.now(timezone.utc) - published_at).days
        age_ok = age_days >= min_age_days
        if not age_ok:
            reason = f"Fix version age {age_days}d is below policy threshold {min_age_days}d."

    candidates.append(
        {
            "package": pkg,
            "severity": sev,
            "fix_name": fix_name,
            "fix_version": fix_version,
            "age_days": age_days,
            "age_ok": age_ok,
            "reason": reason,
        }
    )

print("Remediation candidates:")
for c in candidates:
    fix = f"{c['fix_name']}@{c['fix_version']}" if c["fix_version"] else "N/A"
    age = "unknown" if c["age_days"] is None else f"{c['age_days']}d"
    gate = "PASS" if c["age_ok"] else "BLOCK"
    print(f"  - {c['package']} ({c['severity']}): fix={fix}, age={age}, gate={gate}")
    if c["reason"]:
        print(f"      reason: {c['reason']}")

with open(remediation_path, "w", encoding="utf-8") as f:
    json.dump({"candidates": candidates}, f)
PY

if [[ "$APPLY_FIXES" -eq 0 ]]; then
  if [[ "$AUDIT_STATUS" -eq 0 ]]; then
    echo "No vulnerabilities found."
    exit 0
  fi
  echo "Vulnerabilities detected. Review candidates above or re-run with --apply-fixes." >&2
  exit "$AUDIT_STATUS"
fi

echo "Applying safe fixes as pnpm overrides..."
python3 - "$REMEDIATION_JSON" "$FRONTEND_DIR/package.json" <<'PY'
import json
import sys
from pathlib import Path

remediation_path = Path(sys.argv[1])
package_json_path = Path(sys.argv[2])

remediation = json.loads(remediation_path.read_text(encoding="utf-8"))
candidates = remediation.get("candidates", [])

safe = [c for c in candidates if c.get("fix_version") and c.get("age_ok")]
if not safe:
    print("No age-compliant auto-fix candidates found. No package.json changes made.")
    sys.exit(0)

pkg = json.loads(package_json_path.read_text(encoding="utf-8"))
pnpm = pkg.setdefault("pnpm", {})
overrides = pnpm.setdefault("overrides", {})
if not isinstance(overrides, dict):
    raise SystemExit("package.json has non-object pnpm.overrides; cannot auto-apply.")

for entry in safe:
    name = entry["fix_name"]
    version = entry["fix_version"]
    overrides[name] = version
    print(f"  - override set: {name}={version}")

package_json_path.write_text(json.dumps(pkg, indent=2) + "\n", encoding="utf-8")
print("Updated frontend/package.json overrides.")
PY

echo "Re-installing and validating strict audit..."
(
  cd "$FRONTEND_DIR"
  corepack pnpm install
  corepack pnpm audit --prod --audit-level="$AUDIT_LEVEL"
)
echo "Done."
