"""Azure Function HTTP API for the readmission-risk scoring service.

Implements the contract defined in ``docs/api-design.md``:

- ``GET  /api/v1/health``       - unauthenticated liveness probe
- ``POST /api/v1/score``         - score a single encounter
- ``POST /api/v1/score/batch``   - score a batch of encounters (max 100)

Authentication: Azure AD (Entra ID) bearer tokens are validated against the
configured tenant and audience (OAuth2 client-credentials flow). The function
then calls the AML Managed Online Endpoint using a key retrieved from Key
Vault via the function's system-assigned managed identity.

Required application settings (see ``local.settings.json`` for local dev
placeholders):

- ``AAD_TENANT_ID``        - Azure AD tenant ID used to validate tokens
- ``AAD_API_AUDIENCE``      - expected token audience, e.g. ``api://hcai-readmission-api``
- ``AML_ENDPOINT_URL``      - scoring URL of the AML managed online endpoint
- ``KEY_VAULT_URI``         - e.g. ``https://kv-hcai-dev.vault.azure.net/``
- ``AML_ENDPOINT_KEY_SECRET_NAME`` - Key Vault secret name holding the AML endpoint key
- ``RATE_LIMIT_RPM``        - requests/minute per caller (default: 60)
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections import defaultdict

import azure.functions as func
import requests
from pydantic import ValidationError

from src.common.schemas import ScoringRequest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hcai.function_app")

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

MAX_BATCH_SIZE = 100

# In-memory token-bucket rate limiter, keyed by AAD app id (`appid` claim).
# NOTE: per-instance only; for multi-instance prod deployments, back this
# with Redis or Azure Cache for Redis (see docs/api-design.md §7).
_request_log: dict[str, list[float]] = defaultdict(list)


# ---------------------------------------------------------------------------
# Auth & rate limiting
# ---------------------------------------------------------------------------


class AuthError(Exception):
    def __init__(self, status_code: int, error: str):
        self.status_code = status_code
        self.error = error
        super().__init__(error)


def _get_jwks_client():
    """Return a cached PyJWK client for the configured AAD tenant."""
    import jwt

    tenant_id = os.environ["AAD_TENANT_ID"]
    jwks_url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    return jwt.PyJWKClient(jwks_url)


def validate_token(authorization_header: str | None) -> dict:
    """Validate the ``Authorization: Bearer <token>`` header against AAD.

    Returns the decoded token claims on success.

    Raises:
        AuthError: with status 401 (missing/invalid/expired token) or 403
            (valid token but missing the required scope/role).
    """
    import jwt

    if not authorization_header or not authorization_header.startswith("Bearer "):
        raise AuthError(401, "unauthorized")

    token = authorization_header.removeprefix("Bearer ").strip()
    tenant_id = os.environ["AAD_TENANT_ID"]
    audience = os.environ["AAD_API_AUDIENCE"]

    try:
        jwks_client = _get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=f"https://login.microsoftonline.com/{tenant_id}/v2.0",
        )
    except jwt.PyJWTError as exc:
        logger.warning("token_validation_failed", extra={"error": str(exc)})
        raise AuthError(401, "unauthorized") from exc

    required_scope = "Score.Invoke"
    scopes = claims.get("scp", "").split() + claims.get("roles", [])
    if required_scope not in scopes:
        raise AuthError(403, "forbidden")

    return claims


def check_rate_limit(client_id: str) -> int | None:
    """Return seconds-to-retry if ``client_id`` has exceeded its rate limit, else ``None``."""
    limit = int(os.environ.get("RATE_LIMIT_RPM", "60"))
    now = time.time()
    window_start = now - 60

    history = [t for t in _request_log[client_id] if t > window_start]
    _request_log[client_id] = history

    if len(history) >= limit:
        oldest = min(history)
        return max(1, int(60 - (now - oldest)))

    history.append(now)
    return None


# ---------------------------------------------------------------------------
# AML endpoint client
# ---------------------------------------------------------------------------


_aml_key_cache: dict[str, str] = {}


def _get_aml_endpoint_key() -> str:
    """Fetch the AML endpoint key from Key Vault (cached for the instance lifetime)."""
    if "key" in _aml_key_cache:
        return _aml_key_cache["key"]

    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient

    vault_uri = os.environ["KEY_VAULT_URI"]
    secret_name = os.environ.get("AML_ENDPOINT_KEY_SECRET_NAME", "aml-endpoint-key")

    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=vault_uri, credential=credential)
    key = client.get_secret(secret_name).value

    _aml_key_cache["key"] = key
    return key


def invoke_aml_endpoint(payload: dict, request_id: str) -> dict:
    """Call the AML managed online endpoint's scoring URL."""
    endpoint_url = os.environ["AML_ENDPOINT_URL"]
    key = _get_aml_endpoint_key()

    response = requests.post(
        endpoint_url,
        json=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "x-request-id": request_id,
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route(route="v1/health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    """Unauthenticated liveness probe (docs/api-design.md §3.3)."""
    body = {
        "status": "healthy",
        "model_version": os.environ.get("MODEL_VERSION", "readmission-risk-model:latest"),
    }
    return func.HttpResponse(json.dumps(body), status_code=200, mimetype="application/json")


@app.route(route="v1/score", methods=["POST"])
def score(req: func.HttpRequest) -> func.HttpResponse:
    """Score a single encounter (docs/api-design.md §3.1)."""
    request_id = req.headers.get("x-request-id", str(uuid.uuid4()))

    try:
        claims = validate_token(req.headers.get("Authorization"))
    except AuthError as exc:
        return _error_response(exc.status_code, exc.error, request_id)

    retry_after = check_rate_limit(claims.get("appid", "unknown"))
    if retry_after is not None:
        return func.HttpResponse(
            json.dumps({"error": "rate_limited", "retry_after_seconds": retry_after}),
            status_code=429,
            mimetype="application/json",
            headers={"x-request-id": request_id},
        )

    try:
        body = req.get_json()
        ScoringRequest(**body)  # raises pydantic.ValidationError on bad input
    except (ValueError, ValidationError) as exc:
        return _error_response(400, "validation_error", request_id, details=str(exc))

    try:
        result = invoke_aml_endpoint(body, request_id)
    except requests.RequestException as exc:
        logger.error("aml_endpoint_error", extra={"error": str(exc), "request_id": request_id})
        return _error_response(503, "service_unavailable", request_id)

    return func.HttpResponse(json.dumps(result), status_code=200, mimetype="application/json", headers={"x-request-id": request_id})


@app.route(route="v1/score/batch", methods=["POST"])
def score_batch(req: func.HttpRequest) -> func.HttpResponse:
    """Score a batch of encounters, max ``MAX_BATCH_SIZE`` items (docs/api-design.md §3.2)."""
    request_id = req.headers.get("x-request-id", str(uuid.uuid4()))

    try:
        claims = validate_token(req.headers.get("Authorization"))
    except AuthError as exc:
        return _error_response(exc.status_code, exc.error, request_id)

    try:
        body = req.get_json()
        items = body["data"]
        if not isinstance(items, list) or not items:
            raise ValueError("'data' must be a non-empty array")
        if len(items) > MAX_BATCH_SIZE:
            raise ValueError(f"batch size {len(items)} exceeds max of {MAX_BATCH_SIZE}")
        for item in items:
            ScoringRequest(**item)
    except (ValueError, ValidationError, KeyError, TypeError) as exc:
        return _error_response(400, "validation_error", request_id, details=str(exc))

    retry_after = check_rate_limit(claims.get("appid", "unknown"))
    if retry_after is not None:
        return func.HttpResponse(
            json.dumps({"error": "rate_limited", "retry_after_seconds": retry_after}),
            status_code=429,
            mimetype="application/json",
            headers={"x-request-id": request_id},
        )

    try:
        result = invoke_aml_endpoint({"data": items}, request_id)
    except requests.RequestException as exc:
        logger.error("aml_endpoint_error", extra={"error": str(exc), "request_id": request_id})
        return _error_response(503, "service_unavailable", request_id)

    return func.HttpResponse(json.dumps(result), status_code=200, mimetype="application/json", headers={"x-request-id": request_id})


def _error_response(status_code: int, error: str, request_id: str, details: str | None = None) -> func.HttpResponse:
    body: dict = {"error": error, "request_id": request_id}
    if details:
        body["details"] = details
    return func.HttpResponse(json.dumps(body), status_code=status_code, mimetype="application/json", headers={"x-request-id": request_id})
