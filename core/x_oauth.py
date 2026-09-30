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

X_TOKEN_REFRESH_SKEW_SECONDS = int(
    os.getenv(
        "X_TOKEN_REFRESH_SKEW_SECONDS",
        "60",
    )
)


# =========================================================
# RESULT MODELS
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


@dataclass(frozen=True)
class XOAuthRefreshResult:
    destination_id: int
    access_token: str
    access_token_ciphertext: str
    refresh_token_ciphertext: Optional[str]
    token_expires_at: Optional[float]
    granted_scopes: tuple[str, ...]


class XOAuthRefreshError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        reconnect_required: bool = False,
    ):
        super().__init__(message)
        self.reconnect_required = bool(
            reconnect_required
        )


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
# TOKEN REQUEST HELPERS
# =========================================================

def _token_request_auth_and_client(
    data: Dict[str, Any],
):
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

    return auth


def _parse_scopes(
    raw_scope: Any,
    *,
    fallback=(),
) -> tuple[str, ...]:
    scopes = tuple(
        item
        for item in (
            str(
                raw_scope
                or ""
            )
            .replace(",", " ")
            .split()
        )
        if item
    )

    if scopes:
        return scopes

    return tuple(
        item
        for item in fallback
        if item
    )


def _token_expiry_from_payload(
    payload: Dict[str, Any],
) -> Optional[float]:
    expires_in = payload.get(
        "expires_in"
    )

    if expires_in is None:
        return None

    try:
        return (
            time.time()
            + float(expires_in)
        )
    except (
        TypeError,
        ValueError,
    ):
        return None


