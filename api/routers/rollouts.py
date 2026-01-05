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

"""Rollout API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from api.dependencies import get_store
from api.models import DeploymentConfig, RolloutStatus
from api.storage import InMemoryStore
from api.utils import envelope, paginate

router = APIRouter(prefix="/rollouts", tags=["Rollouts"])


@router.get("")
async def list_rollouts(
    status: RolloutStatus | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    store: InMemoryStore = Depends(get_store),
) -> dict:
    rollouts = store.list_rollouts(status=status)
    paged, metadata = paginate(rollouts, page, limit)
    return envelope(paged, metadata)


@router.post("")
async def create_rollout(
    payload: DeploymentConfig,
    store: InMemoryStore = Depends(get_store),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    if not payload.selector and not payload.vehicleList:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "BAD_REQUEST",
                "message": "selector or vehicleList is required",
            },
        )
    rollout = store.create_rollout(payload, idempotency_key)
    return envelope(rollout)


@router.get("/{rollout_id}")
async def get_rollout(rollout_id: str, store: InMemoryStore = Depends(get_store)) -> dict:
    rollout = store.get_rollout(rollout_id)
    if not rollout:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Rollout not found"},
        )
    return envelope(rollout)


@router.post("/{rollout_id}/pause")
async def pause_rollout(rollout_id: str, store: InMemoryStore = Depends(get_store)) -> dict:
    try:
        rollout = store.pause_rollout(rollout_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Rollout not found"},
        ) from exc
    return envelope(rollout)


@router.post("/{rollout_id}/rollback")
async def rollback_rollout(rollout_id: str, store: InMemoryStore = Depends(get_store)) -> dict:
    try:
        rollout = store.rollback_rollout(rollout_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Rollout not found"},
        ) from exc
    return envelope(rollout)
