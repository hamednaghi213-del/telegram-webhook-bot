import base64
import hashlib
import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)


# =========================================================
# X OAUTH 2.0 / PKCE CONFIGURATION
# =========================================================

X_AUTHORIZE_URL = os.getenv(
    "X_OAUTH_AUTHORIZE_URL",
    "https://x.com/i/oauth2/authorize",
)

X_TOKEN_URL = os.getenv(
    "X_OAUTH_TOKEN_URL",
    "https://api.x.com/2/oauth2/token",
)

X_ME_URL = os.getenv(
    "X_API_ME_URL",
    "https://api.x.com/2/users/me",
)

X_CLIENT_ID = os.getenv(
    "X_CLIENT_ID",
    "",
).strip()

X_CLIENT_SECRET = os.getenv(
    "X_CLIENT_SECRET",
    "",
).strip()

X_OAUTH_REDIRECT_URI = os.getenv(
    "X_OAUTH_REDIRECT_URI",
    "",
).strip()

X_OAUTH_ENCRYPTION_KEY = os.getenv(
    "X_OAUTH_ENCRYPTION_KEY",
    "",
).strip()

X_OAUTH_SESSION_TTL_SECONDS = int(
    os.getenv(
        "X_OAUTH_SESSION_TTL_SECONDS",
        "600",
    )
)

X_HTTP_TIMEOUT_SECONDS = int(
    os.getenv(
        "X_HTTP_TIMEOUT_SECONDS",
        "20",
    )
)

X_OAUTH_SCOPES = tuple(
    item
    for item in (
        os.getenv(
            "X_OAUTH_SCOPES",
            "tweet.read tweet.write users.read offline.access",
        )
        .replace(",", " ")
        .split()
    )
    if item
)


# =========================================================
# RESULT MODEL
# =========================================================

@dataclass(frozen=True)
class XOAuthCallbackResult:
    workspace_id: int
    destination_id: Optional[int]
    requested_by_user_id: Optional[int]
    action: str

    x_user_id: str
    x_username: Optional[str]
    x_display_name: Optional[str]

    access_token_ciphertext: str
    refresh_token_ciphertext: Optional[str]

    token_expires_at: Optional[float]
    granted_scopes: tuple[str, ...]


# =========================================================
# CONFIG VALIDATION
# =========================================================

def _require_config() -> None:
    missing = []

    if not X_CLIENT_ID:
        missing.append("X_CLIENT_ID")

    if not X_OAUTH_REDIRECT_URI:
        missing.append("X_OAUTH_REDIRECT_URI")

    if not X_OAUTH_ENCRYPTION_KEY:
        missing.append("X_OAUTH_ENCRYPTION_KEY")

    if missing:
        raise RuntimeError(
            "Missing X OAuth configuration: "
            + ", ".join(missing)
        )


# =========================================================
# TOKEN ENCRYPTION
# =========================================================

def _fernet():
    """
    Load cryptography lazily.

    Keeping this import lazy prevents unrelated Telegram/Bale startup paths
    from failing before the X feature is actually used.
    """
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise RuntimeError(
            "cryptography package is required for X OAuth"
        ) from exc

    if not X_OAUTH_ENCRYPTION_KEY:
        raise RuntimeError(
            "X_OAUTH_ENCRYPTION_KEY is not configured"
        )

    try:
        return Fernet(
            X_OAUTH_ENCRYPTION_KEY.encode("utf-8")
        )
    except Exception as exc:
        raise RuntimeError(
            "X_OAUTH_ENCRYPTION_KEY is invalid"
        ) from exc


def encrypt_x_secret(value: str) -> str:
    if value is None:
        raise ValueError("X secret cannot be None")

    encoded = str(value).encode("utf-8")

    return (
        _fernet()
        .encrypt(encoded)
        .decode("utf-8")
    )


def decrypt_x_secret(ciphertext: str) -> str:
    if not ciphertext:
        raise ValueError(
            "Encrypted X secret is required"
        )

    return (
        _fernet()
        .decrypt(
            str(ciphertext).encode("utf-8")
        )
        .decode("utf-8")
    )


# =========================================================
# PKCE / STATE
# =========================================================

def generate_pkce_verifier() -> str:
    """
    Produce an RFC 7636 compatible high-entropy verifier.
    """
    verifier = secrets.token_urlsafe(64)

    # token_urlsafe can be longer than RFC 7636's 128 char maximum.
    return verifier[:128]


