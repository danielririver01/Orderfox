# Dependency Vulnerability Scanning (Velzia)

## Approach

OWASP Dependency-Check requires downloading the full NVD database (~367k records, very slow without an API key)
and has weak Python/Node support. For Velzia (Python + Node stack) we use the faster, more accurate native tools:

- **Python** → [`pip-audit`](https://pypi.org/project/pip-audit/) (queries OSV / PyPI advisory DB)
- **Node**   → `npm audit` (built-in, queries GitHub Advisory DB)

> OWASP Dependency-Check 12.1.0 is installed at `C:\tools\dependency-check` (needs Java 17 JRE) but is NOT the
> active scanner due to the NVD download cost. Use it only if an NVD API key is provided.

## Usage

```powershell
# Python
.venv\Scripts\pip-audit.exe --strict -r requirements-dev.txt --desc on

# Node
npm audit
npm audit fix        # applies non-breaking fixes (bumps astro, etc.)
```

## CI gate (VLZ-27)

The workflow installs the pinned development requirements and blocks on:

```bash
pip-audit --strict -r requirements-dev.txt --desc on
```

Bandit runs separately as an informative scan; the Windows-only security
suite remains outside this CI workflow and is tracked in VLZ-19.

## Latest Scan (2026-07-20)

### Python — 39 vulnerabilities / 12 packages

| Package | Installed | Fixed | Nota |
|---------|-----------|-------|------|
| pyjwt | 2.12.1 | 2.13.0 | JWT — relevante a auditoría |
| authlib | 1.6.11 | 1.6.12 | OAuth/OIDC |
| cryptography | 48.0.1 | 50.0.1 | OpenSSL estático |
| click | 8.3.1 | 8.3.3 | command injection |
| pillow | 12.1.1 | 12.3.0 | múltiples (8 CVEs) |
| urllib3 | 2.6.3 | 2.7.0 | SSRF / CORS |
| idna | 3.11 | 3.15 | |
| soupsieve | 2.8.3 | 2.8.4 | |
| filelock | 3.16.1 | 3.20.3 | TOCTOU |
| mako | 1.3.10 | 1.3.12 | path traversal (Windows) |
| (otros) | | | ver `pip-audit` completo |

### Node — RESUELTO (0 high)

El `npm audit` inicial reportó `astro <=6.4.5` vulnerable en el **package.json raíz**.
Investigando se encontró que ese `astro@5` era un **dependencia muerta** en la raíz:
el menú público real vive en `astro/` y ya usa `astro@7.0.7` (0 vulnerabilidades).

**Fix aplicado:** se eliminaron las deps muertas `astro` y `@astrojs/tailwind` del
package.json raíz (se mantienen `@tailwindcss/cli` + `tailwindcss` que usa `build:css`).
Tras `npm install` + `npm audit` en raíz → **found 0 vulnerabilities**.

> No fue necesario ningún major bump breaking: la app desplegada nunca estuvo en riesgo.

## Fix

```powershell
# Node (non-breaking)
npm audit fix

# Python: update the pinned requirements, then reinstall
pip install -r requirements-dev.txt
# The CI gate is the canonical check:
pip-audit --strict -r requirements-dev.txt --desc on
```
