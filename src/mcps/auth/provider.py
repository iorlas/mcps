"""OAuth 2.1 provider with username/password login for MCP servers.

Subclasses FastMCP's InMemoryOAuthProvider, adding:
- bcrypt password verification
- HTML login page flow (authorize -> login -> redirect with code)
- Persistent state across restarts (JSON file)
"""

import json
import re
import secrets
from html import escape
from pathlib import Path

import bcrypt
from loguru import logger
from mcp.server.auth.provider import (
    AuthorizationParams,
)
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from fastmcp.server.auth.auth import ClientRegistrationOptions
from fastmcp.server.auth.providers.in_memory import (
    AccessToken,
    AuthorizationCode,
    InMemoryOAuthProvider,
    RefreshToken,
)

_LOGIN_TEMPLATE = (Path(__file__).parent / "login.html").read_text()


class McpsOAuthProvider(InMemoryOAuthProvider):
    """OAuth provider with bcrypt credential validation, login page, and persistence."""

    def __init__(
        self,
        *,
        base_url: AnyHttpUrl | str,
        users: dict[str, str],  # {username: bcrypt_hash}
        required_scopes: list[str] | None = None,
        state_dir: str = "/data/auth",
    ):
        super().__init__(
            base_url=base_url,
            required_scopes=required_scopes,
            client_registration_options=ClientRegistrationOptions(
                enabled=True,
            ),
        )
        self._users = users
        # Pending auth sessions: session_id -> (client, params)
        self._pending_auth: dict[str, tuple[OAuthClientInformationFull, AuthorizationParams]] = {}

        # Persistence
        self._state_dir = Path(state_dir)
        self._load_state()

    def _state_file(self) -> Path:
        """Derive state filename from base_url (one file per service)."""
        name = str(self.issuer_url).replace("https://", "").replace("http://", "").replace("/", "_")
        return self._state_dir / f"{name}.json"

    def _load_state(self) -> None:
        """Load persisted OAuth state from disk."""
        path = self._state_file()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            for cid, obj in data.get("clients", {}).items():
                self.clients[cid] = OAuthClientInformationFull.model_validate(obj)
            for tok, obj in data.get("access_tokens", {}).items():
                self.access_tokens[tok] = AccessToken.model_validate(obj)
            for tok, obj in data.get("refresh_tokens", {}).items():
                self.refresh_tokens[tok] = RefreshToken.model_validate(obj)
            for k, v in data.get("access_to_refresh", {}).items():
                self._access_to_refresh_map[k] = v
            for k, v in data.get("refresh_to_access", {}).items():
                self._refresh_to_access_map[k] = v
            logger.info(f"auth.loaded_state clients={len(self.clients)} tokens={len(self.access_tokens)} from={path}")
        except Exception as e:
            logger.warning(f"auth.load_state_failed path={path} error={e}")

    def _save_state(self) -> None:
        """Persist OAuth state to disk."""
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            data = {
                "clients": {k: v.model_dump(mode="json") for k, v in self.clients.items()},
                "access_tokens": {k: v.model_dump(mode="json") for k, v in self.access_tokens.items()},
                "refresh_tokens": {k: v.model_dump(mode="json") for k, v in self.refresh_tokens.items()},
                "access_to_refresh": dict(self._access_to_refresh_map),
                "refresh_to_access": dict(self._refresh_to_access_map),
            }
            self._state_file().write_text(json.dumps(data, default=str))
        except Exception as e:
            logger.warning(f"auth.save_state_failed error={e}")

    # -- Override state-mutating methods to trigger persistence --

    async def register_client(self, client_info):
        result = await super().register_client(client_info)
        self._save_state()
        return result

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """Redirect to login page instead of auto-approving."""
        session_id = secrets.token_urlsafe(32)
        self._pending_auth[session_id] = (client, params)
        return f"/login?session_id={session_id}"

    async def exchange_authorization_code(self, client, code):
        result = await super().exchange_authorization_code(client, code)
        self._save_state()
        return result

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        result = await super().exchange_refresh_token(client, refresh_token, scopes)
        self._save_state()
        return result

    async def revoke_token(self, client, token):
        result = await super().revoke_token(client, token)
        self._save_state()
        return result

    def verify_credentials(self, username: str, password: str) -> bool:
        """Check username/password against bcrypt hashes."""
        stored_hash = self._users.get(username)
        if stored_hash is None:
            return False
        return bcrypt.checkpw(password.encode(), stored_hash.encode())

    def _render_login(self, session_id: str, error: str = "") -> str:
        """Render login template with HTML-escaped string replacement."""
        html = _LOGIN_TEMPLATE
        html = html.replace("{{ session_id }}", escape(session_id))
        html = html.replace("{{ error }}", escape(error))
        if error:
            html = html.replace("{% if error %}", "").replace("{% endif %}", "")
        else:
            # Remove the error block
            html = re.sub(r"\{% if error %\}.*?\{% endif %\}", "", html, flags=re.DOTALL)
        return html

    async def _handle_login_get(self, request: Request) -> HTMLResponse:
        """Show login form."""
        session_id = request.query_params.get("session_id", "")
        return HTMLResponse(self._render_login(session_id))

    async def _handle_login_post(self, request: Request) -> RedirectResponse | HTMLResponse:
        """Validate credentials and issue auth code."""
        form = await request.form()
        session_id = str(form.get("session_id", ""))
        username = str(form.get("username", ""))
        password = str(form.get("password", ""))

        if session_id not in self._pending_auth:
            return HTMLResponse(self._render_login(session_id, error="Session expired. Please try again."))

        if not self.verify_credentials(username, password):
            return HTMLResponse(self._render_login(session_id, error="Invalid username or password."))

        # Credentials valid -- issue auth code using parent's logic
        client, params = self._pending_auth.pop(session_id)
        redirect_uri = await super().authorize(client, params)
        return RedirectResponse(url=redirect_uri, status_code=302)

    def get_routes(self, mcp_path: str | None = None) -> list[Route]:
        """Add login routes to the standard OAuth routes."""
        routes = super().get_routes(mcp_path)
        routes.extend([
            Route("/login", endpoint=self._handle_login_get, methods=["GET"]),
            Route("/login", endpoint=self._handle_login_post, methods=["POST"]),
        ])
        return routes
