# Security Policy

## Supported Versions

AudioSure is alpha. Security fixes are applied to the latest release only.

| Version | Supported |
| --- | --- |
| 0.1.x | ✅ |
| < 0.1 | ❌ |

## Reporting a Vulnerability

Please **do not** report security vulnerabilities through public GitHub issues.

Report privately to **security@audiosure.dev** with:

- a description of the issue and its impact
- steps to reproduce, or a minimal project/bank file that triggers it
- affected version (Python package, PyPI version, or git commit) and platform/OS
- any suggested fix, if you have one

You should receive an acknowledgment within **3 business days**. We will work
with you on a coordinated disclosure: a fix and advisory are prepared first,
then released together. We ask for a **90-day disclosure window** before public
detail, shorter if a fix ships sooner.

Credit is given to reporters who wish it.

## Scope notes

AudioSure parses untrusted project files (Wwise `.bnk`/`.wwu`, FMOD `.bank`,
Unity YAML/meta, XML exports). Parser robustness is in scope: crashes, hangs,
and memory blowups from malformed or adversarial input should be reported.

Out of scope:

- vulnerabilities only in the upstream game engines/middleware themselves
- issues requiring a compromised local machine or malicious project already
  executed on the reporter's machine with their privileges (file reads are
  limited to the input project tree by design)
- the cloud runner simulation (no remote execution exists yet; see ROADMAP.md)

## Preferred disclosure

Encrypt sensitive reports with the maintainer's PGP key if the report includes
private project assets; otherwise plain email is fine.
