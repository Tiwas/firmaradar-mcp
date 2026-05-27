# Dockerfile for firmaradar-mcp-remote (Steg A av Android Claude MCP).
#
# Slank Python 3.12-image som installerer pakken med [remote]-extras
# og kjører firmaradar-mcp-remote på 0.0.0.0:8765. Designet for å
# kjøres bak nginx på mcp.firmaradar.no (Lars-beslutning 2026-05-26:
# bruk eksisterende nginx-container med Cloudflare DNS Only + Let's
# Encrypt — IKKE Synologys innebygde reverse-proxy).
#
# Bruk:
#   docker compose -f docker-compose.yml -f docker-compose.mcp.yml up -d firmaradar_mcp_remote
#
# Health-check:
#   curl http://localhost:8765/health

FROM python:3.12-slim AS build

# Bygg-context = tools/mcp_server/ (NB: ikke python/) slik at
# `readme = "../README.md"` i pyproject.toml peker innenfor konteksten.
# Vi setter likevel WORKDIR = /build/python så pip install '.' finner
# pyproject.toml på riktig sted.
WORKDIR /build/python

# Kopier README inn først (utenfor pakke-dir, men referert via ../).
COPY README.md /build/README.md
# Kopier deretter Python-pakken.
COPY python/pyproject.toml ./
COPY python/firmaradar_mcp/ ./firmaradar_mcp/

# Installer pakken med [remote]-extras inn i et venv vi kan kopiere
# inn i prod-imagen. Dette gjør at prod-imagen ikke trenger pip selv.
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir '.[remote]'


FROM python:3.12-slim AS prod

# Kopier ferdig-bygd venv fra build-laget.
COPY --from=build /opt/venv /opt/venv

# Kjør som ikke-rot UID 1000 (matcher firmaradar_web-konvensjon).
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin firmaradar
USER 1000:1000

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    FIRMARADAR_MCP_HOST=0.0.0.0 \
    FIRMARADAR_MCP_PORT=8765

EXPOSE 8765

# Health-check via /health-endpointet i remote_server.py
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request, sys; \
        sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=3).status == 200 else 1)"

ENTRYPOINT ["/opt/venv/bin/firmaradar-mcp-remote"]
CMD ["--host", "0.0.0.0", "--port", "8765"]
