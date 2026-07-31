"""Tool: ``check_aml_pep``.

Screen a name (optionally + birth year) against sanctions and PEP lists.

**Compliance — read carefully:**

This tool talks to ``POST /api/v1/aml/check`` which is PII-sensitive and
gated on:

1. **Signed DPA** with Firmaradar (kunde-tier).
2. **Per-call** DPA-confirmation headers — caller MUST supply a
   ``purpose`` string (free-text describing the legitimate purpose),
   and the tool sets ``X-FR-DPA-Confirmed: true`` automatically. Every
   request is audit-logged for 60 months (Hvitvaskingsloven § 30).
3. **Tight rate-limit** — 50 calls per 30 min per API-key. Burst
   traffic is throttled with ``429`` + ``Retry-After``.

If your agent has no specific legitimate purpose for screening a person,
DO NOT call this tool.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class CheckAmlPepInput(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=200,
        description=(
            "Full name of ONE natural PERSON to screen (e.g. 'Ola Nordmann'). "
            "NOT a company name or orgnr — for company AML use "
            "firmaradar_get_aml_score instead."
        ),
    )
    birth_year: int | None = Field(default=None, ge=1900, le=2100)
    kategori: Literal["sanksjon", "pep", "both"] = Field(default="both")
    min_match_ratio: float = Field(default=0.85, ge=0.0, le=1.0)
    # NB: ``purpose`` er ikke valgfri — kunden må alltid oppgi
    # legitimt formål per kall. Sendes som X-FR-Purpose-header til
    # backend og logges i audit-trail (60 mnd retention).
    purpose: str = Field(
        min_length=4,
        max_length=500,
        description=(
            "Legitimate purpose for this AML/PEP screening (free text, "
            "e.g. 'KYC verification for new customer acme-as'). "
            "Logged in compliance audit for 60 months."
        ),
    )


class AmlPepHit(BaseModel):
    primart_navn: str
    kategori: str
    entitet_type: str | None = None
    kilder: list[str] = Field(default_factory=list)
    match_ratio: float
    match_type: str  # "eksakt" | "fuzzy" | "contains"
    # "contains" = weak network match (name contains the query keyword), NOT a
    # confirmed same-entity hit — verify manually, never treat as authoritative.
    weak_match: bool = False
    ekstern_id: str | None = None
    # Date-verifiability of the hit (all categories). `fodselsdato` is the
    # register row's birth date/year (free-form); `fodselsdato_mangler: true`
    # means the row has NO birth date — the match is name-only and the identity
    # CANNOT be date-verified. Verify manually before weighting such hits.
    # Explicit flag (not just `fodselsdato: null`) per the 2026-07-31
    # transparency decision. Always False for entitet_type=organisasjon
    # (companies have no birth date). Note: a `birth_year` query filter only
    # excludes rows that HAVE a year — dateless rows pass through carrying
    # this flag.
    fodselsdato: str | None = None
    fodselsdato_mangler: bool = False
    # PEP context — populated only for `kategori == "pep"` hits (None for sanctions).
    # `pep_status` ∈ {aktiv, tidligere, historisk}; `embete` is the class-level office
    # (e.g. "Statsråd/minister"); `verv_fra`/`verv_til` are the collapsed ISO period.
    pep_status: str | None = None
    embete: str | None = None
    verv_fra: str | None = None
    verv_til: str | None = None
    # Full date-stamped office timeline (one row per position period, P580/P582
    # preserved): [{embete, klasse, tittel, pos_qid, fra, til}]. `tittel` is the
    # specific position label ("næringsminister") when resolved; empty for sanctions
    # and for PEP rows seeded before title enrichment.
    verv_historikk: list[dict[str, Any]] = Field(default_factory=list)
    # RCA marking (related/close-associate transparency). `pep_type` ∈
    # {direkte, rca_familie, rca_medarbeider}: rca_* = person RELATED to a PEP,
    # not themselves politically exposed. `relasjon` is display prose («Søsken
    # av Ola Nordmann»); `relasjon_kode` the stable form (far/mor/ektefelle/
    # barn/sosken/barns_ektefelle). `relasjon_innenfor_direktivet` is
    # TRI-STATE: True = listed in AML-law § 2 g close-family circle; False =
    # outside it (siblings — included as a signal, not a required match);
    # None = UNKNOWN (pre-migration rows) — never treat None as "outside".
    # `matchgrunnlag` ∈ {navn_alene, navn_og_fodselsaar} (family-RCA only).
    pep_type: str | None = None
    relasjon: str | None = None
    relasjon_kode: str | None = None
    relasjon_innenfor_direktivet: bool | None = None
    matchgrunnlag: str | None = None


class CheckAmlPepOutput(BaseModel):
    query_name: str
    query_birth_year: int | None = None
    hits: list[AmlPepHit]
    hit_count: int
    # True when the query was < 5 chars: only exact/fuzzy was run (no substring
    # discovery). A zero hit_count then does NOT confirm the name is clean.
    query_too_short: bool = False
    note: str | None = None


async def handle(
    client: FirmaradarClient, params: CheckAmlPepInput
) -> CheckAmlPepOutput:
    """Invoke ``POST /api/v1/aml/check`` with DPA-confirmation headers.

    The ``purpose`` field is mapped to ``X-FR-Purpose`` and
    ``X-FR-DPA-Confirmed: true`` is set automatically.

    HTTP headers are ASCII-only per RFC 7230, so non-ASCII characters
    in ``purpose`` (æøå, em-dash, etc.) must be URL-encoded before
    being passed as a header value. Backend reverses the encoding via
    ``urllib.parse.unquote`` before audit-logging.
    """
    from urllib.parse import quote

    payload = {
        "name": params.name,
        "birth_year": params.birth_year,
        "kategori": params.kategori,
        "min_match_ratio": params.min_match_ratio,
    }
    # Encode purpose as RFC 3986 percent-encoding (UTF-8 → %XX bytes).
    # `safe=""` ensures even space → %20 (no '+' substitution which would
    # be valid in form-data but ambiguous in headers).
    encoded_purpose = quote(params.purpose, safe="")
    data = await client.post(
        "/api/v1/aml/check",
        json_body=payload,
        extra_headers={
            "X-FR-Purpose": encoded_purpose,
            "X-FR-Purpose-Encoding": "url",
            "X-FR-DPA-Confirmed": "true",
        },
    )
    return CheckAmlPepOutput(**data)


HANDLER = ToolHandler(
    name="firmaradar_check_aml_pep",
    description=(
        "Screen ONE natural PERSON's full name against sanctions (OFAC, EU, UN) "
        "and PEP lists. "
        "IMPORTANT — this is a PERSON tool only. Do NOT pass a company name, an "
        "organisation number (orgnr), or any non-person string here. For "
        "company-level AML risk use `firmaradar_get_aml_score` (by orgnr); to "
        "screen a company's owners/officers, first resolve the people via "
        "`firmaradar_get_company_roles` / `firmaradar_get_company_ownership`, "
        "then screen each PERSON name with this tool. "
        "Compliance-critical: PII-sensitive, requires a signed DPA and a "
        "legitimate purpose per call (free-text `purpose` parameter). "
        "Audit-logged for 60 months. Rate-limited to 50 calls / 30 min per "
        "API-key. Returns structured hits with category, sources, and "
        "match-ratio (default min 0.85)."
    ),
    input_schema=CheckAmlPepInput,
    output_schema=CheckAmlPepOutput,
    handler=handle,
)
