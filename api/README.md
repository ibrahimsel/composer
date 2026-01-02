# Composer API (FastAPI)

This service provides the MVP backend API for the fleet dashboard. It runs
entirely in-memory by default, with deterministic seed data so the UI is
usable without a large fleet.

## Run Locally

```bash
PYTHONPATH=src/composer uvicorn api.app:app --reload --host 0.0.0.0 --port 8080
```

Or with the helper entrypoint:

```bash
PYTHONPATH=src/composer python -m api.main
```

Cors stuff:

```bash
MUTO_API_CORS_ORIGINS=http://localhost:3001 \
MUTO_API_CORS_CREDENTIALS=false \
PYTHONPATH=src/composer uvicorn api.app:app --reload --host 0.0.0.0 --port 8080
```

## Install Dependencies

```bash
python3 -m pip install --user -r src/composer/requirements.txt
```

## Environment Variables

- `MUTO_API_SEED`: Enable seed data (default: `true`).
- `MUTO_API_SEED_COUNT`: Number of seed vehicles (default: `12`).
- `MUTO_API_PAGE_SIZE`: Default page size (default: `20`).
- `MUTO_API_MAX_PAGE_SIZE`: Max page size (default: `200`).
- `MUTO_API_CORS_ORIGINS`: Comma-separated origins (default: `*`).
- `MUTO_API_CORS_CREDENTIALS`: Allow credentials (default: `false`).
- `MUTO_API_HOST`: Bind host (default: `0.0.0.0`).
- `MUTO_API_PORT`: Bind port (default: `8080`).
- `MUTO_API_RELOAD`: Enable uvicorn reload (default: `false`).

## Notes

- Data is stored in-memory only. Restarting the API resets state.
- Agents can update vehicle status and reports via the POST report endpoints.
- The UI can poll list and detail endpoints on a local dev instance.
