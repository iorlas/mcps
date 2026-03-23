# Reelm — AI-native Media Agent

Reelm collects, downloads, and manages media via MCP servers (Transmission, Jackett, Storage) behind a FastMCP gateway with Google OAuth 2.1.

## Before Making Code Decisions

- **Before deploying:** `~/Documents/Knowledge/Researches/036-deployment-platform/guidelines/` — Dokploy API, Traefik, CI/CD, production lessons
- **Before changing auth/gateway:** `~/Documents/Knowledge/Researches/036-deployment-platform/guidelines/mcp-auth-gateway.md` — MCP OAuth options, provider comparison

## Dev Commands

- Run tests: `make test` (with coverage — check for uncovered lines in files you changed)
- Check diff coverage: `make coverage-diff` — coverage of changed lines vs main. Fails below 95%. Run after writing tests.
- Lint: `make lint` (check only, never modifies files — safe for AI to run anytime)
- Fix: `make fix` (auto-fix formatting and import sorting, then runs `make lint` to verify)
- Full gate: `make check` (lint + test)

## Architecture

```
Internet → FastMCP Gateway (OAuth 2.1, Google, tool federation)
               ├→ reelm-transmission (MCP server, Transmission RPC)
               ├→ reelm-jackett (MCP server, torrent search)
               ├→ reelm-storage (MCP server, WebDAV file ops)
               └→ future services (Jellyfin, mem0, etc.)
```

- **Each MCP server is standalone** — no auth, no shared state, independently deployable
- **Gateway** handles auth (Google OAuth 2.1 via FastMCP GoogleProvider) and federation (tool prefixing)
- **Source layout**: `src/mcps/servers/` — one file per MCP server, `src/mcps/shared/` — pagination, query, schema utils
- **Gateway**: `src/mcps/gateway.py` — FastMCP proxy with GoogleProvider + mounted backends

## Conventions

- All MCP tool functions go in `src/mcps/servers/<service>.py`
- Shared utilities (pagination, filtering, projection) in `src/mcps/shared/`
- Config via `pydantic-settings` in `src/mcps/config.py` — env vars, no hardcoded values
- Tests: `@pytest.mark.unit` for unit tests, `@pytest.mark.contract` for VCR replay tests
- Cassettes in `tests/cassettes/`, golden snapshots in `tests/snapshots/`

## Deployment

- **Model B**: GitHub Actions builds image → pushes to GHCR → updates Dokploy via API → deploys
- **Compose**: `docker-compose.prod.yml` is the source of truth, pushed to Dokploy atomically
- **Images**: SHA-pinned tags (`main-<sha>`), never `:latest` for our images
- **Dokploy API only** — never SSH for routine operations

## Never

- Never add auth code to MCP servers — gateway handles all auth
- Never use SSH for deployment debugging — escalation: API → UI → Swagger → SSH (last resort)
- Never use `:latest` tag for reelm images — always SHA-pinned
- Never manually create/start/stop Dokploy-managed containers with docker commands
- Never commit secrets or `.env` files

## Ask First

- Before adding a new MCP server or external dependency
- Before changing the gateway config or auth flow
- Before modifying docker-compose.prod.yml structure (networks, volumes, labels)
- Before changing the CI/CD pipeline
