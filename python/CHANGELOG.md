# Changelog

Alle merkbare endringer i `firmaradar-mcp` (Python-pakken) dokumenteres her.

Formatet følger [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
og prosjektet bruker [SemVer](https://semver.org/spec/v2.0.0.html).

Versjonene følger n8n-pakka (`n8n-nodes-firmaradar`) — felles
version-bumps gjør det enkelt for kundene å holde MCP-serveren og
workflow-nodene på samme funksjonalitets-baseline.

---

## [Unreleased]

### Added

- **`firmaradar_add_company_monitoring` tool.** Add a Norwegian company (by
  9-digit orgnr) to the user's company-monitoring list. New targets monitor
  all announcement categories by default; `ip_alerts` (default `true`) also
  enables IP-change alerts when the account has the IP-monitoring add-on.
  Backed by `POST /monitoring/targets/add` (now accepts a JSON body).

---

## [0.5.1] — 2026-06-01

### Removed

- **`get_skattelister` tool removed.** Skatteetaten denied API access
  (case SSV-5198) for the underlying tax-list data, and confidential tax
  data is not disclosable to a third-party service. The tool was
  marketplace-hidden and compliance-gated (returned 403), so there is no
  impact on live consumers. The capability may return later via a
  re-architected, credit-bureau-backed flow.

## [0.5.0] — 2026-06-01

### Added

- New tools: `start_aml_report` / `get_aml_report` (async AML-report
  path), `list_nace_codes`, `subscribe_nace`, `list_my_subscriptions`,
  `delete_subscription` (NACE-industry monitoring), and `convert_nok`
  (NOK → EUR/USD/GBP/SEK/DKK).
- Tool titles + `ToolAnnotations` (readOnly / destructive / idempotent /
  openWorld hints) on every tool — required by the connector directories.

### Changed

- **OAuth / reauth hardening.** `mcp_remote` validates the Bearer token
  proactively against `/oauth/introspect` (fail-open on transient
  errors); refresh-token TTL is a 30-day sliding window. The legacy
  `oauth_shim` was removed.

## [0.3.2] — 2026-05-27

### Changed

- **Client-identification header renamed from `X-MCP-Client` to
  `X-FR-Client`** (Firmaradar Client). The MCP server now sends
  `X-FR-Client: firmaradar-mcp/<version>` on every backend request.
  The backend recognizes both headers — legacy `X-MCP-Client` keeps
  working unchanged — but the new name is preferred and the legacy
  one is on a 6-month sunset (planned removal evaluated when
  legacy-traffic drops below 1%). See
  `docs/arkitektur/CLIENT_IDENTIFICATION_HEADER.md` in the private
  repo for the full rationale. Pure additive change on the wire;
  no breaking impact on any caller, including older `firmaradar-mcp`
  installs continuing to send `X-MCP-Client`.

---

## [0.3.1] — 2026-05-27

### Fixed

- **`firmaradar-mcp --help` and `--version` now work without
  `FIRMARADAR_API_KEY` set.** Previously these flags crashed with
  `ValueError: Missing required environment variable FIRMARADAR_API_KEY`
  because the client was instantiated unconditionally before argparse
  ran. Now we short-circuit on `-h`/`--help`/`--version`/`-V` before
  any client construction.

### Added

- `_HELP_TEXT` constant with usage examples for Claude Desktop config,
  env-var documentation, and links to firmaradar.no docs.

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
