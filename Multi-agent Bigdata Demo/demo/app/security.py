from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from fastapi import HTTPException, Request, status


ALL_PRODUCTION_ROLES = frozenset(
    {
        "developer",
        "artifact_reviewer",
        "release_manager",
        "cloud_operator",
        "auditor",
        "admin",
    }
)


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def production_mode_enabled() -> bool:
    return env_flag("SAT_PRODUCTION_MODE")


def cloud_execution_enabled() -> bool:
    return production_mode_enabled() and env_flag("SAT_CLOUD_EXECUTION_ENABLED")


@dataclass(frozen=True)
class Principal:
    subject: str
    roles: frozenset[str]
    authenticated: bool
    auth_mode: str

    def has_any_role(self, allowed: set[str] | frozenset[str]) -> bool:
        return "admin" in self.roles or bool(self.roles.intersection(allowed))

    def as_dict(self) -> dict[str, object]:
        return {
            "subject": self.subject,
            "roles": sorted(self.roles),
            "authenticated": self.authenticated,
            "auth_mode": self.auth_mode,
        }


def _authorization_token(request: Request) -> str:
    value = request.headers.get("authorization", "").strip()
    if not value.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A bearer token is required.",
        )
    token = value[7:].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A bearer token is required.",
        )
    return token


def _jwt_principal(request: Request) -> Principal:
    try:
        import jwt
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT authentication dependencies are not installed.",
        ) from exc

    token = _authorization_token(request)
    algorithm = os.getenv("SAT_JWT_ALGORITHM", "RS256").strip()
    audience = os.getenv("SAT_JWT_AUDIENCE", "").strip() or None
    issuer = os.getenv("SAT_JWT_ISSUER", "").strip() or None
    jwks_url = os.getenv("SAT_JWT_JWKS_URL", "").strip()
    verification_key = os.getenv("SAT_JWT_PUBLIC_KEY", "").replace("\\n", "\n").strip()
    if jwks_url:
        verification_key = jwt.PyJWKClient(jwks_url).get_signing_key_from_jwt(token).key
    if not verification_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT verification is not configured.",
        )

    options = {"require": ["exp", "sub"]}
    try:
        payload = jwt.decode(
            token,
            verification_key,
            algorithms=[algorithm],
            audience=audience,
            issuer=issuer,
            options=options,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The bearer token is invalid or expired.",
        ) from exc

    role_claim = os.getenv("SAT_JWT_ROLE_CLAIM", "roles").strip()
    raw_roles = payload.get(role_claim, [])
    if isinstance(raw_roles, str):
        raw_roles = raw_roles.replace(",", " ").split()
    roles = frozenset(str(role).strip() for role in raw_roles if str(role).strip())
    return Principal(
        subject=str(payload["sub"]),
        roles=roles,
        authenticated=True,
        auth_mode="jwt",
    )


def _trusted_header_principal(request: Request) -> Principal:
    subject_header = os.getenv("SAT_TRUSTED_USER_HEADER", "X-SAT-User")
    roles_header = os.getenv("SAT_TRUSTED_ROLES_HEADER", "X-SAT-Roles")
    subject = request.headers.get(subject_header, "").strip()
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The trusted identity header is missing.",
        )
    roles = frozenset(
        role.strip()
        for role in request.headers.get(roles_header, "").replace(",", " ").split()
        if role.strip()
    )
    return Principal(
        subject=subject,
        roles=roles,
        authenticated=True,
        auth_mode="trusted_header",
    )


def current_principal(request: Request) -> Principal:
    if not production_mode_enabled():
        return Principal(
            subject="local_operator",
            roles=ALL_PRODUCTION_ROLES,
            authenticated=False,
            auth_mode="poc",
        )

    auth_mode = os.getenv("SAT_AUTH_MODE", "disabled").strip().lower()
    if auth_mode == "jwt":
        return _jwt_principal(request)
    if auth_mode == "trusted_header":
        return _trusted_header_principal(request)
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Production mode requires SAT_AUTH_MODE=jwt or trusted_header.",
    )


def require_roles(*roles: str) -> Callable[[Request], Principal]:
    allowed = frozenset(roles)

    def dependency(request: Request) -> Principal:
        principal = current_principal(request)
        if not principal.has_any_role(allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"One of these roles is required: {', '.join(sorted(allowed))}.",
            )
        return principal

    return dependency


def auth_summary(request: Request) -> dict[str, object]:
    principal = current_principal(request)
    return {
        **principal.as_dict(),
        "production_mode": production_mode_enabled(),
        "cloud_execution_enabled": cloud_execution_enabled(),
        "permissions": {
            "create_run": principal.has_any_role({"developer"}),
            "review_artifact": principal.has_any_role({"artifact_reviewer"}),
            "release": principal.has_any_role({"release_manager"}),
            "approve_execution": principal.has_any_role({"cloud_operator"}),
            "audit": principal.has_any_role({"auditor"}),
        },
    }
