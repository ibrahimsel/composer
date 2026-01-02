#
# Copyright (c) 2025 Composiv.ai
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# http://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0
#
# Contributors:
#   Composiv.ai - initial API and implementation
#

"""FastAPI application setup for the Composer API."""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi import HTTPException

from api.config import Settings
from api.routers import (
    audit,
    desired_states,
    releases,
    reports,
    rollouts,
    vehicles,
)
from api.storage import InMemoryStore
from api.utils import build_error, envelope

API_PREFIX = "/api/v1"


def create_app(
    seed_data: Optional[bool] = None, seed_count: Optional[int] = None
) -> FastAPI:
    """Create and configure the FastAPI app."""
    settings = Settings()
    if seed_data is None:
        seed_data = settings.seed_enabled
    if seed_count is None:
        seed_count = settings.seed_count

    app = FastAPI(title=settings.app_name, version=settings.api_version)

    cors_origins = settings.cors_origins
    allow_credentials = settings.cors_allow_credentials
    if "*" in cors_origins:
        allow_credentials = False

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=allow_credentials,
    )
    app.state.store = InMemoryStore(seed_data=seed_data, seed_count=seed_count)

    app.include_router(vehicles.router, prefix=API_PREFIX)
    app.include_router(desired_states.router, prefix=API_PREFIX)
    app.include_router(releases.router, prefix=API_PREFIX)
    app.include_router(rollouts.router, prefix=API_PREFIX)
    app.include_router(reports.router, prefix=API_PREFIX)
    app.include_router(audit.router, prefix=API_PREFIX)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        _request: Request, exc: HTTPException
    ) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and "error" in detail:
            payload = detail
        elif isinstance(detail, dict) and "code" in detail:
            payload = build_error(
                detail.get("code", "HTTP_ERROR"),
                detail.get("message", "Request failed"),
                detail.get("details"),
            )
        else:
            payload = build_error("HTTP_ERROR", str(detail))
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        payload = build_error(
            "BAD_REQUEST",
            "Request validation failed",
            {"errors": exc.errors()},
        )
        return JSONResponse(status_code=400, content=payload)

    @app.get(f"{API_PREFIX}/healthz")
    async def health_check() -> dict:
        return envelope({"status": "ok"})

    return app


app = create_app()
