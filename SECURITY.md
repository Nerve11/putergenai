# Security Policy

Thank you for helping keep `putergenai` and its users safe.

## Supported Versions

We actively provide security fixes for the versions below. Older versions should be upgraded.

| Version        | Supported |
|----------------|-----------|
| 0.1.6          | ✅        |
| 0.1.3          | ❌        |
| 0.1.1          | ❌        |
| 0.1.x (latest) | ❌        |
| < 0.1.1        | ❌        |

> Note: Previously listed `1.6` referred to `0.1.6`. This has been corrected.

## Reporting a Vulnerability

If you believe you’ve found a security issue, please email:

- **contact@fnbubbles420.org** (preferred)
- Alternatively, open a **GitHub private security advisory** on the repository.

Please include:

1. Affected version(s) and environment
2. Reproduction steps or proof-of-concept
3. Impact assessment (e.g., data exposure, RCE, DoS)
4. Any suggested fixes or workarounds

We aim to acknowledge reports within **72 hours** and provide a status update within **7 days**.

## Disclosure Policy

- We follow **coordinated disclosure**.
- We’ll work with you to validate and fix the issue.
- We prefer a **14–30 day** embargo window before public disclosure, depending on severity and patch complexity.
- We will credit reporters who request attribution (unless you prefer to remain anonymous).

## Dependency Security

`putergenai` depends on third-party libraries. We:
- Pin or minimum-pin versions to receive upstream security patches.
- Monitor advisories (PyPI, GitHub Advisories, NVD).
- Issue prompt releases when upstream vulnerabilities affect our package.

If a vulnerability affects a dependency only, please still report it—links to upstream issues are helpful.

## Security Updates

- Critical fixes will be backported to the supported 0.1.x line when feasible.
- Release notes will highlight security-impacting changes.

## GPG / Integrity (optional)

If you need signed artifacts, contact us. We can provide signed wheels/SDists on request while we finalize our signing process.

---

**Thank you** for helping us protect the community.
