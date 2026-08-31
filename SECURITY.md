> **This is an evaluation fork. Report vulnerabilities upstream.**
>
> This repository is a public fork of
> [Panniantong/Agent-Reach](https://github.com/Panniantong/Agent-Reach) and
> ships no releases of its own. A vulnerability in Agent Reach affects
> upstream and every downstream user, so it belongs in upstream's private
> advisory flow:
>
> 👉 **[Report to upstream](https://github.com/Panniantong/Agent-Reach/security/advisories/new)**
>
> Two caveats specific to this fork:
>
> - This fork can lag upstream. Before reporting, check whether the issue is
>   already fixed upstream — the `upstream-drift` workflow reports how many
>   commits behind this snapshot is, and `main` here is not a security-supported
>   distribution.
> - If a problem exists **only** in this fork's own files (`README.md`,
>   `FORK_AUDIT.md`, `.github/`, `scripts/fork-audit.sh`), open a private
>   advisory on this repository instead.
>
> The policy below is upstream's, kept verbatim.

---

# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest  | ✅ Yes    |

## Reporting a Vulnerability

If you discover a security vulnerability in Agent-Reach, please report 
it responsibly by using GitHub's private security advisory feature:

👉 **[Report a vulnerability](https://github.com/Panniantong/Agent-Reach/security/advisories/new)**

Please do NOT open a public GitHub issue for security vulnerabilities.

## What to Include

- Description of the vulnerability
- Steps to reproduce
- Affected versions
- Potential impact
- Suggested fix (if any)

## Response Timeline

- Acknowledgement within **48 hours**
- Status update within **7 days**
- Fix timeline communicated within **14 days**

## Scope

The following are considered in scope:
- Authentication and authorization bypass
- Remote code execution
- Path traversal / arbitrary file read
- Server-Side Request Forgery (SSRF)
- Injection vulnerabilities (SQL, command, prompt)
- Sensitive data exposure

## Out of Scope

- Vulnerabilities in dependencies (report to the dependency maintainer)
- Social engineering attacks
- Denial of service via resource exhaustion

## Credits

We appreciate responsible disclosure and will credit researchers 
in our release notes unless anonymity is requested.
