# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Scope

**In scope:** schemas, validator, IPC protocol (`frames.py`, `peer.py`), conformance tests, CI configuration.

**Out of scope:** third-party adapter examples (`examples/`), documentation-only issues, feature requests.

## Reporting a Vulnerability

**Do not open a public issue for security vulnerabilities.**

Email **security@node1.ai** with:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will:
1. **Acknowledge** within 48 hours
2. **Triage** and confirm the issue within 5 business days
3. **Develop and release** a fix, typically within 30 days
4. **Publish** a security advisory after the fix is available

## Coordinated Disclosure

We follow a **90-day coordinated disclosure** policy. If we have not released a fix within 90 days of your report, you may disclose the vulnerability publicly. We ask that you give us reasonable notice before doing so.

## Safe Harbor

We consider security research conducted in good faith to be authorized. We will not pursue legal action against researchers who:
- Act in good faith and avoid privacy violations, data destruction, or service disruption
- Report vulnerabilities promptly and provide sufficient detail to reproduce
- Do not exploit vulnerabilities beyond what is necessary to demonstrate the issue

Reporters who follow responsible disclosure will be credited in the security advisory (unless they prefer anonymity).
