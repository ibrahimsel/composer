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

"""Audit log API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.dependencies import get_store
from api.storage import InMemoryStore
from api.utils import envelope, paginate

router = APIRouter(prefix="/audit-log", tags=["Audit"])


@router.get("")
async def list_audit_log(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    actor: str | None = None,
    action: str | None = None,
    correlation_id: str | None = Query(default=None, alias="correlationId"),
    store: InMemoryStore = Depends(get_store),
) -> dict:
    entries = store.list_audit_log(actor=actor, action=action)
    if correlation_id:
        entries = [entry for entry in entries if entry.get("correlationId") == correlation_id]
    paged, metadata = paginate(entries, page, limit)
    return envelope(paged, metadata)
