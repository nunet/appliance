# Dependency Vulnerability Management Policy

## Overview

This project adopts a controlled and risk-based approach to managing third-party dependency vulnerabilities.

The goal is to:
- Maintain build stability and reproducibility
- Ensure timely remediation of relevant security risks
- Avoid disruptions caused by external advisory database changes

## Vulnerability Classification

Vulnerabilities are handled according to their severity:

| Severity  | Description                      | Action                      |
|----------|-----------------------------------|-----------------------------|
| CRITICAL | High impact, exploitable remotely | Blocks pipeline             |
| HIGH     | Significant risk                  | Must be fixed within SLA    |
| MEDIUM   | Moderate risk                     | Tracked and prioritized     |
| LOW      | Minimal impact                    | Logged for awareness        |

## CI/CD Enforcement Rules

1. Pull Requests / Standard Pipelines
- Only CRITICAL vulnerabilities block the pipeline
- HIGH and below:
    - Do not block builds
    - Are reported in logs

2. Scheduled Security Audit
- A full security audit runs on a scheduled basis (daily or weekly):
    - Uses strict mode (--strict)
    - Fails on any known vulnerability
    - Results must be reviewed and acted upon

## Remediation SLAs

| Severity | Time to Fix   |
| -------- | ------------- |
| CRITICAL | 24–48 hours   |
| HIGH     | Up to 7 days  |
| MEDIUM   | Up to 30 days |
| LOW      | Best effort   |

## Exceptions (Allowlisting)

Vulnerabilities may be temporarily ignored if:
- No fix is available, or
- The vulnerability does not affect the runtime context

Requirements:
- Must include justification
- Must include expiration or review date

Example:
```
pip-audit --ignore-vuln CVE-XXXX-YYYY
```

## Runtime Context Consideration

Not all vulnerabilities are equally relevant.

Examples:
- Dev-only tools (e.g., build systems, bundlers)
- Test dependencies

These may be deprioritized if:
- Not included in production artifacts
- Not exposed in runtime environments

## Dependency Management

- Dependencies should be version-pinned
- Regular updates must be performed:
    - Weekly or biweekly recommended
- Automated tools (e.g., Renovate, Dependabot) are encouraged

## Responsibilities

- Developers:
    - Review vulnerabilities affecting their changes
    - Address CRITICAL issues immediately

- Maintainers:
    - Review scheduled audit failures
    - Ensure SLA compliance

## Notes

- Security tooling relies on external advisory databases that change over time
- Pipeline stability must not depend on real-time external updates
- Security must be actively managed, not passively enforced

