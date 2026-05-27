"""Tool: ``confirm_risk_score_disclaimer``.

Bekreft pre-screening-disclaimer for :func:`firmaradar_get_risk_score`.

Dette er en éngangs-bekreftelse per Firmaradar-bruker (ikke per agent
eller per kall). Bekreftelsen er permanent og audit-loggføres.

Backend: ``POST /api/v1/risikoscoring/confirm-disclaimer`` (#134,
2026-05-27). Bruker samme audit-tabell
(``extension_kundebekreftelse_event``) som portalets manuelle modal-
bekreftelse — så et MCP-bekreftet selskap kan også bruke portalets
risikoscoring-UI uten ny bekreftelse, og omvendt.

Compliance:

* ``user_id`` lagres som brukeren bak Bearer-tokenet (Bearer →
  portal_api_key → user_id-kjeden er 1:1).
* User-Agent i audit-tabellen inkluderer ``X-MCP-Client``-headeren slik
  at MCP-opphav er sporbart uten ny kolonne.
* Krever at OAuth-token er knyttet til en bruker som har risikoscoring
  aktivert i sin pakke (403 ``extension_not_active`` ellers).
* Hvis bruker allerede har bekreftet, returnerer endpoint eksisterende
  bekreftelse i stedet for å skrive duplikat (idempotent).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


# Disclaimer-konstantene speilet fra
# ``extensions/risikoscoring/handlers/kundebekreftelse.py``. Hvis disse
# endres må også string-konstantene her oppdateres — backend rejector
# eventuell mismatch med ``confirmation_text_mismatch``.

DISCLAIMER_VERSION = "v1"

DISCLAIMER_TEXT = (
    "Risikoscoring i Firmaradar er en pre-screening-indikator basert på "
    "offentlig tilgjengelige data fra Brønnøysundregistrene og andre "
    "åpne kilder. Den er ment som et hjelpemiddel for å eliminere "
    "åpenbart uproblematiske selskaper fra en dypere "
    "compliance-arbeidsflyt.\n\n"
    "Risikoscoringen er IKKE en kredittvurdering, IKKE en "
    "betalingsevne-vurdering, og skal IKKE brukes som grunnlag for "
    "automatiserte negative beslutninger om enkeltselskap. Slike "
    "beslutninger krever et formelt grunnlag fra et kredittopplysnings-"
    "byrå (Bisnode, Experian, Dun & Bradstreet eller tilsvarende) "
    "med konsesjon fra Finanstilsynet.\n\n"
    "Ved å bekrefte denne avtalen erklærer jeg at jeg har forstått dette "
    "og at vårt selskap ikke vil bruke Firmaradars risikoscoring for "
    "automatiserte negative beslutninger eller som erstatning for "
    "formell kredittvurdering."
)


class ConfirmRiskScoreDisclaimerInput(BaseModel):
    """Tom input — disclaimer-versjon og -tekst er innebygd i tool-
    handleren slik at agenten ikke trenger å gjette eller hardkode dem.

    Designvalg: agenten bør lese tool-beskrivelsen som forklarer at
    bekreftelsen forplikter brukeren, og samtykke ved å kalle tool-en
    på vegne av en bruker som har gitt eksplisitt instruksjon.
    """

    # Ingen felt — tool-en tar sin disclaimer-versjon og -tekst fra
    # modulkonstantene over og sender begge til backend i forretningens
    # navn.
    pass


class ConfirmRiskScoreDisclaimerOutput(BaseModel):
    confirmed: bool = Field(description="True hvis disclaimer er bekreftet for brukeren.")
    version: str = Field(description="Disclaimer-versjon som ble bekreftet (f.eks. 'v1').")
    confirmed_at: str | None = Field(
        default=None,
        description="ISO-timestamp for bekreftelsen.",
    )
    confirmed_by_user_id: int = Field(
        description="ID-en til Firmaradar-brukeren bekreftelsen er registrert mot."
    )
    audit_id: int | None = Field(
        default=None,
        description="ID for audit-raden i ``extension_kundebekreftelse_event``.",
    )
    idempotent: bool = Field(
        default=False,
        description="True hvis bekreftelsen eksisterte fra før (ingen ny rad skrevet).",
    )
    raw: dict[str, Any] | None = None


async def handle(
    client: FirmaradarClient,
    params: ConfirmRiskScoreDisclaimerInput,
) -> ConfirmRiskScoreDisclaimerOutput:
    payload = await client.post(
        "/api/v1/risikoscoring/confirm-disclaimer",
        json_body={
            "version": DISCLAIMER_VERSION,
            "confirmation": DISCLAIMER_TEXT,
        },
    )
    if not isinstance(payload, dict):
        payload = {}
    return ConfirmRiskScoreDisclaimerOutput(
        confirmed=bool(payload.get("confirmed", False)),
        version=str(payload.get("version", DISCLAIMER_VERSION)),
        confirmed_at=payload.get("confirmed_at"),
        confirmed_by_user_id=int(payload.get("confirmed_by_user_id", 0) or 0),
        audit_id=(
            int(payload["audit_id"])
            if payload.get("audit_id") is not None else None
        ),
        idempotent=bool(payload.get("idempotent", False)),
        raw=payload,
    )


HANDLER = ToolHandler(
    name="firmaradar_confirm_risk_score_disclaimer",
    description=(
        "Bekreft pre-screening-disclaimer for firmaradar_get_risk_score. "
        "Dette er en éngangs-bekreftelse per Firmaradar-bruker (ikke per "
        "agent eller per kall). Bekreftelsen er permanent og audit-"
        "loggføres. Krever at OAuth-token er knyttet til en bruker som "
        "har risikoscoring aktivert i sin pakke. Hvis bruker allerede "
        "har bekreftet, returnerer endpoint eksisterende confirmation "
        "(idempotent — samme audit_id returneres). "
        "Bekreftelsen erklærer at risikoscoring kun brukes til legitime "
        "formål (KYC, kredittvurdering-pre-screening, due diligence, "
        "leverandørscreening) og IKKE som erstatning for formell "
        "kredittvurdering eller automatisert negativ beslutning. "
        "Disclaimer-tekst og versjon er innebygd i denne tool-en og "
        "sendes til backend som en eksplisitt streng-match — for å "
        "unngå at agenten kan bekrefte en versjon den ikke har sett. "
        "Kall denne tool-en bare når brukeren eksplisitt har gitt deg "
        "instruksjon om å bekrefte disclaimeren på deres vegne."
    ),
    input_schema=ConfirmRiskScoreDisclaimerInput,
    output_schema=ConfirmRiskScoreDisclaimerOutput,
    handler=handle,
)
