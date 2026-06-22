"""Tool: ``find_shared_connections``.

Connection/network analysis across 2–10 Norwegian companies: shared persons,
addresses, owners, auditor, common parent, circular ownership and
founded-close-in-time — plus weighted risk indicators and a graph for
visualisation. Backed by ``GET /api/v1/find-shared-connections`` (the same
``firmaradar.koblingsanalyse`` engine the web UI uses).

Requires the customer's ``koblingsanalyse`` extension to be active; the number
of companies is capped by the customer's tier (free→2, 299→5, 599→10). A 403
(extension not active) is surfaced in ``meta.error`` + ``summary`` rather than
raised.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..client import FirmaradarClient, FirmaradarClientError
from . import ToolHandler


class FindSharedConnectionsInput(BaseModel):
    orgnrs: list[str] = Field(
        min_length=2,
        max_length=10,
        description="2–10 Norwegian organisation numbers (9 digits each) to analyse together.",
    )


class FindSharedConnectionsOutput(BaseModel):
    selskaper: list[dict[str, Any]] = Field(default_factory=list, description="Companies analysed ({orgnr, navn}).")
    risiko_score: float = 0.0
    risiko_niva: str = "ukjent"  # lav | middels | hoy | ukjent
    risiko_indikatorer: list[dict[str, Any]] = Field(default_factory=list)
    felles_personer: list[dict[str, Any]] = Field(default_factory=list)
    felles_adresser: list[dict[str, Any]] = Field(default_factory=list)
    felles_eiere: list[dict[str, Any]] = Field(default_factory=list)
    felles_revisor_selskap: list[dict[str, Any]] = Field(default_factory=list)
    felles_morselskap: list[dict[str, Any]] = Field(default_factory=list)
    sirkulaer_eierskap: list[dict[str, Any]] = Field(default_factory=list)
    stiftet_tett: list[dict[str, Any]] = Field(default_factory=list)
    graf: dict[str, Any] = Field(default_factory=dict, description="{noder, kanter} for graph rendering.")
    meta: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None


async def handle(
    client: FirmaradarClient, params: FindSharedConnectionsInput
) -> FindSharedConnectionsOutput:
    try:
        payload = await client.get(
            "/api/v1/find-shared-connections",
            params={"orgnrs": ",".join(str(o).strip() for o in params.orgnrs)},
        )
    except FirmaradarClientError as exc:
        # Typisk 403 = koblingsanalyse-utvidelsen er ikke aktiv for kundens
        # selskap. Returner pent i stedet for å kaste, så LLM-en kan forklare.
        return FindSharedConnectionsOutput(
            risiko_niva="ukjent",
            meta={"error": str(exc)},
            summary=f"Koblingsanalyse utilgjengelig: {exc}",
        )
    if not isinstance(payload, dict):
        payload = {}

    indikatorer = payload.get("risiko_indikatorer") or []
    selskaper = payload.get("selskaper") or []
    niva = str(payload.get("risiko_niva") or "ukjent")
    score = float(payload.get("risiko_score") or 0.0)
    if indikatorer:
        topp = ", ".join(
            str(i.get("tittel") or i.get("kode") or "") for i in indikatorer[:5]
        )
        kobling_tekst = f"{len(indikatorer)} kobling(er) funnet: {topp}"
    else:
        kobling_tekst = "ingen koblinger funnet"
    summary = (
        f"{len(selskaper)} selskaper analysert. Risiko: {niva} "
        f"(score {score:.1f}) — {kobling_tekst}."
    )

    return FindSharedConnectionsOutput(
        selskaper=selskaper,
        risiko_score=score,
        risiko_niva=niva,
        risiko_indikatorer=indikatorer,
        felles_personer=payload.get("felles_personer") or [],
        felles_adresser=payload.get("felles_adresser") or [],
        felles_eiere=payload.get("felles_eiere") or [],
        felles_revisor_selskap=payload.get("felles_revisor_selskap") or [],
        felles_morselskap=payload.get("felles_morselskap") or [],
        sirkulaer_eierskap=payload.get("sirkulaer_eierskap") or [],
        stiftet_tett=payload.get("stiftet_tett") or [],
        graf=payload.get("graf") or {},
        meta=payload.get("meta") or {},
        summary=summary,
    )


HANDLER = ToolHandler(
    name="firmaradar_find_shared_connections",
    description=(
        "Analyse hidden connections across 2–10 Norwegian companies at once: shared "
        "board members/signatories, shared registered address, shared owners or "
        "ultimate parent, circular ownership, shared auditor, and companies founded "
        "close together in time — returned with weighted risk indicators, an overall "
        "risk level (lav/middels/hoy) and a node/edge graph. Use for due-diligence "
        "cluster analysis, shell-company / straw-man detection and fraud-pattern "
        "research. Requires the customer's koblingsanalyse extension; the company "
        "count is capped by their tier. Look up orgnrs via search_companies first."
    ),
    input_schema=FindSharedConnectionsInput,
    output_schema=FindSharedConnectionsOutput,
    handler=handle,
)
