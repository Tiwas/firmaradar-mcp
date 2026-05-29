# Tool selection cheat-sheet

Map the user's intent to the right `firmaradar_*` tool. Tools take a Norwegian
organization number (`orgnr`, 9 digits) or a person identity unless noted.

## Company core

| Intent | Tool |
|---|---|
| Profile / master data for one company | `firmaradar_get_company` |
| Find a company by name / fuzzy query | `firmaradar_search_companies` |
| Board, managing director, signatory, proxy, auditor roles | `firmaradar_get_company_roles` |
| Annual financials (income statement / balance) | `firmaradar_get_company_financials` |
| BRREG announcements (kunngjøringer) for a company | `firmaradar_get_company_announcements` |
| Aggregated change/distress signals for a company | `firmaradar_get_company_signals` |
| Recent changes across the register | `firmaradar_get_recent_changes` |
| Side-by-side comparison of several companies | `firmaradar_compare_companies` |

## Ownership and groups

| Intent | Tool |
|---|---|
| Who owns this company / what does it own (UBO tree, up/down/both) | `firmaradar_get_company_ownership` |
| Related companies (shared owners/roles) | `firmaradar_find_related_companies` |
| Group-support / konsernstøtte view | `firmaradar_get_konsernstotte` |

## Risk and distress

| Intent | Tool | Note |
|---|---|---|
| Transparent 0–100 company risk score | `firmaradar_get_risk_score` | Call `firmaradar_confirm_risk_score_disclaimer` first |
| Risk score for many companies | `firmaradar_get_risk_score_bulk` | Disclaimer first |
| Is the company in difficulty (FIV / foretak i vanskeligheter)? | `firmaradar_check_foretak_i_vanskeligheter` | Statutory, deterministic |
| FIV for many companies | `firmaradar_check_fiv_bulk` | |

`get_risk_score` is **company** financial health, not a personal credit score.

## AML / PEP / sanctions / tax

| Intent | Tool |
|---|---|
| AML + PEP + sanctions screening | `firmaradar_check_aml_pep` |
| AML score | `firmaradar_get_aml_score` |
| Tax-list data (gated) | `firmaradar_get_skattelister` |

`get_skattelister` is compliance-gated (purpose + full-ownership + audit) and may
return a gate response instead of data.

## People

| Intent | Tool |
|---|---|
| Find / disambiguate a person | `firmaradar_search_persons` |
| Person profile | `firmaradar_get_person` |
| Roles a person holds across companies | `firmaradar_get_person_roles` |
| Companies a person is connected to | `firmaradar_get_person_companies` |

Resolve identity with `search_persons` before the `get_person*` tools — Norwegian
names are frequently shared.

## Industry / sector

| Intent | Tool | Note |
|---|---|---|
| Companies in a NACE industry, filtered by status/kommune/size/founding date | `firmaradar_list_companies_in_nace` | EU NACE format (`62.100`); see `NACE_FORMAT.md` |
| Search announcements across companies | `firmaradar_search_announcements` |

## Typical multi-step flows

- **KYC onboarding:** `get_company` → `get_company_roles` → `get_company_ownership`
  (UBO) → `check_aml_pep` on signatories/owners → `confirm_risk_score_disclaimer`
  → `get_risk_score`.
- **Vendor-risk monitoring:** `get_company_signals` +
  `check_foretak_i_vanskeligheter` + `get_recent_changes`.
- **Prospecting:** `list_companies_in_nace` (NACE + kommune + size +
  `stiftet_etter`) → `get_company_financials` on the shortlist.
