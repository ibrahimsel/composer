"""Shared FastAPI dependencies."""

from fastapi import Request

from api.storage import InMemoryStore


def get_store(request: Request) -> InMemoryStore:
    """Return the in-memory store bound to the app state."""
    return request.app.state.store
