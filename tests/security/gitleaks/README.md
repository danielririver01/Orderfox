# Gitleaks — Secret Scanning

## Install

```powershell
winget install Gitleaks.Gitleaks
```

Version: 8.30.1

## How it works

Gitleaks scans the git history and working tree for secrets: API keys, passwords, tokens, private keys. It uses the built-in rule set (AWS, GitHub, JWT, OpenAI, etc.) extended by `.gitleaks.toml`.

## Usage

### Pre-commit hook (automatic)

The hook at `.git/hooks/pre-commit` blocks any commit that introduces a secret (runs `gitleaks protect --staged`).

### Manual scan of full history

```powershell
npm run audit:gitleaks        # SARIF report -> tests/security/reports/gitleaks.sarif
npm run audit:secrets         # human-readable, redacted output
```

Or directly:

```bash
gitleaks detect --source . --config .gitleaks.toml --redact
```

## Latest Scan (2026-07-20)

- 75 commits scanned (~4.91 MB)
- **Result: no leaks found** ✅

## Configuration

`.gitleaks.toml`:
- `useDefault = true` — built-in rules
- `allowlist.paths` — ignores `node_modules/`, `.venv/`, `tests/security/`, `docs/`, `*.md`
- Custom rule `velzia-test-keys` — allows intentionally fake keys (`sk-test-`, `sk-demo-`, etc.)

## False positives

Add an exception to the `allowlist` in `.gitleaks.toml`, or mark a single finding with a
inline comment `# gitleaks:allow` in the source file.

## Bypass (emergency only)

```bash
git commit --no-verify
```