# =========================================================
# AUTHORIZATION CODE EXCHANGE
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

    auth = _token_request_auth_and_client(
        data
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
# REFRESH TOKEN EXCHANGE
# =========================================================

def _refresh_tokens(
    *,
    refresh_token: str,
) -> Dict[str, Any]:
    if not refresh_token:
        raise XOAuthRefreshError(
            "X refresh token is missing",
            reconnect_required=True,
        )

    data = {
        "grant_type": (
            "refresh_token"
        ),
        "refresh_token": str(
            refresh_token
        ),
    }

    auth = _token_request_auth_and_client(
        data
    )

    try:
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
    except requests.RequestException as exc:
        raise XOAuthRefreshError(
            "X token refresh request failed",
            reconnect_required=False,
        ) from exc

    payload = {}

    try:
        payload = response.json() or {}
    except Exception:
        payload = {}

    if response.status_code >= 400:
        error_code = str(
            payload.get("error")
            or ""
        ).strip().lower()

        reconnect_required = (
            response.status_code == 401
            or error_code
            in {
                "invalid_grant",
                "invalid_token",
                "unauthorized_client",
            }
        )

        logger.warning(
            "X OAuth token refresh failed | "
            "status=%s | error=%s | body=%s",
            response.status_code,
            error_code or "unknown",
            response.text[:500],
        )

        raise XOAuthRefreshError(
            "X OAuth token refresh failed",
            reconnect_required=(
                reconnect_required
            ),
        )

    access_token = str(
        payload.get(
            "access_token"
        )
        or ""
    ).strip()

    if not access_token:
        raise XOAuthRefreshError(
            "X refresh response did not contain an access token",
            reconnect_required=True,
        )

    return payload


def refresh_x_oauth_connection(
    destination_id: int,
) -> XOAuthRefreshResult:
    """
    Refresh one persisted X OAuth connection.

    Transient network/server failures do not force reconnect.
    Invalid/revoked refresh credentials move the connection to
    reconnect_required.
    """
    _require_config()

    from core.database import (
        get_x_oauth_connection,
        update_x_oauth_connection_status,
        upsert_x_oauth_connection,
    )

    destination_id = int(
        destination_id
    )

    connection = (
        get_x_oauth_connection(
            destination_id
        )
    )

    if not connection:
        raise XOAuthRefreshError(
            "X OAuth connection was not found",
            reconnect_required=True,
        )

    connection_status = str(
        connection.get(
            "connection_status"
        )
        or ""
    ).strip().lower()

    if connection_status == "disconnected":
        raise XOAuthRefreshError(
            "X OAuth connection is disconnected",
            reconnect_required=True,
        )

    refresh_ciphertext = str(
        connection.get(
            "refresh_token_ciphertext"
        )
        or ""
    ).strip()

    if not refresh_ciphertext:
        update_x_oauth_connection_status(
            destination_id,
            "reconnect_required",
            last_error=(
                "missing_refresh_token"
            ),
        )

        raise XOAuthRefreshError(
            "X refresh token is missing",
            reconnect_required=True,
        )

    try:
        refresh_token = (
            decrypt_x_secret(
                refresh_ciphertext
            )
        )
    except Exception as exc:
        update_x_oauth_connection_status(
            destination_id,
            "reconnect_required",
            last_error=(
                "refresh_token_decrypt_failed"
            ),
        )

        raise XOAuthRefreshError(
            "X refresh token could not be decrypted",
            reconnect_required=True,
        ) from exc

    try:
        payload = _refresh_tokens(
            refresh_token=(
                refresh_token
            )
        )
    except XOAuthRefreshError as exc:
        if exc.reconnect_required:
            update_x_oauth_connection_status(
                destination_id,
                "reconnect_required",
                last_error=str(exc),
            )

        raise

    access_token = str(
        payload.get(
            "access_token"
        )
        or ""
    ).strip()

    returned_refresh_token = str(
        payload.get(
            "refresh_token"
        )
        or ""
    ).strip()

    if returned_refresh_token:
        refresh_token_ciphertext = (
            encrypt_x_secret(
                returned_refresh_token
            )
        )
    else:
        # Some OAuth servers do not rotate refresh tokens on every refresh.
        # Keep the existing encrypted token in that case.
        refresh_token_ciphertext = (
            refresh_ciphertext
        )

    access_token_ciphertext = (
        encrypt_x_secret(
            access_token
        )
    )

    token_expires_at = (
        _token_expiry_from_payload(
            payload
        )
    )

    existing_scopes = (
        connection.get(
            "granted_scopes"
        )
        or ()
    )

    if isinstance(
        existing_scopes,
        str,
    ):
        existing_scopes = (
            existing_scopes
            .replace(",", " ")
            .split()
        )

    granted_scopes = _parse_scopes(
        payload.get(
            "scope"
        ),
        fallback=(
            existing_scopes
            or X_OAUTH_SCOPES
        ),
    )

    persisted = (
        upsert_x_oauth_connection(
            destination_id=destination_id,
            workspace_id=int(
                connection[
                    "workspace_id"
                ]
            ),
            connected_by_user_id=(
                int(
                    connection[
                        "connected_by_user_id"
                    ]
                )
                if connection.get(
                    "connected_by_user_id"
                )
                is not None
                else None
            ),
            x_user_id=str(
                connection[
                    "x_user_id"
                ]
            ),
            x_username=(
                str(
                    connection[
                        "x_username"
                    ]
                )
                if connection.get(
                    "x_username"
                )
                else None
            ),
            x_display_name=(
                str(
                    connection[
                        "x_display_name"
                    ]
                )
                if connection.get(
                    "x_display_name"
                )
                else None
            ),
            access_token_ciphertext=(
                access_token_ciphertext
            ),
            refresh_token_ciphertext=(
                refresh_token_ciphertext
            ),
            token_expires_at=(
                token_expires_at
            ),
            granted_scopes=(
                granted_scopes
            ),
            connection_status="connected",
            last_error=None,
        )
    )

    if not persisted:
        raise XOAuthRefreshError(
            "Refreshed X OAuth connection could not be persisted",
            reconnect_required=False,
        )

    logger.info(
        "X OAuth token refreshed | destination=%s",
        destination_id,
    )

    return XOAuthRefreshResult(
        destination_id=(
            destination_id
        ),
        access_token=(
            access_token
        ),
        access_token_ciphertext=(
            access_token_ciphertext
        ),
        refresh_token_ciphertext=(
            refresh_token_ciphertext
        ),
        token_expires_at=(
            token_expires_at
        ),
        granted_scopes=(
            granted_scopes
        ),
    )


def get_valid_x_access_token(
    destination_id: int,
    *,
    min_ttl_seconds: Optional[int] = None,
) -> str:
    """
    Return a usable plaintext access token for one X destination.

    The plaintext token exists only in process memory. If the persisted token
    is near expiry or already expired, refresh it first.
    """
    _require_config()

    from core.database import (
        get_x_oauth_connection,
    )

    destination_id = int(
        destination_id
    )

    connection = (
        get_x_oauth_connection(
            destination_id
        )
    )

    if not connection:
        raise XOAuthRefreshError(
            "X OAuth connection was not found",
            reconnect_required=True,
        )

    status = str(
        connection.get(
            "connection_status"
        )
        or ""
    ).strip().lower()

    if status != "connected":
        raise XOAuthRefreshError(
            "X OAuth connection requires reconnect",
            reconnect_required=True,
        )

    ttl = (
        int(min_ttl_seconds)
        if min_ttl_seconds
        is not None
        else int(
            X_TOKEN_REFRESH_SKEW_SECONDS
        )
    )

    expires_at = connection.get(
        "token_expires_at"
    )

    should_refresh = False

    if expires_at is not None:
        try:
            should_refresh = (
                float(expires_at)
                <= (
                    time.time()
                    + max(
                        0,
                        ttl,
                    )
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            should_refresh = True

    access_ciphertext = str(
        connection.get(
            "access_token_ciphertext"
        )
        or ""
    ).strip()

    if not access_ciphertext:
        should_refresh = True

    if should_refresh:
        refreshed = (
            refresh_x_oauth_connection(
                destination_id
            )
        )

        return (
            refreshed.access_token
        )

    try:
        return decrypt_x_secret(
            access_ciphertext
        )
    except Exception:
        refreshed = (
            refresh_x_oauth_connection(
                destination_id
            )
        )

        return (
            refreshed.access_token
        )


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

    token_expires_at = (
        _token_expiry_from_payload(
            token_payload
        )
    )

    scopes = _parse_scopes(
        token_payload.get(
            "scope"
        ),
        fallback=(
            X_OAUTH_SCOPES
        ),
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
