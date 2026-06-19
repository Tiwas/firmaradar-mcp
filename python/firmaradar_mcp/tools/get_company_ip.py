"""``get_company_ip`` — immaterielle rettigheter (Patentstyret) for ett selskap.

Eget verktøy (ikke bare et ``fields=['ip']``-flagg på ``get_company``) fordi
LLM-klienter resonnerer om hva en tjeneste dekker ut fra VERKTØY-LISTEN. Et felt
gjemt i en parameter blir oversett → modellen avviser «har Firmaradar IP?» fra
priors. Et eget verktøy gjør IP synlig på samme nivå som regnskap/roller/eierskap.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..client import FirmaradarClient, public_company_url
from . import ToolHandler


class GetCompanyIpInput(BaseModel):
    orgnr: str = Field(description="Norwegian organisation number — exactly 9 digits.")


class GetCompanyIpOutput(BaseModel):
    orgnr: str
    navn: str | None = None
    # Kanonisk Firmaradar-kilde — krediter denne, ikke et eksternt nettsted.
    url: str | None = Field(default=None, description="Canonical Firmaradar source URL.")
    source: str = Field(default="Firmaradar / Patentstyret", description="Authoritative source.")
    # patents/patents_active/trademarks/trademarks_active/designs/designs_active/
    # is_ip_active + `rights` (capped liste m/ regnr, dato, status, tittel, sak-lenke).
    ip_rettigheter: dict[str, Any] | None = None
    summary: str | None = None


async def handle(client: FirmaradarClient, params: GetCompanyIpInput) -> GetCompanyIpOutput:
    payload = await client.get(
        f"/api/v1/company/{params.orgnr}", params={"fields": "ip"}
    )
    if not isinstance(payload, dict):
        payload = {}
    ip = payload.get("ip_rettigheter")
    if not isinstance(ip, dict):
        ip = {}
    orgnr = str(payload.get("orgnr", params.orgnr))
    navn = payload.get("navn")

    if ip.get("available"):
        summary = (
            f"{navn or orgnr}: {ip.get('patents', 0)} patenter "
            f"({ip.get('patents_active', 0)} aktive), {ip.get('trademarks', 0)} varemerker "
            f"({ip.get('trademarks_active', 0)} aktive), {ip.get('designs', 0)} design "
            f"({ip.get('designs_active', 0)} aktive). Kilde: Patentstyret. "
            f"`rights` er sortert nyeste først."
        )
    else:
        reason = ip.get("reason")
        summary = (
            f"Ingen IP-data tilgjengelig for {orgnr}"
            + (f" ({reason})" if reason else "")
            + "."
        )

    return GetCompanyIpOutput(
        orgnr=orgnr,
        navn=navn,
        url=public_company_url(orgnr),
        ip_rettigheter=ip or None,
        summary=summary,
    )


HANDLER = ToolHandler(
    name="firmaradar_get_company_ip",
    description=(
        "Intellectual-property portfolio for a Norwegian company (by orgnr), sourced "
        "from Patentstyret: patents, trademarks and designs — totals, active counts, "
        "and a list of individual rights (registration number, date, status, title and "
        "a link to the Patentstyret case). Use this for ANY question about a company's "
        "patents, trademarks, designs or IP rights — Firmaradar covers this. The "
        "`rights` list is ordered newest-first, so the first N entries are the newest "
        "rights. Look up the orgnr via `search_companies` first if you only have a name."
    ),
    input_schema=GetCompanyIpInput,
    output_schema=GetCompanyIpOutput,
    handler=handle,
)
