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

"""Report API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_store
from api.models import HealthReport, ReconcileReport
from api.storage import InMemoryStore
from api.utils import envelope

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/reconcile")
async def get_reconcile_report(
    vehicle_id: str = Query(alias="vehicleId"),
    store: InMemoryStore = Depends(get_store),
) -> dict:
    report = store.get_reconcile_report(vehicle_id)
    if not report:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "NOT_FOUND",
                "message": "Reconcile report not found",
            },
        )
    return envelope(report)


@router.post("/reconcile")
async def create_reconcile_report(
    payload: ReconcileReport, store: InMemoryStore = Depends(get_store)
) -> dict:
    report = store.set_reconcile_report(payload)
    return envelope(report)


@router.get("/health")
async def get_health_report(
    vehicle_id: str = Query(alias="vehicleId"),
    store: InMemoryStore = Depends(get_store),
) -> dict:
    report = store.get_health_report(vehicle_id)
    if not report:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Health report not found"},
        )
    return envelope(report)


@router.post("/health")
async def create_health_report(
    payload: HealthReport, store: InMemoryStore = Depends(get_store)
) -> dict:
    report = store.set_health_report(payload)
    return envelope(report)
