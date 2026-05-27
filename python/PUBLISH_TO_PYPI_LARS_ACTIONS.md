# Publiser firmaradar-mcp til PyPI — Lars-aksjoner

**Status:** All infrastruktur er klargjort (pyproject.toml, GitHub Actions
workflow, CHANGELOG, README, sync-script). Lars må selv gjøre de stegene
som krever menneskelig interaksjon med PyPI (konto, 2FA, publisher-oppsett,
tag-push). Estimat for aktiv arbeidstid: **≤ 25 min ekskl. konto-oppretting**.

Workflow: agent forbereder → Lars opp-setter konto → Lars pusher tag →
GitHub Actions publiserer automatisk via Trusted Publishing (OIDC).

---

## Steg 1 — Opprett PyPI-konto (5 min)

URL: https://pypi.org/account/register/

- E-post: `lars@firmaradar.no` (matcher `author.email` i pyproject.toml)
- Brukernavn: f.eks. `firmaradar` eller `larskvanum` — dette navnet
  vises som "owner" på PyPI-prosjektsiden, så velg det du vil at
  kundene ser.

## Steg 2 — Verifiser e-post (1 min)

PyPI sender bekreftelseslink til e-posten over.

## Steg 3 — Aktiver 2FA (10 min)

URL: https://pypi.org/manage/account/two-factor/

- **Anbefalt:** TOTP via Authenticator-app eller hardware-key (YubiKey).
- PyPI tvinger 2FA før du får lov til å publisere.
- Lagre recovery-koder et trygt sted (BitWarden / 1Password / passord-manager).

## Steg 4 — Sett opp Trusted Publisher (5 min)

URL: https://pypi.org/manage/account/publishing/

Klikk **"Add a new publisher"** → GitHub. Fyll inn nøyaktig:

| Felt | Verdi |
|------|-------|
| PyPI Project Name | `firmaradar-mcp` |
| Owner | `Tiwas` |
| Repository name | `firmaradar-mcp` |
| Workflow filename | `publish.yml` |
| Environment name | `pypi` |

`Environment name = pypi` matcher `environment: name: pypi` i workflowen
og gir deg en manuell review-gate før hver publish (du må klikke
"Approve" i GitHub Actions-UIen før jobben kjører). Vil du dropp review-
gaten, la feltet stå tomt OG fjern `environment:`-blokken i workflowen.

**Hva dette gjør:** PyPI godtar publish-requests fra GitHub Actions-runs
i `Tiwas/firmaradar-mcp` som har OIDC-token signert for `publish.yml` i
`pypi`-environmentet — ingen `PYPI_API_TOKEN` lagres lokalt eller i
GitHub.

## Steg 5 — Reservér pakkenavn `firmaradar-mcp`

To valg, velg ett:

**A) La første tag-push reservere navnet (anbefalt).** Hopp rett til
Steg 6. Trusted Publisher må være satt opp først ellers feiler første
push siden navnet ikke eksisterer ennå — men PyPI tillater faktisk
første publish via Trusted Publisher uten pre-eksisterende prosjekt så
lenge owner/repo/workflow matcher.

**B) Manuell 0.0.1-reservasjon.** Trygt hvis du vil sikre navnet før
første "ekte" release:

```bash
cd tools/mcp_server/python
sed -i 's/version = "0.3.0"/version = "0.0.1"/' pyproject.toml
python -m build
# Du må ha twine + en (1!) midlertidig API-token for dette ene kallet:
python -m twine upload dist/firmaradar_mcp-0.0.1*
# Revert versjonen
git checkout pyproject.toml
```

Etterpå kan du yanke 0.0.1 via PyPI-UIet hvis du ikke vil at den dukker
opp i `pip install firmaradar-mcp==`.

## Steg 6 — Tag og push for første publish (2 min)

I privat-repoet:

```bash
cd ~/docker_projects/Firmaradar
git pull
# Bekreft at endringene i tools/mcp_server/ er commitet og pushet til main først
git tag -a python-v0.3.0 -m "firmaradar-mcp v0.3.0 — første PyPI-release"
git push origin python-v0.3.0
```

Deretter speil til public-repo så GitHub Actions trigges der:

```bash
scripts/sync_mcp_public.sh
# Bekreft commit + push når scriptet prompter
```

