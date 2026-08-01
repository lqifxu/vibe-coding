"""Auth API: register / login / logout / me."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import db
from .auth_service import (
    clear_session_cookie,
    create_access_token,
    get_optional_user,
    hash_password,
    set_session_cookie,
    stripe_configured,
    user_public,
    validate_email,
    validate_password,
    verify_password,
)

router = APIRouter(tags=["auth"])


class AuthBody(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=8, max_length=128)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


@router.post("/api/auth/register")
def register(body: AuthBody, response: Response):
    email = validate_email(body.email)
    password = validate_password(body.password)
    try:
        user = db.create_user(email, hash_password(password))
    except sqlite3.IntegrityError:
        return JSONResponse(status_code=409, content={"detail": "该邮箱已注册，请直接登录"})
    token = create_access_token(int(user["id"]), email)
    set_session_cookie(response, token)
    return user_public(user)


@router.post("/api/auth/login")
def login(body: AuthBody, response: Response):
    email = validate_email(body.email)
    password = validate_password(body.password)
    user = db.get_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        return JSONResponse(status_code=401, content={"detail": "邮箱或密码错误"})
    token = create_access_token(int(user["id"]), email)
    set_session_cookie(response, token)
    return user_public(user)


@router.post("/api/auth/logout")
def logout(response: Response):
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/api/auth/me")
def me(request: Request):
    user = get_optional_user(request)
    if not user:
        return {
            "authenticated": False,
            "is_vip": False,
            "stripe_configured": stripe_configured(),
        }
    data = user_public(user, client_ip=_client_ip(request))
    data["authenticated"] = True
    data["stripe_configured"] = stripe_configured()
    return data
