"""Shared FastAPI dependencies."""
from __future__ import annotations

from fastapi import Header, HTTPException

from backend.core.security import require_audit_token


def verify_audit_access(authorization: str | None = Header(default=None)) -> None:
    """Guard for Node 26 audit endpoints (regulator/auditor bearer token)."""
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    if not require_audit_token(token):
        raise HTTPException(status_code=401, detail="Audit bearer token required (AURAMED_AUDIT_TOKEN).")
