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
* User-Agent i audit-tabellen inkluderer klient-marker-headeren
  (``X-FR-Client`` foretrukket, eller legacy ``X-MCP-Client``) slik
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
    confirmed: bool = Field(description="True if the disclaimer is confirmed for the user.")
    version: str = Field(description="Disclaimer version that was confirmed (e.g. 'v1').")
    confirmed_at: str | None = Field(
        default=None,
        description="ISO timestamp of the confirmation.",
    )
    confirmed_by_user_id: int = Field(
        description="ID of the Firmaradar user the confirmation is registered against."
    )
    audit_id: int | None = Field(
        default=None,
        description="ID of the audit row in ``extension_kundebekreftelse_event``.",
    )
    idempotent: bool = Field(
        default=False,
        description="True if the confirmation already existed (no new row written).",
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
        "Confirm the pre-screening disclaimer required by "
        "firmaradar_get_risk_score. This is a one-time confirmation per "
        "Firmaradar user (not per agent and not per call); it is permanent "
        "and audit-logged. Requires an OAuth token tied to a user whose "
        "plan has risk scoring enabled. Idempotent — if the user has "
        "already confirmed, the existing confirmation is returned (same "
        "audit_id). The confirmation declares that risk scoring is used "
        "only for legitimate purposes (KYC, credit pre-screening, due "
        "diligence, supplier screening) and NOT as a substitute for a "
        "formal credit assessment or an automated adverse decision. The "
        "disclaimer text and version are embedded in this tool and sent to "
        "the backend as an explicit string match, so an agent cannot "
        "confirm a version it has not seen. Call this tool only when the "
        "user has explicitly instructed you to confirm the disclaimer on "
        "their behalf."
    ),
    input_schema=ConfirmRiskScoreDisclaimerInput,
    output_schema=ConfirmRiskScoreDisclaimerOutput,
    handler=handle,
)