Public-repoet vil nå ha både python-koden, `.github/workflows/publish.yml`
og en commit som har pakka inn endringene. **Tag-en må også pushes til
public-repoet** — sync-scriptet pusher KUN main-branchen, så:

```bash
# Etter at sync_mcp_public.sh er ferdig:
cd /tmp/firmaradar-mcp-sync
git tag -a python-v0.3.0 -m "firmaradar-mcp v0.3.0"
git push origin python-v0.3.0
```

## Steg 7 — Verifiser at workflow kjører og publiserer (2 min)

URL: https://github.com/Tiwas/firmaradar-mcp/actions

- Du bør se en run navngitt etter tag-en (`python-v0.3.0`).
- Hvis du brukte `environment: pypi` med review-gate, må du klikke
  "Approve" på `publish-pypi`-jobben.
- Etter ~2 min: sjekk https://pypi.org/project/firmaradar-mcp/

## Steg 8 — Test installasjon (1 min)

```bash
pip install firmaradar-mcp
firmaradar-mcp --help  # eller bare `firmaradar-mcp` for å se at den
                       # starter stdio-loopen og venter på input
```

---

## Hvis noe går galt

### Workflow feiler med "OIDC token verification failed"

Trusted Publisher er ikke konfigurert riktig på PyPI. Sjekk at:
- Owner = `Tiwas` (case-sensitive)
- Repository = `firmaradar-mcp`
- Workflow = `publish.yml` (ikke full sti)
- Environment = `pypi` (matcher workflowen)

### Workflow feiler med "name already taken"

Pakkenavnet er allerede registrert av noen andre. Endre `name` i
`pyproject.toml` til f.eks. `firmaradar-mcp-server` og bump versjonen.
Husk å oppdatere `[project.scripts]`-entry-pointen følger pakkenavnet
slik at `firmaradar-mcp`-binæren fortsatt eksponeres.

### Du vil rulle ut en bug-fix raskt

1. Bump `version` i `pyproject.toml` (f.eks. `0.3.0` → `0.3.1`)
2. Bump `__version__` i `firmaradar_mcp/__init__.py`
3. Bump `_SERVER_VERSION` i `firmaradar_mcp/server.py`
4. Legg til en `## [0.3.1] — DATO`-seksjon i `CHANGELOG.md`
5. Commit, push, tag `python-v0.3.1`, kjør sync-scriptet, push tag-en
   til public-repoet
6. GitHub Actions tar resten

### Fallback: API-token-publish

Hvis Trusted Publishing-oppsettet drar ut og du vil komme i gang
umiddelbart:

1. PyPI → Account settings → API tokens → Create token
   - Scope: "Entire account" (første gang) eller
     "Project: firmaradar-mcp" (etter første publish)
2. GitHub → repo Settings → Secrets and variables → Actions →
   New repository secret: `PYPI_API_TOKEN` = `<pypi-...token...>`
3. Rediger `.github/workflows/publish.yml` i public-repoet:
   - Kommentér ut OIDC-publish-steget
   - Aktiver "API token fallback"-blokken som allerede er kommentert
     inn i filen
4. Push og tag som vanlig

Trusted Publishing er strengt bedre — gjør overgangen så fort
infrastrukturen er klar.

---

## Sjekkliste — alt agenten har forberedt

- [x] `pyproject.toml` bumpet til 0.3.0, fullstendige PyPI-metadata
      (urls, classifiers, license, authors)
- [x] `__init__.py` og `server.py` versjon bumpet
- [x] Sdist inkluderer README.md eksplisitt
      (`tool.hatch.build.targets.sdist`)
- [x] GitHub Actions workflow på
      `tools/mcp_server/.github/workflows/publish.yml` med OIDC,
      attestations, version-tag-verifisering og API-token-fallback
- [x] `scripts/sync_mcp_public.sh` utvidet til å speile `.github/`
- [x] `CHANGELOG.md` med 0.3.0-entry
- [x] README oppdatert med PyPI-badges
- [x] Lokal twine-validering grønn (`twine check dist/*`)

Lars trenger kun å gjøre Steg 1–6 over. Estimat: **25 min aktiv tid**
(konto-oppretting + 2FA + Trusted Publisher-oppsett + tag-push).
