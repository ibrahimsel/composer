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

"""Shared helpers for the Composer FastAPI service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple


@dataclass(frozen=True)
class SelectorTerm:
    """Selector key/value filter."""

    key: str
    value: str


def now() -> datetime:
    """Return a timezone-aware timestamp for API responses."""
    return datetime.now(timezone.utc)


def envelope(data: Any, metadata: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Wrap response payloads in the standard API envelope."""
    payload: Dict[str, Any] = {"data": data, "timestamp": now().isoformat()}
    if metadata is not None:
        payload["metadata"] = metadata
    return payload


def build_error(code: str, message: str, details: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Build an error response payload."""
    error: Dict[str, Any] = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {"error": error, "timestamp": now().isoformat()}


def model_dump(model: Any, **kwargs: Any) -> Dict[str, Any]:
    """Serialize Pydantic models across v1 and v2 APIs."""
    if hasattr(model, "model_dump"):
        return model.model_dump(**kwargs)
    return model.dict(**kwargs)


def paginate(items: List[Any], page: int, limit: int) -> Tuple[List[Any], Dict[str, int]]:
    """Paginate a list of items using 1-based page indexing."""
    total_items = len(items)
    if total_items == 0:
        return [], {"page": page, "totalPages": 0, "totalItems": 0}

    total_pages = (total_items + limit - 1) // limit
    start = (page - 1) * limit
    end = start + limit
    return items[start:end], {
        "page": page,
        "totalPages": total_pages,
        "totalItems": total_items,
    }


def parse_selector(selector: str) -> List[SelectorTerm]:
    """Parse a selector string into key/value terms."""
    terms: List[SelectorTerm] = []
    for raw in selector.split("AND"):
        part = raw.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            terms.append(SelectorTerm(key=key, value=value))
    return terms


def selector_matches(tags: Dict[str, str], terms: Iterable[SelectorTerm]) -> bool:
    """Return True if all selector terms match the vehicle tags."""
    for term in terms:
        if tags.get(term.key) != term.value:
            return False
    return True