def build_pkce_challenge(
    verifier: str,
) -> str:
    digest = hashlib.sha256(
        verifier.encode("ascii")
    ).digest()

    return (
        base64.urlsafe_b64encode(digest)
        .rstrip(b"=")
        .decode("ascii")
    )


def generate_oauth_state() -> str:
    return secrets.token_urlsafe(32)


def hash_oauth_state(
    state: str,
) -> str:
    return hashlib.sha256(
        str(state).encode("utf-8")
    ).hexdigest()


# =========================================================
# AUTHORIZATION START
# =========================================================

def start_x_oauth(
    *,
    workspace_id: int,
    requested_by_user_id: Optional[int],
    destination_id: Optional[int] = None,
    action: str = "connect",
) -> str:
    """
    Create a short-lived PKCE session and return the official X authorize URL.

    Raw OAuth state and raw PKCE verifier are never persisted.
    """
    _require_config()

    if action not in {
        "connect",
        "reconnect",
    }:
        raise ValueError(
            "Invalid X OAuth action"
        )

    from core.database import (
        create_x_oauth_session,
    )

    verifier = generate_pkce_verifier()
    challenge = build_pkce_challenge(
        verifier
    )

    state = generate_oauth_state()
    state_hash = hash_oauth_state(
        state
    )

    expires_at = (
        time.time()
        + max(
            60,
            int(
                X_OAUTH_SESSION_TTL_SECONDS
            ),
        )
    )

    create_x_oauth_session(
        state_hash=state_hash,
        workspace_id=int(
            workspace_id
        ),
        destination_id=(
            int(destination_id)
            if destination_id is not None
            else None
        ),
        requested_by_user_id=(
            int(requested_by_user_id)
            if requested_by_user_id
            is not None
            else None
        ),
        action=action,
        code_verifier_ciphertext=(
            encrypt_x_secret(
                verifier
            )
        ),
        redirect_uri=(
            X_OAUTH_REDIRECT_URI
        ),
        expires_at=expires_at,
    )

    params = {
        "response_type": "code",
        "client_id": X_CLIENT_ID,
        "redirect_uri": (
            X_OAUTH_REDIRECT_URI
        ),
        "scope": " ".join(
            X_OAUTH_SCOPES
        ),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }

    return (
        f"{X_AUTHORIZE_URL}?"
        f"{urlencode(params)}"
    )


# =========================================================
# TOKEN EXCHANGE
# =========================================================

def _exchange_code_for_tokens(
    *,
    code: str,
    code_verifier: str,
    redirect_uri: str,
) -> Dict[str, Any]:
    data = {
        "grant_type": (
            "authorization_code"
        ),
        "code": str(code),
        "redirect_uri": str(
            redirect_uri
        ),
        "code_verifier": str(
            code_verifier
        ),
    }

    auth = None

    if X_CLIENT_SECRET:
        auth = (
            X_CLIENT_ID,
            X_CLIENT_SECRET,
        )
    else:
        data["client_id"] = (
            X_CLIENT_ID
        )

    response = requests.post(
        X_TOKEN_URL,
        data=data,
        auth=auth,
        headers={
            "Accept": (
                "application/json"
            ),
        },
        timeout=(
            X_HTTP_TIMEOUT_SECONDS
        ),
    )

    if response.status_code >= 400:
        logger.warning(
            "X OAuth token exchange failed | "
            "status=%s | body=%s",
            response.status_code,
            response.text[:500],
        )

        raise RuntimeError(
            "X OAuth token exchange failed"
        )

    payload = response.json() or {}

    access_token = str(
        payload.get(
            "access_token"
        )
        or ""
    ).strip()

    if not access_token:
        raise RuntimeError(
            "X OAuth response did not contain an access token"
        )

    return payload


# =========================================================
# AUTHENTICATED ACCOUNT
# =========================================================

