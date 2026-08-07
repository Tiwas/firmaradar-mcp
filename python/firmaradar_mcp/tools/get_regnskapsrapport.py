"""Tool: ``get_regnskapsrapport``.

Bestiller en formatert, nedlastbar regnskapsrapport (Excel eller PDF) for
ett selskap — samme aggregerte builder som portalens
``/minbedrift/regnskap/<orgnr>/rapport.xlsx``/``.pdf``. Svaret er metadata
+ et **kortlevd, signert nedlastings-URL** (gyldig ~15 minutter), aldri
base64/binærdata i selve MCP-svaret — rapportene er 50-70 kB, for store
til å bære i et tool-resultat.

Skiller seg fra ``get_company_financials``: dette verktøyet leverer et
FERDIG DOKUMENT (samme tall, sider, kildenote og formatering som en
kunde ville lastet ned i portalen) for arkivering/videresending, ikke
strukturerte tall for programmatisk bruk. Bruk ``get_company_financials``
når agenten skal REGNE på tallene selv.

Backend: ``GET /api/v1/regnskapsrapport/<orgnr>`` (utstedelse, målt) +
``GET /api/v1/regnskapsrapport/download/<token>`` (selve filen, token-
autentisert — se ``src/firmaradar/portal/routes_mcp_v3.py``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class GetRegnskapsrapportInput(BaseModel):
    orgnr: str = Field(description="9-digit Norwegian organisation number.")
    format: Literal["xlsx", "pdf"] = Field(
        default="pdf",
        description=(
            "'xlsx' for a spreadsheet (3 sheets: figures, key ratios, "
            "source) or 'pdf' for a print-ready report. Each format "
            "requires its own subscription add-on on the caller's "
            "account (Excel export / PDF export respectively) — a "
            "403 'extension_not_active' error means that add-on isn't "
            "enabled."
        ),
    )
    regnskapstype: Literal["SELSKAP", "KONSERN"] = Field(
        default="SELSKAP",
        description=(
            "'SELSKAP' for the standalone company accounts, 'KONSERN' "
            "for the consolidated group accounts (only meaningful for "
            "companies that file one)."
        ),
    )
    years: int = Field(
        default=5, ge=1, le=5,
        description="Number of financial years to include (hard-capped at 5).",
    )


class GetRegnskapsrapportOutput(BaseModel):
    orgnr: str
    regnskapstype: str
    format: str
    antall_aar: int = Field(description="Number of years actually delivered in the report.")
    maks_aar: int | None = None
    aar: list[int] | None = Field(
        default=None, description="The financial years included, newest first.",
    )
    kilde: str | None = Field(default=None, description="Source label shown in the report.")
    valuta: str | None = Field(
        default=None,
        description="Reporting currency (ISO 4217, or 'MIXED' if it changed within the series).",
    )
    download_url: str = Field(
        description=(
            "Short-lived signed URL (~15 min) for the actual file. No "
            "further authentication is required to fetch it — the URL "
            "itself is the credential, so treat it as sensitive and "
            "don't share it beyond the requester."
        ),
    )
    expires_in: int = Field(description="Seconds until download_url stops working.")


async def handle(
    client: FirmaradarClient, params: GetRegnskapsrapportInput
) -> GetRegnskapsrapportOutput:
    payload = await client.get(
        f"/api/v1/regnskapsrapport/{params.orgnr}",
        params={
            "format": params.format,
            "regnskapstype": params.regnskapstype,
            "years": params.years,
        },
    )
    if not isinstance(payload, dict):
        payload = {}
    return GetRegnskapsrapportOutput(
        orgnr=str(payload.get("orgnr", params.orgnr)),
        regnskapstype=str(payload.get("regnskapstype", params.regnskapstype)),
        format=str(payload.get("format", params.format)),
        antall_aar=int(payload.get("antall_aar") or 0),
        maks_aar=payload.get("maks_aar"),
        aar=payload.get("aar"),
        kilde=payload.get("kilde"),
        valuta=payload.get("valuta"),
        download_url=str(payload.get("download_url") or ""),
        expires_in=int(payload.get("expires_in") or 0),
    )


HANDLER = ToolHandler(
    name="firmaradar_get_regnskapsrapport",
    description=(
        "Order a formatted, downloadable financial report (Excel or PDF) "
        "for a Norwegian company — the same multi-source-fused figures, "
        "layout and source note as the report a customer would download "
        "in the Firmaradar portal, ready to file or forward. Returns a "
        "short-lived download link + metadata (years covered, source, "
        "currency), NOT the file itself and NOT base64 data — fetch the "
        "download_url separately, no further auth required, within "
        "expires_in seconds. Use `get_company_financials` instead when "
        "you need the raw figures to reason about, not a document to "
        "hand off. Requires the Excel-export or PDF-export add-on "
        "(matching the requested format) on the caller's account. "
        "Charges 1 credit per financial year included in the report."
    ),
    input_schema=GetRegnskapsrapportInput,
    output_schema=GetRegnskapsrapportOutput,
    handler=handle,
)
