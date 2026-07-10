"""Tool: ``check_konkurs_eksponering``.

Name-based bankruptcy-exposure screening ("konkursgjenganger" signal):
leadership roles a person held in companies that later went bankrupt,
tenure-weighted, from the dated role history.

Why a *name* lookup (not a person ID): konkursgjengangere are by
definition FORMER leaders — the bankrupt company's roles have ended, so
they are not in the person/role index and cannot be reached via
``search_persons`` / ``get_person``. This tool queries the dated role
history directly by name.

Backend status: **EXISTS** — wraps
``GET /api/v1/person/konkurs-eksponering?navn=`` (see
``src/firmaradar/portal/routes_api.py``). PII-sensitive: requires
``search_full_enabled``.

The match is by NAME (no national ID), so a hit is a REVIEW FLAG to
verify (birth year / address), not a verdict — the framing travels in
``note``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..client import FirmaradarClient, FirmaradarClientError
from . import ToolHandler


class CheckKonkursEksponeringInput(BaseModel):
    navn: str = Field(
        min_length=2,
        description="Full name to screen (min 2 characters), e.g. 'Karl Petter Ulriksen'.",
    )
    purpose: str | None = Field(
        default=None,
        description=(
            "Purpose-of-processing string for the F10.11 audit trail. "
            "Required when calling against accounts with purpose-confirmation."
        ),
    )


class KonkursForetak(BaseModel):
    orgnr: str | None = None
    rolletype: str | None = None
    konkursdato: str | None = None
    tiltradt: str | None = None
    tenure_days: int | None = None


class CheckKonkursEksponeringOutput(BaseModel):
    navn: str
    antall_konkursforetak: int = 0
    foretak: list[KonkursForetak] = Field(default_factory=list)
    # Review-flag framing — never present a name-based hit as a verdict.
    note: str | None = None


async def handle(
    client: FirmaradarClient, params: CheckKonkursEksponeringInput
) -> CheckKonkursEksponeringOutput:
    qp: dict[str, Any] = {"navn": params.navn}
    ke: dict[str, Any] = {}
    try:
        payload = await client.get("/api/v1/person/konkurs-eksponering", params=qp)
        if isinstance(payload, dict) and isinstance(payload.get("konkurs_eksponering"), dict):
            ke = payload["konkurs_eksponering"]
    except FirmaradarClientError:
        ke = {}

    foretak = [
        KonkursForetak(
            orgnr=(str(f.get("orgnr")) if f.get("orgnr") is not None else None),
            rolletype=f.get("rolletype"),
            konkursdato=f.get("konkursdato"),
            tiltradt=f.get("tiltradt"),
            tenure_days=f.get("tenure_days"),
        )
        for f in (ke.get("foretak") or [])
        if isinstance(f, dict)
    ]
    return CheckKonkursEksponeringOutput(
        navn=params.navn,
        antall_konkursforetak=int(ke.get("antall_konkursforetak") or 0),
        foretak=foretak,
        note=ke.get("note") or None,
    )


HANDLER = ToolHandler(
    name="firmaradar_check_konkurs_eksponering",
    description=(
        "Screen a person by NAME for bankruptcy exposure ('konkursgjenganger'): "
        "leadership roles (chair / managing director) held in companies that "
        "later went bankrupt, tenure-weighted, from the dated role history. Use "
        "this for HISTORICAL leaders who are no longer in any role index and so "
        "cannot be reached via search_persons/get_person. The match is name-based "
        "(no national ID), so a hit is a REVIEW FLAG to verify (birth year / "
        "address), not a verdict. PII-sensitive — requires the search_full_enabled "
        "tier."
    ),
    input_schema=CheckKonkursEksponeringInput,
    output_schema=CheckKonkursEksponeringOutput,
    handler=handle,
)
