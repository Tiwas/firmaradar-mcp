# firmaradar-mcp

[![License: Apache 2.0](https://img.shields.io/badge/license-Apache_2.0-blue.svg)](LICENSE)
[![Python: 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](python/pyproject.toml)
[![MCP](https://img.shields.io/badge/protocol-MCP_1.0-green.svg)](https://modelcontextprotocol.io)

**MCP stdio-server som eksponerer [Firmaradar.no](https://firmaradar.no)
sin REST-API til AI-agenter (Claude, Cursor, OpenAI Codex, Gemini CLI,
m.fl.) via Model Context Protocol.**

Med denne pakken kan agenten din slå opp norske selskaper, eierstruktur,
regnskap, kunngjøringer, risikosignaler og AML/PEP-status direkte i
chatten — uten å skrive REST-kall manuelt.

---

## Hvordan det fungerer

```
┌─────────────────┐   stdio    ┌──────────────────┐   HTTPS   ┌────────────────┐
│ Agent-klient    │ ─────────► │ firmaradar-mcp   │ ────────► │ firmaradar.no  │
│ (Claude, Cursor)│   MCP-JSON │ (denne pakken)   │   REST    │ /api/v1/*      │
└─────────────────┘            └──────────────────┘           └────────────────┘
```

Agenten kaller `tools/list` for å se hva som er tilgjengelig (17 tools),
deretter `tools/call` med strukturerte argumenter. MCP-serveren oversetter
til REST-kall mot Firmaradar og returnerer strukturert JSON tilbake.

---

## Tilgjengelige tools (17)

| Tool | Beskrivelse |
|------|-------------|
| `firmaradar.search_companies` | Strukturert søk i selskapsregisteret |
| `firmaradar.get_company` | Full selskapsprofil |
| `firmaradar.get_company_ownership` | Eierstruktur opp/ned/begge |
| `firmaradar.get_company_roles` | Styreleder, daglig leder, signatur, prokura, revisor |
| `firmaradar.get_company_financials` | Regnskap (inntil 20 år tilbake) |
| `firmaradar.get_company_announcements` | BRREG-kunngjøringer |
| `firmaradar.get_company_signals` | Risikosignal-aggregat |
| `firmaradar.search_persons` | Person-søk |
| `firmaradar.get_person` | Aggregert person-profil |
| `firmaradar.get_person_roles` | Alle roller for én person |
| `firmaradar.get_person_companies` | Alle selskap én person eier |
| `firmaradar.check_aml_pep` | AML/PEP-screening (krever DPA + purpose) |
| `firmaradar.get_recent_changes` | Endringer siste N dager |
| `firmaradar.list_companies_in_nace` | Bransje-søk (NACE + filtre) |
| `firmaradar.find_related_companies` | Relasjons-graf via shared person/adresse/UBO |
| `firmaradar.compare_companies` | Side-by-side for opptil 5 selskap |
| `firmaradar.search_announcements` | Cross-orgnr kunngjøring-søk |

Detaljerte input-skjemaer hentes runtime via MCP `tools/list` — eller se
kildekoden i [`python/firmaradar_mcp/tools/`](python/firmaradar_mcp/tools/).

---

## Komme i gang

### 1. Skaff en API-nøkkel

Opprett konto på [firmaradar.no](https://firmaradar.no), gå til
**Mine API-nøkler**, og generer en nøkkel. NB: nøkkelen vises kun én
gang — kopier den til en sikker plass.

Se [firmaradar.no/prising](https://firmaradar.no/prising) for tier-detaljer
(noen tools krever Utvidet eller Compliance-tier).

### 2. Installer Python-pakken

```bash
git clone https://github.com/Tiwas/firmaradar-mcp.git
cd firmaradar-mcp/python

# Lag og aktiver venv (Debian/Ubuntu 23+ krever dette pga PEP 668):
python3 -m venv .venv
source .venv/bin/activate

# Installer pakken editable:
pip install -e .

# Noter absolutt sti til console-scriptet:
which firmaradar-mcp
# → /full/path/to/.venv/bin/firmaradar-mcp
```

### 3. Konfigurer agent-klienten din

#### Claude Desktop

Rediger config-fila:
* **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
* **Linux**: `~/.config/claude/claude_desktop_config.json`
* **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "firmaradar": {
      "command": "/full/path/to/.venv/bin/firmaradar-mcp",
      "env": {
        "FIRMARADAR_API_KEY": "<din-nøkkel>",
        "FIRMARADAR_API_BASE": "https://firmaradar.no"
      }
    }
  }
}
```

Restart Claude Desktop. Tools vises under «🔌»-ikonet.

#### Claude Code CLI (JSON-form — mest robust)

```bash
claude mcp add-json firmaradar '{
  "command": "/full/path/to/.venv/bin/firmaradar-mcp",
  "env": {
    "FIRMARADAR_API_KEY": "<din-nøkkel>",
    "FIRMARADAR_API_BASE": "https://firmaradar.no"
  }
}'

# Verifiser:
claude mcp list
claude mcp get firmaradar
```

#### Cursor

Settings → Features → Model Context Protocol → «Add server», eller
rediger `~/.cursor/mcp.json` med samme JSON-struktur som Claude Desktop.

#### OpenAI Codex CLI

Rediger `~/.codex/config.toml`:

```toml
[mcp_servers.firmaradar]
command = "/full/path/to/.venv/bin/firmaradar-mcp"
env = { FIRMARADAR_API_KEY = "<din-nøkkel>", FIRMARADAR_API_BASE = "https://firmaradar.no" }
```

#### Gemini CLI (Google)

Rediger `~/.gemini/settings.json` med samme JSON-struktur som Claude Desktop.

### 4. Test det

Start en ny agent-økt og spør:

> *Hvilke Firmaradar-tools har du tilgjengelig?*

Du skal se 17 tools listet. Test deretter et oppslag:

> *Hent grunninfo om Equinor (orgnr 923609016).*

---

## Bruk-eksempler

- *«Finn 20 restauranter i Oslo (kommune 0301) med mer enn 5 ansatte»*
- *«Vis eier-strukturen til Equinor opp 3 nivåer»*
- *«Hvem sitter i styret hos Norwegian Air Shuttle?»*
- *«Sammenlign omsetning siste 5 år for orgnr 982463718 og 991825827»*
- *«Var det noen konkurser i bygg-bransjen (NACE 41) forrige måned?»*
- *«Hva sier risikosignalene om orgnr 923609016?»*

Naturlig språk — agenten velger riktig tool og bygger argumentene selv.

---

## Sikkerhet og personvern

- **API-nøkler** opprettes per bruker, kan revokes når som helst, og rate-limites per tier.
- **AML/PEP-screening** krever signert DPA + per-call `X-FR-Purpose`-header. Hver kall logges i 60 måneder (Hvitvaskingsloven § 30).
- **PII-tiering**: standard / utvidet / compliance — se [firmaradar.no/prising](https://firmaradar.no/prising).
- **Logging til stderr**: serveren sender logs til stderr (ikke stdout) så de ikke korrupter MCP-meldinger. Sett `FIRMARADAR_MCP_LOG_LEVEL=DEBUG` for verbose logging.

Full agent-arkitektur og webhook-plugins er beskrevet på
[firmaradar.no/agentisk-flyt](https://firmaradar.no/agentisk-flyt).

---

## Lisens

Apache License 2.0. Se [LICENSE](LICENSE).

Selve API-tilgangen (mot `https://firmaradar.no/api/v1/`) krever
en aktiv Firmaradar-konto og er underlagt
[våre vilkår](https://firmaradar.no/vilkaar).

---

## Issues og bidrag

- 🐛 **Bugs/feature-requests**: [Issues](https://github.com/Tiwas/firmaradar-mcp/issues)
- 📧 **Generell support**: support@firmaradar.no
- 🔒 **Sikkerhetsfunn**: security@firmaradar.no

Pull requests er velkomne. NB: tool-skjemaer og endpoint-mapping må
matche serverside (firmaradar.no/api/v1) — endringer der må
koordineres med Firmaradar-teamet.
