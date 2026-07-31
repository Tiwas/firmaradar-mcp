"""Tool: ``get_person``.

Unified summary for one person — active roles + shareholdings +
bankruptcy-exposure review flag in a single payload.

Backend: ``GET /api/v1/person/{person_id}`` — the server-side aggregate.
The endpoint resolves the ID variant itself (``person-YYYY-…`` gives
shareholdings, ``role-…`` gives active roles) and normalizes both to the
same key set, so this tool is a single call with no client-side dispatch.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..client import FirmaradarClient, FirmaradarClientError
from . import ToolHandler


class GetPersonInput(BaseModel):
    person_id: str = Field(
        description=(
            "Person ID — either `person-YYYY-[24 hex]` (from `search_persons` "
            "shareholders) or `role-[24 hex]` (from `search_persons` role_persons)."
        )
    )
    purpose: str | None = Field(
        default=None,
        description=(
            "Purpose-of-processing string for the F10.11 audit trail. "
            "Required when calling against accounts with purpose-confirmation."
        ),
    )


class GetPersonOutput(BaseModel):
    person_id: str
    navn: str
    birth_year: int | None = None
    summary: str | None = None
    active_roles: list[dict[str, Any]] = Field(default_factory=list)
    shareholdings: list[dict[str, Any]] = Field(default_factory=list)
    aml_pep_hits: list[dict[str, Any]] = Field(default_factory=list)
    # Rammen fra backend: dette oppslaget gjør INGEN PEP-/sanksjonssjekk, så en
    # tom `aml_pep_hits` betyr ikke «ingen treff». Uten denne noten kan en
    # agent-/CRM-flyt konkludere at personen er ren — bruk `check_aml_pep` /
    # `start_aml_report` for et faktisk oppslag.
    aml_pep_note: str | None = None
    # Name-based bankruptcy exposure ("konkursgjenganger"): leadership roles this
    # person held in companies that later went bankrupt, tenure-weighted, from the
    # dated role history. Since the match is by NAME (no national ID number), this
    # is a REVIEW FLAG, not a verdict — `note` carries that framing.
    konkurs_eksponering: dict[str, Any] = Field(default_factory=dict)


async def handle(
    client: FirmaradarClient, params: GetPersonInput
) -> GetPersonOutput:
    # Server-side-aggregatet samler navn, aktive verv, aksjeposter, summary og
    # konkurs-eksponering i ETT kall — svarformen er identisk med det den
    # tidligere to-kalls fan-out-varianten sammenstilte klient-side.
    # `purpose` beholdes i input-skjemaet (F10.11-kontrakten); GET-stien i
    # klienten sender ingen ekstra headers — uendret fra fan-out-varianten.
    pid = params.person_id

    payload: dict[str, Any] = {}
    try:
        raw = await client.get(f"/api/v1/person/{pid}")
        if isinstance(raw, dict):
            payload = raw
    except FirmaradarClientError:
        # Samme degradering som fan-out-varianten: ukjent ID, ugyldig
        # ID-format eller manglende tilgang gir en tom profil — ikke en feil.
        payload = {}

    navn = str(payload.get("navn") or "")

    birth_year: int | None = None
    by_raw = payload.get("birth_year")
    if by_raw is not None:
        try:
            birth_year = int(by_raw)
        except (TypeError, ValueError):
            pass

    summary_raw = payload.get("summary")
    summary = summary_raw if isinstance(summary_raw, str) else None

    active_roles = [
        r for r in (payload.get("active_roles") or []) if isinstance(r, dict)
    ]
    shareholdings = [
        s for s in (payload.get("shareholdings") or []) if isinstance(s, dict)
    ]
    aml_pep_hits = [
        h for h in (payload.get("aml_pep_hits") or []) if isinstance(h, dict)
    ]

    note_raw = payload.get("aml_pep_note")
    aml_pep_note = note_raw if isinstance(note_raw, str) else None

    # Aggregatet serverer alltid en konkurs-eksponering-blokk (også ved 0
    # treff). Tom-normaliseringen beholdes fra fan-out-varianten: uten treff
    # forblir feltet `{}` i stedet for en null-blokk med tom note.
    konkurs_eksponering: dict[str, Any] = {}
    ke = payload.get("konkurs_eksponering")
    if isinstance(ke, dict) and ke.get("antall_konkursforetak"):
        konkurs_eksponering = ke

    return GetPersonOutput(
        person_id=pid,
        navn=navn,
        birth_year=birth_year,
        summary=summary,
        active_roles=active_roles,
        shareholdings=shareholdings,
        aml_pep_hits=aml_pep_hits,
        aml_pep_note=aml_pep_note,
        konkurs_eksponering=konkurs_eksponering,
    )


HANDLER = ToolHandler(
    name="firmaradar_get_person",
    description=(
        "Aggregated person profile: name, birth year, active roles, "
        "shareholdings and any AML/PEP risk hits. Also returns "
        "`konkurs_eksponering` — leadership roles the person held in companies "
        "that later went bankrupt (tenure-weighted, from the dated role "
        "history). That match is name-based (no national ID), so it is a "
        "REVIEW FLAG to verify, not a verdict. Note: this profile lookup does "
        "NOT run a PEP/sanctions screening — an empty `aml_pep_hits` is not a "
        "clean bill; use `firmaradar_check_aml_pep` for an actual screening. "
        "Strict PII-sensitive — requires search_full_enabled tier and F10.11 "
        "purpose confirmation. Minors are blocked except for super-admin "
        "accounts."
    ),
    input_schema=GetPersonInput,
    output_schema=GetPersonOutput,
    handler=handle,
)
