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

"""Desired state API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from api.dependencies import get_store
from api.models import DesiredStateRequest
from api.storage import InMemoryStore
from api.utils import envelope

router = APIRouter(prefix="/desired-states", tags=["DesiredStates"])


@router.post("")
async def create_desired_state(
    payload: DesiredStateRequest,
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
    desired_state = store.create_desired_state(payload, idempotency_key)
    return envelope(desired_state)


@router.get("/{revision}")
async def get_desired_state(revision: str, store: InMemoryStore = Depends(get_store)) -> dict:
    desired_state = store.get_desired_state(revision)
    if not desired_state:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Desired state not found"},
        )
    return envelope(desired_state)


@router.get("/latest")
async def get_latest_desired_state(
    vehicle_id: str = Query(alias="vehicleId"),
    store: InMemoryStore = Depends(get_store),
) -> dict:
    desired_state = store.get_latest_desired_state(vehicle_id)
    if not desired_state:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Desired state not found"},
        )
    return envelope(desired_state)
