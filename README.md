<div align="center">

<img src="https://firmaradar.no/static/img/logo_nobg.png" alt="Firmaradar" width="220">

# Firmaradar MCP-server

**Slå opp norske selskaper, eierstrukturer, konsernhierarkier og roller direkte fra Claude, ChatGPT, Cursor, Codex, Gemini og andre MCP-kompatible agenter.**

[![PyPI](https://img.shields.io/pypi/v/firmaradar-mcp.svg)](https://pypi.org/project/firmaradar-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/firmaradar-mcp.svg)](https://pypi.org/project/firmaradar-mcp/)
[![Lisens: Apache 2.0](https://img.shields.io/badge/Lisens-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![MCP](https://img.shields.io/badge/MCP-kompatibel-success.svg)](https://modelcontextprotocol.io)
[![Norsk data](https://img.shields.io/badge/data-norske%20selskaper-orange.svg)](https://firmaradar.no)

[**Koble til (anbefalt) →**](https://firmaradar.no/koble-til-agent) &nbsp;·&nbsp;
[Verktøykatalog](#verktøykatalog) &nbsp;·&nbsp;
[Kom i gang](#kom-i-gang) &nbsp;·&nbsp;
[Prising](https://firmaradar.no/prising) &nbsp;·&nbsp;
[Dokumentasjon](https://firmaradar.no/dokumentasjon)

</div>

---

## Hva er dette?

Firmaradar er Norges agentiske infrastruktur for selskapsdata. Denne MCP-serveren gir AI-agenten din direkte tilgang til:

- **2,1 millioner norske enheter** (BRREG-grunnregister, oppdatert daglig)
- **Aksjeeierregisteret** fra Skatteetaten (eierandeler ned til person-nivå, opp gjennom hele konsernet)
- **Roller** (styre, daglig leder, prokura) med historikk
- **Regnskap** (årsregnskap, mellombalanser, signaler)
- **Kunngjøringer** fra Brønnøysund og KYC-flagg
- **AML/PEP-screening** med revisjonsspor
- **NACE-bransjeovervåkning** (varsling ved nystiftet selskap i bransje og geografi)

Bygget for produksjon: OAuth 2.0 og DCR (Claude Mobile og Web støttes), API-nøkkel som alternativ (Cursor og Codex), [loggført per kall](https://firmaradar.no/dokumentasjon), [DSAR-eksport](https://firmaradar.no/dokumentasjon) og GDPR-pseudonymisering på serversiden.

---

## Kom i gang

### Anbefalt — OAuth (Claude Web, Claude Mobile, Claude Desktop)

Lim inn denne adressen som tilkobling i klienten din. Du logger inn via firmaradar.no-konto og velger hvilken API-nøkkel agenten skal bruke.

```
https://mcp.firmaradar.no/mcp
```

Detaljert veiledning per klient: **[firmaradar.no/koble-til-agent](https://firmaradar.no/koble-til-agent)**

### Cursor, Codex eller andre — API-nøkkel via stdio

Hvis klienten din ikke støtter ekstern MCP, kan du kjøre serveren lokalt:

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
        "FIRMARADAR_API_KEY": "din-nøkkel-fra-firmaradar.no/min-side/api-keys",
        "FIRMARADAR_API_BASE": "https://firmaradar.no"
      }
    }
  }
}
```

Hent API-nøkkel: **[firmaradar.no/min-side/api-keys](https://firmaradar.no/min-side/api-keys)** (krever konto).

---

## Verktøykatalog

17 verktøy, alle med samme oppsett i Python (`firmaradar-mcp` på PyPI) og TypeScript (`@firmaradar/mcp-server` på npm):

### Selskaps-oppslag
- `firmaradar_search_companies` — søk på navn eller orgnr
- `firmaradar_get_company` — full profil (organisasjonsform, NACE, ansatte, adresse, regnskap, eiere, roller)
- `firmaradar_get_company_ownership` — konsernhierarki opp og ned, eierandeler, person-nivå
- `firmaradar_get_company_roles` — styre, daglig leder, prokura (med fratrådt-historikk)
- `firmaradar_get_company_financials` — årsregnskap, nøkkeltall og signaler
- `firmaradar_get_company_announcements` — BRREG-kunngjøringer (vedtak, fusjoner, oppløsninger)
- `firmaradar_get_company_signals` — risikoflagg, KYC-flagg, insolvens
- `firmaradar_find_related_companies` — finn relaterte selskaper via eierskap, roller eller adresse

### Person-oppslag (krever full tilgang)
- `firmaradar_search_persons` — navne-søk med toleranse for skrivefeil
- `firmaradar_get_person` — profil med adresse og fødselsår
- `firmaradar_get_person_companies` — alle selskaper personen eier eller har rolle i
- `firmaradar_get_person_roles` — aktive og historiske roller

### KYC og AML
- `firmaradar_check_aml_pep` — full AML/PEP-screening med sanksjonslister og revisjonsspor

### Bransje og overvåkning
- `firmaradar_list_companies_in_nace` — alle selskaper i en NACE-kode med geografisk filter
- `firmaradar_get_recent_changes` — endringer siste N dager for et orgnr
- `firmaradar_search_announcements` — fritekst-søk i BRREG-kunngjøringer
- `firmaradar_compare_companies` — sammenlikne flere selskaper side om side

Full API-referanse og eksempel-prompter: **[firmaradar.no/dokumentasjon](https://firmaradar.no/dokumentasjon)**

---

## Priser

Vi tilbyr én **plattformavgift (99 kr/mnd)** + per-kall-prising. MCP-kallene har en egen pakke (`mcp_full`) som er rabattert for agentbruk siden agenter genererer høyere volum enn manuelle API-integrasjoner.

Detaljert prising: **[firmaradar.no/prising](https://firmaradar.no/prising)**

---

## Hvorfor åpen kildekode?

- **Transparens** — du kan lese hver verktøy-modul og se nøyaktig hva agenten sender til Firmaradar.
- **Tillit gjennom gjennomgang** — koden er Apache 2.0. Gå gjennom den selv, eller lås til en spesifikk versjon.
- **Bidrag velkommen** — vi tar imot pull requests som forbedrer skjemaer eller legger til kompatibilitets-lag for nye klienter.

Backend (firmaradar.no) er proprietær fordi den eier dataflyten og lisensieringen mot Skatteetaten og Brønnøysund.

---

## Sikkerhet og GDPR

- OAuth 2.0 og PKCE (RFC 7636), Dynamic Client Registration (RFC 7591), Protected Resource Metadata (RFC 9728)
- Alle delegerte tokens er lagret i PostgreSQL, knyttet eksplisitt til en API-nøkkel kunden valgte, og kan tilbakekalles uavhengig
- Loggføring per kall (kunde-id, nøkkel-id, endepunkt og status) — eksporteres via DSAR-rapport
- Person-data pseudonymiseres på serversiden; sikkerhetskopier er kryptert og lagres eksternt

Hele sikkerhets-policyen: **[firmaradar.no/personvern](https://firmaradar.no/personvern)**

---

## Støtte og spørsmål

- **Feil i denne MCP-serveren** → [GitHub Issues](https://github.com/Tiwas/firmaradar-mcp/issues)
- **Spørsmål om data eller priser** → [kontakt Firmaradar](https://firmaradar.no/kontakt)
- **Salg eller partnerskap** → lars@firmaradar.no

---

## Mappestruktur

```
tools/mcp_server/
├── README.md                 — denne filen
├── python/                   — pip-pakken «firmaradar-mcp» (PyPI)
│   ├── pyproject.toml
│   ├── firmaradar_mcp/
│   │   ├── server.py         — MCP stdio og ekstern (streamable-HTTP)
│   │   ├── remote_server.py  — OAuth 2.0 og DCR for Claude Mobile/Web
│   │   ├── client.py         — REST-API-wrapper
│   │   └── tools/            — 25 verktøy-moduler
│   └── tests/
└── typescript/               — npm-pakken «@firmaradar/mcp-server»
    └── src/
```

---

<div align="center">

**Bygget av [Firmaradar AS](https://firmaradar.no)** — agentisk infrastruktur for norske selskapsdata.

[firmaradar.no](https://firmaradar.no) &nbsp;·&nbsp; [Prising](https://firmaradar.no/prising) &nbsp;·&nbsp; [Dokumentasjon](https://firmaradar.no/dokumentasjon) &nbsp;·&nbsp; [Personvern](https://firmaradar.no/personvern)

</div>
