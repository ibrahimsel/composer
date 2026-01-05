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

"""Release API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from api.dependencies import get_store
from api.models import ReleaseRequest
from api.storage import InMemoryStore
from api.utils import envelope, paginate

router = APIRouter(prefix="/releases", tags=["Releases"])


@router.get("")
async def list_releases(
    stack: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    store: InMemoryStore = Depends(get_store),
) -> dict:
    releases = store.list_releases(stack=stack)
    paged, metadata = paginate(releases, page, limit)
    return envelope(paged, metadata)


@router.get("/{stack}/{version}")
async def get_release(
    stack: str,
    version: str,
    store: InMemoryStore = Depends(get_store),
) -> dict:
    release = store.get_release(stack, version)
    if not release:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Release not found"},
        )
    return envelope(release)


@router.post("")
async def create_release(
    payload: ReleaseRequest,
    store: InMemoryStore = Depends(get_store),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    release = store.create_release(payload, idempotency_key)
    return envelope(release)
