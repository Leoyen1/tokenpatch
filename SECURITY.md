# Security Policy

## Supported Versions

The current `main` branch is supported for security updates.

## Reporting a Vulnerability

Please do not open public issues for sensitive vulnerabilities.

1. Send details to your private security contact channel for this project.
2. Include reproduction steps, affected versions/commit, and impact scope.
3. If possible, include a minimal patch or mitigation suggestion.

We will acknowledge receipt as quickly as possible, triage severity, and provide a remediation timeline.

## Security Boundaries

- Local open-source client (`tokenpatch` CLI) runs in user environment and uses user-provided model keys in BYOK mode.
- Hosted gateway deployments must keep provider keys (for example DeepSeek) server-side only.
- Production deployments should enable rate limits, quota limits, freeze-on-anomaly controls, and compliance filtering.
