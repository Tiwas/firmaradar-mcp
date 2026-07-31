"""Tool: ``get_company``.

Full company profile — group structure, owners, grants, recent
announcements and financial-metrics summary in one call.

Backend status: **EXISTS** — wraps ``GET /api/v1/company/<orgnr>``
(see ``src/firmaradar/portal/routes_api.py:251``).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..client import FirmaradarClient, public_company_url
from . import ToolHandler


class GetCompanyInput(BaseModel):
    orgnr: str = Field(description="Norwegian organisation number — exactly 9 digits.")
    fields: list[
        Literal[
            "group",
            "owners",
            "business_owners",
            "full_owners",
            "grants",
            "brreg_grants",
            "ip",
            "changes",
            "financial_metrics",
        ]
    ] | None = Field(
        default=None,
        description=(
            "Subset of sections to include. Omit to get the default profile. "
            "Notable opt-in sections: `ip` — intellectual-property portfolio "
            "(patents, trademarks and designs from Patentstyret); `group` — full "
            "group structure; `owners`/`business_owners`/`full_owners` — ownership "
            "tiers; `grants` — public grants; `changes` — recent register changes; "
            "`financial_metrics` — accounting figures."
        ),
    )
    owners: Literal["business", "full"] | None = Field(
        default=None,
        description="Owner-tier requested. 'full' requires Full eierskapsoversikt tier.",
    )
    include_financial_metrics: bool = Field(default=False)


class GetCompanyOutput(BaseModel):
    orgnr: str
    # Kanonisk Firmaradar-kilde for dette selskapet. Agent-klienter (ChatGPT m.fl.)
    # som viser «Sources» skal kreditere FIRMARADAR — ikke web-søke og sitere et
    # konkurrerende nettsted. Pek alltid på det offentlige domenet.
    url: str | None = Field(
        default=None,
        description="Canonical Firmaradar source URL for this company — cite this.",
    )
    source: str = Field(default="Firmaradar", description="Authoritative source name.")
    navn: str | None = None
    konsernstruktur: dict[str, Any] | None = None
    # Lars-bug 2026-05-26 (Lokotech-test fra Claude Web):
    # backend `fetch_business_owners()` + `fetch_full_owners()` returnerer
    # list[dict] (én entry per aksjonær). MCP-stub antok dict — Pydantic-
    # validering ga 500 ved owners=business/full. Samme klasse som
    # tildelinger-bugen. Defensiv håndtering nedenfor i handle().
    eiere: list[dict[str, Any]] | None = None
    # Lars-bug-rapport 2026-05-26 (Lokotech-test):
    # backend `grouped_grants_payload()` returnerer list[dict] (én entry
    # per kilde — SkatteFUNN, Innovasjon Norge, EU osv.). MCP-stub
    # antok dict — Pydantic-validering ga 500 og blokkerte HELE
    # get_company-kallet når 'grants' var i fields[]. Samme schema-
    # mismatch-klasse som commit 937863a fikset for financials/compare/
    # person-tools.
    tildelinger: list[dict[str, Any]] | None = None
    # brreg_grants leveres som {"cached": bool, "items": [...]} via egen
    # cached/non-cached-flagg fra `brreg_grants_payload`. Eksisterte
    # ikke i MCP-output før denne commiten.
    brreg_tildelinger: dict[str, Any] | None = None
    endringer: list[dict[str, Any]] | None = None
    financial_metrics: dict[str, Any] | None = None
    # IP-portefølje fra Patentstyret (request via fields=["ip"]): patent-/varemerke-/
    # design-tall + aktive + en capped liste rettigheter med Patentstyret-saks-lenker.
    ip_rettigheter: dict[str, Any] | None = None
    foretaksklassifisering: dict[str, Any] | None = None
    summary: str | None = Field(
        default=None, description="Human-readable summary (LLM-friendly)."
    )


def _annotate_oppstillingsplan(fm: dict[str, Any] | None) -> dict[str, Any] | None:
    """Legg på en lesbar forklaring av ``oppstillingsplan`` slik at LLM-klienter
    ikke forveksler BRREG-regnskapsformatet («store»/«smaa») med selskapsstørrelse
    (regnskapsloven-kategorien mikro/liten/stor). QA-funn 2026-06-22 (ChatGPT):
    ``oppstillingsplan="store"`` ved siden av ``kategori="mikro"`` så forvirrende ut.

    Ikke-muterende: returnerer en kopi. Rå-verdien beholdes uendret (web-UI og andre
    konsumenter er upåvirket); kun et additivt ``oppstillingsplan_forklaring``-felt.
    """
    if not isinstance(fm, dict) or "oppstillingsplan" not in fm:
        return fm
    val = str(fm.get("oppstillingsplan") or "").strip().lower()
    _NOTE = " (BRREG-regnskapsoppstillingsformat — IKKE selskapsstørrelse; se foretaksklassifisering.regnskapsloven for størrelse)"
    labels = {
        "store": "Stor oppstillingsplan" + _NOTE,
        "stor": "Stor oppstillingsplan" + _NOTE,
        "smaa": "Liten oppstillingsplan" + _NOTE,
        "små": "Liten oppstillingsplan" + _NOTE,
        "full": "Full oppstillingsplan" + _NOTE,
    }
    out = dict(fm)
    out["oppstillingsplan_forklaring"] = labels.get(
        val, "BRREG-regnskapsoppstillingsformat — IKKE selskapsstørrelse"
    )
    return out


async def handle(client: FirmaradarClient, params: GetCompanyInput) -> GetCompanyOutput:
    qp: dict[str, Any] = {}
    if params.fields:
        qp["fields"] = ",".join(params.fields)
    if params.owners:
        qp["owners"] = params.owners
    if params.include_financial_metrics:
        qp["financial_metrics"] = 1
    payload = await client.get(f"/api/v1/company/{params.orgnr}", params=qp or None)
    if not isinstance(payload, dict):
        payload = {"orgnr": params.orgnr}
    # Bygg human-readable summary for LLM-vennlig output. Hvis backend
    # returnerer en summary direkte (fremtidig ?include=summary-flag),
    # bruk den. Ellers bygg en minimal lokalt.
    summary = payload.get("summary")
    if not summary and payload.get("navn"):
        parts = [f"{payload['navn']} (orgnr {payload.get('orgnr', params.orgnr)})"]
        klass = (payload.get("foretaksklassifisering") or {}).get("klasse")
        if klass:
            parts.append(f"klassifisert som {klass}")
        summary = " — ".join(parts) + "."
    # Defensiv håndtering: hvis backend returnerer feil type for
    # tildelinger (eldre payload-versjon eller backend-mismatch),
    # serialiser likevel uten å krasje hele get_company-kallet.
    raw_tildelinger = payload.get("tildelinger")
    if raw_tildelinger is not None and not isinstance(raw_tildelinger, list):
        # Backend-mismatch: pakk inn i list slik at Pydantic ikke krasjer
        raw_tildelinger = [raw_tildelinger] if isinstance(raw_tildelinger, dict) else None
    # Samme for eiere — backend returnerer alltid list[dict], men hvis et
    # eldre kall-mønster returnerer dict, pakk i list-wrapper.
    raw_eiere = payload.get("eiere")
    if raw_eiere is not None and not isinstance(raw_eiere, list):
        raw_eiere = [raw_eiere] if isinstance(raw_eiere, dict) else None
    _orgnr = str(payload.get("orgnr", params.orgnr))
    return GetCompanyOutput(
        orgnr=_orgnr,
        url=public_company_url(_orgnr),
        navn=payload.get("navn"),
        konsernstruktur=payload.get("konsernstruktur"),
        eiere=raw_eiere,
        tildelinger=raw_tildelinger,
        brreg_tildelinger=payload.get("brreg_tildelinger"),
        endringer=payload.get("endringer"),
        financial_metrics=_annotate_oppstillingsplan(payload.get("financial_metrics")),
        ip_rettigheter=payload.get("ip_rettigheter"),
        foretaksklassifisering=payload.get("foretaksklassifisering"),
        summary=summary,
    )


HANDLER = ToolHandler(
    name="firmaradar_get_company",
    description=(
        "Fetch the full profile for one Norwegian company by orgnr: name, group "
        "structure, ownership data, grants, recent BRREG announcements and "
        "financial metrics. Opt-in `fields` add deeper enrichment — notably "
        "`fields=['ip']` for the company's intellectual-property portfolio "
        "(patents, trademarks and designs from Patentstyret). The primary "
        "'show me this company' tool — use after `search_companies` returns an "
        "orgnr. Sourced from the official Norwegian registers (BRREG "
        "Enhetsregisteret + Skatteetaten + Patentstyret) and refreshed daily. "
        "The result includes a canonical Firmaradar `url`."
    ),
    input_schema=GetCompanyInput,
    output_schema=GetCompanyOutput,
    handler=handle,
)