def _get_authenticated_x_user(
    access_token: str,
) -> Dict[str, Any]:
    response = requests.get(
        X_ME_URL,
        headers={
            "Authorization": (
                f"Bearer {access_token}"
            ),
            "Accept": (
                "application/json"
            ),
        },
        timeout=(
            X_HTTP_TIMEOUT_SECONDS
        ),
    )

    if response.status_code >= 400:
        logger.warning(
            "X authenticated user lookup failed | "
            "status=%s | body=%s",
            response.status_code,
            response.text[:500],
        )

        raise RuntimeError(
            "Could not read authenticated X account"
        )

    payload = response.json() or {}
    user = payload.get("data") or {}

    x_user_id = str(
        user.get("id") or ""
    ).strip()

    if not x_user_id:
        raise RuntimeError(
            "X account response did not contain a user id"
        )

    return user


# =========================================================
# CALLBACK COMPLETION
# =========================================================

def complete_x_oauth_callback(
    *,
    state: str,
    code: str,
) -> XOAuthCallbackResult:
    """
    Validate and consume one OAuth state, exchange the code, and resolve
    the authenticated X account.

    This function intentionally does not create the publication destination.
    The Workspace integration layer owns that association and will persist
    the returned encrypted credentials only after it has bound the correct
    destination.
    """
    _require_config()

    if not state:
        raise ValueError(
            "Missing X OAuth state"
        )

    if not code:
        raise ValueError(
            "Missing X OAuth authorization code"
        )

    from core.database import (
        consume_x_oauth_session,
        get_x_oauth_session_by_state_hash,
    )

    state_hash = hash_oauth_state(
        state
    )

    session = (
        get_x_oauth_session_by_state_hash(
            state_hash
        )
    )

    if not session:
        raise RuntimeError(
            "X OAuth session is invalid or already consumed"
        )

    expires_at = float(
        session.get("expires_at")
        or 0
    )

    if (
        expires_at <= time.time()
    ):
        # Consume expired sessions to make replay impossible.
        consume_x_oauth_session(
            int(session["id"])
        )

        raise RuntimeError(
            "X OAuth session has expired"
        )

    consumed = (
        consume_x_oauth_session(
            int(session["id"])
        )
    )

    if not consumed:
        raise RuntimeError(
            "X OAuth session was already consumed"
        )

    verifier = decrypt_x_secret(
        str(
            session.get(
                "code_verifier_ciphertext"
            )
            or ""
        )
    )

    token_payload = (
        _exchange_code_for_tokens(
            code=code,
            code_verifier=verifier,
            redirect_uri=str(
                session.get(
                    "redirect_uri"
                )
                or ""
            ),
        )
    )

    access_token = str(
        token_payload.get(
            "access_token"
        )
        or ""
    )

    refresh_token = (
        str(
            token_payload.get(
                "refresh_token"
            )
        )
        if token_payload.get(
            "refresh_token"
        )
        else None
    )

    user = (
        _get_authenticated_x_user(
            access_token
        )
    )

    expires_in = (
        token_payload.get(
            "expires_in"
        )
    )

    token_expires_at = None

    if expires_in is not None:
        try:
            token_expires_at = (
                time.time()
                + float(expires_in)
            )
        except (
            TypeError,
            ValueError,
        ):
            token_expires_at = None

    raw_scope = str(
        token_payload.get(
            "scope"
        )
        or ""
    )

    scopes = tuple(
        item
        for item in (
            raw_scope
            .replace(",", " ")
            .split()
        )
        if item
    )

    return XOAuthCallbackResult(
        workspace_id=int(
            session["workspace_id"]
        ),
        destination_id=(
            int(
                session[
                    "destination_id"
                ]
            )
            if session.get(
                "destination_id"
            )
            is not None
            else None
        ),
        requested_by_user_id=(
            int(
                session[
                    "requested_by_user_id"
                ]
            )
            if session.get(
                "requested_by_user_id"
            )
            is not None
            else None
        ),
        action=str(
            session.get(
                "action"
            )
            or "connect"
        ),
        x_user_id=str(
            user["id"]
        ),
        x_username=(
            str(user["username"])
            if user.get(
                "username"
            )
            else None
        ),
        x_display_name=(
            str(user["name"])
            if user.get(
                "name"
            )
            else None
        ),
        access_token_ciphertext=(
            encrypt_x_secret(
                access_token
            )
        ),
        refresh_token_ciphertext=(
            encrypt_x_secret(
                refresh_token
            )
            if refresh_token
            else None
        ),
        token_expires_at=(
            token_expires_at
        ),
        granted_scopes=(
            scopes
            or X_OAUTH_SCOPES
        ),
    )
