# Changelog

Alle merkbare endringer i `firmaradar-mcp` (Python-pakken) dokumenteres her.

Formatet følger [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
og prosjektet bruker [SemVer](https://semver.org/spec/v2.0.0.html).

Versjonene følger n8n-pakka (`n8n-nodes-firmaradar`) — felles
version-bumps gjør det enkelt for kundene å holde MCP-serveren og
workflow-nodene på samme funksjonalitets-baseline.

---

## [0.3.0] — 2026-05-27

Første offentlige release på PyPI. Eksponerer 17 read-only MCP-verktøy
mot Firmaradar-backenden via stdio-server (Cursor, Codex, Claude
Desktop) og remote-HTTP/OAuth-server (Claude Web/Mobile).

### Added

- **Console-script `firmaradar-mcp`** — entry point i
  `pyproject.toml [project.scripts]` peker på
  `firmaradar_mcp.server:main`. Etter `pip install firmaradar-mcp` kan
  agent-klienten kalle binæren direkte uten å gå via
  `python -m firmaradar_mcp.server`.
- **Console-script `firmaradar-mcp-remote`** — ASGI-versjon for
  self-hosting av OAuth 2.0 + DCR-flow for Claude Web/Mobile. Krever
  ekstra-en `pip install 'firmaradar-mcp[remote]'` for å trekke inn
  `starlette` + `uvicorn`.
- **GitHub Actions publish-workflow** med OIDC-basert Trusted Publishing
  og Sigstore PEP 740-attestations —
  `.github/workflows/publish.yml`. Trigges på tag `python-v*.*.*`.
- **PyPI-metadata på plass:** `Project-URL`-felt for Homepage,
  Documentation, Repository, Issues og Changelog. Klassifiserings-tags
  for Beta, Norge/finans-domene og Python 3.10–3.13.
- **Sdist-build inkluderer README + tests** via eksplisitt
  `[tool.hatch.build.targets.sdist] include = [...]` — uten dette
  faller `../README.md` ut av tarballen siden Hatchling default kun
  henter filer under pyproject-roten.

### Changed

- **Versjon bumpet 0.1.0a0 → 0.3.0** for å matche n8n-pakka
  (`n8n-nodes-firmaradar@0.3.0`) — felles release-cadence.
- **Python-baseline senket fra >=3.11 til >=3.10.** Hele kodebasen
  bruker `from __future__ import annotations` så PEP 585-syntaks
  (`list[X]`, `dict[X, Y]`) fungerer trygt på 3.10 også. Bredere
  baseline → enklere for kunder å installere uten å først bumpe sin
  egen Python.
- **License-felt:** Privat repo har `Proprietary`. `sync_mcp_public.sh`
  patcher dette til `Apache-2.0` når pakken speiles til
  `Tiwas/firmaradar-mcp` — slik forblir public-pakka Apache-2.0 mens
  intern dev ikke gir feil signal om at koden er offentlig allerede.
- **`_SERVER_VERSION`** i `server.py` bumpet fra `"0.1.0"` til
  `"0.3.0"` slik at MCP-klienter ser riktig server-versjon i
  init-handshaken.

### Documentation

- README oppdatert med `pip install firmaradar-mcp`-eksempel og bekreftelse
  på at `firmaradar-mcp`-konsollkommandoen kan kalles direkte fra
  agent-konfigen (Cursor `~/.cursor/mcp.json`, Codex
  `~/.codex/config.toml`).
- CHANGELOG opprettet (denne filen).

---

## [0.1.0a0] — 2026-05-25 *(internt skjelett, ikke PyPI-publisert)*

Initial skjelett-versjon, brukt internt under MCP v0.1-planlegging.
17 verktøy implementert mot REST-backenden, men aldri publisert til
PyPI — overskredet av 0.3.0 i samme commit-rekke.

---

[0.3.0]: https://github.com/Tiwas/firmaradar-mcp/releases/tag/python-v0.3.0
