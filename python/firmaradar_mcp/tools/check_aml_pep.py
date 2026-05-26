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

from typing import Literal

from pydantic import BaseModel, Field

from ..client import FirmaradarClient
from . import ToolHandler


class CheckAmlPepInput(BaseModel):
    name: str = Field(min_length=2, max_length=200, description="Full name to screen.")
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
    match_type: str
    ekstern_id: str | None = None


class CheckAmlPepOutput(BaseModel):
    query_name: str
    query_birth_year: int | None = None
    hits: list[AmlPepHit]
    hit_count: int


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
    name="firmaradar.check_aml_pep",
    description=(
        "Screen a person's name against sanctions (OFAC, EU, UN) and PEP lists. "
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
