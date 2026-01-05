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

"""Vehicle API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from api.dependencies import get_store
from api.models import (
    VehicleCreateRequest,
    VehicleEventRequest,
    VehicleStatus,
    VehicleStatusUpdate,
    VehicleUpdateRequest,
)
from api.storage import InMemoryStore
from api.utils import envelope, model_dump, paginate

router = APIRouter(prefix="/vehicles", tags=["Vehicles"])


@router.get("")
async def list_vehicles(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    model: str | None = None,
    region: str | None = None,
    ring: str | None = None,
    status: VehicleStatus | None = None,
    search: str | None = None,
    store: InMemoryStore = Depends(get_store),
) -> dict:
    vehicles = store.list_vehicles(
        model=model,
        region=region,
        ring=ring,
        status=status,
        search=search,
    )
    paged, metadata = paginate(vehicles, page, limit)
    return envelope(paged, metadata)


@router.get("/{vehicle_id}")
async def get_vehicle(vehicle_id: str, store: InMemoryStore = Depends(get_store)) -> dict:
    vehicle = store.get_vehicle(vehicle_id)
    if not vehicle:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Vehicle not found"},
        )
    return envelope(vehicle)


@router.post("")
async def create_vehicle(
    payload: VehicleCreateRequest,
    store: InMemoryStore = Depends(get_store),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    try:
        vehicle = store.create_vehicle(model_dump(payload), idempotency_key)
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "CONFLICT", "message": str(exc)},
        ) from exc
    return envelope(vehicle)


@router.patch("/{vehicle_id}")
async def update_vehicle(
    vehicle_id: str,
    payload: VehicleUpdateRequest,
    store: InMemoryStore = Depends(get_store),
) -> dict:
    try:
        vehicle = store.update_vehicle(vehicle_id, payload)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Vehicle not found"},
        ) from exc
    return envelope(vehicle)


@router.post("/{vehicle_id}/status")
async def update_vehicle_status(
    vehicle_id: str,
    payload: VehicleStatusUpdate,
    store: InMemoryStore = Depends(get_store),
) -> dict:
    try:
        vehicle = store.update_vehicle_status(vehicle_id, payload)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Vehicle not found"},
        ) from exc
    return envelope(vehicle)


@router.post("/{vehicle_id}/events")
async def add_vehicle_event(
    vehicle_id: str,
    payload: VehicleEventRequest,
    store: InMemoryStore = Depends(get_store),
) -> dict:
    try:
        vehicle = store.add_vehicle_event(vehicle_id, payload)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Vehicle not found"},
        ) from exc
    return envelope(vehicle)
