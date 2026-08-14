"""Login / logout endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.api.deps import get_app_db, get_optional_user
from app.auth.session import create_session_token
from app.config import settings
from app.db.app_db import AppDB
from app.paths import templates_dir

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory=str(templates_dir()))


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, user=Depends(get_optional_user)):
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None},
    )


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    app_db: AppDB = Depends(get_app_db),
):
    # Strip accidental whitespace (common when pasting credentials)
    username = (username or "").strip()
    password = password or ""

    user = app_db.verify_user(username, password)
    if not user:
        # Use HTTP 200 for HTML form failures. Returning 401 on a browser form
        # POST often triggers abrupt client disconnects on Windows (WinError 10054
        # in asyncio ProactorEventLoop), which is noisy and unhelpful.
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Invalid username or password"},
            status_code=status.HTTP_200_OK,
        )

    token = create_session_token(user)
    resp = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    resp.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_max_age,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return resp


@router.post("/logout")
@router.get("/logout")
async def logout():
    resp = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    resp.delete_cookie(settings.session_cookie_name, path="/")
    return resp
