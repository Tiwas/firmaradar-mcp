<div align="center">

<img src="https://firmaradar.no/static/img/logo_nobg.png" alt="Firmaradar" width="220">

# Firmaradar MCP Server

**Slå opp norske selskaper, eierstrukturer, konsernhierarkier og roller direkte fra Claude, ChatGPT, Cursor, Codex, Gemini og andre MCP-kompatible agenter.**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![MCP](https://img.shields.io/badge/MCP-compatible-success.svg)](https://modelcontextprotocol.io)
[![Norsk data](https://img.shields.io/badge/data-norske%20selskaper-orange.svg)](https://firmaradar.no)

[**Koble til (anbefalt) →**](https://firmaradar.no/koble-til-agent) &nbsp;·&nbsp;
[Tool-katalog](#tool-katalog) &nbsp;·&nbsp;
[Quick-start](#quick-start) &nbsp;·&nbsp;
[Prising](https://firmaradar.no/prising) &nbsp;·&nbsp;
[Dokumentasjon](https://firmaradar.no/dokumentasjon)

</div>

---

## Hva er dette?

Firmaradar er Norges agentiske infrastruktur for selskapsdata. Denne MCP-serveren gir AI-agenten din direkte tilgang til:

- **2,1 millioner norske enheter** (BRREG-baseregister, oppdatert daglig)
- **Aksjeeierregisteret** fra Skatteetaten (eierandeler ned til person-nivå, opp gjennom hele konsernet)
- **Roller** (styre, daglig leder, prokura) med historikk
- **Regnskap** (årsregnskap, mellombalanser, signaler)
- **Kunngjøringer** fra Brønnøysund + KYC-flagg
- **AML/PEP-screening** med audit-trail
- **NACE-bransjeovervåkning** (varsling ved nystiftet selskap i bransje + geografi)

Bygd for produksjon: OAuth 2.0 + DCR (Claude Mobile + Web støttes), API-key-fallback (Cursor + Codex), [audit-logget per kall](https://firmaradar.no/dokumentasjon), [DSAR-eksport](https://firmaradar.no/dokumentasjon) og GDPR-pseudonymisering på serversiden.

---

## Quick-start

### Anbefalt — OAuth (Claude Web, Claude Mobile, Claude Desktop)

Bare lim inn server-URL i klienten din. Du autentiseres via firmaradar.no-konto og velger hvilken API-nøkkel agenten skal bruke.

```
https://mcp.firmaradar.no/mcp
```

Detaljert klient-for-klient-veiledning: **[firmaradar.no/koble-til-agent](https://firmaradar.no/koble-til-agent)**

### Cursor / Codex / annet — API-key via stdio

Hvis klienten din ikke støtter remote MCP, kan du kjøre serveren lokalt:

```bash
pip install firmaradar-mcp
```

`~/.cursor/mcp.json` eller `~/.codex/config.toml`:

```json
{
  "mcpServers": {
    "firmaradar": {
      "command": "firmaradar-mcp",
      "env": {
        "FIRMARADAR_API_KEY": "din-key-fra-firmaradar.no/min-side/api-keys",
        "FIRMARADAR_API_BASE": "https://firmaradar.no"
      }
    }
  }
}
```

Hent API-nøkkel: **[firmaradar.no/min-side/api-keys](https://firmaradar.no/min-side/api-keys)** (krever konto).

---

## Tool-katalog

17 tools, alle med samme schema i Python (`firmaradar-mcp` på PyPI) og TypeScript (`@firmaradar/mcp-server` på npm):

### Selskaps-oppslag
- `firmaradar_search_companies` — søk på navn eller orgnr
- `firmaradar_get_company` — full profil (orgform, NACE, ansatte, adresse, regnskap, eiere, roller)
- `firmaradar_get_company_ownership` — konsernhierarki opp og ned, eierandeler, person-nivå
- `firmaradar_get_company_roles` — styre, daglig leder, prokura (med fratrådt-historikk)
- `firmaradar_get_company_financials` — årsregnskap + nøkkeltall + signaler
- `firmaradar_get_company_announcements` — BRREG-kunngjøringer (vedtak, fusjoner, oppløsninger)
- `firmaradar_get_company_signals` — risikoflagg, KYC-flagg, insolvens
- `firmaradar_find_related_companies` — finn relaterte via eierskap, roller, adresse

### Person-oppslag (krever full-tier)
- `firmaradar_search_persons` — fuzzy navn-søk
- `firmaradar_get_person` — profil med adresse + fødselsår
- `firmaradar_get_person_companies` — alle selskaper personen eier eller har rolle i
- `firmaradar_get_person_roles` — alle aktive + historiske roller

### KYC / AML
- `firmaradar_check_aml_pep` — full AML/PEP-screening med sanksjonslister + audit-trail

### Bransje + overvåkning
- `firmaradar_list_companies_in_nace` — alle selskaper i en NACE-kode + geografisk filter
- `firmaradar_get_recent_changes` — endringer siste N dager for et orgnr
- `firmaradar_search_announcements` — fritekst-søk i BRREG-kunngjøringer
- `firmaradar_compare_companies` — sammenlikne flere selskaper side om side

Full API-referanse + eksempel-prompts: **[firmaradar.no/dokumentasjon](https://firmaradar.no/dokumentasjon)**

---

## Priser

Vi tilbyr én **fellesplattform-pris (99 kr/mnd)** + per-kall-prising. MCP-kallene har dedikert pakke (`mcp_full`) som er rabattert for agentbruk siden agenter genererer høyere volum enn manuelle API-integrasjoner.

Detaljert prising: **[firmaradar.no/prising](https://firmaradar.no/prising)**

---

## Hvorfor open source?

- **Transparens** — du kan lese hvert tool-stub og se nøyaktig hva agenten sender til Firmaradar.
- **Trust** — koden er Apache 2.0. Audit den selv, eller pin en spesifikk versjon.
- **Forks velkommen** — vi tar imot PR-er som forbedrer schemas eller legger til kompatibilitets-shims for nye klienter.

Backend (firmaradar.no) er proprietær fordi den eier data-pipeline + lisensiering mot Skatteetaten/Brønnøysund.

---

## Sikkerhet + GDPR

- OAuth 2.0 + PKCE (RFC 7636), DCR (RFC 7591), Protected Resource Metadata (RFC 9728)
- Alle delegate-tokens er PG-persistente, kobles eksplisitt til en API-nøkkel kunden valgte, og kan revoke-es uavhengig
- Per-kall audit-logging (kunde-id + nøkkel-id + endpoint + status) — eksporteres via DSAR
- Person-data pseudonymiseres på server-siden; backuper er kryptert; backup-eksport er offsite

Hele sikkerhets-policyen: **[firmaradar.no/personvern](https://firmaradar.no/personvern)**

---

## Support + spørsmål

- **Bugs i denne MCP-serveren** → [GitHub Issues](https://github.com/Tiwas/firmaradar-mcp/issues)
- **Spørsmål om data eller priser** → [kontakt Firmaradar](https://firmaradar.no/kontakt)
- **Sales / partnerskap** → lars@firmaradar.no

---

## Project layout

```
tools/mcp_server/
├── README.md                 — denne fila
├── python/                   — pip-pakken «firmaradar-mcp» (PyPI)
│   ├── pyproject.toml
│   ├── firmaradar_mcp/
│   │   ├── server.py         — MCP stdio + remote (streamable-HTTP)
│   │   ├── remote_server.py  — OAuth 2.0 + DCR for Claude Mobile/Web
│   │   ├── client.py         — REST API-wrapper
│   │   └── tools/            — 17 tool-stubs
│   └── tests/
└── typescript/               — npm-pakken «@firmaradar/mcp-server»
    └── src/
```

---

<div align="center">

**Bygd av [Firmaradar AS](https://firmaradar.no)** — agentisk infrastruktur for norske selskapsdata.

[firmaradar.no](https://firmaradar.no) &nbsp;·&nbsp; [Prising](https://firmaradar.no/prising) &nbsp;·&nbsp; [Dokumentasjon](https://firmaradar.no/dokumentasjon) &nbsp;·&nbsp; [Personvern](https://firmaradar.no/personvern)

</div>
